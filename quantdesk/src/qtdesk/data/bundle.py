"""
Paquete de datos y constructor de contexto.

`DataBundle` es la frontera entre "de donde salen los datos" y "que hace el
sistema con ellos". El mundo sintetico, un proveedor real (yfinance/FRED/EDGAR)
o un feed en vivo producen todos un DataBundle; de ahi para adentro el codigo
es identico. Eso es lo que hace que backtest y paper trading no puedan
divergir: no hay dos caminos, hay uno.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..clock import AccessAudit
from ..config import SystemConfig
from ..contracts import Position, Quote
from ..layers.base import MarketContext
from ..risk.state import DeskState
from .bars import BarSeries, ExecutionOracle, SignalView, resample
from .calendar import EventCalendar, TradingCalendar
from .fundamentals import FundamentalStore
from .pit import PointInTimeStore


@dataclass(slots=True)
class DataBundle:
    bars: dict[str, BarSeries]
    calendar: TradingCalendar
    pit: PointInTimeStore = field(default_factory=PointInTimeStore)
    events: EventCalendar = field(default_factory=EventCalendar)
    fundamentals: FundamentalStore = field(default_factory=FundamentalStore)
    sector_map: dict[str, str] = field(default_factory=dict)
    quotes: dict[str, dict[datetime, Quote]] = field(default_factory=dict)
    intraday: bool = False
    # Cuantas barras de historia se exponen a las capas. Techo explicito para
    # que el costo de una decision no crezca con el largo del backtest.
    history_window: int = 400

    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.bars))

    def view(self, symbol: str, as_of: datetime, audit: AccessAudit) -> SignalView:
        return SignalView(self.bars[symbol], as_of, audit)

    def oracle(self, symbol: str, audit: AccessAudit) -> ExecutionOracle:
        """Acceso de EJECUCION. Solo el motor de backtest y el broker lo piden."""
        return ExecutionOracle(self.bars[symbol], audit)

    def context(
        self,
        symbol: str,
        as_of: datetime,
        desk: DeskState,
        config: SystemConfig,
        audit: AccessAudit,
        *,
        open_positions: tuple[Position, ...] = (),
        peers: tuple[str, ...] | None = None,
    ) -> MarketContext:
        """
        Arma el contexto sellado en `as_of`.

        El timeframe superior se calcula resampleando SOLO las barras visibles
        y descartando el bucket en formacion. Si se usara la vela semanal en
        curso, el sistema estaria mirando el cierre del viernes desde el martes.
        """
        view = self.view(symbol, as_of, audit)
        peer_syms = peers if peers is not None else tuple(s for s in self.bars if s != symbol)
        peer_views = {s: self.view(s, as_of, audit) for s in peer_syms if s in self.bars}

        visible = view.window(self.history_window)
        htf_bucket = timedelta(hours=4) if self.intraday else timedelta(days=7)
        htf = resample(visible, htf_bucket, include_partial=False)
        label = "4H" if self.intraday else "SEMANAL"

        return MarketContext(
            as_of=as_of,
            symbol=symbol,
            view=view,
            config=config,
            calendar=self.calendar,
            desk=desk,
            peers=peer_views,
            pit=self.pit,
            events=self.events,
            fundamentals=self.fundamentals,
            quote=self.quotes.get(symbol, {}).get(as_of),
            open_positions=open_positions,
            sector=self.sector_map.get(symbol, "UNKNOWN"),
            sector_map=self.sector_map,
            higher_tf=htf,
            higher_tf_label=label,
            intraday_available=self.intraday,
        )
