import pytest

from cardbox.voice.align import map_words, match_score, numbers_to_digits


def test_matched_words_take_heard_times():
    t = map_words(["hello", "world"], [("Hello,", 0.1, 0.4), ("world.", 0.5, 0.9)], 1.0)
    assert t == [(0.1, 0.4), (0.5, 0.9)]


def test_unheard_words_are_interpolated_in_order():
    script = ["in", "twenty", "ten", "it", "worked"]
    heard = [("In", 0.0, 0.2), ("2010", 0.25, 0.9), ("it", 1.0, 1.1), ("worked", 1.2, 1.6)]
    t = map_words(script, heard, 1.6)
    assert len(t) == 5
    assert t[0] == (0.0, 0.2) and t[3] == (1.0, 1.1)
    assert 0.2 <= t[1][0] < t[2][0] < t[2][1] <= 1.0


def test_no_words_heard_spreads_across_the_take():
    t = map_words(["a", "bb", "ccc"], [], 3.0)
    assert t[0][0] == 0 and t[-1][1] == pytest.approx(3.0)


@pytest.mark.parametrize("spoken,digits", [
    ("ten thousand", "10000"), ("twenty-three", "23"), ("two hundred sixty-five", "265"),
    ("one million", "1000000"), ("eight", "8"),
])
def test_numbers_to_digits(spoken, digits):
    assert numbers_to_digits(spoken.split()) == [digits]


def test_match_score_ignores_number_spelling_and_punctuation():
    assert match_score("Not ten thousand steps. One.", "not 10,000 steps, 1") == 1.0


def test_match_score_catches_a_slurred_word():
    assert match_score("Team SongsPK or team Spotify", "Teams on speak a or team Spotify") < 0.7
