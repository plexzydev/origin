"""
Registro previo CONGELADO, encadenado por hashes.

El requisito del mandato: "Antes de entrar: score de cada capa, regimen, arbol
de escenarios, tesis, FALSACION EXPLICITA, nivel de conviccion y por que."
Y la palabra clave es CONGELADO.

Por que la cadena de hashes: sin ella, el registro previo no vale nada. El
sesgo retrospectivo hace que despues de una perdida uno recuerde haber tenido
dudas, y despues de una ganancia recuerde haber estado seguro. Un archivo de
texto editable no protege contra eso porque el que edita es el mismo que
recuerda mal, y muchas veces ni siquiera de mala fe.

Cada entrada incluye el hash de la anterior. Cambiar cualquier registro pasado
rompe la cadena desde ahi en adelante, y `verify()` lo detecta. No impide la
manipulacion -- nada lo impide en un archivo local -- pero la hace VISIBLE.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

GENESIS = "0" * 64


@dataclass(frozen=True, slots=True)
class JournalEntry:
    seq: int
    ts: datetime
    kind: str                    # DECISION / FILL / REVIEW / VERSION / ERROR
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str

    @staticmethod
    def compute_hash(seq: int, ts: datetime, kind: str, payload: dict, prev_hash: str) -> str:
        blob = json.dumps(
            {"seq": seq, "ts": ts.isoformat(), "kind": kind, "payload": payload, "prev": prev_hash},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_json(self) -> dict[str, Any]:
        return {
            "seq": self.seq, "ts": self.ts.isoformat(), "kind": self.kind,
            "payload": self.payload, "prev_hash": self.prev_hash, "entry_hash": self.entry_hash,
        }


class TamperDetected(RuntimeError):
    """La cadena de hashes no cierra. Alguien edito el historial."""


class Journal:
    """Bitacora append-only en JSONL con cadena de hashes."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else None
        self.entries: list[JournalEntry] = []
        if self.path and self.path.exists():
            self.load()

    @property
    def head(self) -> str:
        return self.entries[-1].entry_hash if self.entries else GENESIS

    def append(self, kind: str, ts: datetime, payload: dict[str, Any]) -> JournalEntry:
        seq = len(self.entries)
        prev = self.head
        h = JournalEntry.compute_hash(seq, ts, kind, payload, prev)
        e = JournalEntry(seq, ts, kind, payload, prev, h)
        self.entries.append(e)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(e.to_json(), ensure_ascii=False, sort_keys=True) + "\n")
        return e

    def record_decision(self, decision) -> JournalEntry:
        """
        Congela la decision COMPLETA antes de operar: scores de cada capa,
        regimen, arbol de escenarios, tesis, falsacion, conviccion y motivo.
        """
        rec = decision.to_record()
        rec["fingerprint"] = decision.fingerprint()
        return self.append("DECISION", decision.ts, rec)

    def record_review(self, review, ts: datetime) -> JournalEntry:
        from dataclasses import asdict
        return self.append("REVIEW", ts, json.loads(json.dumps(asdict(review), default=str)))

    def load(self) -> None:
        self.entries = []
        if not self.path or not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                self.entries.append(JournalEntry(
                    seq=d["seq"], ts=datetime.fromisoformat(d["ts"]), kind=d["kind"],
                    payload=d["payload"], prev_hash=d["prev_hash"], entry_hash=d["entry_hash"],
                ))

    def verify(self) -> tuple[bool, str]:
        """
        Recalcula toda la cadena. Devuelve (integra, detalle).

        Detecta: modificacion de un registro, insercion, borrado y reordenamiento.
        """
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e.seq != i:
                return False, f"secuencia rota en la posicion {i}: seq={e.seq}"
            if e.prev_hash != prev:
                return False, (
                    f"cadena rota en seq={e.seq} ({e.ts.date()}): el registro apunta a "
                    f"{e.prev_hash[:12]}... pero el anterior es {prev[:12]}...  "
                    "Alguien borro, inserto o reordeno entradas."
                )
            h = JournalEntry.compute_hash(e.seq, e.ts, e.kind, e.payload, e.prev_hash)
            if h != e.entry_hash:
                return False, (
                    f"registro ALTERADO en seq={e.seq} ({e.ts.date()}, {e.kind}): "
                    f"hash guardado {e.entry_hash[:12]}... vs recalculado {h[:12]}..."
                )
            prev = e.entry_hash
        return True, f"cadena integra: {len(self.entries)} registros verificados"

    def assert_intact(self) -> None:
        ok, detail = self.verify()
        if not ok:
            raise TamperDetected(detail)

    def by_kind(self, kind: str) -> Iterator[JournalEntry]:
        return (e for e in self.entries if e.kind == kind)

    def decision_for(self, fingerprint: str) -> JournalEntry | None:
        for e in self.by_kind("DECISION"):
            if e.payload.get("fingerprint") == fingerprint:
                return e
        return None
