"""Measure which Whisper settings hear this song best (B314).

Faster-whisper skips a whole thirty-second window as soon as it decides
nothing is being sung (``no_speech_threshold``, rescued by
``log_prob_threshold``). That is the mechanism behind a hole of a minute
in the middle of a song. Which threshold is right for YOUR song cannot
be reasoned out - it has to be measured.

This tool runs the same vocal stem a few times with different settings
and puts side by side how much gets transcribed. Afterwards you put the
winning values in ``config/config.json`` under ``whisper``; the
dependency chain (B311) notices that change and has the transcription
done again.

Usage::

    python tools/whisper_probe.py Lied_S
    python tools/whisper_probe.py Lied_S --gap 135 196
    python tools/whisper_probe.py Lied_S --variants current wider

Runs on the vocal stem from the cache, so Demucs does not have to run
again.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import filesystem, whisper  # noqa: E402
from modules.config import WhisperSettings, load_config  # noqa: E402
from modules.filesystem import ProjectPaths  # noqa: E402

#: The settings that affect "is this window skipped as a whole".
#: B437: seven of the eleven variants gave a bit-identical answer twice
#: in a row - 26 segments, 196 words, one word in the gap - and the two
#: prompt lengths both gave 40/184, which is B391 answered with "no"
#: again. Together that was over half an hour per night job for
#: knowledge already on paper. They are switched OFF here rather than
#: deleted, the same way a model is switched off: the idea stays
#: readable and can be measured again in one line if something changes
#: in Whisper or in the settings.
RETIRED: dict[str, dict] = {
    "wider": {"no_speech_threshold": 0.9},
    "no_silence_threshold": {"no_speech_threshold": None},
    "logprob_loose": {"log_prob_threshold": -2.0},
    "wider_and_loose": {"no_speech_threshold": 0.9,
                      "log_prob_threshold": -2.0},
    "hallucination_jump": {"hallucination_silence_threshold": 2.0},
    "fallback_on": {"temperature": (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)},
}

VARIANTS: dict[str, dict] = {
    "current": {},
    "vad": {"vad_filter": True},
}


def vocal_stem(root: Path, project: str) -> Path:
    """The vocal stem of a project, or ``FileNotFoundError``.

    B359: this is an ordinary function and not a ``main()``. It used to
    raise ``SystemExit``, which is fine for a command-line program but
    not for something the app calls: ``SystemExit`` inherits from
    ``BaseException``, so it slips through every ``except Exception``
    and left the GUI hanging. Translating it into an exit code is the
    job of ``main()`` below.
    """
    paths = ProjectPaths(root=root, song=project)
    stem = paths.cache_dir / "demucs_stems_original" / "vocals.wav"
    if stem.exists():
        return stem
    loose = paths.cache_dir / "original.wav"
    if loose.exists():
        return loose
    raise FileNotFoundError(f"No vocal stem found for {project} in "
                            f"{paths.cache_dir}")


#: B391: prompt lengths worth measuring. The program uses 400
#: characters while the comment beside that number says Whisper only
#: truncates around 224 TOKENS - roughly 700 to 900 characters,
#: depending on the language. So less than half the available budget is
#: used, on a prompt where deduplication makes every character carry a
#: word that occurs nowhere else in it.
#:
#: Worth measuring both ways: more unique words may help Whisper
#: recognise the real vocabulary, but it is also more material to recite
#: during an instrumental stretch (the prompt echo, B390). If the longer
#: prompt fills more gap WITHOUT the segment count jumping, it is a win;
#: if the segments jump along, 400 was not conservative but right.
#: B437: was (400, 700, 900). B391 answered this with "no" twice: a
#: longer prompt gives MORE segments, FEWER words and exactly the same
#: coverage. Only the length in use is left, as a control.
PROMPT_LENGTHS = (400,)


def prompt_for_project(root: Path, project: str,
                       max_chars: int | None = None) -> str:
    """The same initial prompt the program itself uses (B263).

    B391: with ``max_chars`` a different budget, to measure whether the
    program is leaving room unused.
    """
    from modules import song_text

    paths = ProjectPaths(root=root, song=project)
    pad = paths.input_dir / song_text.LYRICS_FILENAME
    if not pad.exists():
        return ""
    words = song_text.load_lyrics(pad)
    if max_chars is None:
        return song_text.deduped_prompt_text(words)
    return song_text.deduped_prompt_text(words, max_chars=max_chars)


def _samples(stem: Path, start: float = 0.0, end: float | None = None):
    """The vocal stem as 16 kHz mono samples, optionally a slice (B390).

    Faster-whisper takes a numpy array just as happily as a path, and
    that is what makes an offset or a chunk possible at all: cut the
    audio, transcribe, and add the offset back to every time. Works with
    any version - no dependency on ``clip_timestamps``.
    """
    import librosa

    samples, rate = librosa.load(str(stem), sr=16000, mono=True)
    first = max(0, int(round(start * rate)))
    last = len(samples) if end is None else min(len(samples),
                                                int(round(end * rate)))
    return samples[first:last]


def run_once(stem: Path, settings: WhisperSettings, prompt: str,
          language: str, start: float = 0.0,
          end: float | None = None) -> list[dict]:
    """One transcription with these settings.

    B390: with ``start``/``end`` only that slice of the audio is
    transcribed and the times are shifted back onto the song's own
    timeline, so an offset run and a chunked run stay comparable to the
    first run.

    B372: the device and the compute type come from
    ``whisper._resolve_device`` - the same function the app uses. There
    used to be a private conversion here that simply passed ``None`` for
    ``device: "auto"``, and ctranslate2 wants a string there: the tool
    fell over immediately with a TypeError. Exactly the pattern of B360 -
    knowledge that lives in two places drifts apart - so now through the
    app instead of beside it.
    """
    # B419: through the app, which keeps the model in ``_MODEL_CACHE``.
    #
    # A fresh ``WhisperModel`` per call is what made the chunking trial
    # look twice as expensive as it is. Measured over 35 pieces of one
    # night job: 0.75 s of compute per second of audio plus 28.9 s FIXED
    # cost per piece - a fragment of 4.3 s took 20 s, which cannot be
    # decoding. Ten pieces meant ten times loading large-v3 from disk,
    # so of the ~450 s a chunked run took, roughly 290 s was loading.
    # That is the price of the measuring tool and it was being reported
    # as the price of the method.
    model = whisper._load_model(settings)
    audio = str(stem) if (start <= 0.0 and end is None) \
        else _samples(stem, start, end)
    raw, _info = model.transcribe(
        audio, language=None if language == "auto" else language,
        word_timestamps=True, beam_size=5,
        condition_on_previous_text=False, initial_prompt=prompt or None,
        **whisper.decode_options(settings))
    shift = float(start)
    out = []
    for s in raw:
        words = [{"text": w.word.strip(), "start": float(w.start) + shift,
                  "end": float(w.end) + shift,
                  "confidence": float(getattr(w, "probability", 0.0))}
                 for w in (s.words or ())]
        out.append({"start": float(s.start) + shift,
                    "end": float(s.end) + shift,
                    "text": s.text.strip(), "words": words})
    return out


def run_chunked(stem: Path, settings: WhisperSettings, language: str,
                chunks, prompt_for, lanes: int | None = None) -> list[dict]:
    """Transcribe every piece on its own and paste the results (B390).

    ``prompt_for(chunk)`` gives the piece its own prompt - locally there
    is room for the real lines instead of a deduplicated word list.

    B423: the pieces go through the work slots instead of one after
    another. This was the longest single item of the night job - 400 to
    640 s per song, strictly serial, while Whisper releases the GIL and
    the model has been allowed to serve several callers since B422. The
    user's rule, in his own words: put as much as possible in the queue.
    """
    import threading

    from modules import measure_pool

    pieces = list(chunks)
    if not pieces:
        return []
    slots = max(1, lanes or measure_pool.whisper_lanes())
    if slots == 1 or len(pieces) == 1:
        out: list[dict] = []
        for chunk in pieces:
            out.extend(run_once(stem, settings, prompt_for(chunk), language,
                                start=chunk.start, end=chunk.end))
        return sorted(out, key=lambda s: s["start"])

    queue = list(pieces)
    found: list[dict] = []
    lock = threading.Lock()

    def worker() -> None:
        while True:
            with lock:
                if not queue:
                    return
                chunk = queue.pop(0)
            part = run_once(stem, settings, prompt_for(chunk), language,
                            start=chunk.start, end=chunk.end)
            with lock:
                found.extend(part)

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(min(slots, len(pieces)))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(found, key=lambda s: s["start"])


def coverage(segments: list[dict], gap: tuple[float, float]) -> float:
    """How many seconds of the given stretch carry a WORD (B410).

    Deliberately words and no longer segment spans. A segment is only a
    bracket around words, and how wide that bracket is says nothing
    about whether anything was heard inside it: VAD produced twelve
    segments instead of twenty-six on the measured song, and one such
    long segment lies over the hole without a single word standing in
    it. That scored 26.4 of 28 s "covered" while the word count went
    DOWN - a win the measurement could not tell apart from a bracket.
    A word has a mouth behind it, a bracket does not.
    """
    lo, hi = gap
    total = 0.0
    for segment in segments:
        for word in segment.get("words") or ():
            start, end = float(word["start"]), float(word["end"])
            if end > lo and start < hi:
                total += min(end, hi) - max(start, lo)
    return total


def words_within(segments: list[dict], gap: tuple[float, float]) -> int:
    """How many words BEGIN inside the given stretch (B410)."""
    lo, hi = gap
    return sum(1 for segment in segments
               for word in (segment.get("words") or ())
               if lo <= float(word["start"]) < hi)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--root", default=str(Path(__file__).resolve()
                                              .parents[1]))
    parser.add_argument("--gap", nargs=2, type=float, metavar=("FROM", "TO"),
                        help="the stretch you know is sung but yields nothing")
    parser.add_argument("--variants", nargs="*", default=list(VARIANTS))
    parser.add_argument("--language", default="")
    args = parser.parse_args()

    root = Path(args.root)
    try:
        stem = vocal_stem(root, args.project)
    except FileNotFoundError as exc:
        # Here it does belong: a command-line program stops with an
        # exit code (B359).
        raise SystemExit(str(exc)) from exc
    prompt = prompt_for_project(root, args.project)
    base = load_config(root / "config" / "config.json").whisper
    language = args.language or base.language
    out_dir = root / "output" / args.project / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"vocal stem : {stem}")
    print(f"sha1       : {filesystem.file_sha1(stem)[:12]}")
    print(f"prompt     : {len(prompt.split())} words")
    print()
    results = {}
    for name in args.variants:
        if name not in VARIANTS:
            print(f"unknown variant: {name}")
            continue
        settings = replace(base, **VARIANTS[name])
        started = time.perf_counter()
        segments = run_once(stem, settings, prompt, language)
        elapsed = time.perf_counter() - started
        results[name] = {"options": {k: str(v) for k, v
                                       in VARIANTS[name].items()},
                            "segments": segments,
                            "seconds": round(elapsed, 1)}
        row = (f"{name:22s} segments {len(segments):3d}  "
                 f"words ~{sum(len(s['text'].split()) for s in segments):4d}"
                 f"  {elapsed:5.0f} s")
        if args.gap:
            row += (f"  in the gap {coverage(segments, tuple(args.gap)):5.1f}"
                      f" of {args.gap[1] - args.gap[0]:.0f} s")
        print(row, flush=True)

    target = out_dir / "whisper_probe.json"
    target.write_text(json.dumps(results, indent=1, ensure_ascii=False),
                    encoding="utf-8")
    print(f"\nfull results: {target}")
    print("Put the winning values in config/config.json under 'whisper'; "
          "the transcription is then redone automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
