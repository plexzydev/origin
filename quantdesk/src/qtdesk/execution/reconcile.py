"""
Reconciliacion permanente entre las posiciones del sistema y las del broker.

Regla del mandato: "Divergencia -> apagado inmediato."

Por que es tan drastico: si el sistema cree que tiene 100 acciones y el broker
tiene 300, no hay forma de saber cual de las dos es la verdad ni desde cuando.
Cualquier accion tomada con el estado equivocado -- incluido "cerrar la
diferencia" -- puede empeorarlo. La unica respuesta segura es congelar, apagar
y que mire una persona.

Tambien cubre las fallas operativas del mandato:
  - conexion caida o broker que no responde
  - retraso de datos
  - stops que NO estan del lado del broker
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..contracts import Position, Severity


@dataclass(frozen=True, slots=True)
class Divergence:
    symbol: str
    code: str
    system_qty: float
    broker_qty: float
    detail: str
    severity: Severity = Severity.CRITICAL


@dataclass(frozen=True, slots=True)
class ReconResult:
    ok: bool
    divergences: tuple[Divergence, ...]
    must_kill: bool
    detail: str
    checked: int


def reconcile(
    system: tuple[Position, ...],
    broker: tuple[Position, ...],
    *,
    qty_tolerance: float = 1e-6,
    stop_tolerance: float = 0.005,
) -> ReconResult:
    """
    Compara posicion por posicion. CUALQUIER divergencia exige apagado.

    `stop_tolerance` es relativa: un stop que difiere mas de 0.5% entre el
    sistema y el broker significa que la proteccion real no es la que se cree.
    """
    sys_by = {p.symbol: p for p in system}
    brk_by = {p.symbol: p for p in broker}
    divs: list[Divergence] = []

    for sym in sorted(set(sys_by) | set(brk_by)):
        s, b = sys_by.get(sym), brk_by.get(sym)

        if s is not None and b is None:
            divs.append(Divergence(
                sym, "POSICION_FANTASMA", s.qty, 0.0,
                f"el sistema cree tener {s.qty:g} unidades de {sym}; el broker no tiene ninguna. "
                "O la orden nunca se ejecuto, o se cerro sin que el sistema se entere.",
            ))
            continue
        if s is None and b is not None:
            divs.append(Divergence(
                sym, "POSICION_HUERFANA", 0.0, b.qty,
                f"el broker tiene {b.qty:g} unidades de {sym} que el sistema desconoce. "
                "Esta posicion NO tiene stop gestionado por el sistema.",
            ))
            continue

        if abs(s.qty - b.qty) > qty_tolerance:
            divs.append(Divergence(
                sym, "CANTIDAD_DIVERGENTE", s.qty, b.qty,
                f"{sym}: el sistema dice {s.qty:g}, el broker {b.qty:g}. "
                "Fill parcial, doble envio o un fill perdido.",
            ))
        if s.side is not b.side:
            divs.append(Divergence(
                sym, "LADO_DIVERGENTE", s.qty, b.qty,
                f"{sym}: el sistema cree estar {s.side.value} y el broker dice {b.side.value}. "
                "Es la divergencia mas grave posible.",
            ))
        if b.stop_price <= 0:
            divs.append(Divergence(
                sym, "SIN_STOP_EN_BROKER", s.qty, b.qty,
                f"{sym}: el broker NO tiene stop cargado. Si se cae la conexion, "
                "esta posicion queda sin proteccion.",
            ))
        elif s.stop_price > 0 and abs(s.stop_price - b.stop_price) / s.stop_price > stop_tolerance:
            divs.append(Divergence(
                sym, "STOP_DIVERGENTE", s.qty, b.qty,
                f"{sym}: stop del sistema {s.stop_price:.4f} vs broker {b.stop_price:.4f}. "
                "La proteccion real no es la que el sistema cree tener.",
            ))

    ok = not divs
    return ReconResult(
        ok=ok, divergences=tuple(divs), must_kill=not ok,
        detail=("posiciones reconciliadas" if ok else
                f"{len(divs)} divergencia(s): APAGADO INMEDIATO. " +
                "; ".join(d.code for d in divs)),
        checked=len(set(sys_by) | set(brk_by)),
    )


@dataclass(frozen=True, slots=True)
class OperationalHealth:
    ok: bool
    must_flatten: bool
    reasons: tuple[str, ...]


def check_operational(
    *,
    broker_health,
    now: datetime,
    last_data_ts: datetime | None,
    max_data_lag: timedelta = timedelta(minutes=5),
    max_heartbeat_lag: timedelta = timedelta(minutes=2),
    open_positions: int = 0,
) -> OperationalHealth:
    """
    Fallas operativas. Si algo falla CON POSICIONES ABIERTAS, la respuesta es
    cerrar o -- como minimo -- garantizar que los stops estan del lado del
    broker y no en esta maquina.
    """
    reasons: list[str] = []
    flatten = False

    if not broker_health.ok:
        reasons.append(f"broker no responde: {broker_health.detail}")
        flatten = open_positions > 0

    if broker_health.last_heartbeat is not None:
        lag = now - broker_health.last_heartbeat
        if lag > max_heartbeat_lag:
            reasons.append(f"sin latido del broker hace {lag}")
            flatten = flatten or open_positions > 0

    if last_data_ts is None:
        reasons.append("sin datos de mercado")
        flatten = flatten or open_positions > 0
    else:
        lag = now - last_data_ts
        if lag > max_data_lag:
            reasons.append(f"feed atrasado {lag}: las decisiones se tomarian a ciegas")
            flatten = flatten or open_positions > 0

    if open_positions > 0 and not broker_health.stops_at_broker:
        reasons.append(
            "los stops NO estan del lado del broker: viven en esta maquina. "
            "Si se cae la conexion o el proceso, las posiciones quedan sin proteccion."
        )
        flatten = True

    return OperationalHealth(ok=not reasons, must_flatten=flatten, reasons=tuple(reasons))
