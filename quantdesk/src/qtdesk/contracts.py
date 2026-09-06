"""
Vocabulario del sistema. Todos los modulos hablan estos tipos y nada mas.

Regla de diseno: los objetos de decision son INMUTABLES (frozen). Una decision
que se puede editar despues del hecho no es una decision, es una excusa.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


# ---------------------------------------------------------------------------
# Enumeraciones basicas
# ---------------------------------------------------------------------------

class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"

    @property
    def sign(self) -> int:
        return {Side.LONG: 1, Side.SHORT: -1, Side.FLAT: 0}[self]


class Action(str, Enum):
    """El default del sistema. Ver REGLA MADRE."""
    NO_TRADE = "NO_TRADE"
    OPEN_LONG = "OPEN_LONG"
    OPEN_SHORT = "OPEN_SHORT"
    ADD = "ADD"            # tranche adicional, solo con confirmacion
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"


class Role(str, Enum):
    """Las cinco voces. Cada output las lleva separadas y visibles."""
    QUANT = "QUANT"
    MACRO = "MACRO"
    FUNDAMENTAL = "FUNDAMENTAL"
    RISK_OFFICER = "RISK_OFFICER"
    DEVILS_ADVOCATE = "ABOGADO_DEL_DIABLO"


class Severity(str, Enum):
    INFO = "INFO"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return {"INFO": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}[self.value]


class LayerId(str, Enum):
    VETO = "CAPA_0_VETO"
    TECHNICAL = "CAPA_1_TECNICO"
    FUNDAMENTAL = "CAPA_2_FUNDAMENTAL"
    MACRO = "CAPA_3_MACRO"
    POLICY = "CAPA_4_POLITICO"
    POSITIONING = "CAPA_5_POSICIONAMIENTO"


class Cycle(str, Enum):
    EXPANSION = "EXPANSION"
    SLOWDOWN = "DESACELERACION"
    CONTRACTION = "CONTRACCION"
    RECOVERY = "RECUPERACION"
    UNKNOWN = "DESCONOCIDO"


class RiskMode(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    NEUTRAL = "NEUTRAL"


# ---------------------------------------------------------------------------
# Datos de mercado
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Bar:
    """
    Barra OHLCV. `ts` es el instante de CIERRE de la barra.

    Invariante critico: una barra con ts=T solo esta disponible para decidir
    a partir de T. Nunca antes. El guard de data/guard.py lo hace cumplir.
    """
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(f"Barra OHLC incoherente en {self.ts}: {self}")
        if self.low <= 0 or self.volume < 0:
            raise ValueError(f"Barra con precio<=0 o volumen<0 en {self.ts}")

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def typical(self) -> float:
        return (self.high + self.low + self.close) / 3.0


@dataclass(frozen=True, slots=True)
class Quote:
    """Instantanea de libro. Sin esto no se puede evaluar liquidez de verdad."""
    ts: datetime
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        m = self.mid
        return 0.0 if m <= 0 else (self.ask - self.bid) / m * 10_000.0


# ---------------------------------------------------------------------------
# Salida de las capas
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LayerScore:
    """
    Score de una capa en [-100, +100] con justificacion ESCRITA obligatoria.

    `confidence` en [0,1] indica cuanta evidencia real hay detras. Una capa
    sin datos devuelve score=0 y confidence=0 -- nunca inventa una opinion.
    """
    layer: LayerId
    score: float
    confidence: float
    rationale: str
    features: Mapping[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not -100.0 <= self.score <= 100.0:
            raise ValueError(f"{self.layer}: score fuera de rango: {self.score}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"{self.layer}: confidence fuera de rango: {self.confidence}")
        if not self.rationale.strip():
            raise ValueError(f"{self.layer}: score sin justificacion escrita")

    @property
    def sign(self) -> int:
        if self.score > 0:
            return 1
        if self.score < 0:
            return -1
        return 0

    @property
    def effective(self) -> float:
        """Score ponderado por su propia confianza. Poca evidencia, poca voz."""
        return self.score * self.confidence


@dataclass(frozen=True, slots=True)
class VetoReason:
    code: str
    detail: str
    severity: Severity = Severity.CRITICAL


@dataclass(frozen=True, slots=True)
class VetoResult:
    """Resultado de CAPA 0. `passed=False` termina la evaluacion, sin discusion."""
    passed: bool
    reasons: tuple[VetoReason, ...] = ()
    checks_run: int = 0

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(r.code for r in self.reasons)


# ---------------------------------------------------------------------------
# Voces de la mesa
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Voice:
    """
    Intervencion de un rol. Se emite SIEMPRE, tambien cuando no hay operacion:
    el sistema debe justificar por que SI entra, y dejar constancia de por que no.
    """
    role: Role
    verdict: str          # texto corto: "APRUEBA" / "VETA" / "NEUTRAL" / ...
    message: str          # argumento completo


# ---------------------------------------------------------------------------
# Escenarios
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Scenario:
    """Un camino posible. `r_multiple` es el payoff en unidades de R (=riesgo inicial)."""
    name: str
    probability: float
    r_multiple: float
    description: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError(f"Probabilidad invalida en escenario {self.name}")


@dataclass(frozen=True, slots=True)
class ScenarioTree:
    scenarios: tuple[Scenario, ...]

    def __post_init__(self) -> None:
        if not 3 <= len(self.scenarios) <= 5:
            raise ValueError("El arbol de escenarios exige entre 3 y 5 caminos")
        total = sum(s.probability for s in self.scenarios)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Las probabilidades suman {total:.4f}, no 1.0")

    @property
    def expected_r(self) -> float:
        return sum(s.probability * s.r_multiple for s in self.scenarios)

    @property
    def worst(self) -> Scenario:
        return min(self.scenarios, key=lambda s: s.r_multiple)

    @property
    def best(self) -> Scenario:
        return max(self.scenarios, key=lambda s: s.r_multiple)


@dataclass(frozen=True, slots=True)
class Argument:
    """Argumento del Abogado del Diablo. Si no se refuta con datos, no hay trade."""
    claim: str
    severity: Severity
    evidence: str
    refuted_by: str | None = None   # None = EN PIE

    @property
    def standing(self) -> bool:
        return self.refuted_by is None


# ---------------------------------------------------------------------------
# Ordenes y posiciones
# ---------------------------------------------------------------------------

class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"


@dataclass(frozen=True, slots=True)
class Order:
    symbol: str
    side: Side
    qty: float
    order_type: OrderType
    limit_price: float | None = None
    stop_price: float | None = None
    tag: str = ""

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError("Orden con cantidad no positiva")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("Orden limite sin precio limite")
        if self.order_type is OrderType.STOP and self.stop_price is None:
            raise ValueError("Orden stop sin precio de disparo")


@dataclass(frozen=True, slots=True)
class BracketOrder:
    """
    Entrada + stop protectivo + objetivos, en un solo paquete indivisible.

    Regla inviolable: `entry` nunca viaja sola. El constructor lo garantiza,
    por eso no existe forma de crear una entrada sin su salida protectora.
    """
    entry: Order
    stop: Order
    targets: tuple[Order, ...]
    thesis_id: str

    def __post_init__(self) -> None:
        if self.stop.qty < self.entry.qty - 1e-9:
            raise ValueError("El stop no cubre la totalidad de la entrada")
        if self.entry.side is Side.LONG and self.stop.stop_price >= self._entry_ref():
            raise ValueError("Stop de un largo por encima de la entrada")
        if self.entry.side is Side.SHORT and self.stop.stop_price <= self._entry_ref():
            raise ValueError("Stop de un corto por debajo de la entrada")

    def _entry_ref(self) -> float:
        return self.entry.limit_price if self.entry.limit_price is not None else 0.0


@dataclass(frozen=True, slots=True)
class Fill:
    ts: datetime
    symbol: str
    side: Side
    qty: float
    price: float
    commission: float
    slippage_bps: float
    reason: str = ""


@dataclass(slots=True)
class Position:
    """Mutable a proposito: es estado vivo, no un registro historico."""
    symbol: str
    side: Side
    qty: float
    avg_price: float
    stop_price: float
    initial_stop: float
    opened_at: datetime
    thesis_id: str
    sector: str = "UNKNOWN"
    targets_hit: int = 0
    time_stop_at: datetime | None = None
    r_unit: float = 0.0          # valor monetario de 1R al abrir

    def unrealized(self, price: float) -> float:
        return (price - self.avg_price) * self.qty * self.side.sign

    def r_now(self, price: float) -> float:
        if self.r_unit <= 0:
            return 0.0
        return self.unrealized(price) / self.r_unit


@dataclass(frozen=True, slots=True)
class AccountState:
    ts: datetime
    equity: float
    cash: float
    positions: tuple[Position, ...] = ()

    @property
    def gross_exposure(self) -> float:
        return sum(abs(p.qty * p.avg_price) for p in self.positions)


# ---------------------------------------------------------------------------
# Decision: el objeto central, congelado y hasheable
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TradePlan:
    """Plan completo. Sin stop calculado no se instancia -- validado abajo."""
    symbol: str
    side: Side
    entry_price: float
    stop_price: float
    targets: tuple[float, ...]
    total_qty: float
    tranches: tuple[float, ...]           # entrada escalonada
    risk_pct_of_equity: float
    r_unit_cash: float
    rr_ratio: float
    time_stop: datetime | None
    sector: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if self.stop_price <= 0:
            raise ValueError("Plan sin stop. No se opera sin stop.")
        if not self.targets:
            raise ValueError("Plan sin objetivo: no se puede evaluar asimetria")
        if abs(sum(self.tranches) - self.total_qty) > 1e-6:
            raise ValueError("Los tramos no suman la cantidad total")
        if len(self.tranches) < 2:
            raise ValueError("Entrada escalonada obligatoria: minimo 2 tramos")


@dataclass(frozen=True, slots=True)
class Decision:
    """
    Registro completo e inmutable de una decision. Se congela y se hashea.
    Esto ES el registro previo exigido por CAPA 6.
    """
    ts: datetime
    symbol: str
    action: Action
    regime_cycle: Cycle
    regime_risk: RiskMode
    veto: VetoResult
    layer_scores: tuple[LayerScore, ...]
    weights: Mapping[str, float]
    combined_score: float
    aligned_layers: int
    scenario_tree: ScenarioTree | None
    arguments: tuple[Argument, ...]
    voices: tuple[Voice, ...]
    plan: TradePlan | None
    thesis: str
    falsification: str
    falsification_deadline: datetime | None
    conviction: int                  # 1..5
    conviction_reason: str
    blocked_by: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.conviction <= 5:
            raise ValueError("Conviccion fuera de 1..5")
        roles = {v.role for v in self.voices}
        missing = set(Role) - roles
        if missing:
            raise ValueError(f"Decision sin todas las voces. Faltan: {sorted(r.value for r in missing)}")
        if self.action is not Action.NO_TRADE:
            if self.plan is None:
                raise ValueError("Accion operativa sin plan")
            if not self.falsification.strip():
                raise ValueError("Trade sin falsacion explicita")

    def to_record(self) -> dict[str, Any]:
        """Serializacion estable para el journal (orden de claves fijo)."""
        return json.loads(json.dumps(asdict(self), default=_json_default, sort_keys=True))

    def fingerprint(self) -> str:
        blob = json.dumps(self.to_record(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()


def _json_default(o: Any) -> Any:
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(f"No serializable: {type(o)}")


def utc(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    """Helper: todos los timestamps del sistema son UTC y timezone-aware."""
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)
