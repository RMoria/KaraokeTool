"""Tests voor modules.proc (vensterloos starten van subprocessen, B89)."""

from __future__ import annotations

import subprocess

from modules import proc


def test_no_window_kwargs_leeg_op_niet_windows(monkeypatch) -> None:
    """Op niet-Windows geeft de helper een lege dict (ongewijzigd gedrag)."""
    monkeypatch.setattr(proc.sys, "platform", "linux")
    assert proc.no_window_kwargs() == {}


def test_no_window_kwargs_zet_vlag_op_windows(monkeypatch) -> None:
    """Op Windows staat de CREATE_NO_WINDOW-vlag + verborgen STARTUPINFO erin."""
    monkeypatch.setattr(proc.sys, "platform", "win32")
    # STARTUPINFO/vlaggen bestaan alleen echt op Windows; simuleer ze.
    monkeypatch.setattr(subprocess, "STARTUPINFO", lambda: type(
        "S", (), {"dwFlags": 0, "wShowWindow": 0})(), raising=False)
    monkeypatch.setattr(subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(proc, "_CREATE_NO_WINDOW", 0x08000000, raising=False)
    kwargs = proc.no_window_kwargs()
    assert kwargs["creationflags"] == 0x08000000
    assert "startupinfo" in kwargs


def test_windowless_python_kiest_pythonw(monkeypatch, tmp_path) -> None:
    """Op Windows wordt python.exe vervangen door pythonw.exe indien aanwezig."""
    python = tmp_path / "python.exe"
    python.write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    monkeypatch.setattr(proc.sys, "platform", "win32")
    monkeypatch.setattr(proc.sys, "executable", str(python))
    assert proc.windowless_python().endswith("pythonw.exe")


def test_windowless_python_terugval_zonder_pythonw(monkeypatch,
                                                   tmp_path) -> None:
    """Zonder pythonw.exe valt het terug op de gewone interpreter."""
    python = tmp_path / "python.exe"
    python.write_text("")
    monkeypatch.setattr(proc.sys, "platform", "win32")
    monkeypatch.setattr(proc.sys, "executable", str(python))
    assert proc.windowless_python() == str(python)


def test_windowless_python_ongewijzigd_op_niet_windows(monkeypatch) -> None:
    """Op niet-Windows blijft sys.executable ongewijzigd."""
    monkeypatch.setattr(proc.sys, "platform", "linux")
    monkeypatch.setattr(proc.sys, "executable", "/usr/bin/python3")
    assert proc.windowless_python() == "/usr/bin/python3"


def test_ffmpeg_loopt_door_de_ene_deur(monkeypatch) -> None:
    """ffmpeg._run gaat via proc.run (B89/B356).

    Sinds B356 is proc.run de enige plek waar een extern programma
    start: daar worden de no-window-kwargs gezet EN wordt het proces
    geregistreerd, zodat Stop het kan afschieten.
    """
    from modules import ffmpeg

    gezien: dict = {}

    def nep_run(command, **kwargs):
        gezien["command"] = list(command)

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    monkeypatch.setattr(ffmpeg.proc, "run", nep_run)
    ffmpeg._run(["ffprobe", "-version"])
    assert gezien["command"] == ["ffprobe", "-version"]


def test_proc_run_verbergt_het_venster_en_registreert(monkeypatch) -> None:
    """De ene deur zet de vlaggen en houdt bij wat er loopt (B89/B356)."""
    from modules import proc

    gezien: dict = {}

    class _Proces:
        returncode = 0

        def communicate(self, timeout=None):
            gezien["draaide"] = list(proc._RUNNING)
            return ("", "")

    def nep_popen(command, **kwargs):
        gezien["kwargs"] = kwargs
        return _Proces()

    monkeypatch.setattr(proc.subprocess, "Popen", nep_popen)
    monkeypatch.setattr(proc, "no_window_kwargs",
                        lambda: {"creationflags": 0x08000000})
    proc.run(["ffprobe", "-version"])
    assert gezien["kwargs"].get("creationflags") == 0x08000000
    assert len(gezien["draaide"]) == 1          # stond geregistreerd
    assert not proc._RUNNING                    # en is weer opgeruimd


def test_terminate_all_schiet_af_wat_er_loopt(monkeypatch) -> None:
    """Stop moet Demucs echt kunnen stoppen (B356)."""
    from modules import proc

    gedood = []

    class _Proces:
        def kill(self):
            gedood.append(self)

    proces = _Proces()
    proc._RUNNING.add(proces)
    try:
        assert proc.terminate_all() == 1
        assert gedood == [proces]
    finally:
        proc._RUNNING.discard(proces)


def test_scheiding_gebruikt_vensterloze_interpreter(monkeypatch,
                                                    tmp_path) -> None:
    """Demucs start met de vensterloze interpreter via proc.run (B89/B356)."""
    from modules import separation

    gezien: dict = {}

    def nep_run(command, **kwargs):
        gezien["command"] = list(command)

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    monkeypatch.setattr(separation, "is_available", lambda: True)
    monkeypatch.setattr(separation.proc, "windowless_python",
                        lambda: "pythonw.exe")
    monkeypatch.setattr(separation.proc, "run", nep_run)
    # Zonder echte stems geeft separate een SeparationError ná de aanroep.
    try:
        separation.separate(tmp_path / "in.wav", tmp_path / "werk")
    except separation.SeparationError:
        pass
    assert gezien["command"][0] == "pythonw.exe"


def test_geen_kale_subprocess_aanroepen() -> None:
    """Alles hoort door de ene deur (B356).

    Een kale ``subprocess.run`` doet twee dingen fout: op Windows
    knippert er een cmd-venster, en het proces luistert niet naar Stop.
    Precies zo ontstonden de pop-ups bij 1.5.7 en de trage Stop.
    """
    import re
    from pathlib import Path

    wortel = Path(__file__).resolve().parents[1]
    fouten = []
    for map_ in ("modules", "tools"):
        for pad in sorted((wortel / map_).glob("*.py")):
            if pad.name == "proc.py":
                continue          # dat IS de deur
            tekst = pad.read_text(encoding="utf-8")
            for treffer in re.finditer(r"subprocess\.(run|Popen|check_output)\s*\(",
                                       tekst):
                regel = tekst[:treffer.start()].count("\n") + 1
                staart = tekst[treffer.start():treffer.start() + 400]
                if "no_window_kwargs" in staart:
                    continue      # mag: zet de vlaggen zelf
                fouten.append(f"{pad.name}:{regel}")
    assert not fouten, ("kale subprocess-aanroep (moet via proc.run): "
                        + ", ".join(fouten))
