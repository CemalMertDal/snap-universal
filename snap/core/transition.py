from dataclasses import dataclass

from snap.effects.base import Effect, ease_in_out_cubic


@dataclass
class Transition:
    effect: Effect
    effect_id: str
    duration: float
    vanish: bool
    start: float

    def p(self, now: float) -> float:
        t = (now - self.start) / max(self.duration, 1e-6)
        e = ease_in_out_cubic(t)
        return e if self.vanish else 1.0 - e

    def done(self, now: float) -> bool:
        return now - self.start >= self.duration
