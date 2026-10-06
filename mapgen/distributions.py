"""Tier 3: replaceable stochastic placement strategies.

Every strategy implements the same contract::

    sample(rng, domain, count, params) -> list[(x, y)]

so a category can switch from ``normal_clusters`` to ``poisson_disk`` by
changing one string in a config file. This is the layer that makes 概率不是定数式
true while keeping 主题确定 intact: the theme decides *what* may appear and
*where* it is allowed, the distribution decides *how* it is spread.

All strategies draw exclusively from the supplied ``DetRandom``, so results are
reproducible per seed and independent of call order elsewhere in the pipeline
(each category gets its own forked stream).

Registering a new distribution: subclass ``Distribution``, then add it to
``REGISTRY`` at the bottom of this module.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Sequence, Tuple

from .rng import DetRandom

Cell = Tuple[int, int]


class Domain:
    """The set of cells a category is allowed to occupy.

    Built once per category (optionally intersected with a region mask) and
    reused for both cluster-centre selection and per-point validity tests.

    ``occupied`` may be an externally-owned set. Passing the same set to several
    Domains makes them share occupancy, which is how two categories in the same
    exclusion group are kept from putting two objects on one cell.

    ``length_scale`` converts an authored length (in reference-grid cells, the
    unit themes and configs write) into cells of *this* grid. See
    ``schema.grid_length_scale``. At the reference resolution it is exactly 1.0,
    so a strategy written against a 256-cell theme keeps its meaning verbatim.
    """

    __slots__ = ("W", "H", "cells", "index", "centroid", "bbox", "_occupied",
                 "length_scale")

    def __init__(self, W: int, H: int, cells: Sequence[Cell],
                 occupied: "set | None" = None,
                 length_scale: float = 1.0):
        self.W = W
        self.H = H
        self.cells: List[Cell] = list(cells)
        self.index = set(self.cells)
        self.length_scale = float(length_scale)
        self._occupied: set = occupied if occupied is not None else set()
        if self.cells:
            sx = sum(c[0] for c in self.cells)
            sy = sum(c[1] for c in self.cells)
            n = len(self.cells)
            self.centroid = (sx / n, sy / n)
            xs = [c[0] for c in self.cells]
            ys = [c[1] for c in self.cells]
            self.bbox = (min(xs), min(ys), max(xs), max(ys))
        else:
            self.centroid = (W * 0.5, H * 0.5)
            self.bbox = (0, 0, W - 1, H - 1)

    def __len__(self) -> int:
        return len(self.cells)

    def valid(self, x: int, y: int) -> bool:
        return 0 <= x < self.W and 0 <= y < self.H and (x, y) in self.index

    def length(self, units: float) -> float:
        """An authored length in reference cells, expressed in this grid's cells."""
        return units * self.length_scale

    def take(self, x: int, y: int) -> bool:
        """Claim a cell. Returns False if already claimed or not in domain."""
        if (x, y) in self._occupied or not self.valid(x, y):
            return False
        self._occupied.add((x, y))
        return True

    def taken(self, x: int, y: int) -> bool:
        return (x, y) in self._occupied

    def reset(self) -> None:
        self._occupied.clear()


class Distribution:
    """Base class. ``id`` must match the key used in config files."""

    id: str = ""
    params: Tuple[str, ...] = ()
    #: True when this strategy naturally yields attributed groups (groves).
    grouped: bool = False

    def sample(self, rng: DetRandom, domain: Domain, count: int,
               params: Dict) -> List[Cell]:
        return [c for g in self.sample_groups(rng, domain, count, params) for c in g]

    def sample_groups(self, rng: DetRandom, domain: Domain, count: int,
                      params: Dict) -> List[List[Cell]]:
        """Return points split into attributed groups.

        The default is a single unattributed group; clustered strategies
        override this so callers can label instances with a cluster id without
        having to reverse-engineer the sampling order.
        """
        raise NotImplementedError

    def describe(self) -> Dict[str, str]:
        return {"id": self.id, "params": ", ".join(self.params) or "(none)",
                "grouped": str(self.grouped)}


class Uniform(Distribution):
    """Uniform random over the domain -- the flat baseline distribution."""

    id = "uniform"
    params = ("max_attempts_per_point",)

    def sample_groups(self, rng, domain, count, params):
        if not domain.cells or count <= 0:
            return []
        budget = int(params.get("max_attempts_per_point", 40)) * count
        out: List[Cell] = []
        n = len(domain.cells)
        for _ in range(budget):
            if len(out) >= count:
                break
            x, y = domain.cells[rng.next_int(0, n)]
            if domain.take(x, y):
                out.append((x, y))
        return [out] if out else []


