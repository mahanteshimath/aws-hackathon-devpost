"""Story generation pipeline.

  photo ──► cleanup ──┬─► Casting agent (Nova 2 Lite vision) ─┐
                      └─► Stability background removal ─────┴─► CAST REVEAL (≈10s)
                                                               │
                         Director agent (Nova 2 Lite + memory tool) ◄┘
                                     │  StoryPlan (validated) ─► Guardrails
                                     ▼
          render workers: SD3.5 Large scenes in the kid's crayon colours  ║  Polly narration + word marks
          priority: 1,2,3, chosen branch first, then the other branch ─► pages stream to the TV as they finish

The story document is rewritten atomically after every step, so the TV can poll and play progressively.
"""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
import traceback
from typing import Any

from . import agents, imaging, universe
from .config import settings
from .models import CharacterCard, StoryPlan
from .storage import store

log = logging.getLogger("crayon.generator")

THEMES = {"space", "jungle", "ocean", "surprise"}
NARRATOR_VOICE = "Joanna"

STYLE = (
    "Children's picture-book background illustration, hand-drawn with wax crayons and soft watercolor on textured paper, "
    "gentle rounded shapes, warm and friendly, wide landscape composition with open empty ground in the lower middle"
)
NEGATIVE = (
    "people, person, child, character, creature, animal, face, text, letters, words, signature, watermark, logo, "
    "scary, dark shadows, monster, weapon, blood, photorealistic, 3d render"
)
MOOD_WORDS = {
    "sunny": "bright morning light, cheerful",
    "magical": "sparkles, soft glow, wonder",
    "cozy": "warm lamplight, snug",
    "exciting": "vivid, playful energy",
    "sleepy": "dusky twilight, gentle moonlight, calm deep blues and lavender",
}


def new_id(nbytes: int = 12) -> str:
    return secrets.token_hex(nbytes)


def clean_name(name: str) -> str:
    name = re.sub(r"[^A-Za-zÀ-ÿ' -]", "", name or "").strip()
    return name[:20].title()


def story_key(story_id: str) -> str:
    return f"stories/{story_id}/story.json"


def choice_key(story_id: str) -> str:
    return f"stories/{story_id}/choice.json"


def create_story_record(session_id: str, household_id: str, image_key: str, kid_name: str, theme: str, bedtime: bool) -> dict:
    story_id = new_id()
    doc = {
        "story_id": story_id,
        "session_id": session_id,
        "household_id": household_id,
        "image_key": image_key,
        "kid_name": clean_name(kid_name),
        "theme": theme if theme in THEMES else "surprise",
        "bedtime": bool(bedtime),
        "created_at": time.time(),
        "status": "casting",
        "error": None,
        "timings": {},
        "character": None,
        "title": None,
        "order": ["1", "2", "3"],
        "choice": None,
        "pages": {},
    }
    store().put_json(story_key(story_id), doc)
    return doc


