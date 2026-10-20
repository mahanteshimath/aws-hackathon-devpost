"""Household 'story universe': heroes and adventures that come back in future stories.

Two layers:
- A structured JSON record in storage (always on; powers the Story Shelf and exact hero recall).
- Amazon Bedrock AgentCore Memory (when AGENTCORE_MEMORY_ID is set): each finished story is written as an
  event; a semantic strategy extracts long-term facts the Director agent retrieves next time.
"""

from __future__ import annotations

import logging
import time

from .config import settings
from .storage import store

log = logging.getLogger("crayon.universe")

MAX_HEROES = 12
MAX_SHELF = 30


def _key(household_id: str) -> str:
    return f"households/{household_id}/universe.json"


def load(household_id: str) -> dict:
    return store().get_json(_key(household_id)) or {"heroes": [], "shelf": []}


def recall(household_id: str) -> str:
    """Plain-text memory brief for the Director agent."""
    data = load(household_id)
    lines = []
    for hero in data["heroes"][-6:]:
        lines.append(f"- {hero['name']} ({hero['species']}), drawn by {hero.get('kid_name') or 'a child'}: {hero.get('recap', '')}")
    memory_id = settings().agentcore_memory_id
    if memory_id:
        try:
            from bedrock_agentcore.memory import MemoryClient

            records = MemoryClient(region_name=settings().region).retrieve_memories(
                memory_id=memory_id,
                namespace=f"crayon/{household_id}/facts",
                query="favourite heroes, past adventures, things the children love",
                top_k=5,
            )
            for rec in records:
                text = (rec.get("content") or {}).get("text")
                if text:
                    lines.append(f"- remembered: {text}")
        except Exception as exc:  # memory is an enhancement, never a blocker
            log.warning("AgentCore Memory recall failed: %s", exc)
    return "\n".join(lines) if lines else "This household has no stories yet - this is their very first one!"


def remember(household_id: str, story: dict) -> None:
    data = load(household_id)
    character = story["character"]
    hero = {
        "name": character["name"],
        "species": character["species"],
        "kid_name": story.get("kid_name", ""),
        "recap": story.get("recap", ""),
        "story_id": story["story_id"],
    }
    data["heroes"] = [h for h in data["heroes"] if h["name"].lower() != hero["name"].lower()][-(MAX_HEROES - 1):] + [hero]
    data["shelf"] = (
        [
            {
                "story_id": story["story_id"],
                "title": story.get("title", ""),
                "hero_name": character["name"],
                "sprite_key": character.get("sprite_key"),
                "cover_key": (story["pages"].get("1") or {}).get("bg_key"),
                "bedtime": story.get("bedtime", False),
                "created_at": story.get("created_at", time.time()),
            }
        ]
        + [s for s in data["shelf"] if s["story_id"] != story["story_id"]]
    )[:MAX_SHELF]
    store().put_json(_key(household_id), data)

    memory_id = settings().agentcore_memory_id
    if memory_id:
        try:
            from bedrock_agentcore.memory import MemoryClient

            MemoryClient(region_name=settings().region).create_event(
                memory_id=memory_id,
                actor_id=household_id,
                session_id=story["story_id"],
                messages=[
                    (f"{story.get('kid_name') or 'A child'} drew {character['species']} named {character['name']}.", "USER"),
                    (f"Story '{story.get('title', '')}': {story.get('recap', '')}", "ASSISTANT"),
                ],
            )
        except Exception as exc:
            log.warning("AgentCore Memory write failed: %s", exc)
