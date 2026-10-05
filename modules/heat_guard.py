"""A helper that is too hot takes no work (v1.0.23, B642).

Pav switched itself off in the night of 28 September: its card lane had
separated with three Roformer models on a 4 GB laptop card for hours, at
84 °C while idle the day before. A laptop protects itself by going out,
and then its rounds wait five minutes before they go back and it is
gone from the network until somebody switches it on.

So a helper on a computer with an NVIDIA card watches the card's
temperature - on a laptop the card and the processor share one cooler,
so it says how hot the whole machine is:

* above :data:`WAIT_ABOVE_C` a lane takes no new round, until the card is
  below :data:`RESUME_BELOW_C` again;
* a round that keeps the card above :data:`STOP_ABOVE_C` for
  :data:`STOP_AFTER_S` is stopped and goes back into the queue, for a
  computer that can take it; then this one cools down for at least
  :data:`COOL_S`.

A computer without ``nvidia-smi`` has nothing to read and is not watched
(its processor's temperature needs rights Windows does not give a
program without asking).
"""
from __future__ import annotations

import subprocess
import time
from typing import Callable

#: No new round above this (°C).
WAIT_ABOVE_C = 80.0
#: ...until the card is below this again.
RESUME_BELOW_C = 70.0
#: A round that keeps the card above this...
STOP_ABOVE_C = 88.0
#: ...for this long is stopped.
STOP_AFTER_S = 60.0
#: After a stopped round, at least this long no new one.
COOL_S = 900.0
#: A reading is used for this long before the card is read again - while
#: a round runs, and (less often, the card is left in peace) while a lane
#: waits for work.
_READ_EVERY_S = 10.0
_READ_IDLE_S = 60.0


def card_temperature() -> float | None:
    """The card's temperature in °C, or ``None`` without ``nvidia-smi``."""
    from . import proc

    try:
        done = proc.run(["nvidia-smi", "--query-gpu=temperature.gpu",
                         "--format=csv,noheader,nounits"], check=False,
                        timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    try:
        return max(float(row) for row in done.stdout.split() if row.strip())
    except ValueError:
        return None


def present() -> bool:
    """Is there a card to watch?"""
    return card_temperature() is not None


class HeatGuard:
    """The temperature rules for the lanes of one computer."""

    #: How often a running round is looked at.
    WATCH_S = 15.0

    def __init__(self, read: Callable[[], float | None] = card_temperature,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._read = read
        self._clock = clock
        self._last: tuple[float, float | None] | None = None
        self._cooling = False
        self._hot_since: float | None = None
        self._cool_until = 0.0

    def degrees(self, every: float = _READ_EVERY_S) -> float | None:
        now = self._clock()
        if self._last is None or now - self._last[0] >= every:
            try:
                value = self._read()
            except Exception:  # noqa: BLE001 - no reading, no rule
                value = None
            self._last = (now, value)
        return self._last[1]

    def must_wait(self) -> float | None:
        """The temperature when a lane has to wait before its next round,
        else ``None``."""
        cooling_down = self._clock() < self._cool_until
        value = self.degrees(_READ_EVERY_S if self._cooling
                             else _READ_IDLE_S)
        if cooling_down:
            # After a stopped round: the quarter of an hour, read or not.
            self._cooling = True
            return value if value is not None else STOP_ABOVE_C
        if value is None:
            return None
        if value > WAIT_ABOVE_C:
            self._cooling = True
        elif value < RESUME_BELOW_C:
            self._cooling = False
        return value if self._cooling else None

    def watch(self) -> bool:
        """While a round runs: must it be stopped?"""
        value = self.degrees()
        now = self._clock()
        if value is None or value <= STOP_ABOVE_C:
            self._hot_since = None
            return False
        if self._hot_since is None:
            self._hot_since = now
        return now - self._hot_since >= STOP_AFTER_S

    def aborted(self) -> None:
        """A round was stopped for the heat: cool down first."""
        self._hot_since = None
        self._cooling = True
        self._cool_until = self._clock() + COOL_S
