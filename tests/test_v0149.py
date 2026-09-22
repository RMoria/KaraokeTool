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

def test_the_delay_names_the_channel_layout() -> None:
    """The user's karaoke.wav files carry channel_layout=unknown, and a
    delay has nothing to bind to without a layout."""
    filter_text = ffmpeg_module.delay_filter(6.215, channels=2)
    assert filter_text.startswith("aformat=channel_layouts=stereo,")
    assert "adelay=6215|6215" in filter_text
    assert ffmpeg_module.delay_filter(1.0, channels=1).startswith(
        "aformat=channel_layouts=mono,")


def test_the_delay_applies_to_every_channel_separately() -> None:
    """Per channel and not "all": then the filter never has to work out
    how many channels "all" means."""
    assert ffmpeg_module.delay_filter(1.0, channels=1).endswith(
        "adelay=1000")
    assert ffmpeg_module.delay_filter(1.0, channels=2).endswith(
        "adelay=1000|1000")
    # Something exotic gets no layout imposed on it, only the delays.
    assert ffmpeg_module.delay_filter(1.0, channels=6) == \
        "adelay=1000|1000|1000|1000|1000|1000"


def test_the_delay_rounds_to_whole_milliseconds() -> None:
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


def _capture(monkeypatch, tmp_path, lines, silence=None, target_name="out",
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


def test_the_delay_comes_before_the_loudness_step(monkeypatch,
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


def test_without_a_lead_in_there_is_no_delay(monkeypatch, tmp_path) -> None:
    """A song whose first line starts after ten seconds needs nothing."""
    seen = _capture(monkeypatch, tmp_path, _lines(14.7), silence=0.0)
    assert _audio_filter(seen["command"]) == "apad"


def test_the_render_refuses_when_the_silence_is_wrong(monkeypatch,
                                                      tmp_path) -> None:
    """The heart of B530: a video that runs out of step is not written."""
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=0.0)
    assert "error" in seen
    assert "6.21" in seen["error"] and "0.0" in seen["error"]
    assert not seen["target"].exists()


def test_the_render_goes_ahead_when_the_silence_is_right(monkeypatch,
                                                         tmp_path) -> None:
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=6.215)
    assert "error" not in seen, seen.get("error")


def test_an_unmeasurable_silence_does_not_stop_the_render(monkeypatch,
                                                          tmp_path) -> None:
    """A check that cannot run may not block a render that is probably
    fine - but it does say so."""
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=None)
    assert "error" not in seen, seen.get("error")


def test_more_silence_than_the_lead_in_is_no_error(monkeypatch,
                                                   tmp_path) -> None:
    """The measured silence is the lead-in PLUS the song's own quiet
    start - the two sit against each other and the meter sees one. Over
    the user's own collection that difference ran up from 0.2 to 0.4 s,
    and every one of those renders was good. Testing both ways would
    refuse exactly those."""
    assert video.LEAD_SILENCE_SLACK_S == pytest.approx(0.10)
    for extra, name in ((0.28, "short"), (0.45, "ample"), (5.0, "very_long")):
        seen = _capture(monkeypatch, tmp_path, _lines(3.785),
                        silence=6.215 + extra, target_name=name)
        assert "error" not in seen, (extra, seen.get("error"))


def test_too_little_silence_is_an_error(monkeypatch, tmp_path) -> None:
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=6.15,
                    target_name="just_enough")
    assert "error" not in seen, seen.get("error")
    seen = _capture(monkeypatch, tmp_path, _lines(3.785), silence=5.9,
                    target_name="too_little")
    assert "error" in seen


def _stub_run(monkeypatch, output: str, code: int = 0) -> None:
    monkeypatch.setattr(ffmpeg_module.proc, "run",
                        lambda *a, **k: types.SimpleNamespace(
                            stderr=output, stdout="", returncode=code))


