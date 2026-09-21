"""Interface language (translation layer) for the GUI.

The default language is Dutch. An extra language is simply an extra
dictionary. Texts are fetched with :func:`t`; if a key is missing in
the chosen language, then it falls back to Dutch and otherwise to the
key itself. The file conventions (``songtekst.txt``, ``[crowd]`` etc.)
are deliberately NOT in here - those stay fixed.
"""

from __future__ import annotations

import re

_CURRENT = "nl"

#: Available languages: code -> label (with flag emoji), sorted by code.
LANGUAGES: dict[str, str] = {
    "en": "🇬🇧 en",
    "nl": "🇳🇱 nl",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "nl": {
        "app_title": "Karaoke Tool",
        "tab_audio": "Muziek laden en analyse",
        "tab_video": "Karaokevideo",
        "tab_settings": "Instellingen",
        "tab_help": "Handleiding",
        "help_missing": "Handleiding niet gevonden (docs/manual.md).",
        "video_colors_group": "Videotekst-kleuren en lettertype",
        "theme_group": "Interface-kleuren",
        "reset": "Terug naar standaard",
        "song_group": "Lied-project",
        "song_label": "Songtitel:",
        "new_project": "Nieuw project...",
        "new_project_title": "Nieuw project",
        "new_project_prompt": "Songtitel voor het nieuwe project:",
        "inputs_group": "Invoerbestanden",
        "choose_file": "Kies bestand...",
        "choose_folder": "Kies map...",
        "output_dir_group": "Output-map",
        "output_dir_hint": "Waar de projectmappen (output/instellingen) komen "
                           "te staan. Kies een andere map of netwerklocatie "
                           "(UNC). Bij het instellen worden bestaande "
                           "projecten daarheen verplaatst en de verwijzingen "
                           "aangepast; input en cache blijven bij de app.",
        "lyrics": "Songtekst",
        "karaoke_text": "Karaoketekst",
        "logo": "Logo",
        "model_label": "Model:",
        "model_accurate": "Nauwkeurig (large-v3)",
        "model_medium": "Gemiddeld (distil-large-v3)",
        "model_fast": "Snel (small)",
        "advanced_group": "Grote modellen (optioneel, vallen terug indien niet beschikbaar)",
        "cache_clear": "Cache wissen bij opstarten en afsluiten",
        "cache_clear_now": "Nu legen",
        "cache_clear_now_tip": "Leeg de cache eenmalig (alle projecten). Dure "
                              "resultaten zoals de zangstem en transcriptie "
                              "worden dan opnieuw gemaakt bij de volgende run.",
        "cache_cleared_now_log": "Cache geleegd.",
        "timing_fallback_title": "Geen koppeling gebruikt",
        "timing_fallback_body": "De timing is gelijkmatig verdeeld omdat de "
                               "transcriptie/koppeling ontbrak (bv. de cache "
                               "was geleegd). Draai eerst "
                               "'{step_detect}' opnieuw, of zet 'cache "
                               "legen' uit, voor een nauwkeurige timing.",
        "steps_group": "Stappen",
        "step_detect": "1.1. Detecteer woorden",
        "step_analyse": "1.3. Analyse",
        "step_karaoke": "1.4. Karaoke aanpassen",
        "ready": "Gereed.",
        "waveform_group": "Golfvorm bewerkte karaoke (rood = gedempt)",
        "damping_editor_button": "Demping bewerken (golfvorm-editor)",
        "fragments_group": "Gedempte fragmenten (uitvinken = niet dempen; "
                           "wijzigingen worden direct toegepast en opnieuw "
                           "geëxporteerd)",
        "clusters_group": "Klankclusters (vink aan wat gedempt moet worden)",
        "clusters_hint": "Standaard niets geselecteerd. Aan-/uitvinken "
                         "wordt direct opgeslagen.",
        "open_report": "HTML-rapport openen",
        "log_group": "Meldingen",
        "language_label": "Taal:",
        "video_edit_stress": "2.1. Klemtoon bewerken",
        "video_timing": "2.2. Timing verfijnen",
        "video_edit_timing": "2.3. Timing bewerken (golfvorm)",
        "stress_title": "Klemtoon bewerken",
        "stress_hint": "Kies een zin. Boven staat het origineel, onder de "
                       "karaoke, allebei op dezelfde tijdbalk. Klik een "
                       "stukje van het origineel en daarna het karaokestukje "
                       "dat erbij hoort: dat stukje neemt de tijd van het "
                       "origineel over en de rest van de zin schikt zich "
                       "naar verhouding. Klik een gekoppeld karaokestukje "
                       "om de koppeling weer los te maken. Oranje = het "
                       "origineel houdt dat stukje lang aan.",
        "stress_group_karaoke": "Karaoke",
        "stress_group_original": "Origineel (gemeten op de opname)",
        "stress_saved": "Klemtoon opgeslagen.",
        "video_render": "2.4. Video maken",
        "video_prep_group": "Voorbereiding",
        "video_collect": "Verzamelen en kopiëren",
        "collect_none": "Er is nog geen enkele video gemaakt; er valt dus niets te verzamelen.",
        "collect_what": "{count} project(en) hebben een video. Wat gaat er mee?",
        "collect_only_video": "Alleen de video's",
        "collect_with_sources": "Verzameling: video, originele opname, songtekst en karaoketekst (map per project)",
        "collect_where": "Waar moet de verzameling naartoe?",
        "err_collect_inside": "Kies een map buiten de uitvoermap van de projecten; anders wordt de verzameling in de projecten zelf gekopieerd.",
        "collect_busy": "Verzamelen: {song} ({done}/{total})",
        "collect_done": "Verzameld: {projects} project(en), {files} bestand(en) naar {folder}",
        "open_video": "Open video",
        "damping_reset": "Reset naar originele karaoke",
        "make_karaoke": "Karaoke uit origineel (Demucs)",
        "make_karaoke_tip": "Maakt een instrumentaal uit het origineel als "
                            "er geen karaokebestand is; uitlijning is dan "
                            "niet nodig (offset 0).",
        "demucs_missing": "Demucs is niet beschikbaar. Installeer de grote "
                          "modellen via install.bat.",
        "making_karaoke": "Instrumentaal maken uit het origineel (Demucs; "
                          "dit kan even duren)...",
        "karaoke_made": "Instrumentaal (karaoke) uit het origineel gemaakt.",
        "karaoke_from_original_label": "Uit origineel",
        "editor_timing_title": "Timing bewerken",
        "editor_damping_title": "Demping bewerken",
        "zoom_in": "Zoom +",
        "zoom_out": "Zoom -",
        "source_label": "Bron:",
        "view_label": "Weergave:",
        "lane_original": "Origineel",
        "lane_original_text": "Originele tekst",
        "lane_karaoke": "Karaoke",
        "lane_vocals": "Zangstem",
        "lane_karaoke_lines": "Karaokeregels",
        "render_opts_title": "Wat wil je in de video?",
        "render_opts_text": "Tekst",
        "render_opts_audio": "Muziek",
        "render_text_karaoke": "Getimede karaoketekst",
        "render_text_original": "Getimede originele tekst",
        "render_audio_karaoke": "Karaoke-muziek",
        "render_audio_original": "Originele muziek",
        "render_audio_vocals": "Alleen zang (vocal)",
        "view_sentences": "Zinnen",
        "view_blocks": "Blokken",
        "view_words": "Woorden",
        "line_toggle": "Regel uit/aan",
        "line_toggle_tip": "Selecteer een blok/zin/woord en zet het uit "
                           "(niet in de render) of weer aan.",
        "play": "Afspelen",
        "pause": "Pauze",
        "reset_original": "Herstel origineel-timing",
        "save_timing": "Opslaan (timing.json)",
        "close": "Sluiten",
        "line_restore": "Uit origineel terughalen",
        "line_restore_tip": "Markeer de gekozen zin: bij 1.4 wordt op die tijd het geluid uit het origineel teruggehaald. De markering staat in beide banen en verhuist mee als je de zin verschuift.",
        "timing_saved_restore": " {count} zin(nen) uit origineel.",
        "add_damping": "Demping toevoegen",
        "add_restore": "Terug uit origineel",
        "remove": "Verwijderen",
        "save_apply": "Opslaan en toepassen",
        "editor_damping_hint": "Klik in de golfvorm = lijn daarheen "
                               "(gepauzeerd). Sleep een blok of rand; "
                               "randcursor = <->. Rood = demping, groen = "
                               "terug uit origineel.",
        "lang_uncertain_title": "Taal onzeker",
        "lang_uncertain_prompt": "De taal van de songtekst is niet zeker. "
                                 "Kies de taal (voor Whisper en forced "
                                 "alignment):",
        "lang_second_title": "Tweede taal in de tekst",
        "lang_second_prompt": "In de tekst staat een stuk in een ander "
                              "schrift ({code}, {count} woorden). In welke "
                              "taal moet Whisper de opnames beluisteren?",
        "lang_second_first": "{code} (gedetecteerd op de rest van de tekst)",
        "lang_second_other": "{code} (het andere schrift)",
        "lang_auto": "Automatisch (Whisper kiest zelf)",
        "lang_other": "Andere... (meer opties)",
        "video_done_title": "Video klaar",
        "activity_group": "Activiteit",
        "stop": "Stop",
        "cancel_hard": "Nog bezig; lopende programma's worden afgebroken.",
        "cancelling": "Bezig met afbreken...",
        "cancelled_done": "Afgebroken; restjes opgeruimd.",
        "delete_project": "Project verwijderen...",
        "delete_project_title": "Project verwijderen",
        "delete_project_confirm": "Weet je zeker dat je het project '{title}' "
                                  "wilt verwijderen? De invoer, uitvoer en "
                                  "cache van dit project worden definitief "
                                  "verwijderd.",
        # --- v0.51 i18n-sweep (B91) ---
        "original": "Origineel",
        "karaoke": "Karaoke",
        "on": "aan",
        "off": "uit",
        "no_title": "(geen titel)",
        "default_value": "standaard",
        "busy_title": "Bezig",
        "busy_running_body": "Er draait al een stap; even geduld.",
        "busy_step_body": "Er draait nog een stap; wacht die eerst af.",
        "busy_switch_title": "Even wachten",
        "busy_switch_body": "Er draait nog een stap; wissel van project als "
                            "die klaar is.",
        "busy_phase": "Bezig",
        "phase_elapsed": "{phase}... {elapsed} s",
        "progress_pct": "Voortgang: {done:.0f} / {total:.0f} s",
        "detect_preparing": "Invoer voorbereiden...",
        "detect_downloading": "Whisper-model wordt gedownload (eenmalig, dit "
                              "kan even duren)...",
        "detect_transcribing": "Transcriberen...",
        "detect_transcribing_parallel": "Origineel en karaoke tegelijk "
                                        "transcriberen...",
        "detect_aligning": "Origineel en karaoke uitlijnen...",
        "detect_from_cache": "[{track}] Transcriptie uit cache "
                             "({segments} segmenten).",
        "detect_ready": "[{track}] Transcriptie klaar: {segments} segmenten, "
                        "{words} woorden.",
        "parallel_detect": "Origineel en karaoke tegelijk transcriberen "
                           "(parallel)",
        "parallel_detect_tip": "Sneller op meerdere kernen, maar gebruikt "
                               "meer geheugen; valt terug op één-voor-één bij "
                               "te weinig geheugen.",
        "parallel_detect_log": "Parallelle detectie: {state} (opgeslagen).",
        "cache_clear_log": "Cache wissen bij opstarten en afsluiten: {state} "
                           "(opgeslagen).",
        "whisper_model_log": "Whisper-model: {code} (wordt zo nodig "
                             "gedownload bij de volgende transcriptie).",
        "lang_saved": "Taal opgeslagen. Herstart de app om de nieuwe taal "
                      "overal toe te passen.\n\nLanguage saved. Restart the "
                      "app to apply the new language everywhere.",
        "project_deleted_log": "Project '{title}' verwijderd (invoer, uitvoer "
                               "en cache).",
        "project_already_active": "Project '{title}' is al actief.",
        "project_opened_log": "Project '{title}' {state}.{extra}",
        "project_state_opened": "geopend",
        "project_state_new": "nieuw aangemaakt",
        "project_moved_extra": " {count} losse bestand(en) verplaatst naar de "
                               "projectmap.",
        "new_project_invalid_title": "Geen geldige titel opgegeven.",
        "project_exists_title": "Project bestaat al",
        "project_exists_body": "Er bestaat al een project '{title}'. Openen?",
        "font_preview_text": "Pa's wijze lynx bezag vroom het fikse "
                             "aquaduct 0123",
        "video_meta_group": "Titels en artiest",
        "meta_karaoke_title": "Karaoketitel:",
        "meta_orig_artist": "Originele artiest:",
        "meta_orig_title": "Originele titel:",
        "meta_background": "Achtergrondafbeelding:",
        "video_timing_group": "Karaoketekst met timing (groen = hoog "
                              "vertrouwen, geel = gemiddeld, rood = "
                              "best-effort)",
        "timing_making": "Timing-skelet maken...",
        "timing_made": "Timing gemaakt: {target} ({count} regels; {detail}).",
        # B326: the {detail} part above; the even variant doubles as the
        # signal for the warning, so compare on the key there and not on
        # a piece of text.
        "timing_detail_coupling": "zin-koppeling: {high}x hoog, {medium}x "
                                  "midden, {low}x laag",
        "timing_detail_even": "gelijkmatig verdeeld (geen songtekst-"
                              "uitlijning beschikbaar); verfijn met "
                              "'{video_edit_timing}'",
        "timing_unreadable": "timing.json is onleesbaar.",
        "no_timing_error": "Geen timing.json; doe eerst "
                           "'{video_timing}'.",
        "editor_loading": "Audio en timing laden voor de editor...",
        "no_original_editor": "Geen origineel gevonden; editor toont alleen "
                              "de karaoke.",
        "timing_saved_log": "Timing opgeslagen: {path}",
        "timing_saved_corrections": "; {count} originele correctie(s) bewaard",
        "orig_timing_restored": "Originele timing hersteld naar de "
                                "audio-uitlijning.",
        "alignment_failed_log": "Uitlijnen mislukt: {error}",
        "no_result": "geen resultaat",
        "video_rendering": "Video renderen (dit kan enkele minuten duren; de "
                           "voortgangsbalk loopt mee)...",
        "background_none": "Geen",
        "background_remove": "Afbeelding verwijderen",
        "background_use_stored": "Deze gebruiken",
        "background_delete_stored": "Opgeslagen achtergrond wissen",
        "background_delete_stored_tip": "Verwijdert de gekozen achtergrond "
                                        "uit de centrale opslag. Projecten "
                                        "die hem gebruiken houden hun eigen "
                                        "kopie.",
        "background_delete_ask": "{name} uit de opslag wissen?",
        "outline_label": "omlijning",
        "video_pick_title": "Welke video?",
        "video_pick_body": "Van dit project staan er meerdere "
                           "video's klaar. Welke wil je openen?",
        "video_done_status": "Video klaar.",
        "video_done_log": "Video klaar: {target}",
        "video_done_prompt": "{title}:\n{target}\n\nMeteen openen?",
        "open_video_button": "Video openen",
        "open_folder_button": "Map openen",
        "copy_failed": "Kopiëren mislukt",
        "copied_to_log": "{name} gekopieerd naar {target}. {note}",
        "copied_untouched_log": "{name} gekopieerd naar {target} (het "
                                "origineel blijft onaangeroerd).",
        "karaoke_text_note": "Crowd-stukken markeren met [crowd] ... "
                             "[/crowd] (die kleuren rood).",
        "choose_karaoke_text_title": "Kies de karaoketekst (nieuwe tekst)",
        "text_structure_title": "Tekststructuur",
        "choose_file_for": "Kies het bestand voor '{stem}'",
        "missing_choose": "ontbreekt - kies een bestand",
        "missing_choose_karaoke": "ontbreekt - kies een bestand of maak uit "
                                  "original",
        "missing_required": "ontbreekt (verplicht)",
        "missing_video": "geen (nodig voor de video)",
        "font_ttf": "Lettertype (.ttf)",
        "font_default": "DejaVu Sans Bold (standaard)",
        "color_before": "Tekst vóór zingen",
        "color_during": "Tijdens zingen",
        "color_after": "Na het zingen",
        "color_crowd": "Crowd tijdens zingen",
        "color_background": "Video-achtergrond",
        "choose_font_title": "Kies lettertype",
        "video_colors_reset_log": "Videokleuren en lettertype teruggezet naar "
                                  "standaard.",
        "theme_background": "Achtergrond",
        "theme_buttons": "Knoppen",
        "theme_button_active": "Knop actief (bezig)",
        "gui_colors_reset_log": "GUI-kleuren teruggezet naar standaard.",
        "model_demucs_desc": "Zang scheiden (restzang / karaoke maken)",
        "model_forced_alignment_desc": "Preciezere woordtijden (wav2vec2)",
        "model_demucs_info": "~250 MB (eenmalig) — traag op CPU (enkele "
                             "minuten per nummer), snel op GPU",
        "model_forced_alignment_info": "~360 MB per taal (eenmalig) — matig; "
                                       "sneller op GPU",
        "model_not_installed_suffix": "  — pakket niet geïnstalleerd (zie "
                                      "install.bat)",
        "model_toggle_log": "{model}: {state}.",
        "package_missing_title": "Pakket ontbreekt",
        "package_missing_body": "Voor '{model}' is het pakket nog niet "
                                "geïnstalleerd. Draai install.bat opnieuw en "
                                "kies de grote modellen, of installeer het "
                                "handmatig.",
        "model_downloading": "{model} - model downloaden/laden",
        "model_ready_log": "{model}: model gereed.",
        "damping_reapply": "Demping opnieuw toepassen...",
        "reexporting": "Opnieuw exporteren...",
        "fragments_applied_log": "Fragmenten toegepast; nieuwe export: "
                                 "{export}",
        "damping_need_step_body": "Draai eerst stap 1 (Detecteer woorden); "
                                  "daarna kun je de fragmenten op de golfvorm "
                                  "bijstellen.",
        "karaoke_wave_loading": "Karaoke-golfvorm laden...",
        "damping_applied_log": "Demping toegepast; export: {export}",
        "damping_reset_log": "Demping teruggezet naar de originele karaoke.",
        "analysing": "Analyseren en clusteren...",
        "karaoke_adjusting": "Karaoke aanpassen...",
        "exporting": "Exporteren...",
        "computing_wave": "Golfvorm berekenen...",
        "karaoke_adjusted_log": "Karaoke aangepast: {count} fragmenten, "
                                "{seconds:.1f} s gedempt met {gain} dB. "
                                "Export: {export}",
        "analyse_done_log": "[{track}] Analyse klaar: {words} woorden, "
                            "{clusters} clusters. Rapport: {report}",
        "cluster_checkbox": "Cluster {id} - {label}   (gevonden: {freq} keer, "
                            "confidence {conf:.2f}){tip}",
        "cluster_suggestion_tag": "  (suggestie)",
        "variants_label": "Varianten: {variants}",
        "suggestion_log": "[{track}] Suggestie op basis van search_words: "
                          "clusters {clusters} (staan gemarkeerd; vink zelf "
                          "aan wat je wilt dempen).",
        "selection_saved_log": "[{track}] Selectie opgeslagen: {labels}.",
        "none_word": "geen",
        "alignment_failed_title": "Uitlijnen mislukt",
        "alignment_failed_body": "Origineel en karaoke konden niet worden "
                                 "uitgelijnd:\n{error}\n\nDe timing/demping "
                                 "kan daardoor afwijken.",
        "alignment_region_log": "  uitlijning {start:.1f}-{end:.1f} s: offset "
                                "{offset:+.0f} ms (confidence {conf:.2f})",
        "alignment_weak_title": "Uitlijning onbetrouwbaar",
        "alignment_weak_body": "De uitlijning tussen origineel en karaoke is "
                               "zwak (confidence {conf:.2f}). Waarschijnlijk "
                               "verschillen de nummers te veel; de timing- en "
                               "demping-projectie kan afwijken.",
        "drift_title": "Drift gedetecteerd",
        "drift_body": "De offset tussen origineel en karaoke verloopt "
                      "{drift:.0f} ms over het nummer (drift: één loopt "
                      "sneller/langzamer).\n\nRegio-gewijs meelopen "
                      "(aanbevolen)? Nee = één vaste offset.",
        "drift_off_log": "Drift-correctie uit: één vaste offset gebruikt.",
        "drift_corrected_log": "Drift {drift:.0f} ms; regio-gewijs "
                               "gecorrigeerd ({count} regio's).",
        "lang_cancelled": "Taalkeuze geannuleerd; detectie niet gestart.",
        "lang_chosen": "Taal gekozen: {code} (wordt gebruikt voor Whisper en "
                       "forced alignment).",
        "task_failed": "Er ging iets mis: {exc} (zie het logbestand in de "
                       "map 'logs')",
        "track_done": "{track}: klaar",
        "yes": "Ja",
        "no": "Nee",
        "choose_logo_title": "Kies het logo",
        "choose_lyrics_title": "Kies de officiële songtekst",
        "lyrics_note": "De originele tekst is leidend bij de analyse.",
        "derived_invalidated": "Nieuwe invoer: eerdere resultaten (cache, "
                               "uitlijning, timing) verwijderd; stappen "
                               "opnieuw uitvoeren.",
        "lyrics_duplicate_warn": "Let op: songtekst en karaoketekst zijn "
                                 "(vrijwel) identiek. Klopt dat? Zet de juiste "
                                 "originele tekst bij het origineel.",
        "prereq_title": "Stap ontbreekt",
        "prereq_need_detect": "Doe eerst '{step_detect}'; die uitvoer "
                              "ontbreekt of is verouderd.",
        "prereq_need_analyse": "Doe eerst '{step_analyse}'; die uitvoer "
                               "ontbreekt of is verouderd.",
        "diagnostics_option": "Diagnostiek (alleen lokaal)",
        "diagnostics_tip": "Schrijft transcriptie-historie en "
                           "timing-diagnostiek naar output/<titel>/"
                           "diagnostiek/. Alleen lokaal; niets wordt "
                           "verstuurd.",
        "diagnostics_log": "Diagnostiek: {state} (opgeslagen).",
        "vocal_analyse_option": "Zangstem-analyse (aangehouden noten + "
                                "vulregels)",
        "vocal_analyse_tip": "Gebruikt de gescheiden zangstem om aangehouden "
                             "noten te verlengen en niet-getranscribeerde "
                             "'na-na'-regels op hun energie-pulsen te "
                             "plaatsen. Vereist Demucs; valt anders netjes "
                             "terug.",
        "vocal_analyse_log": "Zangstem-analyse: {state} (opgeslagen).",
        "step_couple": "1.2. Woorden koppelen",
        "couple_title": "Woorden koppelen",
        "couple_hint": "Koppel de echte songtekstwoorden (onder) aan de "
                       "gevonden woorden (boven), zodat de analyse de juiste "
                       "woorden gebruikt. Klik een woord boven én onder om te "
                       "koppelen; klik op een lijn om die te verwijderen. "
                       "Kleur = betrouwbaarheid (blauw = handmatig).",
        "couple_legend": "Kleuren:",
        "legend_filler_skipped": "overgeslagen stopwoord",
        "legend_mark_tip": "Selecteer een woord en klik hier om het als hallucinatie (bovenste rij) of vulwoord (onderste rij) aan te merken voor deze taal.",
        "mark_select_first": "Selecteer eerst een woord in de juiste rij: een gevonden woord voor hallucinatie, een songtekstwoord voor vulwoord.",
        "mark_word_added": "'{word}' toegevoegd aan de lijst voor taal {language}.",
        "mark_word_removed": "'{word}' weer uit de lijst voor taal {language} gehaald.",
        "legend_no_match": "geen match gevonden",
        "legend_hallucination": "als hallucinatie eruit gefilterd",
        "legend_transcription_gap": "Whisper hoorde hier niets",
        "legend_suspect_run": "reeks zonder koppeling - ziet eruit als een "
                              "hallucinatie; koppel met de hand als het toch "
                              "echte zang is",
        "legend_energy_placed": "niet gekoppeld, wel getimed op de zangstem",
        "legend_manually_uncoupled": "door jou losgekoppeld - de automaat "
                                     "laat dit woord met rust; met "
                                     "\"Vrijgeven\" mag hij het weer proberen",
        "legend_background": "achtergrondzang ([bg]) - staat wel in de "
                             "editors, nooit in de render",
        "legend_repeat_missing": "herhaling die de songtekst mist - deze "
                                 "woorden staan wél in de tekst, maar die "
                                 "schrijft de regel één keer en het lied "
                                 "zingt hem vaker",
        "couple_release": "Vrijgeven",
        "couple_release_tip": "Haalt de handmatige beslissing van het geselecteerde songtekstwoord weg, zodat de automatische koppeling het weer mag proberen. Anders blijft een woord dat je ooit hebt losgekoppeld voor altijd los.",
        "couple_release_first": "Selecteer eerst een songtekstwoord (onderste rij).",
        "log_pins_relocated_by_text": "%d koppeling(en) teruggezocht op het woord zelf, %d losgelaten omdat het woord er niet meer is.",
        "stress_sentence": "Zin:",
        "stress_no_room": "Deze zin zit vol: er is {seconds:.2f} s te weinig ruimte om de niet-gekoppelde stukjes hun minimum te geven. Maak een koppeling los of geef het origineel meer ruimte.",
        "legend_filtered_word": "gevonden woord dat eruit is gefilterd "
                                "(doorgestreept; handmatig koppelen mag)",
        "couple_found": "Gevonden (Whisper):",
        "couple_lyrics": "Songtekst:",
        "couple_save": "Opslaan",
        "couple_cut": "Knippen",
        "couple_cut_tip": "Selecteer een gevonden woord (boven) en knip het in "
                          "twee woorden.",
        "couple_merge": "Samenvoegen",
        "couple_merge_tip": "Selecteer een gevonden woord (boven); dit wordt "
                            "samengevoegd met het woord rechts ernaast.",
        "couple_no_data": "Geen transcriptie/songtekst om te koppelen; doe "
                          "eerst '{step_detect}' en zet de songtekst "
                          "klaar.",
        "couple_saved": "Woordkoppeling opgeslagen: {count} handmatige "
                        "koppeling(en). Analyse opnieuw uitvoeren.",
        # --- Pipeline error messages (B296) ---------------------------
        "err_no_project_delete": "Geen project geladen om te verwijderen.",
        "err_demucs_unavailable": "Demucs is niet beschikbaar; installeer de "
                                  "grote modellen via install.bat.",
        "err_no_original_instrumental": "Geen origineel gevonden om een "
                                        "instrumentaal van te maken.",
        "err_instrumental_failed": "Instrumentaal maken mislukt: {error}",
        "err_no_input_found": "Geen {names} gevonden in {dir}",
        "err_ffmpeg_missing": "ffmpeg/ffprobe niet gevonden; installeer "
                              "ffmpeg (zie README.md).",
        "err_no_transcription": "Geen transcriptie van '{track}' gevonden; "
                                "draai eerst '{step_detect}'.",
        "err_no_cluster_selection_track": "Geen clusterselectie voor "
                                          "'{track}'; draai eerst "
                                          "'{step_analyse}' en kies clusters.",
        "err_cluster_file_missing": "Clusterbestand ontbreekt ({file}); "
                                    "draai '{step_analyse}' opnieuw.",
        "err_selection_mismatch": "De selectie voor '{track}' komt niet "
                                  "overeen met de clusters; draai "
                                  "'{step_analyse}' opnieuw.",
        "err_no_prepared_audio": "Geen voorbereide audio gevonden; draai "
                                 "eerst '{step_detect}'.",
        "err_no_alignment": "Geen uitlijning gevonden; draai "
                            "'{step_karaoke}' - die maakt de uitlijning "
                            "zo nodig zelf.",
        "err_no_cluster_selection": "Geen clusterselectie gevonden; draai "
                                    "eerst '{step_analyse}' en kies "
                                    "clusters.",
        "err_no_fragments": "Geen te dempen fragmenten gevonden voor de "
                            "selectie.",
        "err_no_edited_karaoke": "Geen bewerkte karaoke gevonden; draai "
                                 "eerst '{step_karaoke}'.",
        "err_no_source_properties": "Geen broneigenschappen gevonden; draai "
                                    "eerst '{step_detect}'.",
        "err_no_text_files": "Geen karaoketekst.txt of songtekst.txt "
                             "gevonden; kies eerst de tekst.",
        "err_no_sung_lines": "De tekst bevat geen zangregels.",
        "err_no_original_audio": "Geen origineel-audio gevonden.",
        "err_no_demucs_instrumental": "Nog geen Demucs-instrumentaal "
                                      "(karaoke_demucs.mp3); draai eerst de "
                                      "analyse.",
        "err_no_vocals": "Nog geen zangstem (vocal_demucs.mp3); draai eerst "
                         "de analyse.",
        "err_no_karaoke_audio": "Geen karaoke-audio gevonden (bewerkt of "
                                "kaal).",
        "err_no_original_timing": "Geen originele-tekst-timing beschikbaar; "
                                  "koppel/analyseer eerst het origineel.",
        "err_video_input_incomplete": "Video-invoer onvolledig; er ontbreekt: "
                                      "{missing}",
        # --- HTML cluster report (B296) -------------------------------
        "html_title": "KaraokeTool - klankclusters",
        "html_heading": "Klankclusters",
        "html_intro": "Vink de clusters aan die in de karaoke gedempt "
                      "moeten worden en voer de selectie in bij "
                      "'{step_analyse}'.",
        "html_found_times": "gevonden: {count} keer",
        "html_variants": "Varianten",
        "html_avg_duration": "Gem. duur",
        "html_avg_pause": "Gem. pauze",
        "html_times": "Tijdstippen",
        "html_segments": "Segmenten",
        "html_sample_text": "Voorbeeldtekst",
        "html_cluster": "Cluster {id}",
        "html_confidence": "Confidence",
        "html_footer_label": "Selectie voor '{step_analyse}':",
        "html_copy": "Kopieer",
        "html_nothing_selected": "(niets aangevinkt)",
        "html_lang": "nl",
        "wave_unavailable": "({name} niet beschikbaar)",
        "vi_lyrics": "originele songtekst",
        "vi_karaoke_text": "karaoketekst",
        "vi_logo": "logo",
        "vi_timing": "timing per lettergreep",
        "vi_offset": "offset origineel/karaoke",
        # --- Text structure and timing sync (B326) --------------------
        "text_align_missing": "Songtekst en/of karaoketekst nog niet "
                              "aanwezig.",
        "text_align_header_ok": "Songtekst en karaoketekst komen overeen "
                                "({count} secties).",
        "text_align_header_diff": "Let op: de structuur verschilt "
                                  "(songtekst {lyrics} secties, karaoke "
                                  "{karaoke}).",
        "text_align_row": "Sectie {index}: songtekst {lyrics} / karaoke "
                          "{karaoke}  {mark}",
        "text_align_mark_ok": "OK",
        "text_align_mark_diff": "verschilt",
        "timing_sync_no_file": "Geen timing.json; niets bij te werken.",
        "timing_sync_structure_changed": "Structuur van de karaoketekst is "
                                         "gewijzigd (ander aantal "
                                         "blokken/zinnen); timing "
                                         "verwijderd - doe "
                                         "'{video_timing}' opnieuw.",
        "timing_sync_count_mismatch": "Aantal regels in timing.json komt "
                                      "niet overeen met de karaoketekst; "
                                      "timing.json niet aangepast.",
        "timing_sync_no_diff": "Geen tekstverschillen; timing.json "
                               "ongewijzigd.",
        "timing_sync_updated": "timing.json bijgewerkt: {count} regel(s) "
                               "aangepast.",
        # --- Video input details (B326) -------------------------------
        "vi_detail_lines_crowd": "{lines} regels, {crowd} crowd",
        "vi_detail_unreadable": "onleesbaar",
        "vi_detail_lyrics_fallback": "geen karaoketekst; songtekst wordt "
                                     "gebruikt (video van origineel)",
        "vi_detail_karaoke_text_missing": "{path} (crowd markeren met "
                                          "[crowd]...[/crowd])",
        "vi_detail_timing_lines": "{lines} regels, {filled} met tijden",
        "vi_detail_no_timing": "doe eerst '{video_timing}'",
        "vi_detail_offset_done": "'{step_detect}' uitgevoerd",
        "vi_detail_offset_missing": "draai '{step_detect}' (of "
                                    "'{step_karaoke}', die lijnt zelf uit)",
        # --- File dialog filters (B296) -------------------------------
        "filter_text": "Tekst (*.txt)",
        "filter_images": "Afbeeldingen (*.png *.jpg *.jpeg *.bmp)",
        "filter_image": "Afbeelding (*.png *.jpg *.jpeg *.bmp)",
        "filter_font": "Lettertype (*.ttf *.otf)",
        "filter_audio": "Audio ({patterns})",
        # --- Other visible texts (B296) -------------------------------
        "waveform_after_step4": "Golfvorm verschijnt na "
                                "'{step_karaoke}'.",
        "lines_overflow_title": "Regels lopen uit beeld",
        "lines_overflow_body": "{count} regel(s) passen niet in het "
                               "videobeeld en worden bij het renderen op een "
                               "komma afgebroken (twee rijen strak onder "
                               "elkaar). Overweeg ze korter te maken:\n  - "
                               "{preview}",
    
        # -- Log window (B315). The logger fills the %-placeholders
        # POSITIONALLY, so they stand in the same order in both
        # languages; a test guards that.
        "log_align_model_failed": 'Uitlijnmodel laden mislukt',
        "log_alignment_collapsed": 'Uitlijning teruggebracht tot één vaste offset (%+.0f ms)',
        "log_alignment_report": 'Uitlijnverslag geschreven: %s',
        "log_alignment_skipped": 'Karaoke uit origineel: uitlijning overgeslagen (offset 0)',
        "log_alignment_skipped_words": 'Uitlijning: %d woord(en) overgeslagen (vulwoord/bg), waarvan %d alsnog gekoppeld via het ankervenster',
        "log_all_excluded": 'Alle fragmenten zijn uitgesloten; er wordt niets gedempt',
        "log_already_exists": 'Bestaat al in doelmap, overgeslagen: %s',
        "log_analysis_done": 'Analyse klaar: %s',
        "log_anchors_released": '%d anker(s) losgelaten die onmogelijk snel zingen vereisten',
        "log_appusermodelid_failed": 'AppUserModelID kon niet worden gezet',
        "log_audio_loaded": 'Audio geladen: %s (%d samples, %d Hz, %d kanalen)',
        "log_background_unreadable": 'Achtergrondafbeelding onleesbaar: %s',
        "log_anchors_implausible": 'Ankers losgelaten die geen zin kunnen zijn: %d (fraseperiode %.2f s)',
        "log_lines_snapped": 'Regelbeginnen op de zanginzet gezet: %d regel(s) (%d inzetten gevonden)',
        "log_repetition_loop_dropped": 'Herhaallus uit de transcriptie gehaald: %d woord(en) zonder tijdsduur',
        "log_boundary_merged": 'Woord dat op een segmentgrens was doorgeknipt weer samengevoegd: %d keer',
        "log_missing_failed": 'Controle op ontbrekende herhalingen mislukt',
        "log_cache_filled": 'Cache gevuld voor %s: %d segmenten',
        "log_test_failed": 'Testactie %s is gestruikeld',
        "log_processes_killed": '%d extern proces(sen) afgebroken na Stop',
        "log_test_project_failed": 'Test liep vast op project %s',
        "video_exists_title": "Video bestaat al",
        "video_exists_body": "Er staat al een video van dit project.\n\nOverschrijven vervangt de laatste, \"{name}\".\nNaast elkaar bewaren maakt de nieuwe \"{next}\" en laat alles staan.",
        "video_keep_both": "Naast elkaar bewaren",
        "video_overwrite": "Overschrijven",
        "video_cancel": "Annuleren",
        "test_panel_title": "1.5. Test",
        "test_panel_intro": "Vink aan wat er moet draaien en druk op Start. De vinkjes staan altijd uit als je dit venster opent.",
        "test_scope_current": "Alleen dit project",
        "test_scope_all": "Alle projecten",
        "test_start": "Start",
        "test_no_projects": "Geen projecten gevonden om te meten.",
        "test_nothing_found": "Niets gevonden.",
        "test_weighted": "gewogen fout op {count} verzette regels: {error:.2f} s",
        "test_unique_repeated": "alles samen: uniek {unique:.2f} s, herhaald {repeated:.2f} s",
        "test_running": "{code} draait: {name}",
        "test_done": "{code} klaar.",
        "test_failed": "{code} is gestruikeld (zie het logbestand).",
        "test_project_failed": "{name}: gestruikeld (zie het logbestand)",
        "test_fill_cache": "Cache vullen",
        "test_fill_cache_hint": "Zet het transcriptiecachebestand terug waar het is opgeruimd. Schrijft alleen dat bestand; koppeling en timing blijven staan. Duurt lang.",
        "test_status": "IJkset-status",
        "test_status_hint": "Per project: is er een cache, is er handmatige timing, hoeveel regels, en met welke versie de automatische timing is gemaakt.",
        "test_missing": "Ontbrekende herhalingen",
        "test_missing_hint": "Zoekt in alle projecten naar wat er duidelijk gehoord is maar niet in de songtekst staat.",
        "test_ruler": "Meetlat draaien",
        "test_ruler_hint": "De volledige meting over alle projecten met handmatige timing. Dit is het cijfer dat over releases heen wordt gevolgd, met de vorige versies ernaast. Projecten die sinds de vorige draai niet veranderd zijn, worden overgeslagen.",
        "test_split": "Uniek tegen herhaald",
        "test_split_hint": "Splitst de fout in regels waarvan de tekst uniek is en regels die herhaald worden. Herhaalde regels zijn veel foutiever; dit cijfer volgt die kloof.",
        "test_leave_out": "Weglaatproef",
        "test_leave_out_hint": "Zet elk model om de beurt anders (aan wordt uit, uit wordt aan) en meet wat dat doet. De snelle broer van de grote proef: alleen losse modellen, een paar minuten.",
        "test_reports": "Projectcontrole (teksten, filters, structuur)",
        "test_reports_hint": "Drie goedkope rapporten in één: songtekst tegen karaoketekst, wat de leesfilters weghalen, en de structuur per lied. Samen nog geen minuut.",
        "test_part_texts": "teksten",
        "test_part_filters": "filters",
        "test_part_structure": "structuur",
        "test_syllables": "Woord- en lettergreeptoetsen",
        "test_syllables_hint": "Toetst de woord- en lettergreeptijden zonder handmatige waarheid: tegen de vorm, tegen de audio, tegen elkaar en tegen herhalingen van dezelfde regel.",
        "test_syllable_intro": "Geen fout maar aanwijzingen: vorm = volgorde/overlap/gaten/te kort/te snel binnen een zin, tussen = lege zinnen, zinnen over elkaar en zinnen in de verkeerde volgorde, duur = zinnen die ver van dezelfde zin elders liggen, herhaal = hoe verschillend dezelfde regel twee keer wordt ingedeeld (lager is beter).",
        "test_syllable_total": "Samen: {shape} vormfouten, {silence} woorden in een gemeten stilte, {between} keer iets mis tussen twee zinnen, {duration} zinnen met een onwaarschijnlijke duur.",
        "test_select_all": "Alles aanvinken",
        "test_select_none": "Alles uitvinken",
        "test_force_again": "Opnieuw meten",
        "test_force_again_hint": "Negeer bewaarde uitslagen van deze versie en meet alles opnieuw.",
        "test_skipped_note": "{count} project(en) overgeslagen: er lag al een meting van deze versie op dezelfde bestanden.",
        "test_history_head": "Naast de vorige versies:",
        "test_history_note": "Vergeleken met {count} eerdere versie(s); een streepje betekent dat die versie dit project niet heeft gemeten.",
        "test_without": "zonder",
        "test_with": "MET  ",
        "test_on": "aan",
        "test_off": "UIT",
        "test_all_on": "zoals nu",
        "test_model_state": "Modellen: {state}",
        "test_matrix_state": "Stand van het register bij deze meting: {state}. Een model dat UIT staat wordt andersom gemeten - dan staat er wat AANZETTEN zou opleveren.",
        "test_matrix_made_with": "Gemeten met versie {version}. Een verslag van v0.128.0 t/m v0.137.0 is ONGELDIG: die versies maten elke ronde dezelfde stand.",
        "test_matrix_symmetry": "Voor een model dat aan staat is dit wat uitzetten kost; voor een model dat uit staat wat aanzetten zou opleveren. Een plus betekent in beide gevallen: de huidige stand is de betere.",
        "test_matrix_pairs_all": "Alle {count} paren, zonder drempel. In v0.115.0 gingen alleen modellen met eigen effect mee, en juist die tabel liet zien waarom dat fout is: de ankertoets en de energieplaatsing samen uit gaven 5,66 s waar 3,66 verwacht werd. Een model dat alleen niets doet, kan een vangnet zijn.",
        "log_model_disabled": "Model UIT: %s (%s) - %s",
        "log_model_enabled": "Model weer aan: %s",
        "log_model_unknown": "Onbekend model in de instellingen genegeerd: %s",
        "log_template_retimed": "Regel opnieuw getimed uit een sjabloon: '%s' (%s), sjabloonduur %.2f s",
        "log_template_total": "Regels opnieuw getimed uit een sjabloon: %d",
        "log_template_failed": "Sjabloontiming niet gelukt",
        "heavy_language_used": "Taal voor alle varianten: {code}. Één keer bepaald uit de volledige songtekst en aan elke draai en elk stuk meegegeven, zodat een variant niet kan verschillen doordat de taaldetectie die draai iets anders vond.",
        "heavy_language_auto": "niet vastgezet (auto) - de metingen hieronder kunnen door taaldetectie zijn beïnvloed; kies de taal met de hand op tab 1",
        "heavy_chunk": "Knippen en samenvoegen",
        "heavy_chunk_intro": "Vier manieren om Whisper dezelfde zangstem te laten horen, op {name}: zoals nu, twee keer met een verschoven start, en geknipt in {pieces} stukken op de stiltes met een eigen prompt per stuk. Er is {seconds} s gemeten zang. Waar het om gaat is de kolom \"niet gehoord\": seconden waar wel gezongen wordt maar geen woord staat.",
        "heavy_chunk_advice": "Het samenvoegen mag alleen gaten vullen, nooit overrulen: twee draaien delen dezelfde beginprompt, dus dat ze het eens zijn bewijst niets. Alleen de zangstem weet niets van de tekst en heeft daarom het laatste woord. Wint een variant duidelijk, dan is dat een instelling waard; scheelt het niets, dan weten we dat de vensterranden niet de oorzaak zijn.",
        "heavy_chunk_words": "De gehoorde woorden per variant staan in {path}; leg ze naast songtekst.txt voordat 'meer woorden' als winst telt.",
        "heavy_chunk_tail": "Let op: er wordt na de laatste tekstregel nog {seconds} s gezongen. Dat is ontbrekende tekst, geen gemiste zang - die seconden staan hieronder wel in 'niet gehoord'.",
        "log_measure_failed": "Meting van een project mislukt; de rest loopt door",
        "log_pool_unavailable": "Meten over losse processen lukt niet; terug naar één proces",
        "log_merge_filled": "Woorden uit een tweede transcriptie toegevoegd waar de eerste zweeg: %d",
        "log_chunked_started": "Transcriptie in stukken: %d stukken, samen met de hele draai in één wachtrij.",
        "log_second_language_run": "Tweede taal in de tekst gevonden (%s); het hele lied wordt ook in die taal gelezen, alleen om stiltes te vullen.",
        "log_second_language_filled": "Tweede taal (%s): %d woorden ingevuld die de eerste taal niet had.",
        "log_chunked_filled": "Stukken vulden %d woorden bij; niet gehoorde zang van %.1f s naar %.1f s.",
        "log_chunked_skipped": "Niets om op te knippen (geen gemeten zangvensters); één gewone draai.",
        "log_chunk_failed": "Stuk %.1f-%.1f s mislukt; de rest van de draai gaat door.",
        "log_loudness_failed": "Geluidsniveau kon niet worden gemeten; de video krijgt het niveau van de bron.",
        "log_loudness_silent": "Geen bruikbaar geluidsniveau (stilte of vrijwel stilte); niveau van de bron blijft staan.",
        "log_auto_rebuilt": "Automatische timing opnieuw gemaakt: %s (%d regels); de handmatige timing is niet aangeraakt.",
        "log_auto_rebuild_failed": "Automatische timing kon niet opnieuw worden gemaakt.",
        "log_auto_rebuild_mismatch": "Automatische timing van %s niet opnieuw gemaakt: de handmatige timing heeft %d regels en de karaoketekst levert er %d. Het handwerk is ouder dan de tekst; pas de tekst aan of maak de timing opnieuw.",
        "log_fps_lifted": "Beeldsnelheid van %d naar %d gezet; zet hem terug in config.json als je de oude wilt.",
        "log_outline_reset": "Omlijningskleur teruggezet op automatisch (%s); de standaardkleuren bepalen hem nu.",
        "log_anchors_capped": "%d anker(s) alleen op de duur afgekeurd; hun gemeten begin blijft staan en alleen de duur wordt gekapt.",
        "log_runaway_filtered": "Vastgelopen herhaling weggelaten (%.1f-%.1f s): één woord van %.1f s en %d tekens. Er is daar wél gezongen, maar dit segment zegt niet waar.",
        "ab_only": "Alleen door **{name}** gedekt en niet door {other}: {seconds} s in {count} stuk(ken).",
        "ab_more": "... en nog {count} kortere stukken.",
        "heavy_two_languages": "Zoektocht met twee talen",
        "heavy_two_languages_nowhere": "Geen enkel project heeft een passage in een ander schrift, dus er is hier geen tweede taal om te proberen.",
        "heavy_two_languages_intro": "Over {count} project(en) met een passage in een ander schrift. Drie manieren van lezen (hele lied in de grootste taal, hele lied in de tweede taal, en de grootste taal geknipt op de stiltes) plus de samenvoeging die het programma nu maakt, allemaal in één tabel gelegd naast uw eigen timing van dezelfde opname.",
        "heavy_two_languages_filled": "De tweede taal ({name}) vult {count} woord(en) in waar de eerste taal niets hoorde. Dat is precies wat het programma nu ook doet.",
        "heavy_two_languages_pair": "Grootste taal: {first}. Tweede taal volgens de tekens: {second} ({count} woorden).",
        "heavy_two_languages_runaway": "{count} vastgelopen herhaling(en) uit de draai {name} gelaten voordat er geteld wordt - zo'n lus dekt het gat waar hij in zit en zou juist die plek gezond laten lijken.",
        "search_intro": "{count} manieren om dezelfde {seconds} s zang te lezen, naast elkaar. \"Afstand tot regelbegin\" is de mediane afstand van uw eigen regelbegin tot het dichtstbijzijnde woordbegin - lager is dichter bij uw handwerk, en daarop is de tabel gesorteerd.",
        "search_best": "Dichtst bij het handwerk: {name} ({distance:.2f} s van een regelbegin, {share:.0f}% op een echte zin).",
        "search_no_reference": "Geen handmatige timing van dezelfde opname gevonden; de tabel is dan gesorteerd op gedekte zangtijd en zegt minder.",
        "search_took": "Deze zoektocht kostte {seconds:.0f} s.",
        "search_whole": "hele lied",
        "search_col_run": "draai",
        "search_col_words": "woorden",
        "search_col_in_text": "in tekst",
        "search_col_covered": "gedekt",
        "search_col_unheard": "niet gehoord",
        "search_col_on_line": "op een echte zin",
        "search_col_distance": "afstand tot regelbegin",
        "search_col_spot": "plek",
        "search_chunked": "geknipt",
        "search_fill_silence": "eerste taal + tweede taal alleen in de stilte",
        "heavy_two_languages_reference": "Referentie voor \"op een echte zin\": de handmatige timing van {name}, dat dezelfde opname gebruikt ({count} zinnen). \"In tekst\" kan een juist Koreaans woord niet belonen als de songtekst het fonetisch in Latijnse letters schrijft; dit cijfer weet niets van spelling.",
        "heavy_two_languages_note": "De voorzichtigste samenvoeging mag alleen gaten vullen: de eerste draai blijft de waarheid en de tweede taal kan nooit een woord overrulen dat gewoon gehoord is. De ruimere laten de tweede taal ook binnen de zwakke plekken spreken. Wordt \"in tekst\" lager terwijl \"gedekt\" stijgt, dan is het gat gevuld met verzinsels en heb je niets gewonnen - daarom staan die twee kolommen naast elkaar.",
        "log_config_write_failed": "Kon de instellingen niet terugschrijven naar %s.",
        "log_loudness_measured": "Geluidsniveau karaoke: %.1f LUFS, piek %.1f dBTP; doel %.1f LUFS, haalbaar met rechte versterking tot %.1f LUFS.",
        "log_loudness_limited": "Let op: %.1f LUFS haalt dit nummer niet met een rechte versterking; er wordt %.1f dB gecomprimeerd.",
        "log_versions_changed": "Pakketversies gewijzigd sinds de vorige start: %s",
        "log_version_lookup_failed": "Versienummer van een pakket kon niet worden gelezen",
        "log_version_history_failed": "Versiegeschiedenis kon niet worden gelezen of geschreven",
        "log_updates_available": "Updates beschikbaar volgens de vorige controle: %s",
        "log_project_not_saved": "Geen lied gekozen, dus niets weggeschreven naar %s",
        "log_stray_project_store": "Losse projectadministratie zonder lied gevonden: %s. Die hoort bij geen enkel project en mag weg.",
        "template_no_duration": "geen duur",
        "template_too_fast": "te snel om te zingen",
        "template_longer": "%.1fx langer dan elders",
        "template_shorter": "%.1fx korter dan elders",
        "heavy_probe_nowhere": "Geen enkel project heeft een gat van betekenis: overal waar gezongen wordt heeft Whisper tekst geproduceerd. Er valt hier dus niets te onderzoeken.",
        "heavy_no_measurable": "Geen enkel project heeft handmatige timing, dus er valt niets te meten. Zet de reikwijdte op \"Alle projecten\", of corrigeer eerst de timing van een project met de hand.",
        "log_unsung_dropped": "Segment zonder gemeten zang weggelaten: %.1f s ('%s')",
        "log_unsung_total": "Segmenten zonder gemeten zang weggelaten: %d",
        "test_rebuild": "Alle video's opnieuw maken",
        "test_rebuild_hint": "Rendert elk project met een timing opnieuw, met de standaardachtergrond op iedere video. Per project: eerst renderen en laten controleren, dan pas de oude video's (alle volgnummers) naar de map _to_delete verplaatsen. Mislukt een render, dan blijft daar alles staan. Doet niet mee met 'alles aanvinken'.",
        "rebuild_intro": "{count} project(en), achtergrond {background} op elke video. De oude video's gaan pas weg nadat de nieuwe is gemaakt en goedgekeurd.",
        "rebuild_no_timing": "geen timing, niets te renderen",
        "rebuild_background_missing": "standaardachtergrond niet gevonden; oude achtergrond blijft staan",
        "rebuild_background_failed": "achtergrond niet geplaatst",
        "rebuild_kept_name": "oude video kon niet weg; de nieuwe houdt zijn volgnummer",
        "rebuild_total": "{made} video('s) opnieuw gemaakt, {replaced} oude verplaatst naar {folder}.",
        "test_heavy": "Zware proeven (nachtklus)",
        "test_heavy_hint": "Combinatie-onderzoeken die uren duren: alle combinaties binnen een cluster, en een zoektocht naar de beste stand met controle op achtergehouden liedjes. Doet NOOIT mee met 'Alles aanvinken'. Elk onderzoek slaat zichzelf over tot het twintig versies geleden is.",
        "heavy_intro": "Zware combinatie-onderzoeken. Volledig uitputten over alle modellen is 2^17 = 131.072 metingen, ruim vierhonderd uur; hieronder staat wat wél betaalbaar is en dezelfde kennis oplevert.",
        "inventory_intro": "# Inventarisatie\n\nDrie tellingen over alle projecten, zonder Whisper en zonder modellen. Bedoeld om een vermoeden in een getal te veranderen voordat er iets gebouwd wordt.",
        "inventory_uncoupled": "Woorden die nooit koppelen",
        "inventory_uncoupled_head": "{never} van {total} tekstwoorden ({percent:.1f}%) kregen geen koppeling. Zit hier een patroon in - een woordsoort die principieel niet kan matchen - dan is dat de volgende 45.",
        "inventory_held": "Lang aangehouden lettergrepen",
        "inventory_held_head": "{count} van {total} lettergrepen ({percent:.1f}%) worden lang aangehouden.",
        "inventory_held_note": "De videorenderer kan dit al tonen (het veld `held`), maar niets zet het ooit aan; over alle projecten staat het nergens op waar.",
        "inventory_blocks": "Blokken die terugkomen",
        "inventory_blocks_head": "{count} bloktekst(en) komen meer dan een keer voor. Grote spreiding betekent dat hetzelfde blok de ene keer veel langer duurt dan de andere - dat is drift op blokniveau.",
        "inventory_no_material": "Geen materiaal gevonden voor deze telling.",
        "sanity_all_clear": "Logica-controle: geen enkel model liet een kapotte regel achter (lettergrepen zonder eigen moment, gestapelde lettergrepen, omgekeerde of overlappende tijden).",
        "sanity_found": "Logica-controle: {count} meting(en) lieten een kapotte regel achter. Dit staat los van de gewogen fout, die alleen naar regelbegins kijkt.",
        "heavy_clusters": "Alle combinaties binnen een cluster",
        "heavy_search": "Zoektocht naar de beste stand",
        "heavy_cluster_intro": "Modellen die elkaar aantoonbaar raken vormen een cluster; binnen zo'n cluster worden ALLE combinaties gemeten. Modellen die niemand raken hebben dat niet nodig - daarvoor is de losse tabel van 1.5.10 al het hele antwoord.",
        "heavy_cluster_too_big": "Cluster met {count} modellen overgeslagen: dat is 2^{count} metingen en de grens staat op {max}. Betreft: {names}.",
        "heavy_needs_matrix": "Geen modelmatrix gevonden. Draai eerst 1.5.10; de clusters komen uit die parentabel, en daarop gokken zou de hele proef waardeloos maken.",
        "heavy_no_clusters": "Geen enkel paar toont een wisselwerking. Dan zijn de losse cijfers van 1.5.10 het volledige antwoord en valt er hier niets uit te putten.",
        "heavy_flat_matrix": "De modelmatrix staat op nul: alle paren geven exact +0,00. Dat is geen uitkomst maar een kapotte meting - de versies v0.128.0 t/m v0.137.0 maten elke ronde dezelfde stand. Draai 1.5.10 opnieuw voordat deze proef iets kan zeggen.",
        "heavy_search_intro": "Niet inventariseren maar kiezen: vanaf de huidige stand steeds de omzetting nemen die het meest oplevert, tot niets meer helpt. Een paar keer opnieuw beginnen dekt af dat de klim op een lagere heuvel eindigde.",
        "heavy_search_split": "Gezocht op {search} liedjes met handmatige timing; {held} liedjes zijn ACHTERGEHOUDEN en tellen alleen bij de controle: {names}. Liedjes zonder handmatige timing doen niet mee - daar valt niets te meten.",
        "heavy_search_verdict": "Beste gevonden combinatie: {names}. Verschil op de zoekset {gain:+.2f} s, op de achtergehouden liedjes {held:+.2f} s (negatief is beter, net als in de tabel hierboven).",
        "heavy_search_overfit": "**Let op**: de winst op de achtergehouden liedjes is minder dan de helft van die op de zoekset. Dat is het patroon van overfitten - er is dan iets gevonden dat bij deze liedjes past en niet bij het volgende lied.",
        "heavy_too_few_songs": "Te weinig projecten ({count}) om een deel achter te houden; zonder controleset zegt een gevonden combinatie niets.",
        "heavy_already": "Al gemeten op versie {version}, en er is sindsdien niets veranderd aan de projecten of de modelstand. Vink 'Opnieuw meten' aan om hem toch te doen.",
        "heavy_not_chosen": "Niet aangevinkt bij deze draai.",
        "fill_cache_auto": "Automatische timing opnieuw gemaakt voor {count} project(en): {names}; de handmatige timing is niet aangeraakt.",
        "test_skipped_projects": "Buiten de meting gelaten (wel handmatige timing, geen timing_auto.json om tegen af te zetten): {names}. Draai 1.4 opnieuw voor die projecten, of laat het automatische bestand opnieuw maken.",
        "test_letter_off": "(uit)",
        "heavy_switched_off": "Uitgezet: {reason} Aanzetten kan in één regel in modules/test_panel.py.",
        "heavy_off_chunk_answered": "de vraag is beantwoord - het knippen draait sinds v0.138.0 in productie.",
        "heavy_off_gain_answered": "de vraag is beantwoord - het hardste niveau wint op het totaal maar levert op één lied verzinsels op (62% in tekst), en de aanname is weerlegd: de zachtste zangstem verandert nauwelijks.",
        "heavy_gain": "Niveau van de zangstem",
        "heavy_gain_intro": "Helpt een harder gezette zangstem Whisper? De stemmen lopen over alle projecten van -10,5 tot -26,9 LUFS uiteen, zestien decibel, dus als niveau iets uitmaakt moet het hier te zien zijn. Gemeten op {count} liedjes met de grootste gaten. Minder 'niet gehoord' is beter; springt 'in tekst' omlaag, dan zijn de extra woorden verzinsels.",
        "heavy_gain_level": "Zangstem zoals hij nu is: {lufs:.1f} LUFS, piek {peak:.1f} dBTP.",
        "heavy_gain_note": "Wint een niveau duidelijk, dan is dat een instelling waard en kan deze proef uit. Scheelt het niets, dan weten we dat en kan hij ook uit.",
        "heavy_done": "Zware proeven klaar: {count} regels weggeschreven naar {path}.",
        "log_test_result": "Testactie %s klaar in %.1f s",
        "log_test_busy_machine": "Let op: %s duurde %.0f s wandklok tegen %.0f s rekentijd - er liep ander werk op deze machine, dus die tijd is niet te vergelijken met een eerdere draai",
        "log_history_delete_failed": "Kon de testhistorie niet verwijderen: %s",
        "log_syllable_checks_failed": "Woord- en lettergreeptoetsen niet gelukt",
        "test_matrix": "Grote proef (modelmatrix)",
        "test_matrix_hint": "Meet alle modellen op blok-, zin-, koppel- en woordniveau: apart, in ALLE paren, in omgekeerde volgorde en per project. Schrijft docs/modelmatrix.md, ook halverwege. Reken op een half uur; afbreken kost je alleen de laatste variant.",
        "test_matrix_intro": "Wat elk model bijdraagt aan de timing, gemeten met de meetlat over alle projecten met handmatige timing. Lagere fout is beter. \"Verschil\" is wat er gebeurt als het model UIT staat: een plus betekent dat het model iets waard is.",
        "test_matrix_where": "Per model het project waar uitzetten het meeste kost (daar komt het model tot zijn recht) en waar het juist schaadt. Een model dat overal ongeveer nul geeft maar één project sterk verbetert, staat op de verkeerde plek aan.",
        "test_matrix_pairs": "Twee modellen tegelijk uit. Staat \"samen\" ver van \"los opgeteld\", dan werken ze op dezelfde regels en verdient de combinatie aandacht.",
        "test_order_skipped": "overgeslagen, model staat uit",
        "test_matrix_order": "Dezelfde modellen, andere volgorde. Nul verschil betekent dat de volgorde er niet toe doet en de code op dat punt vrij is.",
        "test_matrix_coupling": "De woordkoppeling telt geen fout maar dekking: hoeveel tekstwoorden houden een koppeling over en wat blijft er liggen. \"Zwak\" telt de koppelingen onder gelijkenis 0,75 - de mediaan stond eerder overal op 1,00 en was dus blind voor de vraag waarvoor die kolom bedoeld was. Meer dekking bij een gelijk aandeel zwak is winst; meer dekking met meer zwak is een model dat gokt.",
        "test_matrix_words": "Op woord- en lettergreepniveau is er geen handmatige waarheid, dus geen fout. Dit zijn zelfcontroles, en de scherpste is \"grensovergang\": de forced alignment meet per woord een begin en eind op de zangstem, los van het lettergreepmodel, en een lettergreep die daaroverheen ligt is aantoonbaar mis.",
        "test_matrix_done": "Grote proef klaar: {count} regels weggeschreven naar {path}.",
        "step_fill_cache": "1.5. Test",
        "fill_cache_none": "Alle projecten hebben hun transcriptiecache nog.",
        "fill_cache_done": "Cache gevuld voor {count} project(en).",
        "missing_repeat_log": 'Meer herhalingen gehoord dan de songtekst heeft: {start:.1f} s, bij regel {line} ("{text}")',
        "missing_unknown_log": 'Duidelijk gehoord maar niet in de songtekst: {start:.1f} s, bij regel {line} ("{text}")',
        "missing_repeat_summary": 'Let op: op {count} plek(ken) zingt het origineel meer herhalingen dan de songtekst heeft ({spots}{more}).',
        "missing_unknown_summary": 'Daarnaast {count} duidelijk gehoord woord(en) die niet in de songtekst staan - zie het logboek.',
        "missing_spot": '{start:.1f} s bij regel {line}',
        "missing_more": ' en nog {count}',
        "log_phantom_words_dropped": 'Spookwoorden uit de transcriptie gehaald (geen duur, geen betrouwbaarheid): %d',
        "log_tail_on_windows": 'Staart op de zangvensters geplaatst: %d regel(s)',
        "log_artifact_in_position": 'Artefact van Whisper eruit gelaten: %r (%.2f-%.2f s, taal %s); die woorden staan hier niet in de songtekst',
        "log_language_word_added": 'Woord %r toegevoegd aan lijst %s van taal %s',
        "log_language_word_removed": 'Woord %r uit lijst %s van taal %s gehaald',
        "log_beat_analysis_failed": 'librosa-beatanalyse mislukt',
        "log_beat_times_failed": 'librosa-beattijden bepalen mislukt',
        "log_best_effort_timing": 'Best-effort timing: %s',
        "log_cache_cleaned": 'Cache opgeschoond: %d item(s) recursief verwijderd',
        "log_cache_current": "Cache actueel voor '%s'; conversie overgeslagen",
        "log_cache_item_failed": 'Kon cache-item niet verwijderen: %s',
        "log_cache_not_empty": 'Cache niet volledig leeg; %d item(s) resteren: %s',
        "log_cleaned_after_cancel": 'Na afbreken opgeruimd: cache gewist en transcriptie/uitlijning teruggezet',
        "log_cleanup_failed": 'Opruimen na afbreken mislukt',
        "log_cluster_selection_saved": 'Clusterselectie (%s) opgeslagen: %s',
        "log_cluster_written": 'Clusteruitvoer geschreven: %s en %s (%d clusters)',
        "log_command": 'Commando: %s',
        "log_config_loaded": 'Configuratie geladen uit %s',
        "log_config_saved": 'Configuratie opgeslagen naar %s',
        "log_converted_wav": 'Geconverteerd naar wav: %s -> %s',
        "log_could_not_remove": 'Kon %s niet verwijderen',
        "log_could_not_write_ffmpeg": 'Kon %s niet schrijven (ffmpeg)',
        "log_couple_paint_error": 'Fout in koppel-editor paintEvent (afgevangen)',
        "log_couple_save_failed": 'Woordkoppeling opslaan mislukt',
        "log_damping_applied": 'Demping toegepast: %d fragmenten, %.1f s, %s dB',
        "log_damping_fragments": 'Dempingsfragmenten: %d (uit %d voorkomens)',
        "log_damping_reset": 'Demping teruggezet naar de originele karaoke',
        "log_delete_failed": 'Kon niet verwijderen (in gebruik?): %s',
        "err_no_project_for_background": "Kies eerst een project; een "
                                        "achtergrond hoort bij een liedje.",
        "log_timing_corrected": 'Slotcontrole: %s regels rechtgetrokken '
                                '(overlap of nul lang).',
        "log_orphans_all": 'Alle %s invoermappen zouden wees zijn tegen '
                           'uitvoermap %s; niets opgeruimd.',
        "log_inline_mark_skipped": 'Regel %s heeft in de tekst een ander '
                                   'aantal woorden dan in de timing; '
                                   'crowd/achtergrond niet gemarkeerd.',
        "log_orphans_skipped": 'Geen projecten in uitvoermap %s; wezen niet '
                               'opgeruimd (dat zou alle invoer wissen).',
        "err_video_in_use": "De video is gemaakt, maar kon niet op zijn "
                            "plek gezet worden - staat {target} nog open in "
                            "een speler? De nieuwe video staat klaar als "
                            "{scratch}.",
        "background_delete_failed": "Wissen mislukt; het bestand is "
                                    "misschien in gebruik.",
        "log_original_times_guessed": 'Geen betrouwbare tijd in de originele tekst; '
                                      '%s regels gelijkmatig verdeeld zodat ze in de '
                                      'editor te plaatsen zijn.',
        "log_demucs_cached": 'Demucs-stems gecachet (%s): %s',
        "log_demucs_copy_failed": 'Kon Demucs-stems niet naar de cache kopiëren: %s',
        "log_demucs_karaoke_done": 'Demucs-karaoke opgeleverd: %s',
        "log_demucs_marker_failed": 'Kon bronmerk bij de Demucs-stems niet schrijven: %s',
        "log_model_half_downloaded": 'Het model in %s is maar half binnengehaald; er wordt opnieuw gedownload',
        "log_transcript_unchanged": 'De transcriptie van %s is woord voor woord dezelfde als de vorige; koppeling en timing blijven staan',
        "log_transcript_fingerprint_failed": 'Kon geen vingerafdruk van de transcriptie maken',
        "log_demucs_reused": 'Demucs-stems hergebruikt uit cache (%s): %s',
        "log_demucs_separating": 'Demucs scheiden: %s',
        "log_demucs_stale": 'Demucs-stems in de cache (%s) horen bij andere audio; opnieuw scheiden',
        "log_demucs_started_original": 'Groot model gestart: Demucs op het origineel (zang isoleren voor betere transcriptie)',
        "log_demucs_started_residual": 'Groot model gestart: Demucs (zang scheiden voor restzang-detectie; geen taal nodig)',
        "log_demucs_stem_done": 'Demucs-stem opgeleverd: %s',
        "log_derived_delete_failed": 'Kon afgeleide niet verwijderen (in gebruik?): %s',
        "log_derived_nothing": 'Wijziging van %s: er stond niets afgeleids klaar',
        "log_derived_removed": 'Afgeleiden verwijderd na wijziging van %s: %s',
        "log_empty_dir_cleaned": 'Lege map opgeruimd: %s',
        "log_energy_word_line_skipped": 'Energie-woordtiming overgeslagen voor regel %d (%r)',
        "log_energy_word_skipped": 'Energie-woordtiming overgeslagen (afgevangen)',
        "log_export_mp3_cbr": 'Export (mp3, CBR %d bps)',
        "log_export_mp3_vbr": 'Export (mp3, VBR ~%s bps): kwaliteit -q:a %d',
        "log_export_wav": 'Export (wav): %s',
        "log_file_delete_failed": 'Kon bestand niet verwijderen: %s',
        "log_filler_on_energy": '%d vulregel(s) op zang-energie geplaatst (%.1f-%.1f s)',
        "log_report_file": "Testverslag van deze draai: %s",
        "log_report_write_failed": "Kon het testverslag niet schrijven: %s",
        "report_title": "Testverslag",
        "report_when": "Gedraaid op %s.",
        "report_version": "Versie %s.",
        "report_scope": "Bereik: %s.",
        "report_actions": "Acties: %s.",
        "report_time": "Duur %.1f s (processortijd %.1f s).",
        "report_alarms": "Alarmen:",
        "report_scope_current": "alleen het huidige project",
        "report_scope_all": "alle projecten",
        "log_block_gap_clipped": '%d regel(s) tussen %.1f en %.1f s niet over de blokgrens verdeeld: %d deel(en)',
        "log_held_note_capped": 'regel %d: vastgehouden noot begrensd op de blokgrens (%.1f -> %.1f s)',
        "log_filler_spread": '%d vulregel(s) over de gezongen tijd verdeeld (%.1f-%.1f s, %d inzet(ten) gevonden)',
        "log_forced_alignment_applied": 'Forced alignment toegepast op %d segmenten',
        "log_forced_alignment_failed": 'Forced alignment mislukt; Whisper-timing behouden',
        "log_forced_alignment_skipped": 'Forced alignment overgeslagen: geen zekere taal (Whisper-timing behouden)',
        "log_forced_alignment_started": 'Groot model gestart: forced alignment (wav2vec2, taal=%s)',
        "log_fragment_exclusions": 'Fragmentuitsluitingen: %d',
        "log_global_offset": 'Globale offset: %+.0f ms (confidence %.2f)',
        "log_gui": 'GUI: %s',
        "log_hallucination_filtered": 'Hallucinatie-segment gefilterd: %r (%.1fs-%.1fs), beste songtekst-match %.2f',
        "log_hallucination_position": 'hallucinatie op positie gefilterd: %r (%.1fs-%.1fs); songtekst-venster woord %d-%d, beste match %.2f',
        "log_hallucinations_filtered": "Hallucinatie-segmenten uit de koppeling gefilterd: %d (bv. 'MUZIEK')",
        "log_history_unreadable": 'Transcriptie-historie onleesbaar; opnieuw gestart',
        "log_history_updated": 'Transcriptie-historie bijgewerkt: %s (run %d, %s)',
        "log_history_write_failed": 'Kon transcriptie-historie niet schrijven (%s)',
        "log_instrumental_made": 'Instrumentaal (karaoke) uit origineel gemaakt: %s (uitlijning wordt overgeslagen, offset 0)',
        "log_input_names_migrated": 'Bestandsnamen van de invoer onder de huidige sleutel gezet (%d stuks)',
        "log_karaoke_from_original_failed": 'Karaoke maken van origineel mislukt',
        "log_karaoke_generated": 'Karaoke gegenereerd uit origineel: %s',
        "log_karaoke_is_instrumental": 'Karaoke is de Demucs-instrumentaal; restzang-analyse overgeslagen (geen zang).',
        "log_karaoke_text_loaded": 'Karaoketekst geladen: %d regels (%d crowd, %d bg)',
        "log_karaoke_text_open_bg": 'Karaoketekst eindigt binnen een [bg]-blok; sluit het af met [/bg]',
        "log_karaoke_text_open_crowd": 'Karaoketekst eindigt binnen een [crowd]-blok; sluit het af met [/crowd]',
        "log_karaoke_vocals_empty": 'Karaoke-zangstem is (nagenoeg) leeg (RMS %.4f < %.4f); transcriptie overgeslagen',
        "log_language_fixed": "Taal handmatig vastgezet op '%s'",
        "log_language_from_original": '[karaoke] Taal overgenomen van het origineel: %s',
        "log_language_from_text": '[%s] Taaldetectie op eigen tekst: %s (%s) -> doorgegeven aan Whisper',
        "log_language_manual": '[%s] Taal (handmatig gekozen): %s',
        "log_language_too_close": '[%s] Taaldetectie te dicht bij elkaar (%s); Whisper detecteert de taal zelf (auto)',
        "log_language_uncertain": '[%s] Taaldetectie onzeker (%s); Whisper detecteert de taal zelf (auto)',
        "log_librosa_resample_missing": 'librosa-resample niet beschikbaar, val terug op scipy',
        "log_logfile_failed": 'Kon logbestand niet verwijderen: %s',
        "log_logs_cleaned": 'Logs opgeschoond: %d verwijderd, %d behouden',
        "log_lyrics_aligned": 'Songtekst uitgelijnd: %d/%d woorden gekoppeld',
        "log_lyrics_alignment_failed": 'Songtekst-uitlijning mislukt; wordt overgeslagen',
        "log_lyrics_extras": "Songtekst-extra's: %d tijdvakken",
        "log_lyrics_loaded": 'Songtekst geladen: %d woorden (%d bg)',
        "log_lyrics_open_bg": 'Songtekst eindigt binnen een [bg]-blok; sluit het af met [/bg]',
        "log_lyrics_override_cleared": 'Songtekst-override gewist',
        "log_lyrics_override_saved": 'Songtekst-override opgeslagen: %d woord(en)',
        "log_manual_damping": 'Handmatige demping toegepast: %d fragmenten',
        "log_meta_removed": "Meta '%s' verwijderd uit project.json",
        "log_meta_updated": "Meta '%s' bijgewerkt in project.json",
        "log_move_failed": 'Verplaatsen mislukt: %s',
        "log_mp3_written": 'Mp3 geschreven: %s',
        "log_no_alignment": 'Geen uitlijning gevonden; wordt automatisch gemaakt',
        "log_no_lyrics_language": "[%s] Geen songtekst; Whisper-taalinstelling '%s' gebruikt",
        "log_no_reliable_windows": 'Geen betrouwbare venstermetingen; globale offset wordt voor de hele song gebruikt',
        "log_no_truetype": 'Geen TrueType-lettertype gevonden; standaardfont wordt gebruikt',
        "log_onset_difference_failed": 'Zang-onset uit verschil bepalen mislukt',
        "log_onset_failed": 'Zang-onset bepalen mislukt voor %s',
        "log_onset_from_demucs": 'Zang-onset uit Demucs-zangstem: %.2f s',
        "log_onset_from_difference": 'Zang-onset bepaald uit origineel-karaoke: %.2f s',
        "log_onset_from_karaoke": 'Zang-onset uit karaoke-zangstem: %.2f s',
        "log_onset_from_original": 'Zang-onset uit origineel-zangstem: %.2f s',
        "log_onset_placement_rejected": 'inzet-plaatsing verworpen (%.2f s regel) voor %d vulregel(s) (%.1f-%.1f s)',
        "log_onsets_failed": 'Energie-inzetten bepalen mislukt',
        "log_open_browser_failed": 'Browser openen mislukt voor %s',
        "log_open_dir_failed": 'Map openen mislukt voor %s',
        "log_open_dir_skipped": 'Map openen overgeslagen (bestaat niet): %s',
        "log_open_file_failed": 'Bestand openen mislukt voor %s',
        "log_orphan_input_failed": 'Kon wees-invoermap niet verwijderen: %s',
        "log_orphans_cleaned": 'Wees-projecten opgeruimd (geen outputmap meer): %s',
        "log_outlier_region": 'Uitschieter-uitlijnregio %.1f-%.1f s (offset %+.0f ms) wijkt af van lokale trend %+.0f ms; vervangen door de trend',
        "log_parallel_detection": 'Parallelle detectie: %s tegelijk',
        "log_parallel_out_of_memory": 'Parallelle detectie kreeg te weinig geheugen; terugval op sequentieel',
        "log_paths_updated": 'Projectpaden bijgewerkt: %d verwijzingen (%s -> %s)',
        "log_phonetic_segmentation_skipped": 'Fonetische segmentatie overgeslagen voor regel',
        "log_phonetic_timing_skipped": 'Fonetische timing overgeslagen (afgevangen)',
        "log_pins_migrated": '%d handmatige koppeling(en) omgezet naar de transcriptie inclusief gefilterde woorden',
        "log_pins_relocated": '%d van %d handmatige koppeling(en) verplaatst: de woordenlijst van de songtekst is van vorm veranderd',
        "log_pins_saved": 'Woordkoppelingen opgeslagen: %d pin(s)',
        "log_preload_failed": 'Kon audio niet vooraf laden voor forced alignment; WhisperX laadt zelf (kan een venster geven)',
        "log_project_damaged": 'Beschadigde project.json (%s); start leeg',
        "log_project_deleted": 'Project verwijderd: %s (invoer, uitvoer en cache)',
        "log_project_saved": 'project.json opgeslagen (%s)',
        "log_project_switch": 'Projectwissel: %s',
        "log_prompt_failed": 'Songtekst-prompt opbouwen mislukt (overgeslagen)',
        "log_properties": 'Eigenschappen %s: %s',
        "log_region_offset": 'Regio %.1f-%.1f s: offset %+.0f ms (confidence %.2f)',
        "log_render_done": 'Render klaar: %s',
        "log_render_command": 'ffmpeg-commando: %s',
        "log_collect_failed": 'Kon %s van %s niet kopiëren',
        "log_collect_renamed": '%s bestond al in de doelmap; gekopieerd als %s',
        "log_collected": '%d project(en) verzameld, %d bestand(en) naar %s',
        "log_lead_silence_ok": 'Stilte voor de zang gecontroleerd: %.2f s',
        "log_lead_silence_unknown": 'Kon de stilte vooraan niet meten in %s; render niet gecontroleerd',
        "log_silence_measure_failed": 'Kon de stilte niet meten in %s',
        "err_lead_silence": "De video liep uit de pas: er hoort {expected} s stilte voor de zang te staan en er staat {measured} s. Beeld en geluid zouden dan het hele nummer lang verschoven zijn, dus de video is niet weggeschreven.",
        "log_frames_reused": "Beelden hergebruikt: %d van %d (%d%%) waren gelijk aan het vorige beeld.",
        "log_render_started": 'Render gestart: %s (%dx%d, %d fps, %.1f s)',
        "log_resampled": 'Geresampled: %s -> %s (%d Hz, %d kanaal/kanalen)',
        "log_residual_on_stem": 'Restzang-detectie op de gescheiden zangstem',
        "log_restore_applied": 'Terug-uit-origineel toegepast: %d fragmenten, %.1f s',
        "log_restore_empty": "Terug-uit-origineel: leeg origineel-fragment voor '%s'; overgeslagen",
        "log_restore_no_original": 'Terug-uit-origineel: geen origineel gevonden; %d fragment(en) overgeslagen',
        "log_restore_rate_mismatch": "Terug-uit-origineel: sample rate origineel (%d Hz) wijkt af van karaoke (%d Hz); fragment '%s' overgeslagen",
        "log_restore_saved": 'Terug-uit-origineel-fragmenten bewaard: %d',
        "log_restore_too_short": "Terug-uit-origineel: origineel-fragment korter dan gemarkeerd venster voor '%s' (%.2fs tekort)",
        "log_restore_unusable": 'Terug-uit-origineel: origineel niet bruikbaar (%s); alle fragmenten overgeslagen',
        "log_rewrite_failed": 'Kon verwijzingen niet herschrijven: %s',
        "log_rms_failed": 'RMS-omhullende bepalen mislukt',
        "log_segments_cached": 'Segmenten gecachet: %s',
        "log_sentence_coupling": 'Zin-koppeling: %s (%s)',
        "log_separation_failed_karaoke": 'Zangscheiding mislukt; hele karaoke gebruikt',
        "log_separation_failed_original": 'Zangscheiding origineel mislukt; mix gebruikt',
        "log_startup_size": "Venster bij het starten van %dx%d naar %dx%d gebracht (%s maat was te klein voor de inhoud)",
        "log_startup_size": "Venster bij het starten van %dx%d naar %dx%d "
                            "gebracht (%s maat was te klein voor de inhoud)",
        "log_after_song_end": "%d koppeling(en) losgemaakt die na het einde van "
                              "de zang lagen (%.1f s)",
        "log_tail_from_the_back": "Staart van %d woord(en) van achteren naar voren "
                                  "gepast: %.1f s zang beschikbaar, %.1f s nodig",
        "log_several_variants": "Meerdere varianten van '%s' gevonden; %s wordt gebruikt",
        "log_skipped_placed": '%d overgeslagen songtekstwoord(en) op de zangstem geplaatst',
        "log_source_changed": 'Bron gewijzigd buiten de stappen om: %s',
        "log_step_removed": "Stap '%s' verwijderd uit project.json",
        "log_step_updated": "Stap '%s' bijgewerkt in project.json",
        "log_stress_paint_error": 'Fout in klemtoon-editor paintEvent (afgevangen)',
        "log_stress_save_failed": 'Klemtoon opslaan mislukt',
        "log_task_cancelled": 'Achtergrondtaak afgebroken door de gebruiker',
        "log_task_error": 'Fout in achtergrondtaak',
        "log_timing_auto_failed": 'Kon timing_auto.json niet schrijven',
        "log_timing_diagnostics_failed": 'Kon timing-diagnostiek niet schrijven',
        "log_timing_paint_error": 'Fout in timing-editor paintEvent (afgevangen)',
        "log_timing_project_mismatch": "timing.json hoort bij project '%s', maar het huidige project is '%s' (%s). Mogelijke kruisbesmetting.",
        "log_timing_reanchored": 'Timing her-verankerd: opgeslagen offset %+.0f ms, nu %+.0f ms -> verschuiving %+.0f ms',
        "log_timing_sync_failed": 'timing.json bijwerken na tekstwijziging mislukt',
        "log_timing_synced": 'timing.json bijgewerkt na karaoketekst-wijziging: %d regel(s) aangepast',
        "log_timing_written": "Timing geschreven: %s (%d regels, offset %s, project '%s')",
        "log_timing_flat_repaired": "Platgeslagen regels hersteld bij openen: %d",
        "log_chunk_words_failed": "De geknipte woorden konden niet worden weggeschreven",
        "log_timing_rescued": "Handmatige timing behouden over de tekstwijziging heen: %d regels, %d met nieuwe tekst",
        "log_timing_kept": "Handmatige timing behouden; gewijzigd was: %s. Klopt de timing niet meer, maak hem opnieuw met 2.2.",
        "log_timing_rescue_failed": "Handmatige timing kon niet worden behouden; het bestand is opnieuw te maken met 2.2",
        "log_transcript_override_cleared": 'Transcript-override gewist',
        "log_transcript_override_saved": 'Transcript-override opgeslagen: %d woord(en)',
        "log_transcription_done": 'Transcriptie klaar: %d segmenten, %d woorden in %.1f s',
        "log_transcription_started": 'Transcriptie gestart: %s',
        "log_unexpected_structure": 'Onverwachte structuur in %s; start leeg',
        "log_unknown_keys": 'Onbekende sleutels genegeerd in %s: %s',
        "log_vbr_failed": 'VBR-detectie mislukt voor %s',
        "log_video_rendered": 'Video gerenderd met audio %s',
        "log_vocal_refine_skipped": 'Zangstem-verfijning overgeslagen (afgevangen)',
        "log_vocal_waveform_missing": 'Zangstem-golfvorm niet beschikbaar',
        "log_vocals_copy_failed": 'Kon zangstem niet naar cache kopiëren',
        "log_vocals_failed": 'Zangstem van origineel maken mislukt',
        "log_vocals_ready": 'Zangstem van origineel klaargezet: %s',
        "log_wav_saved": 'Wav opgeslagen: %s',
        "log_whisper_model_load": 'Whisper-model %s laden (device=%s, compute=%s)',
        "log_whisper_model_lanes": "Whisper mag %d draai(en) tegelijk doen, %d threads elk",
        "log_whisper_model_reused": 'Whisper-model %s hergebruikt (device=%s, compute=%s)',
        "log_whisper_output": 'Whisper-uitvoer geschreven naar %s',
        "log_written_words": 'Geschreven: %s (%d woorden)',
    },
    "en": {
        "app_title": "Karaoke Tool",
        "tab_audio": "Load music & analyse",
        "tab_video": "Karaoke video",
        "tab_settings": "Settings",
        "tab_help": "Manual",
        "help_missing": "Manual not found (docs/manual.md).",
        "video_colors_group": "Video text colours and font",
        "theme_group": "Interface colours",
        "reset": "Reset to defaults",
        "song_group": "Song project",
        "song_label": "Song title:",
        "new_project": "New project...",
        "new_project_title": "New project",
        "new_project_prompt": "Song title for the new project:",
        "inputs_group": "Input files",
        "choose_file": "Choose file...",
        "choose_folder": "Choose folder...",
        "output_dir_group": "Output folder",
        "output_dir_hint": "Where the project folders (output/settings) are "
                           "stored. Pick another folder or network location "
                           "(UNC). On applying, existing projects are moved "
                           "there and references updated; input and cache stay "
                           "with the app.",
        "lyrics": "Original lyrics",
        "karaoke_text": "Karaoke text",
        "logo": "Logo",
        "model_label": "Model:",
        "model_accurate": "Accurate (large-v3)",
        "model_medium": "Medium (distil-large-v3)",
        "model_fast": "Fast (small)",
        "advanced_group": "Large models (optional, fall back if unavailable)",
        "cache_clear": "Clear cache on start and exit",
        "cache_clear_now": "Clear now",
        "cache_clear_now_tip": "Clear the cache once (all projects). Expensive "
                              "results like the vocal stem and transcription "
                              "are rebuilt on the next run.",
        "cache_cleared_now_log": "Cache cleared.",
        "timing_fallback_title": "No coupling used",
        "timing_fallback_body": "The timing was spread evenly because the "
                               "transcription/coupling was missing (e.g. the "
                               "cache was cleared). Run '{step_detect}' "
                               "again, or turn off 'clear cache', for "
                               "accurate timing.",
        "steps_group": "Steps",
        "step_detect": "1.1. Detect words",
        "step_analyse": "1.3. Analyse",
        "step_karaoke": "1.4. Adjust karaoke",
        "ready": "Ready.",
        "waveform_group": "Waveform of adjusted karaoke (red = damped)",
        "damping_editor_button": "Edit damping (waveform editor)",
        "fragments_group": "Damped fragments (uncheck = do not damp; "
                           "changes are applied and re-exported "
                           "immediately)",
        "clusters_group": "Sound clusters (tick what should be damped)",
        "clusters_hint": "Nothing selected by default. Ticking is saved "
                         "immediately.",
        "open_report": "Open HTML report",
        "log_group": "Messages",
        "language_label": "Language:",
        "video_edit_stress": "2.1. Edit stress",
        "video_timing": "2.2. Refine timing",
        "video_edit_timing": "2.3. Edit timing (waveform)",
        "stress_title": "Edit stress",
        "stress_hint": "Pick a sentence. The original is on top, the "
                       "karaoke below, both on the same time bar. Click a "
                       "piece of the original and then the karaoke piece "
                       "that belongs to it: that piece takes over the time "
                       "of the original and the rest of the sentence gives "
                       "way in proportion. Click a coupled karaoke piece to "
                       "release it. Orange = the original holds that piece "
                       "long.",
        "stress_group_karaoke": "Karaoke",
        "stress_group_original": "Original (measured on the recording)",
        "stress_saved": "Stress saved.",
        "video_render": "2.4. Make video",
        "video_prep_group": "Preparation",
        "video_collect": "Collect and copy",
        "collect_none": "No video has been made yet, so there is nothing to collect.",
        "collect_what": "{count} project(s) have a video. What goes along?",
        "collect_only_video": "The videos only",
        "collect_with_sources": "Collection: video, original recording, lyrics and karaoke text (a folder per project)",
        "collect_where": "Where should the collection go?",
        "err_collect_inside": "Pick a folder outside the projects' output folder; otherwise the collection is copied into the projects themselves.",
        "collect_busy": "Collecting: {song} ({done}/{total})",
        "collect_done": "Collected: {projects} project(s), {files} file(s) to {folder}",
        "log_collect_failed": 'Could not copy %s of %s',
        "log_collect_renamed": '%s already existed in the destination; copied as %s',
        "log_collected": 'Collected %d project(s), %d file(s) to %s',
        "open_video": "Open video",
        "damping_reset": "Reset to original karaoke",
        "make_karaoke": "Make karaoke from original (Demucs)",
        "make_karaoke_tip": "Creates an instrumental from the original when "
                            "there is no karaoke file; alignment is then not "
                            "needed (offset 0).",
        "demucs_missing": "Demucs is not available. Install the large models "
                          "via install.bat.",
        "making_karaoke": "Creating instrumental from the original (Demucs; "
                          "this can take a while)...",
        "karaoke_made": "Instrumental (karaoke) created from the original.",
        "karaoke_from_original_label": "From the original",
        "editor_timing_title": "Edit timing",
        "editor_damping_title": "Edit damping",
        "zoom_in": "Zoom +",
        "zoom_out": "Zoom -",
        "source_label": "Source:",
        "view_label": "View:",
        "lane_original": "Original",
        "lane_original_text": "Original lyrics",
        "lane_karaoke": "Karaoke",
        "lane_vocals": "Vocal stem",
        "lane_karaoke_lines": "Karaoke lines",
        "render_opts_title": "What do you want in the video?",
        "render_opts_text": "Text",
        "render_opts_audio": "Music",
        "render_text_karaoke": "Timed karaoke text",
        "render_text_original": "Timed original text",
        "render_audio_karaoke": "Karaoke music",
        "render_audio_original": "Original music",
        "render_audio_vocals": "Vocals only",
        "view_sentences": "Sentences",
        "view_blocks": "Blocks",
        "view_words": "Words",
        "line_toggle": "Line off/on",
        "line_toggle_tip": "Select a block/sentence/word and turn it off "
                           "(not in the render) or back on.",
        "play": "Play",
        "pause": "Pause",
        "reset_original": "Reset original timing",
        "save_timing": "Save (timing.json)",
        "close": "Close",
        "line_restore": "Fetch back from original",
        "line_restore_tip": "Mark the chosen sentence: at 1.4 the sound from the original is fetched back at that time. The mark shows in both lanes and travels along when you move the sentence.",
        "timing_saved_restore": " {count} sentence(s) from the original.",
        "add_damping": "Add damping",
        "add_restore": "Restore from original",
        "remove": "Remove",
        "save_apply": "Save and apply",
        "editor_damping_hint": "Click in the waveform = playhead there "
                               "(paused). Drag a block or edge; edge cursor "
                               "= <->. Red = damping, green = restore from "
                               "original.",
        "lang_uncertain_title": "Language uncertain",
        "lang_uncertain_prompt": "The language of the lyrics is uncertain. "
                                 "Choose the language (for Whisper and forced "
                                 "alignment):",
        "lang_second_title": "Second language in the text",
        "lang_second_prompt": "The text has a passage in another script "
                              "({code}, {count} words). Which language "
                              "should Whisper listen in?",
        "lang_second_first": "{code} (detected on the rest of the text)",
        "lang_second_other": "{code} (the other script)",
        "lang_auto": "Automatic (Whisper decides)",
        "lang_other": "Other... (more options)",
        "video_done_title": "Video ready",
        "activity_group": "Activity",
        "stop": "Stop",
        "cancel_hard": "Still busy; running programs are being killed.",
        "cancelling": "Cancelling...",
        "cancelled_done": "Cancelled; leftovers cleaned up.",
        "delete_project": "Delete project...",
        "delete_project_title": "Delete project",
        "delete_project_confirm": "Are you sure you want to delete the "
                                  "project '{title}'? Its input, output and "
                                  "cache will be permanently removed.",
        # --- v0.51 i18n-sweep (B91) ---
        "original": "Original",
        "karaoke": "Karaoke",
        "on": "on",
        "off": "off",
        "no_title": "(no title)",
        "default_value": "default",
        "busy_title": "Busy",
        "busy_running_body": "A step is already running; please wait.",
        "busy_step_body": "A step is still running; wait for it to finish "
                          "first.",
        "busy_switch_title": "Please wait",
        "busy_switch_body": "A step is still running; switch project once it "
                            "finishes.",
        "busy_phase": "Busy",
        "phase_elapsed": "{phase}... {elapsed} s",
        "progress_pct": "Progress: {done:.0f} / {total:.0f} s",
        "detect_preparing": "Preparing input...",
        "detect_downloading": "Downloading Whisper model (one-off, this may "
                              "take a while)...",
        "detect_transcribing": "Transcribing...",
        "detect_transcribing_parallel": "Transcribing original and karaoke in "
                                        "parallel...",
        "detect_aligning": "Aligning original and karaoke...",
        "detect_from_cache": "[{track}] Transcription from cache "
                             "({segments} segments).",
        "detect_ready": "[{track}] Transcription done: {segments} segments, "
                        "{words} words.",
        "parallel_detect": "Transcribe original and karaoke at the same time "
                           "(parallel)",
        "parallel_detect_tip": "Faster on multiple cores but uses more "
                               "memory; falls back to one-by-one when memory "
                               "is tight.",
        "parallel_detect_log": "Parallel detection: {state} (saved).",
        "cache_clear_log": "Clear cache on start and exit: {state} (saved).",
        "whisper_model_log": "Whisper model: {code} (downloaded if needed on "
                             "the next transcription).",
        "lang_saved": "Language saved. Restart the app to apply the new "
                      "language everywhere.\n\nTaal opgeslagen. Herstart de "
                      "app om de nieuwe taal overal toe te passen.",
        "project_deleted_log": "Project '{title}' deleted (input, output and "
                               "cache).",
        "project_already_active": "Project '{title}' is already active.",
        "project_opened_log": "Project '{title}' {state}.{extra}",
        "project_state_opened": "opened",
        "project_state_new": "newly created",
        "project_moved_extra": " moved {count} loose file(s) into the project "
                               "folder.",
        "new_project_invalid_title": "No valid title given.",
        "project_exists_title": "Project already exists",
        "project_exists_body": "A project '{title}' already exists. Open it?",
        "font_preview_text": "The quick brown fox jumps over the lazy "
                             "dog 0123",
        "video_meta_group": "Titles and artist",
        "meta_karaoke_title": "Karaoke title:",
        "meta_orig_artist": "Original artist:",
        "meta_orig_title": "Original title:",
        "meta_background": "Background image:",
        "video_timing_group": "Karaoke text with timing (green = high "
                              "confidence, yellow = medium, red = best-effort)",
        "timing_making": "Creating timing skeleton...",
        "timing_made": "Timing created: {target} ({count} lines; {detail}).",
        "timing_detail_coupling": "sentence coupling: {high}x high, "
                                  "{medium}x medium, {low}x low",
        "timing_detail_even": "spread evenly (no lyrics alignment "
                              "available); refine with "
                              "'{video_edit_timing}'",
        "timing_unreadable": "timing.json is unreadable.",
        "no_timing_error": "No timing.json; run '{video_timing}' first.",
        "editor_loading": "Loading audio and timing for the editor...",
        "no_original_editor": "No original found; the editor shows only the "
                              "karaoke.",
        "timing_saved_log": "Timing saved: {path}",
        "timing_saved_corrections": "; kept {count} original correction(s)",
        "orig_timing_restored": "Original timing restored to the audio "
                                "alignment.",
        "alignment_failed_log": "Alignment failed: {error}",
        "no_result": "no result",
        "video_rendering": "Rendering video (this can take a few minutes; the "
                           "progress bar follows along)...",
        "background_none": "None",
        "background_remove": "Remove image",
        "background_use_stored": "Use this one",
        "background_delete_stored": "Delete stored background",
        "background_delete_stored_tip": "Removes the chosen background from "
                                        "the central store. Projects using "
                                        "it keep their own copy.",
        "background_delete_ask": "Delete {name} from the store?",
        "outline_label": "outline",
        "video_pick_title": "Which video?",
        "video_pick_body": "This project has more than one video "
                           "ready. Which one do you want to open?",
        "video_done_status": "Video ready.",
        "video_done_log": "Video ready: {target}",
        "video_done_prompt": "{title}:\n{target}\n\nOpen now?",
        "open_video_button": "Open video",
        "open_folder_button": "Open folder",
        "copy_failed": "Copy failed",
        "copied_to_log": "{name} copied to {target}. {note}",
        "copied_untouched_log": "{name} copied to {target} (the original "
                                "stays untouched).",
        "karaoke_text_note": "Mark crowd parts with [crowd] ... [/crowd] "
                             "(they turn red).",
        "choose_karaoke_text_title": "Choose the karaoke text (new lyrics)",
        "text_structure_title": "Text structure",
        "choose_file_for": "Choose the file for '{stem}'",
        "missing_choose": "missing - choose a file",
        "missing_choose_karaoke": "missing - choose a file or make from "
                                  "original",
        "missing_required": "missing (required)",
        "missing_video": "none (needed for the video)",
        "font_ttf": "Font (.ttf)",
        "font_default": "DejaVu Sans Bold (default)",
        "color_before": "Text before singing",
        "color_during": "While singing",
        "color_after": "After singing",
        "color_crowd": "Crowd while singing",
        "color_background": "Video background",
        "choose_font_title": "Choose font",
        "video_colors_reset_log": "Video colours and font reset to defaults.",
        "theme_background": "Background",
        "theme_buttons": "Buttons",
        "theme_button_active": "Button active (busy)",
        "gui_colors_reset_log": "GUI colours reset to defaults.",
        "model_demucs_desc": "Separate vocals (leftover vocals / make "
                             "karaoke)",
        "model_forced_alignment_desc": "More precise word timings (wav2vec2)",
        "model_demucs_info": "~250 MB (one-off) — slow on CPU (a few minutes "
                             "per song), fast on GPU",
        "model_forced_alignment_info": "~360 MB per language (one-off) — "
                                       "moderate; faster on GPU",
        "model_not_installed_suffix": "  — package not installed (see "
                                      "install.bat)",
        "model_toggle_log": "{model}: {state}.",
        "package_missing_title": "Package missing",
        "package_missing_body": "The package for '{model}' is not installed "
                                "yet. Run install.bat again and choose the "
                                "large models, or install it manually.",
        "model_downloading": "{model} - downloading/loading model",
        "model_ready_log": "{model}: model ready.",
        "damping_reapply": "Re-applying damping...",
        "reexporting": "Re-exporting...",
        "fragments_applied_log": "Fragments applied; new export: {export}",
        "damping_need_step_body": "Run step 1 (Detect words) first; then "
                                  "you can tweak the fragments on the "
                                  "waveform.",
        "karaoke_wave_loading": "Loading karaoke waveform...",
        "damping_applied_log": "Damping applied; export: {export}",
        "damping_reset_log": "Damping reset to the original karaoke.",
        "analysing": "Analysing and clustering...",
        "karaoke_adjusting": "Adjusting karaoke...",
        "exporting": "Exporting...",
        "computing_wave": "Computing waveform...",
        "karaoke_adjusted_log": "Karaoke adjusted: {count} fragments, "
                                "{seconds:.1f} s damped at {gain} dB. "
                                "Export: {export}",
        "analyse_done_log": "[{track}] Analysis done: {words} words, "
                            "{clusters} clusters. Report: {report}",
        "cluster_checkbox": "Cluster {id} - {label}   (found: {freq} times, "
                            "confidence {conf:.2f}){tip}",
        "cluster_suggestion_tag": "  (suggestion)",
        "variants_label": "Variants: {variants}",
        "suggestion_log": "[{track}] Suggestion based on search_words: "
                          "clusters {clusters} (marked; tick what you want to "
                          "damp yourself).",
        "selection_saved_log": "[{track}] Selection saved: {labels}.",
        "none_word": "none",
        "alignment_failed_title": "Alignment failed",
        "alignment_failed_body": "Original and karaoke could not be "
                                 "aligned:\n{error}\n\nTiming/damping may be "
                                 "off as a result.",
        "alignment_region_log": "  alignment {start:.1f}-{end:.1f} s: offset "
                                "{offset:+.0f} ms (confidence {conf:.2f})",
        "alignment_weak_title": "Alignment unreliable",
        "alignment_weak_body": "The alignment between original and karaoke is "
                               "weak (confidence {conf:.2f}). The songs "
                               "probably differ too much; the timing and "
                               "damping projection may be off.",
        "drift_title": "Drift detected",
        "drift_body": "The offset between original and karaoke drifts "
                      "{drift:.0f} ms across the song (drift: one runs "
                      "faster/slower).\n\nFollow it per region (recommended)? "
                      "No = a single fixed offset.",
        "drift_off_log": "Drift correction off: a single fixed offset used.",
        "drift_corrected_log": "Drift {drift:.0f} ms; corrected per region "
                               "({count} regions).",
        "lang_cancelled": "Language choice cancelled; detection not started.",
        "lang_chosen": "Language chosen: {code} (used for Whisper and forced "
                       "alignment).",
        "task_failed": "Something went wrong: {exc} (see the log file in the "
                       "'logs' folder)",
        "track_done": "{track}: done",
        "yes": "Yes",
        "no": "No",
        "choose_logo_title": "Choose the logo",
        "choose_lyrics_title": "Choose the official lyrics",
        "lyrics_note": "The original lyrics lead the analysis.",
        "derived_invalidated": "New input: earlier results (cache, alignment, "
                               "timing) removed; run the steps again.",
        "lyrics_duplicate_warn": "Note: original lyrics and karaoke text are "
                                 "(nearly) identical. Is that correct? Put the "
                                 "right original lyrics with the original.",
        "prereq_title": "Step missing",
        "prereq_need_detect": "Run '{step_detect}' first; its output is "
                              "missing or outdated.",
        "prereq_need_analyse": "Run '{step_analyse}' first; its output is "
                               "missing or outdated.",
        "diagnostics_option": "Diagnostics (local only)",
        "diagnostics_tip": "Writes transcription history and timing "
                           "diagnostics to output/<title>/diagnostiek/. Local "
                           "only; nothing is sent.",
        "diagnostics_log": "Diagnostics: {state} (saved).",
        "vocal_analyse_option": "Vocal analysis (held notes + filler lines)",
        "vocal_analyse_tip": "Uses the separated vocal stem to extend held "
                             "notes and place untranscribed 'na-na' lines on "
                             "their energy pulses. Requires Demucs; falls "
                             "back gracefully otherwise.",
        "vocal_analyse_log": "Vocal analysis: {state} (saved).",
        "step_couple": "1.2. Couple words",
        "couple_title": "Couple words",
        "couple_hint": "Couple the real lyric words (bottom) to the found "
                       "words (top) so the analysis uses the correct words. "
                       "Click a word on top and one on the bottom to couple; "
                       "click a line to remove it. Colour = confidence (blue "
                       "= manual).",
        "couple_legend": "Colours:",
        "legend_filler_skipped": "skipped filler word",
        "legend_mark_tip": "Select a word and click here to mark it as a hallucination (top row) or a filler word (bottom row) for this language.",
        "mark_select_first": "Select a word in the right row first: a found word for hallucination, a lyrics word for filler.",
        "mark_word_added": "'{word}' added to the list for language {language}.",
        "mark_word_removed": "'{word}' removed from the list for language {language} again.",
        "legend_no_match": "no match found",
        "legend_hallucination": "filtered out as a hallucination",
        "legend_transcription_gap": "Whisper heard nothing here",
        "legend_suspect_run": "run without any coupling - looks like a "
                              "hallucination; couple by hand if it is real "
                              "singing after all",
        "legend_energy_placed": "not coupled, but timed on the vocal stem",
        "legend_manually_uncoupled": "uncoupled by you - the automatic "
                                     "coupling leaves this word alone; "
                                     "\"Release\" lets it try again",
        "legend_background": "background vocals ([bg]) - shown in the "
                             "editors, never in the render",
        "legend_repeat_missing": "repetition the lyrics are missing - these "
                                 "words ARE in the text, but it writes the "
                                 "line once and the song sings it more often",
        "couple_release": "Release",
        "couple_release_tip": "Removes the manual decision on the selected lyrics word, so the automatic coupling may try again. Without it a word you once uncoupled stays uncoupled forever.",
        "couple_release_first": "Select a lyrics word first (bottom row).",
        "log_pins_relocated_by_text": "%d coupling(s) found back on the word itself, %d let go because the word is no longer there.",
        "stress_sentence": "Sentence:",
        "stress_no_room": "This sentence is full: there is {seconds:.2f} s too little room to give the uncoupled pieces their minimum. Release a coupling or give the original more room.",
        "legend_filtered_word": "found word that was filtered out "
                                "(struck through; coupling by hand is fine)",
        "couple_found": "Found (Whisper):",
        "couple_lyrics": "Lyrics:",
        "couple_save": "Save",
        "couple_cut": "Cut",
        "couple_cut_tip": "Select a found word (top) and cut it into two "
                          "words.",
        "couple_merge": "Merge",
        "couple_merge_tip": "Select a found word (top); it will be merged with "
                            "the word to its right.",
        "couple_no_data": "No transcription/lyrics to couple; run "
                          "'{step_detect}' first and provide the lyrics.",
        "couple_saved": "Word coupling saved: {count} manual link(s). Run "
                        "Analyse again.",
        # --- Pipeline error messages (B296) ---------------------------
        "err_no_project_delete": "No project loaded to delete.",
        "err_demucs_unavailable": "Demucs is not available; install the large "
                                  "models via install.bat.",
        "err_no_original_instrumental": "No original found to create an "
                                        "instrumental from.",
        "err_instrumental_failed": "Creating the instrumental failed: {error}",
        "err_no_input_found": "No {names} found in {dir}",
        "err_ffmpeg_missing": "ffmpeg/ffprobe not found; please install "
                              "ffmpeg (see README.md).",
        "err_no_transcription": "No transcription of '{track}' found; run "
                                "'{step_detect}' first.",
        "err_no_cluster_selection_track": "No cluster selection for "
                                          "'{track}'; run "
                                          "'{step_analyse}' first and pick "
                                          "clusters.",
        "err_cluster_file_missing": "Cluster file missing ({file}); run "
                                    "'{step_analyse}' again.",
        "err_selection_mismatch": "The selection for '{track}' does not match "
                                  "the clusters; run '{step_analyse}' "
                                  "again.",
        "err_no_prepared_audio": "No prepared audio found; run "
                                 "'{step_detect}' first.",
        "err_no_alignment": "No alignment found; run '{step_karaoke}' - it "
                            "creates the alignment itself when needed.",
        "err_no_cluster_selection": "No cluster selection found; run "
                                    "'{step_analyse}' first and pick "
                                    "clusters.",
        "err_no_fragments": "No fragments to damp found for this selection.",
        "err_no_edited_karaoke": "No edited karaoke found; run "
                                 "'{step_karaoke}' first.",
        "err_no_source_properties": "No source properties found; run "
                                    "'{step_detect}' first.",
        "err_no_text_files": "No karaoketekst.txt or songtekst.txt found; "
                             "pick the text first.",
        "err_no_sung_lines": "The text contains no sung lines.",
        "err_no_original_audio": "No original audio found.",
        "err_no_demucs_instrumental": "No Demucs instrumental yet "
                                      "(karaoke_demucs.mp3); run the analysis "
                                      "first.",
        "err_no_vocals": "No vocal track yet (vocal_demucs.mp3); run the "
                         "analysis first.",
        "err_no_karaoke_audio": "No karaoke audio found (edited or plain).",
        "err_no_original_timing": "No original-text timing available; couple "
                                  "or analyse the original first.",
        "err_video_input_incomplete": "Video input incomplete; missing: "
                                      "{missing}",
        # --- HTML cluster report (B296) -------------------------------
        "html_title": "KaraokeTool - sound clusters",
        "html_heading": "Sound clusters",
        "html_intro": "Tick the clusters that should be damped in the "
                      "karaoke and enter the selection at "
                      "'{step_analyse}'.",
        "html_found_times": "found: {count} times",
        "html_variants": "Variants",
        "html_avg_duration": "Avg. duration",
        "html_avg_pause": "Avg. pause",
        "html_times": "Timestamps",
        "html_segments": "Segments",
        "html_sample_text": "Sample text",
        "html_cluster": "Cluster {id}",
        "html_confidence": "Confidence",
        "html_footer_label": "Selection for '{step_analyse}':",
        "html_copy": "Copy",
        "html_nothing_selected": "(nothing ticked)",
        "html_lang": "en",
        "wave_unavailable": "({name} unavailable)",
        "vi_lyrics": "original lyrics",
        "vi_karaoke_text": "karaoke text",
        "vi_logo": "logo",
        "vi_timing": "timing per syllable",
        "vi_offset": "offset original/karaoke",
        # --- Text structure and timing sync (B326) --------------------
        "text_align_missing": "Lyrics and/or karaoke text not present yet.",
        "text_align_header_ok": "Lyrics and karaoke text match "
                                "({count} sections).",
        "text_align_header_diff": "Note: the structure differs (lyrics "
                                  "{lyrics} sections, karaoke {karaoke}).",
        "text_align_row": "Section {index}: lyrics {lyrics} / karaoke "
                          "{karaoke}  {mark}",
        "text_align_mark_ok": "OK",
        "text_align_mark_diff": "differs",
        "timing_sync_no_file": "No timing.json; nothing to update.",
        "timing_sync_structure_changed": "The structure of the karaoke text "
                                         "changed (different number of "
                                         "blocks/sentences); timing removed "
                                         "- run '{video_timing}' again.",
        "timing_sync_count_mismatch": "The number of lines in timing.json "
                                      "does not match the karaoke text; "
                                      "timing.json left unchanged.",
        "timing_sync_no_diff": "No text differences; timing.json unchanged.",
        "timing_sync_updated": "timing.json updated: {count} line(s) "
                               "changed.",
        # --- Video input details (B326) -------------------------------
        "vi_detail_lines_crowd": "{lines} lines, {crowd} crowd",
        "vi_detail_unreadable": "unreadable",
        "vi_detail_lyrics_fallback": "no karaoke text; the lyrics are used "
                                     "(video of the original)",
        "vi_detail_karaoke_text_missing": "{path} (mark crowd with "
                                          "[crowd]...[/crowd])",
        "vi_detail_timing_lines": "{lines} lines, {filled} with times",
        "vi_detail_no_timing": "run '{video_timing}' first",
        "vi_detail_offset_done": "'{step_detect}' has run",
        "vi_detail_offset_missing": "run '{step_detect}' (or "
                                    "'{step_karaoke}', which aligns by "
                                    "itself)",
        # --- File dialog filters (B296) -------------------------------
        "filter_text": "Text (*.txt)",
        "filter_images": "Images (*.png *.jpg *.jpeg *.bmp)",
        "filter_image": "Image (*.png *.jpg *.jpeg *.bmp)",
        "filter_font": "Font (*.ttf *.otf)",
        "filter_audio": "Audio ({patterns})",
        # --- Other visible texts (B296) -------------------------------
        "waveform_after_step4": "The waveform appears after "
                                "'{step_karaoke}'.",
        "lines_overflow_title": "Lines run off screen",
        "lines_overflow_body": "{count} line(s) do not fit the video frame "
                               "and will be broken at a comma when rendering "
                               "(two rows tight below each other). Consider "
                               "shortening them:\n  - {preview}",
    
        # -- Log window (B315). The logger fills the %-placeholders
        # POSITIONALLY, so they stand in the same order in both
        # languages; a test guards that.
        "log_align_model_failed": 'Loading the alignment model failed',
        "log_alignment_collapsed": 'Alignment reduced to one fixed offset (%+.0f ms)',
        "log_alignment_report": 'Alignment report written: %s',
        "log_alignment_skipped": 'Karaoke from the original: alignment skipped (offset 0)',
        "log_alignment_skipped_words": 'Alignment: %d word(s) skipped (filler word/bg), of which %d coupled after all through the anchor window',
        "log_all_excluded": 'All fragments are excluded; nothing is damped',
        "log_already_exists": 'Already exists in the target folder, skipped: %s',
        "log_analysis_done": 'Analysis done: %s',
        "log_anchors_released": '%d anchor(s) released that demanded impossibly fast singing',
        "log_appusermodelid_failed": 'AppUserModelID could not be set',
        "log_audio_loaded": 'Audio loaded: %s (%d samples, %d Hz, %d channels)',
        "log_background_unreadable": 'Background image unreadable: %s',
        "log_anchors_implausible": 'Anchors released that cannot be a sentence: %d (phrase period %.2f s)',
        "log_lines_snapped": 'Line starts put on the vocal onset: %d line(s) (%d onsets found)',
        "log_repetition_loop_dropped": 'Repetition loop removed from the transcription: %d word(s) without any duration',
        "log_boundary_merged": 'Word cut in two by a segment boundary joined up again: %d time(s)',
        "log_missing_failed": 'Check for missing repetitions failed',
        "log_cache_filled": 'Cache filled for %s: %d segments',
        "log_test_failed": 'Test action %s broke down',
        "log_processes_killed": '%d external process(es) killed after Stop',
        "log_test_project_failed": 'Test broke down on project %s',
        "video_exists_title": "Video already exists",
        "video_exists_body": "This project already has a video.\n\nOverwrite replaces the last one, \"{name}\".\nKeeping both makes the new one \"{next}\" and leaves everything alone.",
        "video_keep_both": "Keep both",
        "video_overwrite": "Overwrite",
        "video_cancel": "Cancel",
        "test_panel_title": "1.5. Test",
        "test_panel_intro": "Tick what should run and press Start. The ticks are always off when you open this window.",
        "test_scope_current": "This project only",
        "test_scope_all": "All projects",
        "test_start": "Start",
        "test_no_projects": "No projects found to measure.",
        "test_nothing_found": "Nothing found.",
        "test_weighted": "weighted error on {count} moved lines: {error:.2f} s",
        "test_unique_repeated": "everything together: unique {unique:.2f} s, repeated {repeated:.2f} s",
        "test_running": "{code} running: {name}",
        "test_done": "{code} done.",
        "test_failed": "{code} broke down (see the log file).",
        "test_project_failed": "{name}: broke down (see the log file)",
        "test_fill_cache": "Fill cache",
        "test_fill_cache_hint": "Puts the transcription cache file back where it was cleared. Writes only that file; coupling and timing stay. Takes a long time.",
        "test_status": "Reference set status",
        "test_status_hint": "Per project: is there a cache, is there hand-corrected timing, how many lines, and which version made the automatic timing.",
        "test_missing": "Missing repetitions",
        "test_missing_hint": "Looks in every project for what was clearly heard but is not in the lyrics.",
        "test_ruler": "Run the ruler",
        "test_ruler_hint": "The full measurement over every project with hand-corrected timing. This is the number followed across releases, with the previous versions beside it. Projects unchanged since the last run are skipped.",
        "test_split": "Unique against repeated",
        "test_split_hint": "Splits the error into lines whose text is unique and lines that are repeated. Repeated lines are far more wrong; this number follows that gap.",
        "test_leave_out": "Leave-one-out",
        "test_leave_out_hint": "Flips every model in turn (on becomes off, off becomes on) and measures what that does. The quick brother of the big trial: single models only, a few minutes.",
        "test_reports": "Project checks (texts, filters, structure)",
        "test_reports_hint": "Three cheap reports in one: lyrics against karaoke text, what the read filters remove, and the structure per song. Together under a minute.",
        "test_part_texts": "texts",
        "test_part_filters": "filters",
        "test_part_structure": "structure",
        "test_syllables": "Word and syllable checks",
        "test_syllables_hint": "Checks the word and syllable times without a hand-set truth: against the shape, against the audio, against each other and against repetitions of the same line.",
        "test_syllable_intro": "No error but indications: shape = order/overlap/gaps/too short/too fast within one sentence, between = empty sentences, sentences over each other and sentences in the wrong order, duration = sentences far from the same sentence elsewhere, repeat = how differently the same line is divided twice (lower is better).",
        "test_syllable_total": "Together: {shape} shape errors, {silence} words in a measured silence, {between} problems between two sentences, {duration} sentences with an implausible duration.",
        "test_select_all": "Check all",
        "test_select_none": "Uncheck all",
        "test_force_again": "Measure again",
        "test_force_again_hint": "Ignore kept results from this version and measure everything again.",
        "test_skipped_note": "{count} project(s) skipped: a measurement from this version on the same files was already there.",
        "test_history_head": "Next to the previous versions:",
        "test_history_note": "Compared with {count} earlier version(s); a dash means that version did not measure this project.",
        "test_without": "without",
        "test_with": "WITH ",
        "test_on": "on",
        "test_off": "OFF",
        "test_all_on": "as now",
        "test_model_state": "Models: {state}",
        "test_matrix_state": "State of the register at this measurement: {state}. A model that is OFF is measured the other way round - then it shows what SWITCHING IT ON would deliver.",
        "test_matrix_made_with": "Measured with version {version}. A report from v0.128.0 through v0.137.0 is INVALID: those versions measured the same state every round.",
        "test_matrix_symmetry": "For a model that is on this is what switching it off costs; for a model that is off what switching it on would deliver. A plus means in both cases: the current state is the better one.",
        "test_matrix_pairs_all": "All {count} pairs, without a threshold. In v0.115.0 only models with an effect of their own took part, and that very table showed why that is wrong: the anchor test and the energy placement off together gave 5.66 s where 3.66 was expected. A model that does nothing alone can be a safety net.",
        "log_model_disabled": "Model OFF: %s (%s) - %s",
        "log_model_enabled": "Model on again: %s",
        "log_model_unknown": "Unknown model in the settings ignored: %s",
        "log_template_retimed": "Line re-timed from a template: '%s' (%s), template duration %.2f s",
        "log_template_total": "Lines re-timed from a template: %d",
        "log_template_failed": "Template timing did not work",
        "heavy_language_used": "Language for every variant: {code}. Decided once from the complete lyrics and handed to every run and every piece, so a variant cannot differ because language detection found something else that run.",
        "heavy_language_auto": "not pinned (auto) - the measurements below may have been affected by language detection; pick the language by hand on tab 1",
        "heavy_chunk": "Chunking and merging",
        "heavy_chunk_intro": "Four ways of showing Whisper the same vocal stem, on {name}: as it is now, twice with a shifted start, and cut into {pieces} pieces on the silences with its own prompt per piece. There is {seconds} s of measured singing. What counts is the \"unheard\" column: seconds where there is singing but no word.",
        "heavy_chunk_advice": "The merge may only fill holes, never overrule: two runs share the same initial prompt, so their agreeing proves nothing. Only the vocal stem knows nothing of the lyrics, which is why it has the last word. If a variant wins clearly it is worth a setting; if nothing changes, we know the window edges are not the cause.",
        "heavy_chunk_words": "The words heard per variant are in {path}; put them beside songtekst.txt before counting 'more words' as a gain.",
        "heavy_chunk_tail": "Note: {seconds} s is still sung after the last line of the text. That is missing lyrics, not missed singing - those seconds do count in 'not heard' below.",
        "log_measure_failed": "Measuring a project failed; the rest carries on",
        "log_pool_unavailable": "Measuring over separate processes failed; back to one process",
        "log_merge_filled": "Words added from a second transcription where the first was silent: %d",
        "log_chunked_started": "Transcription in pieces: %d pieces, in one queue together with the whole run.",
        "log_second_language_run": "A second language found in the text (%s); the whole song is read in that language too, only to fill silences.",
        "log_second_language_filled": "Second language (%s): %d words filled in that the first language did not have.",
        "log_chunked_filled": "Pieces filled in %d words; unheard singing from %.1f s to %.1f s.",
        "log_chunked_skipped": "Nothing to cut on (no measured vocal windows); one ordinary run.",
        "log_chunk_failed": "Piece %.1f-%.1f s failed; the rest of the run carries on.",
        "log_loudness_failed": "Could not measure the loudness; the video keeps the level of the source.",
        "log_loudness_silent": "No usable loudness (silence or near silence); the level of the source stays as it is.",
        "log_auto_rebuilt": "Automatic timing rebuilt: %s (%d lines); the hand-made timing was not touched.",
        "log_auto_rebuild_failed": "Could not rebuild the automatic timing.",
        "log_auto_rebuild_mismatch": "Automatic timing of %s not rebuilt: the hand-made timing has %d lines and the karaoke text yields %d. The handwork is older than the text; adjust the text or make the timing again.",
        "log_fps_lifted": "Frame rate raised from %d to %d; set it back in config.json if you want the old one.",
        "log_outline_reset": "Outline colour set back to automatic (%s); the standard colours decide it now.",
        "log_anchors_capped": "%d anchor(s) rejected on duration alone; their measured start stays and only the duration is capped.",
        "log_runaway_filtered": "Runaway repetition left out (%.1f-%.1f s): one word of %.1f s and %d characters. There WAS singing there, but this segment does not say where.",
        "ab_only": "Covered by **{name}** and not by {other}: {seconds} s in {count} stretch(es).",
        "ab_more": "... and {count} shorter stretches.",
        "heavy_two_languages": "Two-language search",
        "heavy_two_languages_nowhere": "No project has a passage in another script, so there is no second language to try here.",
        "heavy_two_languages_intro": "Over {count} project(s) with a passage in another script. Three ways of reading (the whole song in the biggest language, the whole song in the second language, and the biggest language cut on the silences) plus the merge the program now makes, all laid in one table beside your own timing of the same recording.",
        "heavy_two_languages_filled": "The second language ({name}) fills in {count} word(s) where the first language heard nothing. That is exactly what the program does now.",
        "heavy_two_languages_pair": "Biggest language: {first}. Second language by its characters: {second} ({count} words).",
        "heavy_two_languages_runaway": "{count} runaway repetition(s) left out of run {name} before counting - such a loop covers the very hole it sits in and would make that spot look healthy.",
        "search_intro": "{count} ways of reading the same {seconds} s of singing, side by side. \"Distance to line start\" is the median distance from your own line starts to the nearest word start - lower is closer to your hand work, and the table is sorted on it.",
        "search_best": "Closest to the hand work: {name} ({distance:.2f} s from a line start, {share:.0f}% on a real sentence).",
        "search_no_reference": "No hand-made timing of the same recording found; the table is then sorted on covered singing and says less.",
        "search_took": "This search took {seconds:.0f} s.",
        "search_whole": "whole song",
        "search_col_run": "run",
        "search_col_words": "words",
        "search_col_in_text": "in text",
        "search_col_covered": "covered",
        "search_col_unheard": "not heard",
        "search_col_on_line": "on a real line",
        "search_col_distance": "distance to line start",
        "search_col_spot": "spot",
        "search_chunked": "chunked",
        "search_fill_silence": "first language + second language in the silence only",
        "heavy_two_languages_reference": "Reference for \"on a real line\": the hand-made timing of {name}, which uses the same recording ({count} lines). \"In text\" cannot reward a correct Korean word when the lyrics write it phonetically in Latin letters; this figure knows nothing of spelling.",
        "heavy_two_languages_note": "The most careful merge may only fill holes: the first run stays the truth and the second language can never overrule a word that was properly heard. The bolder ones let the second language speak inside the weak spots as well. If \"in text\" drops while \"covered\" rises, the hole was filled with inventions and nothing was gained - which is why those two columns stand side by side.",
        "log_config_write_failed": "Could not write the settings back to %s.",
        "log_loudness_measured": "Karaoke loudness: %.1f LUFS, peak %.1f dBTP; target %.1f LUFS, reachable on a straight gain up to %.1f LUFS.",
        "log_loudness_limited": "Note: this track does not reach %.1f LUFS on a straight gain; %.1f dB is being compressed.",
        "log_versions_changed": "Package versions changed since the previous start: %s",
        "log_version_lookup_failed": "Could not read the version number of a package",
        "log_version_history_failed": "Could not read or write the version history",
        "log_updates_available": "Updates available according to the previous check: %s",
        "log_project_not_saved": "No song chosen, so nothing written to %s",
        "log_stray_project_store": "Loose project record without a song found: %s. It belongs to no project and may be removed.",
        "template_no_duration": "no duration",
        "template_too_fast": "too fast to be sung",
        "template_longer": "%.1fx longer than elsewhere",
        "template_shorter": "%.1fx shorter than elsewhere",
        "heavy_probe_nowhere": "No project has a gap of any significance: everywhere there is singing, Whisper produced text. There is nothing to investigate here.",
        "heavy_no_measurable": "No project has hand-corrected timing, so there is nothing to measure. Set the scope to \"All projects\", or hand-correct the timing of a project first.",
        "log_unsung_dropped": "Segment without measured singing dropped: %.1f s ('%s')",
        "log_unsung_total": "Segments without measured singing dropped: %d",
        "test_rebuild": "Make every video again",
        "test_rebuild_hint": "Renders every project that has a timing again, with the standard background on every video. Per project: render and let it be checked first, and only then move the old videos (all sequence numbers) to the _to_delete folder. If a render fails, everything there stays. Does not join 'tick all'.",
        "rebuild_intro": "{count} project(s), background {background} on every video. The old videos only go once the new one has been made and approved.",
        "rebuild_no_timing": "no timing, nothing to render",
        "rebuild_background_missing": "standard background not found; the old background stays",
        "rebuild_background_failed": "background not placed",
        "rebuild_kept_name": "the old video could not be moved; the new one keeps its sequence number",
        "rebuild_total": "{made} video(s) made again, {replaced} old ones moved to {folder}.",
        "test_heavy": "Heavy trials (overnight)",
        "test_heavy_hint": "Combination studies that take hours: all combinations within a cluster, and a search for the best state with a check on held-out songs. NEVER takes part in 'Check all'. Each study skips itself until it is twenty versions ago.",
        "heavy_intro": "Heavy combination studies. Exhausting all models is 2^17 = 131,072 measurements, over four hundred hours; below is what is affordable and yields the same knowledge.",
        "inventory_intro": "# Inventory\n\nThree countings over all projects, without Whisper and without models. Meant to turn a hunch into a number before anything is built.",
        "inventory_uncoupled": "Words that never couple",
        "inventory_uncoupled_head": "{never} of {total} lyric words ({percent:.1f}%) got no coupling. If there is a pattern here - a kind of word that cannot match in principle - that is the next 45.",
        "inventory_held": "Long held syllables",
        "inventory_held_head": "{count} of {total} syllables ({percent:.1f}%) are held long.",
        "inventory_held_note": "The video renderer can already show this (the `held` field), but nothing ever sets it; across all projects it is nowhere true.",
        "inventory_blocks": "Blocks that return",
        "inventory_blocks_head": "{count} block text(s) occur more than once. A large spread means the same block lasts much longer one time than another - that is drift at block level.",
        "inventory_no_material": "No material found for this counting.",
        "sanity_all_clear": "Logic check: not one model left a broken line behind (syllables without a moment of their own, stacked syllables, reversed or overlapping times).",
        "sanity_found": "Logic check: {count} measurement(s) left a broken line behind. This is separate from the weighted error, which only looks at line starts.",
        "heavy_clusters": "All combinations within a cluster",
        "heavy_search": "Search for the best state",
        "heavy_cluster_intro": "Models that demonstrably affect each other form a cluster; within such a cluster ALL combinations are measured. Models that affect no one do not need this - for those the single-model table of 1.5.10 is the whole answer.",
        "heavy_cluster_too_big": "Cluster with {count} models skipped: that is 2^{count} measurements and the limit is {max}. Concerns: {names}.",
        "heavy_needs_matrix": "No model matrix found. Run 1.5.10 first; the clusters come from that pair table, and guessing at them would make this whole trial worthless.",
        "heavy_no_clusters": "Not a single pair shows an interaction. Then the single figures from 1.5.10 are the complete answer and there is nothing to exhaust here.",
        "heavy_flat_matrix": "The model matrix reads nought: every pair gives exactly +0.00. That is not an outcome but a broken measurement - versions v0.128.0 through v0.137.0 measured the same state every round. Run 1.5.10 again before this trial can say anything.",
        "heavy_search_intro": "Not an inventory but a choice: from the current state keep taking the flip that gains the most, until nothing helps any more. Restarting a few times covers the risk that the climb ended on a lower hill.",
        "heavy_search_split": "Searched on {search} songs with hand-made timing; {held} songs are HELD OUT and count only for the check: {names}. Songs without hand-made timing take no part - there is nothing to measure there.",
        "heavy_search_verdict": "Best combination found: {names}. Difference on the search set {gain:+.2f} s, on the held-out songs {held:+.2f} s (negative is better, as in the table above).",
        "heavy_search_overfit": "**Note**: the gain on the held-out songs is less than half of that on the search set. That is the pattern of overfitting - something was found that fits these songs and not the next one.",
        "heavy_too_few_songs": "Too few projects ({count}) to hold any back; without a check set a found combination says nothing.",
        "heavy_already": "Already measured on version {version}, and nothing has changed since in the projects or the model state. Tick 'Measure again' to do it anyway.",
        "heavy_not_chosen": "Not ticked for this run.",
        "fill_cache_auto": "Automatic timing rebuilt for {count} project(s): {names}; the hand-made timing was not touched.",
        "test_skipped_projects": "Left out of the measurement (hand-made timing, but no timing_auto.json to compare against): {names}. Run 1.4 again for those projects, or have the automatic file rebuilt.",
        "test_letter_off": "(off)",
        "heavy_switched_off": "Switched off: {reason} Switching it on again is one line in modules/test_panel.py.",
        "heavy_off_chunk_answered": "the question has been answered - the cutting has been in production since v0.138.0.",
        "heavy_off_gain_answered": "the question has been answered - the loudest level wins on the total but yields inventions on one song (62% in the text), and the assumption is refuted: the quietest stem hardly changes.",
        "heavy_gain": "Level of the vocal stem",
        "heavy_gain_intro": "Does a louder vocal stem help Whisper? Across all projects the stems run from -10.5 to -26.9 LUFS, sixteen decibels, so if level matters at all it should show here. Measured on {count} songs with the biggest gaps. Less 'unheard' is better; if 'in text' drops, the extra words are inventions.",
        "heavy_gain_level": "Vocal stem as it stands: {lufs:.1f} LUFS, peak {peak:.1f} dBTP.",
        "heavy_gain_note": "If one level wins clearly, that is worth a setting and this trial can go off. If it makes no difference, we know that and it can go off too.",
        "heavy_done": "Heavy trials done: {count} lines written to {path}.",
        "log_test_result": "Test action %s done in %.1f s",
        "log_test_busy_machine": "Note: %s took %.0f s wall clock against %.0f s compute - other work was running on this machine, so that time cannot be compared with an earlier run",
        "log_history_delete_failed": "Could not delete the measurement history: %s",
        "log_syllable_checks_failed": "Word and syllable checks did not work",
        "test_matrix": "Big trial (model matrix)",
        "test_matrix_hint": "Measures every model at block, sentence, coupling and word level: on its own, in ALL pairs, in reverse order and per project. Writes docs/modelmatrix.md, halfway through as well. Expect half an hour; cancelling costs you only the last variant.",
        "test_matrix_intro": "What every model contributes to the timing, measured with the ruler over all projects with hand-corrected timing. Lower error is better. \"Difference\" is what happens when the model is OFF: a plus means the model is worth something.",
        "test_matrix_where": "Per model the project where turning it off costs the most (that is where the model comes into its own) and where it does damage instead. A model that scores about zero everywhere but strongly improves one project is switched on in the wrong place.",
        "test_matrix_pairs": "Two models off at the same time. If \"together\" is far from \"added up separately\", they work on the same lines and the combination deserves attention.",
        "test_order_skipped": "skipped, model is off",
        "test_matrix_order": "The same models, different order. Zero difference means the order does not matter and the code is free at that point.",
        "test_matrix_coupling": "The word coupling counts no error but coverage: how many lyrics words keep a coupling and what is left behind. \"Weak\" counts couplings below similarity 0.75 - the median sat at 1.00 everywhere before and was therefore blind to the very question that column was meant for. More coverage at the same share of weak is a gain; more coverage with more weak is a model that guesses.",
        "test_matrix_words": "At word and syllable level there is no hand-corrected truth, so no error. These are self-checks, and the sharpest is \"boundary crossing\": the forced alignment measures a start and end per word on the vocal stem, independent of the syllable model, and a syllable lying across it is demonstrably wrong.",
        "test_matrix_done": "Big trial done: {count} lines written to {path}.",
        "step_fill_cache": "1.5. Test",
        "fill_cache_none": "Every project still has its transcription cache.",
        "fill_cache_done": "Cache filled for {count} project(s).",
        "missing_repeat_log": 'Heard more repetitions than the lyrics have: {start:.1f} s, at line {line} ("{text}")',
        "missing_unknown_log": 'Clearly heard but not in the lyrics: {start:.1f} s, at line {line} ("{text}")',
        "missing_repeat_summary": 'Note: in {count} place(s) the original sings more repetitions than the lyrics have ({spots}{more}).',
        "missing_unknown_summary": 'On top of that {count} clearly heard word(s) that are not in the lyrics - see the log.',
        "missing_spot": '{start:.1f} s at line {line}',
        "missing_more": ' and {count} more',
        "log_phantom_words_dropped": 'Phantom words removed from the transcription (no duration, no confidence): %d',
        "log_tail_on_windows": 'Tail placed on the sung windows: %d line(s)',
        "log_artifact_in_position": 'Whisper artefact left out: %r (%.2f-%.2f s, language %s); those words are not in the lyrics here',
        "log_language_word_added": 'Word %r added to list %s of language %s',
        "log_language_word_removed": 'Word %r removed from list %s of language %s',
        "log_beat_analysis_failed": 'librosa beat analysis failed',
        "log_beat_times_failed": 'Determining the librosa beat times failed',
        "log_best_effort_timing": 'Best-effort timing: %s',
        "log_cache_cleaned": 'Cache cleaned: %d item(s) removed recursively',
        "log_cache_current": "Cache up to date for '%s'; conversion skipped",
        "log_cache_item_failed": 'Could not delete cache item: %s',
        "log_cache_not_empty": 'Cache not completely empty; %d item(s) left: %s',
        "log_cleaned_after_cancel": 'Cleaned up after cancelling: cache emptied and transcription/alignment reset',
        "log_cleanup_failed": 'Cleaning up after cancelling failed',
        "log_cluster_selection_saved": 'Cluster selection (%s) saved: %s',
        "log_cluster_written": 'Cluster output written: %s and %s (%d clusters)',
        "log_command": 'Command: %s',
        "log_config_loaded": 'Configuration loaded from %s',
        "log_config_saved": 'Configuration saved to %s',
        "log_converted_wav": 'Converted to wav: %s -> %s',
        "log_could_not_remove": 'Could not remove %s',
        "log_could_not_write_ffmpeg": 'Could not write %s (ffmpeg)',
        "log_couple_paint_error": 'Error in the coupling editor paintEvent (caught)',
        "log_couple_save_failed": 'Saving the word coupling failed',
        "log_damping_applied": 'Damping applied: %d fragments, %.1f s, %s dB',
        "log_damping_fragments": 'Damping fragments: %d (from %d occurrences)',
        "log_damping_reset": 'Damping reset to the original karaoke',
        "log_delete_failed": 'Could not delete (in use?): %s',
        "err_no_project_for_background": "Choose a project first; a "
                                        "background belongs to a song.",
        "log_timing_corrected": 'Final check: %s lines pulled into line '
                                '(overlap or zero length).',
        "log_orphans_all": 'All %s input folders would be orphans against '
                           'output folder %s; nothing cleaned up.',
        "log_inline_mark_skipped": 'Line %s has a different number of words '
                                   'in the text than in the timing; '
                                   'crowd/background not marked.',
        "log_orphans_skipped": 'No projects in output folder %s; orphans '
                               'not cleaned up (that would wipe all input).',
        "err_video_in_use": "The video was made but could not be moved into "
                            "place - is {target} still open in a player? The "
                            "new video is waiting as {scratch}.",
        "background_delete_failed": "Delete failed; the file may be in "
                                    "use.",
        "log_original_times_guessed": 'No reliable time in the original text; '
                                      '%s lines spread evenly so they can be '
                                      'placed in the editor.',
        "log_demucs_cached": 'Demucs stems cached (%s): %s',
        "log_demucs_copy_failed": 'Could not copy the Demucs stems to the cache: %s',
        "log_demucs_karaoke_done": 'Demucs karaoke delivered: %s',
        "log_demucs_marker_failed": 'Could not write the source marker next to the Demucs stems: %s',
        "log_model_half_downloaded": 'The model in %s came down only half; it is being downloaded again',
        "log_transcript_unchanged": 'The transcription of %s is word for word the previous one; coupling and timing stay',
        "log_transcript_fingerprint_failed": 'Could not make a fingerprint of the transcription',
        "log_demucs_reused": 'Demucs stems reused from the cache (%s): %s',
        "log_demucs_separating": 'Demucs separating: %s',
        "log_demucs_stale": 'The Demucs stems in the cache (%s) belong to other audio; separating again',
        "log_demucs_started_original": 'Large model started: Demucs on the original (isolating the vocals for a better transcription)',
        "log_demucs_started_residual": 'Large model started: Demucs (separating vocals for residual-vocals detection; no language needed)',
        "log_demucs_stem_done": 'Demucs stem delivered: %s',
        "log_derived_delete_failed": 'Could not remove a derived file (in use?): %s',
        "log_derived_nothing": 'Change to %s: there was nothing derived yet',
        "log_derived_removed": 'Derived data removed after a change to %s: %s',
        "log_empty_dir_cleaned": 'Empty folder cleaned up: %s',
        "log_energy_word_line_skipped": 'Energy word timing skipped for line %d (%r)',
        "log_energy_word_skipped": 'Energy word timing skipped (caught)',
        "log_export_mp3_cbr": 'Export (mp3, CBR %d bps)',
        "log_export_mp3_vbr": 'Export (mp3, VBR ~%s bps): quality -q:a %d',
        "log_export_wav": 'Export (wav): %s',
        "log_file_delete_failed": 'Could not delete the file: %s',
        "log_filler_on_energy": '%d filler line(s) placed on the vocal energy (%.1f-%.1f s)',
        "log_report_file": "Test report of this run: %s",
        "log_report_write_failed": "Could not write the test report: %s",
        "report_title": "Test report",
        "report_when": "Run on %s.",
        "report_version": "Version %s.",
        "report_scope": "Scope: %s.",
        "report_actions": "Actions: %s.",
        "report_time": "Took %.1f s (processor time %.1f s).",
        "report_alarms": "Alarms:",
        "report_scope_current": "the current project only",
        "report_scope_all": "all projects",
        "log_block_gap_clipped": '%d line(s) between %.1f and %.1f s not spread across the block boundary: %d part(s)',
        "log_held_note_capped": 'line %d: held note bounded at the block boundary (%.1f -> %.1f s)',
        "log_filler_spread": '%d filler line(s) spread over the sung time (%.1f-%.1f s, %d onset(s) found)',
        "log_forced_alignment_applied": 'Forced alignment applied to %d segments',
        "log_forced_alignment_failed": 'Forced alignment failed; the Whisper timing is kept',
        "log_forced_alignment_skipped": 'Forced alignment skipped: no certain language (Whisper timing kept)',
        "log_forced_alignment_started": 'Large model started: forced alignment (wav2vec2, language=%s)',
        "log_fragment_exclusions": 'Fragment exclusions: %d',
        "log_global_offset": 'Global offset: %+.0f ms (confidence %.2f)',
        "log_gui": 'GUI: %s',
        "log_hallucination_filtered": 'Hallucination segment filtered: %r (%.1fs-%.1fs), best lyrics match %.2f',
        "log_hallucination_position": 'hallucination filtered by position: %r (%.1fs-%.1fs); lyrics window word %d-%d, best match %.2f',
        "log_hallucinations_filtered": "Hallucination segments filtered out of the coupling: %d (e.g. 'MUZIEK')",
        "log_history_unreadable": 'The transcription history is unreadable; started again',
        "log_history_updated": 'Transcription history updated: %s (run %d, %s)',
        "log_history_write_failed": 'Could not write the transcription history (%s)',
        "log_instrumental_made": 'Instrumental (karaoke) made from the original: %s (alignment is skipped, offset 0)',
        "log_input_names_migrated": 'Input file names moved to their current key (%d of them)',
        "log_karaoke_from_original_failed": 'Making the karaoke from the original failed',
        "log_karaoke_generated": 'Karaoke generated from the original: %s',
        "log_karaoke_is_instrumental": 'The karaoke is the Demucs instrumental; residual-vocals analysis skipped (no singing).',
        "log_karaoke_text_loaded": 'Karaoke text loaded: %d lines (%d crowd, %d bg)',
        "log_karaoke_text_open_bg": 'The karaoke text ends inside a [bg] block; close it with [/bg]',
        "log_karaoke_text_open_crowd": 'The karaoke text ends inside a [crowd] block; close it with [/crowd]',
        "log_karaoke_vocals_empty": 'The karaoke vocal stem is (virtually) empty (RMS %.4f < %.4f); transcription skipped',
        "log_language_fixed": "Language fixed manually to '%s'",
        "log_language_from_original": '[karaoke] Language taken over from the original: %s',
        "log_language_from_text": '[%s] Language detected on its own text: %s (%s) -> passed to Whisper',
        "log_language_manual": '[%s] Language (chosen manually): %s',
        "log_language_too_close": '[%s] Language detection too close together (%s); Whisper detects the language itself (auto)',
        "log_language_uncertain": '[%s] Language detection uncertain (%s); Whisper detects the language itself (auto)',
        "log_librosa_resample_missing": 'librosa resample not available, falling back on scipy',
        "log_logfile_failed": 'Could not delete log file: %s',
        "log_logs_cleaned": 'Logs cleaned: %d removed, %d kept',
        "log_lyrics_aligned": 'Lyrics aligned: %d/%d words coupled',
        "log_lyrics_alignment_failed": 'Lyrics alignment failed; it is skipped',
        "log_lyrics_extras": 'Lyrics extras: %d time slots',
        "log_lyrics_loaded": 'Lyrics loaded: %d words (%d bg)',
        "log_lyrics_open_bg": 'The lyrics end inside a [bg] block; close it with [/bg]',
        "log_lyrics_override_cleared": 'Lyrics override cleared',
        "log_lyrics_override_saved": 'Lyrics override saved: %d word(s)',
        "log_manual_damping": 'Manual damping applied: %d fragments',
        "log_meta_removed": "Meta '%s' removed from project.json",
        "log_meta_updated": "Meta '%s' updated in project.json",
        "log_move_failed": 'Moving failed: %s',
        "log_mp3_written": 'Mp3 written: %s',
        "log_no_alignment": 'No alignment found; it is made automatically',
        "log_no_lyrics_language": "[%s] No lyrics; the Whisper language setting '%s' is used",
        "log_no_reliable_windows": 'No reliable window measurements; the global offset is used for the whole song',
        "log_no_truetype": 'No TrueType font found; the default font is used',
        "log_onset_difference_failed": 'Determining the vocal onset from the difference failed',
        "log_onset_failed": 'Determining the vocal onset failed for %s',
        "log_onset_from_demucs": 'Vocal onset from the Demucs vocal stem: %.2f s',
        "log_onset_from_difference": 'Vocal onset determined from original minus karaoke: %.2f s',
        "log_onset_from_karaoke": 'Vocal onset from the karaoke vocal stem: %.2f s',
        "log_onset_from_original": 'Vocal onset from the original vocal stem: %.2f s',
        "log_onset_placement_rejected": 'onset placement rejected (%.2f s line) for %d filler line(s) (%.1f-%.1f s)',
        "log_onsets_failed": 'Determining the energy onsets failed',
        "log_open_browser_failed": 'Opening the browser failed for %s',
        "log_open_dir_failed": 'Opening the folder failed for %s',
        "log_open_dir_skipped": 'Opening the folder skipped (does not exist): %s',
        "log_open_file_failed": 'Opening the file failed for %s',
        "log_orphan_input_failed": 'Could not delete orphan input folder: %s',
        "log_orphans_cleaned": 'Orphan projects cleaned up (no output folder any more): %s',
        "log_outlier_region": 'Outlier alignment region %.1f-%.1f s (offset %+.0f ms) differs from the local trend %+.0f ms; replaced by the trend',
        "log_parallel_detection": 'Parallel detection: %s at once',
        "log_parallel_out_of_memory": 'Parallel detection ran out of memory; falling back to sequential',
        "log_paths_updated": 'Project paths updated: %d references (%s -> %s)',
        "log_phonetic_segmentation_skipped": 'Phonetic segmentation skipped for a line',
        "log_phonetic_timing_skipped": 'Phonetic timing skipped (caught)',
        "log_pins_migrated": '%d manual coupling(s) converted to the transcription including the filtered words',
        "log_pins_relocated": '%d of %d manual coupling(s) relocated: the lyric word list changed shape',
        "log_pins_saved": 'Word couplings saved: %d pin(s)',
        "log_preload_failed": 'Could not preload the audio for forced alignment; WhisperX loads it itself (may show a window)',
        "log_project_damaged": 'Damaged project.json (%s); starting empty',
        "log_project_deleted": 'Project deleted: %s (input, output and cache)',
        "log_project_saved": 'project.json saved (%s)',
        "log_project_switch": 'Project switch: %s',
        "log_prompt_failed": 'Building the lyrics prompt failed (skipped)',
        "log_properties": 'Properties %s: %s',
        "log_region_offset": 'Region %.1f-%.1f s: offset %+.0f ms (confidence %.2f)',
        "log_render_done": 'Render done: %s',
        "log_render_command": 'ffmpeg command: %s',
        "log_lead_silence_ok": 'Silence before the singing checked: %.2f s',
        "log_lead_silence_unknown": 'Could not measure the leading silence in %s; render not checked',
        "log_silence_measure_failed": 'Could not measure the silence in %s',
        "err_lead_silence": "The video ran out of step: there should be {expected} s of silence before the singing and there is {measured} s. Picture and sound would then be shifted for the whole song, so the video was not written.",
        "log_frames_reused": "Frames reused: %d of %d (%d%%) were the same as the frame before.",
        "log_render_started": 'Render started: %s (%dx%d, %d fps, %.1f s)',
        "log_resampled": 'Resampled: %s -> %s (%d Hz, %d channel(s))',
        "log_residual_on_stem": 'Residual-vocals detection on the separated vocal stem',
        "log_restore_applied": 'Restore from original applied: %d fragments, %.1f s',
        "log_restore_empty": "Restore from original: empty original fragment for '%s'; skipped",
        "log_restore_no_original": 'Restore from original: no original found; %d fragment(s) skipped',
        "log_restore_rate_mismatch": "Restore from original: sample rate of the original (%d Hz) differs from the karaoke (%d Hz); fragment '%s' skipped",
        "log_restore_saved": 'Restore-from-original fragments kept: %d',
        "log_restore_too_short": "Restore from original: the original fragment is shorter than the marked window for '%s' (%.2fs short)",
        "log_restore_unusable": 'Restore from original: the original is unusable (%s); all fragments skipped',
        "log_rewrite_failed": 'Could not rewrite the references: %s',
        "log_rms_failed": 'Determining the RMS envelope failed',
        "log_segments_cached": 'Segments cached: %s',
        "log_sentence_coupling": 'Sentence coupling: %s (%s)',
        "log_separation_failed_karaoke": 'Vocal separation failed; the whole karaoke is used',
        "log_separation_failed_original": 'Vocal separation of the original failed; the mix is used',
        "log_startup_size": "Window resized at startup from %dx%d to %dx%d "
                            "(%s size was too small for the content)",
        "log_after_song_end": "%d coupling(s) released that lay after the end "
                              "of the singing (%.1f s)",
        "log_tail_from_the_back": "Tail of %d word(s) fitted from the back: %.1f s "
                                  "of singing available, %.1f s needed",
        "log_several_variants": "Several variants of '%s' found; %s is used",
        "log_skipped_placed": '%d skipped lyrics word(s) placed on the vocal stem',
        "log_source_changed": 'Source changed outside the steps: %s',
        "log_step_removed": "Step '%s' removed from project.json",
        "log_step_updated": "Step '%s' updated in project.json",
        "log_stress_paint_error": 'Error in the stress editor paintEvent (caught)',
        "log_stress_save_failed": 'Saving the stress failed',
        "log_task_cancelled": 'Background task cancelled by the user',
        "log_task_error": 'Error in a background task',
        "log_timing_auto_failed": 'Could not write timing_auto.json',
        "log_timing_diagnostics_failed": 'Could not write the timing diagnostics',
        "log_timing_paint_error": 'Error in the timing editor paintEvent (caught)',
        "log_timing_project_mismatch": "timing.json belongs to project '%s', but the current project is '%s' (%s). Possible cross-contamination.",
        "log_timing_reanchored": 'Timing re-anchored: stored offset %+.0f ms, now %+.0f ms -> shift %+.0f ms',
        "log_timing_sync_failed": 'Updating timing.json after the text change failed',
        "log_timing_synced": 'timing.json updated after the karaoke text change: %d line(s) adjusted',
        "log_timing_written": "Timing written: %s (%d lines, offset %s, project '%s')",
        "log_timing_flat_repaired": "Flattened lines repaired on opening: %d",
        "log_chunk_words_failed": "The chunked words could not be written",
        "log_timing_rescued": "Manual timing kept across the text change: %d lines, %d with new text",
        "log_timing_kept": "Manual timing kept; what changed was: %s. If the timing no longer fits, make it again with 2.2.",
        "log_timing_rescue_failed": "Manual timing could not be kept; the file can be made again with 2.2",
        "log_transcript_override_cleared": 'Transcript override cleared',
        "log_transcript_override_saved": 'Transcript override saved: %d word(s)',
        "log_transcription_done": 'Transcription done: %d segments, %d words in %.1f s',
        "log_transcription_started": 'Transcription started: %s',
        "log_unexpected_structure": 'Unexpected structure in %s; starting empty',
        "log_unknown_keys": 'Unknown keys ignored in %s: %s',
        "log_vbr_failed": 'VBR detection failed for %s',
        "log_video_rendered": 'Video rendered with audio %s',
        "log_vocal_refine_skipped": 'Vocal stem refinement skipped (caught)',
        "log_vocal_waveform_missing": 'Vocal stem waveform not available',
        "log_vocals_copy_failed": 'Could not copy the vocal stem to the cache',
        "log_vocals_failed": 'Making the vocal stem of the original failed',
        "log_vocals_ready": 'Vocal stem of the original prepared: %s',
        "log_wav_saved": 'Wav saved: %s',
        "log_whisper_model_load": 'Loading Whisper model %s (device=%s, compute=%s)',
        "log_whisper_model_lanes": "Whisper may do %d run(s) at once, %d threads each",
        "log_whisper_model_reused": 'Whisper model %s reused (device=%s, compute=%s)',
        "log_whisper_output": 'Whisper output written to %s',
        "log_written_words": 'Written: %s (%d words)',
    },
}


