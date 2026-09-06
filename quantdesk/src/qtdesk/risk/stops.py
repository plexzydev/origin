"""
Stops, brackets y proteccion de ganancias.

Cuatro invariantes que este modulo hace cumplir por construccion:

  1. Ninguna entrada existe sin su stop. `build_bracket` es la unica forma de
     crear una entrada, y no construye nada sin stop.
  2. El stop dinamico NUNCA retrocede. `ratchet()` devuelve siempre el stop
     mas ajustado entre el viejo y el nuevo. No hay parametro para desactivarlo.
  3. Una vez que el trade corrio a favor, no puede volver a perdida. A 1R el
     stop pasa a breakeven MAS los costos de ida y vuelta.
  4. Salida por tiempo: si la tesis no se cumple en el plazo previsto, se
     cierra. Un trade que no funciona es un trade equivocado, aunque todavia
     no haya perdido.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..config import RiskConfig
from ..contracts import BracketOrder, Order, OrderType, Position, Side
from ..data.calendar import TradingCalendar


class StopViolation(RuntimeError):
    """Se intento mover un stop en contra. Nunca se captura para continuar."""


def ratchet(side: Side, current_stop: float, candidate: float) -> float:
    """
    Trinquete del stop. La unica funcion autorizada a modificar un stop.

    Para un largo devuelve el MAYOR de los dos; para un corto, el MENOR.
    Es imposible que esta funcion afloje un stop, y hay un test que lo
    verifica sobre miles de caminos aleatorios.
    """
    if side is Side.LONG:
        return max(current_stop, candidate)
    if side is Side.SHORT:
        return min(current_stop, candidate)
    raise ValueError("ratchet sobre posicion plana")


def assert_tighter(side: Side, old: float, new: float) -> None:
    if side is Side.LONG and new < old - 1e-9:
        raise StopViolation(f"stop de largo aflojado {old:.4f} -> {new:.4f}")
    if side is Side.SHORT and new > old + 1e-9:
        raise StopViolation(f"stop de corto aflojado {old:.4f} -> {new:.4f}")


def build_bracket(
    symbol: str,
    side: Side,
    entry_price: float,
    stop_price: float,
    targets: tuple[float, ...],
    qty: float,
    thesis_id: str,
    *,
    tranche_qty: float | None = None,
) -> BracketOrder:
    """
    Paquete indivisible entrada + stop + objetivos.

    Las ordenes son LIMITE por defecto. A mercado solo se justifica en un
    cierre de emergencia, y ni siquiera ahi en baja liquidez.
    """
    if stop_price <= 0:
        raise ValueError("no se envia una orden sin stop")
    if side is Side.LONG and stop_price >= entry_price:
        raise ValueError(f"stop {stop_price} por encima de la entrada {entry_price} en un largo")
    if side is Side.SHORT and stop_price <= entry_price:
        raise ValueError(f"stop {stop_price} por debajo de la entrada {entry_price} en un corto")
    if not targets:
        raise ValueError("sin objetivo no se puede evaluar la asimetria minima 1:3")

    first = tranche_qty if tranche_qty is not None else qty
    exit_side = Side.SHORT if side is Side.LONG else Side.LONG

    return BracketOrder(
        entry=Order(symbol, side, first, OrderType.LIMIT, limit_price=entry_price, tag="entrada"),
        # El stop cubre la posicion COMPLETA planificada, no solo el primer
        # tramo: si el mercado salta contra nosotros entre tramos, la
        # proteccion ya esta puesta.
        stop=Order(symbol, exit_side, qty, OrderType.STOP, stop_price=stop_price, tag="stop_protectivo"),
        targets=tuple(
            Order(symbol, exit_side, qty / len(targets), OrderType.LIMIT, limit_price=t, tag=f"objetivo_{i+1}")
            for i, t in enumerate(targets)
        ),
        thesis_id=thesis_id,
    )


def rr_ratio(entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    return 0.0 if risk <= 0 else abs(target - entry) / risk


def first_target_for_rr(entry: float, stop: float, side: Side, rr: float) -> float:
    """Precio objetivo que produce exactamente el ratio pedido."""
    return entry + side.sign * abs(entry - stop) * rr


@dataclass(frozen=True, slots=True)
class StopUpdate:
    new_stop: float
    moved: bool
    reason: str
    close_now: bool = False
    take_fraction: float = 0.0


def update_protection(
    pos: Position,
    price: float,
    atr: float,
    cfg: RiskConfig,
    now: datetime,
    costs_per_share: float = 0.0,
) -> StopUpdate:
    """
    Actualiza la proteccion de una posicion viva.

    Orden de evaluacion (importa):
      1. Salida por tiempo -- si vencio el plazo, se cierra sin importar el resto.
      2. Breakeven + costos al alcanzar 1R -- el trade deja de poder perder.
      3. Toma parcial en los niveles definidos.
      4. Trailing por ATR, siempre con trinquete.
    """
    r_now = pos.r_now(price)
    stop = pos.stop_price

    # 1. Salida por tiempo
    if pos.time_stop_at is not None and now >= pos.time_stop_at:
        return StopUpdate(stop, False,
            f"SALIDA POR TIEMPO: la tesis tenia plazo hasta {pos.time_stop_at.date()} y no se cumplio "
            f"({r_now:+.2f}R). Un trade que no funciona es un trade equivocado, aunque todavia no perdio.",
            close_now=True)

    # 2. Breakeven mas costos: a partir de aca el trade no puede volver a perdida
    if r_now >= cfg.breakeven_at_r:
        be = pos.avg_price + pos.side.sign * costs_per_share
        cand = ratchet(pos.side, stop, be)
        if abs(cand - stop) > 1e-9:
            return StopUpdate(cand, True,
                f"a {r_now:+.2f}R el stop pasa a breakeven + costos ({cand:.4f}). "
                "El trade ya no puede volver a perdida.")

    # 3. Toma parcial
    for i, (lvl, frac) in enumerate(zip(cfg.partial_take_r, cfg.partial_take_fraction)):
        if pos.targets_hit <= i and r_now >= lvl:
            return StopUpdate(stop, False,
                f"objetivo parcial {i+1} alcanzado a {r_now:+.2f}R (nivel {lvl}R): "
                f"se realiza el {frac:.0%} de la posicion",
                take_fraction=frac)

    # 4. Trailing por ATR, con trinquete
    if atr > 0:
        cand = price - pos.side.sign * 2.0 * atr
        new = ratchet(pos.side, stop, cand)
        if abs(new - stop) > 1e-9:
            assert_tighter(pos.side, stop, new)
            return StopUpdate(new, True, f"trailing 2 ATR: stop {stop:.4f} -> {new:.4f} (nunca retrocede)")

    return StopUpdate(stop, False, f"sin cambios en la proteccion ({r_now:+.2f}R)")


def time_stop_at(now: datetime, bdays: int, cal: TradingCalendar) -> datetime:
    d = cal.add_sessions(now.date(), bdays)
    return now.replace(year=d.year, month=d.month, day=d.day)