def test_the_silence_measurement_reads_the_beginning(monkeypatch) -> None:
    """Only a silence that starts at the beginning counts."""
    output = ("[silencedetect] silence_start: 0\n"
              "[silencedetect] silence_end: 6.215 | silence_duration: 6.215\n"
              "[silencedetect] silence_start: 50.1\n")
    _stub_run(monkeypatch, output)
    assert ffmpeg_module.leading_silence(Path("x.mp4")) == pytest.approx(6.215)


def test_sound_that_starts_right_away_measures_zero(monkeypatch) -> None:
    _stub_run(monkeypatch, "niets bijzonders\n")
    assert ffmpeg_module.leading_silence(Path("x.mp4")) == 0.0


def test_silence_that_only_starts_later_measures_zero(monkeypatch) -> None:
    """A pause halfway through the song says nothing about the start -
    and answering "not measured" would let the check look away at
    exactly the flaw it exists to catch."""
    output = ("[silencedetect] silence_start: 12.5\n"
              "[silencedetect] silence_end: 19.0 | silence_duration: 6.5\n")
    _stub_run(monkeypatch, output)
    assert ffmpeg_module.leading_silence(Path("x.mp4")) == 0.0


def test_an_unreadable_file_measures_nothing(monkeypatch) -> None:
    """Zero seconds of silence is a claim, and the caller refuses a
    render on that claim."""
    _stub_run(monkeypatch, "No such file or directory\n", code=1)
    assert ffmpeg_module.leading_silence(Path("weg.mp4")) is None


def test_a_silence_without_an_end_measures_nothing(monkeypatch) -> None:
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


def test_the_job_sits_last_and_is_not_a_measurement() -> None:
    from modules import test_panel
    codes = [a.code for a in test_panel.ACTIONS]
    assert codes[-1] == "1.5.12"
    action = test_panel.ACTIONS[-1]
    assert action.on_request and not action.heavy
    assert action.function is test_panel.rebuild_videos


def test_the_job_never_rides_along_with_select_all(qapp) -> None:
    """Making every video again overwrites finished work; that is done
    on purpose and not with one tick."""
    from modules import test_panel
    panel = test_panel.TestPanel()
    panel._toggle_all()
    assert "1.5.12" not in [a.code for a in panel.chosen()]
    assert all(not a.on_request for a in panel.chosen())


def test_the_job_can_still_be_ticked_on_its_own(qapp) -> None:
    """Outside the 'all' tick, but one click away all the same.

    B563: 1.5.1 became a job as well - it is the only light-looking
    action that starts Demucs and Whisper - so "the first on_request
    action" is no longer 1.5.12. The job is looked up by its code now,
    and every job is checked, because the rule is about all of them.
    """
    from modules import test_panel
    panel = test_panel.TestPanel()
    spots = {a.code: n for n, a in enumerate(panel._actions)
             if a.on_request}
    assert "1.5.12" in spots, "1.5.12 has to be visible"
    for code, spot in spots.items():
        panel._ticks[spot].setChecked(True)
        assert [a.code for a in panel.chosen()] == [code]
        panel._ticks[spot].setChecked(False)


def test_the_job_does_not_count_towards_the_ceiling() -> None:
    from modules import test_panel
    measurements = [a for a in test_panel.ACTIONS
                    if not a.heavy and not a.on_request]
    assert len(measurements) <= test_panel.MAX_ACTIONS == 10


def test_the_old_videos_go_beside_the_program_folder(tmp_path) -> None:
    """B531: into the folder the user empties himself, not into the
    program folder - there they would be clutter."""
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


def test_the_job_renders_first_and_clears_up_after() -> None:
    """The order is the whole safety net: a failed render may never cost
    a finished video."""
    import inspect
    from modules import test_panel
    source = inspect.getsource(test_panel.rebuild_videos)
    assert source.index("run_video") < source.index("shutil.move")
    assert "next_video_target" in source
    # And the old video may only be overwritten once it is really gone.
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
    (paths.input_dir / "lyrics.txt").write_text("een", encoding="utf-8")
    (paths.input_dir / "karaoke_text.txt").write_text("twee", encoding="utf-8")
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


