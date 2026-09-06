"""
Calendario de sesiones y de eventos.

Dos responsabilidades separadas:

  TradingCalendar : que dias hay mercado. Feriados calculados, no hardcodeados,
                    para que el backtest sea valido en cualquier anio.
  EventCalendar   : que eventos vienen. Alimenta los vetos de CAPA 0.

Detalle que casi nadie modela y rompe backtests: la fecha de earnings de una
empresa TAMBIEN es informacion con fecha de publicacion. Una empresa confirma
su fecha ~3 semanas antes. Usar la fecha definitiva para filtrar operaciones
de dos meses antes es look-ahead. Por eso `EarningsEvent` lleva `announced_at`
y, cuando la fecha todavia no fue confirmada, el sistema usa una ESTIMACION y
igual veta -- ante la duda, afuera.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Iterable


# ---------------------------------------------------------------------------
# Feriados de mercado (NYSE / Nasdaq)
# ---------------------------------------------------------------------------

def easter(year: int) -> date:
    """Algoritmo gregoriano anonimo. Necesario para el Viernes Santo."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    """Sabado -> viernes anterior; domingo -> lunes siguiente."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def us_market_holidays(year: int) -> set[date]:
    h = {
        _observed(date(year, 1, 1)),                   # Ano nuevo
        _nth_weekday(year, 1, 0, 3),                   # MLK (3er lunes enero)
        _nth_weekday(year, 2, 0, 3),                   # Presidentes (3er lunes febrero)
        easter(year) - timedelta(days=2),              # Viernes Santo
        _last_weekday(year, 5, 0),                     # Memorial Day
        _observed(date(year, 7, 4)),                   # Independencia
        _nth_weekday(year, 9, 0, 1),                   # Labor Day
        _nth_weekday(year, 11, 3, 4),                  # Accion de Gracias
        _observed(date(year, 12, 25)),                 # Navidad
    }
    if year >= 2022:
        h.add(_observed(date(year, 6, 19)))            # Juneteenth
    return h


# ---------------------------------------------------------------------------
# Calendario de sesiones
# ---------------------------------------------------------------------------

