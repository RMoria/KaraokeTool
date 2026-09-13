"""Tests for v0.149.0.

B530 the picture was shifted forward for the intro and the sound was
not, so three finished videos ran up to 8.3 s out of step; B531 one
action that makes every video again; B532 collecting and copying the
finished work from tab 2.
"""

from __future__ import annotations

import os
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import ffmpeg as ffmpeg_module          # noqa: E402
from modules import video                            # noqa: E402
from modules import timing                           # noqa: E402


# --------------------------------------------------------------------------
# B530 - the silence in front of the sound
# --------------------------------------------------------------------------

def test_de_vertraging_noemt_de_kanaalindeling() -> None:
    """The user's karaoke.wav files carry channel_layout=unknown, and a
    delay has nothing to bind to without a layout."""
    filter_text = ffmpeg_module.delay_filter(6.215, channels=2)
    assert filter_text.startswith("aformat=channel_layouts=stereo,")
    assert "adelay=6215|6215" in filter_text
    assert ffmpeg_module.delay_filter(1.0, channels=1).startswith(
        "aformat=channel_layouts=mono,")


def test_de_vertraging_geldt_voor_elk_kanaal_apart() -> None:
    """Per channel and not "all": then the filter never has to work out
    how many channels "all" means."""
    assert ffmpeg_module.delay_filter(1.0, channels=1).endswith(
        "adelay=1000")
    assert ffmpeg_module.delay_filter(1.0, channels=2).endswith(
        "adelay=1000|1000")
    # Something exotic gets no layout imposed on it, only the delays.
    assert ffmpeg_module.delay_filter(1.0, channels=6) == \
        "adelay=1000|1000|1000|1000|1000|1000"


def test_de_vertraging_rondt_af_op_hele_milliseconden() -> None:
    assert "adelay=500|500" in ffmpeg_module.delay_filter(0.4999)
    assert "adelay=6215|6215" in ffmpeg_module.delay_filter(6.2149)


def _lines(first_start: float, count: int = 6):
    out = []
    for i in range(count):
        start = first_start + i * 4.0
        out.append(timing.TimedLine(
            index=i, text=f"regel {i} een twee", crowd=False, block=0,
            quality="high",
            syllables=(timing.Syllable("re", start, start + 1.0),
                       timing.Syllable(" gel", start + 1.0, start + 2.0))))
    return tuple(out)


def _capture(monkeypatch, tmp_path, lines, silence=None, target_name="uit",
             loudness=None):
    """Run the renderer with a stub ffmpeg and give back its command.

    Small picture and few frames on purpose: this is about the command
    and the check around it, not about drawing.
    """
    seen = {}

    class Stub:
        def __init__(self, command, **kwargs):
            seen["command"] = command
            # The real ffmpeg writes the scratch file; the stub has to do
            # that too, otherwise the move afterwards has nothing to move.
            Path(command[-1]).write_bytes(b"video")
            self.stdin = open(os.devnull, "wb")
            self.stderr = open(os.devnull, "rb")
            self.returncode = 0

        def wait(self, *a, **k):
            return 0

    monkeypatch.setattr(video, "subprocess",
                        types.SimpleNamespace(Popen=Stub, PIPE=-1))
    monkeypatch.setattr(video.ffmpeg_module, "find_executable",
                        lambda name: "/bin/true")
    monkeypatch.setattr(video.ffmpeg_module, "probe",
                        lambda p: types.SimpleNamespace(duration=30.0,
                                                        channels=2))
    monkeypatch.setattr(video.ffmpeg_module, "measure_loudness",
                        lambda *a, **k: loudness)
    monkeypatch.setattr(video.ffmpeg_module, "leading_silence",
                        lambda p, look=30.0: silence)
    logo = tmp_path / "logo.png"
    from PIL import Image
    Image.new("RGBA", (16, 16), (0, 180, 0, 255)).save(logo)
    target = tmp_path / f"{target_name}.mp4"
    try:
        video.render_video(lines, tmp_path / "audio.wav", logo, "Titel",
                           target, width=160, height=90, fps=5,
                           loudness_lufs=(-16.0 if loudness else None))
    except video.VideoError as exc:
        seen["error"] = str(exc)
    seen["target"] = target
    return seen


def _audio_filter(command) -> str:
    return command[command.index("-af") + 1]


def test_de_vertraging_staat_voor_de_niveauregeling(monkeypatch,
                                                    tmp_path) -> None:
    """B530: loudnorm rebuilds its filter graph part-way through, and
    everything behind it is rebuilt with it. Silence that is already in
    the stream by then cannot be lost."""
    from modules.ffmpeg import Loudness
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=6.215,
                    loudness=Loudness(integrated=-14.6, true_peak=-0.1,
                                      lra=11.3, threshold=-24.9))
    chain = _audio_filter(seen["command"])
    assert chain.startswith("aformat=channel_layouts=stereo,adelay=6215")
    assert chain.index("adelay=") < chain.index("loudnorm=")
    assert chain.endswith(",apad")


