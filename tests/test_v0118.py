"""Tests voor v0.118.0: B372 t/m B374.

B372 het gereedschap ``whisper_probe`` struikelde meteen: het zette
     ``device: "auto"`` zelf om naar ``None`` in plaats van de functie
     van de app te gebruiken, en ctranslate2 wil daar een string.
B373 bij een dubbeling op een segmentgrens beslist voortaan de
     SONGTEKST in plaats van vier drempels.
B374 1.5.8 wijst de gaten aan (goedkoop), 1.5.11c meet welke instelling
     ze dicht (duur).

Het slotwoord van een Whisper-segment is gemeten half zo betrouwbaar als
elk ander woord: over 347 overgangen in veertien projecten gemiddeld
0.42 tegen 0.70, en een derde zit onder de 0.30. Dat is geen pech maar
bouw - op een vensterrand heeft de decoder geen rechtercontext - en
daarom staat er hier een rij tests omheen.
"""
from __future__ import annotations

import inspect
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, pipeline, test_history  # noqa: E402
from modules import test_panel  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

WORTEL = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _schoon(tmp_path, monkeypatch):
    monkeypatch.setattr(test_history, "HISTORY_FILE",
                        tmp_path / "testhistorie.json")
    monkeypatch.setattr(test_panel, "COMBINATION_REPORT",
                        tmp_path / "modelcombinaties.md")
    yield
    model_register.restore_all()
    model_register.apply_settings({})


def _woord(tekst, start, eind, zekerheid=0.5):
    from modules.whisper import Word
    return Word(text=tekst, start=start, end=eind, confidence=zekerheid)


def _segment(woorden):
    from modules.whisper import Segment
    return Segment(index=0, text=" ".join(w.text for w in woorden),
                   start=woorden[0].start, end=woorden[-1].end,
                   words=tuple(woorden))


def _lyrics(zin: str):
    from modules.song_text import LyricWord
    return tuple(LyricWord(text=w, index=n, line=0, bg=False)
                 for n, w in enumerate(zin.split()))


# --------------------------------------------------------------------------
# B372 - het gereedschap start weer
# --------------------------------------------------------------------------

def test_de_proef_gebruikt_de_apparaatkeuze_van_de_app() -> None:
    """Eigen omzetting gaf ``device=None`` door; ctranslate2 wil een str."""
    bron = (WORTEL / "tools" / "whisper_probe.py").read_text(encoding="utf-8")
    # B419: het model komt nu via ``whisper._load_model``, en die doet de
    # apparaatkeuze zelf - nog steeds de keuze van de app, en nu ook met
    # de modelcache erachter.
    assert "whisper._load_model(settings)" in bron
    assert "WhisperModel(settings.model" not in bron
    assert "device=None if" not in bron


def test_de_apparaatkeuze_geeft_altijd_strings() -> None:
    from modules import whisper
    from modules.config import WhisperSettings

    for instelling in (WhisperSettings(),
                       replace(WhisperSettings(), device="cpu",
                               compute_type="int8")):
        device, compute = whisper._resolve_device(instelling)
        assert isinstance(device, str) and device
        assert isinstance(compute, str) and compute


# --------------------------------------------------------------------------
# B373 - de songtekst beslist
# --------------------------------------------------------------------------

def test_een_doorgeknipt_woord_wordt_samengevoegd() -> None:
    """"so" staat niet dubbel in de tekst, dus twee keer "so" vlak na
    elkaar is één woord dat op de vensterrand is gesneden."""
    links = _segment([_woord("stand", 1.0, 1.4), _woord("so", 1.4, 1.46,
                                                        0.36)])
    rechts = _segment([_woord("so", 1.50, 1.74, 0.73),
                       _woord("close", 1.8, 2.2)])
    uit = pipeline._merge_boundary_duplicates(
        (links, rechts), lyrics=_lyrics("don't stand so close to me"))
    assert [w.text for s in uit for w in s.words] == ["stand", "so", "close"]
    # Het overgebleven woord begint waar het stuk begon.
    samen = [w for s in uit for w in s.words if w.text == "so"][0]
    assert samen.start == pytest.approx(1.4)


def test_een_echte_herhaling_blijft_staan() -> None:
    """"Sunday, Sunday" staat wél dubbel in de tekst - dan zijn twee
    "Sunday" naast elkaar geen fout maar de zang."""
    links = _segment([_woord("Bloody", 1.0, 1.4), _woord("Sunday", 1.4, 1.8)])
    rechts = _segment([_woord("Sunday", 1.9, 2.4), _woord("morning", 2.5, 3.0)])
    uit = pipeline._merge_boundary_duplicates(
        (links, rechts), lyrics=_lyrics("sunday sunday bloody sunday"))
    assert [w.text for s in uit for w in s.words] == \
        ["Bloody", "Sunday", "Sunday", "morning"]