def test_only_projects_with_a_video_count(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Met_Video")
    _project(tmp_path, "Zonder_Video", video=False)
    assert pipeline.projects_with_video(context) == ["Met_Video"]


def test_only_the_videos_land_flat_in_the_folder(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    target = tmp_path / "uit"
    projects, files = pipeline.collect_videos(context, target,
                                              with_sources=False)
    assert (projects, files) == (1, 1)
    assert [p.name for p in sorted(target.iterdir())] == ["Een Lied_2.mp4"]


def test_the_collection_gets_a_folder_per_project(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    _project(tmp_path, "Twee_Lied")
    target = tmp_path / "uit"
    projects, files = pipeline.collect_videos(context, target,
                                              with_sources=True)
    assert projects == 2 and files == 8
    names = sorted(p.name for p in (target / "Een_Lied").iterdir())
    assert names == ["Een Lied_2.mp4", "karaoke_text.txt", "lyrics.txt",
                     "original.mp3"]


def test_the_newest_render_goes_along(tmp_path) -> None:
    """Highest sequence number, not the newest name - _10 comes after
    _3."""
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    (context.paths.output_dir / "Een Lied_10.mp4").write_bytes(b"nieuwste")
    target = tmp_path / "uit"
    pipeline.collect_videos(context, target, with_sources=False)
    assert (target / "Een Lied_10.mp4").exists()
    assert not (target / "Een Lied_2.mp4").exists()


def test_the_button_is_off_without_a_video(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Zonder", video=False)
    assert pipeline.projects_with_video(context) == []
    target = tmp_path / "uit"
    assert pipeline.collect_videos(context, target,
                                   with_sources=True) == (0, 0)


def test_two_projects_with_the_same_title_do_not_overwrite_each_other(
        tmp_path) -> None:
    """The title comes from the settings and not from the folder name,
    so two projects can carry the same video name. Overwriting in
    silence would cost the first one and turn the count into a lie."""
    from modules import pipeline
    context = _project(tmp_path, "Opname_1", title="Mijn Lied")
    _project(tmp_path, "Opname_2", title="Mijn Lied")
    target = tmp_path / "uit"
    projects, files = pipeline.collect_videos(context, target,
                                              with_sources=False)
    assert (projects, files) == (2, 2)
    assert len(list(target.iterdir())) == 2


def test_the_other_render_variant_stays_behind(tmp_path) -> None:
    """A vocals-only render (_voc_ori) is a different video and does not
    belong in the collection of the ordinary ones."""
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    (context.paths.output_dir / "Een Lied_voc_ori_2.mp4").write_bytes(b"zang")
    target = tmp_path / "uit"
    pipeline.collect_videos(context, target, with_sources=False)
    assert [p.name for p in target.iterdir()] == ["Een Lied_2.mp4"]


def test_collecting_stops_on_the_stop_button(tmp_path) -> None:
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    _project(tmp_path, "Twee_Lied")
    target = tmp_path / "uit"
    assert pipeline.collect_videos(context, target, with_sources=False,
                                   cancelled=lambda: True) == (0, 0)


def test_the_collection_may_not_sit_inside_the_projects(tmp_path) -> None:
    """Otherwise the recording and the lyrics end up in the output
    folder of every project."""
    from modules import pipeline
    context = _project(tmp_path, "Een_Lied")
    for bad in (context.paths.output_root,
                context.paths.output_root / "verzameling",
                context.paths.output_dir):
        with pytest.raises(pipeline.PipelineError):
            pipeline.collect_videos(context, bad, with_sources=True)
    # Beside them is fine.
    assert pipeline.collect_videos(context, tmp_path / "uit",
                                   with_sources=True)[0] == 1


def test_the_gui_asks_for_the_target_folder_before_copying() -> None:
    """The prompt belongs before the work, not out of the worker
    thread."""
    import inspect
    from modules import gui
    source = inspect.getsource(gui.MainWindow._do_collect_videos)
    assert "collect_destination_ok" in source
    assert source.index("collect_destination_ok") < source.index("self._run(")
    # And the progress signal carries two numbers, like every task.
    assert "progress(float(done), float(total))" in source
    assert "cancel_event=cancel" in source


# --------------------------------------------------------------------------
# B530 on a real file: the measurement itself, not a stubbed one
# --------------------------------------------------------------------------

def _needs_ffmpeg():
    from modules import ffmpeg as f
    if not f.is_available():
        pytest.skip("ffmpeg not available")


def test_the_silence_is_found_back_on_a_real_file(tmp_path) -> None:
    """The whole repair hangs on this: the filter chain puts silence in
    front - does the check measure that silence back?"""
    _needs_ffmpeg()
    import subprocess
    from modules import ffmpeg as f

    source = tmp_path / "bron.wav"
    # A tone with half a second of silence of its own in front - like a
    # song that starts quietly.
    subprocess.run([f.find_executable("ffmpeg"), "-v", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-af", "adelay=500|500", "-ac", "2",
                    str(source)], check=True)
    assert f.leading_silence(source) == pytest.approx(0.5, abs=0.15)

    delayed = tmp_path / "vertraagd.wav"
    subprocess.run([f.find_executable("ffmpeg"), "-v", "error", "-y",
                    "-i", str(source), "-af", f.delay_filter(6.215, 2),
                    str(delayed)], check=True)
    measured = f.leading_silence(delayed)
    # The lead-in plus the song's own silence: the two sit against each
    # other and the meter sees one.
    assert measured == pytest.approx(6.715, abs=0.15)
    assert measured > 6.215, "more than the lead-in, and that is normal"


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


def test_the_whole_run_counts_but_only_the_interior_drops() -> None:
    """B535: two questions, two answers about the same packed run.

    Which anchor has to GO is only the interior - the outer two pin the
    stretch (B340). Whether a start may be BELIEVED is asked of the
    whole run.
    """
    lines = _packed_three(103.4)
    anchors = [0, 1, 2]
    runs = timing._packed_runs(lines, anchors, 3.4)
    assert runs == [[0, 1, 2]]


def test_an_overlong_anchor_at_the_edge_loses_its_start() -> None:
    """The last of a packed run runs on into the instrumental. Before
    B535 it came back as "only too long" and kept a start that stood
    10 s too early; now the whole run is refused."""
    lines = _packed_run_in_a_song(125.0)         # 22.6 s against 3.4 s
    suspect, overlong = timing.implausible_and_overlong(lines, 3.4, {})
    assert 2 in suspect
    assert 2 not in overlong


def test_an_overlong_anchor_without_packing_keeps_its_start() -> None:
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


def test_without_a_phrase_length_there_is_no_packing() -> None:
    """No phrase period means no idea how tight is tight."""
    lines = _packed_three(103.4)
    assert timing._packed_runs(lines, [0, 1, 2], None) == []


# --------------------------------------------------------------------------
# B534 - every run keeps its own report
# --------------------------------------------------------------------------

def test_a_report_name_says_when_and_what() -> None:
    from datetime import datetime
    from modules import test_panel
    moment = datetime(2026, 8, 31, 9, 29)
    name = test_panel.report_name(["1.5.5"], "0.150.0", "alle projecten",
                                  moment)
    assert name == ("testverslag_2026-08-31_092900_v0.150.0_1.5.5"
                    "_alle-projecten.md")


def test_a_long_tick_list_becomes_first_to_last() -> None:
    """Twelve codes in a file name help nobody."""
    from datetime import datetime
    from modules import test_panel
    name = test_panel.report_name(
        ["1.5.1", "1.5.2", "1.5.3", "1.5.4", "1.5.5"], "0.150.0", "",
        datetime(2026, 8, 31, 9, 29))
    assert "1.5.1-tm-1.5.5" in name and "1.5.3" not in name


def test_the_name_survives_an_odd_project_name() -> None:
    from datetime import datetime
    from modules import test_panel
    name = test_panel.report_name(["1.5.5"], "0.150.0", "Wie? Wat/Waar!",
                                  datetime(2026, 8, 31, 9, 29))
    assert "/" not in name and "?" not in name and name.endswith(".md")
    assert "Wie-Wat-Waar" in name


def test_two_runs_each_leave_a_report_behind(tmp_path,
                                             monkeypatch) -> None:
    """Exactly what the user asked for: measure everything, then measure
    a new project, and the first result is still there."""
    from datetime import datetime
    from modules import test_panel
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    moments = iter([datetime(2026, 8, 31, 9, 29),
                    datetime(2026, 8, 31, 11, 5)])
    real = test_panel.report_name
    monkeypatch.setattr(
        test_panel, "report_name",
        lambda codes, version="", scope="", moment=None:
            real(codes, version, scope, next(moments)))
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "eerste uitslag", 1.0, 1.0)
    test_panel.start_trial_report(["1.5.5"], "Nieuw lied", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "tweede uitslag", 1.0, 1.0)
    reports = sorted((tmp_path / "verslagen").glob("testverslag_*.md"))
    assert len(reports) == 2
    text = "\n".join(v.read_text(encoding="utf-8") for v in reports)
    assert "eerste uitslag" in text and "tweede uitslag" in text


def test_a_failed_copy_does_not_let_go_of_the_previous_run(
        tmp_path, monkeypatch) -> None:
    """B534: if the report folder is unusable, the copy lands beside the
    source. Otherwise the previous run is overwritten after all and the
    only notice is a log line."""
    from modules import test_panel
    blocker = tmp_path / "geen_map"
    blocker.write_text("dit is een bestand", encoding="utf-8")
    monkeypatch.setattr(test_panel, "REPORT_DIR", blocker)
    source = tmp_path / "modelmatrix.md"
    source.write_text("de vorige draai", encoding="utf-8")
    copy = test_panel.keep_dated_copy(source)
    assert copy is not None and copy.parent == source.parent
    assert copy.read_text(encoding="utf-8") == "de vorige draai"
    assert copy.name.startswith("modelmatrix_") and copy.suffix == ".md"


def test_a_hundred_copies_in_one_second_still_do_not_collide(
        tmp_path, monkeypatch) -> None:
    from modules import test_panel
    folder = tmp_path / "verslagen"
    folder.mkdir()
    path = folder / "testverslag_x.md"
    path.write_text("", encoding="utf-8")
    for number in range(2, 100):
        (folder / f"testverslag_x_{number}.md").write_text("",
                                                           encoding="utf-8")
    free = test_panel._free_path(path)
    assert not free.exists() and free.name.startswith("testverslag_x_")


def test_the_big_reports_keep_a_dated_copy(tmp_path,
                                           monkeypatch) -> None:
    """modelmatrix.md and modelcombinaties.md are overwritten again and
    again during their own run - as they should be - but they may not
    wipe the previous run in silence. The copy is therefore made BEFORE
    the new run starts writing: a run that breaks down halfway is
    precisely the run that would take the previous one with it."""
    from modules import test_panel
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    source = tmp_path / "modelmatrix.md"
    source.write_text("de uitkomst van deze draai", encoding="utf-8")
    copy = test_panel.keep_dated_copy(source)
    assert copy is not None and copy.exists()
    assert copy.read_text(encoding="utf-8") == "de uitkomst van deze draai"
    assert copy.name.startswith("modelmatrix_") and copy.suffix == ".md"
    # The fixed file stays put as "the newest".
    assert source.exists()


def test_a_copy_of_nothing_does_not_fall_over(tmp_path, monkeypatch) -> None:
    from modules import test_panel
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    assert test_panel.keep_dated_copy(tmp_path / "bestaat_niet.md") is None


def test_a_stray_action_starts_its_own_report(tmp_path,
                                              monkeypatch) -> None:
    """Not every action comes in through the panel; those rows may not
    disappear, but they do not belong in the report of an earlier run
    either - that one states at the top when and with which version it
    was made."""
    from modules import test_panel
    folder = tmp_path / "verslagen"
    folder.mkdir()
    monkeypatch.setattr(test_panel, "REPORT_DIR", folder)
    monkeypatch.setattr(test_panel, "TRIAL_REPORT", None)
    earlier = folder / "testverslag_2026-08-31_092900_v0.149.0_1.5.5.md"
    earlier.write_text("# eerder\n", encoding="utf-8")
    test_panel.add_trial_result("1.5.9", "Uitlaatproef", "uitslag", 1.0, 1.0)
    assert earlier.read_text(encoding="utf-8") == "# eerder\n"
    fresh = test_panel.TRIAL_REPORT
    assert fresh is not None and fresh != earlier
    assert "uitslag" in fresh.read_text(encoding="utf-8")


def test_two_runs_in_the_same_second_do_not_collide(tmp_path,
                                                    monkeypatch) -> None:
    """B534: the fixed file name was 'unlikely' to collide as well."""
    from datetime import datetime
    from modules import test_panel
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    fixed = datetime(2026, 8, 31, 9, 29, 0)
    real = test_panel.report_name
    monkeypatch.setattr(
        test_panel, "report_name",
        lambda codes, version="", scope="", moment=None:
            real(codes, version, scope, fixed))
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "eerste", 1.0, 1.0)
    first = test_panel.TRIAL_REPORT
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "tweede", 1.0, 1.0)
    assert test_panel.TRIAL_REPORT != first
    assert "eerste" in first.read_text(encoding="utf-8")


def test_without_an_alarm_there_is_no_alarms_heading(tmp_path,
                                                     monkeypatch) -> None:
    """B537: a reassurance under the heading 'Alarms' reads as an
    alarm."""
    from modules import test_panel
    monkeypatch.setattr(test_panel, "_SANITY_ALARMS", [])
    assert test_panel.alarm_rows() == []
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "uitslag", 1.0, 1.0,
                                test_panel.alarm_rows())
    text = test_panel.TRIAL_REPORT.read_text(encoding="utf-8")
    assert "Alarm" not in text and "* " not in text


