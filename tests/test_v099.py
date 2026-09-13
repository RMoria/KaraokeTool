"""Tests for v0.99.0: B313, B314 and B315.

B313 - skipped lyrics words get a time from the vocal stem.
B314 - the Whisper decoding options are settings instead of defaults.
B315 - the log lines go through the translation layer.
"""
from __future__ import annotations

import re
import types
from dataclasses import replace
from pathlib import Path

import pytest

from modules import pipeline, translations, whisper
from modules.config import WhisperSettings, default_config
from modules.song_text import AlignedWord, LyricWord


# --------------------------------------------------------------------------
# B315: elke logregel is vertaald, in beide talen even veel plaatshouders
# --------------------------------------------------------------------------

#: %-omzettingen zoals de logger ze invult. Bewust GEEN "%%" (dat is een
#: letterlijk procentteken en geen plaatshouder).
_PERCENT = re.compile(r"%(?!%)[-+ #0]*[0-9]*(?:\.[0-9]+)?[a-zA-Z]")
#: {naam}-velden zoals ``str.format`` ze invult.
_FIELD = re.compile(r"\{(\w+)\}")


def test_plaatshouders_komen_in_beide_talen_overeen(monkeypatch) -> None:
    """De belangrijkste bewaker van de vertaallaag.

    De logger vult ``%``-plaatshouders POSITIONEEL in: staat er in het
    Engels een ``%d`` waar het Nederlands een ``%s`` heeft, dan krijg je
    een verkeerd ingevulde regel of een uitzondering middenin het loggen.
    Bij ``{naam}``-velden telt de volgorde niet, maar moet de verzameling
    wel gelijk zijn, anders mist er een waarde.

    Deze test kijkt naar ALLE sleutels, niet alleen de nieuwe: tot nu toe
    werd dit nergens gecontroleerd.
    """
    nl = translations.TRANSLATIONS["nl"]
    en = translations.TRANSLATIONS["en"]
    fouten = []
    for key in sorted(nl):
        dutch, english = str(nl[key]), str(en.get(key, ""))
        if _PERCENT.findall(dutch) != _PERCENT.findall(english):
            fouten.append(f"{key}: % nl={_PERCENT.findall(dutch)} "
                          f"en={_PERCENT.findall(english)}")
        if sorted(_FIELD.findall(dutch)) != sorted(_FIELD.findall(english)):
            fouten.append(f"{key}: velden nl={_FIELD.findall(dutch)} "
                          f"en={_FIELD.findall(english)}")
    assert not fouten, "\n".join(fouten)


def test_beide_talen_hebben_dezelfde_sleutels() -> None:
    nl = set(translations.TRANSLATIONS["nl"])
    en = set(translations.TRANSLATIONS["en"])
    assert nl == en, sorted(nl ^ en)


def test_geen_letterlijke_logteksten_meer_in_de_modules() -> None:
    """Elke ``logger.x(...)`` haalt zijn tekst uit de vertaallaag.

    Zonder deze test sluipt de volgende logregel er gewoon weer in het
    Nederlands in, en dan volgt het logvenster de taalkeuze niet meer.
    """
    import ast

    modules_dir = Path(__file__).resolve().parents[1] / "modules"
    overtreders = []
    for path in sorted(modules_dir.glob("*.py")):
        boom = ast.parse(path.read_text(encoding="utf-8"))
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.Call):
                continue
            f = knoop.func
            if not (isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name)
                    and f.value.id == "logger"):
                continue
            if not knoop.args:
                continue
            eerste = knoop.args[0]
            if isinstance(eerste, ast.Constant) \
                    and isinstance(eerste.value, str):
                overtreders.append(f"{path.name}:{knoop.lineno} "
                                   f"{eerste.value[:50]!r}")
    assert not overtreders, ("logregels met een letterlijke tekst in plaats "
                             "van t(...):\n" + "\n".join(overtreders))


def test_logsleutels_bestaan_echt() -> None:
    """Elke ``t("log_...")`` in de code moet een sleutel hebben."""
    modules_dir = Path(__file__).resolve().parents[1] / "modules"
    patroon = re.compile(r't\("(log_\w+)"\)')
    gebruikt = set()
    for path in sorted(modules_dir.glob("*.py")):
        gebruikt.update(patroon.findall(path.read_text(encoding="utf-8")))
    ontbreekt = sorted(gebruikt - set(translations.TRANSLATIONS["nl"]))
    assert not ontbreekt, ontbreekt
    assert len(gebruikt) > 150, "verwacht ~185 logsleutels, gevonden " \
                                f"{len(gebruikt)}"


def test_geen_bugnummers_in_de_logteksten() -> None:
    """De logregels staan in het venster dat de gebruiker leest; interne
    B-nummers horen in het commentaar, niet daar."""
    for taal, teksten in translations.TRANSLATIONS.items():
        for key, waarde in teksten.items():
            if key.startswith("log_"):
                assert not re.search(r"\bB\d{2,3}\b", str(waarde)), \
                    f"{taal}/{key}: {waarde}"


# --------------------------------------------------------------------------
# B314: de Whisper-instellingen
# --------------------------------------------------------------------------

