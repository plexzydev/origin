"""
Configuracion del sistema. Un solo lugar, todo explicito, todo auditable.

Principio: los limites de riesgo son un TRINQUETE. Solo se pueden mover hacia
mas conservador. `SystemConfig.tighten_only()` lo hace cumplir en tiempo de
ejecucion, para que la CAPA 6 (aprendizaje) no pueda aflojarlos nunca.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping


# ---------------------------------------------------------------------------
# Universo
# ---------------------------------------------------------------------------

INDEX_ETFS = ("SPY", "QQQ", "IWM", "DIA", "MDY")

SECTOR_SPDRS = ("XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC")

LARGE_CAPS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B", "LLY",
    "JPM", "V", "XOM", "UNH", "MA", "COST", "HD", "PG", "JNJ", "ABBV",
    "WMT", "NFLX", "BAC", "CRM", "ORCL", "CVX", "MRK", "KO", "AMD", "PEP",
    "ADBE", "TMO", "LIN", "CSCO", "ACN", "MCD", "ABT", "PM", "DHR", "IBM",
    "GE", "TXN", "QCOM", "INTU", "VZ", "CAT", "NOW", "AMGN", "ISRG", "NEE",
    "CMCSA", "PFE", "SPGI", "RTX", "UNP", "UBER", "AMAT", "HON", "LOW", "T",
    "COP", "BKNG", "PLD", "ELV", "SYK", "BLK", "MS", "GS", "VRTX", "TJX",
    "SCHW", "LMT", "MDT", "AXP", "SBUX", "ADP", "GILD", "MMC", "DE", "BSX",
    "CB", "ADI", "PGR", "REGN", "ETN", "MU", "LRCX", "CI", "SO", "ZTS",
    "BDX", "PANW", "KLAC", "DUK", "SLB", "EOG", "APD", "ITW", "SHW", "CME",
    "NOC", "MCK", "WM", "CSX", "GD", "FDX", "TGT", "MAR", "PYPL", "ORLY",
    "MPC", "PSX", "VLO", "AON", "HCA", "NSC", "EMR", "ROP", "PH", "MSI",
    "AJG", "AFL", "TRV", "ALL", "MET", "PRU", "F", "GM", "DAL", "UAL",
)

DEFAULT_UNIVERSE = INDEX_ETFS + SECTOR_SPDRS + LARGE_CAPS


# ---------------------------------------------------------------------------
# CAPA 0 - umbrales de veto
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class VetoConfig:
    """Cada campo corresponde a uno de los filtros de CAPA 0."""
    vix_extreme: float = 32.0                     # regimen de volatilidad extrema
    vix_backwardation_points: float = 1.5         # VIX - VIX3M >= esto => backwardation fuerte
    hy_spread_widen_bps_5d: float = 60.0          # ampliacion rapida de high yield
    hy_spread_absolute_bps: float = 700.0         # nivel absoluto de estres
    macro_event_window_hours: int = 48            # evento macro programado
    earnings_window_bdays: int = 5                # earnings de la empresa
    min_dollar_volume_20d: float = 20_000_000.0   # liquidez minima
    min_volume_ratio_vs_20d: float = 0.60         # volumen actual vs promedio
    max_spread_bps: float = 8.0                   # spread ancho
    min_book_depth_usd: float = 50_000.0          # profundidad de libro
    max_gap_atr: float = 1.0                      # gap de apertura > X ATR
    max_portfolio_correlation: float = 0.65       # correlacion media del libro
    drawdown_reduce_pct: float = 0.06             # DD vigente que activa reduccion
    drawdown_veto_pct: float = 0.10               # DD que bloquea aperturas nuevas
    max_data_staleness_bars: int = 1              # feed atrasado
    max_data_gap_bdays: int = 2                   # huecos en la serie
    return_anomaly_sigma: float = 8.0             # valores anomalos
    contradiction_score: float = 50.0             # dos capas opuestas y fuertes
    holiday_lookahead_days: int = 4               # fin de semana largo / feriado
    max_trades_per_week: int = 6                  # sobreoperacion => pausa obligatoria
    # Si demasiados chequeos no se pueden correr por falta de datos, eso ES un
    # veto: un riesgo que no se puede medir no es un riesgo chico.
    max_skipped_checks: int = 3


# ---------------------------------------------------------------------------
# Motor de decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DecisionConfig:
    """
    El umbral de conviccion. Es el unico dial que la cuota de frecuencia puede
    mover, y nunca por debajo de `absolute_floor_score`.
    """
    threshold_score: float = 55.0            # umbral inicial, antes de calibrar
    absolute_floor_score: float = 38.0       # piso duro: ni la cuota baja de aca
    # El umbral real se calibra por PERCENTIL sobre las senales pasadas del
    # propio sistema. Un numero absoluto sobre una escala sin calibrar no
    # significa nada: ver engine/calibration.py.
    use_calibrated_threshold: bool = True
    threshold_percentile: float = 0.97       # solo el 3% mejor de las senales
    calibration_warmup: int = 250
    min_aligned_layers: int = 3              # al menos 3 capas alineadas
    min_layer_conviction: float = 25.0       # |score| para contar como "alineada"
    min_layer_confidence: float = 0.30       # una capa sin datos no "alinea" nada
    # Cobertura de datos pobre no debilita la senal: sube la exigencia.
    coverage_bump_max: float = 20.0
    min_expected_r: float = 0.20             # EV exigido cuando la ventaja esta DEMOSTRADA
    # MODO MEDICION.
    #
    # El arbol de escenarios ancla la tasa de acierto en la caminata aleatoria
    # (1/(1+R:R)) porque es lo unico afirmable sin evidencia. Con esa tasa, la
    # friccion real -- gaps, parciales, salidas por tiempo -- da EV negativo
    # SIEMPRE, para cualquier R:R. El sistema necesita ~13 puntos porcentuales
    # de ventaja sobre el azar para no perder plata.
    #
    # Consecuencia: un sistema honesto no puede justificar su primera operacion
    # con EV positivo, porque todavia no midio nada. Y no puede medir sin operar.
    #
    # Se resuelve con un estado explicito: mientras haya menos de
    # `measurement_min_sample` operaciones comparables, el sistema opera en
    # MEDICION -- tamano reducido, EV exigido relajado (pero peor caso igual de
    # sobrevivible), y cada decision marcada VENTAJA_NO_DEMOSTRADA. Recien con
    # muestra suficiente la tasa medida reemplaza a la teorica y se exige EV
    # positivo de verdad.
    measurement_min_sample: int = 30
    # Durante la medicion NO se filtra por EV. Filtrar por una esperanza que
    # todavia no se puede estimar es filtrar por una constante: el modelo sin
    # muestra siempre devuelve "caminata aleatoria menos friccion", o sea
    # negativo, para cualquier setup. El gate se vuelve un apagado disfrazado
    # de analisis.
    #
    # Lo que SI se puede acotar es cuanto se esta dispuesto a gastar
    # aprendiendo. El presupuesto de medicion es el costo maximo de descubrir
    # si el sistema tiene ventaja, asumiendo que TODAS las operaciones de
    # medicion pierden. Es un numero conocido, chico y decidido de antemano.
    measurement_budget_pct: float = 0.05      # 5% del capital, total
    # Lo que si sigue vigente en medicion: el peor caso debe ser sobrevivible.

    @property
    def measurement_risk_per_trade(self) -> float:
        """Riesgo por operacion durante la medicion: presupuesto / muestra."""
        return self.measurement_budget_pct / max(1, self.measurement_min_sample)
    max_worst_case_equity_pct: float = 0.025 # el peor escenario no puede costar mas
    devils_advocate_blocking: str = "HIGH"   # severidad en pie que bloquea


# ---------------------------------------------------------------------------
# Frecuencia de operacion
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FrequencyPolicy:
    """
    Frecuencia objetivo.

    LEER: subir la frecuencia NO crea oportunidades, solo baja el filtro.
    Por eso el sistema separa dos mecanismos que se suelen confundir:

      1. AMPLIAR EL UNIVERSO  -> mas candidatos, MISMA exigencia. Gratis.
      2. BAJAR EL UMBRAL      -> misma cantidad de candidatos, MENOS exigencia.
                                 Se paga con peores trades.

    El sistema usa (1) primero, siempre. Solo recurre a (2) si `quota_mode`
    esta encendido, y cuando lo hace marca cada trade como FORZADO_POR_CUOTA
    y mide su resultado POR SEPARADO. A los pocos meses los numeros dicen si
    la cuota cuesta plata o no. No se discute: se mide.

    Lo que la cuota NUNCA toca: los vetos de CAPA 0, el riesgo por operacion,
    el ratio 1:3, los cortafuegos, ni el veto del Risk Officer.
    """
    target_trades_per_month: float = 10.0
    # Piso mensual. El sistema empuja para alcanzarlo bajando SOLO el umbral.
    quota_floor_per_month: int = 10
    quota_mode: bool = True
    # Techo semanal: sigue vigente aunque la cuota vaya atrasada.
    hard_ceiling_per_week: int = 6
    # Cuantos dias habiles sin operar antes de empezar a aflojar el umbral.
    slack_days_before_easing: int = 3
    # Cuanto baja el umbral por cada dia habil de atraso, en puntos de score.
    ease_per_lagging_day: float = 2.5
    # Barrera absoluta: debe coincidir con DecisionConfig.absolute_floor_score.
    never_below_score: float = 38.0
    # Los trades forzados van con tamano reducido: menos conviccion, menos plata.
    forced_trade_size_multiplier: float = 0.5


# ---------------------------------------------------------------------------
# Riesgo
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RiskConfig:
    risk_per_trade_pct: float = 0.0075        # 0.75% -- dentro del rango 0.5-1%
    max_risk_per_trade_pct: float = 0.01      # techo duro
    # ASIMETRIA -- DESVIACION DELIBERADA DEL MANDATO ORIGINAL, DOCUMENTADA.
    #
    # El mandato pedia 1:3. Medido sobre datos (ver engine/feasibility.py):
    # con el limite de riesgo estresado del 4% y 0.75% por operacion entran
    # ~5 posiciones simultaneas; para 10 operaciones mensuales cada una debe
    # durar ~11-20 ruedas; y a ese plazo el recorrido favorable mediano da un
    # R:R de 1.2-1.7, no de 3. Las tres condiciones no pueden ser ciertas a
    # la vez.
    #
    # Decision del operador: priorizar FRECUENCIA. R:R minimo 1.5:1.
    # Consecuencia aritmetica que hay que tener presente: con 1.5:1 el punto
    # de equilibrio esta en 40% de aciertos (contra 25% con 1:3). El sistema
    # necesita acertar MAS seguido para no perder plata. La asimetria sigue
    # siendo positiva, pero el margen de error es menor.
    #
    # Para volver al mandato original: min_rr_ratio=3.0, time_stop_bdays=130,
    # quota_mode=False. Eso da ~1 operacion por mes.
    min_rr_ratio: float = 1.5
    kelly_fraction: float = 0.25              # Kelly completo es suicida
    entry_tranches: tuple[float, ...] = (0.5, 0.3, 0.2)
    stop_slippage_atr: float = 2.0            # el stop NO es garantia: se desliza
    # Cortafuegos en cascada
    daily_loss_halt_pct: float = 0.02
    weekly_loss_halfsize_pct: float = 0.04
    monthly_loss_shutdown_pct: float = 0.07
    consecutive_losses_pause: int = 3
    # Escalera de drawdown: (dd minimo, multiplicador de tamano)
    drawdown_ladder: tuple[tuple[float, float], ...] = (
        (0.00, 1.00), (0.04, 0.75), (0.06, 0.50), (0.08, 0.25), (0.10, 0.00),
    )
    # Correlacion y concentracion
    max_positions: int = 6
    max_weight_per_asset: float = 0.15
    max_weight_per_sector: float = 0.30
    max_gross_exposure: float = 0.60
    # En crisis todo correlaciona a 1: exposicion efectiva asumiendo corr=1
    max_stressed_risk_pct: float = 0.04
    # Proteccion de ganancias
    breakeven_at_r: float = 1.0               # a 1R el stop va a breakeven + costos
    partial_take_r: tuple[float, ...] = (1.5, 3.0)
    partial_take_fraction: tuple[float, ...] = (0.33, 0.33)
    time_stop_bdays: int = 20                 # salida por tiempo


# ---------------------------------------------------------------------------
# Costos de ejecucion
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CostConfig:
    """
    Costos deliberadamente PEORES que el historico.

    Justificacion: el slippage no es una constante, es una funcion del estres.
    El dia que mas necesitas salir es el dia que peor te ejecutan. Modelar el
    promedio historico es modelar el dia que no importa.
    """
    commission_per_share: float = 0.005
    commission_min: float = 1.00
    half_spread_bps: float = 1.5              # ETFs liquidos
    base_slippage_bps: float = 2.0
    pessimism_multiplier: float = 1.75        # castigo explicito sobre el historico
    stop_slippage_multiplier: float = 3.0     # salir por stop siempre ejecuta peor
    illiquid_penalty_bps: float = 12.0


# ---------------------------------------------------------------------------
# Raiz
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SystemConfig:
    universe: tuple[str, ...] = DEFAULT_UNIVERSE
    veto: VetoConfig = field(default_factory=VetoConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    frequency: FrequencyPolicy = field(default_factory=FrequencyPolicy)
    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    version: str = "0.1.0"

    def __post_init__(self) -> None:
        if self.risk.risk_per_trade_pct > self.risk.max_risk_per_trade_pct:
            raise ValueError("riesgo por trade por encima del techo duro")
        if self.decision.absolute_floor_score != self.frequency.never_below_score:
            raise ValueError(
                "El piso de score del motor y el de la cuota deben coincidir; "
                "si difieren, la cuota podria perforar el piso sin que se note."
            )
        if self.frequency.quota_floor_per_month > 0 and not self.frequency.quota_mode:
            raise ValueError("piso de cuota definido pero quota_mode apagado")

    # -- Trinquete de riesgo ------------------------------------------------
    def tighten_only(self, **changes: float) -> "SystemConfig":
        """
        Unica via para modificar riesgo desde la CAPA 6. Rechaza cualquier
        cambio que afloje un limite. No hay flag para saltearlo: si hiciera
        falta uno, el sistema ya perdio.
        """
        tighter_is_smaller = {
            "risk_per_trade_pct", "daily_loss_halt_pct", "weekly_loss_halfsize_pct",
            "monthly_loss_shutdown_pct", "max_positions", "max_weight_per_asset",
            "max_weight_per_sector", "max_gross_exposure", "max_stressed_risk_pct",
            "kelly_fraction",
        }
        tighter_is_larger = {"min_rr_ratio", "stop_slippage_atr"}
        new_risk = self.risk
        for k, v in changes.items():
            cur = getattr(new_risk, k)
            if k in tighter_is_smaller and v > cur:
                raise ValueError(f"Prohibido aflojar {k}: {cur} -> {v}")
            if k in tighter_is_larger and v < cur:
                raise ValueError(f"Prohibido aflojar {k}: {cur} -> {v}")
            new_risk = replace(new_risk, **{k: v})
        return replace(self, risk=new_risk)

    def describe_weights_doc(self) -> Mapping[str, str]:
        return {
            "umbral": f"score combinado >= {self.decision.threshold_score}",
            "piso_duro": f"nunca por debajo de {self.decision.absolute_floor_score}",
            "capas_alineadas": f">= {self.decision.min_aligned_layers}",
            "asimetria": f"R:R >= {self.risk.min_rr_ratio}:1",
            "riesgo_trade": f"{self.risk.risk_per_trade_pct:.2%} del capital",
        }
