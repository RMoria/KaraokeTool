"""Vocal separation with Demucs, or with a Roformer model (optional).

Is used to:

* isolate the **vocal stem** of the karaoke, so that residual vocals
  are much more reliably detectable than on the mixed karaoke;
* make a **karaoke version out of the original** (vocals removed -> the
  instrumental stem), so that a separate karaoke is not needed.

Demucs runs via a subprocess (``python -m demucs``), so that we do not
depend on a specific Python API version. If Demucs is missing or it
does not succeed, this module raises a :class:`SeparationError` and the
pipeline falls back to the ordinary method (and tries again the next
time).

B591, v1.0.14: three ways, a setting (:data:`METHODS`). "standard" is
Demucs as it always was. "careful" is the fine-tuned Demucs bag with
two shifts - about eight times the work, for a cleaner music track.
"roformer" is a Roformer model through python-audio-separator, which
lives in an environment of its own next to the program (``KaraokeToolGUI.bat``
makes it on request) and runs through :data:`ROFORMER_SCRIPT` like
Demucs runs: as a subprocess. Its models are kept in a folder inside
the installation, not in the system's temp folder where the library
puts them by default. Every way keeps its stems in a folder of its own,
so switching never touches the stems a project already has.

v1.0.22: a fourth backend, ``blend`` (B631): several separations joined
into one (:mod:`modules.stem_blend`) - both Demucs ways now, Roformer
models or all of them later. A blend's parts are ways of their own and
keep their own stems, so a project that already has its Demucs stems
only adds what is missing. And Demucs keeps all four of its stems
(B632): drums, bass and the rest beside the voice, the music being the
three together as it always was.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import cuda, models, proc
from .translations import t

logger = logging.getLogger(__name__)

#: B591: the setting's values, in the order the settings tab shows them.
#: v1.0.22: and the Demucs blend (B631).
#: v1.0.28: and the two Roformer models for clean music, joined (B643's
#: ensemble, measured in 1.5.14: the cleanest music with the timing of
#: the Demucs blend) - for High performance and Normal.
METHODS = ("standard", "careful", "roformer", "demucs_blend", "music_clean")

#: v1.0.28: where a method falls back to when its backend is not
#: installed on this computer: clean music needs the Roformer
#: environment, then the Demucs blend, then the standard way.
FALLBACK = {"music_clean": "demucs_blend", "demucs_blend": "standard",
            "careful": "standard", "roformer": "standard"}

#: v1.0.23 (B643): the two instrumental Roformer models the library
#: ships as its "clean music" preset.
MUSIC_CLEAN = ("mel_band_roformer_instrumental_fv7z_gabox.ckpt"
               "+bs_roformer_instrumental_resurrection_unwa.ckpt")

#: The Roformer models: one that splits voice from music, and one that
#: keeps the backing choir with the music ("karaoke").
ROFORMER_MODELS = {
    "vocals": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
    "karaoke": "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
}

_ROOT = Path(__file__).resolve().parents[1]

#: The script the Roformer environment runs; it imports nothing of ours.
ROFORMER_SCRIPT = _ROOT / "tools" / "roformer_separate.py"

#: The folder of the Roformer environment, next to the program's own
#: ``venv`` (KaraokeToolGUI.bat puts both in %LOCALAPPDATA% when the program
#: folder cannot be written).
ROFORMER_ENV = "venv_separator"


class SeparationError(Exception):
    """Error while separating the stems."""


@dataclass(frozen=True)
class Way:
    """How a separation is made (B591)."""

    backend: str = "demucs"        # "demucs", "roformer" or "blend"
    #: A Roformer ensemble is its models joined by ``+`` (B598).
    model: str = "htdemucs"
    shifts: int = 1
    #: How an ensemble or a blend is joined; empty for one model.
    algorithm: str = ""
    #: v1.0.22 (B631): the separations a blend joins, ways of their own.
    parts: tuple = ()
    #: How much each part counts in an ``avg_wave`` blend; empty: equal.
    weights: tuple = ()

    @property
    def is_standard(self) -> bool:
        return self == Way()

    @property
    def tag(self) -> str:
        """What it is called in the marker and in the folder name."""
        if self.backend == "blend":
            weights = (" " + "/".join(f"{w:g}" for w in self.weights)
                       if self.weights else "")
            return (f"blend {self.algorithm or 'avg_wave'}{weights} ("
                    + " | ".join(part.tag for part in self.parts) + ")")
        if self.backend == "roformer":
            joined = f" {self.algorithm}" if self.algorithm else ""
            return f"roformer {self.model}{joined}"
        return self.model if self.shifts <= 1 else \
            f"{self.model} shifts={self.shifts}"

    def folder(self, key: str) -> str:
        """The stems folder; the standard way keeps the name it always
        had, so every existing project finds its stems where they are."""
        if self.is_standard:
            return f"demucs_stems_{key}"
        safe = "".join(ch if ch.isalnum() else "_" for ch in self.tag)
        if self.backend == "blend" and len(safe) > 60:
            # v1.0.22: a blend's tag names all its parts and grows long;
            # cut, with a hash of the whole, it stays unique and well
            # inside the path length Windows allows.
            import hashlib

            digest = hashlib.sha1(self.tag.encode("utf-8")).hexdigest()[:12]
            safe = f"{safe[:48]}_{digest}"
        return f"stems_{key}_{safe}"


#: v1.0.22 (B631): the blends. ``demucs`` is both Demucs ways, the
#: standard and the careful one, halved: what the test measures now.
#: ``high`` is the owner's thought for later - both Demucs ways and both
#: Roformer voice models - defined so a test can take it along by one
#: line; nothing uses it yet.
BLENDS = {
    "demucs": Way("blend", "", 1, "avg_wave",
                  (Way(), Way("demucs", "htdemucs_ft", 2))),
    "high": Way("blend", "", 1, "avg_wave",
                (Way(), Way("demucs", "htdemucs_ft", 2),
                 Way("roformer", ROFORMER_MODELS["vocals"]),
                 Way("roformer", "mel_band_roformer_vocals_becruily.ckpt"))),
    # v1.0.28: the clean-music ensemble as a blend of its single models,
    # loudest per frequency (as 1.5.14 measured it).
    "music_clean": Way("blend", "", 1, "max_spec", tuple(
        Way("roformer", model) for model in MUSIC_CLEAN.split("+"))),
    # v1.0.28 (B667): the Demucs blend, its dips filled from the part
    # that kept the music there.
    "demucs_repair": Way("blend", "", 1, "avg_wave+repair",
                         (Way(), Way("demucs", "htdemucs_ft", 2))),
    # v1.0.28: the next test - the Demucs blend and clean music together.
    "demucs_music_clean": Way("blend", "", 1, "avg_wave", (
        Way(), Way("demucs", "htdemucs_ft", 2),
        Way("blend", "", 1, "max_spec", tuple(
            Way("roformer", model) for model in MUSIC_CLEAN.split("+"))))),
}


def way_for(method: str, roformer_model: str = "vocals") -> Way:
    """The way a setting value stands for; unknown means standard."""
    if method == "careful":
        return Way("demucs", "htdemucs_ft", 2)
    if method == "roformer":
        return Way("roformer", ROFORMER_MODELS.get(
            roformer_model, ROFORMER_MODELS["vocals"]))
    if method == "demucs_blend":
        return BLENDS["demucs"]
    if method == "music_clean":
        return BLENDS["music_clean"]
    return Way()


def backends(way: Way) -> set[str]:
    """What a computer needs to make this way: ``demucs``, ``roformer``
    or both (a blend needs what its parts need)."""
    if way.backend == "blend":
        return set().union(*(backends(part) for part in way.parts)) \
            if way.parts else {"demucs"}
    return {way.backend}


def way_data(way: Way) -> dict:
    """A way as plain data, to travel to a helper."""
    data = {"backend": way.backend, "model": way.model,
            "shifts": way.shifts, "algorithm": way.algorithm}
    if way.parts:
        data["parts"] = [way_data(part) for part in way.parts]
    if way.weights:
        data["weights"] = list(way.weights)
    return data


def way_from(data: dict) -> Way:
    """A way back from :func:`way_data`."""
    data = dict(data)
    parts = tuple(way_from(part) for part in data.pop("parts", ()) or ())
    weights = tuple(float(w) for w in data.pop("weights", ()) or ())
    known = {"backend", "model", "shifts", "algorithm"}
    return Way(**{key: value for key, value in data.items() if key in known},
               parts=parts, weights=weights)


def is_available(way: Way | None = None) -> bool:
    """Is the separation of this way installed (Demucs by default)?"""
    if way is not None and way.backend == "blend":
        return bool(way.parts) and all(is_available(part)
                                       for part in way.parts)
    if way is not None and way.backend == "roformer":
        return roformer_problem() is None
    return models.is_available("demucs")


def roformer_env_dirs() -> list[Path]:
    """Where the Roformer environment may be, in order."""
    dirs = [_ROOT / ROFORMER_ENV]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "KaraokeTool" / ROFORMER_ENV)
    return dirs


def roformer_python() -> Path | None:
    """The interpreter of the Roformer environment, if it is there."""
    for folder in roformer_env_dirs():
        for candidate in (folder / "Scripts" / "python.exe",
                          folder / "bin" / "python"):
            if candidate.exists():
                return candidate
    return None


#: What :func:`roformer_problem` found, per interpreter, once per run.
_ROFORMER_CHECKED: dict[str, str | None] = {}


def roformer_problem() -> str | None:
    """Why the Roformer environment cannot separate, or ``None`` when it
    can (v1.0.15). There being an interpreter is not enough: in the
    second 1.5.14 night the environment was there and every Roformer
    separation stopped on its first import, because librosa 1.0 no
    longer brings audioread along and audio-separator still imports it.
    So the library itself is imported once, in that environment, and
    the last line of what went wrong is the answer."""
    python = roformer_python()
    if python is None:
        return t("err_roformer_missing")
    key = str(python)
    if key in _ROFORMER_CHECKED:
        return _ROFORMER_CHECKED[key]
    try:
        done = proc.run([_windowless(python), "-c",
                         "import audio_separator.separator"],
                        check=False, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        # Did not finish (a slow first import, Stop): no verdict to keep,
        # the next use asks again.
        problem = last_line(str(exc))
        logger.warning(t("log_roformer_broken"), problem)
        return problem
    text = done.stderr or done.stdout or ""
    if done.returncode != 0 and "Error" not in text:
        # Stopped from outside rather than failed: ask again next time.
        return last_line(text) or t("err_roformer_missing")
    _ROFORMER_CHECKED[key] = (None if done.returncode == 0
                              else last_line(text))
    if _ROFORMER_CHECKED[key]:
        logger.warning(t("log_roformer_broken"), _ROFORMER_CHECKED[key])
    return _ROFORMER_CHECKED[key]


def roformer_selftest() -> str | None:
    """A real separation of three seconds of tone in the Roformer
    environment (v1.0.16), before a night of them: why it cannot, or
    ``None`` when it can. The import check alone let v1.0.15 through
    with a setting the library refuses, which would have cost the whole
    night again."""
    problem = roformer_problem()
    if problem:
        return problem
    python = roformer_python()
    folder = roformer_models_dir()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        done = proc.run([_windowless(python), str(ROFORMER_SCRIPT),
                         "--selftest", str(folder),
                         ROFORMER_MODELS["vocals"]],
                        check=False, timeout=1800)
    except (OSError, subprocess.SubprocessError) as exc:
        return last_line(str(exc))
    if done.returncode != 0:
        return last_line(done.stderr or done.stdout or "") or \
            t("err_roformer_missing")
    return None


#: What :func:`torch_problem` found, per interpreter, once per run.
_TORCH_CHECKED: dict[str, str | None] = {}


def torch_problem(python: Path | str | None = None) -> str | None:
    """Why PyTorch does not load in this environment (``python``, by
    default the running one), or ``None`` when it does (v1.0.23, B649).

    Demucs being installed is not enough: on Probook every package was
    there, yet torch stopped on ``c10.dll`` because the Visual C++ runtime
    of Microsoft was missing, and later because it was too old. The helper
    said it could separate with Demucs all the same, and would have failed
    every Demucs round it took. So torch is loaded once, in a process of
    its own (the lane itself keeps nothing of it)."""
    import sys

    python = str(python or sys.executable)
    if python in _TORCH_CHECKED:
        return _TORCH_CHECKED[python]
    try:
        done = proc.run([python, "-c", "import torch"], check=False,
                        timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        # Did not finish: no verdict to keep, the next start asks again.
        return last_line(str(exc))
    _TORCH_CHECKED[python] = (None if done.returncode == 0 else
                              last_line(done.stderr or done.stdout or "")
                              or "import torch")
    return _TORCH_CHECKED[python]


def last_line(text: str) -> str:
    """The last line of an error that says something: with a traceback
    that is the exception itself, not where it began."""
    lines = [line.strip() for line in str(text).splitlines()
             if line.strip()]
    return (lines[-1] if lines else str(text).strip())[:300]


def roformer_models_dir() -> Path:
    """Where the Roformer models are kept: next to their environment."""
    python = roformer_python()
    base = python.parents[2] if python is not None else _ROOT
    return base / "models" / "audio_separator"


def _windowless(python: Path) -> str:
    """v1.0.28 (B658): ``python.exe`` of the Roformer environment, started
    with ``CREATE_NO_WINDOW`` by :func:`proc.run` - its hidden console is
    shared by the ffmpeg the library starts. Under ``pythonw.exe`` (as up
    to v1.0.27) every such ffmpeg flashed a window of its own."""
    if proc.is_windows() and python.name.lower() == "pythonw.exe":
        console = python.with_name("python.exe")
        if console.exists():
            return str(console)
    return str(python)


def separate(audio_path: Path, work_dir: Path,
             model: str = "htdemucs", shifts: int = 1) -> dict[str, Path]:
    """Separate a file into a vocal and an instrumental stem.

    Args:
        audio_path: The audio file to be separated.
        work_dir: Folder in which Demucs writes its result.
        model: Demucs model (``htdemucs`` by default).
        shifts: Demucs ``--shifts``: each is one more pass, shifted in
            time, averaged (B591).

    Returns:
        ``{"vocals": path, "instrumental": path}`` (wav files), and since
        v1.0.22 (B632) ``drums``, ``bass`` and ``other`` where the model
        makes them.

    Raises:
        SeparationError: If Demucs is missing or the separation fails.
    """
    if not is_available():
        raise SeparationError(t("err_demucs_missing"))
    # Empty the work folder first so that old stems are never reused
    # (B135).
    if work_dir.exists():
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    # B89: Demucs (via torch/multiprocessing) started cmd windows of its
    # own; v1.0.28 (B658) a hidden console shared by them all.
    # B632: all four stems. ``--two-stems`` made the music by adding up
    # the other three inside Demucs; that sum is made here now, the same
    # way, and the drums are kept for the rhythm (B633).
    # v1.0.28 (B658): a hidden console rather than pythonw - see
    # :func:`proc.hidden_console_python`.
    command = [proc.hidden_console_python(), "-m", "demucs",
               "-n", model, "-o", str(work_dir), str(audio_path)]
    # B597: the stems keep the level of the original. By default Demucs
    # scales a whole stem down when it would clip - measured on the
    # owner's songs up to 1.5 dB, which is a step in volume wherever a
    # piece of the original is laid back into the music. As 32-bit float
    # nothing clips, so nothing needs scaling; levelling is the render's
    # job, once, on the mix it plays. Stems made before keep their level:
    # their marker does not change, so nobody's project separates again.
    command[3:3] = _level_args()
    if shifts > 1:
        command[3:3] = ["--shifts", str(int(shifts))]
    logger.info(t("log_demucs_separating"), audio_path.name)
    try:
        # B356: through proc.run, so that a cancel really stops Demucs
        # instead of sitting out three more minutes.
        _run_separation(command)
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise SeparationError(
            t("err_demucs_failed").format(detail=detail)) from exc

    vocals = _find_stem(work_dir, "vocals")
    instrumental = _find_stem(work_dir, "no_vocals")
    extras = {name: _find_stem(work_dir, name) for name in EXTRA_STEMS}
    extras = {name: path for name, path in extras.items() if path}
    if instrumental is None and vocals is not None and extras:
        instrumental = _added(list(extras.values()),
                              vocals.with_name("no_vocals.wav"))
    if vocals is None or instrumental is None:
        raise SeparationError(t("err_demucs_no_stems"))
    return {"vocals": vocals, "instrumental": instrumental, **extras}


#: B632: the stems of Demucs beside the voice; together they are the music.
EXTRA_STEMS = ("drums", "bass", "other")


def _added(paths: list[Path], target: Path) -> Path:
    """The sum of stems, as 32-bit float (what ``--two-stems`` made)."""
    import soundfile

    total = None
    rate = 44_100
    for path in paths:
        data, rate = soundfile.read(str(path), dtype="float32",
                                    always_2d=True)
        if total is None:
            total = data.copy()
        else:
            count = min(len(total), len(data))
            total = total[:count] + data[:count]
    soundfile.write(str(target), total, rate, subtype="FLOAT")
    return target


def _run_separation(command: list[str]) -> None:
    """Run a separation, on the card when the card test allowed that
    (v1.0.20). Should it fail there with a card error - a small card runs
    out of memory on a long song - it runs once more on the processor, and
    the rest of the session stays there."""
    try:
        proc.run(command, check=True, env=cuda.processor_only_env())
    except subprocess.CalledProcessError as exc:
        detail = str(getattr(exc, "stderr", "") or "")
        if not cuda.torch_on_card() or not any(
                word in detail.lower() for word in (
                    "cuda", "out of memory", "cublas", "cudnn")):
            raise
        logger.warning(t("log_separation_card_failed"), last_line(detail))
        cuda.torch_failed()
        proc.run(command, check=True, env=cuda.processor_only_env())


def _level_args() -> list[str]:
    """B597: ``--clip-mode none`` exists from Demucs 4.1; an older one
    refuses it and would stop every separation. There the stems stay
    scaled as before, and the level match of 1.4 makes up for it."""
    try:
        from importlib.metadata import version

        numbers = [int(part) for part in version("demucs").split(".")[:2]
                   if part.isdigit()]
    except Exception:  # noqa: BLE001 - no metadata: assume the old one
        numbers = []
    if tuple(numbers) >= (4, 1):
        return ["--clip-mode", "none", "--float32"]
    return ["--float32"]


def _find_stem(work_dir: Path, name: str) -> Path | None:
    """Find a separated stem (``<model>/<name>/<stem>.wav``)."""
    matches = sorted(work_dir.glob(f"**/{name}.wav"))
    return matches[-1] if matches else None


def separate_roformer(audio_path: Path, work_dir: Path,
                      model: str, algorithm: str = "") -> dict[str, Path]:
    """Separate with a Roformer model, in its own environment (B591).

    ``model`` may be several joined by ``+``: an ensemble, joined the
    ``algorithm`` way (B598). Returns every stem by its name, and
    ``vocals`` and ``instrumental`` where the model makes them.

    Raises:
        SeparationError: If the environment is missing or it fails.
    """
    python = roformer_python()
    if python is None:
        raise SeparationError(t("err_roformer_missing"))
    if work_dir.exists():
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    folder = roformer_models_dir()
    folder.mkdir(parents=True, exist_ok=True)
    command = [_windowless(python), str(ROFORMER_SCRIPT), str(audio_path),
               str(work_dir), str(folder), *model.split("+")]
    if algorithm:
        command += ["--algorithm", algorithm]
    logger.info(t("log_roformer_separating"), audio_path.name, model)
    try:
        _run_separation(command)
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise SeparationError(
            t("err_roformer_failed").format(detail=str(detail)[-800:])) \
            from exc
    stems = {path.stem: path for path in sorted(work_dir.glob("*.wav"))
             if not path.name.startswith("_")}
    if not stems:
        raise SeparationError(t("err_roformer_no_stems"))
    for key, names in (("vocals", ("vocals",)),
                       ("instrumental", ("instrumental", "no_vocals",
                                         "other"))):
        found = next((stems[name] for name in names if name in stems), None)
        if found is not None:
            stems.setdefault(key, found)
    return stems


def separate_way(audio_path: Path, work_dir: Path,
                 way: Way, store=None) -> dict[str, Path]:
    """Separate the way ``way`` says.

    ``store`` (a :class:`modules.stem_store.StemStore`, v1.0.22): stems
    kept by an earlier round. A blend takes its parts from it where they
    are there and keeps the ones it made; a way of its own is kept there
    once made."""
    if way.backend == "blend":
        return _separate_blend(audio_path, work_dir, way, store)
    stems = _separate_one(audio_path, work_dir, way)
    if store is not None:
        store.put(way.tag, stems)
    return stems


def _separate_blend(audio_path: Path, work_dir: Path, way: Way,
                    store) -> dict[str, Path]:
    from . import stem_blend

    if not way.parts:
        raise SeparationError(t("err_blend_no_parts"))
    if work_dir.exists():
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    sets = []
    for number, part in enumerate(way.parts):
        folder = work_dir / f"part{number}"
        kept = store.get(part.tag, folder) if store is not None else None
        if kept is None:
            kept = separate_way(audio_path, folder, part, store)
        else:
            logger.info(t("log_blend_part_kept"), part.tag)
        sets.append(kept)
    try:
        return stem_blend.blend_files(sets, work_dir / "blend",
                                      way.algorithm or "avg_wave",
                                      way.weights or None)
    except (stem_blend.BlendError, OSError, RuntimeError, ValueError) as exc:
        raise SeparationError(str(exc)) from exc


def _separate_one(audio_path: Path, work_dir: Path,
                  way: Way) -> dict[str, Path]:
    if way.backend == "roformer":
        stems = separate_roformer(audio_path, work_dir, way.model,
                                  way.algorithm)
        if "vocals" not in stems or "instrumental" not in stems:
            raise SeparationError(t("err_roformer_no_stems"))
        return stems
    if way.shifts <= 1:
        return separate(audio_path, work_dir, way.model)
    return separate(audio_path, work_dir, way.model, way.shifts)


def separate_cached(audio_path: Path, cache_root: Path, key: str,
                    model: str = "htdemucs",
                    way: Way | None = None) -> dict[str, Path]:
    """Separate a source, but at most once per source (B135/B248).

    The stems are stored in a fixed folder per source
    (``<cache_root>/demucs_stems_<key>/``). If a ``vocals.wav`` and a
    ``no_vocals.wav`` are already there, then those are reused and Demucs
    does not run again. This way the same source (e.g. the original) is not
    separated several times for the different purposes (vocal stem analysis,
    karaoke-from-original, transcription). If the cache is emptied, then the
    folder disappears and the next run separates again by itself.

    Args:
        audio_path: The audio file to be separated.
        cache_root: The cache folder of the project (``paths.cache_dir``).
        key: Stable name for the source, e.g. ``"original"`` or
            ``"karaoke"``.
        model: Demucs model.
        way: The whole way (B591); ``model`` is the standard Demucs way
            with that model when it is not given. Every way has a
            stems folder of its own (:meth:`Way.folder`).

    Returns:
        ``{"vocals": path, "instrumental": path}``.

    Raises:
        SeparationError: If Demucs is missing or the separation fails.
    """
    way = way or Way("demucs", model, 1)
    model = way.tag
    store = cache_root / way.folder(key)
    vocals = store / "vocals.wav"
    instrumental = store / "no_vocals.wav"
    marker = store / "source.sha1"
    checksum = _source_checksum(audio_path)
    if vocals.exists() and instrumental.exists():
        if _marker_matches(marker, checksum, model):
            _write_marker(marker, checksum, model)   # upgrade, B548
            logger.info(t("log_demucs_reused"),
                        key, store)
            return {"vocals": vocals, "instrumental": instrumental,
                    **_kept_extras(store)}
        # B311: the stems belong to OTHER audio. Reusing them anyway is
        # exactly how v0.96 went wrong: Whisper transcribes the vocal
        # stem, so a stale stem silently gives a stale transcription of a
        # song that is no longer there. Separate again.
        logger.info(t("log_demucs_stale"), key)

    # Not yet (completely) in the cache: separate once and put the stems in
    # the fixed place. We separate into a temporary work folder and copy the
    # two stems out of it, so that the fixed place is predictable and does
    # not depend on the internal folder structure of Demucs (<model>/<name>/).
    from . import shared_work, whisper
    if way.backend == "blend":
        # B631: every part through the cache of its own way - a project
        # that already has its Demucs stems only makes the rest - and the
        # blend of them kept like any other way.
        from . import stem_blend

        sets = []
        for number, part in enumerate(way.parts):
            stems = separate_cached(audio_path, cache_root, key, way=part)
            if any(Path(path).parent == cache_root / f"demucs_work_{key}"
                   or cache_root / f"demucs_work_{key}" in Path(path).parents
                   for path in stems.values()):
                # Its fixed place could not be written: out of the work
                # folder the next part empties first.
                stems = _moved_aside(stems,
                                     cache_root / f"demucs_part{number}_{key}")
            sets.append(stems)
        try:
            fresh = stem_blend.blend_files(
                sets, cache_root / f"demucs_work_{key}",
                way.algorithm or "avg_wave", way.weights or None)
        except (stem_blend.BlendError, OSError, RuntimeError,
                ValueError) as exc:
            raise SeparationError(str(exc)) from exc
        made = _into_store(fresh, store, marker, checksum, model, key,
                           cache_root)
        import shutil

        for number in range(len(way.parts)):
            shutil.rmtree(cache_root / f"demucs_part{number}_{key}",
                          ignore_errors=True)
        return made
    if cuda.torch_on_card() and cuda.whisper_device()[0] == "cuda":
        # v1.0.20: a small card holds Whisper or a separation, not both.
        whisper.release_models()
    # v1.0.20: on a helper when one is sooner done, otherwise here.
    from . import step_times
    with step_times.timed(f"separate:{way.tag}",
                          step_times.audio_seconds(audio_path)):
        fresh = shared_work.separate(audio_path,
                                     cache_root / f"demucs_work_{key}", way)
    return _into_store(fresh, store, marker, checksum, model, key,
                       cache_root)


def _into_store(fresh: dict, store: Path, marker: Path, checksum: str,
                model: str, key: str, cache_root: Path) -> dict[str, Path]:
    """Fresh stems into the fixed place of their way, with their marker."""
    import shutil

    vocals = store / "vocals.wav"
    instrumental = store / "no_vocals.wav"
    store.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(fresh["vocals"], vocals)
        shutil.copyfile(fresh["instrumental"], instrumental)
        for name in EXTRA_STEMS:
            if fresh.get(name):
                shutil.copyfile(fresh[name], store / f"{name}.wav")
    except OSError as exc:
        # Copying failed: return the fresh stems so that the run can go on.
        logger.warning(t("log_demucs_copy_failed"), exc)
        return fresh
    # Clean up the (large) work folder; the stems are now in the fixed place.
    shutil.rmtree(cache_root / f"demucs_work_{key}", ignore_errors=True)
    _write_marker(marker, checksum, model)
    logger.info(t("log_demucs_cached"), key, store)
    return {"vocals": vocals, "instrumental": instrumental,
            **_kept_extras(store)}


def _moved_aside(stems: dict, folder: Path) -> dict[str, Path]:
    """Stems moved into a folder of their own."""
    import shutil

    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, path in stems.items():
        target = folder / f"{name}.wav"
        shutil.move(str(path), str(target))
        out[name] = target
    return out


def _kept_extras(store: Path) -> dict[str, Path]:
    """The drums, bass and rest kept beside the voice, where there are."""
    return {name: store / f"{name}.wav" for name in EXTRA_STEMS
            if (store / f"{name}.wav").exists()}


def extra_stem(audio_path: Path, cache_root: Path, key: str,
               name: str) -> Path | None:
    """One of the stems beside the voice (B632) - the drums, say - of the
    standard way, made when the project's stems are from before v1.0.22
    and have only the voice and the music. Those two are left exactly as
    they are (a separation again is never quite the same, and the
    project's transcription was made on them): only what is missing is
    added. ``None`` when Demucs is not there or fails."""
    import shutil

    store = cache_root / Way().folder(key)
    target = store / f"{name}.wav"
    if target.exists():
        return target
    if name not in EXTRA_STEMS or not is_available():
        return None
    work = cache_root / f"demucs_extra_{key}"
    try:
        stems = separate(audio_path, work)
    except SeparationError:
        logger.exception(t("log_extra_stem_failed"), name)
        return None
    try:
        store.mkdir(parents=True, exist_ok=True)
        for extra in EXTRA_STEMS:
            if stems.get(extra) and not (store / f"{extra}.wav").exists():
                shutil.copyfile(stems[extra], store / f"{extra}.wav")
    except OSError:
        logger.exception(t("log_extra_stem_failed"), name)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return target if target.exists() else None


def _source_checksum(audio_path: Path) -> str:
    """Fingerprint of the audio that the stems belong to (B311)."""
    from .filesystem import file_sha1
    try:
        return file_sha1(audio_path)
    except OSError:
        return ""


def _demucs_version() -> str:
    """The installed Demucs version, or empty when it cannot be read."""
    from importlib.metadata import version

    try:
        return str(version("demucs"))
    except Exception:  # noqa: BLE001 - a marker may never break a run
        return ""


def _stamp(checksum: str, model: str) -> str:
    """What the stems were made from: audio, model, Demucs (B548).

    A Roformer way (B591) has its own model file in its tag, and the
    Demucs version says nothing about it.
    """
    version = "" if model.startswith("roformer ") else _demucs_version()
    return "\n".join([checksum, model, version])


def _write_marker(marker: Path, checksum: str, model: str) -> None:
    """Note beside the stems what they were made from.

    Also upgrades a marker from before B548, which held the checksum
    alone: writing the full stamp costs nothing and the next run then
    has the whole answer.
    """
    if not checksum:
        return
    try:
        marker.write_text(_stamp(checksum, model), encoding="utf-8")
    except OSError as exc:          # marker is a bonus, not a condition
        logger.warning(t("log_demucs_marker_failed"), exc)


def _marker_matches(marker: Path, checksum: str, model: str) -> bool:
    """Do the cached stems belong to this audio, model and Demucs?

    B311 asked the first of those three. B548 added the other two: the
    ``model`` argument of :func:`separate_cached` was accepted, passed
    on and never written down, so ``htdemucs_ft`` silently got
    ``htdemucs`` stems back. And a Demucs upgrade - which
    ``KaraokeToolGUI.bat`` invites - leaves stems whose marker still matches,
    so the old model's separation would be reused for ever and Whisper
    would keep transcribing it. That is the B311 failure through
    another door.

    Stems without a marker at all come from before B311. Those are
    still accepted: throwing away a separation that is probably fine
    costs minutes per song, and from the next run onwards there IS a
    marker.

    A marker of ONE line is from before B548 and is not accepted. The
    first thought was to let it pass on its checksum, since the stems
    under it were probably made by the Demucs that is installed now -
    but "probably" is exactly wrong here: a marker from before this
    check is precisely the one that may predate an upgrade, and
    passing it would then also stamp those stems as belonging to the
    new version, so the mistake would never be findable again. It
    costs one separation per project, once.

    A torn write lands in the same branch, which is the second reason:
    half a marker says nothing, and this way it says nothing loudly.
    """
    if not checksum:
        return True
    if not marker.exists():
        return True
    try:
        written = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return True
    if "\n" not in written:     # from before B548, or half written
        return False
    return written == _stamp(checksum, model).strip()


