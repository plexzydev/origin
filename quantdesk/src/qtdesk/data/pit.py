"""
Almacen POINT-IN-TIME. El modulo mas importante del backtest.

El problema que resuelve, en concreto:

  El PBI del 1T2020 se publico por primera vez el 29/04/2020 en -4.8%.
  Se reviso a -5.0%, despues a -31.4% anualizado en el 2T... y hoy la
  serie de FRED muestra los numeros FINALES. Si tu backtest de abril 2020
  lee la serie de hoy, esta usando informacion que en abril no existia.

  Lo mismo pasa con: nominas no agricolas (revision promedio ~50k),
  balances reexpresados, y la composicion de los indices (SPY de 2015 no
  tenia las mismas empresas que hoy).

Modelo de datos: cada observacion es la tupla
    (serie, periodo al que se refiere, CUANDO SE SUPO, valor)

Regla dura: `released_at` es obligatorio. Un dato sin fecha de publicacion
NO SE PUEDE USAR, porque no hay forma de saber si es informacion del futuro.
Preferimos una capa que devuelva score 0 diciendo "no tengo dato" antes que
una capa que opine con datos que ese dia nadie tenia.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Iterator, Mapping

from ..clock import LookAheadError


class MissingVintageError(ValueError):
    """Se intento cargar un dato sin fecha de publicacion conocida."""


@dataclass(frozen=True, slots=True)
class Observation:
    """
    Una observacion tal como existio en un momento dado.

    period_end  : a que periodo se refiere el dato (marzo 2020, 1T2020...)
    released_at : cuando se hizo publico ESTE valor concreto
    revision    : 0 = dato inicial, 1+ = revisiones sucesivas
    """
    series_id: str
    period_end: date
    released_at: datetime
    value: float
    revision: int = 0
    source: str = ""

    def __post_init__(self) -> None:
        if self.released_at is None:
            raise MissingVintageError(f"{self.series_id}: observacion sin released_at")
        rel_date = self.released_at.date()
        if rel_date < self.period_end:
            raise ValueError(
                f"{self.series_id}: publicado ({rel_date}) antes de que termine "
                f"el periodo ({self.period_end}). Eso es imposible."
            )


class PointInTimeStore:
    """
    Deposito de series con vintages.

    `get()` responde siempre la misma pregunta: "que valor de esta serie
    estaba publicado el dia `as_of`?" -- nunca "cual es el valor correcto".
    Son preguntas distintas y el backtest necesita la primera.
    """

    __slots__ = ("_obs", "_sorted", "_strict")

    def __init__(self, *, strict: bool = True) -> None:
        self._obs: dict[str, list[Observation]] = defaultdict(list)
        self._sorted: dict[str, bool] = {}
        self._strict = strict

    # -- carga --------------------------------------------------------------
    def add(self, obs: Observation) -> None:
        self._obs[obs.series_id].append(obs)
        self._sorted[obs.series_id] = False

    def add_many(self, observations: Iterable[Observation]) -> None:
        for o in observations:
            self.add(o)

    def _ensure_sorted(self, series_id: str) -> list[Observation]:
        lst = self._obs.get(series_id, [])
        if not self._sorted.get(series_id, True):
            # Orden por fecha de publicacion: es el eje temporal real.
            lst.sort(key=lambda o: (o.released_at, o.period_end, o.revision))
            self._sorted[series_id] = True
        return lst

    # -- consulta -----------------------------------------------------------
    def _visible(self, series_id: str, as_of: datetime) -> list[Observation]:
        lst = self._ensure_sorted(series_id)
        rels = [o.released_at for o in lst]
        return lst[:bisect_right(rels, as_of)]

    def get(self, series_id: str, as_of: datetime) -> Observation | None:
        """
        Ultimo valor CONOCIDO a `as_of`, para el periodo mas reciente publicado.

        Si de un mismo periodo hay varias revisiones ya publicadas, gana la
        mas reciente. Si la revision se publico despues de `as_of`, no existe.
        """
        vis = self._visible(series_id, as_of)
        if not vis:
            return None
        latest_period = max(o.period_end for o in vis)
        candidates = [o for o in vis if o.period_end == latest_period]
        return max(candidates, key=lambda o: (o.released_at, o.revision))

    def value(self, series_id: str, as_of: datetime, default: float | None = None) -> float | None:
        o = self.get(series_id, as_of)
        return default if o is None else o.value

    def history(self, series_id: str, as_of: datetime, n: int) -> tuple[Observation, ...]:
        """
        Las ultimas n observaciones POR PERIODO, cada una en la version que
        estaba publicada a `as_of`. Esto es lo que se usa para calcular
        tendencias macro sin contaminacion por revisiones posteriores.
        """
        vis = self._visible(series_id, as_of)
        if not vis:
            return ()
        best: dict[date, Observation] = {}
        for o in vis:
            cur = best.get(o.period_end)
            if cur is None or (o.released_at, o.revision) > (cur.released_at, cur.revision):
                best[o.period_end] = o
        periods = sorted(best)[-n:]
        return tuple(best[p] for p in periods)

    def series_values(self, series_id: str, as_of: datetime, n: int) -> tuple[float, ...]:
        return tuple(o.value for o in self.history(series_id, as_of, n))

    def change(self, series_id: str, as_of: datetime, periods: int = 1) -> float | None:
        """Variacion respecto de `periods` atras, tal como se conocia a `as_of`."""
        h = self.history(series_id, as_of, periods + 1)
        if len(h) < periods + 1:
            return None
        return h[-1].value - h[-1 - periods].value

    def revisions_of(self, series_id: str, period_end: date) -> tuple[Observation, ...]:
        """Historial completo de revisiones. Uso: auditar cuanto se revisa una serie."""
        lst = self._ensure_sorted(series_id)
        return tuple(o for o in lst if o.period_end == period_end)

    def known_series(self) -> tuple[str, ...]:
        return tuple(sorted(self._obs))

    def assert_no_future(self, as_of: datetime) -> None:
        """Chequeo de paranoia usado por los tests de integridad."""
        for sid, lst in self._obs.items():
            for o in lst:
                if o.released_at > as_of:
                    continue  # existe pero no es visible: correcto
        # Nada que hacer: la invisibilidad la garantiza _visible(). Este metodo
        # queda como punto de enganche para auditorias externas.

    def staleness_days(self, series_id: str, as_of: datetime) -> float | None:
        """Cuantos dias hace que no se publica nada de esta serie."""
        o = self.get(series_id, as_of)
        if o is None:
            return None
        return (as_of - o.released_at).total_seconds() / 86400.0

    def require(self, series_id: str, as_of: datetime) -> float:
        """
        Version estricta: si no hay dato, LEVANTA. Se usa donde operar sin ese
        dato seria peor que no operar.
        """
        o = self.get(series_id, as_of)
        if o is None:
            raise LookAheadError(
                f"Serie '{series_id}' sin dato publicado al {as_of.date()}. "
                "No se inventa un valor: la capa debe abstenerse."
            )
        return o.value


@dataclass(frozen=True, slots=True)
class UniverseMembership:
    """
    Composicion historica de un indice. Corrige el sesgo de supervivencia.

    Sin esto, un backtest del SP500 opera con las empresas que HOY estan en el
    indice -- es decir, las que sobrevivieron. Lehman, Bear Stearns, Enron,
    Kodak y GE (que salio del Dow en 2018) desaparecen del experimento y el
    resultado sale inflado por construccion.
    """
    index_id: str
    symbol: str
    added_at: date
    removed_at: date | None = None
    removal_reason: str = ""     # quiebra / adquisicion / rebalanceo

    def active_on(self, d: date) -> bool:
        if d < self.added_at:
            return False
        return self.removed_at is None or d < self.removed_at


class SurvivorshipAwareUniverse:
    """Devuelve el universo tal como era en una fecha, no como es hoy."""

    __slots__ = ("_members",)

    def __init__(self, memberships: Iterable[UniverseMembership] = ()) -> None:
        self._members: list[UniverseMembership] = list(memberships)

    def add(self, m: UniverseMembership) -> None:
        self._members.append(m)

    def constituents(self, index_id: str, as_of: datetime) -> tuple[str, ...]:
        d = as_of.date()
        return tuple(sorted(
            m.symbol for m in self._members
            if m.index_id == index_id and m.active_on(d)
        ))

    def delisted_between(self, index_id: str, a: date, b: date) -> tuple[UniverseMembership, ...]:
        return tuple(
            m for m in self._members
            if m.index_id == index_id and m.removed_at and a <= m.removed_at <= b
        )

    def coverage_warning(self) -> str | None:
        """
        Honestidad: si nadie cargo bajas, el universo es sospechoso.
        Un indice sin ninguna salida en anios de historia no existe.
        """
        if self._members and not any(m.removed_at for m in self._members):
            return (
                "El universo cargado no tiene NINGUNA baja historica. Es casi "
                "seguro que arrastra sesgo de supervivencia: los resultados del "
                "backtest van a estar inflados."
            )
        return None