def test_decodeeropties_komen_uit_de_instellingen() -> None:
    settings = replace(WhisperSettings(), temperature=(0.0, 0.4),
                       no_speech_threshold=None, vad_filter=True,
                       hallucination_silence_threshold=2.0,
                       log_prob_threshold=-2.0)
    opties = whisper.decode_options(settings)
    assert opties["temperature"] == [0.0, 0.4]
    assert opties["no_speech_threshold"] is None
    assert opties["log_prob_threshold"] == -2.0
    assert opties["vad_filter"] is True
    assert opties["hallucination_silence_threshold"] == 2.0


def test_standaard_is_herhaalbaar_decoderen() -> None:
    """De standaard is één temperatuur, dus geen bemonstering.

    Faster-whisper valt standaard terug over een ladder van temperaturen
    en decodeert dan MET bemonstering, zonder seed. Op één en hetzelfde
    bronbestand leverde dat 36, 28 en 27 segmenten op. Een karaokevideo
    die je niet kunt reproduceren is onbruikbaar."""
    opties = whisper.decode_options(default_config().whisper)
    assert opties["temperature"] == [0.0]


def test_lege_temperatuur_valt_terug_op_nul() -> None:
    settings = replace(WhisperSettings(), temperature=())
    assert whisper.decode_options(settings)["temperature"] == [0.0]


def test_whisper_instellingen_overleven_opslaan_en_inlezen(
        tmp_path: Path) -> None:
    """De opslag schreef een handgeschreven lijstje sleutels weg, waardoor
    een nieuwe instelling stil verdween bij het volgende opslaan."""
    from dataclasses import fields

    from modules import config as config_module

    doel = tmp_path / "config.json"
    origineel = replace(
        default_config(),
        whisper=replace(default_config().whisper,
                        temperature=(0.0, 0.4), no_speech_threshold=0.9,
                        log_prob_threshold=-2.0, vad_filter=True,
                        hallucination_silence_threshold=2.0))
    config_module.save_config(origineel, doel)
    terug = config_module.load_config(doel)
    for veld in fields(WhisperSettings):
        assert getattr(terug.whisper, veld.name) == \
            getattr(origineel.whisper, veld.name), veld.name


# --------------------------------------------------------------------------
# B313: overgeslagen woorden op de zangstem plaatsen
# --------------------------------------------------------------------------

