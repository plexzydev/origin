"""
MOTOR DE DECISION. Los nueve pasos del mandato, en orden, sin atajos.

  1. CAPA 0 primero. Si veta, termino.
  2. Detectar regimen; los pesos dependen del regimen.
  3. Cada capa emite score con justificacion escrita.
  4. Combinar con pesos dependientes del regimen.
  5. Umbral alto Y al menos 3 capas alineadas.
  6. Contradiccion fuerte entre capas -> no se opera.
  7. Arbol de escenarios: EV positivo Y peor caso sobrevivible.
  8. El Abogado del Diablo escribe el caso en contra.
  9. El Risk Officer revisa y puede vetar sin apelacion.

La salida es SIEMPRE un objeto `Decision` completo, tambien cuando la
respuesta es NO OPERAR -- que es la posicion por defecto. Registrar los
rechazos es lo que despues permite responder "por que no operamos en marzo",
que es una pregunta tan importante como "por que compramos esto".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .. import regime as regime_mod
from ..config import SystemConfig
from ..contracts import (Action, Argument, Cycle, Decision, LayerId, LayerScore, Position,
                         Role, RiskMode, Side, TradePlan, VetoResult, Voice)
from ..layers.fundamental import FundamentalLayer
from ..layers.macro import MacroLayer
from ..layers.policy import PolicyLayer
from ..layers.positioning import PositioningLayer
from ..layers.technical import TechnicalLayer
from ..layers.veto import check_contradiction, run_capa0
from ..risk import limits as limits_mod
from ..risk.sizing import atr_position_size
from ..risk.stops import time_stop_at
from ..stats import log_returns
from . import devils_advocate as devil
from . import risk_officer
from .levels import derive as derive_levels
from .scenarios import TreeInputs, build_tree, evaluate_tree


@dataclass(slots=True)
class EngineDeps:
    """Dependencias inyectadas. Facilita testear cada pieza por separado."""
    technical: TechnicalLayer
    fundamental: FundamentalLayer
    macro: MacroLayer
    policy: PolicyLayer
    positioning: PositioningLayer
    error_book: object | None = None
    freq_governor: object | None = None

    @classmethod
    def default(cls, policy_calendar=None, error_book=None, freq_governor=None) -> "EngineDeps":
        return cls(
            TechnicalLayer(), FundamentalLayer(), MacroLayer(),
            PolicyLayer(policy_calendar), PositioningLayer(),
            error_book, freq_governor,
        )


class DecisionEngine:
    def __init__(self, config: SystemConfig, deps: EngineDeps, calibrator=None) -> None:
        self.cfg = config
        self.deps = deps
        if calibrator is None and config.decision.use_calibrated_threshold:
            from .calibration import ConvictionCalibrator
            calibrator = ConvictionCalibrator(
                percentile=config.decision.threshold_percentile,
                warmup=config.decision.calibration_warmup,
                absolute_floor=config.decision.absolute_floor_score,
            )
        self.calibrator = calibrator

    # -----------------------------------------------------------------
    def decide(self, ctx, breaker_verdict=None, *, sample_size: int = 0,
               measured_hit_rate: float | None = None) -> Decision:
        cfg = self.cfg
        measuring = sample_size < cfg.decision.measurement_min_sample

        # ===== PASO 1: CAPA 0 =========================================
        veto, outcomes = run_capa0(ctx, breaker_verdict)
        if not veto.passed:
            return self._no_trade(
                ctx, veto, (), regime_mod.RegimeCall(Cycle.UNKNOWN, RiskMode.NEUTRAL, 0.0, (), {}, 0.0),
                0.0, 0, None, (), blocked=veto.codes,
                headline="CAPA 0 veto antes de cualquier analisis: no se evaluo ninguna capa.",
                outcomes=outcomes,
            )

        # ===== PASO 2: REGIMEN ========================================
        reg = regime_mod.detect(ctx)

        # ===== PASO 3: SCORES DE CADA CAPA ============================
        scores: tuple[LayerScore, ...] = (
            self.deps.technical.evaluate(ctx),
            self.deps.fundamental.evaluate(ctx),
            self.deps.macro.evaluate(ctx),
            self.deps.policy.evaluate(ctx),
            self.deps.positioning.evaluate(ctx),
        )

        # ===== PASO 4: COMBINACION PONDERADA POR REGIMEN ==============
        # La confianza entra como PESO, no como factor de encogimiento.
        #
        # Si se multiplicara el score por la confianza y despues se promediara
        # con los pesos de regimen, una capa con confianza 0.5 arrastraria el
        # score combinado hacia cero aunque su lectura fuera nitida. El efecto
        # se acumula sobre cinco capas y el score combinado nunca llega a un
        # umbral exigente: el sistema no operaria nunca, y no por prudencia
        # sino por un error de algebra.
        #
        # Lo correcto: la confianza decide CUANTO VOTA cada capa, y la falta
        # agregada de cobertura se cobra subiendo el umbral (abajo), que es
        # donde la incertidumbre debe pagarse.
        weights = reg.weights
        num = sum(s.score * s.confidence * weights.get(s.layer, 0.0) for s in scores)
        den = sum(s.confidence * weights.get(s.layer, 0.0) for s in scores)
        wsum = sum(weights.get(s.layer, 0.0) for s in scores)
        combined = num / den if den > 1e-9 else 0.0
        coverage = den / wsum if wsum else 0.0

        # ===== PASO 6 (adelantado): CONTRADICCION =====================
        # Se evalua antes del umbral porque una contradiccion invalida el
        # score combinado entero, no solo su magnitud.
        contra = check_contradiction(ctx, scores)
        if contra.fired:
            veto2 = VetoResult(False, (contra.as_reason(),), veto.checks_run + 1)
            return self._no_trade(ctx, veto2, scores, reg, combined, 0, None, (),
                                  blocked=("VETO_CONTRADICCION",),
                                  headline="Capas en contradiccion fuerte: no se opera.")

        side = Side.LONG if combined > 0 else Side.SHORT
        sign = side.sign

        # ===== PASO 5: UMBRAL Y CAPAS ALINEADAS =======================
        base_threshold = cfg.decision.threshold_score
        calib_note = f"umbral fijo {base_threshold:.0f}"
        if cfg.decision.use_calibrated_threshold and self.calibrator is not None:
            base_threshold, calib_note = self.calibrator.threshold(cfg.decision.threshold_score)
        coverage_bump = (1.0 - coverage) * cfg.decision.coverage_bump_max
        base_threshold += reg.threshold_bump + coverage_bump
        freq_verdict = None
        if self.deps.freq_governor is not None:
            freq_verdict = self.deps.freq_governor.evaluate(ctx.as_of, base_threshold)
            threshold = freq_verdict.effective_threshold
            size_mult_freq = freq_verdict.size_multiplier
        else:
            threshold = base_threshold
            size_mult_freq = 1.0

        # Una capa "alineada" necesita opinion fuerte Y datos detras. Se mide
        # sobre el score crudo, no el efectivo: si no, una capa con confianza
        # 0.5 nunca podria alinear aunque su lectura fuera inequivoca.
        aligned = [
            s for s in scores
            if abs(s.score) >= cfg.decision.min_layer_conviction
            and s.confidence >= cfg.decision.min_layer_confidence
            and (s.score > 0) == (sign > 0)
        ]
        n_aligned = len(aligned)

        if self.calibrator is not None:
            # Se observa DESPUES de fijar el umbral: el score de hoy no puede
            # influir en su propio umbral.
            self.calibrator.observe(ctx.as_of, combined)

        if abs(combined) < threshold or n_aligned < cfg.decision.min_aligned_layers:
            return self._no_trade(
                ctx, veto, scores, reg, combined, n_aligned, None, (),
                blocked=("UMBRAL_NO_ALCANZADO",),
                headline=(
                    f"Score combinado {combined:+.1f} contra umbral {threshold:.1f} y "
                    f"{n_aligned} capas alineadas de {cfg.decision.min_aligned_layers} exigidas. "
                    f"Senal mediocre: se descarta. [{calib_note}; cobertura de datos "
                    f"{coverage:.0%} -> recargo +{coverage_bump:.0f}]"
                ),
                freq_verdict=freq_verdict, weights=weights,
            )

        # ===== NIVELES: entrada, stop y objetivo estructural ==========
        lv = derive_levels(ctx, side, cfg.risk.min_rr_ratio)
        if not lv.viable:
            return self._no_trade(
                ctx, veto, scores, reg, combined, n_aligned, None, (),
                blocked=("ASIMETRIA_INSUFICIENTE",),
                headline=f"Niveles no viables: {lv.reason}",
                freq_verdict=freq_verdict, weights=weights,
            )

        # ===== CONVICCION =============================================
        conviction, conv_reason = self._conviction(combined, n_aligned, reg, scores, threshold)

        # ===== DIMENSIONAMIENTO =======================================
        size_mult = min(
            1.0,
            (breaker_verdict.size_multiplier if breaker_verdict else 1.0) * size_mult_freq
            * (self._measurement_multiplier() if measuring else 1.0),
        )
        size = atr_position_size(
            ctx.desk.equity, lv.entry, lv.stop, lv.atr, cfg.risk, size_multiplier=size_mult
        )

        # ===== PASO 7: ARBOL DE ESCENARIOS ============================
        vol_stress = self._vol_stress(ctx)
        gap_slip_r = (cfg.risk.stop_slippage_atr * lv.atr) / max(abs(lv.entry - lv.stop), 1e-9)
        tree = build_tree(TreeInputs(
            rr_target=lv.rr, conviction=conviction, vol_stress=vol_stress,
            gap_slippage_r=min(gap_slip_r, 3.0),
            measured_hit_rate=measured_hit_rate, sample_size=sample_size,
        ))
        # En medicion el gate de EV se DESACTIVA explicitamente (se pone en
        # -inf) y su lugar lo ocupa el presupuesto de medicion, que si es
        # estimable. El peor caso sigue teniendo que ser sobrevivible.
        min_ev = float("-inf") if measuring else cfg.decision.min_expected_r
        tv = evaluate_tree(
            tree, size.risk_pct if size.viable else cfg.risk.risk_per_trade_pct,
            min_ev, cfg.decision.max_worst_case_equity_pct,
        )
        self._last_min_ev = min_ev

        # ===== PASO 8: ABOGADO DEL DIABLO =============================
        args = devil.build_case(
            ctx, scores, reg, tv, freq_verdict, size,
            error_book=self.deps.error_book, sample_size=sample_size,
            measuring=measuring,
            measurement_size_multiplier=self._measurement_multiplier(),
        )

        # ===== LIMITES DE CARTERA =====================================
        cand_rets = log_returns(ctx.closes(90))
        peer_rets = {
            p.symbol: log_returns(ctx.peers[p.symbol].closes(90))
            for p in ctx.open_positions if p.symbol in ctx.peers
        }
        cors = limits_mod.portfolio_correlations(cand_rets, peer_rets)
        worst_cases = {
            p.symbol: abs(p.avg_price - p.initial_stop) * p.qty * (1 + cfg.risk.stop_slippage_atr * 0.5)
            for p in ctx.open_positions
        }
        lim = limits_mod.check_limits(
            symbol=ctx.symbol, sector=ctx.sector, entry_price=lv.entry, qty=size.qty,
            worst_case_loss=size.worst_case_loss, positions=ctx.open_positions,
            position_worst_cases=worst_cases, equity=ctx.desk.equity, cfg=cfg.risk,
            correlations=cors,
        )

        hypo = Position(
            symbol=ctx.symbol, side=side, qty=size.qty, avg_price=lv.entry,
            stop_price=lv.stop, initial_stop=lv.stop, opened_at=ctx.as_of,
            thesis_id="candidato", sector=ctx.sector, r_unit=size.r_unit_cash,
        )

        # ===== PASO 9: RISK OFFICER ===================================
        officer = risk_officer.review(
            ctx=ctx, side=side, entry=lv.entry, stop=lv.stop, targets=(lv.target,),
            size_result=size, limit_verdict=lim, breaker_verdict=breaker_verdict,
            tree_verdict=tv, arguments=args, freq_verdict=freq_verdict,
            hypothetical_position=hypo, measuring=measuring,
        )

        if not officer.approved:
            return self._no_trade(
                ctx, veto, scores, reg, combined, n_aligned, tv, args,
                blocked=tuple(v.code for v in officer.vetoes),
                headline=officer.message, freq_verdict=freq_verdict, weights=weights,
                officer=officer, levels=lv, conviction=conviction, conv_reason=conv_reason,
            )

        # ===== PLAN APROBADO ==========================================
        qty = officer.final_qty
        tranches = tuple(t * (qty / size.qty) for t in size.tranches) if size.qty else ()
        ts = time_stop_at(ctx.as_of, cfg.risk.time_stop_bdays, ctx.calendar)
        plan = TradePlan(
            symbol=ctx.symbol, side=side, entry_price=lv.entry, stop_price=lv.stop,
            targets=(lv.target,), total_qty=qty, tranches=tranches,
            risk_pct_of_equity=abs(lv.entry - lv.stop) * qty / ctx.desk.equity,
            r_unit_cash=abs(lv.entry - lv.stop) * qty, rr_ratio=lv.rr,
            time_stop=ts, sector=ctx.sector,
        )
        thesis, falsification = self._thesis(ctx, side, lv, reg, scores, aligned, ts)
        if measuring:
            thesis = (
                f"[MEDICION - VENTAJA NO DEMOSTRADA, {sample_size}/{cfg.decision.measurement_min_sample} "
                f"operaciones comparables; tamano al {self._measurement_multiplier():.0%}, "
                f"presupuesto total de aprendizaje {cfg.decision.measurement_budget_pct:.1%} del capital] "
            ) + thesis

        return Decision(
            ts=ctx.as_of, symbol=ctx.symbol,
            action=Action.OPEN_LONG if side is Side.LONG else Action.OPEN_SHORT,
            regime_cycle=reg.cycle, regime_risk=reg.risk_mode, veto=veto,
            layer_scores=scores, weights={k.value: v for k, v in weights.items()},
            combined_score=combined, aligned_layers=n_aligned, scenario_tree=tv.tree,
            arguments=args,
            voices=self._voices(ctx, scores, reg, combined, n_aligned, tv, args, officer,
                                freq_verdict, lv, veto, outcomes),
            plan=plan, thesis=thesis, falsification=falsification,
            falsification_deadline=ts, conviction=conviction, conviction_reason=conv_reason,
        )

    # -----------------------------------------------------------------
    def _conviction(self, combined, n_aligned, reg, scores, threshold) -> tuple[int, str]:
        """
        Conviccion 1..5, medida en PERCENTIL de lo que este sistema produce.

        Igual que el umbral: un corte absoluto ("score >= 80 = conviccion 5")
        sobre una escala sin calibrar no significa nada. Si los scores del
        sistema viven entre -60 y +60, la conviccion 5 seria inalcanzable y
        el arbol de escenarios usaria siempre la tasa de acierto mas baja.
        Medirla en percentiles la hace comparable entre regimenes y periodos.

        Las capas alineadas actuan como TECHO, no como sumando: una senal
        fortisima sostenida por una sola capa no es alta conviccion, es una
        capa gritando.
        """
        cov = sum(s.confidence for s in scores) / len(scores)
        a = abs(combined)
        pr = self.calibrator.percentile_of(combined) if self.calibrator else None

        if pr is not None:
            if pr >= 0.995:
                c = 5
            elif pr >= 0.99:
                c = 4
            elif pr >= 0.97:
                c = 3
            elif a >= threshold:
                c = 2
            else:
                c = 1
            basis = f"percentil {pr:.1%} de las senales historicas del sistema"
        else:
            # Warmup del calibrador: se cae a cortes absolutos, y se dice.
            c = 3 if a >= 60 else (2 if a >= threshold else 1)
            basis = "cortes absolutos (calibrador en warmup)"

        # Techos por evidencia
        if n_aligned < 4:
            c = min(c, 4)
        if n_aligned < 3:
            c = min(c, 2)
        if reg.confidence < 0.5:
            c = min(c, 3)
        if cov < 0.45:
            c = min(c, 3)

        return c, (
            f"conviccion {c}/5 por {basis}; score |{a:.0f}| contra umbral {threshold:.0f}, "
            f"{n_aligned} capas alineadas, confianza de regimen {reg.confidence:.2f}, "
            f"cobertura de datos {cov:.2f}"
        )

    def _measurement_multiplier(self) -> float:
        """Fraccion del tamano normal durante la fase de medicion."""
        d = self.cfg.decision
        return min(1.0, d.measurement_risk_per_trade / max(self.cfg.risk.risk_per_trade_pct, 1e-9))

    def _vol_stress(self, ctx) -> float:
        vix = ctx.macro("VIX")
        if vix is None:
            return 0.5
        return max(0.0, min(1.0, (vix - 12.0) / 20.0))

    def _thesis(self, ctx, side, lv, reg, scores, aligned, ts) -> tuple[str, str]:
        top = sorted(aligned, key=lambda s: -abs(s.effective))[:3]
        thesis = (
            f"{side.value} en {ctx.symbol} a {lv.entry:.2f}. Regimen {reg.label}. "
            f"Sostienen la tesis: " + "; ".join(f"{s.layer.value} ({s.effective:+.0f})" for s in top)
            + f". {lv.reason}"
        )
        falsification = (
            f"ESTA TESIS ES FALSA SI: (a) el precio cierra {'debajo' if side is Side.LONG else 'encima'} "
            f"de {lv.stop:.2f}, lo que invalida la estructura sobre la que se apoya la entrada; o "
            f"(b) al {ts.date()} ({self.cfg.risk.time_stop_bdays} ruedas) el precio no avanzo al menos "
            f"1R ({lv.entry + side.sign * abs(lv.entry - lv.stop):.2f}), lo que significa que la tesis "
            "no se materializo en el plazo previsto aunque todavia no haya perdido. "
            "Cualquiera de las dos cierra la posicion."
        )
        return thesis, falsification

    # -----------------------------------------------------------------
    def _voices(self, ctx, scores, reg, combined, n_aligned, tv, args, officer,
                freq, lv, veto, outcomes) -> tuple[Voice, ...]:
        """Las cinco voces, siempre las cinco, siempre separadas."""
        by = {s.layer: s for s in scores}
        tech, pos = by.get(LayerId.TECHNICAL), by.get(LayerId.POSITIONING)
        mac, pol = by.get(LayerId.MACRO), by.get(LayerId.POLICY)
        fun = by.get(LayerId.FUNDAMENTAL)

        quant_msg = (
            f"Score combinado {combined:+.1f} con {n_aligned} capas alineadas. "
            f"CAPA 1 tecnico: {tech.score:+.0f} (confianza {tech.confidence:.2f}). {tech.rationale} "
            f"|| CAPA 5 posicionamiento: {pos.score:+.0f}. {pos.rationale}"
        )
        if tv is not None:
            quant_msg += (
                f" || Arbol de escenarios: EV {tv.expected_r:+.2f}R, peor camino "
                f"{tv.tree.worst.name} en {tv.worst_r:.2f}R con probabilidad "
                f"{tv.tree.worst.probability:.0%}; el camino que justifica el trade tiene "
                f"{tv.tree.best.probability:.0%} de probabilidad."
            )
        if lv is not None and lv.atr:
            quant_msg += f" || Niveles: {lv.reason}"

        macro_msg = (
            f"Regimen {reg.label} (confianza {reg.confidence:.2f}, recargo al umbral "
            f"+{reg.threshold_bump:.0f}). Evidencia: {'; '.join(reg.evidence[:4])}. "
            f"|| CAPA 3: {mac.score:+.0f}. {mac.rationale[:400]} "
            f"|| CAPA 4 politico: {pol.score:+.0f}. {pol.rationale[:250]}"
        )

        fund_msg = f"CAPA 2: {fun.score:+.0f} (confianza {fun.confidence:.2f}). {fun.rationale[:500]}"

        if officer is not None:
            risk_msg = officer.message
            if officer.stress_summary:
                risk_msg += f" || Stress test: {officer.stress_summary}"
            if officer.reductions:
                risk_msg += " || Ajustes: " + "; ".join(officer.reductions)
        else:
            limpios = sum(1 for o in outcomes if not o.fired and not o.skipped)
            risk_msg = (
                f"CAPA 0: {limpios}/{len(outcomes)} chequeos limpios. "
                + ("VETADO: " + "; ".join(r.detail[:150] for r in veto.reasons) if not veto.passed
                   else "sin vetos previos.")
            )
        if freq is not None:
            risk_msg += f" || Frecuencia: {freq.note}"

        devil_msg = devil.render(args) if args else (
            "Sin argumentos generados en contra. Si el trade no llego a evaluarse, es esperable; "
            "si llego, revisar por que el generador de objeciones quedo mudo."
        )

        return (
            Voice(Role.QUANT, self._verdict(scores, LayerId.TECHNICAL), quant_msg),
            Voice(Role.MACRO, self._verdict(scores, LayerId.MACRO), macro_msg),
            Voice(Role.FUNDAMENTAL, self._verdict(scores, LayerId.FUNDAMENTAL), fund_msg),
            Voice(Role.RISK_OFFICER,
                  "APRUEBA" if (officer and officer.approved) else "VETA", risk_msg),
            Voice(Role.DEVILS_ADVOCATE,
                  f"{len(devil.blocking(args))} argumento(s) EN PIE" if args else "SIN CASO",
                  devil_msg),
        )

    @staticmethod
    def _verdict(scores, layer) -> str:
        s = next((x for x in scores if x.layer is layer), None)
        if s is None or s.confidence == 0:
            return "SE ABSTIENE"
        if s.score > 25:
            return "A FAVOR"
        if s.score < -25:
            return "EN CONTRA"
        return "NEUTRAL"

    # -----------------------------------------------------------------
    def _no_trade(self, ctx, veto, scores, reg, combined, n_aligned, tv, args,
                  *, blocked, headline, freq_verdict=None, weights=None,
                  officer=None, levels=None, conviction=1, conv_reason="",
                  outcomes=()) -> Decision:
        """
        NO OPERAR tambien produce un registro completo con las cinco voces.

        Es la posicion por defecto del sistema y la que mas se repite. Si no se
        registrara, seria imposible auditar por que el sistema estuvo afuera
        durante un tramo entero -- que es justo lo que hay que poder revisar.
        """
        if not scores:
            from ..contracts import LayerScore as LS
            scores = tuple(
                LS(lid, 0.0, 0.0, "no evaluada: CAPA 0 corto la evaluacion antes del scoring")
                for lid in (LayerId.TECHNICAL, LayerId.FUNDAMENTAL, LayerId.MACRO,
                            LayerId.POLICY, LayerId.POSITIONING)
            )
        return Decision(
            ts=ctx.as_of, symbol=ctx.symbol, action=Action.NO_TRADE,
            regime_cycle=reg.cycle, regime_risk=reg.risk_mode, veto=veto,
            layer_scores=scores,
            weights={k.value: v for k, v in (weights or reg.weights or {}).items()},
            combined_score=combined, aligned_layers=n_aligned, scenario_tree=tv.tree if tv else None,
            arguments=args,
            voices=self._voices(ctx, scores, reg, combined, n_aligned, tv, args, officer,
                                freq_verdict, levels, veto, outcomes),
            plan=None, thesis=headline,
            falsification="", falsification_deadline=None,
            conviction=conviction, conviction_reason=conv_reason or "sin operacion: conviccion no aplica",
            blocked_by=tuple(blocked),
        )
