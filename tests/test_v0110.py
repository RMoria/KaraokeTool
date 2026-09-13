"""Tests voor v0.110.0: B353, B354 en de tijdelijke knop 1.5.

B353 - de gemaakte video wordt niet meer ongeldig verklaard doordat er
       iets bovenstrooms verandert.
B354 - bij het renderen wordt gevraagd wat er met een bestaande video
       moet gebeuren; "naast elkaar bewaren" nummert de NIEUWE.
1.5  - tijdelijke knop die het transcriptiecachebestand terugzet zonder
       iets weg te gooien.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import dependencies as deps  # noqa: E402
from modules import pipeline  # noqa: E402
from modules.config import default_config  # noqa: E402
from modules.filesystem import (ProjectPaths, ProjectStore,  # noqa: E402
                                ensure_directories)


def _context(tmp_path: Path, naam: str = "Proef"):
    paths = ProjectPaths(root=tmp_path, song=naam)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B353: de video blijft
# --------------------------------------------------------------------------

def test_video_hangt_nergens_meer_onder() -> None:
    assert not deps.ARTEFACTS["video"].sources


def test_nieuwe_transcriptie_laat_de_video_staan() -> None:
    """Alles eronder vervalt, de video niet."""
    steps, _metas, files = deps.invalidation_plan(
        ["whisper_original"], (), include_changed=False)
    assert "timing" in steps and "coupling" in steps   # die wel
    assert "video" not in steps
    assert not any("video" in f for f in files)


def test_ook_een_timingwijziging_laat_de_video_staan() -> None:
    steps, _metas, _files = deps.invalidation_plan(
        ["timing"], (), include_changed=False)
    assert "video" not in steps


# --------------------------------------------------------------------------
# B354: vragen in plaats van overschrijven
# --------------------------------------------------------------------------

def test_bestandsnaam_van_de_render(tmp_path) -> None:
    context = _context(tmp_path, "Biertje")
    context.store.set_meta("display_name", "Lied C")
    doel = pipeline.video_target(context)
    assert doel.name == "Lied C.mp4"
    assert doel.parent == context.paths.output_dir


def test_andere_combinatie_krijgt_zijn_eigen_naam(tmp_path) -> None:
    """B271 blijft staan: een afwijkende render botst niet met de gewone."""
    context = _context(tmp_path, "Biertje")
    context.store.set_meta("display_name", "Biertje")
    gewoon = pipeline.video_target(context, "karaoke", "karaoke")
    anders = pipeline.video_target(context, "origineel", "vocals")
    assert gewoon != anders


def test_volgnummer_gaat_naar_de_nieuwe(tmp_path) -> None:
    """De bestaande video wordt nooit aangeraakt."""
    bestaand = tmp_path / "Biertje.mp4"
    bestaand.write_bytes(b"oud")
    volgende = pipeline.next_video_target(bestaand)
    assert volgende.name == "Biertje_2.mp4"
    assert bestaand.read_bytes() == b"oud"
    volgende.write_bytes(b"nieuw")
    assert pipeline.next_video_target(bestaand).name == "Biertje_3.mp4"


def test_render_gebruikt_het_doel_van_de_aanroeper() -> None:
    """De GUI geeft het gekozen pad door; run_video moet dat volgen."""
    import inspect

    handtekening = inspect.signature(pipeline.run_video)
    assert "target" in handtekening.parameters
    bron = inspect.getsource(pipeline.run_video)
    assert "if target is None:" in bron


def test_gui_vraagt_voordat_hij_overschrijft() -> None:
    from modules import gui

    bron = __import__("inspect").getsource(gui.MainWindow._do_render_video)
    assert "video_target" in bron and "_ask_video_exists" in bron


# --------------------------------------------------------------------------
# 1.5: de cache terugzetten zonder iets weg te gooien
# --------------------------------------------------------------------------

def _project(root: Path, naam: str, *, step: bool, cache: bool,
             audio: bool = True) -> None:
    paths = ProjectPaths(root=root, song=naam)
    ensure_directories(paths)
    if audio:
        (paths.input_dir / "original.mp3").write_bytes(b"x")
    store = ProjectStore(paths.project_file)
    if step:
        store.set_step("whisper_original", {"language": "nl"})
    else:
        store.set_meta("display_name", naam)
    if cache:
        (paths.cache_dir / "transcription_original.json").write_text(
            "[]", encoding="utf-8")


def test_alleen_projecten_met_een_gat_worden_genoemd(tmp_path) -> None:
    _project(tmp_path, "MetCache", step=True, cache=True)
    _project(tmp_path, "ZonderCache", step=True, cache=False)
    _project(tmp_path, "NooitGedraaid", step=False, cache=False)
    _project(tmp_path, "GeenAudio", step=True, cache=False, audio=False)
    context = _context(tmp_path, "MetCache")
    assert pipeline.projects_without_cache(context) == ["ZonderCache"]


def test_zusjecontext_wijst_naar_het_andere_project(tmp_path) -> None:
    _project(tmp_path, "Eerste", step=True, cache=True)
    _project(tmp_path, "Tweede", step=True, cache=False)
    context = _context(tmp_path, "Eerste")
    ander = pipeline.context_for_project(context, "Tweede")
    assert ander.paths.song == "Tweede"
    assert ander.config.song.title == "Tweede"
    assert ander.paths.root == context.paths.root


def test_bestaande_cache_wordt_met_rust_gelaten(tmp_path) -> None:
    _project(tmp_path, "MetCache", step=True, cache=True)
    context = _context(tmp_path, "MetCache")
    assert pipeline.fill_transcription_cache(context) is False


def test_cache_vullen_gooit_niets_weg() -> None:
    """De hele reden van bestaan: geen stapadministratie, geen opruiming."""
    import inspect

    bron = inspect.getsource(pipeline.fill_transcription_cache)
    assert "set_step" not in bron
    assert "invalidate" not in bron
    assert "save_segments" in bron


def test_knop_staat_op_tab_1(qapp=None, tmp_path=None) -> None:
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    import tempfile

    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from modules import gui
    from modules.translations import t

    with tempfile.TemporaryDirectory() as tmp:
        window = gui.MainWindow(_context(Path(tmp), "Proef"))
        namen = [b.text() for b in window._step_buttons]
    assert t("step_fill_cache") in namen
    assert namen[0].startswith("1.1.") and namen[-1].startswith("1.5.")


def test_cache_vullen_geeft_een_aanroepbare_afbreekvraag(tmp_path,
                                                         monkeypatch) -> None:
    """De gemelde fout: 'Event' object is not callable.

    ``whisper.transcribe`` wil een functie die ``True`` teruggeeft als er
    moet worden gestopt, geen ``threading.Event``.
    """
    import threading

    from modules import whisper as whisper_module

    _project(tmp_path, "Zonder", step=True, cache=False)
    context = pipeline.context_for_project(_context(tmp_path, "Zonder"),
                                           "Zonder")
    gezien = {}

    def nep_transcribe(wav, settings, output_dir, progress=None,
                       language_override=None, cancelled=None,
                       initial_prompt=""):
        gezien["cancelled"] = cancelled
        return ()

    monkeypatch.setattr(pipeline, "prepare_track",
                        lambda ctx, track: tmp_path / "vocals.wav")
    monkeypatch.setattr(pipeline, "_demucs_enabled", lambda ctx: False)
    monkeypatch.setattr(whisper_module, "transcribe", nep_transcribe)
    monkeypatch.setattr(pipeline.word_alignment, "is_available",
                        lambda: False)

    stop = threading.Event()
    assert pipeline.fill_transcription_cache(
        context, cancelled=stop.is_set) is True
    assert callable(gezien["cancelled"])
    assert gezien["cancelled"]() is False
    stop.set()
    assert gezien["cancelled"]() is True


def test_knop_geeft_de_functie_door_en_niet_het_event() -> None:
    """Precies de fout die de gebruiker meldde, vastgelegd.

    Het cache vullen verhuisde naar 1.5.1 in het testpaneel; de eis is
    dezelfde gebleven - wat er wordt doorgegeven moet aanroepbaar zijn.
    """
    import inspect

    from modules import gui, test_panel

    bron = inspect.getsource(test_panel.fill_cache)
    assert "cancelled=cancelled" in bron
    paneel = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "cancel.is_set" in paneel


def test_er_lopen_er_twee_tegelijk_en_een_fout_stopt_de_rest_niet() -> None:
    """Sinds B357 doet de gedeelde verdeler dat voor alle acties."""
    import inspect

    from modules import test_panel

    verdeler = inspect.getsource(test_panel.across_projects)
    # B396: het aantal werkplekken is een argument geworden (twee voor
    # puur Python, meer voor Whisper-werk dat de GIL loslaat).
    assert "range(max(1, int(slots)))" in verdeler
    assert "never stops the rest" in verdeler
    assert "across_projects" in inspect.getsource(test_panel.fill_cache)


def test_projecten_met_handmatige_timing_gaan_voor(tmp_path) -> None:
    """Stop je halverwege, dan zijn de nuttige projecten klaar."""
    _project(tmp_path, "Aaa_zonder_timing", step=True, cache=False)
    _project(tmp_path, "Zzz_met_timing", step=True, cache=False)
    paden = ProjectPaths(root=tmp_path, song="Zzz_met_timing")
    paden.timing_file.write_text("{}", encoding="utf-8")
    context = _context(tmp_path, "Aaa_zonder_timing")
    assert pipeline.projects_without_cache(context)[0] == "Zzz_met_timing"
