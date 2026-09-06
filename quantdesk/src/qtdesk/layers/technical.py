"""
CAPA 1 - PRICE ACTION / TECNICO.

Seis sub-senales con peso propio. Ninguna decide sola.

Regla dura de la capa (del mandato): el DIARIO define el sesgo y el timeframe
inferior define la entrada. Si no coinciden, NO HAY TRADE. Eso no se resuelve
promediando: se emite `MTF_CONFLICT` y el motor de decision lo trata como
bloqueante. Una capa que devuelve +40 cuando los timeframes se contradicen
esta escondiendo el problema detras de un numero.
"""
from __future__ import annotations

from ..contracts import LayerId, LayerScore
from ..stats import clamp
from . import indicators as ind
from .base import Layer, MarketContext, blend

MTF_CONFLICT = "TIMEFRAMES_DISCORDANTES"
NO_STRUCTURE = "SIN_ESTRUCTURA_DEFINIDA"
AGAINST_BIAS = "CONTRA_SESGO_DIARIO"


class TechnicalLayer(Layer):
    layer_id = LayerId.TECHNICAL

    def evaluate(self, ctx: MarketContext) -> LayerScore:
        bars = ctx.bars(260)
        if len(bars) < 210:
            return self.abstain(f"solo {len(bars)} barras; se necesitan 210 para media de 200 y estructura")
        closes = [b.close for b in bars]

        # -- Puerta multi-timeframe (antes de cualquier score) --------------
        daily_bias = ind.directional_bias(closes, 50, 200)
        htf_closes = [b.close for b in ctx.higher_tf]
        htf_bias = ind.directional_bias(htf_closes, 10, 30) if len(htf_closes) >= 31 else None

        if daily_bias is None:
            return self.abstain("sesgo diario no calculable")
        if htf_bias is None:
            gate_note = (
                f"timeframe superior ({ctx.higher_tf_label}) sin historia suficiente "
                f"({len(htf_closes)} velas): la puerta multi-timeframe NO se pudo verificar"
            )
            gate_warn = ("MTF_NO_VERIFICADO",)
        elif daily_bias != 0 and htf_bias != 0 and daily_bias != htf_bias:
            return self.emit(
                0.0, 0.35,
                f"BLOQUEO MULTI-TIMEFRAME: el diario marca sesgo {daily_bias:+d} y el "
                f"{ctx.higher_tf_label} marca {htf_bias:+d}. El mandato es explicito: "
                "si no coinciden, no hay trade. No se promedia una contradiccion.",
                {"daily_bias": float(daily_bias), "htf_bias": float(htf_bias)},
                (MTF_CONFLICT,),
            )
        else:
            gate_note = f"diario {daily_bias:+d} y {ctx.higher_tf_label} {htf_bias:+d}: coinciden"
            gate_warn = ()

        # -- 1. Estructura de mercado ---------------------------------------
        st = ind.market_structure(bars)
        struct_score = None
        struct_note = "sin estructura calculable"
        if st is not None:
            struct_score = st.trend * 55.0
            if st.bos:
                struct_score += st.bos_direction * 35.0
            struct_note = st.description
        struct_score = clamp(struct_score) if struct_score is not None else None

        # -- 2. Momentum ----------------------------------------------------
        rsi = ind.rsi(closes, 14)
        macd = ind.macd(closes)
        adx = ind.adx(bars, 14)
        mom_parts: list[float] = []
        mom_note: list[str] = []
        if rsi is not None:
            # Lineal alrededor de 50, saturado en los extremos. Deliberadamente
            # NO se usa como sobrecompra/sobreventa: en tendencia, el RSI alto
            # es continuacion, no reversion.
            mom_parts.append(clamp((rsi - 50.0) * 2.4))
            mom_note.append(f"RSI {rsi:.0f}")
        if macd is not None and closes[-1] > 0:
            mom_parts.append(clamp(macd.hist / (closes[-1] * 0.004) * 30.0))
            mom_note.append(f"MACD hist {macd.hist:+.2f}")
        momentum = sum(mom_parts) / len(mom_parts) if mom_parts else None
        # ADX no da direccion: escala la conviccion del momentum.
        if momentum is not None and adx is not None:
            factor = 0.45 if adx < 18 else (1.0 if adx < 25 else 1.15)
            momentum = clamp(momentum * factor)
            mom_note.append(f"ADX {adx:.0f} ({'rango' if adx < 18 else 'tendencia'})")

        # -- 3. Volatilidad -------------------------------------------------
        bb = ind.bollinger(closes, 20, 2.0)
        vr = ind.vol_regime(closes, 20, 100)
        vol_score = None
        vol_note: list[str] = []
        if bb is not None:
            # %B extremo NO es senal por si mismo; se usa como moderador:
            # comprar contra la banda superior en expansion de volatilidad es
            # el error clasico de perseguir.
            vol_score = clamp((bb.percent_b - 0.5) * 90.0)
            vol_note.append(f"%B {bb.percent_b:.2f}")
        if vr is not None:
            vol_note.append(f"vol corta/larga {vr:.2f}")
            if vol_score is not None and vr > 1.5:
                vol_score *= 0.5
                vol_note.append("expansion de volatilidad: se descuenta la senal a la mitad")

        # -- 4. Volumen -----------------------------------------------------
        vratio = ind.volume_ratio(bars, 20)
        vw = ind.vwap(bars, 20)
        vp = ind.volume_profile(bars, 60)
        vol_parts: list[float] = []
        volu_note: list[str] = []
        if vratio is not None:
            # Confirmacion de ruptura: una ruptura sin volumen es una trampa.
            if st is not None and st.bos:
                vol_parts.append(clamp((vratio - 1.0) * 110.0) * st.bos_direction)
                volu_note.append(f"ruptura con volumen {vratio:.2f}x el promedio")
            else:
                vol_parts.append(clamp((vratio - 1.0) * 25.0))
                volu_note.append(f"volumen {vratio:.2f}x")
        if vw is not None and vw > 0:
            vol_parts.append(clamp((closes[-1] / vw - 1.0) * 900.0))
            volu_note.append(f"precio {'sobre' if closes[-1] > vw else 'bajo'} VWAP20")
        if vp is not None:
            vol_parts.append(clamp((closes[-1] / vp.poc - 1.0) * 700.0) * 0.6)
            volu_note.append(f"POC {vp.poc:.2f}, {'dentro' if vp.price_in_value_area else 'FUERA'} del area de valor")
        volume_score = sum(vol_parts) / len(vol_parts) if vol_parts else None

        # -- 5. Amplitud ----------------------------------------------------
        peer_closes = {s: v.closes(260) for s, v in ctx.peers.items()}
        peer_closes = {k: v for k, v in peer_closes.items() if len(v) >= 201}
        br = ind.breadth(peer_closes) if peer_closes else None
        breadth_score = None
        breadth_note = "sin universo para medir amplitud"
        if br is not None:
            breadth_score = clamp((br.pct_above_200 - 0.5) * 150.0 + br.advance_decline * 30.0)
            breadth_note = (
                f"{br.pct_above_200:.0%} del universo sobre su media de 200, "
                f"avance-descenso {br.advance_decline:+.2f} ({br.symbols} papeles)"
            )

        # -- Combinacion ----------------------------------------------------
        score, coverage, _ = blend([
            ("estructura", struct_score, 2.0),
            ("momentum", momentum, 1.5),
            ("volatilidad", vol_score, 1.0),
            ("volumen", volume_score, 1.5),
            ("amplitud", breadth_score, 1.0),
        ])

        rationale = (
            f"{gate_note}. Estructura: {struct_note}. "
            f"Momentum: {', '.join(mom_note) if mom_note else 'sin dato'}. "
            f"Volatilidad: {', '.join(vol_note) if vol_note else 'sin dato'}. "
            f"Volumen: {', '.join(volu_note) if volu_note else 'sin dato'}. "
            f"Amplitud: {breadth_note}."
        )

        warns = list(gate_warn)
        if st is None or st.trend == 0:
            warns.append(NO_STRUCTURE)

        # Senal contra el sesgo diario: no se anula, se descuenta y se marca.
        # Anularla dejaria al sistema incapaz de detectar cualquier giro; no
        # descontarla lo dejaria comprando en plena tendencia bajista porque
        # hubo una ruptura. El descuento preserva la informacion y obliga al
        # Abogado del Diablo a argumentar sobre ella.
        if daily_bias != 0 and score != 0 and (score > 0) != (daily_bias > 0):
            score *= 0.25
            warns.append(AGAINST_BIAS)
            rationale += (
                f" ATENCION: la senal ({score:+.0f} tras descuento) apunta CONTRA el "
                f"sesgo diario ({daily_bias:+d}). Descontada al 25%: puede ser un giro "
                "temprano o una trampa de contratendencia, y el sistema no distingue "
                "entre las dos hasta que ya paso."
            )

        return self.emit(
            score, coverage * (0.75 if warns else 1.0), rationale,
            {
                "estructura": struct_score or 0.0,
                "momentum": momentum or 0.0,
                "volatilidad": vol_score or 0.0,
                "volumen": volume_score or 0.0,
                "amplitud": breadth_score or 0.0,
                "rsi": rsi or 0.0,
                "adx": adx or 0.0,
                "atr": ind.atr(bars, 14) or 0.0,
            },
            warns,
        )
