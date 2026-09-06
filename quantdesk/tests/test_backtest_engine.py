"""
Integracion: el motor de backtest completo, de punta a punta.

Verifica que la corrida entera respete las reglas, no solo las piezas sueltas.
La auditoria anti-look-ahead corre DENTRO del motor en cada rueda; si se
dispara, `run()` levanta y el test falla.
"""
from __future__ import annotations

import pytest

from conftest import SMALL_SYMBOLS

from qtdesk.backtest import metrics as met
from qtdesk.backtest.engine import BacktestEngine
from qtdesk.contracts import Action, Side
from qtdesk.engine.decision import DecisionEngine, EngineDeps
from qtdesk.learning.journal import Journal
from qtdesk.learning.review import ReviewLedger, review_trade
from qtdesk.risk.frequency import FrequencyGovernor


@pytest.fixture(scope="module")
def corrida(request):
    world = request.getfixturevalue("world")
    bundle = request.getfixturevalue("bundle")
    from qtdesk.config import SystemConfig
    cfg = SystemConfig()
    gov = FrequencyGovernor(cfg.frequency)
    eng = DecisionEngine(cfg, EngineDeps.default(freq_governor=gov))
    bt = BacktestEngine(cfg, eng, record_all_decisions=False)
    res = bt.run(bundle, world.sessions, list(SMALL_SYMBOLS),
                 initial_equity=100_000.0, warmup=300, freq_governor=gov)
    return cfg, res


def test_la_corrida_termina_sin_violaciones_de_look_ahead(corrida):
    _, res = corrida
    assert res.audit_violations == [], f"look-ahead detectado: {res.audit_violations}"
    assert res.evaluations > 500, "el motor apenas evaluo: revisar el warmup"


def test_la_curva_de_capital_es_coherente(corrida):
    _, res = corrida
    assert len(res.equity_curve) > 100
    ts = [t for t, _ in res.equity_curve]
    assert ts == sorted(ts), "la curva de capital no esta ordenada en el tiempo"
    assert all(v > 0 for _, v in res.equity_curve), "capital no positivo"


def test_toda_entrada_ejecuta_despues_de_su_senal(corrida):
    """Ningun fill de entrada puede ocurrir en la barra de la senal."""
    _, res = corrida
    entradas = [f for f in res.fills if f.reason.startswith("entrada")]
    for d in res.approved_decisions:
        match = [f for f in entradas if f.symbol == d.symbol and f.ts > d.ts]
        misma = [f for f in entradas if f.symbol == d.symbol and f.ts == d.ts]
        assert not misma, (
            f"{d.symbol}: fill en la MISMA barra de la senal ({d.ts}). Eso es "
            "look-ahead de ejecucion."
        )


def test_toda_posicion_tuvo_stop_desde_el_primer_momento(corrida):
    _, res = corrida
    for d in res.approved_decisions:
        assert d.plan is not None
        assert d.plan.stop_price > 0
        if d.plan.side is Side.LONG:
            assert d.plan.stop_price < d.plan.entry_price
        else:
            assert d.plan.stop_price > d.plan.entry_price


def test_ninguna_operacion_rompe_el_limite_de_riesgo_por_trade(corrida):
    cfg, res = corrida
    for d in res.approved_decisions:
        assert d.plan.risk_pct_of_equity <= cfg.risk.max_risk_per_trade_pct + 1e-9, (
            f"{d.symbol} arriesga {d.plan.risk_pct_of_equity:.3%}, por encima del techo"
        )


def test_toda_operacion_lleva_falsacion_explicita_y_plazo(corrida):
    _, res = corrida
    for d in res.approved_decisions:
        assert d.falsification.strip(), "operacion sin falsacion escrita"
        assert d.falsification_deadline is not None, "falsacion sin plazo"
        assert d.falsification_deadline > d.ts


def test_la_asimetria_minima_se_respeta_en_toda_operacion(corrida):
    cfg, res = corrida
    for d in res.approved_decisions:
        assert d.plan.rr_ratio >= cfg.risk.min_rr_ratio - 1e-9


def test_las_metricas_se_calculan_y_reportan_las_perdidas(corrida):
    _, res = corrida
    m = met.compute(res.equity_curve, res.trades)
    texto = met.render(m)
    assert "PERDIDAS" in texto
    assert texto.index("PERDIDAS") < texto.index("RENDIMIENTO"), \
        "las perdidas deben reportarse ANTES que el rendimiento"
    assert m.max_drawdown >= 0.0


def test_el_journal_congela_las_decisiones_y_la_cadena_cierra(corrida, tmp_path):
    _, res = corrida
    j = Journal(tmp_path / "j.jsonl")
    for d in res.approved_decisions:
        j.record_decision(d)
    ok, detail = j.verify()
    assert ok, detail
    for d in res.approved_decisions:
        assert j.decision_for(d.fingerprint()) is not None


def test_la_revision_clasifica_en_la_matriz_de_cuatro_casillas(corrida):
    _, res = corrida
    led = ReviewLedger()
    por_huella = {d.fingerprint()[:12]: d for d in res.approved_decisions}
    for t in res.trades:
        d = por_huella.get(t.decision_fingerprint[:12])
        if d is None:
            continue
        r = review_trade(d, t)
        led.add(r)
        assert r.quadrant.startswith(("1_", "2_", "3_", "4_"))
        assert r.action
    if led.reviews:
        assert 0.0 <= led.luck_ratio() <= 1.0
        assert 0.0 <= led.model_gap_rate() <= 1.0


def test_el_embudo_de_rechazos_queda_registrado(corrida):
    """
    Registrar POR QUE no se opero es tan importante como registrar por que si.
    Sin esto no se puede responder "por que estuvimos afuera todo marzo".
    """
    _, res = corrida
    assert res.blocked_counts, "no se registro ningun motivo de rechazo"
    total = sum(res.blocked_counts.values())
    assert total > res.evaluations * 0.5, (
        "la mayoria de las evaluaciones deberia terminar en NO OPERAR: "
        "esa es la posicion por defecto del sistema"
    )
