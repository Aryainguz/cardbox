"""The reel spec: what a video is made of, as plain data (YAML or JSON).

A reel is a list of beats. Each beat is one thing on screen and one spoken line (`say`). The renderer
times everything from the voice: a beat lasts as long as its line, captions follow the spoken words,
and animations can be cued to a word ("on": "billion").
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Background(_Model):
    """What plays behind a hook or text beat: an animated scene, or an image with a slow push-in."""

    scene: str | None = None
    image: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class _Spoken(_Model):
    say: str = Field(description="The spoken line. Captions show exactly these words.")
    pronounce: str | None = Field(
        default=None,
        description="Optional respelling for the voice only, e.g. 'Songs P K' while captions keep 'SongsPK'.",
    )


class Hook(_Spoken):
    kind: Literal["hook"] = "hook"
    text: str
    eyebrow: str = ""
    background: Background | None = None


class Text(_Spoken):
    kind: Literal["text"] = "text"
    text: str
    sub: str = ""
    icon: str = ""
    background: Background | None = None


class Stat(_Spoken):
    kind: Literal["stat"] = "stat"
    value: str
    label: str
    icon: str = ""


class ListItem(_Model):
    text: str
    icon: str = ""


class ListBeat(_Spoken):
    kind: Literal["list"] = "list"
    head: str = ""
    items: list[ListItem | str] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def _as_items(cls, v: list[ListItem | str]) -> list[ListItem | str]:
        return [ListItem(text=i) if isinstance(i, str) else i for i in v]


class SceneBeat(_Spoken):
    kind: Literal["scene"] = "scene"
    scene: str
    head: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class End(_Spoken):
    kind: Literal["end"] = "end"
    text: str


Beat = Annotated[Hook | Text | Stat | ListBeat | SceneBeat | End, Field(discriminator="kind")]


Theme = Literal["midnight", "ember", "forest", "neon", "sunset", "mono", "paper"]
Music = Literal["calm", "upbeat", "tense", "none"]


class Reel(_Model):
    """A video. (Named Reel for history; it renders to any format: vertical, landscape or square.)"""

    title: str
    format: str = Field(default="vertical", description="vertical (9:16), landscape (16:9) or square (1:1).")
    handle: str = ""
    theme: Theme = "midnight"
    accent: str | None = Field(default=None, description="Override the theme's accent color, e.g. '#22C55E'.")
    font: Literal["sans", "mono"] = "sans"
    captions: Literal["highlight", "box", "minimal", "none"] = Field(
        default="highlight", description="How spoken-word captions look; 'none' turns them off.")
    voice: str = Field(
        default="default",
        description="A recorded voice profile name, 'system' (the OS voice) or 'none' (silent, timed by estimate).",
    )
    music: Music | bool = Field(default="calm", description="calm, upbeat, tense, or none.")
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list, max_length=5)
    beats: list[Beat] = Field(min_length=1)

    @field_validator("format")
    @classmethod
    def _known_format(cls, v: str) -> str:
        from .formats import get

        return get(v).name

    @property
    def music_mood(self) -> str:
        if self.music is True:
            return "calm"
        if self.music is False:
            return "none"
        return self.music


Video = Reel


def load(path: str | Path) -> Reel:
    """Reads a reel spec from a .yaml/.yml/.json file."""
    text = Path(path).read_text(encoding="utf-8")
    return parse(text)


class _Loader(yaml.SafeLoader):
    """YAML 1.1 reads on/off/yes/no as booleans, which would turn the cue key `on:` into `true:`.
    Only true/false are booleans here, as in YAML 1.2."""


_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:bool"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
                              list("tTfF"))


def parse(text: str) -> Reel:
    """Parses YAML (which also accepts JSON) into a validated Reel."""
    data = yaml.load(text, Loader=_Loader)  # noqa: S506 - a SafeLoader subclass
    if not isinstance(data, dict):
        raise ValueError("a reel spec must be a mapping with 'title' and 'beats'")
    return Reel.model_validate(data)


def dump(reel: Reel) -> str:
    """The spec as YAML, keeping only fields that differ from their defaults (but always each beat's kind)."""
    data = reel.model_dump(exclude_defaults=True)
    data["beats"] = [{"kind": b.kind, **d} for b, d in zip(reel.beats, data["beats"])]
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def schema() -> dict[str, Any]:
    """JSON Schema for the spec (handed to AI clients so they write valid reels)."""
    return Reel.model_json_schema()
