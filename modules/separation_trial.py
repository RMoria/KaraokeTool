"""1.5.14 - which separation makes the better music track (v1.0.14, B592).

The owner heard Demucs weaken the music in places where the band does
not stop at all, and asked for a test before any setting changes: the
music track first, what the transcription gains a bonus - "even if it
is only a few percent in certainty". Every song with a hand timing is
separated again, from its own original, in each way:

* **Demucs** - the program as it is (the standard way);
* **Demucs careful** - the fine-tuned bag with two shifts, about eight
  times the work;
* **Roformer** - a Roformer model that splits voice from music;
* **Roformer karaoke** - a Roformer model that leaves the backing choir
  in the music. Its voice track is the lead voice alone; since v1.0.15
  (B598) the transcription is measured on it too - does Whisper do
  better without a choir singing other words?
* since v1.0.15 (B598) also a newer Roformer model, two combinations
  of models the library ships as presets (clean music, clean vocals),
  the three karaoke models together, the voice with the echo taken off
  by a second model, and a crowd model, measured on how much louder its
  stem is in the lines marked [crowd] than in the others;
* since v1.0.22 (B631) the Demucs blend: both Demucs ways, halved. The
  rounds of the ways a blend is made of keep their stems beside the
  test (:mod:`modules.stem_store`), and a blend round takes its parts
  from there where they are - so a later blend of Roformer models does
  not separate every part once more;
* since v1.0.23 (B643) the three ensembles - clean music, clean voice,
  the karaoke trio - are blends of their models as well: every model a
  round of its own through the queue (its stems kept), and the blend
  round after them joins them and measures. A task is one model instead
  of three, and the models of one song can run on three computers. They
  are joined by the program's own blend, which is close to the
  library's but not the same, so they are measured anew under new tags;
  what the library's ensembles measured stays kept.

The Roformer ways need their own environment (``KaraokeToolGUI.bat``); when it
is not there they are left out and the report says how to add them.

What is measured, per song and way:

* the music: how many words Whisper still hears in it while the hand
  timing says someone sings (vocal residue), and how many seconds it
  drops far below its own level where the original does not (a band
  break is quiet in the original too; a dip the separation made is not);
* the voice, for the transcription: Whisper's mean certainty, the share
  of heard words that are in the lyrics, the measured singing (the hand
  lines) with no word on it, and how many hand line starts have a heard
  word starting within 0.3 s.

Everything happens in ``_to_delete`` next to the program: the original
converted there, the stems made there, and per song an mp3 of the music
and the voice of every way to listen to. The projects are only read.
Results are kept per song and way, so a night broken off goes on where
it stopped - and since v1.0.15 per way's models rather than per program
version, so a new version only measures what is new.
"""
from __future__ import annotations

import json
import logging
import shutil
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from . import pipeline, separation, whisper
from .translations import t

logger = logging.getLogger(__name__)

SCRATCH_NAME = "kt_separation"

#: A heard word starting this close to a hand line start hits it.
HIT_S = 0.3

#: Envelope frames for the dips, and how far below its own median the
#: music has to fall while the original stays within ``MIX_QUIET_DB`` of
#: its median. A band break drops in the original as well and does not
#: count.
FRAME_S = 0.5
DIP_DB = 12.0
MIX_QUIET_DB = 10.0


@dataclass(frozen=True)
class Way:
    """One way to separate, for this trial."""

    key: str
    way: separation.Way
    #: Is the transcription measured on its voice track? For a karaoke
    #: model that is the lead voice alone (B598).
    voice: bool = True
    #: A second Roformer model run on the voice track, whose clean stem
    #: is then the voice - taking the echo off, say (B598).
    then: str = ""
    #: "separation", or "crowd": how much of the crowd stem falls in the
    #: lines marked [crowd] (B598).
    measure: str = "separation"

    @property
    def tag(self) -> str:
        """What its results are kept under: the models and how they are
        used, not the program version, so a new version measures only
        what is new (B598)."""
        tag = self.way.tag
        if self.then:
            tag += f" then {self.then}"
        if self.measure != "separation":
            tag += f" {self.measure}"
        elif not self.voice:
            tag += " music"
        return tag


#: B598: models the 2024 choice has been overtaken by, and combinations
#: the library ships as presets (python-audio-separator 0.47).
BECRUILY_VOCALS = "mel_band_roformer_vocals_becruily.ckpt"
MUSIC_CLEAN = separation.MUSIC_CLEAN
VOICE_CLEAN = ("bs_roformer_vocals_revive_v2_unwa.ckpt"
               "+mel_band_roformer_kim_ft2_bleedless_unwa.ckpt")
KARAOKE_TRIO = ("mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
                "+mel_band_roformer_karaoke_gabox_v2.ckpt"
                "+mel_band_roformer_karaoke_becruily.ckpt")
DEREVERB = "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt"
CROWD = "mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt"

def _blend_of(models: str, algorithm: str) -> separation.Way:
    """v1.0.23 (B643): an ensemble as a blend of its single models."""
    return separation.Way("blend", "", 1, algorithm, tuple(
        separation.Way("roformer", model) for model in models.split("+")))


