"""
Limites de correlacion y concentracion.

El calculo que distingue este modulo de la mayoria: la exposicion se evalua
DOS veces.

  NORMAL     -> con la correlacion historica observada. Sirve para el dia a dia.
  ESTRESADA  -> asumiendo correlacion 1 entre TODAS las posiciones. Es la que
                manda para autorizar una apertura.

Por que la segunda es la que decide: en una crisis las correlaciones no se
degradan, colapsan a 1 en cuestion de dias. Octubre 2008, marzo 2020 y
septiembre 2022 tienen eso en comun: carteras que parecian diversificadas
resultaron ser una sola apuesta apalancada. Dimensionar con la correlacion
historica es dimensionar para el mundo que ya no existe cuando importa.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean

from ..config import RiskConfig
from ..contracts import Position, Severity
from ..stats import correlation


@dataclass(frozen=True, slots=True)
class LimitBreach:
    code: str
    detail: str
    severity: Severity = Severity.HIGH


@dataclass(frozen=True, slots=True)
class LimitVerdict:
    allowed: bool
    breaches: tuple[LimitBreach, ...]
    max_qty: float                  # cantidad maxima que si entraria
    notes: tuple[str, ...]
    stressed_risk_pct: float
    normal_risk_pct: float


def check_limits(
    *,
    symbol: str,
    sector: str,
    entry_price: float,
    qty: float,
    worst_case_loss: float,
    positions: tuple[Position, ...],
    position_worst_cases: dict[str, float],
    equity: float,
    cfg: RiskConfig,
    correlations: dict[str, float] | None = None,
) -> LimitVerdict:
    """
    Verifica todos los limites para una apertura candidata.

    `position_worst_cases` mapea simbolo -> perdida en el peor caso de esa
    posicion (con deslizamiento). Es lo que se suma para el calculo estresado.
    """
    breaches: list[LimitBreach] = []
    notes: list[str] = []
    max_qty = qty

    # -- 1. Cantidad de posiciones ------------------------------------------
    if len(positions) >= cfg.max_positions:
        breaches.append(LimitBreach(
            "MAX_POSICIONES",
            f"{len(positions)} posiciones abiertas >= maximo {cfg.max_positions}. "
            "Mas posiciones no es mas diversificacion, es menos atencion por posicion.",
            Severity.CRITICAL,
        ))
        max_qty = 0.0

    # -- 2. Peso por activo --------------------------------------------------
    notional = qty * entry_price
    existing = sum(abs(p.qty * p.avg_price) for p in positions if p.symbol == symbol)
    w_asset = (notional + existing) / equity if equity > 0 else 0.0
    if w_asset > cfg.max_weight_per_asset:
        allowed_notional = cfg.max_weight_per_asset * equity - existing
        max_qty = min(max_qty, max(0.0, allowed_notional / entry_price))
        breaches.append(LimitBreach(
            "PESO_POR_ACTIVO",
            f"{symbol} quedaria en {w_asset:.1%} del capital > limite {cfg.max_weight_per_asset:.1%}",
        ))
    notes.append(f"peso en {symbol}: {w_asset:.1%} (limite {cfg.max_weight_per_asset:.1%})")

    # -- 3. Peso por sector --------------------------------------------------
    by_sector: dict[str, float] = defaultdict(float)
    for p in positions:
        by_sector[p.sector] += abs(p.qty * p.avg_price)
    w_sector = (by_sector[sector] + notional) / equity if equity > 0 else 0.0
    if w_sector > cfg.max_weight_per_sector:
        allowed_notional = cfg.max_weight_per_sector * equity - by_sector[sector]
        max_qty = min(max_qty, max(0.0, allowed_notional / entry_price))
        breaches.append(LimitBreach(
            "PESO_POR_SECTOR",
            f"sector {sector} quedaria en {w_sector:.1%} > limite {cfg.max_weight_per_sector:.1%}",
        ))
    notes.append(f"peso en sector {sector}: {w_sector:.1%} (limite {cfg.max_weight_per_sector:.1%})")

    # -- 4. Exposicion bruta -------------------------------------------------
    gross = (sum(abs(p.qty * p.avg_price) for p in positions) + notional) / equity if equity > 0 else 0.0
    if gross > cfg.max_gross_exposure:
        breaches.append(LimitBreach(
            "EXPOSICION_BRUTA",
            f"exposicion bruta {gross:.1%} > limite {cfg.max_gross_exposure:.1%}",
        ))
        room = cfg.max_gross_exposure * equity - sum(abs(p.qty * p.avg_price) for p in positions)
        max_qty = min(max_qty, max(0.0, room / entry_price))
    notes.append(f"exposicion bruta: {gross:.1%} (limite {cfg.max_gross_exposure:.1%})")

    # -- 5. Riesgo con correlacion historica --------------------------------
    cors = correlations or {}
    if positions and cors:
        avg_cor = fmean([cors.get(p.symbol, 0.5) for p in positions])
        notes.append(f"correlacion media observada con el libro: {avg_cor:.2f}")
    else:
        avg_cor = 0.0
    existing_risk = sum(position_worst_cases.get(p.symbol, 0.0) for p in positions)
    # Suma en cuadratura con la correlacion observada: el mundo normal.
    normal_risk = (
        (existing_risk ** 2 + worst_case_loss ** 2 + 2 * avg_cor * existing_risk * worst_case_loss) ** 0.5
        if equity > 0 else 0.0
    )
    normal_pct = normal_risk / equity if equity > 0 else 0.0

    # -- 6. Riesgo asumiendo CORRELACION 1 -- el que decide -----------------
    stressed = existing_risk + worst_case_loss
    stressed_pct = stressed / equity if equity > 0 else 0.0
    notes.append(
        f"riesgo agregado: {normal_pct:.2%} con correlacion observada, "
        f"{stressed_pct:.2%} asumiendo correlacion 1"
    )
    if stressed_pct > cfg.max_stressed_risk_pct:
        # Cuanto entra sin romper el limite estresado
        room = cfg.max_stressed_risk_pct * equity - existing_risk
        if room <= 0 or worst_case_loss <= 0:
            max_qty = 0.0
        else:
            max_qty = min(max_qty, qty * (room / worst_case_loss))
        breaches.append(LimitBreach(
            "RIESGO_ESTRESADO",
            f"con correlacion 1 el libro arriesgaria {stressed_pct:.2%} > limite "
            f"{cfg.max_stressed_risk_pct:.2%}. En crisis la correlacion historica "
            "({:.2f}) no sobrevive; esta es la cuenta que vale.".format(avg_cor),
            Severity.CRITICAL,
        ))

    allowed = not breaches
    return LimitVerdict(
        allowed=allowed,
        breaches=tuple(breaches),
        max_qty=max(0.0, max_qty),
        notes=tuple(notes),
        stressed_risk_pct=stressed_pct,
        normal_risk_pct=normal_pct,
    )


def portfolio_correlations(
    candidate_returns: tuple[float, ...], peer_returns: dict[str, tuple[float, ...]]
) -> dict[str, float]:
    out: dict[str, float] = {}
    for sym, rets in peer_returns.items():
        c = correlation(candidate_returns, rets)
        if c is not None:
            out[sym] = c
    return out
