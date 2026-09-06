"""
Estadistica minima, sin dependencias. Solo lo que el sistema realmente usa.

Todo devuelve None ante datos insuficientes en vez de un numero inventado.
"""
from __future__ import annotations

import math
from statistics import fmean, pstdev
from typing import Sequence


def pct_change(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(
        (b - a) / a for a, b in zip(values, values[1:]) if a not in (0.0,)
    )


def log_returns(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(math.log(b / a) for a, b in zip(values, values[1:]) if a > 0 and b > 0)


def correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson. None si no hay al menos 20 puntos o si alguna serie es plana."""
    n = min(len(xs), len(ys))
    if n < 20:
        return None
    xs, ys = xs[-n:], ys[-n:]
    mx, my = fmean(xs), fmean(ys)
    sx, sy = pstdev(xs), pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    cov = fmean([(a - mx) * (b - my) for a, b in zip(xs, ys)])
    return max(-1.0, min(1.0, cov / (sx * sy)))


def zscore(value: float, sample: Sequence[float]) -> float | None:
    if len(sample) < 20:
        return None
    sd = pstdev(sample)
    if sd == 0:
        return None
    return (value - fmean(sample)) / sd


def percentile_rank(value: float, sample: Sequence[float]) -> float | None:
    """En que percentil (0-1) cae `value` dentro de `sample`."""
    if len(sample) < 20:
        return None
    below = sum(1 for s in sample if s < value)
    ties = sum(1 for s in sample if s == value)
    return (below + 0.5 * ties) / len(sample)


def clamp(x: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def squash(z: float, scale: float = 2.0) -> float:
    """
    Mapea un z-score a [-100, 100] con tanh. Saturante a proposito: un dato
    a 6 sigmas no vale el triple que uno a 2 sigmas, casi siempre significa
    que el dato esta mal.
    """
    return 100.0 * math.tanh(z / scale)


def t_statistic(sample: Sequence[float], mu0: float = 0.0) -> tuple[float, int] | None:
    """t de una muestra. Devuelve (t, grados de libertad)."""
    n = len(sample)
    if n < 3:
        return None
    m = fmean(sample)
    sd = pstdev(sample) * math.sqrt(n / (n - 1))   # desvio muestral
    if sd == 0:
        return None
    return (m - mu0) / (sd / math.sqrt(n)), n - 1


def t_pvalue_two_sided(t: float, df: int) -> float:
    """
    p-valor bilateral de la t de Student via funcion beta incompleta.
    Precision suficiente para decidir si un cambio es significativo o ruido.
    """
    x = df / (df + t * t)
    return _betainc(df / 2.0, 0.5, x)


def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
    # Fraccion continua de Lentz
    f, c, d = 1.0, 1.0, 0.0
    for i in range(0, 200):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
        else:
            num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        f *= c * d
        if abs(1.0 - c * d) < 1e-10:
            break
    val = front * (f - 1.0)
    return min(1.0, max(0.0, val if x < (a + 1) / (a + b + 2) else 1.0 - val))


def bootstrap_ci(
    sample: Sequence[float], statistic=fmean, n_boot: int = 2000, alpha: float = 0.05, seed: int = 12345
) -> tuple[float, float] | None:
    """
    Intervalo de confianza por bootstrap percentil.

    Se usa en CAPA 6: ningun peso se toca sin reportar intervalo o p-valor.
    Determinista por `seed` para que las revisiones sean reproducibles.
    """
    import random
    n = len(sample)
    if n < 10:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        stats.append(statistic([sample[rng.randrange(n)] for _ in range(n)]))
    stats.sort()
    lo = stats[int(alpha / 2 * n_boot)]
    hi = stats[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return lo, hi


def max_drawdown(equity: Sequence[float]) -> tuple[float, int, int]:
    """Devuelve (drawdown maximo, indice de pico, indice de valle)."""
    if not equity:
        return 0.0, 0, 0
    peak, peak_i = equity[0], 0
    worst, wi, wj = 0.0, 0, 0
    for i, v in enumerate(equity):
        if v > peak:
            peak, peak_i = v, i
        dd = 0.0 if peak <= 0 else (peak - v) / peak
        if dd > worst:
            worst, wi, wj = dd, peak_i, i
    return worst, wi, wj
