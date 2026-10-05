"""Separate one file with a Roformer model (v1.0.14, B591).

Run by the program in the Roformer environment that ``KaraokeToolGUI.bat``
makes next to it (``venv_separator``), never in the program's own
environment: python-audio-separator pins its own torch and numpy, and
the program's Whisper and WhisperX pin theirs. Nothing of the program
is imported here for the same reason.

    python roformer_separate.py <audio> <output-dir> <model-dir> <model> [<model> ...]
    python roformer_separate.py --download <model-dir> <model> [<model> ...]
    python roformer_separate.py --selftest <model-dir> <model>

The first form writes one wav per stem into ``<output-dir>``, named
after the stem (``vocals.wav``, ``instrumental.wav``, ``other.wav``...),
and prints them as JSON. More than one model makes an ensemble, joined
with ``--algorithm``. The second form only fetches the models into
``<model-dir>``, so ``KaraokeToolGUI.bat`` can do the download while someone
is watching; a model that fails says why and the others still come.

v1.0.15 (B597): the stems keep the level of the original. The library
scales its input and its output down to a peak of 0.9 by default, and
writes 16-bit files that clip what goes over the top; both are off -
the input is handed over as a 32-bit float file, so the stems are
written as float too, and nothing is normalised. Levelling a track is
the render's job, once, on the mix it really plays (the owner's rule).

v1.0.16: the library accepts a normalisation threshold of at most 1.0 -
the 1e6 that v1.0.15 handed it stopped every Roformer separation before
it began (seen in the install log). So the threshold is 1.0, which only
ever turns a stem down when it peaks above full scale, and the library's
one normalising function is told to leave the level alone as well
(:func:`_keep_levels`). Should a later version of the library move that
function, the 1.0 still holds and the level match of 1.4 makes up for
what it turns down.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

#: The highest threshold the library accepts: it turns a stem down only
#: when that peaks above full scale.
NORMALISATION_THRESHOLD = 1.0


def _keep_levels() -> bool:
    """Make the library's normalising function leave the level alone.

    Every place in audio-separator 0.47 that scales audio calls
    ``spec_utils.normalize`` through its module, so replacing it there
    reaches them all. Its checks on the data stay; only the scaling goes.
    Returns whether it could be done.
    """
    try:
        import numpy as np
        from audio_separator.separator.uvr_lib_v5 import spec_utils
    except Exception:  # noqa: BLE001 - then the threshold of 1.0 holds
        return False
    real = spec_utils.normalize

    def unscaled(wave, max_peak=1.0, min_peak=None):
        checked = np.asarray(wave)
        if checked.size == 0 or not np.isfinite(np.abs(checked).max()):
            return real(wave, max_peak=max_peak, min_peak=min_peak)
        return checked

    spec_utils.normalize = unscaled
    return True


def _separator(model_dir: str, output_dir: str | None = None,
               algorithm: str | None = None, segment: int | None = None):
    import logging

    from audio_separator.separator import Separator

    _keep_levels()
    options = dict(log_level=logging.WARNING, model_file_dir=model_dir,
                   output_dir=output_dir, output_format="WAV",
                   normalization_threshold=NORMALISATION_THRESHOLD,
                   amplification_threshold=0.0, use_soundfile=True)
    if algorithm:
        options["ensemble_algorithm"] = algorithm
    if segment:
        # v1.0.23 (B645): smaller pieces at a time, for a small card.
        options["mdxc_params"] = {"segment_size": int(segment),
                                  "override_model_segment_size": True,
                                  "batch_size": 1, "overlap": 8,
                                  "pitch_shift": 0}
    return Separator(**options)


def stem_name(path: str) -> str:
    """``song_(Vocals)_model.wav`` -> ``vocals``; no brackets -> the
    name without its extension."""
    found = re.findall(r"\(([^()]+)\)", Path(path).name)
    name = found[-1] if found else Path(path).stem
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "stem"


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Separate one file with a Roformer model, in the "
                    "Roformer environment next to KaraokeTool.")
    parser.add_argument("paths", nargs="*",
                        help="<audio> <output-dir> <model-dir> <model> "
                             "[<model> ...]")
    parser.add_argument("--download", nargs="+", metavar="ARG",
                        help="<model-dir> <model> [<model> ...]: only "
                             "fetch the models")
    parser.add_argument("--selftest", nargs="+", metavar="ARG",
                        help="<model-dir> <model>: separate three seconds "
                             "of tone and say whether it worked")
    parser.add_argument("--segment", type=int, default=None,
                        help="work in pieces of this size (smaller takes "
                        "less card memory), e.g. 128")
    parser.add_argument("--algorithm", default=None,
                        help="how an ensemble of models is joined, e.g. "
                             "avg_wave or uvr_max_spec")
    args = parser.parse_args(argv)
    if args.download:
        if len(args.download) < 2:
            parser.error("--download needs a model folder and a model")
        separator = _separator(args.download[0])
        failed = 0
        for model in args.download[1:]:
            try:
                separator.load_model(model_filename=model)
                print(f"ready: {model}")
            except Exception as exc:  # noqa: BLE001 - say it, go on
                failed += 1
                print(f"FAILED: {model}: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
        return 1 if failed else 0
    if args.selftest:
        if len(args.selftest) != 2:
            parser.error("--selftest needs a model folder and a model")
        return selftest(*args.selftest)
    if len(args.paths) < 4:
        parser.error("audio, output folder, model folder and at least "
                     "one model")
    audio, output_dir, model_dir, *models = args.paths
    print(json.dumps(separate(audio, output_dir, model_dir, models,
                              args.algorithm, args.segment)))
    _card_peak()
    return 0


def _card_peak() -> None:
    """v1.0.22: how much of the card the separation took at most, on
    stderr - the check of a helper (1.5.18) reads it; a card that runs
    full makes Windows lay the rest in ordinary memory, very slowly."""
    try:
        import torch

        if torch.cuda.is_available():
            peak = torch.cuda.max_memory_reserved() / 2 ** 30
            total = torch.cuda.get_device_properties(0).total_memory / 2 ** 30
            print(f"card_peak_gb={peak:.2f} card_total_gb={total:.2f}",
                  file=sys.stderr)
    except Exception:  # noqa: BLE001 - a note, never a failure
        pass


def separate(audio: str, output_dir: str, model_dir: str,
             models: list[str], algorithm: str | None = None,
             segment: int | None = None) -> dict:
    """One file into its stems; ``{stem name: path}``."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    import soundfile

    data, rate = soundfile.read(audio, dtype="float32", always_2d=True)
    source = out / "_input.wav"
    soundfile.write(str(source), data, rate, subtype="FLOAT")
    separator = _separator(model_dir, str(out), algorithm, segment)
    separator.load_model(model_filename=models if len(models) > 1
                         else models[0])
    stems = {}
    for written in separator.separate(str(source)):
        path = Path(written)
        if not path.is_absolute():
            path = out / path
        target = out / f"{stem_name(path.name)}.wav"
        path.replace(target)
        stems[target.stem] = str(target)
    source.unlink(missing_ok=True)
    return stems


