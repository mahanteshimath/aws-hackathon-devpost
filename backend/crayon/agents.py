"""The two Strands agents.

Casting agent  (fast multimodal model, Amazon Nova 2 Lite by default): looks at the drawing and casts it as a hero.
Director agent (Amazon Nova 2 Lite by default + tools): recalls the household universe and writes a branching story.
Any Bedrock Converse model with vision and tool use can be swapped in via STORY_MODEL_ID / CASTING_MODEL_ID.

Both return validated pydantic objects via Strands structured output. Mock versions keep the app usable
without AWS for UI development and offline demos.
"""

from __future__ import annotations

import random

from .config import settings
from .models import CharacterCard, StoryBranch, StoryPage, StoryPlan

CASTING_PROMPT = """You are the casting director of Crayon Cinema, a bedtime-story app for children aged 3-8.
You are shown a photo of a child's drawing. Treat it with warmth: whatever it is, it is the hero.
If the drawing is abstract, invent a lovable creature inspired by its shapes and colours.
Never comment on drawing quality. Never describe anything scary. Keep names short and easy to say."""

DIRECTOR_PROMPT = """You are the story director of Crayon Cinema, writing a picture-book story for children aged 3-8
that will be read aloud on a TV. The child's own drawing is the hero.

Rules:
- Before writing, call recall_household_universe to see heroes and adventures this family already has.
  If a previous hero fits, give them a small, happy cameo or a callback ("Remember when...").
- Simple words, short sentences, gentle humour, no peril, no villains, nothing scary, no brand names.
- Use the child's first name at most twice. Never ask for or mention personal details (addresses, schools).
- Each page: 2-3 sentences, max 40 words. The scene field describes ONLY the background for the illustrator.
- 3 opening pages, then a choice between two delightful options; each option has exactly 3 pages and a warm ending.
- In bedtime mode: calm, slower pacing, cosy places, the final page ends with the hero yawning and falling asleep."""


def _image_block(jpeg: bytes) -> dict:
    return {"image": {"format": "jpeg", "source": {"bytes": jpeg}}}


def _model(model_id: str, temperature: float, max_tokens: int):
    from strands.models import BedrockModel

    return BedrockModel(model_id=model_id, region_name=settings().region, temperature=temperature, max_tokens=max_tokens)


def cast_character(jpeg: bytes, kid_name: str, theme: str) -> CharacterCard:
    from strands import Agent

    agent = Agent(
        name="casting",
        model=_model(settings().casting_model_id, 0.7, 1500),
        system_prompt=CASTING_PROMPT,
        callback_handler=None,
    )
    prompt = [
        _image_block(jpeg),
        {"text": f"The child's name is {kid_name or 'friend'}. Preferred world: {theme}. Cast this drawing as our hero."},
    ]
    return agent(prompt, structured_output_model=CharacterCard).structured_output


def direct_story(jpeg: bytes, card: CharacterCard, kid_name: str, theme: str, bedtime: bool, household_id: str) -> StoryPlan:
    from strands import Agent, tool

    from . import universe

    @tool
    def recall_household_universe() -> str:
        """Return the heroes and past adventures this household already has, for callbacks and cameos."""
        return universe.recall(household_id)

    agent = Agent(
        name="director",
        model=_model(settings().story_model_id, 0.9, 6000),
        system_prompt=DIRECTOR_PROMPT,
        tools=[recall_household_universe],
        callback_handler=None,
    )
    prompt = [
        _image_block(jpeg),
        {
            "text": (
                f"Hero: {card.hero_name}, {card.species}. Traits: {', '.join(card.traits)}. Moves by: {card.motion}.\n"
                f"World idea: {card.world_hint}\nChild's first name: {kid_name or 'not given'}\n"
                f"Theme requested: {theme}\nMode: {'BEDTIME (calm, sleepy ending)' if bedtime else 'daytime adventure'}\n"
                "Write tonight's story."
            )
        },
    ]
    return agent(prompt, structured_output_model=StoryPlan).structured_output


# ---------------------------------------------------------------- mock mode

_MOCK_NAMES = ["Captain Doodle", "Sir Scribbles", "Princess Squiggle", "Rocket Rex", "Bubbles"]
_THEME_PLACES = {
    "space": ("a sparkly path between the stars", "the Moon's cheese caves", "a rainbow ring around Saturn"),
    "jungle": ("a giggling jungle of giant leaves", "a waterfall that sings", "a treehouse in the clouds"),
    "ocean": ("a beach of rainbow shells", "a coral garden full of bubbles", "an island shaped like a smile"),
}


def mock_cast(kid_name: str, theme: str, seed: int) -> CharacterCard:
    rnd = random.Random(seed)
    name = rnd.choice(_MOCK_NAMES)
    return CharacterCard(
        hero_name=name,
        species="a cheerful crayon creature",
        traits=["brave", "giggly", "kind"],
        motion=rnd.choice(["hop", "walk", "float"]),
        voice=rnd.choice(["Ivy", "Kevin"]),
        greeting=f"Hi {kid_name or 'friend'}! I'm {name}. Let's go on an adventure!",
        world_hint=f"A world full of {theme} wonders.",
    )


def mock_story(card: CharacterCard, kid_name: str, theme: str, bedtime: bool) -> StoryPlan:
    places = _THEME_PLACES.get(theme, _THEME_PLACES["space"])
    hero, kid = card.hero_name, kid_name or "our friend"
    mood = "sleepy" if bedtime else "sunny"

    def page(text: str, scene: str, motion: str = card.motion) -> StoryPage:
        return StoryPage(text=text, scene=scene, mood=mood, hero_motion=motion)  # type: ignore[arg-type]

    ending = "yawned a big yawn and drifted off to sleep." if bedtime else "laughed all the way home."
    return StoryPlan(
        title=f"{hero} and the Great Adventure",
        opening=[
            page(f"One {'starry night' if bedtime else 'bright morning'}, {hero} jumped right off {kid}'s paper!", "a cosy bedroom window looking out over rolling hills"),
            page(f"{hero} followed {places[0]}. Everything twinkled and hummed a happy tune.", places[0]),
            page(f"Then {hero} found two glowing doors. Which one should {hero} open?", "two round glowing doors in a meadow of tall flowers"),
        ],
        choice_prompt=f"Where should {hero} go?",
        option_a=StoryBranch(
            label="The sparkly door",
            pages=[
                page(f"Behind the sparkly door was {places[1]}! {hero} did a little dance.", places[1], "hop"),
                page(f"{hero} made a new friend who loved jokes as much as {kid} does.", places[1]),
                page(f"Waving goodbye, {hero} {ending}", "a quiet hill under a big friendly moon" if bedtime else "a sunny path back to a little house"),
            ],
        ),
        option_b=StoryBranch(
            label="The bouncy door",
            pages=[
                page(f"Behind the bouncy door was {places[2]}! Boing, boing, boing!", places[2], "hop"),
                page(f"{hero} bounced so high that the clouds giggled.", "fluffy clouds over a pastel landscape", "float"),
                page(f"At last, {hero} {ending}", "a soft meadow under twinkling stars" if bedtime else "a meadow with a rainbow"),
            ],
        ),
        recap=f"{hero} explored {places[0]} and chose a magical door.",
    )