def test_zonder_aanloop_geen_vertraging(monkeypatch, tmp_path) -> None:
    """A song whose first line starts after ten seconds needs nothing."""
    seen = _capture(monkeypatch, tmp_path, _lines(14.7), silence=0.0)
    assert _audio_filter(seen["command"]) == "apad"


def test_de_render_weigert_als_de_stilte_niet_klopt(monkeypatch,
                                                    tmp_path) -> None:
    """The heart of B530: a video that runs out of step is not written."""
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=0.0)
    assert "error" in seen
    assert "6.21" in seen["error"] and "0.0" in seen["error"]
    assert not seen["target"].exists()


def test_de_render_gaat_door_als_de_stilte_wel_klopt(monkeypatch,
                                                     tmp_path) -> None:
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=6.215)
    assert "error" not in seen, seen.get("error")


def test_een_onmeetbare_stilte_stopt_de_render_niet(monkeypatch,
                                                    tmp_path) -> None:
    """A check that cannot run may not block a render that is probably
    fine - but it does say so."""
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=None)
    assert "error" not in seen, seen.get("error")


def test_meer_stilte_dan_de_aanloop_is_geen_fout(monkeypatch,
                                                 tmp_path) -> None:
    """De gemeten stilte is de aanloop PLUS de eigen stilte van het
    nummer - die twee grenzen aan elkaar en de meter ziet er één. Op de
    eigen verzameling liep dat verschil van 0,2 tot 0,4 s op, en al die
    renders waren goed. Tweezijdig toetsen zou juist die weigeren."""
    assert video.LEAD_SILENCE_SLACK_S == pytest.approx(0.10)
    for extra, naam in ((0.28, "kort"), (0.45, "ruim"), (5.0, "heel_lang")):
        seen = _capture(monkeypatch, tmp_path, _lines(3.785),
                        silence=6.215 + extra, target_name=naam)
        assert "error" not in seen, (extra, seen.get("error"))


def test_te_weinig_stilte_is_wel_een_fout(monkeypatch, tmp_path) -> None:
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=6.15,
                    target_name="net_goed")
    assert "error" not in seen, seen.get("error")
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=5.9,
                    target_name="te_weinig")
    assert "error" in seen


def _stub_run(monkeypatch, uitvoer: str, code: int = 0) -> None:
    monkeypatch.setattr(ffmpeg_module.proc, "run",
                        lambda *a, **k: types.SimpleNamespace(
                            stderr=uitvoer, stdout="", returncode=code))


def test_de_stiltemeting_leest_het_begin(monkeypatch) -> None:
    """Only a silence that starts at the beginning counts."""
    uitvoer = ("[silencedetect] silence_start: 0\n"
               "[silencedetect] silence_end: 6.215 | silence_duration: 6.215\n"
               "[silencedetect] silence_start: 50.1\n")
    _stub_run(monkeypatch, uitvoer)
    assert ffmpeg_module.leading_silence(Path("x.mp4")) == pytest.approx(6.215)


def test_geluid_dat_meteen_begint_meet_nul(monkeypatch) -> None:
    _stub_run(monkeypatch, "niets bijzonders\n")
    assert ffmpeg_module.leading_silence(Path("x.mp4")) == 0.0


def test_stilte_die_pas_later_begint_meet_nul(monkeypatch) -> None:
    """Een pauze midden in het nummer zegt niets over het begin - en
    "niet gemeten" antwoorden zou de controle laten wegkijken bij precies
    het gebrek dat hij moet vangen."""
    uitvoer = ("[silencedetect] silence_start: 12.5\n"
               "[silencedetect] silence_end: 19.0 | silence_duration: 6.5\n")
    _stub_run(monkeypatch, uitvoer)
    assert ffmpeg_module.leading_silence(Path("x.mp4")) == 0.0


def test_een_onleesbaar_bestand_meet_niets(monkeypatch) -> None:
    """Nul seconden stilte is een bewering, en de aanroeper weigert een
    render op die bewering."""
    _stub_run(monkeypatch, "No such file or directory\n", code=1)
    assert ffmpeg_module.leading_silence(Path("weg.mp4")) is None


def test_een_stilte_zonder_einde_meet_niets(monkeypatch) -> None:
    _stub_run(monkeypatch, "[silencedetect] silence_start: 0\n")
    assert ffmpeg_module.leading_silence(Path("x.mp4")) is None


# --------------------------------------------------------------------------
# B531 - 1.5.12: every video again
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_de_klus_staat_achteraan_en_is_geen_meting() -> None:
    from modules import test_panel
    codes = [a.code for a in test_panel.ACTIONS]
    assert codes[-1] == "1.5.12"
    actie = test_panel.ACTIONS[-1]
    assert actie.on_request and not actie.heavy
    assert actie.function is test_panel.rebuild_videos


def test_de_klus_liftt_nooit_mee_op_alles(qapp) -> None:
    """Alle video's opnieuw maken overschrijft afgemaakt werk; dat doe je
    met opzet en niet met één vinkje."""
    from modules import test_panel
    paneel = test_panel.TestPanel()
    paneel._toggle_all()
    assert "1.5.12" not in [a.code for a in paneel.chosen()]
    assert all(not a.on_request for a in paneel.chosen())


