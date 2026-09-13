"""Tests for v0.98.0: B311 - de afleidingsketen.

De belangrijkste test in dit bestand is
``test_elke_stap_en_meta_staat_in_de_keten``. Die bewaakt niet een bug
maar een WERKWIJZE: wie een nieuwe stap of meta toevoegt zonder te
bepalen waar hij in de keten hoort, krijgt rood in plaats van over een
half jaar stille verouderde gegevens.
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from modules import dependencies as deps
from modules import filesystem, pipeline
from modules.config import AppConfig
from modules.filesystem import ProjectPaths, ProjectStore


# --------------------------------------------------------------------------
# De keten zelf
# --------------------------------------------------------------------------

def test_keten_heeft_geen_kringloop() -> None:
    """Een afgeleide mag nooit (via een omweg) van zichzelf afhangen -
    dan zou invalideren nooit stoppen."""
    kleur: dict[str, str] = {}

    def bezoek(naam: str, pad: list[str]) -> list[str] | None:
        if kleur.get(naam) == "bezig":
            return pad + [naam]
        if kleur.get(naam) == "klaar":
            return None
        kleur[naam] = "bezig"
        for bron in deps.ARTEFACTS[naam].sources:
            gevonden = bezoek(bron, pad + [naam])
            if gevonden:
                return gevonden
        kleur[naam] = "klaar"
        return None

    for naam in deps.ARTEFACTS:
        kringloop = bezoek(naam, [])
        assert kringloop is None, f"kringloop: {' -> '.join(kringloop)}"


def test_elke_bron_bestaat() -> None:
    """Elke genoemde bron moet zelf ook in de kaart staan."""
    for artefact in deps.ARTEFACTS.values():
        for bron in artefact.sources:
            assert bron in deps.ARTEFACTS, \
                f"{artefact.name} verwijst naar onbekende bron {bron}"


def test_elk_artefact_is_beschreven() -> None:
    """Zonder omschrijving is de kaart niet te lezen en dus waardeloos."""
    for artefact in deps.ARTEFACTS.values():
        assert artefact.what.strip(), f"{artefact.name} mist een omschrijving"


def test_elk_bestandsartefact_geeft_paden() -> None:
    paths = ProjectPaths(root=Path("/tmp/x"), song="lied")
    for artefact in deps.ARTEFACTS.values():
        if artefact.kind != deps.FILE:
            continue
        gevonden = deps.paths_for(artefact.name, paths)
        assert gevonden, f"{artefact.name} levert geen paden"


def test_alleen_bronnen_hebben_geen_herkomst() -> None:
    """Een afgeleide zonder bron is een afgeleide die nooit veroudert -
    dat is bijna altijd een vergissing. De uitzonderingen zijn expliciet."""
    losstaand = {naam for naam, a in deps.ARTEFACTS.items()
                 if not a.sources and a.kind != deps.SOURCE}
    # B353: "video" hoort hier bewust bij. De gemaakte video is een
    # eindproduct; een latere wijziging maakt hem verouderd, niet
    # ongeldig, en dat oordeel is aan de gebruiker.
    # B413: "input_last_dir" hoort er ook bij - waar de gebruiker zijn
    # bestanden vandaan haalde veroudert niet door iets dat het programma
    # uitrekent.
    assert losstaand == {"display_name", "input_names", "input_last_dir",
                         "video_titles", "config_signature", "video"}


# --------------------------------------------------------------------------
# De bewaker: staat elke sleutel uit de code in de kaart?
# --------------------------------------------------------------------------

_STEP_CALL = re.compile(
    r"""(?:set|get|clear)_step\(\s*f?["']([^"']+)["']""")
_META_CALL = re.compile(
    r"""(?:set|get|clear)_meta\(\s*f?["']([^"']+)["']""")


#: Plaatsvervangers in f-strings, uitgeschreven naar de echte sleutel.
_PLACEHOLDERS = ("{track}", "{stem}", "{TRACK_ORIGINAL}", "{TRACK_KARAOKE}")


def _module_sources() -> list[str]:
    modules_dir = Path(__file__).resolve().parents[1] / "modules"
    return [path.read_text(encoding="utf-8")
            for path in sorted(modules_dir.glob("*.py"))]


def _keys_in_code(pattern: re.Pattern[str]) -> set[str]:
    """Elke sleutel die ergens in modules/ wordt gebruikt.

    ``{track}``/``{stem}`` en de constantnamen worden uitgeschreven over
    de twee tracks, want zo staan ze ook in project.json.
    """
    gevonden: set[str] = set()
    for tekst in _module_sources():
        for sleutel in pattern.findall(tekst):
            if any(p in sleutel for p in _PLACEHOLDERS):
                for track in deps.TRACKS:
                    uitgeschreven = sleutel
                    for plek in _PLACEHOLDERS:
                        uitgeschreven = uitgeschreven.replace(plek, track)
                    gevonden.add(uitgeschreven)
            else:
                gevonden.add(sleutel)
    return gevonden


def _quoted_literals() -> set[str]:
    """Elke tekst die in modules/ tussen aanhalingstekens staat.

    Een stap hoeft niet per se via ``set_step("naam")`` te lopen: de
    vingerafdruk-stappen staan in een tabel. Voor de omgekeerde controle
    ("beschrijft de kaart alleen dingen die echt bestaan?") telt dus elke
    letterlijke tekst mee."""
    literal = re.compile(r"""["']([^"'\n]+)["']""")
    gevonden: set[str] = set()
    for tekst in _module_sources():
        gevonden.update(literal.findall(tekst))
    return gevonden


def test_elke_stap_en_meta_staat_in_de_keten() -> None:
    """DE bewaker van dit hele ontwerp.

    Tot en met v0.97 stond de invalidatie als handgeschreven lijstjes in
    drie functies. Elke nieuwe stap moest iemand aan het juiste lijstje
    toevoegen, en dat ging keer op keer mis: de clusterselectie overleefde
    nieuwe audio, de handmatig gemarkeerde fragmenten hielden hun tijden
    op een tijdlijn die niet meer bestond, en de projectbrede markeringen
    overleefden alles.

    Deze test maakt dat structureel onmogelijk: gebruikt de code een stap
    of meta die niet in ``dependencies.ARTEFACTS`` staat, dan wordt hij
    rood. Voeg je een stap toe, dan moet je dus bepalen waarvan hij
    afgeleid is - precies de vraag die eerder werd overgeslagen.
    """
    stappen = _keys_in_code(_STEP_CALL)
    metas = _keys_in_code(_META_CALL)
    bekend = set(deps.ARTEFACTS)
    ontbrekend = sorted((stappen | metas) - bekend)
    assert not ontbrekend, (
        "deze stap-/meta-sleutels staan niet in de afleidingsketen "
        f"(modules/dependencies.py): {ontbrekend}")


def test_de_keten_beschrijft_geen_verzonnen_sleutels() -> None:
    """Andersom net zo goed: een stap in de kaart die nergens meer
    gebruikt wordt is dode administratie."""
    gebruikt = (_keys_in_code(_STEP_CALL) | _keys_in_code(_META_CALL)
                | _quoted_literals())
    beschreven = {naam for naam, a in deps.ARTEFACTS.items()
                  if a.kind in (deps.STEP, deps.META)}
    ongebruikt = sorted(beschreven - gebruikt)
    assert not ongebruikt, (
        f"deze artefacten worden nergens meer gebruikt: {ongebruikt}")


# --------------------------------------------------------------------------
# Wat volgt er uit een wijziging?
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bron,verwacht", [
    ("input:original", "whisper_original"),
    ("input:original", "clusters_original"),
    ("input:original", "karaoke"),
    ("input:original", "karaoke_from_original"),
    ("input:original", "vocal_onset_s"),
    ("input:karaoke", "fragment_exclusions"),
    ("input:karaoke", "restore_fragments"),
    ("input:karaoke", "align"),
    ("input:lyrics", "word_coupling"),
    ("input:lyrics", "stress_anchors"),
    ("input:lyrics", "original_overrides"),
    ("input:lyrics", "language_choice"),
    ("input:karaoke_text", "coupling"),
    ("input:karaoke_text", "timing"),
    ("config:forced_alignment", "whisper_original"),
    ("config:karaoke", "karaoke"),
    ("clusters_original", "karaoke"),
    ("word_coupling", "timing"),
])
def test_wijziging_werkt_door(bron: str, verwacht: str) -> None:
    """De gaten uit de doorlichting, één voor één: dit MOET vervallen."""
    assert verwacht in deps.dependents([bron])


@pytest.mark.parametrize("bron,gespaard", [
    # Een andere parodietekst raakt de transcriptie en de handmatige
    # woordkoppelingen niet: die gaan over het origineel.
    ("input:karaoke_text", "whisper_original"),
    ("input:karaoke_text", "word_coupling"),
    ("input:karaoke_text", "clusters_original"),
    # Een andere dempingsinstelling raakt de transcriptie niet.
    ("config:karaoke", "whisper_original"),
    ("config:karaoke", "timing"),
    # De zangstem-/anker-instellingen raken de transcriptie niet.
    ("config:timing", "whisper_original"),
    ("config:timing", "karaoke"),
    # Een nieuw beeldmerk maakt alleen de video oud.
    ("input:logo", "timing"),
    ("input:logo", "karaoke"),
    # Een verse karaoke-transcriptie kost geen handwerk aan het origineel.
    ("whisper_karaoke", "word_coupling"),
    ("whisper_karaoke", "transcript_override"),
])
def test_wijziging_werkt_bewust_NIET_door(bron: str, gespaard: str) -> None:
    """Te veel weggooien kost de gebruiker handwerk en is net zo fout als
    te weinig weggooien. Deze paren horen los van elkaar te staan."""
    assert gespaard not in deps.dependents([bron])


def test_gespaarde_tak_blijft_staan() -> None:
    """'Karaoke uit het origineel gemaakt': de gescheiden zang van het
    origineel blijft geldig en mag niet weg - dat scheiden kost minuten
    per nummer (B248)."""
    stappen, _metas, bestanden = deps.invalidation_plan(
        ["input:karaoke"], keep=["cache:demucs_original"])
    assert "cache:demucs_original" not in bestanden
    assert "cache:original_vocals" not in bestanden
    assert "whisper_original" not in stappen
    assert "cache:karaoke_wav" in bestanden


def test_onbekend_artefact_is_een_luide_fout() -> None:
    """Liever een uitzondering dan stil niets invalideren."""
    with pytest.raises(KeyError):
        deps.dependents(["input:bestaat_niet"])


# --------------------------------------------------------------------------
# De vingerafdrukken: buiten de app om bewerken wordt gemerkt
# --------------------------------------------------------------------------

def _context(tmp_path: Path) -> pipeline.AppContext:
    paths = ProjectPaths(root=tmp_path, song="lied")
    paths.input_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_dir.mkdir(parents=True, exist_ok=True)
    paths.cache_dir.mkdir(parents=True, exist_ok=True)
    store = ProjectStore(paths.project_file)
    return pipeline.AppContext(paths=paths, config=AppConfig(), store=store)


def test_songtekst_buiten_de_app_bewerkt_wordt_gemerkt(
        tmp_path: Path) -> None:
    """Het echte scenario: je verbetert een regel in kladblok. Tot en met
    v0.97 merkte het programma dat nergens en bleven de timing en de
    handmatige koppelingen op de oude tekst slaan."""
    context = _context(tmp_path)
    lyrics = context.paths.input_dir / "songtekst.txt"
    lyrics.write_text("een twee drie\n", encoding="utf-8")
    pipeline.remember_sources(context)

    context.store.set_step("timing", {"lines": 3})
    context.store.set_step("word_coupling", {"pins": {"0": [1]}})
    context.store.set_step("coupling", {"mapping": {}})

    assert pipeline.sync_input_changes(context) == ()      # niets gewijzigd
    assert context.store.get_step("timing") is not None

    lyrics.write_text("een twee vier\n", encoding="utf-8")
    assert pipeline.sync_input_changes(context) == ("input:lyrics",)
    assert context.store.get_step("timing") is None
    assert context.store.get_step("word_coupling") is None
    assert context.store.get_step("coupling") is None


def test_karaoketekst_buiten_de_app_bewerkt_spaart_de_koppeling(
        tmp_path: Path) -> None:
    """En andersom: de parodietekst wijzigen mag de handmatige
    woordkoppelingen NIET kosten."""
    context = _context(tmp_path)
    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "regel een\n", encoding="utf-8")
    pipeline.remember_sources(context)
    context.store.set_step("word_coupling", {"pins": {"0": [1]}})
    context.store.set_step("timing", {"lines": 1})

    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "regel twee\n", encoding="utf-8")
    assert pipeline.sync_input_changes(context) == ("input:karaoke_text",)
    assert context.store.get_step("timing") is None
    assert context.store.get_step("word_coupling") is not None


def test_instelling_wijzigen_wordt_gemerkt(tmp_path: Path) -> None:
    """Forced alignment uitzetten veranderde de woordtijden wél maar
    ongeldigde niets: de transcriptiecache bleef raak schieten."""
    context = _context(tmp_path)
    pipeline.remember_sources(context)
    context.store.set_step("whisper_original", {"segments": 12})

    uit = replace(context.config,
                  advanced=replace(context.config.advanced,
                                   forced_alignment=False))
    context = pipeline.AppContext(paths=context.paths, config=uit,
                                  store=context.store)
    assert pipeline.sync_input_changes(context) == \
        ("config:forced_alignment",)
    assert context.store.get_step("whisper_original") is None


def test_ongewijzigd_project_gooit_niets_weg(tmp_path: Path) -> None:
    """Het tegenovergestelde risico: bij elke stap alles weggooien omdat
    de vingerafdruk nog nooit is opgeslagen."""
    context = _context(tmp_path)
    (context.paths.input_dir / "songtekst.txt").write_text(
        "een twee\n", encoding="utf-8")
    context.store.set_step("timing", {"lines": 2})
    # Eerste keer: nog geen vingerafdrukken bekend -> niets weggooien.
    assert pipeline.sync_input_changes(context) == ()
    assert context.store.get_step("timing") is not None
    # Tweede keer, ongewijzigd: nog steeds niets weggooien.
    assert pipeline.sync_input_changes(context) == ()
    assert context.store.get_step("timing") is not None


def test_invalidatie_verwijdert_ook_de_bestanden(tmp_path: Path) -> None:
    """Een stap wissen zonder het bestand te wissen laat een verouderd
    resultaat op schijf staan dat later gewoon weer gebruikt wordt (de
    oude karaoke_edit.mp3 die de video als bron pakte)."""
    context = _context(tmp_path)
    export = context.paths.output_dir / "karaoke_edit.mp3"
    export.parent.mkdir(parents=True, exist_ok=True)
    export.write_bytes(b"oud")
    bewerkt = context.paths.cache_dir / "karaoke_edited.wav"
    bewerkt.write_bytes(b"oud")
    context.store.set_step("karaoke", {"wav": str(bewerkt)})

    pipeline.invalidate(context, ["clusters_original"])
    assert not export.exists()
    assert not bewerkt.exists()
    assert context.store.get_step("karaoke") is None


def test_meta_wordt_ook_echt_gewist(tmp_path: Path) -> None:
    """``clear_step`` raakt het bovenste niveau van project.json niet;
    daardoor overleefden de projectbrede markeringen alles."""
    context = _context(tmp_path)
    context.store.set_meta("karaoke_from_original", True)
    context.store.set_meta("vocal_onset_s", 1.25)
    pipeline.invalidate(context, ["input:original"])
    assert context.store.get_meta("karaoke_from_original") is None
    assert context.store.get_meta("vocal_onset_s") is None


def test_projectnaam_overleeft_een_bronwijziging(tmp_path: Path) -> None:
    """Niet alles is een afgeleide: hoe het project heet en welke titels
    in de video komen blijven staan, wat je ook vervangt."""
    context = _context(tmp_path)
    context.store.set_meta("display_name", "Lied S")
    context.store.set_meta("video_titles", {"karaoke_title": "Viva"})
    pipeline.invalidate(context, ["input:original"])
    pipeline.invalidate(context, ["input:lyrics"])
    assert context.store.get_meta("display_name") == "Lied S"
    assert context.store.get_meta("video_titles") is not None


# --------------------------------------------------------------------------
# Demucs-stems horen bij één bepaalde audio
# --------------------------------------------------------------------------

def test_demucs_stems_van_andere_audio_worden_niet_hergebruikt(
        tmp_path: Path) -> None:
    """Precies de keten die v0.96 sloopte: Whisper transcribeert de
    zangstem, dus een stem van een ander nummer geeft stilletjes een
    transcriptie van muziek die er niet meer is."""
    from modules import separation

    cache = tmp_path / "cache"
    store = cache / "demucs_stems_original"
    store.mkdir(parents=True)
    (store / "vocals.wav").write_bytes(b"zang")
    (store / "no_vocals.wav").write_bytes(b"muziek")

    bron = tmp_path / "original.wav"
    bron.write_bytes(b"nummer een")
    (store / "source.sha1").write_text(
        filesystem.file_sha1(bron), encoding="utf-8")
    assert separation._marker_matches(store / "source.sha1",
                                      filesystem.file_sha1(bron))

    bron.write_bytes(b"een heel ander nummer")
    assert not separation._marker_matches(store / "source.sha1",
                                          filesystem.file_sha1(bron))


def test_demucs_stems_zonder_merk_blijven_bruikbaar(tmp_path: Path) -> None:
    """Stems van vóór deze versie hebben geen merk. Die weggooien kost
    minuten per nummer voor een scheiding die waarschijnlijk klopt."""
    from modules import separation

    store = tmp_path / "demucs_stems_original"
    store.mkdir(parents=True)
    assert separation._marker_matches(store / "source.sha1", "abc123")


# --------------------------------------------------------------------------
# Het document blijft bij de keten
# --------------------------------------------------------------------------

def test_document_is_bij_de_tijd() -> None:
    """``docs/afhankelijkheden.md`` wordt gegenereerd uit de keten.

    Een met de hand bijgehouden kaart veroudert op het moment dat iemand
    een stap toevoegt en het document vergeet. Deze test vergelijkt het
    bestand op schijf met wat de generator maakt; loopt het achter, draai
    dan ``python tools/write_dependency_doc.py``.
    """
    import importlib.util

    tool = (Path(__file__).resolve().parents[1] / "tools"
            / "write_dependency_doc.py")
    spec = importlib.util.spec_from_file_location("_doc_tool", tool)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.DOC.exists(), "docs/afhankelijkheden.md ontbreekt"
    op_schijf = module.DOC.read_text(encoding="utf-8")
    assert op_schijf == module.render(), (
        "docs/afhankelijkheden.md loopt achter op modules/dependencies.py; "
        "draai: python tools/write_dependency_doc.py")


# --------------------------------------------------------------------------
# B312: een stap gooit zijn eigen zojuist geschreven bestand niet weg
# --------------------------------------------------------------------------

def test_verse_transcriptie_blijft_op_schijf_staan(tmp_path: Path) -> None:
    """De regressie die v0.98.0 opleverde, in één test.

    Na een échte nieuwe transcriptie wist ``detect_track`` alles wat op
    de VORIGE tekst berustte. De keten rekende het zojuist geschreven
    ``transcription_original.json`` daar ook toe, want dat bestand is
    afgeleid van de stap ``whisper_original``. Gevolg: het bestand werd
    verwijderd op het moment dat het geschreven was, en stap 2 meldde dat
    er geen transcriptie was.
    """
    context = _context(tmp_path)
    cache = pipeline.transcript_cache(context, "original")
    cache.write_bytes(b"[]")
    context.store.set_step("whisper_original", {"segments": 28})
    context.store.set_step("coupling", {"mapping": {}})
    context.store.set_step("timing", {"lines": 59})

    pipeline.invalidate_after_fresh_transcript(context, "original")

    assert cache.exists(), "de verse transcriptie mag niet gewist worden"
    assert context.store.get_step("whisper_original") is not None
    assert context.store.get_step("coupling") is None
    assert context.store.get_step("timing") is None


def test_verse_karaoketranscriptie_blijft_ook_staan(tmp_path: Path) -> None:
    """Hetzelfde voor de restzang-transcriptie."""
    context = _context(tmp_path)
    cache = pipeline.transcript_cache(context, "karaoke")
    cache.write_bytes(b"[]")
    context.store.set_step("whisper_karaoke", {"segments": 0})
    pipeline.invalidate_after_fresh_transcript(context, "karaoke")
    assert cache.exists()


def test_elke_stap_spaart_zijn_eigen_product() -> None:
    """Algemeen, niet alleen voor de transcriptie: het bestand dat een
    stap zelf schrijft mag nooit sneuvelen als díe stap net vernieuwd is.
    Anders komt dezelfde fout terug bij de volgende stap die een bestand
    schrijft (clusters.json, alignment.json, karaoke_edited.wav)."""
    for naam, artefact in deps.ARTEFACTS.items():
        if artefact.kind != deps.STEP:
            continue
        producten = deps.direct_products([naam])
        if not producten:
            continue
        _steps, _metas, bestanden = deps.invalidation_plan([naam])
        overlap = producten & set(bestanden)
        assert not overlap, (
            f"{naam} zou zijn eigen zojuist geschreven bestand(en) "
            f"weggooien: {sorted(overlap)}")


def test_timing_weggooien_pakt_de_bestanden_wel_mee() -> None:
    """Het tegenovergestelde risico: te weinig weggooien. Bij
    ``invalidate_timing`` is het juist de bedoeling dat timing.json weg
    is, anders blijft een verouderde timing gewoon in gebruik."""
    _steps, _metas, bestanden = deps.invalidation_plan(
        ["timing"], include_changed=True)
    assert "output:timing" in bestanden


def test_een_bestand_met_meer_bronnen_is_geen_eigen_product() -> None:
    """``lyrics_alignment.txt`` volgt uit de koppeling ÉN de karaoketekst;
    dat is een echte afgeleide en die hoort wel te vervallen."""
    assert "output:lyrics_alignment" not in deps.direct_products(
        ["word_coupling"])
    _steps, _metas, bestanden = deps.invalidation_plan(["word_coupling"])
    assert "output:lyrics_alignment" in bestanden
