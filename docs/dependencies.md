# What carries through to what

Everything this tool makes comes, through a chain of intermediate steps,
from four source files: the original, the karaoke version, the lyrics and
the karaoke text. If something near the start of such a chain changes,
almost nothing after it is still right.

This file is the readable side of `modules/dependencies.py`, where that
chain is laid down as data. **It is generated** by
`tools/write_dependency_doc.py`; change the chain in the module, not
here. One test compares this file with what the generator makes, and a
second checks that every step and every project value the code uses is
really in the chain. That way no derivative can exist without somebody
having decided when it goes stale.

## How to read it

Under **From source to derivative** each source file is listed with
everything that follows from it: change that file and the whole list
lapses. Under **Per artefact** you get the reverse: what this thing
itself depends on.

Two couplings are not obvious and explain a lot:

- `karaoke_text.txt` also steers the **word coupling of the lyrics**,
  through the filler-word priority, and therefore the line times. Your
  parody text helps decide which original words get coupled.
- `lyrics.txt` sits in the cache key of Whisper (as the initial
  prompt). Changing the lyrics can force a full re-transcription.

What deliberately does NOT carry through matters just as much, because
throwing away too much costs hand work. Changing the parody text leaves
the transcription and the manual word couplings alone; a fresh karaoke
transcription (leftover vocals) costs no hand work on the original; a
different logo only makes the video old. And the rendered video itself
is never thrown away - it costs minutes, and the user decides for
himself when to render again.

## From source to derivative


### `input:original` — input/origineel.* (the original recording)

Change this and 37 derivatives lapse.

- Steps: `align`, `analysis_karaoke`, `analysis_original`, `clusters_karaoke`, `clusters_original`, `coupling`, `heard_again`, `karaoke`, `lyrics`, `original_restore_resample`, `source_original`, `timing`, `transcript_override`, `whisper_karaoke`, `whisper_original`, `word_coupling`
- Project values: `karaoke_from_original`, `vocal_end_s`, `vocal_onset_s`
- Files: `cache:demucs_original`, `cache:karaoke_edited`, `cache:karaoke_generated`, `cache:original_for_restore`, `cache:original_vocals`, `cache:original_wav`, `cache:transcription_karaoke`, `cache:transcription_original`, `output:alignment_json`, `output:analysis_karaoke`, `output:analysis_original`, `output:clusters_karaoke`, `output:clusters_original`, `output:demucs_mp3`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `input:karaoke` — input/karaoke.* (the karaoke version)

Change this and 25 derivatives lapse.

- Steps: `align`, `analysis_karaoke`, `clusters_karaoke`, `coupling`, `fragment_exclusions`, `karaoke`, `original_restore_resample`, `restore_fragments`, `restore_lines`, `restore_moved`, `source_karaoke`, `timing`, `whisper_karaoke`
- Project values: `karaoke_from_original`
- Files: `cache:demucs_karaoke`, `cache:karaoke_edited`, `cache:karaoke_wav`, `cache:original_for_restore`, `cache:transcription_karaoke`, `output:alignment_json`, `output:analysis_karaoke`, `output:clusters_karaoke`, `output:karaoke_edit`, `output:timing`, `output:timing_diagnostics`


### `input:lyrics` — input/lyrics.txt

Change this and 23 derivatives lapse.

- Steps: `analysis_original`, `clusters_original`, `coupling`, `heard_again`, `karaoke`, `lyrics`, `lyrics_override`, `original_overrides`, `source_lyrics`, `stress_anchors`, `timing`, `transcript_override`, `whisper_original`, `word_coupling`
- Project values: `language_choice`
- Files: `cache:karaoke_edited`, `cache:transcription_original`, `output:analysis_original`, `output:clusters_original`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `input:karaoke_text` — input/karaoke_text.txt

Change this and 7 derivatives lapse.

