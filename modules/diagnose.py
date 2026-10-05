"""Look at a helper from the laptop, through the work queue (v1.0.21).

The card lane of one helper (Pav) took hours over rounds the laptop does
in one, and the only way to see why was to sit at that computer. Now the
program can send a helper a check: a round of its own kind, addressed to
that computer (``for``) and ahead of every waiting round (``priority``),
so whichever lane of that computer is free first takes it. The check
changes nothing; it only looks:

* the card as the driver sees it (``nvidia-smi``: name, memory, load,
  and which processes are on it right now - is the card lane's
  separation there at all?);
* the card test of :mod:`modules.cuda` in the program's environment;
* PyTorch and ONNX Runtime in the Roformer environment (a version that
  does not compute on the card, or a card too small);
* the three-second trial separation with the card and without, timed -
  the plainest answer to "does the card help";
* processors and memory, and what the lanes of that computer are doing;
* the last lines of the logs of both lanes;
* v1.0.22 (B639): the card under load. The three-second trial said
  Pav's card is 3.5 times faster than its processor, yet its card lane
  took nine hours over the three karaoke models on one song. A minute of
  sound through those three models on the card, with the card's
  temperature, clocks, memory and what holds it back read every few
  seconds, says which of the two suspects it is: a card whose memory
  runs full (Windows then lays the rest in ordinary memory, very
  slowly) or a card that is too hot and slows itself down;
* v1.0.23 (B645): which tasks the card can take and how hot each makes
  it (:func:`card_profile`): at rest, then Whisper large-v3, one Roformer
  model with its own and with smaller pieces, Demucs in shorter pieces
  and the three karaoke models together, each on a minute of sound, the
  card cooling below 70 °C between them - the numbers the rules for a
  small card are to come from.

The answer is a report in Markdown; the program keeps it in
``logs\\helpers\\<computer>`` next to the helper's own logs and shows it.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

from .translations import t

#: The kind of round a check is in the work queue.
JOB_KIND = "check_round"
#: Ahead of every round of a test.
PRIORITY = 10
#: How many lines of each lane's log go into the report.
LOG_LINES = 80
#: How long 1.5.18 waits for the answers at most.
WAIT_S = 3 * 3600.0
#: A trial separation that takes longer says enough.
TRIAL_TIMEOUT_S = 600
#: The load trial: this much sound, through the karaoke trio.
LOAD_SECONDS = 60
#: How often the card is read during the load trial.
LOAD_EVERY_S = 5.0
#: A load trial that takes longer says enough.
LOAD_TIMEOUT_S = 900
#: What ``nvidia-smi`` is asked during the load trial.
LOAD_QUERY = ("temperature.gpu,clocks.sm,clocks.max.sm,power.draw,"
              "memory.used,memory.total,utilization.gpu,"
              "clocks_event_reasons.active")
#: What drivers before the rename (R535) call the last field.
LOAD_QUERY_OLD = LOAD_QUERY.replace("clocks_event_reasons",
                                    "clocks_throttle_reasons")


def check_job(host: str, version: str) -> dict:
    from . import work_queue

    # v1.0.24 (B656): ``own_heat`` - the check measures the card as it
    # is, heat and all; the lane's heat guard stopping the whole check
    # ended Pav's profile halfway, without Demucs and the trio.
    return {"id": work_queue.job_id(f"check|{host}|{time.time_ns()}"),
            "kind": JOB_KIND, "class": JOB_KIND, "needs": [],
            "for": host, "priority": PRIORITY, "version": version,
            "own_heat": True,
            "label": t("check_label").format(host=host), "payload": {}}


def _card_free(env: dict | None = None) -> dict:
    """An environment in which a child sees the card (the processor lane
    hides it from itself)."""
    env = dict(os.environ if env is None else env)
    env.pop("CUDA_VISIBLE_DEVICES", None)
    return env


def _run(command: list[str], env: dict | None = None,
         timeout: float = 600) -> tuple[int, str, float]:
    from . import proc

    began = time.monotonic()
    try:
        done = proc.run(command, check=False, timeout=timeout, env=env,
                        cwd=str(Path(__file__).resolve().parents[1]))
        text = (done.stdout or "") + (done.stderr or "")
        return done.returncode, text.strip(), time.monotonic() - began
    except Exception as exc:  # noqa: BLE001 - a check reports, never falls
        return -1, f"{type(exc).__name__}: {exc}", time.monotonic() - began


def _block(text: str, limit: int = 4000) -> list[str]:
    text = str(text or "").strip() or "-"
    if len(text) > limit:
        text = "..." + text[-limit:]
    return ["```", text, "```"]


def _memory() -> str:
    """Total and free memory, in GB."""
    try:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong),
                        ("load", ctypes.c_ulong),
                        ("total", ctypes.c_ulonglong),
                        ("free", ctypes.c_ulonglong),
                        ("page_total", ctypes.c_ulonglong),
                        ("page_free", ctypes.c_ulonglong),
                        ("virtual_total", ctypes.c_ulonglong),
                        ("virtual_free", ctypes.c_ulonglong),
                        ("extended", ctypes.c_ulonglong)]

        status = Status()
        status.length = ctypes.sizeof(Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return f"{status.total / 2**30:.1f} GB, {status.free / 2**30:.1f} " \
               f"GB free, load {status.load}%"
    except Exception:  # noqa: BLE001 - not Windows
        try:
            pages = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
            return f"{pages / 2**30:.1f} GB"
        except (AttributeError, ValueError, OSError):
            return "-"


def _tail(path: Path, lines: int = LOG_LINES) -> str:
    try:
        rows = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "-"
    return "\n".join(rows[-lines:])


_TORCH_PROBE = (
    "import json\n"
    "out = {}\n"
    "try:\n"
    "    import torch\n"
    "    out['torch'] = torch.__version__\n"
    "    out['torch_cuda'] = torch.version.cuda\n"
    "    out['cuda_available'] = torch.cuda.is_available()\n"
    "    if torch.cuda.is_available():\n"
    "        p = torch.cuda.get_device_properties(0)\n"
    "        out['card'] = p.name\n"
    "        out['card_memory_gb'] = round(p.total_memory / 2**30, 1)\n"
    "        out['capability'] = '%d.%d' % (p.major, p.minor)\n"
    "        out['arch_list'] = torch.cuda.get_arch_list()\n"
    "except Exception as exc:\n"
    "    out['torch_error'] = repr(exc)[:300]\n"
    "try:\n"
    "    import onnxruntime\n"
    "    out['onnxruntime'] = onnxruntime.__version__\n"
    "    out['providers'] = onnxruntime.get_available_providers()\n"
    "except Exception as exc:\n"
    "    out['onnx_error'] = repr(exc)[:300]\n"
    "print(json.dumps(out))\n")


def _card_seen(probe_text: str) -> bool:
    """Did the probe of the Roformer environment see a card?"""
    for row in reversed(str(probe_text or "").splitlines()):
        try:
            return bool(json.loads(row).get("cuda_available"))
        except (ValueError, AttributeError):
            continue
    return False


def _test_sound(path: Path, seconds: int = LOAD_SECONDS) -> None:
    """A minute of something like music: a chord that changes every two
    seconds, a beat and some noise - enough for the models to work as
    hard as on a song."""
    import numpy as np
    import soundfile

    rate = 44_100
    moment = np.arange(rate * seconds) / rate
    rng = np.random.default_rng(1)
    roots = (220.0, 246.9, 261.6, 293.7, 329.6)
    chord = np.zeros_like(moment)
    for n, root in enumerate(roots):
        on = (moment // 2.0).astype(int) % len(roots) == n
        for ratio in (1.0, 1.25, 1.5):
            chord += on * np.sin(2 * np.pi * root * ratio * moment)
    beat = np.exp(-((moment % 0.5) * 30.0)) * rng.standard_normal(
        moment.size)
    wave = 0.15 * chord + 0.3 * beat + 0.02 * rng.standard_normal(
        moment.size)
    soundfile.write(str(path), np.stack([wave, wave], axis=1)
                    .astype(np.float32), rate, subtype="FLOAT")


#: v1.0.23 (B645): after a task the card cools to this before the next.
COOL_TO_C = 70.0
#: ...but no longer than this.
COOL_MAX_S = 600.0
#: How long the card is read before the first task, at rest.
REST_S = 30.0
#: A smaller piece at a time for a Roformer model (the library's
#: default is 256).
SMALL_SEGMENT = 128
#: Pieces of this many seconds for Demucs (its default is 7.8).
DEMUCS_SEGMENT = 4

_WHISPER_TASK = (
    "import sys\n"
    "from modules import cuda\n"
    "cuda.add_cuda_libraries()\n"
    "from faster_whisper import WhisperModel\n"
    "model = WhisperModel('large-v3', device='cuda', compute_type=sys.argv[2])\n"
    "segments, _info = model.transcribe(sys.argv[1], language='nl')\n"
    "print('segments', sum(1 for _s in segments))\n")



def _reading(query: str) -> tuple[int, list[str]]:
    code, text, _took = _run(["nvidia-smi", f"--query-gpu={query}",
                              "--format=csv,noheader,nounits"], timeout=30)
    row = text.splitlines()[0] if code == 0 and text else ""
    return code, [part.strip() for part in row.split(",")] if row else []


def _number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class _Card:
    """The card read now and then; remembers which field name works."""

    def __init__(self) -> None:
        self.query = LOAD_QUERY

    def read(self) -> list[str]:
        code, row = _reading(self.query)
        if code != 0 and self.query == LOAD_QUERY:
            self.query = LOAD_QUERY_OLD         # a driver before R535
            code, row = _reading(self.query)
        return row

    def degrees(self) -> float | None:
        row = self.read()
        return _number(row[0]) if row else None


def _under_load(card: _Card, command: list[str], stop,
                timeout: float = LOAD_TIMEOUT_S) -> dict:
    """Run a task on the card, reading the card every few seconds."""
    import threading

    done: dict = {}

    def task() -> None:
        done["result"] = _run(command, env=_card_free(), timeout=timeout)

    from . import proc

    worker = threading.Thread(target=task, daemon=True)
    worker.start()
    began = time.monotonic()
    rows: list[list[str]] = []
    while worker.is_alive():
        row = card.read()
        if row:
            rows.append([f"{time.monotonic() - began:.0f}"] + row)
        worker.join(LOAD_EVERY_S)
        if stop():
            proc.terminate_all()
            break
    worker.join(30.0)
    code, text, took = done.get("result", (-1, t("check_stopped"), 0.0))
    temps = [_number(row[1]) for row in rows if len(row) > 1]
    memory = [_number(row[5]) for row in rows if len(row) > 5]
    total = next((_number(row[6]) for row in rows if len(row) > 6), None)
    reasons = sorted({row[8] for row in rows if len(row) > 8
                      and row[8] not in ("0x0000000000000000", "0x0", "")})
    return {"code": code, "text": text, "took": took, "rows": rows,
            "timeout": took >= timeout - 1.0,
            "hottest": max((x for x in temps if x is not None),
                           default=None),
            "memory": max((x for x in memory if x is not None),
                          default=None),
            "total": total, "reasons": reasons}


def _cool(card: _Card, stop) -> tuple[float, float | None]:
    """Wait until the card is below :data:`COOL_TO_C` (at most
    :data:`COOL_MAX_S`): how long that took, and where it ended."""
    began = time.monotonic()
    value = card.degrees()
    while value is not None and value >= COOL_TO_C and not stop() and \
            time.monotonic() - began < COOL_MAX_S:
        time.sleep(10.0)
        value = card.degrees()
    return time.monotonic() - began, value


def card_tasks(python, folder: Path, sound: Path, work: Path) -> list:
    """The tasks of the card profile: ``(name, command)``, the lightest
    first, the three models together last - that one shows where the
    card ends."""
    import sys

    from . import separation
    from .separation_trial import KARAOKE_TRIO

    model = separation.ROFORMER_MODELS["vocals"]
    roformer = [str(python), str(separation.ROFORMER_SCRIPT), str(sound),
                str(work / "r"), str(folder), model]
    tasks = [("whisper", [sys.executable, "-c", _WHISPER_TASK, str(sound),
                          "float16"]),
             # v1.0.24 (B656): the smaller Whisper, half the memory.
             ("whisper_int8", [sys.executable, "-c", _WHISPER_TASK,
                               str(sound), "int8_float16"])]
    if (folder / model).exists():
        tasks += [("roformer", roformer),
                  ("roformer_small", roformer[:3] + [str(work / "s")]
                   + roformer[4:] + ["--segment", str(SMALL_SEGMENT)])]
    tasks.append(("demucs", [sys.executable, "-m", "demucs", "-n",
                             "htdemucs", "--segment", str(DEMUCS_SEGMENT),
                             "-o", str(work / "d"), str(sound)]))
    trio = KARAOKE_TRIO.split("+")
    if all((folder / name).exists() for name in trio):
        tasks.append(("trio", [str(python), str(separation.ROFORMER_SCRIPT),
                               str(sound), str(work / "t"), str(folder),
                               *trio, "--algorithm", "avg_wave"]))
    return tasks


def task_outcome(found: dict) -> str:
    """What the report says of a task (v1.0.24, B656): done, stopped at
    its time limit, or the error it ended on - the last line that says
    error, not the last line (on Pav that was a warning of onnxruntime,
    printed while the task was being stopped)."""
    if found.get("code") == 0:
        return t("check_ok")
    if found.get("timeout"):
        return t("check_profile_timeout")
    lines = [line.strip() for line in str(found.get("text", "")).splitlines()
             if line.strip()]
    errors = [line for line in lines
              if any(word in line for word in ("Error", "error:",
                                               "Exception", "FAILED"))]
    from . import separation

    return separation.last_line((errors or lines or ["-"])[-1])


def card_profile(python, folder: Path, stop) -> list[str]:
    """B645: what the card can take, and how hot each task makes it.

    First the card at rest, then every task on a minute of sound - Whisper
    large-v3, one Roformer model with its own pieces and with smaller
    ones, Demucs in shorter pieces, and the three karaoke models together
    - with the card read every few seconds: temperature, clocks, power,
    memory, load and what holds it back. After each task the card cools
    below 70 °C before the next, and how long that takes is noted too:
    so the rules for a small card (which tasks, and where they must slow
    down) come from numbers of this card."""
    card = _Card()
    lines = []
    rest = []
    began = time.monotonic()
    while time.monotonic() - began < REST_S and not stop():
        value = card.degrees()
        if value is not None:
            rest.append(value)
        time.sleep(LOAD_EVERY_S)
    lines.append(t("check_profile_rest").format(
        degrees=f"{min(rest):.0f}-{max(rest):.0f}" if rest else "-"))
    lines.append("")
    table = [t("check_profile_cols"),
             "| --- | --- | ---: | ---: | ---: | --- | ---: |"]
    details = []
    with tempfile.TemporaryDirectory(prefix="kt_profile_",
                                     ignore_cleanup_errors=True) as folder_:
        work = Path(folder_)
        sound = work / "load.wav"
        _test_sound(sound)
        for name, command in card_tasks(python, folder, sound, work):
            if stop():
                break
            found = _under_load(card, command, stop)
            cooled, end = _cool(card, stop)
            outcome = task_outcome(found)
            memory = ("-" if found["memory"] is None else
                      f"{found['memory']:.0f}/{found['total'] or 0:.0f}")
            hottest = "-" if found["hottest"] is None else \
                f"{found['hottest']:.0f}"
            warm = "" if end is None or end < COOL_TO_C else \
                " (" + t("check_profile_still_warm").format(
                    degrees=end) + ")"
            label = t(f"check_task_{name}")
            table.append(
                f"| {label} | {outcome[:80]} | {found['took']:.0f} | "
                f"{memory} | {hottest} | "
                f"{', '.join(found['reasons']) or '-'} | "
                f"{cooled:.0f}{warm} |")
            details += [f"**{label}**", ""]
            details += _block("\n".join("  ".join(row)
                                         for row in found["rows"]) or "-",
                              limit=20000)
            details.append("")
    lines += table + ["", t("check_profile_legend"), "",
                      t("check_load_columns"), ""] + details
    return lines


def run_round(job: dict, queue, stop) -> dict:
    """The check itself, on the helper."""
    from . import __version__, separation, work_queue

    home = Path(__file__).resolve().parents[2]      # ...Helper\app\modules
    lines = [f"## {t('check_title').format(host=work_queue.host_name())}", "",
             f"- {t('check_when')}: {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- {t('check_program')}: {__version__}, Python "
             f"{platform.python_version()}, {platform.platform()}",
             f"- {t('check_lane')}: {os.environ.get('KT_WHISPER_DEVICE', '-')}"
             f" / CUDA_VISIBLE_DEVICES="
             f"{os.environ.get('CUDA_VISIBLE_DEVICES', '-')}",
             f"- {t('check_cpu')}: {os.cpu_count()}; {t('check_memory')}: "
             f"{_memory()}", ""]
    lines += [f"### {t('check_workers')}", ""]
    card_busy = False
    here = work_queue.host_name().lower()
    mine = os.environ.get("KT_WHISPER_DEVICE", "")
    try:
        for status in queue.active_workers():
            if str(status.get("host", "")).lower() != here:
                continue
            lines.append(f"- {status.get('worker')}: "
                         f"{status.get('state')} - {status.get('job')}")
            # The card lane beside this one is working: its round has the
            # card, and a test on it could push that round out of memory.
            # v1.0.24: the lane that does card or processor rounds is one
            # lane - when it runs this check, its card is free.
            device = str(status.get("device", ""))
            if device.startswith("gpu") and device != "gpu-or-cpu" and \
                    status.get("state") == "working" and mine != "cuda":
                card_busy = True
    except OSError:
        pass
    lines += ["", "### nvidia-smi", ""]
    code, text, _took = _run(["nvidia-smi"], timeout=60)
    lines += _block(text if code >= 0 else t("check_no_driver"))
    lines += ["", f"### {t('check_card_test')}", ""]
    if card_busy:
        lines.append(t("check_card_busy"))
    if not card_busy:
        with tempfile.TemporaryDirectory(prefix="kt_check_") as folder:
            found = Path(folder) / "cuda.json"
            code, text, took = _run([sys.executable, "-m", "modules.cuda",
                                     "--write", str(found)],
                                    env=_card_free(), timeout=900)
            try:
                lines += _block(json.dumps(json.loads(found.read_text(
                    encoding="utf-8")), indent=1))
            except (OSError, ValueError):
                lines += _block(text)
    python = separation.roformer_python()
    lines += ["", f"### {t('check_roformer')}", ""]
    if python is None:
        lines.append(t("err_roformer_missing"))
    else:
        code, probe, _took = _run([str(python), "-c", _TORCH_PROBE],
                                  env=_card_free(), timeout=300)
        lines += _block(probe)
        folder = separation.roformer_models_dir()
        folder.mkdir(parents=True, exist_ok=True)
        model = separation.ROFORMER_MODELS["vocals"]
        command = [str(python), str(separation.ROFORMER_SCRIPT),
                   "--selftest", str(folder), model]
        lines += ["", f"### {t('check_trial')}", ""]
        processor = dict(_card_free(), CUDA_VISIBLE_DEVICES="-1")
        if not (folder / model).exists():
            # The first run fetches the model; that is no measure of speed.
            _run(command, env=processor, timeout=TRIAL_TIMEOUT_S * 3)
        trials = [(t("check_without_card"), processor)]
        if not card_busy:
            trials.insert(0, (t("check_with_card"), _card_free()))
        for label, env in trials:
            if stop():
                break
            code, text, took = _run(command, env=env,
                                    timeout=TRIAL_TIMEOUT_S)
            outcome = t("check_ok") if code == 0 else \
                separation.last_line(text)
            lines.append(f"- {label}: {took:.0f} s - {outcome}")
        lines += ["", f"### {t('check_load')}", ""]
        if card_busy:
            lines.append(t("check_card_busy"))
        elif not _card_seen(probe):
            lines.append(t("check_load_no_card"))
        elif not stop():
            lines += card_profile(python, folder, stop)
    lines += ["", f"### {t('check_logs')}", ""]
    logs = home / "logs"
    for lane in ("helper_gpu", "helper_cpu", "helper_mixed", "helper"):
        folder = logs / lane
        newest = sorted(folder.glob("*.log"))[-1:] if folder.is_dir() else []
        if newest:
            lines += [f"**{lane}** ({newest[0].name})", ""]
            lines += _block(_tail(newest[0]), limit=12000)
            lines.append("")
    return {"report": "\n".join(lines)}


def run(context, report, cancelled) -> str:
    """1.5.18 - check every helper that is there (or the ones named)."""
    from . import __version__, work_queue
    from .test_panel import Steps

    queue = work_queue.queue_for(context).ensure()
    # Helpers that are there now, on this version (an older one would
    # never take the check).
    hosts = sorted({str(status.get("host", "")) for status in
                    queue.active_workers()
                    if status.get("host")
                    and status.get("state") in ("waiting", "working",
                                                "cooling")
                    and status.get("version") == __version__
                    and not str(status.get("worker", "")).endswith(
                        work_queue.OWN_LANE)})
    if not hosts:
        return t("check_no_helpers")
    jobs = [check_job(host, __version__) for host in hosts]
    steps = Steps(report, "1.5.18", len(jobs))
    reports: dict[str, str] = {}
    folder_of = {job["id"]: job["for"] for job in jobs}

    def on_answer(answer: dict) -> None:
        host = folder_of.get(answer["job"]["id"])
        if host is None:
            return
        result = answer.get("result") or {}
        text = result.get("report") or str(result.get("failed", "-"))
        reports[host] = text
        target = context.paths.logs_dir / "helpers" / host
        try:
            target.mkdir(parents=True, exist_ok=True)
            (target / f"check_{time.strftime('%Y%m%d_%H%M%S')}.md"
             ).write_text(text, encoding="utf-8")
        except OSError:
            pass
        steps.tick()
        steps.name(f"1.5.18  {host}")

    began = time.monotonic()
    work_queue.run_jobs(queue, jobs, __version__, {JOB_KIND: run_round},
                        on_answer,
                        lambda: cancelled() or
                        time.monotonic() - began > WAIT_S,
                        local_accept=lambda job: False)
    lines = [t("check_intro").format(count=len(hosts)), ""]
    for host in hosts:
        lines += [reports.get(host, t("check_no_answer").format(host=host)),
                  ""]
    return "\n".join(lines)
