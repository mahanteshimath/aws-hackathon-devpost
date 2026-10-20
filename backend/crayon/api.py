"""HTTP API + static hosting, framework-free so the same code runs in the local dev server and AWS Lambda."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import quote

from . import generator, universe
from .config import settings
from .storage import LocalStorage, store

log = logging.getLogger("crayon.api")

MAX_UPLOAD = 8 * 1024 * 1024
MAX_STORIES_PER_SESSION = 8
DAILY_STORY_LIMIT = int(os.environ.get("CRAYON_DAILY_LIMIT", "150"))  # cost guard for a public endpoint
CODE_ALPHABET = "ACDEFHJKMNPRTUVWXY3479"  # no look-alike characters
ID_RE = re.compile(r"^[a-f0-9]{16,64}$")


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> dict:
        if not self.body:
            return {}
        try:
            data = json.loads(self.body)
        except ValueError:
            raise HttpError(400, "invalid JSON")
        if not isinstance(data, dict):
            raise HttpError(400, "expected a JSON object")
        return data

    @property
    def base_url(self) -> str:
        if settings().public_url:
            return settings().public_url
        proto = self.headers.get("x-forwarded-proto", "http")
        return f"{proto}://{self.headers.get('host', 'localhost')}"


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def json_response(obj: Any, status: int = 200) -> Response:
    return Response(status, json.dumps(obj).encode(), {"content-type": "application/json", "cache-control": "no-store"})


# --------------------------------------------------------------------------- launcher

def start_generation(story_id: str) -> None:
    """Kick off story generation without blocking the HTTP response."""
    cfg = settings()
    if cfg.agentcore_runtime_arn:
        _invoke_agentcore(story_id)
    elif os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        import boto3

        boto3.client("lambda", region_name=cfg.region).invoke(
            FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
            InvocationType="Event",
            Payload=json.dumps({"crayon_job": story_id}).encode(),
        )
    else:
        threading.Thread(target=generator.generate_story, args=(story_id,), daemon=True).start()


def _invoke_agentcore(story_id: str) -> None:
    import boto3

    cfg = settings()
    client = boto3.client("bedrock-agentcore", region_name=cfg.region)
    client.invoke_agent_runtime(
        agentRuntimeArn=cfg.agentcore_runtime_arn,
        runtimeSessionId=f"crayon-story-{story_id}".ljust(40, "0"),  # must be >= 33 chars
        payload=json.dumps({"story_id": story_id}).encode(),
        contentType="application/json",
        accept="application/json",
    )


# --------------------------------------------------------------------------- helpers

def _session_key(sid: str) -> str:
    return f"sessions/{sid}.json"


def _load_session(sid: str) -> dict:
    if not ID_RE.match(sid):
        raise HttpError(404, "session not found")
    session = store().get_json(_session_key(sid))
    if not session:
        raise HttpError(404, "session not found")
    return session


def _load_story(story_id: str) -> dict:
    if not ID_RE.match(story_id):
        raise HttpError(404, "story not found")
    doc = store().get_json(generator.story_key(story_id))
    if not doc:
        raise HttpError(404, "story not found")
    return doc


def _url(key: str | None) -> str | None:
    return store().url(key) if key else None


def public_story(doc: dict) -> dict:
    """Story as the TV sees it: storage keys swapped for URLs, internal fields removed."""
    out = {k: v for k, v in doc.items() if k not in {"image_key", "session_id"}}
    if doc.get("character"):
        ch = dict(doc["character"])
        ch["sprite_url"] = _url(ch.pop("sprite_key", None))
        ch["greeting_audio_url"] = _url(ch.pop("greeting_audio_key", None))
        out["character"] = ch
    pages = {}
    for pid, page in (doc.get("pages") or {}).items():
        p = {k: v for k, v in page.items() if k not in {"scene", "bg_key", "audio_key"}}
        p["bg_url"] = _url(page.get("bg_key"))
        p["audio_url"] = _url(page.get("audio_key"))
        pages[pid] = p
    out["pages"] = pages
    return out


def _is_image(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


# --------------------------------------------------------------------------- handlers

def h_config(req: Request) -> Response:
    cfg = settings()
    return json_response({"mode": cfg.mode, "storage": cfg.storage, "agentcore": bool(cfg.agentcore_runtime_arn)})


def h_create_session(req: Request) -> Response:
    body = req.json()
    household_id = str(body.get("household_id") or "")
    if not ID_RE.match(household_id):
        household_id = secrets.token_hex(12)
    sid = secrets.token_hex(16)
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    session = {
        "session_id": sid,
        "household_id": household_id,
        "code": code,
        "created_at": time.time(),
        "phone_connected": False,
        "story_ids": [],
    }
    store().put_json(_session_key(sid), session)
    store().put_json(f"codes/{code}.json", {"session_id": sid, "created_at": time.time()})
    phone_url = f"{req.base_url}/phone/?s={sid}"
    return json_response({**session, "phone_url": phone_url, "qr_url": f"/api/sessions/{sid}/qr.svg"})


def h_get_session(req: Request, sid: str) -> Response:
    session = _load_session(sid)
    latest = None
    if session["story_ids"]:
        doc = store().get_json(generator.story_key(session["story_ids"][-1])) or {}
        latest = {"story_id": doc.get("story_id"), "status": doc.get("status")}
    return json_response({"session_id": sid, "phone_connected": session["phone_connected"], "latest": latest, "code": session["code"]})


def h_qr(req: Request, sid: str) -> Response:
    import qrcode
    import qrcode.image.svg

    _load_session(sid)
    img = qrcode.make(f"{req.base_url}/phone/?s={sid}", image_factory=qrcode.image.svg.SvgPathImage, border=2)
    return Response(200, img.to_string(), {"content-type": "image/svg+xml", "cache-control": "no-store"})


def h_hello(req: Request, sid: str) -> Response:
    session = _load_session(sid)
    if not session["phone_connected"]:
        session["phone_connected"] = True
        store().put_json(_session_key(sid), session)
    return json_response({"ok": True, "household_id": session["household_id"]})


def h_code(req: Request, code: str) -> Response:
    rec = store().get_json(f"codes/{code.upper()[:4]}.json") if re.fullmatch(r"[A-Za-z0-9]{4}", code) else None
    if not rec or time.time() - rec["created_at"] > 24 * 3600:
        raise HttpError(404, "code not found")
    return json_response({"session_id": rec["session_id"]})


def _take_daily_slot() -> None:
    """Best-effort global daily cap so a public URL cannot run up the AWS bill."""
    key = f"limits/{time.strftime('%Y-%m-%d', time.gmtime())}.json"
    rec = store().get_json(key) or {"count": 0}
    if rec["count"] >= DAILY_STORY_LIMIT:
        raise HttpError(429, "The story machine is resting for today. Please try again tomorrow!")
    rec["count"] += 1
    store().put_json(key, rec)


def h_create_story(req: Request, sid: str) -> Response:
    session = _load_session(sid)
    if len(session["story_ids"]) >= MAX_STORIES_PER_SESSION:
        raise HttpError(429, "story limit reached for this session")
    if not req.body or len(req.body) > MAX_UPLOAD:
        raise HttpError(413 if req.body else 400, "send one image up to 8 MB")
    ext = _is_image(req.body)
    if not ext:
        raise HttpError(415, "image must be JPEG, PNG or WebP")
    _take_daily_slot()
    image_key = f"drawings/{sid}/{secrets.token_hex(8)}.{ext}"
    store().put_bytes(image_key, req.body, f"image/{'jpeg' if ext == 'jpg' else ext}")
    doc = generator.create_story_record(
        session_id=sid,
        household_id=session["household_id"],
        image_key=image_key,
        kid_name=req.query.get("kid_name", ""),
        theme=req.query.get("theme", "surprise"),
        bedtime=req.query.get("bedtime") == "1",
    )
    session["story_ids"].append(doc["story_id"])
    session["phone_connected"] = True
    store().put_json(_session_key(sid), session)
    start_generation(doc["story_id"])
    return json_response({"story_id": doc["story_id"]}, 201)


def h_get_story(req: Request, story_id: str) -> Response:
    return json_response(public_story(_load_story(story_id)))


def h_choice(req: Request, story_id: str) -> Response:
    _load_story(story_id)
    option = req.json().get("option")
    if option not in ("a", "b"):
        raise HttpError(400, "option must be 'a' or 'b'")
    store().put_json(generator.choice_key(story_id), {"option": option, "at": time.time()})
    return json_response({"ok": True})


def h_shelf(req: Request, hid: str) -> Response:
    if not ID_RE.match(hid):
        raise HttpError(404, "household not found")
    shelf = universe.load(hid)["shelf"]
    return json_response(
        {
            "stories": [
                {**{k: v for k, v in s.items() if not k.endswith("_key")}, "sprite_url": _url(s.get("sprite_key")), "cover_url": _url(s.get("cover_key"))}
                for s in shelf
            ]
        }
    )


def h_file(req: Request, key: str) -> Response:
    s = store()
    if not isinstance(s, LocalStorage):
        raise HttpError(404, "not found")
    try:
        data = s.get_bytes(key)
    except ValueError:
        raise HttpError(404, "not found")
    if data is None:
        raise HttpError(404, "not found")
    ctype = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(200, data, {"content-type": ctype, "cache-control": "public, max-age=86400"})


def h_static(req: Request, rel: str) -> Response:
    root = settings().web_dir.resolve()
    rel = rel or "tv/index.html"
    path = (root / rel).resolve()
    if path.is_dir():
        path = path / "index.html"
    if root not in path.parents or not path.is_file():
        raise HttpError(404, "not found")
    ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if path.suffix == ".js":
        ctype = "text/javascript"
    return Response(200, path.read_bytes(), {"content-type": ctype, "cache-control": "no-cache"})


ROUTES: list[tuple[str, re.Pattern, Callable[..., Response]]] = [
    ("GET", re.compile(r"^/api/config$"), h_config),
    ("POST", re.compile(r"^/api/sessions$"), h_create_session),
    ("GET", re.compile(r"^/api/sessions/([^/]+)$"), h_get_session),
    ("GET", re.compile(r"^/api/sessions/([^/]+)/qr\.svg$"), h_qr),
    ("POST", re.compile(r"^/api/sessions/([^/]+)/hello$"), h_hello),
    ("POST", re.compile(r"^/api/sessions/([^/]+)/stories$"), h_create_story),
    ("GET", re.compile(r"^/api/codes/([^/]+)$"), h_code),
    ("GET", re.compile(r"^/api/stories/([^/]+)$"), h_get_story),
    ("POST", re.compile(r"^/api/stories/([^/]+)/choice$"), h_choice),
    ("GET", re.compile(r"^/api/households/([^/]+)/shelf$"), h_shelf),
    ("GET", re.compile(r"^/files/(.+)$"), h_file),
    ("GET", re.compile(r"^/((?:tv|phone|shared)/.*)$"), h_static),
]


def handle(req: Request) -> Response:
    try:
        if req.method == "OPTIONS":
            return Response(204, b"", {})
        if req.method == "GET" and req.path in ("/", "/tv"):
            return Response(302, b"", {"location": "/tv/"})
        if req.method == "GET" and req.path == "/phone":
            return Response(302, b"", {"location": "/phone/"})
        for method, pattern, fn in ROUTES:
            m = pattern.match(req.path)
            if m and method == req.method:
                return fn(req, *m.groups())
        raise HttpError(404, "not found")
    except HttpError as err:
        return json_response({"error": err.message}, err.status)
    except Exception:
        log.exception("unhandled error on %s %s", req.method, req.path)
        return json_response({"error": "internal error"}, 500)


def quote_key(key: str) -> str:
    return quote(key)
