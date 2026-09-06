# qtdesk — mesa de trading cuantitativa

**Alcance: backtesting y paper trading ÚNICAMENTE.** El broker vive detrás de una
interfaz abstracta (`execution/broker.py`) y la única implementación que existe en
este árbol es un simulador. No hay, ni va a haber acá, código que envíe órdenes con
dinero real.

---

## Lo primero: qué encontró este sistema al medirse a sí mismo

Antes de la documentación técnica, los tres hallazgos que cambian cómo hay que leer
todo lo demás. Los tres salieron de correr el sistema, no de opinar.

### 1. El ratio riesgo/beneficio no crea esperanza matemática

Sin ventaja demostrada, la probabilidad de tocar +kR antes que −1R es exactamente
1/(1+k) — ruina del jugador. Eso significa que **1:3 con 25% de aciertos y 1,5:1 con
40% valen lo mismo: cero**, antes de costos. Con la fricción real (gaps, tomas
parciales, salidas por tiempo) el valor esperado es negativo para *cualquier* ratio:

| R:R | acierto sin ventaja | acierto para EV=0 | ventaja necesaria |
|-----|--------------------:|------------------:|------------------:|
| 1,5 | 40% | 53% | **+13 pp** |
| 2,0 | 33% | 47% | **+14 pp** |
| 3,0 | 25% | 38% | **+13 pp** |
| 5,0 | 17% | 28% | **+11 pp** |

Ningún ratio hace desaparecer esa brecha. Lo único que la cierra es ventaja real, y
la ventaja **se mide, no se supone**. Por eso el sistema tiene un modo de medición
explícito (abajo).

### 2. Asimetría y frecuencia son aritméticamente incompatibles

Con los límites de riesgo del mandato (4% de riesgo estresado, 0,75% por operación)
entran ~5 posiciones simultáneas. Para 10 operaciones mensuales cada una debe durar
~11 ruedas. El recorrido favorable crece como raíz del tiempo; la distancia al stop
no. Medido sobre datos:

| Plazo de tenencia | R:R mediano alcanzable |
|------------------:|-----------------------:|
| 10 ruedas | 0,88 |
| 20 ruedas | 1,20 |
| 40 ruedas | 1,73 |
| 60 ruedas | 2,23 |

`qtdesk factibilidad` corre este análisis sobre tus datos y devuelve las cuatro
opciones posibles. El sistema **no resuelve la contradicción solo**: la hace visible
y obliga a elegir.

### 3. El sistema opera muy poco, y eso no es un bug

En el mundo sintético de prueba (76 símbolos, 21 meses) el embudo completo da:

```
53%  vetado por CAPA 0  (volatilidad, crédito, eventos macro, earnings, feriados, gaps)
43%  score por debajo del umbral calibrado
 3%  supera el umbral → de esos, 55% muere por contradicción entre capas
                        y la mayor parte del resto por asimetría insuficiente
```

Resultado: **~0,5 operaciones por mes**, no 10. La posición por defecto es NO OPERAR
y el sistema cumple esa regla con una literalidad incómoda.

---

## Arquitectura