def test_de_klus_is_wel_los_aan_te_vinken(qapp) -> None:
    from modules import test_panel
    paneel = test_panel.TestPanel()
    plek = [n for n, a in enumerate(paneel._actions) if a.on_request]
    assert plek, "1.5.12 hoort zichtbaar te zijn"
    paneel._ticks[plek[0]].setChecked(True)
    assert [a.code for a in paneel.chosen()] == ["1.5.12"]


def test_de_klus_telt_niet_mee_voor_het_plafond() -> None:
    from modules import test_panel
    metingen = [a for a in test_panel.ACTIONS
                if not a.heavy and not a.on_request]
    assert len(metingen) <= test_panel.MAX_ACTIONS == 10


def test_de_oude_videos_gaan_naast_de_programmamap(tmp_path) -> None:
    """B531: in de map die de gebruiker zelf leeggooit, niet in de
    programmamap - daar zouden ze vervuiling zijn."""
    from modules import test_panel
    from modules.config import default_config
    from modules.filesystem import ProjectPaths, ProjectStore
    root = tmp_path / "KaraokeTool"
    root.mkdir()
    paths = ProjectPaths(root=root)
    context = test_panel.pipeline.AppContext(
        paths=paths, config=default_config(),
        store=ProjectStore(paths.project_file))
    folder = test_panel._old_videos_folder(context, "Een_Lied")
    assert folder == tmp_path / "_to_delete" / "oude_videos" / "Een_Lied"


def test_de_klus_rendert_eerst_en_ruimt_daarna_op() -> None:
    """De volgorde is de hele veiligheid: een mislukte render mag nooit
    een afgemaakte video kosten."""
    import inspect
    from modules import test_panel
    source = inspect.getsource(test_panel.rebuild_videos)
    assert source.index("run_video") < source.index("shutil.move")
    assert "next_video_target" in source
    # En de oude video mag alleen overschreven worden als hij echt weg is.
    assert "if plain in kept:" in source


# --------------------------------------------------------------------------
# B532 - collecting and copying
# --------------------------------------------------------------------------

def _project(root: Path, song: str, video: bool = True, title: str = ""):
    """A project on disk, with its videos named the way the app names
    them - ``video_target`` works the title out, not the folder name."""
    from dataclasses import replace as _replace
    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)
    paths = ProjectPaths(root=root, song=song)
    ensure_directories(paths)
    paths.project_file.write_text('{"created": "", "steps": {}}',
                                  encoding="utf-8")
    (paths.input_dir / "songtekst.txt").write_text("een", encoding="utf-8")
    (paths.input_dir / "karaoketekst.txt").write_text("twee", encoding="utf-8")
    (paths.input_dir / "original.mp3").write_bytes(b"geluid")
    config = default_config()
    config = _replace(config, song=_replace(config.song, title=song))
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))
    if title:
        context.store.set_meta("video_titles", {"karaoke_title": title})
        context = pipeline.apply_project_titles(context)
    plain = pipeline.video_target(context)
    if video:
        plain.write_bytes(b"film")
        pipeline.next_video_target(plain).write_bytes(b"nieuwere film")
    return context


