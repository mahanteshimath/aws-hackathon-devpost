"""Thin, well-typed wrappers over the AWS services Crayon Cinema uses.

- Stability AI on Amazon Bedrock (InvokeModel): Stable Image Remove Background + Stable Diffusion 3.5 Large scenes
  (Amazon Nova Canvas, the original choice, has reached end of life on Bedrock)
- Amazon Polly: neural narration + word speech marks for read-along highlighting
- Amazon Bedrock Guardrails: ApplyGuardrail on everything shown to a child
"""

from __future__ import annotations

import base64
import json
import logging
import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from xml.sax.saxutils import escape

import boto3
from botocore.config import Config

from .config import settings

log = logging.getLogger("crayon.aws")

_RETRY = Config(retries={"max_attempts": 6, "mode": "adaptive"}, read_timeout=120, connect_timeout=10)
# Polly answers in ~1s; a short timeout turns a stalled pooled connection into a fast retry, not a 2-minute hang.
_FAST = Config(retries={"max_attempts": 4, "mode": "adaptive"}, read_timeout=15, connect_timeout=5)


@lru_cache(maxsize=None)
def client(name: str, region: str | None = None):
    return boto3.client(name, region_name=region or settings().region, config=_FAST if name == "polly" else _RETRY)


# ---------------------------------------------------------------- Stability AI images

_image_slots: threading.BoundedSemaphore | None = None


def _image_semaphore() -> threading.BoundedSemaphore:
    global _image_slots
    if _image_slots is None:
        _image_slots = threading.BoundedSemaphore(settings().image_concurrency)
    return _image_slots


def _stability(model_id: str, region: str, body: dict) -> bytes:
    with _image_semaphore():  # stay inside the account's image-model concurrency quota
        resp = client("bedrock-runtime", region).invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
    payload = json.loads(resp["body"].read())
    reasons = [r for r in payload.get("finish_reasons") or [] if r]
    if reasons or not payload.get("images"):
        raise RuntimeError(f"{model_id} returned no image: {reasons or payload.get('error')}")
    return base64.b64decode(payload["images"][0])


def remove_background(png_bytes: bytes) -> bytes:
    """Transparent PNG of the drawing with the paper removed."""
    cfg = settings()
    return _stability(cfg.cutout_model_id, cfg.region, {"image": base64.b64encode(png_bytes).decode(), "output_format": "png"})


def scene(prompt: str, negative: str, seed: int) -> bytes:
    """A 16:9 storybook background (JPEG)."""
    cfg = settings()
    return _stability(
        cfg.scene_model_id,
        cfg.scene_region,
        {
            "prompt": prompt[:9000],
            "negative_prompt": negative[:9000],
            "mode": "text-to-image",
            "aspect_ratio": "16:9",
            "output_format": "jpeg",
            "seed": seed % 4294967294,
        },
    )


# ---------------------------------------------------------------- Polly

@dataclass
class Narration:
    audio: bytes
    words: list[dict]  # [{"t": ms, "s": charStart, "e": charEnd}]


_SSML_SAFE = re.compile(r"[<>&]")


def narrate(text: str, voice: str, rate: str = "95%") -> Narration:
    """Synthesize speech and word timings. Offsets are converted from SSML bytes to characters of `text`."""
    text = _SSML_SAFE.sub(" ", text)
    prefix = f'<speak><prosody rate="{rate}">'
    ssml = f"{prefix}{escape(text)}</prosody></speak>"
    polly = client("polly")
    common = dict(Engine="neural", VoiceId=voice, Text=ssml, TextType="ssml")
    audio = polly.synthesize_speech(OutputFormat="mp3", **common)["AudioStream"].read()
    marks_raw = polly.synthesize_speech(OutputFormat="json", SpeechMarkTypes=["word"], **common)["AudioStream"].read()

    text_bytes = text.encode("utf-8")
    prefix_len = len(prefix.encode("utf-8"))
    words = []
    for line in marks_raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        mark = json.loads(line)
        if mark.get("type") != "word":
            continue
        b_start = max(0, mark["start"] - prefix_len)
        b_end = max(b_start, mark["end"] - prefix_len)
        s = len(text_bytes[:b_start].decode("utf-8", errors="ignore"))
        e = len(text_bytes[:b_end].decode("utf-8", errors="ignore"))
        if e > s:
            words.append({"t": int(mark["time"]), "s": s, "e": e})
    return Narration(audio=audio, words=words)


# ---------------------------------------------------------------- Guardrails

class UnsafeContent(Exception):
    pass


def guard(text: str, source: str = "OUTPUT") -> None:
    """Raise UnsafeContent if the configured guardrail intervenes. No-op when no guardrail is configured."""
    cfg = settings()
    if not cfg.guardrail_id or not text.strip():
        return
    resp = client("bedrock-runtime").apply_guardrail(
        guardrailIdentifier=cfg.guardrail_id,
        guardrailVersion=cfg.guardrail_version,
        source=source,
        content=[{"text": {"text": text[:20000]}}],
    )
    if resp.get("action") == "GUARDRAIL_INTERVENED":
        log.warning("guardrail intervened (%s)", source)
        raise UnsafeContent(source)