class TradingCalendar:
    """Dias de mercado de EEUU. Cachea feriados por anio."""

    __slots__ = ("_cache", "_extra")

    def __init__(self, extra_closures: Iterable[date] = ()) -> None:
        self._cache: dict[int, set[date]] = {}
        # Cierres no recurrentes: 11-S (2001), Sandy (2012), lutos nacionales.
        self._extra: set[date] = set(extra_closures)

    def holidays(self, year: int) -> set[date]:
        if year not in self._cache:
            self._cache[year] = us_market_holidays(year)
        return self._cache[year]

    def is_session(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays(d.year) and d not in self._extra

    def next_session(self, d: date) -> date:
        cur = d + timedelta(days=1)
        while not self.is_session(cur):
            cur += timedelta(days=1)
        return cur

    def prev_session(self, d: date) -> date:
        cur = d - timedelta(days=1)
        while not self.is_session(cur):
            cur -= timedelta(days=1)
        return cur

    def sessions_between(self, a: date, b: date) -> int:
        if b <= a:
            return 0
        n, cur = 0, a
        while cur < b:
            cur += timedelta(days=1)
            if self.is_session(cur):
                n += 1
        return n

    def add_sessions(self, d: date, n: int) -> date:
        cur = d
        for _ in range(n):
            cur = self.next_session(cur)
        return cur

    def long_weekend_ahead(self, d: date, lookahead_days: int) -> tuple[bool, str]:
        """
        Veto CAPA 0: fin de semana largo o feriado proximo con posicion abierta.

        El riesgo real es el hueco: tres o cuatro dias sin poder ajustar el stop
        mientras el resto del mundo sigue operando y descontando noticias.
        """
        cur = d
        for _ in range(lookahead_days):
            cur += timedelta(days=1)
            if cur.weekday() < 5 and not self.is_session(cur):
                gap = 1
                probe = cur + timedelta(days=1)
                while not self.is_session(probe):
                    gap += 1
                    probe += timedelta(days=1)
                return True, f"feriado el {cur.isoformat()}; mercado cerrado {gap} dia(s) corridos"
        # Un finde comun no es veto; si es viernes y el lunes es feriado, si.
        return False, ""


# ---------------------------------------------------------------------------
# Calendario de eventos
# ---------------------------------------------------------------------------

class EventKind(str, Enum):
    RATE_DECISION = "DECISION_DE_TASAS"
    CPI = "INFLACION_CPI"
    PCE = "INFLACION_PCE"
    PAYROLLS = "EMPLEO_NOMINAS"
    CLAIMS = "PEDIDOS_SUBSIDIO"
    GDP = "PBI"
    ISM = "ISM_PMI"
    FOMC_MINUTES = "MINUTAS_FOMC"
    TREASURY_AUCTION = "LICITACION_TESORO"
    ELECTION = "ELECCION"
    OTHER = "OTRO"


@dataclass(frozen=True, slots=True)
class MacroEvent:
    kind: EventKind
    scheduled_at: datetime
    importance: int = 3                 # 1 (menor) a 5 (mueve todo)
    region: str = "US"
    consensus: float | None = None      # lo que el mercado espera
    actual: float | None = None         # se completa despues del evento
    released_at: datetime | None = None # cuando se conocio el dato real

    def known_at(self, as_of: datetime) -> bool:
        """El calendario del evento se conoce con meses de anticipacion."""
        return True

    def result_known_at(self, as_of: datetime) -> bool:
        return self.released_at is not None and self.released_at <= as_of

    def surprise(self, as_of: datetime) -> float | None:
        """
        Sorpresa = real - consenso, disponible SOLO despues de la publicacion.
        El mercado ya tiene precio para lo esperado; lo que mueve es esto.
        """
        if not self.result_known_at(as_of) or self.consensus is None or self.actual is None:
            return None
        return self.actual - self.consensus


@dataclass(frozen=True, slots=True)
class EarningsEvent:
    symbol: str
    expected_date: date
    announced_at: datetime | None = None   # cuando la empresa confirmo la fecha
    estimated: bool = False                # True = fecha inferida, no confirmada
    confirmed_date: date | None = None

    def date_known_at(self, as_of: datetime) -> date | None:
        """
        Fecha de earnings TAL COMO SE CONOCIA a `as_of`.

        - Si la empresa ya confirmo antes de as_of -> fecha confirmada.
        - Si no confirmo todavia -> se usa la estimacion (cadencia trimestral).
          El veto se aplica igual: ante la duda, afuera.
        """
        if self.announced_at is not None and self.announced_at <= as_of and self.confirmed_date:
            return self.confirmed_date
        return self.expected_date


@dataclass(slots=True)
class EventCalendar:
    macro: list[MacroEvent] = field(default_factory=list)
    earnings: list[EarningsEvent] = field(default_factory=list)

    def add_macro(self, e: MacroEvent) -> None:
        self.macro.append(e)

    def add_earnings(self, e: EarningsEvent) -> None:
        self.earnings.append(e)

    def macro_within(self, as_of: datetime, hours: int, min_importance: int = 4) -> tuple[MacroEvent, ...]:
        """Eventos macro programados en la ventana. Alimenta el veto de 48hs."""
        horizon = as_of + timedelta(hours=hours)
        return tuple(
            e for e in self.macro
            if e.importance >= min_importance and as_of <= e.scheduled_at <= horizon
        )

    def earnings_within(
        self, symbol: str, as_of: datetime, bdays: int, cal: TradingCalendar
    ) -> tuple[EarningsEvent, ...]:
        """Earnings de la empresa dentro de N dias habiles, con fecha PIT."""
        limit = cal.add_sessions(as_of.date(), bdays)
        out = []
        for e in self.earnings:
            if e.symbol != symbol:
                continue
            d = e.date_known_at(as_of)
            if d is not None and as_of.date() <= d <= limit:
                out.append(e)
        return tuple(out)