def test_an_alarm_lands_as_a_table_in_the_report(tmp_path,
                                                 monkeypatch) -> None:
    from modules import test_panel
    monkeypatch.setattr(test_panel, "_SANITY_ALARMS",
                        [{"project": "Lied R", "models": "B213",
                          "counts": {"nieuw": 3}}])
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "verslagen")
    test_panel.start_trial_report(["1.5.5"], "alle projecten", "0.150.0")
    test_panel.add_trial_result("1.5.5", "Meetlat", "uitslag", 1.0, 1.0,
                                test_panel.alarm_rows())
    text = test_panel.TRIAL_REPORT.read_text(encoding="utf-8")
    assert "| Lied R | B213 | nieuw 3 |" in text
    assert "* |" not in text          # no table inside bullets
    assert "\n* \n" not in text       # and no empty bullet


def test_the_first_of_a_packed_run_does_keep_its_start() -> None:
    """B535: the run is packed, but of the copies the FIRST is where the
    singing plausibly began - and that is exactly the shape B522 was
    built for: a sound start with an end that runs on into the
    instrumental."""
    lines = tuple([
        _anchor(0, "loop niet zo", 100.0, 122.0),    # 22 s against 3.4 s
        _anchor(1, "loop niet zo", 101.2, 102.2),
        _anchor(2, "loop niet zo", 102.4, 103.4),
    ] + [_anchor(3 + i, "en verder gaat het lied",
                 130.0 + 4.0 * i, 133.0 + 4.0 * i) for i in range(6)])
    suspect, overlong = timing.implausible_and_overlong(lines, 3.4, {})
    assert 0 in suspect and 0 in overlong


