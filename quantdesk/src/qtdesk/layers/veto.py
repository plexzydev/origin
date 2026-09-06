"""
CAPA 0 - FILTROS DE VETO.

Corre PRIMERO. Si cualquiera se activa, la evaluacion termina ahi: no se
pondera, no se compensa con un score alto en otra capa, no se discute.

Por que los vetos son binarios y no un score mas: un veto no dice "esto esta
un poco mal". Dice "el sistema no puede evaluar esta situacion con su modelo".
Promediar eso contra un RSI en 30 seria justamente el error que el veto existe
para evitar.

Regla de datos faltantes: cada chequeo puede terminar en DISPARADO, LIMPIO o
SALTEADO. Si se saltean demasiados (config.veto.max_skipped_checks), eso es a
su vez un veto. Un riesgo que no se puede medir no es un riesgo chico.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import fmean

from ..contracts import Severity, VetoReason, VetoResult
from ..data.quality import check_feed
from ..stats import correlation, log_returns
from . import indicators as ind
from .base import MarketContext


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    code: str
    fired: bool
    skipped: bool
    detail: str
    severity: Severity = Severity.CRITICAL

    def as_reason(self) -> VetoReason:
        return VetoReason(self.code, self.detail, self.severity)


def _clean(code: str, detail: str) -> CheckOutcome:
    return CheckOutcome(code, False, False, detail)


def _skip(code: str, detail: str) -> CheckOutcome:
    return CheckOutcome(code, False, True, detail)


def _fire(code: str, detail: str, sev: Severity = Severity.CRITICAL) -> CheckOutcome:
    return CheckOutcome(code, True, False, detail, sev)


# ---------------------------------------------------------------------------
# 1. Regimen de volatilidad extrema
# ---------------------------------------------------------------------------

def check_volatility_regime(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    vix = ctx.macro("VIX")
    if vix is None:
        return _skip("VETO_VOLATILIDAD", "sin dato de VIX publicado a la fecha")
    if vix >= cfg.vix_extreme:
        return _fire(
            "VETO_VOLATILIDAD",
            f"VIX en {vix:.1f} >= {cfg.vix_extreme:.0f}. En regimen de volatilidad "
            "extrema los stops se ejecutan lejos y la correlacion tiende a 1: "
            "el tamano calculado deja de representar el riesgo real.",
        )
    vix3m = ctx.macro("VIX3M")
    if vix3m is not None:
        spread = vix - vix3m
        if spread >= cfg.vix_backwardation_points:
            return _fire(
                "VETO_VOLATILIDAD",
                f"curva del VIX en backwardation: contado {vix:.1f} vs 3 meses "
                f"{vix3m:.1f} (+{spread:.1f}). El mercado paga mas por cobertura "
                "inmediata que por cobertura futura, que es la definicion de panico.",
            )
    return _clean("VETO_VOLATILIDAD", f"VIX {vix:.1f}, curva normal")


# ---------------------------------------------------------------------------
# 2. Spreads de credito high yield
# ---------------------------------------------------------------------------

def check_credit_stress(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    hy = ctx.macro("HY_OAS")
    if hy is None:
        return _skip("VETO_CREDITO", "sin dato de spread high yield")
    hist = ctx.macro_hist("HY_OAS", 6)
    if hy >= cfg.hy_spread_absolute_bps:
        return _fire(
            "VETO_CREDITO",
            f"spread high yield en {hy:.0f}bp >= {cfg.hy_spread_absolute_bps:.0f}bp. "
            "El credito es el mejor termometro anticipado de estres: cuando las "
            "empresas pagan esto por financiarse, el equity todavia no se entero.",
        )
    if len(hist) >= 6:
        widening = hy - hist[-6]
        if widening >= cfg.hy_spread_widen_bps_5d:
            return _fire(
                "VETO_CREDITO",
                f"high yield se amplio {widening:+.0f}bp en 5 ruedas "
                f"({hist[-6]:.0f} -> {hy:.0f}). La VELOCIDAD de ampliacion avisa "
                "antes que el nivel absoluto y antes que cualquier indicador tecnico.",
            )
        return _clean("VETO_CREDITO", f"HY {hy:.0f}bp, variacion 5d {widening:+.0f}bp")
    return _clean("VETO_CREDITO", f"HY {hy:.0f}bp (sin historia para medir velocidad)")


# ---------------------------------------------------------------------------
# 3. Evento macro programado dentro de 48hs
# ---------------------------------------------------------------------------

def check_macro_event(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    if ctx.events is None:
        return _skip("VETO_EVENTO_MACRO", "sin calendario de eventos cargado")
    evs = ctx.events.macro_within(ctx.as_of, cfg.macro_event_window_hours)
    if evs:
        e = evs[0]
        horas = (e.scheduled_at - ctx.as_of).total_seconds() / 3600.0
        return _fire(
            "VETO_EVENTO_MACRO",
            f"{e.kind.value} programado en {horas:.0f}hs ({e.scheduled_at:%Y-%m-%d %H:%M}). "
            "Entrar antes de un dato es apostar a la sorpresa, y la sorpresa no "
            "se puede modelar con analisis tecnico.",
        )
    return _clean("VETO_EVENTO_MACRO", f"sin eventos de peso en {cfg.macro_event_window_hours}hs")


# ---------------------------------------------------------------------------
# 4. Earnings de la empresa dentro de 5 dias habiles
# ---------------------------------------------------------------------------

def check_earnings(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    if ctx.events is None:
        return _skip("VETO_EARNINGS", "sin calendario de earnings cargado")
    evs = ctx.events.earnings_within(ctx.symbol, ctx.as_of, cfg.earnings_window_bdays, ctx.calendar)
    if evs:
        e = evs[0]
        d = e.date_known_at(ctx.as_of)
        marca = " (fecha ESTIMADA, no confirmada: se veta igual)" if e.estimated else ""
        return _fire(
            "VETO_EARNINGS",
            f"{ctx.symbol} reporta el {d}{marca}. Un reporte es un evento binario: "
            "el analisis tecnico no tiene informacion sobre el resultado y el gap "
            "posterior puede saltear el stop por completo.",
        )
    return _clean("VETO_EARNINGS", f"sin earnings en {cfg.earnings_window_bdays} ruedas")


# ---------------------------------------------------------------------------
# 5. Liquidez insuficiente
# ---------------------------------------------------------------------------

def check_liquidity(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    bars = ctx.bars(40)
    if len(bars) < 21:
        return _skip("VETO_LIQUIDEZ", "historia insuficiente para medir liquidez")

    dv = ind.dollar_volume(bars, 20)
    if dv is not None and dv < cfg.min_dollar_volume_20d:
        return _fire(
            "VETO_LIQUIDEZ",
            f"volumen en dolares 20d {dv:,.0f} < {cfg.min_dollar_volume_20d:,.0f}. "
            "En un papel asi el propio stop mueve el precio en contra.",
        )
    vr = ind.volume_ratio(bars, 20)
    if vr is not None and vr < cfg.min_volume_ratio_vs_20d:
        return _fire(
            "VETO_LIQUIDEZ",
            f"volumen de hoy al {vr:.0%} del promedio 20d (minimo {cfg.min_volume_ratio_vs_20d:.0%}). "
            "Movimiento sin participacion: no hay quien sostenga la ruptura.",
        )
    if ctx.quote is not None:
        if ctx.quote.spread_bps > cfg.max_spread_bps:
            return _fire(
                "VETO_LIQUIDEZ",
                f"spread {ctx.quote.spread_bps:.1f}bp > {cfg.max_spread_bps:.1f}bp: "
                "el costo de entrar y salir se come una parte relevante del objetivo.",
            )
        depth = min(ctx.quote.bid_size * ctx.quote.bid, ctx.quote.ask_size * ctx.quote.ask)
        if depth and depth < cfg.min_book_depth_usd:
            return _fire(
                "VETO_LIQUIDEZ",
                f"profundidad de libro {depth:,.0f} USD < {cfg.min_book_depth_usd:,.0f}. "
                "El libro no aguanta el tamano de la orden.",
            )
        return _clean("VETO_LIQUIDEZ", f"vol$ {dv:,.0f}, spread {ctx.quote.spread_bps:.1f}bp")
    return CheckOutcome(
        "VETO_LIQUIDEZ", False, False,
        f"vol$ 20d {dv:,.0f} OK; SIN libro de ordenes: spread y profundidad no verificados",
    )


# ---------------------------------------------------------------------------
# 6. Gap de apertura mayor a X ATR
# ---------------------------------------------------------------------------

def check_gap(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    bars = ctx.bars(30)
    if len(bars) < 16:
        return _skip("VETO_GAP", "historia insuficiente para medir el gap en ATR")
    a = ind.atr(bars, 14)
    if a is None or a <= 0:
        return _skip("VETO_GAP", "ATR no calculable")
    gap = bars[-1].open - bars[-2].close
    n = abs(gap) / a
    if n > cfg.max_gap_atr:
        return _fire(
            "VETO_GAP",
            f"gap de apertura {gap:+.2f} = {n:.2f} ATR (limite {cfg.max_gap_atr:.2f}). "
            "Un gap de este tamano significa que el mercado proceso informacion "
            "que el sistema no vio. Operar encima es operar a ciegas.",
        )
    return _clean("VETO_GAP", f"gap {n:.2f} ATR")


# ---------------------------------------------------------------------------
# 7. Correlacion del portafolio
# ---------------------------------------------------------------------------

def check_correlation(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    open_syms = [p.symbol for p in ctx.open_positions]
    if not open_syms:
        return _clean("VETO_CORRELACION", "sin posiciones abiertas: nada que correlacionar")
    cand = log_returns(ctx.closes(90))
    if len(cand) < 40:
        return _skip("VETO_CORRELACION", "historia insuficiente del candidato")
    cors: list[float] = []
    for s in open_syms:
        v = ctx.peers.get(s)
        if v is None:
            continue
        c = correlation(cand, log_returns(v.closes(90)))
        if c is not None:
            cors.append(c)
    if not cors:
        return _skip("VETO_CORRELACION", "sin series comparables de las posiciones abiertas")
    avg, peak = fmean(cors), max(cors)
    if avg > cfg.max_portfolio_correlation:
        return _fire(
            "VETO_CORRELACION",
            f"correlacion media con el libro {avg:.2f} > {cfg.max_portfolio_correlation:.2f} "
            f"(maxima {peak:.2f}). Sumar esto no diversifica: agranda la misma apuesta.",
        )
    return _clean("VETO_CORRELACION", f"correlacion media {avg:.2f}, maxima {peak:.2f}")


# ---------------------------------------------------------------------------
# 8. Drawdown vigente
# ---------------------------------------------------------------------------

def check_drawdown(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    dd = ctx.desk.drawdown
    if dd >= cfg.drawdown_veto_pct:
        return _fire(
            "VETO_DRAWDOWN",
            f"drawdown vigente {dd:.2%} >= {cfg.drawdown_veto_pct:.2%}. "
            "Recuperar exige un porcentaje mayor al que se perdio; a partir de "
            "aca preservar capital vale mas que cualquier setup.",
        )
    if dd >= cfg.drawdown_reduce_pct:
        return CheckOutcome(
            "VETO_DRAWDOWN", False, False,
            f"drawdown {dd:.2%}: por encima del umbral de reduccion, tamano recortado por la escalera",
            Severity.MEDIUM,
        )
    return _clean("VETO_DRAWDOWN", f"drawdown {dd:.2%}")


# ---------------------------------------------------------------------------
# 9. Calidad del feed
# ---------------------------------------------------------------------------

def check_data_quality(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    health = check_feed(
        ctx.view, ctx.as_of, ctx.calendar,
        max_staleness_sessions=cfg.max_data_staleness_bars,
        max_gap_sessions=cfg.max_data_gap_bdays,
        anomaly_sigma=cfg.return_anomaly_sigma,
    )
    if not health.ok:
        codes = ", ".join(f"{i.code} ({i.detail})" for i in health.blocking)
        return _fire("VETO_DATOS", f"feed no confiable: {codes}")
    return _clean("VETO_DATOS", f"feed sano sobre {health.bars_checked} barras")


# ---------------------------------------------------------------------------
# 10. Feriado o fin de semana largo proximo
# ---------------------------------------------------------------------------

def check_holiday(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    hit, detail = ctx.calendar.long_weekend_ahead(ctx.as_of.date(), cfg.holiday_lookahead_days)
    if hit:
        return _fire(
            "VETO_FERIADO",
            f"{detail}. Con el mercado cerrado el stop no existe: el riesgo pasa "
            "a ser el gap de reapertura, que no esta acotado.",
        )
    return _clean("VETO_FERIADO", "sin cierres prolongados a la vista")


# ---------------------------------------------------------------------------
# 11. Sobreoperacion
# ---------------------------------------------------------------------------

def check_overtrading(ctx: MarketContext) -> CheckOutcome:
    cfg = ctx.config.veto
    n = ctx.desk.trades_this_week
    if n >= cfg.max_trades_per_week:
        return _fire(
            "VETO_SOBREOPERACION",
            f"{n} operaciones esta semana >= techo {cfg.max_trades_per_week}. "
            "Operar por encima de la frecuencia esperada es senal de que el "
            "filtro se aflojo solo. Pausa obligatoria: el objetivo de frecuencia "
            "NO levanta este techo.",
        )
    return _clean("VETO_SOBREOPERACION", f"{n}/{cfg.max_trades_per_week} operaciones esta semana")


# ---------------------------------------------------------------------------
# 12. Cortafuegos de riesgo
# ---------------------------------------------------------------------------

def check_circuit_breakers(ctx: MarketContext, breaker) -> CheckOutcome:
    if breaker is None:
        return _skip("VETO_CORTAFUEGOS", "estado de cortafuegos no provisto")
    if not breaker.can_open:
        return _fire(
            "VETO_CORTAFUEGOS",
            f"cortafuegos en {breaker.level.value}: " + "; ".join(breaker.reasons),
        )
    return _clean("VETO_CORTAFUEGOS", f"cortafuegos en {breaker.level.value}")


# ---------------------------------------------------------------------------
# 13. Contradiccion entre capas -- VETO TARDIO
# ---------------------------------------------------------------------------

def check_contradiction(ctx: MarketContext, scores) -> CheckOutcome:
    """
    Unico veto que no puede correr primero: necesita los scores de las capas.

    Se evalua DESPUES del scoring y ANTES de construir el plan. Se documenta
    como veto tardio en vez de disfrazarlo de filtro previo, porque fingir que
    corre en CAPA 0 seria mentir sobre el orden real de ejecucion.
    """
    thr = ctx.config.veto.contradiction_score
    strong = [s for s in scores if abs(s.effective) >= thr]
    pos = [s for s in strong if s.effective > 0]
    neg = [s for s in strong if s.effective < 0]
    if pos and neg:
        p, n = max(pos, key=lambda s: s.effective), min(neg, key=lambda s: s.effective)
        return _fire(
            "VETO_CONTRADICCION",
            f"{p.layer.value} en {p.effective:+.0f} contra {n.layer.value} en "
            f"{n.effective:+.0f}, ambas por encima de {thr:.0f}. La contradiccion "
            "es informacion: significa que el escenario no se entiende. "
            "No se promedia, se sale.",
        )
    return _clean("VETO_CONTRADICCION", "sin contradicciones fuertes entre capas")


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------

PRE_SCORING_CHECKS = (
    check_volatility_regime,
    check_credit_stress,
    check_macro_event,
    check_earnings,
    check_liquidity,
    check_gap,
    check_correlation,
    check_drawdown,
    check_data_quality,
    check_holiday,
    check_overtrading,
)


def run_capa0(ctx: MarketContext, breaker=None) -> tuple[VetoResult, tuple[CheckOutcome, ...]]:
    """
    Corre todos los vetos previos al scoring.

    Devuelve el veredicto y el detalle de CADA chequeo -- tambien los que
    pasaron. El registro de lo que se verifico y dio limpio es parte de la
    auditoria: sin eso no se puede distinguir "no habia riesgo" de
    "no lo miramos".
    """
    outcomes: list[CheckOutcome] = [c(ctx) for c in PRE_SCORING_CHECKS]
    outcomes.append(check_circuit_breakers(ctx, breaker))

    fired = [o for o in outcomes if o.fired]
    skipped = [o for o in outcomes if o.skipped]

    if len(skipped) > ctx.config.veto.max_skipped_checks:
        fired.append(_fire(
            "VETO_COBERTURA_INSUFICIENTE",
            f"{len(skipped)} chequeos no se pudieron correr por falta de datos "
            f"({', '.join(o.code for o in skipped)}). Un riesgo que no se puede "
            "medir no es un riesgo chico: se sale.",
        ))

    return (
        VetoResult(
            passed=not fired,
            reasons=tuple(o.as_reason() for o in fired),
            checks_run=len(outcomes),
        ),
        tuple(outcomes),
    )
