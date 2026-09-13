# Doorontwikkeling – werkwijze en stand van zaken

Het logboek van dit programma: per versie wat er is veranderd, waarom, en wat de meting erover zei.

## Werkwijze

De werkafspraken tussen de eigenaar en de assistent die dit programma
bouwt staan niet in deze publieke kopie. Wat hierna volgt is het
logboek zelf: per versie wat er is veranderd, waarom, en wat de meting
erover zei.

## Data-model

- `input/<lied>/` – alleen de originele bestanden (origineel, karaoke,
  songtekst.txt, karaoketekst.txt, logo).
- `output/<lied>/settings/` – alle keuzes + `timing.json` (+ `timing_auto.json`,
  `project.json`); blijvend.
- `output/<lied>/` – eindproducten (karaoke_edit, video); blijvend.
- `cache/<lied>/` – regenereerbaar; wordt elke sessie recursief gewist.

## Pijplijn (kort)

1. Detecteer woorden (Whisper large-v3/distil/small) op origineel en
   karaoke; taal uit de songtekst (langdetect, drempel 0.70), anders
   auto of handmatige keuze.
2. Analyse + fonetische clustering (restzang in de karaoke opsporen).
3. Uitlijnen origineel↔karaoke (offset-regio's; uitschieters worden
   verworpen, projectie is monotoon). Karaoke uit origineel gemaakt →
   offset 0.
4. Karaoke aanpassen (clusters dempen, −25 dB) + export.
5. Karaokevideo renderen (timing per lettergreep, crowd-secties rood).

## Grote modellen (optioneel, install.bat)

- **Demucs** – zang scheiden (restzang-detectie) én "karaoke uit
  origineel" maken.
- **WhisperX** – forced alignment (preciezere woordtijden per taal).
- Ritme-anker draait op **librosa** en zit vast in de kern.

## Backlog

Verwerkt t/m v0.53: B58–B101.

In v0.54 verwerkt: B103, B104, B106, B108, B110–B120, B129, B130, B131
(bugfixes, opstart/cache/projectbeheer, taaldetectie per track, en de kern
van de timing-herziening). B105 is deels (lettergreepmodel + opschoning);
volledige woord/lettergreep-hiërarchie volgt.

In v0.54.1 verwerkt: B132, B133, B134, B135.
In v0.54.2 verwerkt: B137 (originele baan niet meer geplet), B138 (origineel
1-op-1 boven de karaokezin via de koppeling), redistributie tussen ankers.
In v0.55 verwerkt: onset-fix (percentiel-vloer i.p.v. mediaan; eerste zin
op de echte inzet, geverifieerd op de Oerend Hard-audio -> ~3.7 s).
In v0.56 verwerkt: B141 (hallucinatie-/"MUZIEK"-segmenten uit de koppeling
gefilterd -> geen valse ankers meer, geverifieerd op de aangeleverde
transcriptie) en B142 (origineel getranscribeerd op de Demucs-zangstem
i.p.v. de volledige mix voor betrouwbaardere woorden/tijden).

In v0.57 verwerkt: B146 (knop "Timing verfijnen"), B147 (pauzes tussen
zinnen), B143 (diagnostiek-submap + versie-tracking + Instellingen-toggle),
B149 (juiste taal in de administratie i.p.v. config-default "auto").

In v0.58 verwerkt: B139/B148 (deels) - opgepropte herhaal-/crowdregels in de
fade-out worden gespreid (minimumduur wint, overlap duwt vooruit). De diepere
B148 (koppeling kiest bij veel herhalingen soms de verkeerde bron-plek) blijft
open; die vergt betere brondetectie/koppeling.

In v0.59 verwerkt: eigen app-icoon (venster + Windows-taakbalk via
AppUserModelID) en deterministische taaldetectie (vaste langdetect-seed).

In v0.59 verwerkt: app-icoon (venster + Windows-taakbalk via AppUserModelID),
deterministische taaldetectie (vaste langdetect-seed), en de handleiding
(B128, `docs/handleiding.md`).
In v0.60 verwerkt: B148 - fade-out met veel niet-getranscribeerde
herhaalregels wordt over de volledige resttijd tot het lied-einde verdeeld
(geverifieerd op de Oerend Hard-data: Whisper stopt na ~188 s, de fade-out
loopt tot ~219 s).

In v0.61 verwerkt: B121 - woord-koppel-editor tussen stap 1 en 2. De
testbare kern (pins -> songtekst↔transcriptie-koppeling -> doorwerking naar
analyse/timing, incl. invalidatie) is getest; de Qt-UI (`koppeleditor.py`)
vergt nog een test op de machine met beeldscherm. Basis is herbruikbaar
voor B151 (lettergreep/klemtoon); volledige unificatie met de golfvorm-
editors (B152) blijft een aparte refactor.

In v0.62 verwerkt: B121 (vervolg) - de woord-koppel-editor kan nu 1-op-meer
koppelen (één songtekstwoord aan meerdere gevonden woorden) en de klik-logica
is hersteld: een klik op een woordvak selecteert/(ont)koppelt (vak-klik gaat
vóór lijn-klik, dus lijnen verdwijnen niet meer per ongeluk), en handmatige
koppelingen blijven blauw i.p.v. terug naar rood. Model achter de editor
gebruikt nu lijst-pins (`dict[int, list[int]]`) van songtekst- naar
transcript-index. Daarnaast `download_fonts.bat`: eenmalig script dat per
lettertype de google/fonts-map uitleest en de juiste .ttf ophaalt naar
`assets/fonts/` (voorbereiding op B102; de .ttf's worden aangeleverd en daarna
gebundeld bij de render).

In v0.63 verwerkt:
- **B102** – 15 extra lettertypen meegeleverd in `assets/fonts`; nieuwe
  `modules/fonts.py` leest de map uit; Instellingen heeft een fontkeuze-
  dropdown die bij het openen van de tab wordt ververst; `install.bat`
  controleert de map en haalt alleen ontbrekende fonts op. De losse
  `download_fonts.bat` is vervallen. (Voorbeeld/85%-fit volgt nog.)
- **B107** – inline `[pause]`/`[pauze]`: pauze-teken (…) als eigen
  lettergreep binnen de zin; render tekent puntjes die op de gemiddelde
  beat oplichten (`karaoketekst.apply_pause/is_pause`, `video._draw_pause`).
- **B127** – timing-editor weergavekeuze blokken/zinnen/woorden
  (`timing.editor_view_cells/word_spans`, `TimedLine.blok`); slepen blijft
  op zinsniveau, de andere weergaven zijn ter oriëntatie.
- **B153** – gevonden woorden knippen/samenvoegen in de koppel-editor
  (`songtekst.cut_word/merge_words/remap_pins`), met een persistente
  transcript-override (`pipeline.transcript_override`).

In v0.63.1 verwerkt: fix voor het ophalen van variabele fonts in
`install.bat`. De bestandsnamen bevatten `[wght]`/`[wdth,wght]`; PowerShell's
`-OutFile` interpreteerde die haakjes als jokertekens, waardoor Oswald,
Montserrat, Fredoka, Baloo 2 en Rubik niet werden weggeschreven. De doelnaam
wordt nu ontdaan van `[...]` (bv. `Oswald.ttf`). Rerun `install.bat` om de
vijf variabele fonts alsnog op te halen.

In v0.64 verwerkt:
- **B154/B155** – koppel-editor selectie-UX: tweede klik op hetzelfde woord
  heft de selectie op; na het maken van een koppeling wordt de selectie
  losgelaten.
- **B156** – knippen/samenvoegen ook op de songtekst-rij (bovenop de
  gevonden-woorden-rij van B153), via een songtekst-override
  (`pipeline.lyrics_override`, `songtekst.cut_lyric/merge_lyrics/
  remap_pin_keys`). Alleen voor koppeling/timing; de video-tekst
  (karaoketekst.txt) blijft ongewijzigd.
- **B157/B158** – koppellijnen leesbaar: alleen de lijnen van het
  geselecteerde/gepinde woord vol en dik, de rest heel licht.
- **B159** – staart-analyse (`songtekst.trim_tail_matches`): een reeks
  zwakke matches aan het eind (fade-out, geen betrouwbare transcriptie)
  wordt losgekoppeld i.p.v. het laatste goede woord door te trekken.
- **B160-B163** – timing-editor: dropdown-volgorde blokken/zinnen/woorden
  (standaard zinnen); weergave geldt ook voor de originele-tekstbaan
  (`timing.original_view_cells`); blokken zijn nu sleep- en rekbaar net als
  zinnen (cellen dragen hun bronregels; het hele blok schaalt mee); een blok
  toont de volledige tekst i.p.v. alleen de eerste zin.
- **B150** – lettergreepmodel: `timing.split_syllables` gebruikt pyphen
  (Nederlandse woordafbreking) wanneer beschikbaar, met terugval op de
  klinkergroep-heuristiek. Toegevoegd aan requirements.txt.

In v0.65 verwerkt:
- **B164** – stap-knoppen hernummerd: 1 Detecteer · 2 Woorden koppelen ·
  3 Analyse · 4 Karaoke aanpassen.
- **B165** – handleiding als tabblad (rechts van Instellingen), rendert
  `docs/handleiding.md` via een QTextBrowser (Markdown).
- **B167** – (regressie v0.64) de waarschijnlijkheidskleuren in de koppel-
  editor zijn weer zichtbaar: zonder selectie alles op kleur, alleen dimmen
  wanneer een woord geselecteerd is.
- **B166** – fade-out/overgebleven regels krijgen de duur van de eerdere zin
  met exact dezelfde tekst (mediaan), sequentieel geplaatst
  (`timing._reference_durations`), i.p.v. proportioneel gespreid.
- **B139** – korte crowd-roepjes ('Oeh!', 'Ah!') krijgen een zichtbare
  minimumduur (`_MIN_CROWD_S`) zodat ze niet tot een streepje geplet worden.
- **B136** – tijdelijke test-knop "Modellen vergelijken" (Instellingen):
  `pipeline.compare_models` transcribeert het origineel als volledige mix én
  als Demucs-zangstem met large-v3/distil-large-v3/small en rapporteert per
  combinatie het aantal woorden + songtekst-dekking; schrijft
  `diagnostiek/model_vergelijking.txt`. Kan later weg.

Nog open op dit vlak (nagelopen bij B302, v0.95):
- **B139 (rest)** – volledige crowd-koppeling/plaatsing (inline vs blok,
  volgorde, handmatige overlap) blijft een grotere herziening. Deels
  gebouwd; of de rest nog nodig is, is een inschatting bij gebruik.
- **wav2vec2** – wordt al gebruikt via WhisperX forced alignment op het
  origineel (preciezere woordtijden). Verdere winst zou kunnen uit forced
  alignment ook op de karaoke-restzang en uit een VAD-gestuurde segmentatie.
- *(B136 stond hier ook als "kan later weg" – de knop "Modellen
  vergelijken" en `pipeline.compare_models` zijn intussen verwijderd.)*

In v0.66 verwerkt:
- **B122** – videovelden op de karaokevideo-tab: karaoketitel, originele
  artiest, originele titel (in `config.VideoSettings`, opgeslagen). De
  karaoketitel is leidend voor titel + bestandsnaam.
- **B123/B124** – intro/outro tonen de titel met daaronder een credit-regel
  "artiest - titel" van het origineel (`video.render_video(artist=...,
  orig_title=...)`).
- **B126** – instelbare achtergrondafbeelding (center-crop achter alle
  beelden, `video._load_background`).

In v0.67 verwerkt:
- **B168** – credit-regel (artiest - originele titel) alleen in de intro.
- **B125** – karaokevideo zonder karaoketekst: terugval op `songtekst.txt`
  (`pipeline.karaoke_text_path`), gebruikt in generate_timing, build_coupling
  en de invoerstatus. Zo maak je een karaokevideo van het origineel.
- **B102 (voorbeeld)** – live lettertype-voorbeeld in Instellingen
  (`_update_font_preview` via QFontDatabase).

In v0.68 verwerkt:
- **B102 (voltooid)** – de bodyfont wordt in de render zo groot mogelijk
  gekozen, maar verkleind tot elke regel in max. twee rijen binnen 85% van
  de breedte past (`video._fit_body_font`, `_TEXT_WIDTH_FRAC=0.85`). Teken-
  en overflow-controle gebruiken dezelfde 85%-grens.

In v0.69 verwerkt:
- **B151** – klemtoon (KO-men vs ko-MEN). `Syllable.nadruk` (bewaard in
  timing.json), automatische standaardklemtoon per woord op de eerste
  lettergreep (`timing.apply_default_stress`), toggle-logica
  (`timing.set_word_stress`), een klemtoon-editor (`modules/klemtooneditor.py`)
  met knop op de video-tab, en een subtiel render-accent (schijn-vet) voor de
  beklemtoonde lettergreep.

Hiermee is de oorspronkelijke backlog (B58–B168, B102/B105/B107/B121–B168 en
de klemtoon B150/B151) verwerkt. Verdere ideeën (audio-sjabloonzoeker, diepere
crowd-koppeling) staan los.

In v0.72 verwerkt: B171 (titels op tab 1, links van invoer), B172 (achtergrond
op Instellingen onder Achtergrondkleur), B173 (meldingenpaneel verborgen op
Instellingen/Handleiding), B174 (Opties-blok weg; enabled_tracks altijd
origineel+karaoke; dode toggle-code weg), B178 ("Video-invoer controleren"-knop
weg, video-knoppen hernummerd, _check_video_inputs verwijderd), B180
(TimedLine.uitgeschakeld; regels/blokken/woorden uit/aan in de timing-editor;
render slaat uitgeschakelde regels over), B181/B183 (project/versie/tijd-kop in
timing.json + timing_auto.json via save_timing; timing_project + mismatch-
waarschuwing), B182 (install.bat verplaatst niets meer, alleen waarschuwing),
B184 (clean_cache leegt alles incl. read-only via onexc/onerror + chmod),
B175-B177 (ongebruikte imports/functies/locals opgeruimd).

Staande regel: bij elke wijziging controleren op overbodig geworden code en dat
opruimen (pyflakes + ongebruikte-functie-scan).

In v0.73 verwerkt: B179 (crowd-verwerking). Inline `[crowd]...[/crowd]` blijft
in de logische zin (`karaoketekst._parse_inline` + `TextLine.crowd_words`) en
wordt op lettergreepniveau als crowd gemarkeerd (`Syllable.crowd`,
`timing.apply_inline_crowd`); de render kleurt per lettergreep rood
(`video._draw_line`), een `[pause]` ervoor blijft normaal. Losse crowd-regels
(B179b) en crowd-blokken (B179c) gedragen zich als voorheen. Doordat inline
crowd niet meer wordt afgesplitst, verdwijnen ook de losse crowd-regels die
geen origineel-koppeling hadden.

Hiermee is de volledige verzamelde backlog t/m B184 verwerkt.

In v0.74 verwerkt: B185 (projectnaam -> Karaoketitel voorinvullen, eenrichting),
B186 (karaoke-invoermelding), B187 (venster verticaal schaalbaar via lagere
minimumhoogtes + venstergrootte onthouden met QSettings), B188 ("Titels en
artiest"), B190 (koppelen boven->onder in de koppel-editor), B199/B199b
(uitgeschakelde regels buiten overlap; heringeschakelde regels order-behoudend
inpassen, 2x min + buren 1x min), B200 (knopvolgorde klemtoon vóór timing),
B203 (intro met stilte tot >=5 s via adelay + regels opschuiven), B204 (laatste
zin houdt zang-/crowd-kleur tot de outro), B205 (audiobestanden vrijgeven bij
editor-sluiten zodat de cache leegt).

~~Nog open (zwaardere/onderzoeksitems): B189, B191, B193, B194/B195,
B196, B198, B201/B202.~~ **Achterhaald** – bij B302 (v0.95) nagelopen: al
deze items zijn in latere versies alsnog gebouwd en hebben een
implementatie in `modules/` (B189 `_merged_spans` in koppeleditor.py, B191
`extend_coupling`, B193 `_ORIG_CROWD` in timingeditor.py, B194/B195/B196
in ritme.py/timingeditor.py, B198/B201/B202 in timingeditor.py en
klemtooneditor.py). De lijst was blijven staan zonder te worden
bijgewerkt; wie hem las kreeg een verkeerd beeld van wat er nog te doen
was.

In v0.70 verwerkt:
- **B169** – klemtoon weegt mee in de auto-timing
  (`timing.redistribute_by_stress`): best-effort-regels verdelen hun span naar
  rato van klemtoon (beklemtoonde lettergreep zwaarder), zonder de regel-span
  of betrouwbare/handmatige tijden te wijzigen. Draait in `generate_timing`
  en bij het opslaan in de klemtoon-editor.
- **install.bat** waarschuwt bij uitvoeren vanuit een Temp-/Downloads-map;
  Windows-beveiligingsbeleid (AppLocker/Smart App Control/WDAC) blokkeert daar
  vaak DLL's (bv. PyAV bij faster-whisper: "DLL load failed ... geblokkeerd
  door een beleid voor toepassingsbeheer"). Oplossing: installeer in bv.
  %USERPROFILE%\KaraokeTool.

In v0.71 verwerkt:
- **install.bat verplaatsoptie** – draai je vanuit een Temp-/Downloads-map,
  dan biedt install.bat aan de map (excl. venv/cache) naar
  %USERPROFILE%\KaraokeTool te kopieren (robocopy) en de installatie daar
  voort te zetten. Zo blijft de Windows-beveiliging ongemoeid. Start daarna
  het programma vanuit die nieuwe map.
  (songtekst-)woorden aan de gevonden Whisper-woorden; downstream gebruikt
  de echte woorden; draait ook bij sluiten van de editor.
- **B139** – crowd-timing: inline/blok-crowd niet te los behandelen, in
  volgorde houden, geen auto-overlap (overlap alleen handmatig). Vereist de
  transcriptie-JSON (B131) om de plaatsing exact te reproduceren.
- **B105 (rest)** – volledige hiërarchische timing: woord relatief aan de
  zin, lettergreep relatief aan het woord (nu grotendeels via
  forced-alignment-woordtijden; edge cases resteren).
- **B127** – timing-editor: wisselweergave blokken/zinnen/woorden.
- **B107** – inline `[pause]`: één logische zin, twee delen voor
  plaatsing/timing, in de render puntjes op de gemiddelde beat.
- **B127** – timing-editor: wisselweergave blokken/zinnen/woorden.
- **B121** – woord-match-editor (origineel↔songtekst koppelen, kleuren op
  waarschijnlijkheid, 1-op-meer).
- **B122** – invoervelden originele artiest/titel + karaoketitel (leidend
  voor de render).
- **B123/B124** – video-varianten (muziek×tekst); logo/titel/artiest-regels.
- **B125** – karaoketekst optioneel (karaokevideo van het origineel).
- **B126** – achtergrondafbeelding in Instellingen (center/crop).
- **B102** – extra fonts bundelen (Bebas Neue e.a.) + voorbeeld + 85%-fit;
  de .ttf's haalt install.bat op de eigen machine op.
- **B128** – handleiding/help voor `[crowd]`, `[pause]`, werkwijze, keuzes.

In v0.75 verwerkt (grote gecombineerde ronde):
- **B207** – taaldetectie filtert eerst vulregels ("na-na", "la-la", "oh-oh")
  weg met een structurele heuristiek (herhaling van korte lettergrepen +
  crowd-markers), niet met een woordenlijst; valt terug op de hele tekst als
  er anders niets zinnigs overblijft. `pipeline._is_filler_line`/
  `_strip_filler_for_language`.
- **B208** – als de twee beste taalkandidaten binnen 5% van elkaar liggen,
  vraagt de GUI alsnog om een keuze en laat `_language_for` Whisper zelf
  kiezen (`language_ambiguous`).
- **B191** – `songtekst.extend_coupling`: de automatische 1-op-1-koppeling
  haakt een aangrenzend, nog niet geclaimd gevonden woord aan zolang dat de
  fonetische gelijkenis merkbaar verbetert ("Tinus" → "Tien" + "Is").
- **B189** – de koppel-editor toont een dubbele koppeling van
  aaneengesloten gevonden woorden als één samengevoegd vak; opheffen splitst
  ze weer (`KoppelCanvas._merged_spans`).
- **B193** – losse crowd-regels (bestaan alleen in de karaoke) worden 1-op-1
  in de originele baan van de timing-editor gespiegeld.
- **B194/B195/B209** – zangstem-energie-analyse op de Demucs-zangstem van het
  origineel (`pipeline.ensure_original_vocals` borgt de stem). Aangehouden
  noten van betrouwbare regels lopen door tot de energie echt zakt
  (`ritme.held_note_end`), begrensd door de volgende inzet. Niet-
  getranscribeerde vulregel-reeksen worden op de energie-pulsen geplaatst
  (`ritme.energy_onsets`), met terugval op gelijkmatige/beat-verdeling.
  Aan/uit via Instellingen (`geavanceerd.zangstem_analyse`).
- **B196** – timing-editor toont onder de karaoke-golfvorm ook de zangstem
  (op de karaoke-tijdlijn geprojecteerd), kiesbaar als afspeelbron in "Bron";
  vaste, niet-meeschuivende baanlabels linksboven.
- **B198** – regels uit/aan te zetten vanaf de originele baan; het grijs geldt
  voor beide banen (`original_view_cells` draagt nu `rows`).
- **B201/B202** – klemtoon te bewerken op zowel karaoke als origineel (twee
  groepen in de editor, origineel-klemtoon bewaard in stap
  `klemtoon_origineel`). Het klemtoonverschil lijnt de karaoke-timing max één
  lettergreep-plek uit op het origineel (`timing.shift_stress_to` /
  `align_karaoke_stress`), zonder tekst of volgorde te wijzigen.
- **B206** – invoervelden tonen de originele bestandsnaam (opgeslagen in
  project.json) en de bestandskiezer opent op de laatst gebruikte map als die
  nog bestaat (`pipeline.input_display_name`/`input_start_dir`).
- **B195** – `install.bat` installeert de grote modellen nu altijd (melding +
  pauze i.p.v. J/N-vraag; `:skip_smart` verwijderd).

In v0.76 verwerkt:
- **B210** – Karaoketitel/Originele artiest/Originele titel per project in
  `project.json` (`pipeline.set_project_title`/`apply_project_titles`), geladen
  in `config.video` bij openen/projectwissel zodat de render ze oppakt.
  Eenmalige migratie van bestaande globale waarden; geen globale opslag meer,
  geen weglekken tussen projecten of verlies bij herstart.
- **B211** – het klankcluster-veld krimpt als eerste (minimaal ~2 clusters met
  eigen scrollbalk); pas daarna de vensterscrollbalk. Vensterminimum verlaagd
  naar 760×360.
- **B212** – gedeelde helper `pipeline.export_demucs_stems` schrijft bij elke
  Demucs-splitsing `karaoke_demucs.mp3` (instrumentaal) én `vocal_demucs.mp3`
  (zang) in de output-map. Aangeroepen bij "Karaoke uit origineel", de
  origineel-splitsing in `detect_track`, `ensure_original_vocals` en het
  genereren van de karaoke. (De karaoke-restzang-splitsing exporteert bewust
  niet, om de betekenisvolle originele stems niet te overschrijven.)
- **B213** – `songtekst.is_filler_word` + `align_lyrics(..., skip_filler=True)`:
  na-na/la-la-vulwoorden doen niet mee in de Needleman-Wunsch-uitlijning, zodat
  de echte woorden zuiver 1-op-1 koppelen en de koppellijnen niet scheef
  getrokken worden door een grote na-na-brok of hallucinatie. Timing van die
  vulregels loopt via de zang-energie (B209).

In v0.77 verwerkt:
- **B214** – instelbare output-map (`GeavanceerdSettings.uitvoermap`,
  `ProjectPaths.output_base`). Instellingen heeft een "Output-map"-blok;
  `pipeline.output_writable` test schrijfbaarheid, `relocate_output_base`
  verplaatst bestaande projectmappen en herschrijft de padverwijzingen in
  elk `project.json` (via `ProjectStore.rewrite_prefix`). Input en cache
  blijven bij de app-root. Terug naar `<root>/output` = standaard (geen
  eigen map). De keuze is globaal in config.json.
- **B215** – `pipeline.remove_demucs_stems` wist `karaoke_demucs.mp3` en
  `vocal_demucs.mp3` uit de output-map bij het kiezen van een nieuw
  origineel (aangeroepen vanuit `_choose_file`).
- **B220** – de koppel-editor krijgt een kolom-layout (`_relayout`):
  gekoppelde boven/onder-woorden delen een kolom, ongekoppelde krijgen een
  eigen kolom. Zo staan de koppellijnen recht door het hele nummer, ook bij
  veel ongekoppelde na-na-woorden op één rij. Hittesten en de samengevoegde
  vakken (B189) werken op de kolommen.
- **B216** – herziening van B211: het klankcluster-veld heeft nu verticale
  size-policy Ignored (kleine minimumhoogte), zodat het symmetrisch mee
  krimpt/groeit met het venster i.p.v. alleen omhoog te ratelen.
- Padscan: de code bevat geen harde absolute paden; alles wordt afgeleid van
  de app-root. (Alleen-lezen-locatie -> data naar %LOCALAPPDATA% volgt als
  B221.)

In v0.78 verwerkt:
- **B136** – tijdelijke knop "Modellen vergelijken" + `compare_models`/
  `_transcription_agreement` en de bijbehorende taalteksten/test verwijderd.
- **B223** – zangstembaan in de timing-editor onder de karaokeregels
  (constants verschoven; label mee).
- **B222** – koppel-editor voegt nu ook op de onderrij samen: meerdere
  aaneengesloten songtekstwoorden bij één gevonden woord als één vak, één
  lijn, klik = terugdraaien (`_merged_bottom_spans`), symmetrisch met B189.
- **B224/B225** – `ritme.active_windows`/`active_end` klemmen regels tot waar
  de zang echt klinkt (regels lopen niet meer over lege vocal-stukken);
  `count_repetitions` schat het aantal chant-herhalingen uit de energie.
  Ingehaakt in `_refine_with_vocals`.
- **B226** – `run_video(text_source, audio_source)` + `_render_audio`/
  `_render_timed_lines`; GUI toont bij "Video maken" een pop-up met één
  tekstsoort (karaoke/origineel) en één muzieksoort (karaoke/origineel/
  demucs/vocals). Standaard karaoke + karaoketekst.
- **B227** – `video.GAP_MIN_S`: instrumentaal gat ≥5s tussen twee regels ->
  geen (grijze) tekst maar een 3-2-1-afteller naar de volgende regel.
- **B221** – `filesystem.is_writable`/`resolve_data_root`: bij een alleen-
  lezen app-locatie gaan data (input/output/cache/logs/config) naar
  `%LOCALAPPDATA%\KaraokeTool`. `install.bat` zet de venv daar neer en de
  launcher geeft de datamap door via `KARAOKETOOL_DATA`. De code kent geen
  harde paden; assets/docs blijven leesbaar in de app-map.

In v0.79 verwerkt:
- **B230** – klik op de zangstem-golfvorm verzet de afspeellijn (seek-band
  uitgebreid met de zangbaan onderaan).
- **B232** – de cache-leegmaken-instelling is globaal (config.json) en
  persistent (round-trip bevestigd); staat standaard op wissen=True.
- **B229** – alle knoppen worden 'geel' (bezig) zolang hun actie loopt
  (`_install_busy_indicator`/`_mark_busy_click`); kleur instelbaar via
  `thema.knop_actief` (kleurkiezer bij GUI-kleuren, standaard #f2c200).
- **B222** – koppel-editor voegt onderrij-groepen nu op basis van
  overlappende doelen samen (`_merged_bottom_spans` groepeert transitief),
  dekt ook "Oh bébé," ↔ "Eh l'bébé"; de samengevoegde lijn is blauw zodra
  één lid handmatig gekoppeld is.
- **B228** – `songtekst.creative_couplings`: 2-op-1 ("fort minable" →
  "formidable") en 1-op-1-gaten binnen het ankervenster; verre duplicaten
  blijven buiten schot. Toegepast in `word_coupling_view`.
- **B234** – `timing.distribute_over_windows` +
  `pipeline._apply_energy_word_timing`: binnen elke regel worden de woorden
  over de zang-actieve deelvensters verdeeld, zodat pauzes tussen woorden in
  de timing komen. Zangstem geprojecteerd op de karaoke-tijdlijn; nette
  terugval zonder zangstem. (Lettergreep-rek bij aangehouden klinkers volgt.)

In v0.80 verwerkt:
- **B216 (definitief)** – de heel-venster-`QScrollArea` (B187) is verwijderd:
  die gebruikte de voorkeurshoogte van de inhoud, waardoor het flexibele
  clusterveld nooit meekromp. Nu stuurt de gewone `QMainWindow`-layout de maat
  (`setCentralWidget(central)`); het clusterveld en de video-"karaoketekst met
  timing"-group (beide stretch) groeien/krimpen met het venster. Instellingen
  kreeg een eigen `QScrollArea`. Venster-minimum 760×520.
- **B236** – `CacheSettings.wissen` standaard `False`; knop "Nu legen"
  (`_clear_cache_now`) naast het vinkje voor eenmalig legen.
- **B235** – `_do_generate_timing` waarschuwt als de timing op gelijkmatig
  terugviel (transcriptie/koppeling ontbrak, bv. na cache legen).

In v0.81 verwerkt:
- **B241** – `modules/fonetiek.py`: taalonafhankelijke segment-engine
  (`segment_word`, `segment_weight`, `distribute_word`, `SegmentConfig`) met
  taalregister `LANGUAGES` (nl/en; nieuwe taal = extra invoer). Gewichten:
  medeklinker 1, sonorant 2, korte klinker 6, lange klinkergroep 8; laatste
  klinker +30% reserve; min 15 ms. `timing.apply_phonetic_timing` herbouwt per
  woord de lettergreep-timing op segmenten (klinkers langer, slotklinker
  gerekt), aangeroepen in `generate_timing` na B234, achter
  `geavanceerd.fonetische_timing` (standaard aan) met terugval.
- **B242** – `video`: soepele regelverspringing; vlak na een nieuwe regel
  schuiven de regels in `_LINE_TRANSITION_S` (0,35 s) omhoog (kwadratische
  demping), met de uitgaande regel mee-getekend. Niet-uniforme y-posities
  blijven behouden.
- **B239** – `songtekst.is_symbol_token`/`_meaningful_words`: losse
  leesteken-/symbool-tokens uit de transcriptie gefilterd in `flat_transcript`
  én de uitlijning, zodat ze niet als koppel-doel verschijnen.
- **B240** – timinglijst ververst bij openen van de Karaokevideo-tab.
- **B237** – lege titelvelden bij een leeg project (bij opstart).
- Lettertype-voorbeeld: pangram per taal i.p.v. "Oerend hard".

In v0.82 verwerkt:
- **B248** – Demucs scheidt nog maar één keer per bron via een gedeelde
  cache (i.p.v. tot 4× het origineel).
- **B249** – Drift-bewuste uitlijning: robuuste mediaanfilter + monotoon
  afdwingen, `project_time` interpoleert lineair tussen regio's; timing loopt
  niet meer cumulatief weg in latere coupletten. Fijnere uitlijn-defaults
  (max_offsets 4→12, window 20→10 s, step 10→5 s).
- **B250** – Gewogen timing-ankers: betrouwbare ankers (zang-onset,
  lettergreep/hoog) winnen conflicten van herhaalde refreinregels.
- **B245** – Lettertype draagbaar opgeslagen (bestandsnaam i.p.v. absoluut
  pad), zodat de keuze niet terugvalt na mapverplaatsing/andere computer.
- **B241-vervolg** – Talen on-the-go: Frans ingebouwd; ontbrekende talen
  worden aangemaakt en met header/versie in de projectdiagnostiek + een
  gedeelde `talen/`-verzamelmap bewaard voor hergebruik
  (`fonetiek.ensure_language`/`save_language`/`load_language_dir`).
- **B247** – Render-pop-up: "Karaoke uit origineel" verwijderd; muziek is
  altijd "Karaoke-muziek".
- Karaokevideo-tab: overbodige invoer-hint verwijderd (staat in de
  handleiding). Meegeleverde `config.json`: cache-legen expliciet uit.
  Handleiding: knopvolgorde gelijkgetrokken met de app, optionele stappen
  gemarkeerd.
- **Review-hotfix (deze overdracht)** – `modules/fonetiek.py`: ontbrekende
  `from pathlib import Path` op moduleniveau toegevoegd (de forward-ref
  annotatie `-> "Path | None"` van `save_language` faalde in pyflakes en zou
  bij het wegschrijven van een taal een `NameError` geven). Lokale dubbele
  imports opgeruimd. pytest 321 groen, pyflakes schoon.

In v0.83 verwerkt:
- **B251** – geordende + gewogen timing-arbitrage met blok-barrières. Nieuwe
  `modules/timing_rules.py` (`Candidate`, `best_per_ref`, `arbitrate_anchors`,
  `clamp_refinement`): ankers worden gekozen op effectief gewicht
  (basisgewicht × confidence). `timing.sanitize_timing` gebruikt die engine nu
  voor de ankerreeks. **Kern-fix** (herhaalde refreinen/Formidable): een anker
  uit een eerder blok wordt niet meer door een later blok verdrongen, zodat de
  offset van een refrein niet naar het volgende couplet lekt en elk blok op
  zijn eigen onset verankert. Toggle `geavanceerd.blok_anker_barriere`
  (standaard aan; uit = alles in één virtueel blok = oud gedrag). De
  ankergewichten (`anker_gewicht_lettergreep/hoog/woord/onset`) zijn tunebaar
  via `config.json` (zoals `SegmentConfig`), doorgegeven vanuit
  `generate_timing`. Voor één blok is het gedrag identiek aan v0.82 (B250
  behouden), geverifieerd door de suite.
  - **Eval-harnas** – `modules/timing_eval.py` (`vergelijk`/`vergelijk_paden`/
    `format_report`) + CLI `python -m tools.timing_eval <auto.json>
    <referentie.json>`: vergelijkt auto- met handmatige timing per blok en
    totaal (gem./mediaan/max |onset-fout| en |duur-fout| in ms); alleen regels
    met exact dezelfde tekst tellen mee. Hiermee is "dichter bij mijn versie"
    meetbaar.
  - **Openstaand / vervolg**: de acceptatie op "Lied G"
    (blokken 2–6 omlaag) en op Formidable moet op de gebruikers-pc worden
    gemeten (stap 0 = `timing_auto.json` opnieuw genereren op v0.83 en met
    `tools/timing_eval` tegen de handmatige `timing.json(.bak)` afzetten,
    daarna de gewichten bijstellen). De audio/referenties zitten niet in de
    zip. De engine is klaar om **per-blok zang-onset-kandidaten** te
    accepteren (spec-prioriteit 3); die bron koppelt de zang-energie-analyse
    (`_refine_with_vocals`/`ritme`) in als extra ankers – een vervolgstap die
    de audio nodig heeft. `clamp_refinement` staat klaar om fonetiek/energie-
    vensters als verfijning binnen de anker-span te klemmen.
- **B252** – underscore koppelt woorden tot één lettergreep. `split_syllables`
  geeft een woord met `_` als één lettergreep terug (marker blijft intern
  staan); `apply_phonetic_timing` splitst zo'n woord niet fonetisch op; in de
  render (`video._disp`) wordt de underscore een spatie, ook bij het meten van
  de tekstbreedte. Voorbeeld: `'k_heb` (één lettergreep, gezongen "kep")
  toont als "'k heb". Woordgrens- en komma-detectie blijven op de ruwe tekst.
- **B253** – dode vertaal-sleutels `video_prep_hint` (nl+en) verwijderd (de
  zichtbare invoer-hint op de Karaokevideo-tab was in v0.82 al weg; alleen de
  sleutels bleven achter). nl/en-sleutelsets blijven gelijk.
- **Onderhoud** – stale Qt-test `test_klemtoon_canvas_zet_klemtoon`
  gelijkgetrokken met de grouped `KlemtoonCanvas`-API (B201/B202); die faalde
  alleen als PySide6 aanwezig is. Enkele ongebruikte test-imports opgeruimd
  (pyflakes schoon over modules/tools/tests). pytest 349 groen.

In v0.84 verwerkt (bevindingen van "Lied B"):
- **B256** – `ritme._rms_envelope` cachet nu ook het faalresultaat (per
  bestand pad+mtime+grootte). Root cause: een kapotte/incompatibele numba-
  installatie op de gebruikers-pc (`AttributeError: module 'numba' has no
  attribute 'core'` tijdens librosa's JIT-compilatie) liet elke regel/zin
  van een lied dezelfde dure en kapotte `librosa.load`-aanroep opnieuw
  proberen, met een volledige stacktrace per keer (189× identieke meldingen
  bij één lied in de log van vandaag). Nu wordt zowel het faalresultaat
  gecachet als de foutmelding maar één keer per bestand gelogd. Dit lost het
  achterliggende numba-probleem zelf niet op (dat zit in de Python-omgeving
  van de gebruiker, niet in de code) maar voorkomt de herhaling.
- **B254** – forced-alignment-venster terug: dezelfde kapotte numba-
  installatie liet ook `woorduitlijning._load_mono_16k`'s
  `librosa.resample`-stap falen (nodig omdat WhisperX op 16 kHz werkt), met
  stille terugval op het audiopad - waarna WhisperX zelf de audio via een
  ffmpeg-subprocess laadt, wat het opflitsende venster van vóór B97
  reintroduceert. Nieuwe `woorduitlijning._resample_to` probeert eerst
  librosa, valt bij een fout terug op `scipy.signal.resample_poly` (geen
  numba nodig, scipy is al een kernafhankelijkheid), zodat de in-process
  aanpak - en dus geen venster - ook overeind blijft als librosa/numba
  kapot is.
- **B260 (kern-fix)** – een gemengd blok (zang + losse crowd-regels) telde
  crowd-regels nooit mee in de regelkoppeling met de songtekst
  (`timing.couple_timing`'s `kar_zang`), zelfs niet als het aantal
  karaokeregels (crowd inbegrepen) precies het aantal songtekstregels
  evenaarde. Bij "Lied B" (5 karaokeregels: 2 crowd + 3 zang,
  tegen 5 songtekstregels) bleven de crowd-regels ("De Rood Wit-te
  Zangers...") daardoor ongekoppeld en kregen ze een kort "tussenroep"-
  slotje i.p.v. de tijd van hun songtekstregel ("Met bloed, zweet en
  tranen") - dat verstoorde ook de originele-baan in de golfvorm-editor.
  `kar_zang` telt crowd nu gewoon mee zodra de blokgroottes matchen (blok-
  en losse-regel-crowd); matchen ze niet, dan blijft het oude
  tussenroepje-gedrag gelden (bv. een publieks-"Oeh!" zonder songtekst-
  equivalent). De finale toewijzing gebruikt nu `line.index in assign` i.p.v.
  een aparte crowd-check, zodat beide plekken gegarandeerd in sync blijven.
- **B257 (bleek symptoom van B260)** – de gespiegelde crowd-regel in de
  golfvorm-editor zag eruit als "een karaokezin tussen de originele
  zinnen" doordat hij (door B260) nooit gekoppeld raakte en dus altijd via
  `gui.py`'s crowd-spiegel-logica (B193) als extra, losse cel verscheen
  bovenop de songtekstregel die er al stond. Met B260 gefixed komt de
  crowd-regel gewoon op zijn juiste, gekoppelde plek terecht en verschijnt
  er geen aparte cel meer. De eerder toegevoegde `crowd`-vlag op
  `originals`-dicts (`gui.py`/`timing.original_view_cells`/
  `timingeditor.py`, rood/gestippeld met `[crowd]`-label) blijft nuttig
  voor het overblijvende, écht-ongekoppelde geval (een tussenroepje zonder
  songtekst-equivalent).
- **B258** – Whisper-hallucinatie "ZANG EN MUZIEK" (functiewoord "en"
  plakt twee woorden aan elkaar) overleefde `pipeline._filter_hallucinations`
  omdat die alleen een heel segment verwerpt als *alle* woorden op de
  vaste `cluster.HALLUCINATIONS`-lijst staan; "zang" stond daar niet op.
  Functiewoorden ("en", "de", "het", "een") tellen nu niet meer mee bij die
  check. "zang" is toegevoegd als signaalwoord, maar **alleen** op
  segmentniveau in `pipeline.py` (niet aan `cluster.HALLUCINATIONS` zelf,
  dat zou ook de klankclustering/demping raken) en **alleen** als het
  woord nergens (fonetisch, via `cluster.similarity`) in de songtekst van
  dit lied voorkomt - een lied dat "zang" echt bezingt verliest dat woord
  dus niet. `MUZIEK`/`ondertiteling`-achtige generieke Whisper-artefacten
  blijven altijd hallucinatie, ongeacht de songtekst.
- **B255 (onderzocht, geen bug)** – "Woorden koppelen" toont bewust
  getranscribeerde woorden van het **origineel** gekoppeld aan de
  **songtekst** (beide origineel-gebaseerd); de karaoke komt pas in beeld
  bij "Timing verfijnen" en de golfvorm-editor. Handleiding verduidelijkt
  dit nu expliciet zodat het niet meer als dubbele-origineel-tekst-bug
  oogt.
- **B259 (onderzocht, geen bug)** – na een ffmpeg-update werd ffmpeg pas
  na een reboot weer gevonden (Windows-PATH wordt pas ververst in nieuwe
  processen/sessies, hetzelfde als install.bat al meldt na een
  winget-installatie). Geen codewijziging nodig.
- **ffmpeg 9.0 gecontroleerd** – de verwijderde/gewijzigde onderdelen in
  9.0 (CELT-decodering, verouderde NVENC-opties) raken geen van de
  ffmpeg/ffprobe-aanroepen in dit project (`-acodec pcm_s16le`,
  `-codec:a libmp3lame`, `-c:v libx264 -preset medium -crf 18
  -pix_fmt yuv420p`, ffprobe `-show_format -show_streams
  -print_format json`) - allemaal brede, stabiele opties. Geen
  codewijziging nodig. `install.bat` pint sowieso geen versie (`winget
  install -e --id Gyan.FFmpeg` haalt altijd de nieuwste stable), dus nieuwe
  installaties krijgen 9.0 vanzelf; bestaande installaties worden zoals
  altijd niet automatisch geüpgraded (bewust, zelfde beleid als Python).
- pytest 365 groen (349 + 16 nieuwe B254/B256/B257/B258/B260-tests in
  `tests/test_v084.py`), pyflakes schoon over modules/tools/tests.

In v0.85 verwerkt (afwerken "Lied B", opzet "Lied
P"/Sunday Bloody Sunday):
- **B261** – regels liepen soms fors door tot vlak vóór de volgende regel
  begon, terwijl de voice-only-baan er al (bijna) stil bij lag (visueel
  goed te herkennen). Root cause: `ritme.active_end` (de B224-terugknip die
  een regel moet inkorten tot waar de zang echt stopt) toetste de
  stilte-drempel (`thr_ratio`) tegen `window.max()` - de piek **binnen**
  het venster `[start, end]` zelf. Was dat venster al door B194 (aangehouden
  noot volgen) opgerekt tot vlak vóór de volgende regel, en zat er toevallig
  nog wat resterend geluid/ruis (bv. wegstervend crowd-geroep) vlak vóór het
  venstereinde, dan werd dát de lokale "piek" en bleef de drempel
  (piek × 8%) bijna overal gehaald - `active_end` vond dan geen stilte en
  er werd niets teruggeknipt. Geverifieerd op "Lied B":
  karaokeregel 8 kreeg in `timing_auto.json` 8,43s toebedeeld, terwijl de
  eigenlijke songtekst-uitlijning (woordniveau) maar 5,2s besloeg - de
  resterende ~2s (de adempauze vóór de volgende regel) werd "opgegeten".
  `active_end` toetst de drempel nu tegen de piek van de **hele**
  zangstem-envelop (stabiele referentie, ongeacht hoe ver het venster zelf
  al is opgerekt) i.p.v. tegen zijn eigen, mogelijk al vervuilde venster.
- **B262** – elke projectwissel (`gui.py`'s `_switch_instance`, gebruikt
  door zowel "Nieuw project" als het overschakelen naar een bestaand
  project) schakelt nu terug naar het eerste tabblad ("Audio"). Voorheen
  bleef je op het tabblad staan waar je toevallig was (bv. Instellingen of
  Handleiding) terwijl het nieuwe/andere project juist bij invoerbestanden
  op het Audio-tabblad begint. De `QTabWidget` is nu bewaard als
  `self._tabs`.
- **B263** – Whisper hield bepaalde woorden consequent vast (dezelfde
  denkfout bij elke herhaling van eenzelfde frase). `whisper.transcribe()`
  geeft nu de (gededupliceerde, unieke-woorden-eerst) songtekst mee als
  `initial_prompt` aan faster-whisper, alleen voor het origineel-spoor
  (`songtekst.deduped_prompt_text`, ingekort op woordgrens tot
  `INITIAL_PROMPT_MAX_CHARS`). Herhalingen (refreinen, "Sunday, Bloody
  Sunday" ×4, ...) worden eerst verwijderd zodat de beschikbare ruimte aan
  de volledige unieke woordenschat opgaat, niet aan dezelfde woorden
  telkens opnieuw. De prompt telt mee in de whisper-cachesleutel: een
  bewerkte songtekst zonder audiowijziging transcribeert opnieuw.
- **B264** – nieuwe `[bg]...[/bg]`-notatie (analoog aan `[crowd]`:
  block/regel/inline) voor gelijktijdige achtergrondzang - tekst die
  *tegelijk* met de vorige regel klinkt in plaats van erna, zoals een
  backing-vocal "(Tonight, tonight)" naast de lead "Sunday, Bloody Sunday"
  in "Sunday Bloody Sunday" (project "Lied P"). Werkt onafhankelijk
  in zowel `songtekst.txt` (`songtekst.LyricWord.bg`) als `karaoketekst.txt`
  (`karaoketekst.TextLine.bg`) - het ene bestand kan `[bg]` gebruiken zonder
  het andere. Een `[bg]`-regel/woord: telt niet mee in de blok-/regeltelling
  van `couple_timing` (net als een niet-matchend crowd-blok, B260) en wordt
  overgeslagen in de DP-woorduitlijning (`songtekst.align_lyrics`, net als
  filler-woorden via `skip_filler`) zodat hij geen transcriptiewoorden van
  de lead wegkaapt; krijgt via de nieuwe `timing.attach_bg_lines` hetzelfde
  tijdvak als zijn voorgaande (niet-bg) regel i.p.v. een eigen plek; en
  wordt standaard niet getoond in "Timing verfijnen" en niet gerenderd
  (`TimedLine.uitgeschakeld=True`, per regel weer aan te zetten in de
  editor). De tekst telt wél mee in B263's `initial_prompt` en B258's
  songtekst-aanwezigheidscheck.
- pytest 381 groen (365 + 16 nieuwe B261/B262/B263/B264-tests in
  `tests/test_v085.py`; 1 daarvan slaat over zonder PySide6), pyflakes
  schoon over modules/tools/tests.

In v0.86 verwerkt:
- **B265** – "1 Detecteer woorden" opnieuw draaien met een échte nieuwe
  transcriptie (andere audio/model/taal/`initial_prompt`, dus géén
  cache-hit in `pipeline.detect_track`) liet oude, handmatige woordkoppeling
  (stap "2 Woorden koppelen", `woordkoppeling.pins`) gewoon staan. Die pins
  verwijzen naar transcript-**indices** van de oude transcriptie; na een
  echte herdetectie kloppen die posities niet meer met de nieuwe tekst, maar
  werden ze alsnog toegepast (`songtekst.apply_pins`) - gemeld als "Ik heb de
  woorden gekoppeld. Er zat nog oude data in." Nieuwe
  `pipeline.invalidate_after_fresh_transcript()` wist nu, alleen bij een
  echte nieuwe transcriptie (niet bij een cache-hit), de stappen
  `woordkoppeling`, `align`, `koppeling` en `timing` (plus de
  timing-bestanden) - dezelfde stappen als `invalidate_derived`, maar
  zonder de invoerbestand-specifieke opruiming (Demucs-stems,
  transcript/songtekst-override) die hier niet van toepassing is. Een
  ongewijzigde herdetectie (cache-hit) laat de handmatige koppeling
  terecht met rust; alleen een écht nieuwe transcriptie triggert de
  opruiming.
- pytest 383 groen (381 + 2 nieuwe B265-tests in `tests/test_v086.py`),
  pyflakes schoon over modules/tools/tests.

In v0.87 verwerkt (bevindingen bij het afronden van "Lied P"):
- **B266** – de "Video klaar"-vraag toonde per ongeluk zowel de Nederlandse
  als de Engelse tekst: `video_done_prompt` in de NL-vertaling was letterlijk
  `"{title}:\n{target}\n\nMeteen openen? / Open now?"` - de EN-tekst stond
  hardcoded ín de NL-string geplakt, geen taalselectie-bug. Nu gewoon
  `"Meteen openen?"`.
- **B267** – naast "Video openen" staat nu ook een knop **"Map openen"**
  in de video-klaar-dialoog. Nieuwe `pipeline.open_folder(path)` (analoog
  aan het bestaande `open_file`, zelfde cross-platform aanpak: `os.startfile`
  op Windows, `open` op macOS, `xdg-open` op Linux) opent de *bevattende*
  map als `path` een bestand is. De dialoog zelf is vervangen: i.p.v.
  `_ask_yes_no` (Ja/Nee) is er nu `_ask_video_done` met drie knoppen
  ("Video openen" / "Map openen" / "Sluiten", nieuwe vertaalsleutels
  `open_video_button`/`open_folder_button`, `close` bestond al).
- **B268** – bij een instrumentaal gat (≥5s tussen twee regels, B227) werd
  de al gezongen én de eerstvolgende regeltekst tot nu toe volledig
  weggehaald tijdens de 3-2-1-afteller (`_compose_frame` deed een vroege
  `return frame` ná het tekenen van het cijfer, vóór de normale
  regelweergave). Gemeld gedrag: de tekst verdween en kwam pas terug als de
  afteller klaar was, i.p.v. gewoon door te schuiven. De `return` is
  verwijderd: de afteller wordt nu als **overlay** getekend, waarna de
  normale drie-regel-weergave (net gezongen grijs, eventueel de wachtende
  regel wit) gewoon doorloopt - `active_index` bleef toch al op de laatst
  gestarte regel staan tijdens het gat, dus er was geen andere aanpassing
  nodig. Het cijfer verdwijnt vanzelf zodra `countdown_number` weer `None`
  teruggeeft.
- pytest 387 groen (383 + 4 nieuwe B266/B267/B268-tests in
  `tests/test_v087.py`; 1 daarvan was eerst als losse test in
  `test_video.py` toegevoegd en is voor consistentie met eerdere
  B26x-versies hierheen verplaatst - geen netto-toename op dat punt),
  pyflakes schoon over modules/tools/tests.

In v0.88 verwerkt:
- **B270** – na B268 (de 3-2-1-afteller als overlay tijdens een
  instrumentaal gat, i.p.v. de tekst te verbergen) bleek de afteller zelf
  nog op een vaste beeldpositie te staan (`height * 0.18`), los van hoeveel
  ruimte de tekstregel er vlak boven inneemt. Een regel die lang genoeg is
  om door `_wrap_syllables` over 2 rijen verdeeld te worden, kan dan het
  cijfer overlappen: dat gebeurt specifiek met de regel op **slot -1** (de
  regel die tijdens de soepele B242-overgang, of tijdens een gat, boven de
  actieve regel in beeld blijft) - niet met de regel die net vóór het gat
  gezongen werd, want die staat zelf op slot 0 en groeit met zijn eventuele
  tweede rij omlaag, weg van het cijfer. Nieuwe helper
  `_line_text_height(line, font, width)` berekent (met dezelfde
  `_wrap_syllables`-logica als `_draw_line`) hoeveel px een regel inneemt;
  nieuwe `countdown_y(above_slot)`-closure in `_compose_frame` gebruikt dat
  om de cijferpositie te bepalen: de vaste basispositie, of - als de regel
  op `above_slot` meer ruimte inneemt - net onder die regel, met een harde
  marge (`_MIN_MARGIN_BOVEN_SLOT0 = 12px`) vóór slot 0's tekst zodat het
  cijfer nooit in de eerstvolgende regel zelf terechtkomt. De intro-afteller
  (vóór de allereerste regel) heeft geen slot -1 en bleef dus altijd al
  veilig; die gebruikt dezelfde helper met `above_slot=None` (geen
  gedragswijziging, puur voor consistentie).
- pytest 390 groen (387 + 3 nieuwe B270-tests in `tests/test_v088.py`),
  pyflakes schoon over modules/tools/tests.

In v0.89 verwerkt:
- **B271** – een videorender met een niet-standaard muziek-/tekstcombinatie
  (via de B226-renderdialoog, bv. `audio_source="vocals"` +
  `text_source="origineel"` voor voice-only-muziek met de originele tekst)
  kreeg dezelfde bestandsnaam (`<titel>.mp4`) als de standaardrender
  (karaoke-muziek + karaoketekst) en overschreef die dus stilzwijgend bij
  elke nieuwe variant. Nieuwe `pipeline.render_filename_suffix(audio_source,
  text_source)` levert nu een leeg achtervoegsel voor de standaardcombinatie
  (geen wijziging in bestaand gedrag/bestandsnamen), en anders
  ``_<muziek>_<tekst>`` met 3-letter-codes (`_AUDIO_SUFFIX_CODES`/
  `_TEXT_SUFFIX_CODES`: kar/ori/voc/dem) - muziek eerst, tekst tweede, zoals
  gevraagd. Voorbeeld: `titel_voc_ori.mp4`. Een onbekende bron (zou niet via
  de GUI moeten voorkomen) valt terug op de eerste 3 letters van de
  broncode zelf i.p.v. te crashen.
- pytest 394 groen (390 + 4 nieuwe B271-tests in `tests/test_v089.py`),
  pyflakes schoon over modules/tools/tests.

In v0.90 verwerkt:
- **B272** – vervolg op B270: bij een lang instrumentaal gat liet de
  "bevroren"-layout de regel op slot -1 (de oudste zichtbare, al uit de
  "nu bezig"-aandacht) gewoon staan naast de wachtende regel(s), met
  daartussen een groot leeg gat waar de 3-2-1-afteller dan los in moest
  passen (zichtbaar bij "Lied P": "Zondag, Lied P."
  bovenaan, "Ja, kom op!" (gezongen) erna, dan een leeg gat, dan pas de
  eerstvolgende regels ver onderaan). Op expliciet verzoek verdwijnt de
  regel op slot -1 nu helemaal tijdens het gat; de resterende 3 regels
  (net gezongen op slot 0 - eerstvolgende op slot 1 - daarna op slot 2)
  en de afteller ertussen verdelen zich gelijkmatig over 4 posities
  binnen dezelfde verticale band (voorheen de ruimte tussen slot 0 en
  slot 2). Resultaat: "Ja, kom op!" (grijs) - afteller - "Het decor..."
  - "Want de werkdruk...", zonder leeg gat. De B270-marge-logica
  (afteller schuift mee als de regel erboven over 2 rijen loopt, met een
  harde marge vóór de eerstvolgende regel) blijft binnen dit compactere
  schema intact. De crowd-regel onder slot 0 (normaal een vaste
  `height*0.45`) is ook gat-bewust gemaakt, want slot 0's y verandert nu
  tijdens een gat.
- **B273** – het versienummer van KaraokeTool staat nu in de metadata van
  elke gerenderde video (ffmpeg `-metadata comment="KaraokeTool vX.Y.Z"`),
  zodat bij het testen achteraf te achterhalen is met welke versie een
  videobestand precies is gemaakt (`ffprobe -show_format` toont de tag).
- pytest 397 groen (394 + 3 nieuwe B272/B273-tests in `tests/test_v090.py`;
  de 2 B270-tests in `tests/test_v088.py` die de oude slot -1-zichtbaarheid
  toetsten zijn herschreven naar de nieuwe slot 0-marge-situatie), pyflakes
  schoon over modules/tools/tests.

In v0.91 verwerkt:
- **B274** – bij "Lied I" (parodie op "500 Miles") koppelden
  cijferwoorden in de songtekst ("500", "1000") nooit aan Whisper's
  transcriptie, ook niet als Whisper het getal voluit schreef ("five
  hundred"). Root cause: `phonetic_key` houdt alleen letters over, dus een
  puur-cijferwoord kreeg een LEGE sleutel, en `similarity` geeft voor een
  lege sleutel altijd 0.0 terug - hoe Whisper het getal ook schreef. Nieuwe
  `cluster.number_word_forms(n)` zet een niet-negatief geheel getal (0 t/m
  999.999.999 - "10.000.000" komt soms voor in songteksten, "miljard"/
  "billion" en hoger niet) om naar de Nederlandse ÉN Engelse voluit-vorm,
  als twee APARTE strings (bewust niet samengevoegd tot één sleutel - dat
  bleek de fonetische match te vervuilen/verlengen en verlaagde de
  gelijkenis juist). `cluster.number_key_best_match(text, other_key)`
  probeert bij een cijferwoord beide taalvormen tegen de vergelijkings-
  sleutel en kiest de beste; `songtekst._align_core` gebruikt dit via
  lokale `_lyric_key_for`/`_lyric_sim`/`_lyric_pair_sim`-helpers i.p.v. de
  vaste `lyric_keys[i]`, zowel in de DP-tabelopbouw als de terugloop
  (m11/m21/m12). Geen regressie voor gewone (niet-cijfer) songtekstwoorden.
- **B275** – een gemeld GUI-probleem: de Karaoketitel aanpassen en meteen op
  "Detecteer woorden" klikken paste de wijziging soms niet toe (wel als je
  eerst een ander veld aanklikte). Root cause: de titelvelden bewaren via
  `editingFinished` (vuurt af bij Enter of focusverlies), maar een
  muisklik op een `QPushButton` neemt de focus van een `QLineEdit` niet
  altijd betrouwbaar over vóór de klik zelf wordt afgehandeld
  (platform-/stijlafhankelijk, met name op Windows) - de stap-knoppen lazen
  daardoor soms nog `self._context` van vóór de wijziging. Nieuwe
  `_commit_pending_field()` dwingt expliciet `clearFocus()` af op een actief
  invoerveld, aangeroepen als eerste regel in alle stap-handlers
  (Detecteren/Koppelen/Analyseren/Karaokevideo/Timing maken/Klemtoon
  bewerken/Timing bewerken/Video maken) - `editingFinished` vuurt zo
  gegarandeerd vóór de knop zijn actie start, ongeacht focusgedrag.
- **B276** – vulwoorden ("oh", volledige "da-da-da"/"la-la-la"-blokken)
  werden via `align_lyrics(..., skip_filler=True)` altijd uit de
  hoofduitlijning gehouden, ook als Whisper ze prima had getranscribeerd
  (concreet gemeten bij "Lied A": "oh" stond met confidence 0.92
  precies tussen "veranderd" en "het" in de transcriptie, maar toonde
  "(niet gekoppeld)"). `align_lyrics` doet nu, ná de DP-uitlijning op de
  "echte" woorden, per overgeslagen vulwoord een matchpoging binnen het
  transcript-venster tussen de twee dichtstbijzijnde wél gekoppelde
  buurwoorden (`similarity`/`phonetic_key`, drempel `_FILLER_MATCH_FLOOR
  = 0.6`); alleen zonder goede match blijft het woord ongekoppeld (oude
  energie-timing-terugval). Elk woord van een vulwoord-blok wordt apart
  gematcht (met een `claimed`-set zodat opeenvolgende "da"'s niet naar
  hetzelfde transcript-woord graaien) - een blok zonder échte match in het
  venster (bv. Whisper hoorde er niets zinnigs) blijft gewoon overgeslagen,
  geen regressie. Nieuwe `pipeline._filler_priority_lines` vergelijkt
  songtekst.txt/karaoketekst.txt regel voor regel (ze delen dezelfde
  regelstructuur); bevat de karaoketekst-regel écht (niet-vulwoord) content
  terwijl de songtekst-regel een vulwoord heeft, dan geldt een soepelere
  drempel (`_FILLER_MATCH_FLOOR_PRIORITY = 0.5`) omdat de timing daar
  direct bepaalt waar de karaoke-inhoud in beeld komt.
- **B277 (eerste versie - zie "In v0.92 verwerkt" voor de herziening)** –
  zinnen bleven vaak te lang "aanstaan": de gebruiker herleidde dit
  (deels) tot `held_note_end`/`active_end`, die de zangenergie op een
  ENKEL RMS-steekpunt toetsten (`window >= drempel`). Concreet gemeten
  (`active_end` op een regel in "Lied A": een verhoogde
  `thr_ratio` van 0.08 naar 0.20 veranderde het afkappunt maar 0.02s)
  blijft een hardnekkige lage ruisvloer/nagalm op individuele steekpunten
  net boven zelfs een verhoogde drempel hangen, terwijl het GEMIDDELDE
  daar al (bijna) nul is - exact zoals de gebruiker het omschreef
  ("gemiddelde waveform over 0.1 seconden is bijna 0"). Nieuwe gedeelde
  `ritme._last_active_time(rms, times, mask, drempel)` toetste een ~0.1s
  (`_ACTIVE_WINDOW_S`) glijdend gemiddelde i.p.v. een los steekpunt;
  `held_note_end` (oprekken, met floor/ceil) en `active_end` (terugknippen,
  songbrede piek - B261 blijft intact) waren dunne wrappers om deze helper.
  Apart onderzocht en NIET in scope: het achtergrondkoor-geval (energie
  blijft 16-80% van de piek, dus een genuine tweede stem, geen ruis/
  residueel signaal) - dat vereist echte bronscheiding en blijft een
  handmatige correctie, zoals de gebruiker bevestigde.
- **B278** – het Karaokevideo-tabblad toonde geen enkele voortgang tijdens
  "Video maken" (eerste render) buiten de subtiele B229-gele-knop-styling;
  de échte ffmpeg-encodeer-voortgang ging alleen naar de balk op het
  Audio-tabblad (`self._progress`/`self._status`, gebouwd in
  `_build_progress_group`, dat alleen aan `audio_layout` hangt).
  `_build_video_tab` heeft nu een eigen `self._video_progress`
  (`QProgressBar`) + `self._video_status` (`QLabel`) onder de knoppenrij;
  `_on_progress`/`_on_message`/`_set_busy` en de "video klaar"-afhandeling
  in `_do_render_video` schrijven er nu telkens ook naartoe, zodat beide
  balken altijd in sync blijven zonder de achtergrondtaak-bedrading zelf
  aan te passen.
- **B279** – apart van B277 (zin-lengte): ook de lettergreep-uitlijning
  bínnen een regel kon misgaan. Root cause in `timing._spans_over_words`:
  alle karaoke-lettergrepen werden in één platte pas, puur op relatieve
  POSITIE, over de totale originele-woorden-tijdlijn geresampled. Concreet
  aangetoond met "Ik zeg miauw." (9 lettergrepen) tegen origineel "hoe is
  het nou?" (4 woorden, laatste opgerekt tot 3.42s door B194/B277): de
  lettergreep "auw." (eind van "miauw", positioneel toevallig in het 4e
  woord se venster) erfde 3.42s, terwijl "Ik" (1e lettergreep, hoort qua
  ritme bij het korte "hoe") maar 0.28s kreeg - een compleet verkeerde
  verhouding. Nieuw tweetraps-``_spans_over_words``: eerst worden de
  KARAOKE-woorden (``_karaoke_word_groups``, groepeert ``pieces`` op de
  voorloopspatie-grens van ``split_line``) evenredig over de originele
  woorden geprojecteerd (dezelfde gelijkmatige-verdeling als elders in de
  codebase voor regels/blokken), pas dáárna worden de lettergrepen binnen
  elk gematchte woordpaar gelijkmatig verdeeld. Resultaat op hetzelfde
  voorbeeld: "miauw" (het hele woord, gekoppeld aan het opgerekte "nou?")
  deelt de 3.42s met zijn 2 lettergrepen (1.77s elk), en "Ik" krijgt 0.51s
  (in lijn met de kortere eerste 3 originele woorden) i.p.v. 0.28s.
- pytest 413 groen (397 + 16 nieuwe B274-B279-tests in `tests/test_v091.py`),
  pyflakes schoon over modules/tools/tests.

In v0.92 verwerkt:
- **B277-herziening** – de gebruiker vroeg expliciet om B277 op echte
  projectdata te toetsen: "Lied_A"s `timing.json` (zijn
  handmatig verbeterde versie) vergelijken met `timing_auto.json`
  (dezelfde auto-run) om te zien of v0.91's aanpak dichterbij komt. Op
  dat specifieke project bleken beide bestanden echter identiek (geen
  losstaande handmatige correctie beschikbaar als referentie) - na
  herladen vanaf de gedeelde map bleek dit te kloppen, en de gebruiker gaf
  aan ook de "2 vorige projecten" te mogen gebruiken (`Bier__Zang_en_
  Zangers` en `Lied_P`, met de waarschuwing dat laatstgenoemde
  op stukken het bekende achtergrondkoor-probleem heeft en dus minder
  representatief is). Op `Lied_B` (wél schone testcase, 47
  regels, 31 met verschil >0.3s tussen auto en handmatig) bleek v0.91's
  glijdend-gemiddelde-aanpak nauwelijks te helpen (verbeterde slechts 2
  van de 31 gevallen) - de werkelijke hoofdoorzaak was dat het
  analysevenster van een regel vaak doorloopt tot de start van de
  volgende regel, en "het laatste steekpunt boven drempel" dan de OPBOUW
  van die volgende regel pakt, ook met een lang stil gat ertussen.
  `ritme._last_active_time` is herbouwd naar een gap-gebaseerde aanpak:
  zoek van rechts naar links het eerste aaneengesloten stille gat
  (`_SUSTAINED_SILENCE_S = 0.3`) tussen twee boven-drempel-momenten en
  geef het laatste echte actieve moment daarvóór terug, op de RUWE
  RMS-steekpunten (geen smoothing meer) - een combinatie van smoothing +
  gap-detectie werd ook getest maar presteerde slechter (een korte
  opleving van ~0.07-0.08 fractie kon na middeling net boven de drempel
  uitkomen, waardoor een écht lang stil gat "dichtgesmeerd" werd; op één
  regel gaf dat 4.3s afwijking i.p.v. 0.2s). Resultaat op
  `Lied_B`: gemiddelde afwijking 1.63s -> 0.28s, mediaan
  1.47s -> 0.25s, max 3.22s -> 1.43s. `held_note_end`/`active_end` blijven
  dunne wrappers om de herbouwde helper; hun publieke signatuur en
  B261-songbrede-piek-gedrag zijn ongewijzigd. `tests/test_v091.py`s
  B277-tests zijn bijgewerkt naar het nieuwe gap-gedrag (van 16 naar 17
  tests: een extra test dekt het "geen lang gat gevonden -> oud gedrag"
  pad).
- **B277-nacontrole** – na oplevering van de gap-aanpak vroeg de gebruiker
  expliciet naar verdere verbeterpunten. Twee varianten empirisch getest op
  alle drie de projecten (Lied_A, Lied_B,
  Lied_P): (1) i.p.v. het EERSTE stille gat (≥0.3s) van rechts te
  pakken, het LANGSTE gat in het venster kiezen; (2) de sustain-drempel
  verhogen naar 0.4/0.5/0.6s. Geen van beide verbeterde de resultaten over
  de hele linie - "langste gat" presteerde op Lied_P zelfs
  duidelijk slechter (regel 0 en 40 sloegen door naar een veel te vroege
  afkap, afwijking 5.2s resp. 6.9s i.p.v. 0.6s/2.1s), en een hogere
  sustain-drempel verbeterde Lied_P licht maar verslechterde
  Lied_A. De huidige instelling (eerste gat, 0.3s) blijft staan;
  geen wijziging in `ritme.py`.
- **Regel-timing van Lied_A bijgewerkt** – op verzoek van de
  gebruiker is `output/Lied_A/settings/timing.json` opnieuw
  gegenereerd met de v0.92-inzichten (huidige bestand eerst weggezet als
  `timing.json.bak`). Omdat er geen `project.json`/`cache/`-context
  beschikbaar was om de volledige pipeline te draaien, is dit surgisch
  gedaan: per regel `held_note_end`/`active_end` toegepast op de
  bestaande start/eind-tijden (audio: `vocal_demucs.mp3`), en waar het
  eind wijzigde de lettergrepen herverdeeld via `timing._spans_over_words`
  met de originele Whisper-woorden uit `origineel/woorden.csv` (23
  segmenten, elk overlappend met 1-2 van de 46 karaoke-regels op
  tijdbasis - vastgesteld via tijd-overlap, niet 1:1 index-matching).
  Daarbij kwam een randgeval aan het licht: bij regel 17 ("Word jij een
  luiaard in een boom,") vond `active_end` een toevallig kort adempauze-
  gat (0.348s, net over de 0.3s-drempel) middenin de regel, terwijl de
  zang daarna gewoon doorliep tot het echte stille gat 1,7s verderop -
  zonder correctie had dat de laatste lettergrepen op nul-duur gezet.
  Opgelost met een gerichte guard in het regenereer-script (niet in
  `ritme.py` zelf, zie hierboven): een `active_end`-inkorting wordt
  genegeerd als het gevonden afkappunt meer dan 0.5s vóór het einde van
  het laatst overlappende originele woord ligt. Resultaat: 6 van de 46
  regels opgerekt via `held_note_end` (aangehouden noten als "miauw.",
  "pinguïn,"), regel 17 terecht ongewijzigd gelaten; de nieuwe eindtijden
  liggen opvallend dicht bij de oorspronkelijke `timing_auto.json`-
  waarden.
- **Knoplabel-fix** – de renderknop op het Karaokevideo-tabblad heette
  "4. Video maken (eerste render)", ook al gebruikt dezelfde knop/functie
  (`_do_render_video` → `pipeline.run_video` → altijd `timing.json`,
  nooit `timing_auto.json`) evengoed een herrender na een handmatige
  timing-correctie. Hernoemd naar "4. Video maken" (NL en EN in
  `modules/taal.py`) zodat het label geen aparte eerste-keer-only-actie
  meer suggereert.
- De B277-tests en de nieuwe knoplabel-test zijn ondergebracht in een eigen
  `tests/test_v092.py` (conform de bestaande conventie van één testfile per
  versie), i.p.v. verder aan te groeien in `test_v091.py`: de 3 B277-tests
  zijn daaruit verplaatst (16 → 13 in `test_v091.py`) en samen met 1 nieuwe
  knoplabel-test in `test_v092.py` gezet (4 tests).
- **B280** – bij het "Lied J"-project (parodie op Waylon Jennings -
  Good Ol' Boys) voegde de gebruiker een Dukes-of-Hazzard-dixietoeter toe
  aan het origineel, samengevoegd met Clipchamp; dat programma exporteert
  als `.m4a`. `filesystem.SUPPORTED_EXTENSIONS` kende alleen `.wav`/`.mp3`,
  terwijl ffmpeg/ffprobe (die alle audio-analyse/-conversie al doen) elk
  containerformaat even generiek verwerken - dit was dus puur een
  whitelist-uitbreiding, geen nieuwe verwerkingslogica. Op verzoek breder
  bekeken dan alleen m4a: `.flac`/`.ogg`/`.aac` zijn erbij gezet (alle vier
  door ffmpeg ondersteund; gangbaar bij lossless-rips/Audacity-export/
  kale AAC-streams). Aangepast: `SUPPORTED_EXTENSIONS` (nu 6 extensies,
  `.wav` blijft eerst - geen conversie nodig bij meerdere varianten),
  `find_audio_file`-docstring, de foutmelding in `prepare_track` (somt nu
  alle ondersteunde extensies op i.p.v. hardcoded ".wav of .mp3"), het
  bestandsdialoogfilter in `gui._choose_file`, de opruim-loop in
  `_generate_karaoke_from_original` (liep alleen `.mp3`/`.wav` af, nu
  `SUPPORTED_EXTENSIONS`), en `export.export_result`: een bron in een van
  de vier nieuwe formaten exporteert (net als mp3) naar `karaoke_edit.mp3`
  - er is geen los "m4a/flac/ogg/aac-uitvoerformaat"; de UITVOER blijft
  bewust beperkt tot mp3/wav (expliciete gebruikerswens, niet de invoer
  spiegelen). De bestaande test `test_export_unknown_format` gebruikte
  `.flac` als hét voorbeeld van een niet-ondersteund formaat; die is
  bijgewerkt naar `.xyz` nu `.flac` een geldig invoerformaat is.
- pytest 418 groen (414 + 1 export-test + 3 nieuwe B280-tests in
  `test_v092.py`), pyflakes schoon over modules/tools/tests.

In v0.93 verwerkt:
- **Tussenroepsel-timing (Lied J "Whoo!") – onderzocht, uiteindelijk
  gedropt** – de gebruiker vroeg waarom `ritme._last_active_time` (B277)
  überhaupt een stilte-gat zoekt bij een tussenroepsel/uitroep, terwijl dat
  eerder bedoeld was voor de juiste zin-lengte-timing in het algemeen, niet
  specifiek voor uitroepsels. Vervolgens gevraagd om empirisch te zoeken
  naar wat `timing_auto.json` het dichtst bij de handmatig gecorrigeerde
  `timing.json` brengt. In totaal zijn 9 signalen getest over twee
  sessies (een gap-scanrichting-fix: langste in plaats van eerste gat van
  rechts; een hogere/lagere sustain-drempel; een Whisper/songtekst-
  gebaseerde check of het eerstvolgende getranscribeerde woord na een
  regel een echt songtekstwoord is of vreemd geluid; en de eerdere B277-
  nacontrole-varianten) - geen enkele verbeterde het algemene beeld zonder
  elders een regressie te veroorzaken (bv. een fix voor "yeah," brak het
  legitieme korte laatste-lettergreep-geval "t'rug" in regel 6, omdat
  beide akoestisch niet te onderscheiden zijn: kort en geïsoleerd tussen
  twee stiltes). De gebruiker stuurde vervolgens expliciet bij: "dat zijn
  uitzonderingen, het gaat mij meer om het algemeen nu". Geconcludeerd:
  binnen aanvaardbaar regressierisico bestaat er geen robuuste algemene
  oplossing voor dit specifieke akoestische randgeval; dit item is
  gedropt uit de buildscope zonder wijziging in `ritme.py`.
- **B281** – de daadwerkelijke oorzaak van het "Whoo!"-probleem bleek niet
  in `ritme.py` te zitten maar in `songtekst.py`s koppel-DP: een
  meervoudige koppeling (m21/m12, twee songtekstwoorden tegen één
  transcriptiewoord of andersom) werd toegelaten op basis van de
  GECOMBINEERDE gelijkenis, waardoor "allow" (uit "Than the law will
  allow") in de DP-backtrack aan "land Whoo!" kon koppelen (combinatie-
  score 0.333) - het publieksgeluid "Whoo!" werd zo in de tijdsduur van
  "allow" getrokken. Een eerste poging met een vaste combinatie-drempel
  (`_MIN_MULTI_MATCH_SIM`, geprobeerd van 0.5 tot 0.34) bleek de bug niet
  te kunnen scheiden van de module's eigen "Kedeng Kedeng" ↔ "de trein"-
  vlaggenschipgeval: die scoort combinatie-gewijs exact hetzelfde (0.333),
  dus elke drempel ≥0.34 blokkeerde ook de legitieme koppeling en liet de
  DP-backtrack verschuiven (brak `test_align_matches_gedengedeng_and_
  de_trein` en `test_extra_intervals_finds_new_and_estimates_gap`). Fix:
  in plaats van de gecombineerde score, toetsen op de BESTE van de twee
  LOSSE helft-gelijkenissen (`_m21_best_half_sim`/`_m12_best_half_sim`,
  drempel `_MIN_MULTI_HALF_SIM = 0.3`). Dit scheidt de gevallen wél: bij
  Kedeng scoren "Kedeng"↔"de" én "Kedeng"↔"trein" allebei rond 0.333 (de
  BESTE haalt de drempel), bij "allow" scoort "allow"↔"land" 0.0 en
  "allow"↔"Whoo!" 0.25 (de BESTE haalt de drempel niet). Ook gecontroleerd
  dat dit niet te streng is: "is"↔"ik zo" heeft één helft op 0.0 maar de
  ANDERE op 0.5, en "beste van de twee" (niet "allebei verplicht") laat
  die legitieme koppeling terecht door. Alle 5 bestaande tests in
  `test_songtekst.py` plus 3 nieuwe tests in `test_v092.py` (Whoo!-geval
  geblokkeerd, Kedeng-geval blijft werken, `_MIN_MULTI_HALF_SIM` raakt
  geen m11-koppelingen) zijn groen.
- **B282: "Terug uit origineel"** – op verzoek een tegenhanger van dempen:
  in de dempingseditor kun je nu naast rode dempingsblokken ook groene
  blokken zetten die het bijbehorende stuk ORIGINEEL over de karaoke heen
  leggen (i.p.v. verzwakken), voor geluid dat Demucs (of een handmatige
  montage) heeft weggehaald maar dat er wel bij hoort (uitroep,
  geluidseffect) - "Karaoke aanpassen" (stap 4) kan alleen dempen, nooit
  iets terugzetten dat er niet meer is. Nieuw: `karaoke.RestoreInterval`
  + `karaoke.apply_restore()` (vervangt, i.p.v. mengt, de karaoke-samples
  binnen het venster door geresamplede origineel-samples, met dezelfde
  in/uit-crossfade-ramps als demping, toegepast NA de demping zodat
  hersteld geluid niet zelf gedempt wordt); `align.project_time_reverse`
  (de omgekeerde richting van `project_time`: karaoke-tijd → origineel-
  tijd, nodig omdat de gebruiker het venster op de KARAOKE-golfvorm
  markeert maar het bijbehorende origineel-fragment moet ophalen);
  `ffmpeg.resample_to_match` (expliciete doel-sample-rate/kanalen, i.p.v.
  `convert_to_wav`s "blijft gelijk aan de bron" - nodig omdat origineel en
  karaoke bij losse aanlevering elk hun eigen sample rate kunnen hebben).
  Persistentie via een nieuwe, aparte store-stap `restore_fragmenten`
  (naast `fragment_uitsluitingen`/de clusterdemping) zodat een latere
  stap-4-herrun (nieuwe clusterselectie) de handmatige restore-keuzes niet
  wegveegt - `run_karaoke` en `apply_manual_damping` passen ze allebei
  opnieuw toe, `reset_damping` ruimt ze samen met de gecachete resample op.
  Dempingseditor-UI: `DampingCanvas`-blokken zijn uitgebreid van
  `[start, end]` naar `[start, end, kind, label]` (kind = "demping" of
  "herstel"); een nieuwe knop "Terug uit origineel" voegt een groen blok
  toe; `_save()` splitst de blokken per kind en roept de save-callback aan
  met zowel de dempings- als de restore-spans. De editor-openknop vereiste
  voorheen dat stap 4 al had gedraaid (`context.store.get_step("karaoke")`)
  - dat is losgelaten naar alleen stap 1 (`pipeline.stored_wav`), zodat de
  restore-functie ook zonder voorafgaande clusterselectie bereikbaar is.
  Gevalideerd met een gerichte test (`test_apply_manual_damping_terug_
  uit_origineel`): de herstelde audio komt aantoonbaar uit het origineel
  (RMS > 0.3 binnen het venster vs. ~0 erbuiten), en de keuze overleeft een
  volgende dempings-only-aanroep.
- **B283: klankcluster-groep/gedempte-fragmenten-groep** – op verzoek moet
  de "Klankclusters"-groep volledig verdwijnen (leeg of niet, niet alleen
  leegmaken) zodra "Gedempte fragmenten" actief is: wat daar aangevinkt
  stond, staat al bij "Gedempte fragmenten". `_build_cluster_group` bewaart
  de group nu als `self._cluster_group`; verborgen in `_refresh_fragments`
  (zodra fragmenten getoond worden) en bij een volledige projectreset,
  weer zichtbaar na een nieuwe stap-3-analyse (`_show_analyse_results`) en
  bij `_reset_damping`. Daarnaast heeft "Gedempte fragmenten" nu de
  flexibele groei/krimp-rol bij het vergroten/verkleinen van het venster,
  die daarvoor bij "Klankclusters" lag (`stretch=1`/`stretch=0` omgewisseld
  op de audio-layout, `scroll.setFixedHeight(140)` → `setMinimumHeight`).
- pytest 422 groen (418 + 1 nieuwe restore-test in `test_pipeline.py` + 3
  nieuwe B281-tests in `test_v092.py`), pyflakes schoon over modules/tools/
  tests. De enige resterende faal is `test_language_for_uses_songtekst`
  (taaldetectiebibliotheek-gedrag, onafhankelijk van alle wijzigingen in
  deze versie - aanwezig vóór en na alle B281/B282/B283-aanpassingen).
- **B284: B283-correctie, twee bugs** – na installatie op de lokale machine
  bleek Klankclusters al bij het simpelweg OPENEN/starten van een project
  verborgen te zijn i.p.v. pas na stap 4: `_reset_project_view` (aangeroepen
  bij elke projectwissel) verborg de groep expliciet, terwijl hij daarvoor
  altijd zichtbaar was tot fragmenten actief werden - een verkeerde aanname
  bij het bouwen van B283 ("consistent lege state" bleek niet consistent
  met het bestaande gedrag). Eerste losse fix (alleen die regel terugdraaien
  naar `setVisible(True)`) loste dat op, maar de gebruiker wees terecht op
  een dieper probleem: Klankclusters en Gedempte fragmenten stonden als
  twee LOSSE widgets onder elkaar in de audio-layout, elk met hun eigen
  minimumhoogte (64 resp. 140) en stretch - in-/uitschakelen van de een
  liet de ander de opengevallen ruimte innemen, met een venster dat
  verspringt bij elke wisseling tot gevolg. Gesuggereerde alternatieven:
  ofwel dezelfde afmeting garanderen voor beide, ofwel (zoals vóór B283)
  helemaal geen twee aparte groepen hebben. Gekozen: beide groepen blijven
  functioneel gescheiden (eigen knoppen/logica per fase, geen vermenging
  van clusterselectie en fragment-aan/uitvinken), maar staan nu op dezelfde
  plek in één `QStackedWidget` (`self._cluster_fragment_stack`, toegevoegd
  op de plek waar voorheen de twee losse `addWidget`-regels stonden) met
  een gedeelde minimumhoogte-constante `_CLUSTER_FRAGMENT_MIN_H = 140`
  (beide `scroll.setMinimumHeight(...)`-aanroepen verwijzen er nu naar).
  Alle losse `self._fragment_group.setVisible(...)`/`self._cluster_group.
  setVisible(...)`-aanroepen (4 plekken: `_reset_project_view`,
  `_refresh_fragments`, `_reset_damping`, `_show_analyse_results`) zijn
  vervangen door twee nieuwe helpers `_show_cluster_group()`/
  `_show_fragment_group()` die `self._cluster_fragment_stack.
  setCurrentWidget(...)` aanroepen - nooit meer twee keer `setVisible`
  los van elkaar zetten, dus geen risico meer dat ze uit sync raken.
  Gevalideerd (offscreen, `QT_QPA_PLATFORM=offscreen`): een echte
  `MainWindow` opgebouwd met een tijdelijk project, stack-index bij
  opstarten is 0 (Klankclusters), `sizeHint()`-hoogte van beide groepen is
  identiek (209px) na wisselen via `_show_fragment_group()`/
  `_show_cluster_group()`. pytest blijft 422 groen.

In v0.94 verwerkt:
- **Aanleiding** – de gebruiker liep bij een echte uitlijning ("Lied_S")
  tegen een zooitje aan het einde van het lied aan. Onderzoek wees een
  27 seconden durend transcriptie-gat aan (169,44s-196,62s: "Espagna por
  favor" plus de volledige 4x herhaalde outro "Lalaala lalalalalaa e viva
  Espagna") waarna Whisper "SPANNENDE MUZIEK" hallucineerde (al gefilterd,
  "muziek" staat op de vaste lijst) gevolgd door "Heerlijke Heer,
  Heerlijke Heer." - geen van beide woorden stond op enige
  hallucinatielijst, dus dat laatste segment bleef als anker staan en trok
  de uitlijning eromheen scheef.
- **Doodlopende paden, eerst onderzocht en eerlijk teruggekoppeld vóórdat
  er iets werd gebouwd** – (1) het vermoeden dat "la" niet altijd wordt
  meegenomen als vulwoord zou de kern van dit specifieke geval zijn, bleek
  bij nameting niet te kloppen: Lied_S's exacte spelling ("Lalaala",
  "lalalalalaa") heeft een oneven tekenlengte en voldoet daardoor sowieso
  al niet aan `is_filler_word`s exacte-veelvoud-check - deze woorden
  liepen dus al gewoon door de normale DP-uitlijning, niet via het
  vulwoord-mechanisme. En "Heerlijke"/"Heer" scoren met of zonder die
  woorden in de vergelijkingsset hooguit 0,33-0,40 fonetische gelijkenis
  met de volledige songtekst - ruim onder elke redelijke drempel. (2)
  "Ole!" (regels 1, 3 en 60) bleek NIET via het vulwoord-mechanisme te
  verklaren (het staat niet eens in `_VOCALISE`), maar exact dezelfde
  oorzaak te hebben als het outro-gat: Whisper transcribeert "Ole!"
  nergens in het hele nummer (geverifieerd via een grep over
  transcript.txt/woorden.csv - nul treffers). Voor dit soort "er is
  domweg geen Whisper-transcriptie van dit woord"-gevallen bestaat geen
  betrouwbare automatische-detectie-oplossing zonder onaanvaardbaar
  regressierisico - vandaar de editor-zichtbare markering (B287) als
  vangnet in plaats van een vijfde detectie-heuristiek. (3) Zijdelings ook
  onderzocht (los van deze bug, pure kennisvraag van de gebruiker):
  bestaat er een akoestisch signaal of MIR-techniek (pitch-stabiliteit,
  spectrale vlakheid, chroma-breedte, HNR, singer-diarisatie, multi-F0-
  schatting, MedleyVox, CREPE/RMVPE) om achtergrondkoor/meerdere
  gelijktijdige zangers te onderscheiden van de lead-zang, als alternatief
  voor de handmatige `[bg]`-markering? Geen van deze technieken is
  voldoende robuust/productierijp gebleken; de gebruiker ging akkoord om
  dit te laten rusten ("wat we hebben werkt goed genoeg op dat gebied voor
  nu") - geen wijziging als gevolg hiervan.
- **B285: liedbrede hallucinatiecheck** – `pipeline._filter_hallucinations`
  had tot nu toe alleen een vaste-woordenlijst-check (B141/B258): een
  segment is hallucinatie als al zijn kernwoorden op `cluster.HALLUCINATIONS`
  staan, of (voor het losse signaalwoord "zang") nergens in de songtekst
  voorkomen. "Heerlijke"/"Heer" staan op geen enkele lijst, dus glipten
  erdoorheen. Nieuwe, bredere check (alleen als aanvulling ná de bestaande
  vaste-lijst-check, en alleen als die niets vond): een segment met
  minstens `_SEGMENT_HALLUCINATION_MIN_KERNWOORDEN` (2) kernwoorden wordt
  ook gedropt als (a) GEEN van de kernwoorden ook maar redelijk
  (`_SEGMENT_HALLUCINATION_MATCH_FLOOR = 0.65`) fonetisch matcht met de
  songtekst van dit lied - per kernwoord telt de BESTE match over de hele
  songtekst, niet het gemiddelde, want één woord dat wél ergens matcht is
  genoeg om het hele segment te sparen (zelfde principe als de bestaande
  "zang"-check) - én (b) Whisper's eigen LAAGSTE woord-confidence in het
  segment onder `_SEGMENT_HALLUCINATION_CONF_CEILING` (0.6) blijft. Dat
  moet expliciet de LAAGSTE zijn, niet het gemiddelde: het echte
  "Heerlijke Heer"-segment scoort gemiddeld 0,63 (net boven een
  gemiddelde-drempel van 0,6) maar de laagste losse woord-confidence is
  0,34 - een hallucinatie waarbij Whisper's taalmodel een deel van de zin
  met hoge zekerheid "invult" ondanks zwakke audio geeft precies zo'n
  ongelijkmatig patroon, en een gemiddelde zou dat gemaskeerd hebben.
  Zonder songtekst (`lyrics` leeg/`None`) wordt deze bredere check
  helemaal overgeslagen - er is dan niets om "matcht nergens mee" tegen af
  te zetten. Bij het testen tegen de fonetische-sleutel-vergelijking bleek
  een addertje: "heer" verliest bij het fonetiseren zowel de 'h' als de
  'r' (`cluster._DROPPED`) en houdt dan nog maar één teken over ("e") -
  toevallig identiek aan de sleutel van het songtekstwoordje "E" (uit "E
  viva Espagna"), wat een valse match van 1.0 gaf. Opgelost met
  `_MIN_BROAD_MATCH_KEY_LEN = 2`: een fonetische sleutel korter dan 2
  tekens telt niet mee in de bredere check. Achterwaarts-compatibel
  gehouden via een nieuw optioneel `dropped_out`-argument (in plaats van
  de return-waarde te wijzigen) - alle 6 bestaande directe aanroepen in
  `test_pipeline.py`/`test_v084.py` blijven ongewijzigd werken.
  Gevalideerd tegen de 10 echte projecten die momenteel op de installatie
  staan (Lied_S, Lied_N, Lied_P, Lied_B,
  Lied_T, Lied_J, Lied_O, Lied_I,
  Lied_G, Lied_A): naast de "Heerlijke
  Heer"-hallucinatie (Lied_S) ving de bredere check ook drie eerder
  onopgemerkte hallucinaties/artefacten in andere projecten op - "TV
  Gelderland 2021" (Lied_N, helemaal aan het eind, vermoedelijk een
  uitzend-watermerk van de bron-opname), "Alright, stop!" (Playback_
  Zondag) en "Thank you." (Lied_T, één van de bekendste
  Whisper-hallucinatiezinnen) - stuk voor stuk Engelse frases zonder
  songtekst-match en met een lage laagste-woord-confidence. Geen van de
  10 projecten verloor een segment dat vóór B285 terecht werd behouden.
- **B286: herhaalde vulklanken als bewuste songtekst** – de gebruiker
  merkte terecht op dat het omgekeerde ook waar is: staat "la la la"
  letterlijk in de songtekst, dan is het geen incidentele vulling om over
  te slaan. Nieuw: `songtekst.is_repeated_filler_line` (waar als élk woord
  op een regel een vulklank is én de regel minstens 3 woorden telt) en
  `repeated_filler_lines` (de bijbehorende regelnummers). `align_lyrics`
  sluit zulke regels nu uit van het normale vulwoord-overslaan
  (`skip_filler`) - een woord telt alleen als "over te slaan vulwoord" als
  het zowel een vulklank is ALS niet op een bewust-herhaalde regel staat.
  Dit is (zoals hierboven al bleek) niet de oorzaak van de Lied_S-bug
  zelf, maar wel een correcte, op zichzelf staande verbetering voor
  liedjes waar dit patroon wél optreedt.
- **B287: drie statusmarkeringen in de koppel-editor** – als vangnet voor
  alle "onvindbare woord"-gevallen (inclusief "Ole!", B285's gefilterde
  hallucinaties, en gewone vulwoorden) krijgt elk songtekstwoord in
  `pipeline.word_coupling_view` nu een `status`: "gekoppeld" (heeft een
  koppeling, of is bg/handmatig gepind - ongewijzigd uiterlijk),
  "vulwoord_overgeslagen" (een vulklank die niet via het B276-ankervenster
  hersteld kon worden), "hallucinatie_gefilterd" (de geschatte positie -
  het ankervenster tussen de dichtstbijzijnde gekoppelde buren, zelfde
  aanpak als B276 - overlapt een door B285 weggefilterd segment) of
  "geen_match" (alle overige gevallen, zoals "Ole!"). Achtergrondzang-
  woorden (`bg`) krijgen bewust geen markering: die zijn al apart
  behandeld, ook als de gebruiker een woord expliciet los liet. Volgorde
  van voorrang bij meerdere mogelijke oorzaken: eerst hallucinatie-overlap
  (het meest concreet aanwijsbaar), dan vulwoord, anders "geen_match".
  `modules/koppeleditor.py` tekent niet-gekoppelde songtekstwoorden nu met
  een gestippelde rand in een eigen kleur plus een kort, bewust niet-
  vertaald labeltje - oranje "[vul]", rood "[?]", paars "[hal]" - naar het
  voorbeeld van het bestaande "[crowd]"-patroon in `timingeditor.py`. Een
  handmatige selectie (blauwe rand) gaat altijd vóór de statuskleur, zodat
  duidelijk blijft wat je hebt aangeklikt.
- pytest 440 groen (422 + 18 nieuwe B285/B286/B287-tests in
  `test_v094.py`), pyflakes schoon over modules/tools/tests (de enige
  resterende pyflakes-melding, `np` als forward-ref-typehint in
  `_prepared_restore_intervals`, bestond al vóór v0.94 en valt buiten deze
  release). De enige resterende testfaal is `test_language_for_uses_
  songtekst` (taaldetectiebibliotheek-gedrag, onafhankelijk van alle
  wijzigingen in deze versie).

In v0.95 verwerkt:
- **Aanleiding en werkwijze** – de gebruiker vroeg om de hele code na te
  lopen op logica, dode code en vertaalbaarheid (en op termijn Engelse
  namen). Die review is met vier parallelle deelonderzoeken gedaan (dode
  code, vertaalbaarheid, Nederlandse identifiers, correctheid). Belangrijk
  voor het vertrouwen in wat hieronder staat: elke gemelde bug is eerst
  gereproduceerd met een concreet faalscenario vóórdat er iets is
  aangepast, en de bevindingen die dat niet overleefden zijn geschrapt in
  plaats van "voor de zekerheid" gefixt. Geen van deze bugs was door de
  gebruiker gemeld; ze zaten er stilletjes in.
- **B288: voorrangsdrempel voor vulwoorden toetste het verkeerde getal** –
  `_filler_priority_lines` (B276) levert REGELNUMMERS uit de karaoketekst,
  maar `songtekst.align_lyrics` deed `if i in priority` met `i` = de index
  in de woordenlijst. Omdat elk lied veel meer woorden dan regels heeft,
  sloeg de soepelere drempel praktisch nooit aan waar hij bedoeld was, en
  ging hij juist wél aan bij het woord waarvan de index toevallig gelijk
  was aan een voorrangsregelnummer. Nu `lyrics[i].line in priority`. De
  docstring van `_filler_priority_lines` beloofde bovendien "vergelijkt
  songtekst.txt en karaoketekst.txt regel voor regel", terwijl de functie
  songtekst.txt nooit opent (dat hoeft ook niet: de songtekstkant wordt in
  `align_lyrics` getoetst) - ook gecorrigeerd.
- **B289: `lang="nl"` in een booleaans veld** – `timing.Syllable.lang`
  betekent "lang aangehouden noot" en stuurt in `video.py` de onderstreping
  aan; `timedline_from_text` vulde daar de string `"nl"` in, een
  verwarring met de taalparameter elders in dezelfde module. Een niet-lege
  string is truthy, dus élke lettergreep gold als aangehouden noot zodra de
  video van de originele songtekst werd gerenderd (en in de
  klemtoon-editor). Gecontroleerd in de echte `timing.json`-bestanden van
  alle 10 projecten op de installatie: daar staat overal `False`, dus deze
  bug zat alleen in de render/editor en niet in opgeslagen data - een
  codefix volstond, geen migratie.
- **B290: crash bij meer zangvensters dan woorden, verborgen door een
  vangnet** – `timing.distribute_over_windows` klemt de woordgrenzen per
  venster, maar `max(vorige + 1, ...)` kon voorbij het laatste woord lopen
  zodra een regel `aantal_woorden + 2` of meer vensters had; `woord_spans[wi]`
  gaf dan een IndexError. Uitputtend nagemeten: 2 woorden/4 vensters, 3/5,
  4/6, enzovoort. Het echte probleem zat een laag hoger: de aanroep in
  `pipeline._apply_energy_word_timing` staat binnen één brede
  `except Exception` om de héle stap, dus één probleemregel liet de
  energie-woordtiming (B234) van het complete lied stilzwijgend vervallen,
  met alleen een regel in het log. Twee fixes: overtollige vensters worden
  nu vooraf samengevoegd op de KLEINSTE tussenpauze (zo blijven juist de
  duidelijke pauzes staan, waar B234 om draait, en blijft de buitenspan van
  de regel intact), en de aanroep is per regel afgevangen zodat alleen die
  ene regel zijn verfijning verliest. Geverifieerd over 96 combinaties
  (1-8 woorden x 1-12 vensters) op crashes én op de invarianten: geen
  lettergreep verdwijnt, tijden lopen op en overlappen niet.
- **B291: `blok` en `uitgeschakeld` verdwenen bij een tekstcorrectie** –
  `pipeline.sync_timing_with_text_change` bouwde de nieuwe `TimedLine` mét
  `crowd_section` en `kwaliteit` maar zónder `blok` en `uitgeschakeld`,
  die dus terugvielen op 0 en False. Corrigeerde je een typefout in een
  regel die je eerder had uitgeschakeld (B180), dan stond die regel daarna
  weer gewoon in de video, en klapte de blokindeling van de timing-editor
  (B127) naar blok 0. De docstring belooft expliciet dat alleen
  tekst/lettergrepen veranderen; dat klopt nu weer.
- **B292: losse eindjes uit v0.93/v0.94 (eigen werk)** – de
  `floor`-parameter die bij B285 aan `_word_in_lyrics` was toegevoegd werd
  nooit anders dan met de default aangeroepen, terwijl de docstring
  suggereerde dat de brede liedbrede check hem gebruikte; die check gaat
  via `_best_lyrics_match` met een eigen drempel. Wie op die docstring
  afging om B285 bij te stellen, veranderde het verkeerde. Parameter weg,
  docstring recht gezet. Verder waren `karaoke.restore_intervals_to_dicts`
  en `_from_dicts` (B282) nooit aangeroepen én beschreven ze een ander
  formaat dan er werkelijk wordt opgeslagen (`restore_fragmenten` bewaart
  drietallen, geen dicts) - verwijderd.
- **B293: dode code** – weg: `fonetiek._lang_dir_name`,
  `pipeline.TrackProgressCallback`, `pipeline.detect_words` (deed exact
  wat `detect_tracks(parallel=False)` doet; twee ingangen naar dezelfde
  stap 1 betekent dat een wijziging in de ene stilzwijgend langs de andere
  gaat) en de dode parameter `fallback_offset` in `align._smooth_regions`
  (restant van de mediaan-terugval die bij B249 door trend-detectie is
  vervangen). `gui.py` had een letterlijk identieke privékopie van
  `cluster._format_time`; die is nu één publieke `cluster.format_time`.
  De docstring van `fonetiek.generate_language` beloofde "ingebouwde
  hints" die niet bestaan - eerlijk gemaakt in plaats van de parameter te
  schrappen, want daar horen ze logischerwijs terecht te komen. Met de
  numpy-annotatie achter `TYPE_CHECKING` is **pyflakes nu volledig
  schoon** over modules/tools/tests/KaraokeTool.py; die ene melding stond
  er al vóór deze ronde.
- **B294: alleen-door-tests-gebruikte functies - bewust NIET verwijderd** –
  de review vond er twaalf. Alleen `detect_words` is geschrapt, omdat daar
  een aantoonbaar gelijkwaardige productievervanger voor is. De rest blijft
  staan, met opzet: `timing.best_effort_skeleton` (plus `_cascade_spans`,
  `_build_line`, `line_assignments`) is een substantiële kwaliteit-cascade
  (lettergreep/woord/zin) die het `kwaliteit`-veld voedt dat overal in
  timing.json gebruikt wordt - dat is eerder een losgeraakte tak dan dode
  code, en op een gok weggooien is erger dan laten staan.
  `timing_rules.clamp_refinement` en de constanten `KIND_DURATION`/
  `KIND_REFINE` horen bij het voorbereide (en in dit document beschreven)
  per-blok zang-onset-werk. `config.TrackSettings` blijft omdat `tracks`
  in de echte `config.json` staat: weghalen zou die sleutel stil laten
  verdwijnen. Overige kandidaten (`audio.duration_seconds`,
  `taal.current_language`, `ritme.count_repetitions`,
  `pipeline.export_demucs_karaoke`, `cluster.format_overview`,
  `modellen.info_text`) zijn kleine, correcte en geteste functies; die
  verdienen per stuk een besluit bij gebruik, niet een veegactie.
- **B295: dode vertaalsleutels** – 14 sleutels stonden nog in beide
  woordenboeken maar werden nergens aangeroepen, ook niet via de
  dynamische `t(f"...")`-patronen: `options_group`, `analyse_on`,
  `analyse_hint`, `render_audio_demucs`, `analyse_toggle_log`,
  `track_required_body`, `alignment_remade`, `mark_ok`, `mark_missing`,
  `open` en de vier `video_input_*` (wezen van een dialoog die door een
  foutmelding is vervangen).
- **B296: zichtbare tekst buiten de vertaallaag** – de nl- en en-sleutelsets
  waren netjes in balans, maar er stond veel Nederlands buiten `t()` dat de
  gebruiker wél ziet. Nu vertaalbaar: alle 24 `PipelineError`-meldingen
  (die komen via `_on_failed` in een QMessageBox terecht), het complete
  HTML-clusterrapport (titel, kopjes, voettekst, en het `lang`-attribuut),
  de bestandsdialoog-filters, de "golfvorm verschijnt na..."-tekst, de
  waarschuwing over regels die uit beeld lopen, de namen van de
  video-invooritems (die staan ín een al vertaalde melding, dus die moesten
  mee) en de bronkeuze in de timing-editor. Die laatste toonde de ruwe
  waarden "origineel"/"karaoke"/"zangstem"; hij toont nu de vertaalde naam
  en bewaart de ruwe sleutel als itemdata, zodat het opzoeken in
  `audio_paths` ongewijzigd blijft. Er staan nu 320 sleutels per taal, in
  balans. Een regressietest bewaakt dat er geen letterlijke
  `raise PipelineError("...")` terugkomt.
- **B297: verwijzingen naar niet-bestaande stappen** – meldingen spraken van
  "stap 2 (Analyse)" en "stap 3 (Uitlijnen)" terwijl de knoppen 1 Detecteer
  woorden / 2 Woorden koppelen / 3 Analyse / 4 Karaoke aanpassen heten en
  een aparte Uitlijnen-stap niet meer bestaat (die loopt automatisch via
  `ensure_alignment`). Ook `prereq_need_analyse` verwees in beide talen
  naar "2 Analyse". Alle teksten noemen nu de echte knopnaam; een test
  bewaakt dat.
- **B298: interne bugreferentie in beeld** – de tooltip `line_toggle_tip`
  eindigde in beide talen op "(B180)". Een test controleert nu op elk
  `B<nummer>`-patroon in alle zichtbare teksten.
- **B301: ongecontroleerde drempel en misleidend samengevoegd label** –
  `align.min_confidence` was de enige drempel zonder controle in
  `config._validate`, terwijl 0.0 betekent dat vensters met confidence 0
  door de filter glippen en `np.average(..., weights=...)` dan door een
  gewichtensom van nul deelt. Nu begrensd (0 zelf uitgesloten), plus een
  terugval op het ongewogen gemiddelde in `_build_regions` voor het geval
  zo'n groep er langs een andere weg toch is. En `karaoke.merge_intervals`
  hield bij het samenvoegen alleen het label van het eerste fragment,
  waardoor een vak dat "oe" én "woo" dempte in de dempingseditor als "oe"
  te zien was; het label noemt nu alle klanken ("oe+woo", zonder herhaling)
  en de demping wordt de sterkste van de samengevoegde fragmenten.
- **B302: achterhaalde "nog open"-lijsten** – twee lijsten in dit document
  noemden B139, B189, B191, B193, B194/B195, B196, B198, B201/B202 en B136
  als openstaand. Nagelopen: op B139 (rest) na zijn ze allemaal in latere
  versies gebouwd (met implementatie in `modules/`), en `compare_models`
  (B136, "kan later weg") is al verwijderd. De lijsten gaven wie ze las een
  verkeerd beeld van wat er nog te doen was; ze zijn nu doorgestreept met
  een verwijzing naar waar het werk zit.
- **Bewust NIET meegenomen in deze versie** – de hernoeming naar Engelse
  identifiers/docstrings (B299) en de bijbehorende in-place omzetting van
  de bestaande JSON-bestanden (B300). Die twee horen bij elkaar en zijn op
  verzoek apart gehouden, zodat de bugfixes hierboven los te testen zijn
  zonder de ruis van duizenden hernoemde regels.
- pytest 468 groen (458 + 28 nieuwe B288-B302-tests in `test_v095.py`, waarbij
  4 bestaande pipeline-tests zijn bijgewerkt op de nieuwe foutteksten),
  pyflakes volledig schoon, nl/en-sleutelsets gelijk (320 elk). De enige
  resterende testfaal is `test_language_for_uses_songtekst`
  (taaldetectiebibliotheek-gedrag, onafhankelijk van deze wijzigingen).

In v0.96 verwerkt:
- **B299/B300: volledig Engelse codebase, met omzetting van de bestaande
  data.** Op verzoek in tien fasen uitgevoerd, met na elke fase een groene
  testsuite en een herstelpunt op de pc (de werkomgeving van de assistent
  valt terug bij een reboot; dat is tijdens deze klus drie keer gebeurd en
  elke keer zonder verlies opgevangen). De volledige werklijst met alle
  vertaaltabellen staat in `docs/hernoeming_B299_B300.md`.
- **Wat er is hernoemd** – 13 modulenamen; ~800 identifiers (variabelen,
  parameters, functies, klassen); de dict-sleutels die alleen in het
  geheugen leven; alle docstrings en commentaar; en alle opgeslagen sleutels
  in `config.json`, `project.json`, `timing.json`, `clusters.json`,
  `statistieken.json` en de taalregistry, inclusief bestands- en mapnamen.
- **Wat bewust Nederlands is gebleven** – `songtekst.txt` en
  `karaoketekst.txt` (de gebruiker maakt en bewerkt die zelf en ze staan
  overal in de handleiding), de markup daarin (`[crowd]`, `[bg]`, ...), de
  Nederlandse interfaceteksten in `translations.py` (dat is de vertáling,
  geen code) en deze documentatie.
- **Eén bewuste afwijking van een letterlijke vertaling** – het veld `lang`
  op `Syllable` betekende "lang aangehouden noot", niet een taalcode. Het
  heet nu `held`. Precies die verwarring was de oorzaak van B289 (elke
  lettergreep werd onderstreept omdat er `lang="nl"` in stond); met `held`
  is die fout niet meer te maken.
- **Vijf lessen die het gereedschap nu afdwingt.** Deze klus liep vijf keer
  bijna stil op hetzelfde soort fout; ze staan hier zodat een volgende
  hernoeming ze niet opnieuw hoeft te ontdekken.
  (a) *Botsingen meet je per scope, niet globaal.* `songtekst` -> `lyrics`
  leek prima tot bleek dat `lyrics` al 41x een variabele was: de module
  verdween achter een lokale naam (`lyrics.repeated_filler_lines(lyrics)`).
  Idem `taal` -> `language` (17x). Het werd `song_text` en `translations`.
  Binnen functies gold hetzelfde voor tien namen, bv. `vensters` ->
  `windows` waar `windows` al de parameter was.
  (b) *Alleen verwijzingen hernoemen, geen declaraties.* De eerste versie
  van de tool hernoemde ook het dataclass-veld `AppConfig.analyse` naar
  `analysis` - een `config.json`-sleutel, dus een heel andere fase - en brak
  daarmee alle `config.analyse`-verwijzingen.
  (c) *Keyword-argumenten zijn `ast.keyword`, geen `ast.Name`.* Daardoor
  bleef `timing_report(bron_karaoke=...)` achter terwijl de parameter al
  `source_karaoke` heette.
  (d) *Strings koppelen ook.* `@pytest.mark.parametrize("n_woorden,...")`
  en `caplog.at_level(logger="modules.songtekst")` verwijzen via een string
  naar iets dat wél hernoemd is.
  (e) *Weet welke laag een sleutel bezit.* `timing_eval.py` LEEST
  timing.json, dus zijn invoersleutels horen bij het opgeslagen formaat en
  niet bij de interne rapport-dicts. En de vertaalsleutel `"origineel"` zit
  vast aan de track-identifier, die weer aan bestandsnamen vastzit - een
  losse vervanging daarvan raakte in één klap `TRACK_ORIGINEEL`,
  `origineel.wav` en de stapnamen.
- **De omzetting van de data (B300)** – `tools/migrate_b299.py` draait op de
  installatie zelf. Hij maakt van elk bestand dat hij aanraakt eerst een
  `.pre_b299.bak`, is idempotent, meldt onbekende sleutels luid in plaats
  van ze stil te laten staan (dat laatste is precies hoe `config.py`
  instellingen verliest: onbekende sleutels worden genegeerd met alleen een
  logregel), en controleert achteraf dat elke waarde uit de back-up onder
  zijn nieuwe sleutel terug te vinden is. Vooraf getest op een kopie van de
  echte projectdata: 0 verloren waarden, en de nieuwe code leest de
  omgezette `config.json`, `timing.json`, `project.json`, `clusters.json`,
  `statistics.json` en `languages/nl.json` correct in.
- **Verificatie van fase 4** – dat alleen docstrings en commentaar zijn
  gewijzigd (en geen code) is niet op vertrouwen aangenomen maar machinaal
  vastgesteld: van elk van de 33 modules is de AST vergeleken mét
  geblindeerde docstrings. Alle 33 identiek.
- pytest 468 groen (1 bekende, niet-gerelateerde faal), pyflakes schoon,
  GUI-rooktest in beide talen oke.

In v0.96.1 verwerkt:
- **Aanleiding** – de gebruiker meldde na de overstap naar v0.96 twee dingen:
  een foutmelding bij de analyse van Lied_S, en het gevoel dat het koppelen
  slechter ging. Dat bleken twee losstaande zaken met verschillende oorzaken,
  en maar één ervan was mijn schuld.
- **B303: een ingebouwde functie hernoemd (mijn fout).** In het
  vertaalwoordenboek van B299 stond het Nederlandse "map" als `map` -> `dir`.
  De hernoemer paste dat ook toe op Pythons ingebouwde `map()`, waardoor
  `', '.join(map(str, sorted(suggested)))` in `gui.py` veranderde in
  `', '.join(dir(str, ...))`. `dir()` accepteert hooguit één argument, dus
  de analyse crashte zodra er clusters gesuggereerd werden. De schade is
  begrensd en dat is nagemeten, niet aangenomen: alle aanroepen van
  ingebouwde functies zijn geteld in v0.95 en v0.96, en het enige verschil
  was `map 1 -> 0` en `dir 0 -> 1`.

  Waarom geen enkele test dit ving: de regel zit in een GUI-callback
  (`_show_analyse_results`) die alleen draait als de analyse daadwerkelijk
  clusters suggereert - een pad dat de suite niet aanraakt. En mijn
  botsingscontrole tijdens B299 keek alleen of de DOELnaam al in gebruik was,
  nooit of het BRONwoord een ingebouwde naam ís. Dat gat is nu gedicht met
  drie tests in `tests/test_v0961.py`, waarvan er één meteen nog een tweede
  smet vond (een zinloze identiteitsregel `list` -> `list`).

  Onderscheid dat in die tests is vastgelegd: een bronwoord dat een builtin
  is, is fataal (werkende code verandert stilzwijgend van betekenis, zonder
  syntaxfout). Een doelwoord dat een builtin is (`alle` -> `all`, `reeks` ->
  `range`) is minder erg: dat schaduwt alleen, en alleen binnen die ene
  scope. Die zijn toegestaan, maar een aparte test bewaakt het geval waarin
  die schaduwing daadwerkelijk bijt.
- **CORRECTIE (v0.96.2): het koppelen WAS wel degelijk mijn schuld.** De
  conclusie hieronder ("niet door de hernoeming") klopte voor de koppel-
  logica, maar miste de oorzaak een laag dieper. Zie het blok "In v0.96.2
  verwerkt" voor de volledige keten. Ik laat de oorspronkelijke redenering
  staan omdat ze op zichzelf juist is en laat zien waar de analyse tekort
  schoot: ik heb de code vergeleken, maar niet gevraagd wélk audiobestand er
  eigenlijk in Whisper ging.
- **Het koppelen: niet door de koppel-logica.** Dit is op drie manieren
  nagetrokken voordat er iets is aangepast. (1) Dezelfde songtekst en
  transcriptie van Lied_S door v0.93, v0.95 en v0.96 gehaald: alle drie
  222 transcriptiewoorden, 225 van 257 songtekstwoorden gekoppeld, alleen
  "MUZIEK" weggefilterd, nul woorden met een andere koppeling. (2) Ook de
  volledige koppel-weergave inclusief `extend_coupling` en
  `creative_couplings` (zonder de handmatige pins) is identiek. (3) Van alle
  32 modules is de functiestructuur vergeleken met namen en teksten
  genegeerd: geen enkele wijziging in de logica.

  De werkelijke oorzaak: Whisper heeft op 10 augustus opnieuw gedraaid en
  gaf 23 segmenten in plaats van de 36 van 7 augustus (223 tegen 225
  woorden). Zelfde model, zelfde taal, zelfde `initial_prompt`, en een
  bit-voor-bit identieke bron-mp3 - maar een andere afgeleide wav.
  Segmenten zijn de ankers voor de uitlijning, dus 23 lange segmenten geven
  veel minder houvast dan 36 korte. De betere transcriptie stond nog
  compleet in de diagnostiek-historie en is teruggezet (zie hieronder).
- **B304: gat in de eenmalige omzetting.** Die hernoemde alleen mappen die
  exact `origineel` heetten. Daardoor bleef in vijf projecten
  `cache/<lied>/demucs_stems_origineel` staan terwijl de code al
  `demucs_stems_original` zocht - Demucs draaide daardoor opnieuw vanaf nul,
  minuten per nummer. De omzetting behandelt nu ook mapnamen die op
  `_origineel` eindigen, via een aparte `dir_target_name`-functie die de
  test rechtstreeks toetst.
- **B305: de betere transcriptie teruggezet.** De 36-segmenten-run van
  7 augustus is uit `output/Lied_S/diagnostics/transcription_original.json`
  teruggeschreven naar de cache, met omzetting van de Nederlandse sleutels
  naar de Engelse. De slechtere run is als back-up bewaard
  (`.pre_b305.bak`), en `wav_sha1` in project.json is op de huidige wav
  gezet zodat Whisper niet alsnog opnieuw gaat draaien.

  **Gemeten effect, en dat viel tegen**: de woordkoppeling ging van 225 naar
  227 van de 257 woorden - twee woorden winst, niet meer. Het verschil
  tussen 23 en 36 segmenten raakt dus vooral de zin-verankering en de
  timing (`couple_timing` gebruikt segmenten als ankers per zin), en veel
  minder de woord-voor-woord-koppeling. Wie de klacht "het koppelen gaat
  minder goed" alleen aan het segmentaantal wil toeschrijven, overschat dat
  verband; de winst zit waarschijnlijk in de regeltiming.
- pytest 472 groen (468 + 4 nieuwe), pyflakes schoon.

In v0.96.2 verwerkt:
- **De ware oorzaak van "het koppelen gaat minder goed" - en dat was mijn
  migratiegat, niet Whisper-toeval.** In v0.96.1 concludeerde ik dat de
  hernoeming er niets mee te maken had, omdat de koppel-logica aantoonbaar
  identiek was. Dat was juist maar onvolledig: ik had nooit nagegaan wélke
  audio Whisper krijgt. Dat is niet de mix maar de Demucs-**zangstem**
  (`detect_track`, `wav_path = stems["vocals"]`). De keten:

  1. B304 (mijn migratie hernoemde alleen mappen die exact `origineel`
     heetten) liet `cache/<lied>/demucs_stems_origineel` staan;
  2. de code zocht `demucs_stems_original`, vond niets, en draaide Demucs
     opnieuw vanaf nul;
  3. Demucs is niet bit-reproduceerbaar, dus er kwam een andere zangstem
     uit;
  4. `wav_sha1` (de hash van díe zangstem) kwam niet meer overeen, dus
     Whisper draaide opnieuw;
  5. die run gaf 23 in plaats van 36 segmenten.

  Bewijs, geen redenering: de sha1 van de OUDE `vocals.wav` is
  `c1c3c83e...` - exact de `wav_sha1` van de 36-segmenten-run van 7
  augustus; die van de NIEUWE is `aa8ec41f...` - exact die van de
  23-segmenten-run van 10 augustus.
- **Fout in mijn eigen herstel van v0.96.1, gevonden bij die analyse.** Bij
  B305 zette ik `wav_sha1` op de hash van de MIX (`cache/<lied>/original.wav`)
  terwijl de code de ZANGSTEM hasht. Daardoor zou de cachecheck bij de
  volgende analyse alsnog falen en Whisper opnieuw draaien - het herstel
  zou zichzelf ongedaan hebben gemaakt. Nu staat de bij de herstelde
  transcriptie horende zangstem terug op zijn plek en klopt `wav_sha1`
  daarmee. Nagemeten voor alle projecten: de vijf met een zangstem in de
  cache hergebruiken hun transcriptie (Lied_S met 36 segmenten); de
  andere vijf hebben helemaal geen Demucs-stem in de cache staan, wat al zo
  was en losstaat van deze wijzigingen.
- **B306: de "bekende faal" was geen bug.** `test_language_for_uses_songtekst`
  stond al vele versies rood en werd telkens als "bekende, niet-gerelateerde
  faal" meegesleept. De oorzaak bleek simpel: de test vereist `langdetect`,
  een OPTIONELE library. Zonder haar valt `_language_for` bewust terug op
  "auto", precies zoals bedoeld - de test toetste dus gedrag dat er niet
  was. Hij slaat nu over met `pytest.importorskip` in plaats van rood te
  staan. Daarmee is de suite voor het eerst in lange tijd volledig groen
  (472 geslaagd, 1 overgeslagen), en valt een échte regressie in de
  taaldetectie voortaan wél op tussen het groen.
- **Les.** Twee keer op rij trok ik een conclusie uit een codevergelijking
  ("de logica is identiek, dus het ligt niet aan mij") terwijl het probleem
  in de DATA-keten zat die de code voedt. Bij een regressie na een
  verbouwing is de vraag niet alleen "is de code veranderd" maar ook "krijgt
  de code nog dezelfde invoer".

In v0.97.0 verwerkt:
- **Aanleiding** – de gebruiker begon "Lied_S" opnieuw en vroeg vier
  dingen tegelijk: waarom de hallucinaties "Heerlijke Heer" en "SPANNENDE
  MUZIEK" nog steeds doorkwamen terwijl de songtekst ze had moeten
  ontmaskeren, wat er wél gedetecteerd is maar niet getoond wordt, waarom
  de kleurmarkeringen uit een eerder gesprek niet volledig terugkwamen, en
  of de la-la-la's aan het eind niet gewoon getimed kunnen worden. Met één
  harde randvoorwaarde: **de oplossingen moeten generiek zijn**, niet op
  dit ene liedje toegesneden.
- **B307: de hallucinatiecheck kijkt naar de PLEK, niet alleen naar het
  hele lied.** De check uit B285 vraagt "lijkt dit segment ergens in de
  songtekst op iets?". Dat is te mild op precies de plek waar Whisper het
  vaakst hallucineert: na een lange stilte, aan het eind van een nummer.
  "SPANNENDE MUZIEK" scoort liedbreed een perfecte 1,00 - want "muziek"
  wordt in "Ik hou van dansen en muziek" écht gezongen, halverwege het
  eerste couplet. Het idee van de gebruiker gaf de sleutel: de songtekst
  bevat geen tijden (dat is juist wat dit gereedschap uitrekent) maar wél
  de goede woordvolgorde. Daarmee bepalen de dichtstbijzijnde gekoppelde
  ankers vóór en ná een segment een venster in de songtekst waar het
  segment in moet passen. In dat venster (de outro) komt "muziek" nergens
  voor en zakt de score naar 0,38.
  Twee bewakers houden de check veilig: een segment waarin de uitlijning
  wél iets heeft gekoppeld wordt nooit aangeraakt, en de eigen
  woordzekerheid van Whisper moet laag zijn (hetzelfde vangnet als B285).
  Het venster wordt bovendien verbreed tot minstens twaalf woorden, want
  twee ankers vlak na elkaar leveren anders een venster van één woord op
  waar bijna niets mee matcht.
  Nagemeten op de negen projecten met bruikbare data: precies drie
  segmenten vallen extra af - "SPANNENDE MUZIEK" (Lied_S, 197,1 s),
  "Thank you." (Lied_J, 18 s ná de laatste echte regel) en "C'est
  parti !" (Lied G, zekerheid 0,01, 19 s na de laatste
  regel). Alle drie echte hallucinaties; het aantal gekoppelde woorden
  blijft over alle projecten samen exact gelijk (2037). Het minimumvenster
  is bewust op twaalf gezet: van 1 tot en met 16 woorden verandert de
  uitkomst niet, pas vanaf ongeveer 25 glipt "Thank you." er weer doorheen.
- **B308: "Whisper hoorde hier niets" is iets anders dan "hallucinatie
  weggefilterd".** De 21 outro-woorden kregen de markering `[hal]` omdat er
  toevallig een weggefilterd segment in hun ankervenster viel. De echte
  oorzaak was heel anders: 27,6 seconden lang kwam er niets uit Whisper.
  Dat is een ander probleem met een andere oplossing, en de editor wees de
  gebruiker dus de verkeerde kant op. Een woord waarvan het ankervenster
  geen enkel bewaard segment bevat en minstens vier seconden lang is, krijgt
  nu de eigen status `transcription_gap` met een rustige grijsblauwe
  markering `[leeg]`. Die gaat vóór op de hallucinatiemarkering: als er
  helemaal niets staat, is dát de oorzaak.
- **B309: de weggefilterde gevonden woorden zijn weer zichtbaar - en
  koppelbaar.** Dit was de onafgemaakte helft van een eerdere wens ("als er
  dingen worden weggelaten, deze nog wel weergeven in de editor, om te
  kunnen koppelen, mocht het wel nodig zijn"). De onderste rij markeerde de
  gevolgen al (B287), maar de weggegooide woorden zelf stonden helemaal
  niet meer in de bovenste rij. Ze staan er nu doorgestreept in, met
  dezelfde paarse kleur als de `[hal]`-markering eronder; de automatische
  koppeling laat ze met rust, de gebruiker kan ze met de hand alsnog
  koppelen. Er is ook een legenda bijgekomen: vier markeringen zonder
  uitleg is raden.
  Bijvangst die belangrijker is dan het uiterlijk: het nummer van een
  gevonden woord hing tot nu toe af van wat het filter besloot. Elk
  weggefilterd segment schoof alle nummers erna op, en verschoof daarmee
  stilletjes de handmatige koppelingen die erachter lagen - B307 zou dat
  gedrag hebben verergerd. De nummering telt nu de volledige transcriptie,
  dus filterbesluiten raken de koppelingen niet meer. Bestaande projecten
  worden eenmalig omgerekend (markering `layout: full` in `word_coupling`).
- **B310: la-la's timen, generiek.** Drie losse gebreken hielden elkaar in
  stand.
  (a) Een reeks vulregels aan het EIND van een nummer heeft geen anker
  erachter, dus marcheerde de interpolatie door met de mediane regelduur.
  Bij korte gekoppelde regels stopt die veel te vroeg: de hele outro werd
  in 169-188 s geperst terwijl er tot 204,5 s gezongen wordt. Waar de zang
  echt stopt is bekend - het eind van het laatste zang-actieve venster - en
  dat begrenst nu de laatste regel. Bewust niet `active_end`: die zoekt de
  eerste aangehouden stilte ná het anker (B277) en zou al bij de eerste
  pauze binnen de outro stoppen.
  (b) De sterkste `expected` energie-inzetten kiezen leverde regelmatig
  twee pulsen van dezelfde noot op (de aanzet en het lijf, 70 ms na
  elkaar), en dus regels van 0,07 s. Er geldt nu een minimale onderlinge
  afstand van 0,6 keer de gemiddelde regelafstand.
  (c) Waren er te weinig bruikbare inzetten, dan gebeurde er helemaal
  niets en bleef de gelijkmatige interpolatie staan - inclusief regels over
  instrumentale stiltes. Nu worden de regels naar rato over de zang-actieve
  vensters verdeeld, waarbij geen regel over een pauze heen valt en een
  flintertje venster van enkele honderdsten geen hele regel opslokt.
  Daarbovenop een kwaliteitspoort: levert de inzet-plaatsing een regel van
  minder dan 0,4 s op, dan klopt ze niet en wordt de hele reeks alsnog over
  de gezongen tijd verdeeld.
  Resultaat op de echte projecten: Lied_S krijgt "Espagna por favor" op
  170,5-173,9 s (precies de aangehouden slotzin), "Ole!" op zijn eigen
  uitroep bij 176,2 s en de zeven la-la-regels netjes verdeeld over het
  la-la-blok van 180,2 tot 204,5 s. In "Lied I" landen de
  achttien "da da da"-regels op de twee gezongen vensters in plaats van
  half over de stilte; in "Lied J" en "Lied P" verdwijnen
  vier regels van 0,1 s. Waar niets te verbeteren viel (Lied A, 0
  onbetrouwbare regels) verandert er niets.
- **Wat NIET kan, en waarom.** De la-la's koppelen aan transcriptiewoorden
  kan niet: er staat daar geen enkel transcriptiewoord om aan te koppelen.
  Timen kan wél, want de zang staat gewoon in de zangstem (24,2 s geluid in
  het gat van 27,6 s). Dat is precies waarom de oplossing in de timing zit
  en niet in de koppeling.
- **Werkwijze.** Elke drempelwaarde is op de echte projectdata gemeten in
  plaats van gekozen, en elk van de vier onderdelen is met een mutatietest
  gecontroleerd: de bewuste regel tijdelijk uitgezet en gekeken of er dan
  écht een test rood wordt. Twee tests bleken in eerste instantie loos
  (ze slaagden ook zonder de fix) en zijn herschreven tot ze het echte
  gemeten geval beschrijven - onder andere de dubbele inzet op 180,14 en
  180,21 s uit "Lied I".

In v0.98.0 verwerkt:
- **Aanleiding** – de gebruiker formuleerde het principe scherper dan het
  in de code stond: "als het transcript in stap 1 kan worden aangepast, dan
  moet alles daarna wat ervan is afgeleid weg. Dat geldt eigenlijk voor alle
  stappen. Als je de originele muziek verandert, is alle daarvan afgeleide
  muziek, transcripties, timings ook niet meer goed." Met de opdracht erbij
  om die keten vast te leggen en bij te houden.
- **De doorlichting.** Van bronbestand tot video in kaart gebracht: elke
  stap-sleutel, elk projectgegeven, elk bestand dat het programma schrijft,
  en waar de inhoud van afhangt. Achttien gaten gevonden. De ergste vijf:
  de clusterselectie overleefde nieuwe audio (en dempte daarna op de
  tijdstippen van het vórige nummer); `fragment_exclusions` en
  `restore_fragments` hielden hun absolute tijden op een tijdlijn die niet
  meer bestond; de markering `karaoke_from_original` overleefde een nieuw
  origineel, waarna de uitlijning werd overgeslagen met offset 0 terwijl de
  karaoke bij het vorige origineel hoorde; de Demucs-stemcache had geen
  bron-checksum (exact de faalvorm die v0.96 sloopte, want Whisper
  transcribeert de zangstem); en de oude `karaoke_edit.mp3` overleefde de
  invalidatie en werd daarna als audiobron voor de video gekozen.
- **Twee verborgen koppelingen die veel verklaren.** `karaoketekst.txt`
  stuurt via `_filler_priority_lines` de WOORDKOPPELING van de songtekst,
  en dus de regeltijden - je parodietekst bepaalt mede welke originele
  woorden gekoppeld worden. En `songtekst.txt` zit in de cachesleutel van
  Whisper (als beginprompt), zodat een tekstwijziging een volledige
  hertranscriptie kan afdwingen.
- **De oplossing is niet nog een lijstje.** De kennis over wat waarvan
  afhangt stond als handgeschreven sleutellijsten in drie functies; elke
  nieuwe stap moest iemand aan het juiste lijstje toevoegen, en dat is
  precies wat er keer op keer misging. Die kennis staat nu ÉÉN keer als
  gegevens in `modules/dependencies.py`: 65 artefacten die elk noemen
  waarvan ze zijn afgeleid. Invalideren is daarmee geen lijst meer om bij
  te houden maar een vraag aan die graaf - wat hangt, direct of indirect,
  af van wat er is veranderd? Alle aanroepplekken lopen nu via één
  `pipeline.invalidate(context, ["input:lyrics"])`.
- **Merken dat er buiten de app om iets is veranderd.** Er bestond geen
  enkele checksum van `songtekst.txt` of `karaoketekst.txt`: bewerken met
  kladblok was volstrekt onzichtbaar. Er zijn nu sha1-vingerafdrukken van
  beide teksten en van het beeldmerk, plus een handtekening per
  instellingengroep. `sync_input_changes` draait aan het begin van elke
  stap, zodat geen route eromheen kan. Daarmee is ook het gat gedicht dat
  `advanced.forced_alignment` niet in de transcriptiecachesleutel zat -
  die optie herschrijft de woordtijden, maar uitzetten veranderde niets
  omdat de cache bleef raak schieten. De Demucs-stems krijgen een
  `source.sha1` naast zich; stems van vóór deze versie hebben er geen en
  blijven bruikbaar, want een goede scheiding weggooien kost minuten per
  nummer.
- **`ProjectStore.clear_meta`.** `clear_step` raakt principieel alleen
  `steps`, dus de projectbrede markeringen (`karaoke_from_original`,
  `vocal_onset_s`, `language_choice`) overleefden élke invalidatie. Er was
  domweg geen tegenhanger van `set_meta`.
- **Wat bewust NIET vervalt.** Te veel weggooien kost handwerk en is net
  zo fout als te weinig. De parodietekst wijzigen kost geen handmatige
  woordkoppelingen (die gaan over songtekst en transcriptie); een verse
  restzang-transcriptie kost geen handwerk aan het origineel (dat gebeurde
  wél: de invalidatie was niet per track); de uitlijning overleeft een
  nieuwe transcriptie (die wordt uit de twee audiobestanden berekend, niet
  uit de tekst - hem toch weggooien betekende de trage offsetbepaling
  opnieuw doen voor een ongewijzigd antwoord); de projectnaam en de
  videotitels overleven alles; en de gerenderde video wordt nooit
  weggegooid - die kost minuten en de gebruiker beslist zelf.
- **Bijhouden zonder dat het verrot.** Twee tests dragen dit ontwerp.
  `test_elke_stap_en_meta_staat_in_de_keten` doorzoekt `modules/` op elke
  `set_step`/`get_step`/`clear_step`/`*_meta`-sleutel en eist dat die in de
  keten staat: wie een stap toevoegt zonder te bepalen waarvan hij is
  afgeleid, krijgt rood in plaats van over een half jaar stille verouderde
  gegevens. `docs/afhankelijkheden.md` wordt gegenereerd door
  `tools/write_dependency_doc.py` en een test vergelijkt het bestand met
  wat de generator maakt, zodat het document niet achter de code aan kan
  gaan lopen. Dat is het antwoord op "hou dit bij": geen document dat
  discipline vraagt, maar een test die het afdwingt.
- **Nagemeten op de echte projecten.** De tien projecten op de pc hebben
  allemaal een kloppende checksum, dus de upgrade gooit niets weg. Op een
  nagebouwd v0.97-project gecontroleerd: eerste run na de upgrade verwijdert
  niets en voegt alleen de vingerafdrukstappen toe, een tweede run doet
  niets, en pas een bewerking in kladblok laat de juiste zes afgeleiden
  vervallen.
- **Les.** Drie van de zes rode tests na de verbouwing waren geen regressie
  maar een testopstelling die loog: `source_karaoke` met `"sha1": "x"` bij
  een echt bestand. De nieuwe bronbewaking had gelijk. Een testopstelling
  die iets beweert wat op schijf niet klopt, verbergt precies het soort
  fout dat je zoekt.

In v0.98.1 verwerkt:
- **B312: de afleidingsketen gooide een verse transcriptie meteen weer weg.**
  De gebruiker begon Lied_S opnieuw en draaide "1 Detecteer woorden".
  `project.json` meldde keurig 28 segmenten en 207 woorden, maar
  `cache/Lied_S/transcription_original.json` bestond niet meer. Het
  logboek wees het precies aan: *"Afgeleiden verwijderd na wijziging van
  whisper_original: cache:transcription_original"*.
- **Oorzaak.** `invalidate_after_fresh_transcript` betekent "de
  transcriptie is vernieuwd, wis wat op de vórige berustte". De keten
  leverde daarvoor alles wat van `whisper_original` afhangt - inclusief
  het transcriptiebestand zelf, want dat is nu eenmaal afgeleid van die
  stap. Het onderscheid dat ontbrak: een stap en het bestand dat hij
  schrijft zijn twee kanten van hetzelfde ding, gemaakt in één handeling.
  De stap is de administratie, het bestand de inhoud.
- **Oplossing.** `dependencies.direct_products`: een bestand waarvan een
  artefact de enige bron is, is zijn eigen product en blijft staan zolang
  dat artefact zelf niet expliciet wordt weggegooid. Een bestand met meer
  dan één bron (`output:lyrics_alignment` volgt uit de koppeling én de
  karaoketekst) is een echte afgeleide en vervalt wel. Bij
  `invalidate_timing`, waar timing.json juist wég moet, stond
  `include_changed` al aan; daar verandert niets.
- **Breder dan deze bug.** De test `test_elke_stap_spaart_zijn_eigen_product`
  loopt alle stappen langs die een bestand schrijven en eist dat geen
  enkele zijn eigen product wegwerkt. Zonder die test zou dezelfde fout
  gewoon terugkomen zodra clusters.json, alignment.json of
  karaoke_edited.wav aan de beurt was - het waren dezelfde vijf regels
  code die dat bepaalden.
- **Les.** Bij het invalideren is "wat hangt hiervan af" niet dezelfde
  vraag als "wat is hierdoor verouderd". Het antwoord op de eerste bevat
  het resultaat dat zojuist is gemaakt. Ik had de graaf getest op wat er
  wél weg moest en op wat er gespaard moest blijven van ándere takken,
  maar niet op het meest voor de hand liggende geval: het product van de
  stap die de aanleiding was.

In v0.99.0 verwerkt:
- **Aanleiding** – de gebruiker begon Lied_S opnieuw, met een lege cache.
  Whisper stopte na 134,9 s en begon pas weer op 196,0 s: 61 seconden zonder
  transcriptie, met daarin alleen twee hallucinaties. Het hele slotcouplet
  en het laatste refrein ontbraken. Opdracht: Whisper meteen meepakken, ook
  de nog ongebruikte opties, en de niet-opgepakte woorden alsnog plaatsen
  met een meting van de zangstem.
- **Wat het NIET was.** Drie Demucs-scheidingen uit exact hetzelfde
  bronbestand (dezelfde sha1) gaven drie verschillende zangstems. Toch is
  de stem niet de oorzaak: het energieprofiel per vijf seconden is in alle
  drie gelijk tot op drie decimalen, en de "goede" stem wijkt net zoveel af
  van de nieuwe twee (0,0037) als die twee onderling (0,0026). Er zit in
  alle drie gewoon zang in het gat. De beginprompt was byte-identiek, model
  en taal ook.
- **B314: wat het WEL is, gelezen in de broncode van faster-whisper.**
  Meten kon niet — de werkomgeving van de assistent mag het model niet
  downloaden — maar de bibliotheek zelf geeft het mechanisme prijs:

      should_skip = result.no_speech_prob > options.no_speech_threshold
      if avg_logprob > options.log_prob_threshold:
          should_skip = False
      if should_skip:
          seek += segment_size      # het HELE venster overslaan

  Een venster van dertig seconden wordt in zijn geheel overgeslagen. Ons
  gat is er ruwweg twee. Het is een drempelbeslissing, dus 3% audioruis kan
  hem omklappen. Daar bovenop komt de temperatuurladder: faster-whisper
  decodeert bij terugval mét bemonstering (`sampling_temperature`), en die
  is niet geseed. Dat verklaart precies wat we zagen: dezelfde knop, drie
  uitkomsten.
  `temperature` staat daarom standaard op enkel `0.0` — gulzig decoderen,
  dus herhaalbaar. Een karaokevideo die je niet kunt reproduceren is
  onbruikbaar, en zonder herhaalbaarheid is bovendien niets meetbaar. De
  drempels zelf zijn NIET blind verzet: welke waarde voor een nummer klopt
  valt niet te beredeneren. Ze zijn instelbaar geworden
  (`no_speech_threshold`, `log_prob_threshold`, `vad_filter`,
  `hallucination_silence_threshold`) met `tools/whisper_probe.py` ernaast,
  dat de varianten op de eigen zangstem naast elkaar zet. De
  afhankelijkheidsketen (B311) merkt zo'n wijziging en laat de transcriptie
  vanzelf opnieuw doen.
  Bijvangst: `save_config` schreef voor `whisper` een handgeschreven lijstje
  sleutels weg. De nieuwe instellingen werden wél ingelezen maar nooit
  teruggeschreven, dus een aanpassing in `config.json` verdween stil bij het
  volgende opslaan. Nu via `asdict`, met een test die elk veld van elke
  instellingengroep een rondgang laat maken.
- **B313: overgeslagen woorden op de zangstem plaatsen.** De uitlijning
  koppelt op klank; wat Whisper niet heeft geproduceerd valt niet te
  koppelen. En na een gat grijpt de uitlijning het enige wat binnen bereik
  ligt — gemeten: "alle" en "dagen" gekoppeld aan "la," met 0,25. Beide
  gevallen laten een woord zonder bruikbare tijd achter, terwijl de
  zangstem gewoon laat zien waar er gezongen wordt.
  Per reeks overgeslagen woorden tussen twee goede ankers wordt de gezongen
  tijd in dat venster in volgorde over de woorden verdeeld (via
  `spread_over_active` uit B310, dus stiltes worden overgeslagen). Drie
  regels houden het eerlijk: aan een goed gekoppeld of handmatig vastgezet
  woord wordt niet gezeten, de volgorde blijft behouden doordat een reeks
  binnen het venster van zijn buren blijft, en het resultaat is gemarkeerd
  als `estimated` — zodat een schatting niet stilletjes het gewicht van een
  meting krijgt in de betrouwbaarheidsbeoordeling van een regel.
- **De zelfcorrectie die B313 pas bruikbaar maakte.** De eerste versie
  perste 28 woorden in 3,5 seconde, omdat de gehallucineerde "MUZIEK" een
  perfecte koppeling (1,00) met het songtekstwoord "muziek" opleverde en
  dus als anker gold. Similariteit ontmaskert zo'n anker niet — het is een
  perfecte match op de verkeerde plek — maar het GEVOLG wel: acht woorden
  per seconde zingt niemand. Een venster dat meer dan zes woorden per
  seconde vraagt, laat daarom het aangrenzende anker los.
  Dat sloeg in de eerste opzet door: ook "serenade" en "aan" (1,00)
  schoven een seconde op en de echte la-la-koppelingen vijf. De oplossing
  is het isolatiecriterium: alleen een EENLING mag los — een anker zonder
  anker direct ervoor of erna. Een juiste koppeling staat zelden alleen,
  een verkeerd geplaatste per definitie wel, want er is niets omheen om aan
  te koppelen. Nagemeten op vijf projecten: precies de twee foute ankers
  laten los, geen enkele goede.
- **B315: de logregels door de vertaallaag.** Ze bleken aan de verkeerde
  kant van de taalgrens te staan: via `_QtLogHandler` komen ze in het
  logvenster terecht, dus de gebruiker leest ze. Alle 185 hebben nu een
  `log_`-sleutel in `nl` en `en`. De omzetting ging met AST in plaats van
  met tekstvervanging, en dat was maar goed ook: `ast` geeft kolomposities
  in BYTES van de utf-8-codering, niet in tekens, dus op elke regel met een
  trema liep het tekengewijs snijden scheef en verdween er een komma. Na
  het terugdraaien en opnieuw doen op bytes klopte alles.
  Drie tests bewaken het geheel: geen enkele `logger.x()` mag nog een
  letterlijke tekst hebben, elke gebruikte `log_`-sleutel moet bestaan, en
  de geordende reeks `%`-plaatshouders moet in beide talen gelijk zijn —
  dat laatste voor álle sleutels, wat tot nu toe nergens werd
  gecontroleerd. Een bestaande test ving trouwens meteen iets: mijn
  logteksten begonnen met "B307:", "B313:" enzovoort, en interne
  bugnummers horen niet in zichtbare tekst. Die staan nu in het commentaar.
- **Let op bij het bijwerken.** De Whisper-instellingen zijn veranderd, dus
  de instellingen-handtekening uit B311 verandert mee en de bestaande
  transcriptie vervalt: stap 1 moet één keer opnieuw. Dat is de keten die
  zijn werk doet — een transcriptie die met andere decodeerinstellingen is
  gemaakt, is een ander resultaat. Vanaf die run is de uitkomst wél
  herhaalbaar.

In v0.100.0 verwerkt:
- **B316 – de prompt is een hint, geen bron.** Uit het logboek van de
  gebruiker: hij sloeg een songtekst-override op (263 woorden) en de keten
  antwoordde met *"Afgeleiden verwijderd na wijziging van lyrics_override:
  cache:transcription_original, whisper_original, word_coupling"*. Ik had
  `whisper_original` van `lyrics_override` laten afhangen omdat de
  beginprompt uit de songtekst komt. Technisch waar, maar één woord knippen
  in de koppeleditor gooide daarmee tweeënhalve minuut rekenwerk weg —
  precies de over-invalidatie waar ik zelf voor gewaarschuwd had. De prompt
  zit al in de cachesleutel van de transcriptie, dus wie stap 1 bewust
  opnieuw draait krijgt een gewijzigde tekst alsnog mee. Nieuw: een
  testtabel die per bronwijziging vastlegt wat er juist NIET mag sneuvelen
  — die kant van de keten had ik te licht getest.
- **B317 – de kleur markeert, de legenda legt uit.** De codes voor het
  woord (`[vul]`, `[hal]`, `[zang]`, …) maakten de tekst slechter leesbaar
  en zeiden zonder uitleg niets. Ze zijn weg; bovenaan staat één legenda
  met gekleurde blokjes, opgebouwd uit dezelfde `_STATUS_STYLE`-tabel
  waarmee getekend wordt, zodat een nieuwe markering niet in beeld kan
  komen zonder uitleg.
- **B318 – wegen op lettergrepen.** `spread_over_active` verdeelde de
  gezongen tijd gelijk, dus "Espagna" kreeg evenveel als "e". Met
  `weights` (de lettergreeptelling van pyphen) wordt dat evenredig. Zonder
  gewichten blijft het oude gedrag exact staan.
- **B319 – het einde van de zang is een anker.** Het begin was dat al
  sinds B130/B133 (`vocal_onset_s`), het einde niet, terwijl dat net zo
  hard vaststaat. Er is nu een `vocal_end_s`, en twee dingen volgen
  eruit. Een koppeling die daarna ligt wordt losgemaakt: Whisper schrijft
  na de laatste zang nog wel eens iets op (applaus, uitfade, hallucinatie)
  en een songtekstwoord dat daaraan hangt trekt alles ervóór scheef —
  gemeten op Lied_S: één zo'n koppeling. En een reeks aan het eind wordt
  van achteren naar voren gepast wanneer het venster veel meer tijd biedt
  dan de woorden nodig hebben, met een lettergreepduur die op het nummer
  zelf gemeten is in plaats van aangenomen. Daar ligt immers de zekerheid:
  waar zo'n reeks eindigt weet je, waar hij begint niet.
- **B320 – de rijen liepen uit elkaar.** In een ongekoppeld stuk kregen de
  onderste woorden meteen een kolom, terwijl de bovenste pas een kolom
  kregen zodra er weer een gekoppeld paar langskwam. Gemeten met acht
  ongekoppelde woorden: boven `[0, 9, 10, …, 16]`, onder `[0, 1, …, 8]` —
  een verschuiving van 720 pixels, waardoor je niet meer zag welk gevonden
  woord bij welk songtekstwoord hoorde. Nu schuiven beide rijen samen op:
  achttien kolommen werden er tien en alles staat weer boven elkaar.
  Gekoppelde paren houden hun gedrag van B220.
- **B321 – de klik landde op het verkeerde woord.** Een koppeling wordt
  automatisch uitgerekt naar aangrenzende gevonden woorden (B191, tot
  drie), en zo'n groep werd als één breed vak getekend dat over de kolom
  van de buur rechts heen ligt. `_hit_row` gaf binnen dat vak altijd het
  EERSTE woord van de groep terug: klikken op "dable" in de groep
  "formi|dable" leverde "formi" op, en dus landde een koppeling op het
  woord links van je aanwijzer. De groepering is een tekenkeuze en bepaalt
  nu niets meer over wat je kunt aanwijzen; binnen de groep staat een
  stippellijntje zodat je ziet waar je mikt.
- **B322 – het venster startte te klein voor zijn eigen inhoud.** De
  layout vraagt 789×807, het vensterminimum stond op 760×520. Dat minimum
  is er bewust (B216: krimpen moet mogen), maar het liet het venster ook
  starten op een maat waarop de groepsvakken hun tekst over elkaar heen
  tekenden — gemeten kreeg het invoerblok 54 / 90 / 140 / 175 pixels bij
  een venster van 520 / 600 / 700 / 800, terwijl het er 175 nodig heeft.
  De opstartmaat wordt nu opgetrokken tot wat de layout vraagt, begrensd
  door `availableGeometry` (die de taakbalk al buiten beschouwing laat).
  Het minimum blijft staan, dus daarna zelf kleiner maken mag nog steeds.
- **Les.** Twee van de drie rode tests na afloop waren geen regressie maar
  besmetting: mijn eigen testopstelling verving `rhythm.active_windows`
  rechtstreeks in de module in plaats van via `monkeypatch`, en die
  vervanging bleef staan voor de tests erna. Een testopstelling die de
  echte module aanpast zonder hem terug te zetten, maakt de volgorde van
  de tests onderdeel van het resultaat.

In v0.101.0 verwerkt:
- **B326 – de vastloper bij "2.2. Timing verfijnen".** Uit het logboek:
  `Zin-koppeling: {'high': 43, 'medium': 0, 'low': 16}` en direct daarna
  `KeyError: 'hoog'` op `pipeline.py:3624`. De sleutels van de
  koppelkwaliteit heten sinds B299 Engels; op deze ene plek stond nog
  `quality['hoog']`. Hij zat er dus sinds v0.96 in en viel pas nu op,
  omdat deze regel alleen via die ene knop bereikt wordt — een tak zonder
  test en zonder ander pad ernaartoe. Bij het nakijken bleek het niet één
  vergeten regel te zijn maar een groepje: de teksten die de pijplijn aan
  de GUI teruggeeft (het `{detail}` van de timing, de video-invoercontrole,
  de structuurcontrole van songtekst/karaoketekst en de melding van de
  timing-synchronisatie) stonden allemaal hardgecodeerd in het Nederlands.
  De wacht uit B315 keek namelijk alleen naar `logger.*`-aanroepen, en
  deze teksten gaan niet naar het log maar naar het meldingenpaneel en de
  QMessageBox. Ze lopen nu via `translations.py`; de nieuwe wacht is
  gedragsmatig in plaats van tekstueel — hij roept de functies twee keer
  aan, in `nl` en in `en`, en eist dat het antwoord verschilt.
- **B326-vervolg – een vergelijking op een vertaalde naam.** `render_video`
  bepaalde welke ontbrekende invoer hij mocht negeren met
  `name != "offset origineel/karaoke"`. In het Engels heet dat item
  "offset original/karaoke", dus daar had de render geweigerd op een
  ontbrekende offset die juist optioneel is (stap 1.4 lijnt zelf uit).
  `video_input_status` geeft nu per regel een taalonafhankelijke sleutel
  terug naast de naam voor de gebruiker, en de uitzondering staat als
  `VIDEO_INPUT_OPTIONAL` in code in plaats van in een zin.
- **B325 – de knoppen dragen hun tabblad.** De acht hoofdknoppen heten nu
  1.1.–1.4. en 2.1.–2.4.; tab 1 had helemaal geen punt achter het cijfer,
  tab 2 wel. Het echte werk zat niet in de knoppen maar in de veertien
  meldingen die een knop bij naam noemden ("draai eerst '1 Detecteer
  woorden'") — precies het soort tekst dat bij elke hernummering
  achterloopt, zoals B297 al eens aantoonde. Een melding schrijft nu
  `{step_detect}` en `t()` vult de actuele naam in. Andere plaatshouders
  (`{track}`, `{file}`) blijven staan, zodat de aanroeper zijn eigen
  `.format()` gewoon houdt. Een test eist dat geen enkele tekst een
  knopnaam nog uitschrijft.
- **B323 – Stop pakte de bezig-kleur af.** `_install_busy_indicator` haakt
  aan élke `QPushButton`, dus ook aan Stop. Klikte je Stop, dan werd Stop
  de eigenaar van `_busy_button`, en het opruimen na het afbreken zette
  vervolgens Stop terug in plaats van "1.1. Detecteer woorden" — die bleef
  geel. Drie dingen: Stop haakt niet meer aan (hij start niets, hij
  beëindigt), een klik tijdens een lopende taak neemt het eigenaarschap
  niet over, en `_busy_button` is een verzameling geworden zodat er nooit
  één achterblijft.
- **B324 – de schrijfsleutel was de bestandsnaam.** `_copy_into_input`
  leidde de sleutel af met `Path(target_name).stem`, wat `songtekst` en
  `karaoketekst` oplevert; `_refresh_inputs` en de bestandskiezer vragen
  om `lyrics` en `karaoke_text`. Gevolg: bij beide teksten stond altijd de
  interne naam in plaats van "viva espanja-origineel.txt", en de
  bestandskiezer opende niet in de laatst gebruikte map. Bij het logo werkte
  het bij toeval wél, want daar is de stam ook "logo". De sleutel wordt nu
  expliciet meegegeven, staat als `INPUT_NAME_KEYS` op één plek, en
  bestaande projecten worden bij het openen eenmalig omgezet
  (`migrate_input_names`, idempotent, laat een al goede waarde staan).
- **B327 – een label dat zijn eigen sleutel toont.** De golfvorm-editor
  bouwt zijn baanlabels op met `t(f"lane_{key}")`, en drie van die keys
  (`origineel_tekst`, `karaoke_regels`, `zangstem`) waren bij B299 in het
  Nederlands blijven staan. `t()` valt terug op de sleutel zelf, dus er
  stond letterlijk `lane_zangstem` in beeld — in beide talen, en ook in de
  bronkeuze en de "niet beschikbaar"-melding. De wacht uit B315 miste dit
  omdat hij op `t("log_...")` matcht: letterlijk, en alleen logsleutels.
  Alle `t(f"...")` in `modules/` zijn nagelopen; `model_{key}_desc`,
  `view_{mode}` en `t(track)` waren in orde, deze drie niet. De nieuwe test
  loopt de tabel `_LANE_LABELS` af en eist dat geen sleutel zijn eigen naam
  teruggeeft.
- **B328 – de handleiding beschreef de helft.** Aanleiding was de vraag of
  er nog meer in de handleiding verwezen kon worden. Wat ontbrak was vooral
  het handwerk: de vier editors staan er nu in met hun muisregels, de
  kleurenlegenda van de koppeleditor (inclusief de vijf statuskaders en het
  doorgestreepte gefilterde woord), en een tabelletje voor het venijnigste
  verschil — "Sluiten" slaat op in de koppel- en klemtooneditor en gooit
  weg in de golfvorm- en dempingeditor. Verder de groene "Terug uit
  origineel"-blokken, "Regel uit/aan", de weergavekeuze
  Blokken/Zinnen/Woorden, de zangstem-analyse, het cachebeheer, de
  outputmap, en de render-dialoog die niet alleen muziek maar ook tékst
  kiest. Twee dingen klopten niet meer: die render-dialoog, en de volgorde
  op tab 2 — "2.1. Klemtoon bewerken" weigert te openen tot "2.2. Timing
  verfijnen" een `timing.json` heeft gemaakt. Ten slotte verwijst de
  handleiding nu naar `docs/afhankelijkheden.md`, dat sinds B311 precies de
  zin onderbouwt die er als losse bewering stond.
- **Les.** Twee bugs van deze ronde (B326 en B327) zijn dezelfde bug: een
  hernoeming die op een pad landde waar geen test langskomt. De wacht die
  B315 daarvoor optuigde was tekstueel — hij zocht naar een letterlijk
  patroon in de broncode — en miste daarom alles wat dynamisch is opgebouwd
  of niet naar het log gaat. De wachten van deze ronde toetsen gedrag: roep
  het aan in twee talen en vergelijk. Dat vindt ook wat je niet van tevoren
  hebt bedacht.

In v0.102.0 verwerkt:
- **De ijkset.** Deze ronde begon met een meetopstelling in plaats van met
  een idee. De gebruiker corrigeert `timing.json` met de hand in de
  golfvorm-editor terwijl `timing_auto.json` het automatische resultaat
  bewaart; die twee bestanden samen zijn een ijkpunt, want elke regel die
  hij heeft verschoven is een regel die de automaat fout had. Acht
  projecten leverden 130 zulke regels. `tools/timing_regression.py` bouwt
  de invoer van `sanitize_timing` terug uit de opgeslagen zinkoppeling,
  draait de huidige code eroverheen en rapporteert twee getallen: hoe ver
  de verzette regels ernaast zaten, én hoeveel regels die de gebruiker
  ongemoeid liet er slechter van worden. Dat tweede getal is het
  belangrijkste — een gemiddelde dat verbetert terwijl er goede regels
  sneuvelen is geen verbetering.
- **B332 — het zinsniveau redeneerde in lettergrepen.** `sanitize_timing`
  verdeelde de regels tussen twee ankers *pro rato van lettergrepen* en
  begrensde de duur op `basistempo × lettergrepen × 3`. Dat leest als
  logisch maar het is een woordbegrip, een verdieping te hoog gebruikt:
  een regel van vier lettergrepen krijgt niet een kwart van de tijd van
  een regel van zestien, hij krijgt zijn eigen frase. Een gezongen regel
  is een muzikale frase en die duurt een vast aantal maten — bij Lied S
  begint er elke 3,77 s een nieuwe regel, wat bij 129 BPM precies 8 tellen
  is, en 38 van de 59 handmatige regelbeginnen liggen binnen 0,10 s van
  een gedetecteerde tel. Een strak raster over het hele lied werkt níét
  (dan vallen er maar 13 van de 59 op): de periode is lokaal stabiel, de
  fase niet, want instrumentale stukken breken hem. `phrase_period` meet
  hem daarom over de afstanden tussen opeenvolgende betrouwbaar getimede
  regels en geeft `None` zodra de spreiding boven 18% komt — dan zet het
  hele mechanisme zichzelf uit en werkt alles als voorheen. Bewust over
  álle regels gemeten, crowd inbegrepen: in een parodie is een crowd-regel
  vaak een volwaardige frase, en ze eruit filteren joeg de spreiding van
  6% naar 50%.
- **B332 — de winst zit in het toetsen, niet in het verdelen.** Gemeten op
  het kapotte stuk van Viva: de frasemaat als verdeelgewicht bracht 7,18
  naar 4,53 s, maar als *geldigheidstoets op de ankers* naar 2,09. Een zin
  die geen frase kán zijn is geen geloofwaardig anker, en dat werkt juist
  waar de duur-referentie niets kan zeggen — de "La la la"-regels in de
  outro hebben een spreiding van 63% en dus geen bruikbare mediaan, maar
  spannen van 0,64 en 0,80 s zijn bij een frase van 3,6 s onmogelijk.
  De toets keurt ook goede ankers af (korte halve-frase-regels), maar dat
  kost 0,06 tot 2,11 s terwijl een fout anker in een gat 7 tot 12 s kost;
  die asymmetrie is het argument om hem vroeg te zetten. Wel bleek de
  ondergrens kritisch: op 0,45 × periode sneuvelde een echte regel van
  1,42 s bij een periode van 3,72 en verschoof alles erna 2,27 s. Nu 0,25.
- **B329 — een herhaalde zin is overal ongeveer even lang.** Het idee van
  de gebruiker, en de meting gaf hem gelijk: "E viva Espagna" komt 12 keer
  voor met mediaan 3,60 s, en de exemplaren van 7,66 en 5,31 s waren geen
  aangehouden zinnen maar de oorzaak. Samen met een derde uitschieter
  verklaarden ze 8,8 s van de 9,4 s verschuiving die daarna in het hele
  staartstuk zat. `reference_durations` bouwt die referentie alleen uit
  écht gemeten exemplaren — een schatting als referentie bevestigt zijn
  eigen fout, en in Lied N staat "oehoe oehoe" vijf van de negen keer
  op exact 1,99 s, wat geen waarheid is maar een gelijkmatige verdeling.
  Een tekst met een spreiding boven 15% levert niets: "Sunday Bloody
  Sunday" varieert van 0,10 tot 8,50 s en dat is echt zo. Dit is de
  generalisatie van B166, dat precies dit al deed maar alleen voor de
  regels ná het laatste anker.
- **B330/B331 — de inzetten binnen een venster.** `active_windows` geeft
  alleen de buitenranden van een gezongen passage. De twee "Ole!"-roepen
  in de intro (1,65–4,30 en 4,35–6,80) smolten daardoor samen tot één
  venster van 5,2 s, waarna beide regels gelijkmatig over dat hele gat
  werden uitgesmeerd: 4,78 s per stuk in plaats van 2,55. `rhythm.onsets`
  zoekt stijgflanken ín het venster. Tegen de handmatige timing gehouden
  lag elk regelbegin in een gat van vijftig seconden binnen 0,6 s van zo'n
  inzet, mediaan 0,15 s. Het snappen gebeurt ná de structuur en alleen op
  geschatte regels; een gemeten regel wordt nooit verplaatst.
- **De volgorde is geen detail.** Op een structuur die nog 2 s scheef
  stond maakte het snappen de uitslag *slechter* (2,09 → 2,32) omdat het
  dan de inzet van de buurregel pakt. Op een rechte structuur brengt het
  de regel tot binnen een fractie. Vandaar de reikwijdte van 0,45 × de
  frase: verder en hij grijpt naast.
- **Twee eigen fouten die de meting eruit haalde.** De eerste versie van
  het snappen begrensde het BEGIN van een verschoven regel maar niet zijn
  EINDE, waardoor de gemeten regel erna alsnog vooruit werd geduwd — vijf
  regels die goed stonden gingen zo mis. En ik had een tak ingebouwd die
  regels bij een groot gat tussen twee ankers op hun eigen frase liet
  doorlopen in plaats van uitsmeren; die verbeterde het ene lied en
  verslechterde het andere méér, dus is hij er weer uit. Zonder de ijkset
  had ik hem laten staan.
- **Resultaat en grenzen.** Gewogen fout op de 130 verzette regels: 4,60 s
  → 2,98 s. Lied S van 5,38 naar 0,70, Lied G van
  4,75 naar 2,26, Lied J van 1,13 naar 0,06, Lied P van 3,80
  naar 3,26. Lied N gaat licht achteruit (3,48 → 3,66) en Lied T
   duidelijk (7,60 → 9,26, met vier ongemoeide regels
  slechter). Dat laatste lied heeft een instrumentaal gat van 34 seconden
  midden in zijn la-la-staart; de oude gelijkmatige uitsmering landde daar
  bij toeval beter. Dat is eerlijk gezegd geen opgelost probleem maar een
  geruilde fout, en het staat op de lijst.

In v0.103.0 verwerkt:
- **B333 — de koppeling had gelijk, de timing niet.** "Lied G
  " liep monotoon weg: +2,2 s aan het begin, −7,3 s aan het eind,
  52 van de 64 regels met de hand gecorrigeerd. Het vermoeden was
  uitlijndrift tussen origineel en karaoke, maar dat kon niet: die karaoke
  is met Demucs uit het origineel gemaakt, dus offset 0 en één tijdlijn.
  De meting wees ergens anders heen. Ik heb de originele zin-spannen uit
  de opgeslagen koppeling naast de handmatige tijden gelegd: **mediaan
  0,34 s ernaast**. De koppeling klopte dus gewoon. Wat de timing ervan
  maakte lag er 4,19 s naast. Het probleem zat volledig in
  `sanitize_timing`.
- **De oorzaak: opgestapelde duwtjes.** Een regel die korter is dan zijn
  minimumduur wordt opgerekt, en dat schoof de volgende regel vooruit via
  `start = max(starts[k], prev_end)` — ook als die volgende regel een écht
  gemeten begin had. Eén zo'n duwtje is klein (dit lied heeft zes zinnen
  onder de seconde, samen 3,6 s tekort), maar het minimum hangt ook aan
  het lettergreepaantal van de karaokeregel, en de duwtjes tellen op omdat
  elke geduwde regel zijn opvolger weer duwt. Vandaar dat het verloop
  monotoon is en niet grillig: het is een som, geen fout.
- **De reparatie, en waarom hij een uitzondering nodig had.** Een gemeten
  begin wint nu van de minimumduur van de regel ervoor; die wordt
  ingekort in plaats van de volgende weg te duwen. Dat brak meteen een
  bestaande test (B139/B148: vier herhaalregels die de koppeling op een
  derde seconde van elkaar zette, mogen niet tot slivers worden geplet).
  Terecht: als de ánkers zelf opgepropt staan kunnen ze niet allemaal
  kloppen, en dan is uitspreiden nog steeds het beste dat je kunt doen.
  De regel is nu: inkorten alleen als de regel ervoor daarna nog aan zijn
  eigen minimum komt. Dat onderscheidt "één te korte zin tussen goede
  ankers" van "een tros ankers die niet allemaal waar kan zijn".
- **De meetlat, en waarom hij nodig was.** De gebruiker wees erop dat "Lied G
  " al een tijd en heel wat versies geleden is
  gemaakt. Dat bleek precies raak: de opgeslagen `timing_auto.json` komt
  bij zes van de acht projecten uit versie 0.73 tot 0.93. Een vergelijking
  daarmee meet dus alles wat er sindsdien is gebeurd en niet wat één
  wijziging waard is — mijn eerdere "4,60 → 2,98" was in die zin te mooi.
  `tools/timing_regression.py --vergelijk` zet nu twee draaien van het
  gereedschap tegen elkaar af in plaats van tegen een opgeslagen bestand,
  en `--noteer` schrijft de uitslag per versie weg in `docs/metingen.md`:
  per project hoeveel zinnen er gekoppeld zijn, hoeveel regels er met de
  hand zijn verzet en hoe ver de code daar nog vanaf ligt. Zo blijft over
  releases heen zichtbaar welk lied beter wordt en welk lied betaalt voor
  een verbetering elders.
- **Eerlijk gemeten.** Tegen v0.101 op dezelfde invoer: gewogen 4,62 s →
  2,41 s over 141 handmatig gecorrigeerde regels. Lied G
   4,62 → 0,65, Lied S 5,89 → 0,70, Lied J 1,13 → 0,06,
  Lied P 3,76 → 3,33. Lied N 3,48 → 3,71 en Lied T
   7,60 → 9,26 gaan achteruit; die laatste blijft de openstaande post.

In v0.104.0 verwerkt:
- **B338 - de meetlat mat het verkeerde, en dat kwam eerst.** Het
  gereedschap uit v0.103 bouwde de invoer van het zinsniveau terug uit de
  opgeslagen zinkoppeling. Daar zitten de handmatige correcties van de
  gebruiker op de originele baan in verwerkt: bij Lied G
   58 van de 64 zinnen, bij Lied N 58 van de 69, bij
  Lied P 45 van de 50. De timing kreeg in mijn meting dus een
  invoer die al met de hand was rechtgezet. Het draait nu de echte
  pijplijn over de opgeslagen transcriptie (de diagnostiekkopie van de
  segmenten, die een geleegde cache overleeft) en laat elke handmatige
  stap weg. Het gewogen cijfer gaat daarmee van 2,41 s naar 3,37 s. Dat
  is geen achteruitgang maar een correctie: ik was handwerk als verdienste
  van de tool aan het tellen. De oude rijen in `docs/metingen.md` zijn
  weggehaald in plaats van naast een eerlijke meting te blijven staan.
- **B334 - de herhaallus van Whisper.** Bij het nieuwe project stonden 34
  kopieen van "now," op exact 193.500 s, en 13 keer "oh yeah" op 223.500.
  Betrouwbaarheid 0,98, en "now" komt echt in de songtekst voor, dus geen
  enkele inhoudelijke controle ziet er iets in. De vorm verraadt het wel:
  begin en eind zijn gelijk, dus het woord draagt geen tijd. Het kan
  daarom niets bijdragen aan een timing en alleen een verkeerd anker
  worden - dat maakt weggooien veilig. Over elf projecten gemeten hebben
  acht geen enkel woord zonder duur, twee hebben er een, een heeft een
  reeks van drie en het probleemlied heeft er 34. De drempel ligt op vier:
  dat drietal weghalen maakte Lied N meetbaar (0,16 s) slechter, dus
  dat blijft staan. Het filter zit in het leespad, dus bestaande projecten
  profiteren zonder dat Whisper opnieuw hoeft en zonder dat het
  cachebestand wordt aangeraakt.
- **B336 - de staart hoort waar gezongen wordt.** Waar de transcriptie
  stopt (Whisper schrijft geen vocalises op, dus een "na-na-na"-staart
  levert niets) werden de regels over de resterende speelduur uitgesmeerd.
  Dat gaat mis zodra er nog een instrumentaal stuk in de staart zit. De
  zangstem laat precies zien waar wel gezongen wordt, en de vensterlengte
  gedeeld door de fraseperiode zegt hoeveel regels erin passen: 14,56 s =
  3,90 frases -> 4 regels, 29,88 s = 8,01 -> 8 regels, terwijl een piekje
  van 0,88 s (0,24) en een uithaal van 4,78 s (1,28) er geen dragen. Die
  heeltallige toets is precies wat een reeks gezongen regels onderscheidt
  van een lange noot. Klopt het totaal niet exact, dan doet de regel niets
  - liever niets dan een zelfverzekerde vergissing. Op het lied waarvoor
  hij bedoeld was: twaalf regels, gemiddeld 0,24 s ernaast tegen 9,26 s.
- **B336 - en waarom dat niet in de meting terugkomt.** Dat lied viel uit
  de ijkset: de gebruiker heeft de karaoketekst sindsdien aangepast (36
  regels tegen 40 in de opgeslagen timing), dus de ijkpunten liggen niet
  meer naast elkaar. Van de overige zeven projecten heeft er geen enkele
  een echte staart na het laatste anker. De regel is dus wel doorgerekend
  op de plek waar hij hoort, maar hij staat niet in het gewogen cijfer.
- **B337 - de lijsten hoorden bij de taal, niet bij de code.** De
  hallucinatie- en vulwoordenlijsten waren een vaste Nederlandse set
  ("muziek", "ondertiteling", "zang", en "en/de/het/een") terwijl de
  originelen Engels en Frans zijn. Ze zitten nu in de taalregistry die
  B241 al had: naast klinkers en clusters staan er `hallucinations` en
  `fillers`, ze reizen mee in `languages/<code>.json`, en de opzoeking is
  een VERENIGING van meegeleverd en verzameld - anders wordt een verzameld
  bestand voor een ingebouwde taal stilletjes genegeerd en gebeurt er
  niets als je een woord markeert. Een onbekende taal krijgt lege lijsten,
  dus een Deens liedje maakt zijn eigen `da.json` en er komt niets in de
  meegeleverde set. Een test eist dat elke ingebouwde taal beide sleutels
  expliciet heeft, zodat er geen taal bij kan komen zonder besluit.
- **B337 - op de plek, niet liedbreed.** De toets was "komt dit woord
  ergens in de songtekst voor". Gemeten: alle acht keer "you" in Walking
  on Sunshine staan in de eerste 36% van het lied, en beschermden daarmee
  een "Thank you" in de outro tweehonderd woorden verderop. De toets
  gebruikt nu het positievenster van B307 - het stuk songtekst tussen de
  dichtstbijzijnde goed gekoppelde woorden. Belangrijk detail dat de
  meting eruit haalde: die toets is TOEGEVOEGD aan de bestaande ronde en
  niet in de plaats gekomen. Ik had eerst de liedbrede controle uit ronde
  1 gehaald omdat de positie pas in ronde 2 bekend is; dat kostte Lied S
  meteen 5 seconden, want daar viel een segment weg dat ronde 1 juist
  terecht opruimde.
- **B337 - aanvulbaar vanuit de koppel-editor.** Van de vijf markeringen
  in de legenda zijn er drie een meting ("Whisper hoorde hier niets",
  "getimed op de zangstem", "geen match") en twee een oordeel. Alleen die
  twee zijn klikbaar geworden: hallucinatie werkt op de bovenste rij (wat
  Whisper vond), vulwoord op de onderste (de songtekst). Selecteren,
  klikken, en het woord komt in de lijst van de audiotaal; nog eens
  klikken haalt het weg. Een meegeleverd woord is niet met de hand te
  wissen - dat blijft een codebeslissing.
- **Eerlijk over de opbrengst.** B334, B336 en B337 veranderen op de zeven
  meetbare projecten geen enkel cijfer: 3,37 s voor en na. Dat is geen
  toeval maar de aard van dit werk - het gaat om gevallen die in deze
  liedjes niet voorkomen (de herhaallus zit in een project waarvan stap
  2.2 nog niet is gedraaid) of om gereedschap dat pas iets doet als de
  gebruiker het gebruikt. Wat wel telt: geen van de 130 verzette regels
  gaat erop achteruit, en de "Thank you." die B337 moest vangen bleek al
  door de bestaande controles te worden opgeruimd. De woordenlijsten
  bewijzen zich pas bij een artefact met een hoge betrouwbaarheid.

In v0.105.0 verwerkt:
- **Welke liedjes werken goed - in de handleiding.** Aanleiding was
  "Lied F" (naar Walking on Sunshine): koor en lead
  zingen aan het eind door elkaar, met veel korte tussenroepsels, en de
  koppel-editor werd daar onleesbaar - "een langspeelplaat met een kras",
  in de woorden van de gebruiker. Dat is geen fout die je per lied opnieuw
  hoeft te ontdekken maar een eigenschap van het gereedschap, dus staat
  het nu in `docs/handleiding.md` onder "Wat voor liedjes werken goed?":
  waar het aan ligt (alles hangt aan wat Whisper van de zangstem maakt),
  waaraan je het herkent (veel groenblauwe kaders - wel een tijd, niet
  gekoppeld - of roze, meestal aan het eind), wat de tool er dan doet (de
  regels op de zangenergie zetten, wat een schatting is) en wat je zelf
  kunt doen (`[bg]` bij echte overlap, en anders de golfvorm-editor).
- **Wat de meting eronder zei.** Voor die tekst is het lied regel voor
  regel tegen de handmatige correctie gelegd, omdat de gebruiker het
  idee had dat er stukjes opschoven als een cumulatieve fout. Dat idee
  klopt, maar alleen aan de staart. Het begin staat elf regels lang op
  0,00 s. Het midden wisselt: -0,61 s tot +1,67 s, zes regels vooruit en
  zes achteruit - ruis, geen drift. Vanaf regel 44 is het eenzijdig en
  oplopend: +1,95 s naar +16,36 s, achttien vooruit tegen drie achteruit.
  De onderlinge afstand van de automatische regels is daar mediaan
  1,19 s tegen een frase van ongeveer 3 s, met vier regels op precies
  `_MIN_PHRASE_S` (1,00 s). Dat is het beeld van regels die tegen hun
  minimumduur aan geperst worden en elkaar vooruitduwen.
- **Beide vangnetten stonden erbij en deden niets - volgens ontwerp.**
  `phrase_period` meet op dit lied 25% spreiding tegen een grens van 18%
  en geeft `None` terug, waarmee B332 en B336 zichzelf uitzetten; dat is
  precies de zelf-uit-schakelaar waar ze om vragen, want zonder
  betrouwbare periode zou de mechaniek gaan gokken. En B333 stapt opzij
  zodra ankers opgepropt staan (de B139/B148-uitzondering), wat hier het
  geval is. Er is dus niets kapot; het lied levert de informatie niet die
  de correctie nodig heeft. Twee posten daaruit gaan op de stapel:
  **B339** - regelmarkering/regelnummers in de onderste rij van de
  koppel-editor, want elk woord draagt al een `line` in de weergavedata
  maar die wordt nergens getekend, en zonder dat leest een herhalende
  outro als een muur. **B340** - een reeks ankers die veel dichter op
  elkaar staat dan de frase kan niet in zijn geheel kloppen. Waarschuwing
  daarbij, uit de ontwikkeling van v0.102: een grove variant per paar is
  geprobeerd en was slechter (die sloopte de helft van de couplet-ankers);
  het moet op een *reeks* werken, en het heeft een periode nodig die juist
  dit lied niet levert.

In v0.106.0 verwerkt:
- **B347 - de woordtiming bij een pauze binnen de regel.** Aanleiding was
  de vraag of het bij "Lied D" goed was gegaan met de twee zinnen waar
  een pauze in zit ("Lightning and thunder [2,06 s] magic and wonder" en
  "Golden reflections [2,10 s] givin' directions"). Dat was het niet: van
  de 282 woorden in dat lied hebben er acht helemaal geen duur, en die
  acht zitten allemaal in precies die twee regels, vier van de acht
  woorden per regel, opgestapeld op het regeleinde. In de video lichten
  die in één klap op. Oorzaak: `distribute_over_windows` (B234) telt de
  lettergrepen op twee manieren. De opgeslagen regel bestaat uit 25
  brokjes ('I', 'k', ' g', 'i', 'ng', ...), maar de functie loopt erdoor
  met de telling die `split_line` uit de woordtekst haalt, en die komt op
  10. Na tien brokjes denkt hij klaar te zijn, en het opruimregeltje aan
  het eind zet de overgebleven vijftien op `line.end` met begin gelijk
  aan eind - bij het naspelen kwam er zelfs een woord met een negatieve
  duur uit ("jaren" van 85,34 tot 82,69). Het aandeel van een woord wordt
  nog steeds op lettergrepen gewogen (dat is waar B234 om draait), maar
  de brokjes komen nu uit `piece_groups`, dat telt wat er werkelijk
  staat. Dat het maar bij twee regels zichtbaar was heeft een reden: de
  functie springt er meteen uit zodra een regel maar één zangvenster
  heeft. Alleen een regel mét pauze komt binnen, en zodra hij binnenkomt
  ging het mis. Twee kansen, twee keer raak.
- **B345 - voorbij het eind van het nummer.** Gemeten op een testliedje
  van 20 seconden: de laatste regel liet zich rekken tot 80 s en in zijn
  geheel verslepen naar 199,5-200,5 s, en een originele zin tot 90 s. In
  alle drie de sleepstanden stond de linkerkant al vast (`max(0.0, ...)`)
  en de afspeelkop werd al begrensd op de duur - de blokken hadden die
  behandeling nooit gekregen. Karaokeregels gaan tegen de duur van de
  karaoketrack, originele zinnen tegen die van het origineel.
- **B346 - elkaar passeren.** De 2 rijen op de originele baan en de 3 op
  de karaokebaan zijn puur een tekentruc (`index % 2` en `index % 3`),
  dus daar kon het niet aan liggen. De tijden konden elkaar wél
  passeren: regel 2 op 3,0-4,0 naar 0,4 s gesleept landde op 0,0-1,0,
  vóór regel 1. `clamp_span` bewaakt namelijk *overlap* en niet
  *volgorde* - hij laat het blok in het dichtstbijzijnde vrije gat
  vallen, en een gat vóór de voorganger is net zo vrij. Drie routes
  ernaartoe: de gewone sleep, de crowd-regels die van de overlapcontrole
  zijn uitgezonderd, en de blokweergave, waar de controle helemáál werd
  overgeslagen omdat hij achter `if single:` stond. De editor gebruikt
  `clamp_span` nu niet meer maar begrenst op het EIND van de vorige en
  het BEGIN van de volgende; dat verbiedt overlappen en passeren in één
  greep en laat inschuiven tegen een buur gewoon werken. Afspraak met de
  gebruiker: nooit overlappen, crowd uitgezonderd - en passeren mag
  niemand, ook crowd niet, dus die wordt begrensd op het begin van de
  vorige en het eind van de volgende (overlappen mag, eroverheen
  springen niet).
- **B341 - de bezig-kleur was dood sinds B323.** Gemeten met een echte
  klik: een knop die een taak start komt niet in `_busy_buttons` en
  houdt een lege stylesheet. Dat geldt niet alleen voor "2.4. Video
  maken" maar voor alle acht de stapknoppen. De vangrail uit B323 ("er
  loopt al iets, dus deze klik neemt de kleur niet over") wordt namelijk
  pas ná de eigen handler bereikt, en die heeft de worker al gezet én
  gestart - `QThread.isRunning()` staat direct na `start()` op waar,
  apart nagemeten. Elke knop stapte dus opzij voor zijn eigen taak. De
  eigenaar wordt nu bepaald op "is er een taak BIJGEKOMEN": `pressed`
  vuurt vóór `clicked` en onthoudt welke worker er was, en een andere
  worker daarna hoort bij deze klik. B323 blijft daarmee overeind. De
  oude test zag dit niet omdat hij `_mark_busy_click` rechtstreeks
  aanriep met een lege `_worker`; de nieuwe gaat door een echte klik.
- **B342 - het doorgeknipte woord op de segmentgrens.** Whisper
  decodeert in stukken, en een woord dat op de knip valt komt er twee
  keer uit: een afgeknipt stompje aan het eind van het ene segment en
  het hele woord aan het begin van het volgende, met een hoofdletter
  (daar begint voor hem een nieuwe zin) en soms verkeerd verstaan, omdat
  hij dat stuk opnieuw hoort zonder de aanloop ervoor - vandaar
  "Collections" voor "reflections". Vier gevallen gemeten over twee
  projecten, steeds dezelfde vorm: het stompje is korter (0,08-0,38 s)
  én onzekerder (0,01-0,25) dan zijn tweelingbroer. Het bewijs dat het
  één woord is zit in het lied zelf: "dreaming" duurt 1,31 s en 1,36 s
  waar het niet op een knip valt, en de twee helften samen beslaan
  1,29 s. Ze worden nu weer aan elkaar geplakt in het leespad (naast
  B334), zodat de koppeling één woord ziet en de timing de echte inzet
  krijgt. De grens ligt op 0,30 s tussenruimte: de gemeten gaten zijn
  0,020, 0,120 en 0,201 s. Het vierde geval zit op 0,702 s en blijft met
  opzet staan - daar zou samenvoegen zeven tienden stilte binnen een
  woord proppen. Wat de gelijkenis alléén niet mag doen laat de
  tegenproef zien: bínnen een segment staan overal echte herhalingen
  ("Tickle, tickle", "niggle, niggle", "No, no, no", en bij Woah-oh een
  rij van veertig "now,"), dus de segmentgrens is de hele handtekening.
  Over de drie transcripties waarvan de woorddata er nog is: Lied D 2
  samenvoegingen, Woah-oh 1, Lied S 0. Precies de bekende gevallen en
  niets anders.
- **"amen" in de Engelse lijst.** Gemeten: 182,140-182,249, dus 0,11 s,
  betrouwbaarheid 0,032, in een eigen segmentje, 2,1 s nadat de zang
  stopte en met nog vijf seconden uitfade te gaan. Hij bleef staan omdat
  de brede controle minstens twee kernwoorden eist (B285) en "Amen" er
  één is, dus alleen de vaste lijst kon hem nog vangen. Veilig om mee te
  leveren omdat de toets sinds B337 naar de plek in de songtekst kijkt:
  een lied dat daar echt "amen" zingt houdt hem.
- **Handmatig gerepareerd op verzoek.** De `timing.json` van Lied D
  is op verzoek van de gebruiker bijgewerkt in plaats van de timing
  opnieuw te laten doen: alleen regel 1 en 20, de woorden herverdeeld
  over de twee gezongen helften met dezelfde berekening als B347, buiten
  begin en eind van de regel ongemoeid. Dat is geen code maar het staat
  hier omdat het bestand daarmee afwijkt van wat v0.105 zou hebben
  gemaakt.
- **Nog open uit de Lied D-analyse.** **B343** - woorden van twintig
  milliseconden met een betrouwbaarheid van 0,004 mogen geen zinsbegin
  zijn. Gemeten: van de 270 woorden zijn er elf korter dan 0,06 s, en
  die vallen uiteen in vijf spookwoorden met betrouwbaarheid 0,000-0,006
  en zes gewone korte woordjes met 0,11-0,95. Vier van die vijf werden
  een zinsbegin (ze staan nu eenmaal op de regelovergang) en één kostte
  aantoonbaar een correctie van 2,11 s. **B344** - een gat middenin het
  lied. Een koppelitem van 0,30 s waar dezelfde regel elders 1,81 s
  duurt, waarna de regel tegen zijn voorganger aan wordt geplakt terwijl
  de zang pas 4,1 s later inzet. B330 kan hem niet halen (`_SNAP_MAX_S`
  staat op 1,5 s) en B336 werkt alleen ná het laatste anker. Van de
  vijftig koppelitems waren er twee korter dan 0,6 s en die twee zijn
  allebei met de hand verzet.

In v0.107.0 verwerkt:
- **B348 - de meetlat mat opnieuw het verkeerde, en dat kwam eerst.**
  Bij het meten van B343 gebeurde er niets, en dat bleek te kloppen: het
  gereedschap kopieerde `original/segmenten.json` naar de cachepositie,
  maar dat bestand wordt door `whisper.write_outputs` geschreven vóór de
  forced alignment, terwijl `save_segments` daarná de cache vult. De app
  koppelt op de cache. Ruw tegen uitgelijnd, op Lied D gemeten:
  "Lightning" 10,660 tegen 11,201, "magic" 12,380 (betrouwbaarheid
  0,034, dwars door de pauze heen) tegen 14,905. De ruwe woordtijden van
  Whisper sluiten binnen een segment op elkaar aan; de uitgelijnde hebben
  gaten waar niet gezongen wordt. De meting nam dus de slechtere van de
  twee. Nu wint de cache waar die er nog is, met terugval op de kopie
  waar hij geleegd is en een kolom "bron" die per project zegt welke het
  was. Wat dat alleen al doet: Lied S 4,06 → 0,72 s, fout op ongemoeide
  regels 0,65 → 0,01; Lied D 2,18 → 2,00 met 0,51 → 0,07; Woah-oh
  4,16 → 5,14 op de verzette regels maar 0,58 → 0,12 op de rest, en 51 →
  54 gekoppelde zinnen. Zes van de negen projecten staan nog op de ruwe
  kopie omdat hun cache geleegd is; die cijfers zijn te hoog en niet met
  de andere drie te vergelijken. Dit is de derde keer dat de meetlat zelf
  de fout bleek te zijn (na B333 en B338), en het patroon is steeds
  hetzelfde: het gereedschap voerde de code iets anders dan de app doet.
- **B343 - spookwoorden van twintig milliseconden.** Van de 270 woorden
  in Lied D zijn er elf korter dan 0,06 s. Die vallen uiteen in twee
  groepen met een breed gat ertussen: vijf met betrouwbaarheid
  0,000-0,006 ('I', 'I', 'I', 'of', 'I') en zes gewone korte woordjes
  met 0,11-0,95 ('a', 'it', 'of'). Duur alleen zegt dus niets - 'a' van
  0,040 s scoort 0,952 - en betrouwbaarheid alleen ook niet; de twee
  voorwaarden samen scheiden ze wel. Ze doen pijn omdat ze precies op een
  regelovergang liggen, waar de koppeling het eerste woord als zinsbegin
  neemt: vier van die vijf wérden een zinsbegin, en één zette regel 2 op
  16,446 terwijl de zang op 18,556 begint - 2,11 s die de gebruiker met
  de hand moest rechtzetten. Ze verdwijnen in hetzelfde leespad als B334
  en B342. Gemeten op dezelfde invoer: gewogen 3,69 → 3,19 s, Woah-oh
  7,75 → 5,14, Lied D 2,13 → 2,00, en op de ongemoeide regels van
  Lied D 0,04 → 0,07 (verwaarloosbaar).
- **B339 - regelmarkering in de koppel-editor.** Elk woord droeg zijn
  regelnummer al in de weergavedata mee, maar het werd nergens getekend.
  Onder de songtekstrij staat nu bij elke regelovergang een dun streepje
  met het nummer erbij. Aanleiding was de opmerking dat het einde van een
  herhalend lied leest als "een langspeelplaat met een kras": als
  dezelfde vier woorden acht keer onder elkaar staan, is er zonder
  markering niets om je aan vast te houden.
- **B340 - opgepropte ankers, met een eerlijke uitkomst.** Een reeks van
  drie of meer ankers die op minder dan een halve frase van elkaar staan
  kan niet in zijn geheel kloppen; alleen de buitenste twee blijven
  anker, de rest wordt een schatting ertussenin. Bewust op een REEKS en
  niet per paar, want de grove variant per paar is tijdens v0.102 al
  geprobeerd en was slechter. En eerlijk over de opbrengst: op de hele
  ijkset komt zo'n reeks één keer voor (Lied S, één anker) en er
  verandert geen enkel cijfer. Wat het meten wél opleverde is een
  ongemakkelijk feit: `phrase_period` geeft bij **zeven van de tien**
  projecten `None`. De hele B332-mechaniek staat dus vaker uit dan aan.
  Dat is geen fout - hij zet zichzelf uit als hij het niet zeker weet -
  maar het zegt wel dat de frase-periode een smallere basis is dan hij
  op papier lijkt, en dat B340 daarmee grotendeels slapende machinerie
  is.
- **B344 is gebouwd, gemeten en weer weggehaald.** Het idee: een regel
  die na de structuur in een gat midden in het lied staat (geen anker,
  geen zang) mag verder reizen dan `_SNAP_MAX_S` en gaat naar de
  eerstvolgende zanginzet. Precies het geval van Lied D regel 43:
  geschat op 154,86, tegen zijn voorganger aan geplakt, terwijl de zang
  pas op 158,96 begint. Gemeten maakte het het gewogen cijfer sléchter:
  3,19 → 3,29 s bij een drempel van 1,5 s stilte en 3,21 s bij 3,0 s.
  Lied S betaalde er een hele seconde voor (0,72 → 1,62) en Lied D
  zelf veranderde niet eens. Dus eruit, net als de "opvul"-tak van B332
  destijds. Het probleem staat er nog: een gat middenin heeft geen enkel
  vangnet, want B336 werkt alleen ná het laatste anker en B330 reikt maar
  1,5 s ver. Een volgende poging moet niet naar de eerstvolgende inzet
  grijpen maar naar de structuur van de zangvensters in dat gat kijken,
  zoals B336 dat in de staart doet.

In v0.108.0 verwerkt:
- **B351 - het begin achter een pauze.** Aanleiding: de gebruiker moest
  bij een nieuw project veel regels naar voren bijstellen, en merkte op
  dat het vooral ging om regels waar even niets vóór zit. Nagemeten op
  "Lied C": van de 48 regels heeft hij er zeven meer
  dan 0,3 s verzet, **alle zeven naar voren en alle zeven achter een
  pauze**, terwijl hij van de 23 regels die direct op hun voorganger
  aansluiten er geen enkele heeft aangeraakt. Gemiddelde fout achter een
  pauze 0,29 s, bij een aansluitende regel 0,04 s - een factor zeven.
  De oorzaak zit in wat een anker is: het woordbegin uit de forced
  alignment, en dat ligt mediaan 0,19 s ná de inzet van de zangstem,
  terwijl de gebruiker de regel mediaan 0,12 s vóór die inzet zet. B330
  kan er niet bij, want een gemeten regel wordt met opzet nooit
  verplaatst - dat is de regel die voorkomt dat een goede regel wordt
  verpest. Er is nu precies één uitzondering: staat er een pauze van
  minstens een seconde vóór de regel, dan mag het begin terug naar de
  laatste zanginzet in die stilte, maar alleen als het anker daar
  minstens 0,25 s achter ligt. Die drempel ligt in een gemeten gat: de
  regels die de gebruiker liet staan zitten 0,10-0,23 s achter hun inzet,
  de zeven die hij corrigeerde 0,29-2,36 s. Alleen naar achteren, nooit
  verder dan 1,5 s en nooit voorbij het eind van de vorige regel, en het
  eind van de regel blijft staan.
- **B351 - waarom het cijfer over de hele set toch vlak blijft.** Op de
  vier projecten waarvan de cache er nog is (dus waar op de uitgelijnde
  invoer wordt gemeten, zie B348) gaat Biertje van 0,71 naar 0,39 s,
  Lied D van 2,00 naar 1,98 en blijft Lied S op 0,72. Op de zes
  projecten waarvan de cache geleegd is, en die dus op de ruwe
  transcriptie worden gemeten, kost de regel 0,2 tot 0,3 s op regels die
  de gebruiker niet had aangeraakt. Om dat niet te hoeven geloven is er
  een gecontroleerde proef gedaan: hetzelfde lied, dezelfde regel, alleen
  de invoer verschilt. Uitgelijnde cache: 0,39 s op de verzette regels,
  0,08 s op de ongemoeide. Ruwe kopie: 0,39 s op de verzette regels,
  **0,37 s** op de ongemoeide - ruim vier keer zoveel schade. Dat is ook
  logisch: de hele aanleiding van B351 (het anker ligt achter de inzet)
  is een eigenschap van forced alignment, en in de ruwe woordtijden
  sluiten de woorden binnen een segment gewoon op elkaar aan. De regel is
  dus goed en de zes rijen die achteruitgaan meten invoer die de app
  nooit krijgt. Zodra die projecten opnieuw worden getranscribeerd komt
  hun cache terug en klopt hun rij weer.
- **B350 - melden wat er is gehoord maar niet in de tekst staat.**
  Aanleiding was een van internet geplukte songtekst waarin bij
  "shalalie shalala" op drie plekken een herhaling was weggevallen: de
  zang doet het paar twee keer, de tekst had het één keer, en de
  koppeling hing het ene paar aan het tweede gezongen paar - waardoor de
  karaokeregel 1,35 tot 1,49 s te laat in beeld kwam. De tool weet
  allebei de kanten al, dus dat is te melden. De toets: een gevonden
  woord zonder koppeling, niet weggefilterd als hallucinatie, met
  betrouwbaarheid 0,5 of hoger; aaneengesloten woorden tellen als één
  geval. Staat datzelfde woord ter plekke wél in de songtekst (fonetische
  gelijkenis 0,9 of hoger), dan is het een **ontbrekende herhaling** en
  wordt de regel erbij genoemd; anders heet het onbekende tekst. Die
  0,9 is bewust hoog: "Collections" tegen "reflections" scoort 0,80 en
  dat is een verhoring, geen ontbrekende herhaling. Gemeten over vier
  projecten levert het 0 tot 8 meldingen per lied, en op het project
  waarvoor het bedoeld was precies de drie plekken - en nul nadat de
  gebruiker zijn tekst had bijgewerkt. Bewust geen pop-up: het is een
  tip, geen fout, en bij een herhalende outro zijn het er een paar. Eén
  melding per songtekstregel in het berichtenveld, de details in het
  logboek.
- **B349 - het percentage stond er twee keer.** De voortgangsbalk toont
  zelf al "20%" en de tekst ernaast deed het nog eens dunnetjes over
  ("Voortgang: 20% (12 / 60 s)"). De tekst houdt nu alleen de seconden.
  Twee regels in `translations.py`, geen code: de aanroep geeft `pct`
  nog steeds mee en een ongebruikte sleutel in `format()` doet niets.

In v0.109.0 verwerkt:
- **B352 - de meetlat gaf de zangvensters niet door.** Bij het bouwen
  van B344 gebeurde er niets, en de reden bleek weer in het gereedschap
  te zitten: `pipeline.generate_timing` roept `sanitize_timing` aan met
  `active_windows=_vocal_windows(context)`, maar
  `tools/timing_regression.py` liet dat argument weg. Alles wat op die
  vensters leunt werd dus nooit gemeten. Dat verklaart met terugwerkende
  kracht de zin uit v0.104 dat "B334, B336 en B337 geen enkel cijfer
  veranderen": B336 kón niet meebewegen, want de meting gaf hem geen
  vensters. Nu wel doorgegeven. Het gewogen cijfer blijft 3,11 s; alleen
  Lied B gaat op de ongemoeide regels van 1,24 naar
  1,27 s. Vierde keer dat de meetlat zelf de fout was (na B333, B338 en
  B348), en steeds met hetzelfde patroon: het gereedschap voerde de code
  net iets anders dan de app doet. Er staat nu een test op die eist dat
  de aanroep in het gereedschap `active_windows` bevat.
- **B344 voor de tweede keer gebouwd, gemeten en weer weggehaald.** De
  eerste poging (v0.107) greep naar de eerstvolgende zanginzet en was
  meetbaar slechter. Deze poging volgde het recept van B336: een gat
  tussen twee ankers wordt gevuld met de zangvensters die er helemaal
  tussen liggen, elk venster draagt zoveel regels als het frases lang
  is, en het gebeurt alleen als die vensters exact het benodigde aantal
  regels dragen - "liever niets dan een zelfverzekerde fout". Uitkomst
  van de meting: over tien liedjes zijn er 32 ankerparen met geschatte
  regels ertussen, en de regel vuurt **één keer** (Lied B
  ), met een uitkomst die 0,03 s slechter is. Ook met een
  soepeler periode-schatting (de mediane ankerafstand in plaats van
  `phrase_period`, die bij zeven van de tien projecten niets teruggeeft)
  veranderde er niets.
- **Wat de meting daarbij blootlegde, en dat is de echte opbrengst.**
  Van de tien liedjes bereikt er precies één de staartregel van B336
  (Lied S), en ook die plaatst niets. B336 vuurt dus op de hele ijkset
  **nul keer**. De vensteraanpak - de heeltallig-aantal-frases-toets - is
  te streng om in de praktijk in werking te treden, en tegelijk zijn
  gaten tussen ankers veel zeldzamer dan het probleem bij Lied D deed
  vermoeden: 32 op ruim 400 ankerparen. Wie hier verder aan werkt kan
  daar beter beginnen dan bij een nieuwe verdeelregel: eerst meten of
  het geval waarvoor je bouwt in de ijkset überhaupt voorkomt. Het geval
  dat B344 aanleiding gaf (Lied D regel 43) levert noch een
  betrouwbare frase-periode noch vensters die passen, dus geen van beide
  varianten kan het ooit raken.

In v0.110.0 verwerkt:
- **B353 - de video blijft.** De gemaakte video werd ongeldig verklaard
  zodra er bovenstrooms iets veranderde. Het mp4-bestand werd overigens
  nooit verwijderd: `video` staat in de keten als STAP en niet als
  BESTAND, en alleen bestands-items gaan van schijf. Wat wel verdween was
  de administratie - welk bestand het was en met welke audiobron - en
  daardoor was de app na een herstart vergeten dat er een video was.
  `video` hangt nu bewust nergens meer onder, in hetzelfde gezelschap als
  `display_name`, `input_names` en `video_titles`. Er staat een
  guard-test op die eist dat een afgeleide zonder bron een expliciete
  uitzondering is (B311-familie); die lijst is bijgewerkt, want dat is
  precies de plek waar zo'n besluit hoort te staan. Gevolg dat je moet
  weten: de knop "Open video" kan nu naar een verouderde render wijzen
  als je daarna de timing verandert. Dat is de bedoelde ruil - verouderd
  is iets anders dan ongeldig, en dat oordeel is aan de gebruiker.
- **B354 - vragen in plaats van overschrijven.** De bestandsnaam is
  `<titel>.mp4`, met sinds B271 een achtervoegsel voor een afwijkende
  combinatie van muziek en tekst. Bij dezelfde combinatie schreef de
  render er zonder vragen overheen. Nu wordt vooraf gekeken of het
  bestand er al is, met drie antwoorden: overschrijven, naast elkaar
  bewaren of annuleren. Bij "naast elkaar bewaren" krijgt de NIEUWE
  render het volgnummer (`<naam>_2.mp4`, daarna `_3`), op verzoek van de
  gebruiker - zo wordt er aan een bestaand bestand nooit iets gedaan.
  Technisch is de naamgeving uit `run_video` gelicht naar
  `video_target`, zodat de GUI hem kan uitrekenen vóórdat het renderen
  begint, en `run_video` accepteert nu een doelpad van de aanroeper.
- **1.5. Cache vullen (tijdelijk).** Vijf projecten hebben handmatige
  timing maar geen transcriptiecache meer, en daardoor meet het
  gereedschap bij die projecten op de ruwe transcriptie van vóór de
  forced alignment (B348) - wat de app nooit te zien krijgt. Opnieuw
  "1.1. Detecteer woorden" draaien lost dat op maar vernietigt de reden
  dat die projecten waardevol zijn: de opruimketen haalt `word_coupling`,
  `coupling`, `lyrics`, `karaoke` en `timing` weg, inclusief het bestand
  `settings/timing.json`. Deze knop loopt daarom precies het pad van
  `detect_track` tot en met `save_segments` en stopt daar: geen
  `set_step`, geen `invalidate`, en de diagnostiekbestanden gaan naar een
  tijdelijke map zodat ook `original/segmenten.json` onaangeroerd blijft.
  Hij zoekt zelf de projecten op die ooit getranscribeerd zijn, geen
  cache meer hebben en hun audio nog hebben, toont die lijst en vraagt
  bevestiging. Een test eist dat er in die functie geen `set_step` of
  `invalidate` voorkomt - dat is de hele afspraak. Mag eruit zodra de
  ijkset weer compleet is.

In v0.110.1 verwerkt:
- **1.5 struikelde meteen.** Gemeld door de gebruiker: `Transcriptie
  mislukt: 'Event' object is not callable`. De oorzaak stond in het
  logbestand: `whisper.transcribe` wil bij `cancelled` een *functie* die
  `True` teruggeeft als er gestopt moet worden, en de nieuwe knop gaf het
  `threading.Event` zelf mee. De bestaande detectieknop doet het goed
  (`cancelled=cancel.is_set`), dus dit was puur een afwijking in nieuwe
  code. Er staan nu twee tests op: een functionele die controleert dat
  wat er doorgegeven wordt aanroepbaar is, en een die de aanroep in de
  knop zelf vastlegt - die tweede is degene die het echt zou hebben
  gevangen, want de fout zat niet in de pijplijnfunctie maar in de
  aanroeper.
- **Twee tegelijk.** Op verzoek van de gebruiker draaien er nu twee
  projecten naast elkaar, in dezelfde vorm als de parallelle detectie van
  B90: gewone threads over de gedeelde modelcache van `whisper.py`. Twee
  bijvangsten die het net zo goed waard zijn: een project dat struikelt
  breekt de hele reeks niet meer af maar wordt aan het eind apart
  genoemd, en de projecten met een handmatig gecorrigeerde `timing.json`
  staan vooraan in de rij - stop je halverwege, dan zijn precies de
  projecten klaar die de meting waarde geven.

In v0.111.0 verwerkt:
- **Knop 1.5 is een paneel geworden.** De losse knop "Cache vullen" is
  actie 1.5.1 in een aanvinklijst van tien genummerde testfuncties, zodat
  er in het gesprek naar verwezen kan worden ("draai 1.5.3 even"). De
  nummers horen bij de actie en verschuiven niet als er iets tussenuit
  gaat. Drie afspraken die voor alle tien gelden en waar tests op staan:
  de vinkjes staan bij het openen ALTIJD uit (een vergeten vinkje op de
  weglaatproef kost een half uur), elke actie kijkt in zijn lus naar
  `cancelled()` zodat de Stop-knop werkt, en een actie die struikelt
  stopt de rest niet. Het paneel schrijft niets naar de projecten, met
  twee uitzonderingen die dat in hun eigen omschrijving zeggen.
- **Alles staat als tijdelijk gemarkeerd, en dat wordt bewaakt.** Nieuwe
  paragraaf "Voor publicatie beslissen" in dit document, met per
  onderdeel wat het is, waarom het er is en welke vraag er bij een
  publicatie gesteld moet worden. Een test zoekt in `modules/` en
  `tools/` naar bestanden met een `TIJDELIJK`-markering en eist dat elk
  daarvan in die paragraaf genoemd wordt. Aanleiding: B136 was ook zo'n
  tijdelijke knop (v0.65, eruit in v0.78) en dat die er weer uit ging was
  meer geluk dan wijsheid - hij stond nergens als openstaand besluit.
- **De volgordevraag is beantwoord: nee.** Alle zes de volgordes van de
  drie leespadfilters geven exact 3,37 s - niet bij benadering, tot op
  twee decimalen gelijk. De weglaatproef legt uit waarom: van de negen
  controles dragen er maar twee meetbaar bij (spookwoorden +0,47 s als je
  ze weghaalt, de ankertoets +0,26), snappen en energieplaatsing samen
  +0,14, en B334, B342 en B336 leveren **nul** op. Als er maar één
  leespadfilter iets doet, kan hun onderlinge volgorde per definitie niets
  uitmaken. Combineren heeft ook geen zin: spookwoorden en ankertoets
  samen weglaten kost +0,75 tegen +0,47 en +0,26 los, dus ze tellen op en
  zitten elkaar niet in de weg.
- **Wat een score zou opleveren, en waarom nu niet.** Alles uitzetten wat
  iets doet kost +2,33 s, maar niet gelijkmatig: Lied S gaat van 0,72
  naar 20,55 (de mechaniek houdt dat lied overeind) terwijl Lied
  P juist verbetert van 4,11 naar 2,94 en Lied T van
  7,13 naar 6,44. Dezelfde controles zijn dus twintig seconden waard op
  het ene lied en kosten een seconde op het andere; een ja/nee-filter kan
  dat verschil niet uitdrukken en een gewicht wel. Dat is het enige
  argument voor een scoremodel - maar het gaat om ruim een seconde op twee
  liedjes, terwijl 89% van de fout in vier liedjes zit met hun eigen
  aanwijsbare problemen. Dus niet nu.
- **De echte vondst: herhaalde regels.** Bij Lied N staan regels 20
  t/m 22 exact goed en zijn regels 23 t/m 26 - dezelfde vier teksten nog
  een keer - +2,16, +3,09, +3,62 en +6,68 fout, oplopend. Allemaal op
  kwaliteit `high`: de koppeling wist het zeker en hing de herhaling aan
  de audio van de vorige keer. Over alle elf projecten gesplitst: **0,48 s
  op unieke regels tegen 1,89 s op herhaalde**, en bij Lied N 0,63
  tegen 4,86 en bij Lied P 0,56 tegen 4,17. Die twee dragen samen
  de helft van alle fout. Dit is B148, sinds v0.58 open als bijzin
  ("koppeling kiest bij veel herhalingen soms de verkeerde bron-plek") en
  nu meetbaar de grootste post die er ligt. Het is geen timingprobleem -
  geen enkele regel in `sanitize_timing` kan een zin rechtzetten die aan
  de verkeerde plek in de audio hangt - dus het volgende werk hoort in de
  zinkoppeling, met een eigen ontwerpronde. Actie 1.5.8 houdt dat cijfer
  voortaan bij.
- **B355**: de kop "Lied-project" droeg de uitleg "(projectnaam =
  songtitel; elk een eigen project)" mee. Weg; de handleiding legt het al
  uit.

In v0.112.0 verwerkt:
- **B356 - Stop stopt nu echt.** De gebruiker drukte op Stop en er
  gebeurde minutenlang niets. Twee oorzaken. De eerste: `measure()`
  kijkt nergens naar het afbreeksignaal, dus een lopend project moest
  helemaal af. De tweede en vervelendste: een extern programma luistert
  sowieso nergens naar. `subprocess.run` wacht tot het klaar is, dus een
  Demucs-scheiding van drie minuten maakte die drie minuten af, hoe hard
  je ook drukte. Alles loopt nu door één deur, `proc.run`, die het proces
  registreert zolang het draait; `proc.terminate_all()` schiet ze af.
  De Stop-knop doet eerst het beleefde verzoek en zet vijf seconden later
  `_stop_hard()` in, die alleen afschiet als de taak dan nog loopt - een
  net afgeronde afbreking mag de programma's van een VOLGENDE draai niet
  omleggen. De videorender kan niet door die deur (die pompt zelf beelden
  in de stdin van ffmpeg) en meldt zich daarom apart aan.
- **B356 - en daarmee ook de cmd-vensters.** Bij het testen knipperden er
  vensters over het scherm. Alle subprocessen van de app zelf waren al in
  orde sinds B89; de uitzondering was `_vocals_into_cache` in de meetlat,
  die `ffmpeg` kaal aanriep. Dat viel nooit op omdat het een
  opdrachtregelgereedschap was, maar sinds 1.5.7 draait het vanuit de
  GUI: één venster per project, dus elf bij de meetlat en achtentachtig
  bij de weglaatproef. Bijkomend probleem van diezelfde regel: hij zocht
  `ffmpeg` alleen in PATH terwijl de app ook naar zijn eigen map en de
  instelling kijkt, dus op een andere installatie deed 1.5.7 het gewoon
  niet. Nu via `ffmpeg.resample_to_match`. Een test zoekt `modules/` en
  `tools/` af op `subprocess.run`/`Popen` buiten `proc.py` om en wordt
  rood zodra er weer een kale aanroep bijkomt.
- **B357 - het testpaneel gebruikt beide lijnen.** Twee klachten die
  dezelfde oorzaak hadden: de balken bleven op "1.5.1" en "1.5.2" staan
  terwijl die stappen allang voorbij waren, en alleen 1.5.1 verdeelde
  zijn werk over twee werkplekken. De balken werden namelijk eenmalig
  gezet en daarna nooit meer aangeraakt; de voortgang ging naar het
  berichtenveld. Nu is er een gedeelde verdeler `over_projecten()` die
  elke per-projectactie over twee werkplekken uitzet. Elke werkplek meldt
  via een signaal (uit een werkthread mag je geen Qt-widget aanraken) op
  welk project hij zit; het paneel zet dat als etiket boven zijn eigen
  balk en laat de balk oplopen van nul tot het aantal projecten. Drie
  dingen komen daar gratis bij: het afbreken wordt tussen elk project
  gecontroleerd, een project dat struikelt stopt de rest niet meer maar
  levert een regel in de uitslag, en de uitslag komt in projectvolgorde
  terug ook al lopen de werkplekken door elkaar.

In v0.113.0 verwerkt:
- **B358 - de grote proef (1.5.11).** De weglaatproef van v0.111.0 gaf
  antwoord op één vraag ("wat kost het als deze controle uit gaat?") en
  liet drie andere liggen: waar komt een model tot zijn recht, werken
  twee modellen op dezelfde regels, en doet de volgorde ertoe? Actie
  1.5.11 doet ze alle vier in één nachtelijke draai en schrijft
  `docs/modelmatrix.md`. Zeven secties: het uitgangspunt met de fout per
  project, elk model apart uit, per model het project waar uitzetten het
  meeste kost én waar het schaadt, de paren, de volgordes, de dekking van
  de woordkoppeling en het woordniveau. Na **elke** variant wordt het
  verslag weggeschreven - een vastloper om drie uur 's nachts mag niet de
  hele nacht weggooien - en tussen elke variant wordt de Stop-knop
  gecontroleerd.
- **B358 - de woordkoppeling telt mee.** Tot nu toe ging elke meting over
  de tijden, terwijl de grootste openstaande post (B148) in de
  *koppeling* zit. De koppeling is daarom een eigen niveau in de matrix
  geworden, naast blok en zin: de twee hallucinatierondes (B258/B285 en
  B307/B337), de aparte vulwoordronde (B213) met zijn voorrangsregels
  (B276), het losmaken van een zwakke staart (B159), de handkoppelingen
  (B121) en de energieplaatsing (B313) - die laatste stond eerst onder
  "zin" en staat nu op zijn eigen plek, want twee keer meten geeft twee
  waarheden.
- **B358 - dekking in plaats van fout.** Twee koppelaars draaien alléén
  in het koppelvenster en niet in de tijden: B191 (een gehakt woord weer
  aan elkaar) en B228 (de creatieve 2-op-1). De meetlat ziet die per
  definitie niet, dus ze zouden een tabel vol nullen geven. Ze krijgen
  daarom een eigen maat: hoeveel tekstwoorden houden een koppeling over,
  hoeveel daarvan meervoudig, wat is de mediane gelijkenis, en wat blijft
  er liggen (energiegeplaatst, gat in de transcriptie, weggefilterd,
  vulwoord, geen match). Meer dekking bij gelijke gelijkenis is winst;
  meer dekking bij een lagere gelijkenis is een model dat gokt.
- **B358 - twee volgordes die iets kunnen uitmaken.** Voor het leespad
  was al gemeten dat de volgorde niets doet (alle zes permutaties exact
  gelijk); voor de koppeling was dat nooit gekeken. De proef draait nu
  ook "B307 vóór B285" (eerst de plaatsbewuste hallucinatieronde, dan de
  liedbrede) en "B313 vóór B121" (eerst een tijd van de zangstem, dan de
  handkoppelingen eroverheen). Nul verschil betekent dat de code op dat
  punt vrij is; dat is ook een uitkomst.
- **B358 - de nacht moet wel af komen.** Alle paren van zeventien
  modellen is honderdzesendertig keer de hele ijkset, en de weglaatproef
  liet zien dat de helft in zijn eentje exact 0,00 geeft. Alleen modellen
  die alléén al minstens 0,02 s verschil maakten gaan het paarwerk in, en
  wélke er zijn overgeslagen staat in het verslag zelf - een stilzwijgend
  ingekorte tabel leest als "alles gemeten" terwijl dat niet zo is.
- **B358 - bewaking op de vervangers.** De proef werkt door echte
  functies tijdelijk te overschrijven, en dat gaat stil mis zodra iemand
  er een argument bij zet of een functie hernoemt: de fout valt dan pas
  een uur later, midden in de nacht. Drie tests vangen dat af: elk doel
  moet nog bestaan, elke vervanger moet de verplichte argumenten van het
  origineel aankunnen, en elke vervanger moet ook de keuze-argumenten
  slikken. Een vierde test klapt de proef expres halverwege en eist dat
  alle echte functies daarna weer op hun plek staan - blijft er een
  vervanger hangen, dan draait niet alleen de volgende meting maar ook
  het programma zelf op nep.

In v0.114.0 verwerkt:
- **B359 - de GUI kon stil doodgaan.** De gebruiker startte 1.5.9, er
  gebeurde niets meer, en er was geen CPU-activiteit. Het logboek
  eindigde met "GUI: 1.5.9 draait: Whisper-venstertest" en daarna niets:
  geen fout, geen volgende actie, geen afronding. Dat is de vervelendste
  soort storing, want er is niets te zien - juist die stilte was het
  spoor. De keten: `whisper_probe.zangstem()` meldde een ontbrekende
  zangstem met `SystemExit`, wat voor een opdrachtregelprogramma precies
  goed is maar niet voor een functie die de app aanroept. `SystemExit`
  erft van `BaseException` en niet van `Exception`, dus hij glipte door
  alle drie de vangnetten die `except Exception` zeggen: de actie zelf,
  de lus over de acties in `_do_fill_cache`, en `_Worker.run`. Die
  laatste is de fatale. Als `run()` op een `BaseException` klapt wordt
  géén van de drie signalen (`done`, `failed`, `cancelled`) verstuurd,
  en juist die zetten `_set_busy(False)`. Het venster bleef dus voorgoed
  op "bezig" staan terwijl er letterlijk niets meer draaide - vandaar
  nul CPU. Ook Stop hielp niet: de harde stop uit B356 kijkt of de taak
  nog loopt, en dat deed hij niet meer. Het programma moest dicht, en
  1.5.10 en 1.5.11 zijn nooit gestart.
- **B359 - de reparatie op drie plekken.** Het laatste vangnet in
  `_Worker.run` is nu `BaseException`: liever een lelijke melding dan
  een dood venster, ongeacht welke actie de fout veroorzaakt. Dit is de
  belangrijkste van de drie, want hij dekt ook alles wat er later nog
  bij komt. `zangstem()` gooit voortaan een gewone `FileNotFoundError`
  en `main()` vertaalt die naar een afsluitcode - het onderscheid tussen
  "bibliotheekfunctie" en "opdrachtregelprogramma" hoort in `main()` te
  zitten en nergens anders. En 1.5.9 kijkt vooraf of er überhaupt een
  project gekozen is. Een guard-test loopt `modules/` en `tools/` met de
  AST af en wordt rood zodra er buiten een `main()` weer een
  `SystemExit` bijkomt.
- **B359 - waarom juist nu.** Na de herstart stond het huidige project
  in `config/config.json` leeg. 1.5.9 is de enige van de elf acties die
  op het HUIDIGE project werkt in plaats van op alle projecten, dus hij
  was ook de enige die hierop kon struikelen: met een lege titel werd de
  zoekplek `cache\` in plaats van `cache\<lied>\`, en daar staat geen
  `vocals.wav`. Alle andere tien acties lopen over de projectenlijst en
  merkten er niets van.
- **B359 - de keuzerondjes deden niets.** Bij het uitzoeken bleek dat de
  twee rondjes onderin het testpaneel ("Alleen dit project" / "Alle
  projecten") nergens werden gelezen; hetzelfde gold voor het vlaggetje
  `alle_projecten` per actie. Elke actie kreeg gewoon de huidige context
  en liep over alle projecten. Ze werken nu: de loper zet de reikwijdte
  bij elke draai opnieuw (zodat een keuze van vorige keer nooit blijft
  hangen) en `_projecten()` levert dan alleen het gekozen project. Staat
  er geen project gekozen, dan komt er een nette melding in plaats van
  een lege ronde.
- **B359 - het etiket bleef staan.** Een actie die zelf geen voortgang
  meldt (1.5.9 heeft geen rij projecten om af te lopen) liet de naam van
  de vorige actie boven de balk staan. Dat leest als vastlopen, en in
  dit geval wás het dat ook - maar het mag niet zo zijn dat je aan het
  beeld niet kunt zien wat er aan de hand is. De loper verzet nu het
  etiket van beide balken zodra een actie begint.

In v0.115.0 verwerkt:
- **B360 - 1.5.10 struikelde over de melder.** In B357 kreeg de melder
  een andere vorm: van `melden(naam)` naar `melden(plek, naam, klaar,
  totaal)`, omdat elke werkplek zijn eigen balk kreeg. Alle acties
  gingen mee, behalve `weglaatproef`, die op één plek de oude vorm hield
  en dus meteen op zijn eerste variant omviel met een `TypeError`. De
  variantnaam gaat nu naar de eerste balk; de meetlat eronder verdeelt
  zijn projecten zelf al over beide werkplekken.
- **B360 - waarom 827 tests dit niet zagen.** Dat is de eigenlijke les,
  en die is groter dan de fout. Twee dingen wezen nog naar het oude
  contract. De typeaanduiding bovenin `test_panel.py` stond nog op
  `Callable[[str], None]` - de vorm van vóór B357 - waardoor élke actie
  in dat bestand met het VERKEERDE contract geannoteerd was. Een
  typeaanduiding die niet klopt is erger dan geen: hij wijst de volgende
  lezer actief de verkeerde kant op. En de tests riepen de acties aan
  met `lambda _t: None`, een melder met één argument. De test bevestigde
  dus het oude contract in plaats van het echte en kón deze fout niet
  vinden. Daar kwam bij dat `test_rapporten_draaien_op_een_leeg_project`
  alleen 1.5.2 t/m 1.5.5 aflooopt, en juist die vier roepen de melder
  nooit aan.
- **B360 - drie bewakingen in plaats van één reparatie.** Er staat nu
  één melder in de tests met exact de vorm van de loper, bewust zónder
  `*args` - een melder die alles slikt zou deze bug juist verbergen. Een
  test leest met de AST de melder uit `_do_fill_cache` en legt zijn
  argumentnamen vast aan die van de test, zodat een volgende
  vormverandering de tests laat omvallen in plaats van één vergeten
  actie in beeld. Een tweede loopt `test_panel.py` en `gui.py` af en
  wordt rood zodra `melden()` ergens met minder dan twee argumenten
  wordt aangeroepen. En een derde draait alle ELF acties met die echte
  melder, in plaats van de vier die toevallig nooit iets melden.
- **B360 - "liep vast" betekende iets anders geworden.** Sinds B359 is
  vastlopen een andere storing: een dood venster zonder melding. 1.5.10
  hing niet, hij viel om na achtentwintig milliseconden. De meldingen
  spreken nu van "gestruikeld", zodat de tekst bij het zoeken de goede
  kant op wijst.
- **B360 - de tijdsindicaties klopten niet.** Gemeten op de ijkset doet
  de volledige meetlat over elf projecten er 8,5 seconden over, en 1.5.1
  t/m 1.5.9 samen 41 seconden. De weglaatproef stond op "reken op een
  half uur" en is in werkelijkheid een paar minuten; de grote proef
  stond op "een nachtklus van uren" en is eerder een half uur. Ter
  controle nagegaan of er soms werk werd overgeslagen: dat gebeurt niet.
  Geen enkele actie leest een eerdere uitslag terug, `measure()` maakt
  per project per draai een verse tijdelijke map, en de energiecache in
  `rhythm` hangt aan pad + wijzigingstijd + grootte, dus een gewijzigd
  bestand is altijd een andere sleutel. Alleen 1.5.1 slaat over, en dat
  is zijn opdracht.

In v0.116.0 verwerkt:
- **B361 - het modellenregister.** Twintig ideeën die in de loop van
  honderd versies in de timing en de koppeling zijn gebouwd, stonden
  nergens bij elkaar; wat er van elk bekend was zat in tijdelijke
  testcode. Dat is nu `modules/model_register.py`: per model een
  B-nummer, een naam, een niveau, een neutrale vervanger en een STAND.
  De regel van de gebruiker is daarmee uitvoerbaar geworden - een model
  dat niets waard blijkt gaat **uit en niet weg**, want het idee erachter
  is meestal ergens goed voor. Uitzetten gebeurt centraal met dezelfde
  vervangtabel die de weglaatproef sinds v0.111.0 gebruikt, één keer bij
  het opstarten, en elk uitgezet model logt zichzelf met naam en reden.
  De alternatieve vorm - een `if` op elke aanroepplek - zou twintig
  plekken in vijf modules betekenen, elk met een eigen idee van wat
  "neutraal" is; één tabel die de app én de meting lezen kan niet uit de
  pas lopen, en juist dat uit de pas lopen was B360.
- **B361 - en de matrix werd symmetrisch.** De proef leest datzelfde
  register. Voor een model dat AAN staat meet hij wat uitzetten kost, en
  voor een model dat UIT staat wat aanzetten zou opleveren. Een uitgezet
  idee blijft dus elke draai meelopen en meldt zichzelf zodra het op
  nieuwe liedjes wél wat waard is. De stand gaat ook mee in de
  afleidingsketen (B311) en in de instellingen: een ander model betekent
  een andere timing, en dan horen de afgeleiden te vervallen.
- **B361 - B213 gaat als eerste uit.** De grote proef wees hem aan als
  het enige model dat op de ijkset aantoonbaar SCHAADT: -0,13 s in zijn
  eentje, en samen met B343 uit zelfs 0,23 s onder het uitgangspunt. Alle
  vijf combinaties die beter scoorden dan het uitgangspunt bevatten hem.
  De acht modellen die 0,00 geven blijven bewust aan: het paarwerk liet
  zien dat de ankertoets en de energieplaatsing samen uit 5,66 s geven
  waar 3,66 verwacht werd, dus een model dat in zijn eentje niets doet
  kan een vangnet zijn dat op deze elf liedjes nooit hoefde te vangen.
- **B362 - de meethistorie.** Per actie, project en versie wordt bewaard
  wat er gemeten is, in `docs/testhistorie.json`. Daarmee kan een project
  dat sinds de vorige draai niet veranderd is worden overgeslagen, en zet
  een nieuwe versie zijn cijfers naast die van de vorige drie, zodat een
  terugval in het rapport zelf zichtbaar wordt in plaats van in iemands
  geheugen. De sleutel is bewust méér dan de versie: een versie zegt iets
  over de CODE en niet over de GEGEVENS, dus elke ingang draagt ook een
  vingerafdruk van de projectbestanden, de transcriptiecache én de
  uitgezette modellen. Verandert er iets aan de gegevens of aan een
  model, dan wordt er vanzelf opnieuw gemeten. Een vinkje "opnieuw meten"
  bovenin het paneel negeert het geheugen als je het toch wilt forceren.
- **B363 - woord- en lettergreeptoetsen.** Op lettergreepniveau bestaat
  geen handmatige waarheid: het verslepen van een regel schaalt de
  lettergrepen lineair mee, dus die tijden zijn een GEVOLG van het model
  en geen oordeel erover. Er is toch wat te meten, en het scherpste lag
  al maanden ongebruikt: de forced alignment zet per woord een begin en
  eind op de zangstem, los van het lettergreepmodel, en die tijden staan
  gewoon in de transcriptiecache. Een lettergreep die over zo'n GEMETEN
  woordgrens heen ligt is aantoonbaar mis. Daarnaast toetsen op de vorm
  (volgorde, overlap, gaten binnen een woord, een lettergreep van acht
  milliseconden, meer dan negen lettergrepen per seconde, een aangehouden
  lettergreep die niet de laatste is), op de audio (zonder duur, in een
  gemeten stilte, afstand tot de inzet) en op zichzelf: een regel die
  twee keer gezongen wordt hoort intern hetzelfde ritme te hebben, en dat
  vergt helemaal geen waarheid. Alle vier meten overeenstemming en geen
  juistheid; om ze af te regelen is een klein stukje handwerk nodig, en
  daarvoor moet de timing-editor eerst een handvat op een losse
  lettergreep krijgen. Dat staat als openstaand punt.
- **B364 - sneller, zonder meer werkers.** De processor werd niet vol
  belast, en dat kwam niet door het aantal lijnen. `measure()` maakte per
  aanroep een verse tijdelijke map en zette de zangstem daar opnieuw in,
  dus ffmpeg draaide voor elk project bij elke variant - bij de grote
  proef zo'n honderdnegentig keer hetzelfde werk, en dat is wachttijd.
  De omgezette zangstem wordt nu één keer per project bewaard en daarna
  gekopieerd met `copy2`, zodat ook de energiecache in `rhythm` niet
  telkens op een nieuwe sleutel uitkomt. Verder werd de meetlat per
  variant opnieuw ingelezen en uitgevoerd; dat gebeurt nu één keer. En de
  twee laatste secties van de proef (koppeldekking en woordniveau)
  liepen met een gewone lus over de projecten en gebruikten dus maar één
  werkplek - die gaan nu door dezelfde verdeler als de rest. Het aantal
  werkers blijft op twee, op verzoek.
- **B365 - maximaal tien acties onder 1.5.** Een lijst die alleen maar
  aangroeit wordt onleesbaar, dus er staat nu een plafond op tien en
  kleine tests worden samengevoegd. De teksten-, filter- en
  structuurrapporten waren drie losse acties die alle drie een regel per
  project uit dezelfde bestanden halen en samen geen minuut duren; die
  zijn nu één actie "Projectcontrole". Dat maakte plaats voor de nieuwe
  woord- en lettergreeptoetsen. Gevolg: de nummering is opnieuw gelegd,
  en "draai 1.5.7" betekent iets anders dan vorige week. De meetlat is
  1.5.5, de weglaatproef 1.5.9 en de grote proef 1.5.10.
- **B366 - alle paren, zonder drempel.** In v0.115.0 gingen alleen
  modellen mee die in hun eentje minstens 0,02 s verschil maakten. Die
  snoei was fout, en de tabel die eronder stond bewees het zelf: de
  ankertoets en de energieplaatsing samen uit gaven 5,66 s waar los
  opgeteld 3,66 verwacht werd. Juist een model dat alleen niets doet kan
  een vangnet zijn, en dat zie je alleen in combinatie. Met de meetlat op
  ruim acht seconden kost alles meten een half uur, en dat is het waard.
- **B366 - en de gelijkenis-kolom werkt weer.** Die stond in de
  dekkingstabel overal op 1,00: de mediaan was verzadigd en dus blind
  voor precies de vraag waarvoor de kolom bedoeld was - koppelt een model
  méér maar slechter? Er staat nu het AANTAL en het AANDEEL koppelingen
  onder gelijkenis 0,75, plus de laagste. Meer dekking bij een gelijk
  aandeel zwak is winst; meer dekking met meer zwak is een model dat
  gokt.
- **B367 - de knop 'alle'.** Bovenin het paneel, en hij klapt om: alles
  aan, nog eens klikken is alles uit, met een opschrift dat meebeweegt.
  De regel dat er bij het OPENEN altijd niets aanstaat blijft - dit is
  een bewuste klik en geen toestand die blijft hangen.

In v0.117.0 verwerkt:
- **B368 - de secondeteller bleef steken.** De gebruiker zag "1.5.10
  draait... 361 s" staan terwijl de proef nog een half uur door zou gaan.
  De teller ververst alleen zolang er geen echt percentage te tonen is,
  en dat leidde hij af uit `self._progress.maximum() == 0`. Alleen: die
  balk IS `self._progress_bars[0]`, de eerste testbalk. Zodra de meetlat
  per project meldde zette dat `setRange(0, 13)` op precies dat widget en
  viel de teller stil; tussen de varianten door ging hij kort terug naar
  nul, dus af en toe sprong hij nog bij tot een tik niet meer in dat
  venster viel. Vandaar een getal dat eerst leek te lopen en toen niet
  meer. De teller houdt nu een eigen toestand bij in plaats van hem af te
  leiden uit een widget dat sinds B357 van iemand anders is. Er staat een
  test op die vastlegt dat die gedeelde balk nog steeds gedeeld is - gaat
  dat ooit uit elkaar, dan mag die test omvallen en kan de eigen toestand
  weer weg.
- **B369 - de uitslag komt meteen in beeld.** De loper verzamelde alle
  uitslagen en logde ze pas als de héle reeks klaar was. Bij losse tests
  valt dat niet op, maar met 1.5.10 van achtentwintig minuten aan het
  staartje zat de gebruiker een half uur te wachten op cijfers die allang
  klaar waren - en bij een crash was alles weg. Nu schrijft elke actie
  zijn uitslag weg zodra hij af is, en wel twee kanten op: rechtstreeks
  naar het LOGBESTAND vanuit de werkthread (dat is het deel dat een crash
  overleeft, want een signaal naar het venster staat dan nog in de
  wachtrij van de GUI-thread), en via een eigen signaal naar het
  logvenster. `_log` is daarvoor gesplitst, anders stond elke regel
  dubbel in het bestand.
- **B370 - de duur in de meethistorie.** Per project bij de uitslag die
  er toch al bewaard wordt, en daarnaast één regel per actie per versie
  voor de totale duur. Zonder dat is een draai binnen een week weg, want
  er worden maar vijf logbestanden bewaard. Bewust GEEN melding in het
  programma zelf: het getal wordt bewaard, de vraag of iets naar 1.5.11
  moet stel ik als ik naar de data kijk. De eerste zeven getallen staan
  er meteen in, uit het logboek van v0.116.0 - waarvan 1.5.10 op 1673 s
  (achtentwintig minuten, net binnen de norm) en de weglaatproef op 134 s.
- **B371 - 1.5.11, de zware bak.** Het plafond van tien blijft gelden
  voor het gewone werk; alles wat langer dan een half uur duurt gaat
  hierheen. Hij doet NOOIT mee met "Alles aanvinken" - uren rekenen hoort
  een bewuste keuze te zijn, ook als je "alles" bedoelt - en hij
  verdwijnt volledig uit de lijst als er geen onderzoek onder staat: geen
  lege regel, geen uitgegrijsde knop. Elk onderzoek heeft een eigen
  versiedrempel (standaard twintig) en slaat zichzelf over tot die
  gehaald is; het vinkje "Opnieuw meten" dwingt hem toch af. Voor die
  drempel telt het middelste versienummer, zodat een reparatierelease als
  0.110.1 niet meetelt als een eigen versie.
- **B371 - clusters in plaats van uitputten.** De gebruiker rekende voor
  dat zeventien modellen 2^17 = 131.072 combinaties geven; bij elf
  seconden per meting is dat ruim vierhonderd uur. Dat hoeft niet, want
  de meeste modellen raken elkaar niet. Van de honderdzesendertig paren
  in de matrix tonen er negen een echte wisselwerking, en die vallen
  uiteen in twee clusters: zes modellen rond de ankers en de
  hallucinatiefilter, plus het paar B343/B213. Negen van de zeventien
  raken niemand. Binnen elk cluster worden ALLE combinaties gemeten - 2^6
  + 2^2 = 68 metingen, ongeveer twaalf minuten, met precies dezelfde
  kennis. De clusters komen uit het verslag van 1.5.10 en worden niet
  opnieuw gemeten; ontbreekt dat verslag, dan zegt de proef dat 1.5.10
  eerst moet draaien in plaats van op één groot cluster te gokken.
- **B371 - zoeken in plaats van inventariseren.** Wie de beste stand wil
  weten hoeft de kaart niet compleet te maken. Vanaf de huidige stand
  steeds de omzetting nemen die het meest oplevert, tot niets meer helpt;
  dat is ongeveer 153 metingen tot een lokaal optimum, en een paar
  herstarts vanaf een willekeurige stand dekken af dat de klim op een
  lagere heuvel eindigde. De reeks is met een vaste zaadwaarde
  herhaalbaar, anders geeft dezelfde meting twee antwoorden.
- **B371 - en de belangrijkste stap: liedjes achterhouden.** Met 131.072
  mogelijke standen en 188 verzette regels over elf liedjes vindt een
  grondige zoektocht gegarandeerd iets dat goed scoort door toeval. Dat
  is geen beter model, dat is ruis die is uitgekozen, en hoe grondiger je
  zoekt hoe zekerder je overfit. Drie liedjes blijven daarom BUITEN de
  zoektocht en tellen alleen bij de controle. Is de winst daar minder dan
  de helft van de winst op de zoekset, dan zegt het verslag dat er
  overfitting in het spel is.

In v0.118.0 verwerkt:
- **B372 - de vensterproef startte niet eens.** De gebruiker draaide
  `tools/whisper_probe.py` en kreeg meteen een `TypeError` uit
  ctranslate2. Het gereedschap zette `device: "auto"` zelf om, met een
  eigen regeltje dat in dat geval `None` doorgaf - en ctranslate2 wil
  daar een string. De app doet dit al jaren goed met `_resolve_device()`,
  dat `"auto"` vertaalt naar `cuda`/`cpu` en het rekentype naar
  `float16`/`int8`; het gereedschap gebruikte die functie niet maar had
  zijn eigen versie, en die is nooit meegegroeid. Exact het patroon van
  B360: kennis die dubbel staat loopt uit de pas. Nu via de app.
- **B373 - de songtekst beslist over een grensdubbeling.** Eerst de
  meting, want die verandert de vraag. Over veertien projecten en 347
  segmentovergangen is het SLOTWOORD van een segment gemiddeld 0,42
  zeker tegen 0,70 voor elk ander woord, en een derde zit onder de 0,30.
  Dat is bouw en geen pech: op een vensterrand heeft de decoder geen
  rechtercontext meer, dus het afsluitende woord is een gok. Daar
  ontstaan de dubbelingen en de extra woorden. B342 stapelde er vier
  drempels op (gat, duur, zekerheid, gelijkenis) en ving daarmee vijf
  van de tweeëntwintig gevallen; de echte vangsten lagen er net buiten -
  `so`/`so` struikelde over een zekerheid van 0,36 tegen een grens van
  0,30. De songtekst lost dat op zonder één drempel: staat het woord
  niet DIRECT dubbel in de tekst, dan zijn twee gelijke woorden vlak na
  elkaar één woord dat is doorgesneden. Staat het er wel dubbel, dan is
  het de zang. Op de echte data klopt dat overal: bij "Lied K
  " wordt `so`/`so` nu samengevoegd (218 naar 217 woorden),
  en bij Lied P blijven alle zes de `Sunday`-paren staan omdat
  de tekst daar letterlijk "Sunday, Sunday" zingt - inclusief het paar
  met maar 0,2 seconde ertussen, dat ik op grond van de drempels fout
  zou hebben samengevoegd. Zonder songtekst blijft de oude, voorzichtige
  toets gelden, want het leespad mag daar niet op omvallen.
- **B374 - eerst goedkoop aanwijzen, dan duur meten.** 1.5.8 was de
  Whisper-venstertest, maar die deed niet meer dan de zangstem opzoeken
  en je doorverwijzen naar het gereedschap. Hij is nu een gatdetector:
  leg de woordtijden naast de GEMETEN zangvensters en meld elke stretch
  van vijf seconden of meer waar de zangstem zingt en Whisper zwijgt.
  Dat kost seconden en start geen enkele keer Whisper. Pas als je weet
  waar het gat zit, is het de moeite om acht instellingen te proberen -
  en dat is 1.5.11c geworden, in de zware bak, met drempel 1 zodat hij
  draait wanneer je hem aanvinkt. Hij pakt automatisch het grootste gat
  van het huidige project. TIJDELIJK: zodra we weten welke instelling
  wint mag hij eruit, en dan verdwijnt 1.5.11 vanzelf als er niets
  anders onder staat.
- **B374 - wat de gatdetector meteen laat zien.** Bij "Lied K
  " houdt de zang op bij 161,8 s en komt er daarna nog
  `Thank you.` (0,15/0,03), `We'll be right back.` en twee keer
  `Just as so close to me` op 224-232 s. Die laatste twee zijn ECHTE
  zang - vier van hun woorden koppelen op gelijkenis 1,00 - dus Whisper
  heeft van een outro van ruim een minuut maar twee brokken opgepikt.
  Dat is een overgeslagen venster, geen koppelprobleem.

In v0.119.0 verwerkt:
- **B375 - een `[bg]`-regel knipte zijn eigen blok doormidden.** De
  gebruiker deed precies wat de handleiding zegt - de meegezongen
  achtergrondregels tussen `[bg]` zetten - en zag de koppeling
  instorten. Oorzaak: de blokgrens werd afgeleid uit een GAT in de
  regelnummers, en een `[bg]`-regel valt uit die lijst omdat hij geen
  eigen plek in de zin-koppeling krijgt. Zo'n weggelaten regel geeft dus
  exact hetzelfde gat als een lege regel. Gemeten op "Lied K
  ": de songtekst ging van 8 naar 13 blokken terwijl de
  karaoke er 8 hield, en de zin-koppeling klapte om van 47 regels van
  hoge kwaliteit naar nul. De handleiding beloofde letterlijk het
  tegenovergestelde ("telt niet mee bij het regelaantal per blok"). Nu
  tellen overgeslagen bg-regels niet mee in het gat; op hetzelfde
  project weer 8 blokken en 42 regels van hoge kwaliteit.
- **B376 - en de waarschuwing die daarover ging, was zelf blind.** De
  structuurcontrole telde aan de songtekstkant de ruwe regels (kent wel
  `#`-commentaar, niet `[bg]`) en liet de karaokekant door de echte
  parser lopen. Twee kanten, twee maten: hij meldde 18 tegen 12 waar de
  koppeling 12 tegen 12 zag. Dat is de vervelendste soort melding, want
  je gaat een goed bestand repareren. Beide kanten slaan `[bg]` nu over.
- **B377 - de zangstem als scheidsrechter.** We kenden drie soorten
  rommel in de transcriptie en probeerden ze met tekstregels uit elkaar
  te houden: verzonnen tekst ("MUZIEK", "Thank you"), verkeerd verstane
  zang, en - nieuw ontdekt - de PROMPT-ECHO, waarbij Whisper de
  songtekst die wij als beginprompt meegeven tijdens een instrumentale
  intro gewoon uitspreekt. Die laatste is met geen enkele tekstregel te
  vangen: het ís woordelijk de songtekst, dus elke toets van de vorm
  "lijkt dit op de tekst?" zegt volmondig ja. Bij "Lied K
  " stond op 7,4 s letterlijk de staart van de beginprompt.
  De oplossing hoefde niet uit de tekst te komen. `_vocal_windows` meet
  al waar er gezongen wordt - gebouwd voor de timing, nooit gebruikt om
  te filteren. Staat een segment op geen enkele gemeten zang, dan wordt
  er niet gezongen. Op de ijkset scheidt dat zonder grijs gebied: elk
  echt segment zit op 50 tot 100 procent woorden-op-zang, de twee valse
  op exact nul. Bewust op woordniveau, want Whisper rekt het einde van
  een segment regelmatig ver over de laatste noot heen. Het is een
  gewoon model in het register, dus de proef meet wat het waard is.
  Wat het NIET vangt: een verzinsel waar wel geluid onder zit ("We'll be
  right back" staat op 100 procent zangenergie). Daar is de
  koppelkwaliteit voor nodig, en die staat nog open.
- **B378 - de clusterproef controleert nu of er iets te meten valt.** Met
  de reikwijdte op één project zonder handmatige timing deed hij
  achtenzestig metingen die allemaal 0,00 opleverden, en zette dat als
  tabel in het verslag - te lezen als "geen enkel model doet iets". De
  zoektocht ernaast controleerde dit al wel; nu allebei.

In v0.120.0 verwerkt:
- **B379 - de taalregel heeft eindelijk een bewaking.** De afspraak
  ("Engels is de interne voertaal, inclusief testnamen") stond er sinds
  B299 en is honderd versies lang stilletjes weggeschoven: 839 van de
  852 testnamen zijn Nederlands, en deze week zijn daar een compleet
  tijdelijk paneel en vijf testbestanden bij gekomen zonder dat iemand
  het zag. Elke andere afspraak in dit project heeft een test die rood
  wordt; deze niet. Dat is het verschil tussen een regel en een
  gewoonte. `tests/test_language_guard.py` doet nu twee dingen: hij
  wordt rood als er in een omgezet bestand een Nederlandse functie- of
  klassenaam bijkomt, én als een bestand op de TODO-lijst schoon blijkt.
  Dat tweede is het belangrijkste - zo kan de lijst alleen krimpen en
  wordt hij nooit een permanente vrijstelling.
- **B379 - omgezet.** `tools/whisper_probe.py` in zijn geheel (namen,
  docstrings en de opdrachtregel: `--gap`, `--variants`, `--language`,
  en de acht variantnamen naar `current`, `wider`,
  `no_silence_threshold`, `logprob_loose`, `wider_and_loose`, `vad`,
  `hallucination_jump`, `fallback_on`), de opties van
  `timing_regression` (`--compare`, `--record`, `--date`),
  `timing_eval.compare`, de twee klassen in de koppeleditor
  (`CouplingCanvas`, `CouplingEditorDialog`) en een naam in
  `rename_module`. Let op: je getypte commando's veranderen daarmee.
- **B379 - en meteen de les van B303 herhaald.** De eerste poging ging
  met een reguliere expressie over het hele bestand, en verminkte
  prompt de docstrings: "Dit gereedschap draait dezelfde vocal_stem" en
  "een gap van een minuut". Precies waarom de afspraak een mechanische
  ronde afraadde. De docstrings zijn daarna met de hand vertaald, per
  bestand, met de suite ertussen - en zo gaat de rest ook.
- **B379 - wat er nog Nederlands is**, met opzet en op de lijst:
  `modules/test_panel.py` (drieëntwintig namen plus zijn Nederlandse
  docstrings, dat is vertaalwerk en geen hernoeming) en de genestelde
  melder in `modules/gui.py`. De 839 testnamen staan daar los van: dat
  is de grootste stapel en de docstrings eronder dragen de redenering
  waarom een test bestaat, vaak met het meetgetal erbij. Die gaan in een
  eigen release, zonder er iets anders bij, zodat een regressie
  zichtbaar blijft.

In v0.121.0 verwerkt:
- **B380 - sjabloontiming: gebouwd, gemeten, en uitgezet.** Het idee is
  van de gebruiker en het klopt: wat er in een outro gezongen wordt is
  bijna altijd een herhaling van iets van eerder in het lied, en díe
  keer werd wél goed verstaan. Neem dus de meting van de plek waar het
  wel lukte in plaats van te gokken. Het bewijs stond er ook: op "Lied K
  " wordt "Don't stand, don't stand so, don't stand so
  close to me" vier keer schoon overgenomen, en de twee instanties van
  elf woorden duren 5,38 en 5,40 s - twee onafhankelijke metingen, twee
  honderdsten uit elkaar. En 36,3 s gemeten zang na de laatste coupletten
  gedeeld door 5,39 geeft bijna precies de zes herhalingen die de
  songtekst daar heeft staan.
- **B380 - waarom hij toch uit staat.** `modules/timing_template.py`
  doet het werk goed: het bouwt per regeltekst een sjabloon met een duur
  én een intern profiel (de verhouding per lettergreep, zodat het ritme
  van de zanger blijft staan in plaats van gelijkmatig uitsmeren), het
  laat instanties die op stilte staan buiten het sjabloon, en het weigert
  een sjabloon waarvan de instanties het oneens zijn. Maar het haalt die
  instanties uit de **uitvoer van de zin-koppeling**, en in een outro is
  dat precies de stap die stuk is. Op het echte project kwamen er
  drieëntwintig sjablonen uit, waarvan het belangrijkste `4x duur 1,00 s
  spreiding 0,00` - dat is geen meting maar de ondergrens van
  `sanitize_timing`, vier keer dezelfde bodem die er als eensgezindheid
  uitziet. Negen andere hadden een spreiding van 1,48. Repareren op zulke
  cijfers is slechter dan niets doen: zes regels werden er 1,00 s van.
- **B380 - dus uit en niet weg.** Volgens de afspraak: een model dat
  niets waard blijkt gaat op `default_on=False` met de meting als reden
  in het register, blijft in de code staan en blijft meelopen in de grote
  proef (1.5.11), zodat het elke ronde opnieuw gemeten wordt. De volgende
  ronde is de bron: de sjablonen moeten uit de **transcriptietijden** via
  de koppelkaart komen, niet uit de koppeluitvoer - dan meet je Whisper
  waar Whisper het goed deed, in plaats van de koppeling waar die het
  slecht deed.
- **B381 - de controle die eruit voortkwam, blijft wél aan.**
  `timing_checks.duration_outliers` vergelijkt de duur van elke regel met
  de mediaan van diezelfde regel elders in het lied en telt `odd_duration`.
  Dat was nodig omdat "hoge kwaliteit" alleen zegt dat de koppeling
  één-op-één was: op dit project stond een regel van **19,42 s** als hoog
  gemarkeerd, terwijl dezelfde tekst er 5,4 s over doet. Een sjabloon
  hoeft er niet te zijn om dat te zien - de regel spreekt zichzelf tegen.

In v0.122.0 verwerkt:
- **B382 - `modules/` en `tools/` zijn Engels; de TODO-lijst is leeg.**
  De twee laatste bestanden zijn om: `modules/test_panel.py` (drieën-
  twintig namen, alle lokale variabelen en al zijn Nederlandse
  docstrings) en de genestelde melder in `modules/gui.py`. De bewaking
  uit v0.120.0 deed daarbij precies waarvoor hij is gemaakt: zodra een
  bestand van de lijst schoon bleek werd hij **uit zichzelf rood** met
  "is clean - strike it from TODO". Dat is het verschil met een
  handmatige lijst, die stilletjes zou zijn blijven staan.
- **B382 - hoe het is gedaan, want B303 blijft de les.** Niet met een
  reguliere expressie over het bestand, maar met een hernoemer die
  alléén NAME-tokens aanraakt: strings en commentaar komen er niet aan
  te pas. Voor f-strings was daar een tweede pass voor nodig - Python
  3.11 geeft een f-string als één STRING-token terug, dus wat er tussen
  de accolades staat is code die de tokenizer niet als code aanbiedt.
  De prozadelen (docstrings, commentaar) zijn daarna met de hand
  vertaald, per blok, met de suite ertussen. En het was nodig ook: één
  blinde ronde over de strings maakte van "de weglaatproef" doodleuk
  "de omission_trial" - dezelfde verminking als bij `whisper_probe.py`,
  op dezelfde dag opgemerkt omdat het handwerk erna langskwam.
- **B382 - wat een hernoemer per definitie niet ziet: gegevens.** De
  interne woordenboeksleutels van 1.5.8 (`gezongen`/`gaten`/`stil`) en
  van de koppeldekking (`woorden`, `gekoppeld`, `zwak_deel`, ...) zijn
  strings, geen namen. Ze zijn met de hand omgezet, en dat is de
  gevaarlijkste stap van de hele ronde: de dict wordt in de ene functie
  gevuld en in de andere afgedrukt, en het enige dat die twee verbindt
  is de spelling. Een gemiste sleutel geeft geen foutmelding maar een
  lege kolom. `tests/test_v0122.py` zet ze daarom allemaal met naam op
  papier, aan bouwkant én afdrukkant.
- **B382 - de meldervorm is voor de derde keer een contract geworden.**
  B357 maakte er `report(slot, name, done, total)` van, B360 was de
  nasleep van een typeaanduiding die nog de oude vorm beschreef, en deze
  ronde hernoemde alle vier de argumenten tegelijk. Een hernoeming die
  een contract raakt is dezelfde soort wijziging als B357 was, dus staat
  de vorm nu net zo hard vast: in de loper, in de balk aan paneelkant en
  in de handtekening van elke actie.
- **B382 - de bewaking kijkt nu verder dan de `def`-regel.** Argumenten
  en toegekende variabelen tellen mee. Dat kon pas nadat de stapel op
  was: de laatste zeven restjes in het hele programma (`tekst_grp`,
  `muziek_keuzes`, `grens`, `overgeslagen`, `proef`, `tekst`, `regel`)
  waren allemaal lokalen en parameters, precies wat een bewaking die
  alleen `def`-regels leest niet kan zien. Andersom was het zinloos
  geweest: een brede bewaking over een brede achterstand is een muur van
  rood die wordt uitgezet.
- **B383 - de reden bij een sjabloonherstel stond in het Nederlands in
  de code.** `timing_template.implausible` gaf "2.3x langer dan elders"
  terug, en dat gaat als `%s` de logregel in - dus het logvenster. Dat
  hoort volgens de afspraak sinds B315 door `translations.py`. Nu vier
  sleutels (`template_no_duration`, `template_too_fast`,
  `template_longer`, `template_shorter`), en de test ernaast vergelijkt
  met de vertaaltabel in plaats van met een letterlijke tekst.
- **B382 - wat er nog Nederlands is**, en waarom dat zo blijft: de
  `nl`-teksten in `translations.py`, de documenten hier, de koppen en
  kolomnamen in `modelmatrix.md` en `modelcombinaties.md` (die leest de
  gebruiker), en de niveaunamen in het modelregister (`blok`, `zin`,
  `koppeling`, `venster`, `woord`) - dat zijn gegevens die als kolom in
  zo'n verslag terechtkomen, geen namen in de code. Wat wél nog moet:
  de **839 testnamen** met hun docstrings. Die gaan in een eigen
  release, zonder er iets anders bij, zodat een regressie zichtbaar
  blijft; ze staan bewust niet op de TODO-lijst, want een regel die
  nooit geschrapt kan worden is precies de permanente vrijstelling die
  deze bewaking moet voorkomen.

In v0.123.0 verwerkt:
- **B387 - "Onbekend artefact: 'config:models'": 1.1 en 1.3 vielen om op
  elk bestaand project.** Twee lijsten die uit elkaar zijn gelopen. B361
  (v0.116.0) zette `config:models` in de instellingenhandtekening van
  `_config_signature`, zodat een uitgezet model de afgeleide timing
  ongeldig maakt - maar niemand heeft die naam in de afhankelijkheden-
  kaart gezet. `dependents()` gooit met opzet een KeyError op een naam
  die hij niet kent ("beter een luide fout dan stilletjes niets
  ongeldig maken"), en dat is precies wat er gebeurde.
- **B387 - waarom het vijf versies onzichtbaar bleef.** Zolang de
  opgeslagen handtekening niet veranderde werd de groep nooit als
  gewijzigd gemeld. v0.121.0 voegde B380 aan het register toe, de
  handtekening verschoof, en vanaf dat moment meldde elk project met een
  oudere handtekening "config:models gewijzigd" en viel daarna om.
  Nieuwe projecten hadden er geen last van (verse handtekening), en het
  hele testpaneel 1.5.x roept `sync_input_changes` nooit aan - daarom
  bleef de suite twee releases lang groen terwijl het programma voor de
  gebruiker stuk was. Het opnieuw maken van de karaoke hielp niet: de
  oorzaak zat in de projecthandtekening, niet in de audio.
- **B387 - wat er nu vervalt, en wat met opzet niet.** `config:models`
  hangt aan `word_coupling`, `coupling` en `timing`. Nadrukkelijk NIET
  aan de transcriptie: de leespadfilters (B334/B342/B343) draaien bij
  het LEZEN van de cache, niet bij het schrijven, dus een ander model
  mag nooit een nieuwe Whisper-draai kosten - dat zou een half uur voor
  niets zijn. Ook Demucs blijft staan. Twee tests bewaken precies dat.
- **B387 - de bewaking die dit had moeten vangen, en waarom hij het
  niet deed.** `test_v098` controleert al jaren of elke stap- en
  metasleutel uit de code in de keten staat, maar hij leest daarvoor de
  `set_step`/`set_meta`-aanroepen uit de broncode. De `config:`-sleutels
  komen daar niet vandaan: die staan als dict-literal in
  `_config_signature`. Een hele categorie sleutels is dus nooit
  gecontroleerd. `tests/test_v0123.py` sluit dat gat door de functie
  zelf om zijn sleutels te vragen in plaats van de bron te lezen, en
  controleert ook de omgekeerde kant: een `config:`-artefact dat nergens
  gemeten wordt is een dode regel die stilletjes niets ongeldig maakt.
- **B387 - en de fout die de KeyError liet staan is bewust NIET
  weggevangen.** Een naam die echt niet bestaat gaat nog steeds knallen;
  daar is een test voor. Het probleem was niet de luide fout, het was de
  ontbrekende regel in de kaart.
- **Leveringsfout uit v0.122.0 rechtgezet.** `tests/test_v0112.py` was
  bij de taalronde wel omgezet maar niet meegeleverd, dus op de machine
  van de gebruiker stonden vier tests rood op namen die daar niet meer
  bestonden. Geleverd. De les is klein maar echt: bij een hernoeming
  over meerdere bestanden is de lijst van te leveren bestanden zelf een
  plek waar iets kan wegvallen.

In v0.124.0 verwerkt:
- **B377 - gemeten, en de uitkomst is andersom dan het getal suggereerde.**
  De meetlat ging van 3,25 s naar 3,32 s toen de zangstem-scheidsrechter
  meeging, en op Lied_P kostte hij 0,49 s. Dat leest als een
  regressie. Per regel is het dat niet: **45 van de 50 regels zijn
  identiek** met het model aan of uit, géén enkele wordt beter, en vijf
  opeenvolgende regels (28 t/m 32) dragen alles - drie daarvan alleen al
  19,88 van de 21,82 seconden. En wat B377 daar weggooit is **één
  segment**: "Thank you." op 167,07-167,87, met 0 van zijn 2 woorden op
  gemeten zang, middenin een gat van 22 seconden waar niemand zingt. Dat
  is geen verkeerde drempel, dat is het model dat precies zijn werk doet.
- **B377 - waarom het tóch fout kost: het leugentje was dragend.** Met
  "Thank you" weg staat er tussen 155,64 en 194,98 geen enkel
  transcriptiewoord meer, en de interpolatie zwalkt: regel 31 landt op
  194,98 waar de hand 180,69 zegt - **veertien seconden te laat**. Het
  valse anker hield de boel per ongeluk overeind. **Besluit: B377 blijft
  aan en de drempel blijft op 0,34.** De verleidelijke reparatie - de
  drempel oprekken tot het segment blijft staan - zou de hallucinatie
  hebben behouden; daar staat nu een test op.
- **B392 (nieuw, nog niet gebouwd) - de ankers liggen er al.** Van de
  acht regels zonder transcriptiewoord binnen een seconde liggen er
  **vier binnen 0,22 s van een gemeten zanginzet, en twee binnen 0,03 s**
  - en dat zijn juist de twee die het verst wegzwalkten (180,69 tegen
  inzet 180,65; 185,52 tegen 185,53). `_vocal_windows` wordt al voor elk
  project berekend. Waar de transcriptie zwijgt maar de zang gemeten is,
  ligt het antwoord dus al klaar; het wordt alleen niet als anker
  gebruikt. Let op de keerzijde die de meting óók laat zien: over álle
  regels voorspelt een zanginzet er maar 36% binnen 0,5 s. Dit is dus
  nadrukkelijk een terugval voor regels **zonder** eigen anker, niet een
  algemene regel. Eerst bespreken, dan bouwen.
- **B384 - de energiecache kon nooit raken, en dat is gerepareerd; maar
  de winst is klein.** `measure()` maakte per aanroep een verse
  `TemporaryDirectory`, en de cachesleutel in `rhythm` bevat het pad -
  dus elke meting een misser, plus een kopie van 50 MB omdat de
  "staat-ie er al?"-controle ook in die verse map keek. Nu één werkmap
  per project (veilig, want `_build_project` herschrijft `project.json`
  elke keer volledig) en een harde koppeling in plaats van een kopie.
  **Eerlijk over het getal: ik schatte hier eerst een flinke hap van de
  28 minuten, en dat was fout.** Die eerste meting telde de eenmalige
  opstart van librosa mee. Netjes uitgemeten met zes metingen na
  warmdraaien: 5,85 s tegen 5,59 s, dus **5%** - op 1.5.10 ongeveer 77
  seconden. Het blijft goed werk (de cache was bedoeld om te werken en
  deed dat niet), maar de rekentijd zit in de koppeling zelf en niet in
  het inlezen. Wie 1.5.10 echt korter wil, komt uit bij losse processen.
- **B385 - een proef die afhaakt telde als "gedraaid".** Een afhaker gaf
  zijn uitleg terug als gewone uitslag, en was daarmee niet te
  onderscheiden van echt werk: de duur werd bewaard en de versiedrempel
  schoof twintig versies op. Dat is precies wat er gebeurde: 1.5.11a
  haakte op v0.118.0 in 0,2 s af en boekte daarmee twintig versies
  stilte voor een meting die nooit plaatsvond - vier versies later vroeg
  de gebruiker waarom 1.5.11 zo kort duurde. Nu een eigen uitzondering
  `TrialSkipped`: de reden komt gewoon in het verslag, maar de duur
  wordt niet bewaard en de drempel schuift niet op.
- **B386 - de vensterproef pakte zwijgend het huidige project.** Hij
  meldde "geen gat van betekenis" over een liedje waar niemand naar
  vroeg, en kostte zo een draai van 1.5.11 die niets beantwoordde.
  Willekeurig kiezen zou de stilte oplossen maar niet de verspilling:
  dit zijn acht Whisper-draaien en het laat alleen iets zien waar een
  gat ís. Dus kiest hij nu **het grootste gat over alle projecten**, met
  het huidige project als eerste keus zolang dat zelf een gat heeft. Dat
  kiezen kost geen Whisper: het leunt op de machinerie van 1.5.8, die
  woordtijden tegen gemeten zang legt. Is er nergens een gat, dan haakt
  hij af (B385) in plaats van een oordeel te vellen.
- **Twee vertaalsleutels opgeruimd** die door B386 dood raakten
  (`heavy_probe_no_transcription`, `heavy_probe_no_gap`): de proef zoekt
  nu zelf een ander project in plaats van te melden dat dit er geen
  transcriptie of geen gat heeft.
- **B393 (nieuw, niet gebouwd) - er staan dertig ongebruikte
  vertaalsleutels in `translations.py`** (`lane_*`, `view_*`,
  `model_*_desc`, `fill_cache_*`, `test_texts`, `test_probe`, ...),
  overblijfselen van hernoemde knoppen en samengevoegde tests. Ze doen
  geen kwaad maar ze maken de tabel onbetrouwbaar om in te zoeken. Er is
  geen bewaking tegen; die zou er moeten komen, samen met het opruimen.

In v0.125.0 verwerkt:
- **B389 - de waarneming klopt, het voorgestelde mechanisme niet.** De
  gebruiker zag timingproblemen "doorschuiven" en stelde voor om bij een
  botsing tussen het einde van een zin en het begin van de volgende een
  gevecht op gewicht te houden, met voordeel voor de nieuwere zin.
  Gemeten over dertien projecten met handmatige timing: **botsingen
  bestaan niet.** Er is precies één regel op 643 waarvan het begin vóór
  het einde van zijn voorganger valt; `sanitize_timing` voorkomt overlap
  al. Dat gevecht zou dus vrijwel nooit afgaan.
- **B389 - maar het doorschuiven is echt, en groot.** 158 van die 643
  regels (24,6%) staan er meer dan een seconde naast, en niet verspreid:
  in **38 reeksen van gemiddeld 4,16 regels**, de langste **39
  opeenvolgende regels** in een lied van 64. Uitgesplitst naar of een
  regel een eigen anker heeft is het beeld eenduidig: **17% van de
  regels mét anker staat er meer dan een seconde naast, tegen 75% van de
  regels zonder.** Wat doorschuift is dus geen botsing die zijn buurman
  wegduwt - het is een heel stuk zonder ankers dat samen wegzwalkt.
- **B392 - een gat middenin krijgt nu de gemeten zang.** Precies wat
  B336 al voor de staart deed. `interpolate_spans` trok door een gat
  tussen twee ankers een rechte lijn en wist niets van waar er werkelijk
  gezongen wordt; de zangvensters gingen alleen naar de staart. Nu krijgt
  ook een gat in het midden ze, via `windows_between`. **Met dezelfde
  weigering als B336**: één regel per gemeten venster, en niets zodra de
  vensters de reeks niet precies verklaren - dan blijft de oude
  interpolatie staan. Een verkeerd venster is erger dan een rechte lijn,
  want het ziet eruit als een meting.
- **B392 - gemeten, en het herstelt wat B377 kostte.** Op Lied_P
  4,76 -> **4,39 s** (-0,37), en op Lied_Q en Lied_T
  precies niets (daar verklaren de vensters de reeksen niet, dus houdt hij
  zich netjes stil). Gewogen over die drie 0,17 s beter en nergens
  slechter. Ter herinnering: B377 kostte op dit project 0,49 s door het
  weghalen van een dragend leugentje - B392 haalt daar het grootste deel
  van terug zonder de hallucinatie terug te zetten. **Eerlijk over de
  reikwijdte**: dit is gemeten op drie projecten, niet op de hele ijkset;
  1.5.5 en 1.5.10 geven het echte getal.
- **B388 - een nieuw project opende in de map van het vorige.**
  `input_start_dir` gaf bij een vers project een lege tekenreeks terug,
  en een lege tekenreeks is niet neutraal: Qt vult daar zélf de laatst
  gebruikte map van deze programmadraai in. Vandaar dat het
  verkennervenster bij een nieuw project in de muziekmap van het vorige
  project opende. Nu de thuismap als terugval - een echt pad, dus Qt komt
  er niet meer tussen. Let op: `_pick_background` en `_pick_video_font`
  geven nog steeds een lege startmap mee; dat zijn videovoorkeuren en
  geen projectinvoer, maar het is dezelfde valkuil.

In v0.126.0 verwerkt:
- **B395 - de koppeling rekende hetzelfde duizenden keren opnieuw uit.**
  De vraag van de gebruiker was waarom 1.5.10 zo weinig van zijn machine
  vraagt: 15% op tien kernen, oftewel precies één kern. Het voor de hand
  liggende antwoord was losse processen. De profiler gaf een beter
  antwoord. `cluster._fold_repeats` wordt per meting **636.028 keer
  aangeroepen met 307 verschillende invoeren** - hetzelfde woord
  tweeduizend keer opnieuw gevouwen. Het is een zuivere tekstfunctie, dus
  één `lru_cache`-regel brengt een meting van **2,44 s naar 0,426 s: een
  factor 5,7**. Gecontroleerd dat het niets verschuift: de uitkomsten van
  drie projecten zijn tot op de honderdste identiek voor en na, want een
  zuivere functie cachen kan per definitie geen antwoord veranderen.
- **B395 - wat dat betekent voor de losse processen.** Vier werkprocessen
  zouden een factor drie à vier geven, ten koste van een
  multiprocessing-opzet die op Windows zijn eigen valkuilen heeft. Deze
  factor 5,7 kost tien tekens. Het idee van losse processen blijft op de
  lijst maar zakt naar onderen: pas als dit erin zit weten we waar het
  nieuwe plafond ligt. En het raakt niet alleen het testpaneel - deze
  koppeling draait elke keer als de gebruiker 1.3 indrukt.
- **B394 - de meethistorie raakte metingen kwijt.** Gevonden bij het
  lezen van de uitslagen van diezelfde draai: na 1.5.1 tot en met 1.5.10
  stonden er nog **negen sleutels** in `docs/testhistorie.json` - de
  totalen per actie plus vier van de veertien projecten van 1.5.8.
  Alles van 1.5.5, 1.5.6 en 1.5.7 was weg. `remember()` doet
  lezen-wijzigen-schrijven van het HELE bestand en `across_projects`
  draait twee werkthreads, zonder enige vergrendeling. De tweede
  schrijver laadt zijn momentopname voordat de eerste heeft opgeslagen
  en schrijft die er daarna overheen. Dat ondermijnt precies waarvoor
  B362 bestaat: vergelijken met vorige versies kan alleen als die vorige
  versies er nog zijn. Nu een slot om het lezen-wijzigen-schrijven, met
  een test die zonder dat slot aantoonbaar rood wordt (veertig threads,
  de meeste ingangen verdwijnen).
- **B394 - en een aantekening voor later.** Een threadslot is genoeg
  zolang er één proces schrijft. Zodra de meting over PROCESSEN wordt
  verdeeld moet dit een bestandsslot worden; dat staat in het commentaar
  waar de volgende lezer kijkt, want dat idee staat op de lijst.
- **Wat de draai zelf opleverde.** Het uitgangspunt staat op **3,10 s**
  over veertien projecten (was 3,32 over elf; de set is gegroeid met
  Lied L en Lied Q, dus dat is geen zuivere vergelijking).
  **B392 doet precies wat hij moest doen en niets meer**: +0,37 s op
  Lied_P, nul op alle andere - de weigering houdt hem stil waar
  de vensters de reeks niet verklaren. Gewogen +0,04. **B377** kost nog
  0,04 s, maar per project is het beeld nu tweezijdig: -0,49 op
  Lied_P tegenover **+0,27 op Lied Q**, precies het project
  waar de gebruiker klaagde over weggestreepte woorden aan het eind.
- **En de vondst van de clusterproef, die voor het eerst echt draaide.**
  1.5.11a haalde 32 combinaties in 505 s voordat de gebruiker afbrak, en
  daar staat een uitschieter tussen: **B258/B285 + B313 + B330/B351
  samen UIT geeft 2,07 s tegen 3,10 s uitgangspunt - een derde minder
  fout.** Geen enkel los model komt in de buurt (de beste is B332 met
  0,57). Dit is een **spoor, geen conclusie**: cluster 1 heeft zeven
  modellen (128 combinaties) en er zijn er 32 gemeten, en 1.5.11b - de
  proef die met achtergehouden liedjes controleert of zo'n vondst geen
  toeval is - is niet gedraaid. Met B395 kost die hele cluster nu
  ongeveer zes minuten in plaats van vierendertig, dus het antwoord is
  betaalbaar geworden.

In v0.127.0 verwerkt:
- **B390 - de knip/samenvoeg-proefopstelling staat, en één aanname bleek
  meteen fout.** De goedkoopste kandidaat die ik had aangewezen -
  `condition_on_previous_text=False`, zodat Whisper niet op zijn eigen
  vorige uitvoer voortborduurt - **stond al aan**, zowel in
  `modules/whisper.py` als in de proef. Dat is de tekstboekverklaring
  voor een ontsporende outro, en hij is hier dus al lang uitgesloten. De
  outro's ontsporen tóch. Wat er aan het einde van een lied misgaat is
  dus niet de decoder die zichzelf napraat, en dat is nu opgeschreven in
  `modules/whisper_chunks.py` zodat niemand er nog een dag aan besteedt.
- **B390 - wat er wel overblijft: de vensterindeling en de prompt.**
  `modules/whisper_chunks.py` bevat de delen waarover je kunt nadenken
  zonder Whisper te starten: wáár je knipt, welke prompt een stuk krijgt,
  en hoe je de uitkomsten weer samenvoegt. Knippen gebeurt **in de
  stiltes** die de zangstem al aanwijst, met dertig seconden als
  bovengrens; alleen waar de zang binnen dertig seconden niet pauzeert
  wordt er door de zang geknipt, en dan met overlap zodat het
  grensgebied in twee stukken voorkomt. Want elke knip MAAKT een nieuwe
  rand, en een rand is precies de zwakke plek (0,42 zekerheid tegen 0,70
  elders).
- **B390 - de prompt per stuk is het sterkste deel, en dat werd pas
  duidelijk nadat de prompt goed gelezen was.** Die 400 tekens zijn een
  GLOBAAL tekort dat LOKAAL een overvloed wordt: bij acht stukken heeft
  elk stuk zijn eigen budget en zijn er veel minder unieke woorden
  nodig, dus kan elk stuk de echte regels voluit krijgen - lopende tekst
  met frasering in plaats van een ontdubbelde woordenlijst. Dat laat
  Whisper de juiste ZIN verwachten in plaats van alleen de juiste
  WOORDEN. De snee is met opzet ruim (acht seconden marge), want hij
  leunt op de plaatsing van de eerste draai en die is juist fout waar we
  opnieuw kijken.
- **B390 - het samenvoegen is nadrukkelijk GEEN stemming.** Twee draaien
  delen dezelfde beginprompt, dus dat ze het eens zijn kan óók betekenen
  dat ze allebei de prompt napraten - precies de echo die we willen
  vangen. Overeenstemming is dus geen bewijs. Daarom mag een tweede
  draai alleen spreken waar de eerste **niets** zegt, en dan nog alleen
  met woorden die op gemeten zang staan. De zangstem is de enige getuige
  die niets van de tekst weet, en heeft daarom het vetorecht - dezelfde
  regel die B377 op hele segmenten toepast, hier per woord.
- **B390 - en de proef die het moet uitwijzen: 1.5.11d.** Draait op het
  project met de meeste onverstane zang en zet vier manieren naast
  elkaar: zoals nu, twee keer met een verschoven start (10 en 20 s, want
  met stappen van tien op een venster van dertig ligt elk punt in
  minstens één draai ver van een rand), en geknipt met een prompt per
  stuk. De maat is **seconden gemeten zang zonder woord** - hetzelfde
  getal dat 1.5.8 rapporteert, want een woordentelling zegt niets: een
  draai kan meer woorden geven en hetzelfde gat laten staan. Elke
  variant wordt apart gerapporteerd én de samenvoeging, zodat winst
  herleidbaar is naar waar hij vandaan komt.
- **B390 - de proef kan nu ook een stuk audio transcriberen.**
  `run_once` neemt `start`/`end` en schuift de tijden terug op de
  tijdlijn van het lied, via een numpy-array in plaats van een pad. Dat
  werkt bij elke versie van faster-whisper en hangt niet af van
  `clip_timestamps`.
- Er is nog **niets gemeten**: dit is de opstelling. Wat eruit komt
  bepaalt of knippen een instelling wordt of dat we weten dat de
  vensterranden niet de oorzaak zijn. Beide uitkomsten zijn winst.

In v0.128.0 verwerkt:
- **B396 - de werkplekken gebruiken eindelijk de machine.** De gebruiker
  heeft hier meerdere keren om gevraagd en kreeg elke keer een uitleg in
  plaats van een reparatie. Die uitleg klopte zelfs, en dat maakte hem
  juist waardeloos: twee werkplekken bestaan sinds B357, het zijn echte
  threads, en bij puur Python laat de GIL er maar één tegelijk lopen.
  Vijftien procent van twaalf logische processors is één kern. Dat nog
  eens uitleggen meet niets.
- **B396 - twee soorten werk, twee sommen** (de regel van de gebruiker,
  en het is de juiste omdat de twee soorten werk niet op elkaar lijken):
  - **rekenwerk** (de meetlat, dus 1.5.10 en de cluster- en
    zoekproef) heeft **losse interpreters** nodig. Elke werker houdt dan
    één kern bezig, dus het aantal is kernen min een paar om de machine
    bruikbaar te houden: twaalf geeft **negen**.
  - **Whisper-werk** is precies andersom: ctranslate2 is C++ en laat de
    GIL los, dus daar lopen threads wél echt naast elkaar. Maar één
    draai pakt al ongeveer vier kernen, dus wat er past is kernen
    gedeeld door vier, en daarvan twee derde: twaalf geeft **twee**. Dat
    klopt met de meting - één draai stond op 33% van de machine.
- **B396 - waarom processen hier de enige weg zijn, en niet alleen een
  snellere.** Een modelvariant wordt met `setattr` op moduleglobals
  gezet. Twee varianten in één interpreter zouden elkaars modellen lezen,
  en dat is precies waarom 1.5.10 zijn 256 rondes strikt na elkaar
  aflegt. Geef elke werker zijn eigen interpreter en dat bezwaar
  verdwijnt. Het werkpakket is daarom klein en beitsbaar gemaakt: een
  projectnaam plus de **volledige** gewenste modelstand - geen
  aanroepbare dingen, geen context, geen afsluitingen, want juist die
  maakten de bestaande verdeler thread-only.
- **B396 - de vensterproef liep zijn varianten stuk voor stuk af.** Dat
  was wat de gebruiker op zijn scherm zag: één balk die beweegt en één
  balk met een blijven staan etiket. De acht varianten gaan nu door
  dezelfde verdeler als de projecten, met het Whisper-aantal
  werkplekken. Zichtbaar aan twee bewegende balken, en aan het
  processorgebruik.
- **B396 - met historie blijft het op threads.** Daar wordt het meeste
  werk juist overgeslagen (B362), en dan zou een procespool alleen
  opstartkosten toevoegen. De keuze staat in `_yardstick_rows` en er
  staat een test op de volgorde.
- **B396 - en een terugval zonder gemopper.** Lukt het starten van
  processen niet (een ingevroren bouw, een dichtgetimmerde machine), dan
  gaat het serieel verder met een regel in het logboek. Beter een traag
  antwoord dan geen antwoord.
- **Let op bij het hervatten**: een afgebroken zware proef begint
  opnieuw. `heavy_trial` schrijft het verslag na elk afgerond onderzoek
  en bewaart pas dan de duur, dus een proef die af is wordt de volgende
  keer overgeslagen - maar binnen een proef is er geen hervatpunt.

In v0.129.0 verwerkt:
- **B397 - je kon niet zien welke van de vier draaide.** 1.5.11 is vier
  onderzoeken onder één nummer, en op het scherm stond alleen "1.5.11"
  plus een Nederlandse titel. Daarmee kon de gebruiker niet zeggen over
  welke proef hij het had - en daar zijn die letters nu juist voor. De
  balk toont nu `1.5.11c`, de koppen in `modelcombinaties.md` ook, en
  het paneel zet onder het vinkje wat er onder dat nummer schuilgaat
  (`a: clusters, b: zoektocht, c: vensterproef, d: knippen`). Een test
  bewaakt dat geen enkele proef nog een kaal "1.5.11" schrijft.
- **B397 - de vensterproef noemt zijn eigen winnaar.** Hij leest daarvoor
  zijn eigen tabel terug in plaats van een tweede lijstje bij te houden,
  zodat de conclusie eronder nooit iets anders kan zeggen dan de rijen
  erboven. Met de waarschuwing erbij die er hoort: meer seconden is
  alleen winst als het aantal segmenten niet meespringt, want anders is
  het gat gevuld met verzinsels.

Wat de eerste VOLLEDIGE zware draai zei, en waar ik mezelf moet
corrigeren:
- **De vondst van 1,02 s bestaat niet.** Op de afgebroken draai las ik
  `B258/B285 + B313 + B330/B351` op 2,07 s tegen 3,10 uitgangspunt en
  gaf dat door als een spoor dat aandacht verdiende. Over alle **128**
  combinaties komt diezelfde stand uit op **3,31 s (+0,21)** - hij maakt
  het dus slechter. Ik kan niet hard maken waar die 2,07 vandaan kwam;
  wat ik wel weet is dat een gedeeltelijke tabel geen tabel is en dat ik
  hem niet als spoor had moeten doorgeven. De volledige draai zegt dat
  **geen enkele combinatie in dit cluster de huidige stand met meer dan
  0,04 s verslaat** - en die 0,04 is B377 uitzetten, waarover al besloten
  is.
- **De zoekproef heeft zich terugbetaald, en precies zoals bedoeld.** Hij
  vond `B377 + B329/332/340 + B343 + B258/B285` uit: **-0,32 s op de
  zoekset** en op de drie achtergehouden liedjes van 2,79 naar **10,00 s
  - ruim zeven seconden slechter**. Hij meldde dat zelf als het patroon
  van overfitten. Dat is exact waarvoor `_HELD_BACK` bestaat, en het gaf
  af bij zijn eerste echte draai. Zonder die achtergehouden liedjes was
  dit een "verbetering" van 0,32 s geweest die elk volgend liedje sloopt.
- **De vensterproef leverde het enige bruikbare spoor op: VAD.** Op het
  gat van 28 s in Lied_S dekken zeven van de acht instellingen 0,9 s.
  **VAD dekt 26,4 van de 28 s** - met MINDER segmenten (12 tegen 26) en
  vrijwel evenveel woorden (192 tegen 196). Dat laatste is het
  belangrijkste: minder segmenten bij gelijk aantal woorden betekent dat
  er geen lus in zit. Dat is een ander beeld dan op "Lied K
  ", waar VAD juist tekst verzon en de outro liet vallen. VAD is dus
  liedafhankelijk en verdient een meting per project, geen schakelaar
  die overal aan gaat.

In v0.130.0 verwerkt:
- **B398 - twee regels, negen werkplekken.** Sinds B396 draait de meting
  over negen processen, maar het paneel had twee balken en zocht die op
  met het werkpleknummer - dus werkplek 2 tot en met 8 viel buiten de
  lijst en werd nooit getoond. De gebruiker zag twee rijen terwijl er
  negen liepen, en zei dat ook. Twee regels was en blijft het juiste
  aantal; wat veranderd is, is wat ze betekenen: de **eerste regel is de
  draai als geheel** (welke actie, hoe ver), de **tweede is wie er nu
  bezig zijn**.
- **B398 - en de titels wijken voordat de regel dat doet.** Passen de
  projectnamen niet meer op één regel, dan gaan de namen eruit en blijft
  de telling staan: een eerlijke "9 werkplekken" is beter dan een
  liedtitel die halverwege is afgeknipt. Precies wat de gebruiker
  voorstelde.
- **B399 - één pool voor de hele actie, niet één per ronde.** De eerste
  versie maakte per meetronde een verse procespool en sloot hem daarna
  weer. Dat oogt netjes en is rampzalig: 1.5.10 legt 256 rondes af, dus
  dat zijn 256 x 9 = ruim tweeduizend processtarts - en op Windows is
  een start een volledige herimport van de modules, geen goedkope fork.
  Het werk per ronde is seconden; het starten zou meer hebben gekost dan
  het meten. Hergebruik kan juist doordat het werkpakket zo is
  ontworpen: een kind krijgt bij elk pakket de VOLLEDIGE modelstand mee
  en neemt dus niets mee uit de vorige ronde. De negen werkers gaan weg
  zodra een actie klaar is.
- **B398 - en een echte fout die daarbij boven kwam.** Het geheugen van
  de werkplekken stond eerst als muteerbaar klasse-attribuut. Dat wordt
  gedeeld door elk venster, dus een tweede venster erfde de werkplekken
  van het eerste - zichtbaar geworden doordat twee tests elkaars
  projectnamen te zien kregen. Nu per venster aangemaakt.

In v0.132.0 verwerkt:
- **B403 - het testpaneel liep om de taalbepaling heen.** De gebruiker zag
  in 1.5.11 ineens Spaans langskomen en vroeg of Whisper de taal één keer
  meekrijgt of per stukje. Het programma zelf doet het goed:
  `pipeline._language_for()` bepaalt de taal één keer uit de **volledige**
  songtekst - eerst een handmatige keuze, dan detectie op de tekst, en
  alleen "auto" als dat te onzeker is. Maar het paneel vroeg dat nooit en
  gaf Whisper `config.whisper.language` mee, en dat staat standaard op
  "auto". Elke variant detecteerde dus zijn eigen taal.
- **B403 - en dat is geen schoonheidsfoutje.** Het vervuilt precies de
  vergelijking waarvoor de proef bestaat: een variant kan van zijn buurman
  verschillen doordat díe draai besloot dat het lied Spaans was, en niet
  door de instelling die getoetst wordt. Concreet betekent het dat de
  VAD-uitslag (26,4 van de 28 s tegen 0,9 voor de rest) opnieuw gemeten
  moet worden voor iemand hem gelooft.
- **B404 - bij het knippen was het tien keer zo erg.** `run_chunked` gaf
  dezelfde taalstring aan elk stuk door, maar als die "auto" is, detecteert
  **elk stuk apart**. Tien stukken zijn dan tien onafhankelijke
  taalbeslissingen, en juist een kort stuk - een "la la la", een fade-out -
  is het kwetsbaarst. De gebruiker vond dit vóórdat 1.5.11d ooit had
  gedraaid.
- **B403/B404 - de reparatie.** `probe_language()` bepaalt de taal één
  keer: wat de app zelf zou kiezen, en anders wat Whisper op het HELE
  origineel besloot (dat antwoord staat al in `run_info.json`). Blijft het
  daarna "auto", dan zegt het verslag dat er met de hand een taal gekozen
  moet worden - want een meting waarvan de taal zwerft is dat waard om te
  weten. Beide Whisper-proeven zetten de gebruikte taal onder hun tabel.
- **B402 - de bovenste balk is de actie, de blokjes zijn de werkplekken.**
  De bovenste balk toonde de voortgang BINNEN één meetronde: bij 1.5.10
  stond er "2/17" op 11% terwijl de draai hard liep, dus acht minuten werk
  leek vast te zitten. Een actie telt rondes, een werkplek telt projecten,
  en dat zijn verschillende getallen - dus heeft de actie een eigen kanaal
  gekregen. De tweede rij noemde de bezige werkplekken op één regel en met
  negen paste dat niet meer; nu heeft elke werkplek zijn eigen blokje met
  de naam van waar hij op kauwt, gevuld als hij bezig is en flets als hij
  stilstaat. Ook bij 1.5.11 doorgevoerd: daar is de actie "welk van de vier
  onderzoeken" en zijn de blokjes de varianten.

Wat de metingen van deze dag opleverden, voor het archief:
- **1.5.10 ging van 2316 s naar 472 s** - v0.125.0 2316 s, v0.129.0 739 s
  (de cache van B395), v0.131.0 471,8 s (het hergebruiken van de
  procespool, B399). Van negenendertig minuten naar onder de acht, en dat
  hergebruik alleen was ruim vier minuten aan puur processen starten waard.
  Geheugen is geen bezwaar: ongeveer 230 MB per werker.
- **B391 is beantwoord, en het antwoord is nee.** Een langere beginprompt
  geeft MEER segmenten (26 naar 40), MINDER woorden (196 naar 184) en
  precies dezelfde dekking van het gat. Dat is de waarschuwing die we
  zouden aanhouden: het aantal segmenten springt mee zonder dat er iets
  gevonden wordt. Die 400 tekens waren niet voorzichtig maar goed gekozen;
  het ongebruikte budget is geen gemiste kans.
- **1.5.11d, de knipproef, gaf de grootste vondst tot nu toe** - onder
  voorbehoud van B403/B404. Op Lied_S met 188,2 s gemeten zang: huidig
  68,8 s niet gehoord, offset 10 s 49,2 s, offset 20 s 42,9 s, **geknipt in
  tien stukken 15,3 s**. Dat de offsets alleen al twintig seconden schelen
  is het vensterrand-effect, voor het eerst gemeten in plaats van
  beredeneerd. Maar de geknipte draai levert 456 woorden tegen 197, en dat
  moet tegen de songtekst gelegd worden voordat het winst heet - juist die
  variant stond het meest bloot aan de taaldetectie per stuk.

In v0.133.0 verwerkt:
- **B406 - de timing stapelde woorden op elkaar aan het regeleinde.** Op "Lied I
  " hadden veertien woorden op drie regels lengte nul:
  "en de stemming zit erin" stond met alle vijf zijn woorden op exact
  54,064 s. `_sanitize_spans` kapte af op `high`, en zodra de cursor dat
  plafond raakte werd elk volgend vakje `(high, high)`. Het ergste was niet
  dat het gebeurde maar dat het niet te repareren viel: oprekken in de
  editor schaalt de vakjes lineair, en nul maal welke factor dan ook blijft
  nul. Nu wordt materiaal dat niet past evenredig ingedrukt - acht woorden
  in 1,18 s leest snel maar leest - en repareert de editor bestaande
  platgeslagen regels bij het openen, zodat het pas op schijf komt als de
  gebruiker zelf opslaat.
- **B408 - de koppeling had het antwoord al, en de timing gooide het weg.**
  Dit is de vondst van de dag en hij komt uit `project.json` zelf. In
  `steps.coupling.original_items` staat per zin de gekoppelde spanne, en
  voor de zeven regels die meer dan een seconde te kort uitkwamen staat
  daar het goede getal: regel 12 op 50,78-54,07 terwijl de timing
  50,46-51,64 gaf. Sterker, **46 van de 59 regelspannes die de gebruiker
  met de hand vastlegde zijn exact de spanne die de koppeling al gaf** -
  een middag gehoorwerk om een getal te reconstrueren dat er al stond. Waar
  het precies verdwijnt is nog niet vastgesteld; wel dat het NIET in
  `sanitize_timing` gebeurt, want die heeft een eigen ondergrens van
  `baseline x lettergrepen / 3` (1,28 s voor een regel van 32) en er kwam
  1,15 s uit. De verdachte is `_apply_energy_word_timing`, die de regel
  opnieuw over de zangvensters legt; aanwijzing is dat regel 12 automatisch
  op 50,46 begint, vóór de koppeling. Daarom eerst meten en dan pas
  repareren: de diagnostics zetten nu per regel de spanne na de koppeling,
  na de zinsstap en na de woordstap naast elkaar, met een `KRIMP`-vlag.
- **B405 - oprekken liet het woord aan de verkeerde kant groeien.** Trek je
  de rechterrand tegen een buurman aan, dan hield `_inside` de breedte vast
  en schoof het blok naar links: de winst kwam er aan de linkerkant weer
  uit. Dat schuiven is precies goed bij verplaatsen en precies fout bij
  oprekken; het verschil is welke rand de gebruiker vasthoudt, en die gaat
  nu mee. Is er geen ruimte, dan beweegt er niets - weigeren is bij een
  rek-actie het eerlijke antwoord, springen niet.
- **B407 - dezelfde wijziging, twee tegengestelde uitkomsten.** De
  karaoketekst opnieuw kiezen via de bestandskiezer behield de handmatige
  timing (B99 voert de tekstwijziging netjes door), maar hetzelfde bestand
  in kladblok bewerken liep langs die regeling heen naar
  `sync_input_changes`, die alles wat van de karaoketekst afhangt weggooit
  - inclusief `timing.json`. Dat is deze dag echt gebeurd en het kostte de
  gebruiker bijna een middag handwerk; alleen de back-up redde het. Het
  redden kan zonder geheugen van de oude tekst: `timing.json` draagt de
  tekst van elke regel zelf, en dat is de oude toestand. Bij een gelijk
  aantal regels wordt de wijziging doorgevoerd over de bestaande spanne;
  bij een andere structuur gaat de timing weg zoals voorheen.
- **B409 - het paneel zei twee dingen dubbel en één ding niet.** Boven de
  blokjes stond een regel die dezelfde projectnamen noemde, alleen
  afgeknipt op regelbreedte; die is weg. De bovenste balk las
  "1.5.11 1.5.11 2/4" doordat het omhulsel de actiecode altijd voorplakte
  en de proef zichzelf ook al zo noemde. En de letter van de proef ging
  naar werkplek 0, waar de eerste projectnaam hem een tel later
  overschreef - hij staat nu op de actieregel, dus "1.5.11b 2/4".
- **B410 - het testpaneel, na drie keer vragen.** `_measure` liep nog over
  twee threads die om de beurt de GIL hebben: bij 1.5.11b zijn dat 240
  rondes op één kern van de twaalf, en dat is precies wat de gebruiker in
  de taakbeheerder zag. Het gaat nu over de procespool, wat kon door
  modelcodes door te geven in plaats van `(module, attribuut, vervanging)`;
  een functieobject reist niet naar een kindproces, een code wel.
  1.5.11c meet dekking voortaan op **woorden** in plaats van
  segmentranden - VAD gaf twaalf segmenten tegen zesentwintig en scoorde
  26,4 van 28 s "gedekt" terwijl het aantal woorden juist daalde, en een
  bracket zonder woorden erin is geen dekking. 1.5.11d verdeelt zijn vier
  draaien over twee Whisper-plekken (873 s van de 3551 s liep serieel),
  voegt samen vanaf de **beste** draai in plaats van altijd vanaf "huidig"
  (dat kostte 7 s dekking: knippen alleen haalde 29,3 s, de samenvoeging
  36,5 s) en schrijft de gehoorde woorden weg naar `docs/knipwoorden.txt`.
  De achtergehouden liedjes van 1.5.11b komen uit de meetbare projecten en
  gespreid: het alfabetische staartje leverde drie liedjes waarvan er één
  geen handmatige timing had, dus twee telden er echt mee en één daarvan
  was het slechtste lied dat er is.

Wat de metingen van deze dag opleverden, voor het archief:
- **De taalfix van v0.132.0 was geen cosmetiek.** Opnieuw gemeten met de
  taal vastgezet: de geknipte draai geeft 248 woorden en 29,3 s niet
  gehoord, tegen 456 woorden en 15,3 s in de vervuilde draai. Ruim de helft
  van die woorden was Spaans verzinsel. De conclusie "knippen is de
  grootste vondst tot nu toe" is daarmee ingetrokken; wat overblijft is een
  echte maar veel kleinere winst.
- **1.5.11a is klaar en het antwoord is nul.** Geen enkel paar modellen
  toont een wisselwerking, dus er valt geen cluster te vormen en de losse
  cijfers van 1.5.10 zijn het volledige verhaal.

In v0.134.0 verwerkt:
- **B412 - het getal stond niet in de songtekst.** De gebruiker meldde dat
  "45" ontbrak in de weergave terwijl Whisper het wel had gevonden, en dat
  was letterlijk zo: `load_lyrics` hield per teken alleen `isalpha` over,
  dus "Another 45 miles" werd "Another miles". Niet ongekoppeld maar
  afwezig - onzichtbaar in elke weergave, want het woord bestond nooit. Op
  dat lied elf woorden: 279 in het bestand, 268 in de koppeling, en in het
  koppelverslag elf keer een gat van 0,89 s tussen "Another" en "miles".
  Het wrange is dat `cluster.phonetic_key` getallen al sinds B274 afhandelt
  ("500" wordt uitgeschreven); die machinerie kreeg alleen nooit een getal
  te zien. Bij het repareren kwam er nog een fout onder vandaan: het
  Nederlands werd op zijn Engels aan elkaar geplakt, dus 45 werd
  "veertigvijf" met sleutel `fetikfif`, terwijl het gezongen
  "vijfenveertig" `fifenfetik` geeft. Een sleutel die nooit kan matchen is
  erger dan geen sleutel, want het lijkt alsof het geregeld is.
- **B411 - een refrein erbij kostte de hele timing.** De redding van B407
  werkte alleen bij een gelijk aantal regels; daarboven ging alles weg. Dat
  klopt voor de gewijzigde regels en niet voor alle andere, en juist bij
  een refrein achteraan is alles ervoor nog precies goed. De regels worden
  nu op tekst herkend (`difflib`): wie hetzelfde leest houdt zijn eigen
  lettergrepen, wat er ook omheen schuift. Een nieuwe regel krijgt de
  ruimte tussen zijn buren, gelijk verdeeld - niet goed, maar geplaatst en
  in de editor te repareren zonder overnieuw te beginnen.
- **B413 - één map per project.** De kiezer onthield de laatste map per
  invoersoort, terwijl de werkwijze van de gebruiker andersom is: eerst
  alles van één lied bij elkaar zetten, dan de bestanden één voor één
  aanwijzen. Nu onthoudt het project de laatst gebruikte map, ongeacht
  welke invoer; heeft een soort zijn eigen map al, dan wint die. De
  thuismap blijft de laatste terugval, want een lege startmap is niet
  neutraal (B388).
- **B414 - de lege plekken in de tekstbaan.** Een klik naast een blokje
  deed helemaal niets: geen selectie, geen speelkop. Dat is de breedste
  plek op het scherm en precies waar je kijkt als je een regel zit te
  timen. Alleen de lege plekken - een blokje raken blijft dat blokje
  pakken.
- **B415 - twee stappen, twee kolommen.** In de eerste opzet van B408 zaten
  `sanitize_timing` en het aanschuiven op de zanginzet samen in de kolom
  "zinnen", en dat zijn twee stappen die allebei een regel kunnen inkorten.
  Nu elk een eigen kolom.
- **B416 - 1.5.11d wordt een nachtproef.** Eén lied meten was goedkoop en
  zei niets over de rest: het lied met het grootste gat is per definitie
  het minst representatieve lied dat er is, en elke knip maakt een nieuwe
  rand, dus op een lied met weinig te winnen kan knippen juist schade doen.
  Nu de vier grootste gaten. En de proef meldt de zang NA de laatste
  tekstregel apart: op "Lied M" ontbreekt het laatste refrein
  bewust in de tekst (akoestisch, op gevoel gespeeld, de woorden zijn
  lastig te verstaan), en die seconden als "niet gehoord" tellen geeft
  Whisper de schuld van een gat dat de tekst zelf heeft.

Wat de meting van deze dag opleverde, voor het archief:
- **B408 heeft de verdachte vrijgesproken.** De nieuwe kolommen laten zien
  dat regel 6, 12, 14, 18, 30 en 32 al te kort zijn als ze uit de koppeling
  komen (1,11 / 1,18 / 1,25 / 1,57 / 0,99 / 1,02 s) - dus niet in
  `sanitize_timing`, en zeker niet in de energie-woordtiming waar ik naar
  wees. Terwijl `steps.coupling.original_items` voor diezelfde regels het
  goede getal heeft (28,77-32,25 voor regel 6). Het verlies zit dus in
  `couple_timing`, tussen de originele zinsspannes en de karaokeregels die
  eruit volgen. Dat is de volgende reparatie, en nu een klein stuk code in
  plaats van een middag zoeken.
- **B406 werkt in het echt.** De automatische timing van dat lied ging van
  49 lettergrepen met lengte nul naar nul.

In v0.135.0 verwerkt:
- **B418 - het streepje was geen woordgrens.** De gebruiker dacht dat
  leestekens al genegeerd werden, en dat klopt voor de sleutel: `-la` en
  `la` geven allebei `la`, `e-mail` en `email` allebei `email`. Wat niet
  klopte is de grens. "La-la-la-la-la," bleef één woord met sleutel
  `lalalalala` terwijl Whisper er vijf losse `la`'s van maakt, dus die
  twee konden elkaar nooit raken - precies dezelfde kwaal als de 45.
  Zijn eigen uitleg gaf de oplossing: hij schrijft die streepjes omdat
  het clustertje ritmisch bij elkaar hoort en tellen dan makkelijker is,
  dus het zijn losse klanken en geen samenstelling. Geteld over alle
  zeventien liedjes: 186 woorden met streepje, 132 pure herhalingen
  (`na-na-na`, `la-la-la`) en de overige 54 zijn `woah-oh`, `diggi-loo`,
  `mm-hm`, `zwart-te` - ook gezongen lettergrepen. Geen enkel echt
  samengesteld woord. En zijn tegenwerping over "lala" aan elkaar is al
  gedekt: `_align_core` heeft `_lyric_pair_sim` (twee tekstwoorden tegen
  één transcriptwoord) en de tegenhanger, wat ook het e-mail-geval vangt.
- **B417 - de pins schuiven mee, en dit had gisteren al mee gemoeten.**
  Handmatige woordkoppelingen bewaren POSITIES in de woordenlijst. B412
  zette de cijfers terug in die lijst en verschoof daarmee elke pin
  erna, stilzwijgend: bij "Lied M" 268 naar 279 woorden met
  het eerste getal op positie 65, dus drie van de zeven pins verkeerd,
  en bij "Lied G" vijf van de dertien. Er ging niets
  verloren - de pins stonden er nog, ze werden alleen tegen een langere
  lijst gelezen - maar het gebeurde zonder één regel in het logboek, en
  dat is de vervelendste soort. De omzetting telt bewust geen cijfers en
  streepjes: dat zou een regel zijn die bij elke volgende wijziging van
  de woordindeling uitgebreid moet worden en precies één keer fout gaat.
  In plaats daarvan worden beide lijsten gebouwd - de oude vorm uit
  `words_before_b418`, de nieuwe uit `split_word` - en tegen elkaar
  gelegd. Zelfde gedachte als `_PIN_LAYOUT_FULL`, dat sinds B309 hetzelfde
  doet voor de andere kant van de pin.
- **B419 - ik mat het gereedschap, niet de methode.** De gebruiker zei
  dat die verdubbeling van de transcriptietijd wel zou meevallen, en hij
  had gelijk om een reden die geen van ons beiden had genoemd. Over 35
  stukken van de nachtproef: **0,75 s rekentijd per seconde audio plus
  28,9 s vaste kosten per stuk**. Een fragment van 4,3 s kostte 20 s en
  een van 30 s kostte 56 s; dat eerste kan geen decoderen zijn. De oorzaak
  staat in `tools/whisper_probe.py`, dat bij elke aanroep een verse
  `WhisperModel` bouwde, terwijl `modules/whisper.py` het model al in
  `_MODEL_CACHE` houdt. Van de ~450 s van een knipdraai was ruim 290 s
  modellen laden. Doorgerekend voor Viva: tien stukken, 236 s audio
  inclusief overlap maal 0,75 is 177 s plus één keer laden - tegen 208 s
  voor de hele-liedjesdraai. Knippen kost dus ongeveer hetzelfde, niet het
  dubbele. Dat maakt ook elke volgende nachtproef fors goedkoper.
- **B420 - "niet gehoord" beloont een lus.** Dat getal meet of een gat
  GEVULD is, en een Whisper-lus vult een gat voorbeeldig; de maat beloont
  dus precies de fout die hij moet betrappen. Twee keer gebeurd: een draai
  in het Spaans die het beste scoorde, en een knipdraai met 456 woorden
  waarvan ruim de helft verzonnen. Beide keren viel het op doordat de
  gebruiker iets zag of ik met de hand telde, niet doordat de proef het
  meldde. Nu staat er per variant welk aandeel van het gehoorde in de
  songtekst voorkomt, vergeleken op de fonetische sleutel - dezelfde
  notie van "hetzelfde woord" die de koppeling gebruikt. En de
  samenvoeging kiest zijn basisdraai daar mede op, want anders wordt een
  lus vanzelf de basis en blijven juist zijn verzinsels staan.

Wat de nachtproef opleverde, voor het archief:
- **Knippen werkt, op alle vier de liedjes.** Onverstane zang van 250,7 s
  naar 140,4 s, en met samenvoegen naar 91,9 s - **63% eraf**, van 33,9%
  naar 12,4% van de gezongen tijd. De samenvoeging vanaf de beste draai
  in plaats van vanaf "huidig" bracht Viva van 36,5 naar 17,7 s.
- **De offset is een gok.** Op Lied_O maakt offset 10 het 28,5 s
  SLECHTER dan niets doen. Het verhaal van één lied ("de offset haalt
  26 s terug") gold niet over vier.
- **En bijna een vals alarm van mijn kant.** Lied_T springt
  van 238 naar 552 woorden met 349 herhalingen, wat er precies uitziet als
  een lus. Mijn eerste telling zei 31,5% in de tekst. Dat was mijn eigen
  splitser: de tekst schrijft "La-la-la-la-la," aaneen en Whisper "-la"
  los. Netjes gesplitst is het 95,3% - hóger dan de huidige draai. Alleen
  Lied_O zakt (81,7 naar 76,0), en daar zijn de onbekende woorden
  onzinlettergrepen die het lied sowieso vol staat.

In v0.136.0 verwerkt:
- **B422 - het delen van het model kostte meer dan het opleverde.** De
  reparatie van B419 haalde de 28,9 s laadtijd per stuk weg en zette er
  een wachtrij voor terug: één `WhisperModel` met `num_workers=1`
  behandelt één transcriptie tegelijk, dus twee werkplekken stonden om de
  beurt te wachten. Aan dezelfde nachtproef: 3902 s werd 5522 s, en per
  venster van dertig seconden 44-52 s tegen 20-27 s daarvoor. Precies
  verdubbeld, wat taken-om-de-beurt eruit ziet. De gebruiker zag het in
  de taakbeheerder als vier bezette kernen terwijl er twee draaien
  liepen. Nu krijgt het model `num_workers` en `cpu_threads` mee uit
  dezelfde som die de werkplekken telt. Dat die getallen tot nu toe
  toevallig overeenkwamen met de stille standaard van de bibliotheek
  (vier threads) was geluk; het staat nu op één plek opgeschreven.
  Geruststellend: de uitkomsten waren niet aangetast - "huidig" op
  Lied_S was tussen beide draaien identiek tot op het segment.
- **B423 - de knipstukken door de wachtrij.** De staande afspraak van de
  gebruiker, in zijn woorden: zet zoveel mogelijk in een queue. De tien à
  elf stukken van een knipdraai liepen strikt na elkaar, 400 tot 640 s
  per lied, verreweg het langste losse onderdeel van de nachtproef.
- **B429 - een modelwijziging wist de handmatige timing.** Dit heeft de
  gebruiker echt geld gekost: hij opende Lied_Q, het programma zag
  `config:models` anders staan dan bij de vorige keer, en gooide de
  timing weg. Zonder vraag, zonder logregel. Een model verandert wat de
  AUTOMATISCHE koppeling van het lied maakt; het zegt niets over waar de
  gebruiker zijn zinnen met de hand heeft neergezet. Hetzelfde geldt voor
  een bewerkte karaoketrack: andere audio, dezelfde zinnen. De redding
  van B407/B411 gold alleen bij een gewijzigde karaoketekst en geldt nu
  bij elke wijziging die de timing zou weghalen, met de oorzaak in het
  logboek erbij. Klopt de timing volgens de gebruiker niet meer, dan
  maakt 2.2 hem opnieuw - dat is nu een keuze in plaats van een
  mededeling achteraf.
- **B428 - dempen en terugzetten zijn twee dingen.** Stap 1.4 eiste een
  clusterselectie, terwijl "terug uit het origineel" via
  `restore_fragments` loopt en met dempen niets te maken heeft. Wie één
  toeter wilde terugzetten moest daardoor clusters aanvinken die hij niet
  gedempt wilde hebben - en na een verse transcriptie zelfs opnieuw door
  stap 1.3 voor een selectie die daarna werd weggegooid.
- **B427 - de wacht verwierp een goede draai.** Het zuiverheidspercentage
  rekende alleen tegen de songtekst. Op een lied waar het origineel
  "na-na-na" zingt en Whisper "la" schrijft kwam de knipdraai op 32% en
  werd hij als basis geweigerd, terwijl die woorden gewoon goed gehoord
  waren en alleen anders gespeld. De karaoketekst van datzelfde lied
  schrijft die passage als "la-la-la". Twee teksten van één lied, en
  samen beschrijven ze wat er gezongen mag worden; voor een wacht is te
  mild beter dan te streng.
- **B424/B425 - twee varianten voor twee openstaande vragen.** "knippen
  (globale prompt)" knipt precies zoals gewoonlijk maar geeft elk stuk
  dezelfde ontdubbelde woordenlijst, zodat het verschil met "knippen"
  alléén de prompt per stuk is. Dat beslist of het knippen op een eerste
  transcriptie moet wachten, en dus of stap 1.1 in twee rondes uiteen
  moet vallen of in één wachtrij past. "knippen + vad" is de combinatie
  die nog niemand gemeten heeft: 1.5.11c mat VAD op het hele lied,
  1.5.11d knippen zonder VAD, en het zijn geen alternatieven - VAD haalt
  stilte weg, knippen snijdt er juist in.
- **B430/B431 - het paneel ruimt zichzelf op.** De knopjes van de
  werkplekken bleven na een afgeronde actie staan met de namen van de
  laatste projecten. De opruimroutine bestond al en draait ook na elke
  actie; de knopjes zijn er bij B402 later bij gekomen en waren er nooit
  in opgenomen. En de grijze uitlegregel onder 2.4 is weg: wat er stond
  staat uitgebreider in `docs/karaokevideo_werkwijze.md`.

Werkafspraak erbij (van de gebruiker):
- **Zet zoveel mogelijk in een wachtrij, zwaarste taak eerst.** Bij twee
  Whisper-banen zijn dat acht van de twaalf kernen in plaats van vier.
  Geen vaste rondes met vaste banen: een taak mag de rij in zodra zijn
  voorwaarden klaar zijn, en een vrijkomende plek pakt vanzelf het
  volgende stuk. Reken er daarbij op dat niet elk liedje hetzelfde is -
  bij een echte karaokeversie (niet uit Demucs gemaakt) is de
  karaoke-transcriptie geen wissewasje maar een volle draai.

In v0.137.0 verwerkt:
- **B435 - de logica-controles draaien tussen de modellen door.** Het idee
  is van de gebruiker en het dekt een blinde vlek af die ik zelf niet had
  gezien: de gewogen fout weegt alleen regelBEGINS. Een model kan die met
  rust laten en ondertussen alles binnen de regel slopen - lettergrepen
  zonder eigen moment, een heel woord op een tijdstip, tijden
  achterstevoren - en dat verdwijnt in een gemiddelde. Precies het soort
  schade dat de gebruiker wel in de video ziet; B406 is zo ontdekt, door
  hem en niet door de meting. Elke meting draait nu `timing_checks.sanity`
  mee (alleen de vormcontroles, geen audio, goedkoop genoeg voor een paar
  honderd rondes) en elke proef sluit af met "geen enkel model liet een
  kapotte regel achter" of met een tabel: project, welke modellen anders
  stonden, en wat er mis is.
- **B436 - de tijdmeting weet nu wanneer ze niet klopt.** De gebruiker had
  ander werk op de machine en merkte dat de tijden scheef stonden. Naast
  de wandklok wordt nu de rekentijd van het proces bijgehouden; lopen die
  ver uiteen, dan schrijft de proef zelf in het log dat dit getal niet
  tegen een eerdere draai gelegd kan worden.
- **B437 - drie tellingen erbij, en de uitgeputte proeven uit.** De
  tellingen hangen onder 1.5.7 en niet als elfde actie, want het plafond
  van tien is er met reden. Wat ze beantwoorden: welke tekstwoorden nooit
  koppelen (twee keer bleek dat een hele woordsoort die principieel niet
  kon matchen - cijfers, streepjes - en beide keren vonden we het met de
  hand), hoe vaak een lettergreep lang wordt aangehouden, en of blokken
  die terugkomen even lang duren. Die tweede leverde meteen iets op:
  **1005 lettergrepen** over veertien liedjes, stuk voor stuk klinkers,
  terwijl het veld `held` - dat de videorenderer al kan tonen - over alle
  projecten nergens op waar staat. Er is dus een lamp zonder schakelaar.
  En aan de andere kant: zeven van de elf vensterproefvarianten gaven
  twee draaien op rij een bit-identiek antwoord (26 segmenten, 196
  woorden, 1 woord in het gat) en de promptlengtes beantwoordden B391
  opnieuw met nee. Samen ruim een half uur per nachtdraai voor kennis die
  al op papier stond. Ze zijn UITGEZET, niet weggegooid - dezelfde
  behandeling als een model, zodat het idee leesbaar blijft en in een
  regel terug kan.
- **B438 - mijn eigen taalachterstand.** De regel is duidelijk: een
  bestand dat substantieel wordt aangepast gaat in dezelfde beurt
  helemaal om. Ik heb `pipeline.py`, `gui.py`, `dependencies.py` en
  `model_register.py` vier versies lang bewerkt en het Nederlandse
  commentaar laten staan - 135 regels - en er ging nooit iets rood, want
  `test_language_guard.py` kijkt alleen naar functie- en klassenamen.
  Precies het patroon waar die bewaking ooit voor gemaakt is, en ik liep
  er zelf in. Nu omgezet, met een test die ook het commentaar bewaakt.

Wat de zelfcontrole verder opleverde:
- Elke bouw sinds v0.133.0 had een letterlijke "gogo", en de ingrepen in
  de json-bestanden waren allemaal expliciet gevraagd.
- Twee dingen deed ik zonder te vragen: een veiligheidskopie naast
  `Lied_L` en mijn eigen tijdelijke archieven in `C:/Muziek`. Voor
  dat laatste is nu een afspraak (`_to_delete`), het eerste had ik moeten
  vragen.

## Voor publicatie beslissen

Hier staat alles wat er **tijdelijk** in zit. Dat is code die is gemaakt
om iets te kunnen onderzoeken op de machine van de gebruiker, niet om
mee te gaan naar een publicatie (git of anderszins). Bij het klaarmaken
van zo'n publicatie hoort per regel de vraag gesteld te worden: gaat dit
mee, of gaat het eruit?

Er is precedent voor het vergeten ervan: B136 was ook zo'n tijdelijke
knop ("Modellen vergelijken", v0.65) en dat die er in v0.78 weer uit ging
was meer geluk dan wijsheid - hij stond nergens als openstaand besluit.
Vandaar deze lijst, plus een test die rood wordt zodra er een bestand met
een `TIJDELIJK`- of `TEMPORARY`-markering bijkomt dat hier niet genoemd
wordt. Die tweede is er bij B465 bijgekomen: de code is intussen naar het
Engels omgezet en de bewaker zocht alleen het Nederlandse woord, dus keek
hij langs een tijdelijke functie in `pipeline.py` heen die er al maanden
stond.

Op 25 augustus 2026 zijn deze beslissingen genomen; hieronder staat
per regel wat het wordt in plaats van wat de vraag was. Twee regels zijn
al uitgevoerd omdat hun vraag beantwoord was (B512).

**Stand na v1.0.0 (B542):** de publicatie op GitHub is er, en daarbij is
gevraagd of dit het moment was. Het antwoord: het testpaneel en alles wat
eraan hangt blijven erin - zesenzestig van de zesennegentig testbestanden
importeren `test_panel`, dus eruit halen sloopt de testsuite, en de
gebruiker heeft het gereedschap nog dagelijks nodig. Het meetwerk zelf is
wél buiten de repo gehouden, via `.gitignore`. De vraag "gaat de code
eruit" staat daarmee nog open voor een volgende keer; de vraag "gaan de
meetgegevens mee" is beantwoord met nee.

| onderdeel | bestand(en) | waarom het er is | het besluit |
| --- | --- | --- | --- |
| Testpaneel achter knop 1.5 | `modules/test_panel.py`, de knop in `modules/gui.py` | Genummerde testfuncties (1.5.1 t/m 1.5.10, plus de zware bak 1.5.11) die op de machine van de gebruiker draaien in plaats van bij mij: cache vullen, ijkset-status, projectcontrole, ontbrekende herhalingen, de meetlat, uniek-tegen-herhaald, de woord- en lettergreeptoetsen, de weglaatproef en de grote proef. | **Bij publicatie helemaal eruit**, met alles wat eraan hangt. Het is gereedschap voor de bouw, niet voor de gebruiker. Tot die tijd blijft het staan. |
| Cache aanvullen (1.5.1) | `modules/pipeline.py` (`projects_without_cache`) | Zoekt projecten waarvan de transcriptiecache weg is, zodat de meting niet op de ruwe transcriptie van vóór de forced alignment terugvalt. | **Mee met het paneel eruit.** |
| Meethistorie | `modules/test_history.py`, `docs/testhistorie.json` | Houdt per actie, project en versie bij wat er gemeten is, zodat een onveranderd project overgeslagen kan worden. | **Eruit bij publicatie.** Meetwerk op één ijkverzameling is geen documentatie; het blijft alleen bij de gebruiker staan. |
| Testverslagen | `docs/verslagen/` | De regels van elke gedraaide testactie, met tijd en alarmen (B524), sinds B534 met datum, tijd, versie en bereik in de naam zodat geen enkele draai de vorige overschrijft. Daar staan ook de gedateerde kopieën van `modelmatrix.md` en `modelcombinaties.md`. Het logvenster staat op de machine van de gebruiker en die tekst kan hij niet doorgeven; deze bestanden wel. | **Eruit bij publicatie.** Meetwerk, geen documentatie; gaat nooit mee in een oplevering. De gebruiker gooit de map zelf leeg. |
| Verslag van de zware proeven | `docs/modelcombinaties.md` | Uitkomst van 1.5.11: alle combinaties binnen een cluster en de zoektocht naar de beste stand. | **Eruit bij publicatie**, zelfde reden. |
| Het verslag van de grote proef | `docs/modelmatrix.md` | Uitkomst van 1.5.11: wat elk model waard is per niveau, per project, in paren en in omgekeerde volgorde. | **Eruit bij publicatie**, zelfde reden. |
| ~~Vensterproef 1.5.11c~~ | ~~`test_panel.window_trial`~~ | Acht Whisper-instellingen op het grootste gat. Stond er om één vraag te beantwoorden. | **Uitgevoerd in v0.146.0**: B454 had hem drie keer met "nee" beantwoord, hij stond uit sinds v0.144.0, en met het besluit hierboven was er geen reden meer om hem te bewaren. |
| ~~Bijstelknop en 1.5.11f~~ | ~~`pipeline.refit_syllables`, `test_panel.refit_trial`~~ | De knop van B497 en de meting die moest zeggen wat hij waard was. | **Uitgevoerd in v0.146.0**: de meting gaf +0 ms over achttien projecten, dus knop en proef zijn allebei weg. De cijfers staan bij B512. |

## Testdata (voorbeelden die zijn gebruikt)

- Per Spoor (NL, lastige/ongelijke timing).
- Freed from desire → parodie "Lied T" (crowd-refreinen,
  losse karaoke-mp3).
- Formidable (Frans), Oerend Hard (dialect).

In v0.138.0 verwerkt:
- **B439 - de modelmatrix mat tien versies lang niets.** Dit is de vondst
  van deze ronde en hij is onaangenaam, want het verslag zag er goed uit.
  Sinds B396 (v0.128.0) meet de ijklat in losse processen, en een
  kindproces bouwt zijn wereld op uit de modelstand die het meekrijgt.
  `big_trial` en `omission_trial` zetten hun variant echter nog altijd met
  `setattr` op moduleglobals in het OUDERproces, en `_model_state_now()`
  leest `model_register.enabled()` - het overrides-woordenboek, dat van
  die setattr niets weet. Elke ronde vroeg dus dezelfde stand op. Vandaar
  `+0,00` bij alle twintig modellen, alle 190 paren en beide volgordes, en
  vandaar een gewogen fout die op de honderdste na gelijk bleef. Niet B410
  maar B396 heeft dit gebroken; B410 heeft juist de goede route gebouwd
  (modelcodes, voor 1.5.11b) en die is alleen nooit hierheen doorgetrokken.
  Het bewijs stond in de rapporten naast elkaar: 1.5.11b, dat via
  `_measure` met codes loopt, gaf gewoon verschillen (3,20 → 2,80), terwijl
  1.5.9 en 1.5.10 plat op nul lagen. Twee routes naast elkaar, één ervan
  nooit meeverhuisd.
- **B439 - en waarom geen enkele test dit zag.** Er waren tests op elk
  onderdeel: dat de vervangers de echte functies passen, dat de modellen
  worden teruggezet, dat er na elke variant wordt weggeschreven, dat elke
  lus naar de stopknop kijkt. Geen enkele vroeg of twee varianten
  daadwerkelijk van elkaar verschillen. Die staat er nu, en hij is de kern
  van deze release: de proef wordt gedraaid met een onderschepte
  `measure_rows` en de meegestuurde standen worden vergeleken - alle
  identiek is rood. Plus een tweede die controleert dat elk model met
  precies zijn eigen code omgezet wordt en een derde die telt dat de paren
  er twee tegelijk omzetten.
- **B439 - een volgorde reist als naam.** De twee volgordeproeven zijn
  geen modellen: ze verwisselen hele functies, en een functieobject
  overleeft het beitsen naar een kindproces niet. Daarom zijn ze verhuisd
  naar `modules/model_orders.py` en reist de NAAM; het kind bouwt de
  vervangers zelf. Ze konden niet in `test_panel.py` blijven staan, want
  dat bestand importeert PySide6 bovenaan en een meetproces heeft niets te
  zoeken bij een widgetbibliotheek.
- **B439 - de seriële terugval liet de variant staan.** Onderweg
  gevonden: `_measure_one` is geschreven voor een kind, dat weggegooid
  wordt, en zet dus de modelstand zonder iets terug te leggen. Op de
  seriële route draait diezelfde functie in het OUDERproces, en dan loopt
  het programma daarna door op de laatste variant die het gemeten heeft.
  Die route komt alleen op een dichtgetimmerde machine voor, en juist daar
  was het onvindbaar geweest. Nu wordt de stand eromheen bewaard en
  teruggezet, met `model_register.current_settings()` als tegenhanger van
  `apply_settings`.
- **B440 - een kapot verslag mag niet als uitslag lezen.** 1.5.11a leest
  zijn clusters uit de parentabel van 1.5.10 en concludeerde uit 190 keer
  nul dat geen enkel paar elkaar raakt. Dat stond maandenlang als
  bevinding in `docs/modelcombinaties.md`. De clusterproef weigert nu een
  matrix waarin élk verschil exact nul is - een echte meting geeft dat
  nooit 190 keer op rij - en het verslag draagt voortaan het versienummer
  waarmee het gemaakt is. De twee bestaande verslagen zijn met een blok
  bovenin als ongeldig gemarkeerd, inclusief welke secties er wél kloppen:
  de dekkings- en woord/lettergreeptabellen draaien over threads in
  hetzelfde proces, daar werkt `setattr` wel en daar staan echte
  verschillen in.
- **B440 - en de testsuite overschreef het werk van de gebruiker.** Bij
  het schrijven van bovenstaande viel op dat `docs/modelcombinaties.md`
  telkens leeg terugkwam. Twee tests lopen alle acties van het paneel af
  en leidden alleen `MATRIX_REPORT` om, niet `COMBINATION_REPORT` - dus
  elke `pytest` verving een uur rekentijd van de gebruiker door de
  uitkomst van een leeg testproject, zonder dat iets dat meldde. Per test
  omleiden is precies wat je de vijftiende keer vergeet, dus het gebeurt
  nu voor élke test in `tests/conftest.py`: alles wat naar `docs/` wijst
  gaat opzij. Een test die het echte bestand wil lezen doet dat via het
  pad.
- **B441 - de aangehouden lettergreep, eindelijk gezet.** `Syllable.held`
  bestaat sinds B92 en `video.py` tekent er al even lang een streep onder,
  maar niets zette het veld ooit: 1.5.7 telde over 14308 lettergrepen
  precies nul. De regel is die van de inventarisatie, ongewijzigd, want
  dat is de regel waar de 7,0% en het "allemaal klinkers" uit komen: een
  lettergreep telt als aangehouden bij ≥0,35 s én ≥4× de mediaan van zijn
  eigen regel. Een pauze doet niet mee - die is lang van nature en wordt
  als oplichtende puntjes getekend.
- **B441 - afgeleid en niet opgeslagen, en dat is het hele punt.** Het
  veld wordt herberekend in `load_timing`, wat de stand in het bestand
  ook zegt. Twee redenen: de opgeslagen waarde is in élk bestaand project
  onwaar (het veld werd jarenlang weggeschreven en nooit gezet), en het is
  een oordeel over de spans - rek een lettergreep op in de editor en het
  merkteken moet meebewegen, wat niet kan als het in een bestand
  bevroren zit. Zo krijgen alle zeventien bestaande projecten hun
  aangehouden noten meteen, zonder dat er één `timing.json` wordt
  aangeraakt. Nagerekend op de echte projecten van de gebruiker: 6,0% van
  de lettergrepen, allemaal klinkers, met de 2,39 s 'a' in Lied_S
  bovenaan - exact het geval dat 1.5.7 als langste aanwees. De editor
  herberekent bij opslaan.
  **Let op: de video's zien er hierdoor anders uit** - onder een
  aangehouden lettergreep verschijnt nu een streep.
- **B441 - en dezelfde streep in woorden-koppelen.** Daar komt het merk
  niet uit de timing maar uit de transcriptie zelf: Whisper zegt per woord
  hoe lang het duurde, dus de vraag kan gesteld worden vóórdat er timing
  is. Dat is precies waar het nuttig is - de gebruiker verdeelt daar de
  klemtonen over de karaoketekst, en "dit woord wordt drie seconden lang
  gezongen" is wat hij niet uit de tekst kan aflezen. Geen vulkleur maar
  een streep eronder, dezelfde als in de render: een aangehouden woord is
  meestal prima gekoppeld, en een vulkleur zou zijn echte status
  wegduwen.
- **B442 - het knippen gaat naar productie.** Wat de nachtdraai van
  v0.136.0 mat, nu in het programma: vier liedjes, niet gehoorde zang
  197,7 s voor de enkele draai tegen 71,5 s als de stukken de gaten
  vullen. Twee uitkomsten bepalen de vorm. De winst zit in het KNIPPEN en
  niet in een prompt per stuk (B424: de globale prompt won op twee
  liedjes en stond gelijk op een derde), dus de stukken hoeven niet op een
  eerste transcriptie te wachten - en juist dat maakt één wachtrij
  mogelijk in plaats van twee rondes. En knippen mét VAD was op alle vier
  slechter (B425), dus geen VAD. De hele draai is de zwaarste enkele taak
  en start als eerste, de stukken volgen op aflopende lengte: de regel van
  de gebruiker. Een stuk mag alleen VULLEN - waar de hele draai een woord
  hoorde, blijft dat woord staan. Uit te zetten met
  `chunked_transcription`, en het hangt in de afhankelijkheidsketen zoals
  de forced alignment: aan- of uitzetten geeft een andere transcriptie, en
  alles wat eraan hangt moet dan weg.
- **B442 - en het nieuwe groepje mag de bestaande projecten niet wissen.**
  Het risico bij een nieuwe handtekeninggroep: als een groep die er
  vorige keer nog niet was als "gewijzigd" telt, verliezen zeventien
  projecten hun afgeleide werk bij de eerste start. `sync_input_changes`
  vergelijkt alleen groepen die al in de opgeslagen stand voorkomen, dus
  dat gebeurt niet - maar dat is nu vastgelegd in een test, want het is
  het soort ding dat je één refactor later kwijt bent.
- **B443/B444 - vastleggen waar dit draait, en wat er nieuwer kan.** Het
  verzoek van de gebruiker: er wordt af en toe iets ontwikkeld, en als er
  rare dingen gebeuren wil je dat aan een update kunnen koppelen óf juist
  uitsluiten. Bij elke start worden de versies van de app, Python en
  vijftien pakketten opgeschreven in `docs/pakketversies.json`, maar
  alléén als er iets veranderd is - een regel per start zou binnen een
  maand duizenden identieke regels zijn en dan kijkt niemand er meer in.
  Wat wél verandert krijgt een leesbare regel ("torch 2.3.0 -> 2.4.0"),
  ook verdwijnen en terugkomen. Kost niets: geen netwerk, geen zware
  imports. De updatecheck zelf zit bewust NIET in het programma: pip
  betekent het netwerk en een subproces, en daar mag een start nooit op
  wachten. De bat start hem op de achtergrond, hij bepaalt zelf of hij aan
  de beurt is (hooguit eens per dag), schrijft naar `docs/updates.json` en
  het programma leest dat bij de vólgende start. Het nieuws is dus altijd
  een start te laat, en dat is beter dan een start die hangt op een trage
  spiegelserver. Een verslag ouder dan veertien dagen telt niet meer.
- **B445 - de administratie die van niemand was.**
  `output\settings\project.json` staat sinds eind juli op de machine van
  de gebruiker met de videotitels van "Lied G" erin,
  en klaagde bij elke start dat zijn structuur niet klopte (het bestand is
  van vóór een hernoeming en heeft nog `stappen` in plaats van `steps`).
  Oorzaak: de stand vóórdat er een lied gekozen is heeft geen lied, dus
  `settings_dir` is `output/settings` - en die administratie mocht
  schrijven. Dat mag nu niet meer; lezen wel, anders wordt een bestaand
  bestand ineens onzichtbaar. Het losse bestand wordt bij naam genoemd met
  de mededeling dat het bij geen enkel project hoort en weg mag, en
  verder met rust gelaten: een programma dat stilletjes bestanden opruimt
  in een map die "output" heet, is een programma dat je niet meer
  vertrouwt.
- **B446 - taalachterstand, tweede termijn.** `KaraokeTool.py` en
  `modules/config.py` zijn deze beurt substantieel aangeraakt en dus
  helemaal omgezet. De bewaker uit B438 kijkt nu ook naar de elf bestanden
  die deze release heeft aangeraakt plus het startbestand, zodat de schuld
  alleen kleiner kan worden.

Wat dit betekent voor de metingen:
- De cijfers van 1.5.9, 1.5.10 en 1.5.11a van v0.128.0 tot en met v0.137.0
  zijn onbruikbaar en zijn als zodanig gemarkeerd. 1.5.5, 1.5.7, 1.5.8 en
  1.5.11b t/m d zijn niet geraakt: die lopen over de historie of over
  modelcodes.
- De laatste geldige clusterproef draaide op v0.127.0. 1.5.10 moet dus
  opnieuw voordat 1.5.11a weer iets kan zeggen.
- 1.5.10 zal andere getallen geven in de kolom "vorm" van de sectie Woord
  en lettergreep: `held_not_last` kon nooit afgaan omdat niets `held`
  zette, en gaat dat nu wel doen. Dat is een diagnosekolom, geen alarm -
  `timing_checks.broken()` kijkt er niet naar.

Wat een kritische herlezing van deze release nog opleverde (allemaal
hersteld voordat er iets is opgeleverd):
- **B442 - op Stop drukken had een project zijn handmatige timing kunnen
  kosten.** De eerste versie van `run_over_lanes` slikte `CancelledError`
  per baan en gaf gewoon terug wat er al binnen was. De hele draai
  ontbrak dan stilletjes in het resultaat, `_transcribe_in_pieces` gaf nul
  segmenten terug, en `detect_track` schreef dat als een geslaagde
  transcriptie in de cache, zette de stap op klaar en riep
  `invalidate_after_fresh_transcript` aan - en die keten loopt door tot en
  met `output:timing`. De reddingsactie van B429 zit alleen in
  `sync_input_changes`, dus die had hier niets gedaan. Eén keer Stop op
  het verkeerde moment en een middag handwerk was weg, terwijl de GUI
  netjes "gestopt" meldde. Nu wordt afbreken hard doorgegeven: geen enkele
  halve draai komt er nog uit, plus een vangnet dat weigert terug te geven
  als de hele draai om welke reden dan ook ontbreekt.
- **B439 - het kindproces zette een volgorde neer en haalde hem nooit
  weg.** Precies dezelfde fout als de fout die deze release repareert, één
  proces verderop. `model_orders.apply()` ging ervan uit dat een kind
  wordt weggegooid, maar B399 houdt juist ÉÉN pool in leven voor de hele
  actie. De tweede volgordevariant stapelde dus op de eerste (zijn
  `real_clean` was de eerste volgorde geworden) en elke latere ronde
  zónder volgorde liep er stilzwijgend mee door. Het kind zet nu terug in
  een `finally`.
- **B442 - er werd geknipt op de verkeerde tijdlijn.** `_vocal_windows`
  projecteert de zangvensters op de KARAOKE-tijdlijn, en dat hoort ook zo
  voor alles wat met de karaoketekst werkt. Het knippen werkt echter op de
  zangstem van het ORIGINEEL: het snijdt dat bestand en het beoordeelt
  woordtijden die in dat bestand gemeten zijn. Met een uitlijning erop
  schuiven beide, dus knippen landt naast de echte stiltes en goed
  gehoorde woorden vallen af als "niet op zang". Onzichtbaar bij een
  eerste draai (dan is de projectie de identiteit) en fout bij elke
  hertranscriptie daarna. Er is nu `_original_vocal_windows`.
- **B442 - het hele liedje werd per stuk opnieuw gedecodeerd.**
  `audio_slice` deed een volledige `librosa.load` met resampling per stuk,
  tien tot vijftien keer per liedje. Gemeten: 1,66 s voor het eerste stuk,
  daarna 0,0001 s nu de gedecodeerde audio wordt vastgehouden zolang er in
  geknipt wordt.
- Kleiner: een mislukt stuk telde niet mee in de voortgang (de balk kwam
  dan nooit aan), twee banen konden hun voortgang door elkaar melden
  waardoor de balk achteruit liep, `versions` stond niet in de omleiding
  van `conftest.py`, en terugschakelen naar "geen lied" maakte in de GUI
  alsnog een schrijfbare administratie op de losse plek aan.

In v0.139.0 verwerkt:
- **B447 - de verkleuring veegt, hij klapt niet meer om.** De melding van de
  gebruiker was "iets te schokkerig", en de oorzaak stond in één regel:
  `elif moment >= syllable.start: color = sung_color`. Een fonetisch stukje
  ging in zijn geheel om zodra zijn starttijd voorbij was. Bij korte
  stukjes valt dat mee, maar een aangehouden klinker van twee seconden
  staat twee seconden stil en springt dan in één beeld door - een reeks
  sprongen van ongelijke grootte in plaats van een gelijkmatige veeg.
  Nu geeft `_sung_share` de verstreken breuk en tekent `_draw_swept` het
  stukje twee keer, met de rechterstrook teruggeplakt uit de eerste
  versie. Eén letter in twee kleuren, met de grens precies op de
  veegpositie. Alleen het stukje op de grens betaalt daarvoor; alles
  ervóór is helemaal gezongen en alles erna helemaal niet, en die gaan
  in één keer zoals altijd.
- **B448 - vijftig beelden, en een verschuiving die ook zacht begint.**
  De regelverschuiving bestond al (B242, 0,35 s met demping), maar dat
  waren negen beelden bij 25 per seconde - net weinig genoeg om als
  stapjes te lezen. Bij vijftig zijn het er achttien. En de demping was
  `(1 - t)²`: die landt zacht maar begint op volle snelheid, dus het
  eerste beeld van elke verschuiving was een schok, hoe hoog de
  beeldsnelheid ook stond. Nu een smoothstep, die aan beide kanten
  afremt. De beeldsnelheid in een bestaande `config.json` staat op de
  oude 25 en wordt één keer opgetild, met een markering in het bestand
  zodat dat ook echt één keer is - zonder die markering zou 25 de enige
  waarde zijn die de gebruiker nooit kan bewaren, en dat is het
  tegenovergestelde van een instelling. Audio naar 256 kbps: de
  gebruiker gaf aan dat bestandsgrootte geen bezwaar is, en bij een bron
  die zelf al lossy is scheelt dat een generatie verlies.
- **B449 - de streep weg, op verzoek.** Uit de video, want daar doet de
  verkleuring dat werk al, en uit woorden-koppelen. Wat blijft is het
  merkteken in de klemtoon-editor, en dáár betekent het iets: daar
  liggen het origineel en de karaoke naast elkaar.
- **B450 - de klemtoon-editor rond de opname in plaats van rond een
  spellingsregel.** De gebruiker wees de fout aan: po-lo-NAI-se ligt op
  de derde lettergreep en `apply_default_stress` zegt "po". Die regel
  raadt uit spelling, en een klemtoonlexicon is er niet - `phonetics.py`
  kent klinkergroepen en clusters, verder niets. Maar in zijn eigen
  opzet is dat ook niet nodig, en dat is het aardige eraan: het
  origineel heeft al voorgedaan waar de klemtoon ligt. Per zin staan nu
  twee rijen op één tijdbalk. Je klikt een stukje van het origineel en
  daarna het karaokestukje dat erbij hoort; dat neemt de tijd van het
  origineel over en `fit_between_anchors` schikt de rest van de zin naar
  verhouding, met een ondergrens per stukje en een melding als de zin
  vol zit. De woordgrenzen van het origineel komen uit de forced
  alignment - gemeten - en binnen een woord wordt verdeeld met dezelfde
  fonetische regel die de karaokekant gebruikt. Zo staat er meting waar
  meting is en een model waar die er niet is, en zijn de twee rijen
  vergelijkbaar omdat ze hetzelfde verdeeld zijn.
- **B450 - en de klemtoon zelf blijft met de hand te zetten.** Rechts
  klikken. Dat is er met opzet bij: links koppelen was de nieuwe functie,
  maar de oude weghalen zou iets wegnemen dat in gebruik was.
- **B451 - een gered timing.json neemt zijn maatje mee.** Gevonden bij
  het uitzoeken waarom Lied_Q uit de matrix was verdwenen.
  `output:timing` dekt `timing.json` én `timing_auto.json`, dus een
  invalidatie neemt ze allebei; de reddingsactie van B429 schreef alleen
  de eerste terug. Het handwerk overleefde en zag er goed uit - maar de
  meetlat heeft het PAAR nodig (hij meet hoever de hand de automatische
  timing verschoven heeft) en slaat een project zonder een van de twee
  stilzwijgend over. Lied_Q en Lied_O waren zo uit élke
  meting verdwenen zonder dat er ergens iets stond. Het automatische
  bestand gaat nu door dezelfde `carry_over` als het handwerk, zodat het
  paar op elkaar blijft passen; lukt dat niet, dan wordt er niets
  geschreven - een niet-passend paar is erger dan een ontbrekend, want
  een ontbrekend valt tenminste op.
- **B452/B453 - de rem eruit, de letters erin.** De drempel van twintig
  versies hield in de praktijk alleen 1.5.11a en b tegen (c en d stonden
  al op 1), en hij beschermde precies de uitkomst waarvan we wisten dat
  hij ongeldig was: 1.5.11a draaide voor het laatst op v0.127.0, elf
  versies terug, en die elf versies zijn exact de periode waarin de
  matrix niets mat. Weg ermee. Wat ervoor in de plaats komt is wat de
  gebruiker zelf voorstelde en wat de lichte acties al deden: één keer
  per versie per stand, met een vingerafdruk over de projectbestanden,
  de transcriptiecache en de modelstand - dus een nieuw project draait
  wel, en een gewijzigd bestand ook. Voor 1.5.11a en b is de eenheid de
  hele set, want die meten de set als geheel. En je vinkt voortaan per
  letter aan.
- **B454 - twee proeven uitgezet, niet weggegooid.** 1.5.11c beantwoordde
  B391 drie keer met nee, zes van zijn acht varianten waren al
  gepensioneerd, en op zijn eigen maat wint `current` nu van VAD (31
  woorden / 21,9 s tegen 30 / 16,0). 1.5.11d kostte 3975 van de 4297
  seconden van de hele zware bak - 92% - om elke keer te bevestigen wat
  sinds v0.138.0 in productie draait. Allebei uit zoals een model uit
  gaat: het idee blijft leesbaar en aanzetten is één woord.
- **B455 - de "la la la" die werd gewist.** De gebruiker zag hem
  verdwijnen als hallucinatie "met 50% betrouwbaarheid". Die 50% was
  niet Whisper's zekerheid maar de beste songtekst-match:
  `phonetic_key("la")` is `"la"`, de gelijkenis met `"lang"` is precies
  0,50, en de vloer staat op 0,65 - dus "lijkt nergens op", en met één
  woord onder 0,6 zekerheid gaat het hele segment weg. De oorzaak is een
  gat dat ik zelf half gedicht had: bij B427 stelde ik vast dat één lied
  "na-na-na" zingt terwijl Whisper "la" schrijft en de karaoketekst
  "la-la-la", en dat je voor een bewaker beter te mild dan te streng kunt
  zijn. Dat is toen toegepast op de meting en niet op het filter, terwijl
  een verkeerd oordeel hier geen getal scheeftrekt maar een segment
  wist. Het filter leest nu beide teksten (`lyric_keys`, sinds B442).
  Plus een tweede regel: een segment dat één kort woord herhaalt is
  gezang. Whisper hallucineert plausibele zinnen, geen gezang; drie keer
  hetzelfde korte woord is genoeg om dat te zien.
- **B456 - één niveau voor elke video.** Gemeten op de afgeleverde mp4's
  liepen ze van −12,6 tot −23,6 LUFS: elf decibel, en dus bij elke video
  aan de knop. De zangstemmen lopen nog verder uiteen (−10,5 tot −26,9,
  zestien decibel) en Lied_I en Rood_Witte_Zangers zijn
  al bij de bron tien decibel te zacht. De gebruiker koos eerst −11 en
  liet dat los toen de cijfers kwamen: de harde nummers piepen al tegen
  0 dBFS, dus op −11 moeten alle achttien onder de limiter door met
  uitschieters van 7,1 dB. Op −16 krijgen dertien van de achttien een
  rechte versterking - onaangeroerd - en hoeven de andere vijf hooguit
  2,1 dB inleveren. Vandaar −16, met `linear=true` zodat ffmpeg alleen
  dynamisch wordt waar het niet anders kan, en met de gemeten en de
  haalbare waarde in het log zodat zichtbaar is wélk nummer iets moest
  inleveren.
- **B457 - en de vraag die daaronder ligt, als meting.** Helpt een harder
  gezette zangstem Whisper? De correlatie tussen de luidheid van een stem
  en de fout van dat project is −0,3 - de goede kant op maar veel te
  zwak - en het zachtste lied van allemaal haalde in 1.5.11d juist het
  béste resultaat. Een open vraag dus, en die hoort gemeten te worden en
  niet aangenomen. 1.5.11e draait de zangstem op drie niveaus langs
  dezelfde kolommen als 1.5.11d, en gaat uit zodra hij ja of nee zegt.

Wat een kritische herlezing van deze release opleverde, allemaal
hersteld voordat er iets is opgeleverd:
- **B450 - de koppeling stond achterstevoren.** `couple_timing` bouwt
  `mapping` als `{karaokeregel: origineelregel}` en de twee andere lezers
  in `gui.py` gebruiken het zo; de nieuwe editor pakte het andersom uit.
  Onzichtbaar zolang de koppeling één-op-één is, en fout zodra dat niet
  zo is - precies het geval waarvoor de editor bestaat.
- **B450 - en de inpassing kon tijden achterstevoren opleveren.** De
  editor laat je koppelen in willekeurige volgorde, en twee
  karaokestukjes mogen naar hetzelfde stuk origineel wijzen. Geen van
  beide is een fout om te weigeren, maar allebei gaven een zin met tijden
  die teruglopen - het enige wat die functie belooft nooit te doen. Nu
  worden de ankers op volgorde gelopen, binnen de zin gehouden, en sluit
  een normalisatie af die de belofte afdwingt in plaats van hoopt.
  Nagerekend met zesduizend willekeurige gevallen: geen enkele kapot.
- **B450 - loskoppelen deed niets.** Elke herberekening ging uit van de
  al herberekende tijden, dus een koppeling losmaken kon niet meer terug.
  Samen met "sluiten slaat op" betekende dat: één proefklik en de
  handmatige timing van die zin was permanent weg. De herberekening gaat
  nu altijd uit van de stand bij het openen, en er wordt alleen nog
  opgeslagen op Opslaan - niet op Escape of sluiten.
- **B456 - stilte gaf −inf en daar stierf de render op.** loudnorm
  weigert zijn eigen meting terug ("value out of range [-99 - 0]"),
  terwijl deze stap belooft stil te falen. Een onbruikbare meting is nu
  geen meting.
- **B456 - en elke video kreeg 96 kHz.** loudnorm rekent intern op
  192 kHz en geeft dat door; zonder `aresample` werd alles op 96 kHz
  gecodeerd - twee keer de bestandsgrootte voor geluid waar niemand het
  verschil van hoort.
- **B448 - de beeldsnelheid werd bij élke start opgetild**, waardoor 25
  de enige waarde was die je niet kon bewaren. Nu met een markering, dus
  één keer.

In v0.140.0 verwerkt:
- **B458 - de la-la-la-reparatie kostte 0,56 s, en de meting wees aan
  waar.** 1.5.11a draaide voor het eerst echt, en gaf een uitgangspunt
  van 3,72 s waar de matrix een dag eerder 3,16 s gaf. Dat had ik kunnen
  wegwuiven als een andere projectset, maar er stond een controle in
  dezelfde tabel: met B258/B285 UIT geeft de meetlat in béíde draaien
  exact 3,23 s. Zet het filter uit en er is niets veranderd; zet het aan
  en het is 0,56 s slechter. Daarmee ligt de hele achteruitgang binnen
  dat filter, en dus binnen wat ik er bij B455 aan deed.
  De oorzaak is dat B455 twee dingen tegelijk deed. De kettingregel - een
  segment dat één kort woord herhaalt is gezang - is smal en kijkt alleen
  naar de vórm van het segment; dat was het deel dat nodig was. Maar ik
  liet de karaoketekst óók meetellen in de algemene matchdrempel, en dat
  is de parodie met heel andere woorden. Daardoor vond bijna elk verzonnen
  segment wel érgens een match boven 0,65 en bleef het staan: de la-la-la
  gered en de hallucinaties mee naar binnen. De tweede tekst dient nu
  alleen nog de kettingbeslissing - "na-na-na" in het origineel en
  "la-la-la" in de karaoketekst zijn dan allebei goed - en de drempel
  loopt weer alleen tegen de songtekst.
  Zichtbaar in dezelfde tabel: waar uitzetten van B258/B285 in v0.138.0
  0,07 s kóstte, leverde het in v0.139.0 0,49 s óp. Het filter was van
  licht nuttig naar schadelijk gegaan.
- **B459 - de niveaucontrole wees alle muziek af.** Na de herlezing van
  v0.139.0 voegde ik een bereikcontrole toe omdat stilte `-inf` geeft en
  loudnorm daarop de render meesleurt. Ik eiste −99..0 voor vier waarden
  tegelijk, waaronder `input_lra` - en dat is geen niveau maar een
  dynamiekBEREIK in LU, dus positief bij alles wat op muziek lijkt.
  Gevolg: elke meting kwam terug als "geen meting", en daarmee deed zowel
  de normalisatie in de video als de hele proef 1.5.11e stilzwijgend
  niets. De gebruiker zag het aan de lege kolommen; de video's zouden
  gewoon op hun oude niveau zijn gebleven zonder één klacht.
  Wat het erger maakt: mijn eigen rooktest keurde het goed. Die gebruikte
  een zuivere sinus, en dat is precies het enige signaal met een
  dynamiekbereik van exact 0,0 - de enige waarde die er doorheen kwam.
  Er staat nu een test op materiaal met een zacht en een hard deel, plus
  eentje die vastlegt dat een sinus dat gat was.
  De bereiken zijn nu die van loudnorm zelf, elk apart: niveau en drempel
  −99..0, bereik 0..99, en de piek mag licht boven nul liggen - "Lied M
  " piekt op +0,12 dBTP en dat is een doodgewoon nummer.
- **B460 - 1.5.11e liep op één Whisper-proces.** De afspraak staat sinds
  B396 op twee banen en de gebruiker zag er één. Terecht: ik had de proef
  als een gewone lus geschreven, lied voor lied en niveau voor niveau.
  Nu gaat alles in één wachtrij over `whisper_lanes()`, langste lied
  eerst, en het ffmpeg-werk (de omgezette niveaus) gebeurt vooraf zodat
  de banen alleen nog transcriberen.
- **B461 - het paneel toonde een keuze en bedoelde niets.** De gebruiker
  vinkte a en e aan, b uit, drukte op start en er gebeurde niets. De
  letters openden aangevinkt terwijl 1.5.11 zelf uit stond - zware acties
  beginnen altijd uit - en op start wordt alleen naar dat ene vinkje
  gekeken. Het paneel liet dus "a, b, e aan" zien en bedoelde "niets
  geselecteerd". Nu beginnen de letters uit zoals het nummer, een letter
  aanvinken zet het nummer aan, en het nummer trekt zijn letters mee. Met
  een slotje ertussen, anders zetten de twee elkaar in een kringetje aan.
- **B462 - "gemeten op 16 projecten" waren er 14.** `_measurable_projects`
  keek alleen of er een `timing.json` was, maar de meetlat heeft het paar
  nodig en geeft zonder `timing_auto.json` niets terug. Lied_Q en
  Lied_O stonden zo een dag lang in de kop van het verslag zonder
  ook maar één regel bij te dragen. Ze worden nu bij naam genoemd, met
  wat eraan te doen is. De docstring van diezelfde functie schept
  overigens op dat hij bestaat om precies dit soort meetellen-zonder-
  meten te voorkomen - één niveau lager zat het er gewoon nog in.
- **B463 - en het ontbrekende bestand is terug te maken.** De automatische
  timing is geen handwerk: het is wat de koppeling oplevert, en de
  meetlat rekent hem intern bij elke meting toch opnieuw uit. Dus kan hij
  ook opnieuw geschreven worden, en dat gebeurt in 1.5.1 - de stap die
  klaarzet wat de meting nodig heeft. `timing.json` wordt daarbij niet
  geopend; dát is wel handwerk. Weigert bij een ander aantal regels dan
  de handmatige timing: een paar dat niet op elkaar past is erger dan een
  ontbrekend, want een ontbrekend valt tenminste op.

Wat 1.5.11a opleverde, nu hij eindelijk kon:
- Eén cluster van acht modellen, 256 combinaties. De sterkste enkele
  effecten zijn B332 frase-periode (+1,35), B329/332/340 ankertoets
  (+1,18) en B329 referentieduur (+0,70) - allemaal het aanzetten waard
  en dat staan ze ook.
- De wisselwerking die v0.115.0 al vermoedde is nu hard: B313 +
  B329/332/340 samen uit geeft 6,19 s waar los opgeteld 4,22 verwacht
  werd. Die twee zijn elkaars vangnet.
- De beste gevonden stand was B213 + B258/B285 + B377 anders gezet, op
  2,99 s. Daar zit B258/B285 in, en dat is precies het filter dat door
  B458 verandert - dus die uitkomst moet opnieuw gemeten worden voordat
  er iets mee gedaan wordt.

In v0.141.0 verwerkt:
- **B464 - de kettingregel stelde precies de verkeerde vorm vrij.** Bij
  B455 schreef ik op dat Whisper plausibele ZINNEN verzint en geen
  gezang, en daar bouwde ik een vrijstelling op: een kort woord dat drie
  keer achter elkaar staat is zang. Die aanname is fout. Een
  herhalingslus is juist een van Whispers handtekening-hallucinaties -
  op een instrumentaal stuk produceert hij "la la la la la" zonder dat
  er iets gezongen wordt. Ik had dus een regel gemaakt die de meest
  voorkomende hallucinatie expliciet beschermde.
  De meetlat wees het aan, en wel binnen elke draai afzonderlijk, zodat
  de projectset er niet toe deed: het filter was +0,07 s waard vóór
  B455, -0,49 erna, en -0,40 na de eerste reparatie van B458. Die eerste
  reparatie haalde er dus maar 0,09 van de 0,56 af; de rest zat in de
  kettingregel zelf.
  Wat de la-la-la van de gebruiker onderscheidt van een lus is dat híj in
  de tekst ook herhaald staat - hij schrijft "la-la-la" of "na-na-na" op
  waar een passage echt gescandeerd wordt, en een woord dat één keer
  gezongen wordt staat er één keer. Vandaar `chanted_keys`: alleen
  lettergrepen die in de songtekst of de karaoketekst aaneengesloten
  herhaald voorkomen worden vrijgesteld. Eén van de twee teksten is
  genoeg - het origineel mag "na-na-na" zingen waar de karaoketekst
  "la-la-la" schrijft - maar zonder tekst is er geen vrijstelling meer.
- **B465 - video's opnieuw maken, op verzoek.** Een tijdelijke actie
  1.5.12: elk project dat al een video heeft krijgt er één bij met de
  instellingen van nu, naast de bestaande. Allemaal onder hetzelfde
  nummer `_3`, ook waar een project er nog maar één had - `next_video_
  target` zou het eerste vrije nummer pakken en dan krijgt het ene
  project een `_2` en het volgende een `_3`, en dan is niet meer te zien
  welke bestanden uit deze lichting komen. Overschrijft nooit: staat het
  nummer al bezet, dan wordt het project overgeslagen en gemeld.
  Hij doet niet mee met "alles aanvinken". Die uitzondering bestond
  alleen voor zware acties; `TestAction` heeft er nu een tweede vlag bij
  voor traag-maar-geen-meting, want één klik op "alles" hoort nooit een
  uur video's te gaan renderen. Om dezelfde reden telt hij niet mee in
  het plafond van tien gewone acties.
- **B465 - en de bewaker op tijdelijke code keek langs het Engels heen.**
  Er staat een test die rood wordt zodra er een bestand met een
  `TIJDELIJK`-markering bijkomt dat niet op de publicatielijst staat.
  Die zocht alleen het Nederlandse woord, terwijl de code bij B438 en
  B446 naar het Engels is omgezet - dus stond er in `pipeline.py` al
  maanden een `TEMPORARY`-functie die nergens als openstaand besluit
  genoemd werd. De bewaker kent nu beide woorden en de lijst is
  aangevuld.
- **B466 - zeg wát er mis is.** De weigering om een automatische timing
  te maken meldde "ander aantal regels" en daar kun je niets mee. Nu
  staan de twee aantallen erbij, en dan is het meteen duidelijk:
  Lied_O heeft 55 handmatig getimede regels tegen een
  karaoketekst die er 41 oplevert. Dat is geen fout in de reparatie maar
  een project waarvan het handwerk ouder is dan de tekst, en dat kan
  alleen de gebruiker oplossen.
- **B467 - twee klokken naast elkaar.** De gebruiker merkte op dat
  dezelfde draai in 1.5.11d 49,2 s "niet gehoord" gaf en in 1.5.11e
  68,8 s. Oorzaak: `_vocal_windows` projecteert de zangvensters op de
  KARAOKE-tijdlijn, en dat hoort ook zo voor alles wat met de
  karaoketekst werkt - maar deze proeven transcriberen de zangstem van
  het ORIGINEEL en vergelijken die woordtijden ermee. Twee metingen van
  verschillende klokken dus.
  Het bleek breder dan de twee proeven: ook 1.5.8 en de gatendetectie
  deden het zo. Daarmee is ook die 22% onbezongen zang, het getal waar
  de hele knipdraad mee begon, tegen de verkeerde vensters gemeten
  geweest. Zonder uitlijning is de projectie de identiteit en verandert
  er niets; op elk project dat stap 3 heeft gedraaid lagen de gaten
  naast waar ze echt zitten. Alle vier staan nu op de tijdlijn van het
  bestand dat ze werkelijk beluisteren. Reken erop dat de cijfers van
  1.5.8 en 1.5.11 daardoor verschuiven.

Wat 1.5.11e opleverde, en waarom de vraag nog openstaat:
- Niet gehoorde zang per niveau, over vier liedjes: zoals nu 220,2 s,
  op -16 LUFS 245,3 s, op -11 LUFS 193,5 s. Het hardste niveau wint dus
  op het totaal met twaalf procent en op drie van de vier liedjes.
- Maar het is geen schoon antwoord. Op Lied_T wordt het
  juist slechter (47,1 -> 68,2) en zakt "in tekst" naar 62%, en dat is
  precies de waarschuwing dat de extra woorden verzinsels zijn. En -16
  is op het totaal slechter dan niets doen.
- De aanname waarop de proef gebouwd was, is weerlegd: Groen is met
  -27,0 LUFS veruit de zachtste zangstem en verandert nauwelijks
  (30,6 -> 27,9), terwijl het lied dat het meest profiteert op een
  doodgewone -14,3 zit. Niveau is dus niet wat het verschil maakt.
  Daarom blijft 1.5.11e voorlopig aan en gaat er niets naar productie.

In v0.142.0 verwerkt:

- **B468 - er verdwenen video's van de gebruiker, en de render deed het
  zelf.** Twee keer gemeld ("Lied A", "Lied_P"): een
  bestaande mp4 was weg, terwijl stap 2.4 gewoon weer resultaat gaf. De
  oorzaak zat niet in een opruimactie - er is in de hele keten geen
  regel die een mp4 verwijdert, en `video` is bewust een STAP zonder
  bronnen (B353), dus invalidatie raakt hem nooit. Het was de render
  zelf: `ffmpeg -y ... str(target)` schrijft rechtstreeks op het
  einddoel en kapt dat bestand af op het moment dat het proces start,
  dus vóórdat er ook maar één beeld in zit. Gaat de render daarna stuk,
  of drukt de gebruiker op Stop (`proc.terminate_all` doet een harde
  kill, geen SIGTERM, dus geen moov-atom), dan is de complete oude video
  onherstelbaar weg en blijft er een stuk achter. Er wordt nu naast het
  doel gerenderd (`<naam>.part.mp4`, dezelfde map dus de verplaatsing is
  atomisch) en pas na een geslaagde ffmpeg met `os.replace` op zijn plek
  gezet; élke uitgang ruimt het halve bestand op - een gebroken pijp, een
  ffmpeg die faalt, en ook elke andere fout onderweg (op Windows komt
  een schrijffout niet altijd als `BrokenPipeError` binnen). Het
  bestaande bestand wordt dus nooit aangeraakt tot er een complete
  vervanger is. Lukt het verplaatsen zelf niet - op Windows gebeurt dat
  als de oude video nog openstaat in een speler - dan zegt de melding
  precies dat, en blijft de nieuwe video als `.part.mp4` klaarstaan in
  plaats van verloren te gaan. `existing_videos` slaat die halve
  bestanden over, anders biedt "Open video" een kapot bestand aan.
- **B469 - een eigen uitvoermap kostte bij elke start alle invoermappen.**
  `prune_orphan_projects` (B112) vergelijkt de invoermappen met de
  uitvoermappen en had `root/"output"` hardgecodeerd. Staat er een eigen
  uitvoermap ingesteld (B214), dan is die plek leeg en lijkt élk project
  een wees, waarna `shutil.rmtree` over de invoermap gaat. Bovendien
  draaide de opruiming in `KaraokeTool.py` vóórdat die instelling was
  toegepast. De functie krijgt de uitvoermap nu mee en de aanroep staat
  na het opbouwen van de paden. Er zit ook een rem op: staat er geen
  enkel project in de uitvoermap, dan wordt er niets opgeruimd. "Lege
  uitvoermap" betekent "ik kan het niet zien", niet "het zijn allemaal
  wezen" - zonder die rem zou de eerste start na het verzetten van de
  uitvoermap alsnog alles wissen. Toetsen of de map bestáát is niet
  genoeg: de app maakt hem één regel eerder zelf aan. Dit is niet de oorzaak van B468 (het
  raakt alleen invoer), maar het is wel echt dataverlies en het staat
  gewapend te wachten op de eerste keer dat de uitvoermap wordt verzet.
- **B470 - artiest en originele titel stonden bij vier projecten niet in
  de video.** Ze staan per project in `project.json` (B210) en komen
  alleen in `config.video` terecht via `apply_project_titles`, die op
  precies twee plekken werd aangeroepen: bij het opstarten en bij een
  projectwissel in de GUI. Elke andere renderroute - zoals de
  batch-render van 1.5.12 - rendert dus met de titels die toevallig in
  het geheugen zaten, en die worden bij een projectwissel eerst leeg
  gemaakt. De bestandsnamen bleven wél goed (die vallen terug op
  `display_name`), waardoor het pas in beeld opviel. `run_video` laadt
  ze nu zelf, dus elke route klopt. Tweede helft van dezelfde fout: een
  sleutel die in `video_titles` ontbrak werd overgeslagen, waardoor de
  waarde van het vorige project bleef staan; een titel die dit project
  niet heeft is nu leeg. Wat NIET waar bleek: er is geen instelling voor
  de introduur - `INTRO_MIN_S`/`LEAD_IN_S` zijn vaste 5 s en de intro
  kan in deze code niet korter. Wat de gebruiker zag was dat minimum met
  een lege creditregel eronder.
- **B471 - de originele tekst ontbrak juist waar de koppeling slecht
  was.** Twee oorzaken. (1) B313 gooide de woordtijden van een regel
  zonder ook maar één echte koppeling wég (`del per_line_word_spans`),
  met een goede reden voor de TIMING - een schatting mag geen
  meetwaarde worden - maar de klemtooneditor leest diezelfde lijst, en
  zonder woorden valt `original_pieces` terug op (0.0, 1.0) en plakt de
  zin vooraan het nummer. Ze worden nu bewaard en gemarkeerd
  (`words_estimated`); de koppeling gebruikt nog steeds de gefilterde
  set, de editor alles. (2) Gaf `interpolate_spans` niets terug - geen
  enkele betrouwbare tijd in het hele lied - dan gaf de hele functie
  `None`, en dat betekent verderop een lége originele baan. De tekst is
  er wel, alleen de tijd is onbekend: de editor bouwt die baan nu zelf
  uit `songtekst.txt`, gelijkmatig over de duur verdeeld en met een
  evenredige koppeling, zodat elke zin zichtbaar is en te verslepen. Dat
  vangnet zit met opzet in `editor_originals` en niet in
  `_original_lines_detailed`: de rendertiming heeft voor dit geval al
  een eigen weg (`fallback_even`) en mag niet achter een gok aan gaan
  lopen. De eis van de gebruiker was letterlijk "zelfs niet met 0 of
  onbetrouwbare koppeling, anders kan ik het nooit op de juiste plek
  krijgen".
- **B472 - een karaokezin zonder koppeling had er helemaal geen.** De
  spiegel van B471: `couple_timing` zette alleen een mapping-sleutel
  voor regels die door een van de drie takken heen kwamen. Wie erbuiten
  viel (een los tussenroepje, of alles zodra de blokken niet matchen)
  kreeg geen sleutel - geen `None`, gewoon niets - en dan tekent de
  editor er geen koppellijn bij en is de regel niet te plaatsen. Elke
  karaokeregel krijgt nu een koppeling: naar het origineel van de zin
  ervóór (een tussenroepje hoort bij de regel waar het achteraan komt),
  anders die van de zin erna, anders de eerste. De TIMING blijft
  ongemoeid - een tussenroepje houdt zijn korte slotje (B75).
- **B473 - twee afgebroken zinnen tekenden door elkaar heen.** De
  verticale posities kwamen uit een vaste tabel (0.34/0.56/0.70) en
  niemand mat hoe hoog een zin werkelijk is. Een zin die door
  `_wrap_syllables` over twee rijen loopt is ongeveer 104 px hoog, en
  tussen slot 1 en slot 2 zit 101 px - dus gegarandeerd overlap. De
  sloten stapelen nu: de vaste breuk is de plek die een regel wíl
  hebben, en een hoge zin duwt de regel eronder verder omlaag. Alleen
  omlaag, dus zolang alles op één rij past blijft het beeld hetzelfde.
  Daarmee moest ook de vloeiende regelverschuiving van B242 mee: die
  rekende met één afstand voor álle regels (`slot_y(1) - slot_y(0)`),
  wat klopte zolang de sloten even ver uit elkaar stonden. Met een
  stapel is dat niet meer zo, en één afstand voor iedereen liet de net
  gezongen regel eerst omlaag SPRINGEN en dan omhoog glijden - precies
  de schok die B242/B448 weghaalden. Elke regel begint nu waar hij echt
  stond: op de plek van het slot eronder.
- **B474 - de 3-2-1-teller neemt de plek van de laatst gezongen regel
  in.** Het vermoeden van de gebruiker klopte: tijdens een instrumentaal
  gat werden de drie regels én de teller over vier gelijk verdeelde
  posities geperst (87 px uit elkaar), en daar past geen zin van twee
  rijen tussen. Zijn eigen oplossing is ook de juiste: die bovenste
  regel is klaar en heeft niemand meer nodig. Hij verdwijnt tijdens het
  gat en de teller staat op zijn plek; de regels die nog komen blijven
  staan waar ze altijd staan. Uitzondering, ook door de gebruiker
  genoemd: de teller vóór de allereerste tekst houdt zijn eigen plaats,
  want daar is nog geen gezongen regel om te vervangen. De regel maakt
  pas plaats op het moment dat de teller ook echt in beeld komt (de
  laatste drie seconden); bij een gat van twintig seconden zou er anders
  zeventien seconden een leeg vlak staan. En als het gat voorbij is
  blijft die regel weg: buiten een gat wordt de vorige regel meegetekend
  voor de vloeiende verschuiving (B242), en dat zou hem precies op de
  plek van het cijfer terug laten springen.
- **B475 - een crowdregel schuift gewoon mee.** Een kort tussenroepje
  werd getekend als EXTRA regel onder slot 0 en telde niet mee voor de
  drie zichtbare regels. Daardoor bleef hij staan waar elke andere zin
  naar boven schuift en de vorige eruit drukt, en dat leest als een
  fout. Hij loopt nu gewoon mee in de stroom; rood blijft hij vanzelf,
  want die kleur komt uit `line.crowd` in `_draw_line` en niet uit zijn
  plek op het scherm. Daarmee vervalt ook de vaste crowd-y van 0.45, die
  zelf ook kon botsen.
- **B476 - de twee rijen van één zin staan dichter op elkaar.** Het was
  één getal (`ascent + descent + 2`), dat bovendien op twéé plekken los
  in de code stond - meting en tekening konden dus uit elkaar lopen. Nu
  één `_row_height` met een fractie van de fonthoogte voor de afstand
  BINNEN een zin, en een aparte `_line_gap` voor de ruimte tussen
  zinnen. Daarmee is aan het beeld te zien welke rijen bij elkaar horen.
  De ruimte tussen zinnen is een fractie van de fonthoogte en geen vast
  aantal pixels, want het font schaalt met het beeld: op 4K zouden de
  zinnen anders tegen elkaar aan plakken. Voor de afstand BINNEN een zin
  bleek een fractie juist niet te kunnen. Twee waarden geprobeerd (0,82
  en 0,90) en allebei botsten ze: gemeten over de eenentwintig
  meegeleverde fonts liep bij tien ervan de staart van rij 1 door een
  accentkapitaal op rij 2 (É, Ö - gewoon Nederlands), en het
  standaardfont was daar met acht pixels overlap de ergste. Wat wél
  werkt is meten op de échte inkt van die twee rijen (`getbbox`): de
  onderkant van de diepste letter boven tegen de bovenkant van de
  hoogste letter eronder, plus een beetje lucht. Een rij zonder staarten
  komt daarmee strak omhoog, een rij die met een É begint krijgt de
  ruimte die hij nodig heeft, en dat klopt voor élk font. Bij de fonts
  die de gebruiker gebruikt scheelt het echt: Oswald 97 px in plaats van
  107, Saira 85 in plaats van 114, Baloo 81 in plaats van 116.
- **B477 - dunne omlijning om de letters van de actieve regel.** Voor
  het contrast tegen een achtergrondfoto. Elke tekstkleur heeft zijn
  eigen randkleur, dus binnen één regel verandert de rand mee met de
  veeg: het gezongen deel draagt de rand van de zangkleur, het deel dat
  nog komt die van de wachtkleur. Standaard de contrakleur, bepaald op
  waargenomen helderheid (0.299/0.587/0.114) met de grens op de helft -
  zwart onder een lichte letter, wit onder een donkere; een ingevulde
  instelling wint. De al gezongen regels krijgen er geen, zoals de
  gebruiker vroeg: daar maakt het niet meer uit, en het scheelt
  rekenwerk per beeld. In `_draw_swept` loopt de rand mee met de veeg en
  is de teruggeplakte strook met de randdikte verbreed, anders bleef de
  rand van de gezongen helft over de wachtende helft staan.
- **B478 - "Open video" wist alleen van deze sessie.** Het pad zat in
  één globale `_last_video` die alleen bij een geslaagde render werd
  gezet en nergens werd teruggezet, dus na een projectwissel wees de
  knop nog naar de video van het vorige project (schermafdruk:
  Lied_U met "Lied A_2.mp4" op de knop) en een video
  van gisteren was helemaal niet te openen. De knop kijkt nu in de
  uitvoermap van dít project. Staan er meerdere versies, dan een keuze
  met het hoogste volgnummer voorgeselecteerd - gesorteerd op het nummer
  als getal, want als tekst komt `_10` vóór `_3`. Het nummer staat niet
  meer op de knop zelf.
- **B479 - 1.5.12 is eruit, code en al.** De proef heeft gedaan waarvoor
  hij gemaakt was. Dit is met opzet een uitzondering op "een proef die
  niets oplevert wordt uitgezet, niet weggehaald": die afspraak gaat
  over proeven waarvan de uitkomst niets waard bleek, en 1.5.12 was
  waardevol maar eenmalig. Weg zijn `rerender_videos`,
  `RERENDER_NUMBER`, `_numbered_target`, de vlag `slow` op `TestAction`
  (die bestond alleen hiervoor), de zes vertaalsleutels in nl én en, de
  regel op de publicatielijst en de tests erop. `next_video_target` doet
  het genummerde pad al netjes, dus er ging geen herbruikbare code mee.
- **B480 - achtergrondafbeeldingen centraal.** Een gekozen afbeelding
  gaat naar `config/backgrounds` als `background_001.<ext>` en telt door
  op het hoogste bestaande nummer (niet op het aantal, anders krijgt een
  nieuwe de naam van een gewiste). Dezelfde afbeelding twee keer kiezen
  levert er één: vergeleken op inhoud, niet op naam. Staat er minstens
  één, dan verschijnt er een thumbnaillijst met selecteren en wissen.
  Daarnaast gaat er een kopie naar de invoermap van het project als
  `background.<ext>` zonder nummer, die bij een nieuwe keuze wordt
  overschreven - en de oude extensie wordt opgeruimd, anders staan er
  twee en weet de render niet welke hij moet pakken. De render pakt die
  projectkopie als eerste, dus een gewiste centrale achtergrond breekt
  nooit een render. Nagekeken zoals gevraagd: de afhankelijkheidsketen
  hoeft niets te doen - een extra bestand in `input` staat niet in
  `_FINGERPRINTED`, en `video` hangt bewust aan niets (B353), dus er
  wordt niets ten onrechte ongeldig gemaakt. De render pakt ALLEEN die
  projectkopie: de instelling zelf is globaal, en die als terugval
  gebruiken zou de achtergrond van een ander liedje in deze video
  zetten - precies het lek dat B470 hierboven voor de titels moest
  dichten. **De achtergrond hoort daarmee bij het liedje en niet meer
  bij de app**: een project dat er nog geen heeft gekregen heeft er
  geen. Let op bij het overstappen: een achtergrond die vóór deze versie
  in de instellingen stond gold voor alles, en moet nu per project één
  keer opnieuw gekozen worden. Zonder gekozen project weigert hij
  overigens, want `input` is dan de gedeelde map en daar hoort geen los
  bestand te belanden (B445). In de lijst staat de achtergrond die
  aanstaat geselecteerd, zodat te zien is wélke het is; selecteren
  wisselt hem niet meteen om - anders is een opgeslagen plaatje niet te
  wissen zonder eerst dit project van achtergrond te veranderen. Er
  staan daarom twee knoppen onder: "Deze gebruiken" en "Opgeslagen
  achtergrond wissen" (dubbelklikken doet het eerste ook). Verder heet
  de knop nu
  "Afbeelding verwijderen" in plaats van "Terug naar standaard" en is
  hij alleen actief als er een afbeelding is; zonder afbeelding staat er
  "Geen" en niet 'standaard'. Het geheel staat onder de rij
  "Video-achtergrond" en niet meer in een eigen groep.
- **B481 - de golfvorm-hint is uit de editor.** Inclusief de
  vertaalsleutel in beide talen.
- **B482 - 1.5.11e liet mappen achter in %TEMP%.** `_at_level` maakte
  per omgezet bestand een eigen `mkdtemp` en ruimde die nooit op, ook
  niet op de foutroute. Eén kladmap voor de hele proef, opgeruimd wat er
  ook gebeurt. Let op: die kladmap is gedeeld, en de zangstem heet in
  élk project `vocals.wav` - de omgezette bestanden dragen daarom de
  projectnaam, anders schrijven vier liedjes over elkaar heen en meet de
  hele proef vier keer hetzelfde nummer. Nagelopen zoals gevraagd:
  verder maakt geen enkele
  gewone app-functie een tijdelijke map - de andere twee plekken zitten
  in de meetcode (`fill_transcription_cache` ruimt al netjes op, en
  `tools/timing_regression.py` is de meetlat, die houdt bewust een
  vaste map aan zodat ffmpeg niet elke draai opnieuw hoeft).

In v0.142.1 verwerkt:

- **B483 - de net gezongen zin werd weer wit op de bovenste plek.** In
  `_draw_line` kreeg elke niet-actieve regel de wachtkleur, ongeacht of
  hij al geweest was of nog moest komen. Op de plek onder de actieve
  regel klopt dat (daar staat wat nog komt), op de plek erboven niet:
  daar staat wat net gezongen is, en dat hoort grijs te zijn. De fout
  staat er al sinds de vloeiende regelverschuiving van B242, maar viel
  niet op omdat slot -1 toen bovenin het beeld hing en vooral tijdens de
  0,35 s van de verschuiving te zien was; sinds de stapeling van B473
  staat die regel pal boven de actieve zin. Een niet-actieve regel kijkt
  nu naar zijn eigen eindtijd: voorbij is grijs, nog te gaan is wit. De
  omlijning blijft weg bij een niet-actieve regel, zoals afgesproken.

In v0.143.0 verwerkt:

- **B484 - een `[bg]`-staart maakte de hele zin achtergrondzang.** De
  gebruiker miste in de editor stukken originele tekst van "Lied R".
  Gemeten in zijn eigen `project.json`: 43 originele regels tegen 55
  regels met inhoud in `songtekst.txt`, en de twaalf die ontbraken
  hadden allemaal een `[bg]...[/bg]` áchter de gewone tekst
  ("Noon gam-go, ha-na, dool, set [bg]Twee-uh[/bg]"). Beide tekstlezers
  hadden dezelfde fout: staan `[bg]` én `[/bg]` op één regel, dan werd
  die regel in zijn geheel als achtergrondzang gemarkeerd. In
  `load_lyrics` zette dat `is_bg_line` voor élk woord van de regel, in
  `parse_lines` `bg=True` voor de hele `TextLine`. De docstring van
  `load_lyrics` beloofde al het goede gedrag ("de omsloten woorden
  krijgen bg=True"); de code deed iets anders. De markering hoort bij
  de woorden tussen de markers, precies zoals inline `[crowd]` dat sinds
  B179a al doet - dat patroon stond er dus al naast. `_parse_inline`
  doet nu beide markeringen in één keer, zodat de woordnummers van
  crowd en bg op dezelfde uiteindelijke woordenlijst geteld worden en
  niet uit elkaar kunnen lopen.
  Wat er kapot was, in volgorde: zo'n regel had geen niet-bg woorden
  meer, dus hij kwam niet in `per_line_words`, dus niet in `detailed`,
  dus niet in `original_items` - weg uit de originele baan. Aan de
  karaokekant werd hij vóór de koppeling uit de lijst gehaald, kreeg via
  `attach_bg_lines` de tijd van zijn voorganger mét `disabled=True`, en
  verdween daarmee uit de render. En doordat er aan de originele kant
  twaalf regels wegvielen klopten de blokgroottes niet meer tegen de
  karaoketekst, waardoor de één-op-één-koppeling terugviel op de
  grovere tak. Dat verklaart ook waarom de fonetische stukjes bij Lied R
  "amper gingen".
- **B485 - het stuk blijft onderdeel van zijn regel.** Bewuste keuze van
  de gebruiker tussen twee ontwerpen: het afgeknipte stuk een eigen
  regelnummer geven (eenvoudiger code, maar alle nummers erna schuiven
  op en `timing.json` is op die nummers gebouwd - handwerk weg) of het
  als onderdeel van zijn regel bewaren. Het is het tweede geworden, in
  dezelfde vorm als `crowd_words`: `TextLine.bg_words` met de
  woordnummers, `Syllable.bg` per lettergreep. Er schuift dus niets op
  en elke bestaande `timing.json` blijft geldig; een oud bestand zonder
  het veld leest gewoon door (`syl.get("bg", False)`).
  Wat dat stuk mag en niet mag: het staat in beide editors, het mag in
  de tijd óver zijn buren heen liggen, en het komt nooit in de render.
  Dat laatste liep tot nu toe via `disabled`, en dat vlaggetje is óók de
  knop "regel uit/aan" - wie zo'n regel aanzette kreeg hem alsnog in
  beeld. De render kijkt nu naar de lettergrepen zelf
  (`_sung_syllables`), zowel voor het tekenen als voor de breedte, de
  hoogte en de fontkeuze. Voor het mogen overlappen moesten drie plekken
  ophouden ertegenin te werken: `TimedLine.start`/`end` kijken naar de
  gezongen kant (anders sleept de achtergrondzang de hele zin mee - de
  volledige tijden staan in `full_start`/`full_end`), `apply_spans`
  laat bg-lettergrepen met rust (de auto-fit werkt binnen het venster
  van de zin en zou ze daar weer in trekken), en `_line_span` in de
  timing-editor meet de zin zonder dat stuk.
- **B486 - het stuk mag een anker worden.** Bg-woorden bleven buiten de
  uitlijning én buiten de inhaalronde die opgeslagen woorden er achteraf
  alsnog bij probeert te matchen (B276). Buiten de uitlijning zelf is
  terecht - die loopt op volgorde, en een bg-woord dat tegelijk klinkt
  met de hoofdregel pikt daar het transcriptiewoord van die hoofdregel
  in - maar de inhaalronde daarna kost de hoofdstem niets: die woorden
  zijn dan al geclaimd, en er wordt alleen gezocht binnen het venster
  tussen de gekoppelde buren. Elke treffer is dus winst: een extra anker
  op een stuk waar er geen was.

Wat de kritische herlezing eruit haalde, en wat daarop is aangepast:

- De rem uit B469 kon niet afgaan: `ensure_directories` maakt één regel
  eerder `output/settings` aan, dus "er staat iets in de uitvoermap" was
  altijd waar. De rem telt nu alleen echte projectmappen (`settings`
  telt niet mee) en er staat een tweede rem naast: dat álle invoermappen
  tegelijk wees zijn, is geen opruimklus maar een teken dat er tegen de
  verkeerde map gemeten wordt.
- De timing-editor schreef `bg` niet weg en las het niet terug. Eén keer
  openen en opslaan wiste de markering, waarna het stuk gewoon in de
  video verscheen - precies de belofte die deze release doet.
- De energie-woordtiming (B234) verdeelde álle lettergrepen over het
  venster van de gezongen kant. Daardoor trok hij het bg-stuk terug naar
  binnen én kortte hij de zin in met het aandeel van dat stuk.
- Niets zette `bg` op een `timing.json` die er al was. Markers toevoegen
  verandert geen letter aan de zin (ze worden eruit gestript), dus noch
  de tekstvergelijking noch de carry-over merkte er iets van. De
  markering wordt nu bij het laden uit de tekst teruggelezen
  (`mark_inline_pieces`), voor de render én voor beide editors. Dat is
  meteen de reden dat er verder niets aan bestaande projecten gerepareerd
  hoeft te worden.
- Aan de songtekstkant sloot een inline `[/bg]` het omsluitende
  `[bg]`-blok, aan de karaokekant niet. De twee lezers spraken elkaar
  tegen; nu valt een inline sluiter terug op de blokstand, zoals crowd
  dat al deed.
- De bg-woorden aan de regeltekst plakken liet het woordaantal afwijken
  van de gemeten woordvensters, waardoor de klemtooneditor (B450) voor
  juist die zinnen terugviel op gelijkmatig verdelen - en het zette een
  bg-stuk dat vooraan stond achteraan. De zin houdt zijn eigen woorden;
  het stuk reist als apart veld mee en wordt in de originele baan tussen
  blokhaken achter de zin getoond.
- B472 (elke karaokeregel heeft een koppeling) liet de gespiegelde rij
  van een los tussenroepje uit de originele baan verdwijnen en rekte de
  balk van de originele zin eroverheen. Zo'n regel telt daar nu niet mee.
- Kleiner: `mark_held` nam het bg-stuk mee in de mediaan van de regel en
  kon het zelf als aangehouden noot markeren, en `spread_flattened`
  herverdeelde het mee. Allebei kijken nu naar de gezongen kant.

En wat een derde ronde er nog uit haalde:

- `apply_phonetic_timing` gaf `held`, `stress` en `crowd` door aan de
  nieuwe lettergrepen maar niet `bg`. Die stap staat standaard aan en
  draait op élke verse timing, dus er kwam in geen enkel bestand ooit een
  markering te staan - de hele wijziging leefde alleen nog van het
  terugleesfixje hierboven.
- `mark_held` draaide in `load_timing` vóórdat de markering was
  teruggelezen, dus het bg-stuk zat alsnog in de mediaan van zijn regel.
  Na het teruglezen worden de aangehouden noten opnieuw gewogen.
- `full_end` las `syllables[-1]`, de laatste in TEKSTvolgorde. Een stuk
  dat vooraan staat en over zijn buren heen ligt viel daar buiten; het is
  nu de laatste in tijd.
- `_reflow_line` verdeelde bij een lengteverschil ook de bg-lettergrepen
  over het venster van de gezongen kant, waardoor de zin tijd verloor aan
  het stuk. Diezelfde uitzondering als bij `apply_spans` en
  `distribute_over_windows`.
- Een aangeplakte `[/bg]` werd apart afgehandeld vóór de splitslus,
  waardoor "Tonight[/bg] my dear" van begin tot eind achtergrondzang werd
  en een regel die met een openmarker eindigde het blok niet doorgaf. Nu
  lopen alle markers door dezelfde lus, aan beide kanten; een test
  vergelijkt de twee lezers op negen schrijfwijzen woord voor woord.
- `apply_inline_crowd` legde de woordnummers uit de tekst zonder controle
  op de timing. Klopt het woordaantal van een regel niet meer, dan landt
  de markering op het verkeerde woord - en een woord dat ten onrechte bg
  wordt, verdwijnt helemaal uit de video. Zo'n regel wordt nu overgeslagen
  met een melding in het log.
- De tweede rem op het wezen-opruimen logde de reden van de eerste.

Wat er na deze wijziging opnieuw moet, en waarom:

- **Lied R** - acht regels staan in `timing.json` als uitgeschakeld
  (24 t/m 29, 39 en 47). Dat vlaggetje kwam van `attach_bg_lines` toen
  ze nog als hele bg-regel werden gezien; nu zijn het gewone regels met
  een achtergrondstaart en horen ze aan. Dit is het enige dat NIET
  vanzelf goed komt: `disabled` is ook de knop "regel uit/aan", dus de
  app kan niet zien of dat vlaggetje van de oude fout komt of van een
  bewuste keuze. Zet die acht regels aan in de timing-editor. De
  regelnummers schuiven niet, dus de handmatige timing zelf blijft
  geldig.
- **Lied_U** - de karaoketekst heeft geen enkele inline `[bg]`,
  dus daar verandert niets aan de karaokekant en blijft het handwerk
  volledig overeind. Aan de originele kant komen er zes regels bij (59
  van 59 in plaats van 53), dus de koppeling wordt beter zodra 1.2
  opnieuw draait.
- **Lied_R2** - nog geen timing, dus niets te repareren.
- **Lied_P** - twee inline `[bg]` in de karaoketekst, maar in
  `timing.json` staat geen enkele regel uitgeschakeld; daar is dus niets
  te herstellen.
- De overige zestien projecten gebruiken `[bg]` alleen als losse regel of
  helemaal niet en zijn ongemoeid.

In v0.144.0 verwerkt:

Deze ronde is de hele verzamellijst in één keer, op verzoek van de
gebruiker ("blijf doorbouwen tot alles van de lijst af is").

- **B487 - de omlijning staat op élke regel.** Bij B477 stond er "alleen
  de actieve regel", omdat de gebruiker zei dat het bij een al gezongen
  zin niet meer uitmaakt. Dat was te letterlijk gelezen: op zijn
  schermafdruk van "Lied U" heeft de groene actieve regel een
  rand en vallen de grijze regel erboven en de witte eronder weg tegen de
  achtergrondfoto. Nu krijgt elke regel er een, in de contrakleur van de
  kleur die hij op dat moment heeft - grijs voor wat geweest is, wit voor
  wat komt, rood voor crowd. Ook de oplichtende puntjes van een inline
  pauze, de titel in intro/outro en de creditregel eronder; de
  3-2-1-teller had er al een. Daarbij hoort dat de twee rijen van een
  afgebroken zin ruimte houden voor die rand: die staan met opzet krap
  (B476, gemeten op de echte inkt) en een rand groeit aan beide kanten,
  dus `_row_air` en `_line_gap` zijn nooit kleiner dan de randdikte aan
  twee kanten plus twee pixels.
- **B488 - een leeg blok is nog steeds een blok.** Bij "Lied R" liep de
  koppeling vanaf één regel uit de pas, met "extra koppelingen enzo". De
  blokken zijn aan beide kanten 4-8-4-4-4-8-8-4-4-4-1-2, maar het laatste
  blok van de karaoketekst bestaat uit twee regels die volledig `[bg]`
  zijn; die worden vóór de koppeling uit de lijst gehaald, waarna
  `[b for b in karaoke_blocks if b]` het lege blok helemaal weggooide.
  11 blokken tegen 12, dus `couple_timing` viel terug op zijn grofste tak
  (53 karaokeregels evenredig uitsmeren over 55 originele regels) en
  sloeg regels over. Met het lege blok als lege plék koppelt elke
  karaokeregel weer één-op-één - nagerekend op zijn eigen teksten: 53 van
  de 53, geen enkele afwijking, en alleen de twee "Twee uh"-regels blijven
  ongekoppeld omdat hun tegenhangers volledig `[bg]` zijn.
- **B489 - een ongekoppelde originele zin stond op een andere klok.** Een
  gekoppelde zin krijgt in de baan de tijd van zijn karaokeregel; een
  ongekoppelde viel terug op zijn eigen tijd uit het origineel. Bij
  Lied R scheelt dat een halve minuut, dus zo'n zin sprong zichtbaar naar
  voren en stond in de verkeerde volgorde. Hij wordt nu tussen zijn
  gekoppelde buren gezet, zodat de hele baan op één klok staat.
- **B490 - "overschrijven" pakt de laatste video.** Na een paar keer
  naast elkaar bewaren is de nieuwste `_3`, en dan is de eerste render
  overschrijven nooit wat er bedoeld wordt met "nog een keer".
- **B491 - 1.5.11e gaat uit.** De vraag is beantwoord en het antwoord is
  nee. Over vier liedjes wint het hardste niveau op het totaal (193,5 s
  niet gehoord tegen 220,2 zoals het nu is), maar het verliest hard op
  Lied_T, waar "in tekst" naar 62% zakt - die extra
  woorden zijn verzinsels, geen zang die eindelijk gehoord werd. En de
  aanname eronder is weerlegd: Groen is met -27,0 LUFS veruit de zachtste
  stem en verandert nauwelijks, terwijl het lied dat het meest profiteert
  op een doodgewone -14,3 zit. Uit, niet weg - zoals de afspraak zegt.
- **B492 - een zin met een pauze werd doormidden geknipt.** Twee keer
  gemeld: "de regel komt op de tijd VÓÓR de pauze te staan, ik moet hem
  handmatig over het tweede stuk trekken". B224 kort een regel in die
  doorloopt in stilte, en mat dat met `active_end`. Die functie zoekt van
  rechts naar links naar het eerste stiltegat van 0,3 s en geeft het
  laatste actieve moment DAARVÓÓR terug - goed als een regel op de
  volgende regel is uitgerekt, fout voor een zin met een eigen pauze in
  het midden, want dan is dat gat de pauze zelf en valt de tweede helft
  eraf. Er is nu een `last_energy` die de simpele vraag beantwoordt -
  waar houdt de zang binnen dit venster op - zodat alleen naslaap wordt
  weggeknipt.
- **B493 - de pauze bepaalt waar de zin splitst.** `is_pause` stuurde
  buiten `mark_held` en de render helemaal niets aan. De verdeling over
  de zangvensters (B234) rekende de grens uit op vensterduur, en die
  landde regelmatig op een ander woord. Staat er een `[pause]` in de
  tekst, dan is dat de gebruiker die zegt wáár de zin uiteenvalt; dat is
  nu leidend zodra het aantal pauzes klopt met het aantal gaten.
- **B494 - oprekken schaalt in plaats van uitsmeren.** `_reflow_line`
  maakte bij een lengteverschil alle lettergrepen even breed. Dat gooit
  álle gemeten fijne timing weg, de pauze in het midden voorop - precies
  de tweede helft van zijn klacht. Schalen houdt elke verhouding en zet
  de regel net zo precies op zijn nieuwe venster.
- **B495 - een passage in een ander schrift.** De taaldetectie werkt op
  Latijnse woorden en ziet Koreaans niet. Een blok Hangul is ook geen
  waarschijnlijkheid maar een feit, dus dat wordt op de tekens herkend,
  met de drempel van de gebruiker: meer dan twee woorden achter elkaar,
  of meer dan vijf in het hele lied. Bij 1.1 wordt dan gevraagd in welke
  taal Whisper moet luisteren, vóór de transcriptie - erna kost het een
  hele draai opnieuw. Let op: bij "Lied R" staat het Koreaans fonetisch
  in Latijnse letters en daar valt niets aan te zien; die vraag komt dus
  alleen bij "Lied_R2".
- **B496 - zinnen uit het origineel terughalen.** De gebruiker wil de
  geïsoleerde "eehee's en ow's" terug op de plekken waar ze horen. Het
  mechanisme bestond al (B282: een stuk origineel dat de karaoke daar
  1-op-1 VERVANGT, met een crossfade aan de randen - precies wat hij
  vroeg, en geen mengen); wat ontbrak was de weg ernaartoe. In de
  timing-editor kun je nu een zin aanwijzen; dat wordt per regelnummer
  bewaard en bij het dempen omgezet in een terughaalblok op de timing van
  dát moment - bewust afgeleid en niet vastgezet, zodat het stuk origineel
  meeschuift als je de zin verplaatst. In beide editors krijgt zo'n zin
  een eigen blauwe kleur, zodat te zien is dat hij niet in 1.4 getekend
  is maar in 2.3 gekozen. Over de afhankelijkheidsketen: `restore_lines`
  hangt bewust NIET aan de timing - het zijn regelnummers, en een
  timingwijziging maakt de bewerkte karaoke met opzet niet ongeldig.
- **B497 - lettergrepen bijstellen na handwerk.** Het idee van de
  gebruiker: als de zinnen eenmaal op hun plek staan, is dat een
  betrouwbaar houvast om de lettergrepen erbinnen te verdelen. Het
  machinerie daarvoor bestond al (B234, de verdeling over de
  zangvensters), maar draaide alleen tijdens het genereren, dus handwerk
  had er niets aan. Er zit nu een knop op in de timing-editor die precies
  dat doet, met de zinsgrenzen onaangeroerd.

Wat de kritische herlezing er nog uit haalde (B498):

- **"Overschrijven" pakte de nieuwste video van de hele map.** Staat er
  naast `Titel.mp4`, `_2` en `_3` ook een `Titel_voc_ori.mp4` (een render
  met een ander spoor, B271), dan is de vraag over die laatste maar
  schrijft "overschrijven" over `_3`. `existing_videos` kan nu op één
  genummerde familie filteren; "Open video" blijft de hele map tonen,
  want dat is wat daar de bedoeling is.
- **"Herstel origineel" wiste de zin-markeringen.** `_reset` bouwt de
  regeldicts opnieuw op en die kennen `restore` niet, dus de blauwe
  zinnen verdwenen uit beeld en de eerstvolgende opslag wiste de keuze.
  De markering gaat nu mee: ze zegt iets over de AUDIO en heeft niets met
  de timing te maken.
- **Een blauw blok in 1.4 was niet weg te krijgen.** De editor liet het
  verslepen en verwijderen, maar bij Toepassen werd het gewoon opnieuw
  afgeleid uit de markering - zonder melding. Het regelnummer staat nu in
  het label, dus het verwijderen slaat terug op de markering zelf.
- **Meerdere ongekoppelde zinnen achter elkaar kwamen op dezelfde plek.**
  Precies het geval bij Lied R, waar de twee "Twee uh"-regels aan het
  eind ongekoppeld blijven: die stapelden op één balkje van 0,4 s en
  waren niet meer aan te wijzen. Ze krijgen nu elk hun eigen plekje.
- **De knop "lettergrepen bijstellen" verschoof de zinsgrenzen.** De
  zangvensters worden op de regel geknipt, dus een regel waarvan de
  eerste energie ná het begin ligt werd naar binnen getrokken - precies
  wat niet mag als de gebruiker de zin net zelf heeft geplaatst. Elke
  regel gaat na het bijstellen terug op zijn eigen venster.
- **`_reflow_line` viel om op een regel zonder lettergrepen.** Die zit op
  de opslagroute, dus één zo'n regel liet het opslaan van de hele timing
  omvallen.
- **De pauzepuntjes bleven wit op een al gezongen regel**, terwijl de
  letters eromheen grijs waren.

Wat er van de lijst NIET in zit, en waarom:

- Een meting bij B497. De gebruiker vroeg "kijk maar of daar een test
  voor te maken is". Die is te maken, maar niet zinnig zonder ijkpunt:
  je meet het effect van bijstellen tegen handmatige timing, en dan meet
  je tegen precies het handwerk dat je wilde verbeteren. Wat wél kan is
  het effect meten op de projecten die zowel `timing.json` als
  `timing_auto.json` hebben - eerst vragen wat hij wil vergelijken.
- Bij B492 blijven twee versterkers staan die een meting nodig hebben:
  `spread_over_active` en `windows_between` weigeren met opzet een regel
  over een pauze heen te plaatsen (voor onbetrouwbare regels), en de
  fraseklem in `_dur_for` rekent met één frase per zin terwijl een zin
  met een echte pauze er ongeveer twee duurt. Allebei aanpassen zonder
  meting is gokken; de meetlat (1.5.5/1.5.10) kan zeggen wat het doet.

In v1.0.0 verwerkt:

- **B542 - versie 1.0 en de publicatie op GitHub.** De bouwlijst is leeg,
  de hele weg van opname naar afgemaakte video werkt en de meetlat staat
  op 2,46 s over alle projecten; daarmee is dit geen 0.x meer. De
  broncode staat vanaf nu publiek op GitHub onder de MIT-licentie.

  De voorpagina klopte niet meer en dat is de eerste indruk die iemand
  krijgt. De inleiding zei **"Huidige versie: 0.9"** terwijl de
  roadmaptabel eronder tot 0.152.0 liep, en beschreef alleen het
  oorspronkelijke doel - woorden dempen in een gekochte karaokeversie -
  terwijl het programma intussen splitst, transcribeert, timet en een
  video rendert. Verder stonden er drie dingen in die er niet meer zijn:
  een hele paragraaf "Consolemenu" met een menu van acht opties, terwijl
  `KaraokeTool.py` alleen nog de GUI start; verwijzingen naar
  `KaraokeTool.bat`, dat `KaraokeToolGUI.bat` heet; en verwijzingen naar
  `modules/taal.py`, dat sinds B299 `modules/translations.py` heet. De
  kopregel van `modules/pipeline.py` noemde datzelfde `menu.py` als
  tweede aanroeper. Alles rechtgezet; de historische roadmaprijen blijven
  staan zoals ze waren, want die beschrijven wat er toen was.

- **De publieke kopie is een andere boom dan deze installatie, en
  `tools/github_export.py` maakt hem.** Gevraagd en beantwoord: de eigen
  projectnamen gaan er niet in mee, maar ze blijven hier wel staan. Dat
  kan niet met een schakelaar in de code, dus er is een gereedschap dat
  de publiceerbare kopie bouwt. Het laat weg wat van de gebruiker is
  (`config/`, `input/`, `output/`, `cache/`, `logs/`, `venv/`, en het
  meetwerk: `testhistorie.json`, `modelmatrix.md`, `modelcombinaties.md`,
  `metingen.md`, `testverslag.md`, `knipwoorden.txt`,
  `docs/verslagen/`), het hernoemt de tweeentwintig liedprojecten naar
  `Lied A` tot en met `Lied U` en de vereniging naar "Rood Witte
  Zangers", en het knipt de werkafspraken tussen de gebruiker en de
  assistent uit het logboek - die zijn privé, geen documentatie van het
  programma.

  Hernoemen en niet weggooien, want bijna elke regel in `timing.py`
  draagt de meting die hem rechtvaardigt ("gemeten op X: van 7,58 naar
  3,90 s"). Haal je de naam weg, dan is de regel een blote bewering.
  Twee eigenschappen van de plaatshouders dragen gewicht: ze houden de
  alfabetische volgorde van de originelen aan, omdat meerdere tests de
  volgorde van de projectlijst controleren, en de plaatshouder voor de
  vereniging is zo gekozen dat hij in precies dezelfde lettergrepen
  uiteenvalt als de naam die hij vervangt, omdat juist die naam het
  testmateriaal van de lettergreepsplitser is.

- **Wat de kritische herlezing hiervan opleverde, en dat was niet
  weinig.** De eerste versie van het gereedschap gaf "schoon" terwijl de
  naam van de vereniging er nog twaalf keer voluit in stond. Drie
  oorzaken, en alle drie zaten in de controle zelf: die zocht alleen de
  letterlijke projectnamen (de vereniging stond niet in de lijst), was
  hoofdlettergevoelig (dezelfde naam in kapitalen of juist helemaal in
  kleine letters glipte erlangs) en keek niet over regeleinden heen,
  terwijl de helft van de treffers in afgebroken proza staat. De controle is nu breder dan het werk zelf -
  hoofdletterongevoelig, blind voor regeleinden, en hij leest ook de
  bestandsnamen - want een controle die dezelfde blinde vlekken heeft
  als het werk dat hij controleert is versiering.

  Verder: `\b` telt een underscore als woordteken, waardoor "Lied A
  " in `Lied A_2.mp4` langs de grens glipte; de grens
  is nu uitgeschreven. Een naam kan in een Python-string staan met `\n`
  als twee tekens in plaats van een regeleinde, en precies zo'n geval in
  `test_texts_identical` werd half vervangen: de ene helft van de
  vergelijking wel, de andere niet, waarna de test terecht rood werd. De vervanging zette bovendien twee regels aan elkaar, wat
  niet alleen lelijke lange regels gaf maar in een testbestand een
  regeleinde opat waar het aantal regels juist het onderwerp is; de
  vervanging houdt nu de opmaak van wat hij vervangt. En
  `shutil.rmtree` op een pad van de opdrachtregel deed geen enkele
  controle: een typefout wiste een willekeurige map, en een tweede
  export gooide de `.git` van de vorige weg. Nu blijft `.git` staan,
  weigert het gereedschap een map die niet van hemzelf is, en kan het
  doel nooit in de projectmap liggen.

- **De lettertypen gaan niet mee, en dat lost een licentievraag op.**
  De `LICENSE` beweerde eerst dat de meegeleverde Google Fonts onder de
  SIL Open Font License staan, maar `install.bat` zoekt zelf in
  `@('ofl','apache')` - een deel staat dus onder Apache 2.0. Bovendien
  eist OFL 1.1 dat de licentietekst meereist, en `LICENTIE.txt` geeft
  alleen verwijzingen. Omdat `install.bat` alle twintig families
  gewoon zelf ophaalt, is de oplossing ze niet mee te leveren: alleen
  `DejaVuSans-Bold.ttf` blijft staan als terugval, vrij herverspreidbaar,
  en de repo is vijf megabyte lichter. `test_bundel_bevat_fonts` werd
  daardoor rood op een verse kopie; die slaat zichzelf nu over zolang de
  extra lettertypen er niet staan - dat was trouwens ook vóór deze
  wijziging al fout, want een verse uitpakking van de zip had hetzelfde
  probleem.

- **Het besluit onder "Voor publicatie beslissen" is verschoven, niet
  uitgevoerd.** Daar stond sinds 25 augustus dat het testpaneel 1.5.x,
  de meethistorie en de verslagen er bij publicatie helemaal uit gaan.
  Gevraagd en beantwoord bij deze publicatie: het paneel blijft erin. De
  reden om het eruit te halen (gereedschap voor de bouw, niet voor de
  gebruiker) staat nog steeds, maar zesenzestig van de zesennegentig
  testbestanden importeren `test_panel`, dus eruit halen betekent de
  testsuite slopen - en de gebruiker gebruikt het paneel wekelijks. Wat
  wél is uitgevoerd is de andere helft van dat besluit: het meetwerk
  zelf blijft buiten de repo.

  Daarbij kwam iets aan het licht: de opleveringszip van v0.152.0 bevatte
  die meetbestanden wél. De afspraak "gaat nooit mee in een oplevering"
  was in de praktijk alleen toegepast op de *installatie* - ze worden
  daar niet overschreven - maar de zip was een momentopname van de map en
  nam ze dus mee.

In v0.152.0 verwerkt:

- **B541 - hetzelfde beeld wordt niet twee keer getekend.** Punt 10 van
  de bouwlijst. De renderlus bouwde elk beeld opnieuw op, ook als er
  niets aan veranderd was: de intro is één stilstaand beeld dat 250 keer
  werd opgebouwd, de outro net zo, en tussen twee zinnen beweegt er
  niets. Gemeten op de eigen render van de gebruiker: 249 van de 250
  introbeelden waren byte voor byte gelijk aan hun voorganger, 199 van
  250 in de outro en 99 van 250 in de tekst.

  Waar het om draait is de vraag "is dit beeld hetzelfde als het
  vorige", en die moet exact beantwoord worden - een blijven hangen
  beeld in een afgemaakte video zie je pas als iemand hem uitkijkt. Zo'n
  antwoord afleiden door de tekenregels in een tweede functie na te
  bouwen is precies hoe die twee uit elkaar gaan lopen: de volgende die
  iets aan het tekenen verandert vergeet de kopie. Daarom wordt het
  antwoord niet afgeleid maar OPGENOMEN. Het beeld wordt eerst droog
  opgebouwd met een grootboek in de plaats van het tekenvlak: elke
  opdracht komt in een lijst en er wordt niets gerasterd. Twee beelden
  met dezelfde lijst zouden uit dezelfde opdrachten in dezelfde volgorde
  zijn opgebouwd, en zijn dus per constructie hetzelfde beeld. Wat het
  kost is de opmaak (de lettermetingen), niet het tekenen - en het
  tekenen is de dure helft.

  Twee dingen kwamen uit het meten en staan er allebei in:

  - **De opmaak van een zin wordt nog maar één keer per render
    uitgerekend.** Hoe een zin over rijen breekt en hoe hoog hij is,
    hangt af van de regel, de letter en de breedte - niet van het
    moment. Toch werd het vijftig keer per seconde opnieuw gedaan, voor
    drie zinnen, met een lettermeting per lettergreep. Dat maakt het
    tekenen zelf al een kwart sneller, los van het hergebruik.
  - **Opnemen kost ongeveer een tiende van tekenen**, en dat is winst in
    een stilstaand stuk en verlies in een lied dat van begin tot eind
    doorzingt. Daarom valt het opnemen terug na een rij missers: dan
    kijkt hij nog naar een PAAR beelden per tien - een paar, want zien
    dat er niets beweegt kost twee beelden naast elkaar. Een stilstaand
    stuk wordt zo binnen een vijfde seconde opgepikt en een lied zonder
    stilstand betaalt een paar procent.

  Gemeten op een proeflied van 45 seconden met intro, een zin over twee
  rijen, een meezingregel, een instrumentaal gat met aftelling en een
  outro: 70% van de beelden hergebruikt en 2,4 keer zo snel als
  v0.151.0. Op een lied dat onafgebroken doorzingt (het slechtste
  geval): 1,2 keer zo snel, want daar komt de winst alleen van de
  opmaakcache. In beide gevallen komt er byte voor byte hetzelfde uit,
  en daar staat een toets op die elk beeld van zo'n proeflied met en
  zonder hergebruik naast elkaar legt.

  Wat NIET gebouwd is, is de tweede richting van punt 10: het tekenen
  over meer kernen verdelen. Dat is het echte werk op een machine met
  twaalf draden, maar het is pas te beoordelen als de bottleneck
  gemeten opnieuw bij het tekenen ligt - dus na deze stap, op een echte
  video op de machine van de gebruiker.

In v0.151.0 verwerkt:

- **B538 - een lied met twee talen erin wordt ook in de tweede taal
  gelezen.** 1.5.11g draaide op 31 augustus op "Lied_R2", het enige
  project met een tweede schrift, en de uitslag was duidelijk: het hele
  lied in het Engels met Koreaans dat alleen stiltes mag vullen komt op
  0,08 s van de handmatig gezette regelbegins tegen 0,09 s voor het kale
  Engels, en er komt 2,0 s zang bij in drie stukjes - precies de drie
  Koreaanse kreten. Er gaat niets verloren: nul seconden die het Engels
  wel had en de samenvoeging niet.

  Dat pad staat nu in productie. Ziet de tekst een echte passage in een
  ander schrift (B495), dan gaat het hele lied als één extra klus mee in
  dezelfde rij die de stukken al draait: dezelfde seconden, andere taal.
  Vooraan in de rij, want hij is even zwaar als de eerste hele draai en
  de rij begint met het zwaarste werk. Wat die tweede lezing oplevert
  gaat door precies dezelfde deur als een stuk (B442): het mag een
  stilte vullen en het kan nooit een woord overrulen dat de eerste draai
  gehoord heeft. De tweede taal staat in de cachesleutel - zet er een
  Koreaans couplet bij en de bewaarde transcriptie is het antwoord op
  een andere vraag - en in het logboek staat hoeveel woorden hij echt
  heeft ingevuld, zodat je kunt zien of hij zijn draai waard was.

  Twee dingen uit de herlezing zitten erin. Zonder gemeten zang gaat de
  tweede draai NIET aan: een woord telt alleen als invuller als het op
  zang staat, dus dat zou een hele Whisper-draai voor zeker niets zijn -
  en de voortgangsbalk zou er ook nog bij stilvallen. En kanji tellen
  naar hun blok als Chinees, dus een Japans lied kreeg elke keer een
  hele Chinese draai voor een schrift dat de eerste draai al kent; dat
  gebeurt niet meer.

  Let op bij het in gebruik nemen: de tweede taal zit in de
  cachesleutel, maar een bestaande stap zonder die sleutel blijft geldig
  (net als bij B442). Een project dat al een transcriptie heeft draait
  dus niet uit zichzelf opnieuw - de winst komt pas als er iets anders
  verandert (andere songtekst, ander model, opnieuw gescheiden wav), of
  als je stap 2 met de hand opnieuw draait.

  Wat er tegelijk UIT ging is de route waar 1.5.11g oorspronkelijk voor
  gebouwd was: de tweede taal over alleen de zwakke plekken van de
  eerste. Die gaf zes woorden en 0% op een echte zin - een plek van een
  paar seconden is te weinig aanloop voor Whisper, ook met drie seconden
  speling aan weerskanten. `weak_by_ratio`, `useful_spans`,
  `combine_in_spots` en hun constanten zijn weg, net als bij 1.5.8 en
  1.5.11c: het antwoord blijft in het logboek staan, de weg ernaartoe
  niet in de code. De proef zelf blijft bestaan - één lied is geen regel,
  en hij hoort op een nieuw lied na te gaan of die samenvoeging nog
  steeds wint.

- **B539 - een opgepropte staart wordt over de zang uitgelegd.** Het
  slechtste project van de verzameling, "Lied N" met 7,58 s, bleek
  één duidelijk beeld te hebben. Het lied eindigt met het refrein vier
  keer achter elkaar, de koppeling matchte alle vier op dezelfde vroege
  plek, en de laatste vijftien regels kwamen op de minimumduur van één
  seconde achter elkaar te staan tussen 189 en 204 s - terwijl de
  zangstem laat zien dat er tot 220 s gezongen wordt en de gebruiker die
  regels op 189 tot 222 heeft gezet. Zestien seconden gemeten zang
  zonder een letter tekst erop, en een meter regels schouder aan
  schouder ervoor.

  Twee dingen moeten samen waar zijn en geen van beide is genoeg. Er is
  zang NA de laatste regel - de tekst was dus eerder op dan het lied -
  én de staart ligt op de bodem van de minimumduur, wat de plaatsing
  zelf zegt als ze niets te gaan heeft. Dan worden die regels over de
  zangvensters gelegd vanaf waar de staart begint, elk venster naar rato
  van zijn lengte. De rij moet bovendien OP een bodemregel beginnen,
  anders kruipt hij achteruit over gezonde zinnen heen zolang het
  aandeel maar hoog blijft.

  B336 doet dit al voor de staart na het laatste anker, maar heeft een
  frase-periode nodig én een precieze pasvorm. Dit geval heeft geen van
  beide: de regels ZIJN ankers (verkeerde), en het lied heeft geen
  meetbare periode - en dat is precies waarom er nooit iets op aansloeg.
  Gemeten over alle twintig projecten: "Lied N" van 7,58 s naar
  3,90 s, met de schade op regels die de gebruiker niet eens verzet
  heeft óók omlaag (0,66 naar 0,61), en geen enkel ander project dat een
  duizendste verschuift. De meetlat over de hele verzameling gaat
  daarmee van 2,81 s naar 2,46 s.

  De kritische herlezing heeft deze stap flink bijgeschaafd, en dat is
  de moeite van het opschrijven waard, want de eerste versie was
  0,5 seconde "beter" om de verkeerde reden. Ze verdeelde de regels PER
  VENSTER met afronding, en dat sloeg bij minder regels dan vensters de
  eerste vensters over en schoof de hele staart naar het eind van het
  lied; op "Lied N" viel dat toevallig goed uit. Nu wordt er over de
  gezongen SECONDEN gelopen: de eerste regel landt precies op het begin
  van de staart en de afstand is gelijk in de tijd dat er echt iemand
  zingt. Verder bewaakt de stap nu de afspraken die `sanitize_timing`
  zelf ook nakomt - geen overlap, binnen het lied, nooit onder de
  minimumduur, en gebeurt er niets als dat niet kan - laat hij regels
  die uit staan (B180) hun plek houden in plaats van een stuk zang op te
  eten dat niemand ziet, en eist hij dat de regel vóór de staart géén
  bodemregel is. Zonder dat laatste was een lied van twintig korte
  kreten één staart vanaf regel nul, en verlegde een regel over het EIND
  van een lied het hele lied.

- **B540 - geprobeerd en gemeten dat het niet werkt.** Het op één na
  slechtste project, Lied_T met 7,28 s, heeft een
  vergelijkbaar beeld maar dan middenin: tien regels zonder eigen tijd
  tussen twee ankers, uitgelegd op 5,46 s per stuk dwars door twee
  stiltes van 12,8 en 10,8 s heen. B392 weigert daar in te grijpen zodra
  de vensters de rij niet één-op-één verklaren, en het idee was die
  weigering te verzachten: verdeel ze naar rato over de vensters zodra
  een kwart van het gat stilte is. Gebouwd, gemeten, en het maakte
  precies dat project SLECHTER (7,28 naar 7,35 s, schade 0,69 naar
  0,74) terwijl er verder niets bewoog. De reden is het bewaren waard:
  de twee ankers rond het gat staan zelf verkeerd, en geen enkele
  verdeling tussen twee verkeerde uiteinden kan goed uitkomen. Het idee
  is teruggedraaid; de aantekening staat in de code, waar de volgende
  die dit ziet hem tegenkomt.

  Wat "Lied T" wél nodig heeft is dus iets anders: die
  ankers zelf. Nul unieke regels, veertig keer dezelfde "La-la-la" -
  daar valt met tekst niets te onderscheiden. Nog niet aangepakt.

Wat de meetlat er in totaal van zegt, over 310 door de gebruiker
verzette regels in twintig projecten:

| versie | gewogen fout |
| --- | ---: |
| 0.148.0 | 3,48 s |
| 0.150.0 | 2,81 s |
| 0.151.0 | 2,46 s |

In v0.150.0 verwerkt:

- **B534 - elke draai houdt zijn eigen verslag.** Het testverslag ging
  naar één vast bestand, `docs/testverslag.md`, en werd door de volgende
  draai overschreven. Op 31 augustus was daardoor de draai van 1.5.1 t/m
  1.5.10 over alle projecten weg zodra 1.5.11g startte - meetwerk van
  uren, terug te halen uit het logboek en verder nergens. De verslagen
  gaan nu naar `docs/verslagen/`, met datum, tijd, versie, welke acties
  en welk bereik in de naam: `testverslag_2026-08-31_0929_v0.150.0_
  1.5.5_alle-projecten.md`. Een lange ticklijst wordt "eerste tot
  laatste" (`1.5.1-tm-1.5.10`), want twaalf codes in een bestandsnaam
  helpt niemand. `modelmatrix.md` en `modelcombinaties.md` blijven op
  hun vaste plek staan - dat is "de nieuwste" - maar leggen een
  gedateerde kopie in dezelfde map. Die kopie wordt gemaakt VOORDAT een
  nieuwe draai begint te schrijven en niet als hij klaar is: een draai
  die halverwege wordt afgebroken is juist de draai die de vorige zou
  meenemen. De gebruiker gooit die map zelf leeg; er gaat nooit iets van
  mee in een oplevering.

  Uit de kritische herlezing kwamen nog vier gaten in dezelfde afspraak,
  allemaal dicht: de naam telde in minuten, dus twee draaien vlak na
  elkaar overschreven elkaar alsnog (nu seconden, en bestaat de naam
  toch dan komt er `_2` achter); een actie die zonder gestarte draai
  binnenkwam schreef bij op het nieuwste verslag dat er lag - een
  verslag dat bovenaan een andere datum en versie noemt - en begint nu
  zijn eigen; dezelfde botsing gold voor de gedateerde kopieën; en
  mislukte de kopie, dan schreef de draai daarna gewoon over de vorige
  uitslag heen met alleen een logregel als spoor - de kopie valt nu
  terug op een plek naast de bron. In het logboek staat voortaan ook in
  welk bestand de lopende draai schrijft; er staan er nu veel.

- **B535 - een anker aan het EIND van een gedrongen rij hield zijn begin.**
  B340 laat van een rij ankers die veel dichter op elkaar staan dan de
  frase van het lied alleen de binnenkant vallen: de buitenste twee
  houden de uitrekking op zijn plaats. B522 geeft een anker dat alleen
  te lang is zijn gemeten begin terug. Die twee samen deden precies wat
  geen van beide bedoelde: het laatste lid van zo'n rij mocht zijn begin
  houden, terwijl dat begin net zo slecht gemeten is als dat van de
  leden ernaast. Gemeten op "Lied K": regel 43 loopt in
  de koppeling van 202,57 tot 225,09 (22,5 s tegen een frase van 3,44)
  en begint 10,3 s vóór waar de gebruiker hem heeft gezet; de hele outro
  werd erdoor naar voren getrokken. De meetlat ging van 4,85 s naar
  6,90 s tussen v0.147.0 en v0.148.0 en staat nu weer op 4,85 s. De
  vraag "welk anker moet weg" en de vraag "mag dit begin geloofd worden"
  krijgen nu ieder hun eigen antwoord over dezelfde rij: de binnenkant
  (`run[1:-1]`) tegen de rij zonder zijn eerste lid (`run[1:]`).

  Het EERSTE lid houdt zijn begin, en dat is met opzet. Een gedrongen
  rij is het beeld van één regel die meermaals is neergezet, en van die
  kopieën is de eerste de plek waar de zang aannemelijk begon - de rest
  drijft ervandaan. Het is bovendien precies de vorm waar B522 voor
  gebouwd is: een goed begin met een einde dat het instrumentale stuk in
  loopt. De kritische herlezing wees erop dat er voor het eerste lid
  niets gemeten is; op de vijf projecten waarop dit na te rekenen was
  maakt het geen verschil, dus blijft het zoals het was.

- **B536 - twee modelschakelaars om, allebei twee keer gemeten.** De
  uitlaatproef (1.5.9) draaide op 26 én 31 augustus over alle projecten
  met handmatige timing en zei beide keren hetzelfde:

  - **B213 (vulwoorden apart) staat weer AAN**: -0,18 s. Hij stond uit
    sinds v0.115.0 met de aantekening "-0,13 s op de ijkset". Die
    ijkset is sindsdien gegroeid en de stappen eromheen zijn veranderd;
    een uitgezet model blijft juist daarom elke draai meelopen, anders
    blijft zo'n oordeel dertig versies staan.
  - **B258/B285 (hallucinatiefilter) staat UIT**: -0,14 s. Op "Lied T
    " is het geen nuance maar het hoofdgebrek: 17,29 s fout
    met het filter aan tegen 7,28 s met het filter uit, en de schade op
    regels die de gebruiker niet eens verzet heeft valt van 7,47 s naar
    0,69 s. Uit en niet weg: het blijft elke draai meelopen.

  En daar zat een addertje onder, gevonden bij de kritische herlezing.
  De schakelaar verving `_filter_hallucinations` door een doorgeefluik,
  en in die ene functie wonen nog twee andere ideeën die er niets mee te
  maken hebben en apart gemeten zijn: de vaste lijst van
  Whisper-artefacten (B141, "MUZIEK", "Ondertiteling") en de vastgelopen
  herhaling (B514, twee treffers over twintig projecten en nul valse).
  Die gingen stilzwijgend mee uit. Dat verklaarde ook de enige plek waar
  het filter uitzetten schaadde: "Lied I" ging van 1,81 s
  naar 4,34 s, en dat was B514's La-da-da-lus van 29 seconden die
  terugkwam. De functie heeft nu een schakelaar `song_wide` die precies
  de twee ideeën uitzet waar het model naar heet; B141 en B514 lopen
  door. Nagemeten over de vijf projecten waarop dat hier kon:
  "Lied I" staat weer op 1,81 s en de gewogen fout over
  die vijf gaat van 5,25 s naar 3,58 s.

  Twee dingen die daaruit volgden:

  - De volgordes in 1.5.10 herschikken de pijplijn zoals die ECHT
    draait, dus ze bouwen op de functie die op dat moment op de module
    staat - langs een modelschakelaar heen grijpen zou een pijplijn
    meten die niemand heeft. Maar dan kan een volgorde loos worden: is
    een stap die hij verzet uitgezet, dan valt er niets te herschikken
    en kwam er een keurige "+0,00" in de tabel voor iets dat nooit
    geprobeerd is - precies de meetfout die B529 een laag lager
    opruimde. Elke volgorde noemt nu welke modellen hij verzet, en staat
    er daarvan één uit, dan zegt de tabel "overgeslagen" met de code
    erbij.
  - Er is een toets die de GELEVERDE stand vastlegt (welke modellen uit
    staan, en dat de vaste lijst en de vastgelopen lus dan nog steeds
    filteren terwijl een verzonnen zin blijft staan). De toetsenreeks
    zelf draait met alles aan - anders bewaken veertien toetsen code die
    de app niet meer uitvoert - dus zonder die ene toets komt de echte
    stand nergens langs.

  Uit de tweede herlezing kwam daar nog één ding bij: met de schakelaar
  uit gold een woord uit de B258-lijst als "geen hallucinatie", en dat
  pleitte de rest van het segment mee vrij. "ZANG EN MUZIEK" bleef dan
  staan terwijl kaal "MUZIEK" er wel uit ging - het voorbeeld waarmee de
  uitleg van B258 zelf opent. Zo'n woord telt nu niet mee in plaats van
  vrij te pleiten, net als een functiewoord: dan houdt B141 zijn greep
  en houdt een lied dat écht over zang gaat zijn zin.

  Bij het omzetten kwam een fout in de toetsen zelf boven: een model dat
  uit staat wordt uitgezet door een functie op zijn module te VERVANGEN,
  en die vervanger bleef daarna staan voor de rest van de draai. Zolang
  alleen B213 en B380 uit stonden merkte niemand dat, want geen toets
  meet die functies; met de hallucinatiefilter uit vielen er veertien
  toetsen van precies dat filter om, en alleen als de hele reeks liep.
  Het register wordt nu na ELKE toets teruggezet.

- **B537 - het alarmblok in het testverslag.** De alarmen zijn een
  tabel met een zin erboven, en die werden regel voor regel als bullet
  weggeschreven. Dat gaf een lege bullet (de witregel waarmee het blok
  opent), een tabel die niet meer kon renderen, en bij géén alarm een
  geruststelling onder de kop "Alarmen" - wat leest als een alarm dat
  niemand heeft opgeschreven. Er is nu `alarm_rows()`, dat leeg is als
  er niets aan de hand is, en het blok gaat als blok het verslag in.

Twee dingen op de machine van de gebruiker, geen programmawerk:

- `output/settings/project.json` (29 juli) hield alleen nog oude
  videotitels van "Lied G" vast en hoorde bij geen
  enkel project; daar waarschuwde de app bij elke start over (B445). Het
  programma gooit dat bestand met opzet niet zelf weg; het staat nu in
  `_to_delete`.
- Het logo van "Lied G" stond in een grijs-wit
  ruitjespatroon. Dat zat in de BRON: `logo.png` is RGB zonder
  alfakanaal en de achtergrond is een schaakbord van vakjes van 30 px in
  244 en 254 grijs - platgeslagen transparantie, geen fout in onze
  plaatsing. De bijna-witte vakjes zijn zuiver wit gemaakt (de oude
  staat in `_to_delete`); de video moet daarvoor opnieuw gerenderd
  worden.

In v0.149.0 verwerkt:

- **B530 - het beeld schoof op voor de intro en het geluid niet.** Begint
  de eerste zin van een lied vóór de tiende seconde, dan zet de renderer
  een aanloop voor het beeld (B203) en hoort daar evenveel stilte vóór
  het geluid te komen. Bij drie projecten gebeurde dat tweede niet, en
  dan loopt de tekst het hele nummer achter op de zang. Gemeten over
  alle 21 projecten: tien hebben zo'n aanloop nodig, en bij Lied_S
  (8,30 s nodig, 0,15 s aanwezig), Lied_A (6,21 tegen 0,00) en
  Lied_I (2,96 tegen 0,05) ontbrak hij.

  Een terugval, geen oude fout: de versie staat in de metadata van elke
  video (B273), en Lied_S was goed onder v0.101.0 met 8,60 s stilte,
  Lied_I goed onder v0.132.0 én v0.135.0 met 3,00 s, en
  allebei fout vanaf v0.141.0.

  Twee dingen zijn veranderd, allebei aan de filterketen:

  - de vertraging staat nu VOORAAN in plaats van achter de
    niveauregeling. loudnorm bouwt zijn filtergraaf halverwege een
    nummer opnieuw op - hij kiest na zijn vooruitkijkvenster tussen een
    rechte versterking en dynamische compressie - en alles wat
    dáárachter hangt wordt op dat moment opnieuw opgezet. Stilte die er
    op dat moment al in zit kan niet meer verdwijnen;
  - de kanaalindeling wordt genoemd. De karaoke.wav-bestanden van de
    gebruiker dragen `channel_layout=unknown` (gemeten over zijn hele
    verzameling), en `adelay=...:all=1` moet zich aan de kanalen van een
    bekende indeling binden. Zonder die indeling weigert ffmpeg de
    verbinding ronduit ("Cannot select channel layout for the link
    between filters", gereproduceerd op ffmpeg 4.4) of - erger - hij
    vertraagt niets en zegt er niets over.

  Wat de precieze reden was dat ffmpeg 9.0.1 op Windows de vertraging
  liet vallen is van buitenaf niet hard te maken; beide bovenstaande
  constructies zijn hoe dan ook fragiel en zijn nu weg. Daarom staat er
  ook een derde ding bij, dat onafhankelijk is van de oorzaak: **de
  render rekent zichzelf na**. Vlak voordat het bestand op zijn plek
  wordt gezet, meet hij de stilte vooraan en houdt die tegen de
  verschuiving van het beeld. Is er meer dan een tiende seconde TE
  WEINIG, dan wordt de video niet weggeschreven en krijgt de gebruiker
  te horen waarom. Beter een render die weigert dan een video die liegt.

  Die toets is met opzet eenzijdig, en dat is de reparatie van een fout
  die er eerst wél in zat. Wat gemeten wordt is de stilte aan het begin
  van het afgemaakte bestand, en dat is de aanloop PLUS de stilte
  waarmee het nummer zelf opent - die twee grenzen aan elkaar en de
  meter ziet er één. Op de eigen verzameling liep dat verschil van 0,2
  tot 0,4 s op, en al die renders waren goed. Tweezijdig toetsen zou
  dus precies de gezonde renders hebben geweigerd.

  Het ffmpeg-commando gaat voortaan naar het logboek: dat het er niet in
  stond is de reden dat dit alleen achteraf uit de bestanden zelf te
  achterhalen viel.
- **B531 - 1.5.12: alle video's opnieuw.** Geen meting maar een klus, en
  het is de tweede keer dat hij nodig is: de eerste na de verbeterde
  tekstomlijning (v0.146.0), nu na B530. Bij B479 is precies zo'n actie
  weggehaald als tijdelijk; die kwam dus terug, en daarom staat hij er
  nu als een gewone knop en niet als noodgreep.

  Hij staat achteraan in de lijst, doet nooit mee met het vinkje "alles
  aanvinken" - alle video's opnieuw maken overschrijft afgemaakt werk en
  dat doe je met opzet - en telt niet mee voor het plafond van tien; dat
  plafond gaat over de genummerde metingen. Daarvoor is een eigen veld
  `on_request` bijgekomen, naast `heavy`, want die twee betekenen niet
  hetzelfde: een zware proef verdwijnt uit de lijst als er niets onder
  staat, en deze mag juist nooit verdwijnen.

  Per project in deze volgorde: de standaardachtergrond neerzetten
  (`config/backgrounds/background_001.png` als `input/<project>/
  background.png` - acht projecten hadden hem al, dertien niet; kopiëren
  en niet terugvallen op de globale instelling, want dat is precies wat
  B480 verbiedt), dan renderen náást de bestaande bestanden, en pas als
  die render door zijn eigen controle van B530 is gekomen de oude
  video's (alle volgnummers) verplaatsen naar
  `<programmamap>/../_to_delete/oude_videos/<project>/`. Mislukt de
  render, dan blijft daar alles staan en zegt de tabel dat.
- **B532 - verzamelen en kopiëren, op tab 2.** Aan zodra er in enig
  project een video staat. Twee vragen en dan loopt het: alleen de
  video's, of de hele verzameling - video, originele opname, songtekst
  en karaoketekst - en waar het naartoe moet. De verzameling krijgt een
  map per project, want vier bestanden met dezelfde namen uit twintig
  liedjes in één map is geen verzameling maar een hoop; de video's
  alleen blijven plat, want hun bestandsnamen zijn de titels al. Van een
  project met meerdere renders gaat de nieuwste mee, en dat is de
  hoogste volgnummer en niet de nieuwste naam - `_10` komt na `_3`.

Uit de kritische herlezing vóór de oplevering (B530/B531/B532):

- **De zelfcontrole weigerde goede renders.** Zie hierboven: de toets is
  nu eenzijdig. Een toets die vaker onterecht dan terecht afgaat is
  erger dan geen toets, want dan zet je hem uit.
- **De verzamelknop kon niets kopiëren.** Het voortgangssignaal draagt
  twee getallen en werd met één aangeroepen; die `TypeError` viel op de
  eerste aanroep, nog vóór het eerste bestand. De knop was daarmee
  honderd procent stuk en geen enkele toets raakte hem, omdat ze
  allemaal `collect_videos` rechtstreeks aanriepen.
- **De stiltemeting keek weg bij precies het gebrek dat ze moet
  vangen.** Bij een pauze verderop in het nummer gaf ze "niet gemeten"
  in plaats van "geen stilte vooraan", en dan slaat de controle over.
  Nu telt alleen de eerste gemelde stilte, en begint die later dan
  0,05 s, dan is het antwoord nul.
- **Een onleesbaar bestand mat nul.** De afloopcode werd niet gelezen,
  dus "kan niet meten" en "geen stilte" waren hetzelfde antwoord - en op
  dat antwoord weigert de render.
- **De verzameling pakte de verkeerde variant en overschreef stil.**
  `existing_videos` zonder `like` levert het nieuwste bestand van de hele
  map, en dat kan de zang-alleen variant zijn; de docstring van die
  functie waarschuwt daar zelf voor. En twee projecten kunnen dezelfde
  videotitel hebben, want die komt uit de instellingen en niet uit de
  mapnaam - de tweede kreeg de naam van het project erbij in plaats van
  de eerste te overschrijven.
- **De opruimlus kon de oude video alsnog vernietigen.** Lukte het
  verplaatsen niet, dan werd er tóch hernoemd, en `replace` overschrijft.
  Nu wordt de nieuwe alleen omgedoopt als de oude echt weg is.
- **`projects_with_video` maakte mappen aan.** Via `context_for_project`
  liep `ensure_directories` over elke submap van `output`, ook over
  mappen die geen project zijn. Opsommen mag niets veranderen.
- Kleiner: de kanaalvertraging gaat nu per kanaal (`adelay=6215|6215`) in
  plaats van `all=1`, zodat de filter nooit hoeft uit te zoeken wat
  "all" betekent; het doel van de verzameling mag niet in de
  projectmappen zelf liggen; de Stop-knop werkt tijdens het kopiëren; en
  er is een toets bijgekomen die de meting op een écht bestand doet in
  plaats van op een nagebootste - de drie fouten hierboven bleven
  onzichtbaar juist omdat elke toets de meting wegstubte.

In v0.148.0 verwerkt:

- **B519 - na één handmatige aanpassing schoot de hele koppeleditor naar
  rood.** De koppelingen zelf bleven staan (gemeten: 362 van de 363),
  maar alles wat je ervan ZIET werd gewist: `_word_entry` zette `sim` op
  0.0, `found` op None en liet `status` helemaal weg. De regelkleur komt
  uit `sim` en 0.0 is rood, dus één samenvoeging maakte van 346 groene
  regels 362 rode. Er was niets kapot; je kon alleen niet meer zien wat
  goed was. Die drie velden worden nu opnieuw berekend uit de
  koppelingen zoals ze op dat moment staan - dezelfde fonetische
  vergelijking als de weergave zelf gebruikt. Gemeten na de reparatie:
  345 groen, 9 geel, 8 rood in plaats van 362 rood.
- **B520 - de gevonden baan werd per woord bijgewerkt en de reeksregel
  niet.** Een reeks van vier of meer ongekoppelde woorden achter elkaar
  ziet eruit als een hallucinatie, maar koppel er één van en de reeks is
  gebroken - dan hoort geen enkel woord er nog verdacht te staan.
  `found_word_status` is nu de ENE plek die dat beslist, en de editor
  herziet na elke aanpassing de hele baan in plaats van één woord.
- **B521 - een herhaling uit de songtekst stond aangemerkt als
  verzinsel.** "at a bar called O'Malley." op 268,8 s in het eigen
  project van de gebruiker is letterlijk regel 34 van zijn songtekst;
  het lied zingt de regel twee keer en de tekst schrijft hem één keer,
  dus de koppeling heeft die woorden al opgebruikt. Een reeks waarvan
  tweederde of meer van de woorden fonetisch in de songtekst voorkomt
  heet nu "herhaling, niet in de tekst" en niet meer "lijkt op een
  hallucinatie".
- **B518 - er is één leespad voor de transcriptie, en dat staat nu
  vast.** Het bestand op schijf is niet de lijst waarmee het programma
  werkt: `pipeline.load_segments` haalt er drie reparaties overheen die
  woorden weghalen (bij "Lied R" twee, 291 op schijf tegen 289 in het
  programma). Wie op het ruwe bestand nummert, zit na plek 27 één plek
  mis en na plek 144 twee - wat er precies uitziet als verschoven
  koppelingen en het niet is. Dat kostte de gebruiker een set van
  tweeëntachtig goede koppelingen. Een toets in `tests/test_v0148.py`
  legt nu vast welke functies het ruwe bestand mogen lezen (twee, en
  allebei met reden) en de valkuil staat in de docstring van
  `load_segments` zelf.
- **B522 - een te lange zin verloor zijn gemeten start.** Een zin die te
  lang duurt was "verdacht" en werd daarmee als anker geschrapt, waarna
  zijn START werd geïnterpoleerd tussen de buren. Maar de start is
  meestal wél gemeten; alleen het einde is fout. Zo'n zin blijft nu
  ankerkandidaat en krijgt zijn einde afgekapt op de frase van het lied.
  Gemeten op "Lied H": regel 31 gaat van +7,282 s
  naar +0,370 s ten opzichte van het handwerk (134,973 tegen 134,603) en
  het einde wordt van 152,108 naar 141,169 teruggebracht.
- **B523 - een regel werd over de blokgrens heen uitgesmeerd, het
  instrumentale stuk in.** Tussen twee blokken zit muziek, en die muziek
  hoort bij geen enkel blok - maar er staat wel energie op (een
  spookstem, een aangehouden synth), en de plaatsing liep er zo naartoe.
  Twee plekken repareren dat, allebei met dezelfde gedachte als de
  blokbarrière voor ankers (B251), maar dan voor het plaatsen:
  - de laatste regel van een blok mag met zijn vastgehouden noot niet
    doorlopen tot aan de eerste regel van het VOLGENDE blok. Zijn plafond
    is nu waar de zang van dit blok ophoudt. Gemeten op "Lied H
    " is dat de oorzaak van de verschoven regel 15: de
    zin groeide van 66,39-67,60 naar 66,39-83,31, werd daarmee te lang,
    verloor in v0.147.0 zijn anker en belandde met zijn start midden in
    het instrumentale stuk;
  - een reeks regels zonder eigen tijd wordt op de blokgrens in tweeën
    geknipt: wat bij het blok ervóór hoort blijft ervóór, wat bij het
    blok erna hoort komt erna. De grens is de langste stilte in het gat.
    Gemeten op "Lied P": lyricsregel 20 ("Oh let's go", de
    laatste van zijn blok) liep van 87,911 tot 99,227 - elf seconden,
    tot aan de volgende regel. Nu 87,911-88,816, en het handwerk van de
    gebruiker zegt 87,617-88,688. Op de andere projecten met een
    zangstem verandert er niets.
- **B524 - de uitkomst van een test kan de machine nu af.** Elke actie
  schrijft zijn regels ook naar `docs/testverslag.md`, met tijd,
  processortijd en de alarmen erbij. Het logvenster hield ze al, maar
  die tekst kan de gebruiker niet doorgeven; een bestand wel. Per draai
  opnieuw geschreven, zodat wat erin staat altijd precies één draai
  beschrijft. Meetbestand: gaat nooit mee in een oplevering, en staat
  in `tests/conftest.py` bij de omgeleide paden.
- **B525 - de scherpste toets van 1.5.7 mat niets.** "Lettergrepen over
  een GEMETEN woordgrens" hield de woorden van de PARODIE tegen de
  gemeten woordgrenzen van het ORIGINEEL - andere woorden dus, "app me
  terug" tegen "Write to me". Over twintig projecten gaf hij tussen 44%
  en 76%, en een getal dat altijd hoog staat is geen meting maar ruis
  die de tellers verbergt die wél iets zeggen. Weg; de vorm-, stilte-,
  tussen- en duurtellers staan er nog, en de geschiedenis vergelijkt nu
  op "woorden in een gemeten stilte".
- **B526 - 1.5.8 is weg, met zijn antwoord erbij.** De actie zei altijd
  hetzelfde: dit project heeft een gat of het heeft er geen. Dat weten
  veranderde nooit iets, want alleen 1.5.11 kan zeggen wat eraan te doen
  valt - en die meet het gat zelf. De meting (`_gaps_in`) blijft daarom
  staan als hulpstuk. Het nummer 1.5.8 blijft leeg: doorschuiven zou elk
  nummer in het logboek, in de testhistorie en in het gesprek een andere
  betekenis geven, en juist dat mag een nummer nooit doen. Het volgende
  onderzoek neemt 1.5.8 weer in.
- **B527 - 1.5.11g is een zoektocht geworden in plaats van één
  vergelijking.** Eén vergelijking kan geen gemene deler vinden. Er
  worden nu vier manieren van lezen gemaakt (hele lied in de grootste
  taal, hele lied in de tweede taal, de grootste taal geknipt op de
  stiltes, en de tweede taal over de zwakke plekken - ruim geknipt, drie
  seconden aan weerskanten zodat Whisper een aanloop heeft) en die
  worden op vier manieren gecombineerd, van voorzichtig (de tweede taal
  mag alleen stilte vullen) tot ruim (beide talen over de zwakke
  plekken). Alle acht komen in één tabel, gesorteerd op het getal waar
  het om gaat: de mediane afstand van de eigen regelbegins van de
  gebruiker tot het dichtstbijzijnde woordbegin. Dat is precies wat de
  timing van een transcriptie nodig heeft - elk regelbegin waar hij op
  ankert komt van een woordbegin.
  De zwakke plekken worden niet meer gezocht met "hier is helemaal
  niets" maar met een verhouding: minder dan een derde van de zangtijd
  in de buurt gedekt door woorden die in de songtekst voorkomen. Er is
  namelijk bijna altijd wel wat koppeling, want sommige woorden bestaan
  in beide talen. Gemeten over de projecten met een zangstem levert de
  verhoudingstoets minder maar zinnigere plekken op dan de nultoets
  (Lied_A: 3 plekken van samen 24,0 s in plaats van 12 plekken
  van samen 68,1 s).

Uit de kritische herlezing vóór de oplevering (B528/B529):

- **B528 - `_filtered` en `_in_lyrics` bleven achter bij een knip.** Dat
  zijn óók transcript-indexen, en `_remap` verzette alleen de
  koppelingen. Na een knip wees alles achter het knippunt één plek te
  ver naar links: het verkeerde woord stond doorgestreept en de
  reeksregel van B520/B521 beoordeelde de verkeerde woorden - precies de
  fout die B519 op de andere baan repareert. Ook een handmatige
  markering ("dit is een stopwoord") leefde alleen in de weergave en was
  na een knip weg; die wordt nu onthouden en verhuist mee.
- **B528 - een lege draai won de zoektabel van 1.5.11g.** "Afstand tot
  regelbegin" gaf 0,00 s voor "raakt elk regelbegin precies" én voor "er
  zijn helemaal geen woorden", en op dat getal wordt gesorteerd. Een
  mislukte draai stond dus bovenaan en werd uitgeroepen tot de beste.
  Geen woorden is nu oneindig ver.
- **B528 - `merge_runs` geeft een tuple terug.** De voorzichtigste
  combinatie in de nieuwe zoektocht pakte `(woorden, aantal)` als
  woordenlijst; dat had de hele actie 1.5.11 laten omvallen op de
  machine van de gebruiker, ná de Whisper-tijd van vier draaien.
- **B528 - de blokgrens heeft twee kanten.** Het deel ná de grens begon
  waar de zang van het vórige blok ophield in plaats van waar de zang
  van het volgende blok begint, zodat de eerste regel van dat blok
  alsnog in het instrumentale stuk geplaatst kon worden.
- **B529 - de modelschakelaar "ankertoets" stond op een omhulsel dat
  niemand meer aanriep.** `sanitize_timing` roept sinds B522
  `implausible_and_overlong` rechtstreeks aan, dus dat model uitzetten
  veranderde niets en de matrix (1.5.10) rapporteerde er 0,00 s voor -
  een meetfout, geen meting. De schakelaar zit nu op de functie die
  echt draait; gemeten op "Lied H" verandert er
  één regel als het model uit gaat, en dáárvoor nul.
- **B529 - een scheefgekoppeld anker gold als "alleen te lang".** B522
  laat een verdacht anker zijn gemeten start houden als het alleen te
  lang duurt. Een anker dat verdacht is omdat de koppeling dezelfde
  regel meermaals heeft neergezet, mag niet door die deur: juist zijn
  start is fout.

Valkuil om te onthouden (B518): wie woorden telt of nummert, doet dat
via `pipeline.load_segments` en nooit via `whisper.load_segments`. Het
ruwe bestand heeft meer woorden dan het programma gebruikt, en het
verschil ziet eruit als drift.

Tweede valkuil (B528): wie een lijst hernummert, hernummert álles wat op
die nummers wijst. In de koppeleditor zijn dat `_targets`, `_filtered`,
`_in_lyrics` en `_marked`; vergeet er één en het ziet eruit als drift
die er niet is.

In v0.147.0 verwerkt:

- **B513 - songtekstwoorden lagen bovenop elkaar in de koppeleditor.**
  Dit is de oorzaak waar drie rondes van "de koppelingen zijn weer
  verschoven" op terug te voeren zijn. `_relayout` geeft elk woord een
  kolom, en een kolom IS de positie: `_bot_rect` rekent er de x mee uit
  en `_hit_row` zoekt er het aangeklikte woord mee terug. Twee
  songtekstwoorden op dezelfde kolom worden dus op precies dezelfde
  pixels getekend, en de klik geeft altijd de eerste. Je klikt op het
  vakje dat je ziet en de editor koppelt zijn linkerbuur. Gemeten bij
  "Lied R": 25 onbereikbare woorden (kolom 93 droeg `me` en `I'll`,
  kolom 97 `high` en `That`, kolom 272 droeg er drie), en van de 82
  gevulde pins in dat project kwam er geen enkele overeen met wat de
  automatische koppeling zei - 65 wezen een of twee gevonden woorden te
  ver naar links. De bewaking is één regel: een songtekstwoord landt
  strikt rechts van zijn voorganger. En `paar_col` is veranderd van "de
  kolom die op dit moment vrij is" naar de kolom van het eerste gevonden
  woord van zijn groep, wat B220 pas echt waarmaakt; kan het daar niet
  staan, dan schuift het één plek op en loopt de lijn schuin - een
  rechte lijn naar een woord dat niet te zien en niet aan te klikken is,
  is geen lijn.
  Uit de herlezing kwam er nog een tweede sloper bij: een samengevoegd
  vak kan een kolom overdekken die aan niemand toebehoort, en de
  koppellijn hangt aan het optische midden van dat vak. Een klik daar
  viel door naar `_hit_link` en verwijderde de koppeling van de HELE
  groep, terwijl de gebruiker midden op een woordvak klikte. Een klik
  binnen een getekend vak doet nu niets.
- **B514 - een woord van zevenentwintig seconden is geen woord.** Bij
  "Lied_R2" (Koreaans) produceerde Whisper één woord van 223 tekens dat
  van 116.8 tot 143.8 s liep, dwars over het tweede refrein heen. Het
  glipte door elke controle: de brede check eist minstens twee
  kernwoorden en dit segment heeft er precies één, dus de veiligheidsklep
  "te weinig materiaal om over te oordelen" liet juist het ergste geval
  door. De regel zegt nadrukkelijk NIET dat daar niets gezongen is - de
  gebruiker herkende zijn vier herhaalde kreten erin, en de lus begint
  dus op echte zang. Wat hij zegt is dat zo'n woord geen bruikbare
  woordtijden draagt: wáár in die 27 seconden die kreten liggen valt er
  niet uit af te leiden. Wegfilteren maakt er een eerlijk gat van, en een
  gat is iets waar de volgende poging naar kan zoeken (B515).
  Twee dingen uit de herlezing zitten erin. Lang in TIJD telt alleen
  samen met lang in TEKENS, want een aangehouden noot is precies een
  woord dat lang duurt en kort is in letters ("aaaaah" van negen
  seconden is zang). En het hele segment gaat alleen weg als de lus het
  grotendeels vult, zodat één lange noot tussen negen goede woorden die
  negen niet meesleept. Nagerekend over alle twintig projecten in de
  cache: twee treffers, allebei echte lussen ("Lied_R2" en het
  "La-da-da-da" van 29 s bij Lied_I), nul valse.
- **B515 - proef 1.5.11g, de tweede taal over de zwakke plekken.** Idee
  van de gebruiker, en scherper dan "de hele song in de andere taal" -
  dat is bij B495 gemeten en het verliest. Eerst de hele song in de
  grootste taal, dan de zwakke plekken van díé draai zoeken, en alleen
  die aan de tweede taal aanbieden. Zwak is tweeërlei: zangtijd zonder
  woord (het bekende gat) en zangtijd met woorden die nergens in de
  songtekst voorkomen - dat laatste is hoe een passage in een andere
  taal eruitziet na een draai in de verkeerde, bij "Lied R" kwamen de
  Koreaanse kreten eruit als "Dear" en "Doom".
  Twee dingen die het narekenen op echte data opleverde en die op
  verzonnen testdata onzichtbaar zouden zijn gebleven. De eerste versie
  woog op Whisper's confidence, en met een mediaan van 0,55 en 127 van
  291 woorden onder de helft noemde die 137 seconden zwak in een lied
  met 97 seconden zang - de proef zou dus de hele song hebben overgedaan.
  Nu telt alleen "staat dit woord in de songtekst", met een brug over de
  adem tussen twee woorden binnen een regel. Resultaat bij Lied R:
  precies één zwakke plek van 5,5 s, waar het Engels "I'm confused, but
  who's who" zegt en het Koreaans 착각하지만 누가 누군지 - de echte regel.
  De tweede: `merge_runs` vult alleen stilte, en dat is in productie de
  juiste regel, maar een zwakke plek is meestal geen stilte. Op die ene
  plek voegde hij dan ook exact nul woorden toe. Binnen de gemarkeerde
  plekken, en alleen daar, mag de tweede draai de eerste vervangen; wat
  eruit komt is een DERDE variant naast de twee, en de tabel beslist,
  niet de code.
- **B516 - een meetlat die twee draaien naast elkaar legt.** 1.5.8 telt
  alleen gaten van vijf seconden of langer en gaf voor Lied R en
  Lied_R2 drie keer exact 5,3 s, terwijl de ene draai 21,5 s dekte die
  de andere niet had. Nu: gedekte zangtijd van A, van B, alleen-in-A,
  alleen-in-B, met per stuk de tekst van allebei. Bruikbaar voor elke
  A/B-vraag, niet alleen voor talen.
  Twee correcties uit de herlezing. De ondergrens van een halve seconde
  werd per woordstuk toegepast in plaats van per aaneengesloten strook,
  en Whisper-woorden zijn een derde seconde - dus een hele gemiste regel
  werd als nul gerapporteerd, precies het euvel dat deze meetlat 1.5.8
  verwijt. En de verschilregels stonden zonder kopregel onder een
  alinea, dus ze kwamen als rauwe pipes op het scherm in plaats van als
  tabel.
  Daarbij het idee van de gebruiker: twee projecten kunnen dezelfde
  opname gebruiken ("Lied R" en "Lied_R2" zijn dezelfde m4a met een
  andere songtekst), en dan is het handwerk van de een een referentie
  voor de ander. De kolom "op een echte zin" telt hoeveel gehoorde
  woorden binnen een handmatig getimede zin vallen. Dat vult een echt
  gat: "in tekst" vergelijkt fonetisch met de songtekst, en voor een
  passage in een ander schrift kan die vergelijking niet werken - bij
  "Lied R" staat het Koreaans in Latijnse letters, dus een juist
  Koreaans woord scoort daar nul hoe goed het ook is. De referentie
  weet niets van spelling. De spans worden teruggeprojecteerd naar de
  tijdlijn van het origineel, want een timing staat op de karaokeklok.

In v0.146.0 verwerkt:

- **B506 - een pin was twee kale getallen, en dat hield geen stand.** De
  handmatige woordkoppelingen wezen met een positie in de
  songtekstwoordenlijst en een positie in de transcriptie. Beide lijsten
  veranderen van vorm: B412 liet de cijfers erin, B418 splitst op een
  koppelteken, B484/B485 veranderden wat `[bg]` met de tokens doet. Elke
  keer werd er één keer gemigreerd, met een markering die zegt dat het
  gedaan is - en juist die markering is de fout, want hij belooft dat de
  lijst nooit meer verandert. Gemeten bij "Lied R": honderdtwintig pins,
  waarvan zesenzestig twee tot dertien plaatsen misgewezen in
  aaneengesloten rijen (keys 104-112 wezen naar transcript 77-85, terwijl
  die woorden bij songtekstwoord 91-99 horen), en niet één foutmelding -
  een verschoven pin blijft werken, hij bedoelt alleen een ander woord.
  Een pin draagt nu naast zijn nummers een beschrijving: welk
  songtekstwoord (tekst, regelnummer, het hoeveelste voorkomen op die
  regel) en welke gevonden woorden (tekst en starttijd), plus een
  vingerafdruk van beide lijsten. Klopt de vingerafdruk nog, dan worden
  de nummers ongemoeid gebruikt; klopt hij niet, dan wordt elke pin op
  zijn beschrijving teruggezocht en gaat wat niet meer te vinden is weg
  MET een logregel. De eerste keer wordt er niets verplaatst: wat er
  staat is dan het ijkpunt, want er is geen beschrijving van wat het
  ooit bedoelde en gokken zou een gok vastleggen. Opslaan vanuit de
  editor wist de beschrijving, zodat de pins daarna betekenen waar ze op
  dat moment naar wijzen.
- **B506-vervolg - een lege pin was onzichtbaar.** Vierenvijftig van de
  honderdtwintig pins bij "Lied R" waren leeg ("dit woord heb ik
  losgekoppeld"), en een pin - ook een lege - wint het altijd van de
  automatische koppeling. Ze kregen bovendien status "coupled", dus er
  stond niets op het scherm dat verklaarde waarom een woord los bleef
  terwijl het identieke woord er recht boven stond. Ze hebben nu een
  eigen kleurcode met een regel in de legenda, en er is een derde stand
  bij gekomen naast koppelen en loskoppelen: "Vrijgeven" haalt de
  handmatige beslissing weg, zodat de automaat het woord terugkrijgt.
  Zonder die stand kon een woord dat je ooit had losgekoppeld nooit meer
  terug.
- **B507 - het karaokeblokje was langer dan het originele blokje.** Het
  gekoppelde originele blokje wordt uit de gezongen span van zijn
  karaokeregel gebouwd, maar de karaokecel zelf kwam uit `_dict_span`,
  en die telde het inline `[bg]`-stuk gewoon mee. Alles wat verder over
  de lengte van een zin redeneert (`TimedLine._sung`,
  `timing_editor._line_span`) sloeg dat stuk sinds B485 al over; deze
  ene plek niet. Gemeten bij "Lied R": regel 19 was 0,79 s langer dan
  zijn origineel, regel 24 en 25 elk ongeveer 0,35 s. Het bg-stuk krijgt
  nu een eigen, gestippeld blokje op zijn eigen tijd - in de zinnen-,
  blok- én woordweergave, want achtergrondzang hoort in elke editor te
  staan en alleen niet in de render. Het wordt getekend, niet gesleept:
  het beweegt mee met de zin waar het bij hoort.
- **B508 - de originele baan was een achterdeur.** `_move_original`
  verplaatste of rekte een originele zin, rekende de gekoppelde
  karaokeregels mee, en draaide daarna geen enkele controle op de
  karaokebaan: `_keep_in_order` en `_without_overlap` werden daar niet
  aangeroepen. Bij een regel met een bg-stuk ging het altijd mis, omdat
  dat stuk meeschaalt voorbij het eind. Bovendien begrensde hij op de
  duur van het ORIGINEEL terwijl die baan sinds B489 op de karaokeklok
  loopt. Beide zijn recht. En in plaats van twee spiegelroutes die elk
  hun gaten hadden - `_mirror_to_original` werkte alleen bij een
  1-op-1-koppeling, en in de blokweergave draaide hij helemaal niet -
  wordt het gekoppelde blokje na elke sleep opnieuw uit zijn rijen
  afgeleid, met dezelfde min/max-regel waarmee de editor wordt
  opgebouwd. De regelcontroles van B500 draaien nu ook in de editor: na
  elke sleep, en een zin met overlap, nul lengte of verkeerde volgorde
  krijgt een oranje rand. Dat is waar zo'n overlap gemaakt wordt; hem
  drie stappen later in een rapport noemen is te laat.
- **B509 - een hele `[bg]`-regel stond als wees in de baan.** Zulke
  regels worden bewust buiten `couple_timing` gehouden (B264): ze zouden
  een eigen plaats innemen in de blok- en regeltelling, en een regel die
  OVER een andere klinkt heeft die plaats niet. Maar daarmee kregen ze
  ook geen koppeling, dus stonden de twee `[bg]LIED_R[/bg]`-regels aan
  het eind van "Lied R" tegenover de twee songtekstregels `Twee-uh` die
  erbij horen zonder dat de een van de ander wist - uitzetten van de een
  liet de ander oplichten, en het originele blokje was helemaal niet uit
  te zetten (`if not rows: return False`). Na `attach_bg_lines` koppelt
  een tweede ronde de overgebleven bg-regels aan de overgebleven
  songtekstzinnen, op POSITIE: tussen de zinnen van de gekoppelde
  buurregels ervoor en erna. Bewust niet op bloknummer - de twee teksten
  tellen elk hun eigen witregels, en leunen op de aanname dat die
  nummers gelijk lopen is precies wat bij B488 stukging. Een bg-regel
  met een tegenhanger haalt zijn tijd daaruit; alleen zonder tegenhanger
  valt hij terug op de buurregel, en dán klinkt hij ook echt mee.
- **B510 - `disabled` betekende twee dingen tegelijk.** Een hele
  `[bg]`-regel bleef alleen buiten de render doordat `attach_bg_lines`
  hem uitgeschakeld geboren liet worden; `video.py` filtert op
  `disabled` en `TimedLine` had helemaal geen bg-vlag. Zet je zo'n regel
  in de editor aan - de enige manier om te zien waar hij ligt - dan
  stond hij in de video. Bij "Lied R" stonden regel 53 en 54 aan. `bg`
  is nu een eigen veld op de regel, de render filtert daarop, en
  `disabled` betekent weer wat de gebruiker ermee bedoelt. De vlag komt
  uit de karaoketekst (`apply_inline_crowd`), niet uit het timingbestand,
  en `_to_dict`/`_from_dict` nemen hem mee - dezelfde val waar de
  lettergreep-bg bij B485 al een keer in wegviel. `line_checks` stelt
  een bg-regel vrij van de overlapcontrole: achtergrondzang KAN tegelijk
  met een andere zin klinken, en hoeft dat niet.
- **B511 - de omlijningskleur stond bij twee van de vier verkeerd.**
  `contra_colour` besliste op waargenomen helderheid met de grens op
  128. Wit (255) en grijs (158) kregen daarmee terecht zwart, maar rood
  `#E53935` komt op 108 uit en kreeg wit, en groen `#3CB043` op 128,9 en
  kreeg zwart - allebei omgekeerd aan wat de gebruiker wil, en dat groen
  kantelde op 0,9 punt. Zijn wens is bovendien niet als helderheidsregel
  te schrijven: de grens zou tegelijk onder 108 en boven 129 moeten
  liggen. Het gaat ook niet over helderheid - groen is de actieve kleur
  en moet oplichten, rood is de crowdkleur en moet gewicht krijgen tegen
  een donkere achtergrond. Daarom een vaste tabel voor de vier
  standaardkleuren, met de helderheidsregel als terugval voor een kleur
  die de gebruiker zelf kiest. De vier `outline_*`-instellingen gaan
  eenmalig leeg (markering `outline_reset`), want een ingevulde waarde
  wint van de tabel en zou het oude beeld in leven houden.
- **B512 - wat beantwoord is, gaat weg met zijn onderwerp.** 1.5.11f
  heeft gedraaid over achttien projecten: 1 ms vóór, 1 ms ná, winst
  +0 ms. Dertien van die achttien stonden vóóraf al op 0 of 1 ms - daar
  viel niets te repareren, want binnen de zinnen is het handwerk gewoon
  de automatische verdeling. Op de vijf liederen waar echt met de hand
  in de zinnen is geschoven won de knop vier keer nul en verloor hij één
  keer 14 ms. De bijstelknop van B497 is daarmee eruit, met
  `pipeline.refit_syllables`, `_refit_syllables` in de editor,
  `refit_trial`/`_syllable_error` in het testpaneel en de bijbehorende
  vertaalsleutels. Waar c, d en e uitgezet zijn en bewaard, ging deze
  mee met zijn onderwerp: een proef die zijn eigen meetobject niet meer
  heeft kan alleen nog zijn antwoord herhalen. Dat antwoord staat hier.
  1.5.11c (de vensterproef) is om dezelfde reden verwijderd, samen met
  `_project_with_the_biggest_gap` dat alleen door hem gebruikt werd.

Wat de kritische herlezing in deze ronde vond (twee lezers, allebei op
draaiende reproductie in plaats van alleen lezen) - en het is de moeite
waard omdat de zwaarste vondst NIET in de nieuwe code zat:

- **De waarschijnlijke oorzaak van de drift bij "Lied R" zelf.**
  `set_word_pins` schreef alleen de markering `layout`, niet
  `lyrics_layout`. Die tweede is het enige wat `migrate_lyric_pins`
  tegenhoudt, dus na élke opslag in de koppeleditor draaide de
  B417-conversie opnieuw over keys die al omgezet waren. Gemeten op een
  tekst met een koppelteken erin: een pin op "hey" liep naar "het" en
  daarna naar "nu", twee woorden per opslag, opstapelend. Die bug is
  ouder dan B506 en B506 zou hem hebben vastgelegd in de beschrijving.
- Het regelnummer in een pin-beschrijving was het RUWE bestandsregel-
  nummer, dus één witregel invoegen hernummerde de hele rest van het
  lied terwijl er geen woord verschoof - en gooide elke pin daarna weg.
  Het telt nu de regels die woorden hebben.
- Drie keer "na" die allemaal een beetje verschoven vielen bij het
  terugzoeken op één gevonden woord samen; er wordt nu gereserveerd.
- Een pin die niet te beschrijven was bleef in de nummers staan en
  verdween ongeteld bij de volgende ronde.
- `sanitize_timing`, `repair_line_edges` en `enforce_monotonic` duwden
  de eigen tijd van een bg-regel meteen weer weg - juist de overlap die
  B510 expliciet toestaat. Alle drie stellen bg nu vrij.
- In de editor was een bg-regel een muur geworden: `_without_overlap`,
  `_keep_in_order` en `_reenable_fit` sloegen `disabled` over maar niet
  `bg`, dus de editor weigerde wat de controle correct noemt.
- `_reworded`, `carry_over` en `sync_timing_with_text_change` lieten de
  bg-vlag vallen bij een tekstwijziging.
- Het opnieuw inschakelen van een regel verkort ook de BUREN, en die
  blokken bleven achter - precies de drift die B508 wegneemt.
- De klemvolgorde in `_move_original` liet een gespiegelde crowd- of
  uitgeschakelde buur meetellen, waardoor een sleep naar rechts naar
  links sprong en daarna vastzat.
- Een klik op een bg-blok viel door naar de cel drie posities verder
  (zelfde rij), waarna "regel aan/uit" de verkeerde regel trof.
- De omlijningswisser draaide wél vaker dan één keer: de markering komt
  alleen via `save_config` in het bestand, en er zijn draaien die nooit
  opslaan. Hij schrijft nu meteen terug.

In v0.145.0 verwerkt:

- **B499 - de markering "uit origineel terughalen" zat op de verkeerde
  tekst.** Ik kleurde de KARAOKEzin blauw en zette er `[origineel]` voor;
  daarmee raakte juist de tekst verborgen waar de gebruiker mee bezig is.
  De markering hoort bij het ORIGINEEL dat wordt teruggehaald, dus staat
  hij nu op het blokje in de originele baan, met de tekst gewoon
  leesbaar. Tweede helft: een stuk dat in 1.4 wordt verplaatst of
  uitgerekt overleefde niet - `set_restore_fragments` filterde afgeleide
  blokken eruit en bij de volgende doorgang werd het opnieuw uit de
  timing afgeleid. Zo'n verplaatsing wordt nu per regelnummer bewaard
  (`restore_moved`), en dat is meteen wat de gebruiker vroeg: ligt het
  stuk niet meer op de zin, dan krijgt die zin een blauwe stippelrand, en
  zet nóg een klik op "terug uit origineel" hem terug op de zin. Pas de
  klik daarna zet de markering uit - dat is de goede volgorde, want een
  verplaatsing ongedaan maken is de kleinere stap. Let op de valkuil die
  hier in zat: het herkennen van een verplaatsing vergelijkt tegen de
  KALE afleiding (`apply_moves=False`); tegen de afleiding mét
  verplaatsing zou hij na één keer opslaan zeggen dat er niets verplaatst
  is.
  Op de vraag van de gebruiker of dit de timing raakt: nee.
  `apply_manual_damping` schrijft alleen de dempings- en
  terughaalgegevens, het bewerkte wav-bestand is sample-exact even lang
  (dempen vermenigvuldigt met een envelope, terughalen kopieert en klemt
  op de lengte), en de verankering wordt berekend op de ONBEWERKTE
  karaoke. Er wordt dus nooit opnieuw verankerd.
- **B500 - de logica draaide niet aan het eind, en keek nooit tussen de
  regels.** Het voorstel van de gebruiker ("logica stap aan het einde
  nogmaals") raakte een groter gat dan hij dacht. Ten eerste: er wordt
  halverwege het genereren opgeschoond (`sanitize_timing`), maar daarna
  verschuiven de energie-woordtiming, de fonetische verdeling en het
  aanhouden nog van alles - en wat daar uitkomt ging ongecontroleerd de
  editor en de render in. Er staat nu een slotcontrole op, die zegt
  hoeveel regels ze heeft rechtgetrokken. Ten tweede, en erger:
  `timing_checks` keek uitsluitend BINNEN één zin - volgorde, te kort,
  nul lang, gestapelde en overlappende lettergrepen. Er was geen enkele
  controle tussen de regels: geen overlap tussen regel k en k+1, geen
  regel van nul lang, geen volgorde van regels. Precies wat je in de
  editor en in het beeld ziet, werd door niets gemeten. Die controles
  zijn er nu (`line_checks`), met de uitzonderingen die er horen: een
  crowdregel mag over zijn buren liggen (een kreet klinkt tegelijk met de
  zang, B346) en een uitgeschakelde regel telt niet mee.
- **B501 - overvloeien bij intro en outro.** De intro vloeit in de
  laatste halve seconde over naar het tekstbeeld en de outro in de eerste
  seconde vanuit de tekst, in de kleuren die er op dat moment staan.
  Daarvoor is `_compose_frame` uit elkaar getrokken in `_title_frame` en
  `_text_frame`; op de twee grensmomenten worden allebei gebouwd en met
  `Image.blend` over elkaar gelegd. Dat kost ongeveer 75 extra beelden
  per video, dus de rendertijd merkt er niets van. De creditregel volgt
  nu `outro_start` in plaats van `first_text`, anders viel hij tijdens
  het overvloeien weg.
- **B502/B503 - een reeks zonder koppeling ziet eruit als een
  hallucinatie.** De gebruiker wees een stuk transcriptie aan waar geen
  enkel woord gekoppeld was en zei: hier hoort een filter op. Het
  bestaande filter kon dat niet zien: het werkt per segment en
  alles-of-niets, het slaat segmenten van één woord over (het eist
  minstens twee kernwoorden), en het weegt met `max()` - één woord dat
  toevallig boven 0,65 scoort redt het hele segment. Zijn signaal is
  beter dan het mijne, en het is pas ná de koppeling te meten: een reeks
  van vier of meer gevonden woorden achter elkaar zonder één koppeling.
  Dat kan per definitie geen gekoppeld woord raken. Bewust een markering
  en geen verwijdering: bij een lied met een passage in een andere taal
  (Lied R) is zo'n reeks juist échte zang, en dan moet je hem met de
  hand kunnen koppelen. Daarnaast droeg de baan met gevonden woorden
  helemaal geen kleurcodes - alleen "gefilterd" - terwijl de
  songtekstbaan er vijf had. Die tabel geldt nu voor allebei.
- **B504 - wat de knop van B497 waard is.** Het idee van de gebruiker
  om er een meting voor te maken, uitgewerkt: neem de projecten die
  zowel handwerk als automatische timing hebben, geef elke automatische
  regel de ZINSGRENZEN van het handwerk - dat is de situatie waar de
  knop voor gemaakt is, nagespeeld - en meet de fout op de
  lettergreepgrenzen tegen dat handwerk, vóór en ná het bijstellen. Het
  verschil is precies wat de knop oplevert, en het handwerk is daarbij de
  ijklat in plaats van het onderwerp. Draait alleen waar het handwerk bij
  de huidige tekst hoort (gelijk aantal regels); anders is elk getal
  ruis.
- **B505 - de regelverschuiving rekende met één stapel terwijl er twee
  zijn.** Bij B473 stapelen de regels op hun echte hoogte, en de
  vloeiende verschuiving liet elke regel "naar de plek van het slot
  eronder" gaan - maar beide plekken kwamen uit de NIEUWE stapel, terwijl
  de beweging vanaf de OUDE zou moeten beginnen. De afstand tussen twee
  getekende regels was tijdens die 0,35 s daardoor een mengsel van twee
  stapels, en met een afgebroken zin boven een enkele zin was dat mengsel
  kleiner dan de hoogte van de bovenste - dan liep de tweede beeldrij
  door de zin eronder. Er worden nu twee stapels berekend en daartussen
  geïnterpoleerd.

Wat de kritische herlezing eruit haalde:

- `line_checks` onthield ook een crowd- of uitgeschakelde regel als "de
  vorige", waardoor de laatste gewone zin vergeten werd en een overlap
  met zo'n regel ertussen nooit gezien werd. Zulke regels worden nu
  helemaal overgeslagen - ook voor de volgorde- en nul-controle, want
  een uitgeschakelde restregel op een oude tijd zette de regel erna vals
  in de lijst.
- De slotcontrole gebruikte `enforce_monotonic`, en die duwt een regel
  vooruit zodra zijn voorganger doorloopt. Een regelBEGIN is juist vaak
  gemeten - op de zanginzet gezet (B333/B357) - en dat vooruit duwen zet
  de zin naast de zang én perst hem samen. Gemeten: een regel op 13,0-15,0
  werd 14,0-15,0. De slotcontrole is nu een eigen `repair_line_edges` die
  alleen echte gebreken herstelt, nooit een begin verzet, en een overlap
  van het EINDE van de vorige regel afhaalt - de minst betrouwbare kant
  van een zin, precies wat B224 al bijknipt.
- Het diagnosebestand werd geschreven vóór die slotcontrole, dus het
  beschreef iets anders dan wat er in `timing.json` kwam. En `mark_held`
  stond niet meer als laatste, terwijl dat oordeel over de uiteindelijke
  spans gaat. Allebei rechtgezet.
- De markering was voor een hele `[bg]`-regel onzichtbaar: die zit niet
  in de koppeling, heeft dus geen blok in de originele baan, en de
  karaokebaan was net "met rust gelaten". De karaokezin houdt tekst en
  kleur, maar krijgt wel een blauwe rand - dan is te zien dát hij
  gemarkeerd is zonder dat de tekst eronder verdwijnt.
- Een teruggehaalde crowdzin was niet te onderscheiden van "het stuk ligt
  er niet meer op": allebei gestippeld. Crowd is gestreept, verplaatst is
  gestippeld.
- 1.5.11f mat ook projecten zonder handwerk. `generate_timing` schrijft
  dezelfde inhoud naar `timing.json` én `timing_auto.json`, dus "allebei
  aanwezig" zegt niets; bij zo'n project is de fout vóóraf overal nul en
  kan het bijstellen alleen verliezen. Die worden overgeslagen, en levert
  de hele proef geen enkel cijfer op, dan is dat een overslag en geen
  gedraaide proef.
- Een gefilterd woord telde mee in de verdachte reeks en verloor zijn
  eigen markering, waarmee de drempel feitelijk op één woord kwam. En een
  woord dat je uit het filter haalt of met de hand koppelt bleef eruitzien
  als gefilterd; die status wordt nu bijgewerkt.
- Kon de timing niet gelezen worden, dan toonde 1.4 geen zin-blokken en
  wiste opslaan stilzwijgend álle markeringen. Dat gebeurt alleen nog als
  de afleiding echt gelukt is.

Nog open:

- **B495 op Koreaans.** Whisper met de taal op Koreaans proberen bij
  zowel "Lied R" (fonetisch in Latijnse letters) als "Lied_R2" (echte
  tekens), en kijken of dat de gaten opvult die Whisper-Engels open
  laat. Dat is een meting op de machine van de gebruiker. De herkenning
  zelf is af (v0.144.0) en getoetst op echte Hangul; wat ontbreekt is de
  uitkomst van de proef.
- **Pauzes binnen een zin.** Lied_Q en "Lied K":
  B492/B493 hebben de oorzaak aangepakt, maar of het in de praktijk goed
  genoeg is moet nog blijken.
- **Een niet-aaneengesloten handkoppeling zet de gevonden rij door
  elkaar.** Koppel je een songtekstwoord met de hand aan gevonden woord
  1, 2 en 4, dan slaat `_relayout` gevonden woord 3 over en dat krijgt
  pas in het vangnet een kolom, uiterst rechts. Gemeten: `top_col` werd
  `[0, 1, 2, 7, 3]`. Met de koppelingen die de automaat maakt gebeurt
  het niet (0 van 4000 willekeurige layouts), alleen met de hand. Ouder
  dan B513 en niet erdoor veroorzaakt.
- **Een origineel zonder karaokeregel is niet uit te zetten.** Sinds
  B509 heeft vrijwel elke originele zin een tegenhanger en werkt het
  uitzetten op het paar. Blijft er een zin over die met niets gekoppeld
  is, dan is er ook geen tweede om mee uit te zetten en heeft hij geen
  eigen uit-stand; dat is bewust niet gebouwd omdat het een hele stap
  met eigen afhankelijkheid zou kosten voor een geval dat op de
  ijkverzameling niet meer voorkomt.
