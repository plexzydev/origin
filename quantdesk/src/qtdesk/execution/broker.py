"""
Interfaz abstracta de broker.

ALCANCE DEL SISTEMA: backtesting y paper trading UNICAMENTE. No existe, ni va
a existir en este arbol, una implementacion que envie ordenes con dinero real.
La interfaz esta para que el resto del sistema no dependa de ningun broker
concreto, no para habilitar uno.

Todo broker debe garantizar cuatro cosas, y las cuatro estan en la interfaz
porque son requisitos de RIESGO, no de conveniencia:

  1. `submit_bracket` es la unica via de entrada. No hay `submit_order` suelto:
     es imposible mandar una entrada sin su stop.
  2. `stops_at_broker` informa si los stops viven del lado del broker o de esta
     maquina. Si viven aca y se cae la conexion, no hay proteccion.
  3. `is_healthy` permite detectar broker caido antes de operar.
  4. `kill_all` es el interruptor de apagado, siempre accesible.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ..contracts import AccountState, BracketOrder, Fill, Order, Position


class BrokerError(RuntimeError):
    pass


class BrokerUnavailable(BrokerError):
    """El broker no responde. Nunca se opera a ciegas: se cierra o se apaga."""


@dataclass(frozen=True, slots=True)
class BrokerHealth:
    ok: bool
    latency_ms: float
    last_heartbeat: datetime | None
    stops_at_broker: bool
    detail: str


class Broker(ABC):
    """Contrato minimo. Backtest y paper lo implementan; nada mas lo hace."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def health(self, now: datetime) -> BrokerHealth: ...

    @abstractmethod
    def account(self, now: datetime) -> AccountState: ...

    @abstractmethod
    def positions(self) -> tuple[Position, ...]: ...

    @abstractmethod
    def submit_bracket(self, bracket: BracketOrder, now: datetime) -> str:
        """
        Envia entrada + stop + objetivos como un paquete indivisible.
        Devuelve el id del paquete. UNICA via de apertura.
        """

    @abstractmethod
    def modify_stop(self, position_id: str, new_stop: float, now: datetime) -> None:
        """Solo acepta stops MAS AJUSTADOS. Aflojar debe levantar excepcion."""

    @abstractmethod
    def close(self, symbol: str, qty: float, now: datetime, reason: str) -> Fill | None: ...

    @abstractmethod
    def kill_all(self, now: datetime, reason: str) -> tuple[Fill, ...]:
        """Interruptor de apagado. Cierra todo. Siempre disponible."""

    @abstractmethod
    def fills_since(self, ts: datetime) -> tuple[Fill, ...]: ...