WAYS: tuple[Way, ...] = (
    Way("demucs", separation.way_for("standard")),
    Way("demucs_careful", separation.way_for("careful")),
    Way("roformer", separation.way_for("roformer", "vocals")),
    Way("roformer_karaoke", separation.way_for("roformer", "karaoke")),
    Way("roformer_becruily", separation.Way("roformer", BECRUILY_VOCALS)),
    Way("roformer_music_clean", _blend_of(MUSIC_CLEAN, "max_spec")),
    Way("roformer_voice_clean", _blend_of(VOICE_CLEAN, "min_spec")),
    Way("roformer_karaoke_trio", _blend_of(KARAOKE_TRIO, "avg_wave")),
    Way("roformer_dry", separation.way_for("roformer", "vocals"),
        then=DEREVERB),
    Way("roformer_crowd", separation.Way("roformer", CROWD),
        measure="crowd"),
    # v1.0.22 (B631): the blend of both Demucs ways.
    Way("demucs_blend", separation.way_for("demucs_blend")),
    # v1.0.28: the owner's next question - the Demucs blend and clean
    # music joined. Its parts are kept stems of the rounds above, so it
    # costs a blend, not three separations.
    Way("demucs_music_clean", separation.BLENDS["demucs_music_clean"]),
    # v1.0.28 (B667): the Demucs blend with its dips repaired - the same
    # two kept parts, only joined again.
    Way("demucs_blend_repair", separation.BLENDS["demucs_repair"]),
)


def kept_parts() -> set[str]:
    """The tags of the ways whose stems a blend of this test takes: their
    rounds keep their stems (B632)."""
    return {part.tag for way in WAYS if way.way.backend == "blend"
            for part in way.way.parts}


def keeps_stems(way: Way) -> bool:
    """Does a round of this way use the stem store?"""
    return way.measure == "separation" and not way.then and (
        way.way.backend == "blend" or way.way.tag in kept_parts())

#: What the ways of v1.0.14 were called, so what that version measured
#: is kept under the new names (B598).
_LEGACY_TAGS = {
    "demucs": WAYS[0].tag, "demucs_careful": WAYS[1].tag,
    "roformer": WAYS[2].tag, "roformer_karaoke": WAYS[3].tag + " music",
}


# --------------------------------------------------------------------------
# The measures, each on plain numbers
# --------------------------------------------------------------------------

def _envelope_db(samples: np.ndarray, rate: int,
                 frame_s: float = FRAME_S) -> np.ndarray:
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    size = max(1, int(rate * frame_s))
    count = len(mono) // size
    if count == 0:
        return np.zeros(0)
    frames = mono[:count * size].reshape(count, size)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    return 20.0 * np.log10(np.maximum(rms, 1e-7))


def dip_spans(music: np.ndarray, music_rate: int, mix: np.ndarray,
              mix_rate: int, frame_s: float = FRAME_S,
              least_s: float = 1.0) -> list[tuple[float, float]]:
    """v1.0.28 (B668): where the music falls away while the original
    plays on, as ``(start, end)`` in seconds - runs of at least
    ``least_s``, the measure of :func:`dip_seconds` placed in time."""
    left = _envelope_db(music, music_rate, frame_s)
    right = _envelope_db(mix, mix_rate, frame_s)
    count = min(len(left), len(right))
    if count == 0:
        return []
    left, right = left[:count], right[:count]
    playing = right > float(np.median(right)) - MIX_QUIET_DB
    if not playing.any():
        return []
    level = float(np.median(left[playing]))
    dips = playing & (left < level - DIP_DB)
    spans = []
    frame = 0
    while frame < count:
        if not dips[frame]:
            frame += 1
            continue
        start = frame
        while frame < count and dips[frame]:
            frame += 1
        if (frame - start) * frame_s >= least_s:
            spans.append((round(start * frame_s, 1), round(frame * frame_s, 1)))
    return spans


def dip_seconds(music: np.ndarray, music_rate: int, mix: np.ndarray,
                mix_rate: int, frame_s: float = FRAME_S) -> float:
    """Seconds where the music falls far below its own level while the
    original plays on: what a separation took away that the band did
    not stop. Each track is framed at its own rate, so the frames line
    up in time whatever the two rates are."""
    left = _envelope_db(music, music_rate, frame_s)
    right = _envelope_db(mix, mix_rate, frame_s)
    count = min(len(left), len(right))
    if count == 0:
        return 0.0
    left, right = left[:count], right[:count]
    playing = right > float(np.median(right)) - MIX_QUIET_DB
    if not playing.any():
        return 0.0
    level = float(np.median(left[playing]))
    dips = playing & (left < level - DIP_DB)
    return round(float(dips.sum()) * frame_s, 2)


def residue_words(words: Sequence[dict],
                  sung: Sequence[tuple[float, float]]) -> int:
    """Words heard in the music while the hand timing says someone
    sings: voice the separation left behind."""
    count = 0
    for word in words:
        middle = (float(word["start"]) + float(word["end"])) / 2
        if any(low <= middle <= high for low, high in sung):
            count += 1
    return count