class NormalClusters(Distribution):
    """Gaussian groves: several cluster centres, points normally spread around each.

    This is the classic RTS forest look and the default for vegetation.
    ``cluster_count`` centres are drawn normally about the domain centroid and
    snapped to valid cells; ``count`` is then split across them with a normal
    jitter on each share. Groups are returned separately so callers can label
    instances with a cluster id and report grove centroids.
    """

    id = "normal_clusters"
    grouped = True
    params = ("cluster_count", "spread", "min_cluster_spacing", "centre_sigma")

    def sample_groups(self, rng, domain, count, params):
        if not domain.cells or count <= 0:
            return []
        n_clusters = max(1, int(params.get("cluster_count", 1)))
        spread = domain.length(float(params.get("spread", 3.0)))
        min_spacing = domain.length(
            float(params.get("min_cluster_spacing", spread * 2.2)))
        centre_sigma = float(params.get("centre_sigma", 0.21))
        sigma = max(1.0, spread)

        W, H = domain.W, domain.H
        cx0, cy0 = domain.centroid
        n = len(domain.cells)

        centres: List[Cell] = []
        for _ in range(n_clusters):
            chosen = None
            for _attempt in range(250):
                cx = int(max(0, min(W - 1, round(rng.normal(cx0, W * centre_sigma)))))
                cy = int(max(0, min(H - 1, round(rng.normal(cy0, H * centre_sigma)))))
                if not domain.valid(cx, cy):
                    continue
                if all(math.hypot(cx - px, cy - py) >= min_spacing
                       for px, py in centres):
                    chosen = (cx, cy)
                    break
            if chosen is None:
                chosen = domain.cells[rng.next_int(0, n)]
            centres.append(chosen)

        per = max(1, int(round(count / len(centres))))
        groups: List[List[Cell]] = []
        total = 0
        for cx, cy in centres:
            if total >= count:
                break
            want = max(1, int(round(rng.normal(per, max(1.0, per * 0.18)))))
            want = min(want, count - total)
            group: List[Cell] = []
            attempts = 0
            cap = want * 60
            while len(group) < want and attempts < cap:
                attempts += 1
                x = int(round(rng.normal(cx, sigma)))
                y = int(round(rng.normal(cy, sigma)))
                if domain.take(x, y):
                    group.append((x, y))
            if group:
                groups.append(group)
                total += len(group)
        return groups


class PoissonDisk(Distribution):
    """Blue-noise sampling: uniformly spread but never closer than ``min_spacing``.

    Rejection (dart-throwing) against a spatial hash. Good enough for the
    counts a map prototype needs and fully deterministic.
    """

    id = "poisson_disk"
    params = ("min_spacing", "max_attempts_per_point")

    def sample_groups(self, rng, domain, count, params):
        if not domain.cells or count <= 0:
            return []
        spacing = max(1.0, domain.length(float(params.get("min_spacing", 4.0))))
        attempts_per = int(params.get("max_attempts_per_point", 60))
        cell_size = max(1.0, spacing / math.sqrt(2.0))
        grid: Dict[Tuple[int, int], List[Cell]] = {}
        n = len(domain.cells)
        out: List[Cell] = []
        r2 = spacing * spacing

        def too_close(x: int, y: int) -> bool:
            gx, gy = int(x / cell_size), int(y / cell_size)
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for px, py in grid.get((gx + ox, gy + oy), ()):
                        dx, dy = px - x, py - y
                        if dx * dx + dy * dy < r2:
                            return True
            return False

        budget = count * attempts_per
        for _ in range(budget):
            if len(out) >= count:
                break
            x, y = domain.cells[rng.next_int(0, n)]
            if domain.taken(x, y) or too_close(x, y):
                continue
            if not domain.take(x, y):
                continue
            grid.setdefault((int(x / cell_size), int(y / cell_size)), []).append((x, y))
            out.append((x, y))
        return [out] if out else []


class GridJitter(Distribution):
    """Regular lattice with per-point jitter -- ordered but not mechanical.

    Useful for planted rows, orchards, minefields, street trees: anything a
    designer wants readable as deliberate rather than wild.
    """

    id = "grid_jitter"
    params = ("spacing", "jitter", "search_radius")

    def sample_groups(self, rng, domain, count, params):
        if not domain.cells or count <= 0:
            return []
        spacing = max(1.0, domain.length(float(params.get("spacing", 8.0))))
        jitter = float(params.get("jitter", 0.35)) * spacing
        # Valid cells are usually a scattered subset of the bbox, so an exact
        # lattice hit rate would be very low. Search a small window around each
        # jittered lattice point instead.
        search = max(1, int(round(spacing * float(params.get("search_radius", 0.7)))))
        x0, y0, x1, y1 = domain.bbox
        out: List[Cell] = []
        gy = float(y0)
        while gy <= y1:
            gx = float(x0)
            while gx <= x1:
                if len(out) >= count:
                    return [out]
                jx = int(round(gx + rng.next_float(-jitter, jitter)))
                jy = int(round(gy + rng.next_float(-jitter, jitter)))
                cell = _claim_near(domain, rng, jx, jy, search)
                if cell is not None:
                    out.append(cell)
                gx += spacing
            gy += spacing
        return [out] if out else []


def _claim_near(domain: Domain, rng: DetRandom, x: int, y: int,
                radius: int) -> Cell | None:
    """Claim the nearest free valid cell to (x, y) within ``radius``.

    Ring order is randomised per ring so the fallback does not bias every
    category toward the same corner of its search window.
    """
    if domain.take(x, y):
        return (x, y)
    for r in range(1, radius + 1):
        ring = [(dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                if max(abs(dx), abs(dy)) == r]
        # Deterministic shuffle: rotate by an RNG offset rather than sorting.
        off = rng.next_int(0, len(ring))
        ring = ring[off:] + ring[:off]
        for dx, dy in ring:
            if domain.take(x + dx, y + dy):
                return (x + dx, y + dy)
    return None


REGISTRY: Dict[str, Distribution] = {
    d.id: d for d in (Uniform(), NormalClusters(), PoissonDisk(), GridJitter())
}


def get_distribution(kind: str) -> Distribution:
    try:
        return REGISTRY[kind]
    except KeyError:
        raise KeyError(
            f"unknown distribution {kind!r}; available: {sorted(REGISTRY)}"
        ) from None


def list_distributions() -> List[Dict[str, str]]:
    return [d.describe() for d in REGISTRY.values()]
