"""
PRUEBAS DE LOS CORTAFUEGOS DE RIESGO.

Verifican que efectivamente SE DISPARAN. Un limite de riesgo que nadie probo
es una intencion, no un control.

Cada cortafuegos tiene su test de disparo, su test de NO disparo antes del
umbral, y donde corresponde su test de persistencia (los que exigen
intervencion manual no se liberan solos).
"""
from __future__ import annotations

import random

import pytest

from qtdesk.config import RiskConfig, SystemConfig
from qtdesk.contracts import Position, Side, utc
from qtdesk.risk import circuit_breakers as cb
from qtdesk.risk.limits import check_limits
from qtdesk.risk.sizing import atr_position_size, fractional_kelly
from qtdesk.risk.state import DeskState
from qtdesk.risk.stress import run_all, survives_all


def mk(equity=100_000.0, peak=100_000.0, day=None, week=None, month=None, **kw):
    return DeskState(
        equity=equity, peak_equity=peak,
        day_start_equity=day or equity, week_start_equity=week or equity,
        month_start_equity=month or equity, **kw,
    )


# ===========================================================================
# Perdida diaria -> cierre de jornada
# ===========================================================================

def test_perdida_diaria_dispara_cierre_de_jornada():
    cfg = RiskConfig()
    st = mk(equity=97_900.0, day=100_000.0)          # -2.1% > umbral 2%
    v = cb.evaluate(st, cfg)
    assert v.level is cb.BreakerLevel.DAILY_HALT
    assert not v.can_open
    assert v.size_multiplier == 0.0


def test_perdida_diaria_justo_por_debajo_del_umbral_no_dispara():
    st = mk(equity=98_100.0, day=100_000.0)          # -1.9%
    v = cb.evaluate(st, RiskConfig())
    assert v.can_open, "no deberia disparar antes del umbral"


def test_el_cierre_de_jornada_se_libera_al_dia_siguiente_pero_no_antes():
    cfg = RiskConfig()
    st = mk(equity=97_000.0, day=100_000.0)
    cb.evaluate(st, cfg)
    assert st.day_halt_latched
    # Sigue trabado dentro del mismo dia aunque el equity se recupere
    st.mark_to_market(99_900.0)
    assert not cb.evaluate(st, cfg).can_open
    # Cambio de dia -> se libera
    st.roll_periods(utc(2024, 5, 2))
    assert not st.day_halt_latched
    assert cb.evaluate(st, cfg).can_open


# ===========================================================================
# Perdida semanal -> tamano a la mitad
# ===========================================================================

def test_perdida_semanal_reduce_tamano_a_la_mitad():
    cfg = RiskConfig()
    st = mk(equity=95_500.0, peak=100_000.0, day=95_500.0, week=100_000.0, month=95_500.0)
    v = cb.evaluate(st, cfg)
    assert v.can_open, "la perdida semanal reduce, no bloquea"
    assert v.size_multiplier <= 0.5


# ===========================================================================
# Perdida mensual -> apagado total con reset manual
# ===========================================================================

def test_perdida_mensual_apaga_todo_y_exige_reset_manual():
    cfg = RiskConfig()
    st = mk(equity=92_000.0, peak=100_000.0, day=92_000.0, week=92_000.0, month=100_000.0)
    v = cb.evaluate(st, cfg)
    assert v.level is cb.BreakerLevel.SHUTDOWN
    assert not v.can_open and v.requires_manual_reset

    # No se libera solo, ni cambiando de mes, ni recuperando el capital
    st.mark_to_market(101_000.0)
    st.roll_periods(utc(2024, 6, 1))
    assert not cb.evaluate(st, cfg).can_open, "el apagado mensual NO se libera solo"

    st.manual_reset("operador", "revision completada", utc(2024, 6, 1))
    assert cb.evaluate(st, cfg).can_open
    assert any("RESET MANUAL" in n for n in st.notes), "la reactivacion debe dejar rastro"


# ===========================================================================
# Racha de perdidas -> pausa forzada
# ===========================================================================