def test_the_copy_is_made_before_the_run_writes() -> None:
    """The call sits at the START of 1.5.10 and 1.5.11, not at the end -
    otherwise it does not help when the run is broken off."""
    import inspect
    from modules import test_panel
    for function in (test_panel.big_trial, test_panel.heavy_trial):
        source = inspect.getsource(function)
        assert "keep_dated_copy(report_file)" in source
        assert (source.index("keep_dated_copy(report_file)")
                < source.index("def write_report()")), function.__name__


# --------------------------------------------------------------------------
# B536 - the shipped setting, and what does and does not ship with it
# --------------------------------------------------------------------------

def test_the_shipped_setting_is_exactly_these_two(monkeypatch) -> None:
    """What the user really gets when he starts the app. The whole test
    run goes with everything on (otherwise half the hallucination tests
    would test code that no longer runs), so this setting is seen
    nowhere else."""
    from modules import model_register
    model_register.apply_settings({})
    off = model_register.apply_disabled()
    assert sorted(off) == ["B258/B285", "B380"]


def _segment(index, text, start, end, words, confidence=0.8):
    from modules.whisper import Segment, Word
    return Segment(index, text, start, end,
                   tuple(Word(w, s, e, confidence) for w, s, e in words))


def _invented_line():
    """The real Lied_S hallucination: no match in the lyrics and an
    erratic word confidence (0.34 the lowest)."""
    from modules.whisper import Segment, Word
    return Segment(91, "Heerlijke Heer, Heerlijke Heer", 60.0, 63.0, (
        Word("Heerlijke", 60.0, 61.0, 0.34),
        Word("Heer", 61.0, 62.0, 0.48),
        Word("Heerlijke", 62.0, 62.5, 0.72),
        Word("Heer", 62.5, 63.0, 0.99),
    ))


