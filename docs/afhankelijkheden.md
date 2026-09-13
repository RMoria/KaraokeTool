# Wat werkt waarin door

Alles wat dit gereedschap maakt komt via een keten van tussenstappen uit
vier bronbestanden: het origineel, de karaokeversie, de songtekst en de
karaoketekst. Verandert er iets aan het begin van zo'n keten, dan klopt
bijna alles daarna niet meer.

Dit bestand is de leesbare kant van `modules/dependencies.py`, waar die
keten als gegevens vastligt. **Het wordt gegenereerd** door
`tools/write_dependency_doc.py`; wijzig de keten in de module, niet hier.
Een test vergelijkt dit bestand met wat de generator maakt, en een tweede
test controleert dat elke stap en elk projectgegeven dat de code gebruikt
ook echt in de keten staat. Zo kan er geen afgeleide meer bestaan waarvan
niemand heeft bepaald wanneer hij verouderd is.

## Hoe je het leest

Onder **Van bron naar afgeleide** staat per bronbestand alles wat eruit
volgt: verander je dat bestand, dan vervalt die hele lijst. Onder **Per
artefact** staat het omgekeerde: waar hangt dit ding zelf van af.

Twee koppelingen zijn niet vanzelfsprekend en verklaren veel:

- `karaoketekst.txt` stuurt via de vulwoord-prioriteit ook de
  **woordkoppeling van de songtekst**, en dus de regeltijden. Je
  parodietekst bepaalt mede welke originele woorden gekoppeld worden.
- `songtekst.txt` zit in de cachesleutel van Whisper (als beginprompt).
  De songtekst wijzigen kan dus een volledige hertranscriptie afdwingen.

Wat bewust NIET doorwerkt is net zo belangrijk, want te veel weggooien
kost handwerk. De parodietekst wijzigen raakt de transcriptie en de
handmatige woordkoppelingen niet; een verse karaoke-transcriptie
(restzang) kost geen handwerk aan het origineel; een ander beeldmerk
maakt alleen de video oud. En de gerenderde video zelf wordt nooit
weggegooid - die kost minuten en de gebruiker beslist zelf wanneer hij
opnieuw rendert.

## Van bron naar afgeleide


### `input:original` — input/origineel.* (het origineel)

Verandert dit, dan vervallen 36 afgeleiden.

- Stappen: `align`, `analysis_karaoke`, `analysis_original`, `clusters_karaoke`, `clusters_original`, `coupling`, `karaoke`, `lyrics`, `original_restore_resample`, `source_original`, `timing`, `transcript_override`, `whisper_karaoke`, `whisper_original`, `word_coupling`
- Projectgegevens: `karaoke_from_original`, `vocal_end_s`, `vocal_onset_s`
- Bestanden: `cache:demucs_original`, `cache:karaoke_edited`, `cache:karaoke_generated`, `cache:original_for_restore`, `cache:original_vocals`, `cache:original_wav`, `cache:transcription_karaoke`, `cache:transcription_original`, `output:alignment_json`, `output:analysis_karaoke`, `output:analysis_original`, `output:clusters_karaoke`, `output:clusters_original`, `output:demucs_mp3`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `input:karaoke` — input/karaoke.* (de karaokeversie)

Verandert dit, dan vervallen 25 afgeleiden.

- Stappen: `align`, `analysis_karaoke`, `clusters_karaoke`, `coupling`, `fragment_exclusions`, `karaoke`, `original_restore_resample`, `restore_fragments`, `restore_lines`, `restore_moved`, `source_karaoke`, `timing`, `whisper_karaoke`
- Projectgegevens: `karaoke_from_original`
- Bestanden: `cache:demucs_karaoke`, `cache:karaoke_edited`, `cache:karaoke_wav`, `cache:original_for_restore`, `cache:transcription_karaoke`, `output:alignment_json`, `output:analysis_karaoke`, `output:clusters_karaoke`, `output:karaoke_edit`, `output:timing`, `output:timing_diagnostics`


### `input:lyrics` — input/songtekst.txt

Verandert dit, dan vervallen 22 afgeleiden.

- Stappen: `analysis_original`, `clusters_original`, `coupling`, `karaoke`, `lyrics`, `lyrics_override`, `original_overrides`, `source_lyrics`, `stress_anchors`, `timing`, `transcript_override`, `whisper_original`, `word_coupling`
- Projectgegevens: `language_choice`
- Bestanden: `cache:karaoke_edited`, `cache:transcription_original`, `output:analysis_original`, `output:clusters_original`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `input:karaoke_text` — input/karaoketekst.txt

