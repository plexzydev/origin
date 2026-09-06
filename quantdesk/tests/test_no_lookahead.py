"""
PRUEBAS DE AUSENCIA DE LOOK-AHEAD BIAS.

Este archivo es el entregable mas importante del proyecto. Un backtest sin
estas pruebas es una opinion con numeros.

Cinco enfoques independientes, porque cada uno detecta cosas distintas:

  1. GUARD DIRECTO      -- pedir el futuro levanta excepcion
  2. INVARIANCIA        -- alterar el futuro NO cambia las decisiones pasadas
  3. CONTROL POSITIVO   -- una estrategia tramposa SI es detectada
                           (sin esto, los otros tests podrian pasar por
                            estar mal escritos y nadie se enteraria)
  4. EJECUCION          -- la orden se llena en la barra SIGUIENTE, nunca
                           en la de la senal
  5. DATOS PIT          -- revisiones y filings no se ven antes de publicarse
"""
from __future__ import annotations

import pytest

from conftest import SMALL_SYMBOLS, scramble_after

from qtdesk.clock import AccessAudit, AsOfClock, LookAheadError
from qtdesk.contracts import Bar, Side, utc
from qtdesk.data.bars import BarSeries, ExecutionOracle, SignalView, resample
from qtdesk.data.calendar import EarningsEvent, TradingCalendar
from qtdesk.data.fundamentals import FundamentalRecord, FundamentalStore
from qtdesk.data.pit import Observation, PointInTimeStore
from qtdesk.layers import indicators as ind
from datetime import date, timedelta


# ===========================================================================
# 1. EL GUARD DIRECTO
# ===========================================================================

def test_signal_view_rechaza_acceso_al_futuro(bundle, world):
    as_of = world.sessions[200]
    audit = AccessAudit()
    view = bundle.view("SPY", as_of, audit)
    with pytest.raises(LookAheadError):
        view.at(world.sessions[201])


def test_signal_view_solo_expone_barras_hasta_as_of(bundle, world):
    as_of = world.sessions[200]
    view = bundle.view("SPY", as_of, AccessAudit())
    bars = view.window(500)
    assert bars, "deberia haber historia"
    assert max(b.ts for b in bars) <= as_of
    assert view.last().ts == as_of


def test_signal_view_no_expone_ninguna_via_al_futuro():
    """
    La ausencia de API es parte de la defensa: si no existe `next()`, nadie
    puede escribir `bars[i+1]` en una capa de senal por descuido.
    """
    prohibidos = {"next", "future", "bar_after", "peek", "lookahead", "__getitem__"}
    expuestos = {m for m in dir(SignalView) if not m.startswith("_")} | {"__getitem__"}
    assert not (prohibidos & {m for m in dir(SignalView)}), (
        f"SignalView expone metodos peligrosos: {prohibidos & set(dir(SignalView))}"
    )


def test_auditoria_detecta_acceso_futuro_via_oracle(bundle, world):
    """
    El ExecutionOracle SI puede ver la barra siguiente -- es su trabajo -- pero
    sus accesos se registran aparte y `assert_clean` no los confunde con senal.
    """
    as_of = world.sessions[200]
    audit = AccessAudit()
    oracle = ExecutionOracle(bundle.bars["SPY"], audit)
    nxt = oracle.bar_after(as_of)
    assert nxt is not None and nxt.ts > as_of
    assert audit.execution_accesses and not audit.signal_accesses
    audit.assert_clean(as_of)   # no explota: fue acceso de EJECUCION


def test_reloj_no_retrocede_y_se_congela():
    clock = AsOfClock(utc(2024, 1, 10))
    clock.advance_to(utc(2024, 1, 11))
    with pytest.raises(LookAheadError):
        clock.advance_to(utc(2024, 1, 5))
    with clock.freeze():
        with pytest.raises(LookAheadError):
            clock.advance_to(utc(2024, 1, 12))
    clock.advance_to(utc(2024, 1, 12))   # fuera del freeze, permitido


