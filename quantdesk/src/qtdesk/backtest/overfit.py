"""
Penalizacion explicita por sobreajuste.

Dos herramientas, ambas del mismo lugar (Bailey, Borwein, Lopez de Prado,
Zhu -- "The Probability of Backtest Overfitting"):

  DEFLATED SHARPE RATIO: corrige el Sharpe observado por la cantidad de
  configuraciones probadas. Si probas 100 combinaciones de parametros, la
  MEJOR va a tener buen Sharpe por puro azar. El DSR responde: "cual es la
  probabilidad de que este Sharpe sea real y no el maximo de 100 sorteos".

  MINIMUM BACKTEST LENGTH: cuantos anios de datos hacen falta para que un
  Sharpe observado sea creible dada la cantidad de pruebas.

El mandato pide "penalizacion explicita por cantidad de parametros
optimizados". Esto es esa penalizacion, con nombre y referencia.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inversa de la normal estandar (Acklam), suficiente para este uso."""
    if not 0.0 < p < 1.0:
        raise ValueError("p fuera de (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


@dataclass(frozen=True, slots=True)
class OverfitVerdict:
    observed_sharpe: float
    expected_max_sharpe_by_chance: float
    deflated_sharpe: float
    probability_real: float
    n_trials: int
    n_observations: int
    credible: bool
    verdict: str


def expected_max_sharpe(n_trials: int, sharpe_std: float = 1.0) -> float:
    """
    Sharpe esperado del MEJOR de n intentos, si ninguno tiene ventaja real.

    Aproximacion del maximo de n normales independientes. Es el numero contra
    el que hay que comparar: si probaste 50 configuraciones y la mejor da
    Sharpe 1.2, pero el maximo esperado por azar es 1.15, no encontraste nada.
    """
    if n_trials <= 1:
        return 0.0
    g = 0.5772156649015329          # Euler-Mascheroni
    e = math.e
    return sharpe_std * (
        (1 - g) * _norm_ppf(1 - 1.0 / n_trials)
        + g * _norm_ppf(1 - 1.0 / (n_trials * e))
    )


def deflated_sharpe(
    observed: float, n_trials: int, n_obs: int, *, skew: float = 0.0, kurtosis: float = 3.0
) -> OverfitVerdict:
    """
    Sharpe desinflado y probabilidad de que la ventaja sea real.

    `n_trials` DEBE ser el numero honesto de configuraciones probadas, incluidas
    las que se descartaron mentalmente. Subdeclararlo es la forma mas comun de
    mentirse con esta herramienta.
    """
    exp_max = expected_max_sharpe(n_trials)
    if n_obs <= 1:
        return OverfitVerdict(observed, exp_max, 0.0, 0.0, n_trials, n_obs, False,
                              "observaciones insuficientes")
    # Varianza del estimador de Sharpe con momentos no normales
    var = (1 - skew * observed + (kurtosis - 1) / 4.0 * observed ** 2) / (n_obs - 1)
    sd = math.sqrt(max(var, 1e-12))
    z = (observed - exp_max) / sd
    prob = _norm_cdf(z)
    credible = prob >= 0.95
    if credible:
        verdict = (
            f"Sharpe {observed:.2f} creible: probabilidad {prob:.1%} de que supere lo que "
            f"{n_trials} intentos producirian por azar ({exp_max:.2f})."
        )
    elif observed <= exp_max:
        verdict = (
            f"Sharpe {observed:.2f} POR DEBAJO del maximo esperado por azar con {n_trials} "
            f"intentos ({exp_max:.2f}). No hay evidencia de ventaja: lo que se encontro es ruido."
        )
    else:
        verdict = (
            f"Sharpe {observed:.2f} supera el azar ({exp_max:.2f}) pero solo con {prob:.1%} "
            f"de confianza sobre {n_obs} observaciones. Insuficiente para produccion."
        )
    return OverfitVerdict(observed, exp_max, observed - exp_max, prob, n_trials, n_obs,
                          credible, verdict)


def min_backtest_length_years(n_trials: int, target_sharpe: float = 1.0) -> float:
    """
    Anios minimos de datos para que un Sharpe de `target_sharpe` sea creible
    habiendo probado `n_trials` configuraciones.
    """
    if n_trials <= 1 or target_sharpe <= 0:
        return 0.0
    exp_max = expected_max_sharpe(n_trials)
    if exp_max >= target_sharpe:
        return float("inf")
    return (exp_max / target_sharpe) ** 2 * 2.0


def parameter_penalty(n_params: int, n_trades: int) -> tuple[float, str]:
    """
    Penalizacion simple y brutal: observaciones por parametro.

    Regla de oficio ampliamente aceptada: hacen falta al menos 30 operaciones
    POR PARAMETRO optimizado. Con menos, cualquier resultado es memorizacion.
    """
    if n_params <= 0:
        return 1.0, "sin parametros optimizados: nada que penalizar"
    per_param = n_trades / n_params
    factor = min(1.0, per_param / 30.0)
    if per_param < 10:
        note = (f"{per_param:.1f} operaciones por parametro. Con menos de 10 el backtest "
                "esta memorizando la muestra. Resultado NO utilizable.")
    elif per_param < 30:
        note = (f"{per_param:.1f} operaciones por parametro (minimo recomendado 30). "
                f"Resultados descontados al {factor:.0%}.")
    else:
        note = f"{per_param:.1f} operaciones por parametro: suficiente."
    return factor, note
