"""The voice worker: clones lines and listens back to them.

Runs as `python -m cardbox.voice.worker jobs.json`, in whichever Python has the voice stack
(set CARDBOX_VOICE_PYTHON to use a separate environment for PyTorch). For every line it:

  1. speaks it with Chatterbox in the reference voice,
  2. transcribes the result with Whisper (word timestamps),
  3. compares the transcript with the script, and tries another seed if words came out wrong.

Cloned voices occasionally slur a word or skip one; checking each take automatically is what makes
the output publishable without listening to every line yourself.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .align import match_score

WHISPER_MODEL = os.environ.get("CARDBOX_WHISPER_MODEL", "base.en")


def _device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Listener:
    """Whisper, loaded once. Returns (text, [(word, start, end)])."""

    def __init__(self) -> None:
        import whisper

        self.model = whisper.load_model(WHISPER_MODEL)

    def __call__(self, wav: str) -> tuple[str, list[tuple[str, float, float]]]:
        r = self.model.transcribe(wav, word_timestamps=True, fp16=False, language="en")
        words = [(w["word"].strip(), float(w["start"]), float(w["end"])) for s in r["segments"] for w in s.get("words", [])]
        return r["text"].strip(), words


def run(spec: dict) -> list[dict]:
    jobs = spec.get("jobs", [])
    listener = None
    if spec.get("verify", True) or spec.get("align", True):
        try:
            listener = Listener()
        except ImportError:
            print("whisper not installed: skipping checks and word timing", file=sys.stderr)
    model = None
    if spec.get("engine") == "chatterbox":
        import torchaudio
        from chatterbox.tts import ChatterboxTTS

        model = ChatterboxTTS.from_pretrained(device=_device())
    report = []
    for job in jobs:
        out = job["out"]
        best: dict | None = None
        tries = spec.get("retries", 4) if model else 1
        for attempt in range(tries):
            seed = int(job.get("seed", 7)) + attempt * 101
            if model:
                import torch

                torch.manual_seed(seed)
                wav = model.generate(job["text"], audio_prompt_path=spec["reference"],
                                     exaggeration=spec.get("exaggeration", 0.45), cfg_weight=spec.get("cfg", 0.4))
                tmp = out + f".try{attempt}.wav"
                torchaudio.save(tmp, wav.cpu(), model.sr)
            else:
                tmp = out  # the take already exists (system voice): only listen
            heard_text, heard = listener(tmp) if listener else ("", [])
            score = match_score(job.get("expect", job["text"]), heard_text) if listener else 1.0
            if best is None or score > best["score"]:
                if best and best["file"] != out and os.path.exists(best["file"]):
                    os.remove(best["file"])
                best = {"file": tmp, "score": score, "seed": seed, "heard": heard, "text": heard_text, "attempts": attempt + 1}
            elif tmp != out:
                os.remove(tmp)
            # One wrong word in a ten-word line already scores ~0.9 and can flip the meaning
            # ("AI did" → "yeah I did"), so anything short of a near-exact match is retried.
            if score >= spec.get("min_score", 0.97):
                break
        assert best is not None
        if best["file"] != out:
            os.replace(best["file"], out)
        Path(out + ".heard.json").write_text(json.dumps({"text": best["text"], "words": best["heard"], "score": best["score"]}))
        report.append({"out": out, "score": round(best["score"], 3), "seed": best["seed"], "best_attempt": best["attempts"],
                       "tries": attempt + 1, "heard": best["text"]})
        print(json.dumps(report[-1]), file=sys.stderr, flush=True)
    return report


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text())
    report = run(spec)
    print("REPORT " + json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
