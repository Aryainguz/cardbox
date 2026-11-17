import numpy as np

from cardbox.voice.profile import CONSENT, PROMPTS, Profile, assess

RATE = 16000


def speech_like(seconds=3.0, level=0.3, noise=0.001):
    t = np.arange(int(RATE * seconds)) / RATE
    gate = (np.sin(2 * np.pi * 1.5 * t) > 0).astype(np.float32)  # syllables and pauses
    rng = np.random.default_rng(0)
    return (level * gate * np.sin(2 * np.pi * 180 * t) + noise * rng.standard_normal(len(t))).astype(np.float32)


def test_clean_take_passes():
    assert assess(speech_like()).ok


def test_short_take_flagged():
    assert any("short" in i for i in assess(speech_like(seconds=1.0)).issues)


def test_clipping_flagged():
    assert any("clipping" in i for i in assess(np.clip(speech_like(level=3.0), -1, 1)).issues)


def test_quiet_take_flagged():
    assert any("quiet" in i for i in assess(speech_like(level=0.005, noise=0.0001)).issues)


def test_noisy_room_flagged():
    assert any("noise" in i for i in assess(speech_like(noise=0.08)).issues)


def test_consent_comes_first():
    assert PROMPTS[0] == CONSENT


def test_new_profile_is_not_ready():
    st = Profile("me").status()
    assert st["ready"] is False and st["consent"] is False and st["next_prompt"] == 0


def test_failed_takes_do_not_count_toward_ready(tmp_path):
    import json

    p = Profile("me")
    for i in range(5):
        p.take_path(i).write_bytes(b"x")
    meta = {"consent": True, "takes": {f"{i:02d}": {"ok": i < 3} for i in range(5)}}
    p.meta_path.write_text(json.dumps(meta))
    st = p.status()
    assert st["recorded"] == 5 and st["good"] == 3 and st["ready"] is False
    assert [t.stem for t in p.good_takes()] == ["00", "01", "02"]
