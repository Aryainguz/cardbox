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


@pytest.mark.parametrize("expected,heard", [
    ("My open-source tool turned them into this.", "My open source tool turned them into this."),
    ("there's a Go render API", "there's a GoRender API"),
    ("twenty-three people", "23 people"),
])
def test_match_score_ignores_word_splitting(expected, heard):
    assert match_score(expected, heard) == 1.0


def test_match_score_still_catches_paid_vs_paired():
    assert match_score("You don't need any paid AI to use it", "You don't need any paired AI to use it") < 0.97


def test_one_wrong_word_in_a_long_line_is_an_error():
    from cardbox.voice.align import word_errors

    script = ("Write what you want to say, one paragraph for each scene. The first paragraph is your hook and the last "
              "one is your ending. You don't need any paid AI for this, just write.")
    heard = script.replace("paid", "paired")
    assert match_score(script, heard) > 0.97  # the old percentage check let this through
    assert word_errors(script, heard) == 1


@pytest.mark.parametrize("expected,heard", [
    ("Name a file one dot jpg, and it goes behind the first beat.", "Name a file, 1.jpg and it goes behind the first beat."),
    ("My open-source tool did.", "My open source tool did."),
    ("Mention three hundred sixty thousand", "Mention 360,000"),
])
def test_writing_differences_are_not_errors(expected, heard):
    from cardbox.voice.align import word_errors

    assert word_errors(expected, heard) == 0
