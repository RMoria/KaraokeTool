# KaraokeTool Manual

A short guide to the workflow, the text notation, the editors and the
choices on offer. For the technical state of affairs see
`docs/development_log.md`; for what falls away when you replace
something near the start of the chain see `docs/dependencies.md`.

The buttons carry a double number: the first digit is the tab, the
second its position on that tab. "2.2. Timing verfijnen" is therefore
the second button on tab 2 (Karaokevideo).

Note that the interface is Dutch by default, with English as an option,
so the button and tab names quoted below are the ones you actually see
on screen.

## The workflow in brief

The buttons below appear in the same order as in the app. Steps marked
*(optional)* can be skipped; the rest feed each other.

1. **Loading music and analysis** (tab 1)
   - Pick the **origineel** (original, mp3/wav) and the **karaoke**. If
     you have no karaoke track, make one with **"Karaoke uit origineel"**
     (Demucs strips out the vocals; the result also lands in the output
     folder as `karaoke_demucs.mp3`).
   - Put the **songtekst** (`songtekst.txt`), the **karaoketekst**
     (`karaoketekst.txt`) and optionally a **logo** in place on this tab.
     The original lyrics drive the language detection and the linking;
     the karaoke lyrics and the logo are what go into the video. Behind
     each file you see the name it had on your machine, not the internal
     name.
   - **1.1. Detecteer woorden** (detect words) → transcribes with
     Whisper. If Demucs is available this runs on the isolated vocal
     track, which makes the words and their timings far more reliable.
     This step also determines the offset between original and karaoke.
   - **1.2. Woorden koppelen** (link words) → links the transcribed
     words of the **original** to the **songtekst** (correctable by
     hand). Both rows therefore show text from the original, not the
     karaoke; the karaoke only appears at "2.2. Timing verfijnen" and in
     the waveform editor.
   - **1.3. Analyse** → sound clusters (for damping leftover vocals). It
     also produces an HTML report ("HTML-rapport openen") in which you
     can see the findings per cluster side by side.
   - **1.4. Karaoke aanpassen** (adjust karaoke) *(optional)* → damps
     the ticked clusters and exports `karaoke_edit`. Only needed when
     leftover vocals from the original bleed into the karaoke and you
     want to soften them. Afterwards a list of **gedempte fragmenten**
     (damped fragments) replaces the cluster list: clearing a tick
     immediately reapplies the damping.
   - **1.5. Test** *(temporary)* → opens a checklist of ten numbered
     investigations (1.5.1 through 1.5.10): restoring the cache, the
     calibration-set status, the project check (lyrics, filters and
     structure in one), missing repeats, the yardstick, unique versus
     repeated lines, the word and syllable checks, the Whisper window
     test, the omission trial and the big trial. That last one pits all
     the models against each other — on their own, in every pair and in
     reverse order, at block, sentence, link and word level — and takes
     about half an hour; it writes as it goes to `docs/modelmatrix.md`,
     so aborting only costs you the variant it is working on. Ten is the
     maximum: if something is added, small tests get merged.

     At the top there is **Alles aanvinken** (tick everything; clicking
     again clears them all) and a **Opnieuw meten** (measure again)
     checkbox. You rarely need that last one: what has already been
     measured is tracked per action, project and version, so a project
     that has not changed since the previous run is skipped, and the
     yardstick puts its figures next to those of the three previous
     versions. Change a lyric, a timing or a model setting and that
     counts as new data, so it is measured again by itself. Start is at
     the bottom; the ticks are always cleared when the window opens, so
     you can never kick off a long measurement by accident. The two
     radio buttons underneath choose whether the measurements cover all
     projects or only the one currently open. Stop works here too. Each
     test drops its result into the log window as soon as it finishes,
     so you do not have to wait for the rest.

     An investigation that takes longer than half an hour does not
     appear in this list but under **1.5.11 Zware proeven** (heavy
     trials) — the overnight jobs. That group never joins in with "Alles
     aanvinken", and when nothing is listed under it, it is not visible
     at all. Each investigation there skips itself until it is twenty
     versions old.

     This button exists so that research can be done on your own
     machine, and it will disappear again.

