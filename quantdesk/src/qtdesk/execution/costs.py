"""
Modelo de costos DELIBERADAMENTE PESIMISTA.

El mandato es explicito: "Modela el slippage PEOR que el historico: en el
momento que mas lo necesitas, es peor."

Traducido a la practica: el slippage no es una constante, es una funcion del
estres. El dia que necesitas salir es el dia que peor te ejecutan. Modelar el
promedio historico es modelar el dia que no importa.

Tres multiplicadores que se acumulan:
  pessimism_multiplier      -> castigo base sobre lo observado (1.75x)
  volatilidad relativa      -> mas vol, mas spread efectivo
  stop_slippage_multiplier  -> salir por stop siempre ejecuta peor (3x)

`assert_pessimistic()` verifica que el modelo nunca devuelva un costo menor
al historico. Hay un test que lo comprueba: si alguien "optimiza" los costos
para que el backtest se vea mejor, el test falla.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import CostConfig
from ..contracts import Side


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    commission: float
    spread_cost: float
    slippage_cost: float
    total: float
    slippage_bps: float
    effective_price: float
    notes: str

    @property
    def total_bps(self) -> float:
        return self.slippage_bps


def estimate(
    cfg: CostConfig,
    *,
    side: Side,
    reference_price: float,
    qty: float,
    atr: float = 0.0,
    avg_atr: float = 0.0,
    volume_ratio: float = 1.0,
    is_stop: bool = False,
    is_market: bool = False,
    illiquid: bool = False,
) -> CostBreakdown:
    """
    Costo de ejecutar `qty` a partir de `reference_price`.

    Devuelve el precio efectivo YA con el costo aplicado en contra: comprar
    ejecuta mas caro, vender mas barato. Nunca al reves.
    """
    if reference_price <= 0 or qty <= 0:
        return CostBreakdown(0, 0, 0, 0, 0, reference_price, "orden nula")

    notional = reference_price * qty
    commission = max(cfg.commission_min, cfg.commission_per_share * qty)

    # Spread: la mitad se paga siempre al cruzar
    spread_bps = cfg.half_spread_bps
    if illiquid:
        spread_bps += cfg.illiquid_penalty_bps

    # Slippage base, castigado
    slip_bps = cfg.base_slippage_bps * cfg.pessimism_multiplier
    reasons = [f"base {cfg.base_slippage_bps:.1f}bp x pesimismo {cfg.pessimism_multiplier:.2f}"]

    # Volatilidad relativa: con ATR sobre su promedio, el mercado ejecuta peor
    if atr > 0 and avg_atr > 0:
        vol_ratio = atr / avg_atr
        if vol_ratio > 1.0:
            slip_bps *= vol_ratio
            reasons.append(f"volatilidad {vol_ratio:.2f}x su promedio")

    # Volumen bajo: menos contraparte
    if volume_ratio < 1.0 and volume_ratio > 0:
        factor = min(3.0, 1.0 / volume_ratio)
        slip_bps *= factor
        reasons.append(f"volumen al {volume_ratio:.0%} -> x{factor:.2f}")

    # Salida por stop: el peor momento posible por definicion
    if is_stop:
        slip_bps *= cfg.stop_slippage_multiplier
        reasons.append(f"salida por STOP x{cfg.stop_slippage_multiplier:.1f}")

    # Orden a mercado: se paga el cruce completo
    if is_market:
        spread_bps *= 2.0
        reasons.append("orden a mercado: spread completo")

    spread_cost = notional * spread_bps / 10_000.0
    slippage_cost = notional * slip_bps / 10_000.0
    total = commission + spread_cost + slippage_cost

    # El costo siempre va EN CONTRA
    adverse = (spread_bps + slip_bps) / 10_000.0
    effective = reference_price * (1 + adverse * side.sign)

    return CostBreakdown(
        commission=commission, spread_cost=spread_cost, slippage_cost=slippage_cost,
        total=total, slippage_bps=spread_bps + slip_bps, effective_price=effective,
        notes="; ".join(reasons),
    )


def assert_pessimistic(cfg: CostConfig, observed_slippage_bps: float) -> None:
    """
    Verifica que el modelo sea mas caro que lo observado historicamente.

    Se llama al cargar una configuracion de costos calibrada con datos reales.
    Si alguien baja los costos para que el backtest se vea mejor, esto explota.
    """
    modeled = cfg.base_slippage_bps * cfg.pessimism_multiplier
    if modeled < observed_slippage_bps:
        raise ValueError(
            f"El modelo de costos ({modeled:.2f}bp) es MAS BARATO que el slippage observado "
            f"({observed_slippage_bps:.2f}bp). El mandato exige modelar peor que el historico. "
            "Subi pessimism_multiplier o base_slippage_bps."
        )
