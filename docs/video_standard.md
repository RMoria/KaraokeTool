# Karaoke video standard procedure (v1) - RoodWitte Zangers

Fixed standard for all TVX karaoke videos. Video production stands
apart from the audio analysis/karaoke editing, but uses the same
project data (offset, lyrics, karaoke lyrics).

## Order of work

1. **Finish the lyrics completely first.** Write the full text, and
   only then the timing. Never adjust timing while the text is still
   changing; after that, treat the text as "provisionally final".
2. **Analyse the audio**: official recording + karaoke version.
   Waveform, vocal entries, instrumental cues, differences. Look for a
   fixed offset; do not assume the same time difference everywhere.
3. **Section anchors**: every large section (intro, verse 1, build-up,
   chorus, crowd, verse 2, ...) gets its own, fully independent anchor.
   Never derive later timing from earlier timing; no stacked timing
   patches.
4. **Analyse the singing** for syllables, word stress, long notes,
   breathing points, natural pronunciation. When in doubt: check
   against the official vocals and the karaoke.
5. **Timing per syllable** (not per word): every syllable gets a start
   time and an end/hold time. The colour changes exactly on the entry.
6. **Long syllables**: underlining through a separate render option (no
   stretched letters). Example: `Groe̲n`, `Éé̲n`, `Laa̲t`.
7. **Crowd cues** (`La-la-la...`, `Hey...`, `Ho...`) are handled
   separately: white -> red -> grey. No green.
8. **Colour progression** for normal singing: white -> green (on the
   vocal entry) -> grey.
9. **Logical lines of text**: always complete sentences, never broken
   up arbitrarily. Show line 2 in advance while line 1 is being sung.
10. **Intro**: logo only, no text, at least 5 seconds.
11. **First text**: the first line appears 5 s before the first vocals.
12. **Outro**: leave the last line up for at least 3 s, then logo +
    song title for at least 5 s (as in Zangers Paradijs). Music too
    short? Add silent video time.
13. **Render architecture**: lyrics, timing, colour rules and rendering
    are four separate parts. Never put timing in the render code. The
    renderer is generic, without song-specific exceptions: per song you
    only replace the logo, the audio and the timing file.
14. **First render**: make a full render first, and only then check the
    vocals, fine-tune the timing and correct syllable shifts.
15. **Final format**: video H.264 + yuv420p, audio AAC
    (Windows-compatible).

## How the text is built up on screen

- Intro: logo only, calm, >= 5 s.
- During the singing, never more than two lines:
  - **Line 1** (active): white -> green per syllable -> grey.
  - **Line 2** (next logical sentence): shown in advance, all white.
  - Line 1 done -> line 2 moves up, a new line comes in at the bottom.
- Lines appear ~5 s before the vocals and stay up for ~3 s.
- Crowd: the active line goes white -> red -> grey; the next line waits
  in white.
- Outro: last line >= 3 s, then logo + song title >= 5 s.

Layout:

    ────────────────────────────
               (logo)

    Active line     (white -> green -> grey)
    Next line       (white)
    ────────────────────────────

## Notation of the karaoke lyrics

- One logical sentence per line (never broken up arbitrarily).
- Empty lines separate sections.
- `# comment` (e.g. `# Intro`, `# Couplet 2`): not sung, not shown.
- Crowd parts go between block markers (or inline in the middle of a
  line: `[crowd]Waertje![/crowd]` becomes a crowd line of its own);
  those are coloured white -> red -> grey:

      [crowd]
      La-la-la...
      Hey...
      [/crowd]

## Required input (do not render until everything is there)

- the original lyrics
- the karaoke lyrics (e.g. Per_Spoor_RoodWitte_Zangers_Werkversie.txt)
- timing information at syllable level
- offset original/karaoke (from step 3 of the audio pipeline)
- logo (chosen through the browse button, copied to input\logo.<ext>)
- song title; when the title is known, input and output each get a
  subfolder named after the song title in which all available files are
  placed, and that subfolder is then used throughout the whole program
  (one project folder per song; the main folders stay ready for the
  next use)

If something is missing, the program reports what is missing and does
not start the render.

## Implementation status (v0.25: 3 lines, crowd extra, logo+title intro/outro, mp4 opens after rendering)

Working since v0.15: `modules/timing.py` (syllables, timing.json) and
`modules/video.py` (generic renderer). Video resolution/fps/font in
`config.json` under `video`. Output: `output/<song>/karaoke_video.mp4`,
using the edited karaoke (`karaoke_edit`) when it exists, otherwise the
bare karaoke. Order of work: "2.2. Refine timing" links the karaoke
lyrics structurally to the original lyrics at section level (block by
block: chorus onto chorus, verse onto verse), with interpolation for
choruses that Whisper garbled. The colour shows the confidence of the
link (green=high, yellow=medium, red=low). Without the original lyrics
it is a best effort (through the lyrics alignment: syllable -> word ->
sentence level; otherwise spread out evenly), after which you make a
first render and fine-tune it with "2.3. Edit timing (waveform)":
waveforms of both the original and the karaoke with zoom, playback of
both sources (the offset is accounted for), one continuous playback
line across all tracks (click in the waveform to play from there),
moving lines (drag the middle) or stretching them (drag an edge)
whereby the start of the line snaps to the playback line, and saving
writes `timing.json`. If the original lyrics are present, the editor
shows the original sentences as a track of their own below the original
waveform (linked to the karaoke sentences at sentence level); the
original sentence is easy to line up against the original music, and
moving or stretching it moves the linked karaoke sentence(s) along with
it relatively.
