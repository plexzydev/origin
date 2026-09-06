"""
Mundo sintetico determinista. Infraestructura de test y demo, NO el producto.

Para que sirve: permite ejercitar el sistema completo -- vetos, capas, riesgo,
backtest -- sin depender de una API externa, y con la ventaja decisiva de que
la VERDAD es conocida. Si el generador produce una tendencia alcista entre dos
fechas y el sistema no la ve, el problema es del sistema.

Genera a proposito cosas incomodas:
  - regimenes que cambian (alza, lateral, crash, recuperacion)
  - series macro CON REVISIONES, para ejercitar el store point-in-time
  - eventos macro y earnings con fechas de anuncio realistas
  - una empresa que reexpresa un balance
Todo con semilla fija: dos corridas dan resultados identicos bit a bit.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ...contracts import Bar, utc
from ..bars import BarSeries
from ..calendar import EventCalendar, EarningsEvent, EventKind, MacroEvent, TradingCalendar
from ..fundamentals import FundamentalRecord, FundamentalStore
from ..pit import Observation, PointInTimeStore, SurvivorshipAwareUniverse, UniverseMembership


@dataclass(frozen=True, slots=True)
class RegimeSpec:
    """Un tramo del mercado sintetico."""
    name: str
    days: int
    drift: float          # deriva diaria del factor de mercado
    vol: float            # desvio diario
    label: str            # etiqueta de verdad, para validar la deteccion


DEFAULT_REGIMES = (
    RegimeSpec("alza_tranquila", 260, 0.00055, 0.0072, "EXPANSION/RISK_ON"),
    RegimeSpec("desaceleracion", 130, 0.00005, 0.0105, "DESACELERACION/NEUTRAL"),
    RegimeSpec("crash", 45, -0.0055, 0.0310, "CONTRACCION/RISK_OFF"),
    RegimeSpec("recuperacion", 150, 0.00085, 0.0150, "RECUPERACION/RISK_ON"),
    RegimeSpec("lateral", 170, 0.00008, 0.0088, "EXPANSION/NEUTRAL"),
)


@dataclass(slots=True)
class SyntheticWorld:
    bars: dict[str, BarSeries]
    pit: PointInTimeStore
    events: EventCalendar
    fundamentals: FundamentalStore
    sector_map: dict[str, str]
    calendar: TradingCalendar
    universe: SurvivorshipAwareUniverse
    sessions: list[datetime]
    truth: list[tuple[datetime, str]] = field(default_factory=list)

    def to_bundle(self, history_window: int = 400):
        """Convierte el mundo sintetico en el DataBundle que consume el sistema."""
        from ..bundle import DataBundle
        return DataBundle(
            bars=self.bars, calendar=self.calendar, pit=self.pit, events=self.events,
            fundamentals=self.fundamentals, sector_map=self.sector_map,
            intraday=False, history_window=history_window,
        )

    def regime_truth_at(self, ts: datetime) -> str:
        best = "DESCONOCIDO"
        for t, lab in self.truth:
            if t <= ts:
                best = lab
        return best


# Universo sintetico ampliado. Mismo criterio que el universo real de
# config.py: mas candidatos con la MISMA exigencia por candidato. La cantidad
# de operaciones escala con el universo; el estandar por operacion, no.
SECTORS = {
    "SPY": "INDICE", "QQQ": "INDICE", "IWM": "INDICE", "DIA": "INDICE",
    "XLK": "TECNOLOGIA", "XLF": "FINANCIERO", "XLE": "ENERGIA", "XLV": "SALUD",
    "XLI": "INDUSTRIAL", "XLY": "CONSUMO_DISC", "XLP": "CONSUMO", "XLU": "SERVICIOS",
    "AAPL": "TECNOLOGIA", "MSFT": "TECNOLOGIA", "NVDA": "TECNOLOGIA", "AVGO": "TECNOLOGIA",
    "ORCL": "TECNOLOGIA", "CRM": "TECNOLOGIA", "AMD": "TECNOLOGIA", "ADBE": "TECNOLOGIA",
    "CSCO": "TECNOLOGIA", "TXN": "TECNOLOGIA", "QCOM": "TECNOLOGIA", "INTU": "TECNOLOGIA",
    "JPM": "FINANCIERO", "BAC": "FINANCIERO", "GS": "FINANCIERO", "MS": "FINANCIERO",
    "WFC": "FINANCIERO", "BLK": "FINANCIERO", "SCHW": "FINANCIERO", "AXP": "FINANCIERO",
    "XOM": "ENERGIA", "CVX": "ENERGIA", "COP": "ENERGIA", "SLB": "ENERGIA",
    "EOG": "ENERGIA", "MPC": "ENERGIA", "PSX": "ENERGIA", "VLO": "ENERGIA",
    "JNJ": "SALUD", "UNH": "SALUD", "LLY": "SALUD", "ABBV": "SALUD",
    "MRK": "SALUD", "PFE": "SALUD", "TMO": "SALUD", "ABT": "SALUD",
    "KO": "CONSUMO", "PG": "CONSUMO", "PEP": "CONSUMO", "COST": "CONSUMO",
    "WMT": "CONSUMO", "PM": "CONSUMO", "MDLZ": "CONSUMO", "CL": "CONSUMO",
    "CAT": "INDUSTRIAL", "HON": "INDUSTRIAL", "GE": "INDUSTRIAL", "UNP": "INDUSTRIAL",
    "RTX": "INDUSTRIAL", "DE": "INDUSTRIAL", "LMT": "INDUSTRIAL", "UPS": "INDUSTRIAL",
    "HD": "CONSUMO_DISC", "MCD": "CONSUMO_DISC", "NKE": "CONSUMO_DISC", "SBUX": "CONSUMO_DISC",
    "LOW": "CONSUMO_DISC", "TJX": "CONSUMO_DISC", "BKNG": "CONSUMO_DISC", "TGT": "CONSUMO_DISC",
    "NEE": "SERVICIOS", "DUK": "SERVICIOS", "SO": "SERVICIOS", "AEP": "SERVICIOS",
}


def build_world(
    start: date = date(2019, 1, 2),
    symbols: tuple[str, ...] = tuple(SECTORS),
    seed: int = 20240101,
    regimes: tuple[RegimeSpec, ...] = DEFAULT_REGIMES,
) -> SyntheticWorld:
    rng = random.Random(seed)
    cal = TradingCalendar()

    # -- 1. Sesiones ---------------------------------------------------------
    total_days = sum(r.days for r in regimes)
    sessions: list[datetime] = []
    d = start
    while len(sessions) < total_days:
        if cal.is_session(d):
            sessions.append(utc(d.year, d.month, d.day, 21, 0))  # cierre NY en UTC
        d += timedelta(days=1)

    # -- 2. Factor de mercado con regimenes ---------------------------------
    market: list[float] = []
    truth: list[tuple[datetime, str]] = []
    i = 0
    level = 100.0
    for r in regimes:
        truth.append((sessions[i], r.label))
        for _ in range(r.days):
            if i >= len(sessions):
                break
            shock = rng.gauss(r.drift, r.vol)
            level *= math.exp(shock)
            market.append(shock)
            i += 1

    # -- 3. Factores sectoriales --------------------------------------------
    sector_names = sorted(set(SECTORS.values()))
    sector_shocks = {
        s: [rng.gauss(0.0, 0.006) for _ in range(len(market))] for s in sector_names
    }

    # -- 4. Series por simbolo ----------------------------------------------
    betas = {s: (1.0 if SECTORS.get(s) == "INDICE" else rng.uniform(0.6, 1.7)) for s in symbols}
    bars: dict[str, BarSeries] = {}
    closes_by_symbol: dict[str, list[float]] = {}

    for sym in symbols:
        sec = SECTORS.get(sym, "OTRO")
        beta = betas[sym]
        idio_vol = 0.004 if sec == "INDICE" else rng.uniform(0.008, 0.016)
        px = rng.uniform(40.0, 320.0)
        base_vol = rng.uniform(3e6, 9e7)
        out: list[Bar] = []
        cl: list[float] = []
        for k, ts in enumerate(sessions):
            shock = beta * market[k] + sector_shocks[sec][k] * (0.0 if sec == "INDICE" else 1.0)
            shock += rng.gauss(0.0, idio_vol)
            prev = px
            px *= math.exp(shock)
            rng_day = abs(shock) + abs(rng.gauss(0.0, 0.004))
            hi = max(prev, px) * (1 + rng_day * 0.55)
            lo = min(prev, px) * (1 - rng_day * 0.55)
            op = lo + (hi - lo) * rng.random()
            # El volumen sube con el movimiento: patron real y util para los filtros
            vol = base_vol * (1.0 + 5.0 * abs(shock)) * rng.uniform(0.7, 1.3)
            out.append(Bar(ts, op, max(hi, op, px), min(lo, op, px), px, round(vol)))
            cl.append(px)
        bars[sym] = BarSeries.from_iterable(sym, out)
        closes_by_symbol[sym] = cl

    # -- 5. Macro derivada del propio mercado (coherente, no independiente) --
    pit = PointInTimeStore()
    spy = closes_by_symbol.get("SPY") or next(iter(closes_by_symbol.values()))
    for k, ts in enumerate(sessions):
        # Drawdown de VENTANA MOVIL (60 ruedas), no historico.
        # El credito cotiza riesgo de default, no distancia al maximo historico:
        # en 2013 el SP500 seguia lejos del pico de 2000 en terminos reales y el
        # high yield estaba en 400bp. Usar el drawdown de todos los tiempos deja
        # al generador en estres permanente despues de cualquier crash.
        lo60 = max(0, k - 60)
        peak = max(spy[lo60:k + 1])
        dd = (peak - spy[k]) / peak

        # Volatilidad realizada 20d -> VIX sintetico
        lo = max(0, k - 20)
        rets = [math.log(spy[j + 1] / spy[j]) for j in range(lo, k) if spy[j] > 0]
        rv = (sum(r * r for r in rets) / len(rets)) ** 0.5 * math.sqrt(252) if len(rets) > 5 else 0.15
        vix = max(9.0, min(85.0, rv * 100 * 1.15 + 3.0 + rng.gauss(0, 0.8)))
        # Estructura temporal CONTINUA: contango con VIX bajo, aplanamiento
        # alrededor de 25, backwardation recien en estres real. Un escalon en
        # un umbral fijo hacia que la curva se diera vuelta de golpe y disparaba
        # el veto de volatilidad la mitad de las ruedas por puro artefacto.
        ratio = max(0.85, min(1.16, 1.145 - 0.0105 * max(0.0, vix - 12.0)))
        vix3m = vix * ratio + rng.gauss(0, 0.35)
        pit.add(Observation("VIX", ts.date(), ts, round(vix, 2), source="sintetico"))
        pit.add(Observation("VIX3M", ts.date(), ts, round(vix3m, 2), source="sintetico"))

        # High yield: se amplia con el drawdown y con la volatilidad
        # Calibrado contra la realidad: HY OAS ~330bp en calma (2019, 2021),
        # ~1100bp en el pico de marzo 2020. Un generador que deja el credito
        # permanentemente en estres hace que CAPA 0 vete el 100% del tiempo y
        # el resto del sistema nunca se ejercite.
        hy = 310 + dd * 1500 + max(0.0, vix - 17) * 11 + rng.gauss(0, 6)
        pit.add(Observation("HY_OAS", ts.date(), ts, round(hy, 1), source="sintetico"))
        pit.add(Observation("IG_OAS", ts.date(), ts, round(hy * 0.28, 1), source="sintetico"))

        # Curva de tasas: se aplana y se invierte antes de la contraccion
        t10 = 2.6 - dd * 3.2 + rng.gauss(0, 0.05)
        t2 = t10 - 0.55 + dd * 2.1 + rng.gauss(0, 0.05)
        pit.add(Observation("DGS10", ts.date(), ts, round(t10, 3), source="sintetico"))
        pit.add(Observation("DGS2", ts.date(), ts, round(t2, 3), source="sintetico"))
        pit.add(Observation("DXY", ts.date(), ts, round(98 + dd * 9 + rng.gauss(0, 0.3), 2), source="sintetico"))
        pit.add(Observation("PUT_CALL", ts.date(), ts, round(0.85 + dd * 1.4 + rng.gauss(0, 0.06), 3), source="sintetico"))

    # -- 6. Series mensuales CON REVISIONES ---------------------------------
    # Este bloque existe para que el store point-in-time se ejercite de verdad.
    month_starts = sorted({(t.year, t.month) for t in sessions})
    for (y, m) in month_starts:
        period_end = date(y, m, 28)
        idx = next((k for k, t in enumerate(sessions) if (t.year, t.month) == (y, m)), 0)
        window = spy[max(0, idx - 60):idx + 1]
        mom = (window[-1] / window[0] - 1.0) if len(window) > 5 else 0.0

        # ISM: publicado el primer dia habil del mes siguiente
        ism_real = 52.0 + mom * 55.0
        rel1 = utc(y + (m == 12), (m % 12) + 1, 2)
        pit.add(Observation("ISM_MFG", period_end, rel1, round(ism_real + rng.gauss(0, 0.8), 1), 0, "sintetico"))
        # Revision un mes despues: el dato inicial NO era el definitivo
        rel2 = rel1 + timedelta(days=30)
        pit.add(Observation("ISM_MFG", period_end, rel2, round(ism_real + rng.gauss(0, 0.35), 1), 1, "sintetico"))

        # Nominas: se publican con ~5 dias de rezago y se revisan dos veces
        pr = 180_000 + mom * 900_000
        rel_p = utc(y + (m == 12), (m % 12) + 1, 5)
        pit.add(Observation("PAYROLLS", period_end, rel_p, round(pr + rng.gauss(0, 45_000)), 0, "sintetico"))
        pit.add(Observation("PAYROLLS", period_end, rel_p + timedelta(days=30), round(pr + rng.gauss(0, 20_000)), 1, "sintetico"))
        pit.add(Observation("PAYROLLS", period_end, rel_p + timedelta(days=60), round(pr + rng.gauss(0, 8_000)), 2, "sintetico"))

        cpi = 2.4 - mom * 4.5
        pit.add(Observation("CPI", period_end, utc(y + (m == 12), (m % 12) + 1, 13), round(cpi + rng.gauss(0, 0.1), 2), 0, "sintetico"))
        pit.add(Observation("CORE_PCE", period_end, utc(y + (m == 12), (m % 12) + 1, 28), round(cpi * 0.9 + rng.gauss(0, 0.08), 2), 0, "sintetico"))
        pit.add(Observation("UNRATE", period_end, rel_p, round(4.0 - mom * 6.0 + rng.gauss(0, 0.08), 2), 0, "sintetico"))
        pit.add(Observation("CLAIMS", period_end, rel_p, round(220_000 - mom * 400_000 + rng.gauss(0, 9_000)), 0, "sintetico"))
        pit.add(Observation("AAII_BULL", period_end, rel1, round(38.0 + mom * 90.0 + rng.gauss(0, 4), 1), 0, "sintetico"))
        pit.add(Observation("COT_SPEC", period_end, rel1, round(mom * 190_000 + rng.gauss(0, 20_000)), 0, "sintetico"))

    # -- 7. Calendario de eventos -------------------------------------------
    events = EventCalendar()
    # FOMC: aproximadamente cada 6 semanas
    k = 0
    while k < len(sessions):
        ts = sessions[k]
        events.add_macro(MacroEvent(EventKind.RATE_DECISION, ts.replace(hour=18), importance=5))
        k += 30
    # CPI mensual y nominas: dias fijos, importancia alta
    for (y, m) in month_starts:
        events.add_macro(MacroEvent(EventKind.CPI, utc(y, m, 13, 12, 30), importance=5,
                                    consensus=2.4, actual=None))
        events.add_macro(MacroEvent(EventKind.PAYROLLS, utc(y, m, 5, 12, 30), importance=5))

    # Earnings trimestrales por simbolo, anunciados ~21 dias antes
    fundamentals = FundamentalStore()
    for si, sym in enumerate(symbols):
        if SECTORS.get(sym) == "INDICE":
            continue
        offset = (si * 3) % 25
        for (y, m) in month_starts:
            if m % 3 != 1:
                continue
            edate = date(y, m, min(28, 12 + offset % 14))
            events.add_earnings(EarningsEvent(
                symbol=sym, expected_date=edate,
                announced_at=utc(y, m, 1) - timedelta(days=0),
                estimated=False, confirmed_date=edate,
            ))
            # Fundamental publicado el dia del reporte
            pe = date(y, m, 1) - timedelta(days=1)
            growth = 1.0 + rng.gauss(0.03, 0.05)
            rev = 1_000_000_000 * growth * (1 + si * 0.1)
            fundamentals.add(FundamentalRecord(
                symbol=sym, period_end=pe, filed_at=utc(edate.year, edate.month, edate.day, 21),
                sector=SECTORS.get(sym, "OTRO"),
                revenue=rev, gross_profit=rev * rng.uniform(0.32, 0.58),
                operating_income=rev * rng.uniform(0.10, 0.28),
                net_income=rev * rng.uniform(0.06, 0.20),
                operating_cash_flow=rev * rng.uniform(0.10, 0.26),
                capex=rev * rng.uniform(0.02, 0.08),
                total_debt=rev * rng.uniform(0.5, 2.6), cash=rev * rng.uniform(0.05, 0.5),
                ebitda=rev * rng.uniform(0.15, 0.34),
                interest_expense=rev * rng.uniform(0.005, 0.03),
                shares_diluted=1e9, buyback_cash=rev * rng.uniform(0.0, 0.05),
                insider_net_usd=rng.gauss(0, 4e6),
                eps_estimate_fwd=2.0 + rng.gauss(0, 0.2),
                eps_estimate_fwd_90d_ago=2.0 + rng.gauss(0, 0.2),
                eps_surprise_pct=rng.gauss(0.01, 0.05),
                price_reaction_pct=rng.gauss(0.0, 0.04),
                debt_maturities=((y + 1, rev * 0.2), (y + 3, rev * 0.4)),
                weighted_avg_coupon=0.035, refi_market_rate=0.055,
            ))

    # -- 8. Universo con bajas: sin esto habria sesgo de supervivencia ------
    uni = SurvivorshipAwareUniverse()
    for sym in symbols:
        uni.add(UniverseMembership("DEMO", sym, added_at=start))
    uni.add(UniverseMembership("DEMO", "QUIEBRA_SA", added_at=start,
                               removed_at=start + timedelta(days=400), removal_reason="quiebra"))

    return SyntheticWorld(
        bars=bars, pit=pit, events=events, fundamentals=fundamentals,
        sector_map=dict(SECTORS), calendar=cal, universe=uni,
        sessions=sessions, truth=truth,
    )
