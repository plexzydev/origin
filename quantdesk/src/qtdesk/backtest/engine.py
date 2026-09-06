"""
Motor de backtest honesto.

La regla que ordena todo el archivo: LA SENAL SE CALCULA AL CIERRE DE LA BARRA
T Y SE EJECUTA EN LA BARRA T+1. No es configurable, no hay flag para
desactivarlo, y hay tests que lo verifican de tres formas distintas.

Secuencia por rueda, y el orden importa:

  1. El broker procesa la barra i: llena las entradas pendientes que se
     enviaron en i-1 (a la APERTURA de i) y revisa stops contra el rango de i.
  2. Se marca a mercado y se evaluan los cortafuegos.
  3. Se actualiza la proteccion de las posiciones vivas (trailing, parciales,
     salida por tiempo).
  4. RECIEN AHORA se decide, con `as_of` = cierre de la barra i.
  5. Las ordenes resultantes quedan pendientes para la barra i+1.

Despues de CADA decision se corre `audit.assert_clean(as_of)`. Si alguna capa
toco un timestamp posterior a `as_of`, la corrida se aborta con LookAheadError
en vez de producir un resultado bonito y falso.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..clock import AccessAudit, AsOfClock
from ..config import SystemConfig
from ..contracts import Action, Decision, Fill, Position, Side
from ..data.bundle import DataBundle
from ..execution.paper import PaperBroker
from ..layers import indicators as ind
from ..risk import circuit_breakers as cb
from ..risk.state import DeskState
from ..risk.stops import build_bracket, update_protection
from ..engine.decision import DecisionEngine


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    symbol: str
    side: Side
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    r_multiple: float
    exit_reason: str
    regime: str
    conviction: int
    forced_by_quota: bool
    measuring: bool
    decision_fingerprint: str
    slippage_bps_in: float
    slippage_bps_out: float

    @property
    def won(self) -> bool:
        return self.pnl > 0


@dataclass(slots=True)
class BacktestResult:
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    trades: list[ClosedTrade] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    blocked_counts: dict[str, int] = field(default_factory=dict)
    evaluations: int = 0
    audit_violations: list[str] = field(default_factory=list)
    breaker_events: list[tuple[datetime, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1][1] if self.equity_curve else 0.0

    @property
    def approved_decisions(self) -> list[Decision]:
        return [d for d in self.decisions if d.action is not Action.NO_TRADE]


class BacktestEngine:
    def __init__(self, config: SystemConfig, engine: DecisionEngine,
                 *, record_all_decisions: bool = False) -> None:
        self.cfg = config
        self.engine = engine
        # Guardar TODA decision (incluidos los ~99% de NO OPERAR) es util para
        # auditar pero pesa mucho. Por defecto se guardan solo las operativas y
        # se cuentan los motivos de rechazo.
        self.record_all = record_all_decisions

    def run(
        self,
        bundle: DataBundle,
        sessions: list[datetime],
        symbols: list[str],
        *,
        initial_equity: float = 100_000.0,
        warmup: int = 260,
        freq_governor=None,
    ) -> BacktestResult:
        cfg = self.cfg
        res = BacktestResult()
        broker = PaperBroker(cfg.costs, cfg.risk, initial_equity)
        desk = DeskState(equity=initial_equity)
        clock = AsOfClock(sessions[warmup])
        # indice de barra por simbolo, para no re-buscar en cada rueda
        idx_of: dict[str, int] = {s: -1 for s in symbols}
        open_meta: dict[str, dict] = {}

        for i in range(warmup, len(sessions)):
            as_of = sessions[i]
            clock.advance_to(as_of)
            desk.roll_periods(as_of)
            exec_audit = AccessAudit()

            # ---- 1. El broker procesa la barra i -------------------------
            for sym in symbols:
                series = bundle.bars.get(sym)
                if series is None:
                    continue
                j = series.index_at_or_before(as_of)
                if j < 0 or series.raw(j).ts != as_of:
                    continue
                idx_of[sym] = j
                bar = series.raw(j)
                exec_audit.record_execution(bar.ts, f"{sym}.execution_bar")
                window = series.bars[max(0, j - 40):j + 1]
                atr = ind.atr(window, 14) or 0.0
                avg_atr = ind.atr(series.bars[max(0, j - 100):j + 1], 14) or atr
                vr = ind.volume_ratio(window, 20) or 1.0
                for f in broker.on_bar(sym, bar, atr=atr, avg_atr=avg_atr, volume_ratio=vr):
                    res.fills.append(f)
                    self._on_fill(f, broker, desk, res, open_meta, as_of)

            # ---- 2. Marca a mercado y cortafuegos -------------------------
            desk.mark_to_market(broker.equity())
            res.equity_curve.append((as_of, desk.equity))
            verdict = cb.evaluate(desk, cfg.risk)
            if verdict.level is not cb.BreakerLevel.NORMAL:
                res.breaker_events.append((as_of, verdict.level.value))
            if verdict.level in (cb.BreakerLevel.SHUTDOWN, cb.BreakerLevel.MANUAL_KILL):
                for f in broker.kill_all(as_of, verdict.level.value):
                    res.fills.append(f)
                    self._on_fill(f, broker, desk, res, open_meta, as_of)
                res.notes.append(f"{as_of.date()}: {verdict.level.value} -- libro cerrado")
                continue

            # ---- 3. Proteccion de posiciones vivas ------------------------
            for pos in list(broker.positions()):
                j = idx_of.get(pos.symbol, -1)
                if j < 0:
                    continue
                series = bundle.bars[pos.symbol]
                bar = series.raw(j)
                atr = ind.atr(series.bars[max(0, j - 40):j + 1], 14) or 0.0
                upd = update_protection(pos, bar.close, atr, cfg.risk, as_of)
                if upd.close_now:
                    f = broker.close(pos.symbol, pos.qty, as_of, upd.reason)
                    if f:
                        res.fills.append(f)
                        self._on_fill(f, broker, desk, res, open_meta, as_of)
                elif upd.take_fraction > 0:
                    f = broker.take_partial(pos.symbol, upd.take_fraction, as_of, bar.close, upd.reason)
                    if f:
                        res.fills.append(f)
                elif upd.moved:
                    broker.modify_stop(pos.symbol, upd.new_stop, as_of)

            # ---- 4. Decisiones con as_of = cierre de la barra i ------------
            if not verdict.can_open:
                continue
            audit = AccessAudit()
            # Vistas de pares construidas UNA vez para toda la rueda.
            all_views = bundle.all_views(as_of, audit)
            positions = broker.positions()
            sample = len(res.trades)
            hit_rate = self._measured_hit_rate(res.trades)

            for sym in symbols:
                if sym in {p.symbol for p in positions}:
                    continue
                if idx_of.get(sym, -1) < 0:
                    continue
                ctx = bundle.context(
                    sym, as_of, desk, cfg, audit,
                    open_positions=positions, peer_views=all_views,
                )
                with clock.freeze():
                    d = self.engine.decide(
                        ctx, verdict, sample_size=sample, measured_hit_rate=hit_rate,
                    )
                res.evaluations += 1
                if d.action is Action.NO_TRADE:
                    for c in (d.blocked_by or ("SIN_MOTIVO",)):
                        res.blocked_counts[c] = res.blocked_counts.get(c, 0) + 1
                    if self.record_all:
                        res.decisions.append(d)
                    continue

                res.decisions.append(d)
                self._submit(d, broker, desk, res, open_meta, as_of, freq_governor)
                positions = broker.positions()
                if len(positions) >= cfg.risk.max_positions:
                    break

            # ---- 5. AUDITORIA ANTI-LOOK-AHEAD -----------------------------
            # Si cualquier capa toco una barra posterior a `as_of`, esto
            # levanta LookAheadError y la corrida se aborta. No hay modo
            # "seguir igual": un backtest contaminado no vale nada.
            try:
                audit.assert_clean(as_of)
            except Exception as e:  # LookAheadError
                res.audit_violations.append(str(e))
                raise

        # Cierre final: se liquida todo a ultimo precio conocido
        for f in broker.kill_all(sessions[-1], "fin del backtest"):
            res.fills.append(f)
            self._on_fill(f, broker, desk, res, open_meta, sessions[-1])
        desk.mark_to_market(broker.equity())
        res.equity_curve.append((sessions[-1], desk.equity))
        return res

    # ------------------------------------------------------------------
    def _submit(self, d: Decision, broker, desk, res, open_meta, as_of, freq_governor) -> None:
        plan = d.plan
        first = plan.tranches[0] if plan.tranches else plan.total_qty
        try:
            bracket = build_bracket(
                plan.symbol, plan.side, plan.entry_price, plan.stop_price,
                plan.targets, plan.total_qty, d.fingerprint()[:12],
                tranche_qty=first,
            )
            broker.submit_bracket(
                bracket, as_of, sector=plan.sector, r_unit_cash=plan.r_unit_cash,
                time_stop_at=plan.time_stop,
            )
        except (ValueError, KeyError) as e:
            res.notes.append(f"{as_of.date()} {plan.symbol}: orden rechazada -- {e}")
            return
        open_meta[plan.symbol] = {
            "regime": f"{d.regime_cycle.value}/{d.regime_risk.value}",
            "conviction": d.conviction,
            "fingerprint": d.fingerprint(),
            "forced": "FORZADO_POR_CUOTA" in d.thesis or "[MEDICION" not in d.thesis and False,
            "measuring": d.thesis.startswith("[MEDICION"),
            "r_unit": plan.r_unit_cash,
        }
        desk.register_open()
        if freq_governor is not None:
            v = freq_governor.evaluate(as_of, self.cfg.decision.threshold_score)
            freq_governor.state.register_trade(as_of.date(), v.is_easing)

    def _on_fill(self, f: Fill, broker, desk, res, open_meta, as_of) -> None:
        """Registra un trade cerrado cuando el fill es una salida."""
        meta = open_meta.get(f.symbol)
        if meta is None:
            return
        # Es salida si ya no queda posicion en ese simbolo
        if any(p.symbol == f.symbol for p in broker.positions()):
            return
        entry = next((x for x in reversed(res.fills)
                      if x.symbol == f.symbol and x.reason.startswith("entrada")), None)
        if entry is None:
            return
        pnl = (f.price - entry.price) * f.qty * (1 if entry.side is Side.LONG else -1) \
            - f.commission - entry.commission
        r_unit = meta.get("r_unit", 0.0) or 1.0
        res.trades.append(ClosedTrade(
            symbol=f.symbol, side=entry.side, entry_ts=entry.ts, exit_ts=f.ts,
            entry_price=entry.price, exit_price=f.price, qty=f.qty, pnl=pnl,
            r_multiple=pnl / r_unit if r_unit else 0.0, exit_reason=f.reason,
            regime=meta["regime"], conviction=meta["conviction"],
            forced_by_quota=bool(meta.get("forced")), measuring=bool(meta.get("measuring")),
            decision_fingerprint=meta["fingerprint"],
            slippage_bps_in=entry.slippage_bps, slippage_bps_out=f.slippage_bps,
        ))
        desk.register_close(pnl)
        open_meta.pop(f.symbol, None)

    @staticmethod
    def _measured_hit_rate(trades: list[ClosedTrade]) -> float | None:
        """Tasa de acierto observada. None hasta tener muestra suficiente."""
        if len(trades) < 30:
            return None
        return sum(1 for t in trades if t.won) / len(trades)
