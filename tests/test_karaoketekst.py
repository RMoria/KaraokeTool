"""Tests voor modules.karaoketekst (crowd-markering)."""

from __future__ import annotations

from pathlib import Path

from modules.karaoke_text import (PAUSE_TOKEN, apply_pause, is_pause,
                                   parse_lines)


def test_parse_lines_with_crowd_block(tmp_path: Path) -> None:
    path = tmp_path / "karaoketekst.txt"
    path.write_text(
        "Rood Witte Zangers, vooraan in de polonaise\n"
        "\n"
        "[crowd]\n"
        "La-la-la...\n"
        "Hey...\n"
        "[/crowd]\n"
        "En dan zingen wij weer verder\n",
        encoding="utf-8")
    lines = parse_lines(path)
    assert [line.text for line in lines] == [
        "Rood Witte Zangers, vooraan in de polonaise",
        "La-la-la...", "Hey...", "En dan zingen wij weer verder"]
    assert [line.crowd for line in lines] == [False, True, True, False]
    assert [line.index for line in lines] == [0, 1, 2, 3]


def test_inline_pause_blijft_in_zelfde_regel(tmp_path: Path) -> None:
    """B107: [pause]/[pauze] wordt een los pauze-teken binnen dezelfde zin."""
    path = tmp_path / "karaoketekst.txt"
    path.write_text(
        "Want as de zangers [pause] weer gaan hossen\n"
        "[crowd]\n"
        "Oehoor [pauze] en\n"
        "[/crowd]\n",
        encoding="utf-8")
    lines = parse_lines(path)
    # Nog steeds twee logische regels (de pauze splitst NIET in een nieuwe).
    assert len(lines) == 2
    assert lines[0].text == f"Want as de zangers {PAUSE_TOKEN} weer gaan hossen"
    assert lines[0].crowd is False
    # Ook binnen een crowd-blok wordt de pauze omgezet.
    assert lines[1].text == f"Oehoor {PAUSE_TOKEN} en"
    assert lines[1].crowd is True


def test_apply_pause_en_is_pause() -> None:
    """B107: hulpuncties zetten om en herkennen het pauze-teken."""
    assert apply_pause("a [pause] b") == f"a {PAUSE_TOKEN} b"
    assert apply_pause("a[pauze]b") == f"a {PAUSE_TOKEN} b"
    assert apply_pause("geen pauze hier") == "geen pauze hier"
    assert is_pause(PAUSE_TOKEN) is True
    assert is_pause(" … ") is True
    assert is_pause("word") is False


def test_comment_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "karaoketekst.txt"
    path.write_text("# Intro\nEcht zingen\n# Couplet 2\n",
                    encoding="utf-8")
    lines = parse_lines(path)
    assert [line.text for line in lines] == ["Echt zingen"]


def test_parse_lines_case_insensitive_and_unclosed(tmp_path: Path) -> None:
    path = tmp_path / "karaoketekst.txt"
    path.write_text("[CROWD]\nHo...\n", encoding="utf-8")
    lines = parse_lines(path)
    assert lines[0].crowd is True  # onafgesloten blok: waarschuwing in log


def test_inline_crowd_blijft_in_de_zin(tmp_path: Path) -> None:
    """B179a: inline crowd blijft in de logische zin; de crowd-woorden zijn
    gemarkeerd (rood in de render), de zin is niet crowd op regelniveau."""
    path = tmp_path / "karaoketekst.txt"
    path.write_text("G Z R, G Z R [crowd]Waertje![/crowd]\n",
                    encoding="utf-8")
    lines = parse_lines(path)
    assert len(lines) == 1
    assert lines[0].text == "G Z R, G Z R Waertje!"
    assert lines[0].crowd is False
    # 'Waertje!' is het 7e woord (index 6) en is crowd.
    assert lines[0].crowd_words == frozenset({6})


def test_hele_crowd_regel_is_regelcrowd(tmp_path: Path) -> None:
    """B179b: een regel die volledig [crowd] is, is crowd op regelniveau."""
    path = tmp_path / "karaoketekst.txt"
    path.write_text("Zang hier\n[crowd]Oeh![/crowd]\n", encoding="utf-8")
    lines = parse_lines(path)
    assert [(line.text, line.crowd) for line in lines] == [
        ("Zang hier", False), ("Oeh!", True)]
    assert lines[1].crowd_words == frozenset()


def test_glued_crowd_markers_open_and_close_block(tmp_path: Path) -> None:
    """B74: [crowd] aan het begin en [/crowd] aan het eind (aan de tekst
    geplakt) dekken het hele blok."""
    path = tmp_path / "karaoketekst.txt"
    path.write_text(
        "[crowd]La-la 1\n"
        "La-la 2\n"
        "La-la 3\n"
        "La-la 4[/crowd]\n",
        encoding="utf-8")
    lines = parse_lines(path)
    assert [line.text for line in lines] == [
        "La-la 1", "La-la 2", "La-la 3", "La-la 4"]
    assert all(line.crowd for line in lines)
