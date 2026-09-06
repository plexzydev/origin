"""
Metricas. Con enfasis deliberado en las PERDIDAS.

El mandato es explicito: "Reporta SIEMPRE las perdidas: peor mes, peor racha,
max drawdown". Por eso este modulo calcula primero el dano y despues el
rendimiento, y el reporte de texto los muestra en ese orden.

Nota sobre el Sharpe: se reporta pero se desconfia. El Sharpe castiga la
volatilidad al alza igual que a la baja y asume retornos normales, que no lo
son. El CALMAR (retorno sobre max drawdown) y la DURACION del drawdown dicen
mucho mas sobre si una estrategia es operable por un humano.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from statistics import fmean, pstdev

from ..stats import max_drawdown


@dataclass(frozen=True, slots=True)
class DrawdownInfo:
    max_dd: float
    peak_ts: datetime | None
    trough_ts: datetime | None
    recovery_ts: datetime | None
    duration_sessions: int
    underwater_sessions: int      # ruedas totales por debajo del maximo previo


@dataclass(frozen=True, slots=True)
class Metrics:
    # -- perdidas primero --------------------------------------------------
    max_drawdown: float
    drawdown_duration_sessions: int
    underwater_fraction: float
    worst_month: float
    worst_trade_r: float
    longest_losing_streak: int
    # -- rendimiento -------------------------------------------------------
    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    calmar: float
    # -- calidad de las operaciones ---------------------------------------
    n_trades: int
    win_rate: float
    profit_factor: float
    expectancy_r: float
    avg_win_r: float
    avg_loss_r: float
    payoff_ratio: float
    # -- distribucion ------------------------------------------------------
    return_p05: float
    return_p50: float
    return_p95: float
    skew: float
    kurtosis: float
    # -- desagregados ------------------------------------------------------
    by_regime: dict[str, dict[str, float]] = field(default_factory=dict)
    by_conviction: dict[int, dict[str, float]] = field(default_factory=dict)
    monthly: dict[str, float] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


def compute(equity_curve, trades, *, periods_per_year: int = 252) -> Metrics:
    if len(equity_curve) < 2:
        raise ValueError("curva de capital insuficiente")
    ts = [t for t, _ in equity_curve]
    eq = [v for _, v in equity_curve]

    rets = [(b / a - 1.0) for a, b in zip(eq, eq[1:]) if a > 0]
    total = eq[-1] / eq[0] - 1.0
    years = max((ts[-1] - ts[0]).days / 365.25, 1e-9)
    cagr = (eq[-1] / eq[0]) ** (1 / years) - 1.0 if eq[0] > 0 else 0.0

    dd_info = _drawdown(ts, eq)

    sd = pstdev(rets) if len(rets) > 1 else 0.0
    mean_r = fmean(rets) if rets else 0.0
    sharpe = (mean_r / sd * math.sqrt(periods_per_year)) if sd > 0 else 0.0
    downside = [r for r in rets if r < 0]
    dsd = pstdev(downside) if len(downside) > 1 else 0.0
    sortino = (mean_r / dsd * math.sqrt(periods_per_year)) if dsd > 0 else 0.0
    calmar = (cagr / dd_info.max_dd) if dd_info.max_dd > 1e-9 else 0.0

    monthly = _monthly_returns(ts, eq)
    worst_month = min(monthly.values()) if monthly else 0.0

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_w = sum(t.pnl for t in wins)
    gross_l = abs(sum(t.pnl for t in losses))
    pf = gross_w / gross_l if gross_l > 1e-9 else (float("inf") if gross_w > 0 else 0.0)
    rs = [t.r_multiple for t in trades]
    avg_w = fmean([t.r_multiple for t in wins]) if wins else 0.0
    avg_l = fmean([abs(t.r_multiple) for t in losses]) if losses else 0.0

    srt = sorted(rets) if rets else [0.0]
    p05 = srt[int(0.05 * len(srt))]
    p50 = srt[len(srt) // 2]
    p95 = srt[min(len(srt) - 1, int(0.95 * len(srt)))]

    notes: list[str] = []
    if pf == float("inf"):
        notes.append("profit factor infinito: no hubo NINGUNA operacion perdedora. "
                     "Con muestra chica es esperable; con muestra grande es un bug.")
    if len(trades) < 30:
        notes.append(f"SOLO {len(trades)} operaciones: ninguna de estas metricas es "
                     "estadisticamente significativa. Se reportan para inspeccion, no para decidir.")
    if dd_info.max_dd < 0.02 and len(trades) > 10:
        notes.append("drawdown maximo por debajo del 2% con mas de 10 operaciones: "
                     "sospechoso. Revisar que los stops se esten ejecutando.")

    return Metrics(
        max_drawdown=dd_info.max_dd,
        drawdown_duration_sessions=dd_info.duration_sessions,
        underwater_fraction=dd_info.underwater_sessions / max(1, len(eq)),
        worst_month=worst_month,
        worst_trade_r=min(rs) if rs else 0.0,
        longest_losing_streak=_longest_streak(trades),
        total_return=total, cagr=cagr, sharpe=sharpe, sortino=sortino, calmar=calmar,
        n_trades=len(trades),
        win_rate=len(wins) / len(trades) if trades else 0.0,
        profit_factor=pf,
        expectancy_r=fmean(rs) if rs else 0.0,
        avg_win_r=avg_w, avg_loss_r=avg_l,
        payoff_ratio=avg_w / avg_l if avg_l > 1e-9 else 0.0,
        return_p05=p05, return_p50=p50, return_p95=p95,
        skew=_skew(rets), kurtosis=_kurtosis(rets),
        by_regime=_group(trades, lambda t: t.regime),
        by_conviction=_group(trades, lambda t: t.conviction),
        monthly=monthly,
        notes=tuple(notes),
    )


def _drawdown(ts, eq) -> DrawdownInfo:
    dd, pi, ti = max_drawdown(eq)
    peak = eq[0]
    underwater = 0
    for v in eq:
        peak = max(peak, v)
        if v < peak:
            underwater += 1
    rec = None
    if ti < len(eq):
        for k in range(ti, len(eq)):
            if eq[k] >= eq[pi]:
                rec = ts[k]
                break
    dur = (len(eq) - pi) if rec is None else (
        next(k for k in range(ti, len(eq)) if eq[k] >= eq[pi]) - pi
    )
    return DrawdownInfo(dd, ts[pi], ts[ti], rec, dur, underwater)


def _monthly_returns(ts, eq) -> dict[str, float]:
    out: dict[str, float] = {}
    start_v, start_k = eq[0], ts[0].strftime("%Y-%m")
    for t, v in zip(ts, eq):
        k = t.strftime("%Y-%m")
        if k != start_k:
            out[start_k] = v / start_v - 1.0 if start_v else 0.0
            start_v, start_k = v, k
    out[start_k] = eq[-1] / start_v - 1.0 if start_v else 0.0
    return out


def _longest_streak(trades) -> int:
    best = cur = 0
    for t in trades:
        if t.pnl <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _skew(xs) -> float:
    if len(xs) < 3:
        return 0.0
    m, s = fmean(xs), pstdev(xs)
    return 0.0 if s == 0 else fmean([((x - m) / s) ** 3 for x in xs])


def _kurtosis(xs) -> float:
    if len(xs) < 4:
        return 0.0
    m, s = fmean(xs), pstdev(xs)
    return 0.0 if s == 0 else fmean([((x - m) / s) ** 4 for x in xs]) - 3.0


def _group(trades, key) -> dict:
    out: dict = {}
    for t in trades:
        k = key(t)
        b = out.setdefault(k, {"n": 0, "pnl": 0.0, "wins": 0, "sum_r": 0.0})
        b["n"] += 1
        b["pnl"] += t.pnl
        b["wins"] += 1 if t.pnl > 0 else 0
        b["sum_r"] += t.r_multiple
    for k, b in out.items():
        b["win_rate"] = b["wins"] / b["n"]
        b["expectancy_r"] = b["sum_r"] / b["n"]
    return out


def render(m: Metrics) -> str:
    """Informe de texto. Las perdidas van PRIMERO, a proposito."""
    L = []
    L.append("=" * 66)
    L.append("PERDIDAS  (esto va primero por decision de diseno)")
    L.append("=" * 66)
    L.append(f"  drawdown maximo          {m.max_drawdown:>10.2%}")
    L.append(f"  duracion del drawdown    {m.drawdown_duration_sessions:>10} ruedas")
    L.append(f"  tiempo bajo el maximo    {m.underwater_fraction:>10.1%} de las ruedas")
    L.append(f"  peor mes                 {m.worst_month:>10.2%}")
    L.append(f"  peor operacion           {m.worst_trade_r:>10.2f}R")
    L.append(f"  racha perdedora mas larga{m.longest_losing_streak:>10} operaciones")
    L.append("")
    L.append("RENDIMIENTO")
    L.append(f"  retorno total            {m.total_return:>10.2%}")
    L.append(f"  CAGR                     {m.cagr:>10.2%}")
    L.append(f"  Sharpe                   {m.sharpe:>10.2f}   (castiga la vol al alza; desconfiar)")
    L.append(f"  Sortino                  {m.sortino:>10.2f}")
    L.append(f"  Calmar                   {m.calmar:>10.2f}   (CAGR / max DD: el que importa)")
    L.append("")
    L.append("OPERACIONES")
    L.append(f"  cantidad                 {m.n_trades:>10}")
    L.append(f"  aciertos                 {m.win_rate:>10.1%}")
    L.append(f"  profit factor            {m.profit_factor:>10.2f}")
    L.append(f"  expectativa por trade    {m.expectancy_r:>10.3f}R")
    L.append(f"  ganancia media           {m.avg_win_r:>10.2f}R")
    L.append(f"  perdida media            {m.avg_loss_r:>10.2f}R")
    L.append("")
    L.append("DISTRIBUCION DE RETORNOS DIARIOS")
    L.append(f"  p05 {m.return_p05:+.2%}   mediana {m.return_p50:+.2%}   p95 {m.return_p95:+.2%}")
    L.append(f"  asimetria {m.skew:+.2f}   curtosis {m.kurtosis:+.2f}")
    if m.by_regime:
        L.append("")
        L.append("POR REGIMEN")
        for k, b in sorted(m.by_regime.items()):
            L.append(f"  {k:28} n={b['n']:<4} aciertos {b['win_rate']:>5.0%}  E={b['expectancy_r']:+.2f}R")
    if m.by_conviction:
        L.append("")
        L.append("POR CONVICCION  (si no correlaciona, el sistema no sabe lo que no sabe)")
        for k, b in sorted(m.by_conviction.items()):
            L.append(f"  conviccion {k}/5              n={b['n']:<4} aciertos {b['win_rate']:>5.0%}  E={b['expectancy_r']:+.2f}R")
    if m.notes:
        L.append("")
        L.append("ADVERTENCIAS")
        for n in m.notes:
            L.append(f"  ! {n}")
    return "\n".join(L)
