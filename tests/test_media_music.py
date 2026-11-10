import numpy as np

from cardbox import media, music


def test_credit_line():
    img = media.Image(id="openverse:x", title="Bridge", url="u", thumbnail="u", width=1, height=1,
                      license="CC BY 2.0", author="Ana", page="p", provider="Openverse")
    assert img.credit() == "“Bridge” by Ana (CC BY 2.0), via Openverse"


def test_search_interleaves_sources_and_dedupes(monkeypatch):
    a = media.Image("openverse:1", "A", "https://a", "", 1, 1, "CC0", "", "", "Openverse")
    b = media.Image("commons:B", "B", "https://b", "", 1, 1, "CC BY 4.0", "", "", "Wikimedia Commons")
    monkeypatch.setattr(media, "search_openverse", lambda q, n: [a, a])
    monkeypatch.setattr(media, "search_commons", lambda q, n: [b])
    assert [i.id for i in media.search("x", 5)] == ["openverse:1", "commons:B"]


def test_one_source_failing_does_not_break_search(monkeypatch):
    def boom(q, n):
        raise OSError("down")

    b = media.Image("commons:B", "B", "https://b", "", 1, 1, "CC BY 4.0", "", "", "Wikimedia Commons")
    monkeypatch.setattr(media, "search_openverse", boom)
    monkeypatch.setattr(media, "search_commons", lambda q, n: [b])
    assert [i.id for i in media.search("x")] == ["commons:B"]


def test_music_bed_shape_and_level(tmp_path):
    s = music.bed(4.0, cuts=[1.0, 2.5])
    assert s.shape == (int(music.SR * 4.0), 2)
    assert 0.5 < float(np.abs(s).max()) <= 0.81
    out = music.write(tmp_path / "bed.wav", s)
    assert out.stat().st_size > 1000