def _ordinary_segments(count=12):
    return [_segment(i, "woord", 10.0 + i, 10.4 + i,
                     [("woord", 10.0 + i, 10.4 + i)]) for i in range(count)]


def test_the_fixed_list_and_the_stuck_loop_keep_running() -> None:
    """B536: B141 and B514 live in the same function as B258/B285 but
    have nothing to do with it, and were measured separately. They may
    not go along when the switch is flipped."""
    from modules import model_register, pipeline
    from modules.song_text import LyricWord

    lyrics = tuple(LyricWord(i, w, 0) for i, w in enumerate(
        "ik heb veel bier getapt maar ook veel bier gemorst".split()))
    music = _segment(90, "MUZIEK", 200.0, 208.0,
                     [("MUZIEK", 200.0, 208.0)])
    loop = _segment(99, "D.O." * 55, 116.8, 143.8,
                    [("D.O." * 55, 116.8, 143.8)])
    invented = _invented_line()
    segments = tuple(_ordinary_segments() + [music, loop, invented])

    model_register.apply_settings({})
    model_register.apply_disabled()               # the shipped setting
    try:
        left = pipeline._filter_hallucinations(segments, lyrics)
    finally:
        model_register.restore_all()
    texts = [s.text for s in left]
    assert "MUZIEK" not in texts                  # B141 keeps running
    assert loop.text not in texts                 # B514 keeps running
    assert invented.text in texts                 # B285 is off