2. **Karaokevideo** (tab 2)
   - **2.1. Klemtoon bewerken** (edit stress) *(optional)* → every word
     automatically gets its stress on the first syllable; here you
     correct that where needed. Mind the order: this button needs a
     `timing.json`, so run "2.2. Timing verfijnen" first.
   - **2.2. Timing verfijnen** (refine timing) → produces the timing at
     syllable level, tied to the songtekst.
   - **2.3. Timing bewerken (golfvorm)** (edit timing on the waveform) →
     fine-tuning: shift and stretch lines, with original and karaoke
     shown one above the other.
   - **2.4. Video maken** (make video) → renders the karaoke video. In
     the window that opens you choose both the **text** (timed karaoke
     lyrics or timed original lyrics) and the **music**.

Order matters: a later step uses the output of an earlier one. If that
output is missing, the button tells you which step has to be run (again)
first. Replace an input file and the derived results are discarded and
the steps have to be redone — see "What affects what".

While a step is running its button turns yellow. **Stop** aborts the
running step; that button never turns yellow itself, because it starts
nothing.

## Text notation (karaoketekst.txt)

- **One logical sentence per line.** Never break lines arbitrarily.
- **Blank line** = section break (block).
- `# commentaar` (e.g. `# Intro`, `# Couplet 2`): not sung, not shown.
- **Crowd** (the audience sings along): colours white → red → grey.
  - As a block:

        [crowd]
        La-la-la...
        Hey...
        [/crowd]

  - Inline (mid-sentence): `G Z R, G Z R [crowd]Waertje![/crowd]`
    remains one sentence; only that fragment ("Waertje!") turns red in
    the video, the rest stays green. A `[pause]` in front of it keeps
    the ordinary colour.
  - A line that is entirely `[crowd]...[/crowd]` counts as a normal line
    in the sentence linking as soon as the number of karaoke lines in
    the block (crowd included) exactly matches the number of songtekst
    lines — it then links one-to-one to its songtekst counterpart (say,
    a parody chorus in the place of "Met bloed, zweet en tranen"). If
    the counts do not match, it falls back to a short "shout" slot after
    the previous sentence and, for orientation, is mirrored into the
    original-lyrics track in the waveform editor (2.3. Timing bewerken
    (golfvorm)) with a dotted red border and the label "[crowd]", so it
    stays clear that this is not real original text.
- **Simultaneous backing vocals** (`[bg]...[/bg]`): for a second voice
  that sounds *at the same time* as the previous line — a backing vocal
  singing "Tonight, tonight" while the lead vocal carries on, often
  written in brackets in the lyrics, e.g. "Sunday, Bloody Sunday
  (Tonight, tonight)". Works in `songtekst.txt` (original) as well as in
  `karaoketekst.txt` (karaoke), independently of each other — you can
  use it in one file without the other.
  - As a block:

        [bg]
        Tonight, tonight
        [/bg]

  - Or attached to a single line: `[bg]Tonight, tonight[/bg]`.
  - A `[bg]` line gets no slot of its own in the sentence linking (it
    does not count towards the number of lines per block) but takes the
    same time slot as the preceding line, and by default it is neither
    shown in "2.2. Timing verfijnen" nor rendered (just like a disabled
    line) — the text does help Whisper's recognition and the
    hallucination check. If you do want it shown or rendered, switch
    that on per line in the timing editor.
- **`[pause]`** (or `[pauze]`): marks a sung pause inside a single
  logical sentence, e.g. `Want as de zangers [pause] weer gaan hossen`.
  The sentence stays one whole in the render, but for placement and
  timing it counts as two parts with a slot of its own for the pause. At
  that point in the video, dots appear that light up one by one during
  the pause (on the average beat). Works inside a `[crowd]` block too.