def test_alleen_projecten_met_een_video_tellen(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Met_Video")
    _project(tmp_path, "Zonder_Video", video=False)
    assert pipeline.projects_with_video(context) == ["Met_Video"]


def test_alleen_de_videos_komen_plat_in_de_map(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    doel = tmp_path / "uit"
    projects, files = pipeline.collect_videos(context, doel,
                                              with_sources=False)
    assert (projects, files) == (1, 1)
    assert [p.name for p in sorted(doel.iterdir())] == ["Een Lied_2.mp4"]


def test_de_verzameling_krijgt_een_map_per_project(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    _project(tmp_path, "Twee_Lied")
    doel = tmp_path / "uit"
    projects, files = pipeline.collect_videos(context, doel,
                                              with_sources=True)
    assert projects == 2 and files == 8
    namen = sorted(p.name for p in (doel / "Een_Lied").iterdir())
    assert namen == ["Een Lied_2.mp4", "karaoketekst.txt", "original.mp3",
                     "songtekst.txt"]


def test_de_nieuwste_render_gaat_mee(tmp_path) -> None:
    """Hoogste volgnummer, niet de nieuwste naam - _10 komt na _3."""
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    (context.paths.output_dir / "Een Lied_10.mp4").write_bytes(b"nieuwste")
    doel = tmp_path / "uit"
    pipeline.collect_videos(context, doel, with_sources=False)
    assert (doel / "Een Lied_10.mp4").exists()
    assert not (doel / "Een Lied_2.mp4").exists()


def test_de_knop_staat_uit_zonder_video(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Zonder", video=False)
    assert pipeline.projects_with_video(context) == []
    doel = tmp_path / "uit"
    assert pipeline.collect_videos(context, doel, with_sources=True) == (0, 0)


def test_twee_projecten_met_dezelfde_titel_overschrijven_elkaar_niet(
        tmp_path) -> None:
    """De titel komt uit de instellingen en niet uit de mapnaam, dus twee
    projecten kunnen dezelfde videonaam hebben. Stil overschrijven zou de
    eerste kosten en de telling tot een leugen maken."""
    from modules import pipeline
    context = _project(tmp_path, "Opname_1", title="Mijn Lied")
    _project(tmp_path, "Opname_2", title="Mijn Lied")
    doel = tmp_path / "uit"
    projects, files = pipeline.collect_videos(context, doel,
                                              with_sources=False)
    assert (projects, files) == (2, 2)
    assert len(list(doel.iterdir())) == 2


def test_de_andere_rendervariant_gaat_niet_mee(tmp_path) -> None:
    """Een zang-alleen render (_voc_ori) is een andere video en hoort
    niet in de verzameling van de gewone."""
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    (context.paths.output_dir / "Een Lied_voc_ori_2.mp4").write_bytes(b"zang")
    doel = tmp_path / "uit"
    pipeline.collect_videos(context, doel, with_sources=False)
    assert [p.name for p in doel.iterdir()] == ["Een Lied_2.mp4"]


def test_verzamelen_stopt_op_de_stopknop(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    _project(tmp_path, "Twee_Lied")
    doel = tmp_path / "uit"
    assert pipeline.collect_videos(context, doel, with_sources=False,
                                   cancelled=lambda: True) == (0, 0)


def test_de_verzameling_mag_niet_in_de_projecten_zelf(tmp_path) -> None:
    """Anders komt de opname en de tekst in de uitvoermap van elk project
    terecht."""
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    for slecht in (context.paths.output_root,
                   context.paths.output_root / "verzameling",
                   context.paths.output_dir):
        with pytest.raises(pipeline.PipelineError):
            pipeline.collect_videos(context, slecht, with_sources=True)
    # Ernaast mag wel.
    assert pipeline.collect_videos(context, tmp_path / "uit",
                                   with_sources=True)[0] == 1


def test_de_gui_vraagt_de_doelmap_voor_het_kopieren() -> None:
    """De melding hoort vóór het werk te komen, niet uit de werkdraad."""
    import inspect
    from modules import gui
    source = inspect.getsource(gui.MainWindow._do_collect_videos)
    assert "collect_destination_ok" in source
    assert source.index("collect_destination_ok") < source.index("self._run(")
    # En het voortgangssignaal draagt twee getallen, net als elke taak.
    assert "progress(float(done), float(total))" in source
    assert "cancel_event=cancel" in source


# --------------------------------------------------------------------------
# B530 op een echt bestand: de meting zelf, niet een nagebootste
# --------------------------------------------------------------------------

def _needs_ffmpeg():
    from modules import ffmpeg as f
    if not f.is_available():
        pytest.skip("ffmpeg niet beschikbaar")


def test_de_stilte_wordt_op_een_echt_bestand_teruggevonden(tmp_path) -> None:
    """De hele reparatie hangt hieraan: zet de filterketen er stilte
    voor, en meet de controle die stilte ook terug?"""
    _needs_ffmpeg()
    import subprocess
    from modules import ffmpeg as f

    bron = tmp_path / "bron.wav"
    # Een toon met een halve seconde eigen stilte ervoor - net als een
    # lied dat rustig begint.
    subprocess.run([f.find_executable("ffmpeg"), "-v", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-af", "adelay=500|500", "-ac", "2",
                    str(bron)], check=True)
    assert f.leading_silence(bron) == pytest.approx(0.5, abs=0.15)

    vertraagd = tmp_path / "vertraagd.wav"
    subprocess.run([f.find_executable("ffmpeg"), "-v", "error", "-y",
                    "-i", str(bron), "-af", f.delay_filter(6.215, 2),
                    str(vertraagd)], check=True)
    gemeten = f.leading_silence(vertraagd)
    # De aanloop plus de eigen stilte van het nummer: die twee grenzen
    # aan elkaar en de meter ziet er een.
    assert gemeten == pytest.approx(6.715, abs=0.15)
    assert gemeten > 6.215, "meer dan de aanloop, en dat is normaal"


# --------------------------------------------------------------------------
# B535 - an anchor at the edge of a packed run does not keep its start
# --------------------------------------------------------------------------

def _anchor(index: int, text: str, start: float, end: float):
    """A line that counts as an anchor, spread evenly over its span."""
    words = text.split()
    step = (end - start) / len(words)
    return timing.TimedLine(
        index=index, text=text, crowd=False, block=0, quality="high",
        syllables=tuple(
            timing.Syllable(("" if i == 0 else " ") + word,
                            start + i * step, start + (i + 1) * step)
            for i, word in enumerate(words)))


def _packed_three(last_end: float):
    """Three anchors packed far tighter than the phrase of 3.4 s.

    The last one runs on to ``last_end``, so the caller decides whether
    it is over-long as well as packed.
    """
    return tuple([
        _anchor(0, "loop niet zo", 100.0, 101.0),
        _anchor(1, "loop niet zo", 101.2, 102.2),
        _anchor(2, "loop niet zo", 102.4, last_end),
    ])


def _packed_run_in_a_song(last_end: float):
    """The same packed run, with enough healthy anchors around it that
    the ceiling on dropped anchors does not step in."""
    healthy = [_anchor(3 + i, "en verder gaat het lied",
                       130.0 + 4.0 * i, 133.0 + 4.0 * i)
               for i in range(6)]
    return tuple(list(_packed_three(last_end)) + healthy)


def test_de_hele_rij_telt_maar_alleen_de_binnenkant_valt_af() -> None:
    """B535: two questions, two answers about the same packed run.

    Which anchor has to GO is only the interior - the outer two pin the
    stretch (B340). Whether a start may be BELIEVED is asked of the
    whole run.
    """
    lines = _packed_three(103.4)
    anchors = [0, 1, 2]
    runs = timing._packed_runs(lines, anchors, 3.4)
    assert runs == [[0, 1, 2]]


def test_een_te_lang_anker_aan_de_rand_houdt_zijn_begin_niet() -> None:
    """The last of a packed run runs on into the instrumental. Before
    B535 it came back as "only too long" and kept a start that stood
    10 s too early; now the whole run is refused."""
    lines = _packed_run_in_a_song(125.0)         # 22.6 s against 3.4 s
    suspect, overlong = timing.implausible_and_overlong(lines, 3.4, {})
    assert 2 in suspect
    assert 2 not in overlong


def test_een_te_lang_anker_zonder_gedrang_houdt_zijn_begin_wel() -> None:
    """B522 keeps working where it was meant to: a lone anchor whose
    last word bleeds into the music is only too long, and its start is
    still exactly where the singing begins."""
    lines = tuple([
        _anchor(0, "where we'll plan", 100.0, 103.0),
        _anchor(1, "our escape now", 134.6, 150.2),
        _anchor(2, "and we drive on", 160.0, 163.0),
    ])
    suspect, overlong = timing.implausible_and_overlong(lines, 3.4, {})
    assert 1 in suspect and 1 in overlong


def test_zonder_maat_is_er_geen_gedrang() -> None:
    """No phrase period means no idea how tight is tight."""
    lines = _packed_three(103.4)
    assert timing._packed_runs(lines, [0, 1, 2], None) == []


# --------------------------------------------------------------------------
# B534 - every run keeps its own report
# --------------------------------------------------------------------------

def test_de_naam_van_een_verslag_zegt_wanneer_en_wat() -> None:
    from datetime import datetime
    from modules import test_panel
    moment = datetime(2026, 8, 31, 9, 29)
    naam = test_panel.report_name(["1.5.5"], "0.150.0", "alle projecten",
                                  moment)
    assert naam == ("testverslag_2026-08-31_092900_v0.150.0_1.5.5"
                    "_alle-projecten.md")


def test_een_lange_ticklijst_wordt_van_eerste_tot_laatste() -> None:
    """Twaalf codes in een bestandsnaam helpt niemand."""
    from datetime import datetime
    from modules import test_panel
    naam = test_panel.report_name(
        ["1.5.1", "1.5.2", "1.5.3", "1.5.4", "1.5.5"], "0.150.0", "",
        datetime(2026, 8, 31, 9, 29))
    assert "1.5.1-tm-1.5.5" in naam and "1.5.3" not in naam


def test_de_naam_verdraagt_een_gekke_projectnaam() -> None:
    from datetime import datetime
    from modules import test_panel
    naam = test_panel.report_name(["1.5.5"], "0.150.0", "Wie? Wat/Waar!",
                                  datetime(2026, 8, 31, 9, 29))
    assert "/" not in naam and "?" not in naam and naam.endswith(".md")
    assert "Wie-Wat-Waar" in naam


def test_twee_draaien_laten_allebei_een_verslag_staan(tmp_path,
                                                      monkeypatch) -> None:
    """Precies waar de gebruiker om vroeg: alles meten, dan een nieuw
    project meten, en de eerste uitslag staat er nog."""
    from datetime import datetime
    from modules import test_panel
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    momenten = iter([datetime(2026, 8, 31, 9, 29),
                     datetime(2026, 8, 31, 11, 5)])
    echt = test_panel.report_name
    monkeypatch.setattr(
        test_panel, "report_name",
        lambda codes, version="", scope="", moment=None:
            echt(codes, version, scope, next(momenten)))
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "eerste uitslag", 1.0, 1.0)
    test_panel.start_trial_report(["1.5.5"], "Nieuw lied", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "tweede uitslag", 1.0, 1.0)
    verslagen = sorted((tmp_path / "verslagen").glob("testverslag_*.md"))
    assert len(verslagen) == 2
    tekst = "\n".join(v.read_text(encoding="utf-8") for v in verslagen)
    assert "eerste uitslag" in tekst and "tweede uitslag" in tekst


def test_een_mislukte_kopie_laat_de_vorige_draai_niet_los(tmp_path,
                                                          monkeypatch) -> None:
    """B534: is de verslagmap onbruikbaar, dan komt de kopie naast de
    bron te staan. Anders wordt de vorige draai alsnog overschreven en
    is de enige melding een logregel."""
    from modules import test_panel
    blokkade = tmp_path / "geen_map"
    blokkade.write_text("dit is een bestand", encoding="utf-8")
    monkeypatch.setattr(test_panel, "REPORT_DIR", blokkade)
    bron = tmp_path / "modelmatrix.md"
    bron.write_text("de vorige draai", encoding="utf-8")
    kopie = test_panel.keep_dated_copy(bron)
    assert kopie is not None and kopie.parent == bron.parent
    assert kopie.read_text(encoding="utf-8") == "de vorige draai"
    assert kopie.name.startswith("modelmatrix_") and kopie.suffix == ".md"


def test_honderd_kopieen_in_een_seconde_botsen_nog_steeds_niet(
        tmp_path, monkeypatch) -> None:
    from modules import test_panel
    map_ = tmp_path / "verslagen"
    map_.mkdir()
    pad = map_ / "testverslag_x.md"
    pad.write_text("", encoding="utf-8")
    for nummer in range(2, 100):
        (map_ / f"testverslag_x_{nummer}.md").write_text("", encoding="utf-8")
    vrij = test_panel._free_path(pad)
    assert not vrij.exists() and vrij.name.startswith("testverslag_x_")


def test_de_grote_verslagen_houden_een_gedateerde_kopie(tmp_path,
                                                        monkeypatch) -> None:
    """modelmatrix.md en modelcombinaties.md worden tijdens hun eigen
    draai steeds overschreven - dat moet ook - maar ze mogen de vorige
    draai niet stilzwijgend wissen. De kopie wordt daarom gemaakt
    VOORDAT de nieuwe draai begint te schrijven: een draai die halverwege
    stukloopt is juist de draai die de vorige zou meenemen."""
    from modules import test_panel
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    bron = tmp_path / "modelmatrix.md"
    bron.write_text("de uitkomst van deze draai", encoding="utf-8")
    kopie = test_panel.keep_dated_copy(bron)
    assert kopie is not None and kopie.exists()
    assert kopie.read_text(encoding="utf-8") == "de uitkomst van deze draai"
    assert kopie.name.startswith("modelmatrix_") and kopie.suffix == ".md"
    # Het vaste bestand blijft staan als "de nieuwste".
    assert bron.exists()


def test_een_kopie_van_niets_valt_niet_om(tmp_path, monkeypatch) -> None:
    from modules import test_panel
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    assert test_panel.keep_dated_copy(tmp_path / "bestaat_niet.md") is None


def test_een_losse_actie_begint_zijn_eigen_verslag(tmp_path,
                                                   monkeypatch) -> None:
    """Niet elke actie komt via het paneel binnen; die regels mogen niet
    verdwijnen, maar ze horen ook niet in het verslag van een vorige
    draai - dat zegt bovenaan wanneer en met welke versie het gemaakt
    is."""
    from modules import test_panel
    map_ = tmp_path / "verslagen"
    map_.mkdir()
    monkeypatch.setattr(test_panel, "REPORT_DIR", map_)
    monkeypatch.setattr(test_panel, "TRIAL_REPORT", None)
    eerder = map_ / "testverslag_2026-08-31_092900_v0.149.0_1.5.5.md"
    eerder.write_text("# eerder\n", encoding="utf-8")
    test_panel.add_trial_result("1.5.9", "Uitlaatproef", "uitslag", 1.0, 1.0)
    assert eerder.read_text(encoding="utf-8") == "# eerder\n"
    nieuw = test_panel.TRIAL_REPORT
    assert nieuw is not None and nieuw != eerder
    assert "uitslag" in nieuw.read_text(encoding="utf-8")


def test_twee_draaien_in_dezelfde_seconde_botsen_niet(tmp_path,
                                                      monkeypatch) -> None:
    """B534: de vaste bestandsnaam was ook 'onwaarschijnlijk'."""
    from datetime import datetime
    from modules import test_panel
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    vast = datetime(2026, 8, 31, 9, 29, 0)
    echt = test_panel.report_name
    monkeypatch.setattr(
        test_panel, "report_name",
        lambda codes, version="", scope="", moment=None:
            echt(codes, version, scope, vast))
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "eerste", 1.0, 1.0)
    eerste = test_panel.TRIAL_REPORT
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "tweede", 1.0, 1.0)
    assert test_panel.TRIAL_REPORT != eerste
    assert "eerste" in eerste.read_text(encoding="utf-8")


def test_zonder_alarm_komt_er_geen_kop_alarmen(tmp_path,
                                               monkeypatch) -> None:
    """B537: een geruststelling onder de kop 'Alarmen' leest als alarm."""
    from modules import test_panel
    monkeypatch.setattr(test_panel, "_SANITY_ALARMS", [])
    assert test_panel.alarm_rows() == []
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "uitslag", 1.0, 1.0,
                                test_panel.alarm_rows())
    tekst = test_panel.TRIAL_REPORT.read_text(encoding="utf-8")
    assert "Alarm" not in tekst and "* " not in tekst


def test_een_alarm_komt_als_tabel_in_het_verslag(tmp_path,
                                                 monkeypatch) -> None:
    from modules import test_panel
    monkeypatch.setattr(test_panel, "_SANITY_ALARMS",
                        [{"project": "Lied R", "models": "B213",
                          "counts": {"nieuw": 3}}])
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "uitslag", 1.0, 1.0,
                                test_panel.alarm_rows())
    tekst = test_panel.TRIAL_REPORT.read_text(encoding="utf-8")
    assert "| Lied R | B213 | nieuw 3 |" in tekst
    assert "* |" not in tekst          # geen tabel in bullets
    assert "\n* \n" not in tekst       # en geen lege bullet


