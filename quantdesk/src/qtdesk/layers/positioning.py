"""
CAPA 5 - POSICIONAMIENTO Y SENTIMIENTO.

Se usa como CONTRARIO EN EXTREMOS y de ninguna otra forma.

Esto es una restriccion, no una preferencia. El sentimiento en niveles
normales no tiene poder predictivo: que el 42% de la AAII esté alcista no
dice absolutamente nada. Que esté el 62%, en el percentil 95 de dos anios,
sí dice algo. Por eso cada sub-senal devuelve ~0 dentro de la banda central
y solo despierta pasados los percentiles configurados.

La otra mitad de la regla, igual de importante: el sentimiento extremo marca
TECHOS y PISOS, no timing. Un mercado puede quedarse en euforia durante
meses. Por eso esta capa nunca pesa mas de ~0.15 en la tabla de regimenes.
"""
from __future__ import annotations

from statistics import fmean

from ..contracts import LayerId, LayerScore
from ..stats import clamp, percentile_rank
from .base import Layer, MarketContext, blend

UPPER, LOWER = 0.90, 0.10          # percentiles que despiertan la senal
LOOKBACK = 250                     # ~2 anios de datos semanales o 1 de diarios


class PositioningLayer(Layer):
    layer_id = LayerId.POSITIONING

    def evaluate(self, ctx: MarketContext) -> LayerScore:
        if ctx.pit is None:
            return self.abstain("sin store point-in-time cargado")
        notes: list[str] = []

        def contrarian(series_id: str, label: str, invert: bool) -> float | None:
            """
            `invert=True` cuando un valor ALTO es señal alcista (miedo).
            `invert=False` cuando un valor ALTO es señal bajista (codicia).
            """
            v = ctx.macro(series_id)
            h = ctx.macro_hist(series_id, LOOKBACK)
            if v is None or len(h) < 60:
                return None
            pr = percentile_rank(v, h)
            if pr is None:
                return None
            if pr >= UPPER:
                mag = (pr - UPPER) / (1.0 - UPPER)
                s = mag * 85.0 * (1.0 if invert else -1.0)
                notes.append(f"{label} en percentil {pr:.0%} (EXTREMO) -> contrario {s:+.0f}")
                return s
            if pr <= LOWER:
                mag = (LOWER - pr) / LOWER
                s = mag * 85.0 * (-1.0 if invert else 1.0)
                notes.append(f"{label} en percentil {pr:.0%} (EXTREMO) -> contrario {s:+.0f}")
                return s
            notes.append(f"{label} percentil {pr:.0%}: dentro de la banda normal, sin senal")
            return 0.0

        # Grandes especuladores muy largos = poca polvora seca = techo.
        cot = contrarian("COT_SPEC", "COT grandes especuladores", invert=False)
        # Put/call alto = miedo = piso.
        pc = contrarian("PUT_CALL", "ratio put/call", invert=True)
        # AAII muy alcista = techo.
        aaii = contrarian("AAII_BULL", "encuesta AAII alcistas", invert=False)
        # Interes corto alto = combustible para un squeeze = alcista en extremos.
        si = contrarian("SHORT_INTEREST", "interes corto", invert=True)

        # Curva del VIX: en backwardation el miedo ya explotó (CAPA 0 veta los
        # extremos; lo que queda aca es la zona intermedia).
        vix_score = None
        vix, vix3m = ctx.macro("VIX"), ctx.macro("VIX3M")
        if vix is not None and vix3m is not None:
            spread = vix - vix3m
            vix_score = clamp(spread * 22.0)
            notes.append(
                f"curva VIX {spread:+.1f} ({'backwardation: miedo ya realizado' if spread > 0 else 'contango normal'})"
            )

        score, coverage, _ = blend([
            ("cot", cot, 1.3),
            ("put_call", pc, 1.1),
            ("aaii", aaii, 0.9),
            ("interes_corto", si, 0.9),
            ("curva_vix", vix_score, 1.0),
        ])

        extremes = sum(1 for x in (cot, pc, aaii, si) if x is not None and abs(x) > 1e-9)
        warns = []
        if extremes == 0:
            warns.append("SIN_EXTREMOS")

        return self.emit(
            score,
            # Sin extremos la capa vale poco a proposito: su valor esta en las colas.
            coverage * (1.0 if extremes else 0.35),
            (f"{extremes} indicador(es) en zona extrema. " if extremes
             else "ningun indicador en zona extrema: el sentimiento en niveles normales "
                  "no tiene poder predictivo y la capa lo refleja bajando su confianza. ")
            + " | ".join(notes),
            {"extremos": float(extremes), "curva_vix": vix_score or 0.0},
            warns,
        )
