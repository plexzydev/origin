"""
Compuertas del motor de decision: vetos, umbral, contradiccion, asimetria,
arbol de escenarios y Abogado del Diablo.

La propiedad general que se verifica en todo el archivo: NINGUNA compuerta se
puede compensar con un score alto en otra parte. Cada una bloquea sola.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from conftest import SMALL_SYMBOLS

from qtdesk.clock import AccessAudit
from qtdesk.config import SystemConfig
from qtdesk.contracts import Action, Role, Severity, Side, utc
from qtdesk.data.calendar import EarningsEvent, EventKind, MacroEvent
from qtdesk.engine.decision import DecisionEngine, EngineDeps
from qtdesk.engine.scenarios import (TreeInputs, base_hit_rate, breakeven_hit_rate,
                                     build_tree, evaluate_tree)
from qtdesk.layers.veto import run_capa0
from qtdesk.risk.circuit_breakers import evaluate as breakers
from qtdesk.risk.state import DeskState


# ===========================================================================
# CAPA 0: cada veto bloquea solo
# ===========================================================================

def _ctx(bundle, world, cfg, desk, sym="AAPL", idx=400):
    return bundle.context(sym, world.sessions[idx], desk, cfg, AccessAudit())


def test_capa0_corre_todos_los_chequeos_y_los_reporta(bundle, world, cfg, desk):
    v, outs = run_capa0(_ctx(bundle, world, cfg, desk), breakers(desk, cfg.risk))
    assert len(outs) >= 12, "deberian correr los doce chequeos previos"
    # Los chequeos LIMPIOS tambien se reportan: sin eso no se distingue
    # "no habia riesgo" de "no lo miramos".
    assert any(not o.fired and not o.skipped for o in outs)


def test_veto_de_earnings_bloquea_y_usa_fecha_point_in_time(bundle, world, cfg, desk):
    as_of = world.sessions[400]
    cal = bundle.calendar
    limpio = date(2030, 1, 1)
    bundle.events.earnings.append(EarningsEvent("AAPL", expected_date=limpio))
    v, _ = run_capa0(bundle.context("AAPL", as_of, desk, cfg, AccessAudit()),
                     breakers(desk, cfg.risk))
    sin_earnings = "VETO_EARNINGS" not in v.codes

    proximo = cal.add_sessions(as_of.date(), 2)
    bundle.events.earnings.append(EarningsEvent("AAPL", expected_date=proximo))
    v2, _ = run_capa0(bundle.context("AAPL", as_of, desk, cfg, AccessAudit()),
                      breakers(desk, cfg.risk))
    bundle.events.earnings.pop()
    bundle.events.earnings.pop()
    assert sin_earnings
    assert "VETO_EARNINGS" in v2.codes


def test_veto_de_drawdown_bloquea_aperturas(bundle, world, cfg):
    desk = DeskState(equity=88_000.0, peak_equity=100_000.0,
                     day_start_equity=88_000.0, week_start_equity=88_000.0,
                     month_start_equity=88_000.0)
    v, _ = run_capa0(_ctx(bundle, world, cfg, desk), breakers(desk, cfg.risk))
    assert "VETO_DRAWDOWN" in v.codes


def test_veto_de_sobreoperacion_no_lo_levanta_la_cuota(bundle, world, cfg):
    desk = DeskState(equity=100_000.0, trades_this_week=cfg.veto.max_trades_per_week)
    v, _ = run_capa0(_ctx(bundle, world, cfg, desk), breakers(desk, cfg.risk))
    assert "VETO_SOBREOPERACION" in v.codes


def test_veto_por_cobertura_insuficiente_de_chequeos(bundle, world, cfg, desk):
    """Un riesgo que no se puede medir no es un riesgo chico."""
    from qtdesk.data.bundle import DataBundle
    from qtdesk.data.pit import PointInTimeStore
    from qtdesk.data.calendar import EventCalendar
    pelado = DataBundle(
        bars=bundle.bars, calendar=bundle.calendar,
        pit=PointInTimeStore(), events=EventCalendar(),      # sin macro ni eventos
        sector_map=bundle.sector_map, history_window=bundle.history_window,
    )
    ctx = pelado.context("AAPL", world.sessions[400], desk, cfg, AccessAudit())
    v, outs = run_capa0(ctx, breakers(desk, cfg.risk))
    salteados = [o.code for o in outs if o.skipped]
    assert len(salteados) >= 3
    assert "VETO_COBERTURA_INSUFICIENTE" in v.codes


def test_un_veto_de_capa0_corta_antes_del_scoring(bundle, world, cfg):
    """Si CAPA 0 veta, las capas ni siquiera se evaluan."""
    desk = DeskState(equity=85_000.0, peak_equity=100_000.0,
                     day_start_equity=85_000.0, week_start_equity=85_000.0,
                     month_start_equity=85_000.0)
    eng = DecisionEngine(cfg, EngineDeps.default())
    d = eng.decide(_ctx(bundle, world, cfg, desk), breakers(desk, cfg.risk))
    assert d.action is Action.NO_TRADE
    assert all(s.confidence == 0.0 for s in d.layer_scores), \
        "las capas se evaluaron pese al veto de CAPA 0"


# ===========================================================================
# Las cinco voces, siempre
# ===========================================================================

def test_toda_decision_lleva_las_cinco_voces_incluso_al_no_operar(bundle, world, cfg, desk):
    eng = DecisionEngine(cfg, EngineDeps.default())
    d = eng.decide(_ctx(bundle, world, cfg, desk), breakers(desk, cfg.risk))
    roles = {v.role for v in d.voices}
    assert roles == set(Role), f"faltan voces: {set(Role) - roles}"
    for v in d.voices:
        assert v.message.strip(), f"la voz {v.role.value} vino vacia"


def test_una_decision_sin_todas_las_voces_no_se_puede_construir():
    from qtdesk.contracts import Cycle, Decision, RiskMode, VetoResult, Voice
    with pytest.raises(ValueError, match="sin todas las voces"):
        Decision(
            ts=utc(2024, 1, 2), symbol="X", action=Action.NO_TRADE,
            regime_cycle=Cycle.UNKNOWN, regime_risk=RiskMode.NEUTRAL,
            veto=VetoResult(True), layer_scores=(), weights={},
            combined_score=0.0, aligned_layers=0, scenario_tree=None,
            arguments=(), voices=(Voice(Role.QUANT, "NEUTRAL", "solo yo"),),
            plan=None, thesis="t", falsification="", falsification_deadline=None,
            conviction=1, conviction_reason="r",
        )


# ===========================================================================
# Asimetria: el filtro tiene que filtrar
# ===========================================================================

def test_el_objetivo_no_se_deriva_del_stop(bundle, world, cfg, desk):
    """
    Si el objetivo fuera "entrada + N x stop", el R:R seria SIEMPRE N y el
    filtro no filtraria nada. Se verifica que la distribucion real de R:R
    tenga dispersion y que una parte relevante quede por debajo del minimo.
    """
    from qtdesk.engine.levels import derive
    rrs = []
    for idx in range(320, 700, 7):
        for sym in SMALL_SYMBOLS[:4]:
            lv = derive(bundle.context(sym, world.sessions[idx], desk, cfg, AccessAudit()),
                        Side.LONG, cfg.risk.min_rr_ratio)
            if lv.rr > 0:
                rrs.append(lv.rr)
    assert len(rrs) > 50
    assert len(set(round(r, 2) for r in rrs)) > 20, "el R:R es constante: el objetivo sale del stop"
    rechazados = sum(1 for r in rrs if r < cfg.risk.min_rr_ratio)
    assert rechazados > 0, "el filtro de asimetria no rechaza nada: no esta filtrando"


# ===========================================================================
# Arbol de escenarios
# ===========================================================================

def test_las_probabilidades_del_arbol_suman_exactamente_uno():
    for rr in (1.2, 1.5, 2.0, 3.0, 5.0):
        for c in (1, 2, 3, 4, 5):
            for vs in (0.0, 0.5, 1.0):
                t = build_tree(TreeInputs(rr, c, vs, 0.7))
                assert abs(sum(s.probability for s in t.scenarios) - 1.0) < 1e-9


def test_el_arbol_exige_entre_tres_y_cinco_caminos():
    from qtdesk.contracts import Scenario, ScenarioTree
    with pytest.raises(ValueError, match="3 y 5"):
        ScenarioTree((Scenario("a", 0.5, 1.0, "d"), Scenario("b", 0.5, -1.0, "d")))


def test_la_asimetria_sola_no_crea_esperanza_matematica():
    """
    Propiedad central del modelo: SIN VENTAJA, ningun ratio riesgo/beneficio
    produce esperanza matematica positiva. La asimetria reparte el resultado
    de otra forma; no lo mejora.

    Ademas se verifica algo contraintuitivo que el modelo si captura: subir el
    R:R lo empeora LEVEMENTE. Con objetivos mas lejanos se acierta menos, y
    cada perdida adicional carga su probabilidad de gap. El ratio no es gratis.
    """
    evs = {}
    for rr in (1.5, 2.0, 3.0, 5.0):
        evs[rr] = build_tree(TreeInputs(rr, 3, 0.4, 0.7)).expected_r   # conviccion 3 = sin ventaja
    assert all(v < 0 for v in evs.values()), (
        f"algun R:R da EV positivo sin ventaja ({evs}): el modelo esta regalando "
        "esperanza matematica que la asimetria no produce"
    )
    assert evs[5.0] < evs[1.5], (
        "el modelo no captura que un objetivo mas lejano acierta menos y por lo tanto "
        "queda mas expuesto al riesgo de gap"
    )


def test_la_tasa_de_equilibrio_esta_por_encima_de_la_del_azar():
    """La friccion cuesta: hace falta ventaja real para no perder plata."""
    for rr in (1.5, 2.0, 3.0):
        inp = TreeInputs(rr, 3, 0.4, 0.7)
        assert breakeven_hit_rate(inp) > base_hit_rate(rr) + 0.05


def test_un_ev_positivo_no_habilita_un_peor_caso_intolerable():
    t = build_tree(TreeInputs(3.0, 5, 0.2, 0.7, measured_hit_rate=0.60, sample_size=100))
    assert t.expected_r > 0.2
    v = evaluate_tree(t, risk_pct_of_equity=0.02, min_expected_r=0.20, max_worst_case_pct=0.025)
    assert v.ev_ok and not v.survivable and not v.approved


def test_la_tasa_medida_reemplaza_a_la_teorica_con_muestra_suficiente():
    sin = build_tree(TreeInputs(1.5, 3, 0.4, 0.7, measured_hit_rate=0.65, sample_size=10))
    con = build_tree(TreeInputs(1.5, 3, 0.4, 0.7, measured_hit_rate=0.65, sample_size=50))
    assert con.expected_r > sin.expected_r
    assert "MEDIDA" in con.scenarios[0].description
    assert "NO DEMOSTRADA" in sin.scenarios[0].description


# ===========================================================================
# Abogado del Diablo
# ===========================================================================

def test_el_abogado_del_diablo_habla_en_toda_operacion(bundle, world, cfg, desk):
    eng = DecisionEngine(cfg, EngineDeps.default())
    vistos = 0
    for idx in range(330, 420, 5):
        for sym in SMALL_SYMBOLS[:4]:
            d = eng.decide(bundle.context(sym, world.sessions[idx], desk, cfg, AccessAudit()),
                           breakers(desk, cfg.risk))
            voz = next(v for v in d.voices if v.role is Role.DEVILS_ADVOCATE)
            assert voz.message.strip()
            vistos += 1
    assert vistos > 20


def test_un_argumento_HIGH_sin_refutar_bloquea(bundle, world, cfg, desk):
    from qtdesk.contracts import Argument
    from qtdesk.engine import devils_advocate as da
    args = (
        Argument("objecion grave", Severity.HIGH, "evidencia", refuted_by=None),
        Argument("objecion menor", Severity.MEDIUM, "evidencia", refuted_by=None),
        Argument("objecion refutada", Severity.CRITICAL, "evidencia", refuted_by="datos"),
    )
    bloq = da.blocking(args, "HIGH")
    assert len(bloq) == 1 and bloq[0].claim == "objecion grave"


def test_el_modo_medicion_es_la_unica_refutacion_valida_de_la_falta_de_muestra(bundle, world, cfg, desk):
    from qtdesk.engine import devils_advocate as da
    from qtdesk import regime as R
    ctx = _ctx(bundle, world, cfg, desk)
    reg = R.detect(ctx)
    sin = da.build_case(ctx, [], reg, None, None, None, sample_size=0, measuring=False)
    con = da.build_case(ctx, [], reg, None, None, None, sample_size=0,
                        measuring=True, measurement_size_multiplier=0.22)
    a_sin = next(a for a in sin if "ventaja" in a.claim)
    a_con = next(a for a in con if "ventaja" in a.claim)
    assert a_sin.standing, "sin modo medicion la objecion queda EN PIE"
    assert not a_con.standing, "en modo medicion la objecion se refuta por protocolo"


# ===========================================================================
# Trinquete de configuracion
# ===========================================================================

def test_la_configuracion_no_permite_aflojar_riesgo():
    c = SystemConfig()
    with pytest.raises(ValueError, match="Prohibido aflojar"):
        c.tighten_only(max_stressed_risk_pct=0.10)
    with pytest.raises(ValueError, match="Prohibido aflojar"):
        c.tighten_only(min_rr_ratio=1.0)
    assert c.tighten_only(min_rr_ratio=2.0).risk.min_rr_ratio == 2.0