def test_het_eerste_lid_van_een_gedrongen_rij_houdt_zijn_begin_wel() -> None:
    """B535: de rij is gedrongen, maar van de kopieen is de EERSTE de
    plek waar de zang aannemelijk begon - en dat is precies de vorm
    waarvoor B522 gebouwd is: een goed begin met een einde dat het
    instrumentale stuk in loopt."""
    lines = tuple([
        _anchor(0, "loop niet zo", 100.0, 122.0),    # 22 s tegen 3,4 s
        _anchor(1, "loop niet zo", 101.2, 102.2),
        _anchor(2, "loop niet zo", 102.4, 103.4),
    ] + [_anchor(3 + i, "en verder gaat het lied",
                 130.0 + 4.0 * i, 133.0 + 4.0 * i) for i in range(6)])
    suspect, overlong = timing.implausible_and_overlong(lines, 3.4, {})
    assert 0 in suspect and 0 in overlong


def test_de_kopie_wordt_gemaakt_voordat_de_draai_schrijft() -> None:
    """De aanroep staat aan het BEGIN van 1.5.10 en 1.5.11, niet aan het
    eind - anders helpt hij niet als de draai wordt afgebroken."""
    import inspect
    from modules import test_panel
    for functie in (test_panel.big_trial, test_panel.heavy_trial):
        bron = inspect.getsource(functie)
        assert "keep_dated_copy(report_file)" in bron
        assert (bron.index("keep_dated_copy(report_file)")
                < bron.index("def write_report()")), functie.__name__


