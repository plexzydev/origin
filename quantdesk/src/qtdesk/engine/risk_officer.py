"""
EL RISK OFFICER. Revisa al final y tiene VETO ABSOLUTO, sin apelacion.

Que puede hacer:
  - vetar (y su veto no se pondera con nada)
  - REDUCIR tamano para que entre dentro de los limites

Que NO puede hacer, ni aunque el score sea perfecto:
  - aumentar tamano
  - aflojar un limite
  - autorizar una operacion sin stop

Este modulo corre DESPUES de todo lo demas a proposito. No participa del
scoring, no vota: audita el resultado. Un revisor que participo en construir
la tesis ya no es un revisor.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..contracts import Argument, Severity, Side, VetoReason
from ..risk import stress
from ..risk.stops import rr_ratio


@dataclass(frozen=True, slots=True)
class OfficerVerdict:
    approved: bool
    vetoes: tuple[VetoReason, ...]
    final_qty: float
    reductions: tuple[str, ...]
    message: str
    stress_summary: str = ""

    @property
    def reduced(self) -> bool:
        return bool(self.reductions)


def review(
    *,
    ctx,
    side: Side,
    entry: float,
    stop: float,
    targets: tuple[float, ...],
    size_result,
    limit_verdict,
    breaker_verdict,
    tree_verdict,
    arguments: tuple[Argument, ...],
    freq_verdict,
    hypothetical_position,
) -> OfficerVerdict:
    """Revision final. Cualquier veto termina la operacion."""
    cfg = ctx.config
    vetoes: list[VetoReason] = []
    reductions: list[str] = []
    qty = size_result.qty if size_result is not None else 0.0

    # -- 1. Cortafuegos -----------------------------------------------------
    if breaker_verdict is not None and not breaker_verdict.can_open:
        vetoes.append(VetoReason(
            "OFICIAL_CORTAFUEGOS",
            f"cortafuegos en {breaker_verdict.level.value}: " + "; ".join(breaker_verdict.reasons),
        ))

    # -- 2. Stop colocable --------------------------------------------------
    dist = abs(entry - stop)
    if stop <= 0 or dist <= 0:
        vetoes.append(VetoReason("OFICIAL_SIN_STOP", "no se pudo calcular un stop valido. Sin stop no hay trade."))
    elif dist / entry < 0.002:
        vetoes.append(VetoReason(
            "OFICIAL_STOP_MUY_CERCA",
            f"stop a {dist/entry:.3%} del precio: dentro del ruido de la horquilla. "
            "Se ejecutaria por microestructura, no por invalidacion de la tesis.",
        ))
    elif dist / entry > 0.15:
        vetoes.append(VetoReason(
            "OFICIAL_STOP_MUY_LEJOS",
            f"stop a {dist/entry:.1%} del precio: para respetar el riesgo por operacion el "
            "tamano queda tan chico que los costos fijos se comen la ventaja.",
        ))

    # -- 3. Asimetria 1:3 ---------------------------------------------------
    if targets:
        rr = rr_ratio(entry, stop, targets[0])
        if rr < cfg.risk.min_rr_ratio - 1e-9:
            vetoes.append(VetoReason(
                "OFICIAL_ASIMETRIA",
                f"R:R de {rr:.2f} < minimo {cfg.risk.min_rr_ratio:.1f}. Si el objetivo razonable "
                "no esta a 3 veces la distancia del stop, el trade se descarta. No se acerca el "
                "objetivo para que el numero de.",
            ))
    else:
        vetoes.append(VetoReason("OFICIAL_SIN_OBJETIVO", "sin objetivo no se puede evaluar la asimetria"))

    # -- 4. Tamano viable ---------------------------------------------------
    if size_result is None or not size_result.viable:
        vetoes.append(VetoReason(
            "OFICIAL_TAMANO_NULO",
            "el dimensionamiento da 0 unidades: " + (size_result.notes[0] if size_result and size_result.notes else "sin detalle"),
        ))

    # -- 5. Peor caso del arbol de escenarios -------------------------------
    if tree_verdict is not None:
        if not tree_verdict.survivable:
            vetoes.append(VetoReason(
                "OFICIAL_PEOR_CASO",
                f"el peor camino cuesta {tree_verdict.worst_case_equity_pct:.2%} del capital, por encima "
                f"del techo {cfg.decision.max_worst_case_equity_pct:.2%}. Un valor esperado positivo no "
                "compra supervivencia.",
            ))
        if not tree_verdict.ev_ok:
            vetoes.append(VetoReason(
                "OFICIAL_EV_INSUFICIENTE",
                f"valor esperado {tree_verdict.expected_r:+.2f}R por debajo del minimo "
                f"{cfg.decision.min_expected_r:+.2f}R. La mediocridad es el enemigo.",
            ))

    # -- 6. Peor caso del dimensionamiento ----------------------------------
    if size_result is not None and size_result.viable:
        if size_result.worst_case_pct > cfg.decision.max_worst_case_equity_pct:
            # Aca el oficial REDUCE en vez de vetar: es un problema de tamano.
            factor = cfg.decision.max_worst_case_equity_pct / size_result.worst_case_pct
            new_qty = int(qty * factor)
            reductions.append(
                f"tamano reducido de {qty:,.0f} a {new_qty:,.0f} unidades: el peor caso con "
                f"deslizamiento ({size_result.worst_case_pct:.2%}) superaba el techo "
                f"({cfg.decision.max_worst_case_equity_pct:.2%})"
            )
            qty = new_qty
            if qty <= 0:
                vetoes.append(VetoReason(
                    "OFICIAL_TAMANO_NULO",
                    "tras ajustar por el peor caso el tamano queda en cero",
                ))

    # -- 7. Limites de concentracion y correlacion --------------------------
    if limit_verdict is not None and not limit_verdict.allowed:
        criticals = [b for b in limit_verdict.breaches if b.severity is Severity.CRITICAL]
        if criticals or limit_verdict.max_qty <= 0:
            for b in limit_verdict.breaches:
                vetoes.append(VetoReason(f"OFICIAL_{b.code}", b.detail))
        else:
            new_qty = min(qty, limit_verdict.max_qty)
            reductions.append(
                f"tamano recortado a {new_qty:,.0f} por limites: "
                + "; ".join(b.code for b in limit_verdict.breaches)
            )
            qty = new_qty

    # -- 8. Argumentos en pie del Abogado del Diablo ------------------------
    floor = Severity(cfg.decision.devils_advocate_blocking).rank
    standing = [a for a in arguments if a.standing and a.severity.rank >= floor]
    for a in standing:
        vetoes.append(VetoReason(
            "OFICIAL_ABOGADO_DEL_DIABLO",
            f"argumento sin refutar ({a.severity.value}): {a.claim} | {a.evidence}",
        ))

    # -- 9. Techo de frecuencia ---------------------------------------------
    if freq_verdict is not None and freq_verdict.ceiling_hit:
        vetoes.append(VetoReason(
            "OFICIAL_SOBREOPERACION",
            f"techo semanal alcanzado. El objetivo de frecuencia NO lo levanta: "
            f"{freq_verdict.note}",
        ))

    # -- 10. Stress test sobre el libro resultante --------------------------
    stress_summary = ""
    if qty > 0 and hypothetical_position is not None:
        book = list(ctx.open_positions) + [hypothetical_position]
        results = stress.run_all(book, ctx.desk.equity, cfg.risk)
        ok, msg = stress.survives_all(results)
        stress_summary = msg
        if not ok:
            vetoes.append(VetoReason("OFICIAL_STRESS", f"el libro resultante no sobrevive el stress test: {msg}"))

    approved = not vetoes and qty > 0
    if approved:
        msg = (
            f"APRUEBA {qty:,.0f} unidades. Riesgo nominal "
            f"{size_result.risk_pct:.2%}, peor caso realista {size_result.worst_case_pct:.2%}. "
            + (" ".join(reductions) if reductions else "Sin ajustes de tamano.")
        )
    else:
        msg = f"VETA. {len(vetoes)} motivo(s): " + " || ".join(v.detail[:130] for v in vetoes[:4])

    return OfficerVerdict(
        approved=approved, vetoes=tuple(vetoes), final_qty=max(0.0, qty),
        reductions=tuple(reductions), message=msg, stress_summary=stress_summary,
    )