#: The test tone peaks this far above full scale, so a normalisation that
#: still acts shows up.
SELFTEST_PEAK = 1.2


#: What the library says of audio under ten seconds - the trial's tone is
#: three on purpose; a song never is (v1.0.24, B654).
_SHORT_AUDIO = ("is less than 10 seconds", "override_model_segment_size")


def _quiet_about_short_audio() -> None:
    """The trial separation leaves out the library's warnings about its
    short tone: they say nothing about the environment, and in the
    installer's window they read like a problem."""
    import logging

    real = logging.Filterer.filter

    def without(self, record):
        try:
            text = record.getMessage()
        except Exception:  # noqa: BLE001 - a record that cannot say
            text = ""
        if any(part in text for part in _SHORT_AUDIO):
            return False
        return real(self, record)

    logging.Filterer.filter = without


def selftest(model_dir: str, model: str) -> int:
    """A real separation of three seconds of tone (v1.0.16): whether the
    environment, the model and the writing work, and whether the level
    stays - KaraokeToolGUI.bat runs it once the models are there, so a problem
    shows while someone is watching and not halfway through a night."""
    import tempfile

    import numpy as np
    import soundfile

    _quiet_about_short_audio()
    rate = 44_100
    moment = np.arange(rate * 3) / rate
    tone = SELFTEST_PEAK * np.sin(2 * np.pi * 440.0 * moment)
    with tempfile.TemporaryDirectory() as work:
        audio = Path(work) / "tone.wav"
        soundfile.write(str(audio), np.stack([tone, tone], axis=1)
                        .astype(np.float32), rate, subtype="FLOAT")
        try:
            stems = separate(str(audio), str(Path(work) / "out"), model_dir,
                             [model])
        except Exception as exc:  # noqa: BLE001 - that is the answer
            print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        total = None
        for path in stems.values():
            data, _rate = soundfile.read(path, dtype="float32",
                                         always_2d=True)
            total = data if total is None else total[:len(data)] + \
                data[:len(total)]
        peak = float(np.abs(total).max()) if total is not None else 0.0
    kept = abs(peak - SELFTEST_PEAK) < 0.1
    print(json.dumps({"ok": bool(stems), "stems": sorted(stems),
                      "peak": round(peak, 3), "levels_kept": kept}))
    return 0 if stems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
