"""
Cortafuegos en cascada.

Cuatro niveles independientes que se acumulan, mas la escalera de drawdown.
Ninguno se cancela con otro: si dos aplican, gana el mas restrictivo.

  perdida diaria   -> cierre de jornada
  perdida semanal  -> tamano a la mitad
  perdida mensual  -> apagado total, reset manual obligatorio
  3 perdidas segui -> pausa forzada y auditoria del proceso
  drawdown         -> escalera que reduce tamano automaticamente

PROHIBICION DE MARTINGALA
El multiplicador final es siempre `min()` de los aplicables. No existe ninguna
ruta en el codigo que devuelva un multiplicador mayor a 1.0. Aumentar el
tamano para recuperar no esta "desaconsejado": es inalcanzable desde este
modulo, y hay un test que lo verifica sobre miles de secuencias aleatorias.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..config import RiskConfig
from .state import DeskState


class BreakerLevel(str, Enum):
    NORMAL = "NORMAL"
    DRAWDOWN_REDUCED = "DRAWDOWN_REDUCIDO"
    WEEKLY_HALF = "SEMANAL_MITAD_TAMANO"
    DAILY_HALT = "DIARIO_CIERRE_JORNADA"
    STREAK_PAUSE = "RACHA_PAUSA_AUDITORIA"
    SHUTDOWN = "MENSUAL_APAGADO_TOTAL"
    MANUAL_KILL = "APAGADO_MANUAL"

    @property
    def rank(self) -> int:
        return {
            "NORMAL": 0, "DRAWDOWN_REDUCIDO": 1, "SEMANAL_MITAD_TAMANO": 2,
            "DIARIO_CIERRE_JORNADA": 3, "RACHA_PAUSA_AUDITORIA": 4,
            "MENSUAL_APAGADO_TOTAL": 5, "APAGADO_MANUAL": 6,
        }[self.value]


@dataclass(frozen=True, slots=True)
class BreakerVerdict:
    level: BreakerLevel
    can_open: bool
    size_multiplier: float
    reasons: tuple[str, ...]
    requires_manual_reset: bool

    @property
    def blocked(self) -> bool:
        return not self.can_open


def drawdown_multiplier(dd: float, ladder: tuple[tuple[float, float], ...]) -> float:
    """
    Escalera de drawdown. Devuelve el multiplicador del PEOR escalon alcanzado.
    Monotona no creciente en `dd` por construccion.
    """
    mult = 1.0
    for threshold, m in sorted(ladder):
        if dd >= threshold:
            mult = min(mult, m)
    return mult


def evaluate(state: DeskState, cfg: RiskConfig) -> BreakerVerdict:
    """
    Evalua todos los cortafuegos. Devuelve el veredicto combinado.

    Se llama ANTES de cada apertura y despues de cada marca a mercado.
    """
    reasons: list[str] = []
    level = BreakerLevel.NORMAL
    can_open = True
    mult = 1.0
    manual = False

    # -- 0. Interruptor manual: gana sobre todo -----------------------------
    if state.manual_kill:
        return BreakerVerdict(
            BreakerLevel.MANUAL_KILL, False, 0.0,
            ("apagado manual activo: ninguna apertura hasta reanudacion explicita",),
            True,
        )

    # -- 1. Escalera de drawdown -------------------------------------------
    dd = state.drawdown
    dd_mult = drawdown_multiplier(dd, cfg.drawdown_ladder)
    if dd_mult < 1.0:
        mult = min(mult, dd_mult)
        level = max(level, BreakerLevel.DRAWDOWN_REDUCED, key=lambda x: x.rank)
        reasons.append(
            f"drawdown {dd:.2%} desde el maximo -> tamano al {dd_mult:.0%} "
            "(la escalera baja sola y nunca sube para recuperar)"
        )
    if dd_mult <= 0.0:
        can_open = False
        reasons.append(f"drawdown {dd:.2%} en el ultimo escalon: aperturas bloqueadas")

    # -- 2. Perdida semanal -> mitad de tamano ------------------------------
    if state.weekly_pnl_pct <= -cfg.weekly_loss_halfsize_pct:
        mult = min(mult, 0.5)
        level = max(level, BreakerLevel.WEEKLY_HALF, key=lambda x: x.rank)
        reasons.append(
            f"perdida semanal {state.weekly_pnl_pct:.2%} <= -{cfg.weekly_loss_halfsize_pct:.2%} -> tamano a la mitad"
        )

    # -- 3. Perdida diaria -> cierre de jornada -----------------------------
    if state.day_halt_latched or state.daily_pnl_pct <= -cfg.daily_loss_halt_pct:
        state.day_halt_latched = True
        can_open = False
        level = max(level, BreakerLevel.DAILY_HALT, key=lambda x: x.rank)
        reasons.append(
            f"perdida diaria {state.daily_pnl_pct:.2%} <= -{cfg.daily_loss_halt_pct:.2%}: "
            "jornada cerrada, sin excepciones. Se libera manana."
        )

    # -- 4. Racha de perdidas -> pausa y auditoria --------------------------
    if state.streak_pause_latched or state.consecutive_losses >= cfg.consecutive_losses_pause:
        state.streak_pause_latched = True
        can_open = False
        manual = True
        level = max(level, BreakerLevel.STREAK_PAUSE, key=lambda x: x.rank)
        reasons.append(
            f"{state.consecutive_losses} perdidas consecutivas: pausa forzada. "
            "Exige auditoria del proceso antes de reactivar, no solo esperar."
        )

    # -- 5. Perdida mensual -> apagado total --------------------------------
    if state.shutdown_latched or state.monthly_pnl_pct <= -cfg.monthly_loss_shutdown_pct:
        state.shutdown_latched = True
        can_open = False
        manual = True
        mult = 0.0
        level = BreakerLevel.SHUTDOWN
        reasons.append(
            f"perdida mensual {state.monthly_pnl_pct:.2%} <= -{cfg.monthly_loss_shutdown_pct:.2%}: "
            "APAGADO TOTAL. Revision manual obligatoria para reactivar."
        )

    if not reasons:
        reasons.append("todos los cortafuegos en verde")

    # Candado final: el multiplicador jamas supera 1.0. Aca muere la martingala.
    mult = min(mult, 1.0)
    if not can_open:
        mult = 0.0

    return BreakerVerdict(level, can_open, mult, tuple(reasons), manual)