def test_tres_perdidas_consecutivas_fuerzan_pausa_y_auditoria():
    cfg = RiskConfig()
    st = mk()
    for _ in range(3):
        st.register_close(-500.0)
    v = cb.evaluate(st, cfg)
    assert v.level is cb.BreakerLevel.STREAK_PAUSE
    assert not v.can_open and v.requires_manual_reset


def test_una_ganancia_reinicia_el_contador_de_racha():
    st = mk()
    st.register_close(-500.0)
    st.register_close(-500.0)
    st.register_close(+100.0)
    assert st.consecutive_losses == 0
    assert cb.evaluate(st, RiskConfig()).can_open


# ===========================================================================
# Escalera de drawdown  +  PROHIBICION DE MARTINGALA
# ===========================================================================

def test_la_escalera_de_drawdown_es_monotona_no_creciente():
    cfg = RiskConfig()
    prev = 1.01
    for dd in [i / 200 for i in range(0, 30)]:
        m = cb.drawdown_multiplier(dd, cfg.drawdown_ladder)
        assert m <= prev + 1e-12, f"la escalera SUBIO en dd={dd:.3f}: {prev} -> {m}"
        prev = m
    assert cb.drawdown_multiplier(0.15, cfg.drawdown_ladder) == 0.0


def test_el_multiplicador_nunca_supera_1_en_ninguna_secuencia_aleatoria():
    """
    PROHIBICION DE MARTINGALA.

    Se recorren 20.000 estados aleatorios -- incluyendo rachas de perdidas,
    drawdowns profundos y combinaciones de cortafuegos -- y se verifica que el
    multiplicador de tamano NUNCA supera 1.0. No existe ninguna ruta en el
    codigo que aumente el tamano despues de una perdida.
    """
    cfg = RiskConfig()
    rng = random.Random(7)
    for _ in range(20_000):
        peak = rng.uniform(50_000, 200_000)
        eq = peak * rng.uniform(0.5, 1.0)
        st = mk(equity=eq, peak=peak,
                day=peak * rng.uniform(0.9, 1.1),
                week=peak * rng.uniform(0.9, 1.1),
                month=peak * rng.uniform(0.9, 1.1),
                consecutive_losses=rng.randint(0, 6))
        v = cb.evaluate(st, cfg)
        assert v.size_multiplier <= 1.0, f"multiplicador {v.size_multiplier} > 1.0"
        assert v.size_multiplier >= 0.0


def test_el_dimensionamiento_rechaza_un_multiplicador_mayor_a_uno():
    with pytest.raises(ValueError, match="martingala"):
        atr_position_size(100_000, 100.0, 97.0, 1.5, RiskConfig(), size_multiplier=1.01)


def test_perder_nunca_agranda_la_proxima_posicion():
    """Simulacion directa: tras cada perdida el tamano permitido no puede subir."""
    cfg = RiskConfig()
    st = mk()
    prev_qty = None
    equity = 100_000.0
    for _ in range(8):
        v = cb.evaluate(st, cfg)
        if not v.can_open:
            break
        r = atr_position_size(equity, 100.0, 97.0, 1.5, cfg, size_multiplier=v.size_multiplier)
        if prev_qty is not None:
            assert r.qty <= prev_qty + 1e-9, "el tamano AUMENTO despues de perder"
        prev_qty = r.qty
        equity *= 0.985
        st.mark_to_market(equity)
        st.register_close(-1_000.0)


# ===========================================================================
# Interruptor manual
# ===========================================================================

def test_el_apagado_manual_gana_sobre_todo():
    st = mk()
    st.kill("prueba", utc(2024, 5, 1))
    v = cb.evaluate(st, RiskConfig())
    assert v.level is cb.BreakerLevel.MANUAL_KILL
    assert not v.can_open and v.size_multiplier == 0.0


# ===========================================================================
# Limites de correlacion y concentracion
# ===========================================================================