class StoryRun:
    def __init__(self, story_id: str):
        self.store = store()
        self.doc: dict[str, Any] = self.store.get_json(story_key(story_id))
        if not self.doc:
            raise KeyError(story_id)
        self.id = story_id
        self.lock = threading.Lock()
        self.t0 = time.time()
        self.cfg = settings()
        self.seed = int(story_id[:8], 16)
        self.in_progress: set[str] = set()
        self.narrated: set[str] = set()

    # ------------------------------------------------------------- helpers
    def save(self) -> None:
        with self.lock:
            self.store.put_json(story_key(self.id), self.doc)

    def mark(self, stage: str) -> None:
        self.doc["timings"][stage] = int((time.time() - self.t0) * 1000)
        log.info("story=%s stage=%s t=%sms", self.id, stage, self.doc["timings"][stage])

    def asset(self, name: str) -> str:
        return f"stories/{self.id}/{name}"

    # ------------------------------------------------------------- pipeline
    def run(self) -> dict:
        try:
            photo_bytes = self.store.get_bytes(self.doc["image_key"])
            if photo_bytes is None:
                raise RuntimeError("drawing not found")
            photo = imaging.load_photo(photo_bytes)
            jpeg = imaging.to_jpeg_bytes(photo, 88)

            card, sprite = self._cast(photo, jpeg)
            plan = self._direct(jpeg, card)
            self._render_all()
            self.doc["status"] = "ready"
            self.mark("ready")
            self.save()
            try:
                universe.remember(self.doc["household_id"], self.doc)
            except Exception as exc:  # the story is already playing; memory is a bonus
                log.warning("could not remember story %s: %s", self.id, exc)
        except Exception as exc:
            log.error("story %s failed: %s\n%s", self.id, exc, traceback.format_exc())
            self.doc["status"] = "error"
            self.doc["error"] = "The story machine hiccuped. Please try again."
            self.save()
        finally:
            # Privacy: the original photo is not kept - only the cut-out hero and generated story remain.
            try:
                self.store.delete(self.doc["image_key"])
            except Exception as exc:
                log.warning("could not delete original photo: %s", exc)
        return self.doc

    def _cast(self, photo, jpeg: bytes) -> tuple[CharacterCard, Any]:
        kid, theme = self.doc["kid_name"], self.doc["theme"]
        result: dict[str, Any] = {}

        def do_card():
            try:
                if self.cfg.use_aws:
                    from .aws_services import UnsafeContent, guard

                    card = agents.cast_character(jpeg, kid, theme)
                    try:
                        guard(f"{card.hero_name}. {card.species}. {card.greeting}")
                    except UnsafeContent:
                        card = agents.mock_cast(kid, theme, self.seed)
                    result["card"] = card
                else:
                    result["card"] = agents.mock_cast(kid, theme, self.seed)
            except Exception as exc:  # casting must never block the story
                log.warning("casting agent failed, using fallback: %s", exc)
                result["card"] = agents.mock_cast(kid, theme, self.seed)

        def do_cutout():
            cut = None
            if self.cfg.use_aws:
                try:
                    from .aws_services import remove_background
                    from PIL import Image
                    import io

                    cut = Image.open(io.BytesIO(remove_background(imaging.to_png_bytes(photo)))).convert("RGBA")
                    if not imaging.is_plausible_cutout(cut):
                        log.info("cutout implausible (coverage=%.3f), falling back to paper key", imaging.coverage(cut))
                        cut = None
                except Exception as exc:
                    log.warning("background removal failed: %s", exc)
            if cut is None:
                cut = imaging.paper_key(photo)
            result["sprite"] = imaging.sticker(cut)

        threads = [threading.Thread(target=do_card), threading.Thread(target=do_cutout)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        card: CharacterCard = result["card"]
        sprite = result["sprite"]
        self.store.put_bytes(self.asset("sprite.png"), imaging.to_png_bytes(sprite), "image/png")
        colours = imaging.palette(sprite)
        character = {
            "name": card.hero_name,
            "species": card.species,
            "traits": card.traits,
            "motion": card.motion,
            "voice": card.voice,
            "greeting": card.greeting,
            "sprite_key": self.asset("sprite.png"),
            "sprite_size": list(sprite.size),
            "palette": colours,
            "greeting_audio_key": None,
            "greeting_words": [],
        }
        if self.cfg.use_aws:
            try:
                from .aws_services import narrate

                n = narrate(card.greeting, card.voice, rate="100%")
                self.store.put_bytes(self.asset("greeting.mp3"), n.audio, "audio/mpeg")
                character["greeting_audio_key"] = self.asset("greeting.mp3")
                character["greeting_words"] = n.words
            except Exception as exc:
                log.warning("greeting narration failed: %s", exc)
        if not character["greeting_words"]:
            character["greeting_words"] = estimate_words(card.greeting)
        self.doc["character"] = character
        self.doc["status"] = "cast"
        self.mark("cast")
        self.save()
        return card, sprite

    def _direct(self, jpeg: bytes, card: CharacterCard) -> StoryPlan:
        self.doc["status"] = "writing"
        self.save()
        kid, theme, bedtime = self.doc["kid_name"], self.doc["theme"], self.doc["bedtime"]
        plan: StoryPlan | None = None
        if self.cfg.use_aws:
            from .aws_services import UnsafeContent, guard

            for attempt in range(2):
                try:
                    candidate = agents.direct_story(jpeg, card, kid, theme, bedtime, self.doc["household_id"])
                    guard(plan_text(candidate))
                    plan = candidate
                    break
                except UnsafeContent:
                    log.warning("director output blocked by guardrail (attempt %d)", attempt + 1)
                except Exception as exc:
                    log.warning("director agent failed (attempt %d): %s", attempt + 1, exc)
        if plan is None:
            plan = agents.mock_story(card, kid, theme, bedtime)

        pages: dict[str, dict] = {}
        for i, p in enumerate(plan.opening[:3], start=1):
            pages[str(i)] = page_doc(str(i), p)
        for branch_id, branch in (("a", plan.option_a), ("b", plan.option_b)):
            for i, p in enumerate(branch.pages[:3], start=1):
                pid = f"{branch_id}{i}"
                pages[pid] = page_doc(pid, p)
        self.doc["title"] = plan.title
        self.doc["recap"] = plan.recap
        self.doc["choice"] = {
            "prompt": plan.choice_prompt,
            "options": [
                {"id": "a", "label": plan.option_a.label, "path": [f"a{i}" for i in range(1, len(plan.option_a.pages[:3]) + 1)]},
                {"id": "b", "label": plan.option_b.label, "path": [f"b{i}" for i in range(1, len(plan.option_b.pages[:3]) + 1)]},
            ],
        }
        self.doc["pages"] = pages
        self.doc["status"] = "rendering"
        self.mark("written")
        self.save()
        return plan

    # ------------------------------------------------------------- rendering
    def priority(self) -> list[str]:
        try:
            chosen = (self.store.get_json(choice_key(self.id)) or {}).get("option")
        except Exception as exc:  # never let a storage hiccup stop the render workers
            log.warning("could not read choice: %s", exc)
            chosen = None
        first, second = ("b", "a") if chosen == "b" else ("a", "b")
        order = ["1", "2", "3"]
        if chosen:
            order += [f"{first}{i}" for i in (1, 2, 3)] + [f"{second}{i}" for i in (1, 2, 3)]
        else:
            order += ["a1", "b1", "a2", "b2", "a3", "b3"]
        return [pid for pid in order if pid in self.doc["pages"]]

    def _next(self, field: str, taken: set[str]) -> str | None:
        with self.lock:
            for pid in self.priority():
                if self.doc["pages"][pid].get(field) is None and pid not in taken:
                    taken.add(pid)
                    return pid
        return None

    def _render_all(self) -> None:
        workers = [threading.Thread(target=self._illustrate_worker) for _ in range(self.cfg.image_concurrency)]
        workers.append(threading.Thread(target=self._narrate_worker))
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        self.mark("rendered")

    def _illustrate_worker(self) -> None:
        while (pid := self._next("bg_key", self.in_progress)) is not None:
            page = self.doc["pages"][pid]
            try:
                jpeg = self._illustrate(page, int(pid, 36))
            except Exception as exc:
                log.warning("illustration %s failed, using fallback art: %s", pid, exc)
                jpeg = imaging.to_jpeg_bytes(imaging.mock_scene(self.doc["character"]["palette"], self.seed + int(pid, 36), self.doc["bedtime"]))
            key = self.asset(f"p{pid}.jpg")
            self.store.put_bytes(key, jpeg, "image/jpeg")
            with self.lock:
                page["bg_key"] = key
                self._maybe_ready(page)
            self.save()

    def _narrate_worker(self) -> None:
        while (pid := self._next("words", self.narrated)) is not None:
            page = self.doc["pages"][pid]
            audio_key, words = None, None
            if self.cfg.use_aws:
                try:
                    from .aws_services import narrate

                    n = narrate(page["text"], NARRATOR_VOICE, rate="85%" if self.doc["bedtime"] else "95%")
                    audio_key = self.asset(f"p{pid}.mp3")
                    self.store.put_bytes(audio_key, n.audio, "audio/mpeg")
                    words = n.words
                except Exception as exc:
                    log.warning("narration %s failed: %s", pid, exc)
            with self.lock:
                page["audio_key"] = audio_key
                page["words"] = words or estimate_words(page["text"])
                self._maybe_ready(page)
            self.save()

    @staticmethod
    def _maybe_ready(page: dict) -> None:
        if page.get("bg_key") and page.get("words") is not None:
            page["status"] = "ready"

    def _illustrate(self, page: dict, salt: int) -> bytes:
        bedtime = self.doc["bedtime"]
        colours = list(self.doc["character"]["palette"])
        if not self.cfg.use_aws:
            return imaging.to_jpeg_bytes(imaging.mock_scene(colours, self.seed + salt, bedtime))
        from PIL import Image
        import io

        from .aws_services import scene

        mood = "sleepy" if bedtime else page["mood"]
        palette = ", ".join(imaging.colour_names(colours))
        tones = "deep night blues and lavender" if bedtime else "warm cream paper"
        prompt = f"{STYLE}, {MOOD_WORDS.get(mood, '')}. Scene: {page['scene']}. Colour palette: {palette}, {tones}"
        jpeg = scene(prompt, NEGATIVE, seed=self.seed + salt)
        img = Image.open(io.BytesIO(jpeg))
        img.thumbnail((1280, 720), Image.LANCZOS)  # SD3.5 returns ~1344x768; the TV stage letterboxes 16:9
        return imaging.to_jpeg_bytes(img, 82)


def page_doc(pid: str, page) -> dict:
    return {
        "id": pid,
        "text": page.text.strip(),
        "scene": page.scene.strip(),
        "mood": page.mood,
        "motion": page.hero_motion,
        "status": "pending",
        "bg_key": None,
        "audio_key": None,
        "words": None,
    }


def plan_text(plan: StoryPlan) -> str:
    parts = [plan.title, plan.choice_prompt, plan.option_a.label, plan.option_b.label]
    parts += [p.text for p in plan.opening + plan.option_a.pages + plan.option_b.pages]
    return "\n".join(parts)


def estimate_words(text: str, wpm: int = 150) -> list[dict]:
    """Approximate word timings when no Polly speech marks are available (mock/offline)."""
    words, t = [], 300
    per_word = int(60000 / wpm)
    for m in re.finditer(r"\S+", text):
        words.append({"t": t, "s": m.start(), "e": m.end()})
        t += per_word + (350 if m.group()[-1] in ".!?" else 120 if m.group()[-1] in ",;:" else 0)
    return words


def generate_story(story_id: str) -> dict:
    return StoryRun(story_id).run()
