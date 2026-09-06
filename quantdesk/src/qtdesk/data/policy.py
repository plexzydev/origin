"""
Eventos politicos, regulatorios y de tratados.

La regla del mandato es la que estructura todo este modulo:

    "el mercado ya tiene precio para lo esperado. Lo que mueve es la SORPRESA.
     Modela la diferencia entre consenso y hecho, nunca el evento en si.
     Y los tratados se descuentan cuando se rumorean, no cuando se firman."

Traducido a codigo: cada evento tiene CUATRO tiempos distintos y el valor
informativo vive entre el primero y el segundo, no en el tercero.

    rumored_at   -> empieza a circular. ACA se mueve el precio.
    announced_at -> se anuncia oficialmente. El precio ya lo tiene.
    effective_at -> entra en vigencia. Normalmente no mueve nada.
    outcome_known_at -> se sabe si pasó o no. Sirve para medir la sorpresa.

`unpriced_impact()` implementa exactamente eso: devuelve la parte del impacto
que el mercado TODAVIA no descontó, y decae a cero despues del anuncio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum


class PolicyKind(str, Enum):
    ELECTION = "ELECCION"
    REGULATION = "REGULACION"
    ANTITRUST = "ANTIMONOPOLIO"
    TARIFF = "ARANCEL"
    EXPORT_CONTROL = "CONTROL_DE_EXPORTACION"
    TREATY = "TRATADO"
    SANCTION = "SANCION"
    GEOPOLITICS = "GEOPOLITICA"
    FISCAL = "POLITICA_FISCAL"
    SUPPLY_CHAIN = "CUELLO_DE_BOTELLA"


@dataclass(frozen=True, slots=True)
class PolicyEvent:
    kind: PolicyKind
    description: str
    sectors: tuple[str, ...] = ()          # sectores afectados; () = todo el mercado
    regions: tuple[str, ...] = ("US",)
    rumored_at: datetime | None = None
    announced_at: datetime | None = None
    effective_at: date | None = None
    # Probabilidad que el mercado le asignaba ANTES del anuncio (0..1).
    # Si es None, el sistema no puede medir sorpresa y lo dice.
    consensus_prob: float | None = None
    outcome: bool | None = None
    outcome_known_at: datetime | None = None
    impact_sign: int = -1                  # -1 adverso, +1 favorable al sector
    magnitude: float = 0.5                 # 0..1, severidad estimada
    # Cuantos dias tarda el mercado en digerir el anuncio.
    decay_days: int = 20

    def known_at(self, as_of: datetime) -> bool:
        """Existe para el sistema recien cuando empieza a circular."""
        first = self.rumored_at or self.announced_at
        return first is not None and first <= as_of

    def phase(self, as_of: datetime) -> str:
        if not self.known_at(as_of):
            return "DESCONOCIDO"
        if self.announced_at is None or as_of < self.announced_at:
            return "RUMOR"
        if self.effective_at and as_of.date() >= self.effective_at:
            return "VIGENTE"
        return "ANUNCIADO"

    def unpriced_impact(self, as_of: datetime) -> float:
        """
        Impacto que el mercado TODAVIA no descontó, en [-1, 1].

        Fase RUMOR      -> impacto * (1 - probabilidad ya descontada). Es donde
                           hay informacion aprovechable.
        Fase ANUNCIADO  -> decae linealmente en `decay_days`. El grueso ya
                           se movio; queda el ajuste fino.
        Fase VIGENTE    -> cero. La entrada en vigencia de algo anunciado hace
                           meses no mueve precios, y modelarlo como si lo
                           hiciera es el error clasico de esta capa.
        """
        ph = self.phase(as_of)
        if ph in ("DESCONOCIDO", "VIGENTE"):
            return 0.0
        base = self.impact_sign * self.magnitude
        if ph == "RUMOR":
            priced = self.consensus_prob if self.consensus_prob is not None else 0.5
            return base * (1.0 - priced)
        days = (as_of - self.announced_at).days
        return base * max(0.0, 1.0 - days / max(1, self.decay_days)) * 0.4

    def surprise(self, as_of: datetime) -> float | None:
        """
        Sorpresa realizada = (ocurrio ? 1 : 0) - probabilidad de consenso.
        Solo disponible despues de conocerse el resultado. Sin consenso
        cargado devuelve None: no se puede medir sorpresa contra nada.
        """
        if self.outcome is None or self.consensus_prob is None:
            return None
        if self.outcome_known_at is None or self.outcome_known_at > as_of:
            return None
        return (1.0 if self.outcome else 0.0) - self.consensus_prob

    def affects(self, sector: str) -> bool:
        return not self.sectors or sector in self.sectors


@dataclass(slots=True)
class PolicyCalendar:
    events: list[PolicyEvent] = field(default_factory=list)

    def add(self, e: PolicyEvent) -> None:
        self.events.append(e)

    def active(self, as_of: datetime, sector: str, horizon_days: int = 120) -> list[PolicyEvent]:
        """Eventos conocidos, relevantes al sector, con impacto no descontado."""
        out = []
        for e in self.events:
            if not e.known_at(as_of) or not e.affects(sector):
                continue
            if e.effective_at and as_of.date() > e.effective_at + timedelta(days=horizon_days):
                continue
            out.append(e)
        return out

    def realized_surprises(self, as_of: datetime, sector: str, lookback_days: int = 90) -> list[tuple[PolicyEvent, float]]:
        cut = as_of - timedelta(days=lookback_days)
        out = []
        for e in self.events:
            if not e.affects(sector):
                continue
            s = e.surprise(as_of)
            if s is not None and e.outcome_known_at and e.outcome_known_at >= cut:
                out.append((e, s))
        return out
