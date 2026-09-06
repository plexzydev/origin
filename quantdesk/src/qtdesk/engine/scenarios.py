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
    rr_target: float            # R del objetivo
    conviction: int             # 1..5
    vol_stress: float           # 0 = calma, 1 = estres maximo
    gap_slippage_r: float       # cuanto empeora el stop en un gap, en R
    # Tasa de acierto MEDIDA sobre operaciones comparables. Si hay muestra
    # suficiente, manda esto y no la teoria.
    measured_hit_rate: float | None = None
    sample_size: int = 0
    partial_share: float = 0.40   # de los aciertos, cuantos quedan a medio camino
    partial_r: float = 0.60
    time_share: float = 0.22      # trades que vencen por plazo sin resolverse
    time_stop_r: float = -0.25
    gap_share: float = 0.10       # de las perdidas, cuantas ejecutan con gap


def base_hit_rate(rr_target: float) -> float:
    """
    Probabilidad de tocar +kR antes que -1R SIN NINGUNA VENTAJA.

    Es la ruina del jugador: 1/(1+k). Para k=1.5 da 40%, para k=3 da 25%.

    De aca sale la afirmacion mas importante de todo el modulo: EL RATIO
    RIESGO/BENEFICIO NO CREA ESPERANZA MATEMATICA. Un 1:3 con 25% de aciertos
    y un 1.5:1 con 40% valen exactamente lo mismo: cero, antes de costos.
    Lo unico que crea esperanza es la VENTAJA, y la ventaja se mide, no se
    supone.
    """
    return 1.0 / (1.0 + max(rr_target, 0.1))


def build_tree(inp: TreeInputs) -> ScenarioTree:
    """
    Construye el arbol de 5 caminos. Las probabilidades suman 1 exacto.

    Descomposicion (importa el orden, y una version anterior lo tenia mal):
    primero se separa el resultado BINARIO -- toca objetivo o toca stop --
    segun la tasa de acierto. Recien despues se subdivide cada lado en sus
    variantes realistas. Carvar el camino "avance parcial" del total en vez
    del lado ganador le regalaba masa de probabilidad al lado bueno e inflaba
    el EV. Con la aritmetica corregida, la friccion se ve.
    """
    c = max(1, min(5, inp.conviction))
    vs = max(0.0, min(1.0, inp.vol_stress))

    theory = base_hit_rate(inp.rr_target)
    if inp.measured_hit_rate is not None and inp.sample_size >= 30:
        hit = max(0.02, min(0.95, inp.measured_hit_rate))
        hit_basis = (
            f"tasa MEDIDA {hit:.0%} sobre {inp.sample_size} operaciones comparables "
            f"(teorica sin ventaja: {theory:.0%})"
        )
    else:
        # Sin muestra, la unica ventaja que el sistema se atribuye es +/-4pp
        # por conviccion. Cualquier cosa mayor seria inventar un edge.
        hit = max(0.05, min(0.85, theory + 0.02 * (c - 3)))
        hit_basis = (
            f"tasa TEORICA {theory:.0%} = 1/(1+{inp.rr_target:.1f}) por caminata aleatoria, "
            f"ajustada {0.02 * (c - 3):+.0%} por conviccion {c}/5. VENTAJA NO DEMOSTRADA: "
            f"solo {inp.sample_size} operaciones comparables registradas."
        )

    p_time = inp.time_share
    active = 1.0 - p_time
    p_win = active * hit
    p_loss = active * (1.0 - hit)

    gap_share = min(0.6, inp.gap_share + 0.25 * vs)
    p_full = p_win * (1.0 - inp.partial_share)
    p_partial = p_win * inp.partial_share
    p_gap = p_loss * gap_share
    p_stop = p_loss * (1.0 - gap_share)

    scenarios = (
        Scenario(
            "tesis_se_cumple", round(p_full, 6), inp.rr_target,
            f"El precio alcanza el objetivo completo de {inp.rr_target:.1f}R. {hit_basis}",
        ),
        Scenario(
            "avance_parcial", round(p_partial, 6), inp.partial_r,
            f"Corre a favor, se toma parcial y el resto sale en breakeven: {inp.partial_r:+.1f}R. "
            f"Es el {inp.partial_share:.0%} de los aciertos: la mayoria de los trades que "
            "funcionan no llegan al objetivo completo.",
        ),
        Scenario(
            "stop_limpio", round(p_stop, 6), -1.0,
            "El stop se ejecuta a su precio: -1.00R exacto. Es el caso BUENO cuando sale mal.",
        ),
        Scenario(
            "stop_con_gap", round(p_gap, 6), -(1.0 + inp.gap_slippage_r),
            f"El precio abre del otro lado del stop: {-(1.0 + inp.gap_slippage_r):.2f}R. "
            f"Es el {gap_share:.0%} de las perdidas con el estres de volatilidad actual. "
            "Es el escenario que define el tamano.",
        ),
        Scenario(
            "salida_por_tiempo", round(p_time, 6), inp.time_stop_r,
            f"La tesis no se materializa en el plazo y se cierra en {inp.time_stop_r:+.2f}R.",
        ),
    )
    drift = 1.0 - sum(s.probability for s in scenarios)
    if abs(drift) > 1e-9:
        idx = max(range(len(scenarios)), key=lambda i: scenarios[i].probability)
        fixed = list(scenarios)
        sc = fixed[idx]
        fixed[idx] = Scenario(sc.name, sc.probability + drift, sc.r_multiple, sc.description)
        scenarios = tuple(fixed)

    return ScenarioTree(scenarios)


def breakeven_hit_rate(inp: TreeInputs) -> float:
    """
    Tasa de acierto que hace EV = 0 con esta estructura de salidas.

    Es EL numero que hay que mirar: si esta muy por encima de la tasa teorica
    sin ventaja, el sistema esta exigiendose una ventaja que probablemente no
    tiene.
    """
    active = 1.0 - inp.time_share
    gap_share = min(0.6, inp.gap_share + 0.25 * max(0.0, min(1.0, inp.vol_stress)))
    win_payoff = (1 - inp.partial_share) * inp.rr_target + inp.partial_share * inp.partial_r
    loss_payoff = (1 - gap_share) * 1.0 + gap_share * (1.0 + inp.gap_slippage_r)
    time_drag = inp.time_share * inp.time_stop_r
    # active*(h*win - (1-h)*loss) + time_drag = 0
    if active <= 0 or (win_payoff + loss_payoff) <= 0:
        return 1.0
    return (loss_payoff - time_drag / active) / (win_payoff + loss_payoff)


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
