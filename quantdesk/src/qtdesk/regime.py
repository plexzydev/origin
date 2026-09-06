"""
Deteccion de regimen y tabla de pesos.

Por que existe: el mismo score tecnico significa cosas distintas segun el
contexto. Una ruptura alcista en marzo de 2020 no era una senal de compra,
era ruido dentro de un colapso de credito. La tabla de pesos codifica una
sola idea del mandato:

    "en panico mandan macro y credito; en calma, el tecnico"

Los pesos estan escritos aca, en una tabla explicita y versionada, no
dispersos en condicionales. Cualquiera puede leer que pesa cada capa en cada
regimen sin ejecutar el codigo, que es la unica forma de que la decision sea
auditable seis meses despues.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from .contracts import Cycle, LayerId, RiskMode
from .stats import percentile_rank


# ---------------------------------------------------------------------------
# TABLA DE PESOS  (suman 1.0 en cada fila)
# ---------------------------------------------------------------------------
# Justificacion de cada fila, para que no sea un numero magico:
#
# EXPANSION/RISK_ON     el tecnico manda: en tendencia establecida y con
#                       credito tranquilo, la estructura de precio es la
#                       informacion mas rapida que existe.
# EXPANSION/NEUTRAL     se le devuelve algo de peso a macro: sin confirmacion
#                       de risk-on, el precio miente mas seguido.
# DESACELERACION        macro pasa a mandar. Es el regimen donde el tecnico
#                       genera mas falsas rupturas.
# CONTRACCION/RISK_OFF  macro y credito dominan; el tecnico baja a 0.10. En
#                       panico todo correlaciona y el grafico de un papel deja
#                       de contener informacion propia.
# RECUPERACION          fundamental recupera peso: es cuando la divergencia
#                       entre precio y balance paga.
# ---------------------------------------------------------------------------

WEIGHT_TABLE: dict[tuple[Cycle, RiskMode], dict[LayerId, float]] = {
    (Cycle.EXPANSION, RiskMode.RISK_ON): {
        LayerId.TECHNICAL: 0.35, LayerId.FUNDAMENTAL: 0.20, LayerId.MACRO: 0.20,
        LayerId.POLICY: 0.10, LayerId.POSITIONING: 0.15,
    },
    (Cycle.EXPANSION, RiskMode.NEUTRAL): {
        LayerId.TECHNICAL: 0.30, LayerId.FUNDAMENTAL: 0.22, LayerId.MACRO: 0.23,
        LayerId.POLICY: 0.10, LayerId.POSITIONING: 0.15,
    },
    (Cycle.EXPANSION, RiskMode.RISK_OFF): {
        LayerId.TECHNICAL: 0.20, LayerId.FUNDAMENTAL: 0.20, LayerId.MACRO: 0.35,
        LayerId.POLICY: 0.10, LayerId.POSITIONING: 0.15,
    },
    (Cycle.SLOWDOWN, RiskMode.RISK_ON): {
        LayerId.TECHNICAL: 0.26, LayerId.FUNDAMENTAL: 0.22, LayerId.MACRO: 0.30,
        LayerId.POLICY: 0.10, LayerId.POSITIONING: 0.12,
    },
    (Cycle.SLOWDOWN, RiskMode.NEUTRAL): {
        LayerId.TECHNICAL: 0.22, LayerId.FUNDAMENTAL: 0.22, LayerId.MACRO: 0.32,
        LayerId.POLICY: 0.12, LayerId.POSITIONING: 0.12,
    },
    (Cycle.SLOWDOWN, RiskMode.RISK_OFF): {
        LayerId.TECHNICAL: 0.15, LayerId.FUNDAMENTAL: 0.18, LayerId.MACRO: 0.40,
        LayerId.POLICY: 0.13, LayerId.POSITIONING: 0.14,
    },
    (Cycle.CONTRACTION, RiskMode.RISK_OFF): {
        LayerId.TECHNICAL: 0.10, LayerId.FUNDAMENTAL: 0.15, LayerId.MACRO: 0.45,
        LayerId.POLICY: 0.15, LayerId.POSITIONING: 0.15,
    },
    (Cycle.CONTRACTION, RiskMode.NEUTRAL): {
        LayerId.TECHNICAL: 0.14, LayerId.FUNDAMENTAL: 0.18, LayerId.MACRO: 0.40,
        LayerId.POLICY: 0.14, LayerId.POSITIONING: 0.14,
    },
    (Cycle.CONTRACTION, RiskMode.RISK_ON): {
        LayerId.TECHNICAL: 0.18, LayerId.FUNDAMENTAL: 0.20, LayerId.MACRO: 0.37,
        LayerId.POLICY: 0.12, LayerId.POSITIONING: 0.13,
    },
    (Cycle.RECOVERY, RiskMode.RISK_ON): {
        LayerId.TECHNICAL: 0.30, LayerId.FUNDAMENTAL: 0.25, LayerId.MACRO: 0.25,
        LayerId.POLICY: 0.08, LayerId.POSITIONING: 0.12,
    },
    (Cycle.RECOVERY, RiskMode.NEUTRAL): {
        LayerId.TECHNICAL: 0.26, LayerId.FUNDAMENTAL: 0.26, LayerId.MACRO: 0.27,
        LayerId.POLICY: 0.09, LayerId.POSITIONING: 0.12,
    },
    (Cycle.RECOVERY, RiskMode.RISK_OFF): {
        LayerId.TECHNICAL: 0.16, LayerId.FUNDAMENTAL: 0.22, LayerId.MACRO: 0.36,
        LayerId.POLICY: 0.11, LayerId.POSITIONING: 0.15,
    },
}

# Regimen desconocido: macro pesada y umbral efectivo mas alto. Si el sistema
# no sabe en que regimen esta, la respuesta correcta es exigir mas, no menos.
FALLBACK_WEIGHTS: dict[LayerId, float] = {
    LayerId.TECHNICAL: 0.18, LayerId.FUNDAMENTAL: 0.20, LayerId.MACRO: 0.38,
    LayerId.POLICY: 0.12, LayerId.POSITIONING: 0.12,
}


@dataclass(frozen=True, slots=True)
class RegimeCall:
    cycle: Cycle
    risk_mode: RiskMode
    confidence: float
    evidence: tuple[str, ...]
    weights: Mapping[LayerId, float]
    threshold_bump: float = 0.0     # puntos extra de exigencia si hay dudas

    @property
    def label(self) -> str:
        return f"{self.cycle.value}/{self.risk_mode.value}"


def weights_for(cycle: Cycle, risk: RiskMode) -> dict[LayerId, float]:
    return dict(WEIGHT_TABLE.get((cycle, risk), FALLBACK_WEIGHTS))


def detect(ctx) -> RegimeCall:
    """
    Clasifica el regimen con datos point-in-time.

    Dos ejes independientes:
      CICLO  -> a que velocidad crece la economia (ISM, empleo, curva)
      RIESGO -> cuanto miedo hay AHORA (VIX, credito, amplitud)

    Son distintos a proposito: en marzo 2020 el ciclo todavia figuraba en
    expansion segun los datos publicados, y el riesgo ya estaba en panico.
    Fusionarlos en un solo numero habria borrado justamente esa diferencia.
    """
    ev: list[str] = []

    # -- Eje 1: ciclo -------------------------------------------------------
    cyc_score = 0.0
    cyc_n = 0

    ism = ctx.macro("ISM_MFG")
    if ism is not None:
        ism_hist = ctx.macro_hist("ISM_MFG", 4)
        trend = (ism - ism_hist[0]) if len(ism_hist) >= 2 else 0.0
        cyc_score += (ism - 50.0) / 5.0 + trend / 3.0
        cyc_n += 1
        ev.append(f"ISM {ism:.1f} ({'expansivo' if ism > 50 else 'contractivo'}), tendencia {trend:+.1f}")

    claims = ctx.macro("CLAIMS")
    if claims is not None:
        ch = ctx.macro_change("CLAIMS", 3)
        if ch is not None:
            cyc_score += -ch / 40_000.0
            cyc_n += 1
            ev.append(f"pedidos de subsidio {ch:+,.0f} en 3 meses")

    t10, t2 = ctx.macro("DGS10"), ctx.macro("DGS2")
    slope = None
    if t10 is not None and t2 is not None:
        slope = t10 - t2
        hist10 = ctx.macro_hist("DGS10", 60)
        hist2 = ctx.macro_hist("DGS2", 60)
        prev_slope = (hist10[-20] - hist2[-20]) if len(hist10) >= 20 and len(hist2) >= 20 else slope
        # La DESinversion avisa mas que la inversion: historicamente la
        # recesion empieza cuando la curva se normaliza, no cuando se invierte.
        if slope < 0:
            cyc_score -= 1.2
            ev.append(f"curva 2-10 invertida en {slope:+.2f}")
        elif prev_slope < 0 <= slope:
            cyc_score -= 2.0
            ev.append(f"curva DESinvirtiendose ({prev_slope:+.2f} -> {slope:+.2f}): senal tardia y seria")
        else:
            cyc_score += min(1.0, slope)
            ev.append(f"curva 2-10 en {slope:+.2f}")
        cyc_n += 1

    hy = ctx.macro("HY_OAS")
    hy_hist = ctx.macro_hist("HY_OAS", 60)
    hy_widening = None
    if hy is not None and len(hy_hist) >= 20:
        hy_widening = hy - hy_hist[-20]
        cyc_score -= hy_widening / 60.0
        cyc_n += 1
        ev.append(f"high yield {hy:.0f}bp ({hy_widening:+.0f}bp en 20 ruedas)")

    if cyc_n == 0:
        cycle, cyc_conf = Cycle.UNKNOWN, 0.0
    else:
        m = cyc_score / cyc_n
        prev_growth = _prior_growth(ctx)
        if m > 0.7:
            cycle = Cycle.EXPANSION if prev_growth >= 0 else Cycle.RECOVERY
        elif m > -0.2:
            cycle = Cycle.SLOWDOWN
        elif m > -1.2:
            cycle = Cycle.SLOWDOWN if prev_growth > 0 else Cycle.CONTRACTION
        else:
            cycle = Cycle.CONTRACTION
        cyc_conf = min(1.0, cyc_n / 4.0)

    # -- Eje 2: modo de riesgo ---------------------------------------------
    risk_score = 0.0
    risk_n = 0

    vix = ctx.macro("VIX")
    if vix is not None:
        vix_hist = ctx.macro_hist("VIX", 250)
        pr = percentile_rank(vix, vix_hist) if len(vix_hist) >= 60 else None
        if pr is not None:
            risk_score += (0.5 - pr) * 4.0
            ev.append(f"VIX {vix:.1f} = percentil {pr:.0%} de su propio anio")
        else:
            risk_score += (20.0 - vix) / 6.0
            ev.append(f"VIX {vix:.1f}")
        risk_n += 1

    if hy_widening is not None:
        risk_score += -hy_widening / 45.0
        risk_n += 1

    br = _breadth_score(ctx)
    if br is not None:
        risk_score += br
        risk_n += 1
        ev.append(f"amplitud: contribucion {br:+.2f}")

    if risk_n == 0:
        risk_mode, risk_conf = RiskMode.NEUTRAL, 0.0
    else:
        r = risk_score / risk_n
        risk_mode = RiskMode.RISK_ON if r > 0.55 else (RiskMode.RISK_OFF if r < -0.55 else RiskMode.NEUTRAL)
        risk_conf = min(1.0, risk_n / 3.0)

    conf = (cyc_conf + risk_conf) / 2.0
    bump = 0.0 if conf >= 0.7 else (5.0 if conf >= 0.4 else 12.0)
    if cycle is Cycle.UNKNOWN:
        bump = max(bump, 12.0)
        ev.append("regimen NO identificado: se exige mas score, no menos")

    return RegimeCall(
        cycle=cycle,
        risk_mode=risk_mode,
        confidence=conf,
        evidence=tuple(ev),
        weights=weights_for(cycle, risk_mode),
        threshold_bump=bump,
    )


def _prior_growth(ctx) -> float:
    """Direccion del crecimiento hace ~6 meses: distingue recuperacion de expansion."""
    h = ctx.macro_hist("ISM_MFG", 8)
    if len(h) < 4:
        return 0.0
    return h[-4] - 50.0


def _breadth_score(ctx) -> float | None:
    """
    Amplitud sobre los pares disponibles: cuantos estan sobre su media de 200.
    Un indice que sube con amplitud cayendo es un indice que sube con cuatro
    acciones, y eso termina siempre igual.
    """
    from .layers.indicators import breadth
    closes = {s: v.closes(260) for s, v in ctx.peers.items()}
    closes[ctx.symbol] = ctx.closes(260)
    b = breadth({k: v for k, v in closes.items() if len(v) >= 201})
    if b is None:
        return None
    return (b.pct_above_200 - 0.5) * 3.0 + b.advance_decline * 0.5
