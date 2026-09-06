"""
Gobernador de frecuencia.

Resuelve una tension real del mandato: la REGLA MADRE dice que el default es
no operar, y al mismo tiempo hay un objetivo de ~10 operaciones por mes.

Ambas cosas conviven si y solo si se separan dos palancas distintas:

  PALANCA A (gratis)  : mas candidatos. 146 simbolos en vez de 15. La exigencia
                        por candidato no se mueve ni un punto.
  PALANCA B (se paga) : bajar el umbral de conviccion cuando la cuota va
                        atrasada. Esto SI empeora la calidad promedio.

Este modulo implementa B con tres candados:
  1. Nunca perfora `never_below_score`.
  2. Nunca toca vetos, riesgo por trade, ratio 1:3 ni cortafuegos.
  3. Todo trade abierto bajo umbral aflojado queda marcado FORZADO_POR_CUOTA,
     con tamano reducido, y se mide por separado en los informes.

El punto 3 es lo importante: convierte "creo que operar mas es mejor" en una
hipotesis con datos. A los 30 trades forzados, el informe dice si la cuota
suma o resta, y ahi se decide con numeros y no con ganas.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..config import FrequencyPolicy


def _weekdays_in_month(d: date) -> int:
    total = monthrange(d.year, d.month)[1]
    return sum(1 for i in range(1, total + 1) if date(d.year, d.month, i).weekday() < 5)


def _weekdays_elapsed(d: date) -> int:
    return sum(1 for i in range(1, d.day + 1) if date(d.year, d.month, i).weekday() < 5)


def _weekdays_between(a: date, b: date) -> int:
    if b <= a:
        return 0
    n, cur = 0, a
    while cur < b:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


@dataclass(slots=True)
class FrequencyState:
    """Estado observado. Lo alimenta el motor con los trades realmente abiertos."""
    trades_this_week: int = 0
    trades_this_month: int = 0
    last_trade_date: date | None = None
    week_anchor: date | None = None
    month_anchor: date | None = None
    forced_trades_this_month: int = 0

    def register_trade(self, when: date, forced: bool) -> None:
        self.trades_this_week += 1
        self.trades_this_month += 1
        if forced:
            self.forced_trades_this_month += 1
        self.last_trade_date = when

    def roll(self, today: date) -> None:
        """Reinicia contadores al cambiar de semana o de mes."""
        monday = today - timedelta(days=today.weekday())
        if self.week_anchor != monday:
            self.week_anchor = monday
            self.trades_this_week = 0
        first = today.replace(day=1)
        if self.month_anchor != first:
            self.month_anchor = first
            self.trades_this_month = 0
            self.forced_trades_this_month = 0


@dataclass(frozen=True, slots=True)
class FrequencyVerdict:
    effective_threshold: float
    base_threshold: float
    easing_points: float
    behind_by: float             # trades de atraso respecto del ritmo objetivo
    days_since_last_trade: int
    ceiling_hit: bool            # techo semanal alcanzado -> veto de sobreoperacion
    size_multiplier: float       # 1.0 organico, <1 si va forzado
    note: str

    @property
    def is_easing(self) -> bool:
        return self.easing_points > 1e-9


@dataclass(slots=True)
class FrequencyGovernor:
    policy: FrequencyPolicy
    state: FrequencyState = field(default_factory=FrequencyState)

    def evaluate(self, as_of: datetime, base_threshold: float) -> FrequencyVerdict:
        today = as_of.date()
        self.state.roll(today)

        ceiling_hit = self.state.trades_this_week >= self.policy.hard_ceiling_per_week

        # Ritmo esperado a esta altura del mes.
        elapsed = _weekdays_elapsed(today)
        total = _weekdays_in_month(today)
        target = float(self.policy.quota_floor_per_month)
        expected_by_now = target * (elapsed / total) if total else 0.0
        behind_by = max(0.0, expected_by_now - self.state.trades_this_month)

        days_since = (
            _weekdays_between(self.state.last_trade_date, today)
            if self.state.last_trade_date else self.policy.slack_days_before_easing
        )

        if not self.policy.quota_mode:
            return FrequencyVerdict(
                base_threshold, base_threshold, 0.0, behind_by, days_since,
                ceiling_hit, 1.0,
                "quota_mode apagado: el umbral no se mueve, se opera lo que el mercado ofrezca",
            )

        # Atraso efectivo: el mayor entre "faltan trades para el ritmo" y
        # "hace demasiados dias que no opero".
        drought = max(0, days_since - self.policy.slack_days_before_easing)
        lag_units = max(behind_by, float(drought))
        raw_ease = self.policy.ease_per_lagging_day * lag_units
        max_ease = max(0.0, base_threshold - self.policy.never_below_score)
        easing = min(raw_ease, max_ease)
        effective = base_threshold - easing

        if easing <= 0:
            note = "al dia con el ritmo objetivo: exigencia plena"
            mult = 1.0
        elif effective <= self.policy.never_below_score + 1e-9:
            note = (
                f"atraso de {lag_units:.1f} unidades; umbral en el PISO DURO "
                f"{self.policy.never_below_score:.0f}. Por debajo de aca no se baja "
                "aunque el mes cierre en cero."
            )
            mult = self.policy.forced_trade_size_multiplier
        else:
            note = (
                f"atraso de {lag_units:.1f}; umbral {base_threshold:.0f} -> "
                f"{effective:.0f}. Trade marcado FORZADO_POR_CUOTA, tamano al "
                f"{self.policy.forced_trade_size_multiplier:.0%}."
            )
            mult = self.policy.forced_trade_size_multiplier

        if ceiling_hit:
            note = f"TECHO SEMANAL ALCANZADO ({self.state.trades_this_week}); la cuota no lo levanta. " + note

        return FrequencyVerdict(
            effective_threshold=effective,
            base_threshold=base_threshold,
            easing_points=easing,
            behind_by=behind_by,
            days_since_last_trade=days_since,
            ceiling_hit=ceiling_hit,
            size_multiplier=mult,
            note=note,
        )

    def pace_report(self, as_of: datetime) -> dict[str, float]:
        today = as_of.date()
        elapsed, total = _weekdays_elapsed(today), _weekdays_in_month(today)
        return {
            "trades_mes": float(self.state.trades_this_month),
            "forzados_mes": float(self.state.forced_trades_this_month),
            "objetivo_mes": float(self.policy.quota_floor_per_month),
            "ritmo_esperado_hoy": self.policy.quota_floor_per_month * (elapsed / total) if total else 0.0,
            "trades_semana": float(self.state.trades_this_week),
            "techo_semana": float(self.policy.hard_ceiling_per_week),
        }
