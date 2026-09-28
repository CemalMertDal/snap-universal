"""Vanish effects. Each module registers one Effect subclass on import."""
import numpy as np

from snap.effects.base import EFFECTS, Effect, EffectContext, register  # noqa: F401

ORDER = ["cloud", "dust", "burn", "vortex", "melt", "glitch", "beam"]
RANDOM_ID = "random"
DEFAULT_ID = "cloud"

# Static imports on purpose: they register the effects and let PyInstaller see them.
from snap.effects import beam, burn, cloud, dust, glitch, melt, vortex  # noqa: E402,F401


def effect_ids() -> list[str]:
    return [i for i in ORDER if i in EFFECTS]


def get_effect(effect_id: str) -> Effect:
    return EFFECTS[effect_id]()


def resolve_effect(effect_id: str, rng: np.random.Generator | None = None) -> str:
    ids = effect_ids()
    if effect_id == RANDOM_ID and ids:
        rng = rng or np.random.default_rng()
        return ids[int(rng.integers(len(ids)))]
    if effect_id in ids:
        return effect_id
    return DEFAULT_ID if DEFAULT_ID in ids else (ids[0] if ids else DEFAULT_ID)
