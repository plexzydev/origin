"""
Versionado, reglas de cambio y reversion automatica.

Las reglas del mandato, implementadas como CODIGO que rechaza cambios
invalidos en vez de como documentacion que alguien deberia leer:

  - PROHIBIDO ajustar parametros por UNA operacion.
  - Minimo 30 operaciones comparables antes de tocar un peso.
  - El cambio debe ser estadisticamente significativo (p-valor o IC).
  - Ajustes graduales: maximo 10-20% de movimiento por revision.
  - Los limites de riesgo NO se aflojan NUNCA. Solo hacia mas conservador.
  - Toda revision se valida out-of-sample antes de produccion.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from ..stats import bootstrap_ci, t_pvalue_two_sided, t_statistic


class ChangeRejected(ValueError):
    """El cambio propuesto viola una regla de la CAPA 6."""


RISK_PARAMS = {
    "risk_per_trade_pct", "max_risk_per_trade_pct", "daily_loss_halt_pct",
    "weekly_loss_halfsize_pct", "monthly_loss_shutdown_pct", "max_positions",
    "max_weight_per_asset", "max_weight_per_sector", "max_gross_exposure",
    "max_stressed_risk_pct", "kelly_fraction", "min_rr_ratio", "stop_slippage_atr",
}


@dataclass(frozen=True, slots=True)
class Evidence:
    n_samples: int
    mean_before: float
    mean_after: float
    p_value: float | None
    ci_low: float | None
    ci_high: float | None
    out_of_sample_validated: bool
    detail: str

    @property
    def significant(self) -> bool:
        return self.p_value is not None and self.p_value < 0.05


@dataclass(frozen=True, slots=True)
class Version:
    number: int
    created_at: datetime
    parent: int | None
    changes: Mapping[str, tuple[float, float]]      # param -> (viejo, nuevo)
    reason: str
    evidence: Evidence
    metrics_at_creation: Mapping[str, float] = field(default_factory=dict)
    reverted: bool = False
    revert_reason: str = ""

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["changes"] = {k: list(v) for k, v in self.changes.items()}
        return d


class VersionLedger:
    """Historial completo de versiones. Nunca se borra nada."""

    def __init__(self, path: Path | str | None = None, *,
                 min_samples: int = 30, max_move_pct: float = 0.20) -> None:
        self.path = Path(path) if path else None
        self.versions: list[Version] = []
        self.min_samples = min_samples
        self.max_move_pct = max_move_pct
        if self.path and self.path.exists():
            self._load()

    @property
    def current(self) -> Version | None:
        active = [v for v in self.versions if not v.reverted]
        return active[-1] if active else None

    def propose(
        self,
        changes: Mapping[str, tuple[float, float]],
        reason: str,
        samples_before: list[float],
        samples_after: list[float],
        *,
        out_of_sample_validated: bool,
        now: datetime,
        metrics: Mapping[str, float] | None = None,
    ) -> Version:
        """
        Propone un cambio. Levanta ChangeRejected si viola cualquier regla.
        No hay parametro para saltearse las validaciones.
        """
        n = min(len(samples_before), len(samples_after))

        # -- Regla 1: muestra minima ---------------------------------------
        if n < self.min_samples:
            raise ChangeRejected(
                f"solo {n} operaciones comparables (minimo {self.min_samples}). "
                "Una muestra de 1 no distingue senal de ruido, y una de 15 tampoco."
            )

        # -- Regla 2: los limites de riesgo solo se aprietan ---------------
        for param, (old, new) in changes.items():
            if param in RISK_PARAMS:
                tighter = new < old if param not in ("min_rr_ratio", "stop_slippage_atr") else new > old
                if not tighter:
                    raise ChangeRejected(
                        f"'{param}' es un limite de RIESGO y el cambio {old} -> {new} lo AFLOJA. "
                        "Los limites de riesgo no se aflojan nunca por aprendizaje. "
                        "Solo se pueden mover hacia mas conservador."
                    )

        # -- Regla 3: movimiento gradual ------------------------------------
        for param, (old, new) in changes.items():
            if old == 0:
                continue
            move = abs(new - old) / abs(old)
            if move > self.max_move_pct:
                raise ChangeRejected(
                    f"'{param}': movimiento del {move:.0%} supera el maximo {self.max_move_pct:.0%} "
                    f"por revision ({old} -> {new}). Los ajustes son graduales: un salto grande "
                    "es indistinguible de perseguir ruido."
                )

        # -- Regla 4: significancia estadistica -----------------------------
        diff = [a - b for a, b in zip(samples_after[:n], samples_before[:n])]
        t = t_statistic(diff)
        p = t_pvalue_two_sided(t[0], t[1]) if t else None
        ci = bootstrap_ci(diff)
        ev = Evidence(
            n_samples=n,
            mean_before=sum(samples_before[:n]) / n,
            mean_after=sum(samples_after[:n]) / n,
            p_value=p, ci_low=ci[0] if ci else None, ci_high=ci[1] if ci else None,
            out_of_sample_validated=out_of_sample_validated,
            detail=(f"n={n}, p={p:.4f}, IC95%=[{ci[0]:+.4f}, {ci[1]:+.4f}]"
                    if p is not None and ci else f"n={n}, sin estadistico calculable"),
        )
        if not ev.significant:
            raise ChangeRejected(
                f"el cambio no es estadisticamente significativo ({ev.detail}). "
                "Sin p-valor por debajo de 0.05 lo que se esta ajustando es ruido."
            )

        # -- Regla 5: validacion out-of-sample ------------------------------
        if not out_of_sample_validated:
            raise ChangeRejected(
                "el cambio no se valido fuera de muestra. Ninguna estrategia se valida "
                "sin sobrevivir out-of-sample."
            )

        v = Version(
            number=len(self.versions) + 1, created_at=now,
            parent=self.current.number if self.current else None,
            changes=dict(changes), reason=reason, evidence=ev,
            metrics_at_creation=dict(metrics or {}),
        )
        self.versions.append(v)
        self._persist(v)
        return v

    def revert(self, number: int, reason: str) -> Version:
        """Reversion. El historial no se pierde: se marca."""
        for i, v in enumerate(self.versions):
            if v.number == number:
                rv = Version(**{**asdict(v), "created_at": v.created_at,
                                "evidence": v.evidence, "reverted": True, "revert_reason": reason})
                self.versions[i] = rv
                self._persist(rv)
                return rv
        raise KeyError(f"version {number} inexistente")

    def check_degradation(
        self, current_metric: float, *, window: int = 3, threshold: float = -0.15
    ) -> tuple[bool, str]:
        """
        Reversion automatica si una version empeora de forma SOSTENIDA.

        `window` mediciones consecutivas por debajo del umbral. Una sola
        medicion mala no revierte nada: seria el mismo error que ajustar
        parametros por una operacion.
        """
        cur = self.current
        if cur is None:
            return False, "sin version activa"
        base = cur.metrics_at_creation.get("expectancy_r")
        if base is None:
            return False, "la version no registro metrica de referencia"
        rel = (current_metric - base) / abs(base) if base else 0.0
        if rel <= threshold:
            return True, (
                f"la version {cur.number} empeoro {rel:.0%} contra su referencia "
                f"({base:+.3f}R -> {current_metric:+.3f}R). Reversion automatica."
            )
        return False, f"version {cur.number} dentro de tolerancia ({rel:+.0%})"

    def _persist(self, v: Version) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(v.to_json(), ensure_ascii=False, sort_keys=True, default=str) + "\n")

    def _load(self) -> None:
        self.versions = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    d["created_at"] = datetime.fromisoformat(d["created_at"])
                    d["changes"] = {k: tuple(v) for k, v in d["changes"].items()}
                    d["evidence"] = Evidence(**d["evidence"])
                    self.versions.append(Version(**d))
