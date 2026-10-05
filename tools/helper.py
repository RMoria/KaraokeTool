"""The helper: another computer that works for the program (v1.0.18).

Runs on a computer in the owner's network, from a copy of the program
that ``helper/install_helper.bat`` put in
``%LOCALAPPDATA%\\KaraokeToolHelper``. It takes jobs from the work queue
on the share (:mod:`modules.work_queue`), works on them and gives the
answers back; with nothing to do it waits until new work comes. Close
the window (or Ctrl+C) to stop: the job it was on goes back into the
queue.

v1.0.20: the helper keeps itself up to date. The installer carries a
version (``HELPER_VERSION`` in ``install_helper.bat``, the program's
version); after every job, and every minute while it waits, the helper
compares the one on the share with the one it was installed with. When
the share has a newer one it stops (exit code 3) and ``helper_start.bat``
runs the new installer, which starts the helper again when it is done.

A computer with a usable NVIDIA card works in two lanes at once: one on
the card and one on the processor - the owner's wish for his laptop with
an older card. A card that turns out unusable (too old for the PyTorch
that is installed, no driver) leaves the processor lane only, and says
why.

    python tools/helper.py --share \\\\10.0.0.18\\Tools\\KaraokeTool
    python tools/helper.py --share ... --lanes cpu    (processor only)
    python tools/helper.py --check                    (what would run)

Exit code 3: a newer version waits on the share - ``helper_start.bat``
then runs its installer.

v1.0.23: ``--window`` shows the helper in a small window of its own with
the program's icon instead of a console (:mod:`modules.helper_window`),
with "stop after the current round" and "stop now" (exit code 4: stopped
by the owner, the start file then ends quietly). A card with less than
6 GB of memory gets no lane of its own (B641) - ``lanes.txt`` in the
helper's folder says otherwise per computer (``cpu``, ``gpu,cpu``) - and
a computer with an NVIDIA card watches its heat (B642,
:mod:`modules.heat_guard`).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The helper's own folder (%LOCALAPPDATA%\\KaraokeToolHelper): the program
#: copy is ``app`` inside it.
HOME = ROOT.parent
#: The installer on the share, relative to the KaraokeTool folder there.
INSTALLER = Path("helper") / "install_helper.bat"
#: What the installer wrote down when it was done, next to ``app``.
INSTALLED_FILE = "installed_version.txt"
#: v1.0.23: the owner's choice of lanes for this computer, beside ``app``.
LANES_FILE = "lanes.txt"
#: v1.0.23: the window asks the lanes to finish their round and stop...
FINISH_FLAG = "stop_after_current.flag"
#: ...or to stop at once, the rounds going back into the queue.
STOP_FLAG = "stop_now.flag"
#: Stopped by the owner from the window: the start file ends quietly.
OWNER_EXIT = 4
#: The helper's folder under its old name, up to v1.0.19 (OLD_HOME in the
#: installer): what is left of it goes.
OLD_HOME_NAME = "KaraokeToolHulp"
#: v1.0.24 (B655): the window asks the helper to take itself off this
#: computer, once the lanes have stopped.
REMOVE_FLAG = "remove.flag"


#: v1.0.24 (B646): the lane that takes one round at a time, on the card
#: when the round goes faster there, else on the processor - never both
#: at once (a small card that shares its cooler with the processor).
MIXED = "mixed"
#: How ``lanes.txt`` may call it.
MIXED_WORDS = ("mixed", "gpu-or-cpu", "gpu|cpu", "gpuorcpu", "gpu/cpu")


def choose_lanes(requested: str, gpu_ok: bool,
                 big_enough: bool = True) -> list[str]:
    """Which lanes to run: ``auto`` is the card and the processor when
    the card works and is big enough (v1.0.23: 6 GB); a working card that
    is smaller gets the one lane that takes a round either on the card or
    on the processor (v1.0.24, B646: the owner - a task that goes faster
    on the card is always worth trying, but not a second one on the
    processor beside it); no card, the processor. Asked for by name, a
    working card is used whatever its size - the owner's choice."""
    if requested == "auto":
        if not gpu_ok:
            return ["cpu"]
        return ["gpu", "cpu"] if big_enough else [MIXED]
    lanes = [lane.strip() for lane in requested.split(",") if lane.strip()]
    lanes = [MIXED if lane in MIXED_WORDS else lane for lane in lanes]
    lanes = [lane for lane in lanes if lane in ("gpu", "cpu", MIXED)]
    if not gpu_ok:
        lanes = ["cpu" if lane == MIXED else lane for lane in lanes
                 if lane != "gpu"]
    elif MIXED in lanes:
        lanes = [MIXED]             # one round at a time, by its nature
    unique = []
    for lane in lanes:
        if lane not in unique:
            unique.append(lane)
    return unique or ["cpu"]


#: v1.0.24 (B646): Whisper's compute type on a small card.
SMALL_CARD_COMPUTE = "int8_float16"
#: What makes a round one for the card in the mixed lane: a separation.
CARD_NEEDS = frozenset({"demucs", "roformer"})
#: What a failure on the card says.
_CARD_TROUBLE = ("out of memory", "cuda", "cublas", "cudnn")


def card_round(job: dict) -> bool:
    """B646: does this round go faster on the card? A separation does
    (the check of 1.5.18 measured three times on Pav); a render, the
    yardstick and the rest are processor work."""
    needs = set(job.get("needs") or ())
    return bool(needs & CARD_NEEDS) and "processor" not in needs


def _set_env(values: dict) -> None:
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def mixed_handlers(handlers: dict, card_env: dict, cpu_env: dict,
                   say=None) -> dict:
    """B646: every handler of the mixed lane runs its round on the card or
    on the processor, as :func:`card_round` says. A round the card cannot
    take (out of memory) runs once more on the processor at once, and
    rounds of that class go to the processor from then on."""
    failed: set[str] = set()

    def trouble(answer: dict) -> bool:
        text = str(answer.get("failed", "")).lower()
        return bool(text) and any(word in text for word in _CARD_TROUBLE)

    def wrap(handler):
        def run(job, queue, stop):
            on_card = card_round(job) and job.get("class") not in failed
            _set_env(card_env if on_card else cpu_env)
            if say is not None:
                say("helper_on_card" if on_card else "helper_on_processor",
                    {})
            answer = handler(job, queue, stop)
            if on_card and isinstance(answer, dict) and trouble(answer) \
                    and not stop():
                failed.add(str(job.get("class")))
                if say is not None:
                    say("helper_card_retry", {"problem": str(
                        answer.get("failed"))[:200]})
                _set_env(cpu_env)
                answer = handler(job, queue, stop)
            return answer
        return run

    return {kind: wrap(handler) for kind, handler in handlers.items()}