- Steps: `coupling`, `source_karaoke_text`, `stress_anchors`, `timing`
- Files: `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `input:logo` — input/logo.* (the logo shown in the video)

Change this and 1 derivatives lapse.

- Steps: `source_logo`


### `config:whisper` — setting: Whisper model and language

Change this and 24 derivatives lapse.

- Steps: `analysis_karaoke`, `analysis_original`, `clusters_karaoke`, `clusters_original`, `coupling`, `heard_again`, `karaoke`, `lyrics`, `timing`, `transcript_override`, `whisper_karaoke`, `whisper_original`, `word_coupling`
- Files: `cache:karaoke_edited`, `cache:transcription_karaoke`, `cache:transcription_original`, `output:analysis_karaoke`, `output:analysis_original`, `output:clusters_karaoke`, `output:clusters_original`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `config:forced_alignment` — setting: more precise word times (wav2vec2)

Change this and 24 derivatives lapse.

- Steps: `analysis_karaoke`, `analysis_original`, `clusters_karaoke`, `clusters_original`, `coupling`, `heard_again`, `karaoke`, `lyrics`, `timing`, `transcript_override`, `whisper_karaoke`, `whisper_original`, `word_coupling`
- Files: `cache:karaoke_edited`, `cache:transcription_karaoke`, `cache:transcription_original`, `output:analysis_karaoke`, `output:analysis_original`, `output:clusters_karaoke`, `output:clusters_original`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `config:chunked` — setting: transcription in chunks (fills the gaps)

Change this and 18 derivatives lapse.

- Steps: `analysis_original`, `clusters_original`, `coupling`, `heard_again`, `karaoke`, `lyrics`, `timing`, `transcript_override`, `whisper_original`, `word_coupling`
- Files: `cache:karaoke_edited`, `cache:transcription_original`, `output:analysis_original`, `output:clusters_original`, `output:karaoke_edit`, `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


### `config:analysis` — setting: analysis thresholds

Change this and 4 derivatives lapse.

- Steps: `analysis_karaoke`, `analysis_original`
- Files: `output:analysis_karaoke`, `output:analysis_original`


### `config:cluster` — setting: cluster thresholds

Change this and 8 derivatives lapse.

- Steps: `clusters_karaoke`, `clusters_original`, `karaoke`, `lyrics`
- Files: `cache:karaoke_edited`, `output:clusters_karaoke`, `output:clusters_original`, `output:karaoke_edit`


### `config:align` — setting: alignment

Change this and 9 derivatives lapse.

- Steps: `align`, `coupling`, `karaoke`, `timing`
- Files: `cache:karaoke_edited`, `output:alignment_json`, `output:karaoke_edit`, `output:timing`, `output:timing_diagnostics`


### `config:karaoke` — setting: damping (gain, fades)

Change this and 3 derivatives lapse.

- Steps: `karaoke`
- Files: `cache:karaoke_edited`, `output:karaoke_edit`


### `config:timing` — setting: vocal analysis, anchor weights, phonetic timing

Change this and 4 derivatives lapse.

- Steps: `coupling`, `timing`
- Files: `output:timing`, `output:timing_diagnostics`


### `config:video` — setting: video (colours, fonts)

Change this and 0 derivatives lapse.


### `config:models` — setting: which models are switched on

Change this and 7 derivatives lapse.

- Steps: `coupling`, `lyrics`, `timing`, `word_coupling`
- Files: `output:lyrics_alignment`, `output:timing`, `output:timing_diagnostics`


## Per artefact

