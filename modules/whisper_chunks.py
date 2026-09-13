"""Let Whisper look again: offsets, chunks, and merging (B390).

Whisper works in windows of thirty seconds and those window edges lie
fixed relative to the start of the audio. Measured over 347 transitions
in fourteen projects, the last word of a segment carries 0.42 confidence
against 0.70 elsewhere, and 34% of them fall below 0.30. That is not a
bad model but a missing right-hand context: a word on a window edge has
nothing after it to lean on.

The obvious second suspect turned out to be a dead end, and that is
worth recording before anyone spends a day on it again. Whisper
conditions on its own previous output by default, so a wrong turn feeds
itself - the textbook explanation for an outro derailing while an intro
does not. But ``condition_on_previous_text=False`` has been set in this
project for a long time, in the app (``modules/whisper.py``) AND in the
probe. The conditioning is already off and the outros derail anyway. So
whatever is wrong at the end of a song, it is not the decoder reciting
itself.

What remains is the window geometry, and the prompt. The initial prompt
(B263) is one global budget of 400 characters for a whole song, spent on
the deduplicated vocabulary in order of first appearance.

Two ways to attack that, in rising cost:

1. shift the START of the audio, so the window edges land elsewhere;
2. cut the song into pieces and transcribe each one separately.

The second is the user's idea and it is the stronger, for a reason that
only became clear once the prompt was read properly: those 400 characters
are a GLOBAL shortage that becomes a LOCAL abundance. Split into eight
pieces, every piece has its own budget and needs far fewer unique words -
so each piece can be given the real lines in full, running text with
phrasing, instead of a word list. That makes Whisper expect the right
SENTENCE and not merely know the right WORDS.

But cutting has a cost that has to be measured honestly: every cut MAKES
a new edge, and an edge is exactly the weak spot above. Hence the rule
here: do not cut on the clock but in the silences the vocal stem already
shows (``rhythm.active_windows``), so no word is ever cut in half.

This module holds the parts that can be reasoned about and tested without
starting Whisper: where to cut, what prompt a piece gets, and how to put
the results back together. The transcribing itself lives in
``tools/whisper_probe.py``; the trial that puts the variants side by side
is 1.5.11d.

On merging, one warning that the whole design rests on: two runs with the
SAME initial prompt are not independent votes. If both say the same
thing, that can mean they both heard it - or that both are reciting the
prompt, which is precisely the prompt echo we are trying to catch.
Agreement is therefore not evidence. The vocal stem is the only
independent witness here, because it knows nothing of the lyrics.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Whisper's window. Fixed by the model: the encoder always gets thirty
#: seconds of log-mel, padded or truncated. No piece may exceed this.
WINDOW_S = 30.0

#: A piece shorter than this is not worth its own run: the model's own
#: overhead is larger than the gain, and a very short piece has hardly
#: any context of its own.
MIN_CHUNK_S = 4.0

#: Where no silence can be found within ``WINDOW_S``, we have to cut
#: through singing after all. Then the pieces overlap by this much, so
#: the border area occurs in TWO pieces and the merge can choose the one
#: where the word is furthest from an edge.
OVERLAP_S = 4.0

#: How much room around a piece the lyrics slice gets. The first run
#: placed the lines, and that placement is least reliable exactly where
#: we are re-running - so the slice is deliberately generous.
PROMPT_MARGIN_S = 8.0


@dataclass(frozen=True)
class Chunk:
    """One piece of audio to transcribe on its own."""

    start: float
    end: float
    #: True when this piece had to be cut through singing (no silence
    #: was available), so its edges are suspect and it overlaps its
    #: neighbour.
    forced: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start


def cut_points(windows, total: float, first_sound: float = 0.0,
               window_s: float = WINDOW_S) -> tuple[Chunk, ...]:
    """Cut the song into pieces, in the silences where possible (B390).

    ``windows`` are the measured sung stretches. Between two of them lies
    silence, and a cut in silence costs nothing: no word is split. Only
    where singing runs for longer than ``window_s`` without a pause do we
    cut through it, and then with an overlap.

    Starting at ``first_sound`` is the offset idea in its simplest form:
    begin a couple of seconds in and every window edge lands somewhere
    else than it did in the first run.
    """
    windows = [(float(a), float(b)) for a, b in windows if b > a]
    windows.sort()
    if total <= 0:
        return ()
    if not windows:
        return (Chunk(first_sound, total),)

    # The moments where a cut is free: the middle of each silence.
    free = []
    previous_end = None
    for start, end in windows:
        if previous_end is not None and start > previous_end:
            free.append((previous_end + start) / 2.0)
        previous_end = max(previous_end or 0.0, end)
    free = [m for m in free if m > first_sound]

    chunks: list[Chunk] = []
    begin = float(first_sound)
    while begin < total - 1e-6:
        limit = begin + window_s
        usable = [m for m in free if begin + MIN_CHUNK_S <= m <= limit]
        if usable:
            end, forced = max(usable), False
        elif limit >= total:
            end, forced = total, False
        else:
            end, forced = limit, True
        chunks.append(Chunk(round(begin, 3), round(min(end, total), 3),
                            forced))
        if end >= total - 1e-6:
            break
        begin = end - OVERLAP_S if forced else end
    return tuple(chunks)


def chunk_prompt(lines, chunk: Chunk, margin: float = PROMPT_MARGIN_S,
                 max_chars: int = 400) -> str:
    """The lyrics slice belonging to this piece, as running text (B390).

    ``lines`` are ``(start, text)`` pairs from the first run. Unlike the
    global prompt (B263) nothing is deduplicated here: locally there is
    room, and the point is exactly to hand Whisper the real phrasing.

    The margin is generous on purpose. This slice leans on the placement
    from the first run, and that placement is worst precisely where we
    are looking again - so rather a line too many than a line short.
    """
    low = chunk.start - margin
    high = chunk.end + margin
    picked = [str(text).strip() for start, text in lines
              if low <= float(start) <= high and str(text).strip()]
    if not picked:
        return ""
    out = ""
    for line in picked:
        candidate = (out + " " + line).strip() if out else line
        if len(candidate) > max_chars:
            break
        out = candidate
    return out


def on_singing(word: dict, windows) -> bool:
    """Does the middle of this word fall inside measured singing?"""
    middle = (float(word["start"]) + float(word["end"])) / 2.0
    return any(float(a) <= middle <= float(b) for a, b in windows)


def word_score(word: dict, windows, lyric_keys=None) -> float:
    """How much this word is worth as a candidate (B390).

    Confidence times two independent checks: does it sit on measured
    singing, and does it occur in the lyrics. The singing is the only
    witness that knows nothing of the prompt, so it weighs heaviest - a
    word not on singing scores zero however sure Whisper is of it, which
    is the same rule B377 applies to whole segments.
    """
    if not on_singing(word, windows):
        return 0.0
    score = max(0.0, float(word.get("confidence", 0.0)))
    if lyric_keys:
        from . import cluster as cluster_module

        key = cluster_module.phonetic_key(str(word.get("text", "")))
        score *= 1.0 if key in lyric_keys else 0.5
    return score


def merge_runs(base, extra, windows, lyric_keys=None,
               min_score: float = 0.35):
    """Fill the holes in ``base`` with words from other runs (B390).

    Deliberately NOT a vote. Runs share their initial prompt, so
    agreement between them says nothing (see the module docstring). What
    this does is narrower and defensible: the first run stays the truth,
    and only where it says NOTHING at all may another run speak - and
    then only with words that sit on measured singing and score above
    ``min_score``.

    That keeps the failure mode small. A second run cannot overrule a
    word that was heard; it can only fill a silence. And a silence is
    where the damage is: 22% of all measured singing carries no text at
    all.

    Returns ``(words, filled)``: the merged word list in time order and
    how many words came from elsewhere.
    """
    kept = sorted(base, key=lambda w: float(w["start"]))
    added = words_to_add(kept, extra, windows, lyric_keys, min_score)
    if added:
        from .translations import t

        logger.info(t("log_merge_filled"), len(added))
    return (tuple(sorted(kept + added, key=lambda w: float(w["start"]))),
            len(added))


def words_to_add(base, extra, windows, lyric_keys=None,
                 min_score: float = 0.35) -> list[dict]:
    """Just the words another run may contribute (B442).

    Split off from :func:`merge_runs` because production needs the
    additions on their own: the rest of the program reads SEGMENTS, and
    a filled-in word has to become a segment of its own instead of being
    smuggled into one that was heard properly. Same rule, one
    implementation - merge_runs goes through here too.
    """
    covered = [(float(w["start"]), float(w["end"])) for w in base]

    def free(word: dict) -> bool:
        start, end = float(word["start"]), float(word["end"])
        return not any(end > a and start < b for a, b in covered)

    added: list[dict] = []
    for word in sorted(extra, key=lambda w: float(w["start"])):
        if not free(word):
            continue
        if word_score(word, windows, lyric_keys) < min_score:
            continue
        added.append(word)
        covered.append((float(word["start"]), float(word["end"])))
    return added


def unheard_seconds(words, windows) -> float:
    """Seconds of measured singing with no word on them at all.

    The number the whole exercise is aimed at, and the one the weak
    spot search leans on.
    """
    spans = sorted((float(w["start"]), float(w["end"])) for w in words)
    total = 0.0
    for low, high in windows:
        cursor = float(low)
        for start, end in spans:
            if end <= cursor or start >= high:
                continue
            if start > cursor:
                total += start - cursor
            cursor = max(cursor, end)
        if high > cursor:
            total += high - cursor
    return round(total, 2)


# -- production: the whole song and its pieces in one queue (B442) --------

#: A gap this large between two loose words starts a new segment when the
#: filled-in words are put back together. Whisper's own segments average
#: well under this; a longer silence is a phrase boundary.
_SEGMENT_GAP_S = 0.6


#: The job that is the whole song. An open end is also what tells the
#: runner it may hand the file straight to Whisper instead of cutting
#: samples out of it.
WHOLE_SONG = (0.0, None)


def jobs_heaviest_first(pieces, whole: float, second: str = ""):
    """The work list for one song: the whole run first, then the pieces.

    The user's rule, in his own words: put as much as possible in one
    queue and start the heaviest task first. The whole song IS the
    heaviest single item - it is longer than any piece by definition -
    so it goes in front, and the pieces follow by descending length. A
    lane that finishes the short tail early then still has time to help
    with a long piece.

    Returns ``(start, end)`` pairs; ``end`` is ``None`` for the whole
    song, which is also what tells the runner it may use the file
    directly instead of cutting samples.

    ``second`` (B538) adds one more job: the whole song once more, in
    another language. It goes in FRONT, next to the first whole run,
    because it is just as heavy and the queue starts with the heaviest.
    That job carries its language as a third element, which also keeps
    it apart from the first whole run - same seconds, different reading.
    """
    ordered = sorted(pieces, key=lambda c: -(c.end - c.start))
    jobs: list[tuple] = [WHOLE_SONG]
    if second:
        jobs.append((0.0, None, str(second)))
    return jobs + [(c.start, c.end) for c in ordered
                   if whole <= 0 or c.duration > 0]


def words_of(segments) -> list[dict]:
    """Segments (dataclasses or dicts) as plain word dictionaries."""
    out = []
    for segment in segments:
        words = (segment.get("words") or ()) if isinstance(segment, dict) \
            else segment.words
        for word in words:
            if isinstance(word, dict):
                out.append(dict(word))
            else:
                out.append({"text": word.text, "start": float(word.start),
                            "end": float(word.end),
                            "confidence": float(word.confidence)})
    return out


def segments_from_words(words, first_index: int = 0,
                        gap_s: float = _SEGMENT_GAP_S) -> list[dict]:
    """Group loose words back into segments.

    The merge works on words - that is the level at which a hole can be
    filled without touching anything that was already heard - but the
    rest of the program reads segments. Words that follow each other
    closely become one segment; a silence longer than ``gap_s`` starts a
    new one.
    """
    groups: list[list[dict]] = []
    for word in sorted(words, key=lambda w: float(w["start"])):
        if groups and float(word["start"]) - float(groups[-1][-1]["end"]) \
                <= gap_s:
            groups[-1].append(word)
        else:
            groups.append([word])
    return [{"index": first_index + number,
             "text": " ".join(str(w["text"]).strip() for w in group).strip(),
             "start": float(group[0]["start"]),
             "end": float(group[-1]["end"]),
             "words": list(group)}
            for number, group in enumerate(groups)]


def run_over_lanes(audio_path, settings, jobs, prompt: str, language: str,
                   lanes: int | None = None, cancelled=None,
                   on_done=None) -> dict:
    """Run every job over the Whisper lanes (B442).

    ``jobs`` are ``(start, end)`` pairs as :func:`jobs_heaviest_first`
    gives them. Returns ``{(start, end): segments}``; a PIECE that fails
    is simply absent. The whole song is different in two ways, and both
    of them have to be loud:

    * if it fails, its exception is raised - there is nothing to fill in
      without it;
    * if anything was CANCELLED, the whole call is cancelled. Stop means
      stop, and a half-finished run may not be handed back looking like
      a finished one. Not theoretical: the caller writes what it gets
      into the transcription cache and marks the step done, and
      everything derived from that transcription - a hand-timed
      ``timing.json`` included - is then thrown away on the strength of
      it. One Stop press at the wrong moment would have cost an
      afternoon of work.

    Threads and not processes, deliberately. The measuring pool uses
    processes because that work is pure Python and the GIL makes two
    threads take turns on one core. Whisper is the other case entirely:
    ctranslate2 is C++, it releases the GIL, and since the model is
    handed the number of callers it will get it serves several of them
    at once. A process here would mean loading large-v3 again per lane.
    """
    import threading

    from . import measure_pool, whisper

    queue = list(jobs)
    if not queue:
        return {}
    slots = max(1, lanes or measure_pool.whisper_lanes())
    found: dict = {}
    failed: list = []
    stopped: list = []
    lock = threading.Lock()

    def take():
        with lock:
            return queue.pop(0) if queue else None

    def report() -> None:
        """Count a job as settled, whichever way it went.

        The counter is read under the lock: two lanes reporting from
        outside it can arrive out of order and then the progress bar
        walks backwards. A failed piece counts too - otherwise one
        failure means the bar never reaches the end.
        """
        with lock:
            ready = len(found) + len(failed)
        if on_done is not None:
            on_done(ready, len(jobs))

    def worker() -> None:
        while True:
            job = take()
            if job is None:
                return
            if cancelled is not None and cancelled():
                with lock:
                    stopped.append(job)
                return
            # B538: a job may name its own language. Everything else
            # keeps the language of the call, so the shape of a job did
            # not have to change everywhere.
            start, end, *rest = job
            try:
                segments = whisper.transcribe_slice(
                    audio_path, settings, start=start, end=end,
                    initial_prompt=prompt,
                    language_override=(rest[0] if rest else language),
                    cancelled=cancelled)
            except whisper.CancelledError:
                with lock:
                    stopped.append(job)
                return
            except Exception as exc:      # noqa: BLE001 - one piece is not the run
                with lock:
                    failed.append((job, exc))
                from .translations import t

                # B538: with the language, and the whole song as its
                # own end - "piece 0.0-0.0 s failed" said nothing about
                # which of the two whole runs it was.
                logger.exception(t("log_chunk_failed"), float(start),
                                 float(end if end is not None else -1.0))
                report()
                continue
            with lock:
                found[job] = segments
            report()

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(min(slots, len(jobs)))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if stopped:
        raise whisper.CancelledError()
    for job, exc in failed:
        if job == WHOLE_SONG:
            raise exc
    if WHOLE_SONG in jobs and WHOLE_SONG not in found:
        # Belt and braces. Nothing should reach this, and if something
        # ever does, an empty transcription that LOOKS complete is the
        # one outcome we cannot afford.
        raise whisper.CancelledError()
    return found


def extra_words_from(found: dict) -> list[dict]:
    """Every word the OTHER jobs heard, the first whole run left out.

    The pieces (B442), and since B538 the whole song in a second
    language as well. They are all the same kind of thing here: a
    reading that may fill a silence and may never overrule a word the
    first run heard.
    """
    return [word for job, segments in found.items() if job != WHOLE_SONG
            for word in words_of(segments)]
