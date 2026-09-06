"""
Registro de series macro. Un solo lugar donde se declara QUE dato es cual y
DE DONDE sale.

Que este el codigo de FRED al lado del nombre no es decoracion: cuando dentro
de seis meses una capa macro de un score raro, la primera pregunta es "que
serie miro", y la respuesta tiene que estar a un ctrl+F de distancia.

Todas se cargan en el PointInTimeStore con su fecha de publicacion real.
Las que FRED publica con vintages (ALFRED) tienen revisiones cargables; las
que no, quedan marcadas y la capa lo dice en su justificacion.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Revisability(str, Enum):
    FINAL = "NO_SE_REVISA"           # precios de mercado: el cierre de ayer es el cierre de ayer
    REVISED = "SE_REVISA"            # PBI, nominas, ventas minoristas
    RESTATED = "SE_REEXPRESA"        # balances contables


@dataclass(frozen=True, slots=True)
class SeriesSpec:
    id: str
    name: str
    source: str
    source_code: str
    revisability: Revisability
    typical_lag_days: int            # cuanto tarda en publicarse tras el periodo
    higher_is_risk_on: bool | None = None


# -- Volatilidad y credito: los termometros de estres ------------------------
VIX = SeriesSpec("VIX", "Indice de volatilidad implicita SP500", "FRED", "VIXCLS", Revisability.FINAL, 0, False)
VIX3M = SeriesSpec("VIX3M", "Volatilidad implicita a 3 meses", "CBOE", "VIX3M", Revisability.FINAL, 0, False)
HY_OAS = SeriesSpec("HY_OAS", "Spread high yield (OAS)", "FRED", "BAMLH0A0HYM2", Revisability.FINAL, 1, False)
IG_OAS = SeriesSpec("IG_OAS", "Spread corporativo grado inversor", "FRED", "BAMLC0A0CM", Revisability.FINAL, 1, False)

# -- Curva de tasas ---------------------------------------------------------
DGS2 = SeriesSpec("DGS2", "Tesoro EEUU 2 anios", "FRED", "DGS2", Revisability.FINAL, 1)
DGS10 = SeriesSpec("DGS10", "Tesoro EEUU 10 anios", "FRED", "DGS10", Revisability.FINAL, 1)
DGS3M = SeriesSpec("DGS3M", "Letra 3 meses", "FRED", "DGS3MO", Revisability.FINAL, 1)
FEDFUNDS = SeriesSpec("FEDFUNDS", "Tasa efectiva de fondos federales", "FRED", "DFF", Revisability.FINAL, 1)

# -- Ciclo ------------------------------------------------------------------
ISM_MFG = SeriesSpec("ISM_MFG", "PMI manufacturero ISM", "ISM", "NAPM", Revisability.REVISED, 1, True)
ISM_SVC = SeriesSpec("ISM_SVC", "PMI de servicios ISM", "ISM", "NAPMSI", Revisability.REVISED, 3, True)
INDPRO = SeriesSpec("INDPRO", "Produccion industrial", "FRED", "INDPRO", Revisability.REVISED, 16, True)
RETAIL = SeriesSpec("RETAIL", "Ventas minoristas", "FRED", "RSAFS", Revisability.REVISED, 16, True)

# -- Inflacion --------------------------------------------------------------
CPI = SeriesSpec("CPI", "IPC general interanual", "BLS", "CPIAUCSL", Revisability.REVISED, 13, None)
CORE_PCE = SeriesSpec("CORE_PCE", "PCE nucleo interanual", "BEA", "PCEPILFE", Revisability.REVISED, 30, None)
BREAKEVEN_5Y = SeriesSpec("BREAKEVEN_5Y", "Expectativa de inflacion 5 anios", "FRED", "T5YIE", Revisability.FINAL, 1, None)

# -- Empleo -----------------------------------------------------------------
PAYROLLS = SeriesSpec("PAYROLLS", "Nominas no agricolas (variacion)", "BLS", "PAYEMS", Revisability.REVISED, 5, True)
UNRATE = SeriesSpec("UNRATE", "Tasa de desempleo", "BLS", "UNRATE", Revisability.REVISED, 5, False)
CLAIMS = SeriesSpec("CLAIMS", "Pedidos iniciales de subsidio", "DOL", "ICSA", Revisability.REVISED, 5, False)

# -- Liquidez y politica ----------------------------------------------------
M2 = SeriesSpec("M2", "Agregado monetario M2", "FRED", "M2SL", Revisability.REVISED, 30, True)
FED_ASSETS = SeriesSpec("FED_ASSETS", "Balance de la Reserva Federal", "FRED", "WALCL", Revisability.FINAL, 4, True)
NFCI = SeriesSpec("NFCI", "Indice de condiciones financieras (Chicago Fed)", "FRED", "NFCI", Revisability.REVISED, 4, False)

# -- Fiscal soberano --------------------------------------------------------
DEBT_GDP = SeriesSpec("DEBT_GDP", "Deuda federal / PBI", "FRED", "GFDEGDQ188S", Revisability.REVISED, 90, False)
DEFICIT_GDP = SeriesSpec("DEFICIT_GDP", "Deficit fiscal / PBI", "FRED", "FYFSGDA188S", Revisability.REVISED, 180, False)
CDS_5Y = SeriesSpec("CDS_5Y", "CDS soberano 5 anios", "MERCADO", "CDS5Y", Revisability.FINAL, 1, False)

# -- Divisas y commodities --------------------------------------------------
DXY = SeriesSpec("DXY", "Indice dolar", "ICE", "DTWEXBGS", Revisability.FINAL, 1, None)
WTI = SeriesSpec("WTI", "Petroleo WTI", "FRED", "DCOILWTICO", Revisability.FINAL, 1, None)
COPPER = SeriesSpec("COPPER", "Cobre", "MERCADO", "HG1", Revisability.FINAL, 0, True)
GOLD = SeriesSpec("GOLD", "Oro", "MERCADO", "GC1", Revisability.FINAL, 0, False)

# -- Posicionamiento --------------------------------------------------------
COT_SPEC = SeriesSpec("COT_SPEC", "Posicion neta grandes especuladores SP500", "CFTC", "COT", Revisability.FINAL, 3, None)
PUT_CALL = SeriesSpec("PUT_CALL", "Ratio put/call total CBOE", "CBOE", "PCALL", Revisability.FINAL, 0, None)
AAII_BULL = SeriesSpec("AAII_BULL", "Encuesta AAII % alcistas", "AAII", "AAII", Revisability.FINAL, 0, None)
SHORT_INTEREST = SeriesSpec("SHORT_INTEREST", "Interes corto sobre flotante", "FINRA", "SI", Revisability.FINAL, 10, None)

ALL_SERIES: tuple[SeriesSpec, ...] = tuple(
    v for k, v in list(globals().items())
    if isinstance(v, SeriesSpec)
)

BY_ID = {s.id: s for s in ALL_SERIES}


def spec(series_id: str) -> SeriesSpec:
    if series_id not in BY_ID:
        raise KeyError(f"Serie no registrada: {series_id}. Declarala en data/series.py antes de usarla.")
    return BY_ID[series_id]