def line_hits(words: Sequence[dict], starts: Sequence[float],
              within: float = HIT_S) -> float:
    """Share (%) of hand line starts with a heard word starting near."""
    if not starts:
        return 0.0
    begins = sorted(float(word["start"]) for word in words)
    hit = 0
    for start in starts:
        if any(abs(begin - start) <= within for begin in begins):
            hit += 1
    return round(100.0 * hit / len(starts), 1)


def crowd_contrast(stem: np.ndarray, rate: int,
                   crowd: Sequence[tuple[float, float]],
                   other: Sequence[tuple[float, float]]) -> float | None:
    """How much louder the crowd stem is in the [crowd] lines than in
    the other sung lines, in dB (B598). High: the model hears what the
    owner marked as crowd. ``None`` without both kinds of line."""
    mono = stem.mean(axis=1) if stem.ndim == 2 else stem

    def level(spans) -> float | None:
        parts = [mono[int(a * rate):int(b * rate)] for a, b in spans
                 if b > a]
        parts = [part for part in parts if part.size]
        if not parts:
            return None
        joined = np.concatenate(parts).astype(np.float64)
        return float(np.sqrt(np.mean(joined ** 2)))

    inside, outside = level(crowd), level(other)
    if inside is None or outside is None or outside <= 0 or inside <= 0:
        return None
    return round(20.0 * np.log10(inside / outside), 2)


def _dry_stem(stems: dict) -> Path:
    """The stem of a de-reverb model without the echo."""
    for name in ("noreverb", "no_reverb", "dry", "dereverb"):
        if name in stems:
            return stems[name]
    rest = [path for name, path in stems.items() if "reverb" not in name
            and name not in ("vocals", "instrumental")]
    if rest:
        return rest[0]
    raise separation.SeparationError(t("err_roformer_no_stems"))


def mean_certainty(words: Sequence[dict]) -> float:
    values = [float(word.get("confidence", 0.0)) for word in words]
    return round(statistics.mean(values), 4) if values else 0.0


# --------------------------------------------------------------------------
# One song in one way
# --------------------------------------------------------------------------

def scratch_root(context) -> Path:
    """``_to_delete`` next to the program folder, like 1.5.13."""
    from .front_to_back import scratch_root as beside

    return beside(context).parent / SCRATCH_NAME


def _hand_spans(context, song: str) -> list[tuple[float, float]]:
    from .front_to_back import _hand_lines

    other = pipeline.context_for_project(pipeline.read_only(context), song)
    lines = _hand_lines(other.paths.output_dir) or []
    out = []
    for line in lines:
        pieces = line.get("syllables") or []
        if pieces:
            out.append((float(pieces[0]["start"]),
                        float(pieces[-1]["end"])))
    return out


def _crowd_spans(context, song: str) -> tuple[list, list]:
    """The hand lines marked [crowd] (whole or partly), and the others."""
    from .front_to_back import _hand_lines

    other = pipeline.context_for_project(pipeline.read_only(context), song)
    crowd, rest = [], []
    for line in _hand_lines(other.paths.output_dir) or []:
        pieces = line.get("syllables") or []
        if not pieces:
            continue
        span = (float(pieces[0]["start"]), float(pieces[-1]["end"]))
        marked = [(float(p["start"]), float(p["end"])) for p in pieces
                  if p.get("crowd")]
        if line.get("crowd"):
            crowd.append(span)
        elif marked:
            crowd += marked
        else:
            rest.append(span)
    return crowd, rest


def _heard(audio: Path, settings, language: str, prompt: str,
           cancelled) -> list[dict]:
    from . import whisper_chunks as wc

    with tempfile.TemporaryDirectory() as folder:
        segments = whisper.transcribe(
            audio, settings, Path(folder),
            language_override=language or None, cancelled=cancelled,
            initial_prompt=prompt)
    return wc.words_of(segments)


def _listening_copy(source: Path, target: Path) -> None:
    from . import ffmpeg

    try:
        ffmpeg.encode_mp3(source, target, 44100, 2, vbr_quality=4)
    except Exception:  # noqa: BLE001 - a copy to listen to is a bonus
        logger.warning(t("log_report_write_failed"), target)


def song_facts(context, song: str) -> dict:
    """Everything a round needs to know of a song's project, as plain
    data (v1.0.18): a helper computer has the song's original and this,
    and no project at all."""
    from . import song_text

    project = pipeline.context_for_project(pipeline.read_only(context),
                                           song)
    prompt = ""
    lyrics = project.paths.input_dir / song_text.LYRICS_FILENAME
    if lyrics.exists():
        prompt = song_text.deduped_prompt_text(
            pipeline._effective_lyrics(project, lyrics))
    inside, outside = _crowd_spans(context, song)
    return {"song": song,
            "sung": [list(span) for span in _hand_spans(context, song)],
            "crowd": [[list(span) for span in inside],
                      [list(span) for span in outside]],
            "language": pipeline._language_for(project,
                                               pipeline.TRACK_ORIGINAL),
            "prompt": prompt,
            "keys": sorted(pipeline.lyric_keys(project)),
            "whisper": settings_data(context.config.whisper)}