def test_with_the_switch_on_the_invented_line_does_drop() -> None:
    from modules import pipeline
    from modules.song_text import LyricWord
    lyrics = tuple(LyricWord(i, w, 0) for i, w in enumerate(
        "ik heb veel bier getapt maar ook veel bier gemorst".split()))
    invented = _invented_line()
    left = pipeline._filter_hallucinations(
        tuple(_ordinary_segments() + [invented]), lyrics)
    assert invented.text not in [s.text for s in left]


def test_an_order_builds_on_the_pipeline_that_really_runs() -> None:
    """B536: an order is a rearrangement of the pipeline as the user
    runs it. So it takes the function that is on the module NOW -
    reaching past a model switch would measure a pipeline nobody has."""
    from modules import model_orders, model_register, pipeline

    model_register.apply_settings({})
    model_register.apply_disabled()               # the shipped setting
    try:
        now = pipeline._filter_hallucinations
        built = model_orders.targets("B307 vóór B285")
        assert built and built[0][1] == "_clean_segments_and_alignment"
        in_the_closure = [cell.cell_contents
                          for cell in built[0][2].__closure__ or ()]
        assert now in in_the_closure
    finally:
        model_register.restore_all()


def test_an_order_over_a_disabled_model_is_not_measured() -> None:
    """And that is the other side: if a step the order moves is off,
    there is nothing to rearrange. Then it should say "skipped" and not
    a tidy 0.00 s for something that was never attempted - exactly the
    measuring error B529 cleared up one layer down."""
    from modules import model_orders, model_register

    model_register.apply_settings({})
    assert model_orders.measurable("B307 vóór B285") == ("B258/B285",)
    model_register.apply_settings({"B258/B285": True})
    try:
        assert model_orders.measurable("B307 vóór B285") == ()
    finally:
        model_register.apply_settings({})


