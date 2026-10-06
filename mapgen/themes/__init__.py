"""Theme registry.

A theme is the deterministic tier: it declares the biome vocabulary, the
terrain parameters, the categories available under it, and the contract the
finished map must satisfy. Adding a theme = adding a module here and one line
to ``REGISTRY``; nothing else in the pipeline changes.
"""

from __future__ import annotations

from typing import Dict, List

from ..schema import ThemeSpec
from . import island, snow

REGISTRY: Dict[str, ThemeSpec] = {t.id: t for t in (snow.THEME, island.THEME)}


def get_theme(theme_id: str) -> ThemeSpec:
    try:
        return REGISTRY[theme_id]
    except KeyError:
        raise KeyError(
            f"unknown theme {theme_id!r}; available: {sorted(REGISTRY)}"
        ) from None


def list_themes() -> List[Dict[str, object]]:
    return [
        {
            "id": t.id,
            "display_name": t.display_name,
            "description": t.description,
            "biomes": [b.key for b in t.biomes],
            "categories": [c.id for c in t.categories],
            "forbidden_biomes": list(t.forbidden_biomes),
            "checks": len(t.contract),
        }
        for t in REGISTRY.values()
    ]
