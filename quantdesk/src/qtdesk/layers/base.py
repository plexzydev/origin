"""
Contexto de mercado y contrato comun de las capas.

`MarketContext` es la UNICA puerta de entrada a datos que tienen las capas.
Se construye una vez por decision, ya sellado en `as_of`, y se pasa por valor.
Ninguna capa abre un archivo, hace una request ni consulta una base: si el
dato no esta en el contexto, para esa capa no existe.

Esto tiene un costo (hay que precargar) y una ventaja que lo justifica: el
backtest y el paper trading corren EXACTAMENTE el mismo codigo de analisis.
La unica diferencia entre ambos es quien llena el contexto.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Sequence

from ..config import SystemConfig
from ..contracts import Bar, LayerId, LayerScore, Position, Quote
from ..data.bars import SignalView
from ..data.calendar import EventCalendar, TradingCalendar
from ..data.fundamentals import FundamentalStore
from ..data.pit import PointInTimeStore
from ..risk.state import DeskState


@dataclass(frozen=True, slots=True)
class MarketContext:
    as_of: datetime
    symbol: str
    view: SignalView                                  # barras del simbolo evaluado
    config: SystemConfig
    calendar: TradingCalendar
    desk: DeskState
    peers: Mapping[str, SignalView] = field(default_factory=dict)
    pit: PointInTimeStore | None = None
    events: EventCalendar | None = None
    fundamentals: FundamentalStore | None = None
    quote: Quote | None = None
    open_positions: tuple[Position, ...] = ()
    sector: str = "UNKNOWN"
    sector_map: Mapping[str, str] = field(default_factory=dict)
    # Timeframe superior ya resampleado (semanal o 4h segun granularidad).
    higher_tf: Sequence[Bar] = ()
    higher_tf_label: str = "SEMANAL"
    # Cuando la fuente es diaria y no hay intradiario, el sistema lo dice en
    # vez de fingir que analiza 4h. Ver README, seccion de limitaciones.
    intraday_available: bool = False

    # -- accesos comodos ----------------------------------------------------
    def bars(self, n: int) -> tuple[Bar, ...]:
        return self.view.window(n)

    def closes(self, n: int) -> tuple[float, ...]:
        return self.view.closes(n)

    def macro(self, series_id: str, default: float | None = None) -> float | None:
        """Valor macro tal como se conocia hoy. None si no habia publicacion."""
        if self.pit is None:
            return default
        return self.pit.value(series_id, self.as_of, default)

    def macro_hist(self, series_id: str, n: int) -> tuple[float, ...]:
        if self.pit is None:
            return ()
        return self.pit.series_values(series_id, self.as_of, n)

    def macro_change(self, series_id: str, periods: int = 1) -> float | None:
        if self.pit is None:
            return None
        return self.pit.change(series_id, self.as_of, periods)

    def peer_closes(self, n: int) -> dict[str, tuple[float, ...]]:
        return {s: v.closes(n) for s, v in self.peers.items()}

    def close_on_or_before(self, d) -> float | None:
        """
        Cierre de la ultima sesion con fecha <= `d`, dentro de la ventana visible.
        Se usa para valuar multiplos historicos con el precio de ESE momento,
        nunca con el precio de hoy.
        """
        bars = self.view.window(self.view.available or 1)
        best = None
        for b in bars:
            if b.ts.date() <= d:
                best = b.close
            else:
                break
        return best

    def sector_peers(self) -> list[str]:
        return [s for s, sec in self.sector_map.items() if sec == self.sector and s != self.symbol]


class Layer(ABC):
    """
    Contrato de una capa de analisis.

    Obligaciones que el sistema hace cumplir:
      - devolver siempre un LayerScore, nunca None ni una excepcion
      - justificar por escrito, incluso cuando el score es 0
      - bajar `confidence` cuando falten datos, en vez de opinar igual
    """

    layer_id: LayerId

    @abstractmethod
    def evaluate(self, ctx: MarketContext) -> LayerScore: ...

    # -- helpers para las subclases ----------------------------------------
    def abstain(self, reason: str, features: Mapping[str, float] | None = None) -> LayerScore:
        """Abstencion explicita: score 0 y confianza 0. No es neutralidad."""
        return LayerScore(
            layer=self.layer_id,
            score=0.0,
            confidence=0.0,
            rationale=f"ABSTENCION: {reason}",
            features=dict(features or {}),
            warnings=("datos insuficientes",),
        )

    def emit(
        self,
        score: float,
        confidence: float,
        rationale: str,
        features: Mapping[str, float] | None = None,
        warnings: Sequence[str] = (),
    ) -> LayerScore:
        return LayerScore(
            layer=self.layer_id,
            score=max(-100.0, min(100.0, score)),
            confidence=max(0.0, min(1.0, confidence)),
            rationale=rationale,
            features=dict(features or {}),
            warnings=tuple(warnings),
        )


def blend(parts: Sequence[tuple[str, float | None, float]]) -> tuple[float, float, list[str]]:
    """
    Combina sub-senales de una capa.

    `parts` = [(nombre, valor en [-100,100] o None, peso), ...]

    Devuelve (score, cobertura, notas).

    DOS PROPIEDADES, y la segunda es la que evita un error estructural:

    1. COBERTURA: fraccion del peso que efectivamente tenia dato. Se usa como
       `confidence`. Una capa que solo pudo evaluar 2 de 6 sub-senales pesa poco.

    2. COHERENCIA: el promedio simple aplasta todo hacia cero. Con 6 sub-senales,
       una capa con estructura +80, momentum +60 y volumen +40 -- evidencia
       fuerte y unanime -- daria 60, igual que una con +80 y +40 y dos en
       contra. Eso hace que el score combinado nunca supere un umbral exigente
       y el sistema no opere NUNCA por un artefacto aritmetico, no por prudencia.

       Solucion: cuando las sub-senales COINCIDEN en signo, el score se corre
       del promedio hacia la magnitud maxima, proporcionalmente al grado de
       acuerdo. Con acuerdo total devuelve el maximo; con acuerdo nulo devuelve
       el promedio. Evidencia coherente vale mas que la media de sus partes;
       evidencia contradictoria no vale mas que su promedio.
    """
    total_w = sum(w for _, _, w in parts)
    if total_w <= 0:
        return 0.0, 0.0, ["sin sub-senales definidas"]
    acc = 0.0
    covered = 0.0
    signed_w = 0.0
    max_mag = 0.0
    notes: list[str] = []
    for name, val, w in parts:
        if val is None:
            notes.append(f"{name}: sin dato")
            continue
        acc += val * w
        covered += w
        signed_w += w * (1 if val > 0 else (-1 if val < 0 else 0))
        max_mag = max(max_mag, abs(val))
        notes.append(f"{name}: {val:+.0f}")
    if covered <= 0:
        return 0.0, 0.0, notes

    mean = acc / covered
    agreement = abs(signed_w) / covered          # 1 = unanime, 0 = empatado
    boosted = mean + (max_mag - abs(mean)) * (agreement ** 2) * (1 if mean >= 0 else -1)
    notes.append(f"acuerdo entre sub-senales {agreement:.0%}: {mean:+.0f} -> {boosted:+.0f}")
    return max(-100.0, min(100.0, boosted)), covered / total_w, notes
