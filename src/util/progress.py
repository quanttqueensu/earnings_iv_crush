"""A tiny dependency-free progress bar with a live ETA.

The real-data assembly (event chains, daily term-spread panels) is network-bound
and slow, so the long loops report progress to stderr: a bar, the count, percent,
elapsed time and an ETA that updates in place. No third-party dependency (so it
works in the project's stdlib-only spirit) and silent when disabled, so library
and test callers are unaffected.

Usage::

    for item in progress_iter(items, total=len(items), label="events"):
        ...                       # one tick per item

or manually::

    bar = ProgressBar(total, label="term panel")
    for ...:
        ...
        bar.update()
    bar.close()
"""
from __future__ import annotations

import sys
import time


def _fmt(seconds: float) -> str:
    """Seconds -> H:MM:SS (or M:SS under an hour)."""
    seconds = int(max(seconds, 0))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


class ProgressBar:
    """Render an in-place stderr progress bar with elapsed time and ETA."""

    def __init__(self, total: int, label: str = "", width: int = 30,
                 stream=None, enabled: bool = True):
        self.total = max(int(total), 1)
        self.label = label
        self.width = width
        self.stream = stream if stream is not None else sys.stderr
        self.enabled = enabled
        self.n = 0
        self.start = time.time()

    def update(self, step: int = 1) -> None:
        """Advance by `step` and redraw."""
        self.n += step
        if not self.enabled:
            return
        frac = min(self.n / self.total, 1.0)
        filled = int(self.width * frac)
        bar = "#" * filled + "-" * (self.width - filled)
        elapsed = time.time() - self.start
        rate = self.n / elapsed if elapsed > 0 else 0.0
        eta = (self.total - self.n) / rate if rate > 0 else 0.0
        self.stream.write(
            f"\r{self.label} [{bar}] {self.n}/{self.total} {frac * 100:5.1f}%  "
            f"elapsed {_fmt(elapsed)}  ETA {_fmt(eta)}   ")
        self.stream.flush()

    def close(self) -> None:
        """Finish the line so later output starts cleanly."""
        if self.enabled:
            self.stream.write("\n")
            self.stream.flush()


def progress_iter(iterable, total: int, label: str = "", enabled: bool = True):
    """Yield from `iterable`, ticking a `ProgressBar` after each item."""
    bar = ProgressBar(total, label=label, enabled=enabled)
    try:
        for item in iterable:
            yield item
            bar.update()
    finally:
        bar.close()
