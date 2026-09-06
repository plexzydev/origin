"""
CAPA 3 - MACRO Y SITUACION DE ESTADOS.

Fuente: FRED, BLS, bancos centrales -- todo via PointInTimeStore, es decir
con la fecha de publicacion real. Esto importa mas aca que en ninguna otra
capa: el ISM se revisa, las nominas se revisan dos veces, el PBI tres.

Nueve sub-senales. Dos merecen explicacion porque son las que mas seguido se
implementan mal:

  CURVA DE TASAS: la DESinversion pesa mas que la inversion. La curva se
  invierte 12-18 meses antes de la recesion (aviso temprano y ruidoso) pero se
  DESinvierte semanas antes (aviso tardio y confiable). Casi todos los sistemas
  puntuan la inversion y se pierden la senal util.

  CREDITO: se puntua la VELOCIDAD de ampliacion, no el nivel. Un HY en 500bp
  estable es un mercado tranquilo con riesgo caro; un HY que paso de 350 a 500
  en dos semanas es otra cosa completamente distinta.
"""
from __future__ import annotations

from statistics import fmean

from ..contracts import LayerId, LayerScore
from ..stats import clamp, percentile_rank
from .base import Layer, MarketContext, blend


class MacroLayer(Layer):
    layer_id = LayerId.MACRO

    def evaluate(self, ctx: MarketContext) -> LayerScore:
        if ctx.pit is None:
            return self.abstain("sin store point-in-time cargado")
        notes: list[str] = []

        # -- 1. Ciclo -------------------------------------------------------
        cycle_parts: list[float] = []
        ism = ctx.macro("ISM_MFG")
        if ism is not None:
            h = ctx.macro_hist("ISM_MFG", 4)
            trend = (ism - h[0]) if len(h) >= 2 else 0.0
            cycle_parts.append(clamp((ism - 50.0) * 7.0 + trend * 6.0))
            notes.append(f"ISM manufacturero {ism:.1f} ({trend:+.1f} en 3 meses)")
        for sid, label in (("ISM_SVC", "ISM servicios"), ("INDPRO", "produccion industrial"),
                           ("RETAIL", "ventas minoristas")):
            v = ctx.macro(sid)
            ch = ctx.macro_change(sid, 3)
            if v is not None and ch is not None:
                base = 50.0 if sid == "ISM_SVC" else 0.0
                scale = 7.0 if sid == "ISM_SVC" else 4.0
                cycle_parts.append(clamp((v - base) * (7.0 if sid == "ISM_SVC" else 0.0) + ch * scale))
                notes.append(f"{label} {ch:+.2f} en 3 meses")
        cycle_score = fmean(cycle_parts) if cycle_parts else None

        # -- 2. Inflacion: importa la DIRECCION -----------------------------
        infl_parts: list[float] = []
        cpi = ctx.macro("CPI")
        cpi_ch = ctx.macro_change("CPI", 3)
        if cpi is not None and cpi_ch is not None:
            # Desinflacion desde niveles altos = alcista (permite recortes).
            # Inflacion acelerando = bajista (obliga a subir tasas).
            infl_parts.append(clamp(-cpi_ch * 45.0 - max(0.0, cpi - 3.0) * 12.0))
            notes.append(f"IPC {cpi:.1f}% ({cpi_ch:+.2f} en 3 meses)")
        pce_ch = ctx.macro_change("CORE_PCE", 3)
        if pce_ch is not None:
            infl_parts.append(clamp(-pce_ch * 50.0))
            notes.append(f"PCE nucleo {pce_ch:+.2f} en 3 meses")
        be = ctx.macro("BREAKEVEN_5Y")
        if be is not None:
            # Expectativas desancladas en cualquier direccion son malas.
            infl_parts.append(clamp(-abs(be - 2.2) * 45.0))
            notes.append(f"expectativa de inflacion 5a {be:.2f}%")
        infl_score = fmean(infl_parts) if infl_parts else None

        # -- 3. Empleo ------------------------------------------------------
        emp_parts: list[float] = []
        pr = ctx.macro("PAYROLLS")
        if pr is not None:
            emp_parts.append(clamp((pr - 100_000) / 2_000.0))
            notes.append(f"nominas {pr:+,.0f}")
        un_ch = ctx.macro_change("UNRATE", 3)
        if un_ch is not None:
            # Regla de Sahm en espiritu: la SUBA del desempleo avisa recesion.
            emp_parts.append(clamp(-un_ch * 200.0))
            notes.append(f"desempleo {un_ch:+.2f}pp en 3 meses")
        cl_ch = ctx.macro_change("CLAIMS", 3)
        if cl_ch is not None:
            emp_parts.append(clamp(-cl_ch / 900.0))
            notes.append(f"pedidos de subsidio {cl_ch:+,.0f}")
        emp_score = fmean(emp_parts) if emp_parts else None

        # -- 4. Politica monetaria -----------------------------------------
        pol_parts: list[float] = []
        ff_ch = ctx.macro_change("FEDFUNDS", 60)
        if ff_ch is not None:
            pol_parts.append(clamp(-ff_ch * 55.0))
            notes.append(f"tasa de referencia {ff_ch:+.2f}pp en 60 ruedas")
        ba_ch = ctx.macro_change("FED_ASSETS", 60)
        ba = ctx.macro("FED_ASSETS")
        if ba_ch is not None and ba:
            pol_parts.append(clamp(ba_ch / ba * 900.0))
            notes.append(f"balance del banco central {ba_ch / ba:+.2%} en 60 ruedas")
        policy_score = fmean(pol_parts) if pol_parts else None

        # -- 5. Curva de tasas ---------------------------------------------
        curve_score = None
        t10, t2 = ctx.macro("DGS10"), ctx.macro("DGS2")
        if t10 is not None and t2 is not None:
            slope = t10 - t2
            h10, h2 = ctx.macro_hist("DGS10", 40), ctx.macro_hist("DGS2", 40)
            prev = (h10[-20] - h2[-20]) if len(h10) >= 20 and len(h2) >= 20 else slope
            if prev < 0 <= slope:
                curve_score = -85.0
                notes.append(
                    f"curva 2-10 DESINVIRTIENDOSE ({prev:+.2f} -> {slope:+.2f}). "
                    "Historicamente la recesion empieza cuando la curva se normaliza, "
                    "no cuando se invierte. Es la senal tardia y la confiable."
                )
            elif slope < 0:
                curve_score = clamp(slope * 55.0)
                notes.append(f"curva 2-10 invertida en {slope:+.2f}")
            else:
                curve_score = clamp((slope - 0.8) * 35.0)
                notes.append(f"curva 2-10 en {slope:+.2f}")

        # -- 6. Credito: manda la VELOCIDAD ---------------------------------
        credit_parts: list[float] = []
        for sid, label, scale in (("HY_OAS", "high yield", 1.6), ("IG_OAS", "grado inversor", 4.0)):
            v = ctx.macro(sid)
            h = ctx.macro_hist(sid, 25)
            if v is not None and len(h) >= 20:
                widening = v - h[-20]
                credit_parts.append(clamp(-widening / scale))
                notes.append(f"{label} {v:.0f}bp ({widening:+.0f}bp en 20 ruedas)")
        credit_score = fmean(credit_parts) if credit_parts else None

        # -- 7. Salud fiscal soberana ---------------------------------------
        fiscal_parts: list[float] = []
        dg = ctx.macro("DEBT_GDP")
        if dg is not None:
            fiscal_parts.append(clamp((100.0 - dg) * 0.8))
            notes.append(f"deuda/PBI {dg:.0f}%")
        defg = ctx.macro("DEFICIT_GDP")
        if defg is not None:
            fiscal_parts.append(clamp((defg + 3.0) * 14.0))
            notes.append(f"deficit/PBI {defg:.1f}%")
        cds = ctx.macro("CDS_5Y")
        if cds is not None:
            fiscal_parts.append(clamp((40.0 - cds) * 1.5))
            notes.append(f"CDS soberano {cds:.0f}bp")
        fiscal_score = fmean(fiscal_parts) if fiscal_parts else None

        # -- 8. Divisas y commodities ---------------------------------------
        fx_parts: list[float] = []
        dxy_ch = ctx.macro_change("DXY", 20)
        dxy = ctx.macro("DXY")
        if dxy_ch is not None and dxy:
            # Dolar fuerte aprieta las condiciones financieras globales.
            fx_parts.append(clamp(-dxy_ch / dxy * 1400.0))
            notes.append(f"dolar {dxy_ch / dxy:+.2%} en 20 ruedas")
        cu, au = ctx.macro("COPPER"), ctx.macro("GOLD")
        if cu and au:
            h_cu, h_au = ctx.macro_hist("COPPER", 60), ctx.macro_hist("GOLD", 60)
            if len(h_cu) >= 40 and len(h_au) >= 40:
                ratio_now, ratio_prev = cu / au, h_cu[-40] / h_au[-40]
                # Cobre/oro: el termometro de crecimiento menos manipulable.
                fx_parts.append(clamp((ratio_now / ratio_prev - 1.0) * 320.0))
                notes.append(f"cobre/oro {ratio_now / ratio_prev - 1.0:+.1%} en 40 ruedas")
        fx_score = fmean(fx_parts) if fx_parts else None

        # -- 9. Liquidez global ---------------------------------------------
        liq_parts: list[float] = []
        m2_ch = ctx.macro_change("M2", 3)
        m2 = ctx.macro("M2")
        if m2_ch is not None and m2:
            liq_parts.append(clamp(m2_ch / m2 * 2200.0))
            notes.append(f"M2 {m2_ch / m2:+.2%} en 3 meses")
        nfci = ctx.macro("NFCI")
        if nfci is not None:
            liq_parts.append(clamp(-nfci * 95.0))
            notes.append(f"condiciones financieras {nfci:+.2f} ({'restrictivas' if nfci > 0 else 'laxas'})")
        liq_score = fmean(liq_parts) if liq_parts else None

        score, coverage, _ = blend([
            ("ciclo", cycle_score, 1.6),
            ("inflacion", infl_score, 1.2),
            ("empleo", emp_score, 1.3),
            ("politica_monetaria", policy_score, 1.2),
            ("curva", curve_score, 1.4),
            ("credito", credit_score, 2.0),      # el mejor termometro anticipado
            ("fiscal", fiscal_score, 0.6),
            ("divisas_commodities", fx_score, 0.8),
            ("liquidez", liq_score, 1.0),
        ])

        warns = []
        if coverage < 0.5:
            warns.append("COBERTURA_MACRO_BAJA")

        return self.emit(
            score, coverage,
            "Macro con datos tal como se conocian al " + ctx.as_of.date().isoformat() +
            " (sin revisiones posteriores). " + " | ".join(notes),
            {
                "ciclo": cycle_score or 0.0, "inflacion": infl_score or 0.0,
                "empleo": emp_score or 0.0, "curva": curve_score or 0.0,
                "credito": credit_score or 0.0, "liquidez": liq_score or 0.0,
            },
            warns,
        )
