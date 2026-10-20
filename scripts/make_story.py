"""Generate a story from a drawing on the command line (mock or AWS mode, per .env).

    .venv/bin/python scripts/make_story.py samples/dino.jpg --name Maya --theme space [--bedtime]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from crayon import generator  # noqa: E402
from crayon.config import settings  # noqa: E402
from crayon.storage import store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--name", default="Maya")
    ap.add_argument("--theme", default="space")
    ap.add_argument("--bedtime", action="store_true")
    ap.add_argument("--household", default="0" * 24)
    args = ap.parse_args()

    data = Path(args.image).read_bytes()
    key = f"drawings/cli/{int(time.time())}.jpg"
    store().put_bytes(key, data, "image/jpeg")
    doc = generator.create_story_record("cli", args.household, key, args.name, args.theme, args.bedtime)
    t0 = time.time()
    result = generator.generate_story(doc["story_id"])
    print(json.dumps({k: result[k] for k in ("story_id", "status", "title", "timings")}, indent=2))
    print("hero:", result["character"]["name"], "| palette:", result["character"]["palette"])
    for pid in ["1", "2", "3", "a1", "b1"]:
        page = result["pages"].get(pid)
        if page:
            print(f"  [{pid}] {page['status']:8} {page['text'][:90]}")
    print(f"mode={settings().mode} total={time.time() - t0:.1f}s data={settings().data_dir / 'stories' / doc['story_id']}")


if __name__ == "__main__":
    main()
