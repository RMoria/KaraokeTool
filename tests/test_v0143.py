"""Tests for v0.143.0.

B484 an inline ``[bg]`` piece marks its own words instead of the whole
sentence, B485 that piece stays part of its line - visible in the
editors, allowed to overlap, never in the render - and B486 it gets its
own attempt at an anchor.
"""

from __future__ import annotations

import inspect
from pathlib import Path



from modules import karaoke_text, song_text, timing, video


# --------------------------------------------------------------------------
# B484 - the marking belongs to the words, not to the line
# --------------------------------------------------------------------------

def _lyrics(tmp_path: Path, text: str):
    path = tmp_path / song_text.LYRICS_FILENAME
    path.write_text(text, encoding="utf-8")
    return song_text.load_lyrics(path)


def test_a_background_tail_leaves_the_rest_of_the_sentence_alone(
        tmp_path) -> None:
    """Dit is de fout waardoor twaalf regels van Lied R uit de originele
    baan verdwenen: de hele zin werd achtergrondzang."""
    words = _lyrics(tmp_path, "een twee drie [bg]vier[/bg]\n")
    assert [(w.text, w.bg) for w in words] == [
        ("een", False), ("twee", False), ("drie", False), ("vier", True)]


def test_a_background_head_does_the_same(tmp_path) -> None:
    words = _lyrics(tmp_path, "[bg]vier[/bg] een twee\n")
    assert [w.bg for w in words] == [True, False, False]


def test_a_background_piece_in_the_middle_marks_only_itself(
        tmp_path) -> None:
    words = _lyrics(tmp_path, "een [bg]vier[/bg] twee\n")
    assert [w.bg for w in words] == [False, True, False]


def test_a_whole_background_line_is_still_a_whole_background_line(
        tmp_path) -> None:
    words = _lyrics(tmp_path, "[bg]alles hier[/bg]\ngewoon\n")
    assert [w.bg for w in words] == [True, True, False]


def test_a_background_block_still_runs_over_several_lines(
        tmp_path) -> None:
    words = _lyrics(tmp_path, "[bg]\neerste\ntweede\n[/bg]\ngewoon\n")
    assert [w.bg for w in words] == [True, True, False]


def _karaoke(tmp_path: Path, text: str):
    path = tmp_path / karaoke_text.FILENAME
    path.write_text(text, encoding="utf-8")
    return karaoke_text.parse_lines(path)


def test_the_karaoke_side_marks_the_words_too(tmp_path) -> None:
    lines = _karaoke(tmp_path, "Dus laat maar komen [bg]LIED_R[/bg]\n")
    assert len(lines) == 1
    assert lines[0].bg is False, "de zin zelf is geen achtergrondzang"
    assert lines[0].bg_words == frozenset({4})
    assert lines[0].text == "Dus laat maar komen LIED_R"


def test_a_karaoke_line_that_is_only_background_keeps_its_flag(
        tmp_path) -> None:
    lines = _karaoke(tmp_path, "[bg]LIED_R[/bg]\n")
    assert lines[0].bg is True and not lines[0].bg_words


def test_crowd_and_background_can_share_a_line(tmp_path) -> None:
    """De woordnummers worden op de uiteindelijke lijst geteld, dus de
    twee markeringen lopen niet uit elkaar."""
    lines = _karaoke(tmp_path,
                     "een [crowd]twee[/crowd] drie [bg]vier[/bg]\n")
    assert lines[0].crowd_words == frozenset({1})
    assert lines[0].bg_words == frozenset({3})
    assert lines[0].text == "een twee drie vier"


def test_the_line_numbers_do_not_shift(tmp_path) -> None:
    """Het bg-stuk blijft onderdeel van zijn regel, dus een bestaande
    timing.json blijft geldig."""
    lines = _karaoke(tmp_path,
                     "een\ntwee [bg]bg[/bg]\ndrie\n")
    assert [line.index for line in lines] == [0, 1, 2]
    assert [line.text for line in lines] == ["een", "twee bg", "drie"]