- **Stress** *(optional; button "2.1. Klemtoon bewerken" on the video
  tab)*: every word automatically gets its stress on the first syllable.
  If that is wrong (ko-MEN instead of KO-men, say), click the right
  syllable; click the marked one again to remove the stress. The
  stressed syllable gets a subtle accent in the video. Skip this step
  and the automatic stress applies throughout.

## The editors

Four windows do the handwork. They look alike, but they **treat closing
differently** — that is the first thing to remember:

| Window | "Sluiten" (close, and Esc) |
| --- | --- |
| 1.2. Woorden koppelen | saves |
| 2.1. Klemtoon bewerken | saves |
| 2.3. Timing bewerken (golfvorm) | discards unsaved work |
| Demping bewerken | discards unsaved work |

### 1.2. Woorden koppelen

The words Whisper heard are on top, the songtekst underneath. Click a
word above and one below to link them; click a line to remove it. Click
the same word again to drop the selection. If a word sits inside a
merged block, your click lands on the word you are actually pointing at
(the dotted lines within the block show the word boundaries) and a click
on the link releases the whole group.

The colours are given as a **legenda** (legend) above the rows, with
the rest of the explanation — not as text in front of the words themselves. The line
between two words is green for a high similarity, orange for a middling
one, red for a low one, and **blue when you drew it yourself**. Only
those manual links are kept; the automatic ones are recomputed every
time. A border around a word means:

- **dotted orange** — skipped stop word;
- **dotted pink/red** — no match found;
- **dotted purple** — filtered out as a hallucination;
- **dotted grey-blue** — Whisper heard nothing here (a gap in the
  transcription);
- **dotted blue-green** — not linked, but timed on the vocal track: the
  tool measured its position from the vocal energy.

A **struck-through** word in the top row is a detected word that has
been filtered out. You are free to link it by hand anyway if it turns
out to be right.

Two boxes in the legend are buttons: **"als hallucinatie eruit
gefilterd"** (filtered out as a hallucination) and **"overgeslagen
stopwoord"** (skipped stop word). Select a word and click one of them to
mark it as such yourself — hallucination on the top row (what Whisper
found), stop word on the bottom one (the songtekst). The word joins the
list for the language of this song, so every later song in that language
benefits; clicking again takes it off. The other three markings are
measurements and are there for explanation only.

"Knippen" (cut) splits the selected word in two, "Samenvoegen" (merge)
glues it to its right-hand neighbour. Both work on the top row as well
as the bottom one. Saving invalidates the sentence linking, the timing
and the video; cutting or merging in the songtekst also invalidates the
saved stresses and the manual line timings, because the words get
renumbered.

### 2.1. Klemtoon bewerken

Click the syllable that carries the stress; click the marked one again
to remove it. One stress per word. The original lines sit beside the
karaoke lines, so the stress of the parody can be placed on that of the
original. Saving redistributes the best-effort line duration on the
basis of the stresses.

### 2.3. Timing bewerken (golfvorm)

Five tracks stacked up: the waveform of the **original**, the
**original lyrics**, the waveform of the **karaoke**, the **karaoke
lines** and the **vocal track**. The original and the vocal track are
projected onto the karaoke timeline, so the peaks line up vertically
even when the tempo differs.

- **Clicking in a waveform, on the time bar or in the vocal track** puts
  the playhead there and leaves a permanent grey tick behind to align
  against. Playback keeps running.
- **Dragging in the middle of a block** shifts the line; its start
  **snaps to the playhead** when that is close by.
- **Dragging an edge** (the cursor turns into ↔) stretches or shrinks.
  A line never gets shorter than 0.2 s and never collides with another
  line; crowd lines may overlap, and overlapping a disabled line is
  allowed too.
- Drag an **original sentence** and the karaoke lines linked to it move
  along. It works the other way round as well: a karaoke line that is
  linked one-to-one is mirrored in the original track.
- **Weergave: Blokken / Zinnen / Woorden** (view: blocks / sentences /
  words). In *Blokken* you drag a whole block at once (the lines inside
  scale with it), in *Zinnen* a single line; *Woorden* is for reading
  only, there is no dragging there.
