"""
Informes agregados semanal y mensual.

"Los patrones reales aparecen en el agregado, nunca en el trade suelto."

Este modulo no calcula nada nuevo: junta lo que ya midieron metrics.py,
review.py y degradation.py, y lo ordena para que se pueda leer. El orden es
deliberado: primero las alarmas, despues las perdidas, despues los
desagregados, y el rendimiento al final.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from ..backtest import metrics as met
from . import degradation


def _bucket(trades, key):
    out = defaultdict(list)
    for t in trades:
        out[key(t)].append(t)
    return out


def periodic_report(
    equity_curve, trades, review_ledger, *, period: str = "MENSUAL",
    version_ledger=None, now: datetime | None = None,
    backtest_expectancy: float | None = None,
) -> str:
    now = now or (equity_curve[-1][0] if equity_curve else datetime.now())
    L: list[str] = []
    L.append("=" * 70)
    L.append(f"INFORME {period}  --  hasta {now.date()}")
    L.append("=" * 70)

    # -- 1. Alarmas primero -------------------------------------------------
    live_exp = (sum(t.r_multiple for t in trades) / len(trades)) if trades else None
    alarms = degradation.run_all(
        version_ledger=version_ledger, review_ledger=review_ledger, now=now,
        live_expectancy=live_exp, backtest_expectancy=backtest_expectancy,
    )
    L.append("")
    L.append("ALARMAS DE DEGRADACION")
    if not alarms:
        L.append("  ninguna activa")
    for a in alarms:
        L.append(f"  [{a.severity.value}] {a.code}")
        L.append(f"      {a.message}")
        L.append(f"      accion: {a.action}")

    # -- 2. Matriz de cuatro casillas --------------------------------------
    L.append("")
    L.append("MATRIZ DE DECISION vs RESULTADO")
    counts = review_ledger.quadrant_counts()
    total = sum(counts.values()) or 1
    for k in sorted(counts):
        L.append(f"  {k:34} {counts[k]:>4}  ({counts[k]/total:>5.1%})")
    L.append(f"  ganancias por suerte (casilla 3): {review_ledger.luck_ratio():.1%} de las ganancias")
    L.append(f"  violaciones de proceso por operacion: {review_ledger.process_violation_rate():.2f}")
    L.append(f"  resultados FUERA del arbol de escenarios: {review_ledger.model_gap_rate():.1%} "
             "(huecos en el modelo)")

    # -- 3. Metricas, con las perdidas primero ------------------------------
    if len(equity_curve) >= 2:
        m = met.compute(equity_curve, trades)
        L.append("")
        L.append(met.render(m))

    # -- 4. Desagregados adicionales ----------------------------------------
    if trades:
        L.append("")
        L.append("POR SETUP / SALIDA")
        for k, ts in sorted(_bucket(trades, lambda t: t.exit_reason.split(":")[0][:40]).items()):
            e = sum(t.r_multiple for t in ts) / len(ts)
            L.append(f"  {k:42} n={len(ts):<4} E={e:+.2f}R")
        L.append("")
        L.append("OPERACIONES EN MEDICION vs CON VENTAJA DEMOSTRADA")
        for k, ts in sorted(_bucket(trades, lambda t: "MEDICION" if t.measuring else "NORMAL").items()):
            e = sum(t.r_multiple for t in ts) / len(ts)
            L.append(f"  {k:42} n={len(ts):<4} E={e:+.2f}R")
        forced = [t for t in trades if t.forced_by_quota]
        if forced:
            organic = [t for t in trades if not t.forced_by_quota]
            fe = sum(t.r_multiple for t in forced) / len(forced)
            oe = (sum(t.r_multiple for t in organic) / len(organic)) if organic else 0.0
            L.append("")
            L.append("CUOTA DE FRECUENCIA: forzados vs organicos")
            L.append(f"  forzados por cuota   n={len(forced):<4} E={fe:+.2f}R")
            L.append(f"  organicos            n={len(organic):<4} E={oe:+.2f}R")
            L.append(f"  costo de la cuota: {fe - oe:+.2f}R por operacion forzada")
            if len(forced) >= 30:
                L.append("  muestra suficiente: la comparacion ya es utilizable para decidir "
                         "si conviene apagar quota_mode.")
            else:
                L.append(f"  muestra insuficiente ({len(forced)}/30): todavia no concluye nada.")
    return "\n".join(L)


def weekly(equity_curve, trades, review_ledger, **kw) -> str:
    cutoff = equity_curve[-1][0] - timedelta(days=7) if equity_curve else None
    if cutoff:
        equity_curve = [(t, v) for t, v in equity_curve if t >= cutoff]
        trades = [t for t in trades if t.exit_ts >= cutoff]
    return periodic_report(equity_curve, trades, review_ledger, period="SEMANAL", **kw)


def monthly(equity_curve, trades, review_ledger, **kw) -> str:
    return periodic_report(equity_curve, trades, review_ledger, period="MENSUAL", **kw)