# --------------------------------------------------------------------------
# B536 - de geleverde stand, en wat er WEL en NIET mee uit gaat
# --------------------------------------------------------------------------

def test_de_geleverde_stand_is_precies_deze_twee(monkeypatch) -> None:
    """Wat de gebruiker echt krijgt als hij de app start. De hele
    toetsenreeks draait met alles aan (anders toetst de helft van de
    hallucinatietoetsen code die niet meer loopt), dus die stand komt
    nergens anders langs."""
    from modules import model_register
    model_register.apply_settings({})
    uit = model_register.apply_disabled()
    assert sorted(uit) == ["B258/B285", "B380"]


def _segment(index, text, start, end, words, confidence=0.8):
    from modules.whisper import Segment, Word
    return Segment(index, text, start, end,
                   tuple(Word(w, s, e, confidence) for w, s, e in words))


def _verzonnen_zin():
    """De echte Lied_S-hallucinatie: geen songtekst-match en een
    wisselvallige woord-confidence (0,34 het laagst)."""
    from modules.whisper import Segment, Word
    return Segment(91, "Heerlijke Heer, Heerlijke Heer", 60.0, 63.0, (
        Word("Heerlijke", 60.0, 61.0, 0.34),
        Word("Heer", 61.0, 62.0, 0.48),
        Word("Heerlijke", 62.0, 62.5, 0.72),
        Word("Heer", 62.5, 63.0, 0.99),
    ))