# --------------------------------------------------------------------------
# B485 - part of its line, out of the render, allowed to overlap
# --------------------------------------------------------------------------

def test_the_syllables_of_the_piece_are_marked() -> None:
    lines = (timing.TimedLine(
        index=0, text="een bg", crowd=False,
        syllables=(timing.Syllable("een", 0.0, 1.0),
                   timing.Syllable(" bg", 1.0, 2.0))),)

    class _Text:
        index, crowd_words, bg_words = 0, frozenset(), frozenset({1})
        text = "een bg"

    out = timing.apply_inline_crowd(lines, (_Text(),))
    assert [s.bg for s in out[0].syllables] == [False, True]


def test_the_piece_does_not_decide_where_the_sentence_ends() -> None:
    """Anders sleept het bg-stuk de hele zin mee zodra het over zijn buur
    heen wordt gelegd."""
    line = timing.TimedLine(
        index=0, text="een bg", crowd=False,
        syllables=(timing.Syllable("een", 1.0, 2.0),
                   timing.Syllable(" bg", 2.0, 9.0, bg=True)))
    assert line.start == 1.0 and line.end == 2.0
    # De volledige tijd blijft opvraagbaar: de muziek moet er wel
    # lang genoeg voor doorlopen.
    assert line.full_end == 9.0


def test_a_line_that_is_all_background_keeps_its_own_times() -> None:
    line = timing.TimedLine(
        index=0, text="bg", crowd=False,
        syllables=(timing.Syllable("bg", 3.0, 4.0, bg=True),))
    assert line.start == 3.0 and line.end == 4.0


def test_the_render_leaves_the_piece_out() -> None:
    line = timing.TimedLine(
        index=0, text="een bg", crowd=False,
        syllables=(timing.Syllable("een", 0.0, 1.0),
                   timing.Syllable(" bg", 1.0, 2.0, bg=True)))
    assert [s.text for s in video._sung_syllables(line)] == ["een"]


def test_a_line_without_anything_else_is_not_rendered_empty() -> None:
    line = timing.TimedLine(
        index=0, text="bg", crowd=False,
        syllables=(timing.Syllable("bg", 0.0, 1.0, bg=True),))
    assert len(video._sung_syllables(line)) == 1


def test_the_width_and_the_height_count_without_the_piece() -> None:
    # B541: het meten zelf staat in ``_measure_line_height``; de naam
    # ernaast onthoudt alleen de uitkomst voor deze render.
    source = inspect.getsource(video._measure_line_height)
    assert "_sung_syllables(line)" in source
    assert "_sung_syllables(line)" in inspect.getsource(video._rows_of)
    assert "_sung_syllables(line)" in inspect.getsource(video._fit_body_font)


def test_the_refit_keeps_its_hands_off_the_piece() -> None:
    """De auto-fit werkt binnen het venster van de zin en zou de
    achtergrondzang daar weer in trekken."""
    line = timing.TimedLine(
        index=0, text="een bg", crowd=False,
        syllables=(timing.Syllable("een", 1.0, 2.0),
                   timing.Syllable(" bg", 2.0, 9.0, bg=True)))
    out = timing.apply_spans(line, [(0.5, 1.5), (1.5, 2.5)])
    assert (out.syllables[0].start, out.syllables[0].end) == (0.5, 1.5)
    assert (out.syllables[1].start, out.syllables[1].end) == (2.0, 9.0)


def test_the_editor_measures_the_sentence_without_the_piece() -> None:
    from modules import timing_editor

    line = {"syllables": [{"text": "een", "start": 1.0, "end": 2.0},
                          {"text": " bg", "start": 2.0, "end": 9.0,
                           "bg": True}]}
    assert timing_editor._line_span(line) == (1.0, 2.0)