Verandert dit, dan vervallen 7 afgeleiden.

- Stappen: `coupling`, `source_karaoke_text`, `stress_anchors`, `timing`
- Bestanden: `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `input:logo` — input/logo.* (beeldmerk in de video)

Verandert dit, dan vervallen 1 afgeleiden.

- Stappen: `source_logo`


### `config:whisper` — instelling: Whisper-model en taal

Verandert dit, dan vervallen 23 afgeleiden.

- Stappen: `analysis_karaoke`, `analysis_original`, `clusters_karaoke`, `clusters_original`, `coupling`, `karaoke`, `lyrics`, `timing`, `transcript_override`, `whisper_karaoke`, `whisper_original`, `word_coupling`
- Bestanden: `cache:karaoke_edited`, `cache:transcription_karaoke`, `cache:transcription_original`, `output:analysis_karaoke`, `output:analysis_original`, `output:clusters_karaoke`, `output:clusters_original`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `config:forced_alignment` — instelling: preciezere woordtijden (wav2vec2)

Verandert dit, dan vervallen 23 afgeleiden.

- Stappen: `analysis_karaoke`, `analysis_original`, `clusters_karaoke`, `clusters_original`, `coupling`, `karaoke`, `lyrics`, `timing`, `transcript_override`, `whisper_karaoke`, `whisper_original`, `word_coupling`
- Bestanden: `cache:karaoke_edited`, `cache:transcription_karaoke`, `cache:transcription_original`, `output:analysis_karaoke`, `output:analysis_original`, `output:clusters_karaoke`, `output:clusters_original`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `config:chunked` — instelling: transcriptie in stukken (gaten opvullen)

Verandert dit, dan vervallen 17 afgeleiden.

- Stappen: `analysis_original`, `clusters_original`, `coupling`, `karaoke`, `lyrics`, `timing`, `transcript_override`, `whisper_original`, `word_coupling`
- Bestanden: `cache:karaoke_edited`, `cache:transcription_original`, `output:analysis_original`, `output:clusters_original`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `config:analysis` — instelling: analysedrempels

Verandert dit, dan vervallen 4 afgeleiden.

- Stappen: `analysis_karaoke`, `analysis_original`
- Bestanden: `output:analysis_karaoke`, `output:analysis_original`


### `config:cluster` — instelling: clusterdrempels

Verandert dit, dan vervallen 8 afgeleiden.

- Stappen: `clusters_karaoke`, `clusters_original`, `karaoke`, `lyrics`
- Bestanden: `cache:karaoke_edited`, `output:clusters_karaoke`, `output:clusters_original`, `output:karaoke_edit`


### `config:align` — instelling: uitlijning

Verandert dit, dan vervallen 9 afgeleiden.

- Stappen: `align`, `coupling`, `karaoke`, `timing`
- Bestanden: `cache:karaoke_edited`, `output:alignment_json`, `output:karaoke_edit`, `output:timing`, `output:timing_diagnostics`


### `config:karaoke` — instelling: demping (gain, fades)

Verandert dit, dan vervallen 3 afgeleiden.

- Stappen: `karaoke`
- Bestanden: `cache:karaoke_edited`, `output:karaoke_edit`


### `config:timing` — instelling: zangstem-analyse, ankergewichten, fonetische timing

Verandert dit, dan vervallen 4 afgeleiden.

- Stappen: `coupling`, `timing`
- Bestanden: `output:timing`, `output:timing_diagnostics`


### `config:video` — instelling: video (kleuren, fonts)

Verandert dit, dan vervallen 0 afgeleiden.


### `config:models` — instelling: welke modellen aan of uit staan

Verandert dit, dan vervallen 7 afgeleiden.

- Stappen: `coupling`, `lyrics`, `timing`, `word_coupling`
- Bestanden: `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


## Per artefact

