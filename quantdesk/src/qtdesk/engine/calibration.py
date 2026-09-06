"""
Calibracion del umbral de conviccion.

El problema que resuelve: un umbral absoluto sobre una escala inventada
("score combinado >= 55") no significa nada hasta que se sabe como se
distribuyen los scores que el sistema produce de verdad. Si los scores
tipicos viven entre -30 y +30, un umbral de 55 no es "exigente": es
"apagado". Y si viven entre -90 y +90, es "cualquier cosa pasa".

La solucion es expresar la exigencia donde SI tiene sentido: en el PERCENTIL.
"Solo se opera el 3% mejor de las senales que este sistema genera" es una
definicion operativa de umbral exigente. "55" es un numero magico.

CUIDADO CON EL LOOK-AHEAD: el percentil se calcula UNICAMENTE con scores
observados ANTES de la decision actual. Calibrar con la muestra completa
seria mirar el futuro, y ademas garantizaria por construccion que el 3% de
los dias opera -- incluso en un mercado donde no habia nada que operar.
Por eso la ventana es movil y estrictamente pasada, y ademas existe un PISO
ABSOLUTO por debajo del cual el percentil no habilita nada.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ConvictionCalibrator:
    """Ventana movil de scores pasados. Nunca ve el presente ni el futuro."""
    percentile: float = 0.97
    window: int = 2000
    warmup: int = 250
    absolute_floor: float = 38.0
    _obs: deque[float] = field(default_factory=lambda: deque(maxlen=2000))
    _last_ts: datetime | None = None

    def __post_init__(self) -> None:
        self._obs = deque(maxlen=self.window)

    def observe(self, ts: datetime, combined_score: float) -> None:
        """
        Registra un score YA UTILIZADO para decidir. Se llama DESPUES de
        calcular el umbral, nunca antes: si se observara primero, el score
        de hoy influiria en su propio umbral.
        """
        if self._last_ts is not None and ts < self._last_ts:
            raise ValueError("calibrador alimentado fuera de orden temporal")
        self._last_ts = ts
        self._obs.append(abs(combined_score))

    def threshold(self, base: float) -> tuple[float, str]:
        """
        Umbral vigente y su explicacion.

        Durante el warmup manda el umbral absoluto configurado: no se puede
        calibrar un percentil con 40 observaciones.
        """
        if len(self._obs) < self.warmup:
            return base, (
                f"umbral absoluto {base:.0f} (calibrador en warmup: "
                f"{len(self._obs)}/{self.warmup} observaciones)"
            )
        ordered = sorted(self._obs)
        idx = min(len(ordered) - 1, int(self.percentile * len(ordered)))
        calibrated = ordered[idx]
        effective = max(calibrated, self.absolute_floor)
        return effective, (
            f"umbral calibrado en el percentil {self.percentile:.0%} de las ultimas "
            f"{len(ordered)} senales = {calibrated:.1f}"
            + (f", elevado al piso absoluto {self.absolute_floor:.0f}" if effective > calibrated else "")
            + f" (mediana historica {ordered[len(ordered)//2]:.1f})"
        )

    def percentile_of(self, score: float) -> float | None:
        """
        En que percentil cae |score| dentro de lo que este sistema suele
        producir. Es la base para medir CONVICCION de forma consistente con
        el umbral: si el umbral es relativo, la conviccion tambien debe serlo.
        """
        if len(self._obs) < self.warmup:
            return None
        v = abs(score)
        below = sum(1 for o in self._obs if o < v)
        return below / len(self._obs)

    @property
    def n_observations(self) -> int:
        return len(self._obs)

    def snapshot(self) -> dict[str, float]:
        if not self._obs:
            return {}
        o = sorted(self._obs)
        return {
            "n": float(len(o)),
            "mediana": o[len(o) // 2],
            "p90": o[int(0.90 * len(o))],
            "p97": o[min(len(o) - 1, int(0.97 * len(o)))],
            "max": o[-1],
        }
