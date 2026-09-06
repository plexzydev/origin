"""
Fallas operativas: reconciliacion con el broker, apagado y guard
anti-retrospectiva del featurizer de texto.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from qtdesk.contracts import Position, Side, utc
from qtdesk.execution.broker import BrokerHealth
from qtdesk.execution.reconcile import check_operational, reconcile
from qtdesk.layers.llm_features import (Document, FrozenFeatureStore, HindsightError,
                                        LexiconFeaturizer, MAX_LAYER_WEIGHT,
                                        contribution_weight)


def _pos(sym="SPY", qty=100.0, stop=410.0, side=Side.LONG):
    return Position(sym, side, qty, 420.0, stop, stop, utc(2024, 1, 2), "t")


def test_sin_divergencias_no_hay_apagado():
    p = (_pos(),)
    r = reconcile(p, p)
    assert r.ok and not r.must_kill


def test_cualquier_divergencia_exige_apagado_inmediato():
    for sistema, broker in [
        ((_pos(qty=100),), (_pos(qty=300),)),                    # cantidad
        ((_pos(),), ()),                                          # fantasma
        ((), (_pos(),)),                                          # huerfana
        ((_pos(),), (_pos(side=Side.SHORT),)),                    # lado
        ((_pos(stop=410),), (_pos(stop=390),)),                   # stop distinto
    ]:
        r = reconcile(sistema, broker)
        assert r.must_kill, f"no exigio apagado: {sistema} vs {broker}"


def test_una_posicion_sin_stop_en_el_broker_es_divergencia():
    r = reconcile((_pos(stop=410),), (_pos(stop=0.0),))
    assert any(d.code == "SIN_STOP_EN_BROKER" for d in r.divergences)


def test_stops_en_la_maquina_obligan_a_cerrar_con_posiciones_abiertas():
    h = BrokerHealth(ok=True, latency_ms=1.0, last_heartbeat=utc(2024, 1, 2, 15, 0),
                     stops_at_broker=False, detail="ok")
    o = check_operational(broker_health=h, now=utc(2024, 1, 2, 15, 1),
                          last_data_ts=utc(2024, 1, 2, 15, 0), open_positions=2)
    assert o.must_flatten
    assert any("NO estan del lado del broker" in r for r in o.reasons)


def test_feed_atrasado_con_posiciones_abiertas_obliga_a_cerrar():
    h = BrokerHealth(ok=True, latency_ms=1.0, last_heartbeat=utc(2024, 1, 2, 15, 0),
                     stops_at_broker=True, detail="ok")
    o = check_operational(broker_health=h, now=utc(2024, 1, 2, 15, 30),
                          last_data_ts=utc(2024, 1, 2, 15, 0), open_positions=1)
    assert o.must_flatten and any("atrasado" in r for r in o.reasons)


def test_broker_caido_sin_posiciones_no_obliga_a_cerrar_pero_no_esta_ok():
    h = BrokerHealth(ok=False, latency_ms=0.0, last_heartbeat=None,
                     stops_at_broker=True, detail="sin conexion")
    o = check_operational(broker_health=h, now=utc(2024, 1, 2, 15, 1),
                          last_data_ts=utc(2024, 1, 2, 15, 0), open_positions=0)
    assert not o.ok and not o.must_flatten


# ---------------------------------------------------------------------------

def test_el_store_congelado_rechaza_features_con_retrospectiva():
    st = FrozenFeatureStore(knowledge_cutoff=date(2025, 1, 1), generator="modelo-moderno")
    with pytest.raises(HindsightError, match="corte de conocimiento"):
        st.require_clean(backtest_start=date(2020, 1, 1))


def test_el_store_acepta_un_generador_anterior_al_backtest():
    st = FrozenFeatureStore(knowledge_cutoff=date(2018, 12, 31), generator="modelo-viejo")
    st.require_clean(backtest_start=date(2019, 1, 1))       # no levanta


def test_los_features_no_son_visibles_antes_de_publicarse():
    st = FrozenFeatureStore(knowledge_cutoff=date(2018, 12, 31), generator="x")
    doc = Document("d1", "NOTICIA", utc(2020, 5, 10, 12), "texto")
    st.add(doc, LexiconFeaturizer().featurize(doc))
    assert st.get("d1", utc(2020, 5, 9)) is None
    assert st.get("d1", utc(2020, 5, 11)) is not None


def test_el_lexicon_no_tiene_corte_de_conocimiento():
    """No sabe nada, por lo tanto no puede recordar el futuro."""
    assert LexiconFeaturizer().knowledge_cutoff is None


def test_el_llm_nunca_pesa_mas_que_el_techo():
    doc = Document("d", "NOTICIA", utc(2024, 1, 2), "crecimiento solido y mejora")
    f = LexiconFeaturizer().featurize(doc)
    for pedido in (0.05, 0.30, 0.90):
        assert contribution_weight(f, pedido) <= MAX_LAYER_WEIGHT + 1e-9


def test_el_cambio_de_tono_se_mide_contra_el_documento_anterior():
    lex = LexiconFeaturizer()
    prev = Document("a", "COMUNICADO_BANCO_CENTRAL", utc(2024, 1, 2),
                    "riesgo de recesion, deterioro, debil, contraccion")
    cur = Document("b", "COMUNICADO_BANCO_CENTRAL", utc(2024, 3, 2),
                   "crecimiento solido, mejora, expansion, fuerte", prior_doc_id="a")
    f = lex.featurize(cur, prev)
    assert f.tone > 0 and f.tone_delta_vs_prior > 1.0, "el cambio de tono deberia ser grande"