| Artefact | Soort | Wat het is | Afgeleid van |
|---|---|---|---|
| `input:original` | bron | input/origineel.* (het origineel) | *(bron)* |
| `input:karaoke` | bron | input/karaoke.* (de karaokeversie) | *(bron)* |
| `input:lyrics` | bron | input/songtekst.txt | *(bron)* |
| `input:karaoke_text` | bron | input/karaoketekst.txt | *(bron)* |
| `input:logo` | bron | input/logo.* (beeldmerk in de video) | *(bron)* |
| `config:whisper` | bron | instelling: Whisper-model en taal | *(bron)* |
| `config:forced_alignment` | bron | instelling: preciezere woordtijden (wav2vec2) | *(bron)* |
| `config:chunked` | bron | instelling: transcriptie in stukken (gaten opvullen) | *(bron)* |
| `config:analysis` | bron | instelling: analysedrempels | *(bron)* |
| `config:cluster` | bron | instelling: clusterdrempels | *(bron)* |
| `config:align` | bron | instelling: uitlijning | *(bron)* |
| `config:karaoke` | bron | instelling: demping (gain, fades) | *(bron)* |
| `config:timing` | bron | instelling: zangstem-analyse, ankergewichten, fonetische timing | *(bron)* |
| `config:video` | bron | instelling: video (kleuren, fonts) | *(bron)* |
| `config:models` | bron | instelling: welke modellen aan of uit staan | *(bron)* |
| `source_original` | stap | sha1 + wav-pad van het voorbereide origineel | `input:original` |
| `source_karaoke` | stap | sha1 + wav-pad van de voorbereide karaoke | `input:karaoke` |
| `source_lyrics` | stap | sha1 van songtekst.txt zoals het programma die kent | `input:lyrics` |
| `source_karaoke_text` | stap | sha1 van karaoketekst.txt zoals het programma die kent | `input:karaoke_text` |
| `source_logo` | stap | sha1 van het beeldmerk zoals het programma dat kent | `input:logo` |
| `config_signature` | stap | de gebruikte instellingen per groep (om een wijziging te merken) | *(geen — blijft altijd geldig)* |
| `cache:original_wav` | bestand | cache/original.wav | `source_original` |
| `cache:karaoke_wav` | bestand | cache/karaoke.wav | `source_karaoke` |
| `cache:demucs_original` | bestand | cache/demucs_stems_original/ (zang + instrumentaal) | `cache:original_wav` |
| `cache:demucs_karaoke` | bestand | cache/demucs_stems_karaoke/ | `cache:karaoke_wav` |
| `cache:original_vocals` | bestand | cache/original_vocals.wav (zangstem voor de energie-analyse) | `cache:demucs_original` |
| `cache:karaoke_generated` | bestand | cache/karaoke_generated.wav (instrumentaal uit het origineel) | `cache:demucs_original` |
| `output:demucs_mp3` | bestand | output/karaoke_demucs.mp3 en vocal_demucs.mp3 | `cache:demucs_original` |
| `vocal_onset_s` | projectgegeven | het moment waarop de zang begint (anker voor de eerste zin) | `cache:demucs_original` |
| `vocal_end_s` | projectgegeven | het moment waarop de zang stopt (anker voor de staart, B319) | `cache:demucs_original` |
| `karaoke_from_original` | projectgegeven | of de karaoke uit het origineel is gemaakt (uitlijning overslaan) | `input:original`, `input:karaoke` |
| `language_choice` | projectgegeven | de handmatig vastgezette taal | `input:lyrics` |
| `whisper_original` | stap | transcriptie van het origineel (sha1, model, taal, prompt) | `cache:demucs_original`, `cache:original_wav`, `input:lyrics`, `config:whisper`, `config:forced_alignment`, `config:chunked` |
| `whisper_karaoke` | stap | transcriptie van de karaoke (restzang) | `cache:karaoke_wav`, `config:whisper`, `config:forced_alignment`, `karaoke_from_original` |
| `cache:transcription_original` | bestand | cache/transcription_original.json | `whisper_original` |
| `cache:transcription_karaoke` | bestand | cache/transcription_karaoke.json | `whisper_karaoke` |
| `transcript_override` | stap | de geknipte/samengevoegde transcriptie (handwerk) | `whisper_original` |
| `lyrics_override` | stap | de geknipte/samengevoegde songtekstwoorden (handwerk) | `input:lyrics` |
| `word_coupling` | stap | handmatige woordkoppelingen (songtekstwoord -> gevonden woord) | `whisper_original`, `transcript_override`, `lyrics_override`, `input:lyrics`, `config:models` |
| `original_overrides` | stap | handmatig gecorrigeerde regeltijden van het origineel | `input:lyrics`, `lyrics_override` |
| `stress_anchors` | stap | handmatig gekoppelde stukjes origineel <-> karaoke per zin | `input:lyrics`, `input:karaoke_text`, `lyrics_override` |
| `analysis_original` | stap | analysestatistiek van de original-transcriptie | `whisper_original`, `config:analysis` |
| `output:analysis_original` | bestand | output/original/statistics.json en de csv-rapporten | `analysis_original` |
| `analysis_karaoke` | stap | analysestatistiek van de karaoke-transcriptie | `whisper_karaoke`, `config:analysis` |
| `output:analysis_karaoke` | bestand | output/karaoke/statistics.json en de csv-rapporten | `analysis_karaoke` |
| `clusters_original` | stap | gekozen klankclusters van het origineel | `whisper_original`, `config:cluster`, `input:lyrics`, `lyrics_override` |
| `clusters_karaoke` | stap | gekozen klankclusters van de karaoke (restzang) | `whisper_karaoke`, `config:cluster` |
| `output:clusters_original` | bestand | output/original/clusters.json en clusters.html | `clusters_original` |
| `output:clusters_karaoke` | bestand | output/karaoke/clusters.json en clusters.html | `clusters_karaoke` |
| `output:lyrics_alignment` | bestand | output/original/lyrics_alignment.txt | `word_coupling`, `input:karaoke_text` |
| `align` | stap | de offsetregio's tussen origineel en karaoke | `cache:original_wav`, `cache:karaoke_wav`, `config:align`, `karaoke_from_original` |
| `output:alignment_json` | bestand | output/alignment.json (rapport) | `align` |
| `coupling` | stap | origineelregels met tijden + welke karaokeregel bij welke hoort | `word_coupling`, `align`, `input:lyrics`, `input:karaoke_text`, `lyrics_override`, `transcript_override`, `original_overrides`, `config:timing`, `config:models` |
| `lyrics` | stap | aantal extra dempingsfragmenten uit de songtekst | `clusters_original`, `word_coupling` |
| `timing` | stap | de regel- en lettergreeptiming voor de video | `coupling`, `input:karaoke_text`, `vocal_onset_s`, `align`, `cache:original_vocals`, `language_choice`, `config:timing`, `config:models` |
| `output:timing` | bestand | output/settings/timing.json en timing_auto.json | `timing` |
| `output:timing_diagnostics` | bestand | output/diagnostics/timing_diagnostics.txt | `timing` |
| `fragment_exclusions` | stap | uitgevinkte dempingsfragmenten (tijden op de karaoke-tijdlijn) | `cache:karaoke_wav` |
| `restore_fragments` | stap | 'terug uit origineel'-fragmenten (karaoke-tijdlijn) | `cache:karaoke_wav` |
| `restore_lines` | stap | zinnen die uit het origineel worden teruggehaald (regelnummers) | `cache:karaoke_wav` |
| `restore_moved` | stap | verplaatste 'terug uit origineel'-stukken (per regelnummer) | `restore_lines` |
| `original_restore_resample` | stap | sha1 + samplerate van het hergebruikte origineel | `input:original`, `cache:karaoke_wav` |
| `cache:original_for_restore` | bestand | cache/original_for_restore.wav | `original_restore_resample` |
| `karaoke` | stap | de bewerkte karaoke (welke fragmenten gedempt zijn) | `cache:karaoke_wav`, `clusters_original`, `clusters_karaoke`, `fragment_exclusions`, `restore_fragments`, `restore_lines`, `restore_moved`, `align`, `config:karaoke` |
| `cache:karaoke_edited` | bestand | cache/karaoke_edited.wav | `karaoke` |
| `output:karaoke_edit` | bestand | output/karaoke_edit.mp3 en karaoke_edit.wav | `karaoke` |
| `display_name` | projectgegeven | de leesbare projectnaam | *(geen — blijft altijd geldig)* |
| `input_names` | projectgegeven | waar de invoerbestanden vandaan kwamen (voor de bestandskiezer) | *(geen — blijft altijd geldig)* |
| `input_last_dir` | projectgegeven | de laatst gebruikte map van dit project, ongeacht welke invoer (B413) | *(geen — blijft altijd geldig)* |
| `video_titles` | projectgegeven | artiest/titel voor in de video | *(geen — blijft altijd geldig)* |
| `video` | stap | de gemaakte video (pad + gebruikte audiobron) | *(geen — blijft altijd geldig)* |