| Artefact | Kind | What it is | Derived from |
|---|---|---|---|
| `input:original` | source | input/origineel.* (the original recording) | *(source)* |
| `input:karaoke` | source | input/karaoke.* (the karaoke version) | *(source)* |
| `input:lyrics` | source | input/lyrics.txt | *(source)* |
| `input:karaoke_text` | source | input/karaoke_text.txt | *(source)* |
| `input:logo` | source | input/logo.* (the logo shown in the video) | *(source)* |
| `config:whisper` | source | setting: Whisper model and language | *(source)* |
| `config:forced_alignment` | source | setting: more precise word times (wav2vec2) | *(source)* |
| `config:chunked` | source | setting: transcription in chunks (fills the gaps) | *(source)* |
| `config:analysis` | source | setting: analysis thresholds | *(source)* |
| `config:cluster` | source | setting: cluster thresholds | *(source)* |
| `config:align` | source | setting: alignment | *(source)* |
| `config:karaoke` | source | setting: damping (gain, fades) | *(source)* |
| `config:timing` | source | setting: vocal analysis, anchor weights, phonetic timing | *(source)* |
| `config:video` | source | setting: video (colours, fonts) | *(source)* |
| `config:models` | source | setting: which models are switched on | *(source)* |
| `source_original` | step | sha1 + wav path of the prepared original | `input:original` |
| `source_karaoke` | step | sha1 + wav path of the prepared karaoke | `input:karaoke` |
| `source_lyrics` | step | sha1 of lyrics.txt as the program knows it | `input:lyrics` |
| `source_karaoke_text` | step | sha1 of karaoke_text.txt as the program knows it | `input:karaoke_text` |
| `source_logo` | step | sha1 of the logo as the program knows it | `input:logo` |
| `config_signature` | step | the settings in use, per group (to notice a change) | *(none — always stays valid)* |
| `cache:original_wav` | file | cache/original.wav | `source_original` |
| `cache:karaoke_wav` | file | cache/karaoke.wav | `source_karaoke` |
| `cache:demucs_original` | file | cache/demucs_stems_original/ (vocals + instrumental) | `cache:original_wav` |
| `cache:demucs_karaoke` | file | cache/demucs_stems_karaoke/ | `cache:karaoke_wav` |
| `cache:original_vocals` | file | cache/original_vocals.wav (vocals for the energy analysis) | `cache:demucs_original` |
| `cache:karaoke_generated` | file | cache/karaoke_generated.wav (instrumental from the original) | `cache:demucs_original` |
| `output:demucs_mp3` | file | output/karaoke_demucs.mp3 and vocal_demucs.mp3 | `cache:demucs_original` |
| `vocal_onset_s` | project value | where the singing starts (anchor for the first line) | `cache:demucs_original` |
| `vocal_end_s` | project value | where the singing stops (anchor for the tail, B319) | `cache:demucs_original` |
| `karaoke_from_original` | project value | whether the karaoke was made from the original (skips alignment) | `input:original`, `input:karaoke` |
| `language_choice` | project value | the language pinned by hand | `input:lyrics` |
| `whisper_original` | step | transcription of the original (sha1, model, language, prompt) | `cache:demucs_original`, `cache:original_wav`, `input:lyrics`, `config:whisper`, `config:forced_alignment`, `config:chunked` |
| `whisper_karaoke` | step | transcription of the karaoke (leftover vocals) | `cache:karaoke_wav`, `config:whisper`, `config:forced_alignment`, `karaoke_from_original` |
| `cache:transcription_original` | file | cache/transcription_original.json | `whisper_original` |
| `cache:transcription_karaoke` | file | cache/transcription_karaoke.json | `whisper_karaoke` |
| `transcript_override` | step | the cut and merged transcription (hand work) | `whisper_original` |
| `lyrics_override` | step | the cut and merged lyric words (hand work) | `input:lyrics` |
| `word_coupling` | step | manual word couplings (lyric word -> detected word) | `whisper_original`, `transcript_override`, `lyrics_override`, `input:lyrics`, `config:models` |
| `heard_again` | step | stretches heard again or aligned from the coupling editor | `whisper_original` |
| `original_overrides` | step | hand-corrected line times of the original | `input:lyrics`, `lyrics_override` |
| `stress_anchors` | step | hand-coupled pieces of original <-> karaoke, per line | `input:lyrics`, `input:karaoke_text`, `lyrics_override` |
| `analysis_original` | step | analysis figures for the original transcription | `whisper_original`, `config:analysis`, `heard_again` |
| `output:analysis_original` | file | output/original/statistics.json and the csv reports | `analysis_original` |
| `analysis_karaoke` | step | analysis figures for the karaoke transcription | `whisper_karaoke`, `config:analysis` |
| `output:analysis_karaoke` | file | output/karaoke/statistics.json and the csv reports | `analysis_karaoke` |
| `clusters_original` | step | the chosen sound clusters of the original | `whisper_original`, `config:cluster`, `input:lyrics`, `lyrics_override` |
| `clusters_karaoke` | step | the chosen sound clusters of the karaoke (leftover vocals) | `whisper_karaoke`, `config:cluster` |
| `output:clusters_original` | file | output/original/clusters.json and clusters.html | `clusters_original` |
| `output:clusters_karaoke` | file | output/karaoke/clusters.json and clusters.html | `clusters_karaoke` |
| `output:lyrics_alignment` | file | output/original/lyrics_alignment.txt | `word_coupling`, `heard_again`, `input:karaoke_text` |
| `align` | step | the offset regions between original and karaoke | `cache:original_wav`, `cache:karaoke_wav`, `config:align`, `karaoke_from_original` |
| `output:alignment_json` | file | output/alignment.json (report) | `align` |
| `coupling` | step | original lines with times + which karaoke line goes with which | `word_coupling`, `heard_again`, `align`, `input:lyrics`, `input:karaoke_text`, `lyrics_override`, `transcript_override`, `original_overrides`, `config:timing`, `config:models` |
| `lyrics` | step | how many extra damping fragments come from the lyrics | `clusters_original`, `word_coupling`, `heard_again` |
| `timing` | step | the line and syllable timing for the video | `coupling`, `input:karaoke_text`, `vocal_onset_s`, `align`, `cache:original_vocals`, `language_choice`, `config:timing`, `config:models` |
| `output:timing` | file | output/settings/timing.json and timing_auto.json | `timing` |
| `output:timing_diagnostics` | file | output/diagnostics/timing_diagnostics.txt | `timing` |
| `fragment_exclusions` | step | unticked damping fragments (times on the karaoke timeline) | `cache:karaoke_wav` |
| `restore_fragments` | step | 'back from the original' fragments (karaoke timeline) | `cache:karaoke_wav` |
| `restore_lines` | step | lines fetched back from the original (line numbers) | `cache:karaoke_wav` |
| `restore_moved` | step | moved 'back from the original' pieces (per line number) | `restore_lines` |
| `original_restore_resample` | step | sha1 + sample rate of the reused original | `input:original`, `cache:karaoke_wav` |
| `cache:original_for_restore` | file | cache/original_for_restore.wav | `original_restore_resample` |
| `karaoke` | step | the edited karaoke (which fragments are damped) | `cache:karaoke_wav`, `clusters_original`, `clusters_karaoke`, `fragment_exclusions`, `restore_fragments`, `restore_lines`, `restore_moved`, `align`, `config:karaoke` |
| `cache:karaoke_edited` | file | cache/karaoke_edited.wav | `karaoke` |
| `output:karaoke_edit` | file | output/karaoke_edit.mp3 and karaoke_edit.wav | `karaoke` |
| `display_name` | project value | the readable project name | *(none — always stays valid)* |
| `input_names` | project value | where the input files came from (for the file chooser) | *(none — always stays valid)* |
| `input_last_dir` | project value | the last folder used in this project, whatever the input (B413) | *(none — always stays valid)* |
| `video_titles` | project value | artist/title to show in the video | *(none — always stays valid)* |
| `video` | step | the rendered video (path + audio source used) | *(none — always stays valid)* |
