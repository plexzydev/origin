"""
Revision post-operacion. La matriz de cuatro casillas.

PRINCIPIO RECTOR: separar SIEMPRE la calidad de la DECISION del RESULTADO.

    1. buena decision + ganancia -> proceso validado, no tocar nada
    2. buena decision + perdida  -> VARIANZA. No tocar nada. Es la casilla que
                                    mas gente rompe: cambian un sistema que
                                    funciona porque perdio tres veces seguidas.
    3. mala decision + ganancia  -> SUERTE. Alerta roja. Es la mas peligrosa
                                    porque se siente identica a ganar bien, y
                                    se repite hasta que la suerte se acaba.
    4. mala decision + perdida   -> error real. Aca si se aprende.

La calidad de la decision se evalua SOLO con lo que estaba escrito ANTES de
entrar: si se respeto el plan, si el escenario ocurrido estaba en el arbol, si
la falsacion se verifico. Nunca con el resultado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Quadrant(str, Enum):
    GOOD_WIN = "1_BUENA_DECISION_GANANCIA"
    GOOD_LOSS = "2_BUENA_DECISION_PERDIDA"
    BAD_WIN = "3_MALA_DECISION_GANANCIA"
    BAD_LOSS = "4_MALA_DECISION_PERDIDA"

    @property
    def action(self) -> str:
        return {
            "1_BUENA_DECISION_GANANCIA": "proceso validado: NO TOCAR NADA",
            "2_BUENA_DECISION_PERDIDA": "varianza: NO TOCAR NADA. Cambiar aca degrada el sistema.",
            "3_MALA_DECISION_GANANCIA": "ALERTA ROJA: se gano por motivos que no estaban en la tesis. "
                                        "Es la casilla mas peligrosa porque se siente igual que ganar bien.",
            "4_MALA_DECISION_PERDIDA": "error real: aca si se corrige, empezando por el proceso.",
        }[self.value]


@dataclass(frozen=True, slots=True)
class ProcessCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class TradeReview:
    symbol: str
    fingerprint: str
    entry_ts: datetime
    exit_ts: datetime
    pnl: float
    r_multiple: float
    quadrant: str
    decision_quality_score: float          # 0..1, calculado solo con el plan previo
    thesis_confirmed: bool
    scenario_was_in_tree: bool
    scenario_matched: str
    falsification_triggered: bool
    slippage_expected_bps: float
    slippage_actual_bps: float
    process_checks: tuple[ProcessCheck, ...]
    process_violations: int
    layer_attribution: dict[str, str] = field(default_factory=dict)
    lessons: tuple[str, ...] = ()
    action: str = ""


def review_trade(decision, trade, *, expected_slippage_bps: float = 5.0) -> TradeReview:
    """
    Revisa una operacion cerrada contra su registro previo congelado.

    La calidad de la decision se calcula ANTES de mirar el resultado, con seis
    chequeos de proceso. El resultado solo determina la COLUMNA de la matriz,
    nunca la fila.
    """
    checks: list[ProcessCheck] = []

    # -- 1. Hubo plan con stop y objetivo -----------------------------------
    has_plan = decision.plan is not None
    checks.append(ProcessCheck(
        "plan_completo", has_plan,
        "habia plan con stop, objetivo y tamano" if has_plan else "SIN PLAN: violacion de proceso",
    ))

    # -- 2. Falsacion explicita escrita -------------------------------------
    has_fals = bool(decision.falsification.strip())
    checks.append(ProcessCheck(
        "falsacion_escrita", has_fals,
        "la falsacion estaba escrita antes de entrar" if has_fals
        else "SIN FALSACION: no se podia saber que probaria estar equivocado",
    ))

    # -- 3. El escenario ocurrido estaba en el arbol ------------------------
    matched, in_tree = _match_scenario(decision, trade)
    checks.append(ProcessCheck(
        "escenario_previsto", in_tree,
        f"el resultado corresponde al camino '{matched}' del arbol" if in_tree
        else f"el resultado ('{matched}') NO estaba en el arbol: hay un hueco en el modelo",
    ))

    # -- 4. Se respeto el stop inicial --------------------------------------
    respected = True
    detail = "el stop se respeto"
    if has_plan and trade.side.value == "LONG" and trade.exit_price < decision.plan.stop_price * 0.90:
        respected = False
        detail = (f"salida en {trade.exit_price:.2f} muy por debajo del stop "
                  f"{decision.plan.stop_price:.2f}: revisar si fue gap o si se movio el stop")
    checks.append(ProcessCheck("stop_respetado", respected, detail))

    # -- 5. Slippage dentro de lo esperado ----------------------------------
    actual = (trade.slippage_bps_in + trade.slippage_bps_out) / 2.0
    slip_ok = actual <= expected_slippage_bps * 2.0
    checks.append(ProcessCheck(
        "slippage_esperado", slip_ok,
        f"slippage real {actual:.1f}bp vs esperado {expected_slippage_bps:.1f}bp"
        + ("" if slip_ok else " -- MAS DEL DOBLE: revisar liquidez o modelo de costos"),
    ))

    # -- 6. Habia al menos 3 capas alineadas --------------------------------
    aligned_ok = decision.aligned_layers >= 3
    checks.append(ProcessCheck(
        "capas_alineadas", aligned_ok,
        f"{decision.aligned_layers} capas alineadas al entrar",
    ))

    violations = sum(1 for c in checks if not c.passed)
    quality = sum(1 for c in checks if c.passed) / len(checks)
    good_decision = quality >= 0.80

    won = trade.pnl > 0
    if good_decision and won:
        q = Quadrant.GOOD_WIN
    elif good_decision and not won:
        q = Quadrant.GOOD_LOSS
    elif not good_decision and won:
        q = Quadrant.BAD_WIN
    else:
        q = Quadrant.BAD_LOSS

    lessons: list[str] = []
    if q is Quadrant.BAD_WIN:
        lessons.append(
            "Se gano con un proceso deficiente. Este resultado NO valida nada y no debe "
            "reforzar el comportamiento. Si esta casilla crece, el sistema esta ganando "
            "por motivos que no entiende."
        )
    if q is Quadrant.GOOD_LOSS:
        lessons.append(
            "Perdida con proceso correcto: es varianza esperada. Cambiar parametros aca "
            "es exactamente como se degradan los sistemas."
        )
    if not in_tree:
        lessons.append(
            "El escenario ocurrido no estaba previsto: agregar ese camino al generador "
            "de arboles antes de la proxima operacion comparable."
        )
    for c in checks:
        if not c.passed:
            lessons.append(f"violacion de proceso -- {c.name}: {c.detail}")

    return TradeReview(
        symbol=trade.symbol, fingerprint=trade.decision_fingerprint,
        entry_ts=trade.entry_ts, exit_ts=trade.exit_ts, pnl=trade.pnl,
        r_multiple=trade.r_multiple, quadrant=q.value,
        decision_quality_score=quality,
        thesis_confirmed=in_tree and won,
        scenario_was_in_tree=in_tree, scenario_matched=matched,
        falsification_triggered=not won and has_fals,
        slippage_expected_bps=expected_slippage_bps, slippage_actual_bps=actual,
        process_checks=tuple(checks), process_violations=violations,
        layer_attribution=_attribute(decision, won),
        lessons=tuple(lessons), action=q.action,
    )


def _match_scenario(decision, trade) -> tuple[str, bool]:
    """Que camino del arbol se materializo. Si ninguno, hay un hueco en el modelo."""
    if decision.scenario_tree is None:
        return "sin arbol registrado", False
    r = trade.r_multiple
    best, best_d = None, float("inf")
    for s in decision.scenario_tree.scenarios:
        d = abs(s.r_multiple - r)
        if d < best_d:
            best, best_d = s, d
    # Tolerancia: 0.5R de distancia al camino mas cercano
    if best is not None and best_d <= 0.5:
        return best.name, True
    return f"resultado {r:+.2f}R fuera de todos los caminos previstos", False


def _attribute(decision, won: bool) -> dict[str, str]:
    """Que capa acerto y cual erro. Se mide contra el resultado, capa por capa."""
    out: dict[str, str] = {}
    sign = 1 if decision.action.value == "OPEN_LONG" else -1
    for s in decision.layer_scores:
        if s.confidence < 0.2:
            out[s.layer.value] = "se abstuvo"
            continue
        agreed = (s.score > 0) == (sign > 0)
        if won:
            out[s.layer.value] = "ACERTO" if agreed else "erro (estaba en contra y salio bien)"
        else:
            out[s.layer.value] = "erro" if agreed else "ACERTO (estaba en contra y salio mal)"
    return out


@dataclass(slots=True)
class ReviewLedger:
    """Acumula revisiones. Los patrones aparecen en el agregado, no en el trade suelto."""
    reviews: list[TradeReview] = field(default_factory=list)

    def add(self, r: TradeReview) -> None:
        self.reviews.append(r)

    def quadrant_counts(self) -> dict[str, int]:
        out: dict[str, int] = {q.value: 0 for q in Quadrant}
        for r in self.reviews:
            out[r.quadrant] = out.get(r.quadrant, 0) + 1
        return out

    def process_violation_rate(self) -> float:
        if not self.reviews:
            return 0.0
        return sum(r.process_violations for r in self.reviews) / len(self.reviews)

    def luck_ratio(self) -> float:
        """Fraccion de ganancias que vinieron de decisiones malas. Si sube, alarma."""
        wins = [r for r in self.reviews if r.pnl > 0]
        if not wins:
            return 0.0
        return sum(1 for r in wins if r.quadrant == Quadrant.BAD_WIN.value) / len(wins)

    def model_gap_rate(self) -> float:
        """Fraccion de resultados que no estaban en ningun arbol de escenarios."""
        if not self.reviews:
            return 0.0
        return sum(1 for r in self.reviews if not r.scenario_was_in_tree) / len(self.reviews)
