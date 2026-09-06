"""
Stress testing obligatorio.

Cuatro escenarios: 2008, marzo 2020, 2022 y un shock de tasas inventado.
Si el sistema no sobrevive los cuatro, no se usa. No es una recomendacion.

Lo que este modulo hace y casi ningun backtest hace: modela el GAP. En los
tres episodios historicos el stop no protegio como se planeo, porque el precio
abrio del otro lado. Un stress test que asume que los stops se ejecutan a su
precio esta midiendo un riesgo que no es el que corres.

Limitacion que el modulo REPORTA en vez de esconder: los cortafuegos de
perdida diaria/semanal/mensual limitan cuando DEJAS de abrir posiciones. No
limitan lo que perdes con las posiciones que ya tenias abiertas cuando el
mercado abrio 12% abajo. Esa diferencia es exactamente el riesgo residual.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..config import RiskConfig
from ..contracts import Position, Side


@dataclass(frozen=True, slots=True)
class StressScenario:
    name: str
    cumulative_drop: float          # caida total del indice (fraccion negativa)
    worst_day: float                # peor rueda individual
    worst_gap: float                # peor gap de apertura (el stop no protege)
    duration_sessions: int
    vol_multiplier: float
    correlation: float              # correlacion efectiva entre activos
    credit_widening_bps: float
    slippage_multiplier: float      # cuanto peor ejecuta el broker
    description: str


HISTORICAL: tuple[StressScenario, ...] = (
    StressScenario(
        "CRISIS_2008", -0.568, -0.090, -0.080, 517, 3.2, 0.95, 1600, 4.0,
        "Sep-2008 a Mar-2009. Caida del 56.8% en 17 meses. Lo que rompio carteras "
        "no fue la magnitud sino la DURACION: 517 ruedas de drawdown agotan cualquier "
        "sistema que no reduzca tamano automaticamente.",
    ),
    StressScenario(
        "COVID_MARZO_2020", -0.339, -0.120, -0.070, 23, 4.5, 0.98, 900, 6.0,
        "19-feb a 23-mar-2020. -33.9% en 23 ruedas. VIX 82.7. Varias aperturas con "
        "gap de -7%: los stops se ejecutaron muy por debajo de su precio. El caso "
        "que demuestra que un stop es una intencion, no una garantia.",
    ),
    StressScenario(
        "TASAS_2022", -0.254, -0.045, -0.030, 282, 1.9, 0.85, 500, 2.5,
        "Ene-2022 a oct-2022. -25.4% moliendo, sin un solo dia de panico. Acciones y "
        "bonos cayeron JUNTOS: la cobertura clasica 60/40 fallo por primera vez en "
        "40 anios. Es el escenario que castiga la falsa diversificacion.",
    ),
    StressScenario(
        "SHOCK_TASAS_INVENTADO", -0.180, -0.070, -0.055, 5, 5.0, 1.00, 700, 8.0,
        "Escenario construido, no historico: +300bp de tasa larga en 5 ruedas con "
        "equity -18%, correlacion exactamente 1 y liquidez evaporada (slippage x8). "
        "Existe para probar el sistema contra algo que NO esta en la muestra "
        "historica, que es de donde siempre viene el golpe que te saca.",
    ),
)


@dataclass(frozen=True, slots=True)
class PositionStress:
    symbol: str
    planned_loss: float             # lo que el stop deberia costar
    realized_loss: float            # lo que cuesta con gap y slippage
    slippage_cost: float
    stop_jumped: bool


@dataclass(frozen=True, slots=True)
class StressResult:
    scenario: StressScenario
    total_loss: float
    loss_pct: float
    planned_loss_pct: float
    survived: bool
    per_position: tuple[PositionStress, ...]
    notes: tuple[str, ...]

    @property
    def excess_over_plan(self) -> float:
        return self.loss_pct - self.planned_loss_pct


def apply_scenario(
    scenario: StressScenario,
    positions: Sequence[Position],
    equity: float,
    cfg: RiskConfig,
    *,
    ruin_threshold: float = 0.20,
) -> StressResult:
    """
    Aplica un escenario al libro abierto.

    Modelo de ejecucion en el peor momento:
      1. El precio abre con `worst_gap`.
      2. Si el gap cruza el stop, la salida se ejecuta al precio de apertura,
         NO al stop. Ahi nace la diferencia entre perdida planeada y real.
      3. Encima se aplica slippage adicional por iliquidez.
      4. La correlacion del escenario decide cuantas posiciones sufren a la vez;
         en 2008/2020 es ~1, o sea TODAS.
    """
    if equity <= 0:
        raise ValueError("equity no positivo")
    per: list[PositionStress] = []
    total = 0.0
    planned_total = 0.0

    for p in positions:
        notional = abs(p.qty * p.avg_price)
        planned = abs(p.avg_price - p.initial_stop) * p.qty
        planned_total += planned

        # Precio de apertura tras el gap, en contra de la posicion
        gap_price = p.avg_price * (1.0 + scenario.worst_gap * p.side.sign)
        jumped = (gap_price < p.initial_stop) if p.side is Side.LONG else (gap_price > p.initial_stop)

        if jumped:
            exit_px = gap_price
        else:
            exit_px = p.initial_stop

        # Slippage adicional por iliquidez, en bps sobre el nocional
        slip_bps = 2.0 * scenario.slippage_multiplier
        slip_cost = notional * slip_bps / 10_000.0
        loss = abs(p.avg_price - exit_px) * p.qty + slip_cost

        # La correlacion del escenario modula cuanto del libro sufre en simultaneo
        loss *= scenario.correlation if len(positions) > 1 else 1.0

        total += loss
        per.append(PositionStress(p.symbol, planned, loss, slip_cost, jumped))

    loss_pct = total / equity
    planned_pct = planned_total / equity
    notes = [
        f"perdida planeada (stops al precio): {planned_pct:.2%}",
        f"perdida REAL modelada (gap + slippage x{scenario.slippage_multiplier:.0f}): {loss_pct:.2%}",
        f"exceso sobre el plan: {loss_pct - planned_pct:+.2%}",
    ]
    jumped_n = sum(1 for x in per if x.stop_jumped)
    if jumped_n:
        notes.append(
            f"{jumped_n} de {len(per)} stops fueron SALTEADOS por el gap de apertura "
            f"({scenario.worst_gap:.1%}): se ejecutaron al precio de apertura, no al planeado"
        )
    notes.append(
        "LIMITACION: los cortafuegos diario/semanal/mensual detienen aperturas NUEVAS. "
        "No reducen la perdida de las posiciones que ya estaban abiertas cuando el "
        "mercado abrio en contra. Ese es el riesgo residual irreducible."
    )
    survived = loss_pct < ruin_threshold
    if not survived:
        notes.append(
            f"NO SOBREVIVE: {loss_pct:.2%} supera el umbral de ruina {ruin_threshold:.0%}. "
            "Con este libro el sistema NO se usa hasta reducir tamano o correlacion."
        )
    return StressResult(scenario, total, loss_pct, planned_pct, survived, tuple(per), tuple(notes))


def run_all(
    positions: Sequence[Position], equity: float, cfg: RiskConfig, *, ruin_threshold: float = 0.20
) -> tuple[StressResult, ...]:
    return tuple(apply_scenario(s, positions, equity, cfg, ruin_threshold=ruin_threshold)
                 for s in HISTORICAL)


def survives_all(results: Sequence[StressResult]) -> tuple[bool, str]:
    failed = [r.scenario.name for r in results if not r.survived]
    if failed:
        return False, f"NO sobrevive: {', '.join(failed)}. El sistema no se pone en produccion asi."
    worst = max(results, key=lambda r: r.loss_pct)
    return True, (
        f"sobrevive los {len(results)} escenarios. Peor caso: {worst.scenario.name} "
        f"con {worst.loss_pct:.2%} de perdida "
        f"({worst.excess_over_plan:+.2%} por encima de lo que los stops prometian)."
    )