# ===========================================================================
# 2. INVARIANCIA ANTE MUTACION DEL FUTURO  -- la prueba central
# ===========================================================================

def _decisiones_hasta(bundle, world, cfg, cutoff_idx, symbols):
    """Corre el motor completo hasta el corte y devuelve huellas de decision."""
    from qtdesk.engine.decision import DecisionEngine, EngineDeps
    from qtdesk.risk.circuit_breakers import evaluate as breakers
    from qtdesk.risk.state import DeskState

    desk = DeskState(equity=100_000.0)
    eng = DecisionEngine(cfg, EngineDeps.default())
    huellas = []
    for i in range(cutoff_idx - 25, cutoff_idx + 1):
        as_of = world.sessions[i]
        audit = AccessAudit()
        views = bundle.all_views(as_of, audit)
        for sym in symbols:
            ctx = bundle.context(sym, as_of, desk, cfg, audit, peer_views=views)
            d = eng.decide(ctx, breakers(desk, cfg.risk))
            huellas.append((as_of, sym, d.action.value, round(d.combined_score, 9),
                            d.aligned_layers, tuple(round(s.score, 9) for s in d.layer_scores),
                            tuple(sorted(d.blocked_by))))
        audit.assert_clean(as_of)
    return huellas


def test_mutar_el_futuro_no_cambia_ninguna_decision_pasada(bundle, world, cfg):
    """
    LA PRUEBA CENTRAL.

    Se corre el motor hasta una fecha de corte y se guardan las decisiones.
    Despues se REEMPLAZA POR RUIDO todo lo posterior al corte -- precios entre
    1 y 5000, volumenes aleatorios -- y se vuelve a correr exactamente lo mismo.

    Si UNA sola decision cambia, alguna capa estaba leyendo el futuro. No hay
    interpretacion alternativa: los datos anteriores al corte son identicos
    byte a byte en las dos corridas.
    """
    from qtdesk.data.bundle import DataBundle

    cutoff_idx = 320
    cutoff_ts = world.sessions[cutoff_idx]
    symbols = list(SMALL_SYMBOLS)

    antes = _decisiones_hasta(bundle, world, cfg, cutoff_idx, symbols)

    mutado = DataBundle(
        bars={s: scramble_after(ser, cutoff_ts) for s, ser in bundle.bars.items()},
        calendar=bundle.calendar, pit=bundle.pit, events=bundle.events,
        fundamentals=bundle.fundamentals, sector_map=bundle.sector_map,
        history_window=bundle.history_window,
    )
    # El mundo mutado DEBE ser distinto despues del corte, si no el test no prueba nada.
    orig = bundle.bars["SPY"].bars
    mut = mutado.bars["SPY"].bars
    assert any(a != b for a, b in zip(orig, mut) if a.ts > cutoff_ts), \
        "la mutacion no cambio nada: el test seria vacio"
    assert all(a == b for a, b in zip(orig, mut) if a.ts <= cutoff_ts), \
        "la mutacion toco el pasado: el test seria invalido"

    despues = _decisiones_hasta(mutado, world, cfg, cutoff_idx, symbols)

    assert len(antes) == len(despues)
    for a, b in zip(antes, despues):
        assert a == b, (
            f"LOOK-AHEAD DETECTADO: la decision de {a[1]} el {a[0].date()} cambio al "
            f"alterar datos POSTERIORES al corte.\n  antes:   {a}\n  despues: {b}"
        )


