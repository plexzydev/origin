"""
Libro de errores. Persistente, consultado ANTES de cada operacion.

La pregunta que responde: "esto se parece a un error que ya cometi?"

Tres tipos de error, con tratamiento distinto porque la evidencia necesaria
para corregirlos es distinta:

  PROCESO -> no se siguio el plan. Correccion INMEDIATA, sin necesitar
             estadistica: si el sistema movio un stop en contra, no hace falta
             una muestra de 30 para saber que esta mal.
  MODELO  -> el modelo estaba equivocado. Requiere EVIDENCIA (>=30 casos
             comparables y significancia). Es el tipo que mas se corrige de
             mas, confundiendo mala suerte con mal modelo.
  DATOS   -> la fuente estaba mal. Se arregla la fuente, no el modelo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


class ErrorKind(str, Enum):
    PROCESS = "PROCESO"
    MODEL = "MODELO"
    DATA = "DATOS"


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    id: str
    created_at: datetime
    kind: ErrorKind
    title: str
    description: str
    # Condiciones bajo las que aparecio. Se usan para el matching.
    conditions: Mapping[str, Any] = field(default_factory=dict)
    correction: str = ""
    times_seen: int = 1
    resolved: bool = False

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["kind"] = self.kind.value
        d["conditions"] = dict(self.conditions)
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "ErrorEntry":
        return cls(
            id=d["id"], created_at=datetime.fromisoformat(d["created_at"]),
            kind=ErrorKind(d["kind"]), title=d["title"], description=d["description"],
            conditions=d.get("conditions", {}), correction=d.get("correction", ""),
            times_seen=d.get("times_seen", 1), resolved=d.get("resolved", False),
        )


def _similarity(a: Mapping[str, Any], b: Mapping[str, Any], tol: float = 0.25) -> float:
    """
    Similitud entre dos conjuntos de condiciones, en [0,1].

    Numericos: coinciden si difieren menos de `tol` en terminos relativos.
    Texto: coincidencia exacta. Deliberadamente tosco -- una metrica sofisticada
    aca daria falsos positivos y el libro de errores perderia utilidad.
    """
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    hits = 0
    for k in keys:
        va, vb = a[k], b[k]
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            denom = max(abs(float(va)), abs(float(vb)), 1e-9)
            if abs(float(va) - float(vb)) / denom <= tol:
                hits += 1
        elif str(va) == str(vb):
            hits += 1
    return hits / len(set(a) | set(b))


class ErrorBook:
    """Archivo persistente en JSONL. Append-only en disco, indexado en memoria."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else None
        self.entries: list[ErrorEntry] = []
        if self.path and self.path.exists():
            self.load()

    def add(self, entry: ErrorEntry) -> None:
        self.entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_json(), ensure_ascii=False, sort_keys=True) + "\n")

    def load(self) -> None:
        self.entries = []
        if not self.path or not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.entries.append(ErrorEntry.from_json(json.loads(line)))

    def similar(self, conditions: Mapping[str, Any], threshold: float = 0.5) -> list[tuple[ErrorEntry, float]]:
        """Errores pasados parecidos a la situacion actual, del mas parecido al menos."""
        out = [
            (e, _similarity(e.conditions, conditions))
            for e in self.entries if not e.resolved
        ]
        out = [(e, s) for e, s in out if s >= threshold]
        out.sort(key=lambda x: -x[1])
        return out

    def by_kind(self, kind: ErrorKind) -> list[ErrorEntry]:
        return [e for e in self.entries if e.kind is kind]

    def process_violation_count(self) -> int:
        """Las violaciones de proceso se cuentan aparte y pesan mas que cualquier perdida."""
        return sum(e.times_seen for e in self.by_kind(ErrorKind.PROCESS))

    def summary(self) -> str:
        if not self.entries:
            return "libro de errores vacio (sistema nuevo o nadie registro nada, que ya es un error)"
        by = {k: len(self.by_kind(k)) for k in ErrorKind}
        return (
            f"{len(self.entries)} errores registrados: "
            + ", ".join(f"{k.value} {v}" for k, v in by.items())
            + f". Violaciones de proceso acumuladas: {self.process_violation_count()}"
        )