```
quantdesk/
├── src/qtdesk/
│   ├── contracts.py          Tipos inmutables. Las reglas inviolables se hacen
│   │                         cumplir por TIPO: BracketOrder no se construye sin
│   │                         stop; Decision no se construye sin las cinco voces.
│   ├── clock.py              AsOfClock monótono + AccessAudit. El look-ahead no se
│   │                         evita con disciplina: se hace imposible.
│   ├── config.py             Todos los umbrales en un lugar. tighten_only() es un
│   │                         trinquete: los límites de riesgo solo se aprietan.
│   ├── stats.py              Estadística mínima sin dependencias (t, bootstrap, corr)
│   ├── regime.py             Detección de régimen + TABLA DE PESOS explícita
│   │
│   ├── data/
│   │   ├── bars.py           BarSeries → SignalView (sellada en as_of, sin API al
│   │   │                     futuro) vs ExecutionOracle (privilegiado, auditado aparte)
│   │   ├── pit.py            PointInTimeStore con vintages + universo sin sesgo
│   │   │                     de supervivencia
│   │   ├── fundamentals.py   Filings con filed_at; respeta reexpresiones
│   │   ├── calendar.py       Sesiones (feriados calculados) + eventos con fecha
│   │   │                     de anuncio. Calendario vacío ≠ "no hay eventos".
│   │   ├── quality.py        Integridad del feed: atraso, huecos, congelado, splits
│   │   ├── policy.py         Eventos políticos con cuatro tiempos (rumor → anuncio →
│   │   │                     vigencia → resultado)
│   │   ├── series.py         Registro de series macro con fuente y revisabilidad
│   │   ├── bundle.py         Frontera datos/sistema. Backtest y paper usan el mismo
│   │   │                     camino de código.
│   │   └── providers/synthetic.py   Mundo determinista para tests y demo
│   │
│   ├── layers/
│   │   ├── base.py           MarketContext (única puerta a datos) + Layer + blend()
│   │   ├── indicators.py     Funciones puras, sin estado, None si falta historia
│   │   ├── veto.py           CAPA 0 — 13 filtros que bloquean todo
│   │   ├── technical.py      CAPA 1 — puerta multi-timeframe + 6 sub-señales
│   │   ├── fundamental.py    CAPA 2 — valuación siempre relativa, sorpresa vs reacción
│   │   ├── macro.py          CAPA 3 — 9 sub-señales; desinversión > inversión
│   │   ├── policy.py         CAPA 4 — impacto NO descontado por fase
│   │   └── positioning.py    CAPA 5 — contraria solo en extremos
│   │
│   ├── engine/
│   │   ├── decision.py       Los 9 pasos + emisión de las cinco voces
│   │   ├── calibration.py    Umbral por percentil, ventana estrictamente pasada
│   │   ├── levels.py         Entrada/stop/objetivo — el objetivo NO sale del stop
│   │   ├── scenarios.py      Árbol de 3-5 caminos anclado en caminata aleatoria
│   │   ├── devils_advocate.py  11 generadores de argumentos con refutación por datos
│   │   ├── risk_officer.py   Veto absoluto; puede reducir tamaño, nunca aumentarlo
│   │   └── feasibility.py    Detecta configuraciones que se contradicen a sí mismas
│   │
│   ├── risk/
│   │   ├── state.py          DeskState: drawdown contra el máximo histórico
│   │   ├── circuit_breakers.py  Cascada diaria/semanal/mensual/racha + escalera DD
│   │   ├── sizing.py         ATR y Kelly/4; reporta el peor caso, no el nominal
│   │   ├── stops.py          Trinquete, breakeven a 1R, parciales, salida por tiempo
│   │   ├── limits.py         Exposición evaluada DOS veces: observada y a corr=1
│   │   ├── stress.py         2008 / marzo 2020 / 2022 / shock inventado, con gaps
│   │   └── frequency.py      Gobernador de cuota con piso duro
│   │
│   ├── execution/
│   │   ├── broker.py         Interfaz abstracta. submit_bracket es la única entrada.
│   │   ├── paper.py          Simulador: barra siguiente, stop antes que objetivo, gaps
│   │   ├── costs.py          Slippage deliberadamente peor que el histórico
│   │   └── reconcile.py      Reconciliación con el broker + kill switch
│   │
│   ├── backtest/
│   │   ├── engine.py         Señal en T, ejecución en T+1. Auditoría por rueda.
│   │   ├── metrics.py        Las PÉRDIDAS se reportan primero, por diseño
│   │   ├── walkforward.py    Purged K-Fold con embargo (López de Prado)
│   │   └── overfit.py        Deflated Sharpe + penalización por parámetros
│   │
│   ├── learning/             CAPA 6
│   │   ├── journal.py        Registro previo congelado, encadenado por hashes
│   │   ├── review.py         Matriz de cuatro casillas
│   │   ├── error_book.py     Libro de errores consultado ANTES de operar
│   │   ├── versioning.py     Reglas de cambio como código que rechaza
│   │   ├── shadow.py         Modo sombra con test de promoción
│   │   ├── degradation.py    Los cinco detectores
│   │   └── reports.py        Informes semanal y mensual
│   │
│   └── cli.py
└── tests/                    97 tests
```

**El núcleo no tiene dependencias.** Decisión deliberada: el motor se prueba contra sí
mismo, no contra la semántica de alineación de índices de pandas — que es una fuente
clásica de look-ahead silencioso vía `.shift()`, `rolling` centrado o `reindex` con
forward-fill.

---

## Uso

