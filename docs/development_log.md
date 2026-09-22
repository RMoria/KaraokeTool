# Further development – approach and current state

The log of this program: per version what changed, why, and what the measurement said about it.

## Approach

The working agreement between the owner and the assistant that builds
this program is not part of this public copy. What follows is the log
itself: per version what changed, why, and what the measurement said
about it.

## Data model

- `input/<song>/` – only the original files (original, karaoke,
  songtekst.txt, karaoketekst.txt, logo).
- `output/<song>/settings/` – all choices + `timing.json` (+ `timing_auto.json`,
  `project.json`); permanent.
- `output/<song>/` – end products (karaoke_edit, video); permanent.
- `cache/<song>/` – regenerable; wiped recursively every session.

## Pipeline (short)

1. Detect words (Whisper large-v3/distil/small) on the original and the
   karaoke; language from the lyrics (langdetect, threshold 0.70),
   otherwise auto or a manual choice.
2. Analysis + phonetic clustering (tracking down residual vocals in the
   karaoke).
3. Align original↔karaoke (offset regions; outliers are rejected, the
   projection is monotonic). Karaoke made from the original → offset 0.
4. Adjust the karaoke (damp clusters, −25 dB) + export.
5. Render the karaoke video (timing per syllable, crowd sections red).

## Large models (optional, install.bat)

- **Demucs** – separate the vocals (residual-vocal detection) and make
  "karaoke from the original".
- **WhisperX** – forced alignment (more precise word times per language).
- The rhythm anchor runs on **librosa** and is fixed in the core.

## Backlog

Handled through v0.53: B58–B101.

Included in v0.54: B103, B104, B106, B108, B110–B120, B129, B130, B131
(bugfixes, startup/cache/project management, language detection per track,
and the core of the timing overhaul). B105 is partly done (syllable model +
cleanup); the full word/syllable hierarchy follows.

Included in v0.54.1: B132, B133, B134, B135.
Included in v0.54.2: B137 (original track no longer squashed), B138 (original
1-to-1 above the karaoke line via the coupling), redistribution between anchors.
Included in v0.55: onset fix (percentile floor instead of median; first line
on the real entry, verified on the Oerend Hard audio -> ~3.7 s).
Included in v0.56: B141 (hallucination/"MUZIEK" segments filtered out of the
coupling -> no more false anchors, verified on the supplied transcription)
and B142 (original transcribed on the Demucs vocal track instead of the full
mix, for more reliable words/times).

Included in v0.57: B146 (button "Timing verfijnen"), B147 (pauses between
lines), B143 (diagnostics subfolder + version tracking + a Settings toggle),
B149 (the right language in the bookkeeping instead of the config default "auto").

Included in v0.58: B139/B148 (partly) - crammed repeat/crowd lines in the
fade-out get spread out (minimum duration wins, overlap pushes forward). The
deeper B148 (with many repetitions the coupling sometimes picks the wrong
source spot) stays open; that needs better source detection/coupling.

Included in v0.59: own app icon (window + Windows taskbar via AppUserModelID)
and deterministic language detection (fixed langdetect seed).

Included in v0.59: app icon (window + Windows taskbar via AppUserModelID),
deterministic language detection (fixed langdetect seed), and the manual
(B128, `docs/manual.md`).
Included in v0.60: B148 - a fade-out with many untranscribed repeat lines is
spread over the full remaining time up to the end of the song (verified on
the Oerend Hard data: Whisper stops after ~188 s, the fade-out runs to
~219 s).

Included in v0.61: B121 - word coupling editor between step 1 and 2. The
testable core (pins -> lyrics↔transcription coupling -> effect on
analysis/timing, including invalidation) is tested; the Qt UI
(`koppeleditor.py`) still needs a test on the machine with a screen. The
base is reusable for B151 (syllable/stress); full unification with the
waveform editors (B152) stays a separate refactor.

Included in v0.62: B121 (continued) - the word coupling editor can now couple
1-to-many (one lyrics word to several found words) and the click logic is
repaired: a click on a word box selects/(un)couples (box click takes
precedence over line click, so lines no longer disappear by accident), and
manual couplings stay blue instead of reverting to red. The model behind the
editor now uses list pins (`dict[int, list[int]]`) from lyrics index to
transcript index. Plus `download_fonts.bat`: a one-off script that reads the
google/fonts folder per typeface and fetches the right .ttf into
`assets/fonts/` (preparation for B102; the .ttf files are supplied and then
bundled with the render).

Included in v0.63:
- **B102** – 15 extra typefaces shipped in `assets/fonts`; a new
  `modules/fonts.py` reads the folder; Settings has a font-choice dropdown
  that refreshes when the tab is opened; `install.bat` checks the folder and
  fetches only the missing fonts. The separate `download_fonts.bat` is gone.
  (Preview/85% fit still to come.)
- **B107** – inline `[pause]`/`[pauze]`: the pause sign (…) as its own
  syllable inside the line; the render draws dots that light up on the
  average beat (`karaoketekst.apply_pause/is_pause`, `video._draw_pause`).
- **B127** – timing editor display choice blocks/lines/words
  (`timing.editor_view_cells/word_spans`, `TimedLine.blok`); dragging stays
  at line level, the other views are for orientation.
- **B153** – cut/merge found words in the coupling editor
  (`songtekst.cut_word/merge_words/remap_pins`), with a persistent
  transcript override (`pipeline.transcript_override`).

Included in v0.63.1: a fix for fetching variable fonts in `install.bat`. The
file names contain `[wght]`/`[wdth,wght]`; PowerShell's `-OutFile` read those
brackets as wildcards, so Oswald, Montserrat, Fredoka, Baloo 2 and Rubik were
never written out. The target name now has `[...]` stripped off (e.g.
`Oswald.ttf`). Rerun `install.bat` to fetch the five variable fonts after
all.

Included in v0.64:
- **B154/B155** – coupling editor selection UX: a second click on the same
  word clears the selection; after making a coupling the selection is
  released.
- **B156** – cutting/merging on the lyrics row as well (on top of the
  found-words row from B153), via a lyrics override
  (`pipeline.lyrics_override`, `songtekst.cut_lyric/merge_lyrics/
  remap_pin_keys`). Only for coupling/timing; the video text
  (karaoketekst.txt) stays unchanged.
- **B157/B158** – coupling lines made readable: only the lines of the
  selected/pinned word solid and thick, the rest very faint.
- **B159** – tail analysis (`songtekst.trim_tail_matches`): a run of weak
  matches at the end (fade-out, no reliable transcription) is uncoupled
  instead of dragging the last good word through.
- **B160-B163** – timing editor: dropdown order blocks/lines/words (lines by
  default); the view also applies to the original text track
  (`timing.original_view_cells`); blocks are now draggable and stretchable
  just like lines (cells carry their source lines; the whole block scales
  along); a block shows the full text instead of only the first line.
- **B150** – syllable model: `timing.split_syllables` uses pyphen (Dutch
  hyphenation) when available, falling back on the vowel-group heuristic.
  Added to requirements.txt.

Included in v0.65:
- **B164** – step buttons renumbered: 1 Detecteer · 2 Woorden koppelen ·
  3 Analyse · 4 Karaoke aanpassen.
- **B165** – the manual as a tab (to the right of Settings), renders
  `docs/manual.md` through a QTextBrowser (Markdown).
- **B167** – (regression in v0.64) the probability colours in the coupling
  editor are visible again: without a selection everything is coloured, only
  dimming when a word is selected.
- **B166** – fade-out/leftover lines get the duration of the earlier line
  with exactly the same text (median), placed sequentially
  (`timing._reference_durations`), instead of spread proportionally.
- **B139** – short crowd shouts ('Oeh!', 'Ah!') get a visible minimum
  duration (`_MIN_CROWD_S`) so they are not squashed into a dash.
- **B136** – temporary test button "Modellen vergelijken" (Settings):
  `pipeline.compare_models` transcribes the original both as a full mix and
  as the Demucs vocal track with large-v3/distil-large-v3/small and reports
  the word count + lyrics coverage per combination; writes
  `diagnostiek/model_vergelijking.txt`. Can go later.

Still open here (reviewed at B302, v0.95):
- **B139 (rest)** – the full crowd coupling/placement (inline vs block,
  order, manual overlap) stays a bigger overhaul. Partly built; whether the
  rest is still needed is a judgement call in use.
- **wav2vec2** – already used via WhisperX forced alignment on the original
  (more precise word times). Further gain could come from forced alignment
  on the karaoke residual vocals too, and from VAD-driven segmentation.
- *(B136 was listed here too as "can go later" – the button "Modellen
  vergelijken" and `pipeline.compare_models` have since been removed.)*

Included in v0.66:
- **B122** – video fields on the karaoke video tab: karaoke title, original
  artist, original title (in `config.VideoSettings`, stored). The karaoke
  title is leading for the title + file name.
- **B123/B124** – intro/outro show the title with a credit line underneath,
  "artist - title" of the original (`video.render_video(artist=...,
  orig_title=...)`).
- **B126** – configurable background image (center crop behind all the
  images, `video._load_background`).

Included in v0.67:
- **B168** – credit line (artist - original title) only in the intro.
- **B125** – karaoke video without karaoke text: fall back on `songtekst.txt`
  (`pipeline.karaoke_text_path`), used in generate_timing, build_coupling and
  the input status. That is how you make a karaoke video of the original.
- **B102 (preview)** – live typeface preview in Settings
  (`_update_font_preview` via QFontDatabase).

Included in v0.68:
- **B102 (completed)** – the body font is chosen as large as possible in the
  render, but shrunk until every line fits in at most two rows within 85% of
  the width (`video._fit_body_font`, `_TEXT_WIDTH_FRAC=0.85`). Drawing and
  overflow checks use the same 85% limit.

Included in v0.69:
- **B151** – stress (KO-men vs ko-MEN). `Syllable.nadruk` (stored in
  timing.json), an automatic default stress per word on the first
  syllable (`timing.apply_default_stress`), toggle logic
  (`timing.set_word_stress`), a stress editor
  (`modules/klemtooneditor.py`) with a button on the video tab, and a
  subtle render accent (fake bold) for the stressed syllable.

That completes the original backlog (B58–B168, B102/B105/B107/B121–B168 and
the stress items B150/B151). Further ideas (audio template finder, deeper
crowd coupling) stand on their own.

Included in v0.72: B171 (titles on tab 1, left of the input), B172 (background
on Settings under Background colour), B173 (message panel hidden on
Settings/Manual), B174 (Options block gone; enabled_tracks always
original+karaoke; dead toggle code gone), B178 ("Video-invoer controleren"
button gone, video buttons renumbered, _check_video_inputs removed), B180
(TimedLine.uitgeschakeld; lines/blocks/words off/on in the timing editor;
render skips disabled lines), B181/B183 (project/version/time header in
timing.json + timing_auto.json via save_timing; timing_project + mismatch
warning), B182 (install.bat no longer moves anything, only warns), B184
(clean_cache empties everything incl. read-only via onexc/onerror + chmod),
B175-B177 (unused imports/functions/locals cleaned up).

Standing rule: with every change, check for code that has become redundant and
clean it up (pyflakes + an unused-function scan).

Included in v0.73: B179 (crowd handling). Inline `[crowd]...[/crowd]` stays
inside the logical line (`karaoketekst._parse_inline` + `TextLine.crowd_words`)
and is marked as crowd at syllable level (`Syllable.crowd`,
`timing.apply_inline_crowd`); the render colours per syllable red
(`video._draw_line`), a `[pause]` before it stays normal. Separate crowd lines
(B179b) and crowd blocks (B179c) behave as before. Because inline crowd is no
longer split off, the separate crowd lines that had no coupling to the
original disappear as well.

That completes the whole collected backlog up to and including B184.

Included in v0.74: B185 (project name -> prefill Karaoketitel, one direction),
B186 (karaoke input message), B187 (window vertically scalable via lower
minimum heights + window size remembered with QSettings), B188 ("Titels en
artiest"), B190 (coupling top->bottom in the coupling editor), B199/B199b
(disabled lines out of the overlap; re-enabled lines fitted back in keeping
order, 2x min + neighbours 1x min), B200 (button order stress before timing),
B203 (intro with silence up to >=5 s via adelay + lines shifted), B204 (last
line keeps its vocal/crowd colour until the outro), B205 (audio files released
when the editor closes so the cache empties).

~~Still open (heavier/research items): B189, B191, B193, B194/B195, B196,
B198, B201/B202.~~ **Out of date** – reviewed at B302 (v0.95): all of these
items were built in later versions after all and have an implementation in
`modules/` (B189 `_merged_spans` in koppeleditor.py, B191 `extend_coupling`,
B193 `_ORIG_CROWD` in timingeditor.py, B194/B195/B196 in
ritme.py/timingeditor.py, B198/B201/B202 in timingeditor.py and
klemtooneditor.py). The list had simply been left standing without being
updated; anyone reading it got a wrong picture of what was still to be
done.

Included in v0.70:
- **B169** – stress counts in the auto timing
  (`timing.redistribute_by_stress`): best-effort lines divide their span in
  proportion to stress (the stressed syllable heavier), without changing the
  line span or reliable/manual times. Runs in `generate_timing` and on saving
  in the stress editor.
- **install.bat** warns when run from a Temp/Downloads folder; Windows
  security policy (AppLocker/Smart App Control/WDAC) often blocks DLLs there
  (e.g. PyAV with faster-whisper: "DLL load failed ... blocked by an
  application control policy"). Fix: install in e.g.
  %USERPROFILE%\KaraokeTool.

Included in v0.71:
- **install.bat move option** – if you run it from a Temp/Downloads folder,
  install.bat offers to copy the folder (excl. venv/cache) to
  %USERPROFILE%\KaraokeTool (robocopy) and continue the installation there.
  That leaves Windows security alone. Start the program from that new folder
  afterwards.
  (lyrics) words to the found Whisper words; downstream uses the real
  words; also runs when the editor is closed.
- **B139** – crowd timing: do not treat inline/block crowd too loosely, keep
  it in order, no automatic overlap (overlap only by hand). Needs the
  transcription JSON (B131) to reproduce the placement exactly.
- **B105 (rest)** – full hierarchical timing: word relative to the line,
  syllable relative to the word (now largely via forced-alignment word times;
  edge cases remain).
- **B127** – timing editor: switchable view blocks/lines/words.
- **B107** – inline `[pause]`: one logical line, two parts for
  placement/timing, dots on the average beat in the render.
- **B127** – timing editor: switchable view blocks/lines/words.
- **B121** – word match editor (couple original↔lyrics, colours by
  probability, 1-to-many).
- **B122** – input fields for original artist/title + karaoke title (leading
  for the render).
- **B123/B124** – video variants (music×text); logo/title/artist lines.
- **B125** – karaoke text optional (karaoke video of the original).
- **B126** – background image in Settings (center/crop).
- **B102** – bundle extra fonts (Bebas Neue and others) + preview + 85% fit;
  install.bat fetches the .ttf files on the machine itself.
- **B128** – manual/help for `[crowd]`, `[pause]`, the workflow, the choices.

Included in v0.75 (big combined round):
- **B207** – language detection first filters out filler lines ("na-na",
  "la-la", "oh-oh") with a structural heuristic (repetition of short
  syllables + crowd markers), not with a word list; falls back on the whole
  text if nothing sensible would be left otherwise.
  `pipeline._is_filler_line`/`_strip_filler_for_language`.
- **B208** – if the two best language candidates are within 5% of each other,
  the GUI asks for a choice after all and `_language_for` lets Whisper decide
  itself (`language_ambiguous`).
- **B191** – `songtekst.extend_coupling`: the automatic 1-to-1 coupling hooks
  in an adjacent, not yet claimed found word as long as that noticeably
  improves the phonetic similarity ("Tinus" → "Tien" + "Is").
- **B189** – the coupling editor shows a double coupling of consecutive found
  words as one merged box; undoing it splits them again
  (`KoppelCanvas._merged_spans`).
- **B193** – separate crowd lines (which exist only in the karaoke) are
  mirrored 1-to-1 into the original track of the timing editor.
- **B194/B195/B209** – vocal energy analysis on the Demucs vocal track of the
  original (`pipeline.ensure_original_vocals` secures the vocals). Held notes
  of reliable lines run on until the energy really drops
  (`ritme.held_note_end`), bounded by the next entry. Untranscribed runs of
  filler lines are placed on the energy pulses (`ritme.energy_onsets`), with
  a fallback on an even/beat distribution. On/off via Settings
  (`geavanceerd.zangstem_analyse`).
- **B196** – the timing editor also shows the vocal track under the karaoke
  waveform (projected onto the karaoke timeline), selectable as playback
  source in "Bron"; fixed, non-scrolling track labels at the top left.
- **B198** – lines can be switched off/on from the original track; the grey
  applies to both tracks (`original_view_cells` now carries `rows`).
- **B201/B202** – stress editable on both the karaoke and the original (two
  groups in the editor, original stress stored in step `klemtoon_origineel`).
  The stress difference aligns the karaoke timing at most one syllable slot
  onto the original (`timing.shift_stress_to` / `align_karaoke_stress`),
  without changing text or order.
- **B206** – input fields show the original file name (stored in
  project.json) and the file picker opens on the last used folder if it still
  exists (`pipeline.input_display_name`/`input_start_dir`).
- **B195** – `install.bat` now always installs the large models (a message +
  pause instead of a Y/N question; `:skip_smart` removed).

Included in v0.76:
- **B210** – Karaoke title/Original artist/Original title per project in
  `project.json` (`pipeline.set_project_title`/`apply_project_titles`), loaded
  into `config.video` on opening/switching projects so the render picks them
  up. One-off migration of existing global values; no global storage any
  more, no leaking between projects or loss on restart.
- **B211** – the sound cluster field shrinks first (at least ~2 clusters with
  their own scrollbar); only after that the window scrollbar. Window minimum
  lowered to 760×360.
- **B212** – a shared helper `pipeline.export_demucs_stems` writes
  `karaoke_demucs.mp3` (instrumental) and `vocal_demucs.mp3` (vocals) into the
  output folder on every Demucs split. Called from "Karaoke uit origineel",
  the original split in `detect_track`, `ensure_original_vocals` and the
  generation of the karaoke. (The karaoke residual-vocal split deliberately
  does not export, so as not to overwrite the meaningful original stems.)
- **B213** – `songtekst.is_filler_word` + `align_lyrics(..., skip_filler=True)`:
  na-na/la-la filler words take no part in the Needleman-Wunsch alignment, so
  the real words couple cleanly 1-to-1 and the coupling lines are not pulled
  askew by a big na-na chunk or a hallucination. Timing of those filler lines
  runs through the vocal energy (B209).

Included in v0.77:
- **B214** – configurable output folder (`GeavanceerdSettings.uitvoermap`,
  `ProjectPaths.output_base`). Settings has an "Output-map" block;
  `pipeline.output_writable` tests writability, `relocate_output_base` moves
  existing project folders and rewrites the path references in every
  `project.json` (via `ProjectStore.rewrite_prefix`). Input and cache stay at
  the app root. Back to `<root>/output` = default (no folder of your own).
  The choice is global in config.json.
- **B215** – `pipeline.remove_demucs_stems` wipes `karaoke_demucs.mp3` and
  `vocal_demucs.mp3` from the output folder when a new original is chosen
  (called from `_choose_file`).
- **B220** – the coupling editor gets a column layout (`_relayout`): coupled
  top/bottom words share a column, uncoupled ones get a column of their own.
  That keeps the coupling lines straight through the whole song, even with
  many uncoupled na-na words on one row. Hit testing and the merged boxes
  (B189) work on the columns.
- **B216** – revision of B211: the sound cluster field now has vertical size
  policy Ignored (small minimum height), so it shrinks/grows symmetrically
  with the window instead of only ratcheting upwards.
- Path scan: the code contains no hard absolute paths; everything is derived
  from the app root. (Read-only location -> data to %LOCALAPPDATA% follows as
  B221.)

Included in v0.78:
- **B136** – temporary button "Modellen vergelijken" + `compare_models`/
  `_transcription_agreement` and the accompanying language texts/test removed.
- **B223** – vocal track in the timing editor under the karaoke lines
  (constants shifted; label along with them).
- **B222** – the coupling editor now merges on the bottom row as well:
  several consecutive lyrics words at one found word as a single box, a
  single line, click = undo (`_merged_bottom_spans`), symmetric with B189.
- **B224/B225** – `ritme.active_windows`/`active_end` clamp lines to where the
  vocals really sound (no overrun of empty vocal patches); `count_repetitions`
  estimates chant repeats from the energy. Hooked into `_refine_with_vocals`.
- **B226** – `run_video(text_source, audio_source)` + `_render_audio`/
  `_render_timed_lines`; on "Video maken" the GUI shows a pop-up with one
  text kind (karaoke/original) and one music kind (karaoke/original/
  demucs/vocals). Default karaoke + karaoke text.
- **B227** – `video.GAP_MIN_S`: an instrumental gap ≥5s between two lines ->
  no (grey) text but a 3-2-1 countdown to the next line.
- **B221** – `filesystem.is_writable`/`resolve_data_root`: with a read-only
  app location the data (input/output/cache/logs/config) goes to
  `%LOCALAPPDATA%\KaraokeTool`. `install.bat` puts the venv there and the
  launcher passes the data folder on via `KARAOKETOOL_DATA`. The code knows
  no hard paths; assets/docs stay readable in the app folder.

Included in v0.79:
- **B230** – clicking the vocal waveform moves the playback line (the seek
  band extended with the vocal track at the bottom).
- **B232** – the cache-clearing setting is global (config.json) and
  persistent (round-trip confirmed); defaults to clearing=True.
- **B229** – all buttons turn 'yellow' (busy) as long as their action runs
  (`_install_busy_indicator`/`_mark_busy_click`); the colour is configurable
  via `thema.knop_actief` (colour picker at the GUI colours, default #f2c200).
- **B222** – the coupling editor now merges bottom-row groups on the basis of
  overlapping targets (`_merged_bottom_spans` groups transitively), which also
  covers "Oh bébé," ↔ "Eh l'bébé"; the merged line is blue as soon as one
  member has been coupled by hand.
- **B228** – `songtekst.creative_couplings`: 2-to-1 ("fort minable" →
  "formidable") and 1-to-1 gaps within the anchor window; distant duplicates
  stay out of range. Applied in `word_coupling_view`.
- **B234** – `timing.distribute_over_windows` +
  `pipeline._apply_energy_word_timing`: within each line the words are spread
  over the vocal-active sub-windows, so pauses between words end up in the
  timing. Vocals projected onto the karaoke timeline; clean fallback without
  vocals. (Syllable stretching on held vowels follows.)

Included in v0.80:
- **B216 (final)** – the whole-window `QScrollArea` (B187) has been removed:
  it used the preferred height of the content, which meant the flexible
  cluster field never shrank along. Now the plain `QMainWindow` layout drives
  the size (`setCentralWidget(central)`); the cluster field and the video
  "karaoke text with timing" group (both stretch) grow/shrink with the window.
  Settings got a `QScrollArea` of its own. Window minimum 760×520.
- **B236** – `CacheSettings.wissen` defaults to `False`; a button "Nu legen"
  (`_clear_cache_now`) next to the checkbox for a one-off clear.
- **B235** – `_do_generate_timing` warns when the timing fell back on an even
  spread (transcription/coupling missing, e.g. after clearing the cache).

Included in v0.81:
- **B241** – `modules/fonetiek.py`: a language-independent segment engine
  (`segment_word`, `segment_weight`, `distribute_word`, `SegmentConfig`) with
  a language register `LANGUAGES` (nl/en; a new language = one extra entry).
  Weights: consonant 1, sonorant 2, short vowel 6, long vowel group 8; the
  last vowel gets +30% reserve; min 15 ms. `timing.apply_phonetic_timing`
  rebuilds the syllable timing per word on segments (vowels longer, the final
  vowel stretched), called in `generate_timing` after B234, behind
  `geavanceerd.fonetische_timing` (on by default) with a fallback.
- **B242** – `video`: smooth line transitions; just after a new line the lines
  move up over `_LINE_TRANSITION_S` (0.35 s, quadratic damping), with the
  outgoing line drawn along. Non-uniform y positions are preserved.
- **B239** – `songtekst.is_symbol_token`/`_meaningful_words`: stray
  punctuation/symbol tokens from the transcription filtered out of
  `flat_transcript` and of the alignment, so they cannot be a coupling target.
- **B240** – timing list refreshed when the Karaoke video tab is opened.
- **B237** – empty title fields for an empty project (at startup).
- Typeface preview: a pangram per language instead of "Oerend hard".

Included in v0.82:
- **B248** – Demucs separates each source only once now, through a shared
  cache (instead of up to 4× the original).
- **B249** – Drift-aware alignment: robust median filter + enforced
  monotonicity, `project_time` interpolates linearly between regions; the
  timing no longer drifts cumulatively in later verses. Finer alignment
  defaults (max_offsets 4→12, window 20→10 s, step 10→5 s).
- **B250** – Weighted timing anchors: reliable anchors (vocal onset,
  syllable/high) win conflicts against repeated chorus lines.
- **B245** – Typeface stored portably (file name instead of an absolute path),
  so the choice does not reset after a folder move or on another computer.
- **B241 follow-up** – Languages on the go: French built in; missing languages
  are created and kept with a header/version in the project diagnostics plus a
  shared `talen/` collection folder for reuse
  (`fonetiek.ensure_language`/`save_language`/`load_language_dir`).
- **B247** – Render pop-up: "Karaoke uit origineel" removed; the music is
  always "Karaoke-muziek".
- Karaoke video tab: the redundant input hint removed (it is in the
  manual). The shipped `config.json`: cache clearing explicitly off.
  Manual: button order brought in line with the app, optional steps
  marked.
- **Review hotfix (this handover)** – `modules/fonetiek.py`: the missing
  `from pathlib import Path` added at module level (the forward-ref annotation
  `-> "Path | None"` on `save_language` failed under pyflakes and would have
  raised a `NameError` when writing out a language). Local duplicate imports
  cleaned up. pytest 321 green, pyflakes clean.

Included in v0.83:
- **B251** – ordered + weighted timing arbitration with block barriers. A new
  `modules/timing_rules.py` (`Candidate`, `best_per_ref`, `arbitrate_anchors`,
  `clamp_refinement`): anchors are picked on effective weight (base weight ×
  confidence). `timing.sanitize_timing` now uses that engine for the anchor
  sequence. **Core fix** (repeated choruses/Formidable): an anchor from an
  earlier block is no longer displaced by a later block, so the offset of a
  chorus does not leak into the next verse and every block anchors on its own
  onset. Toggle `geavanceerd.blok_anker_barriere` (on by default; off =
  everything in one virtual block = old behaviour). The anchor weights
  (`anker_gewicht_lettergreep/hoog/woord/onset`) are tunable via `config.json`
  (like `SegmentConfig`), passed down from `generate_timing`. For a single
  block the behaviour is identical to v0.82 (B250 preserved), verified by the
  suite.
  - **Eval harness** – `modules/timing_eval.py` (`vergelijk`/`vergelijk_paden`/
    `format_report`) + CLI `python -m tools.timing_eval <auto.json>
    <referentie.json>`: compares the auto timing with the manual one per block
    and in total (mean/median/max |onset error| and |duration error| in ms);
    only lines with exactly the same text count. This makes "closer to my own
    version" measurable.
  - **Open / next step**: acceptance on "Lied G" (blocks
    2–6 down) and on Formidable has to be measured on the user's PC (step 0 =
    regenerate `timing_auto.json` on v0.83 and set it against the manual
    `timing.json(.bak)` with `tools/timing_eval`, then adjust the weights).
    The audio/references are not in the zip. The engine is ready to accept
    **per-block vocal onset candidates** (spec priority 3); that source hooks
    the vocal energy analysis (`_refine_with_vocals`/`ritme`) in as extra
    anchors – a next step that needs the audio. `clamp_refinement` stands
    ready to clamp phonetic/energy windows as a refinement within the anchor
    span.
- **B252** – an underscore joins words into one syllable. `split_syllables`
  returns a word with `_` as a single syllable (the marker stays internally);
  `apply_phonetic_timing` does not split such a word phonetically; in the
  render (`video._disp`) the underscore becomes a space, also when measuring
  the text width. Example: `'k_heb` (one syllable, sung "kep") shows as
  "'k heb". Word boundary and comma detection stay on the raw text.
- **B253** – dead translation keys `video_prep_hint` (nl+en) removed (the
  visible input hint on the Karaoke video tab was already gone in v0.82; only
  the keys were left behind). The nl/en key sets stay equal.
- **Maintenance** – the stale Qt test `test_klemtoon_canvas_zet_klemtoon`
  brought in line with the grouped `KlemtoonCanvas` API (B201/B202); it only
  failed when PySide6 is present. A few unused test imports cleaned up
  (pyflakes clean over modules/tools/tests). pytest 349 green.

Included in v0.84 (findings from "Lied B"):
- **B256** – `ritme._rms_envelope` now caches the failure result as well (per
  file path+mtime+size). Root cause: a broken/incompatible numba
  installation on the user's PC (`AttributeError: module 'numba' has no
  attribute 'core'` during librosa's JIT compilation) made every line of a
  song retry the same expensive and broken `librosa.load` call, with a full
  stack trace every time (189× identical messages for one song in today's
  log). Now both the failure result is cached and the error message is
  logged only once per file. This does not solve the underlying numba
  problem itself (that sits in the user's Python environment, not in the
  code) but it does prevent the repetition.
- **B254** – the forced-alignment window came back: the same broken numba
  installation also made the `librosa.resample` step in
  `woorduitlijning._load_mono_16k` fail (needed because WhisperX works at
  16 kHz), with a silent fallback on the audio path - after which WhisperX
  loads the audio itself through an ffmpeg subprocess, which reintroduces
  the flashing window from before B97. A new
  `woorduitlijning._resample_to` tries librosa first and falls back on
  `scipy.signal.resample_poly` on an error (no numba needed, scipy is
  already a core dependency), so the in-process approach - and therefore
  no window - holds up even when librosa/numba is broken.
- **B260 (core fix)** – a mixed block (vocals + separate crowd lines) never
  counted the crowd lines in the line coupling with the lyrics
  (`timing.couple_timing`'s `kar_zang`), not even when the number of karaoke
  lines (crowd included) exactly matched the number of lyrics lines. In "Lied B
  " (5 karaoke lines: 2 crowd + 3 vocal, against 5 lyrics
  lines) the crowd lines ("De Rood Wit-te Zangers...") therefore stayed
  uncoupled and got a short "shout" slot instead of the time of their lyrics
  line ("Met bloed, zweet en tranen") - which also disturbed the original
  track in the waveform editor. `kar_zang` now simply counts crowd along as
  soon as the block sizes match (block crowd and separate-line crowd); if they
  do not match, the old shout behaviour still applies (e.g. an audience "Oeh!"
  with no lyrics equivalent). The final assignment now uses `line.index in
  assign` instead of a separate crowd check, so both places are guaranteed to
  stay in sync.
- **B257 (turned out to be a symptom of B260)** – the mirrored crowd line
  in the waveform editor looked like "a karaoke line in among the original
  lines" because (through B260) it never got coupled and therefore always
  appeared, via `gui.py`'s crowd mirror logic (B193), as an extra, loose
  cell on top of the lyrics line that was already there. With B260 fixed,
  the crowd line simply lands in its proper, coupled place and no separate
  cell appears any more. The `crowd` flag added earlier to the
  `originals` dicts (`gui.py`/`timing.original_view_cells`/
  `timingeditor.py`, red/dotted with a `[crowd]` label) stays useful for
  the remaining, genuinely uncoupled case (a shout with no lyrics
  equivalent).
- **B258** – the Whisper hallucination "ZANG EN MUZIEK" (the function word
  "en" glueing two words together) survived `pipeline._filter_hallucinations`
  because that only rejects a whole segment when *all* of its words are on the
  fixed `cluster.HALLUCINATIONS` list; "zang" was not on it. Function words
  ("en", "de", "het", "een") no longer count in that check. "zang" has been
  added as a signal word, but **only** at segment level in `pipeline.py` (not
  to `cluster.HALLUCINATIONS` itself, which would also affect the sound
  clustering/damping) and **only** when the word occurs nowhere (phonetically,
  via `cluster.similarity`) in the lyrics of this song - a song that really
  sings about "zang" therefore does not lose the word. Generic Whisper
  artefacts like `MUZIEK`/`ondertiteling` always stay hallucinations,
  regardless of the lyrics.
- **B255 (investigated, not a bug)** – "Woorden koppelen" deliberately
  shows transcribed words from the **original** coupled to the
  **lyrics** (both original-based); the karaoke only comes into view at
  "Timing verfijnen" and the waveform editor. The manual now spells this
  out explicitly, so it no longer looks like a bug where the original
  text appears twice.
- **B259 (investigated, not a bug)** – after an ffmpeg update, ffmpeg was
  only found again after a reboot (the Windows PATH is only refreshed in new
  processes/sessions, the same as install.bat already reports after a winget
  install). No code change needed.
- **ffmpeg 9.0 checked** – the parts removed/changed in 9.0 (CELT
  decoding, deprecated NVENC options) touch none of the ffmpeg/ffprobe
  calls in this project (`-acodec pcm_s16le`, `-codec:a libmp3lame`,
  `-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p`, ffprobe
  `-show_format -show_streams -print_format json`) - all of them broad,
  stable options. No code change needed. `install.bat` does not pin a
  version anyway (`winget install -e --id Gyan.FFmpeg` always fetches the
  newest stable), so new installations get 9.0 by themselves; existing
  installations are, as always, not upgraded automatically (deliberately,
  the same policy as for Python).
- pytest 365 green (349 + 16 new B254/B256/B257/B258/B260 tests in
  `tests/test_v084.py`), pyflakes clean over modules/tools/tests.

Included in v0.85 (finishing "Lied B", starting "Lied
P"/Sunday Bloody Sunday):
- **B261** – lines sometimes ran on well past the point where the voice-only
  track was already (almost) silent, right up to just before the next line
  started (easy to spot visually). Root cause: `ritme.active_end` (the B224
  clip-back that should shorten a line to where the vocals really stop)
  tested the silence threshold (`thr_ratio`) against `window.max()` - the
  peak **inside** the window `[start, end]` itself. If that window had
  already been stretched by B194 (following a held note) to just before the
  next line, and there happened to be some residual sound/noise (e.g. a crowd
  shout dying away) just before the end of the window, then that became the
  local "peak" and the threshold (peak × 8%) was met almost everywhere -
  `active_end` found no silence and nothing was clipped back. Verified on
  "Lied B": karaoke line 8 was given 8.43s in
  `timing_auto.json`, while the actual lyrics alignment (word level) covered
  only 5.2s - the remaining ~2s (the breath before the next line) was "eaten
  up". `active_end` now tests the threshold against the peak of the **whole**
  vocal envelope (a stable reference, no matter how far the window itself has
  already been stretched) instead of against its own, possibly dirty window.
- **B262** – every project switch (`gui.py`'s `_switch_instance`, used
  both by "Nieuw project" and by switching over to an existing project)
  now goes back to the first tab ("Audio"). Previously you stayed on
  whatever tab you happened to be on (for example Settings or the
  Manual), while a new or different project in fact starts at the input
  files on the Audio tab. The `QTabWidget` is now kept around as
  `self._tabs`.
- **B263** – Whisper held on to certain words consistently (the same mistake
  at every repeat of the same phrase). `whisper.transcribe()` now passes the
  (deduplicated, unique-words-first) lyrics to faster-whisper as
  `initial_prompt`, only for the original track
  (`songtekst.deduped_prompt_text`, trimmed on a word boundary to
  `INITIAL_PROMPT_MAX_CHARS`). Repetitions (choruses, "Sunday, Bloody Sunday"
  ×4, ...) are removed first so that the available room goes to the full
  unique vocabulary, not to the same words over and over. The prompt counts in
  the whisper cache key: edited lyrics without an audio change transcribe
  again.
- **B264** – new `[bg]...[/bg]` notation (analogous to `[crowd]`:
  block/line/inline) for simultaneous backing vocals - text that sounds *at
  the same time* as the previous line instead of after it, like a backing
  vocal "(Tonight, tonight)" next to the lead "Sunday, Bloody Sunday" in
  "Sunday Bloody Sunday" (project "Lied P"). Works independently in
  both `songtekst.txt` (`songtekst.LyricWord.bg`) and `karaoketekst.txt`
  (`karaoketekst.TextLine.bg`) - one file can use `[bg]` without the other. A
  `[bg]` line/word: does not count in the block/line tally of `couple_timing`
  (just like a non-matching crowd block, B260) and is skipped in the DP word
  alignment (`songtekst.align_lyrics`, just like filler words via
  `skip_filler`) so that it does not steal transcription words from the lead;
  gets the same time slot as its preceding (non-bg) line through the new
  `timing.attach_bg_lines` instead of a place of its own; and is by default
  not shown in "Timing verfijnen" and not rendered
  (`TimedLine.uitgeschakeld=True`, switchable back on per line in the
  editor). The text does count in B263's `initial_prompt` and in B258's
  lyrics-presence check.
- pytest 381 green (365 + 16 new B261/B262/B263/B264 tests in
  `tests/test_v085.py`; 1 of them skips without PySide6), pyflakes clean over
  modules/tools/tests.

Included in v0.86:
- **B265** – running "1 Detecteer woorden" again with a genuinely new
  transcription (other audio/model/language/`initial_prompt`, so no
  cache hit in `pipeline.detect_track`) left the old, manual word
  coupling (step "2 Woorden koppelen", `woordkoppeling.pins`) simply
  standing. Those pins point at transcript **indices** of the old
  transcription; after a real re-detection those positions no longer
  match the new text, but they were applied all the same
  (`songtekst.apply_pins`) - reported as "I coupled the words. There was
  still old data in there." A new
  `pipeline.invalidate_after_fresh_transcript()` now wipes, only on a
  genuinely new transcription (not on a cache hit), the steps
  `woordkoppeling`, `align`, `koppeling` and `timing` (plus the timing
  files) - the same steps as `invalidate_derived`, but without the
  input-file-specific cleanup (Demucs stems, transcript/lyrics override)
  that does not apply here. An unchanged re-detection (cache hit) rightly
  leaves the manual coupling alone; only a genuinely new transcription
  triggers the cleanup.
- pytest 383 green (381 + 2 new B265 tests in `tests/test_v086.py`),
  pyflakes clean over modules/tools/tests.

Included in v0.87 (findings while finishing "Lied P"):
- **B266** – the "Video klaar" prompt accidentally showed both the Dutch and
  the English text: `video_done_prompt` in the NL translation was literally
  `"{title}:\n{target}\n\nMeteen openen? / Open now?"` - the EN text was
  hardcoded into the NL string, not a language-selection bug. Now simply
  `"Meteen openen?"`.
- **B267** – next to "Video openen" there is now also a button **"Map
  openen"** in the video-done dialog. A new `pipeline.open_folder(path)`
  (analogous to the existing `open_file`, same cross-platform approach:
  `os.startfile` on Windows, `open` on macOS, `xdg-open` on Linux) opens the
  *containing* folder if `path` is a file. The dialog itself has been
  replaced: instead of `_ask_yes_no` (Yes/No) there is now `_ask_video_done`
  with three buttons ("Video openen" / "Map openen" / "Sluiten", new
  translation keys `open_video_button`/`open_folder_button`, `close` existed).
- **B268** – at an instrumental gap (≥5s between two lines, B227) both the
  line just sung and the text of the next line were removed entirely
  during the 3-2-1 countdown (`_compose_frame` did an early `return frame`
  after drawing the digit, before the normal line display). Reported
  behaviour: the text disappeared and only came back once the countdown
  was finished, instead of simply scrolling on. The `return` has been
  removed: the countdown is now drawn as an **overlay**, after which the
  normal three-line display (the line just sung grey, the waiting line
  white where there is one) carries on - `active_index` stayed on the last
  started line during the gap anyway, so no other change was needed. The
  digit disappears by itself as soon as `countdown_number` returns `None`
  again.
- pytest 387 green (383 + 4 new B266/B267/B268 tests in
  `tests/test_v087.py`; 1 of them was first added as a separate test in
  `test_video.py` and has been moved here for consistency with the earlier
  B26x versions - no net increase on that point), pyflakes clean over
  modules/tools/tests.

Included in v0.88:
- **B270** – after B268 (the 3-2-1 countdown as an overlay during an
  instrumental gap, instead of hiding the text) the countdown itself
  turned out to still sit at a fixed screen position (`height * 0.18`),
  independent of how much room the text line just above it takes up. A
  line long enough to be split over 2 rows by `_wrap_syllables` can then
  overlap the digit: that happens specifically with the line in **slot
  -1** (the line that stays on screen above the active line during the
  smooth B242 transition, or during a gap) - not with the line that was
  sung just before the gap, because that one sits in slot 0 itself and
  grows downward with its possible second row, away from the digit. A new
  helper `_line_text_height(line, font, width)` computes (with the same
  `_wrap_syllables` logic as `_draw_line`) how many px a line takes up; a
  new `countdown_y(above_slot)` closure in `_compose_frame` uses that to
  place the digit: the fixed base position, or - if the line in
  `above_slot` takes up more room - just below that line, with a hard
  margin (`_MIN_MARGIN_BOVEN_SLOT0 = 12px`) before slot 0's text so the
  digit never ends up inside the next line itself. The intro countdown
  (before the very first line) has no slot -1 and was therefore always
  safe; it uses the same helper with `above_slot=None` (no behaviour
  change, purely for consistency).
- pytest 390 green (387 + 3 new B270 tests in `tests/test_v088.py`),
  pyflakes clean across modules/tools/tests.

Included in v0.89:
- **B271** – a video render with a non-standard music/text combination
  (via the B226 render dialog, e.g. `audio_source="vocals"` +
  `text_source="origineel"` for voice-only music with the original lyrics)
  got the same filename (`<titel>.mp4`) as the default render (karaoke
  music + karaoke lyrics) and therefore silently overwrote it on every new
  variant. A new `pipeline.render_filename_suffix(audio_source,
  text_source)` now returns an empty suffix for the default combination
  (no change to existing behaviour or filenames), and otherwise
  ``_<music>_<text>`` with 3-letter codes
  (`_AUDIO_SUFFIX_CODES`/`_TEXT_SUFFIX_CODES`: kar/ori/voc/dem) - music
  first, text second, as requested. Example: `titel_voc_ori.mp4`. An
  unknown source (should not be reachable from the GUI) falls back to the
  first 3 letters of the source code itself instead of crashing.
- pytest 394 green (390 + 4 new B271 tests in `tests/test_v089.py`),
  pyflakes clean across modules/tools/tests.

Included in v0.90:
- **B272** – follow-up to B270: during a long instrumental gap the
  "frozen" layout simply left the line in slot -1 (the oldest visible
  one, already out of the "busy now" focus) standing next to the waiting
  line(s), with a large empty gap in between into which the 3-2-1
  countdown then had to fit (visible in "Lied P": "Zondag,
  Lied P." at the top, "Ja, kom op!" (sung) after it, then an
  empty gap, then the next lines far below). On explicit request the line
  in slot -1 now disappears entirely during the gap; the remaining 3
  lines (just sung in slot 0 - next up in slot 1 - after that in slot 2)
  and the countdown between them spread evenly over 4 positions within
  the same vertical band (previously the space between slot 0 and slot
  2). Result: "Ja, kom op!" (grey) - countdown - "Het decor..." - "Want
  de werkdruk...", without an empty gap. The B270 margin logic (the
  countdown shifts along if the line above it runs over 2 rows, with a
  hard margin before the next line) stays intact within this more compact
  scheme. The crowd line below slot 0 (normally a fixed `height*0.45`)
  has been made gap-aware as well, because slot 0's y now changes during
  a gap.
- **B273** – the version number of KaraokeTool is now in the metadata of
  every rendered video (ffmpeg `-metadata comment="KaraokeTool vX.Y.Z"`),
  so that during later testing you can work out exactly which version
  produced a given video file (`ffprobe -show_format` shows the tag).
- pytest 397 green (394 + 3 new B272/B273 tests in `tests/test_v090.py`;
  the 2 B270 tests in `tests/test_v088.py` that checked the old slot -1
  visibility have been rewritten for the new slot 0 margin situation),
  pyflakes clean across modules/tools/tests.

Included in v0.91:
- **B274** – in "Lied I" (a parody of "500 Miles") number words
  in the lyrics ("500", "1000") never linked to Whisper's transcription, not
  even when Whisper wrote the number out in full ("five hundred"). Root
  cause: `phonetic_key` keeps only letters, so a pure-digit word got an EMPTY
  key, and `similarity` always returns 0.0 for an empty key - however Whisper
  wrote the number. A new `cluster.number_word_forms(n)` turns a non-negative
  integer (0 through 999.999.999 - "10.000.000" does turn up in lyrics now
  and then, "miljard"/"billion" and up do not) into the Dutch AND the English
  written-out form, as two SEPARATE strings (deliberately not merged into one
  key - that turned out to pollute and lengthen the phonetic match and
  actually lowered the similarity). `cluster.number_key_best_match(text,
  other_key)` tries both language forms of a number word against the
  comparison key and picks the best; `songtekst._align_core` uses this
  through local `_lyric_key_for`/`_lyric_sim`/`_lyric_pair_sim` helpers
  instead of the fixed `lyric_keys[i]`, both when building the DP table and
  in the backtrack (m11/m21/m12). No regression for ordinary (non-number)
  lyric words.
- **B275** – a reported GUI problem: editing the karaoke title and immediately
  clicking "Detecteer woorden" sometimes did not apply the change (it did if you
  clicked another field first). Root cause: the title fields save via
  `editingFinished` (which fires on Enter or on focus loss), but a mouse click
  on a `QPushButton` does not always reliably take focus away from a `QLineEdit`
  before the click itself is handled (platform- and style-dependent, on Windows
  in particular) - so the step buttons sometimes still read the `self._context`
  from before the change. A new `_commit_pending_field()` explicitly forces
  `clearFocus()` on an active input field, called as the first line in all step
  handlers (Detecteren/Koppelen/Analyseren/Karaokevideo/Timing maken/Klemtoon
  bewerken/Timing bewerken/Video maken) - that way `editingFinished` is
  guaranteed to fire before the button starts its action, whatever the focus
  behaviour.
- **B276** – filler words ("oh", whole "da-da-da"/"la-la-la" blocks) were
  always kept out of the main alignment via `align_lyrics(...,
  skip_filler=True)`, even when Whisper had transcribed them perfectly well
  (measured concretely in "Lied A": "oh" sat with confidence 0.92
  exactly between "veranderd" and "het" in the transcription, but showed
  "(niet gekoppeld)"). After the DP alignment on the "real" words,
  `align_lyrics` now makes one match attempt per skipped filler word within
  the transcript window between the two nearest neighbours that did get linked
  (`similarity`/`phonetic_key`, threshold `_FILLER_MATCH_FLOOR = 0.6`); only
  without a good match does the word stay unlinked (the old energy-timing
  fallback). Every word of a filler block is matched separately (with a
  `claimed` set so that consecutive "da"s do not grab the same transcript
  word) - a block without a real match in the window (say Whisper heard
  nothing meaningful there) simply stays skipped, no regression. A new
  `pipeline._filler_priority_lines` compares songtekst.txt/karaoketekst.txt
  line by line (they share the same line structure); if the karaoke line does
  contain real (non-filler) content while the lyrics line has a filler word, a
  more lenient threshold applies (`_FILLER_MATCH_FLOOR_PRIORITY = 0.5`),
  because the timing there directly determines when the karaoke content
  appears on screen.
- **B277 (first version - see "Included in v0.92" for the revision)** – lines
  often stayed "on" too long: the user traced this (partly) to
  `held_note_end`/`active_end`, which tested the vocal energy at a SINGLE
  RMS sample point (`window >= threshold`). Measured concretely
  (`active_end` on a line in "Lied A": raising `thr_ratio` from
  0.08 to 0.20 moved the cut-off point by only 0.02s), a stubborn low
  noise floor/reverb tail on individual sample points keeps hanging just
  above even a raised threshold, while the AVERAGE there is already
  (nearly) zero - exactly as the user described it ("the average waveform
  over 0.1 seconds is nearly 0"). A new shared
  `ritme._last_active_time(rms, times, mask, drempel)` tested a ~0.1s
  (`_ACTIVE_WINDOW_S`) sliding average instead of a single sample point;
  `held_note_end` (stretching, with floor/ceil) and `active_end` (clipping
  back, song-wide peak - B261 stays intact) were thin wrappers around this
  helper. Investigated separately and NOT in scope: the backing-choir case
  (energy stays 16-80% of the peak, so a genuine second voice, not noise
  or residual signal) - that requires real source separation and stays a
  manual correction, as the user confirmed.
- **B278** – the Karaokevideo tab showed no progress at all during
  "Video maken" (first render) beyond the subtle B229 yellow-button
  styling; the actual ffmpeg encoding progress went only to the bar on
  the Audio tab (`self._progress`/`self._status`, built in
  `_build_progress_group`, which hangs off `audio_layout` only).
  `_build_video_tab` now has its own `self._video_progress`
  (`QProgressBar`) + `self._video_status` (`QLabel`) under the button
  row; `_on_progress`/`_on_message`/`_set_busy` and the "video done"
  handling in `_do_render_video` now write there as well, so both bars
  always stay in sync without touching the background-task wiring
  itself.
- **B279** – separately from B277 (line length): the syllable alignment
  within a line could go wrong too. Root cause in
  `timing._spans_over_words`: all karaoke syllables were resampled in one
  flat pass, purely on relative POSITION, over the total original-word
  timeline. Shown concretely with "Ik zeg miauw." (9 syllables) against
  the original "hoe is het nou?" (4 words, the last one stretched to 3.42s
  by B194/B277): the syllable "auw." (the end of "miauw", positionally by
  chance inside the 4th word's window) inherited 3.42s, while "Ik" (1st
  syllable, rhythmically belonging with the short "hoe") got only 0.28s -
  a completely wrong ratio. A new two-stage ``_spans_over_words``: first
  the KARAOKE words (``_karaoke_word_groups``, which groups ``pieces`` on
  the leading-space boundary of ``split_line``) are projected
  proportionally onto the original words (the same even distribution used
  elsewhere in the codebase for lines and blocks), and only then are the
  syllables spread evenly within each matched word pair. Result on the
  same example: "miauw" (the whole word, linked to the stretched "nou?")
  shares its 3.42s over its 2 syllables (1.77s each), and "Ik" gets 0.51s
  (in line with the shorter first 3 original words) instead of 0.28s.
- pytest 413 green (397 + 16 new B274-B279 tests in `tests/test_v091.py`),
  pyflakes clean across modules/tools/tests.

Included in v0.92:
- **B277 revision** – the user explicitly asked to test B277 against
  real project data: compare "Lied_A"'s `timing.json` (his
  manually corrected version) with `timing_auto.json` (the same auto
  run) to see whether v0.91's approach gets closer. On that particular
  project both files turned out to be identical (no separate manual
  correction available as a reference) - after reloading from the
  shared folder this proved to be right, and the user said the "2
  previous projects" could be used as well (`Lied_B` and
  `Lied_P`, with the warning that the latter has the known
  backing-choir problem in places and is therefore less
  representative). On `Lied_B` (a clean test case after
  all, 47 lines, 31 of them with a difference >0.3s between auto and
  manual) v0.91's sliding-average approach turned out to help hardly at
  all (it improved only 2 of the 31 cases) - the real root cause was
  that a line's analysis window often runs on until the start of the
  next line, and "the last sample point above threshold" then picks up
  the BUILD-UP of that next line, even with a long silent gap in
  between. `ritme._last_active_time` has been rebuilt around a
  gap-based approach: scan from right to left for the first contiguous
  silent gap (`_SUSTAINED_SILENCE_S = 0.3`) between two above-threshold
  moments and return the last genuinely active moment before it, on the
  RAW RMS sample points (no more smoothing) - a combination of
  smoothing + gap detection was tested too but performed worse (a short
  surge of ~0.07-0.08 fraction could end up just above the threshold
  after averaging, smearing a genuinely long silent gap shut; on one
  line that gave a 4.3s deviation instead of 0.2s). Result on
  `Lied_B`: mean deviation 1.63s -> 0.28s, median 1.47s
  -> 0.25s, max 3.22s -> 1.43s. `held_note_end`/`active_end` remain
  thin wrappers around the rebuilt helper; their public signature and
  B261 song-wide-peak behaviour are unchanged. `tests/test_v091.py`'s
  B277 tests have been updated to the new gap behaviour (from 16 to 17
  tests: an extra test covers the "no long gap found -> old behaviour"
  path).
- **B277 follow-up check** – after the gap approach was delivered the
  user explicitly asked about further improvements. Two variants were
  tested empirically on all three projects (Lied_A,
  Lied_B, Lied_P): (1) instead of taking the
  FIRST silent gap (≥0.3s) from the right, pick the LONGEST gap in the
  window; (2) raise the sustain threshold to 0.4/0.5/0.6s. Neither
  improved the results across the board - "longest gap" did clearly worse
  on Lied_P (lines 0 and 40 overshot into a far too early
  cut-off, 5.2s and 6.9s off instead of 0.6s/2.1s), and a higher sustain
  threshold improved Lied_P slightly but made Lied_A
  worse. The current setting (first gap, 0.3s) stands; no change in
  `ritme.py`.
- **Line timing of Lied_A updated** – at the user's request
  `output/Lied_A/settings/timing.json` has been regenerated
  with the v0.92 insights (the existing file first set aside as
  `timing.json.bak`). Because there was no `project.json`/`cache/`
  context available to run the full pipeline, this was done surgically:
  `held_note_end`/`active_end` applied per line to the existing
  start/end times (audio: `vocal_demucs.mp3`), and wherever the end
  changed the syllables were redistributed via
  `timing._spans_over_words` with the original Whisper words from
  `origineel/woorden.csv` (23 segments, each overlapping 1-2 of the 46
  karaoke lines on a time basis - established by time overlap, not by
  1:1 index matching). That brought an edge case to light: on line 17
  ("Word jij een luiaard in een boom,") `active_end` found an incidental
  short breath-pause gap (0.348s, just over the 0.3s threshold) in the
  middle of the line, while the singing simply ran on afterwards until
  the real silent gap 1.7s further along - without a correction that
  would have set the last syllables to zero duration. Solved with a
  targeted guard in the regeneration script (not in `ritme.py` itself,
  see above): an `active_end` shortening is ignored if the cut-off point
  found lies more than 0.5s before the end of the last overlapping
  original word. Result: 6 of the 46 lines stretched via `held_note_end`
  (held notes such as "miauw.", "pinguïn,"), line 17 rightly left
  unchanged; the new end times land remarkably close to the original
  `timing_auto.json` values.
- **Button label fix** – the render button on the Karaokevideo tab was
  called "4. Video maken (eerste render)", even though the same button and
  function (`_do_render_video` → `pipeline.run_video` → always
  `timing.json`, never `timing_auto.json`) serves just as well for a
  re-render after a manual timing correction. Renamed to "4. Video maken"
  (NL and EN in `modules/taal.py`) so that the label no longer suggests a
  separate first-time-only action.
- The B277 tests and the new button-label test have been moved into a
  `tests/test_v092.py` of their own (following the existing convention of
  one test file per version) instead of growing further in `test_v091.py`:
  the 3 B277 tests have been moved out of it (16 → 13 in `test_v091.py`) and
  placed together with 1 new button-label test in `test_v092.py` (4 tests).
- **B280** – in the "Lied J" project (a parody of Waylon Jennings -
  Good Ol' Boys) the user added a Dukes-of-Hazzard dixie horn to the
  original, merged in with Clipchamp; that program exports as `.m4a`.
  `filesystem.SUPPORTED_EXTENSIONS` only knew `.wav`/`.mp3`, while
  ffmpeg/ffprobe (which already do all the audio analysis and conversion)
  handle any container format just as generically - so this was purely a
  whitelist extension, no new processing logic. Looked at more broadly than
  m4a alone, on request: `.flac`/`.ogg`/`.aac` have been added as well (all
  four supported by ffmpeg; common with lossless rips, Audacity exports and
  bare AAC streams). Changed: `SUPPORTED_EXTENSIONS` (6 extensions now,
  `.wav` stays first - no conversion needed when several variants exist),
  the `find_audio_file` docstring, the error message in `prepare_track`
  (which now lists all supported extensions instead of a hardcoded ".wav or
  .mp3"), the file dialog filter in `gui._choose_file`, the cleanup loop in
  `_generate_karaoke_from_original` (which only walked `.mp3`/`.wav`, now
  `SUPPORTED_EXTENSIONS`), and `export.export_result`: a source in one of
  the four new formats exports (just like mp3) to `karaoke_edit.mp3` -
  there is no separate "m4a/flac/ogg/aac output format"; the OUTPUT stays
  deliberately limited to mp3/wav (an explicit user wish, not mirroring the
  input). The existing test `test_export_unknown_format` used `.flac` as
  its example of an unsupported format; that has been updated to `.xyz` now
  that `.flac` is a valid input format.
- pytest 418 green (414 + 1 export test + 3 new B280 tests in
  `test_v092.py`), pyflakes clean across modules/tools/tests.

Included in v0.93:
- **Interjection timing (Lied J "Whoo!") - investigated, eventually dropped**
  – the user asked why `ritme._last_active_time` (B277) looks for a
  silent gap at all in the case of an interjection or shout, when it
  was meant for getting line lengths right in general, not specifically
  for shouts. He then asked for an empirical search for whatever brings
  `timing_auto.json` closest to the manually corrected `timing.json`.
  In total 9 signals were tested over two sessions (a
  gap-scan-direction fix: longest instead of first gap from the right;
  a higher and a lower sustain threshold; a Whisper/lyrics-based check
  of whether the next transcribed word after a line is a real lyric
  word or a stray sound; and the earlier B277 follow-up variants) - not
  one of them improved the general picture without causing a regression
  elsewhere (a fix for "yeah," for instance broke the legitimate short
  last-syllable case "t'rug" in line 6, because the two are
  acoustically indistinguishable: short and isolated between two
  silences). The user then steered explicitly: "those are exceptions, I
  care more about the general case now". Conclusion: within acceptable
  regression risk there is no robust general solution for this
  particular acoustic edge case; this item has been dropped from the
  build scope with no change in `ritme.py`.
- **B281** – the actual cause of the "Whoo!" problem turned out not to
  sit in `ritme.py` but in `songtekst.py`'s coupling DP: a multiple link
  (m21/m12, two lyric words against one transcription word or the other
  way round) was allowed on the basis of the COMBINED similarity, which
  let "allow" (from "Than the law will allow") link to "land Whoo!" in
  the DP backtrack (combination score 0.333) - the audience noise
  "Whoo!" was thereby pulled into the duration of "allow". A first
  attempt with a fixed combination threshold (`_MIN_MULTI_MATCH_SIM`,
  tried from 0.5 down to 0.34) turned out to be unable to separate the
  bug from the module's own "Kedeng Kedeng" ↔ "de trein" flagship case:
  that scores exactly the same combination-wise (0.333), so every
  threshold ≥0.34 blocked the legitimate link too and shifted the DP
  backtrack (it broke `test_align_matches_gedengedeng_and_de_trein` and
  `test_extra_intervals_finds_new_and_estimates_gap`). Fix: instead of
  the combined score, test against the BEST of the two SEPARATE
  half-similarities (`_m21_best_half_sim`/`_m12_best_half_sim`,
  threshold `_MIN_MULTI_HALF_SIM = 0.3`). That does separate the cases:
  with Kedeng, "Kedeng"↔"de" AND "Kedeng"↔"trein" both score around
  0.333 (the BEST clears the threshold), with "allow", "allow"↔"land"
  scores 0.0 and "allow"↔"Whoo!" 0.25 (the BEST does not clear it). Also
  checked that this is not too strict: "is"↔"ik zo" has one half at 0.0
  but the OTHER at 0.5, and "best of the two" (not "both required")
  rightly lets that legitimate link through. All 5 existing tests in
  `test_lyrics.py` plus 3 new tests in `test_v092.py` (Whoo! case
  blocked, Kedeng case still works, `_MIN_MULTI_HALF_SIM` does not touch
  m11 links) are green.
- **B282: "Terug uit origineel"** – on request, a counterpart to damping:
  in the damping editor you can now place green blocks next to the red
  damping blocks, which lay the corresponding piece of the ORIGINAL over
  the karaoke (instead of attenuating it), for sound that Demucs (or a
  manual edit) removed but that does belong there (a shout, a sound effect)
  - "Karaoke aanpassen" (step 4) can only damp, never put back something
  that is no longer there. New: `karaoke.RestoreInterval` +
  `karaoke.apply_restore()` (which replaces, rather than mixes, the karaoke
  samples within the window with resampled original samples, with the same
  in/out crossfade ramps as damping, applied AFTER the damping so that
  restored sound is not damped itself); `align.project_time_reverse` (the
  reverse direction of `project_time`: karaoke time → original time, needed
  because the user marks the window on the KARAOKE waveform but the
  matching original fragment has to be fetched); `ffmpeg.resample_to_match`
  (explicit target sample rate/channels, instead of `convert_to_wav`'s
  "stays the same as the source" - needed because original and karaoke can
  each have their own sample rate when supplied separately). Persistence
  via a new, separate store step `restore_fragmenten` (alongside
  `fragment_uitsluitingen`/the cluster damping) so that a later step-4
  rerun (a new cluster selection) does not wipe out the manual restore
  choices - `run_karaoke` and `apply_manual_damping` both reapply them, and
  `reset_damping` clears them together with the cached resample. Damping
  editor UI: `DampingCanvas` blocks have been extended from `[start, end]`
  to `[start, end, kind, label]` (kind = "demping" or "herstel"); a new
  "Terug uit origineel" button adds a green block; `_save()` splits the
  blocks by kind and calls the save callback with both the damping and the
  restore spans. The button that opens the editor used to require step 4 to
  have run already (`context.store.get_step("karaoke")`) - that has been
  relaxed to step 1 only (`pipeline.stored_wav`), so the restore function
  is reachable without a prior cluster selection. Validated with a targeted
  test (`test_apply_manual_damping_terug_uit_origineel`): the restored
  audio demonstrably comes from the original (RMS > 0.3 inside the window
  vs. ~0 outside it), and the choice survives a subsequent damping-only
  call.
- **B283: sound-cluster group / damped-fragments group** – on request the
  "Klankclusters" group has to disappear completely (empty or not, not merely
  be emptied) as soon as "Gedempte fragmenten" is active: whatever was ticked
  there already shows up under "Gedempte fragmenten". `_build_cluster_group`
  now keeps the group as `self._cluster_group`; hidden in
  `_refresh_fragments` (as soon as fragments are shown) and on a full project
  reset, visible again after a new step-3 analysis (`_show_analyse_results`)
  and on `_reset_damping`. On top of that, "Gedempte fragmenten" now has the
  flexible grow/shrink role when the window is resized, which used to sit
  with "Klankclusters" (`stretch=1`/`stretch=0` swapped on the audio layout,
  `scroll.setFixedHeight(140)` → `setMinimumHeight`).
- pytest 422 green (418 + 1 new restore test in `test_pipeline.py` + 3 new
  B281 tests in `test_v092.py`), pyflakes clean across modules/tools/tests.
  The only remaining failure is `test_language_for_uses_songtekst`
  (language-detection library behaviour, independent of every change in
  this version - present before and after all the B281/B282/B283 work).
- **B284: B283 correction, two bugs** – after installing on the local
  machine, Klankclusters turned out to be hidden already on simply OPENING
  or starting a project instead of only after step 4:
  `_reset_project_view` (called on every project switch) hid the group
  explicitly, whereas before it was always visible until fragments became
  active - a wrong assumption while building B283 ("a consistently empty
  state" turned out not to be consistent with the existing behaviour). A
  first isolated fix (just reverting that one line to `setVisible(True)`)
  solved that, but the user rightly pointed at a deeper problem:
  Klankclusters and Gedempte fragmenten sat as two SEPARATE widgets
  stacked in the audio layout, each with its own minimum height (64 and
  140) and stretch - switching one on or off let the other take the freed
  space, giving a window that jumps on every switch. Alternatives
  suggested: either guarantee the same size for both, or (as before B283)
  not have two separate groups at all. Chosen: both groups stay
  functionally separate (their own buttons and logic per phase, no mixing
  of cluster selection and fragment ticking), but they now sit in the same
  place in a single `QStackedWidget` (`self._cluster_fragment_stack`,
  added where the two separate `addWidget` lines used to be) with a shared
  minimum-height constant `_CLUSTER_FRAGMENT_MIN_H = 140` (both
  `scroll.setMinimumHeight(...)` calls now refer to it). All the separate
  `self._fragment_group.setVisible(...)`/`self._cluster_group.setVisible(...)`
  calls (4 places: `_reset_project_view`, `_refresh_fragments`,
  `_reset_damping`, `_show_analyse_results`) have been replaced by two new
  helpers `_show_cluster_group()`/`_show_fragment_group()` that call
  `self._cluster_fragment_stack.setCurrentWidget(...)` - never two
  `setVisible` calls set independently again, so no more risk of them
  drifting out of sync. Validated (offscreen,
  `QT_QPA_PLATFORM=offscreen`): a real `MainWindow` built with a temporary
  project, stack index at startup is 0 (Klankclusters), and the
  `sizeHint()` height of both groups is identical (209px) after switching
  via `_show_fragment_group()`/`_show_cluster_group()`. pytest stays 422
  green.

Included in v0.94:
- **Background** – on a real alignment ("Lied_S") the user ran into a
  mess at the end of the song. Investigation pointed to a 27-second
  transcription gap (169.44s-196.62s: "Espagna por favor" plus the full
  4x repeated outro "Lalaala lalalalalaa e viva Espagna") after which
  Whisper hallucinated "SPANNENDE MUZIEK" (already filtered out,
  "muziek" is on the fixed list) followed by "Heerlijke Heer, Heerlijke
  Heer." - neither word was on any hallucination list, so that last
  segment stayed in place as an anchor and pulled the alignment around
  it out of true.
- **Dead ends, investigated and honestly reported back before anything was
  built** – (1) the suspicion that "la" is not always taken along as a
  filler word would be the core of this particular case turned out on
  measurement not to hold: Lied_S's exact spelling ("Lalaala",
  "lalalalalaa") has an odd character length and therefore already
  fails `is_filler_word`'s exact-multiple check - so these words were
  already going through the normal DP alignment, not through the filler
  mechanism. And "Heerlijke"/"Heer" score at most 0.33-0.40 phonetic
  similarity with the full lyrics, with or without those words in the
  comparison set - well below any reasonable threshold. (2) "Ole!"
  (lines 1, 3 and 60) turned out NOT to be explained by the filler
  mechanism (it is not even in `_VOCALISE`), but to have exactly the
  same cause as the outro gap: Whisper transcribes "Ole!" nowhere in
  the entire song (verified with a grep over transcript.txt/woorden.csv
  - zero hits). For this kind of "there simply is no Whisper
  transcription of this word" case there is no reliable
  automatic-detection solution without unacceptable regression risk -
  hence the editor-visible marking (B287) as a safety net instead of a
  fifth detection heuristic. (3) Also looked into on the side
  (unrelated to this bug, a pure knowledge question from the user): is
  there an acoustic signal or MIR technique (pitch stability, spectral
  flatness, chroma width, HNR, singer diarisation, multi-F0 estimation,
  MedleyVox, CREPE/RMVPE) for telling a backing choir or several
  simultaneous singers apart from the lead vocal, as an alternative to
  the manual `[bg]` marking? None of these techniques turned out to be
  robust or production-ready enough; the user agreed to let this rest
  ("what we have works well enough in that area for now") - no change
  as a result.
- **B285: song-wide hallucination check** – `pipeline._filter_hallucinations`
  so far had only a fixed-word-list check (B141/B258): a segment is a
  hallucination if all of its content words are on
  `cluster.HALLUCINATIONS`, or (for the standalone signal word "zang")
  appear nowhere in the lyrics. "Heerlijke"/"Heer" are on no list at all,
  so they slipped through. A new, broader check (only as a supplement
  AFTER the existing fixed-list check, and only if that found nothing): a
  segment with at least `_SEGMENT_HALLUCINATION_MIN_KERNWOORDEN` (2)
  content words is dropped as well if (a) NONE of the content words
  matches the lyrics of this song even reasonably
  (`_SEGMENT_HALLUCINATION_MATCH_FLOOR = 0.65`) in phonetic terms - per
  content word the BEST match over the whole lyrics counts, not the
  average, because one word that does match somewhere is enough to spare
  the whole segment (the same principle as the existing "zang" check) -
  AND (b) Whisper's own LOWEST word confidence in the segment stays below
  `_SEGMENT_HALLUCINATION_CONF_CEILING` (0.6). That has to be explicitly
  the LOWEST, not the average: the actual "Heerlijke Heer" segment
  averages 0.63 (just above an average threshold of 0.6) but its lowest
  individual word confidence is 0.34 - a hallucination in which Whisper's
  language model "fills in" part of the sentence with high certainty
  despite weak audio gives exactly that kind of uneven pattern, and an
  average would have masked it. Without lyrics (`lyrics` empty/`None`)
  this broader check is skipped entirely - there is then nothing to weigh
  "matches nothing anywhere" against. Testing against the phonetic-key
  comparison turned up a catch: "heer" loses both its 'h' and its 'r' in
  phonetisation (`cluster._DROPPED`) and then has only one character left
  ("e") - by chance identical to the key of the lyric word "E" (from "E
  viva Espagna"), which gave a false match of 1.0. Solved with
  `_MIN_BROAD_MATCH_KEY_LEN = 2`: a phonetic key shorter than 2 characters
  does not count in the broader check. Kept backwards compatible via a new
  optional `dropped_out` argument (instead of changing the return value) -
  all 6 existing direct calls in `test_pipeline.py`/`test_v084.py` keep
  working unchanged. Validated against the 10 real projects currently on
  the installation (Lied_S, Lied_N, Lied_P,
  Lied_B, Lied_T, Lied_J,
  Lied_O, Lied_I, Lied_G,
  Lied_A): besides the "Heerlijke Heer" hallucination (Lied_S)
  the broader check also caught three previously unnoticed hallucinations
  and artefacts in other projects - "TV Gelderland 2021" (Lied_N,
  right at the end, presumably a broadcast watermark on the source
  recording), "Alright, stop!" (Lied_P) and "Thank you."
  (Lied_T, one of the best-known Whisper hallucination
  phrases) - every one of them an English phrase without a lyrics match
  and with a low lowest-word confidence. None of the 10 projects lost a
  segment that was rightly kept before B285.
- **B286: repeated filler sounds as deliberate lyrics** – the user
  rightly noted that the reverse holds as well: if "la la la" is
  literally in the lyrics, it is not incidental filler to be skipped.
  New: `songtekst.is_repeated_filler_line` (true if every word on a line
  is a filler sound AND the line has at least 3 words) and
  `repeated_filler_lines` (the corresponding line numbers).
  `align_lyrics` now excludes such lines from the normal filler skipping
  (`skip_filler`) - a word only counts as a "filler word to skip" if it
  is both a filler sound AND not on a deliberately repeated line. This is
  (as shown above) not the cause of the Lied_S bug itself, but it is a
  correct, standalone improvement for songs where this pattern does
  occur.
- **B287: three status markers in the coupling editor** – as a safety net
  for all the "word cannot be found" cases (including "Ole!", B285's
  filtered hallucinations, and ordinary filler words) every lyric word in
  `pipeline.word_coupling_view` now gets a `status`: "gekoppeld" (has a
  link, or is bg/manually pinned - appearance unchanged),
  "vulwoord_overgeslagen" (a filler sound that could not be recovered
  through the B276 anchor window), "hallucinatie_gefilterd" (its estimated
  position - the anchor window between the nearest linked neighbours, the
  same approach as B276 - overlaps a segment filtered out by B285) or
  "geen_match" (all remaining cases, such as "Ole!"). Backing-vocal words
  (`bg`) deliberately get no marker: those are handled separately already,
  even when the user left a word unlinked on purpose. Order of precedence
  when several causes are possible: hallucination overlap first (the most
  concretely demonstrable), then filler word, otherwise "geen_match".
  `modules/koppeleditor.py` now draws unlinked lyric words with a dotted
  border in a colour of their own plus a short, deliberately untranslated
  label - orange "[vul]", red "[?]", purple "[hal]" - modelled on the
  existing "[crowd]" pattern in `timingeditor.py`. A manual selection
  (blue border) always takes precedence over the status colour, so it
  stays clear what you clicked on.
- pytest 440 green (422 + 18 new B285/B286/B287 tests in `test_v094.py`),
  pyflakes clean across modules/tools/tests (the only remaining pyflakes
  warning, `np` as a forward-ref type hint in
  `_prepared_restore_intervals`, already existed before v0.94 and falls
  outside this release). The only remaining test failure is
  `test_language_for_uses_songtekst` (language-detection library
  behaviour, independent of every change in this version).

Included in v0.95:
- **Background and approach** – the user asked for the whole codebase to
  be gone through for logic, dead code and translatability (and eventually
  English names). That review was done as four parallel sub-investigations
  (dead code, translatability, Dutch identifiers, correctness). Important
  for trusting what follows: every bug reported here was first reproduced
  with a concrete failure scenario before anything was changed, and the
  findings that did not survive that were dropped instead of being fixed
  "just in case". None of these bugs had been reported by the user; they
  were sitting there quietly.
- **B288: the filler-word priority threshold tested the wrong number** – `_filler_priority_lines`
  (B276) returns LINE NUMBERS from the karaoke text, but
  `songtekst.align_lyrics` did `if i in priority` with `i` = the index in
  the word list. Because every song has many more words than lines, the
  more lenient threshold practically never kicked in where it was meant
  to, and it did kick in for the word whose index happened to equal a
  priority line number. Now `lyrics[i].line in priority`. The docstring of
  `_filler_priority_lines` also promised "compares songtekst.txt and
  karaoketekst.txt line by line", while the function never opens
  songtekst.txt (nor does it need to: the lyrics side is tested in
  `align_lyrics`) - corrected as well.
- **B289: `lang="nl"` in a boolean field** – `timing.Syllable.lang` means
  "long held note" and drives the underlining in `video.py`;
  `timedline_from_text` filled the string `"nl"` in there, a mix-up with
  the language parameter elsewhere in the same module. A non-empty string
  is truthy, so every syllable counted as a held note as soon as the video
  was rendered from the original lyrics (and in the stress editor).
  Checked in the real `timing.json` files of all 10 projects on the
  installation: they hold `False` everywhere, so this bug lived only in
  the render and the editor and not in stored data - a code fix was
  enough, no migration.
- **B290: crash with more vocal windows than words, hidden by a safety net**
  – `timing.distribute_over_windows` clamps the word boundaries per
  window, but `max(vorige + 1, ...)` could run past the last word as
  soon as a line had `aantal_woorden + 2` or more windows;
  `woord_spans[wi]` then raised an IndexError. Measured exhaustively: 2
  words/4 windows, 3/5, 4/6, and so on. The real problem sat a layer
  higher: the call in `pipeline._apply_energy_word_timing` sits inside
  one broad `except Exception` around the whole step, so one problem
  line silently dropped the energy word timing (B234) for the complete
  song, with only a line in the log. Two fixes: surplus windows are now
  merged beforehand at the SMALLEST gap between them (this keeps exactly
  the clear pauses that B234 is about, and keeps the line's outer span
  intact), and the call is caught per line so that only that one line
  loses its refinement. Verified over 96 combinations (1-8 words x 1-12
  windows) for crashes AND for the invariants: no syllable disappears,
  times increase and do not overlap.
- **B291: `blok` and `uitgeschakeld` were lost on a text correction** – `pipeline.sync_timing_with_text_change`
  built the new `TimedLine` WITH `crowd_section` and `kwaliteit` but
  WITHOUT `blok` and `uitgeschakeld`, which therefore fell back to 0 and
  False. If you corrected a typo in a line you had disabled earlier
  (B180), that line was simply back in the video afterwards, and the block
  layout of the timing editor (B127) collapsed to block 0. The docstring
  explicitly promises that only text and syllables change; that is true
  again now.
- **B292: loose ends from v0.93/v0.94 (my own work)** – the `floor`
  parameter that was added to `_word_in_lyrics` for B285 was never called
  with anything but the default, while the docstring suggested that the
  broad song-wide check used it; that check goes through
  `_best_lyrics_match` with a threshold of its own. Anyone going by that
  docstring to adjust B285 would have changed the wrong thing. Parameter
  gone, docstring set straight. Furthermore
  `karaoke.restore_intervals_to_dicts` and `_from_dicts` (B282) were never
  called AND described a different format from what is actually stored
  (`restore_fragmenten` holds triples, not dicts) - removed.
- **B293: dead code** – gone: `fonetiek._lang_dir_name`,
  `pipeline.TrackProgressCallback`, `pipeline.detect_words` (which did
  exactly what `detect_tracks(parallel=False)` does; two entrances to the
  same step 1 means a change to the one silently passes the other by) and
  the dead `fallback_offset` parameter in `align._smooth_regions` (a
  leftover from the median fallback that was replaced by trend detection
  in B249). `gui.py` had a literally identical private copy of
  `cluster._format_time`; that is now one public `cluster.format_time`.
  The docstring of `fonetiek.generate_language` promised "built-in hints"
  that do not exist - made honest instead of dropping the parameter,
  because that is logically where they belong. With the numpy annotation
  behind `TYPE_CHECKING`, **pyflakes is now completely clean** across
  modules/tools/tests/KaraokeTool.py; that one warning had been there
  before this round.
- **B294: functions used only by tests - deliberately NOT removed** – the
  review found twelve of them. Only `detect_words` was dropped, because
  there is a demonstrably equivalent production replacement for it. The rest
  stays, on purpose: `timing.best_effort_skeleton` (plus `_cascade_spans`,
  `_build_line`, `line_assignments`) is a substantial quality cascade
  (syllable/word/line) that feeds the `kwaliteit` field used all over
  timing.json - that is a branch that came loose rather than dead code, and
  throwing it away on a hunch is worse than leaving it in.
  `timing_rules.clamp_refinement` and the constants
  `KIND_DURATION`/`KIND_REFINE` belong to the prepared (and in this document
  described) per-block vocal-onset work. `config.TrackSettings` stays
  because `tracks` is in the real `config.json`: removing it would let that
  key quietly disappear. The other candidates (`audio.duration_seconds`,
  `taal.current_language`, `ritme.count_repetitions`,
  `pipeline.export_demucs_karaoke`, `cluster.format_overview`,
  `modellen.info_text`) are small, correct and tested functions; each of
  them deserves a decision when it is used, not a sweep.
- **B295: dead translation keys** – 14 keys were still in both
  dictionaries but were called nowhere, not even via the dynamic
  `t(f"...")` patterns: `options_group`, `analyse_on`, `analyse_hint`,
  `render_audio_demucs`, `analyse_toggle_log`, `track_required_body`,
  `alignment_remade`, `mark_ok`, `mark_missing`, `open` and the four
  `video_input_*` (orphans of a dialog that was replaced by an error
  message).
- **B296: visible text outside the translation layer** – the nl and en key
  sets were neatly in balance, but there was a lot of Dutch outside `t()`
  that the user does get to see. Now translatable: all 24 `PipelineError`
  messages (which end up in a QMessageBox via `_on_failed`), the complete
  HTML cluster report (title, headings, footer, and the `lang` attribute),
  the file dialog filters, the "waveform appears after..." text, the warning
  about lines running off screen, the names of the video input items (which
  sit inside an already translated message, so they had to come along) and
  the source selector in the timing editor. That last one showed the raw
  values "origineel"/"karaoke"/"zangstem"; it now shows the translated name
  and keeps the raw key as item data, so that the lookup in `audio_paths`
  stays unchanged. There are now 320 keys per language, in balance. A
  regression test guards against a literal `raise PipelineError("...")`
  coming back.
- **B297: references to steps that do not exist** – messages spoke of
  "stap 2 (Analyse)" and "stap 3 (Uitlijnen)" while the buttons are called
  1 Detecteer woorden / 2 Woorden koppelen / 3 Analyse / 4 Karaoke
  aanpassen and a separate Uitlijnen step no longer exists (that runs
  automatically via `ensure_alignment`). `prereq_need_analyse` also
  referred to "2 Analyse" in both languages. All the texts now name the
  real button; a test guards that.
- **B298: internal bug reference on screen** – the tooltip
  `line_toggle_tip` ended in "(B180)" in both languages. A test now checks
  for any `B<number>` pattern in all visible texts.
- **B301: unchecked threshold and a misleading merged label** – `align.min_confidence`
  was the only threshold without a check in `config._validate`, while 0.0
  means that windows with confidence 0 slip through the filter and
  `np.average(..., weights=...)` then divides by a weight sum of zero. Now
  bounded (0 itself excluded), plus a fallback to the unweighted mean in
  `_build_regions` in case such a group gets there by some other route.
  And `karaoke.merge_intervals` kept only the label of the first fragment
  when merging, so a box that damped both "oe" and "woo" showed up in the
  damping editor as "oe"; the label now names all the sounds ("oe+woo",
  without repetition) and the damping becomes the strongest of the merged
  fragments.
- **B302: outdated "still open" lists** – two lists in this document named
  B139, B189, B191, B193, B194/B195, B196, B198, B201/B202 and B136 as
  open. Checked: apart from B139 (the remainder) they have all been built
  in later versions (with an implementation in `modules/`), and
  `compare_models` (B136, "can go later") has already been removed. The
  lists gave anyone reading them a wrong picture of what was still to do;
  they have now been struck through with a pointer to where the work sits.
- **Deliberately NOT included in this version** – the rename to English
  identifiers and docstrings (B299) and the accompanying in-place
  conversion of the existing JSON files (B300). Those two belong together
  and were kept apart on request, so that the bugfixes above can be tested
  without the noise of thousands of renamed lines.
- pytest 468 green (458 + 28 new B288-B302 tests in `test_v095.py`, with 4
  existing pipeline tests updated to the new error texts), pyflakes
  completely clean, nl/en key sets equal (320 each). The only remaining
  test failure is `test_language_for_uses_songtekst` (language-detection
  library behaviour, independent of these changes).

Included in v0.96:
- **B299/B300: fully English codebase, with conversion of the existing data.**
  Carried out in ten phases on request, with a green test suite and a
  restore point on the pc after each phase (the assistant's working
  environment resets on a reboot; that happened three times during this
  job and was caught every time without loss). The full work list with all
  the translation tables is in `docs/hernoeming_B299_B300.md`.
- **What has been renamed** – 13 module names; ~800 identifiers (variables,
  parameters, functions, classes); the dict keys that live only in memory;
  all docstrings and comments; and all the stored keys in `config.json`,
  `project.json`, `timing.json`, `clusters.json`, `statistieken.json` and
  the language registry, including file and folder names.
- **What has deliberately stayed Dutch** – `songtekst.txt` and
  `karaoketekst.txt` (the user creates and edits those himself and they
  appear all through the manual), the markup in them (`[crowd]`, `[bg]`,
  ...), the Dutch interface texts in `translations.py` (that is the
  translation, not code) and this documentation.
- **One deliberate departure from a literal translation** – the field
  `lang` on `Syllable` meant "long held note", not a language code. It is
  now called `held`. That exact confusion was the cause of B289 (every
  syllable was underlined because it held `lang="nl"`); with `held` that
  mistake can no longer be made.
- **Five lessons the tooling now enforces.** This job nearly stalled five
  times on the same kind of mistake; they are written down here so that a
  future rename does not have to discover them again.
  (a) *Measure collisions per scope, not globally.* `songtekst` -> `lyrics` looked
  fine until it turned out `lyrics` was already a variable 41 times: the module
  disappeared behind a local name (`lyrics.repeated_filler_lines(lyrics)`). Same
  for `taal` -> `language` (17x). They became `song_text` and `translations`.
  Inside functions the same held for ten names, e.g. `vensters` -> `windows` where
  `windows` was already the parameter.
  (b) *Rename references only, not declarations.* The first version of the
  tool also renamed the dataclass field `AppConfig.analyse` to `analysis`
  - a `config.json` key, so a completely different phase - and thereby
  broke all the `config.analyse` references.
  (c) *Keyword arguments are `ast.keyword`, not `ast.Name`.* That left
  `timing_report(bron_karaoke=...)` behind while the parameter was already
  called `source_karaoke`.
  (d) *Strings link things too.* `@pytest.mark.parametrize("n_woorden,...")`
  and `caplog.at_level(logger="modules.songtekst")` refer via a string to
  something that did get renamed.
  (e) *Know which layer owns a key.* `timing_eval.py` READS timing.json,
  so its input keys belong to the stored format and not to the internal
  report dicts. And the translation key `"origineel"` is tied to the track
  identifier, which is in turn tied to file names - one loose replacement
  of it hit `TRACK_ORIGINEEL`, `origineel.wav` and the step names in one
  go.
- **The data conversion (B300)** – `tools/migrate_b299.py` runs on the
  installation itself. It makes a `.pre_b299.bak` of every file it
  touches, is idempotent, reports unknown keys loudly instead of leaving
  them silently in place (that last part is exactly how `config.py` loses
  settings: unknown keys are ignored with only a log line), and checks
  afterwards that every value from the backup can be found again under its
  new key. Tested beforehand on a copy of the real project data: 0 lost
  values, and the new code reads the converted `config.json`,
  `timing.json`, `project.json`, `clusters.json`, `statistics.json` and
  `languages/nl.json` correctly.
- **Verification of phase 4** – that only docstrings and comments were
  changed (and no code) was not taken on trust but established
  mechanically: for each of the 33 modules the AST was compared with the
  docstrings blanked out. All 33 identical.
- pytest 468 green (1 known, unrelated failure), pyflakes clean, GUI smoke
  test fine in both languages.

Included in v0.96.1:
- **Background** – after moving to v0.96 the user reported two things: an
  error during the analysis of Lied_S, and the feeling that the coupling
  was doing worse. Those turned out to be two unrelated matters with
  different causes, and only one of them was my fault.
- **B303: a built-in function renamed (my fault).** The B299
  translation dictionary had the Dutch "map" as `map` -> `dir`. The
  renamer applied that to Python's built-in `map()` as well,
  turning `', '.join(map(str, sorted(suggested)))` in `gui.py` into
  `', '.join(dir(str, ...))`. `dir()` takes at most one argument,
  so the analysis crashed as soon as clusters were suggested. The
  damage is bounded, and that was measured, not assumed: all the
  calls to built-in functions were counted in v0.95 and v0.96, and
  the only difference was `map 1 -> 0` and `dir 0 -> 1`.

  Why no test caught this: the line sits in a GUI callback
  (`_show_analyse_results`) that only runs if the analysis actually suggests
  clusters - a path the suite does not touch. And my collision check during
  B299 only looked at whether the TARGET name was already in use, never at
  whether the SOURCE word IS a built-in name. That hole has now been plugged
  with three tests in `tests/test_v0961.py`, one of which immediately found
  a second blemish as well (a pointless identity rule `list` -> `list`).

  A distinction recorded in those tests: a source word that is a builtin
  is fatal (working code silently changes meaning, without a syntax
  error). A target word that is a builtin (`alle` -> `all`, `reeks` ->
  `range`) is less bad: that only shadows, and only within that one scope.
  Those are allowed, but a separate test guards the case where that
  shadowing actually bites.
- **CORRECTION (v0.96.2): the coupling WAS my fault after all.** The
  conclusion below ("not caused by the rename") was right for the coupling
  logic, but missed the cause a layer deeper. See the "Included in
  v0.96.2" block for the full chain. I am leaving the original reasoning
  in place because it is correct in itself and shows where the analysis
  fell short: I compared the code, but did not ask which audio file
  actually went into Whisper.
- **The coupling: not the coupling logic.** This was checked three ways
  before anything was changed. (1) The same lyrics and transcription of
  Lied_S put through v0.93, v0.95 and v0.96: all three 222
  transcription words, 225 of 257 lyric words linked, only "MUZIEK"
  filtered out, zero words with a different link. (2) The full coupling
  view including `extend_coupling` and `creative_couplings` (without the
  manual pins) is identical too. (3) For all 32 modules the function
  structure was compared with names and texts ignored: not a single
  change in the logic.

  The real cause: Whisper ran again on 10 August and gave 23 segments
  instead of the 36 of 7 August (223 against 225 words). Same model, same
  language, same `initial_prompt`, and a bit-for-bit identical source mp3
  - but a different derived wav. Segments are the anchors for the
  alignment, so 23 long segments give far less grip than 36 short ones.
  The better transcription was still complete in the diagnostics history
  and has been put back (see below).
- **B304: gap in the one-off conversion.** It renamed only folders called
  exactly `origineel`. As a result `cache/<lied>/demucs_stems_origineel`
  stayed put in five projects while the code was already looking for
  `demucs_stems_original` - so Demucs ran again from scratch, minutes per
  song. The conversion now also handles folder names ending in
  `_origineel`, via a separate `dir_target_name` function that the test
  checks directly.
- **B305: the better transcription put back.** The 36-segment run of 7
  August has been written back from
  `output/Lied_S/diagnostics/transcription_original.json` into the cache,
  with the Dutch keys converted to the English ones. The worse run has been
  kept as a backup (`.pre_b305.bak`), and `wav_sha1` in project.json has
  been set to the current wav so that Whisper does not start over anyway.

  **Measured effect, and it was disappointing**: word coupling went from
  225 to 227 of 257 words - two words gained, no more. So the difference
  between 23 and 36 segments mainly affects sentence anchoring and the
  timing (`couple_timing` uses segments as per-sentence anchors), and far
  less the word-by-word coupling. Anyone who wants to pin the complaint
  "the coupling is getting worse" on the segment count alone is
  overestimating that link; the gain is probably in the line timing.
- pytest 472 green (468 + 4 new), pyflakes clean.

Included in v0.96.2:
- **The real cause of "the coupling is getting worse" - and that was my
  migration gap, not Whisper randomness.** In v0.96.1 I concluded that the
  rename had nothing to do with it, because the coupling logic was
  demonstrably identical. That was right but incomplete: I had never
  checked WHICH audio Whisper gets. Not the mix but the Demucs **vocals**
  (`detect_track`, `wav_path = stems["vocals"]`). The chain:

  1. B304 (my migration renamed only folders named exactly `origineel`)
     left `cache/<lied>/demucs_stems_origineel` in place;
  2. the code looked for `demucs_stems_original`, found nothing, and ran
     Demucs again from scratch;
  3. Demucs is not bit-reproducible, so a different vocal track came
     out;
  4. `wav_sha1` (the hash of THAT vocal track) no longer matched, so
     Whisper ran again;
  5. that run gave 23 segments instead of 36.

  Proof, not reasoning: the sha1 of the OLD `vocals.wav` is
  `c1c3c83e...` - exactly the `wav_sha1` of the 36-segment run of 7
  August; that of the NEW one is `aa8ec41f...` - exactly that of the
  23-segment run of 10 August.
- **A mistake in my own v0.96.1 repair, found during that analysis.** At
  B305 I set `wav_sha1` to the hash of the MIX (`cache/<lied>/original.wav`)
  while the code hashes the VOCALS. The cache check would therefore have
  failed at the next analysis anyway and Whisper would have run again -
  the repair would have undone itself. The vocal track belonging to the
  restored transcription is now back in place and `wav_sha1` matches it.
  Measured across all projects: the five with a vocal track in the cache
  reuse their transcription (Lied_S with 36 segments); the other five
  have no Demucs stem in the cache at all, which was already the case and
  is unrelated to these changes.
- **B306: the "known failure" was not a bug.** `test_language_for_uses_songtekst`
  had been red for many versions and was dragged along each time as a
  "known, unrelated failure". The cause was simple: the test needs
  `langdetect`, an OPTIONAL library. Without it `_language_for`
  deliberately falls back to "auto", exactly as intended - so the test
  checked behaviour that was not there. It now skips with
  `pytest.importorskip` instead of standing red. The suite is fully green
  for the first time in ages (472 passed, 1 skipped), and a REAL
  regression in language detection will now show up against the green.
- **Lesson.** Twice in a row I drew a conclusion from a code comparison
  ("the logic is identical, so it is not my doing") while the problem sat
  in the DATA chain feeding that code. After a rebuild, a regression
  raises not only the question "did the code change" but also "is the code
  still getting the same input".

Included in v0.97.0:
- **Reason** – the user started "Lied_S" over and asked four things
  at once: why the hallucinations "Heerlijke Heer" and "SPANNENDE
  MUZIEK" still came through when the lyrics should have exposed them,
  what was detected but is not being shown, why the colour markings
  from an earlier session did not fully come back, and whether the
  la-la-las at the end could not simply be timed. With one hard
  constraint attached: **the solutions have to be generic**, not
  tailored to this one song.
- **B307: the hallucination check looks at the SPOT, not just at the
  whole song.** The check from B285 asks "does this segment resemble
  anything anywhere in the lyrics?". That is too lenient at exactly the
  spot where Whisper hallucinates most often: after a long silence, at
  the end of a track. "SPANNENDE MUZIEK" scores a perfect 1.00 song-wide
  - because "muziek" really is sung in "Ik hou van dansen en muziek",
  halfway through the first verse. The user's idea gave the key: the
  lyrics carry no times (working those out is the whole point of this
  tool) but they do carry the right word order. So the nearest coupled
  anchors before and after a segment define a window in the lyrics that
  the segment has to fit into. In that window (the outro) "muziek" does
  not occur at all and the score drops to 0.38.
  Two guards keep the check safe: a segment in which the alignment did
  couple something is never touched, and Whisper's own word confidence
  has to be low (the same safety net as B285). On top of that the
  window is widened to at least twelve words, because two anchors right
  after one another otherwise leave a window of one word that almost
  nothing matches.
  Measured on the nine projects with usable data: exactly three extra
  segments drop out - "SPANNENDE MUZIEK" (Lied_S, 197.1 s), "Thank
  you." (Lied_J, 18 s after the last real line) and "C'est parti !"
  (Lied G, confidence 0.01, 19 s after the last
  line). All three real hallucinations; the coupled word count stays
  exactly the same over all projects together (2037). The minimum window
  is deliberately twelve: from 1 through 16 words the outcome does not
  change, and only from about 25 does "Thank you." slip through again.
- **B308: "Whisper heard nothing here" is something other than
  "hallucination filtered out".** The 21 outro words were marked `[hal]`
  because a filtered-out segment happened to fall in their anchor window.
  The real cause was quite different: for 27.6 seconds nothing came out
  of Whisper at all. That is a different problem with a different
  solution, so the editor was pointing the user the wrong way. A word
  whose anchor window contains no kept segment at all and is at least
  four seconds long now gets its own status `transcription_gap` with a
  calm grey-blue marking `[leeg]`. That takes precedence over the
  hallucination marking: if there is nothing there, that is the cause.
- **B309: the filtered-out detected words are visible again - and
  couplable.** This was the unfinished half of an earlier wish ("if
  things get left out, still show them in the editor, so they can be
  coupled if it does turn out to be needed"). The bottom row already
  marked the consequences (B287), but the discarded words themselves
  were no longer in the top row at all. They are in it now, struck
  through, in the same purple as the `[hal]` marking below it;
  automatic coupling leaves them alone, and the user can still couple
  them by hand. A legend has been added as well: four markings without
  any explanation is guesswork.
  Side catch that matters more than the looks: until now the number of a
  detected word depended on what the filter decided. Every filtered-out
  segment shifted all the numbers after it, and thereby quietly moved the
  manual couplings behind it - B307 would have made that worse. The
  numbering now counts the full transcription, so filter decisions no
  longer touch the couplings. Existing projects are converted once
  (marking `layout: full` in `word_coupling`).
- **B310: timing la-las, generically.** Three separate defects propped
  each other up.
  (a) A run of filler lines at the END of a track has no anchor behind
  it, so the interpolation marched on with the median line duration.
  With short coupled lines that stops far too early: the whole outro got
  squeezed into 169-188 s while singing goes on until 204.5 s. Where the
  singing really stops is known - the end of the last vocal-active
  window - and that now bounds the last line. Deliberately not
  `active_end`: that looks for the first sustained silence AFTER the
  anchor (B277) and would stop at the first pause inside the outro.
  (b) Picking the strongest `expected` energy onsets regularly produced
  two pulses from the same note (the attack and the body, 70 ms apart),
  and thus lines of 0.07 s. There is now a minimum mutual distance of
  0.6 times the average line spacing.
  (c) If there were too few usable onsets, nothing happened at all and
  the even interpolation stayed - including lines across instrumental
  silences. The lines are now distributed proportionally over the
  vocal-active windows, with no line falling across a pause and no
  sliver of a window of a few hundredths swallowing a whole line.
  On top of that a quality gate: if the onset placement yields a line of
  less than 0.4 s it is wrong, and the whole run is spread over the sung
  time after all.
  Result on the real projects: Lied_S gets "Espagna por favor" at
  170.5-173.9 s (exactly the sustained closing line), "Ole!" on its own
  shout at 176.2 s and the seven la-la lines neatly spread over the la-la
  block from 180.2 to 204.5 s. In "Lied I" the eighteen
  "da da da" lines land on the two sung windows instead of half across
  the silence; in "Lied J" and "Lied P" four lines of 0.1 s
  disappear. Where there was nothing to improve (Lied A, 0
  unreliable lines) nothing changes.
- **What is NOT possible, and why.** Coupling the la-las to transcription
  words cannot be done: there is not a single transcription word there to
  couple to. Timing them can be done, because the singing is simply there
  in the vocal track (24.2 s of sound in the 27.6 s gap). That is exactly
  why the solution lives in the timing and not in the coupling.
- **Method.** Every threshold was measured on the real project data
  instead of chosen, and each of the four parts was checked with a
  mutation test: the line in question switched off temporarily to see
  whether a test really does go red. Two tests turned out to be idle at
  first (they passed without the fix too) and were rewritten until they
  describe the actual measured case - among them the double onset at
  180.14 and 180.21 s from "Lied I".

Included in v0.98.0:
- **Reason** – the user put the principle more sharply than the code
  did: "if the transcript can be changed in step 1, then everything
  derived from it afterwards has to go. That really goes for all the
  steps. If you change the original music, all the music, transcriptions
  and timings derived from it are no longer right either." With the
  instruction to write that chain down and keep it up to date.
- **The audit.** Mapped from source file to video: every step key, every
  project value, every file the program writes, and what its content
  depends on. Eighteen gaps found. The worst five: the cluster selection
  survived new audio (and then ducked at the timestamps of the PREVIOUS
  track); `fragment_exclusions` and `restore_fragments` kept their
  absolute times on a timeline that no longer existed; the marking
  `karaoke_from_original` survived a new original, after which the
  alignment was skipped with offset 0 while the karaoke belonged to the
  previous original; the Demucs stem cache had no source checksum
  (exactly the failure mode that wrecked v0.96, because Whisper
  transcribes the vocal track); and the old `karaoke_edit.mp3` survived
  invalidation and was then picked as the audio source for the video.
- **Two hidden couplings that explain a lot.** `karaoketekst.txt` steers
  the WORD COUPLING of the lyrics through `_filler_priority_lines`, and
  therefore the line times - your parody text partly determines which
  original words get coupled. And `songtekst.txt` sits in Whisper's cache
  key (as initial prompt), so a text change can force a complete
  re-transcription.
- **The solution is not yet another list.** The knowledge about what
  depends on what lived as hand-written key lists in three functions;
  every new step meant somebody had to add it to the right list, and
  that is exactly what kept going wrong. That knowledge now sits ONCE,
  as data, in `modules/dependencies.py`: 65 artefacts that each name
  what they are derived from. Invalidation is therefore no longer a list
  to maintain but a question to that graph - what depends, directly or
  indirectly, on what changed? All call sites now go through one
  `pipeline.invalidate(context, ["input:lyrics"])`.
- **Noticing that something changed outside the app.** There was no
  checksum at all of `songtekst.txt` or `karaoketekst.txt`: editing them
  in Notepad was completely invisible. There are now sha1 fingerprints
  of both texts and of the logo, plus a signature per settings group.
  `sync_input_changes` runs at the start of every step, so no route can
  get around it. That also closes the gap that
  `advanced.forced_alignment` was not in the transcription cache key -
  that option rewrites the word times, but switching it off changed
  nothing because the cache kept hitting. The Demucs stems get a
  `source.sha1` beside them; stems from before this version have none
  and stay usable, because throwing away a good separation costs minutes
  per track.
- **`ProjectStore.clear_meta`.** `clear_step` touches only `steps` by
  design, so the project-wide markings (`karaoke_from_original`,
  `vocal_onset_s`, `language_choice`) survived EVERY invalidation. There
  simply was no counterpart to `set_meta`.
- **What deliberately does NOT expire.** Throwing away too much costs
  handwork and is just as wrong as throwing away too little. Changing the
  parody text costs no manual word couplings (those are about lyrics and
  transcription); a fresh residual-vocal transcription costs no handwork
  on the original (which did happen: invalidation was not per track); the
  alignment survives a new transcription (it is computed from the two
  audio files, not from the text - throwing it away anyway meant redoing
  the slow offset determination for an unchanged answer); the project
  name and the video titles survive everything; and the rendered video is
  never thrown away - it costs minutes and the user decides that himself.
- **Keeping it up to date without it rotting.** Two tests carry this
  design. `test_elke_stap_en_meta_staat_in_de_keten` searches `modules/`
  for every `set_step`/`get_step`/`clear_step`/`*_meta` key and demands
  that it appear in the chain: whoever adds a step without deciding what
  it is derived from gets red instead of silently stale data six months
  later. `docs/dependencies.md` is generated by
  `tools/write_dependency_doc.py`, and a test compares the file with what
  the generator produces, so the document cannot fall behind the code.
  That is the answer to "keep this up to date": not a document that asks
  for discipline, but a test that enforces it.
- **Measured on the real projects.** All ten projects on the pc have a
  matching checksum, so the upgrade throws nothing away. Checked on a
  rebuilt v0.97 project as well: the first run after the upgrade removes
  nothing and only adds the fingerprint steps, a second run does nothing
  at all, and only an edit in Notepad makes the right six derivatives
  expire.
- **Lesson.** Three of the six red tests after the rebuild were not a
  regression but a test fixture that lied: `source_karaoke` with
  `"sha1": "x"` next to a real file. The new source watch was right. A
  fixture that asserts something which is not true on disk hides exactly
  the kind of fault you are looking for.

Included in v0.98.1:
- **B312: the dependency chain threw a fresh transcription straight
  back out.** The user started Lied_S over and ran "1 Detecteer
  woorden" (detect words). `project.json` dutifully reported 28
  segments and 207 words, but
  `cache/Lied_S/transcription_original.json` no longer existed. The
  log pointed right at it: *"Derivatives removed after change of
  whisper_original: cache:transcription_original"*.
- **Cause.** `invalidate_after_fresh_transcript` means "the transcription
  has been renewed, wipe what rested on the PREVIOUS one". The chain
  delivered everything depending on `whisper_original` - including the
  transcription file itself, which is derived from that step too. The
  missing distinction: a step and the file it writes are one thing made
  in one action - the step is the bookkeeping, the file the content.
- **Solution.** `dependencies.direct_products`: a file whose only source
  is one artefact is that artefact's own product and stays as long as the
  artefact itself is not explicitly discarded. A file with more than one
  source (`output:lyrics_alignment` follows from the coupling AND the
  karaoke text) is a real derivative and does expire. In
  `invalidate_timing`, where timing.json has to GO, `include_changed` was
  already on; nothing changes there.
- **Wider than this bug.** The test
  `test_elke_stap_spaart_zijn_eigen_product` walks every step that writes
  a file and demands that none of them wipes out its own product. Without
  that test the same fault would simply come back as soon as
  clusters.json, alignment.json or karaoke_edited.wav was up next - it
  was the same five lines of code that decided all of them.
- **Lesson.** When invalidating, "what depends on this" is not the same
  question as "what has this made stale". The answer to the first
  includes the result that was just produced. I had tested the graph on
  what did have to go and on what had to be spared on OTHER branches, but
  not on the most obvious case: the product of the step that triggered it
  all.

Included in v0.99.0:
- **Reason** – the user started Lied_S over with an empty cache.
  Whisper stopped after 134.9 s and only started again at 196.0 s: 61
  seconds without transcription, holding nothing but two hallucinations.
  The whole closing verse and the last chorus were missing. Assignment:
  take on Whisper itself, including the still unused options, and place
  the words it missed after all, measured on the vocal track.
- **What it was NOT.** Three Demucs separations from exactly the same
  source file (the same sha1) gave three different vocal tracks. Still
  the vocals are not the cause: the energy profile per five seconds is
  identical in all three to three decimals, and the "good" track differs
  from the two new ones (0.0037) about as much as those two differ from
  each other (0.0026). All three simply have singing in the gap. The
  initial prompt was byte-identical, and so were model and language.
- **B314: what it IS, read in the source of faster-whisper.** Measuring
  was impossible — the assistant's working environment may not download
  the model — but the library itself gives the mechanism away:

      should_skip = result.no_speech_prob > options.no_speech_threshold
      if avg_logprob > options.log_prob_threshold:
          should_skip = False
      if should_skip:
          seek += segment_size      # skip the WHOLE window

  A window of thirty seconds is skipped in its entirety. Our gap is
  roughly two of them. It is a threshold decision, so 3% of audio noise
  can flip it. On top of that comes the temperature ladder:
  faster-whisper decodes with sampling on fallback
  (`sampling_temperature`), and that is not seeded. Which explains
  exactly what we saw: the same button, three outcomes.
  `temperature` is therefore `0.0` only by default — greedy decoding, and
  thus repeatable. A karaoke video you cannot reproduce is useless, and
  without repeatability nothing is measurable either. The thresholds
  themselves have NOT been moved blindly: which value is right for a
  given track cannot be reasoned out. They have become settable
  (`no_speech_threshold`, `log_prob_threshold`, `vad_filter`,
  `hallucination_silence_threshold`) with `tools/whisper_probe.py`
  alongside, which puts the variants side by side on your own vocal
  track. The dependency chain (B311) notices such a change and has the
  transcription redone by itself.
  Side catch: `save_config` wrote a hand-written list of keys for
  `whisper`. The new settings were read in but never written back, so a
  change in `config.json` disappeared silently at the next save. Now via
  `asdict`, with a test that sends every field of every settings group
  around the loop.
- **B313: placing skipped words on the vocal track.** The alignment
  couples on sound; what Whisper never produced cannot be coupled. And
  after a gap the alignment grabs whatever is within reach — measured:
  "alle" and "dagen" coupled to "la," at 0.25. Both cases leave a word
  without a usable time, while the vocal track simply shows where the
  singing is.
  Per run of skipped words between two good anchors, the sung time in
  that window is distributed over the words in order (via
  `spread_over_active` from B310, so silences are skipped). Three rules
  keep it honest: a properly coupled or manually fixed word is not
  touched, the order is preserved because a run stays within the window
  of its neighbours, and the result is marked `estimated` — so an
  estimate does not quietly get the weight of a measurement in the
  reliability assessment of a line.
- **The self-correction that made B313 usable.** The first version
  squeezed 28 words into 3.5 seconds, because the hallucinated "MUZIEK"
  gave a perfect coupling (1.00) with the lyrics word "muziek" and so
  counted as an anchor. Similarity does not expose such an anchor — it is
  a perfect match in the wrong place — but the CONSEQUENCE does: nobody
  sings eight words per second. A window demanding more than six words
  per second therefore lets go of the adjacent anchor.
  That overshot in the first attempt: "serenade" and "aan" (1.00) shifted
  by a second as well and the real la-la couplings by five. The solution
  is the isolation criterion: only a LONER may let go — an anchor with no
  anchor directly before or after it. A correct coupling is rarely alone,
  a misplaced one is by definition, because there is nothing around it to
  couple to. Measured on five projects: exactly the two wrong anchors let
  go, not a single good one.
- **B315: the log lines through the translation layer.** They turned out
  to be on the wrong side of the language border: via `_QtLogHandler`
  they end up in the log pane, so the user reads them. All 185 now have a
  `log_` key in `nl` and `en`. The conversion went through AST instead of
  text replacement, and just as well: `ast` gives column positions in
  BYTES of the utf-8 encoding, not in characters, so on every line with a
  diaeresis the character-wise slicing went off and a comma vanished.
  After rolling back and redoing it on bytes everything matched.
  Three tests guard the whole: no `logger.x()` may carry a literal text
  any more, every `log_` key used has to exist, and the ordered sequence
  of `%` placeholders has to be the same in both languages — that last
  one for ALL keys, which was checked nowhere until now. An existing test
  caught something straight away, by the way: my log texts started with
  "B307:", "B313:" and so on, and internal bug numbers do not belong in
  visible text. They are in the comments now.
- **Note when upgrading.** The Whisper settings have changed, so the
  settings signature from B311 changes with them and the existing
  transcription expires: step 1 has to be run once more. That is the
  chain doing its job — a transcription made with different decoding
  settings is a different result. From that run on the outcome is
  repeatable.

Included in v0.100.0:
- **B316 – the prompt is a hint, not a source.** From the user's log: he
  saved a lyrics override (263 words) and the chain answered with
  *"Derivatives removed after change of lyrics_override:
  cache:transcription_original, whisper_original, word_coupling"*. I had
  made `whisper_original` depend on `lyrics_override` because the initial
  prompt comes from the lyrics. Technically true, but cutting one word in
  the coupling editor threw away two and a half minutes of computation —
  exactly the over-invalidation I had warned about myself. The prompt is
  already in the transcription's cache key, so anyone who deliberately
  reruns step 1 still gets a changed text along. New: a test table that
  records per source change what specifically must NOT be destroyed —
  that side of the chain I had tested too lightly.
- **B317 – the colour marks, the legend explains.** The codes on the word
  (`[vul]`, `[hal]`, `[zang]`, …) made the text harder to read and said
  nothing without an explanation. They are gone; at the top there is one
  legend with coloured blocks, built from the same `_STATUS_STYLE` table
  that does the drawing, so a new marking cannot appear on screen without
  an explanation.
- **B318 – weighting on syllables.** `spread_over_active` divided the
  sung time evenly, so "Espagna" got as much as "e". With `weights` (the
  syllable count from pyphen) that becomes proportional. Without weights
  the old behaviour stays exactly as it was.
- **B319 – the end of the singing is an anchor.** The start had been one
  since B130/B133 (`vocal_onset_s`), the end was not, while it is just as
  firmly fixed. There is now a `vocal_end_s`, and two things follow from
  it. A coupling that lies after it is released: Whisper does write
  something down after the last singing now and then (applause, fade-out,
  hallucination) and a lyrics word hanging off that pulls everything
  before it out of true — measured on Lied_S: one such coupling. And a
  run at the end is fitted from back to front when the window offers much
  more time than the words need, with a syllable duration measured on the
  track itself instead of assumed. That is where the certainty is: you
  know where such a run ends, not where it begins.
- **B320 – the rows drifted apart.** In an uncoupled stretch the bottom
  words got a column right away, while the top words only got one as soon
  as a coupled pair came past. Measured with eight uncoupled words: top
  `[0, 9, 10, …, 16]`, bottom `[0, 1, …, 8]` — a shift of 720 pixels,
  which meant you could no longer see which detected word belonged to
  which lyrics word. Both rows now advance together: eighteen columns
  became ten and everything lines up again. Coupled pairs keep their
  behaviour from B220.
- **B321 – the click landed on the wrong word.** A coupling is stretched
  automatically to adjacent detected words (B191, up to three), and such
  a group was drawn as one wide box lying across the column of the
  neighbour to its right. `_hit_row` always returned the FIRST word of
  the group inside that box: clicking "dable" in the group "formi|dable"
  gave "formi", so a coupling landed on the word left of your pointer.
  The grouping is a drawing choice and now decides nothing about what you
  can point at; inside the group there is a dotted line so you can see
  what you are aiming at.
- **B322 – the window started too small for its own content.** The layout
  asks for 789×807, the window minimum was 760×520. That minimum is there
  on purpose (B216: shrinking must be allowed), but it also let the window
  start at a size where the group boxes drew their text on top of each
  other — measured, the input block got 54 / 90 / 140 / 175 pixels at a
  window of 520 / 600 / 700 / 800, while it needs 175. The startup size is
  now raised to what the layout asks, bounded by `availableGeometry`
  (which already leaves the taskbar out). The minimum stays, so shrinking
  it yourself afterwards is still allowed.
- **Lesson.** Two of the three red tests afterwards were not a regression
  but contamination: my own test fixture replaced `rhythm.active_windows`
  directly in the module instead of via `monkeypatch`, and that
  replacement stayed in place for the tests after it. A fixture that
  changes the real module without putting it back makes the order of the
  tests part of the result.

Included in v0.101.0:
- **B326 – the hang at "2.2. Timing verfijnen".** From the log:
  `Zin-koppeling: {'high': 43, 'medium': 0, 'low': 16}` and immediately
  after it `KeyError: 'hoog'` at `pipeline.py:3624`. The coupling quality
  keys have been English since B299; in this one place it still said
  `quality['hoog']`. So it had been in there since v0.96 and only showed
  up now, because this line is reachable only through that one button — a
  branch with no test and no other path to it. Checking it over, it
  turned out not to be one forgotten line but a little group: the texts
  the pipeline hands back to the GUI (the `{detail}` of the timing, the
  video input check, the structure check of lyrics/karaoke text and the
  timing synchronisation message) were all hard-coded in Dutch. The guard
  from B315 only looked at `logger.*` calls, and these texts do not go to
  the log but to the message panel and the QMessageBox. They now run
  through `translations.py`; the new guard is behavioural instead of
  textual — it calls the functions twice, in `nl` and in `en`, and
  demands that the answers differ.
- **B326 follow-up – a comparison on a translated name.** `render_video`
  decided which missing input it was allowed to ignore with
  `name != "offset origineel/karaoke"`. In English that item is called
  "offset original/karaoke", so there the render would have refused over
  a missing offset that is in fact optional (step 1.4 aligns by itself).
  `video_input_status` now returns a language-independent key per line
  next to the name for the user, and the exception stands as
  `VIDEO_INPUT_OPTIONAL` in code instead of in a sentence.
- **B325 – the buttons carry their tab.** The eight main buttons are now
  called 1.1.–1.4. and 2.1.–2.4.; tab 1 had no dot after the digit at
  all, tab 2 did. The real work was not in the buttons but in the
  fourteen messages that named a button ("run '1 Detecteer woorden'
  first") — exactly the kind of text that lags behind at every
  renumbering, as B297 already demonstrated. A message now writes
  `{step_detect}` and `t()` fills in the current name. Other placeholders
  (`{track}`, `{file}`) stay, so the caller keeps its own `.format()`. A
  test demands that no text spells out a button name any more.
- **B323 – Stop stole the busy colour.** `_install_busy_indicator` hooks
  onto EVERY `QPushButton`, so onto Stop as well. If you clicked Stop,
  Stop became the owner of `_busy_button`, and the cleanup after the
  abort then restored Stop instead of "1.1. Detecteer woorden" — which
  stayed yellow. Three things: Stop no longer hooks on (it starts
  nothing, it ends something), a click during a running task does not
  take over ownership, and `_busy_button` has become a set so that none
  can ever be left behind.
- **B324 – the write key was the file name.** `_copy_into_input` derived
  the key with `Path(target_name).stem`, which yields `songtekst` and
  `karaoketekst`; `_refresh_inputs` and the file chooser ask for `lyrics`
  and `karaoke_text`. Consequence: for both texts the internal name was
  always shown instead of "viva espanja-origineel.txt", and the file
  chooser did not open in the last used folder. For the logo it happened
  to work, because there the stem is "logo" as well. The key is now
  passed explicitly, sits in one place as `INPUT_NAME_KEYS`, and existing
  projects are converted once when opened (`migrate_input_names`,
  idempotent, leaves an already correct value alone).
- **B327 – a label showing its own key.** The waveform editor builds its
  lane labels with `t(f"lane_{key}")`, and three of those keys
  (`origineel_tekst`, `karaoke_regels`, `zangstem`) had stayed Dutch at
  B299. `t()` falls back to the key itself, so the screen literally read
  `lane_zangstem` — in both languages, and in the source selection and
  the "not available" message too. The guard from B315 missed this
  because it matches on `t("log_...")`: literally, and only log keys. All
  `t(f"...")` in `modules/` have been checked; `model_{key}_desc`,
  `view_{mode}` and `t(track)` were fine, these three were not. The new
  test walks the `_LANE_LABELS` table and demands that no key returns its
  own name.
- **B328 – the manual described half of it.** The occasion: could more
  be cross-referenced? What was missing was mostly the handwork. The
  four editors are in it now with their mouse rules, the colour legend
  of the coupling editor (including the five status frames and the
  struck-through filtered word), and a small table for the nastiest
  difference — "Sluiten" (close) saves in the coupling and stress
  editors and discards in the waveform and ducking editors. Further the
  green "Terug uit origineel" blocks, "Regel uit/aan", the
  Blokken/Zinnen/Woorden display choice, the vocal analysis, the cache
  management, the output folder, and the render dialog that picks not
  only music but TEXT as well. Two things were no longer right: that
  render dialog, and the order on tab 2 — "2.1. Klemtoon bewerken"
  refuses to open until "2.2. Timing verfijnen" has made a
  `timing.json`. Finally the manual refers to `docs/dependencies.md`,
  which since B311 underpins the sentence that stood there as a claim.
- **Lesson.** Two bugs from this round (B326 and B327) are the same bug:
  a rename that landed on a path where no test comes past. The guard
  B315 set up for that was textual — it searched for a literal pattern
  in the source — and therefore missed everything that is built
  dynamically or does not go to the log. This round's guards check
  behaviour: call it in two languages and compare. That also finds what
  you did not think of in advance.

Included in v0.102.0:
- **The calibration set.** This round started with a measurement setup
  instead of with an idea. The user corrects `timing.json` by hand in the
  waveform editor while `timing_auto.json` keeps the automatic result;
  those two files together are a calibration point, because every line he
  has moved is a line the automation got wrong. Eight projects yielded
  130 such lines. `tools/timing_regression.py` rebuilds the input of
  `sanitize_timing` from the stored sentence coupling, runs the current
  code over it and reports two numbers: how far the moved lines were off,
  AND how many of the lines he left alone get worse from it. That second
  number is the most important one — an average that improves while good
  lines are being wrecked is not an improvement at all, however nice the
  figure looks.
- **B332 — the sentence level reasoned in syllables.** `sanitize_timing`
  divided the lines between two anchors *pro rata by syllables* and
  capped the duration at `base tempo × syllables × 3`. That reads as
  logical but it is a word-level notion, used one storey too high: a line
  of four syllables does not get a quarter of the time of a line of
  sixteen, it gets its own phrase. A sung line is a musical phrase and
  that lasts a fixed number of bars — in Lied S a new line starts every
  3.77 s, which at 129 BPM is exactly 8 beats, and 38 of the 59 manual
  line starts lie within 0.10 s of a detected beat. A rigid grid over the
  whole song does NOT work (then only 13 of the 59 land on it): the
  period is locally stable, the phase is not, because instrumental
  passages break it. `phrase_period` therefore measures it over the
  distances between consecutive reliably timed lines and returns `None`
  as soon as the spread goes above 18% - then the whole mechanism
  switches itself off and everything works as before. Deliberately
  measured over ALL lines, crowd included: in a parody a crowd line is
  often a full phrase, and filtering them out drove the spread from 6%
  to 50%.
- **B332 — the gain is in the test, not in the dividing.** Measured on
  the broken stretch of Viva: the phrase measure as a distribution weight
  brought 7.18 down to 4.53 s, but as a *validity test on the anchors*
  down to 2.09. A sentence that CANNOT be a phrase is not a credible
  anchor, and that works precisely where the duration reference has
  nothing to say — the "La la la" lines in the outro have a spread of 63%
  and thus no usable median, but spans of 0.64 and 0.80 s are impossible
  against a phrase of 3.6 s. The test rejects good anchors too (short
  half-phrase lines), but that costs 0.06 to 2.11 s while a wrong anchor
  in a gap costs 7 to 12 s, which is the argument for putting it early.
  The lower bound is critical: at 0.45 × period a real line of 1.42 s was
  lost at a period of 3.72 and everything after it shifted 2.27 s. Now
  0.25.
- **B329 — a repeated line is about the same length everywhere.** The
  user's idea, and the measurement proved him right: "E viva Espagna"
  occurs 12 times with a median of 3.60 s, and the instances of 7.66 and
  5.31 s were not held notes but the cause. Together with a third outlier
  they explained 8.8 s of the 9.4 s shift that sat in the whole tail
  afterwards. `reference_durations` builds that reference only from
  REALLY measured instances — an estimate used as a reference confirms
  its own error, and in Lied N "oehoe oehoe" is at exactly 1.99 s
  five times out of nine, which is not a truth but an even distribution.
  A text with a spread above 15% yields nothing: "Sunday Bloody Sunday"
  varies from 0.10 to 8.50 s and that is genuinely so. This is the
  generalisation of B166, which did exactly this already but only for the
  lines after the last anchor.
- **B330/B331 — the onsets inside a window.** `active_windows` gives only
  the outer edges of a sung passage. The two "Ole!" shouts in the intro
  (1.65–4.30 and 4.35–6.80) therefore melted into one window of 5.2 s,
  after which both lines were smeared evenly over that whole gap: 4.78 s
  each instead of 2.55. `rhythm.onsets` looks for rising edges INSIDE the
  window. Held against the manual timing, every line start in a gap of
  fifty seconds lay within 0.6 s of such an onset, median 0.15 s. The
  snapping happens AFTER the structure and only on estimated lines; a
  measured line is never moved.
- **The order is not a detail.** On a structure still 2 s out of true the
  snapping made the result *worse* (2.09 → 2.32) because it then grabs
  the onset of the neighbouring line. On a straight structure it brings
  the line to within a fraction. Hence the reach of 0.45 × the phrase:
  any further and it grabs the wrong one.
- **Two mistakes of my own that the measurement caught.** The first
  version of the snapping bounded the START of a moved line but not its
  END, so the measured line after it was pushed forward anyway — five
  lines that were right went wrong that way. And I had built in a branch
  that let lines run on at their own phrase across a large gap between
  two anchors instead of smearing them; it improved one song and made
  another one worse by MORE, so it is out again. Without the calibration
  set I would have left it in.
- **Result and limits.** Weighted error on the 130 moved lines: 4.60 s →
  2.98 s. Lied S from 5.38 to 0.70, Lied G from
  4.75 to 2.26, Lied J from 1.13 to 0.06, Lied P from 3.80
  to 3.26. Lied N gets slightly worse (3.48 → 3.66) and Lied T
   clearly so (7.60 → 9.26, with four untouched lines worse).
  That last song has an instrumental gap of 34 seconds in the middle of
  its la-la tail; the old even smearing happened to land better there.
  Frankly that is not a solved problem but a traded fault, and it is on
  the list.

Included in v0.103.0:
- **B333 — the coupling was right, the timing was not.** "Lied G
  " drifted monotonically: +2.2 s at the start, −7.3 s at the
  end, 52 of the 64 lines corrected by hand. The suspicion was alignment
  drift between original and karaoke, but that could not be: that karaoke
  was made from the original with Demucs, so offset 0 and one timeline.
  The measurement pointed somewhere else entirely. I laid the original
  sentence spans from the stored coupling next to the manual times:
  **median 0.34 s off**. So the coupling was simply right. What the
  timing made of it was 4.19 s off. The problem was entirely in
  `sanitize_timing`.
- **The cause: accumulated nudges.** A line shorter than its minimum
  duration gets stretched, and that pushed the next line forward via
  `start = max(starts[k], prev_end)` — even when that next line had a
  REALLY measured start. One such nudge is small (this song has six
  sentences under a second, 3.6 s short in total), but the minimum also
  depends on the syllable count of the karaoke line, and the nudges add
  up because every pushed line pushes its successor in turn. Hence the
  drift is monotonic and not erratic: it is a sum, not an error.
- **The repair, and why it needed an exception.** A measured start now
  beats the minimum duration of the line before it; that one gets
  shortened instead of pushing the next one away. That immediately broke
  an existing test (B139/B148: four repeat lines that the coupling put a
  third of a second apart may not be squashed into slivers). Rightly so:
  if the ANCHORS themselves are crammed together they cannot all be
  right, and then spreading them out is still the best you can do. The
  rule now is: shorten only if the line before it still reaches its own
  minimum afterwards. That distinguishes "one too-short sentence between
  good anchors" from "a cluster of anchors that cannot all be true".
- **The yardstick, and why it was needed.** The user pointed out that
  "Lied G" was made a while and quite a few versions
  ago. That turned out to be exactly right: the stored `timing_auto.json`
  comes from version 0.73 to 0.93 for six of the eight projects. A
  comparison against it therefore measures everything that has happened
  since and not what one change is worth — my earlier "4.60 → 2.98" was
  too flattering in that sense. `tools/timing_regression.py --vergelijk`
  now sets two runs of the tool against each other instead of against a
  stored file, and `--noteer` writes the result per version to
  `docs/metingen.md`: per project how many sentences are coupled, how
  many lines were moved by hand and how far the code still is from them.
  That keeps it visible across releases which song gets better and which
  song pays for an improvement elsewhere.
- **Measured honestly.** Against v0.101 on the same input: weighted
  4.62 s → 2.41 s over 141 manually corrected lines. Lied G
   4.62 → 0.65, Lied S 5.89 → 0.70, Lied J 1.13 → 0.06,
  Lied P 3.76 → 3.33. Lied N 3.48 → 3.71 and Lied T
   7.60 → 9.26 get worse; the latter remains the open item.

Included in v0.104.0:
- **B338 - the yardstick measured the wrong thing, and that came first.**
  The tool from v0.103 rebuilt the input of the sentence level from the
  stored sentence coupling. The user's manual corrections on the original
  lane are baked into that: at Lied G 58 of the 64
  sentences, at Lied N 58 of the 69, at Lied P 45 of the 50.
  So in my measurement the timing got an input that had already been
  straightened out by hand. It now runs the real pipeline over the stored
  transcription (the diagnostic copy of the segments, which survives an
  emptied cache) and leaves out every manual step. The weighted figure
  goes from 2.41 s to 3.37 s as a result. That is not a regression but a
  correction: I was counting handwork as a merit of the tool. The old
  rows in `docs/metingen.md` have been removed instead of left standing
  next to an honest measurement.
- **B334 - Whisper's repeat loop.** In the new project there were 34
  copies of "now," at exactly 193.500 s, and 13 times "oh yeah" at
  223.500. Confidence 0.98, and "now" really does occur in the lyrics, so
  no content check sees anything wrong with it. The shape does give it
  away: start and end are equal, so the word carries no time. It can
  therefore contribute nothing to a timing and can only become a wrong
  anchor - which makes discarding it safe. Measured over eleven projects,
  eight have no word without a duration at all, two have one, one has a
  run of three and the problem song has 34. The threshold is at four:
  removing that group of three made Lied N measurably worse (0.16 s),
  so it stays. The filter sits in the read path, so existing projects
  benefit without Whisper having to run again and without the cache file
  being touched.
- **B336 - the tail belongs where the singing is.** Where the
  transcription stops (Whisper does not write down vocalises, so a
  "na-na-na" tail yields nothing) the lines were smeared over the
  remaining playing time. That goes wrong as soon as there is still an
  instrumental passage in the tail. The vocal track shows exactly where
  singing does happen, and the window length divided by the phrase period
  says how many lines fit in it: 14.56 s = 3.90 phrases -> 4 lines,
  29.88 s = 8.01 -> 8 lines, while a little peak of 0.88 s (0.24) and a
  held note of 4.78 s (1.28) carry none. That integer test is exactly
  what separates a run of sung lines from one long note. If the total
  does not come out exactly, the rule does nothing - better nothing than
  a confident mistake. On the song it was meant for: twelve lines, on
  average 0.24 s off against 9.26 s.
- **B336 - and why that does not show up in the measurement.** That song
  dropped out of the calibration set: the user has changed the karaoke
  text since (36 lines against 40 in the stored timing), so the
  calibration points no longer line up. Of the other seven projects not
  one has a real tail after the last anchor. So the rule has been worked
  through where it belongs, but it is not in the weighted figure.
- **B337 - the lists belonged to the language, not to the code.** The
  hallucination and filler word lists were a fixed Dutch set ("muziek",
  "ondertiteling", "zang", and "en/de/het/een") while the originals are
  English and French. They now sit in the language registry B241 already
  had: next to vowels and clusters there are `hallucinations` and
  `fillers`, they travel along in `languages/<code>.json`, and the lookup
  is a UNION of shipped and collected - otherwise a collected file for a
  built-in language is silently ignored and nothing happens when you mark
  a word. An unknown language gets empty lists, so a Danish song makes
  its own `da.json` and nothing ends up in the shipped set. A test
  demands that every built-in language has both keys explicitly, so no
  language can be added without a decision.
- **B337 - at the spot, not song-wide.** The test was "does this word
  occur anywhere in the lyrics". Measured: all eight occurrences of "you"
  in Walking on Sunshine are in the first 36% of the song, and they were
  protecting a "Thank you" in the outro two hundred words further on. The
  test now uses the position window from B307 - the stretch of lyrics
  between the nearest properly coupled words. Important detail the
  measurement brought out: that test has been ADDED to the existing
  round, not put in its place. I first took the song-wide check out of
  round 1 because the position is only known in round 2; that cost Lied
  S five seconds straight away, because a segment disappeared there
  that round 1 was rightly clearing up.
- **B337 - extendable from the coupling editor.** Of the five markings in
  the legend three are a measurement ("Whisper heard nothing here",
  "timed on the vocal track", "no match") and two are a judgement. Only
  those two have become clickable: hallucination works on the top row
  (what Whisper found), filler word on the bottom one (the lyrics).
  Select, click, and the word goes into the list of the audio language;
  clicking again takes it out. A shipped word cannot be erased by hand -
  that stays a code decision.
- **Honest about the yield.** B334, B336 and B337 change not a single
  figure on the seven measurable projects: 3.37 s before and after. That
  is no coincidence but the nature of this work - it is about cases that
  do not occur in these songs (the repeat loop is in a project whose step
  2.2 has not been run yet) or about tooling that only does something
  once the user uses it. What does count: none of the 130 moved lines
  gets worse, and the "Thank you." that B337 was meant to catch turned
  out to be cleared up by the existing checks already. The word lists
  will prove themselves only on an artefact with a high confidence.

Included in v0.105.0:
- **Which songs work well - in the manual.** The occasion was "Lied F
  " (after Walking on Sunshine): choir and lead
  sing over each other at the end, with a lot of short interjections, and
  the coupling editor became unreadable there - "a long-player with a
  scratch", in the user's words. That is not a fault you have to
  rediscover per song but a property of the tool, so it is now in
  `docs/manual.md` under "Wat voor liedjes werken goed?" (which songs
  work well): what it comes down to (everything hangs on what Whisper
  makes of the vocal track), how you recognise it (many green-blue frames
  - a time, but not coupled - or pink ones, usually at the end), what the
  tool then does (put the lines on the vocal energy, which is an
  estimate) and what you can do yourself (`[bg]` for real overlap, and
  otherwise the waveform editor).
- **What the measurement under it said.** For that text the song was laid
  line by line against the manual correction, because the user had the
  idea that bits were shifting like a cumulative error. That idea is
  right, but only in the tail. The start sits at 0.00 s for eleven lines.
  The middle varies: -0.61 s to +1.67 s, six lines forward and six back -
  noise, not drift. From line 44 on it is one-sided and rising: +1.95 s
  to +16.36 s, eighteen forward against three back. The mutual distance
  of the automatic lines there is a median 1.19 s against a phrase of
  about 3 s, with four lines at exactly `_MIN_PHRASE_S` (1.00 s). That is
  the picture of lines being squeezed against their minimum duration and
  pushing each other forward.
- **Both safety nets were there and did nothing - by design.**
  `phrase_period` measures 25% spread on this song against a limit of 18%
  and returns `None`, with which B332 and B336 switch themselves off;
  that is exactly the self-off switch they ask for, because without a
  reliable period the mechanism would start guessing. And B333 steps
  aside as soon as anchors are crammed together (the B139/B148
  exception), which is the case here. So nothing is broken; the song does
  not supply the information the correction needs. Two items come out of
  it and go on the pile: **B339** - line marking/line numbers in the
  bottom row of the coupling editor, because every word already carries a
  `line` in the display data but it is drawn nowhere, and without that a
  repeating outro reads as a wall. **B340** - a run of anchors packed
  much tighter than the phrase cannot be right as a whole. Warning
  attached, from the development of v0.102: a crude variant per pair was
  tried and was worse (it wrecked half the verse anchors); it has to work
  on a *run*, and it needs a period that this song in particular does not
  supply.

Included in v0.106.0:
- **B347 - word timing at a pause inside the line.** The occasion was the
  question whether things had gone well at "Lied D" with the two
  sentences that have a pause in them ("Lightning and thunder [2.06 s]
  magic and wonder" and "Golden reflections [2.10 s] givin' directions").
  They had not: of the 282 words in that song eight have no duration at
  all, and those eight all sit in exactly those two lines, four of the
  eight words per line, stacked on the line end. In the video they light
  up all at once. Cause: `distribute_over_windows` (B234) counts the
  syllables in two ways. The stored line consists of 25 pieces ('I', 'k',
  ' g', 'i', 'ng', ...), but the function walks through it with the count
  that `split_line` takes from the word text, and that comes to 10. After
  ten pieces it thinks it is done, and the cleanup line at the end puts
  the remaining fifteen on `line.end` with start equal to end - on
  playback a word with a negative duration even came out ("jaren" from
  85.34 to 82.69). A word's share is still weighted on syllables (that is
  what B234 is about), but the pieces now come from `piece_groups`, which
  counts what is actually there. That it was visible in only two lines
  has a reason: the function bails out immediately as soon as a line has
  only one vocal window. Only a line WITH a pause gets in, and as soon as
  it got in it went wrong. Two chances, two hits.
- **B345 - past the end of the track.** Measured on a 20-second test
  song: the last line could be stretched to 80 s and dragged as a whole
  to 199.5-200.5 s, and an original sentence to 90 s. In all three drag
  modes the left side was already fixed (`max(0.0, ...)`) and the
  playhead was already bounded by the duration - the blocks had never had
  that treatment. Karaoke lines are bounded against the duration of the
  karaoke track, original sentences against that of the original.
- **B346 - passing each other.** The 2 rows on the original lane and the
  3 on the karaoke lane are purely a drawing trick (`index % 2` and
  `index % 3`), so that could not be the cause. The times could pass
  each other: line 2 at 3.0-4.0 dragged to 0.4 s landed at 0.0-1.0,
  before line 1. `clamp_span` guards *overlap* and not *order* - it
  drops the block into the nearest free gap, and a gap before its
  predecessor is just as free. Three routes to it: the ordinary drag,
  the crowd lines that are exempted from the overlap check, and the
  block view, where the check was skipped ENTIRELY because it sat behind
  `if single:`. The editor no longer uses `clamp_span` but bounds on the
  END of the previous and the START of the next; that forbids
  overlapping and passing in one grip and still lets you slide up
  against a neighbour. Agreement with the user: never overlap, crowd
  excepted - and nobody may pass, crowd included, so crowd is bounded on
  the start of the previous and the end of the next (overlapping
  allowed, jumping over it not).
- **B341 - the busy colour had been dead since B323.** Measured with a
  real click: a button that starts a task does not end up in
  `_busy_buttons` and keeps an empty stylesheet. That goes not only for
  "2.4. Video maken" but for all eight step buttons. The guard rail from
  B323 ("something is already running, so this click does not take over
  the colour") is only reached AFTER the button's own handler, and that
  has already set AND started the worker - `QThread.isRunning()` is true
  right after `start()`, measured separately. So every button stepped
  aside for its own task. The owner is now decided on "has a task been
  ADDED": `pressed` fires before `clicked` and remembers which worker
  there was, and a different worker after that belongs to this click.
  B323 stays standing. The old test did not see this because it called
  `_mark_busy_click` directly with an empty `_worker`; the new one goes
  through a real click.
- **B342 - the word cut in two at the segment boundary.** Whisper
  decodes in chunks, and a word that falls on the cut comes out twice: a
  clipped stump at the end of one segment and the whole word at the
  start of the next, with a capital (a new sentence starts there as far
  as it is concerned) and sometimes misheard, because it hears that
  piece again without the run-up in front of it - hence "Collections"
  for "reflections". Four cases measured over two projects, always the
  same shape: the stump is shorter (0.08-0.38 s) AND less certain
  (0.01-0.25) than its twin. The proof that it is one word is in the
  song itself: "dreaming" lasts 1.31 s and 1.36 s where it does not fall
  on a cut, and the two halves together span 1.29 s. They are glued back
  together in the read path now (next to B334), so the coupling sees one
  word and the timing gets the real onset. The boundary is at 0.30 s of
  gap: the measured gaps are 0.020, 0.120 and 0.201 s. The fourth case
  sits at 0.702 s and deliberately stays - merging there would stuff
  seven tenths of silence inside a word. What similarity alone may not
  do is shown by the counter-test: INSIDE a segment there are real
  repetitions everywhere ("Tickle, tickle", "niggle, niggle", "No, no,
  no", and at Woah-oh a row of forty "now,"), so the segment boundary is
  the whole signature. Over the three transcriptions whose word data
  still exists: Lied D 2 merges, Woah-oh 1, Lied S 0. Exactly the
  known cases and nothing else.
- **"amen" in the English list.** Measured: 182.140-182.249, so 0.11 s,
  confidence 0.032, in a segment of its own, 2.1 s after the singing
  stopped and with five seconds of fade-out still to go. It stayed
  because the broad check demands at least two core words (B285) and
  "Amen" is one, so only the fixed list could still catch it. Safe to
  ship because since B337 the test looks at the position in the lyrics:
  a song that really sings "amen" there keeps it.
- **Repaired by hand on request.** The `timing.json` of Lied D has
  been updated at the user's request instead of having the timing
  redone: only lines 1 and 20, the words redistributed over the two
  sung halves with the same calculation as B347, leaving the start and
  end of the line untouched. That is not code, but it is noted here
  because the file thereby differs from what v0.105 would have
  produced.
- **Still open from the Lied D analysis.** **B343** - words of twenty
  milliseconds with a confidence of 0.004 must not be a sentence start.
  Measured: of the 270 words eleven are shorter than 0.06 s, and they
  fall apart into five ghost words with confidence 0.000-0.006 and six
  ordinary short words with 0.11-0.95. Four of those five became a
  sentence start (they happen to sit on the line transition) and one
  demonstrably cost a correction of 2.11 s. **B344** - a gap in the
  middle of the song. A coupling item of 0.30 s where the same line
  lasts 1.81 s elsewhere, after which the line is glued against its
  predecessor while the singing only starts 4.1 s later. B330 cannot
  reach it (`_SNAP_MAX_S` is at 1.5 s) and B336 works only AFTER the
  last anchor. Of the fifty coupling items two were shorter than 0.6 s
  and those two were both moved by hand.

Included in v0.107.0:
- **B348 - the yardstick measured the wrong thing again, and that came
  first.** Measuring B343 did nothing, and that turned out to be right:
  the tool copied `original/segmenten.json` to the cache position, but
  that file is written by `whisper.write_outputs` before the forced
  alignment, while `save_segments` fills the cache after it. The app
  couples on the cache. Raw against aligned, measured on Lied D:
  "Lightning" 10.660 against 11.201, "magic" 12.380 (confidence 0.034,
  straight through the pause) against 14.905. Whisper's raw word times
  join up within a segment; the aligned ones have gaps where nothing is
  sung. The measurement took the worse of the two. Now the cache wins
  where it still exists, with fallback to the copy where it was emptied,
  and a "source" column saying per project which it was. What that alone
  does: Lied S 4.06 → 0.72 s, error on untouched lines 0.65 → 0.01;
  Lied D 2.18 → 2.00 with 0.51 → 0.07; Woah-oh 4.16 → 5.14 on the
  moved lines but 0.58 → 0.12 on the rest, and 51 → 54 coupled
  sentences. Six of the nine projects are still on the raw copy because
  their cache was emptied; those numbers are too high and not comparable
  with the other three. This is the third time the yardstick itself was
  the fault (after B333 and B338), and the pattern is always the same:
  the tool ran the code slightly differently than the app does.
- **B343 - ghost words of twenty milliseconds.** Of the 270 words in
  Lied D, eleven are shorter than 0.06 s. They fall into two groups
  with a wide gap between them: five with confidence 0.000-0.006 ('I',
  'I', 'I', 'of', 'I') and six ordinary short words with 0.11-0.95 ('a',
  'it', 'of'). So duration alone says nothing - 'a' of 0.040 s scores
  0.952 - and confidence alone says nothing either; the two conditions
  together do separate them. They hurt because they sit exactly on a
  line boundary, where the coupling takes the first word as the start of
  the sentence: four of those five did become a sentence start, and one
  put line 2 at 16.446 while the singing starts at 18.556 - 2.11 s the
  user had to correct by hand. They disappear in the same read path as
  B334 and B342. Measured on the same input: weighted 3.69 → 3.19 s,
  Woah-oh 7.75 → 5.14, Lied D 2.13 → 2.00, and on Lied D's
  untouched lines 0.04 → 0.07 (negligible).
- **B339 - line markers in the coupling editor.** Every word already
  carried its line number in the display data, but it was never drawn
  anywhere. Under the lyrics row there is now a thin tick with the
  number beside it at every line boundary. The trigger was the remark
  that the end of a repetitive song reads like "a record with a
  scratch": if the same four words sit under each other eight times,
  there is nothing to hold on to without a marker.
- **B340 - crowded anchors, with an honest outcome.** A run of three or
  more anchors sitting less than half a phrase apart cannot be right in
  its entirety; only the outer two stay anchors, the rest become an
  estimate in between. Deliberately on a RUN and not per pair, because
  the crude per-pair variant was already tried during v0.102 and was
  worse. And to be honest about the yield: across the whole reference
  set such a run occurs exactly once (Lied S, one anchor) and not a
  single number changes. What the measuring did turn up is an
  uncomfortable fact: `phrase_period` returns `None` for **seven out of
  ten** projects. So the whole B332 mechanism is off more often than it
  is on. That is not a bug - it switches itself off when it is not sure
  - but it does say that the phrase period rests on a narrower base
  than it looks on paper, and that B340 is therefore largely sleeping
  machinery.
- **B344 was built, measured and removed again.** The idea: a line that
  after structuring ends up in a gap in the middle of the song (no
  anchor, no singing) may travel further than `_SNAP_MAX_S` and go to
  the next vocal onset. Exactly the case of Lied D line 43: estimated
  at 154.86, glued against its predecessor, while the singing only
  starts at 158.96. Measured, it made the weighted figure worse: 3.19 →
  3.29 s at a threshold of 1.5 s of silence and 3.21 s at 3.0 s. Lied
  S paid a full second for it (0.72 → 1.62) and Lied D itself did
  not even change. So out it goes, like the "fill" branch of B332 back
  then. The problem is still there: a gap in the middle has no safety
  net at all, because B336 only works after the last anchor and B330
  reaches just 1.5 s. A next attempt should not grab the next onset but
  look at the structure of the vocal windows in that gap, the way B336
  does in the tail.

Included in v0.108.0:
- **B351 - the start behind a pause.** The trigger: on a new project
  the user had to adjust a lot of lines forward, and remarked that it
  was mostly about lines with nothing sitting just before them.
  Measured on "Lied C": of the 48 lines he moved
  seven by more than 0.3 s, **all seven forward and all seven behind a
  pause**, while of the 23 lines that join straight onto their
  predecessor he touched none at all. Average error behind a pause
  0.29 s, on a joining line 0.04 s - a factor of seven. The cause lies
  in what an anchor is: the word start from the forced alignment, and
  that sits a median 0.19 s after the onset of the voice, while the
  user puts the line a median 0.12 s before that onset. B330 cannot
  reach it, because a measured line is deliberately never moved - that
  is the rule that keeps a good line from being ruined. There is now
  exactly one exception: if there is a pause of at least a second
  before the line, the start may go back to the last vocal onset in
  that silence, but only if the anchor sits at least 0.25 s behind it.
  That threshold lies in a measured gap: the lines the user left alone
  sit 0.10-0.23 s behind their onset, the seven he corrected
  0.29-2.36 s. Backwards only, never further than 1.5 s and never
  past the end of the previous line, and the end of the line stays
  where it is.
- **B351 - why the figure over the whole set stays flat anyway.** On the
  four projects whose cache still exists (so where the measurement runs
  on the aligned input, see B348) Biertje goes from 0.71 to 0.39 s,
  Lied D from 2.00 to 1.98, and Lied S stays at 0.72. On the six
  projects whose cache has been emptied, and which are therefore
  measured on the raw transcription, the rule costs 0.2 to 0.3 s on
  lines the user had not touched. So as not to have to take that on
  faith, a controlled trial was run: same song, same rule, only the
  input differs. Aligned cache: 0.39 s on the moved lines, 0.08 s on the
  untouched ones. Raw copy: 0.39 s on the moved lines, **0.37 s** on the
  untouched - well over four times as much damage. That makes sense too:
  the whole reason for B351 (the anchor sits behind the onset) is a
  property of forced alignment, and in the raw word times the words
  simply join up within a segment. So the rule is good and the six rows
  that get worse are measuring input the app never gets. As soon as
  those projects are transcribed again their cache comes back and their
  row is right again.
- **B350 - reporting what was heard but does not appear in the text.**
  The trigger was a set of lyrics pulled off the internet in which a
  repetition had dropped out in three places at "shalalie shalala": the
  singing does the pair twice, the text had it once, and the coupling
  hung that one pair on the second sung pair - which made the karaoke
  line appear on screen 1.35 to 1.49 s too late. The tool already knows
  both sides, so it is in a position to say so. The test: a found word
  without a coupling, not filtered out as a hallucination, with
  confidence 0.5 or higher; adjacent words count as one case. If that
  same word does appear in the lyrics at that spot (phonetic similarity
  0.9 or higher) it is a **missing repetition** and the line is named
  with it; otherwise it is called unknown text. That 0.9 is deliberately
  high: "Collections" against "reflections" scores 0.80 and that is a
  misheard word, not a missing repetition. Measured over four projects
  it yields 0 to 8 reports per song, and on the project it was meant
  for exactly the three places - and zero once the user had updated his
  text. Deliberately no pop-up: it is a tip and not an error, and with
  a repetitive outro there will always be a handful of them. One
  report per lyrics line goes in the message field, the details go in
  the log file.
- **B349 - the percentage was there twice.** The progress bar already
  shows "20%" itself and the text next to it said it again in weaker
  form ("Voortgang: 20% (12 / 60 s)"). The text now keeps only the
  seconds. Two lines in `translations.py`, no code: the call still
  passes `pct` and an unused key in `format()` does nothing.

Included in v0.109.0:
- **B352 - the yardstick did not pass on the vocal windows.** While
  building B344 nothing happened, and the reason again turned out to sit
  in the tooling: `pipeline.generate_timing` calls `sanitize_timing`
  with `active_windows=_vocal_windows(context)`, but
  `tools/timing_regression.py` left that argument out. So everything
  that leans on those windows was never measured. That explains in
  retrospect the sentence from v0.104 that "B334, B336 and B337 change
  not a single number": B336 could not move along, because the
  measurement gave it no windows. Passed on now. The weighted figure
  stays at 3.11 s; only Lied B goes from 1.24 to 1.27 s
  on the untouched lines. Fourth time the yardstick itself was the fault
  (after B333, B338 and B348), and always with the same pattern: the
  tool ran the code just slightly differently than the app does. A test
  now demands that the call in the tool contains `active_windows`.
- **B344 built, measured and removed a second time.** The first attempt
  (v0.107) grabbed the next vocal onset and was measurably worse. This
  attempt followed the recipe of B336: a gap between two anchors is
  filled with the vocal windows that lie entirely inside it, each window
  carries as many lines as it is phrases long, and it only happens if
  those windows carry exactly the required number of lines - "better
  nothing than a confident mistake". Outcome of the measurement: across
  ten songs there are 32 anchor pairs with estimated lines between them,
  and the rule fires **once** (Lied B), with an outcome
  that is 0.03 s worse. And with a more forgiving period estimate as
  well (the median anchor spacing instead of `phrase_period`, which
  returns nothing for seven of the ten projects) nothing changed
  either.
- **What the measurement laid bare along the way, and that is the real
  yield.** Of the ten songs exactly one reaches the tail rule of B336
  (Lied S), and that one places nothing either. So B336 fires **zero
  times** across the whole reference set. The window approach - the
  whole-number-of-phrases test - is too strict to come into play in
  practice, and at the same time gaps between anchors are far rarer than
  the Lied D case suggested: 32 out of more than 400 anchor pairs.
  Anyone working on this further would do better to start there than
  with a new distribution rule: first measure whether the case you are
  building for occurs in the reference set at all. The case that
  prompted B344 (Lied D line 43) yields neither a reliable phrase
  period nor windows that fit, so neither variant can ever touch it.

Included in v0.110.0:
- **B353 - the video stays.** The rendered video was declared invalid as
  soon as anything upstream changed. The mp4 file was never deleted, by
  the way: `video` sits in the chain as a STEP and not as a FILE, and
  only file items go from disk. What did disappear was the bookkeeping -
  which file it was and with which audio source - and because of that
  the app had forgotten there was a video after a restart. `video` now
  deliberately hangs under nothing, in the same company as
  `display_name`, `input_names` and `video_titles`. There is a guard
  test demanding that a derivative without a source is an explicit
  exception (the B311 family); that list has been updated, because that
  is exactly where such a decision belongs. Consequence you need to
  know: the "Open video" button can now point at a stale render if you
  change the timing afterwards. That is the intended trade - stale is
  something other than invalid, and that judgement is the user's.
- **B354 - asking instead of overwriting.** The file name is
  `<titel>.mp4`, with a suffix since B271 for a deviating combination of
  music and text. With the same combination the render simply wrote over
  it without asking. Now it checks up front whether the file is already
  there, with three answers: overwrite, keep both, or cancel. With "keep
  both" the NEW render gets the sequence number (`<naam>_2.mp4`, then
  `_3`), at the user's request - that way nothing is ever done to an
  existing file. Technically the naming has been lifted out of
  `run_video` into `video_target`, so the GUI can work it out before
  rendering starts, and `run_video` now accepts a target path from the
  caller.
- **1.5. Cache vullen (fill cache, temporary).** Five projects have
  manual timing but no transcription cache any more, so for those
  projects the tool measures on the raw transcription from before the
  forced alignment (B348) - which the app never gets to see. Running
  "1.1. Detecteer woorden" again fixes that but destroys the very reason
  those projects are valuable: the cleanup chain removes `word_coupling`,
  `coupling`, `lyrics`, `karaoke` and `timing`, including the file
  `settings/timing.json`. This button therefore walks exactly the path
  from `detect_track` up to and including `save_segments` and stops
  there: no `set_step`, no `invalidate`, and the diagnostic files go to
  a temporary folder so that `original/segmenten.json` stays untouched
  as well. It looks up the projects itself - ever transcribed, no cache
  left, audio still present - shows that list and asks for confirmation.
  A test demands that this function contains no `set_step` or
  `invalidate` - that is the whole agreement. May go as soon as the
  reference set is complete again.

Included in v0.110.1:
- **1.5 tripped straight away.** Reported by the user: `Transcriptie
  mislukt: 'Event' object is not callable`. The cause was in the log
  file: `whisper.transcribe` wants a *function* for `cancelled` that
  returns `True` when it should stop, and the new button passed the
  `threading.Event` itself. The existing detect button does it right
  (`cancelled=cancel.is_set`), so this was purely a deviation in new
  code. There are now two tests: a functional one checking that what
  gets passed is callable, and one that pins down the call in the
  button itself - the second is the one that would really have caught
  it, because the fault was not in the pipeline function but in the
  caller.
- **Two at a time.** At the user's request two projects now run
  alongside each other, in the same shape as the parallel detection of
  B90: plain threads over the shared model cache of `whisper.py`. Two
  side catches that are just as worthwhile: a project that trips no
  longer aborts the whole run but is named separately at the end, and
  the projects with a hand-corrected `timing.json` are at the front of
  the queue - stop halfway and exactly the projects that give the
  measurement its value are done.

Included in v0.111.0:
- **Button 1.5 has become a panel.** The single "Cache vullen" button is
  action 1.5.1 in a checklist of ten numbered test functions, so it can
  be referred to in conversation ("run 1.5.3 for a moment"). The numbers
  belong to the action and do not shift if something drops out. Three
  agreements that hold for all ten and have tests on them: the boxes are
  ALWAYS unchecked when the panel opens (a forgotten tick on the
  ablation trial costs half an hour), every action looks at `cancelled()`
  in its loop so the Stop button works, and an action that trips does
  not stop the rest. The panel writes nothing to the projects, with two
  exceptions that say so in their own description.
- **Everything is marked as temporary, and that is guarded.** A new
  section "Decide before release" in this document, with per item what
  it is, why it is there and which question has to be asked at a
  release. A test searches `modules/` and `tools/` for files with a
  `TIJDELIJK` marker and demands that each of them is named in that
  section. Trigger: B136 was such a temporary button too (v0.65, removed
  in v0.78) and its removal was more luck than judgement - it was
  nowhere on record as an open decision.
- **The ordering question has been answered: no.** All six orderings of
  the three read-path filters give exactly 3.37 s - not approximately,
  equal to two decimals. The ablation trial explains why: of the nine
  checks only two contribute measurably (ghost words +0.47 s if you take
  them out, the anchor test +0.26), snapping and energy placement
  together +0.14, and B334, B342 and B336 yield **nothing**. If only one
  read-path filter does anything, their relative order can by definition
  make no difference. Combining makes no sense either: leaving out ghost
  words and the anchor test together costs +0.75 against +0.47 and +0.26
  separately, so they add up and do not get in each other's way.
- **What a score would yield, and why not now.** Switching off
  everything that does something costs +2.33 s, but not evenly: Lied S
  goes from 0.72 to 20.55 (the machinery is what keeps that song
  standing) while Lied P actually improves from 4.11 to 2.94
  and Lied T from 7.13 to 6.44. So the same checks are
  worth twenty seconds on one song and cost a second on another; a
  yes/no filter cannot express that difference and a weight can. That is
  the only argument for a scoring model - but it is about a second or so
  on two songs, while 89% of the error sits in four songs with their own
  identifiable problems. So not now.
- **The real find: repeated lines.** In Lied N lines 20 to 22 are
  exactly right and lines 23 to 26 - the same four texts once more - are
  +2.16, +3.09, +3.62 and +6.68 off, increasing. All of them at quality
  `high`: the coupling was certain and hung the repetition on the audio
  of the previous time. Split across all eleven projects: **0.48 s on
  unique lines against 1.89 s on repeated ones**, and for Lied N
  0.63 against 4.86 and for Lied P 0.56 against 4.17. Those two
  together carry half of all the error. This is B148, open since v0.58
  as a subclause ("with many repetitions the coupling sometimes picks
  the wrong source position") and now measurably the largest item on the
  table. It is not a timing problem - no rule in `sanitize_timing` can
  straighten out a sentence that hangs on the wrong place in the audio -
  so the next work belongs in the sentence coupling, with a design round
  of its own. Action 1.5.8 keeps track of that figure from now on.
- **B355**: the heading "Lied-project" carried the explanation
  "(projectnaam = songtitel; elk een eigen project)" with it. Gone; the
  manual already explains it.

Included in v0.112.0:
- **B356 - Stop now really stops.** The user pressed Stop and nothing
  happened for minutes. Two causes. The first: `measure()` looks at the
  abort signal nowhere, so a running project had to finish completely.
  The second and nastiest: an external program listens to nothing at
  all. `subprocess.run` waits until it is done, so a three-minute Demucs
  separation finished those three minutes however hard you pressed.
  Everything now goes through one door, `proc.run`, which registers the
  process while it runs; `proc.terminate_all()` shoots them down. The
  Stop button first makes the polite request and five seconds later sets
  `_stop_hard()` on it, which only shoots if the task is still running
  then - a just-finished abort must not take down the programs of a NEXT
  run. The video render cannot go through that door (it pumps frames
  into ffmpeg's stdin itself) and therefore registers separately.
- **B356 - and with it the cmd windows.** While testing, windows were
  flashing across the screen. All subprocesses of the app itself had
  been in order since B89; the exception was `_vocals_into_cache` in the
  yardstick, which called `ffmpeg` bare. That never showed because it
  was a command-line tool, but since 1.5.7 it runs from the GUI: one
  window per project, so eleven for the yardstick and eighty-eight for
  the ablation trial. A side problem of that same line: it looked for
  `ffmpeg` in PATH only, while the app also looks in its own folder and
  in the setting, so on another installation 1.5.7 simply did not work.
  Now via `ffmpeg.resample_to_match`. A test scans `modules/` and
  `tools/` for `subprocess.run`/`Popen` outside `proc.py` and turns red
  as soon as another bare call appears.
- **B357 - the test panel uses both lines.** Two complaints with the
  same cause: the bars stayed on "1.5.1" and "1.5.2" while those steps
  were long past, and only 1.5.1 spread its work over two workers. The
  bars were set once and never touched again; the progress went to the
  message field. There is now a shared distributor `over_projecten()`
  that farms every per-project action out over the two workers. Each
  worker reports through a signal (you must not touch a Qt widget from
  a worker thread) which project it is on; the panel puts that as a
  label above its own bar and lets the bar run from zero up to the
  number of projects. Three things come with that for free: the abort
  is checked between every project, a project that trips no longer
  stops the rest but yields a line in the result, and the result comes
  back in project order even though the workers run through each
  other.

Included in v0.113.0:
- **B358 - the big trial (1.5.11).** The ablation trial of v0.111.0
  answered one question ("what does it cost when this check goes off?")
  and left three others lying: where does a model come into its own, do
  two models work on the same lines, and does the order matter? Action
  1.5.11 does all four in one overnight run and writes
  `docs/modelmatrix.md`. Seven sections: the baseline with the error per
  project, each model switched off on its own, per model the project
  where switching off costs the most and where it does harm, the pairs,
  the orderings, the coverage of the word coupling and the word level.
  After **every** variant the report is written out - a hang at three in
  the morning must not throw away the whole night - and between every
  variant the Stop button is checked.
- **B358 - the word coupling counts too.** Until now every measurement
  was about the times, while the largest open item (B148) sits in the
  *coupling*. The coupling has therefore become a level of its own in
  the matrix, beside block and sentence: the two hallucination rounds
  (B258/B285 and B307/B337), the separate filler-word round (B213) with
  its precedence rules (B276), detaching a weak tail (B159), the manual
  couplings (B121) and the energy placement (B313) - that last one used
  to sit under "sentence" and now has its own place, because measuring
  twice gives two truths.
- **B358 - coverage instead of error.** Two couplers run only in the
  coupling window and not in the times: B191 (a chopped-up word put
  back together) and B228 (the creative 2-to-1). The yardstick by
  definition does not see those, so they would give a table of zeroes.
  They get their own measure: how many text words end up with a
  coupling, how many of those multiply, the median similarity, and
  what is left lying (energy-placed, gap in the transcription,
  filtered out, filler word, no match). More coverage at equal
  similarity is a gain; more at a lower one is a model that guesses.
- **B358 - two orderings that could matter.** For the read path it had
  already been measured that order does nothing (all six permutations
  exactly equal); for the coupling that had never been looked at. The
  trial now also runs "B307 before B285" (first the place-aware
  hallucination round, then the song-wide one) and "B313 before B121"
  (first a time from the voice, then the manual couplings over it). Zero
  difference means the code is free at that point; that is a result too.
- **B358 - the night does have to finish.** All pairs of seventeen
  models is one hundred and thirty-six times the whole reference set,
  and the ablation trial showed that half give exactly 0.00 alone. So
  only models worth at least 0.02 s on their own go into the pair
  work, and WHICH were skipped is in the report itself - a silently
  shortened table reads as "everything measured" while it is not.
- **B358 - guards on the stand-ins.** The trial works by temporarily
  overwriting real functions, and that goes silently wrong as soon as
  someone adds an argument or renames a function: the fault then falls
  an hour later, in the middle of the night. Three tests catch that:
  every target must still exist, every stand-in must be able to handle
  the required arguments of the original, and every stand-in must
  swallow the optional arguments too. A fourth test crashes the trial
  halfway on purpose and demands that all the real functions are back in
  place afterwards - if a stand-in stays behind, not only the next
  measurement but the program itself runs on fakes.

Included in v0.114.0:
- **B359 - the GUI could die silently.** The user started 1.5.9, nothing
  happened any more, and there was no CPU activity. The log ended with
  "GUI: 1.5.9 draait: Whisper-venstertest" and then nothing: no error,
  no next action, no completion. That is the nastiest kind of failure,
  because there is nothing to see - and that silence was exactly the
  trail. The chain: `whisper_probe.zangstem()` reported a missing vocal
  track with `SystemExit`, which is exactly right for a command-line
  program but not for a function the app calls. `SystemExit` inherits
  from `BaseException` and not from `Exception`, so it slipped through
  all three safety nets that say `except Exception`: the action itself,
  the loop over the actions in `_do_fill_cache`, and `_Worker.run`. That
  last one is the fatal one. If `run()` crashes on a `BaseException`,
  none of the three signals (`done`, `failed`, `cancelled`) is sent, and
  those are what set `_set_busy(False)`. So the window stayed on "busy"
  for good while literally nothing was running any more - hence zero
  CPU. Stop did not help either: the hard stop from B356 checks whether
  the task is still running, and it was not. The program had to be
  closed, and 1.5.10 and 1.5.11 were never started.
- **B359 - the repair in three places.** The last safety net in
  `_Worker.run` is now `BaseException`: better an ugly message than a
  dead window, no matter which action causes the fault. This is the most
  important of the three, because it also covers everything that gets
  added later. `zangstem()` now raises a plain `FileNotFoundError` and
  `main()` translates that into an exit code - the distinction between
  "library function" and "command-line program" belongs in `main()` and
  nowhere else. And 1.5.9 checks up front whether a project has been
  chosen at all. A guard test walks `modules/` and `tools/` with the AST
  and turns red as soon as another `SystemExit` appears outside a
  `main()`.
- **B359 - why right now.** After the restart the current project in
  `config/config.json` was empty. 1.5.9 is the only one of the eleven
  actions that works on the CURRENT project instead of on all projects,
  so it was also the only one that could trip over this: with an empty
  title the lookup path became `cache\` instead of `cache\<lied>\`, and
  there is no `vocals.wav` there. All ten other actions run over the
  project list and noticed nothing.
- **B359 - the radio buttons did nothing.** While working this out it
  turned out that the two radio buttons at the bottom of the test panel
  ("Alleen dit project" / "Alle projecten") were read nowhere; the same
  went for the `alle_projecten` flag per action. Every action simply got
  the current context and ran over all projects. They work now: the
  runner sets the scope afresh on every run (so a choice from last time
  never lingers) and `_projecten()` then yields only the chosen project.
  If no project is selected, a proper message comes up instead of an
  empty round.
- **B359 - the label stayed put.** An action that reports no progress
  itself (1.5.9 has no row of projects to walk) left the name of the
  previous action above the bar. That reads as a hang, and in this case
  it was one - but it must not be the case that you cannot tell from the
  screen what is going on. The runner now moves the label of both bars
  as soon as an action starts.

Included in v0.115.0:
- **B360 - 1.5.10 tripped over the reporter.** In B357 the reporter got
  a different shape: from `melden(naam)` to `melden(plek, naam, klaar,
  totaal)`, because every worker got its own bar. All actions came
  along, except `weglaatproef`, which kept the old shape in one place
  and so fell over on its very first variant with a `TypeError`. The
  variant name now goes to the first bar; the yardstick underneath
  already spreads its projects over both workers itself.
- **B360 - why 827 tests did not see this.** That is the real lesson,
  and it is bigger than the bug. Two things still pointed at the old
  contract. The type annotation at the top of `test_panel.py` still said
  `Callable[[str], None]` - the shape from before B357 - which meant
  EVERY action in that file was annotated with the WRONG contract. A
  type annotation that is wrong is worse than none: it actively points
  the next reader the wrong way. And the tests called the actions with
  `lambda _t: None`, a reporter with one argument. So the test confirmed
  the old contract instead of the real one and COULD not find this bug.
  On top of that, `test_rapporten_draaien_op_een_leeg_project` only
  walks 1.5.2 to 1.5.5, and those four are precisely the ones that never
  call the reporter.
- **B360 - three guards instead of one repair.** There is now one
  reporter in the tests with exactly the shape of the runner,
  deliberately without `*args` - a reporter that swallows everything
  would hide this bug. A test reads the reporter out of `_do_fill_cache`
  with the AST and pins its argument names to those of the test, so that
  a next change of shape makes the tests fall over instead of one
  forgotten action showing up. A second walks `test_panel.py` and
  `gui.py` and turns red as soon as `melden()` is called anywhere with
  fewer than two arguments. And a third runs all ELEVEN actions with
  that real reporter, instead of the four that happen never to report.
- **B360 - "hung" has come to mean something else.** Since B359 a hang
  is a different failure: a dead window without a message. 1.5.10 did
  not hang, it fell over after twenty-eight milliseconds. The messages
  now say "tripped", so that the text points the right way when you
  search.
- **B360 - the time estimates were wrong.** Measured on the reference
  set, the full yardstick takes 8.5 seconds over eleven projects, and
  1.5.1 to 1.5.9 together 41 seconds. The ablation trial was listed as
  "reckon on half an hour" and is in reality a few minutes; the big
  trial was listed as "an overnight job of hours" and is more like
  half an hour. Checked as a control whether work was being skipped
  somewhere: it is not. No action reads back an earlier result,
  `measure()` makes a fresh temporary folder per project per run, and
  the energy cache in `rhythm` hangs on path + modification time +
  size, so a changed file is always a different key. Only 1.5.1 skips,
  and that is its job.

Included in v0.116.0:
- **B361 - the model register.** Twenty ideas built into the timing and
  the coupling over the course of a hundred versions were nowhere
  together; what was known about each of them sat in temporary test
  code. That is now `modules/model_register.py`: per model a B number, a
  name, a level, a neutral stand-in and a STATE. That makes the user's
  rule executable - a model that turns out to be worth nothing goes
  **off and not away**, because the idea behind it is usually good for
  something somewhere. Switching off happens centrally with the same
  substitution table the ablation trial has used since v0.111.0, once at
  startup, and every disabled model logs itself with name and reason.
  The alternative shape - an `if` at every call site - would mean twenty
  places in five modules, each with its own idea of what "neutral" is;
  one table that both the app and the measurement read cannot get out of
  step, and getting out of step was exactly what B360 was.
- **B361 - and the matrix became symmetric.** The trial reads that same
  register. For a model that is ON it measures what switching it off
  costs, and for a model that is OFF what switching it on would yield.
  So a disabled idea keeps running along every time and reports itself
  as soon as it is worth something on new songs. The state also goes
  into the derivation chain (B311) and into the settings: a different
  model means a different timing, and then the derivatives should lapse.
- **B361 - B213 goes off first.** The big trial pointed at it as the
  only model that demonstrably DOES HARM on the reference set: -0.13 s
  on its own, and together with B343 off even 0.23 s below the baseline.
  All five combinations that scored better than the baseline contain it.
  The eight models that give 0.00 deliberately stay on: the pair work
  showed that the anchor test and the energy placement off together give
  5.66 s where 3.66 was expected, so a model that does nothing on its
  own can be a safety net that never had to catch on these eleven songs.
- **B362 - the measurement history.** Per action, project and version
  what was measured is kept, in `docs/testhistorie.json`. That lets a
  project unchanged since the previous run be skipped, and a new
  version puts its figures next to those of the previous three, so
  that a regression becomes visible in the report itself instead of in
  someone's memory. The key is deliberately more than the version: a
  version says something about the CODE and not about the DATA, so
  every entry also carries a fingerprint of the project files, the
  transcription cache and the disabled models. Change the data or a
  model and it gets measured again by itself. An "opnieuw meten" tick
  at the top of the panel ignores the memory if you want to force it.
- **B363 - word and syllable tests.** At syllable level there is no
  manual truth: dragging a line scales the syllables along linearly, so
  those times are a CONSEQUENCE of the model and not a judgement on it.
  There is something to measure anyway, and the sharpest thing had been
  lying unused for months: the forced alignment puts a start and an end
  on the voice per word, independent of the syllable model, and those
  times are simply in the transcription cache. A syllable that runs past
  such a MEASURED word boundary is demonstrably wrong. Beside that,
  tests on the shape (order, overlap, gaps within a word, a syllable of
  eight milliseconds, more than nine syllables per second, a held
  syllable that is not the last), on the audio (without duration, in a
  measured silence, distance to the onset) and on itself: a line that is
  sung twice should have the same rhythm internally, and that needs no
  truth at all. All four measure consistency and not correctness; tuning
  them takes a small piece of handwork, and for that the timing editor
  first needs a handle on an individual syllable. That stands as an open
  point.
- **B364 - faster, without more workers.** The processor was not being
  fully loaded, and that was not down to the number of lines.
  `measure()` made a fresh temporary folder per call and put the voice
  track in it again, so ffmpeg ran for every project on every variant
  - in the big trial some one hundred and ninety times the same work,
  and that is waiting time. The converted voice track is now kept once
  per project and copied with `copy2`, so that the energy cache in
  `rhythm` does not end up on a new key every time either. On top of
  that the yardstick was read in and executed again per variant; that
  now happens once. And the last two sections of the trial (coupling
  coverage and word level) ran with a plain loop over the projects and
  so used only one worker - those now go through the same distributor
  as the rest. The number of workers stays at two, on request.
- **B365 - at most ten actions under 1.5.** A list that only grows
  becomes unreadable, so there is now a ceiling of ten and small tests
  get merged. The text, filter and structure reports were three separate
  actions that all three pull a line per project out of the same files
  and together take less than a minute; those are now one action
  "Projectcontrole". That made room for the new word and syllable tests.
  Consequence: the numbering has been laid out again, and "run 1.5.7"
  means something different than last week. The yardstick is 1.5.5, the
  ablation trial 1.5.9 and the big trial 1.5.10.
- **B366 - all pairs, without a threshold.** In v0.115.0 only models
  worth at least 0.02 s on their own went along. That pruning was
  wrong, and the table under it proved so: the anchor test and the
  energy placement off together gave 5.66 s where 3.66 was expected
  from adding them up. A model that does nothing alone can be a safety
  net, and you only see that in combination. Measuring everything
  costs half an hour at eight seconds a run, and that is worth it.
- **B366 - and the similarity column works again.** In the coverage
  table it stood at 1.00 everywhere: the median was saturated and so
  blind to exactly the question the column was meant for - does a model
  couple MORE but worse? It now shows the NUMBER and the SHARE of
  couplings below similarity 0.75, plus the lowest. More coverage at an
  equal weak share is a gain; more coverage with more weak ones is a
  model that guesses.
- **B367 - the 'all' button.** At the top of the panel, and it toggles:
  everything on, clicking again is everything off, with a caption that
  moves along. The rule that nothing is ticked when the panel OPENS
  stays - this is a deliberate click and not a state that lingers.

Included in v0.117.0:
- **B368 - the second counter got stuck.** The user saw "1.5.10
  draait... 361 s" standing there while the trial still had half an hour
  to go. The counter only refreshes as long as there is no real
  percentage to show, and it derived that from
  `self._progress.maximum() == 0`. Except: that bar IS
  `self._progress_bars[0]`, the first test bar. As soon as the yardstick
  reported per project that put `setRange(0, 13)` on exactly that widget
  and the counter fell still; between variants it briefly went back to
  zero, so now and then it still jumped along until a tick no longer
  fell in that window. Hence a number that first seemed to run and then
  did not. The counter now keeps its own state instead of deriving it
  from a widget that has belonged to someone else since B357. There is a
  test pinning down that the shared bar is still shared - if that ever
  comes apart, that test may fall over and the own state can go again.
- **B369 - the result appears immediately.** The runner collected all
  the results and only logged them when the whole run was done. With
  single tests that does not show, but with 1.5.10 of twenty-eight
  minutes on the tail the user sat waiting half an hour for figures that
  had been ready all along - and on a crash everything was gone. Now
  every action writes out its result as soon as it is finished, and in
  two directions: straight to the LOG FILE from the worker thread (that
  is the part that survives a crash, because a signal to the window is
  still in the GUI thread's queue at that point), and through its own
  signal to the log window. `_log` has been split for that, otherwise
  every line would stand twice in the file.
- **B370 - the duration in the measurement history.** Per project with
  the result that is kept anyway, plus one line per action per version
  for the total duration. Without it a run is gone within a week,
  because only five log files are kept. Deliberately NO message in the
  program itself: the number is kept, and whether something moves to
  1.5.11 is a question I ask when I look at the data. The first seven
  numbers come straight from the v0.116.0 log: the ablation trial at
  134 s and 1.5.10 at 1673 s (twenty-eight minutes, just within the norm).
- **B371 - 1.5.11, the heavy bin.** The ceiling of ten still holds for
  the ordinary work; anything that takes longer than half an hour goes
  here. It NEVER takes part in "Alles aanvinken" - hours of computing
  should be a deliberate choice, even when you mean "everything" - and
  it disappears from the list entirely if there is no investigation
  under it: no empty line, no greyed-out button. Every investigation has
  its own version threshold (twenty by default) and skips itself until
  that is reached; the "Opnieuw meten" tick forces it anyway. For that
  threshold the middle version number counts, so that a repair release
  like 0.110.1 does not count as a version of its own.
- **B371 - clusters instead of exhausting.** The user worked out that
  seventeen models give 2^17 = 131,072 combinations; at eleven seconds
  per measurement that is over four hundred hours. That is not needed,
  because most models do not touch each other. Of the one hundred and
  thirty-six pairs in the matrix, nine show a real interaction, and they
  fall into two clusters: six models around the anchors and the
  hallucination filter, plus the pair B343/B213. Nine of the seventeen
  touch nobody. Within each cluster ALL combinations get measured - 2^6
  + 2^2 = 68 measurements, about twelve minutes, with exactly the same
  knowledge. The clusters come from the report of 1.5.10 and are not
  measured again; if that report is missing, the trial says 1.5.10 has
  to run first instead of betting on one big cluster.
- **B371 - searching instead of inventorying.** Anyone who wants to know
  the best state does not have to complete the map. From the current
  state, keep taking the switch that yields the most, until nothing
  helps any more; that is about 153 measurements to a local optimum, and
  a few restarts from a random state cover the risk that the climb ended
  on a lower hill. The run is repeatable with a fixed seed, otherwise
  the same measurement gives two answers.
- **B371 - and the most important step: holding songs back.** With
  131,072 possible states and 188 moved lines across eleven songs, a
  thorough search is guaranteed to find something that scores well by
  chance. That is not a better model, that is noise that has been picked
  out, and the more thoroughly you search the more certainly you overfit.
  Three songs therefore stay OUT of the search and count only at the
  check. If the gain there is less than half the gain on the search set,
  the report says overfitting is in play.

Included in v0.118.0:
- **B372 - the window trial did not even start.** The user ran
  `tools/whisper_probe.py` and got a `TypeError` out of ctranslate2
  straight away. The tool converted `device: "auto"` itself, with a
  rule of its own that passed `None` in that case - and ctranslate2
  wants a string. The app has done this right for years with
  `_resolve_device()`, which turns `"auto"` into `cuda`/`cpu` and the
  compute type into `float16`/`int8`; the tool did not use it but had
  its own version, which never grew along. Exactly B360's pattern:
  knowledge kept twice gets out of step. Now via the app.
- **B373 - the lyrics decide on a boundary doubling.** The measurement
  first, because it changes the question. Across fourteen projects and
  347 segment boundaries the FINAL WORD of a segment is on average 0.42
  certain against 0.70 for every other word, and a third of them sit
  below 0.30. That is by construction and not bad luck: on a window edge
  the decoder has no right-hand context left, so the closing word is a
  guess. That is where the doublings and the extra words come from. B342
  stacked four thresholds on it (gap, duration, certainty, similarity)
  and caught five of the twenty-two cases with them; the real catches
  lay just outside - `so`/`so` tripped over a certainty of 0.36 against
  a limit of 0.30. The lyrics solve that without a single threshold: if
  the word is not DIRECTLY doubled in the text, then two identical words
  right after each other are one word that has been cut through. If it
  is there twice, it is the singing. On the real data that holds
  everywhere: in "Lied K" `so`/`so` is now merged (218
  to 217 words), and in Lied P all six `Sunday` pairs stay
  because the text there literally sings "Sunday, Sunday" - including
  the pair with only 0.2 seconds between them, which on the thresholds I
  would have merged wrongly. Without lyrics the old, cautious test still
  applies, because the read path must not fall over on that.
- **B374 - point it out cheaply first, then measure expensively.** 1.5.8
  was the Whisper window test, but it did no more than look up the voice
  track and refer you to the tool. It is now a gap detector: lay the
  word times beside the MEASURED vocal windows and report every stretch
  of five seconds or more where the voice sings and Whisper is silent.
  That costs seconds and starts Whisper not once. Only once you know
  where the gap is is it worth trying eight settings - and that has
  become 1.5.11c, in the heavy bin, with threshold 1 so that it runs
  whenever you tick it. It automatically takes the largest gap of the
  current project. TEMPORARY: as soon as we know which setting wins it
  may go, and then 1.5.11 disappears by itself if there is nothing else
  under it.
- **B374 - what the gap detector shows straight away.** In "Lied K
  " the singing stops at 161.8 s and after that there is still
  `Thank you.` (0.15/0.03), `We'll be right back.` and twice `Just as so
  close to me` at 224-232 s. Those last two are REAL singing - four of
  their words couple at similarity 1.00 - so Whisper picked up only two
  chunks of an outro of over a minute. That is a skipped window, not a
  coupling problem.

Included in v0.119.0:
- **B375 - a `[bg]` line cut its own block in half.** The user did exactly
  what the manual says - put the backing lines that are sung along
  between `[bg]` - and watched the coupling collapse. Cause: the block
  boundary was derived from a GAP in the line numbers, and a `[bg]` line
  drops out of that list because it gets no place of its own in the
  sentence coupling. So a line left out that way produces exactly the
  same gap as a blank line. Measured on "Lied K": the
  lyrics went from 8 to 13 blocks while the karaoke kept 8, and the
  sentence coupling flipped over from 47 high-quality lines to none.
  The manual literally promised the opposite ("does not count towards
  the number of lines per block"). Skipped bg lines no longer count in
  the gap; on the same project, 8 blocks again and 42 high-quality
  lines.
- **B376 - and the warning about it was itself blind.** The structure
  check counted raw lines on the lyrics side (it knows `#` comments, not
  `[bg]`) and ran the karaoke side through the real parser. Two sides,
  two yardsticks: it reported 18 against 12 where the coupling saw 12
  against 12. That is the most annoying kind of report, because you go
  and repair a good file. Both sides now skip `[bg]`.
- **B377 - the singing voice as referee.** We knew three kinds of junk in
  the transcription and tried to tell them apart with text rules:
  invented text ("MUZIEK", "Thank you"), misheard singing, and - newly
  discovered - the PROMPT ECHO, where Whisper simply speaks out the
  lyrics we hand it as the initial prompt during an instrumental intro.
  That last one cannot be caught by any text rule: it IS the lyrics
  verbatim, so every test of the form "does this look like the lyrics?"
  answers a wholehearted yes. On "Lied K" the tail of
  the initial prompt sat at 7.4 s, literally.
  The solution did not have to come from the text. `_vocal_windows`
  already measures where there is singing - built for the timing, never
  used to filter. If a segment sits on no measured singing at all, then
  nobody is singing there. On the reference set that separates without a
  grey area: every real segment is at 50 to 100 percent words-on-vocals,
  the two false ones at exactly zero. Deliberately at word level, because
  Whisper regularly stretches the end of a segment far past the last
  note. It is an ordinary model in the register, so the trial measures
  what it is worth. What it does NOT catch: an invention with real sound
  underneath it ("We'll be right back" sits at 100 percent vocal energy).
  That needs the coupling quality, and that one is still open.
- **B378 - the cluster trial now checks whether there is anything to
  measure.** With the scope on one project without manual timing it did
  sixty-eight measurements that all came out 0.00, and put that in the
  report as a table - reading as "not a single model does anything". The
  search beside it already checked for this; now both do.

Included in v0.120.0:
- **B379 - the language rule finally has a guard.** The agreement
  ("English is the working language of this project, test names
  included") has been there since B299 and has quietly slipped for a
  hundred versions: 839 of the 852 test names are Dutch, and this week a
  complete temporary panel and five test files were added to that
  without anyone noticing. Every other agreement in this project has a
  test that turns red; this one did not. That is the difference between
  a rule and a habit. `tests/test_language_guard.py` now does two
  things: it turns red when a Dutch function or class name appears in a
  converted file, and when a file on the TODO list turns out to be
  clean. The second is the important one - that way the list can only
  shrink and never becomes a permanent exemption.
- **B379 - converted.** `tools/whisper_probe.py` in full (names,
  docstrings and the command line: `--gap`, `--variants`, `--language`,
  and the eight variant names to `current`, `wider`,
  `no_silence_threshold`, `logprob_loose`, `wider_and_loose`, `vad`,
  `hallucination_jump`, `fallback_on`), the options of
  `timing_regression` (`--compare`, `--record`, `--date`),
  `timing_eval.compare`, the two classes in the coupling editor
  (`CouplingCanvas`, `CouplingEditorDialog`) and a name in
  `rename_module`. Note: this changes the commands you type.
- **B379 - and the lesson of B303 repeated at once.** The first attempt
  went over the whole file with a regular expression and promptly
  mangled the docstrings: "Dit gereedschap draait dezelfde vocal_stem"
  and "een gap van een minuut". Exactly why the agreement advised
  against a mechanical pass. The docstrings were translated by hand
  afterwards, per file, with the suite in between - and so will the rest.
- **B379 - what is still Dutch**, on purpose and on the list:
  `modules/test_panel.py` (twenty-three names plus its Dutch docstrings,
  which is translation work and not a rename) and the nested reporter in
  `modules/gui.py`. The 839 test names are separate from that: it is the
  biggest pile and the docstrings under them carry the reasoning why a
  test exists, often with the measured number attached. Those go in a
  release of their own, with nothing else alongside, so that a
  regression stays visible.

Included in v0.121.0:
- **B380 - template timing: built, measured, and switched off.** The idea
  is the user's and it is sound: what gets sung in an outro is almost
  always a repeat of something earlier in the song, and THAT time it was
  heard correctly. So take the measurement from the place where it did
  work instead of guessing. The evidence was there too: on "Lied K
  " the line "Don't stand, don't stand so, don't stand so
  close to me" is picked up cleanly four times, and the two instances of
  eleven words last 5.38 and 5.40 s - two independent measurements, two
  hundredths apart. And 36.3 s of measured singing after the last verses
  divided by 5.39 gives almost exactly the six repeats the lyrics have
  standing there.
- **B380 - why it is switched off anyway.** `modules/timing_template.py`
  does the work well: per line text it builds a template with a duration
  AND an internal profile (the ratio per syllable, so the singer's
  rhythm stays in place instead of being smeared out evenly), it leaves
  instances that sit on silence out of the template, and it refuses a
  template whose instances disagree. But it takes those instances from
  the **output of the sentence coupling**, and in an outro that is
  exactly the step that is broken. On the real project twenty-three
  templates came out, the most important of them `4x duur 1,00 s
  spreiding 0,00` - that is not a measurement but the floor of
  `sanitize_timing`, the same bottom four times over, which looks like
  agreement. Nine others had a spread of 1.48. Repairing on numbers like
  that is worse than doing nothing: six lines became 1.00 s.
- **B380 - so off, not gone.** Per the agreement: a model that turns out
  to be worth nothing goes to `default_on=False` with the measurement as
  the reason in the register, stays in the code and keeps running in the
  big trial (1.5.11), so that it gets measured again every round. The
  next round is the source: the templates have to come from the
  **transcription times** via the coupling map, not from the coupling
  output - then you measure Whisper where Whisper got it right, instead
  of the coupling where it got it wrong.
- **B381 - the check that came out of it does stay on.**
  `timing_checks.duration_outliers` compares the duration of each line
  with the median of that same line elsewhere in the song and counts
  `odd_duration`. That was needed because "high quality" only says the
  coupling was one-to-one: on this project a line of **19.42 s** was
  marked as high, while the same text takes 5.4 s. You need no template
  to see that - the line contradicts itself.

Included in v0.122.0:
- **B382 - `modules/` and `tools/` are English; the TODO list is empty.**
  The last two files are over: `modules/test_panel.py` (twenty-three
  names, every local variable and all of its Dutch docstrings) and the
  nested reporter in `modules/gui.py`. The guard from v0.120.0 did
  exactly what it was built for: as soon as a file on the list turned
  out to be clean it went **red of its own accord** with "is clean -
  strike it from TODO". That is the difference from a manual list, which
  would quietly have stayed put.
- **B382 - how it was done, because B303 remains the lesson.** Not with a
  regular expression over the file, but with a renamer that only touches
  NAME tokens: strings and comments are left alone. F-strings needed a
  second pass for that - Python 3.11 hands back an f-string as a single
  STRING token, so what stands between the braces is code the tokenizer
  does not offer as code. The prose parts (docstrings, comments) were
  then translated by hand, block by block, with the suite in between.
  And it was needed too: one blind pass over the strings blithely turned
  "de weglaatproef" into "de omission_trial" - the same mangling as with
  `whisper_probe.py`, spotted the same day because the handwork came
  past afterwards.
- **B382 - what a renamer by definition does not see: data.** The internal
  dictionary keys of 1.5.8 (`gezongen`/`gaten`/`stil`) and of the
  coupling coverage (`woorden`, `gekoppeld`, `zwak_deel`, ...) are
  strings, not names. They were converted by hand, and that is the most
  dangerous step of the whole round: the dict is filled in one function
  and printed in another, and the only thing connecting the two is the
  spelling. A missed key gives no error message but an empty column.
  `tests/test_v0122.py` therefore writes them all down by name, on the
  building side AND the printing side.
- **B382 - the reporter shape has become a contract for the third time.**
  B357 made it `report(slot, name, done, total)`, B360 was the aftermath
  of a type annotation that still described the old shape, and this
  round renamed all four arguments at once. A rename that touches a
  contract is the same kind of change B357 was, so the shape is now
  pinned down just as hard: in the runner, in the bar on the panel side
  and in the signature of every action.
- **B382 - the guard now looks past the `def` line.** Arguments and
  assigned variables count too. That was only possible once the pile was
  gone: the last seven leftovers in the whole program (`tekst_grp`,
  `muziek_keuzes`, `grens`, `overgeslagen`, `proef`, `tekst`, `regel`)
  were all locals and parameters, exactly what a guard that only reads
  `def` lines cannot see. The other way round would have been pointless:
  a wide guard over a wide backlog is a wall of red that gets switched
  off.
- **B383 - the reason given for a template repair was in Dutch in the
  code.** `timing_template.implausible` returned "2.3x langer dan
  elders", and that goes into the log line as `%s` - so into the log
  window. Per the agreement since B315 that belongs in `translations.py`.
  Now four keys (`template_no_duration`, `template_too_fast`,
  `template_longer`, `template_shorter`), and the test beside it compares
  against the translation table instead of a literal text.
- **B382 - what is still Dutch**, and why it stays that way: the `nl`
  texts in `translations.py`, the documents here, the headings and
  column names in `modelmatrix.md` and `modelcombinaties.md` (the user
  reads those), and the level names in the model register (`blok`,
  `zin`, `koppeling`, `venster`, `woord`) - those are data that end up
  as a column in such a report, not names in the code. What does still
  have to happen: the **839 test names** with their docstrings. Those go
  in a release of their own, with nothing else alongside, so that a
  regression stays visible; they are deliberately not on the TODO list,
  because a rule that can never be struck is exactly the permanent
  exemption this guard is meant to prevent.

Included in v0.123.0:
- **B387 - "Onbekend artefact: 'config:models'": 1.1 and 1.3 fell over on
  every existing project.** Two lists that had drifted apart. B361
  (v0.116.0) put `config:models` in the settings signature of
  `_config_signature`, so that a switched-off model invalidates the
  derived timing - but nobody put that name in the dependency map.
  `dependents()` deliberately throws a KeyError on a name it does not
  know ("better a loud error than quietly invalidating nothing"), and
  that is exactly what happened.
- **B387 - why it stayed invisible for five versions.** As long as the
  stored signature did not change, the group was never reported as
  changed. v0.121.0 added B380 to the register, the signature shifted,
  and from that moment every project with an older signature reported
  "config:models gewijzigd" and then fell over. New projects had no
  trouble with it (fresh signature), and the whole 1.5.x test panel
  never calls `sync_input_changes` - which is why the suite stayed green
  for two releases while the program was broken for the user. Rebuilding
  the karaoke did not help: the cause sat in the project signature, not
  in the audio.
- **B387 - what is invalidated now, and what deliberately is not.**
  `config:models` hangs on `word_coupling`, `coupling` and `timing`.
  Emphatically NOT on the transcription: the read-path filters
  (B334/B342/B343) run when READING the cache, not when writing, so
  another model must never cost a fresh Whisper run - that would be half
  an hour for nothing. Demucs stays put too. Two tests guard exactly that.
- **B387 - the guard that should have caught this, and why it did not.**
  `test_v098` has checked for years whether every step key and meta key
  in the code stands in the chain, but to do so it reads the
  `set_step`/`set_meta` calls out of the source. The `config:` keys do
  not come from there: those sit as a dict literal in
  `_config_signature`. So a whole category of keys was never checked at
  all. `tests/test_v0123.py` closes that gap by asking the function
  itself for its keys instead of reading the source, and it checks the
  reverse side too: a `config:` artefact that is measured nowhere is a
  dead line that quietly invalidates nothing.
- **B387 - and the error that let the KeyError stand was deliberately NOT
  swallowed.** A name that really does not exist still blows up; there
  is a test for that. The problem was not the loud error, it was the
  missing line in the map.
- **Delivery mistake from v0.122.0 put right.** `tests/test_v0112.py` was
  converted in the language round but not shipped, so on the user's
  machine four tests stood red on names that no longer existed there.
  Shipped. The lesson is small but real: with a rename across several
  files, the list of files to ship is itself a place where something can
  fall away.

Included in v0.124.0:
- **B377 - measured, and the outcome is the reverse of what the number
  suggested.** The yardstick went from 3.25 s to 3.32 s when the vocal
  referee joined in, and on Lied_P it cost 0.49 s. That reads as
  a regression. Per line it is not: **45 of the 50 lines are identical**
  with the model on or off, not one gets better, and five consecutive
  lines (28 through 32) carry all of it - three of those alone account for
  19.88 of the 21.82 seconds. And what B377 throws away there is **one
  segment**: "Thank you." at 167.07-167.87, with 0 of its 2 words on
  measured singing, in the middle of a 22 second gap where nobody sings.
  That is no wrong threshold, that is the model doing exactly its job.
- **B377 - why it costs error anyway: the little lie was load-bearing.**
  With "Thank you" gone there is no transcription word at all between
  155.64 and 194.98, and the interpolation wanders: line 31 lands on
  194.98 where the hand says 180.69 - **fourteen seconds too late**. The
  false anchor was accidentally holding the whole thing up. **Decision:
  B377 stays on and the threshold stays at 0.34.** The tempting repair -
  stretching the threshold until the segment survives - would have kept
  the hallucination; there is a test on that now.
- **B392 (new, not built yet) - the anchors are already there.** Of the
  eight lines without a transcription word within a second, **four lie
  within 0.22 s of a measured vocal onset, and two within 0.03 s** - and
  those are precisely the two that wandered off furthest (180.69 against
  onset 180.65; 185.52 against 185.53). `_vocal_windows` is already
  computed for every project. So where the transcription is silent but
  the singing is measured, the answer is already lying there; it is just
  not used as an anchor. Note the other side that the measurement shows
  as well: across ALL lines a vocal onset predicts only 36% of them
  within 0.5 s. So this is emphatically a fallback for lines **without**
  an anchor of their own, not a general rule. Discuss first, then build.
- **B384 - the energy cache could never hit, and that is repaired; but the
  gain is small.** `measure()` made a fresh `TemporaryDirectory` per call,
  and the cache key in `rhythm` contains the path - so every measurement a
  miss, plus a 50 MB copy because the "is it there already?" check looked
  in that fresh directory too. Now one working directory per project
  (safe, because `_build_project` rewrites `project.json` in full every
  time) and a hard link instead of a copy. **Honest about the number: I
  first estimated a decent bite out of the 28 minutes here, and that was
  wrong.** That first measurement counted the one-off startup of librosa.
  Measured out properly with six runs after warming up: 5.85 s against
  5.59 s, so **5%** - on 1.5.10 roughly 77 seconds. It stays good work
  (the cache was meant to work and did not), but the compute time sits in
  the coupling itself and not in the reading. Whoever really wants 1.5.10
  shorter ends up at separate processes.
- **B385 - a trial that bows out counted as "ran".** A quitter returned
  its explanation as an ordinary result, and was thereby
  indistinguishable from real work: the duration was stored and the
  version threshold moved twenty versions on. That is exactly what
  happened: 1.5.11a bowed out on v0.118.0 in 0.2 s and thereby booked
  twenty versions of silence for a measurement that never took place -
  four versions later the user asked why 1.5.11 was so short. Now a
  dedicated exception `TrialSkipped`: the reason simply goes into the
  report, but the duration is not stored and the threshold does not move.
- **B386 - the window trial silently grabbed the current project.** It
  reported "no gap of any significance" about a song nobody had asked
  about, and so cost a run of 1.5.11 that answered nothing. Choosing at
  random would solve the silence but not the waste: these are eight
  Whisper runs and it only shows something where there IS a gap. So it
  now picks **the largest gap across all projects**, with the current
  project as first choice as long as that one has a gap of its own. That
  choosing costs no Whisper: it leans on the machinery of 1.5.8, which
  lays word times against measured singing. If there is no gap anywhere,
  it bows out (B385) instead of passing judgement.
- **Two translation keys cleaned up** that B386 made dead
  (`heavy_probe_no_transcription`, `heavy_probe_no_gap`): the trial now
  looks for another project itself instead of reporting that this one
  has no transcription or no gap.
- **B393 (new, not built) - there are thirty unused translation keys in
  `translations.py`** (`lane_*`, `view_*`, `model_*_desc`, `fill_cache_*`,
  `test_texts`, `test_probe`, ...), leftovers from renamed buttons and
  merged tests. They do no harm but they make the table unreliable to
  search in. There is no guard against it; there should be one, together
  with the clean-up.

Included in v0.125.0:
- **B389 - the observation is right, the proposed mechanism is not.** The
  user saw timing problems "shifting along" and proposed that on a
  collision between the end of one sentence and the start of the next
  there should be a fight on weight, with the advantage to the newer
  sentence. Measured over thirteen projects with manual timing:
  **collisions do not exist.** There is exactly one line in 643 whose
  start falls before the end of its predecessor; `sanitize_timing`
  already prevents overlap. So that fight would almost never fire.
- **B389 - but the shifting is real, and large.** 158 of those 643 lines
  (24.6%) are more than a second off, and not scattered: in **38 runs of
  4.16 lines on average**, the longest **39 consecutive lines** in a song
  of 64. Split by whether a line has an anchor of its own the picture is
  unambiguous: **17% of the lines WITH an anchor are more than a second
  off, against 75% of the lines without.** So what shifts along is not a
  collision shoving its neighbour aside - it is a whole stretch without
  anchors wandering off together.
- **B392 - a gap in the middle now gets the measured singing.** Exactly
  what B336 already did for the tail. `interpolate_spans` drew a straight
  line through a gap between two anchors and knew nothing about where
  there is actually singing; the vocal windows only went to the tail. Now
  a gap in the middle gets them too, via `windows_between`. **With the
  same refusal as B336**: one line per measured window, and nothing as
  soon as the windows do not explain the run exactly - then the old
  interpolation stands. A wrong window is worse than a straight line,
  because it looks like a measurement.
- **B392 - measured, and it recovers what B377 cost.** On Lied_P
  4.76 -> **4.39 s** (-0.37), and on Lied_Q and Lied_T
  exactly nothing (there the windows do not explain the runs, so it keeps
  quiet as it should). Weighted over those three, 0.17 s better and
  nowhere worse. As a reminder: B377 cost 0.49 s on this project by
  removing a load-bearing little lie - B392 takes the larger part of that
  back without putting the hallucination back. **Honest about the scope**:
  this is measured on three projects, not on the whole reference set;
  1.5.5 and 1.5.10 give the real number.
- **B388 - a new project opened in the folder of the previous one.**
  `input_start_dir` returned an empty string for a fresh project, and an
  empty string is not neutral: Qt fills in the last used folder of this
  program run itself. Hence the explorer window opening in the music
  folder of the previous project when starting a new one. Now the home
  folder as fallback - a real path, so Qt no longer gets in between. Note:
  `_pick_background` and `_pick_video_font` still pass an empty start
  folder; those are video preferences and not project input, but it is the
  same trap.

Included in v0.126.0:
- **B395 - the coupling recomputed the same thing thousands of times.**
  The user's question was why 1.5.10 asks so little of his machine: 15%
  on ten cores, which is exactly one core. The obvious answer was
  separate processes. The profiler gave a better one.
  `cluster._fold_repeats` is called **636,028 times per measurement with
  307 distinct inputs** - the same word folded two thousand times over.
  It is a pure text function, so one `lru_cache` line takes a measurement
  from **2.44 s to 0.426 s: a factor of 5.7**. Checked that it shifts
  nothing: the outcomes of three projects are identical to the hundredth
  before and after, because caching a pure function cannot by definition
  change an answer.
- **B395 - what that means for the separate processes.** Four worker
  processes would give a factor of three to four, at the cost of a
  multiprocessing setup that has its own pitfalls on Windows. This factor
  of 5.7 costs ten characters. The idea of separate processes stays on the
  list but drops to the bottom: only once this is in do we know where the
  new ceiling lies. And it does not just touch the test panel - this
  coupling runs every time the user presses 1.3.
- **B394 - the measurement history was losing measurements.** Found while
  reading the results of that same run: after 1.5.1 through 1.5.10 there
  were still **nine keys** in `docs/testhistorie.json` - the totals per
  action plus four of the fourteen projects of 1.5.8. Everything from
  1.5.5, 1.5.6 and 1.5.7 was gone. `remember()` does a
  read-modify-write of the WHOLE file and `across_projects` runs two
  worker threads, without any locking at all. The second writer loads
  its snapshot before the first has saved, and then writes over it. That
  undermines exactly what B362 exists for: comparing against previous
  versions only works if those previous versions are still there. Now a
  lock around the read-modify-write, with a test that demonstrably turns
  red without that lock (forty threads, most of the entries
  disappear).
- **B394 - and a note for later.** A thread lock is enough as long as one
  process writes. As soon as the measurement is spread over PROCESSES
  this has to become a file lock; that stands in the comment where the
  next reader looks, because that idea is on the list.
- **What the run itself produced.** The baseline stands at **3.10 s**
  over fourteen projects (was 3.32 over eleven; the set has grown with
  Lied L and Lied Q, so that is not a clean comparison).
  **B392 does exactly what it had to do and nothing more**: +0.37 s on
  Lied_P, zero on all the others - the refusal keeps it quiet
  where the windows do not explain the run. Weighted +0.04. **B377**
  still costs 0.04 s, but per project the picture is now two-sided: -0.49
  on Lied_P against **+0.27 on Lied Q**, precisely the
  project where the user complained about words struck off at the end.
- **And the find from the cluster trial, which really ran for the first
  time.** 1.5.11a got through 32 combinations in 505 s before the user
  broke it off, and there is an outlier among them: **B258/B285 + B313 +
  B330/B351 all OFF gives 2.07 s against a 3.10 s baseline - a third
  less error.** No single model comes close (the best is B332 with
  0.57). This is a **lead, not a conclusion**: cluster 1 has seven
  models (128 combinations) and 32 of them have been measured, and
  1.5.11b - the trial that checks with held-back songs whether such a
  find is not a coincidence - has not run. With B395 that whole cluster
  now costs about six minutes instead of thirty-four, so the answer has
  become affordable.

Included in v0.127.0:
- **B390 - the chop/merge test rig stands, and one assumption turned out
  wrong straight away.** The cheapest candidate I had pointed at -
  `condition_on_previous_text=False`, so that Whisper does not build on
  its own previous output - **was already on**, both in
  `modules/whisper.py` and in the trial. That is the textbook explanation
  for a derailing outro, and it has therefore long been ruled out here.
  The outros derail anyway. So what goes wrong at the end of a song is not
  the decoder repeating itself, and that is now written down in
  `modules/whisper_chunks.py` so nobody spends another day on it.
- **B390 - what does remain: the window layout and the prompt.**
  `modules/whisper_chunks.py` holds the parts you can think about without
  starting Whisper: WHERE you cut, which prompt a chunk gets, and how you
  merge the results back together. Cutting happens **in the silences**
  that the vocal track already points out, with thirty seconds as an
  upper bound; only where the singing does not pause within thirty
  seconds is the cut made through the singing, and then with overlap so
  that the border area occurs in two chunks. Because every cut MAKES a
  new edge, and an edge is precisely the weak spot (0.42 confidence
  against 0.70 elsewhere).
- **B390 - the prompt per chunk is the strongest part, and that only
  became clear once the prompt had been read properly.** Those 400
  characters are a GLOBAL shortage that becomes a LOCAL abundance: with
  eight chunks each chunk has its own budget and far fewer unique words
  are needed, so each chunk can get the real lines in full - running text
  with phrasing instead of a de-duplicated word list. That lets Whisper
  expect the right SENTENCE instead of only the right WORDS. The cut is
  deliberately generous (eight seconds of margin), because it leans on
  the placement of the first run and that is exactly what is wrong where
  we are looking again.
- **B390 - the merging is emphatically NOT a vote.** Two runs share the
  same initial prompt, so their agreeing can ALSO mean that they are both
  parroting the prompt - precisely the echo we want to catch. Agreement
  is therefore no proof. So a second run may only speak where the first
  says **nothing**, and even then only with words that sit on measured
  singing. The vocal track is the only witness that knows nothing of the
  text, and therefore has the veto - the same rule B377 applies to whole
  segments, here per word.
- **B390 - and the trial that has to settle it: 1.5.11d.** Runs on the
  project with the most unheard singing and puts four ways side by side:
  as it is now, twice with a shifted start (10 and 20 s, because with
  steps of ten on a window of thirty every point lies far from an edge in
  at least one run), and chopped with a prompt per chunk. The measure is
  **seconds of measured singing without a word** - the same number that
  1.5.8 reports, because a word count says nothing: a run can give more
  words and leave the same gap standing. Every variant is reported
  separately AND the merge, so that a gain can be traced back to where it
  came from.
- **B390 - the trial can now also transcribe a piece of audio.**
  `run_once` takes `start`/`end` and shifts the times back onto the
  timeline of the song, via a numpy array instead of a path. That works
  with every version of faster-whisper and does not depend on
  `clip_timestamps`.
- Nothing has been **measured yet**: this is the rig. What comes out of
  it decides whether chopping becomes a setting or whether we know the
  window edges are not the cause. Both outcomes are a gain.

Included in v0.128.0:
- **B396 - the workspaces finally use the machine.** The user has asked
  for this several times and got an explanation instead of a repair every
  time. The explanation was even correct, and that is precisely what made
  it worthless: two workspaces have existed since B357, they are real
  threads, and with pure Python the GIL lets only one of them run at a
  time. Fifteen percent of twelve logical processors is one core.
  Explaining that once more measures nothing.
- **B396 - two kinds of work, two sums** (the user's rule, and it is the
  right one because the two kinds of work look nothing alike):
  - **compute work** (the yardstick, so 1.5.10 and the cluster and
    search trials) needs **separate interpreters**. Each worker then
    keeps one core busy, so the number is cores minus a couple to keep
    the machine usable: twelve gives **nine**.
  - **Whisper work** is exactly the other way round: ctranslate2 is C++
    and releases the GIL, so there threads really do run alongside each
    other. But one run already takes about four cores, so what fits is
    cores divided by four, and two thirds of that: twelve gives **two**.
    That matches the measurement - one run sat at 33% of the machine.
- **B396 - why processes are the only way here, and not just a faster
  one.** A model variant is set on module globals with `setattr`. Two
  variants in one interpreter would read each other's models, and that is
  exactly why 1.5.10 walks its 256 rounds strictly one after another.
  Give every worker its own interpreter and that objection disappears.
  The work package is therefore made small and picklable: a project name
  plus the **full** desired model state - no callables, no context, no
  closures, because those are what made the existing distributor
  thread-only.
- **B396 - the window trial walked its variants one by one.** That was
  what the user saw on his screen: one bar that moves and one bar with a
  label that just sits there. The eight variants now go through the
  same distributor as the projects, with the Whisper number of
  workspaces. Visible from two moving bars, and from the processor
  usage.
- **B396 - with history it stays on threads.** There most of the work is
  skipped anyway (B362), and then a process pool would only add startup
  costs. The choice sits in `_yardstick_rows` and there is a test on the
  order.
- **B396 - and a fallback without any grumbling.** If starting processes
  does not work (a frozen build, a locked-down machine), it carries on
  serially with a line in the log. Better a slow answer than no answer at
  all.
- **Note when resuming**: an aborted heavy trial starts over. `heavy_trial`
  writes the report after each finished investigation and only then stores
  the duration, so a trial that is done is skipped next time - but within
  a trial there is no resume point.

Included in v0.129.0:
- **B397 - you could not see which of the four was running.** 1.5.11 is
  four investigations under one number, and the screen showed only
  "1.5.11" plus a Dutch title. That left the user unable to say which
  trial he was talking about - and those letters are there for exactly
  that. The bar now shows `1.5.11c`, the headings in
  `modelcombinaties.md` too, and the panel puts under the checkbox what
  hides behind that number (`a: clusters, b: zoektocht, c: vensterproef,
  d: knippen`). A test guards that no trial writes a bare "1.5.11" any more.
- **B397 - the window trial names its own winner.** It reads back its own
  table for that instead of keeping a second little list, so the
  conclusion underneath can never say anything other than the rows above
  it. With the warning that belongs beside it: more seconds is only a
  gain if the number of segments does not jump along, because otherwise
  the gap has been filled with inventions.

What the first COMPLETE heavy run said, and where I have to correct
myself:
- **The find of 1.02 s does not exist.** On the aborted run I read
  `B258/B285 + B313 + B330/B351` at 2.07 s against a 3.10 baseline and
  passed that on as a lead worth attention. Over all **128** combinations
  that same setting comes out at **3.31 s (+0.21)** - so it makes things
  worse. I cannot account for where that 2.07 came from; what I do know
  is that a partial table is no table and that I should not have passed
  it on as a lead. The complete run says that **not a single combination
  in this cluster beats the current setting by more than 0.04 s** - and
  that 0.04 is switching off B377, on which the decision has already been
  taken.
- **The search trial has paid for itself, and exactly as intended.** It
  found `B377 + B329/332/340 + B343 + B258/B285`: **-0.32 s on the search
  set** and on the three held-back songs from 2.79 to **10.00 s - well
  over seven seconds worse**. It reported that itself as the pattern of
  overfitting. That is exactly what `_HELD_BACK` exists for, and it went
  off on its first real run. Without those held-back songs this would
  have been an "improvement" of 0.32 s that wrecks every next song.
- **The window trial produced the only usable lead: VAD.** On the 28 s gap
  in Lied_S seven of the eight settings cover 0.9 s. **VAD covers 26.4
  of the 28 s** - with FEWER segments (12 against 26) and practically as
  many words (192 against 196). That last part is the most important:
  fewer segments with the same number of words means there is no loop in
  it. That is a different picture from "Lied K", where
  VAD invented text and dropped the outro. So VAD is song-dependent and
  deserves a measurement per project, not a switch that goes on
  everywhere.

Included in v0.130.0:
- **B398 - two lines, nine workspaces.** Since B396 the measurement runs
  over nine processes, but the panel had two bars and looked them up by
  workspace number - so workspaces 2 through 8 fell outside the list and
  were never shown. The user saw two rows while nine were running, and
  said so as well. Two lines was and remains the right number; what has
  changed is what they mean: the **first line is the run as a whole**
  (which action, how far along), the **second is who is busy right
  now**.
- **B398 - and the titles give way before the line does.** If the project
  names no longer fit on one line, then the names go out and the count
  stays standing: an honest "9 workspaces" is better than a song title
  that has been cut off halfway through. Exactly what the user
  proposed.
- **B399 - one pool for the whole action, not one per round.** The first
  version made a fresh process pool per measurement round and closed it
  again afterwards. That looks tidy and is disastrous: 1.5.10 walks 256
  rounds, so that is 256 x 9 = over two thousand process starts - and on
  Windows a start is a complete re-import of the modules, not a cheap
  fork. The work per round is seconds; the starting would have cost more
  than the measuring. Reuse is possible precisely because the work
  package is designed the way it is: a child gets the FULL model state
  with every package and therefore carries nothing over from the previous
  round. The nine workers go away as soon as an action is finished.
- **B398 - and a real bug that surfaced along with it.** The memory of the
  workspaces first stood as a mutable class attribute. That is shared by
  every window, so a second window inherited the workspaces of the
  first - which became visible when two tests got to see each other's
  project names. Now created per window.

Included in v0.132.0:
- **B403 - the test panel walked around the language determination.** The
  user suddenly saw Spanish go by in 1.5.11 and asked whether Whisper
  gets the language once or per chunk. The program itself does it right:
  `pipeline._language_for()` determines the language once from the
  **complete** lyrics - first a manual choice, then detection on the
  text, and only "auto" if that is too uncertain. But the panel never
  asked for it and handed Whisper `config.whisper.language`, which is on
  "auto" by default. So every variant detected its own language.
- **B403 - and that is no cosmetic flaw.** It pollutes precisely the
  comparison the trial exists for: a variant can differ from its
  neighbour because THAT run decided the song was Spanish, and not
  because of the setting being tested. Concretely it means the VAD result
  (26.4 of the 28 s against 0.9 for the rest) has to be measured again
  before anyone believes it.
- **B404 - with the chopping it was ten times as bad.** `run_chunked`
  passed the same language string to every chunk, but if that is "auto",
  **every chunk detects separately**. Ten chunks are then ten independent
  language decisions, and it is precisely a short chunk - a "la la la", a
  fade-out - that is the most vulnerable. The user found this BEFORE
  1.5.11d had ever run.
- **B403/B404 - the repair.** `probe_language()` determines the language
  once: what the app itself would choose, and otherwise what Whisper
  decided on the WHOLE original (that answer is already in
  `run_info.json`). If it stays "auto", the report says a language has to
  be picked by hand - a measurement whose language wanders is worth
  knowing about. Both Whisper trials put the language used under their table.
- **B402 - the top bar is the action, the blocks are the workspaces.** The
  top bar showed the progress WITHIN one measurement round: at 1.5.10 it
  said "2/17" at 11% while the run was going hard, so eight minutes of
  work looked stuck. An action counts rounds, a workspace counts projects,
  and those are different numbers - so the action has been given a channel
  of its own. The second row named the busy workspaces on one line and
  with nine that no longer fitted; now every workspace has its own block
  with the name of what it is chewing on, filled when it is busy and pale
  when it is idle. Carried through at 1.5.11 as well: there the action is
  "which of the four investigations" and the blocks are the variants.

What this day's measurements produced, for the archive:
- **1.5.10 went from 2316 s to 472 s** - v0.125.0 2316 s, v0.129.0 739 s
  (the cache of B395), v0.131.0 471.8 s (reusing the process pool, B399).
  From thirty-nine minutes to under eight, and that reuse alone was a good
  four minutes of pure process starting. Memory is no objection: about
  230 MB per worker.
- **B391 is answered, and the answer is no.** A longer initial prompt gives
  MORE segments (26 to 40), FEWER words (196 to 184) and exactly the same
  coverage of the gap. That is the warning we said we would hold to: the
  number of segments jumps along without anything being found. Those 400
  characters were not cautious but well chosen; the unused budget is no
  missed opportunity.
- **1.5.11d, the chop trial, gave the biggest find so far** - subject to
  B403/B404. On Lied_S with 188.2 s of measured singing: current 68.8 s
  unheard, offset 10 s 49.2 s, offset 20 s 42.9 s, **chopped into ten
  pieces 15.3 s**. That the offsets alone differ by twenty seconds is the
  window-edge effect, measured for the first time instead of reasoned out.
  But the chopped run yields 456 words against 197, and that has to be
  laid against the lyrics before it can be called a gain - that variant in
  particular was the most exposed to the per-chunk language detection.

Included in v0.133.0:
- **B406 - the timing stacked words on top of each other at the line end.**
  On "Lied I" fourteen words across three lines had length
  zero: "en de stemming zit erin" stood with all five of its words at
  exactly 54.064 s. `_sanitize_spans` clipped at `high`, and as soon as the
  cursor hit that ceiling every following box became `(high, high)`. The
  worst part was not that it happened but that it could not be repaired:
  stretching in the editor scales the boxes linearly, and zero times any
  factor stays zero. Now material that does not fit is squeezed
  proportionally - eight words in 1.18 s reads fast but reads - and the
  editor repairs existing flattened lines when opening, so that it only
  reaches disk when the user saves himself.
- **B408 - the coupling already had the answer, and the timing threw it
  away.** This is the find of the day and it comes out of `project.json`
  itself. `steps.coupling.original_items` holds the coupled span per
  sentence, and for the seven lines that came out more than a second too
  short the right number is sitting there: line 12 at 50.78-54.07 while
  the timing gave 50.46-51.64. Stronger still, **46 of the 59 line spans
  the user pinned down by hand are exactly the span the coupling already
  gave** - an afternoon of listening work to reconstruct a number that was
  already there. Where it disappears exactly is not yet established; it
  does NOT happen in `sanitize_timing`, because that has a floor of its
  own of `baseline x lettergrepen / 3` (1.28 s for a line of 32) and
  1.15 s came out. The suspect is `_apply_energy_word_timing`, which lays
  the line over the vocal windows again; the clue: line 12 automatically
  starts at 50.46, before the coupling. So measure first and repair after:
  the diagnostics now put the span after the coupling, after the sentence
  step and after the word step side by side per line, with a `KRIMP` flag.
- **B405 - stretching let the word grow on the wrong side.** Pull the
  right edge up against a neighbour and `_inside` held the width fixed and
  shifted the block to the left: the gain came back out on the left side.
  That shifting is exactly right when moving and exactly wrong when
  stretching; the difference is which edge the user is holding, and that
  now travels along. If there is no room, nothing moves - refusing is the
  honest answer for a stretch action, jumping is not.
- **B407 - the same change, two opposite outcomes.** Picking the karaoke
  text again through the file chooser preserved the manual timing (B99
  carries the text change through properly), but editing the same file in
  Notepad went around that arrangement to `sync_input_changes`, which
  throws away everything that depends on the karaoke text - `timing.json`
  included. That really happened this day and it cost the user almost an
  afternoon of handwork; only the backup saved it. The saving can be done
  without any memory of the old text: `timing.json` carries the text of
  each line itself, and that is the old state. With an equal number of
  lines the change is carried through over the existing span; with a
  different structure the timing goes as before.
- **B409 - the panel said two things twice and one thing not at all.**
  Above the blocks stood a line naming the same project names, only cut
  off at line width; that one is gone. The top bar read "1.5.11 1.5.11
  2/4" because the wrapper always pasted the action code in front and the
  trial already named itself that way. And the letter of the trial went to
  workspace 0, where the first project name overwrote it a beat later - it
  now stands on the action line, so "1.5.11b 2/4".
- **B410 - the test panel, after asking three times.** `_measure` still
  ran over two threads that take turns holding the GIL: at 1.5.11b that is
  240 rounds on one core out of twelve, and that is exactly what the user
  saw in the task manager. It now goes over the process pool, which became
  possible by passing model codes instead of `(module, attribuut,
  vervanging)`; a function object does not travel to a child process, a
  code does. 1.5.11c from now on measures coverage on **words** instead of
  segment edges - VAD gave twelve segments against twenty-six and scored
  26.4 of 28 s "covered" while the number of words actually dropped, and a
  bracket with no words in it is not coverage. 1.5.11d spreads its four
  runs over two Whisper slots (873 s of the 3551 s ran serially), merges
  from the **best** run instead of always from "current" (that cost 7 s of
  coverage: chopping alone got 29.3 s, the merge 36.5 s) and writes the
  heard words out to `docs/knipwoorden.txt`. The held-back songs of
  1.5.11b come from the measurable projects and spread out: the
  alphabetical tail end yielded three songs of which one had no manual
  timing, so two really counted and one of those was the worst song there
  is.

What this day's measurements produced, for the archive:
- **The language fix of v0.132.0 was not cosmetics.** Measured again with
  the language pinned down: the chopped run gives 248 words and 29.3 s
  unheard, against 456 words and 15.3 s in the polluted run. Well over
  half of those words were Spanish invention. The conclusion "chopping is
  the biggest find so far" is thereby withdrawn; what remains is a real
  but far smaller gain.
- **1.5.11a is finished and the answer is zero.** Not a single pair of
  models shows any interaction, so there is no cluster to form and the
  separate numbers of 1.5.10 are the whole story.

Included in v0.134.0:
- **B412 - the number was not in the lyrics.** The user reported that "45"
  was missing from the display while Whisper had found it, and that was
  literally the case: `load_lyrics` kept only `isalpha` per character, so
  "Another 45 miles" became "Another miles". Not uncoupled but absent -
  invisible in every view, because the word never existed. Eleven words on
  that song: 279 in the file, 268 in the coupling, and in the coupling
  report eleven times a gap of 0.89 s between "Another" and "miles". The
  galling part is that `cluster.phonetic_key` has handled numbers since
  B274 ("500" gets written out); that machinery just never got to see a
  number. While repairing it another bug came out from under it: the Dutch
  was glued together the English way, so 45 became "veertigvijf" with key
  `fetikfif`, while the sung "vijfenveertig" gives `fifenfetik`. A key
  that can never match is worse than no key, because it looks as though it
  has been taken care of.
- **B411 - one extra chorus cost the whole timing.** The rescue of B407
  only worked with an equal number of lines; above that everything went.
  That is correct for the changed lines and not for all the others, and
  with a chorus tacked on at the end everything before it is still exactly
  right. The lines are now recognised by text (`difflib`): whoever reads
  the same keeps his own syllables, whatever shifts around him. A new line
  gets the room between its neighbours, evenly divided - not right, but
  placed and repairable in the editor without starting over.
- **B413 - one folder per project.** The chooser remembered the last
  folder per input type, while the user's way of working is the other way
  round: first put everything for one song together, then point at the
  files one by one. Now the project remembers the last used folder,
  whatever the input; if a type already has a folder of its own, that one
  wins. The home folder stays the last fallback, because an empty start
  folder is not neutral (B388).
- **B414 - the empty spots in the text lane.** A click beside a block did
  nothing at all: no selection, no playhead. That is the widest spot on
  the screen and it is exactly where you are looking when you sit timing a
  line. Only the empty spots, though - hitting a block still grabs that
  block.
- **B415 - two steps, two columns.** In the first setup of B408
  `sanitize_timing` and the shifting onto the vocal onset sat together in
  the column "zinnen", and those are two steps that can both shorten a
  line. Each has its own column now.
- **B416 - 1.5.11d becomes a night trial.** Measuring one song was cheap
  and said nothing about the rest: the song with the biggest gap is by
  definition the least representative song there is, and every cut makes a
  new edge, so on a song with little to gain chopping can do damage. Now
  the four biggest gaps. And the trial reports the singing AFTER the last
  text line separately: on "Lied M" the last chorus is
  deliberately missing from the text (acoustic, played by feel, the words
  are hard to make out), and counting those seconds as "unheard" blames
  Whisper for a gap the text itself has.

What this day's measurement produced, for the archive:
- **B408 has cleared the suspect.** The new columns show that lines 6, 12,
  14, 18, 30 and 32 are already too short when they come out of the
  coupling (1.11 / 1.18 / 1.25 / 1.57 / 0.99 / 1.02 s) - so not in
  `sanitize_timing`, and certainly not in the energy word timing I was
  pointing at. While `steps.coupling.original_items` has the right number
  for those same lines (28.77-32.25 for line 6). So the loss sits in
  `couple_timing`, between the original sentence spans and the karaoke
  lines that follow from them. That is the next repair, and now a small
  piece of code instead of an afternoon of searching.
- **B406 works in practice.** The automatic timing of that song went from
  49 syllables with length zero to none.

Included in v0.135.0:
- **B418 - the hyphen was not a word boundary.** The user thought
  punctuation was already being ignored, and that is true for the key:
  `-la` and `la` both give `la`, `e-mail` and `email` both give `email`.
  What was not true is the boundary. "La-la-la-la-la," stayed one word
  with key `lalalalala` while Whisper makes five separate `la`s of it, so
  those two could never meet - the same ailment as the 45. His own
  explanation gave the solution: he writes those hyphens because the
  cluster belongs together rhythmically and counting is then easier, so
  they are separate sounds and not a compound. Counted over all seventeen
  songs: 186 words with a hyphen, 132 pure repetitions (`na-na-na`,
  `la-la-la`) and the remaining 54 are `woah-oh`, `diggi-loo`, `mm-hm`,
  `zwart-te` - sung syllables as well. Not a single real compound word.
  And his objection about "lala" written together is already covered:
  `_align_core` has `_lyric_pair_sim` (two lyric words against one
  transcript word) and its counterpart, which also catches the e-mail case.
- **B417 - the pins shift along, and this should have gone along
  yesterday.** Manual word couplings store POSITIONS in the word list.
  B412 put the digits back into that list and thereby shifted every pin
  after it, silently: on "Lied M" 268 to 279 words with the
  first number at position 65, so three of the seven pins wrong, and on
  "Lied G" five of the thirteen. Nothing was lost -
  the pins were still there, they were just read against a longer list -
  but it happened without a single line in the log, and that is the most
  annoying kind. The conversion deliberately does not count digits and
  hyphens: that would be a rule which has to be extended with every next
  change to the word splitting and goes wrong exactly once. Instead both
  lists are built - the old form from `words_before_b418`, the new one
  from `split_word` - and laid against each other. Same thought as
  `_PIN_LAYOUT_FULL`, which has been doing the same for the other side of
  the pin since B309.
- **B419 - I was measuring the tool, not the method.** The user said that
  the doubling of the transcription time would not be so bad, and he was
  right for a reason neither of us had named. Over 35 chunks of the night
  trial: **0.75 s of compute per second of audio plus 28.9 s of fixed cost
  per chunk**. A fragment of 4.3 s cost 20 s and one of 30 s cost 56 s;
  that first one cannot be decoding. The cause sits in
  `tools/whisper_probe.py`, which built a fresh `WhisperModel` on every
  call, while `modules/whisper.py` already keeps the model in
  `_MODEL_CACHE`. Of the ~450 s of a chop run, a good 290 s was loading
  models. Worked through for Viva: ten chunks, 236 s of audio including
  overlap times 0.75 is 177 s plus one load - against 208 s for the
  whole-song run. So chopping costs about the same, not double. That also
  makes every next night trial considerably cheaper.
- **B420 - "unheard" rewards a loop.** That number measures whether a gap
  is FILLED, and a Whisper loop fills a gap exemplarily; so the measure
  rewards precisely the fault it is supposed to catch. Happened twice: a
  run in Spanish that scored best, and a chop run with 456 words of which
  well over half were invented. Both times it was noticed because the user
  saw something or I counted by hand, not because the trial reported it.
  Now each variant states what share of what was heard occurs in the
  lyrics, compared on the phonetic key - the same notion of "the same
  word" that the coupling uses. And the merge picks its base run partly on
  that, because otherwise a loop automatically becomes the base and its
  inventions in particular stay standing.

What the overnight trial produced, for the record:
- **Chunking works, on all four songs.** Unheard vocals from 250.7 s
  down to 140.4 s, and with merging to 91.9 s - **63% off**, from 33.9%
  to 12.4% of the sung time. Merging from the best run instead of from
  "current" took Viva from 36.5 to 17.7 s.
- **The offset is a guess.** On Lied_O offset 10 makes it 28.5 s
  WORSE than doing nothing. The story of one song ("the offset wins back
  26 s") did not hold across four.
- **And nearly a false alarm on my side.** Lied_T jumps
  from 238 to 552 words with 349 repeats, which looks exactly like a
  loop. My first count said 31.5% in the lyrics. That was my own
  splitter: the lyrics write "La-la-la-la-la," as one word and Whisper
  writes "-la" separately. Split properly it is 95.3% - HIGHER than the
  current run. Only Lied_O drops (81.7 to 76.0), and there the
  unknown words are the nonsense syllables the song is full of anyway.

Included in v0.136.0:
- **B422 - sharing the model cost more than it gained.** The fix for
  B419 removed the 28.9 s load time per chunk and put a queue in its
  place: one `WhisperModel` with `num_workers=1` handles one
  transcription at a time, so two lanes were taking turns
  waiting. On the same overnight trial: 3902 s became 5522 s, and
  per thirty-second window 44-52 s against 20-27 s before. Exactly
  doubled, which is what taking turns looks like. The user saw it in
  the task manager as four busy cores while two lanes were running.
  The model now gets `num_workers` and `cpu_threads` from the same sum
  that counts the lanes. That those numbers happened to match the
  library's silent default (four threads) until now was luck; it is
  written down in one place now. Reassuring: the results were not
  affected - "current" on Lied_S was identical between both runs
  down to the segment.
- **B423 - the chunks go through the queue.** The user's standing
  agreement, in his words: queue as much as possible. The ten or eleven
  chunks of a chunked run ran strictly one after another, 400 to 640 s
  per song, by far the longest single item of the overnight trial.
- **B429 - a model change wiped the manual timing.** This one actually
  cost the user money: he opened Lied_Q, the program saw
  `config:models` standing differently than the previous time, and threw
  the timing away. No question asked, no log line. A model changes what
  the AUTOMATIC coupling of the song produces; it says nothing about
  where the user placed his lines by hand. The same goes for an edited
  karaoke track: different audio, same lines. The rescue from B407/B411
  only applied to a changed karaoke text and now applies to every change
  that would remove the timing, with the cause written to the log
  alongside. If the user says the timing no longer fits, 2.2 rebuilds
  it - that is now a choice instead of a notification after the
  fact.
- **B428 - muting and restoring are two different things.** Step 1.4
  demanded a cluster selection, while "terug uit origineel" (restore
  from the original) runs through `restore_fragments` and has nothing to
  do with muting. Anyone wanting to restore one horn blast had to tick
  clusters he did not want muted - and after a fresh transcription even
  go through step 1.3 again for a selection that was then thrown away.
- **B427 - the guard rejected a good run.** The purity percentage only
  counted against the lyrics. On a song where the original sings
  "na-na-na" and Whisper writes "la" the chunked run came out at 32% and
  was refused as a base, while those words had simply been heard
  correctly and only spelled differently. The karaoke text of that same
  song writes that passage as "la-la-la". Two texts for one song, and
  together they describe what may be sung; for a guard, too lenient is
  better than too strict.
- **B424/B425 - two variants for two open questions.** "chunking (global
  prompt)" chunks exactly as usual but gives every chunk the same
  deduplicated word list, so that the difference with "chunking" is ONLY
  the per-chunk prompt. That decides whether chunking has to wait for a
  first transcription, and so whether step 1.1 has to fall apart into
  two rounds or fits in one queue. "chunking + vad" is the combination
  nobody has measured yet: 1.5.11c measured VAD on the whole song,
  1.5.11d chunking without VAD, and they are not alternatives - VAD
  removes silence, chunking cuts into it.
- **B430/B431 - the panel cleans up after itself.** The lane buttons
  stayed behind after a finished action with the names of the last
  projects. The cleanup routine already existed and also runs after
  every action; the buttons were added later at B402 and had never been
  included in it. And the grey explanatory line under 2.4 is gone: what
  it said is written out more fully in `docs/video_standard.md`.

Working agreement added (from the user):
- **Queue as much as possible, heaviest task first.** With two Whisper
  lanes that is eight of the twelve cores instead of four. No fixed
  rounds with fixed jobs: a task may enter the queue as soon as its
  conditions are met, and a freeing lane picks up the next chunk by
  itself. Count on the songs not all being the same while doing so -
  with a real karaoke version (not made from Demucs) the karaoke
  transcription is not a trifle but a full run.

Included in v0.137.0:
- **B435 - the logic checks run between the models.** The idea is the
  user's and it covers a blind spot I had not seen myself: the weighted
  error only weighs line STARTS. A model can leave those alone and wreck
  everything inside the line in the meantime - syllables without a
  moment of their own, a whole word on one timestamp, times back to
  front - and that disappears into an average. Exactly the kind of
  damage the user does see in the video; B406 was found that way, by him
  and not by the measurement. Every measurement now runs
  `timing_checks.sanity` along (the shape checks only, no audio, cheap
  enough for a few hundred rounds) and every trial ends with "no model
  left a broken line behind" or with a table: project, which models were
  set differently, and what is wrong.
- **B436 - the timing measurement now knows when it is off.** The user
  had other work running on the machine and noticed the times were
  skewed. Besides the wall clock the process CPU time is now tracked; if
  the two diverge far, the trial writes in the log itself that this
  number cannot be laid next to an earlier run.
- **B437 - three counts added, and the exhausted trials switched off.**
  The counts hang under 1.5.7 and not as an eleventh action, because the
  ceiling of ten is there for a reason. What they answer: which lyric
  words never couple (twice it turned out that a whole word category
  could not match on principle - digits, hyphens - and both times we
  found it by hand), how often a syllable is held long, and whether
  blocks that come back last equally long. The second one produced
  something straight away: **1005 syllables** across fourteen songs,
  every one of them a vowel, while the field `held` - which the video
  renderer can already show - is nowhere true across all projects. So
  there is a lamp without a switch. And on the other side: seven of the
  eleven window-trial variants gave a bit-identical answer two runs in a
  row (26 segments, 196 words, 1 word in the gap) and the prompt lengths
  answered B391 with no once again. Together a good half hour per
  overnight run for knowledge that was already on paper. They are
  SWITCHED OFF, not thrown away - the same treatment as a model, so the
  idea stays readable and can come back in one line.
- **B438 - my own language debt.** The rule is clear: a file that is
  substantially modified goes over to English entirely in the same turn.
  I edited `pipeline.py`, `gui.py`, `dependencies.py` and
  `model_register.py` for four versions and left the Dutch comments
  standing - 135 lines - and nothing ever went red, because
  `test_language_guard.py` only looks at function and class names.
  Exactly the pattern that guard was built for once, and I walked into
  it myself. Translated now, with a test that guards comments too.

What the self-check produced further:
- Every build since v0.133.0 had a literal "gogo", and the interventions
  in the json files were all explicitly asked for.
- Two things I did without asking: a safety copy next to `Lied_L`
  and my own temporary archives in `C:/Muziek`. For the latter there is
  now an agreement (`_to_delete`), the first one I should have asked
  about.

## Decide before release

Here is everything that is in there **temporarily**. That is code that
was made to be able to investigate something on the user's machine, not
to travel along to a release (git or otherwise). When preparing such a
release, the question belongs per row: does this one go along, or does
it go out?

There is precedent for forgetting it: B136 was such a temporary button
too ("Modellen vergelijken", v0.65) and that it went out again in v0.78
was more luck than judgement - it was nowhere written down as an open
decision. Hence this list, plus a test that goes red as soon as a file
with a `TIJDELIJK` or `TEMPORARY` marker turns up that is not named
here. That second one was added at B465: the code has meanwhile been
converted to English and the guard only looked for the Dutch word, so it
looked straight past a temporary function in `pipeline.py` that had been
there for months.

On 25 August 2026 these decisions were taken; below is per row what it
becomes instead of what the question was. Two rows have already been
carried out because their question had been answered (B512).

**Status after v1.0.0 (B542):** the release on GitHub is there, and with
it came the question of whether this was the moment. The answer: the
test panel and everything hanging off it stay in - sixty-six of the
ninety-six test files import `test_panel`, so taking it out breaks the
test suite, and the user still needs the tooling daily. The measurement
work itself has been kept outside the repo, via `.gitignore`. The
question "does the code go out" is therefore still open for a next time;
the question "do the measurements travel along" is answered with no.

| part | file(s) | why it is there | the decision |
| --- | --- | --- | --- |
| Test panel behind button 1.5 | `modules/test_panel.py`, the button in `modules/gui.py` | Numbered test functions (1.5.1 through 1.5.10, plus the heavy batch 1.5.11) that run on the user's machine instead of mine: filling the cache, calibration-set status, project check, missing repeats, the yardstick, unique-versus-repeated, the word and syllable checks, the omission trial and the big trial. | **Out entirely on release**, with everything hanging off it. It is tooling for the build, not for the user. Until then it stays. |
| Fill the cache (1.5.1) | `modules/pipeline.py` (`projects_without_cache`) | Finds projects whose transcription cache is gone, so the measurement does not fall back on the raw transcription from before the forced alignment. | **Goes out with the panel.** |
| Measurement history | `modules/test_history.py`, `docs/testhistorie.json` | Keeps track per action, project and version of what has been measured, so an unchanged project can be skipped. | **Out on release.** Measurement work on one calibration set is not documentation; it stays with the user only. |
| Test reports | `docs/verslagen/` | The lines of every test action that ran, with time and alarms (B524), since B534 with date, time, version and scope in the name so no run overwrites the previous one. The dated copies of `modelmatrix.md` and `modelcombinaties.md` live there too. The log window sits on the user's machine and he cannot pass that text on; these files he can. | **Out on release.** Measurement work, not documentation; it never travels along in a delivery. The user empties the folder himself. |
| Report of the heavy trials | `docs/modelcombinaties.md` | Outcome of 1.5.11: all combinations within a cluster and the search for the best setting. | **Out on release**, same reason. |
| The report of the big trial | `docs/modelmatrix.md` | Outcome of 1.5.11: what each model is worth per level, per project, in pairs and in reverse order. | **Out on release**, same reason. |
| ~~Window trial 1.5.11c~~ | ~~`test_panel.window_trial`~~ | Eight Whisper settings on the largest gap. It was there to answer one question. | **Carried out in v0.146.0**: B454 had answered it three times with "no", it had been switched off since v0.144.0, and with the decision above there was no reason left to keep it. |
| ~~Refit button and 1.5.11f~~ | ~~`pipeline.refit_syllables`, `test_panel.refit_trial`~~ | The button from B497 and the measurement that was to say what it was worth. | **Carried out in v0.146.0**: the measurement gave +0 ms across eighteen projects, so button and trial are both gone. The numbers are at B512. |

## Test data (examples that were used)

- Per Spoor (NL, awkward/uneven timing).
- Freed from desire → parody "Lied T" (crowd choruses,
  separate karaoke mp3).
- Formidable (French), Oerend Hard (dialect).

Included in v0.138.0:
- **B439 - the model matrix measured nothing for ten versions.** This is
  the find of this round and it is unpleasant, because the report looked
  fine. Since B396 (v0.128.0) the yardstick measures in separate
  processes, and a child process builds its world from the model state
  it is handed. `big_trial` and `omission_trial` however still set their
  variant with `setattr` on module globals in the PARENT process, and
  `_model_state_now()` reads `model_register.enabled()` - the overrides
  dictionary, which knows nothing of that setattr. So every round asked
  for the same state. Hence `+0.00` for all twenty models, all 190 pairs
  and both orders, and hence a weighted error that stayed equal down to
  the hundredth. Not B410 but B396 broke this; B410 in fact built the
  good route (model codes, for 1.5.11b) and that was simply never
  extended here. The proof stood side by side in the reports: 1.5.11b,
  which runs through `_measure` with codes, simply gave differences
  (3.20 → 2.80), while 1.5.9 and 1.5.10 lay flat at zero. Two routes
  next to each other, one of them never moved along.
- **B439 - and why no test saw this.** There were tests on every part:
  that the replacements match the real functions, that the models get
  put back, that something is written out after every variant, that
  every loop looks at the stop button. Not one asked whether two
  variants actually differ from each other. That one is there now, and
  it is the core of this release: the trial is run with an intercepted
  `measure_rows` and the states sent along are compared - all identical
  is red. Plus a second one that checks that every model is switched
  with exactly its own code and a third that counts that the pairs
  switch two at a time.
- **B439 - an order travels as a name.** The two order trials are not
  models: they swap whole functions, and a function object does not
  survive the pickling to a child process. That is why they have moved
  to `modules/model_orders.py` and the NAME travels; the child builds
  the replacements itself. They could not stay in `test_panel.py`,
  because that file imports PySide6 at the top and a measuring process
  has no business near a widget library.
- **B439 - the serial fallback left the variant standing.** Found along
  the way: `_measure_one` is written for a child, which gets thrown
  away, and so sets the model state without putting anything back. On
  the serial route that same function runs in the PARENT process, and
  then the program carries on afterwards with the last variant it
  measured. That route only occurs on a locked-down machine, and there
  of all places it would have been impossible to find. The state around
  it is now saved and restored, with `model_register.current_settings()`
  as the counterpart of `apply_settings`.
- **B440 - a broken report must not read as a result.** 1.5.11a reads
  its clusters from the pair table of 1.5.10 and concluded from 190
  times zero that no pair touches any other. That stood as a finding in
  `docs/modelcombinaties.md` for months. The cluster trial now refuses a
  matrix in which EVERY difference is exactly zero - a real measurement
  never gives that 190 times in a row - and the report from now on
  carries the version number it was made with. The two existing reports
  have been marked invalid with a block at the top, including which
  sections do hold: the coverage and word/syllable tables run over
  threads in the same process, there `setattr` does work and there are
  real differences in them.
- **B440 - and the test suite overwrote the user's work.** While writing
  the above it stood out that `docs/modelcombinaties.md` kept coming
  back empty. Two tests walk through all the panel's actions and only
  redirected `MATRIX_REPORT`, not `COMBINATION_REPORT` - so every
  `pytest` replaced an hour of the user's compute time with the outcome
  of an empty test project, without anything reporting it. Redirecting
  per test is exactly what you forget the fifteenth time, so it now
  happens for EVERY test in `tests/conftest.py`: everything pointing at
  `docs/` is moved aside. A test that wants to read the real file does
  so via the path.
- **B441 - the held syllable, set at last.** `Syllable.held` has existed
  since B92 and `video.py` has been drawing a line under it for just as
  long, but nothing ever set the field: 1.5.7 counted exactly zero
  across 14308 syllables. The rule is the one from the inventory,
  unchanged, because that is the rule the 7.0% and the "all vowels" come
  from: a syllable counts as held at ≥0.35 s AND ≥4× the median of its
  own line. A pause does not take part - it is long by nature and is
  drawn as glowing dots.
- **B441 - derived and not stored, and that is the whole point.** The
  field is recomputed in `load_timing`, whatever the state in the file
  says. Two reasons: the stored value is false in EVERY existing
  project (the field was written out for years and never set), and it
  is a judgement about the spans - stretch a syllable in the editor and
  the marking has to move with it, which it cannot if it sits frozen in
  a file. That way all seventeen existing projects get their held notes
  straight away, without a single `timing.json` being touched.
  Recomputed on the user's real projects: 6.0% of the syllables, all
  vowels, with the 2.39 s 'a' in Lied_S at the top - exactly the case
  1.5.7 pointed out as the longest one. The editor recomputes when
  saving.
  **Note: the videos look different because of this** - a line now
  appears under a held syllable.
- **B441 - and the same line in word coupling.** There the mark does not
  come from the timing but from the transcription itself: Whisper says
  per word how long it lasted, so the question can be asked BEFORE there
  is any timing. That is exactly where it is useful - it is there that
  the user spreads the stresses over the karaoke text, and "this word is
  sung for three seconds" is what he cannot read off the text. Not a
  fill colour but a line underneath, the same one as in the render: a
  held word is usually coupled just fine, and a fill colour would push
  its real status out of view.
- **B442 - chunking goes to production.** What the overnight run of
  v0.136.0 measured, now in the program: four songs, vocals not heard
  197.7 s for the single run against 71.5 s when the chunks fill the
  gaps. Two outcomes determine the shape. The gain is in the CHUNKING
  and not in a per-chunk prompt (B424: the global prompt won on two
  songs and tied on a third), so the chunks do not have to wait for a
  first transcription - and that is exactly what makes one queue
  possible instead of two rounds. And chunking WITH VAD was worse on all
  four (B425), so no VAD. The whole run is the heaviest single task and
  starts first, the chunks follow in descending length: the user's rule.
  A chunk may only FILL - where the whole run heard a word, that word
  stays. Switchable off with `chunked_transcription`, and it hangs in
  the dependency chain like the forced alignment: switching it on or off
  gives a different transcription, and everything hanging off it has to
  go then.
- **B442 - and the new group must not wipe the existing projects.** The
  risk with a new signature group: if a group that was not there last
  time counts as "changed", seventeen projects lose their derived work
  on the first start. `sync_input_changes` only compares groups that
  already occur in the stored state, so that does not happen - but that
  is now pinned down in a test, because it is the kind of thing you lose
  one refactor later.
- **B443/B444 - recording where this runs, and what could be newer.**
  The user's request: something gets developed now and then, and when
  odd things happen you want to be able to tie that to an update or rule
  it out. At every start the versions of the app, Python and fifteen
  packages are written to `docs/pakketversies.json`, but ONLY if
  something changed - a line per start would be thousands of identical
  lines within a month and then nobody looks at it any more. What does
  change gets a readable line ("torch 2.3.0 -> 2.4.0"), disappearing and
  coming back included. Costs nothing: no network, no heavy imports. The
  update check itself is deliberately NOT in the program: pip means the
  network and a subprocess, and a start must never wait on that. The bat
  starts it in the background, it decides for itself whether it is its
  turn (at most once a day), writes to `docs/updates.json` and the
  program reads that at the NEXT start. So the news is always one start
  late, and that is better than a start that hangs on a slow mirror. A
  report older than fourteen days no longer counts.
- **B445 - the bookkeeping that belonged to nobody.**
  `output\settings\project.json` has been sitting on the user's machine
  since the end of July with the video titles of "Lied G
  " in it, and complained at every start that its structure
  was wrong (the file predates a rename and still has `stappen`
  instead of `steps`). Cause: the state before a song has been chosen
  has no song, so `settings_dir` is `output/settings` - and that
  bookkeeping was allowed to write. That is no longer allowed; reading
  is, otherwise an existing file suddenly becomes invisible. The stray
  file is named explicitly with the message that it belongs to no
  project and may go, and is otherwise left alone: a program that
  quietly cleans up files in a folder called "output" is a program you
  no longer trust.
- **B446 - language debt, second term.** `KaraokeTool.py` and
  `modules/config.py` were substantially touched this turn and are
  therefore fully converted. The guard from B438 now also looks at the
  eleven files this release touched plus the entry file, so the debt can
  only get smaller.

What this means for the measurements:
- The numbers of 1.5.9, 1.5.10 and 1.5.11a from v0.128.0 up to and
  including v0.137.0 are unusable and have been marked as such. 1.5.5,
  1.5.7, 1.5.8 and 1.5.11b through d are untouched: those run over the
  history or over model codes.
- The last valid cluster trial ran on v0.127.0. So 1.5.10 has to run
  again before 1.5.11a can say anything.
- 1.5.10 will give different numbers in the "shape" column of the Word
  and syllable section: `held_not_last` could never fire because nothing
  set `held`, and now it will. That is a diagnostic column, not an
  alarm - `timing_checks.broken()` does not look at it.

What a critical re-read of this release turned up as well (all fixed
before anything was delivered):
- **B442 - pressing Stop could have cost a project its manual timing.**
  The first version of `run_over_lanes` swallowed `CancelledError` per
  lane and simply returned what had already come in. The whole run was
  then silently missing from the result, `_transcribe_in_pieces`
  returned zero segments, and `detect_track` wrote that into the cache
  as a successful transcription, set the step to done and called
  `invalidate_after_fresh_transcript` - and that chain runs all the way
  through to `output:timing`. The rescue from B429 sits only in
  `sync_input_changes`, so it would have done nothing here. One Stop at
  the wrong moment and an afternoon of handwork was gone, while the GUI
  neatly reported "stopped". Cancellation is now passed on hard: no half
  run comes out any more, plus a safety net that refuses to return if
  the whole run is missing for whatever reason.
- **B439 - the child process set an order and never removed it.**
  Exactly the same mistake as the one this release repairs, one process
  further along. `model_orders.apply()` assumed a child gets thrown
  away, but B399 in fact keeps ONE pool alive for the whole action. The
  second order variant therefore stacked on top of the first (its
  `real_clean` had become the first order) and every later round WITHOUT
  an order silently carried on with it. The child now restores in a
  `finally`.
- **B442 - the chunking happened on the wrong timeline.**
  `_vocal_windows` projects the vocal windows onto the KARAOKE timeline,
  and that is right for everything that works with the karaoke text. The
  chunking however works on the vocals of the ORIGINAL: it cuts that
  file and it judges word times measured in that file. With an alignment
  on top both shift, so the chunking lands beside the real silences and
  correctly heard words drop out as "not on vocals". Invisible on a
  first run (the projection is the identity then) and wrong on every
  retranscription after that. There is now `_original_vocal_windows`.
- **B442 - the whole song was decoded again for every chunk.**
  `audio_slice` did a full `librosa.load` with resampling per chunk, ten
  to fifteen times per song. Measured: 1.66 s for the first chunk, 0.0001
  s after that now that the decoded audio is held on to as long as it is
  being cut.
- Smaller: a failed chunk did not count towards the progress (so the bar
  never arrived), two lanes could report their progress over each other
  which made the bar run backwards, `versions` was not in the redirect
  of `conftest.py`, and switching back to "no song" still created a
  writable bookkeeping file in the shared place in the GUI.

Included in v0.139.0:
- **B447 - the colouring sweeps, it no longer flips.** The user's report
  was "a bit too jerky", and the cause was in one line:
  `elif moment >= syllable.start: color = sung_color`. A phonetic piece
  flipped over as a whole as soon as its start time had passed. With
  short pieces that is not so bad, but a held vowel of two seconds
  stands still for two seconds and then jumps through in a single frame
  - a series of jumps of unequal size instead of an even sweep.
  Now `_sung_share` gives the elapsed fraction and `_draw_swept` draws
  the piece twice, with the right-hand strip pasted back from the first
  version. One letter in two colours, with the boundary exactly at the
  sweep position. Only the piece on the boundary pays for that;
  everything before it is entirely sung and everything after it not at
  all, and those go in one go as always.
- **B448 - fifty frames, and a shift that also starts softly.** The
  line shift already existed (B242, 0.35 s with damping), but that
  was nine frames at 25 per second - just few enough to read as
  steps. At fifty it is eighteen. And the damping was `(1 - t)²`:
  that lands softly but starts at full speed, so the first frame
  of every shift was a jolt, no matter how high the frame rate was
  set. Now a smoothstep, which slows down at both ends. The frame
  rate in an existing `config.json` stands at the old 25 and is
  lifted once, with a marker in the file so that it really is only
  once - without that marker 25 would be the only value the user
  could never save, and that is the opposite of a setting. Audio to
  256 kbps: the user indicated that file size is no objection, and
  with a source that is itself already lossy that saves a
  generation of loss.
- **B449 - the line gone, on request.** Out of the video, because there
  the colouring already does that job, and out of word coupling. What
  stays is the marking in the stress editor, and there it means
  something: there the original and the karaoke lie side by side.
- **B450 - the stress editor around the recording instead of around a
  spelling rule.** The user pointed out the mistake: po-lo-NAI-se has the
  stress on the third syllable and `apply_default_stress` says "po". That
  rule guesses from spelling, and there is no stress lexicon -
  `phonetics.py` knows vowel groups and clusters, nothing more. But in its
  own setup that is not needed either, and that is the nice part of it:
  the original has already demonstrated where the stress lies. Per line
  there are now two rows on one time bar. You click a piece of the
  original and then the karaoke piece that belongs to it; that takes over
  the time of the original and `fit_between_anchors` arranges the rest of
  the line proportionally, with a lower bound per piece and a message when
  the line is full. The word boundaries of the original come from the
  forced alignment - measured - and within a word the division uses the
  same phonetic rule the karaoke side uses. So measurement stands where
  there is measurement and a model where there is none, and the two rows
  are comparable because they are divided the same way.
- **B450 - and the stress itself stays settable by hand.** Right click.
  That is there on purpose: coupling on the left was the new function,
  but removing the old one would take away something that was in use.
- **B451 - a rescued timing.json takes its mate along.** Found while
  working out why Lied_Q had disappeared from the matrix.
  `output:timing` covers `timing.json` AND `timing_auto.json`, so an
  invalidation takes both of them; the rescue from B429 only wrote the
  first one back. The handwork survived and looked fine - but the
  yardstick needs the PAIR (it measures how far the hand shifted the
  automatic timing) and silently skips a project without one of the two.
  Lied_Q and Lied_O had disappeared from EVERY measurement
  that way without anything standing anywhere. The automatic file now
  goes through the same `carry_over` as the handwork, so the pair keeps
  fitting together; if that fails, nothing is written - a mismatched
  pair is worse than a missing one, because a missing one at least
  stands out.
- **B452/B453 - the brake out, the letters in.** The threshold of
  twenty versions in practice only held back 1.5.11a and b (c and d
  were already at 1), and it protected exactly the outcome we knew to
  be invalid: 1.5.11a last ran on v0.127.0, eleven versions back, and
  those eleven versions are exactly the period in which the matrix
  measured nothing. Out with it. What replaces it is what the user
  proposed himself and what the light actions already did: once per
  version per state, with a fingerprint over the project files, the
  transcription cache and the model state - so a new project does run,
  and a changed file too. For 1.5.11a and b the unit is the whole set,
  because those measure the set as a whole. And from now on you tick
  per letter.
- **B454 - two trials switched off, not thrown away.** 1.5.11c answered
  B391 three times with no, six of its eight variants were already
  retired, and by its own measure `current` now beats VAD (31 words /
  21.9 s against 30 / 16.0). 1.5.11d cost 3975 of the 4297 seconds of
  the whole heavy batch - 92% - to confirm every time what has been
  running in production since v0.138.0. Both off the way a model goes
  off: the idea stays readable and switching on is one word.
- **B455 - the "la la la" that was erased.** The user saw it disappear
  as a hallucination "with 50% confidence". That 50% was not Whisper's
  certainty but the best lyric match: `phonetic_key("la")` is `"la"`,
  the similarity with `"lang"` is exactly 0.50, and the floor is at
  0.65 - so "resembles nothing", and with one word below 0.6 confidence
  the whole segment goes. The cause is a gap I had half closed myself:
  at B427 I established that one song sings "na-na-na" while Whisper
  writes "la" and the karaoke text "la-la-la", and that for a guard you
  are better off too lenient than too strict. That was applied to the
  measurement at the time and not to the filter, while a wrong judgement
  here does not skew a number but erases a segment. The filter now reads
  both texts (`lyric_keys`, since B442). Plus a second rule: a segment
  that repeats one short word is singing. Whisper hallucinates plausible
  sentences, not singing; three times the same short word is enough to
  see that.
- **B456 - one level for every video.** Measured on the delivered mp4s
  they ran from −12.6 to −23.6 LUFS: eleven decibels, and so reaching
  for the knob at every video. The vocals diverge even further (−10.5 to
  −26.9, sixteen decibels) and Lied_I and
  Rood_Witte_Zangers are already ten decibels too quiet at the source.
  The user first chose −11 and let it go when the numbers came in: the
  loud tracks already squeak against 0 dBFS, so at −11 all eighteen
  would have to go through the limiter with peaks of 7.1 dB. At −16
  thirteen of the eighteen get a straight gain - untouched - and the
  other five have to give up 2.1 dB at most. Hence −16, with
  `linear=true` so ffmpeg only gets dynamic where there is no other way,
  and with the measured and the achievable value in the log so it is
  visible WHICH track had to give something up.
- **B457 - and the question underneath it, as a measurement.** Does a
  louder vocal help Whisper? The correlation between the loudness of a
  vocal and the error of that project is −0.3 - the right direction but
  far too weak - and the quietest song of them all got the BEST result
  in 1.5.11d. So an open question, and that belongs measured and not
  assumed. 1.5.11e runs the vocals at three levels along the same
  columns as 1.5.11d, and goes off as soon as it says yes or no.

What a critical re-read of this release turned up, all fixed before
anything was delivered:
- **B450 - the coupling stood back to front.** `couple_timing` builds
  `mapping` as `{karaoke line: original line}` and the two other readers
  in `gui.py` use it that way; the new editor unpacked it the other way
  round. Invisible as long as the coupling is one-to-one, and wrong as
  soon as it is not - exactly the case the editor exists for.
- **B450 - and the fitting could produce times back to front.** The
  editor lets you couple in arbitrary order, and two karaoke pieces may
  point at the same piece of the original. Neither is a mistake to
  refuse, but both gave a line with times running backwards - the one
  thing that function promises never to do. The anchors are now walked
  in order, kept inside the line, and a normalisation at the end
  enforces the promise instead of hoping for it. Checked with six
  thousand random cases: not one broken.
- **B450 - uncoupling did nothing.** Every recomputation started from
  the already recomputed times, so releasing a coupling could not go
  back. Together with "closing saves" that meant: one trial click and
  the manual timing of that line was permanently gone. The recomputation
  now always starts from the state at opening, and saving only happens
  on Save - not on Escape or closing.
- **B456 - silence gave −inf and the render died on it.** loudnorm
  refuses its own measurement back ("value out of range [-99 - 0]"),
  while this step promises to fail quietly. An unusable measurement is
  now no measurement.
- **B456 - and every video got 96 kHz.** loudnorm computes internally at
  192 kHz and passes that on; without `aresample` everything was encoded
  at 96 kHz - twice the file size for sound nobody can hear the
  difference in.
- **B448 - the frame rate was lifted at EVERY start**, which made 25
  the only value you could not save. Now with a marker, so it happens
  once.

Included in v0.140.0:
- **B458 - the la-la-la repair cost 0.56 s, and the measurement pointed
  out where.** 1.5.11a ran for real for the first time, and gave a
  baseline of 3.72 s where the matrix had given 3.16 s a day earlier. I
  could have waved that away as a different project set, but there was a
  control in the same table: with B258/B285 OFF the yardstick gives
  exactly 3.23 s in BOTH runs. Switch the filter off and nothing has
  changed; switch it on and it is 0.56 s worse. So the whole regression
  lies inside that filter, and so inside what I did to it at B455.
  The cause is that B455 did two things at once. The chant rule - a
  segment that repeats one short word is singing - is narrow and only
  looks at the SHAPE of the segment; that was the part that was needed.
  But I also let the karaoke text count in the general match threshold,
  and that is the parody with completely different words. As a result
  almost every invented segment found a match above 0.65 somewhere and
  stayed: the la-la-la saved and the hallucinations let in with it. The
  second text now only serves the chant decision - "na-na-na" in the
  original and "la-la-la" in the karaoke text are then both fine - and
  the threshold runs against the lyrics only again.
  Visible in the same table: where switching B258/B285 off COST 0.07 s
  in v0.138.0, it GAINED 0.49 s in v0.139.0. The filter had gone from
  mildly useful to harmful.
- **B459 - the level check rejected all music.** After the re-read of
  v0.139.0 I added a range check because silence gives `-inf` and loudnorm
  drags the render down with it. I demanded −99..0 for four values at
  once, among them `input_lra` - and that is not a level but a dynamic
  RANGE in LU, so positive for anything that resembles music. Consequence:
  every measurement came back as "no measurement", and with that both the
  normalisation in the video and the whole trial 1.5.11e silently did
  nothing. The user saw it from the empty columns; the videos would simply
  have stayed at their old level without a single complaint.
  What makes it worse: my own smoke test approved it. That used a pure
  sine, and that is precisely the only signal with a dynamic range of
  exactly 0.0 - the only value that got through.
  There is now a test on material with a quiet and a loud part, plus one
  that pins down that a sine was that gap.
  The ranges are now loudnorm's own, each separately: level and threshold
  −99..0, range 0..99, and the peak may be slightly above zero - "Lied M
  " peaks at +0.12 dBTP and that is a perfectly ordinary track.
- **B460 - 1.5.11e ran on one Whisper process.** The agreement has been
  two lanes since B396 and the user saw one. Rightly: I had written the
  trial as an ordinary loop, song by song and level by level. Now
  everything goes into one queue over `whisper_lanes()`, longest song
  first, and the ffmpeg work (the converted levels) happens up front so
  the lanes only have to transcribe.
- **B461 - the panel showed a selection and meant nothing.** The user
  ticked a and e, unticked b, pressed start and nothing happened. The
  letters opened ticked while 1.5.11 itself was off - heavy actions
  always start off - and on start only that one tick is looked at. So
  the panel showed "a, b, e on" and meant "nothing selected". Now the
  letters start off like the number, ticking a letter switches the
  number on, and the number pulls its letters along. With a lock in
  between, otherwise the two switch each other on in a circle.
- **B462 - "measured on 16 projects" were 14.** `_measurable_projects`
  only looked at whether there was a `timing.json`, but the yardstick
  needs the pair and returns nothing without `timing_auto.json`.
  Lied_Q and Lied_O stood in the header of the report for a
  whole day that way without contributing a single line. They are now
  named explicitly, with what can be done about it. The docstring of that
  same function incidentally boasts that it exists to prevent exactly this
  kind of counting-without-measuring - one level down it was still in there.
- **B463 - and the missing file can be remade.** The automatic timing is
  not handwork: it is what the coupling produces, and the yardstick
  recomputes it internally at every measurement anyway. So it can be
  written again too, and that happens in 1.5.1 - the step that prepares
  what the measurement needs. `timing.json` is not opened in the
  process; THAT is handwork. Refuses at a different line count than the
  manual timing: a pair that does not fit is worse than a missing one,
  because a missing one at least stands out.

What 1.5.11a produced, now that it finally could:
- One cluster of eight models, 256 combinations. The strongest single
  effects are B332 phrase period (+1.35), B329/332/340 anchor check
  (+1.18) and B329 reference duration (+0.70) - all worth switching on
  and that is how they stand.
- The interaction v0.115.0 already suspected is now hard: B313 +
  B329/332/340 switched off together gives 6.19 s where added separately
  4.22 was expected. Those two are each other's safety net.
- The best setting found was B213 + B258/B285 + B377 set differently, at
  2.99 s. B258/B285 is in there, and that is exactly the filter B458
  changes - so that outcome has to be measured again before anything is
  done with it.

Included in v0.141.0:
- **B464 - the chant rule exempted exactly the wrong shape.** At B455 I
  wrote down that Whisper invents plausible SENTENCES and not singing,
  and on that I built an exemption: a short word standing three times in
  a row is singing. That assumption is wrong. A repetition loop is in
  fact one of Whisper's signature hallucinations - on an instrumental
  passage it produces "la la la la la" without anything being sung. So I
  had made a rule that explicitly protected the most common
  hallucination.
  The yardstick pointed it out, and within each run separately, so that
  the project set did not matter: the filter was worth +0.07 s before
  B455, -0.49 after it, and -0.40 after the first repair of B458. So
  that first repair took only 0.09 of the 0.56 off; the rest was in the
  chant rule itself.
  What distinguishes the user's la-la-la from a loop is that HIS is
  repeated in the text as well - he writes "la-la-la" or "na-na-na"
  wherever a passage really is chanted, and a word that is sung once
  stands there once. Hence `chanted_keys`: only syllables that occur
  repeated back-to-back in the lyrics or the karaoke text are exempted.
  One of the two texts is enough - the original may sing "na-na-na"
  where the karaoke text writes "la-la-la" - but without a text there is
  no exemption any more.
- **B465 - remaking videos, on request.** A temporary action 1.5.12:
  every project that already has a video gets another one with the
  current settings, next to the existing one. All under the same number
  `_3`, also where a project only had one - `next_video_target` would
  take the first free number and then one project gets a `_2` and the
  next a `_3`, and then you can no longer see which files come from
  this batch. Never overwrites: if the number is already taken, the
  project is skipped and reported.
  It does not join in with "tick everything". That exception only
  existed for heavy actions; `TestAction` now has a second flag for
  slow-but-no-measurement, because one click on "everything" should
  never start rendering videos for an hour. For the same reason it
  does not count towards the ceiling of ten ordinary actions.
- **B465 - and the guard on temporary code looked straight past the
  English.** There is a test that goes red as soon as a file with a
  `TIJDELIJK` marker turns up that is not on the release list. That
  one only looked for the Dutch word, while the code was converted to
  English at B438 and B446 - so there had been a `TEMPORARY` function
  in `pipeline.py` for months that was named nowhere as an open
  decision. The guard now knows both words and the list has been
  completed.
- **B466 - say WHAT is wrong.** The refusal to build an automatic timing
  reported "different line count" and there is nothing you can do with
  that. The two counts are now given alongside, and then it is
  immediately clear: Lied_O has 55 manually timed lines against a
  karaoke text that yields 41. That is not a fault in the repair but a
  project whose handwork is older than the text, and only the user can
  solve that.
- **B467 - two clocks side by side.** The user noticed that the same run
  gave 49.2 s "not heard" in 1.5.11d and 68.8 s in 1.5.11e. Cause:
  `_vocal_windows` projects the vocal windows onto the KARAOKE timeline,
  and that is right for everything that works with the karaoke text -
  but these trials transcribe the vocals of the ORIGINAL and compare
  those word times against it. Two measurements from different clocks,
  then.
  It turned out to be broader than the two trials: 1.5.8 and the gap
  detection did it that way too. With that, the 22% unsung vocals, the
  number the whole chunking thread started with, has been measured
  against the wrong windows as well. Without alignment the projection is
  the identity and nothing changes; on every project that has run step 3
  the gaps lay beside where they really are. All four now stand on the
  timeline of the file they actually listen to. Count on the numbers of
  1.5.8 and 1.5.11 shifting because of it.

What 1.5.11e produced, and why the question is still open:
- Vocals not heard per level, across four songs: as it is now 220.2 s,
  at -16 LUFS 245.3 s, at -11 LUFS 193.5 s. So the loudest level wins on
  the total by twelve percent and on three of the four songs.
- But it is not a clean answer. On Lied_T it gets worse
  instead (47.1 -> 68.2) and "in lyrics" drops to 62%, and that is
  exactly the warning that the extra words are inventions. And -16 is
  worse on the total than doing nothing.
- The assumption the trial was built on has been refuted: Groen at
  -27.0 LUFS is by far the quietest vocal and barely changes
  (30.6 -> 27.9), while the song that benefits most sits at a perfectly
  ordinary -14.3. So level is not what makes the difference. That is why
  1.5.11e stays on for now and nothing goes to production.

Included in v0.142.0:

- **B468 - videos of the user's disappeared, and the render did it
  itself.** Reported twice ("Lied A", "Lied_P"): an
  existing mp4 was gone, while step 2.4 simply produced a result again.
  The cause was not in a cleanup action - there is no line in the whole
  chain that deletes an mp4, and `video` is deliberately a STEP without
  sources (B353), so invalidation never touches it. It was the render
  itself: `ffmpeg -y ... str(target)` writes straight to the final
  target and truncates that file the moment the process starts, so
  before there is a single frame in it. If the render then breaks, or
  the user presses Stop (`proc.terminate_all` does a hard kill, no
  SIGTERM, so no moov atom), the complete old video is irrecoverably
  gone and a fragment is left behind. Rendering now happens next to the
  target (`<name>.part.mp4`, the same folder so the move is atomic) and
  is only put in place with `os.replace` after a successful ffmpeg;
  EVERY exit cleans up the half file - a broken pipe, an ffmpeg that
  fails, and also any other error along the way (on Windows a write
  error does not always come in as `BrokenPipeError`). So the existing
  file is never touched until there is a complete replacement. If the
  move itself fails - on Windows that happens when the old video is
  still open in a player - the message says exactly that, and the new
  video stays ready as `.part.mp4` instead of being lost.
  `existing_videos` skips those half files, otherwise "Open video"
  offers a broken file.
- **B469 - a custom output folder cost all input folders at every start.**
  `prune_orphan_projects` (B112) compares the input folders with the output
  folders and had `root/"output"` hard-coded. If a custom output folder is
  set (B214), that place is empty and EVERY project looks like an orphan,
  after which `shutil.rmtree` goes over the input folder. On top of that the
  cleanup in `KaraokeTool.py` ran BEFORE that setting had been applied. The
  function now gets the output folder handed to it and the call sits after
  the paths have been built. There is a brake on it as well: if there is not
  a single project in the output folder, nothing is cleaned up. "Empty
  output folder" means "I cannot see it", not "they are all orphans" -
  without that brake the first start after moving the output folder would
  still wipe everything. Testing whether the folder EXISTS is not enough:
  the app creates it itself one line earlier. This is not the cause of B468
  (it only touches input), but it is real data loss and it stands armed,
  waiting for the first time the output folder is moved.
- **B470 - artist and original title were missing from the video in four
  projects.** They sit per project in `project.json` (B210) and only end
  up in `config.video` via `apply_project_titles`, which was called in
  exactly two places: at startup and on a project switch in the GUI. So
  every other render route - such as the batch render of 1.5.12 -
  renders with whatever titles happened to be in memory, and those get
  emptied first on a project switch. The file names did stay right (they
  fall back on `display_name`), which is why it only showed up on
  screen. `run_video` now loads them itself, so every route is correct.
  Second half of the same fault: a key missing from `video_titles` was
  skipped, which left the value of the previous project standing; a
  title this project does not have is now empty. What turned out NOT to
  be true: there is no setting for the intro duration - `INTRO_MIN_S`/
  `LEAD_IN_S` are a fixed 5 s and the intro cannot be shorter in this
  code. What the user saw was that minimum with an empty credit line
  underneath.
- **B471 - the original text was missing exactly where the coupling was
  bad.** Two causes. (1) B313 threw away the word times of a line
  without a single real coupling (`del per_line_word_spans`), with a
  good reason for the TIMING - an estimate must not become a measured
  value - but the stress editor reads that same list, and without words
  `original_pieces` falls back on (0.0, 1.0) and sticks the line at the
  front of the track. They are now kept and marked
  (`words_estimated`); the coupling still uses the filtered set, the
  editor everything. (2) If `interpolate_spans` returned nothing - not a
  single reliable time in the whole song - then the whole function
  returned `None`, and further on that means an EMPTY original lane. The
  text is there, only the time is unknown: the editor now builds that
  lane itself from `songtekst.txt`, spread evenly over the duration
  and with a proportional coupling, so that every line is visible and
  can be dragged. That safety net sits deliberately in
  `editor_originals` and not in `_original_lines_detailed`: the render
  timing already has its own way for this case (`fallback_even`) and
  must not go chasing a guess. The user's requirement was literally
  "not even with 0 or unreliable coupling, otherwise I can never get
  it in the right place".
- **B472 - a karaoke line without a coupling had none at all.** The
  mirror image of B471: `couple_timing` only set a mapping key for lines
  that came through one of the three branches. Anything falling outside
  (a stray interjection, or everything as soon as the blocks do not
  match) got no key - not `None`, simply nothing - and then the editor
  draws no coupling line for it and the line cannot be placed. Every
  karaoke line now gets a coupling: to the original of the line before
  it (an interjection belongs to the line it trails), otherwise that of
  the line after, otherwise the first. The TIMING is left untouched - an
  interjection keeps its short slot (B75).
- **B473 - two wrapped lines drew through each other.** The vertical
  positions came from a fixed table (0.34/0.56/0.70) and nobody measured
  how tall a line actually is. A line that runs over two rows through
  `_wrap_syllables` is about 104 px high, and between slot 1 and slot 2
  there is 101 px - so guaranteed overlap. The slots now stack: the
  fixed fraction is the place a line WANTS to have, and a tall line
  pushes the line below it further down. Only down, so as long as
  everything fits on one row the picture stays the same. That meant the
  smooth line shift from B242 had to come along: it computed with one
  distance for ALL lines (`slot_y(1) - slot_y(0)`), which was right as
  long as the slots were equally far apart. With a stack that is no
  longer so, and one distance for everybody made the just-sung line
  first JUMP down and then glide up - exactly the jolt B242/B448
  removed. Every line now starts where it really stood: at the place of
  the slot below it.
- **B474 - the 3-2-1 counter takes the place of the last sung line.**
  The user's suspicion was right: during an instrumental gap the three
  lines AND the counter were pressed over four evenly divided
  positions (87 px apart), and a line of two rows does not fit in
  between. His own solution is also the right one: that top line is
  done and nobody needs it any more. It disappears during the gap and
  the counter stands in its place; the lines still to come stay where
  they always stand. An exception, also named by the user: the counter
  before the very first text keeps its own place, because there is no
  sung line there yet to replace. The line only makes room at the
  moment the counter actually comes into view (the last three
  seconds); with a gap of twenty seconds there would otherwise be an
  empty area standing for seventeen seconds. And when the gap is over
  that line stays away: outside a gap the previous line is drawn along
  for the smooth shift (B242), and that would let it jump back exactly
  onto the place of the digit.
- **B475 - a crowd line simply moves along.** A short interjection was
  drawn as an EXTRA line under slot 0 and did not count towards the
  three visible lines. Because of that it stayed put where every other
  line shifts upwards and pushes the previous one out, and that reads as
  a fault. It now simply runs along in the flow; it stays red by itself,
  because that colour comes from `line.crowd` in `_draw_line` and not
  from its place on the screen. That also does away with the fixed crowd
  y of 0.45, which could collide in its own right.
- **B476 - the two rows of one line sit closer together.** It was one
  number (`ascent + descent + 2`), which on top of that stood loose in
  TWO places in the code - so measurement and drawing could drift apart.
  Now one `_row_height` with a fraction of the font height for the
  distance WITHIN a line, and a separate `_line_gap` for the space
  between lines. That way the picture shows which rows belong together.
  The space between lines is a fraction of the font height and not a
  fixed number of pixels, because the font scales with the picture: at
  4K the lines would otherwise stick against each other. For the
  distance WITHIN a line a fraction turned out not to work. Two values
  tried (0.82 and 0.90) and both collided: measured over the twenty-one
  bundled fonts, in ten of them the tail of row 1 ran through an
  accented capital on row 2 (É, Ö - ordinary Dutch), and the default
  font was the worst of them with eight pixels of overlap. What does
  work is measuring on the REAL ink of those two rows (`getbbox`): the
  bottom of the deepest letter above against the top of the tallest
  letter below, plus a bit of air. A row without tails comes up tight
  that way, a row starting with an É gets the space it needs, and that
  is right for EVERY font. With the fonts the user uses it really makes
  a difference: Oswald 97 px instead of 107, Saira 85 instead of 114,
  Baloo 81 instead of 116.
- **B477 - a thin outline around the letters of the active line.** For
  the contrast against a background photo. Every text colour has its own
  outline colour, so within one line the outline changes along with the
  sweep: the sung part carries the outline of the sung colour, the part
  still to come that of the waiting colour. By default the counter
  colour, determined on perceived brightness (0.299/0.587/0.114) with
  the boundary at half - black under a light letter, white under a dark
  one; a filled-in setting wins. The lines already sung get none, as the
  user asked: it no longer matters there, and it saves work per frame.
  In `_draw_swept` the outline runs along with the sweep and the
  pasted-back strip is widened by the outline thickness, otherwise the
  outline of the sung half stayed over the waiting half.
- **B478 - "Open video" only knew about this session.** The path sat in
  one global `_last_video` that was only set on a successful render and
  never reset, so after a project switch the button still pointed at the
  video of the previous project (screenshot: Lied_U with "Lied A
  _2.mp4" on the button) and a video from yesterday could not
  be opened at all. The button now looks in the output folder of THIS
  project. If there are several versions, a choice with the highest
  sequence number preselected - sorted on the number as a number,
  because as text `_10` comes before `_3`. The number is no longer on
  the button itself.
- **B479 - 1.5.12 is out, code and all.** The trial has done what it was
  made for. This is deliberately an exception to "a trial that yields
  nothing is switched off, not removed": that agreement is about trials
  whose outcome turned out to be worth nothing, and 1.5.12 was valuable
  but one-off. Gone are `rerender_videos`, `RERENDER_NUMBER`,
  `_numbered_target`, the flag `slow` on `TestAction` (which existed
  only for this), the six translation keys in nl and en, the row on the
  release list and the tests on it. `next_video_target` already does the
  numbered path neatly, so no reusable code went with it.
- **B480 - background images centralised.** A chosen image goes to
  `config/backgrounds` as `background_001.<ext>` and counts on from the
  highest existing number (not on the count, otherwise a new one gets
  the name of a deleted one). Choosing the same image twice yields one:
  compared on content, not on name. If there is at least one, a
  thumbnail list appears with selecting and deleting. Alongside that a
  copy goes to the input folder of the project as `background.<ext>`
  without a number, which is overwritten on a new choice - and the old
  extension is cleaned up, otherwise there are two and the render does
  not know which one to take. The render takes that project copy first,
  so a deleted central background never breaks a render. Checked as
  asked: the dependency chain does not have to do anything - an extra
  file in `input` is not in `_FINGERPRINTED`, and `video` deliberately
  hangs on nothing (B353), so nothing is invalidated wrongly. The render
  takes ONLY that project copy: the setting itself is global, and using
  it as a fallback would put the background of another song in this
  video - exactly the leak B470 above had to close for the titles. **The
  background therefore belongs to the song and no longer to the app**: a
  project that has not been given one does not have one. Watch out when
  switching over: a background that stood in the settings before this
  version applied to everything, and now has to be chosen once per
  project. Without a chosen project it refuses, incidentally, because
  `input` is then the shared folder and no loose file belongs there
  (B445). In the list the background that is switched on is selected, so
  you can see WHICH one it is; selecting does not switch it over
  straight away - otherwise a stored picture cannot be deleted without
  first changing this project's background. That is why there are two
  buttons underneath: "Deze gebruiken" (use this one) and "Opgeslagen
  achtergrond wissen" (delete stored background); double-clicking does
  the first one too. Furthermore the button is now called
  "Afbeelding verwijderen" (remove image) instead of "Terug
  naar standaard" and is only active when there is an image;
  without an image it says "Geen" and not 'standaard'. The whole
  thing sits under the row "Video-achtergrond" and no longer in a
  group of its own.
- **B481 - the waveform hint is out of the editor.** Including the
  translation key in both languages.
- **B482 - 1.5.11e left folders behind in %TEMP%.** `_at_level` made its
  own `mkdtemp` per converted file and never cleaned them up, not on the
  error route either. One scratch folder for the whole trial, cleaned up
  whatever happens. Note: that scratch folder is shared, and the vocals
  are called `vocals.wav` in EVERY project - the converted files
  therefore carry the project name, otherwise four songs write over each
  other and the whole trial measures the same track four times. Checked
  as asked: no other ordinary app function makes a temporary folder -
  the other two places are in the measurement code
  (`fill_transcription_cache` already cleans up neatly, and
  `tools/timing_regression.py` is the yardstick, which deliberately
  keeps a fixed folder so ffmpeg does not have to redo it every run).

Included in v0.142.1:

- **B483 - the line just sung turned white again in the top slot.** In
  `_draw_line` every non-active line got the waiting colour, whether it
  had already passed or was still to come. In the slot below the active
  line that is right (what stands there is still to come), in the slot
  above it is not: there stands what was just sung, and that should be
  grey. The bug has been there since the smooth line shift of B242, but
  went unnoticed because slot -1 hung at the top of the frame back then
  and was mainly visible during the 0.35 s of the shift; since the
  stacking of B473 that line sits right above the active line. A
  non-active line now looks at its own end time: past is grey, still to
  come is white. The outline stays off on a non-active line, as agreed.

Included in v0.143.0:

- **B484 - a `[bg]` tail turned the whole line into background vocals.**
  The user was missing chunks of the original text of "Lied R" in the
  editor. Measured in his own `project.json`: 43 original lines against
  55 lines with content in `songtekst.txt`, and the twelve that were
  missing all had a `[bg]...[/bg]` after the normal text
  ("Noon gam-go, ha-na, dool, set [bg]Twee-uh[/bg]"). Both text
  readers had the same bug: with `[bg]` and `[/bg]` on one line, that
  line was marked as background vocals in its entirety. In
  `load_lyrics` that set `is_bg_line` on every word of the line, in
  `parse_lines` `bg=True` on the whole `TextLine`. The docstring of
  `load_lyrics` already promised the right behaviour ("the enclosed
  words get bg=True"); the code did something else. The marking belongs
  to the words between the markers, exactly as inline `[crowd]` has
  done since B179a - so that pattern was already sitting right beside
  it. `_parse_inline` now does both markings in one pass, so that the
  word numbers of crowd and bg are counted on the same final word list
  and cannot drift apart.
  What was broken, in order: such a line had no non-bg words left, so
  it did not end up in `per_line_words`, so not in `detailed`, so not
  in `original_items` - gone from the original track. On the karaoke
  side it was pulled out of the list before the coupling, got the time
  of its predecessor via `attach_bg_lines` with `disabled=True`, and so
  disappeared from the render. And because twelve lines dropped out on
  the original side, the block sizes no longer matched the karaoke
  text, which made the one-to-one coupling fall back to the coarser
  branch. That also explains why the phonetic bits in Lied R "barely
  worked".
- **B485 - the piece stays part of its line.** Deliberate choice by the
  user between two designs: give the clipped piece its own line number
  (simpler code, but every number after it shifts and `timing.json` is
  built on those numbers - manual work gone) or keep it as part of its
  line. It became the second, in the same form as `crowd_words`:
  `TextLine.bg_words` with the word numbers, `Syllable.bg` per
  syllable. So nothing shifts and every existing `timing.json` stays
  valid; an old file without the field simply reads through
  (`syl.get("bg", False)`).
  What that piece may and may not do: it appears in both editors, it
  may lie over its neighbours in time, and it never reaches the render.
  That last one ran via `disabled` until now, and that flag is also the
  "line off/on" button - switch such a line on and you got it on screen
  after all. The render now looks at the syllables themselves
  (`_sung_syllables`), for the drawing as well as for the width, the
  height and the font choice. For the overlap to be allowed, three
  places had to stop working against it: `TimedLine.start`/`end` look
  at the sung side (otherwise the background vocals drag the whole line
  along - the full times are in `full_start`/`full_end`), `apply_spans`
  leaves bg syllables alone (the auto-fit works within the window of
  the line and would pull them back into it), and `_line_span` in the
  timing editor measures the line without that piece.
- **B486 - the piece may become an anchor.** Bg words stayed outside
  the alignment and outside the catch-up round that afterwards tries to
  match stored words after all (B276). Outside the alignment itself is
  right - that runs in order, and a bg word sounding at the same time
  as the main line would grab the transcription word of that main line
  - but the catch-up round after it costs the main voice nothing: those
  words are already claimed by then, and it only searches within the
  window between the coupled neighbours. Every hit is therefore gain:
  an extra anchor in a stretch where there was none.

What the critical re-read turned up, and what was changed for it:

- The brake from B469 could never trip: `ensure_directories` creates
  `output/settings` one line earlier, so "there is something in the
  output folder" was always true. The brake now counts only real
  project folders (`settings` does not count) and a second brake stands
  beside it: that ALL input folders are orphans at once is not a
  cleanup job but a sign of measuring against the wrong folder.
- The timing editor did not write `bg` out and did not read it back.
  Opening and saving once wiped the marking, after which the piece
  simply appeared in the video - exactly the promise this release makes.
- The energy word timing (B234) spread ALL syllables over the window of
  the sung side. That pulled the bg piece back inside and shortened the
  line by the share of that piece.
- Nothing set `bg` on a `timing.json` that already existed. Adding
  markers changes not a letter of the line (they are stripped out), so
  neither the text comparison nor the carry-over noticed a thing. The
  marking is now read back out of the text on loading
  (`mark_inline_pieces`), for the render and for both editors. That is
  at the same time the reason nothing else has to be repaired in
  existing projects.
- On the lyrics side an inline `[/bg]` closed the enclosing `[bg]`
  block, on the karaoke side it did not. The two readers contradicted
  each other; now an inline closer falls back to the block state, as
  crowd already did.
- Gluing the bg words onto the line text made the word count differ
  from the measured word windows, so the stress editor (B450) fell back
  to even distribution for exactly those lines - and it moved a bg
  piece that stood in front to the back. The line keeps its own words;
  the piece travels along as a separate field and is shown in the
  original track in square brackets behind the line.
- B472 (every karaoke line has a coupling) made the mirrored row of a
  loose interjection disappear from the original track and stretched
  the bar of the original line over it. Such a line no longer counts there.
- Smaller: `mark_held` took the bg piece into the median of the line
  and could mark it as a held note itself, and `spread_flattened`
  redistributed it along. Both now look at the sung side.

And what a third round turned up on top of that:

- `apply_phonetic_timing` passed `held`, `stress` and `crowd` on to the
  new syllables but not `bg`. That step is on by default and runs on
  EVERY fresh timing, so no file ever ended up with a marking in it at
  all - the whole change was still living on nothing but the read-back
  fix above.
- `mark_held` ran in `load_timing` before the marking had been read
  back, so the bg piece sat in the median of its line after all. After
  the read-back the held notes are weighed again.
- `full_end` read `syllables[-1]`, the last one in TEXT order. A piece
  that stands in front and lies over its neighbours fell outside that;
  it is now the last one in time.
- `_reflow_line` also spread the bg syllables over the window of the
  sung side when the length differed, so the line lost time to the
  piece. The same exception as with `apply_spans` and
  `distribute_over_windows`.
- An attached `[/bg]` was handled separately before the split loop, so
  "Tonight[/bg] my dear" became background vocals from start to finish
  and a line ending on an opening marker did not pass the block on. All
  markers now run through the same loop, on both sides; a test compares
  the two readers on nine spellings word for word.
- `apply_inline_crowd` laid the word numbers from the text down without
  checking them against the timing. If a line's word count no longer
  matches, the marking lands on the wrong word - and a word that
  wrongly becomes bg disappears from the video entirely. Such a line is
  now skipped with a message in the log.
- The second brake on the orphan cleanup logged the reason of the first.

What has to be redone after this change, and why:

- **Lied R** - eight lines sit in `timing.json` as disabled (24 through
  29, 39 and 47). That flag came from `attach_bg_lines` back when they
  were still seen as whole bg lines; now they are normal lines with a
  background tail and they belong on. This is the only thing that does
  NOT come right by itself: `disabled` is also the "line off/on"
  button, so the app cannot tell whether that flag comes from the old
  bug or from a deliberate choice. Switch those eight lines on in the
  timing editor. The line numbers do not shift, so the manual timing
  itself stays valid.
- **Lied_U** - the karaoke text has no inline `[bg]` at all, so
  nothing changes on the karaoke side and the manual work stays
  entirely intact. On the original side six lines come back (59 of 59
  instead of 53), so the coupling gets better as soon as 1.2 runs
  again.
- **Lied_R2** - no timing yet, so nothing to repair.
- **Lied_P** - two inline `[bg]` in the karaoke text, but not
  a single line in `timing.json` is disabled; so there is nothing to
  restore there.
- The other sixteen projects use `[bg]` only as a line of its own or
  not at all and are untouched.

Included in v0.144.0:

This round is the whole collected list in one go, at the request of the
user ("keep building until everything is off the list").

- **B487 - the outline is on EVERY line.** At B477 it said "only the
  active line", because the user said it no longer matters on a line
  that has already been sung. That was read too literally: on his
  screenshot of "Lied U" the green active line has a border and
  the grey line above it and the white one below it vanish against the
  background photo. Now every line gets one, in the contrast colour of
  the colour it has at that moment - grey for what is past, white for
  what is coming, red for crowd. The lighting dots of an inline pause
  too, the title in intro/outro and the credit line under it; the
  3-2-1 counter already had one. Part of that is that the two rows of a
  broken line keep room for that border: those sit deliberately tight
  (B476, measured on the real ink) and a border grows on both sides, so
  `_row_air` and `_line_gap` are never smaller than the border
  thickness on two sides plus two pixels.
- **B488 - an empty block is still a block.** With "Lied R" the
  coupling ran out of step from one line onward, with "extra couplings
  and such". The blocks are 4-8-4-4-4-8-8-4-4-4-1-2 on both sides, but
  the last block of the karaoke text consists of two lines that are
  entirely `[bg]`; those are pulled out of the list before the
  coupling, after which `[b for b in karaoke_blocks if b]` threw the
  empty block away altogether. 11 blocks against 12, so `couple_timing`
  fell back to its coarsest branch (spreading 53 karaoke lines evenly
  over 55 original lines) and skipped lines. With the empty block as an
  empty SPOT every karaoke line couples one-to-one again - recomputed
  on his own texts: 53 of 53, not a single deviation, and only the two
  "Twee uh" lines stay uncoupled because their counterparts are all `[bg]`.
- **B489 - an uncoupled original line was on a different clock.** A
  coupled line gets the time of its karaoke line in the track; an
  uncoupled one fell back to its own time from the original. With
  Lied R that is half a minute apart, so such a line visibly jumped
  forward and stood in the wrong order. It is now placed between its
  coupled neighbours, so the whole track runs on one clock.
- **B490 - "overwrite" takes the latest video.** After saving side by
  side a few times the newest one is `_3`, and then overwriting the
  first render is never what "one more time" means.
- **B491 - 1.5.11e goes off.** The question has been answered and the
  answer is no. Over four songs the harshest level wins on the total
  (193.5 s not heard against 220.2 as it stands now), but it loses
  badly on Lied_T, where "in text" drops to 62% - those
  extra words are inventions, not singing that was finally heard. And
  the assumption underneath is refuted: Groen at -27.0 LUFS is by far
  the softest voice and barely changes, while the song that gains most
  sits at a perfectly ordinary -14.3. Off, not gone - as agreed.
- **B492 - a line with a pause got cut in half.** Reported twice: "the
  line ends up on the time BEFORE the pause, I have to drag it over the
  second part by hand". B224 shortens a line that runs on into silence,
  and measured that with `active_end`. That function searches from
  right to left for the first silence gap of 0.3 s and returns the last
  active moment BEFORE it - fine when a line is stretched onto the next
  line, wrong for a line with a pause of its own in the middle, because
  then that gap is the pause itself and the second half drops off.
  There is now a `last_energy` that answers the simple question - where
  does the singing stop within this window - so that only the trailing
  silence gets clipped away.
- **B493 - the pause decides where the line splits.** `is_pause` drove
  nothing at all outside `mark_held` and the render. The distribution
  over the singing windows (B234) computed the boundary from window
  duration, and that regularly landed on a different word. If there is
  a `[pause]` in the text, that is the user saying WHERE the line falls
  apart; that now leads as soon as the pause count matches the gap count.
- **B494 - stretching scales instead of spreading out.** `_reflow_line`
  made every syllable equally wide when the length differed. That
  throws away ALL the measured fine timing, the pause in the middle
  first of all - exactly the second half of his complaint. Scaling
  keeps every ratio and puts the line just as precisely on its new window.
- **B495 - a passage in another script.** The language detection works
  on Latin words and does not see Korean. A block of Hangul is not a
  probability either but a fact, so that is recognised on the
  characters, with the user's threshold: more than two words in a row,
  or more than five in the whole song. At 1.1 it then asks which
  language Whisper should listen in, before the transcription -
  afterwards it costs a whole run again. Note: with "Lied R" the Korean
  is phonetic in Latin letters and there is nothing to see; so that
  question only comes up with "Lied_R2".
- **B496 - pulling lines back from the original.** The user wants the
  isolated "eehee's and ow's" back in the places where they belong. The
  mechanism already existed (B282: a piece of the original that
  REPLACES the karaoke there one-to-one, with a crossfade at the edges
  - exactly what he asked for, and no mixing); what was missing was the
  way to get there. In the timing editor you can now point at a line;
  that is stored per line number and, on muting, turned into a restore
  block on the timing of THAT moment - derived on purpose and not
  pinned, so the piece of original moves along when you move the line.
  In both editors such a line gets its own blue colour, so you can see
  it was not drawn in 1.4 but chosen in 2.3. On the dependency chain:
  `restore_lines` deliberately does NOT hang on the timing - they are
  line numbers, and a timing change does not invalidate the edited karaoke.
- **B497 - adjusting syllables after manual work.** The user's idea:
  once the lines are in place, that is a reliable hold for spreading
  the syllables within them. The machinery for that already existed
  (B234, the distribution over the singing windows), but it only ran
  during generation, so manual work got nothing out of it. There is now
  a button for it in the timing editor that does exactly that, with the
  line boundaries untouched.

What the critical re-read turned up on top of that (B498):

- **"Overwrite" took the newest video in the whole folder.** If next to
  `Titel.mp4`, `_2` and `_3` there is also a `Titel_voc_ori.mp4` (a
  render with a different track, B271), the question is about that last
  one but "overwrite" writes over `_3`. `existing_videos` can now
  filter on one numbered family; "Open video" keeps showing the whole
  folder, because that is what is wanted there.
- **"Restore original" wiped the line markings.** `_reset` rebuilds the
  line dicts and those do not know `restore`, so the blue lines
  disappeared from view and the next save wiped the choice. The marking
  now travels along: it says something about the AUDIO and has nothing
  to do with the timing.
- **A blue block in 1.4 could not be got rid of.** The editor let you
  drag it and delete it, but on Apply it was simply derived from the
  marking again - without a message. The line number is now in the
  label, so deleting it strikes back at the marking itself.
- **Several uncoupled lines in a row ended up in the same place.**
  Exactly the case with Lied R, where the two "Twee uh" lines at the
  end stay uncoupled: they stacked on one 0.4 s bar and could no longer
  be pointed at. They each get their own little spot now.
- **The "adjust syllables" button shifted the line boundaries.** The
  singing windows are clipped to the line, so a line whose first energy
  lies after its start got pulled inwards - exactly what must not
  happen when the user has just placed the line himself. After
  adjusting, every line goes back onto its own window.
- **`_reflow_line` fell over on a line without syllables.** That one
  sits on the save route, so a single such line brought down the saving
  of the whole timing.
- **The pause dots stayed white on a line already sung**, while the
  letters around them were grey.

What of the list is NOT in it, and why:

- A measurement at B497. The user asked "just see whether a test can be
  made for that". It can be made, but it is not meaningful without a
  reference: you measure the effect of adjusting against manual timing,
  and then you are measuring against exactly the manual work you wanted
  to improve. What can be done is measuring the effect on the projects
  that have both `timing.json` and `timing_auto.json` - ask him first what to compare.
- At B492 two amplifiers are left that need a measurement:
  `spread_over_active` and `windows_between` deliberately refuse to put
  a line across a pause (for unreliable lines), and the phrase clamp in
  `_dur_for` reckons with one phrase per line while a line with a real
  pause lasts about two. Changing either without measuring is guessing;
  the yardstick (1.5.5/1.5.10) can say what it does.

Included in v1.0.8:

- **B563 - the panel kept ten buttons for work that was finished.**
  Under 1.5 stood ten numbered actions. Four of them ask something
  about the PROGRAM: what does leaving a check out cost (1.5.9), what
  is each model worth (1.5.10), how wrong are repeated lines against
  unique ones (1.5.6), and the heavy bin (1.5.11). Those questions
  have been answered and the answers are in production. 1.5.10 costs a
  hundred and forty-four seconds and 1.5.11 costs hours, and both
  confirm what is already decided.

  Honest about the evidence: it is not true that they never moved a
  switch. The register was last changed BY one of them - B536 flipped
  two states at v0.150.0 on the strength of 1.5.9 - and an earlier
  version of this entry claimed nothing had moved since v0.148.0,
  which the review took apart against the code's own comments. What is
  true is that nothing has moved since, and that the owner's judgement
  is the ground here rather than a number: we do not measure for the
  sake of measuring. They are switched off, not deleted, so the day
  there is a reason again it is one word away.

  The other five say something about the SONGS - what is measurable,
  the three cheap project reports, what was heard but is not in the
  lyrics, the yardstick against his own timing, and the word and
  syllable checks. Those are worth a look at every new song, they read
  only files that are lying there anyway, and together they take under
  a minute over twenty-two projects. They were five ticks that were
  always ticked together; they are one action now, 1.5.2, which takes
  the place of the old 1.5.2. Its duration rows in the history from
  before this version are therefore the old status scan, a tenth of a
  second where this one takes a minute - that feeds nothing but an
  estimate, and it corrects itself after one run.

  A part that stumbles costs only its own table. Before the merge each
  of the five was an action of its own and the runner caught per
  action, so a fall cost one report of five; merged into one button an
  uncaught error would have thrown away the four that DID work,
  including the expensive yardstick. And the progress goes over the
  ACTION bar through `Steps`, not to work slot 0 - reporting to slot 0
  is what 1.5.11 did before B409, and the first project name of a part
  overwrites it a moment later, so the top row never moves.

  The measurement history is untouched by the merge. Every part keeps
  recording under its OWN code - the yardstick stays 1.5.5 there, the
  syllable checks stay 1.5.7 - so the comparison with earlier versions
  runs on. Only the panel shows one line instead of five. And because
  the five explanations that stood beside those ticks now have nowhere
  to go, each part prints its own above its table: five tables without
  a word about what they mean is a report nobody reads twice.

  The nine are switched off, not deleted, the way a heavy trial is
  since B454 and for the same reason. The code stays, the number stays,
  and one word brings any of them back.

- **Filling the cache is a decision, so it is a button.** 1.5.1 looked
  like an ordinary light action and joined "tick all". It is the only
  one of them that starts Demucs AND Whisper: on twenty-two projects
  with a cleared cache that is hours of work, one click away from a run
  that takes a minute. 1.5.11 and 1.5.12 were kept out of that button
  long ago, for exactly this reason; 1.5.1 had been forgotten. It is
  `on_request` now. With one tickable action left the "tick all" button
  says what the tick beside it already says, so it steps aside until
  there is something to gather again.

- **And the panel's own promise did not hold.** The text at the top
  said the actions write nothing into the projects, "with exactly two
  exceptions". Measured: three of the five reports save a
  `word_coupling` step into the `project.json` of every project they
  touch - the project reports and the syllable checks through
  `pipeline.build_coupling`, and "heard but not in the lyrics" through
  `word_coupling_view`, which relocates the pins on its way. On one
  project that is 214 bytes before and 487 after. That step is the
  user's hand-made pin work, and the relocation path inside it can
  drop pins. It has always done that; only the promise was wrong. It
  now says what happens, and the real repair - letting a report ask for
  a coupling without saving one - is written down as the next thing
  rather than smuggled into a release about switching buttons off.

Included in v1.0.7:

- **B559 - the last fifty-two texts that did not follow the language
  choice.** Every `raise SomeError("...")` in `modules/` carried its
  message literally. Not an aesthetic matter: several of them are what
  the user reads in the log window when something goes wrong - no
  ffmpeg, a broken configuration file, a transcription that failed -
  and they stayed Dutch whatever language he chose, while every log
  line had been going through `t(...)` since B356.

  The guard of B356 covers `logger.x(...)` and nothing else, which is
  how a whole second class slipped past it. B550 found them, counted
  them, and could do no more than hold the number at fifty-two with a
  ratchet, because moving them is fifty-two texts in two languages and
  every one of them something he reads. That is done now, and the
  ratchet has become the rule: a `raise` with a literal text turns the
  suite red, exactly as a `logger` call does.

  Fifty of the fifty-two render byte for byte what they rendered
  before - whitespace, `!r` quoting, format specifications and all,
  checked one by one against the v1.0.6 files. Deliberately: he reads
  these sentences, three tests match on their wording, and a rewrite
  dressed up as a move is how a conversion quietly changes behaviour.
  The two that did move are the `KeyError` texts in
  `modules/dependencies.py`, which were English where everything
  around them was Dutch; those now follow the language like the rest.
  The English side is new throughout and is a translation, not a
  paraphrase.

  Two things fell out of it. `err_ffmpeg_missing` already existed with
  another text, and the new key went in under the same name - Python
  keeps the last one in a dict literal, so one of the two messages was
  gone and nothing said a word. That one was made and unmade within
  this release; `log_startup_size` had been standing twice in the
  shipped tree for a long time, for exactly the same reason.
  `test_no_translation_key_is_written_twice` refuses both from now on.
  It is the kind of mistake that only a machine notices: two identical
  keys are three hundred lines apart and both look right.

  The rule itself has one more hole than the first version of it saw.
  A concatenation - `raise ValueError("Breedte moet " + str(n) + "
  zijn")` - is a literal too, and walked straight through a check that
  only looked at plain strings and f-strings. It counts now. The scope
  is `modules/` on purpose: `tools/` prints to a terminal for whoever
  runs it by hand, and there is no language setting to follow there.

- **B560 - the Dutch identifiers no stem caught, and why there was
  always one.** The deny-list of the language guard can never be a
  dictionary; that is written down and it is true. But it also had a
  bug: `DUTCH_STEMS` cut the pattern on its LAST bracket, which is the
  one of the trailing `(_|$)`, so the final stem came out as `zoek)(_`
  plus a stray `$` - whichever word stood last in the list was dead.
  Two people had noticed the symptom and worked around it by keeping a
  known-dead word in last place, rather than looking at the cut. It
  reads the first bracket now, which is the group of stems.

  Then the renames themselves: `cel`, `uit` and `op_een_cel` in
  `modules/timing_editor.py`; eleven locals in `modules/gui.py`;
  eleven in `tools/rename_identifiers.py`, which was almost entirely
  Dutch inside. And one public name, `KlemtoonEditorDialog` in
  `modules/stress_editor.py` - the module had been renamed long ago
  and the class inside it had not. Ten stems were added to the
  deny-list and a dozen rejected because they also live inside an
  English word: `cel` in "cell", `uit` in "fruit", `pad` in "padded",
  `lang` in "language". Eleven were added in the end, and none of them
  matches a single identifier anywhere in the tree - checked, because
  a guard with false alarms is a guard that gets switched off.

- **B561 - the report words go through the translation layer too.**
  The per-project text report in `modules/test_panel.py` and the table
  of `modules/timing_eval.py` wrote their Dutch straight into the
  output. Same class as the fifty-two, same answer.

- **B562 - `format_report` raised a `KeyError` on every call.** It
  asked for `gem`, and `_stats` has written `avg` since the rename of
  B299. So the only thing that function could produce was a traceback
  - and its one caller, `tools/timing_eval.py`, was broken in the same
  round (B550 found that one: it called `vergelijk_paden`, renamed at
  B379). Two halves of one tool, both dead for a hundred versions,
  neither noticed, because nothing ever ran it. Both halves work now
  and there is a test that actually runs the thing, which is the whole
  lesson: a tool without a test is a tool that has stopped working and
  has not told anyone.

  The first version of that test did not run it either. It fed rows
  without syllables, and the measures are taken from the syllables -
  so `per_block` came back empty, the loop that reads `avg` never
  executed, and the test passed against the broken code. The review
  proved it by putting `gem` back and watching the suite stay green.
  It now asserts on the per-block rows themselves. And with the table
  finally printing, a second thing showed up that had been wrong all
  along: the header put its separators one column to the left of the
  rows. The test checks the columns line up.

Included in v1.0.6:

- **B555 - the last two Dutch names, and the only ones he also sees in
  Explorer.** `input/<song>/songtekst.txt` and `karaoketekst.txt` are
  `lyrics.txt` and `karaoke_text.txt` now. Everywhere else the program
  had called them that for a long time already - `input:lyrics`,
  `source_lyrics`, the `lyrics` and `karaoke_text` keys in
  `input_names` - so what was left was one file name that had to be
  translated in the head on every read.

  The first question was whether it would cost him anything, because
  twenty-two projects carry hand-made word coupling and hand-made
  timing and those are worth more than the rename. It does not.
  `sync_input_changes` compares the SHA1 of a source and nothing else;
  the `path` beside it is written in two places and read back in
  exactly one, and that one is the karaoke AUDIO, for its suffix. A
  rename with unchanged content is therefore invisible to the whole
  derivation chain, which the review proved on a project made on disk:
  pins, `timing.json` and `timing_auto.json` all still there
  afterwards. The stored path is rewritten all the same, because a path
  naming a file that no longer exists is a lie waiting for the next
  reader.

  But the same review proved the other half, and that one was a hole
  big enough to sink the release. Renaming NOTHING is what costs him.
  From `sync_input_changes` a project that still holds `songtekst.txt`
  looks like one whose lyrics have been DELETED, and its answer to a
  deleted source is to throw away everything derived from it. Measured
  on disk: pins gone, `timing.json` gone, `timing_auto.json` gone, and
  the rescue of B407/B429 cannot step in because it needs the karaoke
  text and that is missing under its new name too. One click on any
  step button, and no backup exists unless the migration has already
  run. So `unmigrated_texts` sits at the head of `sync_input_changes`,
  which every step passes through: an unmigrated project refuses,
  names the file it found and says what to run. The hard cut is only
  defensible with that gate in front of it.

  No fallback on the old name. That was a deliberate choice against the
  softer one: a program that reads both names has two truths for one
  file, and that is exactly how a rename stays half done for years -
  see the `input_names` keys, which were still being repaired at B324,
  four versions after the rename that caused them. So the app opens the
  new name only, and a project has to be migrated before it opens.

  `tools/migrate_texts.py` does that, in the shape of `migrate_b299.py`:
  a dry run by default that only says what it would do, a
  `.pre_b555.bak` beside every file before anything is written and
  nothing ever deleted, idempotent so running it twice is harmless, and
  afterwards a check per project that the new file holds byte for byte
  what the old one held and that no recorded path still names the old
  one. Where BOTH names are present it does nothing at all and says so:
  that is the only case in which he can lose something, and guessing
  which of the two he meant is not this script's job. Fourteen tests
  cover each of those cases on a real folder.

  Three of those tests exist because the review broke the first
  version. It rewrote any path ENDING in the old name, so somebody's
  `my_songtekst.txt` became `my_lyrics.txt` silently; it raised on a
  `project.json` whose `steps` are not a mapping - which `ProjectStore`
  tolerates - and it raised AFTER the renaming, so the verification
  never ran; and its verification searched the whole `project.json` for
  the old words, which also hits `input_names`, where the name of the
  file the USER picked is kept. A text he called "Kedeng songtekst.txt"
  would have been reported as a leftover on a migration that was
  perfectly fine, and a check that cries wolf gets ignored on the one
  occasion it is right.

  A fourth came out of running the dry run over his real installation
  rather than over a test folder, which is why that was worth doing.
  It reported 44 files to rename and 0 paths to correct, where the
  answer is 44 and 44: the paths in `project.json` are WINDOWS paths,
  `PurePath` follows the platform it runs on, and on anything else
  `PurePath("C:\\x\\songtekst.txt").name` is the whole string. It
  would have worked on his machine and silently done half the job
  anywhere else - including in this sandbox, where every test of it
  runs.

  And one safety measure was removed rather than fixed: it claimed to
  refuse while the app was running, on a `.write_test` that nothing in
  the program ever leaves behind. A promise in a docstring with nothing
  underneath it is worse than no promise. The real protection is the
  gate above, which is in the app itself.

  The reason this was a job of thirty-three files instead of two lines
  is that the name was typed out everywhere: the GUI, and
  `tools/timing_regression.py`, and the descriptions behind
  `dependencies.md`, and every test that makes an input folder.
  Eighteen files read the two constants now, seventy-three times over.
  The next rename is two lines.

- **B556 - the language guard did not read import aliases.** `from .
  import song_text as songtekst_module` stood three times in
  `modules/pipeline.py` - in the module this whole rename is about -
  and the guard called that file clean, because the walk looked at
  function, class, argument and variable names and never at
  `ast.alias`. The three are gone (`song_text` was already imported at
  the top of the file, so they were shadows of a name that was there),
  and the walk reads aliases now.

- **B557 - the two labels of the input panel were code, not
  translation.** "Songtekst" and "Karaoketekst" stood in `gui.py` as
  literal dictionary keys, and were therefore Dutch whatever language
  was chosen. They come from `t(...)` now, like everything else in that
  panel.

- **B558 - `woorden.json` and `segmenten.json`.** The same kind as
  B555 and much cheaper, because nothing reads them: not the app, not a
  tool, not a test. They are `words.json` and `segments.json` now.
  `words.csv` beside them had been English for a long time already,
  which is how this pair stayed invisible - the folder read as half
  converted and nobody looked twice.

  Two things to know rather than to fix. The old pair is not cleaned
  up: `write_outputs` makes the folder if it is not there and never
  clears it, so a stale `woorden.json` sits beside the new one until
  the folder goes, and quietly drifts. And `tools/timing_regression.py`
  and `projects_without_cache` look for
  `output/<song>/original/segments.json`, which no project has until it
  has been detected again - so until then the yardstick silently skips
  all twenty-two. That is a measurement, not data, and he re-detects
  when he measures anyway.

What is NOT in it:

- The fifty-two literal `raise` texts of B550 are still literal. This
  release did not touch them; the ratchet still holds the number at
  fifty-two.
- The Dutch report words in `modules/test_panel.py` and
  `modules/timing_eval.py` (`songtekst`, `blok`, the keys `gem` and
  `med`) stay. Those end up in reports the user reads, so they are
  interface language rather than code - but they are written as literal
  strings instead of through `t(...)`, so they belong with those
  fifty-two rather than here.

Included in v1.0.5:

- **B549 - emptying the cache quietly cost the hand-made coupling.**
  "Nu legen" removes the transcription from the cache. The cache hit in
  `detect_track` needs exactly that file, so after emptying there is
  never a hit, and every detection after it ran
  `invalidate_after_fresh_transcript`: the word coupling of step 2,
  `timing.json` and `timing_auto.json` went. Even when the
  transcription that came back was word for word the one they were
  made on, which after an emptied cache it usually is - the audio, the
  model, the language and the prompt are all unchanged, only the file
  is gone. Hours of hand work for a button that promises to free up
  disk space.

  Missing the cache is not the same as a different answer. A
  fingerprint of the transcript - a sha1 over the serialised segments,
  so the words AND their times count - now stands in the step beside
  the cache key. The step lives in `project.json` and survives an
  emptied cache, so after a new transcription the two can be compared:
  the same text means the coupling still fits and stays. B265 is
  untouched for the case it was written for - another text still
  clears it, because the pins point at positions in the transcript and
  on another text they point at nothing.

  Found during the review of B545 and demonstrated there; it is a
  different defect from the one that release was about, which is why
  it waited for its own number.

- **B550 - the rule said English, the guard said nothing, and the
  README said it was done.** v1.0.1 claimed the whole tree was English
  and all three TODO lists were empty. Both true, and the conclusion
  wrong: the lists were empty because the guard could not see what was
  left.

  Four holes, all four of them in the guard itself. The prose check
  gives no verdict below twenty-five countable words, and fifteen test
  files sat under that floor with Dutch function words and NO English
  ones at all - `tests/test_v077.py` had twenty-two against nought.
  The floor was meant to stop a one-line comment turning the suite
  red; it was forgiving whole files. Below the floor a second question
  is asked now: at least three Dutch words and at least twice as many
  as English. That is not a one-line comment any more, that is a file.

  Then the verdict was per FILE, which is a majority vote, and a
  majority hides a minority. `modules/test_history.py` has forty Dutch
  function words against two hundred and thirty-six English ones and
  passed - while three of its docstrings are Dutch from the first word
  to the last. Twenty-one such pieces stood in ten files. Every
  comment run and every docstring is now weighed on its own, and there
  is nothing left for them to hide behind.

  The identifier check anchored its Dutch stems at the START of a
  name. Every test name starts with `test_`, so the check was nearly
  powerless over the file type with the most Dutch in it -
  `test_woorduitlijning_fallback` walked straight past. Every piece
  between the underscores is weighed now, and a stem counts when the
  piece begins OR ends with it. Both ends, because Dutch glues its
  compounds together and puts the head LAST: `woorduitlijning` is
  `woord` plus `uitlijning`, and `kernwoorden` ends on the very stem
  that gives it away. Looking only at the beginning, as the first
  version of this did, misses that whole half.

  And the guard read only `.py` and `.md`. `requirements.txt` - the
  first file anyone who installs this project reads - was Dutch from
  top to bottom, and so were the comments in `install.bat` and
  `KaraokeToolGUI.bat` and the two notes in `assets/fonts/`. Those are
  read now, with the same division a module gets: in a `.bat` the
  `rem` lines are this project talking to whoever reads the script and
  are English, while the `echo` lines are the program talking to the
  user and stay Dutch, for the same reason the manual keeps the Dutch
  button names.

  Then the work the holes exposed. Twenty-one files by the widened
  file rule - fifteen test files, `tools/timing_eval.py`,
  `requirements.txt`, both `.bat` files and the two notes in
  `assets/fonts/` - then twenty-one single pieces in ten more files by
  the per-block rule, in six passes that ran side by side. Comments
  and docstrings carried over with their reasoning and their build
  numbers intact, and twenty-six Dutch identifiers that the guard can
  see renamed with their references, plus a row of locals beside them
  that it cannot. Content stayed content: the lyrics the tests are
  built on, the markup the user types, the `nl` translations, the
  Dutch the interface shows him.

  Two files were converted that the guard still cannot see:
  `tests/test_audio.py` and `tests/test_ffmpeg.py` each had exactly
  two Dutch function words and no English ones - one under the new
  threshold. Leaving them would have meant a threshold tuned to keep
  the last two files green, which is how a guard becomes decoration.
  Lowering it to two is not the answer either: a single two-word Dutch
  comment would then turn the suite red. They were done by hand and
  this paragraph is the record that the hole is real.

  One real bug fell out of it. `tools/timing_eval.py` called
  `timing_eval.compare_paths` under its old Dutch name
  `vergelijk_paden`, which was renamed at B379 - the command-line tool
  had been dead since then and nobody had run it.

  What is NOT done, named rather than glossed over. The deny-list is
  still a deny-list and not a dictionary, and it always will be: a
  word list of Dutch would also flag "over", "index" and "single", and
  a guard with false alarms is a guard that gets switched off. Seventy
  stems now, and Dutch locals remain that none of them catch -
  `modules/timing_editor.py` (`uit`, `cel`, `raak`, `ingang`),
  `modules/gui.py`, `tools/rename_identifiers.py` (`bron`, `punten`),
  `modules/timing_eval.py` (`per_blok_on`, `maten`, and the report
  keys `gem` and `med`).

  And the larger one: fifty-two `raise SomeError("...")` texts in
  `modules/` carry their message literally, nearly all of them Dutch,
  and several reach the user through the log window without following
  his language choice. The guard against literal texts (B356) covers
  `logger.x(...)` and stops there. Moving all fifty-two into the
  translation layer is a job of its own - fifty-two texts, two
  languages, each one something he reads - so it gets its own number.
  What is here is a ratchet:
  `test_the_literal_exception_texts_do_not_grow` counts them and
  refuses both a higher number and a stale lower one, so the hole
  cannot quietly widen while it waits.

- **B554 - three error messages named settings that do not exist.**
  Found while reading `modules/config.py` for the language work.
  Reject a configuration file and it would say `'marge_ms'` may not be
  negative, or `'analyse.min_confidence'`, or that one of
  `'tracks.origineel'` has to be on. Those keys were renamed long ago:
  the fields are `margin_ms`, `analysis.min_confidence` and
  `tracks.original`. So the user was sent to a setting that
  `_dataclass_from_mapping` would have reported as unknown if he had
  gone and made it. The names in the messages match the fields again.

- **B551 - two tests that asserted nothing on the machine they had to
  work on.** `test_separation_unavailable_raises` had its whole body
  under `if not separation.is_available():`, with "In this environment
  Demucs is not installed" beside it; `test_woorduitlijning_fallback`
  hid the second of its two assertions the same way. On a machine with
  Demucs and WhisperX - which is the machine this is built for, and
  which `install.bat` makes certain of - both passed while asking
  nothing. The absence is arranged with a monkeypatch now, so the
  question is about the code instead of about the machine. The second
  one also had a Dutch name and is `test_word_alignment_falls_back`.

- **B552 - the suite ran on a machine that did not meet
  requirements.txt.** This is the test that would have prevented the
  whole of B545. Three tests were green here and red there, and the
  reason underneath was not those three tests: `faster-whisper` and
  `langdetect` are declared as required and were not installed in the
  reference environment. A suite that runs with half the requirements
  missing is not testing the program, it is testing a program that
  happens to be there. `tests/test_requirements.py` imports every line
  of the file, and the two that were missing have been installed - the
  suite reports 1763 passed and, for the first time, nothing skipped.

  Installing them found something immediately.
  `test_language_for_uses_the_lyrics_file` had been skipping for years
  and now ran - and it ran red in the PUBLIC copy while passing here.
  Its karaoke sentence opened with the name of the user's own
  association, which langdetect read as Dutch at 0.72 against
  Afrikaans at 0.28, and the publication tool replaces that name by a
  neutral one, which tipped it to Afrikaans. Fragile twice over: a
  test whose material is the owner's private data only works on one
  machine, and a 0.72 margin is decided by langdetect's own random
  sampling as much as by the text. The sentence is longer and carries
  no names now, at 0.99999.

  The optional models are deliberately outside it. `requirements.txt`
  puts Demucs and WhisperX under a heading of their own with a `pip
  install` line beside them, and the code asks `is_available` before
  it uses them. A third test keeps that difference visible, because
  the day one of them moves into the list proper, a machine without it
  is broken rather than merely limited. Worth knowing: `install.bat`
  installs both of them always (B195), so on the machine this is built
  for they are there - which is exactly why the two tests of B551
  asserted nothing.

  "Nothing skipped" is about this tree. The published copy still
  reports sixteen skips, and rightly: fifteen of them are
  `tests/test_export_tool.py`, which tests a tool that deliberately
  does not travel, and one is the font test on a checkout where
  `install.bat` has not run yet.

- **B553 - the Demucs simulation is a fixture instead of a throwaway.**
  It was built twice now to prove something (B545, and again to check
  the fix), and thrown away twice. It stubs the only two places
  `modules/separation.py` touches the outside world - whether the
  package is there and the subprocess that would run it - and lets
  everything else run for real. As `demucs_installed` in
  `tests/conftest.py`, asked for by name and never automatic, it gives
  `separate_cached` its first test across two calls: the marker, the
  staleness check of B311, the copying into the fixed place, and B548
  end to end with two different models.

Included in v1.0.4:

- **B547 - the download message stayed away in exactly the two cases
  it exists for.** `model_cached` is there so that "the model is being
  downloaded" appears when that is really about to happen, and not
  otherwise. It walked the hub folder and accepted any directory whose
  name CONTAINED the model name.

  So with only `models--Systran--faster-whisper-large-v3-turbo` in the
  cache, the question about `large-v3` answered yes: that name
  contains this one. Three gigabytes came down with nothing on screen.

  The rule now is that the pieces of the model appear in the folder in
  that order and the folder ENDS on the last of them. Ending on the
  last piece is what keeps `-turbo` and `tiny.en` out. Order without
  adjacency is what the second of the three models in the drop-down
  needs: `distil-large-v3` lives in
  `models--Systran--faster-distil-whisper-large-v3`, with `whisper`
  standing in the middle of the name, so a rule that wants the model
  in one piece never finds it and the message would show on every
  single run. That one was wrong before this release too, and the
  review caught it while checking the fix for the other two.

  It stays an estimate and says so. The folder for a model cannot be
  derived from the name faster-whisper accepts, only guessed at:
  `large`, which faster-whisper reads as an alias for `large-v3`, is
  not found this way. The app does not offer it, and the cost of a
  miss is a message too many, never a wrong transcription.

  And a download that was broken off is not a model. huggingface_hub
  puts the pieces down as `blobs/<sha>.incomplete`, and a folder with
  one of those in it counted as a finished model. Close the app during
  the first download of `large-v3`, start it again, press "1 Detecteer
  woorden": no message, and a window that sits there for ten minutes.
  That is precisely the symptom this function is meant to prevent. A
  folder holding an unfinished piece is skipped now, with a line in
  the log saying which one.

  Both were found in the review of B545 and put aside then, because
  they are a different defect from the one that release was about.

- **B548 - the Demucs stems were kept on the checksum of the audio and
  nothing else.** `separate_cached` takes a `model` argument, passes
  it to `separate`, and never wrote it down: the marker `source.sha1`
  held the checksum of the source. Two things follow from that.

  `separate_cached(..., model="htdemucs_ft")` gets the stems of
  `htdemucs` back and says nothing, because as far as the marker is
  concerned they belong to this audio and the question is answered.
  Latent as long as every call site uses the default, which is true
  today - and the argument exists precisely so that it will not stay
  true.

  Worse, and not latent: `install.bat` invites `pip install -U
  demucs`. After an upgrade the stems of the old model still match
  their marker, so they are reused for ever and Whisper keeps
  transcribing them. That is the B311 failure through another door -
  "a stale stem silently gives a stale transcription of a song that is
  no longer there" - only this time the audio is right and the
  separator is not.

  The marker holds three lines now: the checksum, the model, and the
  installed Demucs version.

  A marker from before this is one line, and the first version of this
  change let it pass on its checksum - those stems were probably made
  by the Demucs that is installed now, and throwing away a separation
  that is probably right costs minutes per song. The review took that
  apart, and rightly. A marker from before the check is PRECISELY the
  one that may predate an upgrade: separate on 4.0.0, `pip install -U
  demucs`, update to this version, and the first run would reuse the
  4.0.0 stems - the exact failure this build number is about - and
  then stamp them as belonging to 4.1.0, after which the mistake can
  never be found again. It would not have fixed the case, it would
  have cemented it.

  So a marker of one line is not accepted, and the stems are made
  once more. That costs one separation per project, once, the first
  time it is touched after this update. A write torn after the first
  line lands in the same branch, which is the second reason for it:
  half a marker says nothing, and this way it says nothing loudly.
  Stems with NO marker at all are still accepted - that is the rule
  from B311 about separations from before any of this, and it is left
  where it was.

  The test that goes with the version had to be rewritten as well. It
  passed with the version left out of the stamp altogether, because
  Demucs is not installed on the machine the suite runs on and it was
  asking whether "" equals "". It monkeypatches the version now.

Included in v1.0.3:

- **B546 - the publication check stopped the first push of v1.0.2 on a
  name that is nowhere.** `push_to_github.bat` ran, the export wrote
  its 167 files, and then: `left standing:
  .git\objects\pack\pack-f3f05e11....pack:18252: TVX`, one leftover,
  nothing pushed.

  There is no TVX there. `leftovers` walks the whole target folder, and
  after `_clear` the only thing still standing in a clone is `.git`. A
  packfile has no extension the binary list knows, so it was read as
  text with `errors="replace"` and searched case-insensitively. Three
  megabytes of zlib output contain three given letters somewhere by
  sheer chance, and they did: `TVX`, at character 2337971, in the
  middle of a compressed stream. The literal `TVX` does not occur in
  that pack at all - `data.find(b"TVX")` is -1 - and `git grep -i` over
  all twelve revisions finds the name in no file. The repository is
  clean; the check was reading noise.

  `.git` is git's own storage and this tool never writes a byte of it,
  so the walk skips it. That is not a weakening: the folder is not part
  of what gets committed, and the thing it was accidentally rummaging
  through is unreadable this way by construction. It would also have
  got worse on its own - every push adds objects, so the chance of the
  next false alarm grows with the history.

- **But the question underneath it is real, so it is asked properly.**
  The working copy is what the next commit will hold; the history is
  what the world can already read. A name that got out in an earlier
  push stays in the history after the working copy has been cleaned,
  and no export takes it back out - that needs a rewritten history and
  a force push, which is exactly the kind of thing you want to be told
  about rather than to discover. `history_leftovers` runs `git grep`
  with every hunted name through every revision and reports what it
  finds. It reports and passes, rather than blocking, when git is
  missing or the target is no repository: it sits on top of
  `leftovers`, it is not a second gate in front of it. On the real
  repository it says clean.

  The first version of it searched plain substrings, case blind, and
  promptly reported five files of the project itself: "Lied R" inside
  "springen", and the copyright line of `LICENSE`, which the walk
  exempts on purpose. A check that cries wolf gets switched off by
  whoever has to read it, so it runs the same patterns the walk runs -
  through `git grep -P`, in two passes, because seven of the
  eighty-four names are case sensitive and git applies `-i` to the
  whole call.

  Three places are read, because a name can be public in three ways.
  The CONTENT of the files in every revision. The PATHS of every
  object, since `git grep` matches content and a file that was deleted
  still stands in the history under the name it had. And the COMMIT
  MESSAGES, which no grep over the trees ever sees and which are as
  public as any file. What is not covered is a name wrapped over two
  lines inside old content: git grep works line by line. The walk over
  the working copy does read across line breaks, so a fresh leak is
  caught there; only one that was pushed wrapped in an earlier version
  slips through, and that is written here rather than glossed over.

  Three things the review found, and that are fixed: a hit from the
  first pass was thrown away when a later call failed ("not checked"
  returned zero, and the export then called the whole thing clean - a
  confirmed leak turned into a clean bill of health); the closing
  "clean" line was printed even when the history had never been looked
  at, so it now says separately what was read and what was not; and
  every name goes on the command line as its own `-e`, which is six
  kilobytes before the first revision, so past roughly six hundred and
  fifty revisions Windows refuses the command and the check would have
  passed quietly - the revisions go in batches of two hundred now.

  Eleven tests in `tests/test_export_tool.py`: a packfile carrying the
  name in `.git` is ignored, the same name in a file beside it is
  still found, a name in `.gitignore` is still found (only `.git` is
  skipped, not everything that starts with a dot), a real repository
  whose history holds the name is caught while its working copy is
  clean, a deleted file is caught by its name, a commit message is
  caught, `LICENSE` stays exempt in the history too, a clean
  repository stays clean, a folder without `.git` has no history, a
  repository without commits has none either, and a history full of
  "Springen" is not a hit.

  The first version called `subprocess.run` for git and
  `test_no_bare_subprocess_calls` turned red on it, which is the guard
  doing its job: on Windows that flashes a cmd window and the process
  does not listen to Stop (B356). It goes through `proc.run` like
  everything else. The assertion message of that guard was still
  Dutch and is now English.

Included in v1.0.2:

- **B545 - three tests were green here and red on the machine they had
  to be green on.** After the delivery of v1.0.1 the full suite on the
  user's own PC gave 3 failed, 1730 passed, while the same tree here
  ran 1732 passed, 1 skipped. Three tests that pass or fail depending
  on what happens to be installed are worth less than no tests at all:
  they say nothing about the code and everything about the machine.

  First the question of whether the translation round had broken them,
  because that is the cheapest explanation and the one that has to be
  ruled out before any other. It had not. `modules/whisper.py` and
  `tests/test_whisper.py` were byte for byte what they were in v1.0.0,
  `modules/pipeline.py` differed by exactly one line - a docstring that
  points at `docs/video_standard.md` under its new name - and the two
  failing test functions were, once their docstrings were stripped,
  identical trees to their v1.0.0 versions. All three were already
  broken; nobody had run them on a machine with everything installed.

- **Two of them ask about the transcription cache and leave Demucs
  on.** `test_detect_words_uses_cache` and
  `test_detect_track_cache_hit_keeps_the_pins` write the step
  `whisper_<track>` with the checksum of the wav file they have just
  put in `input`, and then expect a cache hit. But `detect_track`
  separates first when the option is on and Demucs is available, and
  from that moment transcribes the vocal stem: the key holds the
  checksum of the stem, the test wrote the one of the mix, and there is
  no hit. Here Demucs is not installed, so `_demucs_enabled` is false,
  the whole branch is skipped, `wav_path` stays the mix and the key
  matches - the tests were passing for a reason that has nothing to do
  with what they are about.

  Reproduced without installing anything: a pytest plugin that stubs
  the two places the outside world is actually touched - whether the
  package is there (`models.is_available("demucs")`) and the
  subprocess that would run it (`proc.run`) - and lets everything in
  `modules/separation.py` run for real: the command building, the work
  folder, finding the stems, copying them into the fixed place, the
  marker and its staleness check. On the v1.0.1 tree, with `HOME`
  pointing at a cache that holds `large-v3`, that plugin gives exactly
  3 failed, 1729 passed, 1 skipped - the user's own three, with the
  same `TypeError: 'NoneType' object is not iterable` out of
  `whisper.segments_to_dicts`, where the monkeypatched `transcribe`
  returns None because it should never have been called. So it is
  these three and no others.

  Stubbing higher up is what a first attempt did - replacing
  `separate_cached` itself - and that also breaks
  `test_demucs_separate_cached_reuses`, which is about that very
  function. A simulation has to stub at the boundary, or it starts
  answering about itself.

  Both now switch Demucs off, with the reason written above them, and
  because that leaves the separation branch with no test at all,
  `test_detect_words_uses_cache_along_the_demucs_path` asks the same
  question with the separation stubbed on: a stem that is deliberately
  not its source, `detect_track` twice, and then the checks that the
  second run came from the cache, that Whisper saw the STEM and not the
  mix, and that the key holds the checksum of the stem. A third run
  after the stem has been overwritten with other audio checks the other
  half of a key - that a changed checksum really forces a new
  transcription. Without that run the whole `wav_sha1` condition could
  be struck out of `detect_track` and the entire suite stayed green,
  which the review demonstrated. And because both reworked tests now
  lean on `demucs=False`, `test_demucs_off_really_skips_the_separation`
  pins that the switch is what turns the branch off and not the absence
  of Demucs: with separation available and the option off, the mix has
  to be the thing transcribed. That is the branch the user's machine
  walks every day, and nothing here could reach any of it before.

  The app itself is right. The stem is stable for the same source and
  model, `separate_cached` reuses it through its marker, so the key is
  the same on the next run, and switching the option off changes the
  key and therefore correctly forces a new transcription. Nothing
  changed in `modules/pipeline.py`.

- **The third one found something real.** `model_cached` exists to show
  "the model is being downloaded" only when that is actually going to
  happen. It built the hub folder out of `HF_HOME`, and if that folder
  did not exist it fell back to `~/.cache/huggingface/hub` - which is
  exactly the situation the function is there for: a fresh `HF_HOME`
  has no `hub` yet precisely because nothing has been downloaded into
  it. So it looked in the default cache instead, found the model there,
  and reported the download as already done. On the user's machine that
  is what turned `test_model_cached` red; in normal use it means that
  whoever points `HF_HOME` somewhere else gets no message before a
  multi-gigabyte download.

  Which folder it is now comes from `hub_cache_dir`, which resolves the
  five steps `huggingface_hub.constants` resolves - `HF_HUB_CACHE`, the
  legacy `HUGGINGFACE_HUB_CACHE`, `HF_HOME/hub`,
  `XDG_CACHE_HOME/huggingface/hub`, `~/.cache/huggingface/hub` - with a
  `~` and a variable expanded on the way, as it expands them, and a
  variable that is set but EMPTY counted as set, as `os.getenv` counts
  it. Both of those were wrong in the first version of this function
  and both were found by the review: the legacy name was the one branch
  that did not expand, and `set HF_HUB_CACHE=%MODELDIR%` with an
  undefined `MODELDIR` - an ordinary Windows accident - would have sent
  the answer to the home cache while the download went to the working
  directory. That is the original bug again, one door along.

  Read out rather than imported, so the answer is there on a machine
  without the library; the price of that copy is that it can drift, and
  `test_hub_cache_dir_agrees_with_huggingface_hub` runs fourteen
  environments through both - a tilde and a variable in each of the
  four names, the empty value in each of them, and the combinations
  where one shadows another - and skips only where the library is
  absent. Twenty-four environments were compared by hand as well; all
  twenty-four agree.

  The test that goes with the fix had to be rewritten, because the
  first version of it passed against the old code as well: it set
  `HF_HOME` to an empty folder and asserted False, and the old code
  answered False there too as long as the real cache of the machine
  happened to hold nothing. It now builds the situation that actually
  separates them - a filled default cache and an `HF_HOME` pointing
  elsewhere that is still empty - and fails against the old function on
  any machine.

- **Checked in both directions.** With the fixes the suite is green in
  four environments: plain, under the Demucs plugin that reproduced the
  three failures (1738 passed, 1 skipped), with `HOME` pointing at a
  cache that holds `large-v3`, and with all four Hugging Face cache
  variables set at once. The same four are what made the two machines
  disagree. The regression test for `model_cached` was
  run against the old function on a machine where the old function is
  wrong, and it is red there. The new Demucs test is green against the
  unchanged `modules/pipeline.py`, as it should be: it is coverage of a
  branch that was right all along and had nothing watching it, not a
  test for a fix.

What is NOT in it, and why:

- **`model_cached` still says True on an interrupted download and on a
  neighbouring model.** It walks the hub folder and accepts any
  directory whose name contains the model name, so a folder holding
  nothing but `blobs/*.incomplete` counts as present, and with only
  `...faster-whisper-large-v3-turbo` in the cache the question about
  `large-v3` also answers True. Both give the silent freeze that this
  function exists to prevent. Found during the review of this change;
  it is a different defect from the one B545 is about and gets its own
  number rather than being folded into this narrative.
- **The tests here run on a machine that does not meet
  `requirements.txt`.** `faster-whisper` and `langdetect` are declared
  as required and are not installed in the sandbox, and that - not the
  three tests - is the reason the two machines disagreed at all. A test
  that imports every requirement would catch the whole class at once
  and would be red here today. Whether that test belongs in this suite
  is the user's call, because it also decides what a fresh clone from
  GitHub is allowed to fail on.
- **Two more tests hide assertions behind what is installed.**
  `test_separation_unavailable_raises` in `tests/test_pipeline.py` has
  its whole body under `if not separation.is_available():` and
  therefore asserts nothing at all on a machine with Demucs;
  `test_woorduitlijning_fallback` in `tests/test_models.py` keeps one
  assertion outside the `if` and hides only the second. Same disease as
  B545, other patient - and the second one still carries a Dutch name
  and a Dutch docstring that the guard's deny-list walks past, because
  it anchors `woord` on a word boundary and the name runs on into
  `woorduitlijning`.
- **Emptying the cache throws away hand-made word pins.** The cache hit
  needs `cache_file.exists()`, and the transcript cache lives in the
  cache folder, so "Nu legen" guarantees a miss on the next detection,
  `invalidate_after_fresh_transcript` fires, and the coupling, the
  timing and the automatic timing go - even when the new transcription
  is identical to the one thrown away. Demonstrated during the review.
  Comparing the fresh transcript with the cached one before invalidating
  would fix it. Its own number.
- **The Demucs plugin is not committed.** It was built to verify this
  change and thrown away again. Committed as an opt-in fixture it would
  give the real `separate_cached` - the marker, the staleness check,
  the copying into the fixed place - its first coverage across two
  calls; the new tests stub at the level above it and therefore supply
  the stem stability themselves rather than proving it. Worth doing,
  but it is a piece of test infrastructure and not part of fixing three
  red tests.

- **`separate_cached` records only the source checksum in its marker,
  not the model or the Demucs version.** Upgrading Demucs therefore
  leaves stems that still match their marker and get reused forever -
  the B311 failure mode through another door. Latent while every call
  site uses the default model. Its own number.

Included in v1.0.1:

- **B543 - English is the language of the whole tree now, and something
  checks it.** The rule had been written down since B299/B300, but its
  scope was two folders: `modules/` and `tools/`. Everything outside
  them drifted. Of the 1647 test names roughly half were Dutch, 67 of
  the 96 test files carried Dutch comments and docstrings, ten file
  names were Dutch, and every document was. That is not a rule, that is
  a habit with a guard around a quarter of it.

  Widened in one pass. Twelve file names renamed with their references
  pulled along: `docs/afhankelijkheden.md` to `dependencies.md`,
  `doorontwikkeling.md` to `development_log.md`, `handleiding.md` to
  `manual.md`, `karaokevideo_werkwijze.md` to `video_standard.md`,
  `assets/fonts/LICENTIE.txt` to `LICENSE.txt`, `PLAATS_FONTS_HIER.txt`
  to `PUT_FONTS_HERE.txt`, `tools/b299_woordenboek.py` to
  `b299_dictionary.py`, and five test files. Then the test names, the
  docstrings under them, the comments, the Dutch helper and local names,
  the text the tools print and their `--help` lines, and finally the
  documents: the manual, the video standard, the `what=` descriptions
  that generate `dependencies.md`, the README with its roadmap of a
  hundred and sixty versions, and this log itself - four hundred
  kilobytes of reasoning, carried over by hand rather than by a
  dictionary.

- **The guard is three checks now, and each one carries a list that may
  only shrink.** Identifiers, prose and file names. A file on a list has
  to still be Dutch: the moment it reads as clean the suite turns red
  until it is struck, so a list can never quietly become a permanent
  exemption. That mechanism is older than this release and it is the
  reason the work could be done in waves without losing track - the
  lists were the work list.

  All three are empty as of this version. The prose check is the weakest
  of the three and says so in its own docstring: it weighs Dutch
  function words against English ones, which is a heuristic and not a
  fact, and it refuses to judge a file with fewer than twenty-five
  countable words rather than fire on a two-line comment.

- **What stays Dutch, because it is content and not code.** The `nl`
  half of `translations.py` together with `languages/nl.json` - that is
  the Dutch interface itself - and the markup the user types in his own
  lyrics, `[pauze]` beside `[pause]`. The guard reads comments and
  docstrings but never string literals, precisely so those can stay.

  And one group is waiting rather than exempt: `songtekst.txt`,
  `karaoketekst.txt` and the keys of the same name in `project.json`.
  Renaming those rewrites every project on disk, so they need a
  migration, not a translation. They are named in the working agreement
  so the debt stays visible.

- **B544 - the safety catch on the export folder refused the only way
  to publish.** `_clear` empties the target before the export is written
  into it, and after the review of B542 it only accepted a folder that
  was empty or carried this tool's own marker. The first real push
  showed what that rules out: the way to publish an update is to clone
  the repository and export over the clone, because only then does git
  see the renamed and deleted files and put them in the commit. A fresh
  clone has neither the marker nor emptiness, so the export stopped and
  nothing was pushed.

  A git working copy is now accepted as a third case, and for the same
  reason the other two are: emptying it costs nothing. Everything in it
  is in the repository as well, and `git status` afterwards shows
  exactly what the export changed. `tests/test_export_tool.py` covers
  all five cases - empty, marked, clone, a stranger's folder, and the
  project itself - and skips itself in a published copy, where the tool
  is not present.

- **Two things moved with the translation and had to follow.** The
  headings of this log are English now, so the publication tool cuts the
  private section on `## Approach (important)` and `## Data model`
  instead of on the Dutch headings - it would silently have cut nothing
  and published the working agreement. And `docs/manual.md` describes a
  Dutch interface: the button names in it are what the user reads on his
  own screen, so "Zangstem-analyse", "Terug uit origineel" and
  "legenda" stayed, with an English gloss beside them. A test checks
  exactly that, and it caught the three that had been translated away.

Included in v1.0.0:

- **B542 - version 1.0 and publication on GitHub.** The build list is
  empty, the whole road from recording to finished video works and the
  yardstick stands at 2.46 s over all projects; that makes this no
  longer a 0.x. The source is public on GitHub under the MIT licence.

  The front page was no longer right, and that is the first impression
  someone gets. The introduction said **"Current version: 0.9"** while
  the roadmap table below it ran to 0.152.0, and described only the
  original goal - muting words in a bought karaoke version - while the
  program by now splits, transcribes, times and renders a video. Three
  more things in it no longer exist: a whole paragraph "Console menu"
  with a menu of eight options, while `KaraokeTool.py` only starts the
  GUI; references to `KaraokeTool.bat`, which is called
  `KaraokeToolGUI.bat`; and references to `modules/taal.py`, which has
  been called `modules/translations.py` since B299. The header line of
  `modules/pipeline.py` named that same `menu.py` as its second caller.
  All set straight; the historical roadmap rows stay as they were,
  because they describe what there was back then.

- **The public copy is a different tree from this installation, and
  `tools/github_export.py` builds it.** Asked and answered: his own
  project names do not go in, but they do stay here. That cannot be
  done with a switch in the code, so there is a tool that builds the
  publishable copy. It leaves out what belongs to the user (`config/`,
  `input/`, `output/`, `cache/`, `logs/`, `venv/`, and the measurement
  work: `testhistorie.json`, `modelmatrix.md`, `modelcombinaties.md`,
  `metingen.md`, `testverslag.md`, `knipwoorden.txt`,
  `docs/verslagen/`), it renames the twenty-two song projects to
  `Lied A` through `Lied U` and the association to "Rood Witte
  Zangers", and it cuts the working agreements between the user and the
  assistant out of the log - those are private, not documentation of
  the program.

  Rename and not throw away, because almost every rule in `timing.py`
  carries the measurement that justifies it ("measured on X: from 7.58
  to 3.90 s"). Take the name away and the rule is a bare claim. Two
  properties of the placeholders carry weight: they keep the
  alphabetical order of the originals, because several tests check the
  order of the project list, and the placeholder for the association is
  chosen so that it breaks into exactly the same syllables as the name
  it replaces, because that name is precisely the test material of the
  syllable splitter.

- **What the critical re-read of this turned up, and that was not
  little.** The first version of the tool reported "clean" while the
  name of the association was still in it twelve times in full. Three
  causes, and all three sat in the check itself: it looked only for the
  literal project names (the association was not in the list), it was
  case-sensitive (the same name in capitals or all in lowercase slipped
  past) and it did not look across line breaks, while half the hits sit
  in wrapped prose. The check is now wider than the work itself -
  case-insensitive, blind to line breaks, and it reads the filenames
  too - because a check with the same blind spots as the work it checks
  is decoration.

  Further: `\b` counts an underscore as a word character, so "Lied A
  " in `Lied A_2.mp4` slipped past the boundary; the
  boundary is now spelled out in full. A name can sit in a Python
  string with `\n` as two characters instead of a line break, and
  exactly such a case in `test_texts_identical` was half replaced: one
  half of the comparison yes, the other not, after which the test
  rightly went red. The replacement also joined two lines together,
  which not only gave ugly long lines but in a test file ate a line
  break where the number of lines is precisely the subject; the
  replacement now keeps the layout of what it replaces. And
  `shutil.rmtree` on a path from the command line did no check at all:
  a typo wiped an arbitrary folder, and a second export threw away the
  `.git` of the previous one. Now `.git` stays, the tool refuses a
  folder that is not its own, and the target can never lie in the project folder.

- **The fonts do not travel along, and that settles a licence
  question.** The `LICENSE` first claimed that the bundled Google Fonts
  are under the SIL Open Font License, but `install.bat` itself
  searches in `@('ofl','apache')` - so part of them is under Apache
  2.0. On top of that OFL 1.1 requires the licence text to travel
  along, and `LICENSE.txt` gives only references. Because `install.bat`
  fetches all twenty families itself anyway, the solution is not to
  ship them: only `DejaVuSans-Bold.ttf` stays as a fallback, freely
  redistributable, and the repo is five megabytes lighter.
  `test_bundel_bevat_fonts` went red on a fresh copy because of that;
  it now skips itself as long as the extra fonts are not there - which
  was wrong before this change too, by the way, because a fresh
  unpacking of the zip had the same problem.

- **The decision under "Decide before release" has moved, not been
  carried out.** It had said there since 25 August that the 1.5.x test
  panel, the measurement history and the reports all go out at
  release. Asked and answered at this release: the panel stays in. The
  reason to take it out (a tool for the build, not for the user) still
  stands, but sixty-six of the ninety-six test files import
  `test_panel`, so taking it out means wrecking the test suite - and
  the user uses the panel weekly. What has been carried out is the
  other half of that decision: the measurement work itself stays
  outside the repo.

  Something came to light along with that: the delivery zip of v0.152.0
  did contain those measurement files. The agreement "never travels
  along in a delivery" had in practice only been applied to the
  *installation* - they are not overwritten there - but the zip was a
  snapshot of the folder and so took them along.

Included in v0.152.0:

- **B541 - the same frame is not drawn twice.** Point 10 of the build
  list. The render loop built every frame up again, even when nothing
  about it had changed: the intro is one still image that was built
  250 times, the outro likewise, and between two lines nothing moves.
  Measured on the user's own render: 249 of the 250 intro frames were
  byte for byte equal to their predecessor, 199 of 250 in the outro and
  99 of 250 in the text.

  What it comes down to is the question "is this frame the same as the
  previous one", and that has to be answered exactly - a frame that
  stays stuck in a finished video you only notice when someone watches
  it all the way through. Deriving such an answer by rebuilding the
  drawing rules in a second function is exactly how those two drift
  apart: the next person to change something about the drawing forgets
  the copy. So the answer is not derived but RECORDED. The frame is
  first built dry with a ledger in place of the canvas: every command
  goes into a list and nothing is rasterised. Two frames with the same
  list would have been built from the same commands in the same order,
  and are therefore by construction the same frame. What that costs is
  the layout (the font measurements), not the drawing - and the drawing
  is the expensive half.

  Two things came out of the measuring and both are in it:

  - **The layout of a line is computed only once per render.** How a
    line breaks over rows and how high it is depends on the line, the
    font and the width - not on the moment. Yet it was redone fifty
    times a second, for three lines, with a font measurement per
    syllable. That alone makes the drawing itself a quarter faster,
    apart from the reuse.
  - **Recording costs about a tenth of drawing**, and that is a gain in
    a still stretch and a loss in a song that sings through from start
    to finish. So the recording backs off after a run of misses: it
    then still looks at a FEW frames per ten - a few, because seeing
    that nothing moves costs two frames side by side. A still stretch
    is picked up within a fifth of a second that way, and a song
    without any stillness pays a few percent.

  Measured on a 45-second test song with intro, a line over two rows, a
  sing-along line, an instrumental gap with countdown and an outro: 70%
  of the frames reused and 2.4 times as fast as v0.151.0. On a song
  that sings through unbroken (the worst case): 1.2 times as fast,
  because there the gain comes only from the layout cache. In both
  cases byte for byte the same comes out, and there is a test on that
  which puts every frame of such a test song with and without reuse
  side by side.

  What has NOT been built is the second direction of point 10:
  spreading the drawing over more cores. That is the real work on a
  machine with twelve threads, but it can only be judged once the
  bottleneck is measured to lie at the drawing again - so after this
  step, on a real video on the user's machine.

Included in v0.151.0:

- **B538 - a song with two languages in it gets read in the second
  language too.** 1.5.11g ran on 31 August on "Lied_R2", the only
  project with a second script, and the result was clear: the whole
  song in English with Korean that may only fill silences comes to
  0.08 s from the manually set line starts against 0.09 s for bare
  English, and 2.0 s of singing is added in three bits - exactly the
  three Korean shouts. Nothing is lost: zero seconds that English did
  have and the merge did not.

  That path is in production now. If the text sees a real passage in
  another script (B495), the whole song goes along as one extra job in
  the same queue that already runs the pieces: the same seconds,
  another language. At the front of the queue, because it is as heavy
  as the first whole run and the queue starts with the heaviest work.
  What that second reading yields goes through exactly the same door as
  a piece (B442): it may fill a silence and it can never overrule a
  word the first run heard. The second language is in the cache key -
  add a Korean verse and the stored transcription is the answer to a
  different question - and the log says how many words it really filled
  in, so you can see whether it was worth its run.

  Two things from the re-read are in it. Without measured singing the
  second run does NOT start: a word only counts as a filler if it sits
  on singing, so that would be a whole Whisper run for certainly
  nothing - and the progress bar would stall on it as well. And kanji
  count towards their block as Chinese, so a Japanese song got a whole
  Chinese run every time for a script the first run already knows; that
  does not happen any more.

  Note when putting this to use: the second language is in the cache
  key, but an existing step without that key stays valid (as with
  B442). A project that already has a transcription therefore does not
  rerun by itself - the gain only comes when something else changes
  (other lyrics, other model, newly separated wav), or when you run
  step 2 again by hand.

  What went OUT at the same time is the route 1.5.11g was originally
  built for: the second language over only the weak spots of the
  first. That gave six words and 0% on a real line - a spot of a few
  seconds is too little run-up for Whisper, even with three seconds of
  slack on either side. `weak_by_ratio`, `useful_spans`,
  `combine_in_spots` and their constants are gone, just as with 1.5.8
  and 1.5.11c: the answer stays in the log, the road towards it does
  not stay in the code. The experiment itself remains - one song is no
  rule, and it should be checked on a new song whether that merge still
  wins.

- **B539 - a crammed tail gets laid out over the singing.** The worst
  project in the collection, "Lied N" at 7.58 s, turned out to
  have one clear picture. The song ends with the chorus four times in a
  row, the coupling matched all four on the same early spot, and the
  last fifteen lines ended up back to back at the minimum duration of
  one second between 189 and 204 s - while the vocal track shows that
  there is singing up to 220 s and the user has put those lines at 189
  to 222. Sixteen seconds of measured singing without a letter of text
  on it, and a metre of lines standing shoulder to shoulder in front
  of it.

  Two things have to be true together and neither of them is enough.
  There is singing AFTER the last line - so the text ran out before the
  song did - and the tail lies on the floor of the minimum duration,
  which is what the placement itself says when it has nowhere to go.
  Then those lines are laid out over the singing windows from where the
  tail starts, each window in proportion to its length. The run also
  has to START on a floor line, otherwise it creeps backwards over
  healthy lines for as long as the share stays high.

  B336 already does this for the tail after the last anchor, but it
  needs a phrase period AND a precise fit. This case has neither: the
  lines ARE anchors (wrong ones), and the song has no measurable
  period - and that is exactly why nothing ever caught on it. Measured
  over all twenty projects: "Lied N" from 7.58 s to 3.90 s, with
  the damage on lines the user has not even moved down as well (0.66
  to 0.61), and not a single other project shifting by a thousandth.
  The yardstick over the whole collection goes from 2.81 s to 2.46 s
  with it.

  The critical re-read has planed this step down a good deal, and that
  is worth writing down, because the first version was 0.5 second
  "better" for the wrong reason. It spread the lines PER WINDOW with
  rounding, and with fewer lines than windows that skipped the first
  windows and shoved the whole tail to the end of the song; on "Lied
  N" that happened to come out well. Now it walks over the sung
  SECONDS: the first line lands exactly on the start of the tail and
  the spacing is equal in the time when someone is really singing. The
  step also keeps the agreements `sanitize_timing` itself keeps - no
  overlap, within the song, never under the minimum duration, and
  nothing happens if that cannot be done - it lets lines that are off
  (B180) keep their place instead of eating a piece of singing nobody
  sees, and it demands that the line before the tail is NOT a floor
  line. Without that last one a song of twenty short shouts was one
  tail from line zero, and moving a line over the END of a song shifted
  the whole song.

- **B540 - tried and measured that it does not work.** The
  second-worst project, Lied_T at 7.28 s, has a
  comparable picture but in the middle: ten lines without a time of
  their own between two anchors, laid out at 5.46 s each straight
  through two silences of 12.8 and 10.8 s. B392 refuses to step in
  there as soon as the windows do not explain the run one-to-one, and
  the idea was to soften that refusal: spread them proportionally over
  the windows as soon as a quarter of the gap is silence. Built,
  measured, and it made exactly that project WORSE (7.28 to 7.35 s,
  damage 0.69 to 0.74) while nothing else moved. The reason is worth
  keeping: the two anchors around the gap are themselves wrong, and no
  distribution between two wrong ends can come out right. The idea has
  been rolled back; the note is in the code, where the next person to
  see this will run into it.

  What "Lied T" does need is therefore something else:
  those anchors themselves. Zero unique lines, forty times the same
  "La-la-la" - nothing to tell apart with text there. Not tackled yet.

What the yardstick says about all of it, over 310 lines moved by the
user across twenty projects:

| version | weighted error |
| --- | ---: |
| 0.148.0 | 3.48 s |
| 0.150.0 | 2.81 s |
| 0.151.0 | 2.46 s |

Included in v0.150.0:

- **B534 - every run keeps its own report.** The test report went to
  one fixed file, `docs/testverslag.md`, and was overwritten by the
  next run. On 31 August that wiped out the run of 1.5.1 through
  1.5.10 over all projects the moment 1.5.11g started - hours of
  measurement work, recoverable from the log and nowhere else. The
  reports now go to `docs/verslagen/`, with date, time, version, which
  actions and which scope in the name:
  `testverslag_2026-08-31_0929_v0.150.0_1.5.5_alle-projecten.md`. A
  long tick list becomes "first to last" (`1.5.1-tm-1.5.10`), because
  twelve codes in a filename helps nobody. `modelmatrix.md` and
  `modelcombinaties.md` stay in their fixed place - that is "the
  newest" - but drop a dated copy in the same folder. That copy is made
  BEFORE a new run starts writing and not when it is finished: a run
  that is broken off halfway is precisely the run that would take the
  previous one with it. The user empties that folder himself; nothing
  from it ever travels along in a delivery.

  Out of the critical re-read came four more holes in the same
  agreement, all closed: the name counted in minutes, so two runs close
  together still overwrote each other (now seconds, and if the name
  exists anyway a `_2` is appended); an action that came in without a
  started run appended to the newest report lying there - a report that
  names a different date and version at the top - and now starts its
  own; the same collision applied to the dated copies; and if the copy
  failed, the run after it simply wrote over the previous result with
  only a log line as a trace - the copy now falls back to a spot beside
  the source. The log now also says which file the running run writes
  to; there are a lot of them now.

- **B535 - an anchor at the END of a crowded run kept its start.** B340
  drops only the inside of a run of anchors that sit much closer
  together than the phrase of the song: the outer two hold the stretch
  in place. B522 gives an anchor that is only too long its measured
  start back. Those two together did exactly what neither of them
  intended: the last member of such a run kept its start, while that
  start is measured just as badly as those of the members beside it.
  Measured on "Lied K": line 43 runs in the coupling
  from 202.57 to 225.09 (22.5 s against a phrase of 3.44) and starts
  10.3 s before where the user has put it; the whole outro was dragged
  forward by it. The yardstick went from 4.85 s to 6.90 s between
  v0.147.0 and v0.148.0 and is back at 4.85 s now. The question "which
  anchor has to go" and "may this start be believed" now each get their
  own answer over the same run: the inside (`run[1:-1]`) against the
  run without its first member (`run[1:]`).

  The FIRST member keeps its start, and that is deliberate. A crowded
  row is the picture of one line laid down several times, and of those
  copies the first is where the singing plausibly began - the rest
  drift away from it. It is moreover exactly the shape B522 was built
  for: a good start with an end that runs into the instrumental
  section. The critical re-read noted that nothing was measured for the
  first member; on the five projects where this could be recalculated
  it makes no difference, so it stays as it was.

- **B536 - two model switches flipped, both measured twice.** The
  leave-out trial (1.5.9) ran on 26 and 31 August across every project
  with manual timing and said the same thing both times:

  - **B213 (filler words separately) is back ON**: -0.18 s. It was off
    since v0.115.0 with the note "-0.13 s on the reference set". That
    set has grown since and the steps around it have changed; a model
    that is switched off keeps running every pass for that reason,
    otherwise such a judgement stands for thirty versions.
  - **B258/B285 (hallucination filter) is OFF**: -0.14 s. On "Lied T
    " it is not a nuance but the main defect: 17.29 s of
    error with the filter on against 7.28 s with it off, and the damage
    on lines the user never even moved drops from 7.47 s to 0.69 s. Off
    and not gone: it keeps running along every pass.

  And there was a catch in that, found during the critical re-read. The
  switch replaced `_filter_hallucinations` with a pass-through, and two
  other ideas live in that one function that have nothing to do with it
  and were measured separately: the fixed list of Whisper artefacts
  (B141, "MUZIEK", "Ondertiteling") and the stuck repetition (B514, two
  hits over twenty projects and zero false ones). Those went off
  silently along with it. That also explained the only place where
  switching the filter off did damage: "Lied I" went from
  1.81 s to 4.34 s, and that was B514's 29-second La-da-da loop coming
  back. The function now has a `song_wide` switch that turns off
  exactly the two ideas the model is named after; B141 and B514 keep
  running. Re-measured over the five projects where that was possible
  here: "Lied I" is back at 1.81 s and the weighted error
  over those five goes from 5.25 s to 3.58 s.

  Two things followed from that:

  - The orderings in 1.5.10 rearrange the pipeline as it REALLY runs,
    so they build on whatever function sits on the module at that
    moment - reaching past a model switch would measure a pipeline
    nobody has. But then an ordering can become empty: if a step it
    moves is switched off, there is nothing to rearrange and a tidy
    "+0.00" turned up in the table for something that was never
    attempted - exactly the measurement error that B529 cleared up one
    layer down. Every ordering now names the models it moves, and if
    one of those is off, the table says "skipped" with the code beside
    it.
  - There is a test that pins down the SHIPPED state (which models are
    off, and that the fixed list and the stuck loop still filter while
    an invented sentence stays). The test suite itself runs with
    everything on - otherwise fourteen tests guard code the app no
    longer executes - so without that one test the real state is never
    checked anywhere.

  The second re-read added one more thing: with the switch off, a word
  from the B258 list counted as "not a hallucination", and that
  acquitted the rest of the segment along with it. "ZANG EN MUZIEK"
  then stayed while a bare "MUZIEK" did go - the example the
  explanation of B258 itself opens with. Such a word now does not count
  instead of acquitting, the same as a function word: then B141 keeps
  its grip and a song that really is about singing keeps its line.

  Converting it brought a fault in the tests themselves to light: a
  model that is off is switched off by REPLACING a function on its
  module, and that replacement then stayed in place for the rest of the
  run. As long as only B213 and B380 were off nobody noticed, because
  no test measures those functions; with the hallucination filter off,
  fourteen tests of exactly that filter fell over, and only when the
  whole suite ran. The registry is now restored after EVERY test.

- **B537 - the alarm block in the test report.** The alarms are a table
  with a sentence above it, and they were written out line by line as
  bullets. That gave an empty bullet (the blank line the block opens
  with), a table that could no longer render, and with no alarm at all
  a reassurance under the heading "Alarmen" - which reads like an alarm
  nobody wrote down. There is now `alarm_rows()`, which is empty when
  nothing is wrong, and the block goes into the report as a block.

Two things on the user's machine, no program work:

- `output/settings/project.json` (29 July) held nothing but old video
  titles from "Lied G" and belonged to no project
  at all; the app warned about it at every start (B445). The program
  deliberately does not delete that file itself; it now sits in
  `_to_delete`.
- The logo of "Lied G" sat in a grey-and-white
  checker pattern. That was in the SOURCE: `logo.png` is RGB without an
  alpha channel and the background is a chessboard of 30 px squares in
  244 and 254 grey - flattened transparency, not a fault in our
  placement. The near-white squares have been made pure white (the old
  one is in `_to_delete`); the video has to be re-rendered for that to
  show.

Included in v0.149.0:

- **B530 - the picture shifted for the intro and the sound did not.** If
  a song's first line starts before the tenth second, the renderer puts a
  run-up in front of the picture (B203), and as much silence should come
  in front of the sound. On three projects that second part did not
  happen, and then the text lags the singing all song long. Measured over
  all 21 projects: ten need such a run-up, and on Lied_S (8.30 s
  needed, 0.15 s present), Lied_A (6.21 against 0.00) and
  Lied_I (2.96 against 0.05) it was missing.

  A regression, not an old fault: the version sits in the metadata of
  every video (B273), and Lied_S was right under v0.101.0 with 8.60 s
  of silence, Lied_I right under both v0.132.0 and
  v0.135.0 with 3.00 s, and both wrong from v0.141.0 on.

  Two things have changed, both in the filter chain:

  - the delay now sits at the FRONT instead of behind the level
    control. loudnorm rebuilds its filter graph halfway through a song
    - after its look-ahead window it chooses between a straight gain
    and dynamic compression - and everything hanging behind it is set
    up again at that moment. Silence that is already in by then can no
    longer disappear;
  - the channel layout is stated. The user's karaoke.wav files carry
    `channel_layout=unknown` (measured across his whole collection),
    and `adelay=...:all=1` has to bind itself to the channels of a
    known layout. Without that layout ffmpeg either refuses the link
    outright ("Cannot select channel layout for the link between
    filters", reproduced on ffmpeg 4.4) or - worse - it delays nothing
    and says nothing about it.

  Exactly why ffmpeg 9.0.1 on Windows dropped the delay cannot be
  proven from the outside; both constructions above are fragile in any
  case and are now gone. That is why a third thing comes with it, one
  that is independent of the cause: **the render checks itself**. Just
  before the file is put in its place, it measures the silence at the
  front and holds it against the shift of the picture. If more than a
  tenth of a second is MISSING, the video is not written out and the
  user is told why. Better a render that refuses than a video that
  lies.

  That check is one-sided on purpose, and that is the repair of a fault
  that was in it at first. What gets measured is the silence at the
  start of the finished file, and that is the run-up PLUS the silence
  the song itself opens with - the two border on each other and the
  meter sees one. On his own collection that difference ran from 0.2 to
  0.4 s, and all those renders were fine. Checking both sides would
  have refused exactly the healthy renders.

  The ffmpeg command now goes to the log: the fact that it was not in
  there is why this could only be worked out afterwards from the files
  themselves.
- **B531 - 1.5.12: re-render every video.** Not a measurement but a
  chore, and the second time it has been needed: the first after the
  improved text outline (v0.146.0), now after B530. At B479 exactly
  such an action was removed as temporary; so it came back, and that is
  why it now stands as an ordinary button and not as a stopgap.

  It sits at the end of the list, never joins in with the "select all"
  checkbox - re-rendering every video overwrites finished work and you
  do that deliberately - and does not count towards the ceiling of ten;
  that ceiling is about the numbered measurements. A field of its own,
  `on_request`, has been added for it beside `heavy`, because those two
  do not mean the same thing: a heavy trial drops out of the list when
  there is nothing underneath it, and this one must never drop out.

  Per project in this order: put the default background in place
  (`config/backgrounds/background_001.png` as `input/<project>/
  background.png` - eight projects already had it, thirteen did not;
  copy it and do not fall back on the global setting, because that is
  exactly what B480 forbids), then render alongside the existing files,
  and only once that render has passed its own B530 check move the old
  videos (all sequence numbers) to
  `<programmamap>/../_to_delete/oude_videos/<project>/`. If the render
  fails, everything stays where it is and the table says so.
- **B532 - collect and copy, on tab 2.** On as soon as any project has
  a video. Two questions and then it runs: only the videos, or the
  whole set - video, original recording, lyrics and karaoke text - and
  where it should go. The full set gets a folder per project, because
  four files with the same names from twenty songs in one folder is not
  a collection but a heap; the videos on their own stay flat, since
  their file names are the titles already. From a project with several
  renders the newest goes along, and that is the highest sequence
  number and not the newest name - `_10` comes after `_3`.

From the critical re-read before release (B530/B531/B532):

- **The self-check refused good renders.** See above: the check is now
  one-sided. A check that fires wrongly more often than rightly is
  worse than no check, because then you switch it off.
- **The collect button could not copy anything.** The progress signal
  carries two numbers and was called with one; that `TypeError` hit on
  the first call, before the first file. The button was a hundred
  percent broken and not one test touched it, because they all called
  `collect_videos` directly.
- **The silence measurement looked away at exactly the defect it has to
  catch.** With a pause later in the song it returned "not measured"
  instead of "no silence at the front", and then the check is skipped.
  Only the first reported silence now counts, and if that starts later
  than 0.05 s the answer is zero.
- **An unreadable file measured zero.** The exit code was not read, so
  "cannot measure" and "no silence" were the same answer - and on that
  answer the render refuses.
- **The collection picked the wrong variant and overwrote silently.**
  `existing_videos` without `like` returns the newest file in the whole
  folder, and that can be the vocals-only variant; the docstring of
  that function warns about it itself. And two projects can have the
  same video title, because it comes from the settings and not from the
  folder name - the second now gets the project name added instead of
  overwriting the first.
- **The cleanup loop could still destroy the old video.** If the move
  failed it renamed anyway, and `replace` overwrites. The new one is
  now only renamed once the old one is really gone.
- **`projects_with_video` created folders.** Via `context_for_project`
  `ensure_directories` ran over every subfolder of `output`, including
  ones that are not projects. Listing must not change anything.
- Smaller: the channel delay is now given per channel
  (`adelay=6215|6215`) instead of `all=1`, so the filter never has to
  work out what "all" means; the destination of the collection may not
  lie inside the project folders themselves; the Stop button works
  while copying; and a test has been added that does the measurement on
  a real file instead of a mocked one - the three faults above stayed
  invisible precisely because every test stubbed the measurement out.

Included in v0.148.0:

- **B519 - after one manual adjustment the whole link editor went
  red.** The links themselves stayed (measured: 362 of the 363), but
  everything you SEE of them was wiped: `_word_entry` set `sim` to 0.0,
  `found` to None and left `status` out entirely. The row colour comes
  from `sim` and 0.0 is red, so one merge turned 346 green rows into
  362 red ones. Nothing was broken; you just could not see any more
  what was right. Those three fields are now recomputed from the links
  as they stand at that moment - the same phonetic comparison the
  display itself uses. Measured after the repair: 345 green, 9 yellow,
  8 red instead of 362 red.
- **B520 - the found track was updated per word and the run rule was
  not.** A run of four or more unlinked words in a row looks like a
  hallucination, but link one of them and the run is broken - then no
  word in it should still stand as suspect. `found_word_status` is now
  the ONE place that decides that, and after every adjustment the
  editor revises the whole track instead of one word.
- **B521 - a repeat from the lyrics was flagged as an invention.** "at
  a bar called O'Malley." at 268.8 s in the user's own project is
  literally line 34 of his lyrics; the song sings that line twice while
  the text writes it only once, so the linking has already used those
  words up by the time the repeat comes round. A run in which two
  thirds or more of the words occur phonetically in the lyrics is now
  called "repeat, not in the text" and no longer "looks like a
  hallucination".
- **B518 - there is one read path for the transcription, and it is now
  pinned down.** The file on disk is not the list the program works
  with: `pipeline.load_segments` runs three repairs over it that take
  words out (at "Lied R" two of them, 291 on disk against 289 in the
  program). Anyone who numbers against the raw file is one place off
  after position 27 and two off after position 144 - which looks
  exactly like shifted links and is not. That cost the user a set of
  eighty-two good links. A test in `tests/test_v0148.py` now records
  which functions are allowed to read the raw file (two, and both with
  a reason), and the trap is written down in the docstring of
  `load_segments` itself.
- **B522 - an over-long sentence lost its measured start.** A sentence
  that runs too long was "suspect" and was dropped as an anchor, after
  which its START was interpolated between its neighbours. But the
  start is usually measured; only the end is wrong. Such a sentence now
  stays an anchor candidate and gets its end clipped to the phrase of
  the song. Measured on "Lied H": line 31 goes
  from +7.282 s to +0.370 s against the manual timing (134.973 against
  134.603) and the end is brought back from 152.108 to 141.169.
- **B523 - a line was smeared across the block boundary, into the
  instrumental section.** Between two blocks there is music, and that
  music belongs to no block - but there is energy on it (a ghost voice,
  a held synth), and the placement drifted towards it. Two places
  repair that, both with the same idea as the block barrier for anchors
  (B251), but now for the placement:
  - the last line of a block may not run on with its held note as far
    as the first line of the NEXT block. Its ceiling is now where the
    singing of this block stops. Measured on "Lied H
    " that is the cause of the shifted line 15: the sentence grew
    from 66.39-67.60 to 66.39-83.31, became too long by that, lost its
    anchor in v0.147.0 and ended up with its start in the middle of the
    instrumental section;
  - a run of lines without a time of their own is cut in two at the
    block boundary: what belongs to the block before stays before, what
    belongs to the block after comes after. The boundary is the longest
    silence in the gap. Measured on "Lied P": lyrics line 20
    ("Oh let's go", the last of its block) ran from 87.911 to 99.227 -
    eleven seconds, right up to the next line. Now 87.911-88.816, and
    the user's manual timing says 87.617-88.688. On the other projects
    with a singing voice nothing changes.
- **B524 - the outcome of a test can now leave the machine.** Every
  action also writes its lines to `docs/testverslag.md`, with the time,
  the processor time and the alarms alongside. The log window already
  kept them, but the user cannot pass that text on; a file he can.
  Rewritten per run, so that what is in it always describes exactly one
  run. A measurement file: never goes along in a release, and sits in
  `tests/conftest.py` among the redirected paths.
- **B525 - the sharpest measure of 1.5.7 measured nothing.** "Syllables
  across a MEASURED word boundary" held the words of the PARODY against
  the measured word boundaries of the ORIGINAL - different words, "app
  me terug" against "Write to me". Over twenty projects it gave between
  44% and 76%, and a number that always stands high is not a
  measurement but noise hiding the counters that do say something.
  Gone; the shape, silence, gap and duration counters remain, and the
  history now compares on "words in a measured silence".
- **B526 - 1.5.8 is gone, and its answer with it.** The action always
  said the same thing: this project has a gap or it has not. Knowing
  that never changed anything, because only 1.5.11 can say what to do
  about it - and that measures the gap itself. The measurement
  (`_gaps_in`) therefore stays as a helper. The number 1.5.8 stays
  empty: renumbering would give every number in the log, in the test
  history and in conversation a different meaning, and that is exactly
  what a number must never do. The next investigation takes 1.5.8 again.
- **B527 - 1.5.11g has become a search instead of a single
  comparison.** One comparison cannot find a common denominator. Four
  ways of reading are now produced (the whole song in the largest
  language, the whole song in the second language, the largest language
  cut at the silences, and the second language over the weak spots -
  cut generously, three seconds either side so that Whisper has a
  run-up) and those are combined in four ways, from cautious (the
  second language may only fill silence) to wide (both languages over
  the weak spots). All eight go into one table, sorted on the number
  that matters: the median distance from the user's own line starts to
  the nearest word start. That is exactly what the timing of a
  transcription needs - every line start it anchors on comes from a
  word start.
  The weak spots are no longer found with "there is nothing at all
  here" but with a ratio: less than a third of the singing time in the
  neighbourhood covered by words that occur in the lyrics. There is
  almost always some linking, after all, because some words exist in
  both languages. Measured over the projects with a singing voice, the
  ratio test yields fewer but more meaningful spots than the zero test
  (Lied_A: 3 spots totalling 24.0 s instead of 12 spots
  totalling 68.1 s).

From the critical re-read before release (B528/B529):

- **B528 - `_filtered` and `_in_lyrics` were left behind on a split.**
  Those are transcript indexes too, and `_remap` moved only the links.
  After a split everything behind the split point pointed one place too
  far left: the wrong word was struck through and the run rule of
  B520/B521 judged the wrong words - exactly the fault B519 repairs on
  the other track. A manual mark ("this is a filler word") also lived
  only in the display and was gone after a split; it is now remembered
  and moves along.
- **B528 - an empty run won the search table of 1.5.11g.** "Distance to
  line start" gave 0.00 s both for "hits every line start exactly" and
  for "there are no words at all", and that is the number it sorts on.
  A failed run therefore stood at the top and was declared the best. No
  words is now infinitely far.
- **B528 - `merge_runs` returns a tuple.** The most cautious
  combination in the new search took `(woorden, aantal)` as a word
  list; that would have toppled the whole 1.5.11 action on the user's
  machine, after the Whisper time of four runs.
- **B528 - the block boundary has two sides.** The part after the
  boundary started where the singing of the previous block stopped
  instead of where the singing of the next block begins, so the first
  line of that block could still end up in the instrumental section.
- **B529 - the model switch "anchor check" sat on a wrapper nobody
  called any more.** Since B522 `sanitize_timing` calls
  `implausible_and_overlong` directly, so switching that model off
  changed nothing and the matrix (1.5.10) reported 0.00 s for it - a
  measurement error, not a measurement. The switch now sits on the
  function that really runs; measured on "Lied H
  " one line changes when the model goes off, and zero before it.
- **B529 - a skewed anchor counted as "only too long".** B522 lets a
  suspect anchor keep its measured start if it is only too long. An
  anchor that is suspect because the linking has laid down the same
  line several times must not come through that door: its start is
  precisely what is wrong.

Trap to remember (B518): anyone counting or numbering words does it
through `pipeline.load_segments` and never through
`whisper.load_segments`. The raw file has more words than the program
uses, and the difference looks like drift.

Second trap (B528): anyone renumbering a list renumbers everything that
points at those numbers. In the link editor those are `_targets`,
`_filtered`, `_in_lyrics` and `_marked`; forget one and it looks like
drift that is not there.

Included in v0.147.0:

- **B513 - lyrics words lay on top of each other in the link editor.**
  This is the cause that three rounds of "the links have shifted again"
  trace back to. `_relayout` gives every word a column, and a column IS
  the position: `_bot_rect` computes the x from it and `_hit_row` finds
  the clicked word back with it. Two lyrics words on the same column
  are therefore drawn on exactly the same pixels, and the click always
  returns the first. You click the box you see and the editor links its
  left-hand neighbour. Measured at "Lied R": 25 unreachable words
  (column 93 carried `me` and `I'll`, column 97 `high` and `That`,
  column 272 carried three of them), and of the 82 filled pins in that
  project not one matched what the automatic linking said - 65 pointed
  one or two found words too far left. The guard is one rule: a lyrics
  word lands strictly to the right of its predecessor. And `paar_col`
  has changed from "the column that is free at this moment" to the
  column of the first found word of its group, which is what finally
  makes B220 true; if it cannot stand there it shifts one place and the
  line runs at an angle - a straight line to a word that cannot be seen
  and cannot be clicked is no line.
  The re-read added a second wrecker: a merged box can cover a column
  that belongs to nobody, and the link line hangs from the optical
  centre of that box. A click there fell through to `_hit_link` and
  removed the link of the WHOLE group, while the user was clicking in
  the middle of a word box. A click inside a drawn box now does
  nothing.
- **B514 - a word of twenty-seven seconds is not a word.** At
  "Lied_R2" (Korean) Whisper produced one word of 223 characters
  running from 116.8 to 143.8 s, straight across the second chorus. It
  slipped through every check: the broad check demands at least two
  content words and this segment has exactly one, so the safety valve
  "too little material to judge" let through precisely the worst case.
  The rule emphatically does NOT say that nothing was sung there - the
  user recognised his four repeated shouts in it, so the loop starts on
  real singing. What it says is that such a word carries no usable word
  times: where in those 27 seconds those shouts lie cannot be derived
  from it. Filtering it out makes an honest gap of it, and a gap is
  something the next attempt can search for (B515).
  Two things from the re-read are in it. Long in TIME only counts
  together with long in CHARACTERS, because a held note is exactly a
  word that lasts long and is short in letters ("aaaaah" of nine
  seconds is singing). And the whole segment only goes when the loop
  largely fills it, so that one long note among nine good words does
  not drag those nine along. Recalculated over all twenty projects in
  the cache: two hits, both real loops ("Lied_R2" and the
  "La-da-da-da" of 29 s at Lied_I), zero false ones.
- **B515 - trial 1.5.11g, the second language over the weak spots.**
  The user's idea, and sharper than "the whole song in the other
  language" - that was measured at B495 and it loses. First the whole
  song in the largest language, then find the weak spots of THAT run,
  and offer only those to the second language. Weak is twofold: singing
  time without a word (the familiar gap) and singing time with words
  that occur nowhere in the lyrics - the latter is what a passage in
  another language looks like after a run in the wrong one; at "Lied R"
  the Korean shouts came out as "Dear" and "Doom".
  Two things the recalculation on real data produced that would have
  stayed invisible on invented test data. The first version weighed on
  Whisper's confidence, and with a median of 0.55 and 127 of 291 words
  below half it called 137 seconds weak in a song with 97 seconds of
  singing - so the trial would have redone the whole song. Now only
  "does this word occur in the lyrics" counts, with a bridge over the
  breath between two words within a line. Result at Lied R: exactly one
  weak spot of 5.5 s, where the English says "I'm confused, but who's
  who" and the Korean 착각하지만 누가 누군지 - the real line. The second:
  `merge_runs` only fills silence, and in production that is the right
  rule, but a weak spot is usually not silence. On that one spot it
  therefore added exactly zero words. Within the marked spots, and only
  there, the second run may replace the first; what comes out of it is
  a THIRD variant beside the two, and the table decides, not the code.
- **B516 - a yardstick that lays two runs side by side.** 1.5.8 counts
  only gaps of five seconds or longer and gave exactly 5.3 s three
  times for Lied R and Lied_R2, while one run covered 21.5 s that the
  other did not have. Now: covered singing time of A, of B, only-in-A,
  only-in-B, with the text of both for each piece. Usable for any A/B
  question, not only for languages.
  Two corrections from the re-read. The floor of half a second was
  applied per word piece instead of per contiguous stretch, and
  Whisper words are a third of a second - so a whole missed line was
  reported as zero, exactly the failing this yardstick holds against
  1.5.8. And the difference rows stood under a paragraph without a
  header row, so they came out on screen as raw pipes instead of as a
  table.
  With it the user's idea: two projects can use the same recording
  ("Lied R" and "Lied_R2" are the same m4a with different lyrics), and
  then the manual timing of the one is a reference for the other. The
  column "on a real sentence" counts how many heard words fall inside a
  manually timed sentence. That fills a real gap: "in text" compares
  phonetically with the lyrics, and for a passage in another script
  that comparison cannot work - at "Lied R" the Korean is written in
  Latin letters, so a correct Korean word scores zero there however
  good it is. The reference knows nothing about spelling. The spans are
  projected back onto the timeline of the original, because a timing
  sits on the karaoke clock.

Included in v0.146.0:

- **B506 - a pin was two bare numbers, and that did not hold.** The
  manual word links pointed with a position in the lyrics word list and
  a position in the transcription. Both lists change shape: B412 left
  the digits in, B418 splits on a hyphen, B484/B485 changed what `[bg]`
  does with the tokens. Each time there was a one-off migration, with a
  marker saying it has been done - and that marker is exactly the
  mistake, because it promises the list will never change again.
  Measured at "Lied R": a hundred and twenty pins, sixty-six of which
  pointed two to thirteen places wrong in contiguous rows (keys 104-112
  pointed at transcript 77-85, while those words belong to lyrics word
  91-99), and not one error message - a shifted pin keeps working, it
  just means another word. Beside its numbers a pin now carries a
  description: which lyrics word (text, line number, which occurrence
  on that line) and which found words (text and start time), plus a
  fingerprint of both lists. If the fingerprint still matches, the
  numbers are used untouched; if it does not, every pin is looked up
  again by its description and whatever can no longer be found goes
  WITH a log line. The first time nothing is moved: what is there is
  then the reference point, because there is no description of what it
  once meant and guessing would set a guess in stone. Saving from the
  editor wipes the description, so that the pins afterwards mean
  whatever they point at at that moment.
- **B506 follow-up - an empty pin was invisible.** Fifty-four of the
  hundred and twenty pins at "Lied R" were empty ("I have unlinked this
  word"), and a pin - an empty one too - always beats the automatic
  linking. On top of that they got status "coupled", so there was
  nothing on the screen that explained why a word stayed loose while
  the identical word stood right above it. They now have a colour code
  of their own with a line in the legend, and a third state has come
  alongside linking and unlinking: "Vrijgeven" (release) takes the
  manual decision away, so that the automation gets the word back.
  Without that state a word you had once unlinked could never come
  back.
- **B507 - the karaoke box was longer than the original box.** The
  linked original box is built from the sung span of its karaoke line,
  but the karaoke cell itself came from `_dict_span`, and that simply
  counted the inline `[bg]` part along. Everything else that reasons
  about the length of a sentence (`TimedLine._sung`,
  `timing_editor._line_span`) has skipped that part since B485; this
  one place did not. Measured at "Lied R": line 19 was 0.79 s longer
  than its original, lines 24 and 25 about 0.35 s each. The bg part now
  gets its own dotted box on its own time - in the sentence, block AND
  word views, because backing vocals belong in every editor and only
  not in the render. It is drawn, not dragged: it moves along with the
  sentence it belongs to.
- **B508 - the original track was a back door.** `_move_original` moved
  or stretched an original sentence, took the linked karaoke lines
  along, and then ran no check at all on the karaoke track:
  `_keep_in_order` and `_without_overlap` were not called there. With a
  line that has a bg part it always went wrong, because that part
  scales along past the end. On top of that it clamped on the duration
  of the ORIGINAL while that track has run on the karaoke clock since
  B489. Both are straightened out. And instead of two mirroring routes
  that each had their holes - `_mirror_to_original` only worked on a
  1-to-1 link, and in the block view it did not run at all - the linked
  box is derived again from its rows after every drag, with the same
  min/max rule the editor is built with. The line checks of B500 now
  run in the editor too: after every drag, and a sentence with overlap,
  zero length or wrong order gets an orange border. That is where such
  an overlap is made; naming it three steps later in a report is too
  late.
- **B509 - a whole `[bg]` line stood orphaned in the track.** Such
  lines are deliberately kept out of `couple_timing` (B264): they would
  take a place of their own in the block and line count, and a line
  that sounds OVER another does not have that place. But that also left
  them without a link, so the two `[bg]LIED_R[/bg]` lines at the end of
  "Lied R" stood opposite the two lyrics lines `Twee-uh` that belong
  with them without either knowing of the other - switching one off let
  the other light up, and the original box could not be switched off at
  all (`if not rows: return False`). After `attach_bg_lines` a second
  round links the leftover bg lines to the leftover lyrics sentences,
  by POSITION: between the sentences of the linked neighbouring lines
  before and after. Deliberately not by block number - the two texts
  each count their own blank lines, and leaning on the assumption that
  those numbers run together is exactly what broke at B488. A bg line
  with a counterpart takes its time from it; only without a counterpart
  does it fall back on the neighbouring line, and then it really sounds
  along.
- **B510 - `disabled` meant two things at once.** A whole `[bg]` line
  stayed out of the render only because `attach_bg_lines` let it be
  born disabled; `video.py` filters on `disabled` and `TimedLine` had
  no bg flag at all. Switch such a line on in the editor - the only way
  to see where it lies - and it stood in the video. At "Lied R" lines
  53 and 54 were on. `bg` is now a field of its own on the line, the
  render filters on that, and `disabled` means again what the user
  means by it. The flag comes from the karaoke text
  (`apply_inline_crowd`), not from the timing file, and
  `_to_dict`/`_from_dict` carry it along - the same trap the syllable
  bg already fell into once at B485. `line_checks` exempts a bg line
  from the overlap check: backing vocals CAN sound at the same time as
  another sentence, and need not.
- **B511 - the outline colour was wrong for two of the four.**
  `contra_colour` decided on perceived brightness with the threshold at
  128. White (255) and grey (158) rightly got black by that, but red
  `#E53935` comes out at 108 and got white, and green `#3CB043` at
  128.9 and got black - both the reverse of what the user wants, and
  that green tipped on 0.9 of a point. His wish cannot be written as a
  brightness rule either: the threshold would have to lie below 108 and
  above 129 at the same time. Nor is it about brightness - green is the
  active colour and has to light up, red is the crowd colour and has to
  gain weight against a dark background. Hence a fixed table for the
  four standard colours, with the brightness rule as a fallback for a
  colour the user picks himself. The four `outline_*` settings are
  cleared once (marker `outline_reset`), because a filled-in value
  beats the table and would keep the old picture alive.
- **B512 - what has been answered goes away with its subject.** 1.5.11f
  has run over eighteen projects: 1 ms before, 1 ms after, gain +0 ms.
  Thirteen of those eighteen were already at 0 or 1 ms beforehand -
  there was nothing to repair there, because inside the sentences the
  manual timing is simply the automatic distribution. On the five songs
  where things really were moved by hand inside the sentences the
  button won zero four times and lost 14 ms once. The refit button of
  B497 is out with that, along with `pipeline.refit_syllables`,
  `_refit_syllables` in the editor, `refit_trial`/`_syllable_error` in
  the test panel and the matching translation keys. Where c, d and e
  are switched off and kept, this one went with its subject: a trial
  that no longer has its own object of measurement can only repeat its
  answer. That answer stands here. 1.5.11c (the window trial) has been
  removed for the same reason, along with
  `_project_with_the_biggest_gap`, which only it used.

What the critical re-read found this round (two readers, both on a
running reproduction instead of reading only) - and it is worth the
trouble because the heaviest find was NOT in the new code:

- **The likely cause of the drift at "Lied R" itself.**
  `set_word_pins` wrote only the marker `layout`, not `lyrics_layout`.
  That second one is the only thing holding `migrate_lyric_pins` back,
  so after EVERY save in the link editor the B417 conversion ran again
  over keys that had already been converted. Measured on a text with a
  hyphen in it: a pin on "hey" walked to "het" and then to "nu", two
  words per save, stacking up. That bug is older than B506, and B506
  would have frozen it into the description.
- The line number in a pin description was the RAW file line number, so
  inserting one blank line renumbered the whole rest of the song while
  no word moved - and threw away every pin after it. It now counts the
  lines that have words.
- Three occurrences of "na" that had all shifted a little collapsed
  onto one found word when looked up again; slots are now reserved.
- A pin that could not be described stayed in the numbers and
  disappeared uncounted at the next round.
- `sanitize_timing`, `repair_line_edges` and `enforce_monotonic` pushed
  a bg line's own time straight back out again - precisely the overlap
  that B510 explicitly allows. All three now exempt bg.
- In the editor a bg line had become a wall: `_without_overlap`,
  `_keep_in_order` and `_reenable_fit` skipped `disabled` but not `bg`,
  so the editor refused what the check calls correct.
- `_reworded`, `carry_over` and `sync_timing_with_text_change` dropped
  the bg flag on a text change.
- Re-enabling a line also shortens the NEIGHBOURS, and those boxes were
  left behind - exactly the drift B508 takes away.
- The clamping order in `_move_original` let a mirrored crowd or
  disabled neighbour count, so that a drag to the right jumped left and
  then stuck.
- A click on a bg box fell through to the cell three positions further
  along (same row), after which "line on/off" hit the wrong line.
- The outline wiper did run more than once: the marker only reaches the
  file through `save_config`, and there are runs that never save. It
  now writes back immediately.

Included in v0.145.0:

- **B499 - the marker "restore from original" sat on the wrong text.**
  I coloured the KARAOKE sentence blue and put `[origineel]` in front
  of it; that hid exactly the text the user is working on. The marker
  belongs to the ORIGINAL that is being restored, so it now sits on the
  box in the original track, with the text plainly readable. Second
  half: a fragment that is moved or stretched in 1.4 did not survive -
  `set_restore_fragments` filtered derived boxes out and at the next
  pass it was derived from the timing again. Such a move is now stored
  per line number (`restore_moved`), and that is at once what the user
  asked for: if the fragment no longer lies on the sentence, that
  sentence gets a blue dotted border, and another click on "Terug uit
  origineel" puts it back on the sentence. Only the click after that
  turns the marker off - that is the right order, because undoing a
  move is the smaller step. Mind the trap that was in here: recognising
  a move compares against the BARE derivation (`apply_moves=False`);
  against the derivation WITH the move it would say after one save that
  nothing had been moved.
  On the user's question whether this touches the timing: no.
  `apply_manual_damping` only writes the damping and restore data, the
  edited wav file is sample-exactly the same length (damping multiplies
  by an envelope, restoring copies and clamps to the length), and the
  anchoring is computed on the UNEDITED karaoke. So nothing is ever
  anchored again.
- **B500 - the logic did not run at the end, and never looked between
  the lines.** The user's proposal ("the logic step once more at the
  end") touched a bigger hole than he thought. First: there is a
  cleanup halfway through generating (`sanitize_timing`), but after
  that the energy word timing, the phonetic distribution and the
  holding still shift everything - and what comes out of that went into
  the editor and the render unchecked. There is now a closing check on
  it, which says how many lines it straightened out. Second, and worse:
  `timing_checks` looked exclusively WITHIN one sentence - order, too
  short, zero length, stacked and overlapping syllables. There was no
  check at all between the lines: no overlap between line k and k+1, no
  line of zero length, no order of lines. Exactly what you see in the
  editor and in the picture was measured by nothing. Those checks are
  there now (`line_checks`), with the exceptions that belong: a crowd
  line may lie over its neighbours (a shout sounds at the same time as
  the singing, B346) and a disabled line does not count.
- **B501 - cross-fading at the intro and the outro.** The intro fades
  over to the text picture in its last half second and the outro fades
  in from the text in its first second, in whatever colours stand at
  that moment. For that `_compose_frame` has been pulled apart into
  `_title_frame` and `_text_frame`; at the two boundary moments both
  are built and laid over each other with `Image.blend`. That costs
  about 75 extra frames per video, so the render time notices nothing.
  The credit line now follows `outro_start` instead of `first_text`,
  otherwise it dropped out during the fade.
- **B502/B503 - a run without a link looks like a hallucination.** The
  user pointed at a stretch of transcription where not one word was
  linked and said: this needs a filter on it. The existing filter could
  not see that: it works per segment and all-or-nothing, it skips
  segments of one word (it demands at least two content words), and it
  weighs with `max()` - one word that happens to score above 0.65 saves
  the whole segment. His signal is better than mine, and it can only be
  measured AFTER the linking: a run of four or more found words in a
  row without a single link. By definition that cannot touch a linked
  word. Deliberately a mark and not a removal: in a song with a passage
  in another language (Lied R) such a run is real singing, and then you
  have to be able to link it by hand. Besides that, the track with
  found words carried no colour codes at all - only "filtered" - while
  the lyrics track had five. That table now applies to both.
- **B504 - what the button of B497 is worth.** The user's idea of
  making a measurement for it, worked out: take the projects that have
  both manual and automatic timing, give every automatic line the
  SENTENCE BOUNDARIES of the manual timing - that is the situation the
  button was made for, replayed - and measure the error on the syllable
  boundaries against that manual timing, before and after the refit.
  The difference is exactly what the button yields, and the manual
  timing is the yardstick there instead of the subject. Only runs where
  the manual timing belongs to the current text (equal line count);
  otherwise every number is noise.
- **B505 - the line shift reckoned with one stack while there are
  two.** Since B473 the lines stack at their real height, and the
  smooth shift let every line move "to the place of the slot below it"
  - but both places came from the NEW stack, while the movement should
  start from the OLD one. During those 0.35 s the distance between two
  drawn lines was therefore a mixture of two stacks, and with a wrapped
  sentence above a single sentence that mixture was smaller than the
  height of the top one - and then the second picture row ran through
  the sentence below it. Two stacks are now computed and interpolated
  between.

What the critical re-read turned up:

- `line_checks` also remembered a crowd or disabled line as "the
  previous one", so the last ordinary sentence was forgotten and an
  overlap with such a line in between was never seen. Such lines are
  now skipped entirely - for the order and zero checks too, because a
  disabled leftover line on an old time put the line after it falsely
  in the list.
- The closing check used `enforce_monotonic`, and that pushes a line
  forward as soon as its predecessor runs on. A line START is often
  measured - set on the vocal onset (B333/B357) - and pushing it
  forward puts the sentence beside the singing AND squeezes it
  together. Measured: a line at 13.0-15.0 became 14.0-15.0. The closing
  check is now a `repair_line_edges` of its own that repairs only real
  defects, never moves a start, and takes an overlap off the END of the
  previous line - the least reliable side of a sentence, exactly what
  B224 already trims.
- The diagnostics file was written before that closing check, so it
  described something other than what ended up in `timing.json`. And
  `mark_held` no longer stood last, while that judgement is about the
  final spans. Both put right.
- The marker was invisible for a whole `[bg]` line: it is not in the
  linking, so it has no box in the original track, and the karaoke
  track had just been "left alone". The karaoke sentence keeps its text
  and colour but does get a blue border - then you can see THAT it is
  marked without the text underneath disappearing.
- A restored crowd sentence could not be told apart from "the fragment
  no longer lies on it": both dotted. Crowd is dashed now, moved is
  dotted.
- 1.5.11f also measured projects without manual timing.
  `generate_timing` writes the same content to `timing.json` AND
  `timing_auto.json`, so "both present" says nothing; with such a
  project the error beforehand is zero everywhere and the refit can
  only lose. Those are skipped, and if the whole trial yields no number
  at all, that is a skip and not a trial that ran.
- A filtered word counted towards the suspect run and lost its own
  mark, which effectively put the threshold at one word. And a word you
  take out of the filter or link by hand went on looking filtered; that
  status is now updated.
- If the timing could not be read, 1.4 showed no sentence boxes and
  saving silently wiped ALL markers. That now happens only when the
  derivation really succeeded.

Still open:

- **B495 on Korean.** Try Whisper with the language set to Korean on
  both "Lied R" (phonetic in Latin letters) and "Lied_R2" (real
  characters), and see whether that fills the gaps Whisper-English
  leaves open. That is a measurement on the user's machine. The
  recognition itself is finished (v0.144.0) and tested on real Hangul;
  what is missing is the outcome of the trial.
- **Pauses within a sentence.** Lied_Q and "Lied K
  ": B492/B493 have dealt with the cause, but whether that is good
  enough in practice still has to show.
- **A non-contiguous manual link scrambles the found row.** If you link
  a lyrics word by hand to found words 1, 2 and 4, `_relayout` skips
  found word 3 and that only gets a column in the safety net, far to
  the right. Measured: `top_col` became `[0, 1, 2, 7, 3]`. With the
  links the automation makes it does not happen (0 of 4000 random
  layouts), only by hand. Older than B513 and not caused by it.
- **An original without a karaoke line cannot be switched off.** Since
  B509 almost every original sentence has a counterpart and switching
  off works on the pair. If a sentence is left that is linked to
  nothing, there is no second one to switch off with it and it has no
  off state of its own; that was deliberately not built because it
  would cost a whole step with its own dependency for a case that no
  longer occurs on the reference collection.