def _gewone_segmenten(count=12):
    return [_segment(i, "woord", 10.0 + i, 10.4 + i,
                     [("woord", 10.0 + i, 10.4 + i)]) for i in range(count)]


def test_de_vaste_lijst_en_de_vastgelopen_lus_blijven_lopen() -> None:
    """B536: B141 en B514 wonen in dezelfde functie als B258/B285 maar
    hebben er niets mee te maken, en zijn los gemeten. Ze mogen niet
    meegaan als de schakelaar om gaat."""
    from modules import model_register, pipeline
    from modules.song_text import LyricWord

    lyrics = tuple(LyricWord(i, w, 0) for i, w in enumerate(
        "ik heb veel bier getapt maar ook veel bier gemorst".split()))
    muziek = _segment(90, "MUZIEK", 200.0, 208.0,
                      [("MUZIEK", 200.0, 208.0)])
    lus = _segment(99, "D.O." * 55, 116.8, 143.8,
                   [("D.O." * 55, 116.8, 143.8)])
    verzonnen = _verzonnen_zin()
    segmenten = tuple(_gewone_segmenten() + [muziek, lus, verzonnen])

    model_register.apply_settings({})
    model_register.apply_disabled()               # de geleverde stand
    try:
        over = pipeline._filter_hallucinations(segmenten, lyrics)
    finally:
        model_register.restore_all()
    teksten = [s.text for s in over]
    assert "MUZIEK" not in teksten                # B141 loopt door
    assert lus.text not in teksten                # B514 loopt door
    assert verzonnen.text in teksten              # B285 staat uit


