"""
Integridad del feed de datos.

Veto de CAPA 0: "feed con retraso, huecos o valores anomalos -> afuera".

Por que esto es un veto y no un warning: un feed roto no produce senales
malas, produce senales SIN SENTIDO, y el sistema no tiene forma de saber que
son sin sentido. Un precio congelado se ve identico a un mercado sin
movimiento. Un hueco de dos dias se ve identico a un fin de semana. La unica
respuesta segura es no operar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from statistics import median, pstdev

from ..contracts import Severity
from .bars import SignalView
from .calendar import TradingCalendar


@dataclass(frozen=True, slots=True)
class DataIssue:
    code: str
    detail: str
    severity: Severity


@dataclass(frozen=True, slots=True)
class FeedHealth:
    symbol: str
    ok: bool
    issues: tuple[DataIssue, ...]
    bars_checked: int

    @property
    def blocking(self) -> tuple[DataIssue, ...]:
        return tuple(i for i in self.issues if i.severity.rank >= Severity.HIGH.rank)


def check_feed(
    view: SignalView,
    as_of: datetime,
    cal: TradingCalendar,
    *,
    max_staleness_sessions: int = 1,
    max_gap_sessions: int = 2,
    anomaly_sigma: float = 8.0,
    min_bars: int = 60,
    lookback: int = 120,
) -> FeedHealth:
    """
    Revisa la ventana visible. Nunca mira mas alla de `as_of` porque recibe
    una SignalView, no la serie cruda.
    """
    issues: list[DataIssue] = []
    bars = view.window(lookback)

    if len(bars) < min_bars:
        issues.append(DataIssue(
            "HISTORIA_INSUFICIENTE",
            f"{len(bars)} barras disponibles, se necesitan {min_bars}. "
            "Sin historia no hay estadistica, y sin estadistica no hay senal.",
            Severity.HIGH,
        ))
        return FeedHealth(view.symbol, False, tuple(issues), len(bars))

    # -- 1. Retraso del feed ------------------------------------------------
    last = bars[-1]
    stale = cal.sessions_between(last.ts.date(), as_of.date())
    if stale > max_staleness_sessions:
        issues.append(DataIssue(
            "FEED_ATRASADO",
            f"ultima barra {last.ts.date()}, as_of {as_of.date()}: {stale} sesiones de atraso",
            Severity.CRITICAL,
        ))

    # -- 2. Huecos en la serie ----------------------------------------------
    worst_gap, worst_at = 0, None
    for prev, cur in zip(bars, bars[1:]):
        gap = cal.sessions_between(prev.ts.date(), cur.ts.date())
        if gap > worst_gap:
            worst_gap, worst_at = gap, cur.ts.date()
    if worst_gap > max_gap_sessions:
        issues.append(DataIssue(
            "HUECO_EN_SERIE",
            f"{worst_gap} sesiones sin dato antes de {worst_at}",
            Severity.HIGH,
        ))

    # -- 3. Valores anomalos ------------------------------------------------
    rets = [math.log(c.close / p.close) for p, c in zip(bars, bars[1:]) if p.close > 0]
    if len(rets) >= 30:
        sd = pstdev(rets)
        if sd > 0:
            extremes = [(b.ts.date(), r) for b, r in zip(bars[1:], rets) if abs(r) > anomaly_sigma * sd]
            if extremes:
                d, r = max(extremes, key=lambda x: abs(x[1]))
                issues.append(DataIssue(
                    "RETORNO_ANOMALO",
                    f"{d}: retorno {r:+.2%} = {abs(r)/sd:.1f} sigmas. "
                    "Puede ser un split no ajustado, un mal tick o un evento real; "
                    "el sistema no puede distinguirlos, asi que se abstiene.",
                    Severity.HIGH,
                ))

    # -- 4. Feed congelado --------------------------------------------------
    frozen = 0
    for prev, cur in zip(bars[-10:], bars[-9:]):
        if cur.close == prev.close and cur.high == prev.high and cur.low == prev.low:
            frozen += 1
    if frozen >= 3:
        issues.append(DataIssue(
            "FEED_CONGELADO",
            f"{frozen} barras identicas consecutivas: el proveedor esta repitiendo el ultimo valor",
            Severity.CRITICAL,
        ))

    # -- 5. Volumen ausente -------------------------------------------------
    zero_vol = sum(1 for b in bars[-20:] if b.volume <= 0)
    if zero_vol >= 3:
        issues.append(DataIssue(
            "VOLUMEN_AUSENTE",
            f"{zero_vol} de las ultimas 20 barras sin volumen: no se puede validar liquidez ni rupturas",
            Severity.HIGH,
        ))

    # -- 6. Salto de precio sin volumen (posible split no ajustado) ---------
    if len(bars) >= 2:
        med_vol = median([b.volume for b in bars[-40:]]) or 1.0
        for prev, cur in zip(bars[-20:], bars[-19:]):
            jump = abs(cur.close / prev.close - 1.0) if prev.close else 0.0
            if jump > 0.35 and cur.volume < med_vol * 1.5:
                issues.append(DataIssue(
                    "POSIBLE_SPLIT_NO_AJUSTADO",
                    f"{cur.ts.date()}: salto de {jump:.0%} sin volumen extraordinario",
                    Severity.CRITICAL,
                ))
                break

    ok = not any(i.severity.rank >= Severity.HIGH.rank for i in issues)
    return FeedHealth(view.symbol, ok, tuple(issues), len(bars))