def test_el_riesgo_estresado_bloquea_aunque_la_correlacion_historica_sea_baja():
    """
    En crisis todo correlaciona a 1. El limite que decide es el estresado,
    no el observado -- aunque el observado diga que esta todo bien.
    """
    cfg = RiskConfig()
    pos = tuple(
        Position(f"S{i}", Side.LONG, 100, 100.0, 97.0, 97.0, utc(2024, 1, 2), "t", sector=f"SEC{i}")
        for i in range(3)
    )
    wc = {p.symbol: 1_400.0 for p in pos}       # 4.2% acumulado
    v = check_limits(
        symbol="NUEVO", sector="OTRO", entry_price=100.0, qty=10, worst_case_loss=1_000.0,
        positions=pos, position_worst_cases=wc, equity=100_000.0, cfg=cfg,
        correlations={p.symbol: 0.05 for p in pos},   # correlacion historica casi nula
    )
    assert not v.allowed
    assert any(b.code == "RIESGO_ESTRESADO" for b in v.breaches)
    assert v.stressed_risk_pct > v.normal_risk_pct


def test_limite_de_concentracion_por_sector():
    cfg = RiskConfig()
    pos = (
        Position("A", Side.LONG, 150, 100.0, 97.0, 97.0, utc(2024, 1, 2), "t", sector="TEC"),
        Position("B", Side.LONG, 140, 100.0, 97.0, 97.0, utc(2024, 1, 2), "t", sector="TEC"),
    )
    v = check_limits(
        symbol="C", sector="TEC", entry_price=100.0, qty=100, worst_case_loss=500.0,
        positions=pos, position_worst_cases={"A": 400.0, "B": 400.0},
        equity=100_000.0, cfg=cfg, correlations={},
    )
    assert not v.allowed
    assert any(b.code == "PESO_POR_SECTOR" for b in v.breaches)


def test_maximo_de_posiciones_simultaneas():
    cfg = RiskConfig()
    pos = tuple(
        Position(f"S{i}", Side.LONG, 10, 100.0, 97.0, 97.0, utc(2024, 1, 2), "t", sector=f"S{i}")
        for i in range(cfg.max_positions)
    )
    v = check_limits(
        symbol="X", sector="OTRO", entry_price=100.0, qty=10, worst_case_loss=100.0,
        positions=pos, position_worst_cases={p.symbol: 100.0 for p in pos},
        equity=1_000_000.0, cfg=cfg, correlations={},
    )
    assert not v.allowed and v.max_qty == 0.0


# ===========================================================================
# Kelly
# ===========================================================================

def test_kelly_no_opera_con_muestra_chica_ni_sin_ventaja():
    cfg = RiskConfig()
    f, note = fractional_kelly(0.60, 3.0, 1.0, cfg, n_trades=15)
    assert f == 0.0 and "minimo 30" in note

    f, note = fractional_kelly(0.20, 2.0, 1.0, cfg, n_trades=100)
    assert f == 0.0 and "no tiene ventaja" in note


def test_kelly_nunca_supera_el_techo_de_riesgo_por_trade():
    cfg = RiskConfig()
    for wr in (0.4, 0.5, 0.6, 0.7, 0.9):
        f, _ = fractional_kelly(wr, 5.0, 1.0, cfg, n_trades=200)
        assert f <= cfg.risk_per_trade_pct + 1e-12


# ===========================================================================
# Stress testing
# ===========================================================================

def test_el_stress_muestra_que_el_gap_cuesta_mas_que_el_stop():
    cfg = RiskConfig()
    book = [Position("SPY", Side.LONG, 120, 420.0, 408.0, 408.0, utc(2024, 1, 2), "t", sector="INDICE")]
    res = run_all(book, 100_000.0, cfg)
    covid = next(r for r in res if r.scenario.name == "COVID_MARZO_2020")
    assert covid.loss_pct > covid.planned_loss_pct, (
        "el stress test dice que el gap NO cuesta mas que el stop: el modelo esta regalando proteccion"
    )
    assert any(p.stop_jumped for p in covid.per_position)


def test_un_libro_sobredimensionado_no_sobrevive():
    cfg = RiskConfig()
    grande = [
        Position(f"S{i}", Side.LONG, 900, 100.0, 94.0, 94.0, utc(2024, 1, 2), "t", sector=f"S{i}")
        for i in range(6)
    ]
    ok, msg = survives_all(run_all(grande, 100_000.0, cfg))
    assert not ok, "un libro de este tamano deberia fallar el stress test"
    assert "NO sobrevive" in msg