- **Regel uit/aan** (line off/on) disables the selected line (or block,
  or word): it turns grey, gets "[uit]" in front of it and stays out of
  the render. Switching it back on makes room among its neighbours by
  itself.
- **Herstel origineel-timing** (restore original timing) throws away the
  manual corrections on the original track and rebuilds the linking.
  Careful: it resets the karaoke lines too.
- **Opslaan (timing.json)** saves the lines plus only those original
  sentences that changed. **Sluiten does not save.**

### Demping bewerken

Reachable from tab 1 as soon as "1.1. Detecteer woorden" has run. Red
blocks damp a stretch of karaoke; the green blocks
(**"Terug uit origineel"**, bring back from the original) do the
opposite — there the
matching stretch of the original is laid over the karaoke. That is meant
for material Demucs removed while it should have stayed. Click in the
waveform to place the playhead, drag a block or its edge, and
"Verwijderen" (delete) removes the selected block. "Opslaan en
toepassen" (save and apply) applies everything and exports again;
**Sluiten does not save.**

## Which songs work well?

The tool leans on what Whisper makes of the vocal track. A single voice
singing intelligibly gives the best linking. Songs get difficult when a
backing choir sings something *else* at the same time, when there are
many short shouts in a row, or when an outro repeats nearly the same
line six or seven times. Whisper often writes nothing down there, or it
gets stuck and repeats one word dozens of times.

You can spot it in the linking editor: many words with the blue-green
border (timed but not linked) or the pink border (no match), usually
towards the end of the song. The tool does the right thing there — it
places those lines on the vocal energy — but the placement is then an
estimate, and the waveform editor is your tool. In a tail like that the
error can also accumulate: the lines get squeezed against their minimum
duration and push each other forward, which over a long outro can add up
to ten seconds or more. The start and the middle of the song do not
suffer from this — they are usually accurate to a fraction of a second.

When a second voice really does overlap, help it along with `[bg]` (see
Text notation). For a tightly sung song with a single voice you usually
need to do nothing.

## Choices and settings

Settings apply to the whole app (not per project), apart from the titles
and the artist — those belong to the song and live on tab 1.

- **Large models (Demucs / forced alignment):** recommended; without
  them the transcription runs on the full mix and the timing is less
  accurate. They fall back gracefully when absent. Ticking the box
  fetches the model straight away, so the first real run does not have
  to wait.
- **Parallel detection:** original and karaoke at the same time (faster,
  more memory; falls back to one at a time).
- **Zangstem-analyse** (vocal-track analysis, sustained notes and
  filler lines): on by default. It uses the separated vocal track to
  lengthen sustained
  notes, to place "na-na" lines that were not transcribed on their
  energy pulses, to give songtekst words that exact matching skipped a
  timing after all (those get the blue-green border in the linking
  editor), and to put an estimated line start on the vocal onset where
  it belongs. Requires Demucs; otherwise it falls back gracefully.
- **The song's rhythm:** where a song is sung tightly, the tool measures
  for itself how long a line takes (the phrase) and how long a repeated
  sentence ought to be. That way a chorus that comes round four times
  stays the same length everywhere, even in a spot where Whisper did not
  pick up the words. With a loosely timed song the tool notices and
  leaves it alone; there is nothing for you to set.
- **Diagnostics (local only):** writes the transcription history and
  `timing_diagnostiek.txt` to `output/<title>/diagnostiek/`. Handy for
  analysing problems; nothing is sent anywhere.
- **Cache:** "Cache wissen bij opstarten en afsluiten" (clear cache on
  start-up and shutdown) is off by default, and that is deliberate —
  without a transcription in the cache the timing falls back to even
  distribution. "Nu legen" (empty now) clears it once, for **all**
  projects.
- **Output folder:** where the project folders end up; a network
  location (UNC) is allowed too. When you change it, existing projects
  move along and the references are updated; input and cache stay with
  the app.
- **Interface language:** Dutch/English (separate from the audio
  language, which is detected from the songtekst/karaoketekst). Takes
  effect after a restart.
