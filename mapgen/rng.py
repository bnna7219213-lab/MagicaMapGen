"""Deterministic random stream.

Extracted verbatim from the validated ``island_generator.py`` implementation so
that the reproducibility guarantee already proven by byte-identical re-runs is
preserved. SplitMix64 seed expansion + xorshift128+; no dependency on Python's
``random`` module, no global state, identical output across platforms.

Every generator in this package must take an explicit ``DetRandom`` instance.
Never call ``random.*`` or ``os.urandom``.
"""

import math

MASK64 = (1 << 64) - 1


class DetRandom:
    """Reproducible stream: same seed => same sequence, everywhere."""

    __slots__ = ("_s0", "_s1")

    def __init__(self, seed: int):
        z = ((seed & MASK64) + 0x9E3779B97F4A7C15) & MASK64
        self._s0 = self._mix(z)
        self._s1 = self._mix(z)
        if self._s0 == 0 and self._s1 == 0:
            self._s1 = 1

    @staticmethod
    def _mix(z: int) -> int:
        z = (z + 0x9E3779B97F4A7C15) & MASK64
        x = z
        x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK64
        return (x ^ (x >> 31)) & MASK64

    def next_ulong(self) -> int:
        s1 = self._s0
        s0 = self._s1
        self._s0 = s0
        s1 = (s1 ^ ((s1 << 23) & MASK64)) & MASK64
        self._s1 = (s1 ^ s0 ^ ((s1 >> 18) & MASK64) ^ ((s0 >> 5) & MASK64)) & MASK64
        return (self._s1 + s0) & MASK64

    def next_float(self, lo: float, hi: float) -> float:
        t = (self.next_ulong() >> 11) / 9007199254740992.0
        return lo + (hi - lo) * t

    def normal(self, mean: float, sigma: float) -> float:
        """Box-Muller normal sample drawn from this generator's own stream."""
        u1 = max(1e-15, self.next_float(0.0, 1.0))
        u2 = self.next_float(0.0, 1.0)
        return mean + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def next_int(self, lo: int, hi: int) -> int:
        if hi <= lo:
            return lo
        return lo + (self.next_ulong() % (hi - lo))

    def chance(self, p: float) -> bool:
        return self.next_float(0.0, 1.0) < p

    def fork(self, key: str) -> "DetRandom":
        """Derive an independent child stream.

        FNV-1a over the key keeps sub-streams stable regardless of the order in
        which callers request them, so adding a new feature cannot reshuffle the
        sequences of existing ones.
        """
        h = 2166136261
        for ch in key.encode("utf-8"):
            h ^= ch
            h = (h * 16777619) & 0xFFFFFFFF
        return DetRandom((self._s0 ^ (h << 1)) & 0x7FFFFFFF)
