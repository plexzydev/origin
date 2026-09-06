"""
Validacion metodologica: purga con embargo, integridad del journal,
pesimismo de costos y penalizacion por sobreajuste.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from qtdesk.backtest.overfit import (deflated_sharpe, expected_max_sharpe,
                                     parameter_penalty)
from qtdesk.backtest.walkforward import (assert_no_leakage, purged_kfold,
                                         walk_forward)
from qtdesk.config import CostConfig
from qtdesk.contracts import Side, utc
from qtdesk.execution.costs import assert_pessimistic, estimate
from qtdesk.learning.error_book import ErrorBook, ErrorEntry, ErrorKind
from qtdesk.learning.journal import Journal, TamperDetected
from qtdesk.learning.versioning import ChangeRejected, VersionLedger


# ===========================================================================
# Purga con embargo
# ===========================================================================

def test_purged_kfold_no_deja_solapamiento_entre_train_y_test():
    folds = purged_kfold(1000, k=5, label_horizon=20, embargo_pct=0.01)
    assert_no_leakage(folds)
    for f in folds:
        assert not (set(f.train) & set(f.test))


def test_la_purga_elimina_las_observaciones_que_se_solapan_con_el_test():
    """
    Sin purga, la observacion del dia lo-1 con horizonte de 20 dias contiene
    informacion de los primeros 20 dias del test. Se verifica que ninguna
    observacion de entrenamiento pueda alcanzar el test con su etiqueta.
    """
    h = 20
    folds = purged_kfold(1000, k=5, label_horizon=h, embargo_pct=0.0)
    for f in folds:
        lo = f.test[0]
        for j in f.train:
            if j < lo:
                assert j + h < lo, (
                    f"la observacion {j} tiene etiqueta hasta {j+h}, que entra en el "
                    f"test que empieza en {lo}: eso es filtracion temporal"
                )


def test_el_embargo_elimina_las_observaciones_posteriores_al_test():
    folds = purged_kfold(1000, k=5, label_horizon=5, embargo_pct=0.02)
    emb = int(1000 * 0.02)
    for f in folds:
        hi = f.test[-1] + 1
        for j in f.train:
            assert not (hi <= j < hi + emb), (
                f"la observacion {j} esta dentro del embargo posterior al test"
            )
    assert sum(f.embargoed for f in folds) > 0, "el embargo no elimino nada"


def test_walk_forward_deja_hueco_igual_al_horizonte_de_etiqueta():
    w = walk_forward(1000, train_size=400, test_size=100, label_horizon=20)
    assert w
    for win in w:
        assert win.test_start - win.train_end == 20
        assert win.train_end <= win.test_start


# ===========================================================================
# Journal: deteccion de manipulacion
# ===========================================================================

def test_el_journal_detecta_modificacion_de_un_registro(tmp_path):
    j = Journal(tmp_path / "j.jsonl")
    for i in range(5):
        j.append("DECISION", utc(2024, 1, i + 1), {"score": i, "tesis": f"t{i}"})
    ok, _ = j.verify()
    assert ok

    # Alguien "recuerda" haber tenido mas conviccion de la que anoto
    j.entries[2] = type(j.entries[2])(
        seq=j.entries[2].seq, ts=j.entries[2].ts, kind=j.entries[2].kind,
        payload={"score": 99, "tesis": "yo sabia que iba a pasar"},
        prev_hash=j.entries[2].prev_hash, entry_hash=j.entries[2].entry_hash,
    )
    ok, detail = j.verify()
    assert not ok and "ALTERADO" in detail
    with pytest.raises(TamperDetected):
        j.assert_intact()


def test_el_journal_detecta_borrado_de_un_registro(tmp_path):
    j = Journal(tmp_path / "j.jsonl")
    for i in range(5):
        j.append("DECISION", utc(2024, 1, i + 1), {"n": i})
    del j.entries[2]          # se borra una operacion incomoda
    ok, detail = j.verify()
    assert not ok
    assert "secuencia rota" in detail or "cadena rota" in detail


def test_el_journal_persiste_y_recarga_intacto(tmp_path):
    p = tmp_path / "j.jsonl"
    j = Journal(p)
    for i in range(10):
        j.append("DECISION", utc(2024, 2, i + 1), {"n": i})
    j2 = Journal(p)
    assert len(j2.entries) == 10
    ok, _ = j2.verify()
    assert ok


# ===========================================================================
# Reglas de cambio de la CAPA 6
# ===========================================================================

def test_no_se_puede_cambiar_un_peso_con_muestra_chica(tmp_path):
    led = VersionLedger(tmp_path / "v.jsonl")
    with pytest.raises(ChangeRejected, match="minimo 30"):
        led.propose({"peso_tecnico": (0.30, 0.33)}, "corazonada",
                    [0.1] * 10, [0.2] * 10, out_of_sample_validated=True, now=utc(2024, 5, 1))


def test_no_se_puede_aflojar_un_limite_de_riesgo_nunca(tmp_path):
    led = VersionLedger(tmp_path / "v.jsonl")
    import random
    rng = random.Random(3)
    before = [rng.gauss(0.0, 0.1) for _ in range(60)]
    after = [b + 0.35 for b in before]
    with pytest.raises(ChangeRejected, match="AFLOJA"):
        led.propose({"risk_per_trade_pct": (0.0075, 0.008)},
                    "el sistema anda bien, subamos el riesgo",
                    before, after, out_of_sample_validated=True, now=utc(2024, 5, 1))


def test_si_se_puede_apretar_un_limite_de_riesgo(tmp_path):
    led = VersionLedger(tmp_path / "v.jsonl")
    import random
    rng = random.Random(5)
    before = [rng.gauss(0.0, 0.1) for _ in range(60)]
    after = [b + 0.4 for b in before]
    v = led.propose({"risk_per_trade_pct": (0.0075, 0.0070)}, "mas conservador",
                    before, after, out_of_sample_validated=True, now=utc(2024, 5, 1))
    assert v.number == 1 and v.evidence.significant


def test_no_se_puede_mover_un_parametro_mas_del_maximo_por_revision(tmp_path):
    led = VersionLedger(tmp_path / "v.jsonl", max_move_pct=0.20)
    import random
    rng = random.Random(11)
    before = [rng.gauss(0.0, 0.1) for _ in range(60)]
    after = [b + 0.4 for b in before]
    with pytest.raises(ChangeRejected, match="movimiento"):
        led.propose({"umbral": (55.0, 80.0)}, "salto grande",
                    before, after, out_of_sample_validated=True, now=utc(2024, 5, 1))


def test_no_se_puede_cambiar_sin_significancia_estadistica(tmp_path):
    led = VersionLedger(tmp_path / "v.jsonl")
    import random
    rng = random.Random(13)
    before = [rng.gauss(0.0, 0.5) for _ in range(60)]
    after = [rng.gauss(0.0, 0.5) for _ in range(60)]     # sin diferencia real
    with pytest.raises(ChangeRejected, match="significativo"):
        led.propose({"umbral": (55.0, 54.0)}, "parece mejor",
                    before, after, out_of_sample_validated=True, now=utc(2024, 5, 1))


def test_no_se_puede_pasar_a_produccion_sin_validacion_fuera_de_muestra(tmp_path):
    led = VersionLedger(tmp_path / "v.jsonl")
    import random
    rng = random.Random(17)
    before = [rng.gauss(0.0, 0.1) for _ in range(60)]
    after = [b + 0.4 for b in before]
    with pytest.raises(ChangeRejected, match="out-of-sample"):
        led.propose({"umbral": (55.0, 54.0)}, "mejora clara",
                    before, after, out_of_sample_validated=False, now=utc(2024, 5, 1))


# ===========================================================================
# Costos
# ===========================================================================

def test_los_costos_van_siempre_en_contra():
    cfg = CostConfig()
    compra = estimate(cfg, side=Side.LONG, reference_price=100.0, qty=100)
    venta = estimate(cfg, side=Side.SHORT, reference_price=100.0, qty=100)
    assert compra.effective_price > 100.0, "comprar deberia ejecutar mas caro"
    assert venta.effective_price < 100.0, "vender deberia ejecutar mas barato"


def test_salir_por_stop_cuesta_mas_que_una_salida_normal():
    cfg = CostConfig()
    normal = estimate(cfg, side=Side.SHORT, reference_price=100.0, qty=100)
    por_stop = estimate(cfg, side=Side.SHORT, reference_price=100.0, qty=100, is_stop=True)
    assert por_stop.slippage_bps > normal.slippage_bps * 2


def test_el_slippage_crece_con_la_volatilidad_y_cae_con_el_volumen():
    cfg = CostConfig()
    base = estimate(cfg, side=Side.LONG, reference_price=100.0, qty=100)
    volatil = estimate(cfg, side=Side.LONG, reference_price=100.0, qty=100, atr=3.0, avg_atr=1.0)
    ilíquido = estimate(cfg, side=Side.LONG, reference_price=100.0, qty=100, volume_ratio=0.3)
    assert volatil.slippage_bps > base.slippage_bps
    assert ilíquido.slippage_bps > base.slippage_bps


def test_la_guardia_de_pesimismo_rechaza_costos_optimistas():
    cfg = CostConfig()
    assert_pessimistic(cfg, observed_slippage_bps=1.0)     # modelo mas caro: OK
    with pytest.raises(ValueError, match="MAS BARATO"):
        assert_pessimistic(cfg, observed_slippage_bps=20.0)


# ===========================================================================
# Sobreajuste
# ===========================================================================

def test_el_sharpe_desinflado_rechaza_lo_que_el_azar_produce():
    v = deflated_sharpe(1.4, n_trials=200, n_obs=1500)
    assert not v.credible
    assert v.observed_sharpe < v.expected_max_sharpe_by_chance


def test_mas_intentos_exigen_mas_sharpe():
    assert expected_max_sharpe(10) < expected_max_sharpe(100) < expected_max_sharpe(1000)


def test_la_penalizacion_por_parametros_castiga_muestras_chicas():
    f_pocos, nota = parameter_penalty(n_params=10, n_trades=50)
    f_muchos, _ = parameter_penalty(n_params=10, n_trades=600)
    assert f_pocos < f_muchos
    assert "memorizando" in nota


# ===========================================================================
# Libro de errores
# ===========================================================================

def test_el_libro_de_errores_encuentra_situaciones_parecidas(tmp_path):
    book = ErrorBook(tmp_path / "e.jsonl")
    book.add(ErrorEntry(
        id="E1", created_at=utc(2024, 1, 15), kind=ErrorKind.PROCESS,
        title="movi el stop en contra",
        description="entre en tecnologia con el credito ampliandose",
        conditions={"regimen": "CONTRACCION/RISK_OFF", "sector": "TECNOLOGIA", "drawdown": 0.05},
        correction="prohibir aperturas con HY ampliando",
    ))
    m = book.similar({"regimen": "CONTRACCION/RISK_OFF", "sector": "TECNOLOGIA", "drawdown": 0.055})
    assert m and m[0][1] >= 0.5
    assert not book.similar({"regimen": "EXPANSION/RISK_ON", "sector": "ENERGIA", "drawdown": 0.0})
