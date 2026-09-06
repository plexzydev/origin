"""
Dimensionamiento de posiciones.

Dos metodos, ambos acotados:

  ATR          -> tamano tal que la distancia al stop cueste exactamente el
                  riesgo presupuestado. Es el metodo por defecto porque no
                  depende de estimar probabilidades.
  KELLY / 4    -> fraccion optima recortada al 25%. Kelly completo maximiza el
                  crecimiento logaritmico esperado y en la practica produce
                  drawdowns del 50-70%, porque asume que conoces tu win rate
                  exacto. No lo conoces: lo estimaste con 40 trades.

ENTRADA ESCALONADA: nunca posicion completa de una. Los tramos posteriores
solo se agregan si el mercado confirma la tesis, y la confirmacion esta
definida ANTES de entrar, no improvisada despues.

EL STOP NO ES UNA GARANTIA. Es una intencion. En un gap se ejecuta al precio
que haya. Por eso toda salida de este modulo reporta ademas el peor caso con
deslizamiento (`worst_case_loss`), y ese numero -- no el nominal -- es el que
el Risk Officer usa para decidir si el trade entra.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..config import RiskConfig
from ..contracts import Side


@dataclass(frozen=True, slots=True)
class SizeResult:
    qty: float
    tranches: tuple[float, ...]
    risk_cash: float               # perdida si el stop se ejecuta al precio nominal
    worst_case_loss: float         # perdida si el stop se desliza `stop_slippage_atr`
    risk_pct: float
    worst_case_pct: float
    r_unit_cash: float             # valor monetario de 1R
    notes: tuple[str, ...]

    @property
    def viable(self) -> bool:
        return self.qty > 0


def atr_position_size(
    equity: float,
    entry: float,
    stop: float,
    atr: float,
    cfg: RiskConfig,
    *,
    size_multiplier: float = 1.0,
    lot: float = 1.0,
) -> SizeResult:
    """
    Tamano por distancia al stop.

    `size_multiplier` viene de los cortafuegos y del gobernador de frecuencia.
    Siempre <= 1.0 por construccion (ver circuit_breakers.evaluate).
    """
    notes: list[str] = []
    dist = abs(entry - stop)
    if dist <= 0 or equity <= 0:
        return SizeResult(0, (), 0, 0, 0, 0, 0, ("distancia al stop nula: no se puede dimensionar",))
    if size_multiplier > 1.0:
        # Candado redundante y deliberado: si alguna vez alguien pasa >1 desde
        # otro modulo, aca se corta. Nunca se aumenta tamano para recuperar.
        raise ValueError(f"multiplicador {size_multiplier} > 1.0: martingala prohibida")

    budget = equity * cfg.risk_per_trade_pct * size_multiplier
    qty = math.floor((budget / dist) / lot) * lot
    if qty <= 0:
        return SizeResult(0, (), 0, 0, 0, 0, 0,
                          (f"presupuesto {budget:,.0f} insuficiente para 1 unidad con stop a {dist:.2f}",))

    risk_cash = qty * dist
    # Peor caso: el stop se ejecuta `stop_slippage_atr` ATR mas alla.
    slip = cfg.stop_slippage_atr * atr if atr > 0 else dist * 0.5
    worst = qty * (dist + slip)
    notes.append(f"{qty:,.0f} unidades; stop a {dist:.2f} = {risk_cash:,.0f} ({risk_cash/equity:.2%})")
    notes.append(
        f"peor caso con deslizamiento de {cfg.stop_slippage_atr:.1f} ATR: "
        f"{worst:,.0f} ({worst/equity:.2%}). Este es el numero que importa."
    )
    if size_multiplier < 1.0:
        notes.append(f"tamano reducido al {size_multiplier:.0%} por cortafuegos o cuota")

    tranches = scaled_entry(qty, cfg.entry_tranches, lot)
    notes.append(f"entrada escalonada en {len(tranches)} tramos: {[f'{t:,.0f}' for t in tranches]}")

    return SizeResult(
        qty=qty, tranches=tranches, risk_cash=risk_cash, worst_case_loss=worst,
        risk_pct=risk_cash / equity, worst_case_pct=worst / equity,
        r_unit_cash=risk_cash, notes=tuple(notes),
    )


def scaled_entry(total_qty: float, fractions: tuple[float, ...], lot: float = 1.0) -> tuple[float, ...]:
    """
    Reparte la posicion en tramos. El resto se asigna al ULTIMO tramo, no al
    primero: si el trade nunca confirma, la exposicion real queda por debajo
    de la planificada, que es el sesgo correcto.
    """
    if total_qty <= 0 or not fractions:
        return ()
    out = [math.floor(total_qty * f / lot) * lot for f in fractions[:-1]]
    out.append(total_qty - sum(out))
    return tuple(t for t in out if t > 0)


def fractional_kelly(
    win_rate: float, avg_win_r: float, avg_loss_r: float, cfg: RiskConfig, n_trades: int = 0
) -> tuple[float, str]:
    """
    Kelly fraccionado. Devuelve (fraccion del capital, justificacion).

    Tres candados:
      1. Se recorta al `kelly_fraction` (25% por defecto).
      2. Nunca supera `risk_per_trade_pct`: Kelly informa, no manda.
      3. Con menos de 30 trades devuelve 0 y lo dice. Estimar un win rate con
         15 operaciones y dimensionar con eso es como medir con una regla de
         goma: el numero sale, y esta mal.
    """
    if n_trades < 30:
        return 0.0, (
            f"Kelly no aplicable con {n_trades} operaciones (minimo 30). "
            "Se usa dimensionamiento por ATR, que no requiere estimar probabilidades."
        )
    if avg_loss_r <= 0 or not 0.0 < win_rate < 1.0:
        return 0.0, "parametros de Kelly invalidos"
    b = avg_win_r / avg_loss_r
    full = (win_rate * (b + 1) - 1) / b
    if full <= 0:
        return 0.0, f"Kelly completo {full:.3f} <= 0: la estrategia no tiene ventaja medible. No se opera."
    frac = full * cfg.kelly_fraction
    capped = min(frac, cfg.risk_per_trade_pct)
    note = (
        f"Kelly completo {full:.1%} -> fraccionado al {cfg.kelly_fraction:.0%} = {frac:.2%}"
        + (f", recortado al techo de riesgo por trade {capped:.2%}" if capped < frac else "")
        + f" (win rate {win_rate:.0%}, b={b:.2f}, n={n_trades})"
    )
    return capped, note


def add_tranche_allowed(
    entry_price: float, current_price: float, side: Side, r_unit_price: float, tranche_index: int
) -> tuple[bool, str]:
    """
    Confirmacion para agregar un tramo. Definida ANTES de entrar.

    Criterio: el precio tiene que haber avanzado a favor al menos 0.5R por
    cada tramo adicional. Promediar a la baja esta prohibido: es martingala
    con otro nombre.
    """
    if r_unit_price <= 0:
        return False, "unidad de R no definida"
    move_r = (current_price - entry_price) * side.sign / r_unit_price
    needed = 0.5 * tranche_index
    if move_r >= needed:
        return True, f"confirmado: el precio avanzo {move_r:+.2f}R (requerido {needed:+.2f}R)"
    return False, (
        f"NO confirmado: {move_r:+.2f}R vs {needed:+.2f}R requeridos. "
        "Agregar aca seria promediar a la baja, que esta prohibido."
    )