```bash
cd quantdesk
python -m pytest tests/ -q                      # 97 tests
PYTHONPATH=src python -m qtdesk.cli demo        # backtest con informe completo
PYTHONPATH=src python -m qtdesk.cli voces --simbolo XLV --sesion 309
PYTHONPATH=src python -m qtdesk.cli embudo      # por qué NO se opera
PYTHONPATH=src python -m qtdesk.cli factibilidad
PYTHONPATH=src python -m qtdesk.cli stress
PYTHONPATH=src python -m qtdesk.cli journal ruta/al/journal.jsonl
```

---

## Cómo se prueba la ausencia de look-ahead

`tests/test_no_lookahead.py` — 15 tests, cinco enfoques independientes:

1. **Guard directo.** `SignalView.at()` con un timestamp futuro levanta
   `LookAheadError`. La clase no expone `next()`, `bar_after()` ni índices absolutos:
   la ausencia de API es parte de la defensa.

2. **Invariancia ante mutación del futuro** — *la prueba central*. Se corre el motor
   completo hasta una fecha de corte y se guardan las decisiones. Después se
   **reemplaza por ruido** todo lo posterior al corte (precios entre 1 y 5000) y se
   vuelve a correr lo mismo. Si una sola decisión cambia, alguna capa leía el futuro.
   No hay interpretación alternativa: los datos anteriores al corte son idénticos.

3. **Control positivo.** Una estrategia deliberadamente tramposa **debe** ser
   detectada. Sin este test los otros no valen nada: podrían estar pasando por estar
   mal escritos.

4. **Ejecución.** Se verifica que un fill nunca ocurra en la barra de la señal, y que
   un gap que abre del otro lado del stop ejecute a la apertura, no al stop.

5. **Datos PIT.** Revisiones del PBI, reexpresiones de balances y fechas de earnings
   no son visibles antes de su publicación.

`tests/test_circuit_breakers.py` — 19 tests que verifican que cada cortafuegos
**efectivamente se dispara**, que no se dispara antes del umbral, y que los que exigen
intervención manual no se liberan solos. Incluye una prueba de la prohibición de
martingala sobre 20.000 estados aleatorios.

---

## LIMITACIONES REALES — qué NO puede saber este sistema

Esta sección es tan importante como el código.

### Sobre los datos

- **No tiene datos point-in-time reales.** El `PointInTimeStore` está construido y
  exige vintages, pero *cargarlos es responsabilidad de quien conecte las fuentes*.
  Con yfinance o series de FRED sin ALFRED, lo que se carga son los valores
  **revisados de hoy**. El backtest será optimista y no hay forma de saber cuánto.
  Este es el punto individual que más infla backtests, y el sistema solo provee la
  estructura, no los datos.

- **No corrige sesgo de supervivencia por sí solo.** `SurvivorshipAwareUniverse`
  existe y avisa si nadie cargó bajas históricas, pero la lista de empresas que
  quebraron o salieron del índice hay que conseguirla y cargarla.

- **No tiene profundidad de libro.** Los vetos de spread y profundidad solo corren si
  se les da un `Quote` real. Sin datos de nivel 2, el veto de liquidez se reduce a
  volumen en dólares y ratio de volumen, y el sistema lo declara en su justificación.

- **No verifica timestamps de noticias.** El módulo de política exige fechas
  explícitas de rumor y anuncio, pero no puede validar que sean correctas. Una fecha
  mal cargada mete look-ahead que ninguna auditoría del sistema detecta.

- **El mundo sintético no es el mercado.** Todos los números de este README salen del
  generador determinista. Sirven para validar la mecánica, no para estimar
  rentabilidad.

### Sobre el riesgo

- **El stop no es una garantía, es una intención.** En un gap se ejecuta al precio que
  haya. El sistema dimensiona asumiendo 2 ATR de deslizamiento y reporta el peor caso,
  pero no puede evitar el gap. El stress test muestra que en un escenario tipo 2008 la
  pérdida real es ~2,5× lo que los stops prometían.

- **Los cortafuegos no limitan la pérdida, limitan cuándo dejás de operar.** Si el
  shock ocurre durante la noche con posiciones abiertas, el cortafuegos se entera
  cuando ya perdiste. Ese es el riesgo residual irreducible y el módulo de stress lo
  imprime en cada corrida.

- **Riesgo cero no existe** y el sistema no lo simula. Lo que entrega es riesgo
  *acotado por construcción* con el peor caso escrito en cada decisión.

- **La reconciliación con el broker es simulada.** En el `PaperBroker`,
  `stops_at_broker` devuelve True trivialmente. Contra un broker real hay que
  verificar que los stops estén efectivamente cargados del lado del broker.

### Sobre el modelo

