import base64
import io
import json

import pytest
from PIL import Image

from crayon import api, aws_services, generator, imaging
from crayon.storage import store
from make_sample_drawing import dino


@pytest.fixture(scope="module")
def drawing_bytes(tmp_path_factory) -> bytes:
    path = tmp_path_factory.mktemp("art") / "dino.jpg"
    dino(path)
    return path.read_bytes()


# ------------------------------------------------------------------ imaging

def test_paper_key_keeps_the_drawing_and_drops_the_paper(drawing_bytes):
    photo = imaging.load_photo(drawing_bytes)
    cut = imaging.paper_key(photo)
    assert imaging.is_plausible_cutout(cut)
    # corners are paper -> transparent; the dino body (centre-left) is opaque
    assert cut.getpixel((5, 5))[3] == 0
    assert cut.getpixel((int(photo.width * 0.33), int(photo.height * 0.58)))[3] > 200


def test_sticker_crops_and_palette_finds_crayon_colours(drawing_bytes):
    sprite = imaging.sticker(imaging.paper_key(imaging.load_photo(drawing_bytes)))
    assert sprite.mode == "RGBA" and max(sprite.size) <= 900
    colours = imaging.palette(sprite)
    assert 1 <= len(colours) <= 4 and all(c.startswith("#") and len(c) == 7 for c in colours)
    # the drawing is mostly purple: at least one colour should be blue-ish red-ish (purple)
    assert any(int(c[1:3], 16) > 100 and int(c[5:7], 16) > 150 for c in colours)


def test_load_photo_respects_image_model_size_limits():
    big = Image.new("RGB", (4000, 3000), "white")
    buf = io.BytesIO()
    big.save(buf, "JPEG")
    img = imaging.load_photo(buf.getvalue())
    assert max(img.size) <= imaging.MAX_SIDE and min(img.size) >= imaging.MIN_SIDE


def test_colour_names_turn_the_palette_into_prompt_words():
    assert imaging.colour_names(["#A070E0", "#FF8A20", "#9F6FDF"]) == ["lavender", "orange"]


# ------------------------------------------------------------------ Stability AI responses

class _FakeBedrock:
    def __init__(self, payload: dict):
        self.payload, self.calls = payload, []

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        return {"body": _Stream(json.dumps(self.payload).encode())}


def test_scene_decodes_image_and_targets_the_scene_region(monkeypatch):
    fake = _FakeBedrock({"images": [base64.b64encode(b"jpegbytes").decode()], "finish_reasons": [None]})
    regions = []
    monkeypatch.setattr(aws_services, "client", lambda name, region=None: regions.append(region) or fake)
    assert aws_services.scene("a meadow", "scary", seed=7) == b"jpegbytes"
    body = json.loads(fake.calls[0]["body"])
    assert body["aspect_ratio"] == "16:9" and body["mode"] == "text-to-image" and body["seed"] == 7
    assert regions == [aws_services.settings().scene_region]


def test_content_filtered_image_raises_so_the_generator_uses_fallback_art(monkeypatch):
    fake = _FakeBedrock({"images": [], "finish_reasons": ["Filter reason: prompt"]})
    monkeypatch.setattr(aws_services, "client", lambda name, region=None: fake)
    with pytest.raises(RuntimeError):
        aws_services.scene("a meadow", "scary", seed=1)


# ------------------------------------------------------------------ Polly speech marks

class _Stream:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakePolly:
    """Returns speech marks with byte offsets into the SSML input, exactly like Polly."""

    def synthesize_speech(self, OutputFormat, Text, **kwargs):
        if OutputFormat == "mp3":
            return {"AudioStream": _Stream(b"ID3fake")}
        raw = Text.encode("utf-8")
        body_start = raw.index(b">", raw.index(b"<prosody")) + 1
        body_end = raw.index(b"</prosody>")
        lines, t, pos = [], 0, body_start
        for word in raw[body_start:body_end].split(b" "):
            if word:
                start = raw.index(word, pos)
                lines.append(json.dumps({"time": t, "type": "word", "start": start, "end": start + len(word), "value": word.decode()}))
                pos = start + len(word)
                t += 250
        return {"AudioStream": _Stream("\n".join(lines).encode())}


def test_narrate_maps_ssml_byte_offsets_to_text_characters(monkeypatch):
    monkeypatch.setattr(aws_services, "client", lambda name: FakePolly())
    text = "Zoë the dino said “hello” to Maya!"
    n = aws_services.narrate(text, "Joanna")
    assert n.audio == b"ID3fake"
    words = [text[w["s"]:w["e"]] for w in n.words]
    assert words == ["Zoë", "the", "dino", "said", "“hello”", "to", "Maya!"]
    assert [w["t"] for w in n.words] == sorted(w["t"] for w in n.words)


def test_narrate_strips_ssml_breaking_characters(monkeypatch):
    monkeypatch.setattr(aws_services, "client", lambda name: FakePolly())
    n = aws_services.narrate("Rex & Maya <3 cake", "Joanna")
    assert len(n.words) == 4  # '&' and '<' removed; no SSML injection


def test_guard_is_a_noop_without_a_configured_guardrail():
    aws_services.guard("anything at all")  # must not raise or call AWS


# ------------------------------------------------------------------ API + pipeline (mock mode)

def call(method, path, body=b"", query=None, headers=None):
    req = api.Request(method=method, path=path, query=query or {}, headers=headers or {"host": "tv.test"}, body=body)
    resp = api.handle(req)
    data = json.loads(resp.body) if resp.headers.get("content-type") == "application/json" else resp.body
    return resp.status, data