def lanes_wanted(requested: str, home: Path | None = None) -> str:
    """``--lanes``, or when that is ``auto`` what ``lanes.txt`` says."""
    if requested != "auto":
        return requested
    try:
        raw = ((home or HOME) / LANES_FILE).read_bytes()
    except OSError:
        return "auto"
    # Notepad writes UTF-8 with a mark in front, PowerShell 5 UTF-16.
    for encoding in ("utf-16", "utf-8-sig") if raw[:2] in (
            b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except ValueError:
            continue
    else:
        return "auto"
    words = re.split(r"[\s,+;]+", text.strip().lower())
    return ",".join(word for word in words if word) or "auto"


def _flag(name: str, home: Path | None = None) -> Path:
    return (home or HOME) / name


def clear_flags(home: Path | None = None) -> None:
    """A new start: what the window asked last time is done."""
    for name in (FINISH_FLAG, STOP_FLAG):
        try:
            _flag(name, home).unlink()
        except OSError:
            pass


def set_flag(name: str, on: bool = True, home: Path | None = None) -> None:
    try:
        if on:
            _flag(name, home).write_text("1", encoding="utf-8")
        else:
            _flag(name, home).unlink()
    except OSError:
        pass


def probe() -> dict:
    """What this computer can do on its card, in a process of its own so
    the helper itself holds nothing on the card (see :mod:`modules.cuda`)."""
    from modules import cuda

    found = cuda.probe(whisper_too=True)
    found["gpu_ok"] = bool(found.get("torch"))
    return found


def _probe_elsewhere() -> dict:
    import json

    try:
        from modules import proc

        # v1.0.28 (B658): hidden, like every task of a helper.
        done = proc.run([proc.hidden_console_python(),
                         str(Path(__file__).resolve()), "--probe"],
                        timeout=900, check=False)
        line = [row for row in done.stdout.splitlines()
                if row.startswith("{")][-1]
        return json.loads(line)
    except Exception as exc:  # noqa: BLE001 - then the processor only
        return {"gpu_ok": False, "card": f"{type(exc).__name__}: {exc}"[:200],
                "device": "cpu", "compute": "int8"}


def _say(lane: str):
    import logging

    from modules.translations import t

    log = logging.getLogger("helper")

    def say(key: str, values: dict) -> None:
        text = t(key).format(**values)
        print(f"[{lane}] " + text, flush=True)
        # v1.0.21: what the window shows is in the log too, and so on the
        # share (see mirror_logs). DEBUG: the file takes it, the window
        # (which shows INFO) has it already.
        log.debug("[%s] %s", lane, text)

    return say


# -- the logs, also on the laptop ------------------------------------------------

#: How long the logs are kept, here and on the share (the owner's choice).
KEEP_LOG_DAYS = 30
#: How often a running helper puts its logs on the share.
MIRROR_EVERY_S = 300.0


def central_logs(share: str) -> Path:
    """Where this helper's logs go on the laptop (v1.0.21): the program's
    own log folder, one subfolder per computer."""
    from modules import work_queue

    # v1.0.22: the name the helper list shows (the host name), which the
    # batch files use too (``hostname``). %COMPUTERNAME% can be another
    # name altogether: BarWin10's logs landed in LAPTOP-1VM4EIM2, which
    # reads like the laptop's.
    return Path(share) / "logs" / "helpers" / work_queue.host_name()


def mirror_logs(local: Path, central: Path,
                keep_days: float = KEEP_LOG_DAYS,
                now: float | None = None) -> int:
    """Put the local logs on the share: every file that is new or has
    changed, the ones from before the move to the share too. Logs older
    than ``keep_days`` go, here and there - there only in this helper's
    own folder. The share may be away: then nothing happens, and the
    next time catches up. Returns how many files were copied."""
    import shutil

    now = time.time() if now is None else now
    limit = now - keep_days * 86400.0
    copied = 0
    try:
        files = [path for path in local.rglob("*") if path.is_file()]
    except OSError:
        return 0
    for path in files:
        try:
            if path.stat().st_mtime < limit:
                path.unlink()
                continue
            target = central / path.relative_to(local)
            there = target.stat() if target.exists() else None
            here = path.stat()
            if there is None or there.st_size != here.st_size or \
                    there.st_mtime < here.st_mtime:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                copied += 1
        except OSError:
            continue
    try:
        for path in [item for item in central.rglob("*") if item.is_file()]:
            if path.stat().st_mtime < limit:
                path.unlink()
    except OSError:
        pass
    return copied


def _keep_mirroring(share: str, stop) -> None:
    """While the helper runs: its logs to the share now and then."""
    import threading

    def loop() -> None:
        while not stop.wait(MIRROR_EVERY_S):
            mirror_logs(HOME / "logs", central_logs(share))

    threading.Thread(target=loop, daemon=True).start()


def capabilities(say) -> set[str]:
    """What this computer can do, tried once at the start of a lane: a
    helper only takes rounds it can do (the ``needs`` of a job), so a
    missing Roformer environment leaves those rounds to another computer
    instead of failing them all in a minute."""
    from modules import ffmpeg, separation

    if not ffmpeg.is_available():
        say("helper_no_ffmpeg", {})
        return set()
    have = {"ffmpeg", "whisper"}
    if separation.is_available():
        # v1.0.23 (B649): Demucs only when PyTorch really loads here.
        problem = separation.torch_problem()
        if problem is None:
            have.add("demucs")
            # v1.0.23 (B652): the forced aligner, on the same PyTorch.
            from modules import word_alignment

            if word_alignment.is_available():
                have.add("whisperx")
        else:
            say("helper_no_torch", {"problem": problem})
    if separation.roformer_python() is not None:
        problem = separation.roformer_selftest()
        if problem is None:
            have.add("roformer")
        else:
            say("helper_no_roformer", {"problem": problem})
    say("helper_can", {"ways": ", ".join(sorted(
        have - {"ffmpeg", "whisper", "whisperx"})) or "-"})
    if "whisperx" in have:
        say("helper_can_align", {})
    return have


# -- a quiet window (v1.0.23, B648) --------------------------------------------

#: Loggers whose everyday lines (every request to Hugging Face) are for
#: the log file, not for the window.
CHATTY_LOGGERS = ("httpx", "httpcore", "urllib3", "huggingface_hub",
                  "filelock")


def quiet_downloads(env: dict | None = None) -> dict:
    """Hugging Face without its warning about symbolic links (Windows
    without developer mode cannot make them; the cache works all the
    same) and without progress bars, which come through the window's
    pipe as one endless line. Set before anything imports it."""
    env = os.environ if env is None else env
    env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    return env


class _NotChatty:
    """A filter for the console handler: the chatty loggers only from a
    warning up. The log file keeps everything."""

    def filter(self, record) -> bool:
        import logging

        name = record.name.split(".")[0]
        return name not in CHATTY_LOGGERS or record.levelno >= logging.WARNING


def quiet_window() -> None:
    import logging

    for handler in logging.getLogger().handlers:
        if not isinstance(handler, logging.FileHandler):
            handler.addFilter(_NotChatty())


def prefetch_whisper(model: str | None = None, download=None,
                     cached=None) -> int:
    """At the installation: fetch the Whisper model the helper's rounds
    use, so that its first round does not spend a quarter of an hour on
    three gigabytes (EDE-JS6X0J4 did). A model already there is not
    fetched again. Returns 0, or 1 when the download failed (the helper
    then fetches it at its first round, as before)."""
    from modules import whisper
    from modules.config import WhisperSettings
    from modules.translations import t

    settings = WhisperSettings() if model is None else \
        WhisperSettings(model=model)
    cached = whisper.model_cached if cached is None else cached
    if cached(settings):
        print(t("helper_whisper_cached").format(model=settings.model),
              flush=True)
        return 0
    print(t("helper_whisper_fetch").format(model=settings.model), flush=True)
    try:
        if download is None:
            from faster_whisper import download_model as download
        download(settings.model)
    except Exception as exc:  # noqa: BLE001 - the first round fetches it
        from modules import separation

        print(t("helper_whisper_fetch_failed").format(
            model=settings.model,
            problem=separation.last_line(f"{type(exc).__name__}: {exc}")),
            flush=True)
        return 1
    print(t("helper_whisper_fetched").format(model=settings.model),
          flush=True)
    return 0


#: The languages whose aligner model the installer fetches (B652): the
#: owner's songs are Dutch, a few English.
ALIGN_LANGUAGES = ("nl", "en")


def prefetch_aligners(languages=ALIGN_LANGUAGES, load=None) -> int:
    """At the installation: the forced aligner's models (WhisperX, one
    wav2vec2 model per language) - the rounds of 1.5.15 and 1.5.20 need
    them. Without WhisperX nothing happens. Returns 0, or 1 when one could
    not be fetched (a round fetches it then)."""
    from modules import separation, word_alignment
    from modules.translations import t

    if load is None:
        if not word_alignment.is_available():
            return 0

        def load(language):
            import whisperx  # type: ignore

            whisperx.load_align_model(language_code=language, device="cpu")
    failed = 0
    for language in languages:
        print(t("helper_aligner_fetch").format(language=language),
              flush=True)
        try:
            load(language)
        except Exception as exc:  # noqa: BLE001 - a round fetches it
            failed = 1
            print(t("helper_aligner_fetch_failed").format(
                language=language,
                problem=separation.last_line(f"{type(exc).__name__}: {exc}")),
                flush=True)
    return failed


def _on_close(stop, queue) -> None:
    """Closing the window or Ctrl+C: put the job back, stop what runs
    under this lane, and let the lane end. Windows gives a closing
    console a few seconds, enough for this."""
    if os.name != "nt":
        return
    import ctypes
    from modules import proc

    def handler(event):
        stop.asked = True
        if stop.current is not None:
            queue.release(stop.current)
            stop.current = None
        proc.terminate_all()
        return event in (0, 1)          # Ctrl+C/Break: we end ourselves

    routine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)(handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(routine, True)
    _on_close.keep = routine            # keep it alive


#: v1.0.28 (B659): the language the helper last followed, for the window
#: that opens before the laptop is found.
LANGUAGE_FILE = "language.txt"


def follow_language(queue_dir: Path | None = None,
                    home: Path | None = None) -> str:
    """v1.0.28 (B659): speak the program's language - what the program
    wrote into the queue (``laptop.json``), otherwise what was followed
    last time; Dutch when nothing says. Returns the code."""
    import json

    from modules import translations

    home = home or HOME
    code = None
    if queue_dir is not None:
        try:
            where = json.loads((Path(queue_dir) / "laptop.json").read_text(
                encoding="utf-8"))
            code = where.get("language") if isinstance(where, dict) else None
        except (OSError, ValueError):
            code = None
    remembered = home / LANGUAGE_FILE
    if code:
        try:
            remembered.write_text(str(code), encoding="utf-8")
        except OSError:
            pass
    else:
        try:
            code = remembered.read_text(encoding="utf-8").strip() or None
        except OSError:
            code = None
    translations.set_language(code or "nl")
    return translations.current_language()


def run_lane(queue_dir: Path, lane: str, share: str = "") -> int:
    """One lane: a worker loop until stopped. Returns the exit code."""
    from modules import __version__, cuda, logger, proc, queue_jobs
    from modules import work_queue

    home = ROOT.parent
    quiet_downloads()
    follow_language(queue_dir)
    logger.setup_logging(home / "logs" / f"helper_{lane}")
    quiet_window()
    os.environ["KT_WHISPER_LANES"] = "1"
    card_env = cpu_env = None
    if lane == MIXED:
        cuda.add_cuda_libraries()
        card_env = {"CUDA_VISIBLE_DEVICES": None, "KT_FREE_CARD": "1",
                    "KT_WHISPER_DEVICE": os.environ.get("KT_WHISPER_DEVICE",
                                                        "cuda"),
                    "KT_WHISPER_COMPUTE": os.environ.get(
                        "KT_WHISPER_COMPUTE", SMALL_CARD_COMPUTE)}
        cpu_env = {"CUDA_VISIBLE_DEVICES": "-1", "KT_FREE_CARD": None,
                   "KT_WHISPER_DEVICE": "cpu", "KT_WHISPER_COMPUTE": "int8"}
        _set_env(cpu_env)
        device = "gpu-or-cpu"
    elif lane == "gpu":
        os.environ.setdefault("KT_WHISPER_DEVICE", "cuda")
        os.environ.setdefault("KT_WHISPER_COMPUTE", "float16")
        os.environ["KT_FREE_CARD"] = "1"
        cuda.add_cuda_libraries()
        device = "gpu" if os.environ["KT_WHISPER_DEVICE"] == "cuda" \
            else "gpu+cpu-whisper"
    else:
        os.environ["KT_WHISPER_DEVICE"] = "cpu"
        os.environ["KT_WHISPER_COMPUTE"] = "int8"
        device = "cpu"
    queue = work_queue.Queue(queue_dir)
    worker = f"{work_queue.host_name()}-{lane}"
    say = _say(lane)
    say("helper_started", {"worker": worker, "queue": queue_dir,
                         "version": __version__})
    have = capabilities(say)
    if lane in ("cpu", MIXED) and have:
        # v1.0.21: rounds for the processor alone (a render) go here, not
        # to the card lane beside it. v1.0.24: the mixed lane takes them
        # too, with the card hidden.
        have.add("processor")
    stop = work_queue.Stop()
    _on_close(stop, queue)
    _watch_stop_flag(stop, queue)
    from modules import heat_guard

    # v1.0.24 (B646): the mixed lane has no temperature rules of its own.
    # The owner: the card slows itself down when it gets hot (Pav's held
    # at 86-89 °C in 1.5.18), so no other rules on top of that - with one
    # round at a time the processor lane beside it, which made Pav switch
    # itself off, is gone.
    heat = heat_guard.HeatGuard() if heat_guard.present() and \
        lane != MIXED else None
    handlers = queue_jobs.handlers()
    if lane == MIXED:
        handlers = mixed_handlers(handlers, card_env, cpu_env, say)
    try:
        outcome = work_queue.work(
            queue, worker, device, __version__, handlers, stop, say,
            accept=work_queue.accept_for(have, handlers),
            on_lost=proc.terminate_all, can=sorted(have),
            update_check=(lambda: update_waiting(share)) if share
            else None,
            finish_check=lambda: _flag(FINISH_FLAG).exists(),
            heat=heat,
            # v1.0.28 (B665): answers the share could not take wait here.
            parked=home / "parked" / lane)
    except KeyboardInterrupt:
        stop.asked = True
        proc.terminate_all()
        say("helper_stopped", {})
        return 0
    if stop():
        say("helper_stopped", {})
    return work_queue.UPDATE_EXIT if outcome == "update" else 0


def _watch_stop_flag(stop, queue) -> None:
    """"Stop now" from the window: the round goes back into the queue,
    what runs under this lane is stopped, and the lane ends."""
    import threading

    from modules import proc

    def look() -> None:
        while not stop():
            if _flag(STOP_FLAG).exists():
                # The worker loop puts the round back itself once its
                # heartbeat has stopped - doing it here too could put
                # back a claim that is another worker's by then.
                stop.asked = True
                proc.terminate_all()
                return
            time.sleep(2.0)

    threading.Thread(target=look, daemon=True).start()


#: A lane that falls over is started again, but not more often than this
#: within :data:`_RESTART_WINDOW_S`.
_MAX_RESTARTS = 5
_RESTART_WINDOW_S = 3600.0


# -- where the laptop is ------------------------------------------------------

def split_unc(path: str) -> tuple[str, list[str]]:
    """``\\\\server\\share\\KaraokeTool`` -> ``("server", ["share",
    "KaraokeTool"])``; a path that is not UNC has no server."""
    text = str(path).replace("/", "\\")
    if not text.startswith("\\\\"):
        return "", []
    parts = [part for part in text.strip("\\").split("\\") if part]
    return (parts[0], parts[1:]) if parts else ("", [])


def join_unc(server: str, rest: list[str]) -> str:
    return "\\\\" + "\\".join([server] + list(rest))


def _reachable(path: str, timeout: float = 15.0) -> bool:
    """Does the KaraokeTool folder answer there? A share that is gone can
    keep Windows asking for half a minute, so it gets a time limit."""
    import threading

    found = []

    def look() -> None:
        try:
            found.append((Path(path) / "KaraokeTool.py").exists())
        except OSError:
            found.append(False)

    thread = threading.Thread(target=look, daemon=True)
    thread.start()
    thread.join(timeout)
    return bool(found and found[0])


def _known() -> dict:
    import json

    try:
        return json.loads((HOME / "known.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def remember(share: str) -> None:
    """Keep what the laptop said about itself (its name and addresses),
    for the day its address changes."""
    import json

    from modules import work_queue

    known = dict(_known(), share=share)
    where = work_queue.queue_folder(share) / "laptop.json"
    try:
        said = json.loads(where.read_text(encoding="utf-8"))
        known["host"] = said.get("host", known.get("host", ""))
        known["addresses"] = sorted(set(said.get("addresses") or []) |
                                    set(known.get("addresses") or []))
    except (OSError, ValueError):
        pass
    try:
        (HOME / "known.json").write_text(json.dumps(known), encoding="utf-8")
        (HOME / "share.txt").write_text(share + "\n", encoding="utf-8")
    except OSError:
        pass


def candidates(stored: str, known: dict) -> list[str]:
    """Where to look, in the owner's order: the folder the installation
    came from, the laptop by name, its last known addresses."""
    out = [stored] if stored else []
    server, rest = split_unc(stored or known.get("share", ""))
    if rest:
        names = [known.get("host", "")] + list(known.get("addresses") or [])
        out += [join_unc(name, rest) for name in names
                if name and name.lower() != server.lower()]
    seen, unique = set(), []
    for path in out:
        if path.lower() not in seen:
            seen.add(path.lower())
            unique.append(path)
    return unique


def _own_networks() -> list[str]:
    """The first three numbers of this computer's own IPv4 addresses."""
    import socket

    addresses = set()
    try:
        addresses |= set(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))      # sends nothing
        addresses.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    return sorted({".".join(address.split(".")[:3]) for address in addresses
                   if address.count(".") == 3
                   and not address.startswith(("127.", "169.254."))})


def scan(rest: list[str], networks: list[str], limit_s: float = 120.0,
         reachable=None) -> str | None:
    """Look for the share on every address of the own networks, many at
    once: the last resort when the name and the known addresses fail."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    reachable = reachable or (lambda path: _reachable(path, 8.0))
    paths = [join_unc(f"{net}.{last}", rest) for net in networks
             for last in range(1, 255)]
    if not paths:
        return None
    pool = ThreadPoolExecutor(max_workers=64)
    futures = {pool.submit(reachable, path): path for path in paths}
    found = None
    try:
        for future in as_completed(futures, timeout=max(1.0, limit_s)):
            if future.result():
                found = futures[future]
                break
    except Exception:  # noqa: BLE001 - the time limit
        pass
    # What still waits is not looked at any more; what runs ends on its
    # own time limit without anybody waiting for it.
    pool.shutdown(wait=False, cancel_futures=True)
    return found


def find_share(stored: str, reachable=_reachable,
               networks=None) -> str | None:
    """The KaraokeTool folder on the laptop, wherever it is today."""
    known = _known()
    for path in candidates(stored, known):
        if reachable(path):
            return path
    _server, rest = split_unc(stored or known.get("share", ""))
    if not rest:
        return None
    return scan(rest, _own_networks() if networks is None else networks,
                reachable=reachable)


# -- keeping itself up to date -------------------------------------------------

_VERSION_LINE = re.compile(r'set "HELPER_VERSION=([0-9][0-9A-Za-z.]*)"')


def installer_version(path: Path) -> str | None:
    """The version an installer carries, or ``None``."""
    try:
        found = _VERSION_LINE.search(path.read_text(encoding="utf-8",
                                                    errors="replace"))
    except OSError:
        return None
    return found.group(1) if found else None


def installed_version(home: Path | None = None) -> str:
    try:
        return ((home or HOME) / INSTALLED_FILE).read_text(
            encoding="utf-8").strip()
    except OSError:
        return ""


def update_waiting(share: str, home: Path | None = None) -> bool:
    """Does the share have a NEWER installer than the one this helper was
    installed with? Unreadable (the share is away): no."""
    from modules import work_queue

    offered = installer_version(Path(share) / INSTALLER)
    if not offered:
        return False
    have = installed_version(home)
    return not have or work_queue.version_key(offered) > \
        work_queue.version_key(have)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="KaraokeTool helper: works on the long tests of the "
                    "program on the share.")
    parser.add_argument("--share", help="the KaraokeTool folder on the "
                        "share, e.g. \\\\10.0.0.18\\Tools\\KaraokeTool")
    parser.add_argument("--queue", help="the work queue folder (default: "
                        "helper\\kt_work in --share)")
    parser.add_argument("--lanes", default="auto",
                        help="auto, cpu, gpu or gpu,cpu")
    parser.add_argument("--check", action="store_true",
                        help="only say which lanes would run")
    parser.add_argument("--window", action="store_true",
                        help="show the helper in a window of its own "
                        "instead of the console")
    parser.add_argument("--lane", help=argparse.SUPPRESS)
    parser.add_argument("--probe", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--find", metavar="PATH",
                        help="print where the KaraokeTool folder on the "
                        "laptop is today (starting from PATH); exit 1 when "
                        "it is nowhere")
    parser.add_argument("--needs-update", metavar="SHARE",
                        help="exit 1 when the share has a newer installer "
                        "than this helper was installed with")
    parser.add_argument("--mirror-logs", metavar="SHARE",
                        help="put this helper's logs on the share")
    parser.add_argument("--prefetch-whisper", action="store_true",
                        help="fetch the Whisper model of the rounds and "
                        "the aligner's models now (the installer's step)")
    parser.add_argument("--start", action="store_true",
                        help="the shortcut's start: find the laptop, update "
                        "and run the helper in its window, no console")
    parser.add_argument("--remove", action="store_true",
                        help="take the helper off this computer")
    parser.add_argument("--installed", metavar="VERSION",
                        help="note the version this helper is installed "
                        "with (the installer's last step)")
    args = parser.parse_args(argv)
    # v1.0.28 (B659): the language followed last time, until the queue
    # says which the program speaks now.
    follow_language()

    from modules import work_queue
    from modules.translations import t

    if args.probe:
        import json

        print(json.dumps(probe()), flush=True)
        return 0
    if args.find is not None:
        found = find_share(args.find.strip().strip('"'))
        if found is None:
            print(t("helper_share_not_found").format(share=args.find),
                  file=sys.stderr, flush=True)
            return 1
        remember(found)
        print(found, flush=True)
        return 0
    if args.mirror_logs is not None:
        mirror_logs(HOME / "logs",
                    central_logs(args.mirror_logs.strip().strip('"')))
        return 0
    if args.needs_update is not None:
        return 1 if update_waiting(args.needs_update.strip().strip('"')) \
            else 0
    if args.start:
        return start(args.lanes)
    if args.remove:
        return remove_command()
    if args.prefetch_whisper:
        quiet_downloads()
        # v1.0.23 (B652): and the aligner's models with it.
        return max(prefetch_whisper(), prefetch_aligners())
    if args.installed:
        (HOME / INSTALLED_FILE).write_text(args.installed.strip() + "\n",
                                           encoding="utf-8")
        return 0
    if args.queue:
        queue_dir = Path(args.queue)
    elif args.share:
        queue_dir = work_queue.queue_folder(args.share)
    elif not args.check:
        parser.error("--share or --queue is needed")
    if args.lane:
        return run_lane(queue_dir, args.lane, args.share or "")
    if args.share:
        import threading

        from modules import logger as log_setup

        log_setup.setup_logging(HOME / "logs" / "helper")
        remember(args.share)
        mirror_logs(HOME / "logs", central_logs(args.share))
        stop_mirror = threading.Event()
        _keep_mirroring(args.share, stop_mirror)
        if update_waiting(args.share):
            _tell(t("helper_update"))
            mirror_logs(HOME / "logs", central_logs(args.share))
            return work_queue.UPDATE_EXIT
    if args.check:
        lanes, found, _big, card = plan_lanes(args.lanes)
        print(t("helper_check").format(card=card,
                                     lanes=", ".join(lanes),
                                     device=found["device"],
                                     compute=found["compute"]))
        return 0
    clear_flags()
    window = _window_parts(queue_dir) if args.window else None
    if window is None:
        code = serve(args.share or "", queue_dir, args.lanes)
    else:
        import threading

        result: dict = {}

        def run() -> None:
            result["code"] = serve(args.share or "", queue_dir, args.lanes,
                                   window)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        window["run"](lambda: not thread.is_alive())
        thread.join()
        code = result.get("code", 0)
    if code == OWNER_EXIT and _flag(REMOVE_FLAG).exists():
        remove_helper(args.share or "")
    return code


def plan_lanes(requested: str) -> tuple[list[str], dict, bool, str]:
    """The lanes this computer runs, what the card test found, whether
    the card is big enough, and what to say of the card."""
    from modules import cuda
    from modules.translations import t

    requested = lanes_wanted(requested)
    found = (_probe_elsewhere() if requested != "cpu" else
             {"gpu_ok": False, "card": "-", "device": "cpu",
              "compute": "int8"})
    big = cuda.big_enough(found)
    lanes = choose_lanes(requested, found["gpu_ok"], big)
    card = found["card"]
    if found.get("gpu_ok") and not big and MIXED in lanes:
        card = t("helper_card_mixed").format(
            card=card, memory=found.get("memory_gb"),
            least=cuda.MIN_CARD_GB)
    elif found.get("gpu_ok") and not big and "gpu" not in lanes:
        card = t("helper_card_too_small").format(
            card=card, memory=found.get("memory_gb"),
            least=cuda.MIN_CARD_GB)
    return lanes, found, big, card


def serve(share: str, queue_dir: Path, requested: str = "auto",
          window: dict | None = None) -> int:
    """Start the lanes and keep them going until they end: 0, the exit
    code of an update (a newer version waits) or :data:`OWNER_EXIT` (the
    owner stopped the helper)."""
    from modules import local_copy, work_queue
    from modules.translations import t

    follow_language(queue_dir)
    lanes, found, big, card = plan_lanes(requested)
    # v1.0.23 (B647): what crashed rounds left in %TEMP% goes.
    local_copy.tidy()
    if window is not None:
        window["set_lanes"](lanes, queue_dir)
    _tell(t("helper_lanes").format(card=card, lanes=", ".join(lanes)))

    def start(lane: str):
        env = quiet_downloads(dict(os.environ, PYTHONUNBUFFERED="1",
                                   PYTHONIOENCODING="utf-8"))
        if lane == "cpu":
            # The processor lane may not see the card, or both lanes
            # would end up on it.
            env["CUDA_VISIBLE_DEVICES"] = "-1"
        else:
            env["KT_WHISPER_DEVICE"] = found["device"]
            env["KT_WHISPER_COMPUTE"] = found["compute"]
            if lane == MIXED or not big:
                # v1.0.24 (B646): large-v3 in float16 does not fit a 4 GB
                # card (1.5.18 on Pav); the smaller type is half of it.
                env["KT_WHISPER_COMPUTE"] = SMALL_CARD_COMPUTE
        command = [_console_python(), str(Path(__file__).resolve()),
                   "--queue", str(queue_dir), "--lane", lane]
        if share:
            command += ["--share", share]
        if window is None:
            return subprocess.Popen(command, env=env)
        from modules import proc

        child = subprocess.Popen(
            command, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", **proc.no_window_kwargs())
        _read_lines(child, window["lines"])
        return child

    codes = _supervise(start, lanes, share)
    if share:
        mirror_logs(HOME / "logs", central_logs(share))
    # The owner's stop goes before an update: the start finds the update
    # at the next start all the same.
    if _flag(FINISH_FLAG).exists() or _flag(STOP_FLAG).exists():
        clear_flags()
        return OWNER_EXIT
    if work_queue.UPDATE_EXIT in codes.values():
        return work_queue.UPDATE_EXIT
    return 0

def _log_crashes() -> None:
    """Under pythonw nothing shows an error: it goes into the log."""
    import logging

    def hook(kind, value, trace) -> None:
        logging.getLogger("helper").error(_text("log_helper_crashed"),
                                          exc_info=(kind, value, trace))

    sys.excepthook = hook
    try:
        import faulthandler

        faulthandler.enable(open(HOME / "logs" / "helper_crash.log", "a",
                                 encoding="utf-8"))
    except OSError:
        pass


def _console_python() -> str:
    """The lanes run under ``python.exe`` also when the helper itself is
    ``pythonw.exe`` (the window): their lines come through a pipe, and
    they need a console of their own for nothing."""
    path = Path(sys.executable)
    if path.name.lower() == "pythonw.exe":
        console = path.with_name("python.exe")
        if console.exists():
            return str(console)
    return sys.executable


def _read_lines(child, lines) -> None:
    """A lane's lines into the window, and into the helper's log."""
    import threading

    def read() -> None:
        for row in child.stdout:
            lines.put(row.rstrip())

    threading.Thread(target=read, daemon=True).start()


def _window_parts(queue_dir: Path | None = None) -> dict | None:
    """What the window needs; ``None`` without Qt (then the console).
    v1.0.24 (B653): the lanes and the queue come in later
    (``set_lanes``) - the window is there from the start."""
    import queue as queue_module

    try:
        from modules import helper_window
    except Exception:  # noqa: BLE001 - no Qt here: the console as before
        return None
    from modules import __version__, work_queue
    from modules.translations import t

    import threading

    lines: queue_module.Queue = queue_module.Queue()
    global _SINK
    _SINK = lines.put
    _log_crashes()
    host = work_queue.host_name()
    state: dict = {"lanes": [], "queue": queue_dir, "ended": False}
    known: dict[str, dict] = {}

    def set_lanes(lanes: list[str], queue: Path | None = None) -> None:
        if queue is not None:
            state["queue"] = queue
        state["lanes"] = list(lanes)

    def read_status() -> None:
        # On a thread of its own: a share that is away can keep a read
        # waiting for half a minute, and the window may never hang on it.
        import json

        while True:
            queue = state["queue"]
            for lane in list(state["lanes"]):
                if queue is None:
                    break
                path = work_queue.Queue(Path(queue)).workers / \
                    f"{work_queue._safe(f'{host}-{lane}')}.json"
                try:
                    known[lane] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
            time.sleep(2.0)

    threading.Thread(target=read_status, daemon=True).start()

    def status_of(lane: str) -> dict | None:
        return known.get(lane)

    def remove() -> None:
        set_flag(REMOVE_FLAG, True)
        set_flag(STOP_FLAG, True)

    def run(finished) -> None:
        helper_window.run(
            t("helper_window_title").format(host=host, version=__version__),
            lambda: state["lanes"], status_of, lines,
            lambda on: set_flag(FINISH_FLAG, on),
            lambda: set_flag(STOP_FLAG, True), finished, remove,
            lambda: state["ended"])

    def ended() -> None:
        state["ended"] = True

    return {"lines": lines, "run": run, "set_lanes": set_lanes,
            "ended": ended, "state": state}


# -- the start, in the window (v1.0.24, B653) --------------------------------------

#: The helper's process number while it runs (for ``--remove``).
PID_FILE = "helper.pid"
#: An installation that started longer ago than this has gone wrong.
_LOCK_S = 3 * 3600.0


def _installing(home: Path | None = None, now: float | None = None) -> bool:
    """Is an installation running (it started this helper's update)?"""
    lock = (home or HOME) / "installing.lock"
    try:
        age = (time.time() if now is None else now) - lock.stat().st_mtime
    except OSError:
        return False
    return age < _LOCK_S


def _owner_asked() -> bool:
    return _flag(FINISH_FLAG).exists() or _flag(STOP_FLAG).exists()


def _wait(seconds: float, sleep=time.sleep) -> bool:
    """Wait, unless the owner asks to stop: then ``True`` at once."""
    for _step in range(max(1, int(seconds))):
        if _owner_asked():
            return True
        sleep(1.0)
    return _owner_asked()


def launch_update(share: str, home: Path | None = None) -> bool:
    """The installer of the share, copied here and started with ``/update``
    in a window of its own - it starts the helper again when it is done."""
    import shutil

    home = home or HOME
    target = home / "install_helper_run.bat"
    try:
        shutil.copyfile(Path(share) / INSTALLER, target)
    except OSError:
        return False
    try:
        subprocess.Popen(["cmd", "/c", str(target), "/update"],
                         cwd=str(home),
                         creationflags=getattr(subprocess,
                                               "CREATE_NEW_CONSOLE", 0))
    except OSError:
        return False
    return True


def _stored_share(home: Path | None = None) -> str:
    try:
        return ((home or HOME) / "share.txt").read_text(
            encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def session(requested: str, window: dict, find=None, serve_=None,
            update=None, sleep=time.sleep) -> int:
    """What ``helper_start.bat`` did, in the window: find the laptop (every
    minute while it is away), fetch a newer version when the share has
    one, start the lanes, and after an update of the lanes start over."""
    import shutil
    import threading

    from modules import work_queue
    from modules.translations import t

    find = find or find_share
    serve_ = serve_ or serve
    update = update or launch_update
    if _installing():
        _tell(t("helper_being_updated"))
        sleep(15.0)
        return 0
    shutil.rmtree(Path(os.environ.get("LOCALAPPDATA", str(HOME.parent)))
                  / OLD_HOME_NAME, ignore_errors=True)
    stored = _stored_share()
    while True:
        if _owner_asked():
            clear_flags()
            if _flag(REMOVE_FLAG).exists():
                remove_helper(stored)
            return OWNER_EXIT
        share = find(stored)
        if share is None:
            _tell(t("helper_start_no_laptop"))
            _wait(60.0, sleep)
            continue
        remember(share)
        stored = share
        _tell(t("helper_start_found").format(share=share))
        mirror_logs(HOME / "logs", central_logs(share))
        if update_waiting(share):
            _tell(t("helper_update"))
            mirror_logs(HOME / "logs", central_logs(share))
            if update(share):
                return work_queue.UPDATE_EXIT
            _tell(t("helper_update_failed"))
            _wait(60.0, sleep)
            continue
        stop_mirror = threading.Event()
        _keep_mirroring(share, stop_mirror)
        try:
            code = serve_(share, work_queue.queue_folder(share), requested,
                          window)
        finally:
            stop_mirror.set()
        if code == OWNER_EXIT:
            if _flag(REMOVE_FLAG).exists():
                remove_helper(share)
            return OWNER_EXIT
        if code == work_queue.UPDATE_EXIT:
            continue
        _tell(t("helper_stopped_end"))
        window["ended"]()
        return code


def start(requested: str = "auto") -> int:
    """``--start``, what the shortcut runs under ``pythonw``: the window at
    once, and the start of :func:`session` in it - no console."""
    import threading

    from modules import logger as log_setup

    (HOME / "logs").mkdir(parents=True, exist_ok=True)
    log_setup.setup_logging(HOME / "logs" / "helper")
    clear_flags()
    set_flag(REMOVE_FLAG, False)
    window = _window_parts(None)
    if window is None:
        # No Qt here: the start file in a console, as before.
        subprocess.Popen(["cmd", "/c", str(HOME / "helper_start.bat")],
                         cwd=str(HOME),
                         creationflags=getattr(subprocess,
                                               "CREATE_NEW_CONSOLE", 0))
        return 0
    try:
        (HOME / PID_FILE).write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    result: dict = {"code": 0}

    def control() -> None:
        try:
            result["code"] = session(requested, window)
        except Exception:  # noqa: BLE001 - into the log, the window says it
            import logging

            logging.getLogger("helper").exception(_text("log_helper_start_failed"))
            window["ended"]()

    thread = threading.Thread(target=control, daemon=True)
    thread.start()
    window["run"](lambda: not thread.is_alive()
                  and not window["state"]["ended"])
    # Closed while the lanes still stop (or the helper removes itself):
    # that is finished first.
    thread.join()
    try:
        (HOME / PID_FILE).unlink()
    except OSError:
        pass
    return result["code"]


# -- taking the helper off this computer (v1.0.24, B655) ---------------------------

#: What the installer wrote down it installed itself (``ffmpeg``,
#: ``python``; ``unknown`` for a helper installed before it kept count).
INSTALLED_BY_FILE = "installed_by_helper.txt"
#: What winget calls them.
WINGET_IDS = {"ffmpeg": "Gyan.FFmpeg", "python": "Python.Python.3.13"}
#: Demucs' checkpoints for the two ways the program uses, when the list of
#: the installed Demucs cannot be read.
_DEMUCS_FILES = ("955717e8-8726e21a.th", "f7e0c4bc-ba3fe64a.th",
                 "d12395a8-e57c48e6.th", "92cfc3b6-ef3bcb9c.th",
                 "04573f0d-f3cf25b2.th")
#: The aligner's models, when WhisperX cannot say.
_ALIGNER_REPOS = ("jonatasgrosman/wav2vec2-large-xlsr-53-dutch",)
_ALIGNER_FILES = ("wav2vec2_fairseq_base_ls960_asr_ls960.pth",)


def installed_by_helper(home: Path | None = None) -> set[str]:
    """What this helper installed itself. Without a note - a helper from
    before v1.0.24 - it counts as both: the owner's choice."""
    try:
        words = {line.strip().lower() for line in
                 ((home or HOME) / INSTALLED_BY_FILE).read_text(
                     encoding="utf-8", errors="replace").splitlines()}
    except OSError:
        return set(WINGET_IDS)
    if "unknown" in words:
        return set(WINGET_IDS)
    return {word for word in words if word in WINGET_IDS}


def program_here(share: str, host: str | None = None,
                 addresses=None) -> bool:
    """Does the program itself run on this computer (the helper on the
    laptop)? Then what the two share - Python, ffmpeg, the models - stays."""
    from modules import work_queue

    server, _rest = split_unc(share)
    if not share or not server:
        return bool(share)          # a local folder: the program is here
    names = {(host or work_queue.host_name()).lower(), "localhost",
             "127.0.0.1"}
    if addresses is None:
        import socket

        try:
            names |= set(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass
    else:
        names |= set(addresses)
    return server.lower() in {name.lower() for name in names}


def _desktop() -> Path:
    """The desktop as Windows has it (OneDrive moves it)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0,
                                                   buffer)
            if buffer.value:
                return Path(buffer.value)
        except Exception:  # noqa: BLE001 - the usual place then
            pass
    return Path.home() / "Desktop"


def _model_caches() -> list[Path]:
    """The models this helper fetched outside its own folder: Whisper's
    and the aligner's in the Hugging Face cache, Demucs' and the English
    aligner's in PyTorch's."""
    from modules import whisper

    found: list[Path] = []
    hub = whisper.hub_cache_dir()
    repos = list(_ALIGNER_REPOS)
    files = list(_DEMUCS_FILES) + list(_ALIGNER_FILES)
    try:
        from whisperx import alignment  # type: ignore

        repos += [name for language, name in
                  alignment.DEFAULT_ALIGN_MODELS_HF.items()
                  if language in ALIGN_LANGUAGES]
    except Exception:  # noqa: BLE001 - the names above then
        pass
    try:
        from importlib import resources

        listed = (resources.files("demucs") / "remote" / "files.txt"
                  ).read_text(encoding="utf-8")
        files += [line.strip().split("/")[-1] for line in listed.splitlines()
                  if line.strip().endswith(".th")]
    except Exception:  # noqa: BLE001 - the names above then
        pass
    try:
        for entry in hub.iterdir():
            if entry.name.lower().startswith("models--systran--faster-"):
                found.append(entry)
    except OSError:
        pass
    found += [hub / ("models--" + repo.replace("/", "--"))
              for repo in dict.fromkeys(repos)]
    torch_home = Path(os.environ.get("TORCH_HOME") or
                      Path.home() / ".cache" / "torch")
    found += [torch_home / "hub" / "checkpoints" / name
              for name in dict.fromkeys(files)]
    return [path for path in found if path.exists()]


def removal_plan(share: str, home: Path | None = None) -> dict:
    """What "Helper verwijderen" takes away, and what stays."""
    from modules import local_copy

    home = home or HOME
    local = Path(os.environ.get("LOCALAPPDATA", str(home.parent)))
    here = program_here(share)
    desktop = _desktop()
    return {
        "home": home,
        "now": [path for path in (local / OLD_HOME_NAME,
                                  local_copy.base(),
                                  desktop / "KaraokeTool helper.lnk",
                                  desktop / "KaraokeTool hulp.lnk")
                if path.exists()] + ([] if here else _model_caches()),
        "uninstall": [] if here else [WINGET_IDS[name] for name in
                                      sorted(installed_by_helper(home))],
        "program_here": here,
    }


def _remove_now(paths) -> list[str]:
    import shutil

    failed = []
    for path in paths:
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError:
            failed.append(str(path))
    return failed


def _forget_in_queue(share: str) -> None:
    """Its status goes from the queue, so it is no longer listed. Its
    speeds stay - should it come back - and so do its logs on the laptop."""
    from modules import work_queue

    if not share:
        return
    workers = work_queue.Queue(work_queue.queue_folder(share)).workers
    host = work_queue.host_name()
    for lane in ("gpu", "cpu", MIXED):
        try:
            (workers / f"{work_queue._safe(f'{host}-{lane}')}.json").unlink()
        except OSError:
            pass


def removal_script(plan: dict, pid: int) -> str:
    """The last step, in a batch file of its own in %TEMP%: once this
    helper has stopped, uninstall what it installed and remove its folder
    (a program cannot remove the folder it runs from)."""
    from modules.translations import t

    home = str(plan["home"])
    rows = ["@echo off", "title KaraokeTool helper",
            "echo " + t("helper_remove_script_busy"),
            ":wait",
            f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
            "if not errorlevel 1 (",
            "    timeout /t 2 /nobreak >nul",
            "    goto :wait",
            ")"]
    for package in plan["uninstall"]:
        rows.append(f"winget uninstall -e --id {package} --silent "
                    "--accept-source-agreements")
    rows += ["set TRIES=0",
             ":again",
             f'rd /s /q "{home}" >nul 2>nul',
             f'if not exist "{home}" goto :done',
             "set /a TRIES+=1",
             "if %TRIES% GEQ 15 goto :done",
             "timeout /t 3 /nobreak >nul",
             "goto :again",
             ":done",
             f'if exist "{home}" echo '
             + t("helper_remove_script_left").format(folder=home),
             "echo " + t("helper_remove_script_done"),
             "timeout /t 15 >nul",
             '(goto) 2>nul & del "%~f0"']
    return "\r\n".join(rows) + "\r\n"


def remove_helper(share: str, pid: int | None = None, start=True) -> Path:
    """B655: take this helper off this computer. What can go now goes now;
    the folder it runs from, and what it installed, go in a batch file
    that waits until it has stopped. Returns that file."""
    import logging
    import tempfile

    from modules.translations import t

    plan = removal_plan(share)
    _tell(t("helper_removing"))
    if plan["program_here"]:
        _tell(t("helper_remove_program_here"))
    _forget_in_queue(share)
    for path in _remove_now(plan["now"]):
        logging.getLogger("helper").warning(_text("log_helper_not_removed"),
                                            path)
    pid = os.getpid() if pid is None else pid
    script = Path(tempfile.gettempdir()) / f"kt_helper_remove_{pid}.bat"
    script.write_bytes(removal_script(plan, pid).encode("cp1252",
                                                        errors="replace"))
    if start:
        subprocess.Popen(["cmd", "/c", str(script)],
                         cwd=tempfile.gettempdir(),
                         creationflags=getattr(subprocess,
                                               "CREATE_NEW_CONSOLE", 0))
    return script


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259            # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def remove_command() -> int:
    """``--remove`` (``install_helper.bat /remove``): a helper that runs is
    asked to stop and take itself off; otherwise this does it."""
    from modules.translations import t

    try:
        pid = int((HOME / PID_FILE).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = 0
    if pid and pid != os.getpid() and _alive(pid):
        set_flag(REMOVE_FLAG, True)
        set_flag(STOP_FLAG, True)
        print(t("helper_remove_asked"), flush=True)
        return 0
    remove_helper(_stored_share())
    return 0


def _supervise(start, lanes: list[str], share: str) -> dict[str, int]:
    """Start the lanes and keep them going; a lane that falls over is
    started again (not after the owner asked to stop). A lane that ended
    because the owner asked to stop after its round is started again when
    he takes that back while another lane still works. Returns the exit
    code of every lane."""
    from modules import work_queue
    from modules.translations import t

    children = {lane: start(lane) for lane in lanes}
    restarts: dict[str, list[float]] = {lane: [] for lane in lanes}
    codes: dict[str, int] = {}
    parked: list[str] = []
    try:
        while children:
            time.sleep(2.0)
            if parked and not _flag(FINISH_FLAG).exists() and \
                    not _flag(STOP_FLAG).exists():
                for lane in parked:
                    codes.pop(lane, None)
                    children[lane] = start(lane)
                parked = []
            for lane, child in list(children.items()):
                code = child.poll()
                if code is None:
                    continue
                del children[lane]
                if code == 0 and _flag(FINISH_FLAG).exists() and \
                        not _flag(STOP_FLAG).exists():
                    parked.append(lane)
                    codes[lane] = code
                    continue
                if code in (0, work_queue.UPDATE_EXIT) or \
                        _flag(FINISH_FLAG).exists() or \
                        _flag(STOP_FLAG).exists():
                    codes[lane] = code
                    continue
                now = time.monotonic()
                recent = [moment for moment in restarts[lane]
                          if now - moment < _RESTART_WINDOW_S]
                if len(recent) >= _MAX_RESTARTS:
                    _tell(t("helper_lane_gave_up").format(lane=lane))
                    codes[lane] = code
                    continue
                restarts[lane] = recent + [now]
                _tell(t("helper_lane_restart").format(lane=lane, code=code))
                time.sleep(30.0)
                children[lane] = start(lane)
    except KeyboardInterrupt:
        for child in children.values():
            try:
                child.wait(timeout=60)
            except Exception:  # noqa: BLE001
                child.kill()
        if share:
            mirror_logs(HOME / "logs", central_logs(share))
        codes = {lane: 0 for lane in lanes}
    return codes


#: v1.0.23: where :func:`_tell` puts its lines when the helper has a window.
_SINK = None


def _text(key: str) -> str:
    """A log text in the helper's language (v1.0.28, B659)."""
    from modules.translations import t

    return t(key)


def _tell(text: str) -> None:
    """A line in the window (or the console) and in the log."""
    import logging

    if _SINK is not None:
        _SINK(text)
    else:
        print(text, flush=True)
    logging.getLogger("helper").debug(text)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
