"""Value-noise primitives.

Extracted verbatim from the validated ``island_generator.py`` so terrain shape
behaviour is unchanged. These functions are pure: same inputs => same output,
no RNG state involved (the seed is an explicit argument).
"""

import math
from typing import List, Sequence, Tuple

Basin = Tuple[float, float, float, float]  # cx, cy, radius, depth


def hash2(x: int, y: int, seed: int) -> int:
    h = seed & 0xFFFFFFFF
    h ^= (x * 374761393) & 0xFFFFFFFF
    h ^= (y * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h & 0xFFFFFF


def smooth_noise(x: float, y: float, seed: int) -> float:
    ix = int(math.floor(x))
    iy = int(math.floor(y))
    fx = x - ix
    fy = y - iy
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = hash2(ix, iy, seed) / 16777215.0
    b = hash2(ix + 1, iy, seed) / 16777215.0
    c = hash2(ix, iy + 1, seed) / 16777215.0
    d = hash2(ix + 1, iy + 1, seed) / 16777215.0
    ab = a + (b - a) * fx
    cd = c + (d - c) * fx
    return ab + (cd - ab) * fy


def fbm(x: float, y: float, seed: int, octaves: int, persistence: float,
        lacunarity: float) -> float:
    amp, freq, s, norm = 1.0, 1.0, 0.0, 0.0
    for o in range(octaves):
        s += amp * smooth_noise(x * freq, y * freq, seed + o * 1013)
        norm += amp
        amp *= persistence
        freq *= lacunarity
    return s / norm


def ridged(x: float, y: float, seed: int, octaves: int, persistence: float,
           lacunarity: float) -> float:
    amp, freq, s, norm = 1.0, 1.0, 0.0, 0.0
    for o in range(octaves):
        n = smooth_noise(x * freq, y * freq, seed + o * 2017)
        n = 1.0 - abs(n * 2.0 - 1.0)
        n = n * n
        s += amp * n
        norm += amp
        amp *= persistence
        freq *= lacunarity
    return s / norm


def valley_carve(u: float, v: float, basins: Sequence[Basin]) -> float:
    val = 1.0
    for cx, cy, r, depth in basins:
        dx = u - cx
        dy = v - cy
        d2 = dx * dx + dy * dy
        r2 = r * r
        falloff = max(0.0, 1.0 - d2 / r2)
        falloff = falloff * falloff * (3 - 2 * falloff)
        val -= falloff * depth
    return max(0.0, val)


def smooth_step(a: float, b: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)
