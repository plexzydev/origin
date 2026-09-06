"""
CAPA 2 - FUNDAMENTAL DE EMPRESAS.

Fuente: SEC EDGAR (10-K, 10-Q, 8-K) via FundamentalStore, siempre con
`filed_at`. Los ETFs de indice no tienen balance: para ellos la capa se
abstiene explicitamente en vez de inventar un score.

Dos criterios del mandato que estan implementados literal y merecen atencion:

  "la DIRECCION del cambio pesa mas que el nivel"
      -> las revisiones de estimaciones puntuan por su derivada, no por su
         valor. Una empresa cara con estimaciones subiendo vale mas que una
         barata con estimaciones cayendo.

  "si sube con mal resultado, ya estaba descontado"
      -> la sorpresa de earnings se cruza con la reaccion del precio. Reaccion
         positiva ante mal dato = el mercado ya tenia el mal dato en precio,
         y eso es alcista, no bajista.
"""
from __future__ import annotations

from statistics import fmean

from ..contracts import LayerId, LayerScore
from ..stats import clamp, percentile_rank
from .base import Layer, MarketContext, blend

INDEX_LIKE = {"INDICE", "ETF", "INDEX"}


class FundamentalLayer(Layer):
    layer_id = LayerId.FUNDAMENTAL

    def evaluate(self, ctx: MarketContext) -> LayerScore:
        if ctx.sector in INDEX_LIKE:
            return self.abstain(
                f"{ctx.symbol} es un vehiculo de indice: no tiene balance propio. "
                "Analizar su 'fundamental' seria analizar el promedio de 500 empresas "
                "distintas, que es exactamente lo que la CAPA 3 hace mejor."
            )
        if ctx.fundamentals is None:
            return self.abstain("sin store de fundamentales cargado")

        hist = ctx.fundamentals.history(ctx.symbol, ctx.as_of, 9)
        if len(hist) < 4:
            return self.abstain(
                f"solo {len(hist)} trimestres publicados a la fecha; se necesitan 4 "
                "para medir tendencia sin confundirla con estacionalidad"
            )
        cur = hist[-1]
        notes: list[str] = []

        # -- 1. Crecimiento de ingresos y margenes --------------------------
        growth_score = None
        revs = [r.revenue for r in hist if r.revenue]
        if len(revs) >= 5:
            yoy = revs[-1] / revs[-5] - 1.0
            qoq = revs[-1] / revs[-2] - 1.0 if revs[-2] else 0.0
            growth_score = clamp(yoy * 320.0 + qoq * 120.0)
            notes.append(f"ingresos {yoy:+.1%} interanual, {qoq:+.1%} trimestral")

        margin_score = None
        margins = [r.operating_margin for r in hist if r.operating_margin is not None]
        if len(margins) >= 4:
            trend = margins[-1] - fmean(margins[-4:-1])
            margin_score = clamp(trend * 900.0)
            notes.append(f"margen operativo {margins[-1]:.1%} ({trend:+.2%} vs promedio 3T)")

        # -- 2. Caja vs ganancia contable -----------------------------------
        cash_score = None
        ratio = cur.fcf_vs_earnings
        if ratio is not None:
            # Bandera roja: ganancia creciente con caja que no acompana.
            cash_score = clamp((ratio - 0.75) * 130.0)
            if ratio < 0.5:
                notes.append(
                    f"ALERTA caja: FCF es solo {ratio:.0%} de la ganancia contable. "
                    "La utilidad puede estar en cuentas por cobrar o en gastos capitalizados"
                )
            else:
                notes.append(f"FCF/ganancia {ratio:.0%}")

        # -- 3. Deuda -------------------------------------------------------
        debt_parts: list[float] = []
        nde = cur.net_debt_to_ebitda
        if nde is not None:
            debt_parts.append(clamp((2.5 - nde) * 40.0))
            notes.append(f"deuda neta/EBITDA {nde:.1f}x")
        cov = cur.interest_coverage
        if cov is not None:
            debt_parts.append(clamp((cov - 4.0) * 18.0))
            notes.append(f"cobertura de intereses {cov:.1f}x")
        refi = cur.refi_risk()
        if refi is not None:
            # Cuanto EBITDA se come el encarecimiento de la deuda que vence.
            debt_parts.append(clamp(-refi * 900.0))
            notes.append(f"refinanciacion: {refi:.2%} del EBITDA de costo incremental")
        debt_score = fmean(debt_parts) if debt_parts else None

        # -- 4. Valuacion RELATIVA (nunca absoluta) -------------------------
        val_score, val_note = self._valuation(ctx, cur, hist)
        if val_note:
            notes.append(val_note)

        # -- 5. Revisiones de estimaciones: manda la DIRECCION --------------
        rev_score = None
        er = cur.estimate_revision_pct
        if er is not None:
            rev_score = clamp(er * 900.0)
            notes.append(f"estimaciones {er:+.1%} en 90 dias ({'al alza' if er > 0 else 'a la baja'})")

        # -- 6. Sorpresa cruzada con reaccion del precio --------------------
        surprise_score = None
        sp, pr = cur.eps_surprise_pct, cur.price_reaction_pct
        if sp is not None and pr is not None:
            base = clamp(sp * 500.0)
            if sp < -0.01 and pr > 0.01:
                surprise_score = clamp(45.0)
                notes.append(
                    f"sorpresa {sp:+.1%} pero el precio reacciono {pr:+.1%}: "
                    "el mal resultado YA estaba descontado. Alcista."
                )
            elif sp > 0.01 and pr < -0.01:
                surprise_score = clamp(-45.0)
                notes.append(
                    f"sorpresa {sp:+.1%} y el precio cayo {pr:+.1%}: "
                    "buen dato ya en precio, o el mercado mira otra cosa. Bajista."
                )
            else:
                surprise_score = base
                notes.append(f"sorpresa {sp:+.1%}, reaccion {pr:+.1%} (coherentes)")

        # -- 7. Insiders, recompras, dilucion -------------------------------
        flow_parts: list[float] = []
        if cur.insider_net_usd is not None and cur.revenue:
            flow_parts.append(clamp(cur.insider_net_usd / (cur.revenue * 0.002)))
            notes.append(f"insiders netos {cur.insider_net_usd:+,.0f} USD")
        shares = [r.shares_diluted for r in hist if r.shares_diluted]
        if len(shares) >= 5 and shares[-5]:
            dilution = shares[-1] / shares[-5] - 1.0
            flow_parts.append(clamp(-dilution * 1400.0))
            notes.append(
                f"acciones en circulacion {dilution:+.2%} interanual "
                f"({'recompra' if dilution < 0 else 'dilucion'})"
            )
        flow_score = fmean(flow_parts) if flow_parts else None

        score, coverage, _ = blend([
            ("crecimiento", growth_score, 1.5),
            ("margenes", margin_score, 1.2),
            ("caja", cash_score, 1.5),
            ("deuda", debt_score, 1.5),
            ("valuacion", val_score, 1.0),
            ("revisiones", rev_score, 1.3),
            ("sorpresa", surprise_score, 0.8),
            ("insiders_recompras", flow_score, 0.7),
        ])

        rationale = (
            f"{ctx.symbol} ({ctx.sector}), ultimo filing {cur.form_type} del "
            f"{cur.period_end} publicado el {cur.filed_at.date()}. " + " | ".join(notes)
        )
        warns = []
        lag_days = (ctx.as_of.date() - cur.filed_at.date()).days
        if lag_days > 100:
            warns.append("FILING_VIEJO")
            rationale += f". ATENCION: el ultimo filing tiene {lag_days} dias; los numeros pueden estar desactualizados"

        return self.emit(score, coverage, rationale, {
            "crecimiento": growth_score or 0.0, "margenes": margin_score or 0.0,
            "caja": cash_score or 0.0, "deuda": debt_score or 0.0,
            "valuacion": val_score or 0.0, "revisiones": rev_score or 0.0,
            "fcf_vs_ganancia": ratio or 0.0, "deuda_neta_ebitda": nde or 0.0,
        }, warns)

    # -- valuacion relativa -------------------------------------------------
    def _valuation(self, ctx: MarketContext, cur, hist) -> tuple[float | None, str]:
        """
        Multiplos SIEMPRE relativos: contra el sector y contra la propia
        historia de la empresa. Un PER de 30 no dice nada solo; un PER de 30
        cuando el papel promedio de su sector esta en 18 y el propio historico
        es 22, dice bastante.
        """
        px = ctx.closes(1)
        if not px or not cur.shares_diluted:
            return None, ""
        mcap = px[-1] * cur.shares_diluted

        def multiple(rec, price: float | None) -> float | None:
            if price is None or not rec.shares_diluted or not rec.ebitda or rec.ebitda <= 0:
                return None
            mc = price * rec.shares_diluted
            ev = mc + (rec.total_debt or 0.0) - (rec.cash or 0.0)
            return ev / rec.ebitda

        cur_mult = multiple(cur, px[-1])
        if cur_mult is None:
            return None, ""

        parts: list[float] = []
        bits: list[str] = []

        # Contra su propia historia, valuada con el precio de cada momento
        own: list[float] = []
        for r in hist[:-1]:
            p = ctx.close_on_or_before(r.filed_at.date())
            m = multiple(r, p)
            if m is not None:
                own.append(m)
        if len(own) >= 4:
            pr = percentile_rank(cur_mult, own)
            if pr is not None:
                parts.append(clamp((0.5 - pr) * 130.0))
                bits.append(f"EV/EBITDA {cur_mult:.1f}x = percentil {pr:.0%} de su propia historia")
        elif own:
            med = fmean(own)
            parts.append(clamp((med - cur_mult) / max(med, 1e-9) * 110.0))
            bits.append(f"EV/EBITDA {cur_mult:.1f}x vs {med:.1f}x promedio propio (muestra corta)")

        # Contra el sector
        peers = ctx.sector_peers()
        peer_mults: list[float] = []
        for s in peers:
            r = ctx.fundamentals.latest(s, ctx.as_of) if ctx.fundamentals else None
            v = ctx.peers.get(s)
            if r is None or v is None:
                continue
            pc = v.closes(1)
            m = multiple(r, pc[-1] if pc else None)
            if m is not None:
                peer_mults.append(m)
        if len(peer_mults) >= 2:
            med = fmean(peer_mults)
            parts.append(clamp((med - cur_mult) / max(med, 1e-9) * 110.0))
            bits.append(f"vs sector {med:.1f}x ({len(peer_mults)} pares)")

        if not parts:
            return None, f"EV/EBITDA {cur_mult:.1f}x sin base de comparacion: NO se puntua en absoluto"
        return fmean(parts), "; ".join(bits)
