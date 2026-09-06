"""
CAPA 4 - POLITICO, REGULATORIO, TRATADOS.

Es la capa mas facil de hacer mal, por dos razones:

 1. Tentacion de puntuar el EVENTO en vez de la SORPRESA. Que haya elecciones
    no es informacion: la fecha se sabe hace cuatro anios. Lo que mueve es la
    diferencia entre lo que se esperaba y lo que pasó.

 2. Sesgo de retrospectiva brutal. Es imposible leer "aranceles a China 2018"
    sin saber como terminó. Por eso esta capa NO acepta texto libre ni juicio
    del modelo: solo consume `PolicyEvent` con fechas explicitas, y el calculo
    de impacto no descontado es aritmetica, no opinion.

Si no hay consenso cargado para un evento, la capa lo dice y no lo puntua.
Un evento sin consenso es un evento del que no se puede medir la sorpresa.
"""
from __future__ import annotations

from statistics import fmean

from ..contracts import LayerId, LayerScore
from ..data.policy import PolicyCalendar, PolicyKind
from ..stats import clamp
from .base import Layer, MarketContext, blend


class PolicyLayer(Layer):
    layer_id = LayerId.POLICY

    def __init__(self, calendar: PolicyCalendar | None = None) -> None:
        self.calendar = calendar or PolicyCalendar()

    def evaluate(self, ctx: MarketContext) -> LayerScore:
        if not self.calendar.events:
            return self.abstain(
                "sin calendario politico cargado. La capa NO estima riesgo "
                "regulatorio a partir del precio: eso seria duplicar la CAPA 1 "
                "y llamarlo analisis politico."
            )

        active = self.calendar.active(ctx.as_of, ctx.sector)
        if not active:
            return self.emit(
                0.0, 0.4,
                f"sin eventos politicos o regulatorios activos para {ctx.sector} "
                f"al {ctx.as_of.date()}. Neutral por ausencia, no por analisis.",
                {"eventos_activos": 0.0},
            )

        notes: list[str] = []
        by_kind: dict[str, list[float]] = {}
        no_consensus = 0

        for e in active:
            imp = e.unpriced_impact(ctx.as_of)
            phase = e.phase(ctx.as_of)
            if e.consensus_prob is None and phase == "RUMOR":
                no_consensus += 1
            if abs(imp) < 1e-9:
                continue
            by_kind.setdefault(e.kind.value, []).append(imp * 100.0)
            notes.append(
                f"[{phase}] {e.kind.value}: {e.description} -> impacto no descontado {imp:+.2f}"
            )

        # Sorpresas ya realizadas: memoria corta de como reaccionó el sector.
        realized = self.calendar.realized_surprises(ctx.as_of, ctx.sector)
        surprise_score = None
        if realized:
            vals = [s * e.impact_sign * e.magnitude * 100.0 for e, s in realized]
            surprise_score = clamp(fmean(vals))
            notes.append(
                f"{len(realized)} sorpresas resueltas en 90 dias, promedio {surprise_score:+.0f} "
                "(consenso vs hecho, no el evento en si)"
            )

        parts = [
            ("regulatorio", _avg(by_kind, PolicyKind.REGULATION.value, PolicyKind.ANTITRUST.value), 1.4),
            ("comercio", _avg(by_kind, PolicyKind.TARIFF.value, PolicyKind.EXPORT_CONTROL.value), 1.3),
            ("tratados", _avg(by_kind, PolicyKind.TREATY.value), 1.0),
            ("geopolitica", _avg(by_kind, PolicyKind.GEOPOLITICS.value, PolicyKind.SANCTION.value,
                                 PolicyKind.SUPPLY_CHAIN.value), 1.2),
            ("fiscal", _avg(by_kind, PolicyKind.FISCAL.value), 1.0),
            ("electoral", _avg(by_kind, PolicyKind.ELECTION.value), 0.8),
            ("sorpresas_resueltas", surprise_score, 1.1),
        ]
        score, coverage, _ = blend(parts)

        warns = []
        if no_consensus:
            warns.append("EVENTOS_SIN_CONSENSO")
            notes.append(
                f"{no_consensus} evento(s) en fase de rumor SIN consenso cargado: "
                "se asumió 50% descontado por defecto, que es una suposicion, no un dato"
            )

        return self.emit(
            score, coverage,
            f"{len(active)} evento(s) activos para {ctx.sector}. " + " | ".join(notes[:8]),
            {"eventos_activos": float(len(active)), "sorpresas": float(len(realized))},
            warns,
        )


def _avg(by_kind: dict[str, list[float]], *kinds: str) -> float | None:
    vals = [v for k in kinds for v in by_kind.get(k, [])]
    return clamp(fmean(vals)) if vals else None
