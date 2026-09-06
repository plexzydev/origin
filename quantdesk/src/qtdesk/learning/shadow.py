"""
MODO SOMBRA.

Toda mejora detectada corre primero EN PARALELO, sin dinero, registrando que
habria hecho. Pasa a produccion solo si supera al sistema vigente con muestra
suficiente.

Por que existe: la tentacion de aplicar una mejora "obvia" directo a
produccion es enorme y casi siempre esta mal. El modo sombra convierte
"esto deberia andar mejor" en "esto anduvo mejor durante N operaciones", que
es una afirmacion distinta y verificable.

Lo que el modo sombra NO resuelve: si la variante sombra y la de produccion
comparten el mismo sesgo (por ejemplo, ambas leen la misma serie contaminada),
correr en paralelo no lo detecta. Por eso la comparacion se hace tambien
contra un benchmark pasivo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..stats import bootstrap_ci, t_pvalue_two_sided, t_statistic


@dataclass(slots=True)
class ShadowRun:
    """Una variante corriendo en paralelo, sin dinero."""
    name: str
    description: str
    started_at: datetime
    r_multiples: list[float] = field(default_factory=list)
    decisions: int = 0
    trades: int = 0
    diverged_from_production: int = 0

    def record(self, r_multiple: float, diverged: bool) -> None:
        self.r_multiples.append(r_multiple)
        self.trades += 1
        if diverged:
            self.diverged_from_production += 1

    @property
    def expectancy(self) -> float:
        return sum(self.r_multiples) / len(self.r_multiples) if self.r_multiples else 0.0


@dataclass(frozen=True, slots=True)
class PromotionVerdict:
    promote: bool
    reason: str
    n: int
    shadow_expectancy: float
    production_expectancy: float
    p_value: float | None
    ci: tuple[float, float] | None


def evaluate_promotion(
    shadow: ShadowRun,
    production_r: list[float],
    *,
    min_samples: int = 30,
    alpha: float = 0.05,
) -> PromotionVerdict:
    """
    Decide si la variante sombra reemplaza a produccion.

    Tres condiciones, todas necesarias:
      1. muestra suficiente en AMBAS
      2. mejor expectativa
      3. diferencia estadisticamente significativa
    """
    n = min(len(shadow.r_multiples), len(production_r))
    se = shadow.expectancy
    pe = sum(production_r) / len(production_r) if production_r else 0.0

    if n < min_samples:
        return PromotionVerdict(
            False,
            f"muestra insuficiente: {n} operaciones comparables (minimo {min_samples}). "
            "La sombra sigue corriendo.",
            n, se, pe, None, None,
        )
    diff = [s - p for s, p in zip(shadow.r_multiples[:n], production_r[:n])]
    t = t_statistic(diff)
    p = t_pvalue_two_sided(t[0], t[1]) if t else None
    ci = bootstrap_ci(diff)

    if se <= pe:
        return PromotionVerdict(
            False, f"la sombra ({se:+.3f}R) NO supera a produccion ({pe:+.3f}R)",
            n, se, pe, p, ci,
        )
    if p is None or p >= alpha:
        pv = f"p={p:.4f}" if p is not None else "p no calculable"
        return PromotionVerdict(
            False,
            f"la sombra rinde mas ({se:+.3f}R vs {pe:+.3f}R) pero la diferencia NO es "
            f"significativa ({pv}). Es exactamente el caso en el que uno se convence de "
            "una mejora que no existe: la diferencia entra dentro del ruido de la muestra.",
            n, se, pe, p, ci,
        )

    ci_txt = f", IC95%=[{ci[0]:+.3f}, {ci[1]:+.3f}]" if ci else ""
    return PromotionVerdict(
        True,
        f"PROMOVER: sombra {se:+.3f}R vs produccion {pe:+.3f}R sobre {n} operaciones "
        f"comparables, p={p:.4f}{ci_txt}",
        n, se, pe, p, ci,
    )


@dataclass(slots=True)
class ShadowRegistry:
    runs: dict[str, ShadowRun] = field(default_factory=dict)

    def start(self, name: str, description: str, now: datetime) -> ShadowRun:
        if name in self.runs:
            return self.runs[name]
        r = ShadowRun(name, description, now)
        self.runs[name] = r
        return r

    def summary(self) -> str:
        if not self.runs:
            return "sin variantes en modo sombra"
        return "\n".join(
            f"  {r.name}: {r.trades} operaciones, expectativa {r.expectancy:+.3f}R, "
            f"divergio de produccion {r.diverged_from_production} veces -- {r.description}"
            for r in self.runs.values()
        )