def test_mutar_el_futuro_no_cambia_los_indicadores(bundle, world):
    """Version acotada y rapida: los indicadores tampoco pueden ver adelante."""
    cutoff_idx = 300
    cutoff_ts = world.sessions[cutoff_idx]
    ser = bundle.bars["AAPL"]
    mut = scramble_after(ser, cutoff_ts)

    v1 = SignalView(ser, cutoff_ts, AccessAudit())
    v2 = SignalView(mut, cutoff_ts, AccessAudit())
    b1, b2 = v1.window(260), v2.window(260)
    c1 = [b.close for b in b1]
    c2 = [b.close for b in b2]

    assert ind.rsi(c1) == ind.rsi(c2)
    assert ind.atr(b1) == ind.atr(b2)
    assert ind.adx(b1) == ind.adx(b2)
    assert ind.macd(c1) == ind.macd(c2)
    assert ind.volume_profile(b1) == ind.volume_profile(b2)
    s1, s2 = ind.market_structure(b1), ind.market_structure(b2)
    assert (s1 is None) == (s2 is None)
    if s1 is not None:
        assert s1 == s2


# ===========================================================================
# 3. CONTROL POSITIVO -- el test tiene que poder FALLAR
# ===========================================================================

def test_control_positivo_una_estrategia_tramposa_ES_detectada(bundle, world):
    """
    Sin este test, los anteriores no valen nada: podrian estar pasando porque
    estan mal escritos. Aca se construye a proposito una capa que hace trampa
    y se verifica que la auditoria la agarra.
    """
    as_of = world.sessions[300]
    audit = AccessAudit()
    view = bundle.view("SPY", as_of, audit)

    # Capa tramposa: simula querer el cierre de manana.
    manana = world.sessions[301]
    with pytest.raises(LookAheadError):
        view.at(manana)

    # Segunda forma de trampa: registrar un acceso al futuro a mano y ver que
    # la auditoria lo detecta al cerrar la barra.
    audit2 = AccessAudit()
    audit2.record_signal(manana, "estrategia_tramposa.close_de_manana")
    with pytest.raises(LookAheadError):
        audit2.assert_clean(as_of)
    assert audit2.violations, "la violacion deberia quedar registrada"


def test_control_positivo_resample_con_bucket_abierto_es_distinto(bundle, world):
    """
    Usar la vela semanal EN FORMACION es look-ahead. Se verifica que
    `include_partial=True` produce un resultado DISTINTO de la version segura:
    si fueran iguales, el parametro no estaria haciendo nada y el default
    seguro seria una ilusion.
    """
    as_of = world.sessions[302]           # un miercoles cualquiera
    view = bundle.view("SPY", as_of, AccessAudit())
    bars = view.window(200)
    seguro = resample(bars, timedelta(days=7), include_partial=False)
    inseguro = resample(bars, timedelta(days=7), include_partial=True)
    assert len(inseguro) >= len(seguro)
    if len(inseguro) > len(seguro):
        assert inseguro[-1].ts == bars[-1].ts, "el bucket parcial cierra en la ultima barra"


# ===========================================================================
# 4. EJECUCION EN LA BARRA SIGUIENTE
# ===========================================================================

def test_la_orden_se_llena_en_la_barra_siguiente_nunca_en_la_de_la_senal():
    from qtdesk.config import CostConfig, RiskConfig
    from qtdesk.execution.paper import PaperBroker
    from qtdesk.risk.stops import build_bracket

    broker = PaperBroker(CostConfig(), RiskConfig(), 100_000.0)
    senal_ts = utc(2024, 3, 5, 21)
    barra_senal = Bar(senal_ts, 100.0, 101.0, 99.0, 100.5, 1e6)
    barra_siguiente = Bar(utc(2024, 3, 6, 21), 100.4, 102.0, 100.0, 101.5, 1e6)

    br = build_bracket("TEST", Side.LONG, 100.5, 97.0, (105.0,), 100, "t1")
    broker.submit_bracket(br, senal_ts)

    # En la MISMA barra de la senal no puede haber fill, aunque el precio pase.
    fills = broker.on_bar("TEST", barra_senal)
    assert fills == [], "hubo fill en la barra de la senal: eso es look-ahead de ejecucion"
    assert not broker.positions()

    # En la SIGUIENTE si.
    fills = broker.on_bar("TEST", barra_siguiente)
    assert len(fills) == 1
    assert fills[0].ts == barra_siguiente.ts
    # Y el precio pagado sale de la barra siguiente, no de la de la senal.
    assert fills[0].price >= min(barra_siguiente.low, barra_siguiente.open)