def _woorden(spec: list[tuple[str, float | None, float]]):
    """(tekst, starttijd of None, similariteit) -> uitgelijnde woorden."""
    uit = []
    for index, (tekst, start, sim) in enumerate(spec):
        uit.append(AlignedWord(
            LyricWord(index=index, text=tekst, line=index // 4),
            start, None if start is None else start + 0.3,
            tekst if start is not None else None, sim))
    return tuple(uit)


def _context(vensters, monkeypatch):
    """Stand-in met een zangstem waarvan de actieve vensters vaststaan.

    Via ``monkeypatch``, zodat de vervanging na de test weer wordt
    teruggedraaid - anders draagt hij over naar tests die de echte
    zangstem-analyse gebruiken.
    """
    from modules import rhythm

    context = types.SimpleNamespace(
        config=types.SimpleNamespace(
            advanced=types.SimpleNamespace(vocal_analysis=True)),
        store=types.SimpleNamespace(get_step=lambda _naam: None,
                                    set_meta=lambda *_a: None))
    monkeypatch.setattr(rhythm, "active_windows",
                        lambda *_a, **_k: vensters)
    monkeypatch.setattr(pipeline, "ensure_original_vocals",
                        lambda _c: Path("nep.wav"))
    return context


def test_overgeslagen_woorden_krijgen_een_tijd(monkeypatch) -> None:
    aligned = _woorden([("een", 1.0, 1.0), ("twee", None, 0.0),
                        ("drie", None, 0.0), ("vier", 10.0, 1.0)])
    uit = pipeline._place_skipped_on_energy(_context([(0.0, 12.0)], monkeypatch), aligned)
    assert all(w.start is not None for w in uit)
    assert uit[1].estimated and uit[2].estimated
    assert 1.3 <= uit[1].start < uit[2].start <= 10.0


def test_goede_koppelingen_blijven_onaangeroerd(monkeypatch) -> None:
    """De harde eis: aan een woord dat goed gekoppeld is, komen we niet."""
    aligned = _woorden([("een", 1.0, 1.0), ("twee", None, 0.0),
                        ("drie", 5.0, 0.9), ("vier", 10.0, 1.0)])
    uit = pipeline._place_skipped_on_energy(_context([(0.0, 12.0)], monkeypatch), aligned)
    for origineel, nieuw in zip(aligned, uit):
        if origineel.sim >= pipeline._ESTIMATE_MAX_SIM:
            assert nieuw == origineel, origineel.lyric.text


def test_zwakke_koppeling_telt_als_overgeslagen(monkeypatch) -> None:
    """"alle" op "la," met 0,25 zegt meer over de wanhoop van de
    uitlijning dan over het woord; die mag opnieuw geplaatst worden."""
    aligned = _woorden([("een", 1.0, 1.0), ("alle", 9.5, 0.25),
                        ("vier", 10.0, 1.0)])
    uit = pipeline._place_skipped_on_energy(_context([(0.0, 12.0)], monkeypatch), aligned)
    assert uit[1].estimated and uit[1].start < 9.5


def test_volgorde_blijft_behouden(monkeypatch) -> None:
    aligned = _woorden([("a", 1.0, 1.0)] + [(f"w{i}", None, 0.0)
                                            for i in range(10)]
                       + [("z", 20.0, 1.0)])
    uit = pipeline._place_skipped_on_energy(_context([(0.0, 25.0)], monkeypatch), aligned)
    tijden = [w.start for w in uit if w.start is not None]
    assert tijden == sorted(tijden)


def test_stilte_wordt_overgeslagen(monkeypatch) -> None:
    """Woorden komen in de gezongen stukken, niet in de stilte ertussen."""
    aligned = _woorden([("a", 0.5, 1.0)] + [(f"w{i}", None, 0.0)
                                            for i in range(4)]
                       + [("z", 30.0, 1.0)])
    uit = pipeline._place_skipped_on_energy(
        _context([(0.0, 1.0), (5.0, 9.0), (20.0, 24.0)], monkeypatch), aligned)
    for woord in uit[1:5]:
        assert (5.0 <= woord.start <= 9.0) or (20.0 <= woord.start <= 24.0), \
            woord.start


def test_eenzaam_anker_dat_te_snel_zingen_vraagt_wordt_losgelaten(monkeypatch) -> None:
    """De gemeten Viva-situatie: het songtekstwoord "muziek" gekoppeld aan
    een gehallucineerde "MUZIEK" met een perfecte 1,00, midden in een gat.
    Dat ene anker perste achtentwintig woorden in drieënhalve seconde."""
    spec = [("start", 1.0, 1.0)]
    spec += [(f"a{i}", None, 0.0) for i in range(5)]
    spec += [("muziek", 30.0, 1.0)]                 # eenling in het gat
    spec += [(f"b{i}", None, 0.0) for i in range(28)]
    spec += [("eind", 33.5, 1.0)]
    aligned = _woorden(spec)
    uit = pipeline._place_skipped_on_energy(_context([(0.0, 40.0)], monkeypatch), aligned)
    muziek = uit[6]
    assert muziek.estimated, "het valse anker had losgelaten moeten worden"
    assert muziek.start < 30.0
    duur = [w.end - w.start for w in uit if w.estimated]
    assert min(duur) > 0.2, "geen enkel woord in een fractie van een seconde"


def test_een_anker_met_buren_wordt_nooit_losgelaten(monkeypatch) -> None:
    """Een juiste koppeling staat zelden alleen: haar buren kloppen ook.
    Zo'n groep blijft staan, ook als het venster ernaast krap is."""
    spec = [("start", 1.0, 1.0)]
    spec += [(f"a{i}", None, 0.0) for i in range(3)]
    spec += [("serenade", 30.0, 1.0), ("aan", 30.4, 1.0)]   # groepje
    spec += [(f"b{i}", None, 0.0) for i in range(28)]
    spec += [("eind", 33.5, 1.0)]
    aligned = _woorden(spec)
    uit = pipeline._place_skipped_on_energy(_context([(0.0, 40.0)], monkeypatch), aligned)
    assert not uit[4].estimated and uit[4].start == 30.0
    assert not uit[5].estimated and uit[5].start == 30.4


def test_zonder_zangstem_verandert_er_niets() -> None:
    aligned = _woorden([("een", 1.0, 1.0), ("twee", None, 0.0)])
    context = types.SimpleNamespace(
        config=types.SimpleNamespace(
            advanced=types.SimpleNamespace(vocal_analysis=False)),
        store=types.SimpleNamespace(get_step=lambda _naam: None))
    assert pipeline._place_skipped_on_energy(context, aligned) == aligned


def test_schatting_telt_niet_mee_als_betrouwbare_regel() -> None:
    """Een schatting mag niet stilletjes het gewicht van een meting
    krijgen: de regel zou dan betrouwbaar heten, door B194 opgerekt
    worden en de energie-plaatsing van B209/B310 mislopen."""
    woord = AlignedWord(LyricWord(0, "la", 0), 1.0, 2.0, None, 0.0,
                        estimated=True)
    assert woord.estimated is True
    normaal = AlignedWord(LyricWord(0, "la", 0), 1.0, 2.0, "la", 1.0)
    assert normaal.estimated is False


@pytest.mark.parametrize("aantal,venster,haalbaar", [
    (2, 1.0, True),      # 2 woorden per seconde: prima
    (6, 1.0, True),      # precies op de grens telt nog als haalbaar
    (7, 1.0, False),     # daarboven niet meer
    (28, 3.5, False),    # de gemeten Viva-situatie
])
def test_grens_voor_haalbaar_zingen(aantal: int, venster: float,
                                    haalbaar: bool) -> None:
    assert (aantal / venster <= pipeline._MAX_WORDS_PER_SECOND) is haalbaar
