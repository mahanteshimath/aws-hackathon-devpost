"""Structured outputs the agents must produce. Strands validates model output against these."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Motion = Literal["walk", "hop", "fly", "float", "roll"]
Mood = Literal["sunny", "magical", "cozy", "exciting", "sleepy"]
ChildVoice = Literal["Ivy", "Kevin"]


class CharacterCard(BaseModel):
    """What the casting agent sees in the child's drawing."""

    hero_name: str = Field(description="A short, fun, kid-friendly name for the drawn character (1-3 words).")
    species: str = Field(description="What the drawing looks like, e.g. 'a purple dinosaur with a spiky back'.")
    traits: list[str] = Field(description="2-3 gentle personality adjectives inspired by the drawing.")
    motion: Motion = Field(description="How this character moves across the screen.")
    voice: ChildVoice = Field(description="Ivy (girl-like child voice) or Kevin (boy-like child voice).")
    greeting: str = Field(description="One short line (max 12 words) the hero says to greet the child by name.")
    world_hint: str = Field(description="One sentence about the kind of world this hero would love to explore.")


class StoryPage(BaseModel):
    text: str = Field(description="2-3 short sentences, max 40 words, simple words a 5-year-old understands.")
    scene: str = Field(
        description=(
            "Visual description of the BACKGROUND ONLY for an illustrator: place, objects, light. "
            "Never include the hero, people, faces, letters or text. Leave open space in the lower middle."
        )
    )
    mood: Mood
    hero_motion: Motion


class StoryBranch(BaseModel):
    label: str = Field(description="2-4 word choice shown on the TV, e.g. 'Fly to the moon'.")
    pages: list[StoryPage] = Field(
        min_length=3, max_length=3, description="Exactly 3 pages that follow this choice and end the story warmly."
    )


class StoryPlan(BaseModel):
    title: str = Field(description="Story title, max 7 words, includes the hero's name.")
    opening: list[StoryPage] = Field(min_length=3, max_length=3, description="Exactly 3 opening pages before the choice.")
    choice_prompt: str = Field(description="Question asked to the child at the end of page 3, max 8 words.")
    option_a: StoryBranch
    option_b: StoryBranch
    recap: str = Field(description="One sentence summary to remember for future stories.")