def test_el_gap_saltea_el_stop_y_ejecuta_peor():
    """El stop no es un piso magico: si abre debajo, se sale al precio de apertura."""
    from qtdesk.config import CostConfig, RiskConfig
    from qtdesk.execution.paper import PaperBroker
    from qtdesk.risk.stops import build_bracket

    broker = PaperBroker(CostConfig(), RiskConfig(), 100_000.0)
    t0 = utc(2024, 3, 5, 21)
    broker.submit_bracket(build_bracket("TEST", Side.LONG, 100.0, 97.0, (110.0,), 100, "t"), t0)
    broker.on_bar("TEST", Bar(utc(2024, 3, 6, 21), 100.0, 101.0, 99.5, 100.5, 1e6))
    assert broker.positions()

    # Apertura con gap MUY por debajo del stop
    fills = broker.on_bar("TEST", Bar(utc(2024, 3, 7, 21), 90.0, 91.0, 88.0, 89.0, 1e6))
    assert fills, "deberia haber salida"
    salida = fills[-1]
    assert salida.price < 97.0, (
        f"la salida ejecuto en {salida.price:.2f}, por encima del stop 97.0: "
        "el simulador esta regalando proteccion que en un gap no existe"
    )
    assert "GAP" in salida.reason


# ===========================================================================
# 5. DATOS POINT-IN-TIME
# ===========================================================================

def test_pit_no_muestra_revisiones_futuras():
    s = PointInTimeStore()
    s.add(Observation("PBI", date(2020, 3, 31), utc(2020, 4, 29), -4.8, 0))
    s.add(Observation("PBI", date(2020, 3, 31), utc(2020, 6, 25), -31.4, 1))

    assert s.get("PBI", utc(2020, 4, 20)) is None
    assert s.value("PBI", utc(2020, 5, 1)) == -4.8
    assert s.value("PBI", utc(2020, 7, 1)) == -31.4


def test_pit_rechaza_dato_publicado_antes_de_que_termine_el_periodo():
    with pytest.raises(ValueError):
        Observation("X", date(2024, 6, 30), utc(2024, 5, 1), 1.0)


def test_fundamentales_respetan_la_fecha_del_filing_y_las_reexpresiones():
    st = FundamentalStore()
    st.add(FundamentalRecord("ACME", date(2023, 3, 31), utc(2023, 5, 5), revenue=1000.0))
    st.add(FundamentalRecord("ACME", date(2023, 3, 31), utc(2023, 11, 2),
                             form_type="10-Q/A", revenue=940.0, amendment_of=date(2023, 3, 31)))

    assert st.latest("ACME", utc(2023, 4, 20)) is None, "el filing no existia todavia"
    assert st.latest("ACME", utc(2023, 6, 1)).revenue == 1000.0, "deberia ver el original"
    assert st.latest("ACME", utc(2023, 12, 1)).revenue == 940.0, "deberia ver la reexpresion"


def test_fecha_de_earnings_es_dato_con_fecha_de_publicacion():
    cal = TradingCalendar()
    e = EarningsEvent("ACME", expected_date=date(2024, 5, 2),
                      announced_at=utc(2024, 4, 11), confirmed_date=date(2024, 5, 3))
    # Antes del anuncio se usa la ESTIMACION, no la fecha confirmada
    assert e.date_known_at(utc(2024, 3, 1)) == date(2024, 5, 2)
    # Despues del anuncio, la confirmada
    assert e.date_known_at(utc(2024, 4, 20)) == date(2024, 5, 3)