def settings_data(settings) -> dict:
    """Whisper's settings as plain data."""
    from dataclasses import asdict

    return {key: (list(value) if isinstance(value, tuple) else value)
            for key, value in asdict(settings).items()}


def settings_from(data: dict):
    """Whisper's settings back from plain data; what this version does
    not know is left out, what it knows and the data lacks keeps its
    default."""
    from dataclasses import fields

    from .config import WhisperSettings

    names = {field.name for field in fields(WhisperSettings)}
    return WhisperSettings(**{
        key: (tuple(value) if isinstance(value, list) else value)
        for key, value in dict(data or {}).items() if key in names})


def measure_one(context, song: str, way: Way, mix_wav: Path, work: Path,
                listen: Path, cancelled) -> dict:
    """Separate one song one way and measure it, on this computer."""
    return measure_with(song_facts(context, song), way, mix_wav, work,
                        listen, cancelled)


def measure_with(facts: dict, way: Way, mix_wav: Path, work: Path,
                 listen: Path, cancelled, settings=None,
                 store=None) -> dict:
    """One round from plain data - on the laptop or on a helper.
    ``store``: the kept stems of this song (v1.0.22), or ``None``."""
    from . import audio as audio_module
    from .test_panel import in_the_text
    from . import whisper_chunks as wc

    settings = settings or settings_from(facts.get("whisper"))
    sung = [tuple(span) for span in facts.get("sung", ())]
    language = facts.get("language", "")
    began = time.monotonic()
    try:
        if way.measure == "crowd":
            stems = separation.separate_roformer(mix_wav, work,
                                                 way.way.model)
            crowd_stem = stems.get("crowd") or next(iter(stems.values()))
            data, rate = audio_module.load_audio(crowd_stem)
            inside, outside = facts.get("crowd", ([], []))
            return {"crowd": crowd_contrast(
                        data, rate, [tuple(span) for span in inside],
                        [tuple(span) for span in outside]),
                    "seconds": round(time.monotonic() - began, 1)}
        if store is not None and keeps_stems(way):
            stems = separation.separate_way(mix_wav, work, way.way, store)
        else:
            stems = separation.separate_way(mix_wav, work, way.way)
        if way.then:
            stems = dict(stems)
            stems["vocals"] = _dry_stem(separation.separate_roformer(
                stems["vocals"], work / "then", way.then))
        # v1.0.20: where the time goes - the card lane of one helper
        # took hours over rounds the laptop does in one, and only the
        # split into separating and listening can say which part is slow.
        separated = round(time.monotonic() - began, 1)
        music, rate = audio_module.load_audio(stems["instrumental"])
        mix, mix_rate = audio_module.load_audio(mix_wav)
        out = {"dips": dip_seconds(music, rate, mix, mix_rate),
               "separate_s": separated,
               "whisper_device": whisper._resolve_device(
                   settings)[0]}
        del music, mix
        out["residue"] = residue_words(
            _heard(stems["instrumental"], settings, language, "",
                   cancelled), sung)
        if way.voice:
            words = _heard(stems["vocals"], settings, language,
                           facts.get("prompt", ""), cancelled)
            out.update({
                "certainty": mean_certainty(words),
                "in_text": round(in_the_text(
                    words, frozenset(facts.get("keys", ()))), 2),
                "unheard": round(wc.unheard_seconds(words, sung), 2),
                "hits": line_hits(words, [low for low, _high in sung]),
                "words": len(words)})
        _listening_copy(stems["instrumental"], listen / f"{way.key}_music.mp3")
        _listening_copy(stems["vocals"], listen / f"{way.key}_voice.mp3")
        out["seconds"] = round(time.monotonic() - began, 1)
        return out
    except whisper.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - one song, not the night
        logger.exception(t("log_separation_trial_failed"),
                         facts.get("song", "?"), way.key)
        return {"failed": separation.last_line(str(exc))}
    finally:
        shutil.rmtree(work, ignore_errors=True)


#: The kind of job a round of this test is, in the work queue.
JOB_KIND = "separation_round"