def test_every_order_names_the_models_it_moves() -> None:
    """Without that link nobody can see that an order is empty."""
    from modules import model_orders, model_register

    for name in model_orders.names():
        codes = model_orders.models_for(name)
        assert codes, name
        for code in codes:
            assert model_register.by_code(code) is not None, code


def test_singing_and_music_drops_with_the_switch_off_too() -> None:
    """B536: "ZANG EN MUZIEK" is the example the B258 explanation opens
    with. With the switch off "zang" no longer counts - but then it has
    to fall away as a filler word and not act as a free pass, otherwise
    the segment survives while a bare "MUZIEK" is thrown out."""
    from modules import model_register, pipeline
    from modules.song_text import LyricWord

    lyrics = tuple(LyricWord(i, w, 0) for i, w in enumerate(
        "ik heb veel bier getapt maar ook veel bier gemorst".split()))
    together = _segment(90, "ZANG EN MUZIEK", 229.9, 241.0,
                        [("ZANG", 229.9, 231.3), ("EN", 231.3, 232.7),
                         ("MUZIEK", 232.7, 241.0)], confidence=0.98)
    bare = _segment(92, "MUZIEK", 250.0, 258.0,
                    [("MUZIEK", 250.0, 258.0)], confidence=0.98)
    segments = tuple(_ordinary_segments() + [together, bare])

    model_register.apply_settings({})
    model_register.apply_disabled()
    try:
        left = [s.text for s in pipeline._filter_hallucinations(segments,
                                                               lyrics)]
    finally:
        model_register.restore_all()
    assert "MUZIEK" not in left and "ZANG EN MUZIEK" not in left


def test_a_song_really_about_singing_keeps_its_line() -> None:
    """The other way round: "zang" may not be a hallucination signal
    while B258 is off, not even by a detour."""
    from modules import model_register, pipeline
    from modules.song_text import LyricWord

    lyrics = tuple(LyricWord(i, w, 0) for i, w in enumerate(
        "wij gaan zingen want de zang zit in ons bloed".split()))
    line = _segment(90, "de zang zit in ons bloed", 100.0, 103.0,
                    [("de", 100.0, 100.4), ("zang", 100.4, 101.0),
                     ("zit", 101.0, 101.4), ("in", 101.4, 101.8),
                     ("ons", 101.8, 102.2), ("bloed", 102.2, 103.0)],
                    confidence=0.95)
    segments = tuple(_ordinary_segments() + [line])
    model_register.apply_settings({})
    model_register.apply_disabled()
    try:
        left = [s.text for s in pipeline._filter_hallucinations(segments,
                                                               lyrics)]
    finally:
        model_register.restore_all()
    assert "de zang zit in ons bloed" in left
