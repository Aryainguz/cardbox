import pytest

from cardbox.captions import chunks, schedule, spread, words


def test_chunks_break_after_punctuation_and_merge_lone_words():
    assert chunks("Wait. You're telling me it ran on one server?") == [
        ["Wait.", "You're", "telling", "me", "it"], ["ran", "on", "one", "server?"]]


def test_chunks_keep_every_word_once():
    line = "Take the arrow for king, subtract man, add woman, and the closest word is queen."
    assert [w for c in chunks(line) for w in c] == words(line)


def test_spread_covers_the_line():
    t = spread("one two three", 3.0)
    assert t[0][0] == 0 and t[-1][1] == pytest.approx(3.0)


def test_schedule_never_overlaps():
    groups = [["a", "b"], ["c"]]
    times = [(0.0, 0.5), (0.4, 0.9), (0.85, 1.2)]  # overlapping on purpose
    s = schedule(groups, times, lead=0.15)
    for (_, _, _, end), (_, _, start, _) in zip(s, s[1:]):
        assert end < start
    assert s[0][2] == pytest.approx(0.15)


def test_schedule_rejects_mismatched_timings():
    with pytest.raises(ValueError):
        schedule([["a", "b"]], [(0, 1)])