def run_round(job: dict, queue, stop) -> dict:
    """A round of 1.5.14 as a job of the work queue (v1.0.18). The
    helper sets on which device Whisper listens (``KT_WHISPER_DEVICE``,
    ``KT_WHISPER_COMPUTE``); the separation takes the card by itself
    when the process may see one."""
    import os
    from dataclasses import replace

    payload = job["payload"]
    if payload.get("part"):
        return part_round(job, queue, stop)
    way = next(way for way in WAYS if way.key == payload["way"])
    settings = settings_from(payload["facts"].get("whisper"))
    device = os.environ.get("KT_WHISPER_DEVICE")
    if device:
        settings = replace(settings, device=device,
                           compute_type=os.environ.get(
                               "KT_WHISPER_COMPUTE", "auto"))
    if os.environ.get("KT_FREE_CARD"):
        # A small graphics card: the Whisper model of the last round out
        # of the way before the separation needs the card.
        whisper.release_models()
    store = None
    if payload.get("stems"):
        from .stem_store import StemStore

        store = StemStore(queue.root / payload["stems"])
    from .local_copy import fetched

    # v1.0.23 (B647): the song fetched once, not read over the network.
    with fetched(queue.root, job["id"], [payload["mix"]]) as (mix,), \
            tempfile.TemporaryDirectory(prefix="kt_round_",
                                        ignore_cleanup_errors=True) as folder:
        try:
            return measure_with(payload["facts"], way, mix,
                                Path(folder) / "work",
                                queue.out_dir(job["id"]), stop, settings,
                                store)
        except whisper.CancelledError:
            return {"cancelled": True}


def needs_of(way: Way) -> list[str]:
    """What a computer needs for a round of this way."""
    return ["ffmpeg", *sorted(separation.backends(way.way))] + (
        ["roformer"] if way.then else [])


def stems_folder(root: Path, queue, song: str, mix: Path) -> str:
    """Where the kept stems of a song are, as a path from the queue (the
    helpers reach it through the share), or empty when the test's folder
    is not beside the queue (v1.0.22). Named after the song's audio and
    the Demucs installed: a new original or another Demucs gets stems of
    its own, never the old ones."""
    from . import work_queue

    sign = f"{song}|{separation._source_checksum(mix)}|" \
           f"{separation._demucs_version()}"
    folder = root / "stems" / work_queue.job_id(sign)
    try:
        relative = folder.relative_to(queue.root.parent)
    except ValueError:
        return ""
    return Path("..").joinpath(relative).as_posix()


def local_capabilities() -> set[str]:
    """What the program's own computer can do, without trying (the test
    already tried Roformer once before the night)."""
    from . import ffmpeg

    have = {"whisper", "processor"}
    if ffmpeg.is_available():
        have.add("ffmpeg")
    if separation.is_available():
        have.add("demucs")
    if separation.roformer_python() is not None:
        have.add("roformer")
    # v1.0.23 (B652): the forced aligner, for the rounds that lay the
    # text on the voice.
    from . import word_alignment

    if word_alignment.is_available():
        have.add("whisperx")
    return have


# --------------------------------------------------------------------------
# The trial
# --------------------------------------------------------------------------

def _way_name(way: Way) -> str:
    return t(f"sep_{way.key}")


def _average(rows: list[dict], name: str) -> float | None:
    values = [float(row[name]) for row in rows
              if row.get(name) is not None]
    return statistics.mean(values) if values else None


def _cell(value: float | None, pattern: str) -> str:
    return "-" if value is None else pattern.format(value)


def report_lines(results: dict, songs: Sequence[str],
                 ways: Sequence[Way], skipped: Sequence[Way]) -> list[str]:
    """The table: per way the means over the songs it managed."""
    lines = [t("separation_trial_cols"), "| --- |" + " ---: |" * 8]

    def measured(song: str, key: str) -> dict:
        row = results.get(song, {}).get(key) or {}
        return row if row and "failed" not in row else {}

    for way in ways:
        if way.measure != "separation":
            continue
        good = [measured(song, way.key) for song in songs
                if measured(song, way.key)]
        certainty = _average(good, "certainty")
        # The gain against Demucs over the songs both managed.
        both = [song for song in songs if measured(song, way.key)
                and measured(song, WAYS[0].key)]
        base_certainty = _average([measured(song, WAYS[0].key)
                                   for song in both], "certainty")
        mine = _average([measured(song, way.key) for song in both],
                        "certainty")
        gain = (100.0 * (mine - base_certainty) / base_certainty
                if mine is not None and base_certainty else None)
        lines.append(
            f"| {_way_name(way)} | {len(good)} |"
            f" {_cell(_average(good, 'residue'), '{:.1f}')} |"
            f" {_cell(_average(good, 'dips'), '{:.1f}')} |"
            f" {_cell(certainty, '{:.3f}')}"
            f"{'' if gain is None else f' ({gain:+.1f}%)'} |"
            f" {_cell(_average(good, 'in_text'), '{:.1f}%')} |"
            f" {_cell(_average(good, 'unheard'), '{:.1f}')} |"
            f" {_cell(_average(good, 'hits'), '{:.1f}%')} |"
            f" {_cell(_average(good, 'seconds'), '{:.0f}')} |")
    for way in skipped:
        lines.append(f"| {_way_name(way)} | "
                     + t("separation_trial_not_installed") + " |"
                     + " |" * 7)
    for way in ways:
        if way.measure != "crowd":
            continue
        rows = [measured(song, way.key).get("crowd") for song in songs]
        values = [value for value in rows if value is not None]
        lines += ["", t("separation_trial_crowd").format(
            songs=len(values),
            contrast=f"{statistics.mean(values):+.1f}" if values else "-")]
    return lines


#: Bump when what is measured changes, not when the program does.
MEASURE_FORMAT = 2