def test_the_file_carries_the_mark_and_an_older_one_still_reads(
        tmp_path) -> None:
    line = timing.TimedLine(
        index=0, text="een bg", crowd=False,
        syllables=(timing.Syllable("een", 0.0, 1.0),
                   timing.Syllable(" bg", 1.0, 2.0, bg=True)))
    path = tmp_path / "timing.json"
    timing.save_timing([line], path)
    back = timing.load_timing(path)
    assert [s.bg for s in back[0].syllables] == [False, True]
    # Een bestand van vóór deze versie heeft het veld niet.
    text = path.read_text(encoding="utf-8").replace('"bg": true', '"bg": false')
    path.write_text(text.replace('"bg": false,', ""), encoding="utf-8")
    assert all(not s.bg for s in timing.load_timing(path)[0].syllables)


# --------------------------------------------------------------------------
# B486 - the piece may become an anchor
# --------------------------------------------------------------------------

def _source_of(module) -> str:
    """De broncode van het bestand zelf.

    Bewust niet via ``inspect.getsource(functie)``: een andere test kan
    de functie op de module vervangen hebben, en dan lees je die.
    """
    return Path(module.__file__).read_text(encoding="utf-8")


def test_background_words_get_their_own_attempt() -> None:
    source = _source_of(song_text)
    assert "fillable = [i for i in range(len(lyrics)) if i in skip]" in source
    assert "if i in skip and not lyrics[i].bg]" not in source


def test_they_still_stay_out_of_the_ordered_matching() -> None:
    """Ze klinken tegelijk met de hoofdstem en zouden daar de woorden van
    de hoofdstem inpikken."""
    source = _source_of(song_text)
    assert "if w.bg or (skip_filler" in source


# --------------------------------------------------------------------------
# The original lane, end to end on the user's own text
# --------------------------------------------------------------------------

def test_every_sentence_of_the_real_song_keeps_its_lead(tmp_path) -> None:
    """Twaalf regels van Lied R hadden een achtergrondstaart en vielen
    daardoor helemaal weg."""
    text = (
        "I'm not that easy to tame\n"
        "Noon gam-go, ha-na, dool, set [bg]Twee-uh[/bg]\n"
        "Arе you not entertained? [bg]No[/bg]\n"
        "All gas, no brakes, yeah [bg]Woo, woo, woo[/bg]\n"
    )
    words = _lyrics(tmp_path, text)
    per_line = {}
    for word in words:
        per_line.setdefault(word.line, []).append(word.bg)
    assert len(per_line) == 4
    assert all(any(not bg for bg in flags) for flags in per_line.values()), \
        "elke regel houdt zijn eigen woorden"


def test_the_original_lane_shows_the_piece_but_does_not_time_it() -> None:
    from modules import pipeline

    source = inspect.getsource(pipeline._original_lines_detailed)
    assert "bg_text.setdefault(word.lyric.line" in source
    assert 'bg_text.get(ln, [])' in source


# --------------------------------------------------------------------------
# What the critical re-read found
# --------------------------------------------------------------------------

def test_the_editor_keeps_the_mark_when_it_saves() -> None:
    """Eén keer opslaan wiste de markering, en daarna stond het stuk
    gewoon in de video."""
    from modules import timing_editor

    line = timing.TimedLine(
        index=0, text="een bg", crowd=False,
        syllables=(timing.Syllable("een", 0.0, 1.0),
                   timing.Syllable(" bg", 1.0, 2.0, bg=True)))
    back = timing_editor._from_dict(timing_editor._to_dict(line))
    assert [s.bg for s in back.syllables] == [False, True]


def test_an_empty_output_folder_is_not_a_folder_full_of_orphans(
        tmp_path) -> None:
    """De app maakt ``output/settings`` zelf aan, dus "de map bestaat"
    zegt niets."""
    from modules import filesystem

    (tmp_path / "input" / "Een Lied").mkdir(parents=True)
    out = tmp_path / "uit"
    (out / "settings").mkdir(parents=True)
    assert filesystem.prune_orphan_projects(tmp_path, out) == []
    assert (tmp_path / "input" / "Een Lied").exists()


