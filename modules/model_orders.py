"""The orders the big trial measures, apart from the panel (B439).

This used to sit inside ``test_panel._orders``, and that was the one
variant of 1.5.10 that could never travel to a child interpreter. A
model travels as a CODE - the child rebuilds the state from the register
itself - but an order is not a model: it swaps whole functions for each
other, and a function object does not survive pickling.

So the order travels as a NAME, and the child builds the replacements
itself from that name. Which means the definitions have to live
somewhere a measuring process can import, and ``test_panel`` is not that
place: it pulls in PySide6 at module level, and a worker that measures
timing has no business starting a widget toolkit.

Nothing about the orders themselves changed; they moved.
"""
from __future__ import annotations

from . import pipeline


def _position_first_targets():
    """B307 before B285: position-aware round first, song-wide after."""
    from . import song_text as ST

    # B536: deliberately the functions as they stand on the module RIGHT
    # NOW, replacements and all. An order rearranges the pipeline the
    # user really runs; reaching past a model switch would measure a
    # pipeline nobody has. What may not happen is that an order quietly
    # reports 0.00 s because a step it moves is switched off - that is
    # what ``models`` below is for: then the trial says "skipped" and
    # names the model, instead of printing a number for something that
    # was never tried.
    real_position = pipeline._filter_hallucinations_in_position
    real_all = pipeline._filter_hallucinations

    def position_first(context, lyrics, segments, dropped_out=None):
        # Reversed: first the position-aware round (B307) on an alignment
        # over the RAW segments, and only then the song-wide one (B285).
        priority = pipeline._filler_priority_lines(context)

        def align(segs):
            return ST.trim_tail_matches(
                ST.align_lyrics(lyrics, segs, skip_filler=True,
                                priority_lines=priority))

        first = real_position(
            segments, lyrics, align(segments), dropped_out=dropped_out,
            language=pipeline._language_for(context,
                                            pipeline.TRACK_ORIGINAL))
        clean = real_all(first, lyrics, dropped_out=dropped_out)
        return clean, align(clean)

    return [(pipeline, "_clean_segments_and_alignment", position_first)]


def _energy_first_targets():
    """B313 before B121: a time from the vocal stem, pins on top."""
    real_clean = pipeline._clean_segments_and_alignment
    real_energy = pipeline._place_skipped_on_energy

    def energy_first(context, lyrics, segments, dropped_out=None):
        # B313 normally runs AFTER the hand couplings (B121). The other
        # way round: first a time from the vocal stem, then the pins on
        # top of it.
        clean, aligned = real_clean(context, lyrics, segments,
                                    dropped_out=dropped_out)
        return clean, real_energy(context, aligned)

    return [(pipeline, "_clean_segments_and_alignment", energy_first),
            (pipeline, "_place_skipped_on_energy", lambda ctx, a: a)]


#: Name -> (builder, the model codes the order moves). The name is what
#: travels to a child process; the codes say when the order cannot be
#: measured at all, because a step it rearranges is switched off (B536).
_BUILDERS = {
    "B307 vóór B285": (_position_first_targets, ("B307/B337", "B258/B285")),
    "B313 vóór B121": (_energy_first_targets, ("B313", "B121")),
}


def names() -> tuple[str, ...]:
    """The orders that can be measured, in report order."""
    return tuple(_BUILDERS)


#: The word between the two codes of an order name. The name itself is
#: an id - it travels to a child process and into the measurement
#: history - so it keeps its spelling; only what a report prints is
#: translated (v1.0.11).
_BETWEEN = " vóór "


def label(name: str) -> str:
    """An order name the way a report prints it, in the active language."""
    from .translations import t

    first, found, second = name.partition(_BETWEEN)
    if not found:
        return name
    return f"{first} {t('model_order_before')} {second}"


def targets(name: str):
    """The ``(module, attribute, replacement)`` triples for one order.

    Built fresh on every call on purpose: a builder closes over the
    function that is real RIGHT NOW, so building it once at import time
    would freeze whatever happened to be installed then.
    """
    entry = _BUILDERS.get(name)
    return entry[0]() if entry else []


def models_for(name: str) -> tuple[str, ...]:
    """The model codes this order rearranges (B536).

    An order that moves a step which is switched off measures nothing
    and would report a tidy 0.00 s for it. The caller asks this first
    and says "skipped" instead.
    """
    entry = _BUILDERS.get(name)
    return entry[1] if entry else ()


def measurable(name: str) -> tuple[str, ...]:
    """The codes of this order that are OFF - empty means measurable."""
    from . import model_register

    return tuple(code for code in models_for(name)
                 if not model_register.enabled(code))


def build_all():
    """``(name, targets)`` for every order - what the panel reports on."""
    return tuple((name, targets(name)) for name in names())


def apply(name: str) -> None:
    """Install an order in THIS interpreter (B439).

    Installs only - the caller saves and restores, and it has to: the
    measuring pool keeps ONE set of workers alive for a whole action, so
    a worker measures round after round. An order left standing would
    stack on the next one and would keep running in every later round
    that has no order at all.
    """
    for module, attribute, replacement in targets(name):
        setattr(module, attribute, replacement)