def kept_results(stored: dict, remeasure: bool = False) -> dict:
    """What earlier runs measured, under the tags of today (B598).

    The results are kept per song and per way - its models and how they
    are used - and no longer thrown away with every new version of the
    program: a night of careful Demucs costs a day, and a new version
    should only measure what is new. v1.0.14 kept them per way name;
    those are carried over under their tags.
    """
    if remeasure:
        return {"format": MEASURE_FORMAT, "runs": {}}
    if stored.get("format") == MEASURE_FORMAT:
        stored.setdefault("runs", {})
        return stored
    runs = {}
    if stored.get("version") == "1.0.14":
        for key, value in (stored.get("runs") or {}).items():
            parts = key.split("|")
            if len(parts) == 3 and parts[2] in _LEGACY_TAGS:
                runs[f"{parts[0]}|{parts[1]}|{_LEGACY_TAGS[parts[2]]}"] = \
                    value
    return {"format": MEASURE_FORMAT, "runs": runs}


def run(context, report, cancelled) -> str:
    """1.5.14 itself. Returns the report as text."""
    from . import __version__, test_panel, work_queue
    from .front_to_back import _inputs_of, songs_with_hand_timing

    songs = songs_with_hand_timing(context)
    if not songs:
        return t("front_to_back_nothing")
    root = scratch_root(context)
    store_path = root / "results.json"
    try:
        stored = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    stored = kept_results(stored, test_panel.REMEASURE)
    runs: dict = stored["runs"]
    ways = [way for way in WAYS if separation.is_available(way.way)]
    # v1.0.16: one real separation before the night, so an environment
    # that imports but cannot separate costs half a minute, not a night.
    broken = None
    if any("roformer" in separation.backends(way.way) for way in ways):
        broken = separation.roformer_selftest()
        if broken:
            logger.warning(t("log_roformer_broken"), broken)
            ways = [way for way in ways
                    if "roformer" not in separation.backends(way.way)]
    skipped = [way for way in WAYS if way not in ways]
    prior = {}
    for way in ways:
        spent = [float(run["seconds"]) for key, run in runs.items()
                 if key.endswith("|" + way.tag) and run.get("seconds")]
        if spent:
            prior[way.key] = statistics.mean(spent)
    # What is still to do, up front: a round kept from an earlier night
    # is neither counted nor timed, so the time left is the time of the
    # work that is really left.
    inputs_of = {song: _inputs_of(context, song) for song in songs}
    todo_of = {song: [way for way in ways
                      if f"{song}|{inputs_of[song]}|{way.tag}" not in runs
                      or "failed" in runs[f"{song}|{inputs_of[song]}|"
                                          f"{way.tag}"]]
               for song in songs}
    # v1.0.23 (B643): the parts of the blends to do, a round each, first -
    # unless the part is a way of its own still to do in this run.
    parts_of = {song: _parts_to_make(todo_of[song]) for song in songs}
    plan = [PART for song in songs for _part in parts_of[song]] + \
        [way.key for song in songs for way in todo_of[song]]
    steps = test_panel.Steps(report, "1.5.14", len(plan), plan=plan,
                             prior=prior,
                             forecast=work_queue.forecaster(
                                 work_queue.queue_for(context), __version__))
    failed_songs = _share_out(context, songs, ways, todo_of, inputs_of,
                              runs, stored, store_path, root, steps,
                              report, cancelled, parts_of)
    results: dict = {}
    for song in songs:
        for way in ways:
            key = f"{song}|{inputs_of[song]}|{way.tag}"
            if song in failed_songs and way in todo_of[song]:
                results.setdefault(song, {})[way.key] = {
                    "failed": failed_songs[song]}
            elif key in runs:
                results.setdefault(song, {})[way.key] = runs[key]

    lines = ["## " + t("separation_trial_title"), "",
             t("separation_trial_intro").format(count=len(songs),
                                                folder=root / "listen"), ""]
    lines += report_lines(results, songs, ways, skipped)
    if skipped:
        problem = broken or separation.roformer_problem()
        if problem and separation.roformer_python() is not None:
            # There, but broken: say what broke, not "missing".
            lines += ["", t("separation_trial_broken").format(
                problem=problem)]
        else:
            lines += ["", t("separation_trial_install_hint")]
    helpers = _by_worker(results)
    if helpers:
        lines += ["", t("separation_trial_helpers")]
        lines += [t("separation_trial_helper_row").format(
            worker=worker, rounds=count, hours=seconds / 3600.0,
            minutes=seconds / 60.0 / max(1, count),
            separating=("-" if share < 0 else f"{100.0 * share:.0f}%"),
            whisper=device)
            for worker, (count, seconds, share, device)
            in sorted(helpers.items())]
    failures = [(song, key, value["failed"])
                for song, per in results.items()
                for key, value in per.items() if "failed" in value]
    if failures:
        lines += ["", t("front_to_back_failures")]
        lines += [f"- {song} / {key}: {why}" for song, key, why in failures]
    return "\n".join(lines)