def test_never_all_of_them_at_once(tmp_path) -> None:
    """Dat álles tegelijk een wees is, is geen opruimklus maar een teken
    dat er tegen de verkeerde map gemeten wordt."""
    from modules import filesystem

    for naam in ("Een", "Twee", "Drie"):
        (tmp_path / "input" / naam).mkdir(parents=True)
    out = tmp_path / "output"
    (out / "Vier").mkdir(parents=True)
    assert filesystem.prune_orphan_projects(tmp_path, out) == []
    assert len(list((tmp_path / "input").iterdir())) == 3
    # Eén wees tussen projecten die er wél zijn wordt gewoon opgeruimd.
    (out / "Een").mkdir()
    (out / "Twee").mkdir()
    assert filesystem.prune_orphan_projects(tmp_path, out) == ["Drie"]


def test_a_marker_does_what_it_says_wherever_it_stands(tmp_path) -> None:
    """Een aangeplakte marker werd apart afgehandeld vóór de lus, en dan
    werd "Tonight[/bg] my dear" van begin tot eind achtergrondzang."""
    words = _lyrics(tmp_path, "[bg]\naaa\nbbb[/bg] ccc\nddd\n")
    assert [(w.text, w.bg) for w in words] == [
        ("aaa", True), ("bbb", True), ("ccc", False), ("ddd", False)]


def test_the_two_readers_say_the_same_thing(tmp_path) -> None:
    """Songtekst en karaoketekst moeten elke schrijfwijze gelijk lezen;
    ze voeden dezelfde koppeling."""
    for text in ("een twee [bg]drie[/bg]\n",
                 "[bg]een[/bg] twee drie\n",
                 "een [bg]twee[/bg] drie\n",
                 "[bg]\naaa\nbbb\n[/bg]\nccc\n",
                 "[bg]aaa\nbbb\n[/bg]\nccc\n",
                 "[bg]\naaa\nbbb[/bg] ccc\nddd\n",
                 "[bg]alles hier[/bg]\ngewoon\n",
                 "a [bg]b[/bg] c [bg]d[/bg] e\n",
                 "een [BG]twee[/BG] drie\n"):
        (tmp_path / song_text.LYRICS_FILENAME).write_text(text,
                                                          encoding="utf-8")
        (tmp_path / karaoke_text.FILENAME).write_text(text, encoding="utf-8")
        from_lyrics = [(w.text, w.bg)
                       for w in song_text.load_lyrics(
                           tmp_path / song_text.LYRICS_FILENAME)]
        from_karaoke = []
        for line in karaoke_text.parse_lines(tmp_path / karaoke_text.FILENAME):
            for position, word in enumerate(line.text.split()):
                from_karaoke.append(
                    (word, line.bg or (position in line.bg_words)))
        assert from_lyrics == from_karaoke, text


def test_the_energy_timing_leaves_the_piece_where_it_is() -> None:
    line = timing.TimedLine(
        index=0, text="a b c bg", crowd=False,
        syllables=(timing.Syllable("a", 10.0, 11.0),
                   timing.Syllable(" b", 11.0, 12.0),
                   timing.Syllable(" c", 12.0, 13.0),
                   timing.Syllable(" bg", 13.0, 14.0, bg=True)))
    out = timing.distribute_over_windows(line, [(10.0, 11.5), (12.0, 13.0)])
    assert (out.syllables[-1].start, out.syllables[-1].end) == (13.0, 14.0)
    # En de zin zelf verliest zijn tijd niet aan het stuk.
    assert out.end <= 13.0


def test_the_marking_is_read_back_from_the_text() -> None:
    """Markers toevoegen aan een liedje dat al getimed is verandert geen
    letter aan de zin, dus niets merkte het."""
    from modules import pipeline

    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    assert "def mark_inline_pieces(" in source
    assert "mark_inline_pieces(context, timing_module.load_timing(path))" \
        in source
    gui_source = Path(
        __import__("modules.gui", fromlist=["x"]).__file__).read_text(
            encoding="utf-8")
    assert gui_source.count("pipeline.mark_inline_pieces(") == 2


