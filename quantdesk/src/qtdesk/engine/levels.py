"""
Derivacion de niveles: entrada, stop y objetivo.

Aca hay una trampa que rompe la mitad de los sistemas que dicen usar 1:3, y
este modulo la evita de forma explicita:

    Si el objetivo se calcula como "entrada + 3 x distancia al stop", entonces
    el filtro de R:R >= 3 NO FILTRA NADA. Siempre da exactamente 3. Es una
    tautologia con aspecto de gestion de riesgo.

Por eso el objetivo se deriva de la ESTRUCTURA DEL PRECIO -- la resistencia
siguiente, o la proyeccion del rango de consolidacion -- de forma totalmente
independiente del stop. Recien despues se calcula el ratio, y si no llega a 3,
el trade se descarta. Eso hace que el filtro rechace de verdad.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, median

from ..contracts import Side
from ..layers import indicators as ind


def favorable_excursion(bars, side: Side, horizon: int, pct: float = 0.50) -> float | None:
    """
    Recorrido favorable TIPICO durante el plazo de tenencia, medido en la
    historia reciente del propio papel.

    Esta es la forma honesta de responder "cual es un objetivo razonable":
    no la resistencia mas cercana (que es el objetivo mas pesimista posible y
    hace que ningun trade llegue a 1:3), ni entrada+3R (que es una tautologia).
    Es cuanto se movio a favor este papel, en ventanas de la misma duracion que
    el trade planeado, en el pasado observable.

    Dos anclajes deliberados, para que no sean perillas ajustables:
      - `horizon` = el plazo real del time stop del plan. No un numero elegido.
      - `pct` = 0.50 (la MEDIANA). Usar el percentil 80 seria elegir el
        escenario optimista para que el ratio cierre. La mediana dice: "en la
        mitad de los casos el papel se movio al menos esto".

    PIT-safe: solo usa ventanas COMPLETAS y pasadas. La ultima ventana que
    todavia no cerro no se cuenta.
    """
    if len(bars) < horizon * 3:
        return None
    moves: list[float] = []
    for i in range(len(bars) - horizon):
        ref = bars[i].close
        window = bars[i + 1:i + 1 + horizon]
        if not window or ref <= 0:
            continue
        if side is Side.LONG:
            moves.append(max(b.high for b in window) - ref)
        else:
            moves.append(ref - min(b.low for b in window))
    moves = [m for m in moves if m > 0]
    if len(moves) < 20:
        return None
    moves.sort()
    return moves[min(len(moves) - 1, int(pct * len(moves)))]


@dataclass(frozen=True, slots=True)
class Levels:
    entry: float
    stop: float
    target: float
    atr: float
    rr: float
    stop_basis: str
    target_basis: str
    viable: bool
    reason: str


def derive(ctx, side: Side, min_rr: float, horizon: int = 20) -> Levels:
    bars = ctx.bars(260)
    if len(bars) < 90:
        return Levels(0, 0, 0, 0, 0, "", "", False, "historia insuficiente para derivar niveles")
    atr = ind.atr(bars, 14)
    if atr is None or atr <= 0:
        return Levels(0, 0, 0, 0, 0, "", "", False, "ATR no calculable")

    entry = bars[-1].close
    pv = ind.pivots(bars, 3, 3)
    highs = [p.price for p in pv if p.is_high]
    lows = [p.price for p in pv if not p.is_high]

    if side is Side.LONG:
        # -- Stop: bajo el ultimo minimo estructural, con colchon de ATR ----
        swing = max([l for l in lows if l < entry], default=None)
        floor10 = min(b.low for b in bars[-10:])
        base = min(swing, floor10) if swing is not None else floor10
        stop = min(base - 0.25 * atr, entry - 1.2 * atr)
        stop_basis = (
            f"minimo estructural {base:.2f} menos colchon 0.25 ATR"
            if swing is not None else f"minimo de 10 ruedas {floor10:.2f} menos colchon"
        )
        # -- Objetivo: INDEPENDIENTE del stop -------------------------------
        exc = favorable_excursion(bars, side, horizon)
        if exc is None:
            return Levels(entry, stop, 0, atr, 0, stop_basis, "", False,
                          "sin historia suficiente para estimar el recorrido favorable tipico")
        target = entry + exc
        target_basis = (
            f"recorrido favorable MEDIANO en ventanas de {horizon} ruedas: {exc:.2f} "
            f"({exc/atr:.1f} ATR)"
        )
        res = min([h for h in highs if h > entry], default=None)
        if res is not None and res < target:
            target_basis += f"; ATENCION: hay resistencia estructural en {res:.2f}, antes del objetivo"
    else:
        swing = min([h for h in highs if h > entry], default=None)
        ceil10 = max(b.high for b in bars[-10:])
        base = max(swing, ceil10) if swing is not None else ceil10
        stop = max(base + 0.25 * atr, entry + 1.2 * atr)
        stop_basis = (
            f"maximo estructural {base:.2f} mas colchon 0.25 ATR"
            if swing is not None else f"maximo de 10 ruedas {ceil10:.2f} mas colchon"
        )
        exc = favorable_excursion(bars, side, horizon)
        if exc is None:
            return Levels(entry, stop, 0, atr, 0, stop_basis, "", False,
                          "sin historia suficiente para estimar el recorrido favorable tipico")
        target = entry - exc
        target_basis = (
            f"recorrido favorable MEDIANO en ventanas de {horizon} ruedas: {exc:.2f} "
            f"({exc/atr:.1f} ATR)"
        )
        sup = max([l for l in lows if l < entry], default=None)
        if sup is not None and sup > target:
            target_basis += f"; ATENCION: hay soporte estructural en {sup:.2f}, antes del objetivo"

    risk = abs(entry - stop)
    if risk <= 0:
        return Levels(entry, stop, target, atr, 0, stop_basis, target_basis, False, "distancia al stop nula")
    reward = (target - entry) * side.sign
    rr = reward / risk

    if reward <= 0:
        return Levels(entry, stop, target, atr, rr, stop_basis, target_basis, False,
                      f"el objetivo estructural ({target:.2f}) esta del lado equivocado de la entrada")
    if rr < min_rr:
        return Levels(entry, stop, target, atr, rr, stop_basis, target_basis, False,
                      f"el objetivo razonable esta a {rr:.2f}R y el minimo es {min_rr:.1f}R. "
                      "No se acerca el stop ni se aleja el objetivo para que el numero cierre: se descarta.")
    return Levels(entry, stop, target, atr, rr, stop_basis, target_basis, True,
                  f"stop por {stop_basis}; objetivo por {target_basis}; R:R {rr:.2f}")
