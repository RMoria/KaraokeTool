"""The hints Whisper gets, as variants for 1.5.13 (v1.0.13, B583).

Shipped as they were: every cut piece gets the whole text (B424 found
that the better hint on long pieces), and "Listen again" gets the whole
lines of its place. The other ways exist so the night trial can measure
them on short pieces.
"""
from __future__ import annotations


from modules import listen_again as again
from modules import pipeline, song_text, whisper
from modules.config import default_config
from modules.filesystem import ProjectPaths, ProjectStore, ensure_directories


def test_the_three_hints_of_listening_again() -> None:
    area = again.Area(2.0, 9.0, ["de", "fiets"], "de fiets staat bij de deur",
                      before="zon", after="het")
    assert again.hint_for(area) == "de fiets staat bij de deur"
    assert again.hint_for(area, "expected") == "de fiets"
    assert again.hint_for(area, "anchored") == \
        "zon de fiets staat bij de deur het"
    assert again.HINT == "lines" and set(again.HINTS) == {
        "lines", "expected", "anchored"}


def test_an_area_knows_the_anchors_around_it() -> None:
    transcript = [("ik", 1.0, 1.3), ("stad", 20.0, 20.5)]
    words = [{"index": 0, "text": "ik", "line": 0, "transcript_indices": [0],
              "sim": 1.0, "status": "coupled"},
             {"index": 1, "text": "fiets", "line": 1,
              "transcript_indices": [], "status": "no_match"},
             {"index": 2, "text": "stad", "line": 2,
              "transcript_indices": [1], "sim": 1.0, "status": "coupled"}]
    area, = again.problem_areas({"transcript": transcript, "words": words},
                                {1: "de fiets"}, 30.0)
    assert (area.before, area.after) == ("ik", "stad")


def _context(tmp_path):
    paths = ProjectPaths(root=tmp_path, song="Song_H")
    ensure_directories(paths)
    (paths.input_dir / song_text.LYRICS_FILENAME).write_text(
        "wij lopen door de stad\nhet regent op het plein\n",
        encoding="utf-8")
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


def _dicts(text, start, end):
    words = text.split()
    step = (end - start) / len(words)
    return {"index": 0, "text": text, "start": start, "end": end,
            "words": [{"text": w, "start": start + n * step,
                       "end": start + (n + 1) * step, "confidence": 0.9}
                      for n, w in enumerate(words)]}


def test_with_a_hint_per_piece_each_piece_gets_its_own_lines(
        tmp_path, monkeypatch) -> None:
    asked = []

    def fake_slice(audio_path, settings, start=0.0, end=None,
                   initial_prompt="", language_override=None,
                   cancelled=None):
        asked.append((start, end, initial_prompt))
        if end is None:
            return whisper.segments_from_dicts([
                _dicts("wij lopen door de stad", 1.0, 4.0),
                _dicts("het regent op het plein", 21.0, 24.0)])
        return ()

    context = _context(tmp_path)
    monkeypatch.setattr(whisper, "transcribe_slice", fake_slice)
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: [(0.0, 5.0), (20.0, 25.0)])
    monkeypatch.setattr(pipeline, "lyric_keys", lambda c: frozenset())
    pipeline._transcribe_in_pieces(
        context, tmp_path / "x.wav", context.config.whisper, "GLOBAL", "nl",
        context.paths.output_dir / "original")

    wholes = [a for a in asked if a[1] is None]
    assert len(wholes) == 1, "the whole song is read once, not twice"
    pieces = [a for a in asked if a[1] is not None]
    assert pieces
    late = [prompt for start, _end, prompt in pieces if start >= 10.0]
    assert late and all("plein" in prompt and "stad" not in prompt
                        for prompt in late)


def test_shipped_the_pieces_get_the_whole_text(tmp_path, monkeypatch) -> None:
    from modules import model_register

    asked = []

    def fake_slice(audio_path, settings, start=0.0, end=None,
                   initial_prompt="", language_override=None,
                   cancelled=None):
        asked.append(initial_prompt)
        return ()

    context = _context(tmp_path)
    monkeypatch.setattr(whisper, "transcribe_slice", fake_slice)
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: [(0.0, 5.0), (20.0, 25.0)])
    monkeypatch.setattr(pipeline, "lyric_keys", lambda c: frozenset())
    model_register.apply_settings({})
    model_register.apply_disabled()
    try:
        pipeline._transcribe_in_pieces(
            context, tmp_path / "x.wav", context.config.whisper, "GLOBAL",
            "nl", context.paths.output_dir / "original")
    finally:
        model_register.restore_all()
    assert asked and set(asked) == {"GLOBAL"}