#: The kind of step a part round is in the time left.
PART = "part"


def _parts_to_make(todo: Sequence[Way]) -> list[separation.Way]:
    """The parts of the blends in ``todo`` that need a round of their
    own: every part once, and not a part that is a way of its own in
    ``todo`` (its round keeps its stems anyway)."""
    own = {way.way.tag for way in todo
           if way.way.backend != "blend" and keeps_stems(way)}
    out: list[separation.Way] = []
    for way in todo:
        if way.way.backend != "blend":
            continue
        for part in way.way.parts:
            if part.tag not in own and part not in out:
                out.append(part)
    return out


def part_round(job: dict, queue, stop) -> dict:
    """The stems of one part of a blend, kept for the blend round."""
    from .stem_store import StemStore

    import os

    payload = job["payload"]
    part = separation.way_from(payload["part"])
    store = StemStore(queue.root / payload["stems"])
    began = time.monotonic()
    if store.has(part.tag):
        return {"kept": part.tag, "seconds": 0.0}
    if os.environ.get("KT_FREE_CARD"):
        # A card lane: the Whisper model of the last round off the card
        # before a separation needs it, as ``run_round`` does.
        whisper.release_models()
    from .local_copy import fetched

    with fetched(queue.root, job["id"], [payload["mix"]]) as (mix,), \
            tempfile.TemporaryDirectory(prefix="kt_part_",
                                        ignore_cleanup_errors=True) as folder:
        try:
            separation.separate_way(mix, Path(folder) / "work", part, store)
        except separation.SeparationError as exc:
            return {"failed": separation.last_line(str(exc))}
    if stop():
        return {"cancelled": True}
    return {"kept": part.tag, "seconds": round(time.monotonic() - began, 1)}


def queue_root(context) -> Path:
    """The work queue (kept for the tests of v1.0.18)."""
    from . import work_queue

    return work_queue.queue_for(context).root


