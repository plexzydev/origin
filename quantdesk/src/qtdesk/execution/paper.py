"""
Broker simulado. Sirve para backtest y para paper trading: es el mismo codigo.

Que eso sea el mismo codigo importa: si el backtest usara un simulador y el
paper otro, las diferencias entre ambos serian imposibles de atribuir.

DECISIONES DE EJECUCION, todas hacia el lado pesimista:

  1. Las entradas se ejecutan en la barra SIGUIENTE a la senal, a la apertura.
     Nunca en la barra de la senal. Esto no es configurable.
  2. Si dentro de una barra se tocan el stop Y el objetivo, se asume que
     toco PRIMERO EL STOP. Sin datos intradiarios es imposible saber cual fue
     primero, y suponer lo favorable es la forma mas comun de inflar un
     backtest sin darse cuenta.
  3. Si la apertura ya esta del otro lado del stop (gap), se ejecuta a la
     APERTURA, no al stop. El stop no es un piso magico.
  4. Una orden limite de entrada solo se llena si el precio realmente
     estuvo disponible: para una compra, si el minimo de la barra toco el
     limite. Si no, no hay fill -- y no operar es un resultado valido.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..config import CostConfig, RiskConfig
from ..contracts import (AccountState, Bar, BracketOrder, Fill, OrderType, Position, Side)
from ..risk.stops import StopViolation, assert_tighter
from . import costs as cost_mod
from .broker import Broker, BrokerHealth


@dataclass(slots=True)
class PendingBracket:
    bracket: BracketOrder
    submitted_at: datetime
    sector: str = "UNKNOWN"
    r_unit_cash: float = 0.0
    time_stop_at: datetime | None = None
    bars_waiting: int = 0
    max_wait_bars: int = 3          # si no se llena en 3 ruedas, se cancela


@dataclass(slots=True)
class PaperBroker(Broker):
    cost_cfg: CostConfig
    risk_cfg: RiskConfig
    initial_equity: float
    cash: float = 0.0
    _positions: dict[str, Position] = field(default_factory=dict)
    _pending: dict[str, PendingBracket] = field(default_factory=dict)
    _fills: list[Fill] = field(default_factory=list)
    _last_prices: dict[str, float] = field(default_factory=dict)
    _healthy: bool = True
    _last_heartbeat: datetime | None = None
    realized_pnl: float = 0.0
    rejected: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.cash <= 0:
            self.cash = self.initial_equity

    # -- interfaz Broker ---------------------------------------------------
    @property
    def name(self) -> str:
        return "PAPER"

    def health(self, now: datetime) -> BrokerHealth:
        return BrokerHealth(
            ok=self._healthy, latency_ms=0.0, last_heartbeat=self._last_heartbeat,
            # En un broker real esto seria True solo si los stops estan
            # efectivamente cargados del lado del broker. En simulacion es
            # trivialmente cierto, y el README lo aclara.
            stops_at_broker=True,
            detail="broker simulado: sin riesgo de conexion real",
        )

    def account(self, now: datetime) -> AccountState:
        return AccountState(now, self.equity(), self.cash, tuple(self._positions.values()))

    def positions(self) -> tuple[Position, ...]:
        return tuple(self._positions.values())

    def equity(self) -> float:
        unreal = sum(
            p.unrealized(self._last_prices.get(p.symbol, p.avg_price))
            for p in self._positions.values()
        )
        return self.cash + sum(
            abs(p.qty * p.avg_price) for p in self._positions.values()
        ) + unreal

    def submit_bracket(self, bracket: BracketOrder, now: datetime, *,
                       sector: str = "UNKNOWN", r_unit_cash: float = 0.0,
                       time_stop_at: datetime | None = None) -> str:
        sym = bracket.entry.symbol
        if sym in self._positions:
            self.rejected.append(f"{sym}: ya hay posicion abierta")
            raise ValueError(f"posicion ya abierta en {sym}")
        self._pending[sym] = PendingBracket(bracket, now, sector, r_unit_cash, time_stop_at)
        return f"BR-{sym}-{now.isoformat()}"

    def modify_stop(self, position_id: str, new_stop: float, now: datetime) -> None:
        p = self._positions.get(position_id)
        if p is None:
            raise KeyError(f"sin posicion {position_id}")
        # Aca vive el candado: aflojar un stop levanta excepcion, siempre.
        assert_tighter(p.side, p.stop_price, new_stop)
        p.stop_price = new_stop

    def close(self, symbol: str, qty: float, now: datetime, reason: str) -> Fill | None:
        p = self._positions.get(symbol)
        if p is None:
            return None
        px = self._last_prices.get(symbol, p.avg_price)
        return self._execute_exit(p, px, qty, now, reason, is_stop=False)

    def kill_all(self, now: datetime, reason: str) -> tuple[Fill, ...]:
        out = []
        for sym in list(self._positions):
            f = self.close(sym, self._positions[sym].qty, now, f"APAGADO: {reason}")
            if f:
                out.append(f)
        self._pending.clear()
        return tuple(out)

    def fills_since(self, ts: datetime) -> tuple[Fill, ...]:
        return tuple(f for f in self._fills if f.ts >= ts)

    # -- motor de simulacion -----------------------------------------------
    def on_bar(
        self, symbol: str, bar: Bar, *, atr: float = 0.0, avg_atr: float = 0.0,
        volume_ratio: float = 1.0,
    ) -> list[Fill]:
        """
        Procesa una barra. Devuelve los fills generados.

        ORDEN DE EVENTOS, deliberadamente pesimista:
          1. gap contra una posicion abierta -> salida a la apertura
          2. stop tocado dentro de la barra  -> salida al stop con slippage
          3. objetivo tocado                 -> salida al objetivo
          4. entradas pendientes             -> fill a la apertura o al limite
        """
        self._last_prices[symbol] = bar.close
        self._last_heartbeat = bar.ts
        out: list[Fill] = []

        pos = self._positions.get(symbol)
        if pos is not None:
            hit_stop, exit_px, why = self._check_stop(pos, bar)
            if hit_stop:
                f = self._execute_exit(pos, exit_px, pos.qty, bar.ts, why,
                                       is_stop=True, atr=atr, avg_atr=avg_atr,
                                       volume_ratio=volume_ratio)
                if f:
                    out.append(f)
                pos = None

        # Entradas pendientes: en la barra SIGUIENTE a la senal
        pend = self._pending.get(symbol)
        if pend is not None and symbol not in self._positions:
            if pend.submitted_at < bar.ts:
                fill = self._try_entry(pend, bar, atr, avg_atr, volume_ratio)
                if fill is not None:
                    out.append(fill)
                    del self._pending[symbol]
                else:
                    pend.bars_waiting += 1
                    if pend.bars_waiting >= pend.max_wait_bars:
                        self.rejected.append(
                            f"{symbol}: limite no alcanzado en {pend.max_wait_bars} ruedas, "
                            "orden cancelada (no se persigue el precio)"
                        )
                        del self._pending[symbol]
        return out

    def _check_stop(self, pos: Position, bar: Bar) -> tuple[bool, float, str]:
        if pos.side is Side.LONG:
            if bar.open <= pos.stop_price:
                return True, bar.open, f"GAP por debajo del stop: apertura {bar.open:.4f} < stop {pos.stop_price:.4f}"
            if bar.low <= pos.stop_price:
                return True, pos.stop_price, f"stop tocado en {pos.stop_price:.4f}"
        else:
            if bar.open >= pos.stop_price:
                return True, bar.open, f"GAP por encima del stop: apertura {bar.open:.4f} > stop {pos.stop_price:.4f}"
            if bar.high >= pos.stop_price:
                return True, pos.stop_price, f"stop tocado en {pos.stop_price:.4f}"
        return False, 0.0, ""

    def _try_entry(self, pend: PendingBracket, bar: Bar, atr, avg_atr, vr) -> Fill | None:
        o = pend.bracket.entry
        limit = o.limit_price
        # Orden limite: solo se llena si el precio realmente estuvo ahi.
        if o.side is Side.LONG:
            if bar.open <= limit:
                px = bar.open                      # abrio mejor que el limite
            elif bar.low <= limit:
                px = limit
            else:
                return None
        else:
            if bar.open >= limit:
                px = bar.open
            elif bar.high >= limit:
                px = limit
            else:
                return None

        c = cost_mod.estimate(self.cost_cfg, side=o.side, reference_price=px, qty=o.qty,
                              atr=atr, avg_atr=avg_atr, volume_ratio=vr)
        eff = c.effective_price
        stop_px = pend.bracket.stop.stop_price
        self.cash -= abs(o.qty * eff) + c.commission
        self._positions[o.symbol] = Position(
            symbol=o.symbol, side=o.side, qty=o.qty, avg_price=eff,
            stop_price=stop_px, initial_stop=stop_px, opened_at=bar.ts,
            thesis_id=pend.bracket.thesis_id, sector=pend.sector,
            time_stop_at=pend.time_stop_at, r_unit=abs(eff - stop_px) * o.qty,
        )
        f = Fill(bar.ts, o.symbol, o.side, o.qty, eff, c.commission, c.slippage_bps,
                 f"entrada en la barra siguiente a la senal ({c.notes})")
        self._fills.append(f)
        return f

    def _execute_exit(self, pos: Position, price: float, qty: float, now: datetime,
                      reason: str, *, is_stop: bool, atr=0.0, avg_atr=0.0, volume_ratio=1.0) -> Fill | None:
        qty = min(qty, pos.qty)
        if qty <= 0:
            return None
        exit_side = Side.SHORT if pos.side is Side.LONG else Side.LONG
        c = cost_mod.estimate(self.cost_cfg, side=exit_side, reference_price=price, qty=qty,
                              atr=atr, avg_atr=avg_atr, volume_ratio=volume_ratio, is_stop=is_stop)
        eff = c.effective_price
        pnl = (eff - pos.avg_price) * qty * pos.side.sign - c.commission
        self.cash += abs(qty * pos.avg_price) + pnl
        self.realized_pnl += pnl
        pos.qty -= qty
        if pos.qty <= 1e-9:
            del self._positions[pos.symbol]
        f = Fill(now, pos.symbol, exit_side, qty, eff, c.commission, c.slippage_bps, reason)
        self._fills.append(f)
        return f

    def take_partial(self, symbol: str, fraction: float, now: datetime, price: float,
                     reason: str) -> Fill | None:
        p = self._positions.get(symbol)
        if p is None:
            return None
        qty = p.qty * fraction
        p.targets_hit += 1
        return self._execute_exit(p, price, qty, now, reason, is_stop=False)

    def simulate_outage(self, healthy: bool) -> None:
        """Para tests de falla operativa."""
        self._healthy = healthy
