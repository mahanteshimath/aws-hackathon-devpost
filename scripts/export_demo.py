"""Export a generated story as the bundled offline demo (web/tv/demo/) - used by 'Watch a sample story'.

    .venv/bin/python scripts/export_demo.py <story_id>
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from crayon import generator  # noqa: E402
from crayon.storage import store  # noqa: E402

OUT = ROOT / "web" / "tv" / "demo"


def main(story_id: str) -> None:
    s = store()
    doc = s.get_json(generator.story_key(story_id))
    if not doc or doc.get("status") != "ready":
        raise SystemExit(f"story {story_id} not found or not ready")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    def copy(key: str | None) -> str | None:
        if not key:
            return None
        data = s.get_bytes(key)
        if data is None:
            return None
        name = key.rsplit("/", 1)[-1]
        (OUT / name).write_bytes(data)
        return name

    ch = dict(doc["character"])
    ch["sprite_url"] = copy(ch.pop("sprite_key"))
    ch["greeting_audio_url"] = copy(ch.pop("greeting_audio_key", None))
    pages = {}
    for pid, page in doc["pages"].items():
        p = {k: v for k, v in page.items() if k not in {"scene", "bg_key", "audio_key"}}
        p["bg_url"] = copy(page.get("bg_key"))
        p["audio_url"] = copy(page.get("audio_key"))
        pages[pid] = p
    out = {k: v for k, v in doc.items() if k not in {"image_key", "session_id", "household_id"}}
    out.update(character=ch, pages=pages, story_id="demo")
    (OUT / "story.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"exported {story_id} -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
