"""
Fundamentales con fecha de publicacion. Fuente: SEC EDGAR + APIs.

El campo que hace toda la diferencia es `filed_at`: la fecha en que la SEC
ACEPTO el filing, no el cierre del trimestre. Un 10-Q del trimestre cerrado
el 31/03 se publica entre el 01/05 y el 15/05. Filtrar por `period_end` en un
backtest te da 30-45 dias de informacion que nadie tenia.

Segundo problema: las REEXPRESIONES. Cuando una empresa corrige un balance
anterior, la base de datos de hoy muestra el numero corregido. El mercado de
entonces operaba con el numero viejo. Por eso cada registro guarda su
`amendment_of` y el store devuelve la version vigente A ESA FECHA.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class FundamentalRecord:
    """Foto de una empresa tal como la reporto un filing concreto."""
    symbol: str
    period_end: date
    filed_at: datetime                 # SEC acceptance datetime
    form_type: str = "10-Q"            # 10-K / 10-Q / 8-K / 10-K-A
    sector: str = "UNKNOWN"

    # Resultados
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None

    # Caja: donde se ve si las ganancias son reales
    operating_cash_flow: float | None = None
    capex: float | None = None

    # Balance y deuda
    total_debt: float | None = None
    cash: float | None = None
    ebitda: float | None = None
    interest_expense: float | None = None
    # Calendario de vencimientos: {anio: monto} y a que tasa refinancian
    debt_maturities: tuple[tuple[int, float], ...] = ()
    weighted_avg_coupon: float | None = None
    refi_market_rate: float | None = None      # a que tasa saldria hoy

    # Acciones
    shares_diluted: float | None = None
    buyback_cash: float | None = None
    insider_net_usd: float | None = None       # compras - ventas de insiders

    # Estimaciones y sorpresas (la DIRECCION importa mas que el nivel)
    eps_estimate_fwd: float | None = None
    eps_estimate_fwd_90d_ago: float | None = None
    eps_surprise_pct: float | None = None
    price_reaction_pct: float | None = None    # reaccion del precio al reporte

    amendment_of: date | None = None           # si reexpresa un periodo previo

    # -- derivados ---------------------------------------------------------
    @property
    def free_cash_flow(self) -> float | None:
        if self.operating_cash_flow is None or self.capex is None:
            return None
        return self.operating_cash_flow - abs(self.capex)

    @property
    def fcf_vs_earnings(self) -> float | None:
        """
        FCF / utilidad neta. Bandera roja clasica: ganancia contable creciente
        con caja estancada significa que la ganancia esta en cuentas por cobrar
        o en capitalizacion agresiva de gastos.
        """
        fcf, ni = self.free_cash_flow, self.net_income
        if fcf is None or ni is None or ni == 0:
            return None
        return fcf / ni

    @property
    def net_debt_to_ebitda(self) -> float | None:
        if self.total_debt is None or self.ebitda is None or self.ebitda <= 0:
            return None
        return (self.total_debt - (self.cash or 0.0)) / self.ebitda

    @property
    def interest_coverage(self) -> float | None:
        if self.operating_income is None or not self.interest_expense:
            return None
        return self.operating_income / abs(self.interest_expense)

    @property
    def operating_margin(self) -> float | None:
        if self.operating_income is None or not self.revenue:
            return None
        return self.operating_income / self.revenue

    @property
    def gross_margin(self) -> float | None:
        if self.gross_profit is None or not self.revenue:
            return None
        return self.gross_profit / self.revenue

    @property
    def estimate_revision_pct(self) -> float | None:
        """Direccion del cambio de estimaciones a 90 dias."""
        now, before = self.eps_estimate_fwd, self.eps_estimate_fwd_90d_ago
        if now is None or not before:
            return None
        return (now - before) / abs(before)

    def refi_risk(self, horizon_years: int = 2) -> float | None:
        """
        Cuanta deuda vence pronto y cuanto mas cara sale renovarla.

        Devuelve el costo incremental anual como fraccion del EBITDA. Es la
        forma concreta de responder "a que tasa refinancian" sin adivinar.
        """
        if not self.debt_maturities or self.refi_market_rate is None or self.weighted_avg_coupon is None:
            return None
        if not self.ebitda or self.ebitda <= 0:
            return None
        this_year = max(y for y, _ in self.debt_maturities) - 10  # placeholder de anclaje
        soon = sum(amt for y, amt in self.debt_maturities if y <= self.period_end.year + horizon_years)
        delta_rate = self.refi_market_rate - self.weighted_avg_coupon
        return (soon * delta_rate) / self.ebitda


class FundamentalStore:
    """
    Devuelve el ultimo filing PUBLICADO a una fecha. Nunca el mas reciente
    en el sentido de "el mejor dato disponible hoy".
    """

    __slots__ = ("_by_symbol", "_sorted")

    def __init__(self) -> None:
        self._by_symbol: dict[str, list[FundamentalRecord]] = defaultdict(list)
        self._sorted: dict[str, bool] = {}

    def add(self, rec: FundamentalRecord) -> None:
        self._by_symbol[rec.symbol].append(rec)
        self._sorted[rec.symbol] = False

    def _ensure(self, symbol: str) -> list[FundamentalRecord]:
        lst = self._by_symbol.get(symbol, [])
        if not self._sorted.get(symbol, True):
            lst.sort(key=lambda r: (r.filed_at, r.period_end))
            self._sorted[symbol] = True
        return lst

    def latest(self, symbol: str, as_of: datetime) -> FundamentalRecord | None:
        lst = self._ensure(symbol)
        filed = [r.filed_at for r in lst]
        vis = lst[:bisect_right(filed, as_of)]
        return vis[-1] if vis else None

    def history(self, symbol: str, as_of: datetime, n: int) -> tuple[FundamentalRecord, ...]:
        """
        Ultimos n trimestres, cada uno en la version vigente a `as_of`.
        Una reexpresion publicada despues de `as_of` no se aplica.
        """
        lst = self._ensure(symbol)
        filed = [r.filed_at for r in lst]
        vis = lst[:bisect_right(filed, as_of)]
        best: dict[date, FundamentalRecord] = {}
        for r in vis:
            cur = best.get(r.period_end)
            if cur is None or r.filed_at > cur.filed_at:
                best[r.period_end] = r
        periods = sorted(best)[-n:]
        return tuple(best[p] for p in periods)

    def peer_metric(self, symbols: list[str], as_of: datetime, attr: str) -> tuple[float, ...]:
        """Metrica del sector para valuacion RELATIVA (nunca absoluta)."""
        out = []
        for s in symbols:
            r = self.latest(s, as_of)
            if r is None:
                continue
            v = getattr(r, attr, None)
            v = v() if callable(v) else v
            if v is not None:
                out.append(float(v))
        return tuple(out)

    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_symbol))
