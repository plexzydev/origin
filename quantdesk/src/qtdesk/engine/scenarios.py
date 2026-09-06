"""
Arbol de escenarios obligatorio: 3 a 5 caminos con probabilidad y payoff.

El punto de este modulo NO es predecir. Es obligar a escribir el peor caso
ANTES de entrar, y verificar dos cosas:

    1. el valor esperado es positivo
    2. el PEOR camino es sobrevivible

Decision de diseno importante: las probabilidades se derivan de una tabla
documentada y NO se ajustan para que el EV de positivo. Si un setup de baja
conviccion produce EV de +0.08R, el sistema lo rechaza por debajo del minimo
en vez de retocar las probabilidades hasta que pase. Un arbol de escenarios
que siempre justifica el trade no es un arbol de escenarios, es una excusa
con formato de tabla.

Anclajes de las probabilidades (y por que):
  - tasa base de acierto 22%-42% segun conviccion. Un sistema que apunta a 3R
    NO acierta el 60%: la asimetria se paga con frecuencia de acierto baja.
    Prometer 3R con 55% de aciertos es la firma de un backtest con bug.
  - probabilidad de gap que saltea el stop: 4% en calma, hasta 10% en estres.
    Sale de la frecuencia observada de gaps > 1 ATR en indices liquidos.
  - salida por tiempo ~20%-26%: la mayoria de los trades no gana ni pierde,
    se queda quieto hasta que vence el plazo.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..contracts import Scenario, ScenarioTree


@dataclass(frozen=True, slots=True)
class TreeInputs:
    rr_target: float          # R del objetivo principal (>= 3 por mandato)
    conviction: int           # 1..5
    vol_stress: float         # 0 = calma, 1 = estres maximo
    gap_slippage_r: float     # cuanto empeora el stop en un gap, en R
    partial_r: float = 0.6    # payoff del camino "avanzo y volvio a breakeven"
    time_stop_r: float = -0.25


def build_tree(inp: TreeInputs) -> ScenarioTree:
    """Construye el arbol de 5 caminos. Las probabilidades suman 1 exacto."""
    c = max(1, min(5, inp.conviction))
    vs = max(0.0, min(1.0, inp.vol_stress))

    # Camino 4: el gap saltea el stop. Sube con el estres de volatilidad.
    p_gap = 0.04 + 0.06 * vs
    # Camino 5: la tesis no se materializa y vence el plazo.
    p_time = 0.22 - 0.02 * (c - 3)
    remaining = 1.0 - p_gap - p_time

    # Tasa de acierto condicional a que el trade se resuelva
    hit = 0.22 + 0.05 * (c - 1)
    p_full = remaining * hit
    p_partial = remaining * 0.30
    p_stop = remaining - p_full - p_partial

    scenarios = (
        Scenario(
            "tesis_se_cumple", round(p_full, 6), inp.rr_target,
            f"El precio alcanza el objetivo de {inp.rr_target:.1f}R. Camino principal "
            f"de la tesis. Probabilidad {p_full:.1%} anclada en una tasa base de "
            f"{hit:.0%} para conviccion {c}, no en optimismo.",
        ),
        Scenario(
            "avance_parcial", round(p_partial, 6), inp.partial_r,
            f"Corre a favor, se toma parcial y el resto sale en breakeven: {inp.partial_r:+.1f}R. "
            "Es el resultado mas frecuente de un trade 'que casi funciona'.",
        ),
        Scenario(
            "stop_limpio", round(p_stop, 6), -1.0,
            "El stop se ejecuta a su precio: -1.00R exacto. Este es el caso BUENO "
            "cuando el trade sale mal.",
        ),
        Scenario(
            "stop_con_gap", round(p_gap, 6), -(1.0 + inp.gap_slippage_r),
            f"El precio abre del otro lado del stop y la salida se ejecuta "
            f"{inp.gap_slippage_r:.1f}R mas abajo: {-(1.0 + inp.gap_slippage_r):.2f}R. "
            "Es el escenario que la gente olvida y el que define el tamano.",
        ),
        Scenario(
            "salida_por_tiempo", round(p_time, 6), inp.time_stop_r,
            f"La tesis no se cumple en el plazo previsto y se cierra en {inp.time_stop_r:+.2f}R "
            "(costos). Un trade que no funciona es un trade equivocado.",
        ),
    )
    # Reparacion de redondeo sobre el camino mas probable, nunca sobre el peor.
    drift = 1.0 - sum(s.probability for s in scenarios)
    if abs(drift) > 1e-9:
        idx = max(range(len(scenarios)), key=lambda i: scenarios[i].probability)
        fixed = list(scenarios)
        s = fixed[idx]
        fixed[idx] = Scenario(s.name, s.probability + drift, s.r_multiple, s.description)
        scenarios = tuple(fixed)

    return ScenarioTree(scenarios)


@dataclass(frozen=True, slots=True)
class TreeVerdict:
    tree: ScenarioTree
    expected_r: float
    worst_r: float
    worst_case_equity_pct: float
    ev_ok: bool
    survivable: bool
    notes: tuple[str, ...]

    @property
    def approved(self) -> bool:
        return self.ev_ok and self.survivable


def evaluate_tree(
    tree: ScenarioTree, risk_pct_of_equity: float, min_expected_r: float, max_worst_case_pct: float
) -> TreeVerdict:
    """
    Las dos condiciones del mandato, verificadas por separado.

    Un EV positivo con un peor caso que te saca del juego NO habilita el trade.
    Son condiciones conjuntas, no un promedio ponderado.
    """
    ev = tree.expected_r
    worst = tree.worst.r_multiple
    worst_pct = abs(worst) * risk_pct_of_equity

    ev_ok = ev >= min_expected_r
    survivable = worst_pct <= max_worst_case_pct

    notes = [
        f"EV = {ev:+.3f}R (minimo exigido {min_expected_r:+.2f}R) -> {'OK' if ev_ok else 'INSUFICIENTE'}",
        f"peor camino: {tree.worst.name} en {worst:.2f}R = {worst_pct:.2%} del capital "
        f"(techo {max_worst_case_pct:.2%}) -> {'sobrevivible' if survivable else 'NO SOBREVIVIBLE'}",
        f"mejor camino: {tree.best.name} en {tree.best.r_multiple:+.2f}R con probabilidad {tree.best.probability:.1%}",
    ]
    if ev_ok and not survivable:
        notes.append(
            "ATENCION: el valor esperado es positivo pero el peor caso no es tolerable. "
            "El EV positivo no compra supervivencia: se rechaza."
        )
    return TreeVerdict(tree, ev, worst, worst_pct, ev_ok, survivable, tuple(notes))