def test_the_sentence_keeps_its_own_words() -> None:
    """De bg-woorden erbij plakken liet het woordaantal afwijken van de
    gemeten woordvensters, en dan valt de klemtooneditor terug op
    gelijkmatig verdelen."""
    from modules import pipeline

    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    assert '"text": " ".join(per_line_words[ln]),' in source
    assert '"bg_text": " ".join(bg_text.get(ln, [])),' in source
    assert '"bg": line.get("bg_text", ""),' in source


def test_a_loose_crowd_line_keeps_its_own_row_in_the_lane() -> None:
    from modules import gui

    source = Path(gui.__file__).read_text(encoding="utf-8")
    assert source.count("and not _mirrored(karaoke_index)") == 1
    assert source.count("and not _mirrored_row(k)") == 1


def test_the_piece_does_not_count_as_a_held_note() -> None:
    line = timing.TimedLine(
        index=0, text="a b c bg", crowd=False,
        syllables=(timing.Syllable("a", 0.0, 0.2),
                   timing.Syllable(" b", 0.2, 0.4),
                   timing.Syllable(" c", 0.4, 0.6),
                   timing.Syllable(" bg", 0.6, 6.0, bg=True)))
    out = timing.mark_held([line])[0]
    assert not any(s.held for s in out.syllables)


def test_the_music_runs_long_enough_for_the_piece() -> None:
    source = Path(video.__file__).read_text(encoding="utf-8")
    assert "max(line.full_end for line in ordered)" in source


def test_the_mark_is_not_laid_on_a_line_that_no_longer_matches() -> None:
    """Woordnummers uit de tekst op een timing leggen werkt alleen zolang
    de twee hetzelfde zeggen; anders verdwijnt er een woord uit beeld."""
    lines = (timing.TimedLine(
        index=0, text="een bg", crowd=False,
        syllables=(timing.Syllable("een", 0.0, 1.0),
                   timing.Syllable(" bg", 1.0, 2.0))),)

    class _Text:
        index, crowd_words, bg_words = 0, frozenset(), frozenset({3})
        text = "een twee drie bg"

    out = timing.apply_inline_crowd(lines, (_Text(),))
    assert not any(s.bg for s in out[0].syllables)


def test_the_phonetic_step_keeps_the_mark() -> None:
    """Die stap draait op élke verse timing, dus zonder dit stond er in
    geen enkel bestand een markering."""
    source = Path(timing.__file__).read_text(encoding="utf-8")
    assert "achtergrond = any(s.bg for s in group)" in source
    assert source.count("crowd=crowd, bg=achtergrond)") == 2


def test_the_held_notes_are_weighed_again_after_the_mark_is_back() -> None:
    from modules import pipeline

    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    assert "return timing_module.mark_held(marked)" in source


def test_the_full_end_is_the_last_one_in_time() -> None:
    line = timing.TimedLine(
        index=0, text="bg een", crowd=False,
        syllables=(timing.Syllable("bg", 1.0, 9.0, bg=True),
                   timing.Syllable(" een", 2.0, 3.0)))
    assert line.end == 3.0
    assert line.full_end == 9.0


def test_the_reflow_leaves_the_piece_alone() -> None:
    line = timing.TimedLine(
        index=0, text="a b bg", crowd=False,
        syllables=(timing.Syllable("a", 1.0, 2.0),
                   timing.Syllable(" b", 2.0, 3.0),
                   timing.Syllable(" bg", 3.0, 4.0, bg=True)))
    out = timing._reflow_line(line, 5.0, 8.0)
    assert (out.syllables[-1].start, out.syllables[-1].end) == (3.0, 4.0)
    assert out.start == 5.0 and out.end == 8.0