- **Video text colours and font:** the colour before, during and after
  singing, the crowd colour and the video background, plus the font
  (`.ttf` from `assets/fonts`, with a sample line). Beside each text
  colour is the colour of the **outline**: a thin border around the
  letters of the line currently up, so the text stands out against a
  background photo. Leave it empty and the tool picks the contrasting
  colour itself (black under a light letter, white under a dark one).
  "Terug naar standaard" (back to defaults) resets colours, outlines and
  font alike.
- **Background image:** sits under Video-achtergrond and belongs to the
  song. A chosen image is kept in a central collection (next to the
  settings, as `background_001`, `background_002`, ...) and as a copy in
  the project's input folder. When there is anything in that collection
  you see the thumbnails: click one and press **Deze gebruiken** (use
  this one) or double-click it to take it for this project, or press
  **Opgeslagen achtergrond wissen** (delete saved background) to remove
  it from the collection — projects using it keep their own copy.
  **Afbeelding verwijderen** (remove image) takes the background out of
  *this* project; when there is none you see "Geen" (none).
- **Interface colours:** background, buttons, and the colour of a button
  that is busy.
- **Uit origineel terughalen (2.3):** in the timing editor, point out a
  sentence with the **Uit origineel terughalen** (bring back from the
  original) button. That sentence turns blue in both tracks, and at
  **1.4. Karaoke aanpassen** it is waiting as a blue block: at that
  moment the sound of the original is put in place of the karaoke
  one-to-one, with a short fade in and out. Handy for stray shouts that
  have disappeared from the karaoke version. Move the sentence later and
  the stretch of original moves with it.
- **Lettergrepen bijstellen (2.3):** the **Lettergrepen bijstellen**
  (adjust syllables) button redistributes the syllables *within* each
  sentence on the vocal energy, without touching the sentence
  boundaries. Meant for after you have put the sentences themselves in
  place.
- **Open video:** the button next to "2.4. Video maken" looks in the
  output folder of the project that is open, so a video from yesterday
  opens just as easily. When there are several versions it asks which
  one; the newest (highest sequence number) is preselected.
- **Music when rendering:** in the render window you choose the music:
  **Karaoke-muziek** (the audio the alignment and timing were made
  against — whether that is a separate karaoke track or comes from the
  original makes no difference), **Originele muziek** (original music),
  or **Alleen zang** (vocals only). Beside that you choose which **text**
  appears on screen: the karaoke lyrics or the original lyrics.
- **Language (phonetic timing):** the audio language is detected from
  the songtekst. When a language model is missing (French for a French
  song, say), the tool puts one in place itself. Dutch, English and
  French are built in; other languages are created automatically.

## What affects what

Everything comes out of four source files through a chain of
intermediate steps: the original, the karaoke version, the songtekst and
the karaoketekst. Change something at the start of such a chain and
almost everything after it falls away, and the app tells you which steps
have to be redone. The full list is in `docs/dependencies.md`.

Two of the connections are not obvious, and they explain most of the
surprises:

- through the filler-word priority, the **karaoketekst** also steers the
  word linking of the songtekst, and hence the line timings;
- the **songtekst** travels to Whisper as the initial prompt and is
  therefore part of the cache key: replacing the file can force a full
  re-transcription. A correction in the linking editor deliberately does
  *not*.

What does *not* fall away matters just as much: changing the parody
lyrics leaves the transcription and your manual word links untouched, a
different logo only makes the video stale, and the rendered video is
never discarded automatically.

## Using the diagnostics

When the timing goes wrong somewhere, look in
`output/<title>/diagnostiek/timing_diagnostiek.txt`: one line per
sentence with start/end/duration/syllable-count/quality plus automatic
markers (too short, overlap). The top line shows the app version and the
offset used. `transcriptie_<track>.json` keeps a timestamped run per
detection, so it is visible whether and when a step was redone. If a
language was created on the fly, it sits as `<code>.json` (with header
and build version) in the same diagnostics folder, so you can send the
whole folder in one go.
