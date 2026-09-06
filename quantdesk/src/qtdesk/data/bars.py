"""
Almacen de barras y la VISTA SELLADA que reciben las estrategias.

Aca vive la defensa principal contra el look-ahead:

  BarSeries       -> deposito crudo. Nadie que decida lo toca directo.
  SignalView      -> lo unico que ve la logica de senal. Corta en `as_of`.
  ExecutionOracle -> acceso privilegiado a la barra SIGUIENTE, exclusivo del
                     ejecutor. Sus accesos se auditan por separado.

Si una capa de analisis recibe un ExecutionOracle, es un bug de cableado, no
un error de logica. Por eso los tipos son distintos y no intercambiables.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Sequence

from ..clock import AccessAudit, LookAheadError
from ..contracts import Bar


@dataclass(slots=True)
class BarSeries:
    """Serie ordenada e inmutable de barras para un simbolo."""
    symbol: str
    bars: tuple[Bar, ...]
    _ts: tuple[datetime, ...] = ()

    def __post_init__(self) -> None:
        if any(self.bars[i].ts >= self.bars[i + 1].ts for i in range(len(self.bars) - 1)):
            raise ValueError(f"{self.symbol}: barras desordenadas o con timestamps duplicados")
        self._ts = tuple(b.ts for b in self.bars)

    def __len__(self) -> int:
        return len(self.bars)

    def index_at_or_before(self, ts: datetime) -> int:
        """Indice de la ultima barra con ts <= dado. -1 si no hay ninguna."""
        return bisect_right(self._ts, ts) - 1

    def raw(self, i: int) -> Bar:
        return self.bars[i]

    @classmethod
    def from_iterable(cls, symbol: str, bars: Iterable[Bar]) -> "BarSeries":
        return cls(symbol, tuple(sorted(bars, key=lambda b: b.ts)))


class SignalView:
    """
    Ventana de solo-lectura hasta `as_of`. Cada acceso queda registrado.

    No expone indices absolutos: solo "las ultimas N barras conocidas". Eso
    elimina la clase entera de bugs del tipo `bars[i+1]` en la logica de senal.
    """

    __slots__ = ("_series", "_as_of", "_audit", "_cut")

    def __init__(self, series: BarSeries, as_of: datetime, audit: AccessAudit) -> None:
        self._series = series
        self._as_of = as_of
        self._audit = audit
        self._cut = series.index_at_or_before(as_of)   # ultima barra visible

    @property
    def symbol(self) -> str:
        return self._series.symbol

    @property
    def as_of(self) -> datetime:
        return self._as_of

    @property
    def available(self) -> int:
        """Cuantas barras hay disponibles. 0 = la capa debe devolver score 0."""
        return self._cut + 1

    def window(self, n: int) -> tuple[Bar, ...]:
        """Ultimas n barras cerradas y conocidas. Puede devolver menos de n."""
        if n <= 0:
            raise ValueError("window(n) exige n>0")
        if self._cut < 0:
            return ()
        lo = max(0, self._cut - n + 1)
        out = self._series.bars[lo:self._cut + 1]
        if out:
            self._audit.record_signal(out[-1].ts, f"{self.symbol}.window({n})")
        return out

    def last(self) -> Bar | None:
        if self._cut < 0:
            return None
        b = self._series.raw(self._cut)
        self._audit.record_signal(b.ts, f"{self.symbol}.last")
        return b

    def at(self, ts: datetime) -> Bar:
        """Acceso por timestamp. Explota si se pide el futuro."""
        if ts > self._as_of:
            raise LookAheadError(
                f"{self.symbol}: acceso a {ts} con as_of={self._as_of}. "
                "Esto es informacion que ese dia no existia."
            )
        i = self._series.index_at_or_before(ts)
        if i < 0 or self._series.raw(i).ts != ts:
            raise KeyError(f"{self.symbol}: no hay barra en {ts}")
        self._audit.record_signal(ts, f"{self.symbol}.at")
        return self._series.raw(i)

    def closes(self, n: int) -> tuple[float, ...]:
        return tuple(b.close for b in self.window(n))

    def highs(self, n: int) -> tuple[float, ...]:
        return tuple(b.high for b in self.window(n))

    def lows(self, n: int) -> tuple[float, ...]:
        return tuple(b.low for b in self.window(n))

    def volumes(self, n: int) -> tuple[float, ...]:
        return tuple(b.volume for b in self.window(n))

    # -- deliberadamente NO existe next(), future(), ni acceso por indice
    #    absoluto. Si lo necesitas para una senal, la senal esta mal planteada.


class ExecutionOracle:
    """
    Acceso a la barra de EJECUCION: la siguiente a la de la senal.

    Solo el motor de backtest y el broker simulado lo reciben. Sus lecturas se
    registran en `execution_accesses`, separadas de las de senal, para que la
    auditoria distinga "el ejecutor miro la apertura de manana" (legitimo y
    necesario) de "la estrategia miro la apertura de manana" (fraude).
    """

    __slots__ = ("_series", "_audit")

    def __init__(self, series: BarSeries, audit: AccessAudit) -> None:
        self._series = series
        self._audit = audit

    def bar_after(self, ts: datetime) -> Bar | None:
        """Primera barra con timestamp estrictamente mayor a `ts`."""
        i = self._series.index_at_or_before(ts)
        nxt = i + 1
        if nxt >= len(self._series):
            return None
        b = self._series.raw(nxt)
        self._audit.record_execution(b.ts, f"{self._series.symbol}.bar_after({ts})")
        return b


# ---------------------------------------------------------------------------
# Multi-timeframe
# ---------------------------------------------------------------------------

def resample(bars: Sequence[Bar], bucket: timedelta, *, include_partial: bool = False) -> tuple[Bar, ...]:
    """
    Agrega barras a un timeframe superior.

    CRITICO: por defecto emite unicamente buckets CERRADOS. Usar la barra
    semanal en curso -- calculada con los cinco dias de la semana cuando es
    martes -- es una de las formas mas comunes y mas invisibles de look-ahead
    en sistemas multi-timeframe.

    `include_partial=True` existe solo para operar en vivo sobre la vela en
    formacion, y el llamador debe saber lo que hace.
    """
    if not bars:
        return ()
    out: list[Bar] = []
    cur_key: datetime | None = None
    o = h = l = c = 0.0
    v = 0.0
    last_ts: datetime | None = None

    for b in bars:
        key = _bucket_start(b.ts, bucket)
        if cur_key is None or key != cur_key:
            if cur_key is not None:
                out.append(Bar(last_ts, o, h, l, c, v))     # type: ignore[arg-type]
            cur_key, o, h, l, c, v = key, b.open, b.high, b.low, b.close, b.volume
        else:
            h = max(h, b.high)
            l = min(l, b.low)
            c = b.close
            v += b.volume
        last_ts = b.ts

    # El ultimo bucket puede estar incompleto: solo se emite si se pide.
    if cur_key is not None and include_partial:
        out.append(Bar(last_ts, o, h, l, c, v))             # type: ignore[arg-type]
    elif cur_key is not None and last_ts is not None and _bucket_closed(last_ts, bucket):
        out.append(Bar(last_ts, o, h, l, c, v))
    return tuple(out)


def _bucket_start(ts: datetime, bucket: timedelta) -> datetime:
    if bucket >= timedelta(days=7):
        # Semanal: ancla en lunes.
        monday = ts.date() - timedelta(days=ts.weekday())
        return datetime(monday.year, monday.month, monday.day, tzinfo=ts.tzinfo)
    if bucket >= timedelta(days=1):
        return datetime(ts.year, ts.month, ts.day, tzinfo=ts.tzinfo)
    secs = int(bucket.total_seconds())
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % secs), tz=ts.tzinfo)


def _bucket_closed(last_ts: datetime, bucket: timedelta) -> bool:
    """
    Heuristica conservadora: solo damos por cerrado un bucket semanal si la
    ultima barra cae en viernes; uno diario, siempre (la barra diaria cierra
    con la sesion). Ante la duda, NO se emite.
    """
    if bucket >= timedelta(days=7):
        return last_ts.weekday() == 4
    if bucket >= timedelta(days=1):
        return True
    start = _bucket_start(last_ts, bucket)
    return last_ts >= start + bucket - timedelta(seconds=1)
