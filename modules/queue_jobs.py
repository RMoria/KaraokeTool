"""Every kind of job the program puts in the work queue, in one place
(v1.0.19): the helper takes what is listed here, the program the same.
v1.0.20: besides the tests, a separation of ordinary work
(:mod:`modules.shared_work`).

A kind is ``(handler, name)``: the handler does one round from plain
data, ``handler(job, queue, stop) -> answer``. Modules are imported when
asked, so a helper without the Qt window never loads it.
"""
from __future__ import annotations

from typing import Callable


def handlers() -> dict[str, Callable]:
    """Kind -> handler, for all tests and the shared separation."""
    from . import block_trial, jamendo_trial, musdb_trial, separation_trial
    from . import diagnose, shared_work, stem_trial

    return {separation_trial.JOB_KIND: separation_trial.run_round,
            shared_work.JOB_KIND: shared_work.run_round,
            shared_work.RENDER_KIND: shared_work.run_render_round,
            diagnose.JOB_KIND: diagnose.run_round,
            block_trial.JOB_KIND: block_trial.run_round,
            stem_trial.PREP_KIND: stem_trial.prep_round,
            jamendo_trial.JOB_KIND: jamendo_trial.run_round,
            musdb_trial.JOB_KIND: musdb_trial.run_round}
