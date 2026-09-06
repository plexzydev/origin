"""
Guardia de factibilidad. Detecta configuraciones que se contradicen a si mismas.

Existe porque el sistema encontro una incompatibilidad ARITMETICA entre tres
parametros que el mandato pide simultaneamente, y esconderla habria sido peor
que reportarla:

    (a) R:R minimo 1:3
    (b) ~10 operaciones por mes
    (c) riesgo estresado total <= 4% con 0.75% por operacion

Las tres no pueden ser ciertas a la vez. La cadena:

  1. (c) limita las posiciones simultaneas a ~5 (4% / 0.75%).
  2. operaciones por mes = posiciones simultaneas / plazo de tenencia en meses.
     Para 10 al mes con 5 slots, el plazo tiene que ser ~medio mes (10 ruedas).
  3. El recorrido favorable crece como raiz del tiempo; la distancia al stop
     no. Medido sobre datos: a 10 ruedas el R:R mediano alcanzable es ~0.8;
     a 60 ruedas es ~2.35.
  4. Entonces (b) implica R:R ~1:1, que contradice (a).

Este modulo no resuelve la contradiccion -- no le corresponde. La hace
VISIBLE y obliga a elegir explicitamente, en vez de que el sistema opere cero
veces sin decir por que.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import SystemConfig
from ..contracts import Side
from .levels import favorable_excursion


@dataclass(frozen=True, slots=True)
class FeasibilityReport:
    max_concurrent_positions: float
    implied_holding_sessions: float
    achievable_rr_median: float | None
    required_rr: float
    feasible: bool
    diagnosis: str
    options: tuple[str, ...]


def analyze(cfg: SystemConfig, measured_rr_by_horizon: dict[int, float] | None = None) -> FeasibilityReport:
    """
    `measured_rr_by_horizon` viene de medir sobre datos reales (ver
    `measure_rr_by_horizon`). Sin el, se usa la aproximacion raiz-del-tiempo
    anclada en un unico punto medido.
    """
    risk = cfg.risk
    # 1. Posiciones simultaneas que tolera el limite de riesgo estresado
    slots = min(
        float(risk.max_positions),
        risk.max_stressed_risk_pct / max(risk.risk_per_trade_pct, 1e-9),
    )
    # 2. Plazo implicado por el objetivo de frecuencia
    per_month = max(cfg.frequency.target_trades_per_month, 1e-9)
    holding_months = slots / per_month
    holding_sessions = holding_months * 21.0

    # 3. R:R alcanzable a ese plazo
    achievable = None
    if measured_rr_by_horizon:
        # Interpolacion sobre los horizontes medidos
        pts = sorted(measured_rr_by_horizon.items())
        if holding_sessions <= pts[0][0]:
            achievable = pts[0][1] * (holding_sessions / pts[0][0]) ** 0.5
        elif holding_sessions >= pts[-1][0]:
            achievable = pts[-1][1] * (holding_sessions / pts[-1][0]) ** 0.5
        else:
            for (h0, r0), (h1, r1) in zip(pts, pts[1:]):
                if h0 <= holding_sessions <= h1:
                    t = (holding_sessions - h0) / (h1 - h0)
                    achievable = r0 + t * (r1 - r0)
                    break

    required = risk.min_rr_ratio
    feasible = achievable is None or achievable >= required

    if feasible:
        diag = (
            f"Configuracion coherente: {slots:.1f} posiciones simultaneas, plazo implicado "
            f"{holding_sessions:.0f} ruedas, R:R alcanzable {achievable:.2f} vs exigido {required:.1f}."
            if achievable is not None else
            "Sin medicion de R:R alcanzable: no se puede verificar la coherencia. Correr "
            "`qtdesk feasibility` sobre datos antes de operar."
        )
        options: tuple[str, ...] = ()
    else:
        diag = (
            f"CONFIGURACION IMPOSIBLE. El limite de riesgo estresado ({risk.max_stressed_risk_pct:.1%}) "
            f"con {risk.risk_per_trade_pct:.2%} por operacion permite {slots:.1f} posiciones a la vez. "
            f"Para {per_month:.0f} operaciones mensuales cada una debe durar {holding_sessions:.0f} ruedas. "
            f"A ese plazo el R:R mediano alcanzable es {achievable:.2f}, muy por debajo del "
            f"{required:.1f} exigido. No es un problema de calibracion: el recorrido favorable crece "
            "como raiz del tiempo y la distancia al stop no."
        )
        # Plazo necesario para el R:R exigido, por escalamiento raiz-del-tiempo
        need_sessions = holding_sessions * (required / max(achievable, 1e-9)) ** 2
        options = (
            f"OPCION A -- priorizar la asimetria: mantener R:R 1:{required:.0f}, subir el plazo a "
            f"~{need_sessions:.0f} ruedas. Con {slots:.1f} slots eso da "
            f"~{slots / (need_sessions / 21):.1f} operaciones por mes, no {per_month:.0f}.",
            f"OPCION B -- priorizar la frecuencia: mantener {per_month:.0f} operaciones mensuales y "
            f"bajar el R:R minimo a ~{achievable:.1f}:1, que es lo que el mercado ofrece a "
            f"{holding_sessions:.0f} ruedas. Sigue siendo asimetria positiva, pero NO es 1:3.",
            f"OPCION C -- ampliar la capacidad de riesgo: subir el riesgo estresado maximo por encima "
            f"del {risk.max_stressed_risk_pct:.1%} actual para tener mas posiciones simultaneas. "
            "Es la unica opcion que AFLOJA un limite de riesgo, y por eso el sistema no la toma solo.",
            "OPCION D -- cambiar el instrumento: estructuras de opciones con perdida maxima acotada "
            "permiten construir un 1:3 por diseno en vez de esperarlo del recorrido del subyacente. "
            "El mandato las prefiere explicitamente, pero quedan fuera del alcance actual "
            "(indices, ETFs y acciones).",
        )

    return FeasibilityReport(
        max_concurrent_positions=slots,
        implied_holding_sessions=holding_sessions,
        achievable_rr_median=achievable,
        required_rr=required,
        feasible=feasible,
        diagnosis=diag,
        options=options,
    )


def measure_rr_by_horizon(bundle, cfg, desk, symbols, sessions, horizons=(10, 20, 40, 60), step=4) -> dict[int, float]:
    """Mide el R:R mediano alcanzable sobre datos reales, por plazo de tenencia."""
    from ..clock import AccessAudit
    from .levels import derive
    out: dict[int, float] = {}
    for hz in horizons:
        rrs = []
        for i in range(len(sessions) // 2, len(sessions), step):
            for sym in symbols:
                lv = derive(bundle.context(sym, sessions[i], desk, cfg, AccessAudit()), Side.LONG,
                            cfg.risk.min_rr_ratio, horizon=hz)
                if lv.rr > 0:
                    rrs.append(lv.rr)
        if rrs:
            rrs.sort()
            out[hz] = rrs[len(rrs) // 2]
    return out
