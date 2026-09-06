"""Fixtures compartidas. Mundo sintetico chico para que los tests sean rapidos."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qtdesk.config import SystemConfig                      # noqa: E402
from qtdesk.contracts import Bar                            # noqa: E402
from qtdesk.data.bars import BarSeries                      # noqa: E402
from qtdesk.data.providers.synthetic import build_world     # noqa: E402
from qtdesk.risk.state import DeskState                     # noqa: E402

SMALL_SYMBOLS = ("SPY", "AAPL", "MSFT", "JPM", "XOM", "KO", "XLK", "XLE")


@pytest.fixture(scope="session")
def world():
    return build_world(seed=424242)


@pytest.fixture(scope="session")
def bundle(world):
    return world.to_bundle()


@pytest.fixture
def cfg():
    return SystemConfig()


@pytest.fixture
def desk():
    return DeskState(equity=100_000.0)


def scramble_after(series: BarSeries, cutoff_ts, seed: int = 99) -> BarSeries:
    """
    Reemplaza TODAS las barras posteriores a `cutoff_ts` por ruido.

    Es la herramienta central del test de invariancia: si una decision tomada
    antes del corte cambia cuando el futuro cambia, esa decision estaba
    mirando el futuro. No hay otra explicacion posible.
    """
    rng = random.Random(seed)
    out = []
    for b in series.bars:
        if b.ts <= cutoff_ts:
            out.append(b)
        else:
            px = rng.uniform(1.0, 5000.0)
            hi = px * rng.uniform(1.0, 1.4)
            lo = px * rng.uniform(0.6, 1.0)
            op = rng.uniform(lo, hi)
            cl = rng.uniform(lo, hi)
            out.append(Bar(b.ts, op, max(hi, op, cl), min(lo, op, cl), cl,
                           rng.uniform(1.0, 1e9)))
    return BarSeries(series.symbol, tuple(out))