def test_met_de_schakelaar_aan_valt_het_verzonnen_stuk_wel_af() -> None:
    from modules import pipeline
    from modules.song_text import LyricWord
    lyrics = tuple(LyricWord(i, w, 0) for i, w in enumerate(
        "ik heb veel bier getapt maar ook veel bier gemorst".split()))
    verzonnen = _verzonnen_zin()
    over = pipeline._filter_hallucinations(
        tuple(_gewone_segmenten() + [verzonnen]), lyrics)
    assert verzonnen.text not in [s.text for s in over]


def test_een_volgorde_bouwt_op_de_pijplijn_die_er_echt_draait() -> None:
    """B536: een volgorde is een herschikking van de pijplijn zoals de
    gebruiker hem draait. Hij pakt dus de functie die NU op de module
    staat - langs een modelschakelaar heen grijpen zou een pijplijn
    meten die niemand heeft."""
    from modules import model_orders, model_register, pipeline

    model_register.apply_settings({})
    model_register.apply_disabled()               # de geleverde stand
    try:
        nu = pipeline._filter_hallucinations
        gebouwd = model_orders.targets("B307 vóór B285")
        assert gebouwd and gebouwd[0][1] == "_clean_segments_and_alignment"
        in_de_sluiting = [cel.cell_contents
                          for cel in gebouwd[0][2].__closure__ or ()]
        assert nu in in_de_sluiting
    finally:
        model_register.restore_all()


def test_een_volgorde_over_een_uitgezet_model_wordt_niet_gemeten() -> None:
    """En dat is de keerzijde: staat een stap die de volgorde verzet
    uit, dan is er niets te herschikken. Dan hoort er "overgeslagen" te
    staan en geen keurige 0,00 s voor iets dat nooit geprobeerd is -
    precies de meetfout die B529 een laag lager opruimde."""
    from modules import model_orders, model_register

    model_register.apply_settings({})
    assert model_orders.measurable("B307 vóór B285") == ("B258/B285",)
    model_register.apply_settings({"B258/B285": True})
    try:
        assert model_orders.measurable("B307 vóór B285") == ()
    finally:
        model_register.apply_settings({})


def test_elke_volgorde_noemt_de_modellen_die_hij_verzet() -> None:
    """Zonder die koppeling kan niemand zien dat een volgorde loos is."""
    from modules import model_orders, model_register

    for name in model_orders.names():
        codes = model_orders.models_for(name)
        assert codes, name
        for code in codes:
            assert model_register.by_code(code) is not None, code


def test_zang_en_muziek_valt_ook_met_de_schakelaar_uit_af() -> None:
    """B536: "ZANG EN MUZIEK" is het voorbeeld waarmee de B258-uitleg
    opent. Met de schakelaar uit telt "zang" niet meer mee - maar dan
    moet het wel als vulwoord wegvallen en niet als vrijbrief, anders
    overleeft het segment terwijl kaal "MUZIEK" er wel uit gaat."""
    from modules import model_register, pipeline
    from modules.song_text import LyricWord

    lyrics = tuple(LyricWord(i, w, 0) for i, w in enumerate(
        "ik heb veel bier getapt maar ook veel bier gemorst".split()))
    samen = _segment(90, "ZANG EN MUZIEK", 229.9, 241.0,
                     [("ZANG", 229.9, 231.3), ("EN", 231.3, 232.7),
                      ("MUZIEK", 232.7, 241.0)], confidence=0.98)
    kaal = _segment(92, "MUZIEK", 250.0, 258.0,
                    [("MUZIEK", 250.0, 258.0)], confidence=0.98)
    segmenten = tuple(_gewone_segmenten() + [samen, kaal])

    model_register.apply_settings({})
    model_register.apply_disabled()
    try:
        over = [s.text for s in pipeline._filter_hallucinations(segmenten,
                                                                lyrics)]
    finally:
        model_register.restore_all()
    assert "MUZIEK" not in over and "ZANG EN MUZIEK" not in over


def test_een_lied_dat_echt_over_zang_gaat_houdt_zijn_zin() -> None:
    """De andere kant: "zang" mag geen hallucinatiesignaal zijn zonder
    dat B258 aan staat, ook niet via een omweg."""
    from modules import model_register, pipeline
    from modules.song_text import LyricWord

    lyrics = tuple(LyricWord(i, w, 0) for i, w in enumerate(
        "wij gaan zingen want de zang zit in ons bloed".split()))
    zin = _segment(90, "de zang zit in ons bloed", 100.0, 103.0,
                   [("de", 100.0, 100.4), ("zang", 100.4, 101.0),
                    ("zit", 101.0, 101.4), ("in", 101.4, 101.8),
                    ("ons", 101.8, 102.2), ("bloed", 102.2, 103.0)],
                   confidence=0.95)
    segmenten = tuple(_gewone_segmenten() + [zin])
    model_register.apply_settings({})
    model_register.apply_disabled()
    try:
        over = [s.text for s in pipeline._filter_hallucinations(segmenten,
                                                                lyrics)]
    finally:
        model_register.restore_all()
    assert "de zang zit in ons bloed" in over