def test_full_story_flow_from_phone_upload_to_shelf(monkeypatch, drawing_bytes):
    monkeypatch.setattr(api, "start_generation", lambda story_id: generator.generate_story(story_id))

    status, session = call("POST", "/api/sessions", b"{}")
    assert status == 200 and session["phone_url"].startswith("http://tv.test/phone/?s=")
    sid, hid = session["session_id"], session["household_id"]

    status, qr = call("GET", f"/api/sessions/{sid}/qr.svg")
    assert status == 200 and b"<svg" in qr

    status, created = call("POST", f"/api/sessions/{sid}/stories", drawing_bytes, {"kid_name": "Maya<script>", "theme": "space"})
    assert status == 201
    story_id = created["story_id"]

    status, story = call("GET", f"/api/stories/{story_id}")
    assert status == 200 and story["status"] == "ready"
    assert story["kid_name"] == "Mayascript"  # sanitised
    assert "image_key" not in story and "session_id" not in story
    assert story["character"]["sprite_url"].startswith("/files/")
    assert set(story["pages"]) == {"1", "2", "3", "a1", "a2", "a3", "b1", "b2", "b3"}
    assert all(p["status"] == "ready" and p["bg_url"] and p["words"] for p in story["pages"].values())
    assert [o["id"] for o in story["choice"]["options"]] == ["a", "b"]

    # privacy: the original photo is deleted after the cut-out is made
    doc = store().get_json(generator.story_key(story_id))
    assert store().get_bytes(doc["image_key"]) is None

    status, info = call("GET", f"/api/sessions/{sid}")
    assert info["latest"] == {"story_id": story_id, "status": "ready"}

    status, shelf = call("GET", f"/api/households/{hid}/shelf")
    assert shelf["stories"][0]["story_id"] == story_id and shelf["stories"][0]["sprite_url"]

    status, _ = call("POST", f"/api/stories/{story_id}/choice", b'{"option": "b"}')
    assert status == 200


def test_rejects_non_images_and_unknown_sessions(drawing_bytes):
    _, session = call("POST", "/api/sessions", b"{}")
    status, err = call("POST", f"/api/sessions/{session['session_id']}/stories", b"not an image")
    assert status == 415
    status, _ = call("POST", "/api/sessions/deadbeefdeadbeefdeadbeef/stories", drawing_bytes)
    assert status == 404
    status, _ = call("GET", "/api/stories/../../etc/passwd")
    assert status == 404


def test_static_files_cannot_escape_web_root():
    status, _ = call("GET", "/tv/../../.env")
    assert status == 404
    status, body = call("GET", "/tv/")
    assert status == 200 and b"Crayon Cinema" in body


def test_chosen_branch_is_rendered_first(drawing_bytes):
    key = "drawings/test/p.jpg"
    store().put_bytes(key, drawing_bytes, "image/jpeg")
    doc = generator.create_story_record("s", "0" * 24, key, "Ada", "ocean", False)
    run = generator.StoryRun(doc["story_id"])
    run.doc["pages"] = {pid: {} for pid in ["1", "2", "3", "a1", "a2", "a3", "b1", "b2", "b3"]}
    assert run.priority()[:5] == ["1", "2", "3", "a1", "b1"]
    store().put_json(generator.choice_key(doc["story_id"]), {"option": "b"})
    assert run.priority()[3:6] == ["b1", "b2", "b3"]


def test_estimated_word_timings_cover_every_word():
    words = generator.estimate_words("One, two. Three!")
    assert len(words) == 3 and words[0]["t"] < words[1]["t"] < words[2]["t"]


def test_lambda_function_url_events_round_trip(drawing_bytes, monkeypatch):
    import base64

    import lambda_handler

    monkeypatch.setattr(api, "start_generation", lambda story_id: None)

    def event(method, path, body=b"", query=None, binary=False):
        return {
            "rawPath": path,
            "queryStringParameters": query,
            "headers": {"host": "abc.lambda-url.us-east-1.on.aws", "x-forwarded-proto": "https", "content-type": "image/jpeg" if binary else "application/json"},
            "requestContext": {"http": {"method": method}},
            "body": base64.b64encode(body).decode() if binary else body.decode(),
            "isBase64Encoded": binary,
        }

    out = lambda_handler.handler(event("POST", "/api/sessions", b"{}"), None)
    session = json.loads(out["body"])
    assert out["statusCode"] == 200 and session["phone_url"].startswith("http://tv.test/phone/")  # CRAYON_PUBLIC_URL wins
    out = lambda_handler.handler(event("POST", f"/api/sessions/{session['session_id']}/stories", drawing_bytes, {"theme": "jungle"}, binary=True), None)
    assert out["statusCode"] == 201
    out = lambda_handler.handler(event("GET", "/shared/fonts/Fredoka.ttf"), None)
    assert out["statusCode"] == 200 and out["isBase64Encoded"] and base64.b64decode(out["body"])[:4] == b"\x00\x01\x00\x00"


def test_story_plan_rejects_a_branch_without_three_pages():
    from pydantic import ValidationError

    from crayon import agents
    from crayon.models import StoryPlan

    plan = agents.mock_story(agents.mock_cast("Maya", "space", 1), "Maya", "space", bedtime=False).model_dump()
    plan["option_a"]["pages"] = plan["option_a"]["pages"][:1]
    with pytest.raises(ValidationError):
        StoryPlan.model_validate(plan)
