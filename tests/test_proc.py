"""Tests for modules.proc (starting subprocesses windowless, B89)."""

from __future__ import annotations

import subprocess

from modules import proc


def test_no_window_kwargs_empty_off_windows(monkeypatch) -> None:
    """Off Windows the helper returns an empty dict (unchanged behaviour)."""
    monkeypatch.setattr(proc.sys, "platform", "linux")
    assert proc.no_window_kwargs() == {}


def test_no_window_kwargs_sets_the_flag_on_windows(monkeypatch) -> None:
    """On Windows: the CREATE_NO_WINDOW flag + a hidden STARTUPINFO."""
    monkeypatch.setattr(proc.sys, "platform", "win32")
    # STARTUPINFO and the flags only truly exist on Windows; simulate them.
    monkeypatch.setattr(subprocess, "STARTUPINFO", lambda: type(
        "S", (), {"dwFlags": 0, "wShowWindow": 0})(), raising=False)
    monkeypatch.setattr(subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(proc, "_CREATE_NO_WINDOW", 0x08000000, raising=False)
    kwargs = proc.no_window_kwargs()
    assert kwargs["creationflags"] == 0x08000000
    assert "startupinfo" in kwargs


def test_windowless_python_picks_pythonw(monkeypatch, tmp_path) -> None:
    """On Windows python.exe is replaced by pythonw.exe when present."""
    python = tmp_path / "python.exe"
    python.write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    monkeypatch.setattr(proc.sys, "platform", "win32")
    monkeypatch.setattr(proc.sys, "executable", str(python))
    assert proc.windowless_python().endswith("pythonw.exe")


def test_windowless_python_falls_back_without_pythonw(monkeypatch,
                                                      tmp_path) -> None:
    """Without pythonw.exe it falls back to the ordinary interpreter."""
    python = tmp_path / "python.exe"
    python.write_text("")
    monkeypatch.setattr(proc.sys, "platform", "win32")
    monkeypatch.setattr(proc.sys, "executable", str(python))
    assert proc.windowless_python() == str(python)


def test_windowless_python_unchanged_off_windows(monkeypatch) -> None:
    """Off Windows sys.executable stays unchanged."""
    monkeypatch.setattr(proc.sys, "platform", "linux")
    monkeypatch.setattr(proc.sys, "executable", "/usr/bin/python3")
    assert proc.windowless_python() == "/usr/bin/python3"


def test_ffmpeg_goes_through_the_one_door(monkeypatch) -> None:
    """ffmpeg._run goes through proc.run (B89/B356).

    Since B356 proc.run is the only place where an external program
    starts: that is where the no-window kwargs are set AND where the
    process is registered, so that Stop can kill it.
    """
    from modules import ffmpeg

    seen: dict = {}

    def fake_run(command, **kwargs):
        seen["command"] = list(command)

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    monkeypatch.setattr(ffmpeg.proc, "run", fake_run)
    ffmpeg._run(["ffprobe", "-version"])
    assert seen["command"] == ["ffprobe", "-version"]


def test_proc_run_hides_the_window_and_registers(monkeypatch) -> None:
    """The one door sets the flags and tracks what runs (B89/B356)."""
    from modules import proc

    seen: dict = {}

    class _Process:
        returncode = 0

        def communicate(self, timeout=None):
            seen["was_running"] = list(proc._RUNNING)
            return ("", "")

    def fake_popen(command, **kwargs):
        seen["kwargs"] = kwargs
        return _Process()

    monkeypatch.setattr(proc.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(proc, "no_window_kwargs",
                        lambda: {"creationflags": 0x08000000})
    proc.run(["ffprobe", "-version"])
    assert seen["kwargs"].get("creationflags") == 0x08000000
    assert len(seen["was_running"]) == 1        # it was registered
    assert not proc._RUNNING                    # and cleaned up again


def test_terminate_all_kills_what_is_running(monkeypatch) -> None:
    """Stop has to be able to really stop Demucs (B356)."""
    from modules import proc

    killed = []

    class _Process:
        def kill(self):
            killed.append(self)

    process = _Process()
    proc._RUNNING.add(process)
    try:
        assert proc.terminate_all() == 1
        assert killed == [process]
    finally:
        proc._RUNNING.discard(process)


def test_separation_uses_the_windowless_interpreter(monkeypatch,
                                                    tmp_path) -> None:
    """B89/B356: Demucs starts with the windowless interpreter."""
    from modules import separation

    seen: dict = {}

    def fake_run(command, **kwargs):
        seen["command"] = list(command)

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    monkeypatch.setattr(separation, "is_available", lambda: True)
    monkeypatch.setattr(separation.proc, "windowless_python",
                        lambda: "pythonw.exe")
    monkeypatch.setattr(separation.proc, "run", fake_run)
    # Without real stems separate raises a SeparationError after the call.
    try:
        separation.separate(tmp_path / "in.wav", tmp_path / "werk")
    except separation.SeparationError:
        pass
    assert seen["command"][0] == "pythonw.exe"


def test_no_bare_subprocess_calls() -> None:
    """Everything belongs through the one door (B356).

    A bare ``subprocess.run`` gets two things wrong: on Windows a cmd
    window flashes, and the process does not listen to Stop. That is
    exactly how the pop-ups at 1.5.7 and the slow Stop came about.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for folder in ("modules", "tools"):
        for path in sorted((root / folder).glob("*.py")):
            if path.name == "proc.py":
                continue          # that one IS the door
            text = path.read_text(encoding="utf-8")
            for hit in re.finditer(r"subprocess\.(run|Popen|check_output)\s*\(",
                                   text):
                line = text[:hit.start()].count("\n") + 1
                tail = text[hit.start():hit.start() + 400]
                if "no_window_kwargs" in tail:
                    continue      # allowed: sets the flags itself
                offenders.append(f"{path.name}:{line}")
    assert not offenders, ("bare subprocess call (has to go through "
                           "proc.run): " + ", ".join(offenders))