def _share_out(context, songs, ways, todo_of, inputs_of, runs, stored,
               store_path, root, steps, report, cancelled,
               parts_of=None) -> dict:
    """Every round still to do as a job of the work queue, worked on by
    whichever computer takes it - this one too, unless a helper runs on
    it - and every answer taken over into ``runs`` as it comes in
    (v1.0.18; the queue itself is :func:`work_queue.run_jobs` since
    v1.0.19). Returns the songs that could not be put out, with why."""
    from . import __version__, ffmpeg, filesystem, test_panel, work_queue

    queue = work_queue.Queue(queue_root(context)).ensure()
    # Every round this run counts in its progress, ticked once, however
    # its answer comes in - also one a helper finished before this run.
    planned = {f"{song}|{inputs_of[song]}|{way.tag}": way
               for song in songs for way in todo_of[song]}
    if test_panel.REMEASURE:
        for answer in queue.answers():
            if answer["job"].get("kind") == JOB_KIND:
                queue.take_answer(answer["job"]["id"])

    def save() -> None:
        try:
            spare = store_path.with_suffix(".tmp")
            spare.parent.mkdir(parents=True, exist_ok=True)
            spare.write_text(json.dumps(stored), encoding="utf-8")
            spare.replace(store_path)
        except OSError:
            logger.warning(t("log_report_write_failed"), store_path)

    parts_of = parts_of or {}
    part_ids: set[str] = set()

    def on_answer(answer: dict) -> None:
        job = answer["job"]
        payload = job["payload"]
        if payload.get("part"):
            shutil.rmtree(queue.out_dir(job["id"]), ignore_errors=True)
            if job["id"] in part_ids:
                part_ids.discard(job["id"])
                steps.tick(1, kind=PART)
                report(0, f"{job.get('label', '')}  "
                          f"({answer.get('worker', '')})")
            return
        result = dict(answer.get("result") or {})
        result["worker"] = answer.get("worker", "")
        result["device"] = answer.get("device", "")
        earlier = runs.get(payload["key"])
        if not ("failed" in result and earlier and "failed" not in earlier):
            # A late failure never overwrites a good answer.
            runs[payload["key"]] = result
            save()
        listen = root / "listen" / payload["song"]
        listen.mkdir(parents=True, exist_ok=True)
        made = queue.out_dir(job["id"])
        for path in (sorted(made.glob("*")) if made.is_dir() else ()):
            try:
                shutil.move(str(path), str(listen / path.name))
            except OSError:
                pass
        shutil.rmtree(made, ignore_errors=True)
        way = planned.pop(payload["key"], None)
        if way is not None:
            steps.tick(1, kind=way.key)
            report(0, f"{payload['song']}  {_way_name(way)}  "
                      f"({result['worker']})")

    failed: dict[str, str] = {}
    jobs = []
    for song in songs:
        todo = [way for way in todo_of[song]
                if f"{song}|{inputs_of[song]}|{way.tag}" not in runs
                or "failed" in runs[f"{song}|{inputs_of[song]}|{way.tag}"]]
        if not todo or cancelled():
            continue
        folder = queue.files / "sep" / work_queue.job_id(song)
        mix_wav = folder / "original.wav"
        try:
            project = pipeline.context_for_project(
                pipeline.read_only(context), song)
            if not mix_wav.exists():
                source = filesystem.find_audio_file(
                    project.paths.input_dir, pipeline.TRACK_ORIGINAL)
                if source is None:
                    raise FileNotFoundError(song)
                folder.mkdir(parents=True, exist_ok=True)
                ffmpeg.convert_to_wav(source, mix_wav)
            facts = song_facts(context, song)
        except Exception as exc:  # noqa: BLE001 - one song, not the night
            logger.exception(t("log_separation_trial_failed"), song, "-")
            failed[song] = separation.last_line(str(exc))
            for _way in todo:
                if planned.pop(f"{song}|{inputs_of[song]}|{_way.tag}",
                               None) is not None:
                    steps.tick(1, kind=_way.key)
            steps.tick(len(parts_of.get(song, ())), kind=PART)
            continue
        stems = stems_folder(root, queue, song, mix_wav)
        # v1.0.23 (B643): a round per part of a blend, before the blend.
        after: dict[str, str] = {}
        for way in todo:
            if keeps_stems(way) and way.way.backend != "blend":
                after[way.way.tag] = work_queue.job_id(
                    f"{song}|{inputs_of[song]}|{way.tag}")
        for part in parts_of.get(song, ()):
            if not stems:
                steps.tick(1, kind=PART)       # the blend makes it itself
                continue
            key = f"part|{song}|{stems}|{part.tag}"
            job_id = work_queue.job_id(key)
            after[part.tag] = job_id
            part_ids.add(job_id)
            jobs.append({"id": job_id, "kind": JOB_KIND,
                         "class": f"part:{part.tag}",
                         "needs": ["ffmpeg",
                                   *sorted(separation.backends(part))],
                         "label": f"{song} - {part.tag}",
                         "payload": {"key": key, "song": song,
                                     "part": separation.way_data(part),
                                     "stems": stems,
                                     "mix": mix_wav.relative_to(
                                         queue.root).as_posix()}})
        for way in todo:
            key = f"{song}|{inputs_of[song]}|{way.tag}"
            payload = {"key": key, "song": song, "way": way.key,
                       "facts": facts,
                       "mix": mix_wav.relative_to(queue.root).as_posix()}
            if keeps_stems(way):
                payload["stems"] = stems
            job = {"id": work_queue.job_id(key), "kind": JOB_KIND,
                   "class": f"sep:{way.key}", "needs": needs_of(way),
                   "label": f"{song} - {_way_name(way)}",
                   "payload": payload}
            if way.way.backend == "blend":
                # After the rounds of its parts, which keep their stems
                # for it - never before, when it would make them itself.
                job["priority"] = -1
                job["after"] = sorted({after[part.tag]
                                       for part in way.way.parts
                                       if part.tag in after})
            jobs.append(job)
    logger.info(t("log_queue_published"), len(jobs), queue.root)

    def on_local(job: dict) -> None:
        steps.name(f"1.5.14  {job.get('label', '')}",
                   kind=job["payload"].get("way") or PART)
        report(0, job.get("label", ""))

    work_queue.run_jobs(queue, jobs, __version__, {JOB_KIND: run_round},
                        on_answer, cancelled, on_local=on_local,
                        local_accept=work_queue.accept_for(
                            local_capabilities(), {JOB_KIND: run_round}),
                        poll_s=_POLL_S, can=sorted(local_capabilities()))
    _clear_files(queue, "sep")
    return failed


#: How often the program looks at the queue while helpers work.
_POLL_S = 5.0


def _clear_files(queue, part: str) -> None:
    """The originals no waiting or claimed job needs any more go."""
    needed = queue.referenced()
    folder_root = queue.files / part
    for folder in (sorted(folder_root.glob("*"))
                   if folder_root.is_dir() else ()):
        if folder.relative_to(queue.root).as_posix() not in needed:
            shutil.rmtree(folder, ignore_errors=True)
    try:
        folder_root.rmdir()
    except OSError:
        pass


def _by_worker(results: dict) -> dict[str, tuple[int, float, float, str]]:
    """Per computer: rounds, time, the part of it spent separating
    (v1.0.20, rounds that say so) and where Whisper listened."""
    out: dict[str, list] = {}
    for per in results.values():
        for row in per.values():
            worker = row.get("worker")
            if worker and "failed" not in row:
                entry = out.setdefault(worker, [0, 0.0, 0.0, 0.0, set()])
                entry[0] += 1
                entry[1] += float(row.get("seconds") or 0.0)
                if row.get("separate_s") is not None:
                    entry[2] += float(row["separate_s"])
                    entry[3] += float(row.get("seconds") or 0.0)
                if row.get("whisper_device"):
                    entry[4].add(str(row["whisper_device"]))
    return {worker: (count, seconds,
                     (split / timed) if timed else -1.0,
                     "+".join(sorted(devices)) or "-")
            for worker, (count, seconds, split, timed, devices)
            in out.items()}