def set_language(code: str) -> None:
    """Set the active interface language (falls back to nl if unknown)."""
    global _CURRENT
    _CURRENT = code if code in TRANSLATIONS else "nl"


def current_language() -> str:
    """The active language code."""
    return _CURRENT


#: The numbered main buttons, in the order in which they appear on the
#: tabs (B325). A message that refers to a button writes the key between
#: braces (``"doe eerst '{step_detect}'"``); :func:`t` fills in the
#: current label. That way the numbering is maintained in one place, and
#: a message can never quote an outdated button name again.
BUTTON_KEYS: tuple[str, ...] = (
    "step_detect", "step_couple", "step_analyse", "step_karaoke",
    "video_edit_stress", "video_timing", "video_edit_timing", "video_render",
)

_BUTTON_PATTERN = re.compile(r"\{(" + "|".join(BUTTON_KEYS) + r")\}")


def t(key: str) -> str:
    """Translate a key into the active language.

    Falls back to Dutch when the key is missing there, and to the key
    itself when it is missing in both. A reference to a button
    (``{step_detect}`` and the like, see :data:`BUTTON_KEYS`) is filled
    in right away; every other placeholder is left alone so that the
    caller can still ``.format()`` it (B325).
    """
    text = (TRANSLATIONS.get(_CURRENT, {}).get(key)
            or TRANSLATIONS["nl"].get(key)
            or key)
    if "{" in text and key not in BUTTON_KEYS:
        text = _BUTTON_PATTERN.sub(lambda m: t(m.group(1)), text)
    return text
