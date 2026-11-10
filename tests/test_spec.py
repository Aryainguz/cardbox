from pathlib import Path

import pytest
from pydantic import ValidationError

from cardbox import spec

EXAMPLE = Path(__file__).parents[1] / "examples" / "hash-table" / "reel.yaml"


def test_example_parses():
    reel = spec.load(EXAMPLE)
    assert reel.beats[0].kind == "hook"
    assert reel.beats[-1].kind == "end"


def test_on_key_is_not_a_boolean():
    reel = spec.parse("""
title: t
beats:
  - {kind: scene, scene: counter, say: one two three, params: {to: 3, on: three}}
""")
    assert reel.beats[0].params == {"to": 3, "on": "three"}


def test_true_false_still_booleans():
    reel = spec.parse("title: t\nmusic: false\nbeats: [{kind: end, text: bye, say: bye}]")
    assert reel.music is False


def test_list_items_accept_strings():
    reel = spec.parse("title: t\nbeats: [{kind: list, items: [a, {icon: wifi, text: b}], say: a b}]")
    assert [i.text for i in reel.beats[0].items] == ["a", "b"]


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        spec.parse("title: t\nbeats: [{kind: poster, say: x}]")


def test_too_many_hashtags_rejected():
    with pytest.raises(ValidationError):
        spec.parse("title: t\nhashtags: [a, b, c, d, e, f]\nbeats: [{kind: end, text: x, say: x}]")


def test_dump_round_trips():
    reel = spec.load(EXAMPLE)
    assert spec.parse(spec.dump(reel)) == reel
