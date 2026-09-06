"""
El reloj del sistema.

Toda la arquitectura se apoya en una sola idea: existe un unico instante
`as_of` que define QUE SE SABE. Ningun modulo puede leer un dato cuyo
`available_at` sea posterior a `as_of`. No es una convencion: es una
excepcion en tiempo de ejecucion.

El look-ahead bias no se evita con disciplina. Se evita haciendolo imposible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


class LookAheadError(RuntimeError):
    """
    Se intento leer informacion del futuro.

    Esta excepcion NUNCA debe capturarse y continuar. Si salta en produccion,
    el sistema tiene un bug de diseno y hay que apagarlo, no parchearlo.
    """


@dataclass(slots=True)
class AsOfClock:
    """
    Reloj monotono. Solo avanza. `rewind` existe unicamente para el arranque
    de un backtest y deja rastro en `rewinds` para que la auditoria lo vea.
    """
    _now: datetime
    rewinds: int = 0
    _frozen: bool = False

    @property
    def now(self) -> datetime:
        return self._now

    def advance_to(self, ts: datetime) -> None:
        if self._frozen:
            raise LookAheadError("Reloj congelado: no se puede avanzar durante una evaluacion")
        if ts < self._now:
            raise LookAheadError(f"Retroceso de reloj prohibido: {self._now} -> {ts}")
        self._now = ts

    def rewind_for_new_run(self, ts: datetime) -> None:
        """Solo para iniciar una corrida nueva. Contabilizado."""
        self._now = ts
        self.rewinds += 1

    def freeze(self) -> "_FrozenScope":
        """
        Context manager: durante la evaluacion de una decision el reloj no se
        mueve. Impide el patron 'calculo la senal, avanzo, uso el dato nuevo'.
        """
        return _FrozenScope(self)

    def visible(self, available_at: datetime) -> bool:
        return available_at <= self._now


@dataclass(slots=True)
class _FrozenScope:
    clock: AsOfClock

    def __enter__(self) -> AsOfClock:
        self.clock._frozen = True
        return self.clock

    def __exit__(self, *exc: object) -> None:
        self.clock._frozen = False


@dataclass(slots=True)
class AccessAudit:
    """
    Bitacora de accesos a datos. El motor de backtest la revisa despues de
    CADA barra: si un acceso de senal toco un timestamp > as_of, la corrida
    se considera contaminada y se aborta.

    Esto convierte el look-ahead de "bug sutil que descubris en produccion"
    a "error ruidoso en el test".
    """
    signal_accesses: list[tuple[datetime, str]] = field(default_factory=list)
    execution_accesses: list[tuple[datetime, str]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    def record_signal(self, ts: datetime, what: str) -> None:
        self.signal_accesses.append((ts, what))

    def record_execution(self, ts: datetime, what: str) -> None:
        self.execution_accesses.append((ts, what))

    def max_signal_ts(self) -> datetime | None:
        return max((t for t, _ in self.signal_accesses), default=None)

    def assert_clean(self, as_of: datetime) -> None:
        worst = self.max_signal_ts()
        if worst is not None and worst > as_of:
            offenders = [w for t, w in self.signal_accesses if t > as_of]
            msg = f"Acceso de senal al futuro: {worst} > as_of {as_of}. Origen: {offenders[:5]}"
            self.violations.append(msg)
            raise LookAheadError(msg)

    def reset(self) -> None:
        self.signal_accesses.clear()
        self.execution_accesses.clear()


def business_days_between(a: datetime, b: datetime) -> int:
    """Dias habiles (lun-vie) entre dos fechas. Feriados los maneja el calendario."""
    if b < a:
        a, b = b, a
    days = 0
    cur = a.date()
    end = b.date()
    while cur < end:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days
