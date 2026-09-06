"""
Detectores de degradacion.

Los cinco del mandato, cada uno con su umbral y su lectura:

  1. cambia parametros muy seguido       -> persigue ruido
  2. la conviccion no correlaciona con
     el resultado                        -> no sabe lo que no sabe
  3. las metricas en vivo se despegan
     del backtest                        -> la estrategia murio o cambio el
                                            regimen. APAGAR, no reajustar.
  4. las reglas y excepciones crecen
     sin parar                           -> sobreajuste acumulado
  5. suben los trades de categoria 3     -> gana por motivos que no entiende

El cuarto es el mas dificil de ver desde adentro y el que mas seguido mata
sistemas: cada excepcion se justifico sola en su momento.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import fmean

from ..contracts import Severity
from ..stats import correlation


@dataclass(frozen=True, slots=True)
class Alarm:
    code: str
    severity: Severity
    message: str
    action: str


def detect_parameter_churn(version_ledger, now: datetime, *, window_days: int = 90,
                           max_changes: int = 3) -> Alarm | None:
    recent = [v for v in version_ledger.versions
              if not v.reverted and (now - v.created_at).days <= window_days]
    if len(recent) > max_changes:
        return Alarm(
            "PERSIGUE_RUIDO", Severity.HIGH,
            f"{len(recent)} cambios de parametros en {window_days} dias (maximo {max_changes}). "
            "Cada cambio se justifico solo, pero el conjunto es la firma de estar ajustando "
            "a la ultima racha en vez de al mercado.",
            "congelar parametros por un trimestre completo y medir sin tocar nada",
        )
    return None


def detect_conviction_blindness(reviews, *, min_n: int = 30,
                                min_corr: float = 0.10) -> Alarm | None:
    """
    La conviccion deberia correlacionar con el resultado. Si no lo hace, el
    sistema no distingue lo que sabe de lo que no sabe -- que es peor que no
    saber, porque dimensiona en base a eso.
    """
    if len(reviews) < min_n:
        return None
    conv = [r.decision_quality_score for r in reviews]
    res = [r.r_multiple for r in reviews]
    c = correlation(conv, res)
    if c is None:
        return None
    if c < min_corr:
        return Alarm(
            "CONVICCION_CIEGA", Severity.HIGH,
            f"correlacion entre calidad de decision y resultado: {c:+.2f} sobre {len(reviews)} "
            f"operaciones (minimo esperado {min_corr:+.2f}). El sistema no sabe lo que no sabe: "
            "sus operaciones de 'alta conviccion' no rinden mejor que las de baja.",
            "dejar de escalar tamano por conviccion hasta que la correlacion sea positiva",
        )
    return None


def detect_live_vs_backtest_drift(live_expectancy: float, backtest_expectancy: float,
                                  n_live: int, *, min_n: int = 30,
                                  max_drift: float = 0.50) -> Alarm | None:
    if n_live < min_n or backtest_expectancy == 0:
        return None
    drift = (live_expectancy - backtest_expectancy) / abs(backtest_expectancy)
    if drift < -max_drift:
        return Alarm(
            "METRICAS_DESPEGADAS", Severity.CRITICAL,
            f"la expectativa en vivo ({live_expectancy:+.3f}R) esta {abs(drift):.0%} por debajo "
            f"del backtest ({backtest_expectancy:+.3f}R) sobre {n_live} operaciones. "
            "O la estrategia murio o cambio el regimen.",
            "APAGAR. No reajustar parametros para tapar la diferencia: eso convierte una "
            "estrategia muerta en una estrategia muerta y sobreajustada.",
        )
    return None


def detect_rule_creep(n_rules: int, n_exceptions: int, baseline_rules: int,
                      *, max_growth: float = 0.50) -> Alarm | None:
    growth = (n_rules - baseline_rules) / max(baseline_rules, 1)
    if growth > max_growth or n_exceptions > baseline_rules * 0.3:
        return Alarm(
            "SOBREAJUSTE_ACUMULADO", Severity.HIGH,
            f"las reglas crecieron {growth:.0%} desde la linea base ({baseline_rules} -> {n_rules}) "
            f"y hay {n_exceptions} excepciones. Cada una se justifico sola; el conjunto es "
            "un modelo memorizando su propia historia.",
            "volver al conjunto de reglas base y re-validar cada agregado por separado "
            "contra datos fuera de muestra",
        )
    return None


def detect_luck_dependence(ledger, *, min_n: int = 20, max_luck: float = 0.30) -> Alarm | None:
    """Casilla 3 de la matriz: ganar con mal proceso. La mas peligrosa."""
    if len(ledger.reviews) < min_n:
        return None
    luck = ledger.luck_ratio()
    if luck > max_luck:
        return Alarm(
            "GANANCIAS_POR_SUERTE", Severity.CRITICAL,
            f"el {luck:.0%} de las ganancias vino de decisiones de mala calidad "
            f"(maximo tolerado {max_luck:.0%}). El sistema esta ganando por motivos que no "
            "entiende, y eso se siente exactamente igual que ganar bien hasta que deja de pasar.",
            "revisar el proceso, no los parametros. Las operaciones de categoria 3 no validan nada.",
        )
    return None


def run_all(*, version_ledger=None, review_ledger=None, now: datetime | None = None,
            live_expectancy: float | None = None, backtest_expectancy: float | None = None,
            n_rules: int = 0, n_exceptions: int = 0, baseline_rules: int = 0) -> list[Alarm]:
    """Corre los cinco detectores. Devuelve solo las alarmas activas."""
    now = now or datetime.now()
    out: list[Alarm] = []
    if version_ledger is not None:
        a = detect_parameter_churn(version_ledger, now)
        if a:
            out.append(a)
    if review_ledger is not None:
        for a in (detect_conviction_blindness(review_ledger.reviews),
                  detect_luck_dependence(review_ledger)):
            if a:
                out.append(a)
    if live_expectancy is not None and backtest_expectancy is not None and review_ledger is not None:
        a = detect_live_vs_backtest_drift(live_expectancy, backtest_expectancy,
                                          len(review_ledger.reviews))
        if a:
            out.append(a)
    if baseline_rules:
        a = detect_rule_creep(n_rules, n_exceptions, baseline_rules)
        if a:
            out.append(a)
    return out
