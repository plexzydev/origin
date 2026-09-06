"""
Indicadores. Funciones puras: entran secuencias, sale un numero.

Tres reglas de diseno que evitan bugs sutiles:

  1. NINGUNA funcion accede a datos por su cuenta. Reciben la ventana que la
     SignalView ya recorto en `as_of`. Es imposible que miren el futuro.
  2. Devuelven None cuando no hay historia suficiente. Nunca un valor por
     defecto disfrazado de calculo: un RSI de 50 "porque no habia datos" es
     una mentira que despues alguien opera.
  3. Sin estado. Dos llamadas con la misma entrada dan lo mismo siempre, lo
     que hace reproducible el backtest bit a bit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Sequence

from ..contracts import Bar


# ---------------------------------------------------------------------------
# Medias y momentum
# ---------------------------------------------------------------------------

def sma(values: Sequence[float], n: int) -> float | None:
    if len(values) < n or n <= 0:
        return None
    return fmean(values[-n:])


def ema(values: Sequence[float], n: int) -> float | None:
    """EMA sembrada con SMA de las primeras n barras (convencion estandar)."""
    if len(values) < n or n <= 0:
        return None
    k = 2.0 / (n + 1.0)
    e = fmean(values[:n])
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def rsi(closes: Sequence[float], n: int = 14) -> float | None:
    """RSI de Wilder (suavizado exponencial con alpha=1/n, no SMA)."""
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[:n], closes[1:n + 1]):
        d = b - a
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / n, losses / n
    for a, b in zip(closes[n:-1], closes[n + 1:]):
        d = b - a
        avg_g = (avg_g * (n - 1) + max(d, 0.0)) / n
        avg_l = (avg_l * (n - 1) + max(-d, 0.0)) / n
    if avg_l == 0:
        return 100.0 if avg_g > 0 else 50.0
    rs = avg_g / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


@dataclass(frozen=True, slots=True)
class Macd:
    macd: float
    signal: float
    hist: float


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, sig: int = 9) -> Macd | None:
    if len(closes) < slow + sig:
        return None
    # Serie de MACD para poder suavizar la senal correctamente.
    line: list[float] = []
    for i in range(slow, len(closes) + 1):
        f, s = ema(closes[:i], fast), ema(closes[:i], slow)
        if f is None or s is None:
            return None
        line.append(f - s)
    if len(line) < sig:
        return None
    sg = ema(line, sig)
    if sg is None:
        return None
    return Macd(line[-1], sg, line[-1] - sg)


# ---------------------------------------------------------------------------
# Volatilidad
# ---------------------------------------------------------------------------

def true_range(prev_close: float, bar: Bar) -> float:
    return max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))


def atr(bars: Sequence[Bar], n: int = 14) -> float | None:
    """ATR de Wilder. Es la unidad de medida del riesgo en todo el sistema."""
    if len(bars) < n + 1:
        return None
    trs = [true_range(p.close, c) for p, c in zip(bars, bars[1:])]
    a = fmean(trs[:n])
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) / n
    return a


@dataclass(frozen=True, slots=True)
class Bollinger:
    upper: float
    mid: float
    lower: float
    width_pct: float
    percent_b: float


def bollinger(closes: Sequence[float], n: int = 20, k: float = 2.0) -> Bollinger | None:
    if len(closes) < n:
        return None
    w = closes[-n:]
    m, sd = fmean(w), pstdev(w)
    up, lo = m + k * sd, m - k * sd
    pb = 0.5 if up == lo else (closes[-1] - lo) / (up - lo)
    return Bollinger(up, m, lo, (up - lo) / m if m else 0.0, pb)


def realized_vol(closes: Sequence[float], n: int = 20, annualize: int = 252) -> float | None:
    if len(closes) < n + 1:
        return None
    rets = [math.log(b / a) for a, b in zip(closes[-n - 1:-1], closes[-n:]) if a > 0]
    if len(rets) < 2:
        return None
    return pstdev(rets) * math.sqrt(annualize)


def vol_regime(closes: Sequence[float], short: int = 20, long: int = 100) -> float | None:
    """
    Razon vol corta / vol larga. >1.3 = expansion de volatilidad,
    <0.8 = compresion (suele preceder rupturas).
    """
    vs, vl = realized_vol(closes, short), realized_vol(closes, long)
    if vs is None or vl is None or vl <= 0:
        return None
    return vs / vl


# ---------------------------------------------------------------------------
# Tendencia
# ---------------------------------------------------------------------------

def adx(bars: Sequence[Bar], n: int = 14) -> float | None:
    """
    ADX de Wilder. Mide FUERZA de tendencia, no direccion.
    <20 = rango (las rupturas fallan), >25 = tendencia establecida.
    """
    if len(bars) < 2 * n + 1:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for p, c in zip(bars, bars[1:]):
        up, dn = c.high - p.high, p.low - c.low
        plus_dm.append(up if up > dn and up > 0 else 0.0)
        minus_dm.append(dn if dn > up and dn > 0 else 0.0)
        trs.append(true_range(p.close, c))

    def wilder(xs: list[float]) -> list[float]:
        out = [sum(xs[:n])]
        for x in xs[n:]:
            out.append(out[-1] - out[-1] / n + x)
        return out

    str_, sp, sm = wilder(trs), wilder(plus_dm), wilder(minus_dm)
    dxs = []
    for t, p, m in zip(str_, sp, sm):
        if t <= 0:
            continue
        pdi, mdi = 100 * p / t, 100 * m / t
        denom = pdi + mdi
        dxs.append(100 * abs(pdi - mdi) / denom if denom else 0.0)
    if len(dxs) < n:
        return None
    a = fmean(dxs[:n])
    for d in dxs[n:]:
        a = (a * (n - 1) + d) / n
    return a


def directional_bias(closes: Sequence[float], fast: int = 50, slow: int = 200) -> int | None:
    """+1 alcista, -1 bajista, 0 sin definir. Sesgo estructural simple."""
    f, s = sma(closes, fast), sma(closes, slow)
    if f is None or s is None:
        return None
    if f > s * 1.005:
        return 1
    if f < s * 0.995:
        return -1
    return 0


# ---------------------------------------------------------------------------
# Estructura de mercado
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Pivot:
    index: int
    price: float
    is_high: bool


def pivots(bars: Sequence[Bar], left: int = 3, right: int = 3) -> tuple[Pivot, ...]:
    """
    Pivotes confirmados. Un pivote necesita `right` barras POSTERIORES para
    confirmarse: se detecta con retraso, y asi debe ser. Detectar un pivote el
    mismo dia que ocurre es look-ahead disfrazado de analisis tecnico.
    """
    out: list[Pivot] = []
    for i in range(left, len(bars) - right):
        w = bars[i - left:i + right + 1]
        b = bars[i]
        if b.high == max(x.high for x in w) and all(b.high >= x.high for x in w):
            out.append(Pivot(i, b.high, True))
        if b.low == min(x.low for x in w) and all(b.low <= x.low for x in w):
            out.append(Pivot(i, b.low, False))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Structure:
    trend: int                  # +1 HH/HL, -1 LH/LL, 0 mixto
    last_high: float | None
    last_low: float | None
    bos: bool                   # ruptura de estructura en la ultima barra
    bos_direction: int
    description: str


def market_structure(bars: Sequence[Bar], left: int = 3, right: int = 3) -> Structure | None:
    """Maximos/minimos crecientes o decrecientes + ruptura de estructura (BOS)."""
    if len(bars) < 4 * (left + right):
        return None
    pv = pivots(bars, left, right)
    highs = [p for p in pv if p.is_high]
    lows = [p for p in pv if not p.is_high]
    if len(highs) < 2 or len(lows) < 2:
        return None

    hh = highs[-1].price > highs[-2].price
    hl = lows[-1].price > lows[-2].price
    lh = highs[-1].price < highs[-2].price
    ll = lows[-1].price < lows[-2].price

    if hh and hl:
        trend, desc = 1, "maximos y minimos crecientes (estructura alcista)"
    elif lh and ll:
        trend, desc = -1, "maximos y minimos decrecientes (estructura bajista)"
    else:
        trend, desc = 0, "estructura mixta: sin sesgo estructural claro"

    last = bars[-1]
    bos, bdir = False, 0
    if last.close > highs[-1].price:
        bos, bdir = True, 1
        desc += f"; RUPTURA alcista del maximo {highs[-1].price:.2f}"
    elif last.close < lows[-1].price:
        bos, bdir = True, -1
        desc += f"; RUPTURA bajista del minimo {lows[-1].price:.2f}"

    return Structure(trend, highs[-1].price, lows[-1].price, bos, bdir, desc)


@dataclass(frozen=True, slots=True)
class OrderBlock:
    low: float
    high: float
    direction: int          # +1 alcista, -1 bajista
    bars_ago: int


def order_blocks(bars: Sequence[Bar], impulse_atr: float = 1.5, lookback: int = 60) -> tuple[OrderBlock, ...]:
    """
    Order blocks: ultima vela contraria antes de un movimiento impulsivo.

    Definicion operativa (no mistica): la vela bajista previa a un impulso
    alcista de >= `impulse_atr` ATR. Es donde quedo demanda sin ejecutar.
    """
    a = atr(bars, 14)
    if a is None or a <= 0 or len(bars) < 20:
        return ()
    out: list[OrderBlock] = []
    window = bars[-lookback:]
    off = len(bars) - len(window)
    for i in range(1, len(window) - 1):
        prev, cur = window[i - 1], window[i]
        move = cur.close - cur.open
        if move > impulse_atr * a and prev.close < prev.open:
            out.append(OrderBlock(prev.low, prev.high, 1, len(bars) - (off + i - 1) - 1))
        elif -move > impulse_atr * a and prev.close > prev.open:
            out.append(OrderBlock(prev.low, prev.high, -1, len(bars) - (off + i - 1) - 1))
    return tuple(out[-5:])


def liquidity_zones(bars: Sequence[Bar], left: int = 3, right: int = 3) -> tuple[float, ...]:
    """
    Zonas de liquidez = pivotes donde se acumulan stops. Igual-maximos e
    igual-minimos son los imanes clasicos.
    """
    pv = pivots(bars, left, right)
    prices = sorted(p.price for p in pv)
    zones: list[float] = []
    i = 0
    while i < len(prices):
        cluster = [prices[i]]
        j = i + 1
        while j < len(prices) and abs(prices[j] - cluster[0]) / cluster[0] < 0.004:
            cluster.append(prices[j])
            j += 1
        if len(cluster) >= 2:
            zones.append(fmean(cluster))
        i = j
    return tuple(zones)


# ---------------------------------------------------------------------------
# Volumen
# ---------------------------------------------------------------------------

def vwap(bars: Sequence[Bar], n: int = 20) -> float | None:
    if len(bars) < n:
        return None
    w = bars[-n:]
    tv = sum(b.volume for b in w)
    if tv <= 0:
        return None
    return sum(b.typical * b.volume for b in w) / tv


def volume_ratio(bars: Sequence[Bar], n: int = 20) -> float | None:
    """Volumen de la ultima barra vs promedio. <1 en una ruptura = sospechosa."""
    if len(bars) < n + 1:
        return None
    avg = fmean([b.volume for b in bars[-n - 1:-1]])
    return None if avg <= 0 else bars[-1].volume / avg


def dollar_volume(bars: Sequence[Bar], n: int = 20) -> float | None:
    if len(bars) < n:
        return None
    return fmean([b.close * b.volume for b in bars[-n:]])


@dataclass(frozen=True, slots=True)
class VolumeProfile:
    poc: float                  # precio con mas volumen negociado
    value_area_low: float
    value_area_high: float
    price_in_value_area: bool


def volume_profile(bars: Sequence[Bar], n: int = 60, bins: int = 24) -> VolumeProfile | None:
    """
    Perfil de volumen simplificado: reparte el volumen de cada barra en el
    rango que recorrio. El POC marca el precio de mayor aceptacion.
    """
    if len(bars) < n:
        return None
    w = bars[-n:]
    lo, hi = min(b.low for b in w), max(b.high for b in w)
    if hi <= lo:
        return None
    step = (hi - lo) / bins
    buckets = [0.0] * bins
    for b in w:
        i0 = min(bins - 1, max(0, int((b.low - lo) / step)))
        i1 = min(bins - 1, max(0, int((b.high - lo) / step)))
        span = i1 - i0 + 1
        for i in range(i0, i1 + 1):
            buckets[i] += b.volume / span
    poc_i = max(range(bins), key=lambda i: buckets[i])
    total = sum(buckets)
    # Area de valor: 70% del volumen expandiendo desde el POC.
    acc, lo_i, hi_i = buckets[poc_i], poc_i, poc_i
    while acc < 0.7 * total and (lo_i > 0 or hi_i < bins - 1):
        down = buckets[lo_i - 1] if lo_i > 0 else -1.0
        up = buckets[hi_i + 1] if hi_i < bins - 1 else -1.0
        if up >= down:
            hi_i += 1
            acc += up
        else:
            lo_i -= 1
            acc += down
    val, vah = lo + lo_i * step, lo + (hi_i + 1) * step
    px = w[-1].close
    return VolumeProfile(lo + (poc_i + 0.5) * step, val, vah, val <= px <= vah)


# ---------------------------------------------------------------------------
# Amplitud de mercado (se calcula sobre el universo, no sobre un simbolo)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Breadth:
    pct_above_200: float
    advance_decline: float      # (avances - retrocesos) / total
    new_highs_minus_lows: float
    symbols: int


def breadth(
    universe_closes: dict[str, Sequence[float]],
    universe_highs: dict[str, Sequence[float]] | None = None,
    universe_lows: dict[str, Sequence[float]] | None = None,
    hl_window: int = 252,
) -> Breadth | None:
    """
    Amplitud: cuantas acciones acompanan al indice.

    Es de los pocos indicadores tecnicos con valor predictivo documentado:
    un indice en maximos con amplitud cayendo significa que suben cuatro
    empresas y el resto ya dio vuelta.
    """
    above = adv = dec = nh = nl = 0
    n = 0
    for sym, closes in universe_closes.items():
        if len(closes) < 201:
            continue
        n += 1
        m200 = sma(closes, 200)
        if m200 is not None and closes[-1] > m200:
            above += 1
        if closes[-1] > closes[-2]:
            adv += 1
        elif closes[-1] < closes[-2]:
            dec += 1
        hs = (universe_highs or {}).get(sym)
        ls = (universe_lows or {}).get(sym)
        if hs and ls and len(hs) >= hl_window:
            if hs[-1] >= max(hs[-hl_window:]):
                nh += 1
            if ls[-1] <= min(ls[-hl_window:]):
                nl += 1
    if n == 0:
        return None
    tot = max(1, adv + dec)
    return Breadth(above / n, (adv - dec) / tot, (nh - nl) / n, n)
