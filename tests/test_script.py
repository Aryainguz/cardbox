import pytest

from cardbox.script import from_text, headline

SCRIPT = """Remember SongsPK? For a whole generation, that's where music came from.

# Rejected by Google
Around then, a teenager applied for a job at Google. They said no.

# 8.8% of the music
Only eight point eight percent of the music came from the servers.

# 265 ms to start a song
The typical song started in two hundred sixty-five milliseconds.

2010 was the year it all changed, and nobody noticed.

Team SongsPK or team Spotify? Tell me in the comments."""


def test_plain_text_becomes_beats():
    r = from_text(SCRIPT, format="square", voice="none")
    assert [b.kind for b in r.beats] == ["hook", "text", "stat", "stat", "text", "end"]
    assert r.beats[0].text == "Remember SongsPK?" and r.format == "square"
    assert (r.beats[2].value, r.beats[2].label) == ("8.8%", "of the music")
    assert (r.beats[3].value, r.beats[3].label) == ("265 ms", "to start a song")
    assert r.beats[4].kind == "text"  # auto headline starting with a number stays a text card


def test_spoken_text_is_kept_exactly():
    r = from_text(SCRIPT)
    assert r.beats[1].say == "Around then, a teenager applied for a job at Google. They said no."


@pytest.mark.parametrize("spoken,shown", [
    ("Short and sweet. Second sentence.", "Short and sweet"),
    ("Checking names one by one gets slower, and a million names means a million checks.", "Checking names one by one gets slower"),
    ("This is a very long first sentence with no commas in it at all really.", "This is a very long first…"),
])
def test_headline(spoken, shown):
    assert headline(spoken) == shown


def test_needs_a_hook_and_an_ending():
    with pytest.raises(ValueError):
        from_text("Just one paragraph.")