def test_een_groot_gat_wordt_nooit_samengevoegd() -> None:
    """Ook als het woord niet dubbel in de tekst staat: drie seconden
    ertussen is een herhaling, geen doorgesneden woord."""
    links = _segment([_woord("een", 1.0, 1.4), _woord("so", 1.4, 1.8)])
    rechts = _segment([_woord("so", 4.8, 5.2), _woord("twee", 5.3, 5.7)])
    uit = pipeline._merge_boundary_duplicates(
        (links, rechts), lyrics=_lyrics("een so twee so"))
    assert sum(len(s.words) for s in uit) == 4


def test_verschillende_woorden_blijven_verschillend() -> None:
    links = _segment([_woord("een", 1.0, 1.4), _woord("taart", 1.4, 1.6)])
    rechts = _segment([_woord("maar", 1.7, 2.0), _woord("twee", 2.1, 2.4)])
    uit = pipeline._merge_boundary_duplicates(
        (links, rechts), lyrics=_lyrics("een taart maar twee"))
    assert sum(len(s.words) for s in uit) == 4


def test_zonder_songtekst_geldt_de_oude_voorzichtige_toets() -> None:
    """Het leespad mag niet omvallen op een project zonder songtekst."""
    links = _segment([_woord("stand", 1.0, 1.4), _woord("so", 1.4, 1.46,
                                                        0.36)])
    rechts = _segment([_woord("so", 1.50, 1.74, 0.73)])
    uit = pipeline._merge_boundary_duplicates((links, rechts))
    assert sum(len(s.words) for s in uit) == 3      # niets samengevoegd


def test_de_dubbelingen_uit_de_songtekst_worden_herkend() -> None:
    dubbel = pipeline._doubled_lyric_keys(
        _lyrics("ooh ooh don't stand so close to me"))
    from modules.cluster import phonetic_key
    assert phonetic_key("ooh") in dubbel
    assert phonetic_key("so") not in dubbel
    assert phonetic_key("stand") not in dubbel


def test_het_leespad_geeft_de_songtekst_mee() -> None:
    bron = inspect.getsource(pipeline.load_segments)
    assert "lyrics=_lyrics_for_boundaries(context)" in bron


def test_een_ontbrekende_songtekst_geeft_none(tmp_path) -> None:
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    assert pipeline._lyrics_for_boundaries(context) is None


# --------------------------------------------------------------------------
# B374 - eerst goedkoop aanwijzen, dan duur meten
# --------------------------------------------------------------------------

def test_de_gatdetector_is_geen_actie_meer() -> None:
    """B526: 1.5.8 is weg; zijn antwoord staat in het logboek.

    De actie zei altijd hetzelfde - dit project heeft een gat of niet -
    en dat weten veranderde nooit iets. Alleen 1.5.11 kan zeggen wat
    eraan te doen valt, en die meet het gat zelf.
    """
    assert not any(a.code == "1.5.8" for a in test_panel.ACTIONS)
    assert not hasattr(test_panel, "transcription_gaps")


def test_de_gatmeting_zelf_start_geen_whisper() -> None:
    """De hele winst: hij kost seconden in plaats van acht transcripties."""
    bron = inspect.getsource(test_panel._gaps_in)
    assert "WhisperModel" not in bron and "probe" not in bron
    assert "_original_vocal_windows" in bron


def test_een_klein_gat_telt_niet_mee() -> None:
    """Adem tussen twee regels is geen overgeslagen venster."""
    assert test_panel._GAP_MIN_S >= 5.0


def test_de_vensterproef_is_weg(qapp=None) -> None:
    """B512: 1.5.11c stond sinds v0.144.0 uit met zijn antwoord erbij en
    is nu weg. De zware bak zelf blijft één actie."""
    codes = [p.code for p in test_panel.HEAVY_TRIALS]
    assert "1.5.11c" not in codes
    assert not hasattr(test_panel, "window_trial")
    heavy = [a for a in test_panel.ACTIONS if a.heavy]
    assert [a.code for a in heavy] == ["1.5.11"]


def test_de_teksten_van_de_gatdetector_zijn_mee_opgeruimd() -> None:
    """B526: een weggehaalde actie laat geen teksten achter."""
    for sleutel in ("test_gaps", "test_gaps_hint", "test_gaps_intro",
                    "test_gaps_advice"):
        for taal in ("nl", "en"):
            assert sleutel not in TRANSLATIONS[taal], f"{sleutel} ({taal})"
