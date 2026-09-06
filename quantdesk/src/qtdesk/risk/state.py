"""
Estado vivo de la mesa. Lo que los cortafuegos observan.

Distincion importante que el sistema mantiene explicita:

  equity      -> lo que vale la cuenta AHORA (incluye no realizado)
  peak_equity -> el maximo historico. El drawdown se mide contra esto, no
                 contra el capital inicial. Una cuenta que fue de 100k a 150k
                 y volvio a 120k esta en -20% de drawdown, no en +20% de
                 ganancia. Las dos cosas son ciertas y solo una importa para
                 dimensionar riesgo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta


@dataclass(slots=True)
class DeskState:
    equity: float
    peak_equity: float = 0.0
    day_start_equity: float = 0.0
    week_start_equity: float = 0.0
    month_start_equity: float = 0.0
    consecutive_losses: int = 0
    trades_this_week: int = 0
    trades_this_month: int = 0
    closed_trades: int = 0
    # Anclas de periodo
    day_anchor: date | None = None
    week_anchor: date | None = None
    month_anchor: date | None = None
    # Interruptores
    manual_kill: bool = False              # apagado manual, siempre accesible
    shutdown_latched: bool = False         # perdida mensual: exige reset manual
    streak_pause_latched: bool = False     # 3 perdidas seguidas: exige auditoria
    day_halt_latched: bool = False         # perdida diaria: cierre de jornada
    # Trazabilidad
    process_violations: int = 0
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.peak_equity <= 0:
            self.peak_equity = self.equity
        for attr in ("day_start_equity", "week_start_equity", "month_start_equity"):
            if getattr(self, attr) <= 0:
                setattr(self, attr, self.equity)

    # -- metricas -----------------------------------------------------------
    @property
    def drawdown(self) -> float:
        """Drawdown vigente contra el maximo historico. Siempre >= 0."""
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity)

    @property
    def daily_pnl_pct(self) -> float:
        return 0.0 if self.day_start_equity <= 0 else (self.equity - self.day_start_equity) / self.day_start_equity

    @property
    def weekly_pnl_pct(self) -> float:
        return 0.0 if self.week_start_equity <= 0 else (self.equity - self.week_start_equity) / self.week_start_equity

    @property
    def monthly_pnl_pct(self) -> float:
        return 0.0 if self.month_start_equity <= 0 else (self.equity - self.month_start_equity) / self.month_start_equity

    # -- ciclo de vida ------------------------------------------------------
    def mark_to_market(self, equity: float) -> None:
        self.equity = equity
        if equity > self.peak_equity:
            self.peak_equity = equity

    def roll_periods(self, ts: datetime) -> None:
        """
        Reinicia anclas al cambiar de dia/semana/mes.

        El latch diario se libera al abrir la jornada siguiente: "cierre de
        jornada" significa exactamente eso, no "apagado permanente".
        El latch mensual y el de racha NO se liberan solos: exigen intervencion
        humana, que es justamente el punto de tenerlos.
        """
        d = ts.date()
        if self.day_anchor != d:
            self.day_anchor = d
            self.day_start_equity = self.equity
            self.day_halt_latched = False
        monday = d - timedelta(days=d.weekday())
        if self.week_anchor != monday:
            self.week_anchor = monday
            self.week_start_equity = self.equity
            self.trades_this_week = 0
        first = d.replace(day=1)
        if self.month_anchor != first:
            self.month_anchor = first
            self.month_start_equity = self.equity
            self.trades_this_month = 0

    def register_open(self) -> None:
        self.trades_this_week += 1
        self.trades_this_month += 1

    def register_close(self, pnl: float) -> None:
        self.closed_trades += 1
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    # -- intervencion humana ------------------------------------------------
    def manual_reset(self, who: str, reason: str, ts: datetime) -> None:
        """
        Reactivacion despues de un apagado. Deja rastro: si esto se usa seguido,
        el problema no es el cortafuegos.
        """
        self.shutdown_latched = False
        self.streak_pause_latched = False
        self.consecutive_losses = 0
        self.notes.append(f"[{ts.isoformat()}] RESET MANUAL por {who}: {reason}")

    def kill(self, reason: str, ts: datetime) -> None:
        self.manual_kill = True
        self.notes.append(f"[{ts.isoformat()}] APAGADO: {reason}")

    def resume(self, who: str, ts: datetime) -> None:
        self.manual_kill = False
        self.notes.append(f"[{ts.isoformat()}] REANUDADO por {who}")
