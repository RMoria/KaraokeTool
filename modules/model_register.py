"""The register of switchable models (B361).

Every idea that has ever been built into the timing and the coupling
stands here by name, with a level, a neutral replacement and a state.
There are two reasons for this register.

The first is the user's rule: a model that turns out to be worth nothing
is **switched off, not removed**. The idea behind it is usually good for
something, so it stays in the code, it stays in this list and it keeps
taking part in the measurements - only neutralised. B360 taught what
happens when knowledge about models lives in temporary test code: it
drifts away from the real thing without anyone noticing.

The second is the measurement itself. The big trial (1.5.10) reads this
register, so the matrix is symmetrical: for a model that is ON it
measures what switching it off costs, and for a model that is OFF what
switching it on would deliver. A switched-off idea therefore reports
itself the moment it does turn out to be worth something on new songs.

How switching off works: every model carries a list of ``(module,
attribute, replacement)`` - the same shape the leave-one-out has used
since v0.111.0. :func:`apply_disabled` installs those replacements once
at startup for everything that is off. That is monkey-patching in a
running program, which deserves a word of justification: the
alternative, an ``if`` at every call site, would mean twenty places in
five modules, each with its own idea of what "neutral" means. One table
that both the app and the measurement read is easier to check and
impossible to get out of step - and getting out of step is exactly what
B360 was about. Every switch-off is logged by name at startup, so a
model is never silently off.

Not to be confused with :mod:`modules.models`, which is about the large
optional libraries (Demucs, wav2vec2).

The measured value per model is in ``docs/modelmatrix.md``; the
reasoning behind a state is in ``docs/doorontwikkeling.md``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: Level a model works on; determines where it lands in the matrix.
#: ``view`` models only feed the coupling editor, never the times - the
#: ruler cannot see those, so they are measured on coverage.
LEVELS = ("blok", "zin", "koppeling", "woord", "venster")


@dataclass(frozen=True)
class Model:
    """One switchable idea."""

    #: The B-number(s), e.g. "B329/332/340". Unique, and the key used by
    #: the settings and the measurement history.
    code: str
    #: Short name in the tables (Dutch: it is read in reports).
    name: str
    level: str
    #: Default state. Off means: measured and kept, but not running.
    default_on: bool = True
    #: Why it is off (empty when on). Ends up in the startup log and in
    #: the matrix, so a state is never anonymous.
    reason: str = ""
    #: ``(module, attribute, replacement)``; a replacement has to accept
    #: the same arguments as the real function.
    targets: tuple = field(default_factory=tuple)

    @property
    def label(self) -> str:
        return f"{self.code} {self.name}"


def _build() -> tuple[Model, ...]:
    """The register, built late so the imports stay circular-free."""
    from . import pipeline
    from . import song_text as song
    from . import timing as tim
    from . import timing_rules as rules

    # B373: ``lyrics=`` was added, so the replacement has to swallow it too.
    same = lambda segments, *a, **k: segments                    # noqa: E731
    real_arbitrate = rules.arbitrate_anchors
    real_align = song.align_lyrics

    def without_block_border(candidates):
        # Everything in the same (virtual) block: then a later anchor can
        # push away an earlier anchor from another block (B250/B251).
        from dataclasses import replace as _replace
        return real_arbitrate([_replace(c, block=0) for c in candidates])

    def without_filler_round(lyrics, segments, skip_filler=False,
                             priority_lines=None):
        # B213: let filler words simply take part in the main alignment.
        return real_align(lyrics, segments, skip_filler=False,
                          priority_lines=priority_lines)

    real_hallucinations = pipeline._filter_hallucinations

    def without_song_wide(segments, *args, **kwargs):
        # B536: switching this model off may not take B141 and B514 with
        # it. Those live in the same function and were measured on their
        # own; the model is named after B258/B285 and only those two go.
        kwargs["song_wide"] = False
        return real_hallucinations(segments, *args, **kwargs)

    return (
        Model("B250/B251", "blokgrens", "blok",
              targets=((rules, "arbitrate_anchors", without_block_border),)),
        # B522/B529: the switch has to sit on the function the pipeline
        # really calls. ``implausible_anchors`` became a wrapper and
        # ``sanitize_timing`` calls ``implausible_and_overlong``
        # directly, so switching the old name off changed nothing at all
        # - and then the matrix reports 0.00 s for this model and the
        # conclusion "that check does nothing" is a measuring error.
        Model("B329/332/340", "ankertoets", "zin",
              targets=((tim, "implausible_and_overlong",
                        lambda *a, **k: (set(), set())),)),
        Model("B332", "frase-periode", "zin",
              targets=((tim, "phrase_period", lambda *a, **k: None),)),
        Model("B329", "referentieduur", "zin",
              targets=((tim, "reference_durations", lambda *a, **k: {}),)),
        Model("B330/B351", "snappen", "zin",
              targets=((tim, "snap_to_onsets",
                        lambda lines, *a, **k: tuple(lines)),)),
        Model("B351", "begin na pauze", "zin",
              targets=((tim, "_onset_before_start", lambda *a, **k: None),)),
        Model("B336", "staartvensters", "zin",
              targets=((tim, "tail_over_windows", lambda *a, **k: None),)),
        Model("B334", "herhaallus", "zin",
              targets=((pipeline, "_drop_repetition_loop", same),)),
        Model("B342", "grenswoorden", "zin",
              targets=((pipeline, "_merge_boundary_duplicates", same),)),
        Model("B343", "spookwoorden", "zin",
              targets=((pipeline, "_drop_phantom_words", same),)),
        # B377: the vocal stem as referee. If a segment sits on no
        # measured singing at all, it is not singing - not even when the
        # text comes word for word from the lyrics (the prompt echo).
        Model("B377", "zang als scheidsrechter", "koppeling",
              targets=((pipeline, "_drop_unsung_segments",
                        lambda ctx, segments, *a, **k: segments),)),
        # B536: OFF since v0.150.0, and that was a surprise. The filter
        # throws away segments that look like a hallucination of the
        # model, and on the benchmark set it costs more than it saves:
        # switching it off gave -0.14 s over all projects with hand
        # timing, measured twice (26 and 31 August, 1.5.9). On "Lied T
        # " it is not a nuance but the main defect: 17.29 s
        # error with it on against 7.28 s with it off, and the damage to
        # lines the user never touched falls from 7.47 s to 0.69 s. It
        # does earn its keep somewhere - "Lied I" goes
        # from 1.81 s to 4.34 s without it - so off, not gone: the trial
        # keeps taking it along and reports the day it turns.
        Model("B258/B285", "hallucinaties", "koppeling", default_on=False,
              reason="-0,14 s op de ijkset; op Lied_T "
                     "17,29 s tegen 7,28 s",
              targets=((pipeline, "_filter_hallucinations",
                        without_song_wide),)),
        Model("B307/B337", "hallucinaties op plek", "koppeling",
              targets=((pipeline, "_filter_hallucinations_in_position",
                        lambda segments, *a, **k: segments),)),
        # B536: ON again since v0.150.0. It was off from v0.115.0
        # because it cost 0.13 s on the benchmark set of the day, but
        # the set and the steps around it have both grown since; on
        # 26 and 31 August the leave-out trial (1.5.9) measured it the
        # other way round, twice: -0.18 s WITH it on. A model that is
        # off keeps being measured every run precisely so a verdict from
        # thirty versions ago cannot quietly stay standing.
        Model("B213", "vulwoorden apart", "koppeling",
              targets=((song, "align_lyrics", without_filler_round),)),
        Model("B276", "vulwoord-voorrang", "koppeling",
              targets=((pipeline, "_filler_priority_lines",
                        lambda ctx: frozenset()),)),
        Model("B159", "zwakke staart losmaken", "koppeling",
              targets=((song, "trim_tail_matches",
                        lambda aligned, *a, **k: tuple(aligned)),)),
        Model("B121", "handkoppelingen", "koppeling",
              targets=((pipeline, "_pins_for_transcript",
                        lambda *a, **k: {}),)),
        Model("B313", "energieplaatsing", "koppeling",
              targets=((pipeline, "_place_skipped_on_energy",
                        lambda ctx, a: a),)),
        # B380: take an impossible line duration from the same line
        # elsewhere in the song. Where the biggest error sits (repeated
        # lines, 1.89 s against 0.48 s) the solution sits too: of those
        # lines there is a well measured copy elsewhere.
        # OFF, with reason. The idea is right - a repeated line IS well
        # measured elsewhere in the song - but this one builds its
        # templates from the OUTPUT of the sentence coupling, and that is
        # exactly the step that is broken in an outro. Measured on "Lied K
        # ": four "instances" of exactly 1.00 s, which
        # is not a measurement but the floor from sanitize_timing, and
        # nine instances with a spread of 1.48. The template should come
        # from the TRANSCRIPTION TIMES (the original side), through the
        # coupling map. Off instead of gone: the trial keeps taking it
        # along every run and reports the moment it IS worth something.
        Model("B392", "gat op de zang", "zin",
              reason="een gat middenin kreeg een rechte lijn; B336 deed "
                     "dit al voor de staart",
              targets=((tim, "windows_between",
                        lambda count, windows, after, before: None),)),
        Model("B380", "sjabloontiming", "zin", default_on=False,
              reason="bouwt sjablonen uit de koppeluitvoer; op een stukke "
                     "outro levert dat een ondergrens van 1.00 s op",
              targets=((pipeline, "_retime_from_templates",
                        lambda ctx, timed: timed),)),
        Model("B234/B347", "woorden op de zangvensters", "woord",
              targets=((tim, "distribute_over_windows",
                        lambda line, *a, **k: line),)),
        Model("B241", "fonetische lettergrepen", "woord",
              targets=((tim, "apply_phonetic_timing",
                        lambda lines, *a, **k: tuple(lines)),)),
        # These two only feed the coupling view and not the times; the
        # yardstick cannot see them by definition and scores them on
        # coverage.
        Model("B191", "koppeling uitbreiden", "venster",
              targets=((song, "extend_coupling",
                        lambda text, transcript, base, claimed, **k:
                        [base]),)),
        Model("B228", "creatieve koppelingen", "venster",
              targets=((song, "creative_couplings",
                        lambda texts, transcript, targets, **k:
                        [list(x) for x in targets]),)),
    )


_REGISTER: tuple[Model, ...] | None = None
#: Overrides from the settings; :func:`apply_settings` fills this.
_OVERRIDES: dict[str, bool] = {}
#: Which models are really neutralised right now, with their originals.
_DISABLED_NOW: dict[str, tuple] = {}


def register() -> tuple[Model, ...]:
    """All models, built once."""
    global _REGISTER
    if _REGISTER is None:
        _REGISTER = _build()
    return _REGISTER


def by_code(code: str) -> Model | None:
    return next((m for m in register() if m.code == code), None)


def enabled(code: str) -> bool:
    """Is this model on? A setting wins over the default."""
    if code in _OVERRIDES:
        return _OVERRIDES[code]
    model = by_code(code)
    return True if model is None else model.default_on


def apply_settings(overrides) -> None:
    """Take over the ``models`` block from the settings.

    An unknown code is ignored with a warning: a typo in a settings file
    must not silently switch off a model that does exist, nor pretend a
    non-existent one is being steered.
    """
    from .translations import t

    _OVERRIDES.clear()
    for code, state in dict(overrides or {}).items():
        if by_code(str(code)) is None:
            logger.warning(t("log_model_unknown"), code)
            continue
        _OVERRIDES[str(code)] = bool(state)


def apply_disabled() -> tuple[str, ...]:
    """Neutralise everything that is off, and report by name.

    Idempotent: calling twice does not switch anything off twice, and a
    model that is on again gets its real function back.
    """
    from .translations import t

    for code, saved in list(_DISABLED_NOW.items()):
        if enabled(code):
            for module, attribute, real in saved:
                setattr(module, attribute, real)
            _DISABLED_NOW.pop(code)
            logger.info(t("log_model_enabled"), code)
    for model in register():
        if enabled(model.code) or model.code in _DISABLED_NOW:
            continue
        saved = tuple((module, attribute, getattr(module, attribute))
                      for module, attribute, _new in model.targets)
        for module, attribute, replacement in model.targets:
            setattr(module, attribute, replacement)
        _DISABLED_NOW[model.code] = saved
        logger.info(t("log_model_disabled"), model.code, model.name,
                    model.reason or "-")
    return disabled_now()


def current_settings() -> dict:
    """The overrides as they stand now (B439).

    Enough to put the register back exactly as it was after something
    measured a variant in this same interpreter. Deliberately the
    OVERRIDES and not the full on/off map: handing back a complete map
    would turn every default into an explicit setting, and then a later
    change of a default would silently not arrive.
    """
    return dict(_OVERRIDES)


def restore_all() -> None:
    """Put every neutralised model back (for tests)."""
    for code, saved in list(_DISABLED_NOW.items()):
        for module, attribute, real in saved:
            setattr(module, attribute, real)
        _DISABLED_NOW.pop(code)


def disabled_now() -> tuple[str, ...]:
    """The codes that are really neutralised at this moment."""
    return tuple(sorted(_DISABLED_NOW))


def state_line() -> str:
    """One line for a report: how many on, how many off, and which."""
    off = [m.code for m in register() if not enabled(m.code)]
    aan = len(register()) - len(off)
    return f"{aan} aan, {len(off)} uit" + (
        f" (uit: {', '.join(off)})" if off else "")
