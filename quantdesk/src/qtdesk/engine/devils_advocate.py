"""
EL ABOGADO DEL DIABLO.

Unica funcion: argumentar por que el trade esta MAL. Habla en cada operacion,
sin excepcion, tambien cuando el score es excelente -- sobre todo entonces.

Mecanica: cada argumento se genera CON DATOS y se intenta REFUTAR CON DATOS.
Un argumento que queda en pie con severidad HIGH o superior bloquea el trade.
No hay ponderacion ni promedio: si no se puede refutar, no se opera.

La razon de que esto sea codigo y no una seccion del informe: un humano que
revisa su propia tesis encuentra las objeciones que ya penso. Este modulo
genera SIEMPRE las mismas diez objeciones, incluidas las incomodas, y las
aplica con la misma dureza al trade que te encanta y al que te da igual.
"""
from __future__ import annotations

from statistics import fmean

from ..contracts import Argument, LayerId, Severity
from ..layers.technical import AGAINST_BIAS, MTF_CONFLICT
from ..stats import correlation, log_returns


def build_case(
    ctx,
    scores,
    regime,
    tree_verdict,
    freq_verdict,
    size_result,
    *,
    error_book=None,
    sample_size: int = 0,
) -> tuple[Argument, ...]:
    """Genera el caso en contra. Devuelve todos los argumentos, refutados o no."""
    args: list[Argument] = []
    by_layer = {s.layer: s for s in scores}

    # -- 1. El edge puede ser ruido ----------------------------------------
    if sample_size < 30:
        args.append(Argument(
            claim="No sabes si este setup tiene ventaja: nunca lo mediste con muestra suficiente.",
            severity=Severity.MEDIUM if sample_size >= 10 else Severity.HIGH,
            evidence=(
                f"solo {sample_size} operaciones comparables registradas. Con menos de 30 no se "
                "distingue senal de ruido, y el propio sistema prohibe tocar pesos con esa muestra."
            ),
            refuted_by=None if sample_size < 10 else (
                f"muestra de {sample_size}: insuficiente para concluir, suficiente para no ser un disparate. "
                "Se opera con tamano reducido y se sigue midiendo."
            ),
        ))

    # -- 2. Concentracion disfrazada de diversificacion --------------------
    if ctx.open_positions:
        cand = log_returns(ctx.closes(90))
        cors = []
        for p in ctx.open_positions:
            v = ctx.peers.get(p.symbol)
            if v is not None:
                c = correlation(cand, log_returns(v.closes(90)))
                if c is not None:
                    cors.append((p.symbol, c))
        if cors:
            avg = fmean([c for _, c in cors])
            worst = max(cors, key=lambda x: x[1])
            args.append(Argument(
                claim="Esto no diversifica: agranda la apuesta que ya tenes puesta.",
                severity=Severity.HIGH if avg > 0.55 else Severity.MEDIUM,
                evidence=f"correlacion media {avg:.2f} con el libro; la peor es {worst[0]} en {worst[1]:.2f}. "
                         "En una crisis todas se van a 1 y hoy ya estan cerca.",
                refuted_by=(
                    f"correlacion media {avg:.2f} por debajo de 0.45 y el limite estresado del "
                    "Risk Officer ya contempla correlacion 1" if avg <= 0.45 else None
                ),
            ))

    # -- 3. Contradiccion interna del analisis -----------------------------
    strong = [s for s in scores if abs(s.effective) >= 35]
    pos = [s for s in strong if s.effective > 0]
    neg = [s for s in strong if s.effective < 0]
    if pos and neg:
        args.append(Argument(
            claim="Tus propias capas no se ponen de acuerdo, y estas operando igual.",
            severity=Severity.HIGH,
            evidence=(
                f"{', '.join(f'{s.layer.value} {s.effective:+.0f}' for s in pos[:2])} contra "
                f"{', '.join(f'{s.layer.value} {s.effective:+.0f}' for s in neg[:2])}. "
                "La contradiccion significa que no entendes el escenario."
            ),
            refuted_by=None,
        ))

    # -- 4. Capas opinando sin datos ---------------------------------------
    weak = [s for s in scores if s.confidence < 0.4 and abs(s.score) > 20]
    if weak:
        args.append(Argument(
            claim="Parte del score viene de capas que casi no tienen datos.",
            severity=Severity.MEDIUM,
            evidence="; ".join(f"{s.layer.value}: score {s.score:+.0f} con confianza {s.confidence:.2f}" for s in weak),
            refuted_by=(
                "el score combinado usa el score EFECTIVO (ponderado por confianza), "
                "asi que esas capas ya pesan poco"
            ),
        ))

    # -- 5. Regimen incierto ------------------------------------------------
    if regime.confidence < 0.6:
        args.append(Argument(
            claim="No sabes en que regimen estas, y los pesos dependen del regimen.",
            severity=Severity.HIGH if regime.confidence < 0.35 else Severity.MEDIUM,
            evidence=f"confianza del regimen {regime.confidence:.2f} sobre {regime.label}. "
                     f"Se aplico un recargo de +{regime.threshold_bump:.0f} puntos al umbral.",
            refuted_by=(
                f"el recargo de +{regime.threshold_bump:.0f} puntos ya compensa la incertidumbre "
                "exigiendo mas score" if regime.threshold_bump >= 5 else None
            ),
        ))

    # -- 6. Senal contra el sesgo estructural -------------------------------
    tech = by_layer.get(LayerId.TECHNICAL)
    if tech is not None and AGAINST_BIAS in tech.warnings:
        args.append(Argument(
            claim="Estas operando en contra de la tendencia que vos mismo definiste como sesgo.",
            severity=Severity.HIGH,
            evidence="la CAPA 1 marco CONTRA_SESGO_DIARIO: la senal apunta al revés del sesgo de "
                     "medias 50/200. Puede ser un giro temprano o una trampa; el sistema no distingue.",
            refuted_by=None,
        ))
    if tech is not None and MTF_CONFLICT in tech.warnings:
        args.append(Argument(
            claim="Los timeframes se contradicen.",
            severity=Severity.CRITICAL,
            evidence="CAPA 1 emitio TIMEFRAMES_DISCORDANTES. El mandato es explicito: no hay trade.",
            refuted_by=None,
        ))

    # -- 7. Trade forzado por la cuota de frecuencia ------------------------
    if freq_verdict is not None and freq_verdict.is_easing:
        args.append(Argument(
            claim="Este trade no aparecio porque el mercado lo ofreciera, sino porque venias atrasado con la cuota.",
            severity=Severity.HIGH if freq_verdict.easing_points > 10 else Severity.MEDIUM,
            evidence=(
                f"el umbral bajo de {freq_verdict.base_threshold:.0f} a "
                f"{freq_verdict.effective_threshold:.0f} por {freq_verdict.behind_by:.1f} de atraso y "
                f"{freq_verdict.days_since_last_trade} dias sin operar. Esto es, textualmente, "
                "'operar por no haber operado hoy'."
            ),
            refuted_by=(
                f"el tamano ya se recorto al {freq_verdict.size_multiplier:.0%}, el trade queda marcado "
                "FORZADO_POR_CUOTA y su resultado se mide por separado. La hipotesis se contrasta con "
                "datos en vez de discutirse."
                if freq_verdict.size_multiplier < 1.0 else None
            ),
        ))

    # -- 8. Revancha en drawdown -------------------------------------------
    dd = ctx.desk.drawdown
    if dd > 0.03 and ctx.desk.consecutive_losses >= 1:
        args.append(Argument(
            claim="Venis perdiendo. Este trade puede ser revancha disfrazada de analisis.",
            severity=Severity.HIGH if ctx.desk.consecutive_losses >= 2 else Severity.MEDIUM,
            evidence=f"drawdown {dd:.2%} y {ctx.desk.consecutive_losses} perdida(s) consecutiva(s).",
            refuted_by=(
                "la escalera de drawdown ya redujo el tamano automaticamente y el sistema no tiene "
                "ninguna ruta que aumente tamano tras una perdida (multiplicador acotado a 1.0)"
            ),
        ))

    # -- 9. Peor caso vs plan ----------------------------------------------
    if size_result is not None and size_result.worst_case_pct > size_result.risk_pct * 1.6:
        args.append(Argument(
            claim="Tu 'riesgo del 0.75%' es ficcion: el peor caso realista es mas del doble.",
            severity=Severity.MEDIUM,
            evidence=(
                f"riesgo nominal {size_result.risk_pct:.2%} pero con deslizamiento del stop "
                f"{size_result.worst_case_pct:.2%}. El stop es una intencion, no una garantia."
            ),
            refuted_by=(
                f"el Risk Officer dimensiona contra el peor caso ({size_result.worst_case_pct:.2%}) "
                "y no contra el nominal, y ese numero esta dentro del techo autorizado"
            ),
        ))

    # -- 10. Objetivo geometricamente improbable ---------------------------
    if tree_verdict is not None:
        best = tree_verdict.tree.best
        if best.probability < 0.20:
            args.append(Argument(
                claim="El escenario que justifica el trade es el menos probable de todos.",
                severity=Severity.MEDIUM,
                evidence=f"'{best.name}' paga {best.r_multiple:+.1f}R pero solo tiene {best.probability:.0%} "
                         f"de probabilidad. El EV total es {tree_verdict.expected_r:+.2f}R.",
                refuted_by=(
                    f"asi funciona la asimetria 1:3: se acierta poco y se gana mucho cuando se acierta. "
                    f"El EV de {tree_verdict.expected_r:+.2f}R ya incorpora la baja frecuencia de acierto."
                    if tree_verdict.expected_r >= 0.2 else None
                ),
            ))

    # -- 11. Ya cometiste este error ---------------------------------------
    if error_book is not None:
        conds = {
            "regimen": regime.label,
            "sector": ctx.sector,
            "score_tecnico": by_layer[LayerId.TECHNICAL].score if LayerId.TECHNICAL in by_layer else 0.0,
            "drawdown": round(dd, 3),
        }
        matches = error_book.similar(conds, threshold=0.45)
        if matches:
            e, sim = matches[0]
            args.append(Argument(
                claim=f"Ya cometiste este error: '{e.title}'.",
                severity=Severity.HIGH if e.kind.value == "PROCESO" else Severity.MEDIUM,
                evidence=f"similitud {sim:.0%} con un error de tipo {e.kind.value} registrado el "
                         f"{e.created_at.date()}. {e.description}",
                refuted_by=(f"correccion ya aplicada: {e.correction}" if e.correction and e.resolved else None),
            ))

    return tuple(args)


def blocking(arguments, min_severity: str = "HIGH") -> tuple[Argument, ...]:
    """Argumentos EN PIE con severidad suficiente para bloquear."""
    floor = Severity(min_severity).rank
    return tuple(a for a in arguments if a.standing and a.severity.rank >= floor)


def render(arguments) -> str:
    """Texto del caso en contra, para el informe."""
    if not arguments:
        return "Sin objeciones generadas. Eso NO es una buena senal: revisar si el generador quedo mudo."
    lines = []
    for a in arguments:
        estado = "EN PIE" if a.standing else "refutado"
        lines.append(f"[{a.severity.value}/{estado}] {a.claim}")
        lines.append(f"    evidencia: {a.evidence}")
        if a.refuted_by:
            lines.append(f"    refutacion: {a.refuted_by}")
    return "\n".join(lines)