- **No sabe si tiene ventaja.** Con menos de 30 operaciones comparables el árbol de
  escenarios usa la tasa de acierto teórica sin ventaja, el EV modelado es negativo, y
  el sistema opera en **MODO MEDICIÓN**: tamaño al 22%, presupuesto total de
  aprendizaje del 5% del capital, y cada decisión marcada `VENTAJA_NO_DEMOSTRADA`.
  Esto no es prudencia decorativa: es la consecuencia de no poder afirmar algo que no
  midió.

- **La detección de régimen llega tarde.** El dato macro se publica con rezago y se
  revisa. En noviembre de 2020 el sistema clasificó "contracción" cuando la verdad del
  generador ya era "recuperación" — porque el ISM publicado *ese día* mostraba 27,1.
  El sistema tenía razón dados sus datos, y eso no lo hace útil para atrapar giros.

- **El umbral se calibra sobre las señales del propio sistema.** Si el sistema entero
  está sesgado, el percentil no lo detecta: calibra el sesgo.

- **El árbol de escenarios no predice.** Las probabilidades salen de una tabla
  documentada anclada en caminata aleatoria. Su función es obligar a escribir el peor
  caso antes de entrar, no adivinar el futuro.

- **El LLM como feature no está conectado.** `layers/llm_features.py` define el
  contrato y el guard anti-hindsight, pero no hay adaptador. Y la advertencia de fondo
  sigue en pie: un modelo entrenado después de 2020 **sabe cómo terminó 2020**. Para
  backtest solo sirve con un store de features congelado con fecha de corte
  documentada.

### Sobre la frecuencia

- **No se puede garantizar un número de operaciones por mes.** La cuota baja el umbral
  de convicción hasta un piso duro, pero **nunca** toca los vetos de CAPA 0, el riesgo
  por operación, la asimetría mínima ni los cortafuegos. En un mes donde el mercado no
  ofrece setups, el mes cierra bajo la cuota y el sistema reporta el faltante con su
  motivo. Eso es correcto, no es una falla.

### Lo que el sistema no hace y habría que construir

- Adaptadores reales de datos (yfinance / FRED / EDGAR) — los stubs de
  `data/providers/` están, la implementación no.
- Estructuras de opciones con pérdida máxima acotada, que el mandato prefiere
  explícitamente y son la única vía honesta a un 1:3 estructural.
- Datos intradiarios. Con barras diarias, el "4h define la entrada" del mandato
  degrada a "semanal define sesgo, diario define entrada", y el sistema lo dice en la
  justificación de CAPA 1 en vez de fingir lo contrario.

---

## Reglas que el código hace cumplir (no la documentación)

| Regla | Dónde se hace cumplir |
|---|---|
| Nunca operar sin stop | `BracketOrder.__post_init__`, `TradePlan.__post_init__` |
| Nunca mover un stop en contra | `stops.ratchet()` / `assert_tighter()` — única vía autorizada |
| Nunca aumentar tamaño para recuperar | `circuit_breakers.evaluate()` acota el multiplicador a 1,0; `atr_position_size` levanta excepción |
| Los límites de riesgo solo se aprietan | `SystemConfig.tighten_only()` |
| Mínimo 30 operaciones antes de tocar un peso | `VersionLedger.propose()` |
| Ningún cambio sin significancia ni validación fuera de muestra | `VersionLedger.propose()` |
| Toda decisión lleva las cinco voces | `Decision.__post_init__` |
| Ejecución en la barra siguiente | `PaperBroker.on_bar()` + tests |
| El objetivo no se deriva del stop | `engine/levels.py` + test que verifica dispersión del R:R |

---

## Honestidad obligatoria

El mandato pedía que si algo era imposible se dijera directamente. Tres cosas se
dijeron y están documentadas arriba con números:

1. **1:3 + 10 operaciones/mes + 4% de riesgo estresado** no pueden ser ciertas a la
   vez. Se eligió priorizar frecuencia y se bajó el mínimo a 1,5:1, con la
   consecuencia escrita en `config.py`: el punto de equilibrio pasa de 25% a 40% de
   aciertos.

2. **Ningún R:R crea esperanza matemática por sí solo.** Hace falta ~13 puntos de
   ventaja sobre el azar, y esa ventaja hay que medirla.

3. **Un backtest sin pérdidas es un backtest con un bug.** `metrics.py` levanta una
   advertencia explícita si el profit factor es infinito o si el drawdown máximo es
   menor al 2% con más de 10 operaciones.
