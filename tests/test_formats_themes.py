import pytest
from pydantic import ValidationError

from cardbox import cards, formats, spec, themes


@pytest.mark.parametrize("alias,name", [("reel", "vertical"), ("youtube", "landscape"), ("1:1", "square"), ("feed", "square")])
def test_format_aliases(alias, name):
    assert formats.get(alias).name == name


def test_unknown_format_rejected():
    with pytest.raises(ValidationError):
        spec.parse("title: t\nformat: cinema\nbeats: [{kind: end, text: x, say: x}]")


def test_accent_override_and_bad_hex_ignored():
    assert themes.get("midnight", "#22C55E")["accent"] == "#22C55E"
    assert themes.get("midnight", "green")["accent"] == themes.THEMES["midnight"]["accent"]


def test_light_theme_uses_deeper_status_colors():
    assert themes.get("paper")["green"] != themes.get("midnight")["green"]


@pytest.mark.parametrize("value,mood", [(True, "calm"), (False, "none"), ("tense", "tense")])
def test_music_mood(value, mood):
    r = spec.Reel(title="t", music=value, beats=[spec.End(text="x", say="x")])
    assert r.music_mood == mood


@pytest.mark.parametrize("fmt", list(formats.FORMATS))
def test_cards_render_for_every_format(fmt):
    r = spec.parse(f"title: t\nformat: {fmt}\ncaptions: box\nbeats: [{{kind: scene, scene: counter, head: Hi, say: one two}}]")
    html = cards.card_html(r, r.beats[0], 1)
    f = formats.get(fmt)
    assert f"width:{f.w}px; height:{f.h}px" in html
    assert "cap box" in cards.caption_html(r, ["one", "two"], 0)
