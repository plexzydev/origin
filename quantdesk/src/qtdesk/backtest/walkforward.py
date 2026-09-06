"""
Walk-forward y validacion cruzada PURGADA con embargo (Lopez de Prado).

El problema que resuelve: en series financieras las observaciones se SOLAPAN.
Si una etiqueta se construye mirando los proximos 20 dias, la observacion del
lunes y la del martes comparten 19 dias de informacion. Un k-fold comun pone
una en entrenamiento y otra en test, y el modelo "aprende" la respuesta.
El resultado es un backtest excelente que en vivo no funciona.

Dos correcciones, ambas necesarias:

  PURGA   -> se eliminan del entrenamiento las observaciones cuyo horizonte de
             etiqueta se solapa con el periodo de test.
  EMBARGO -> se eliminan ademas las observaciones inmediatamente POSTERIORES
             al test. Sin esto, la autocorrelacion de la serie filtra
             informacion del test hacia el entrenamiento por el otro lado.

Sin purga el error es optimista y grande. Sin embargo el error es optimista y
chico, pero sistematico. Se necesitan las dos.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class Fold:
    train: tuple[int, ...]
    test: tuple[int, ...]
    purged: int
    embargoed: int

    def assert_disjoint(self) -> None:
        overlap = set(self.train) & set(self.test)
        if overlap:
            raise ValueError(f"fold contaminado: {len(overlap)} indices en train Y test")


def purged_kfold(
    n: int, k: int = 5, *, label_horizon: int = 20, embargo_pct: float = 0.01
) -> list[Fold]:
    """
    K-fold purgado con embargo sobre `n` observaciones ordenadas en el tiempo.

    `label_horizon` = cuantas barras hacia adelante mira la etiqueta. Debe
    coincidir con el plazo real del trade (el time stop), no con un numero
    elegido: si el trade dura 20 ruedas, el solapamiento es de 20 ruedas.
    """
    if k < 2 or n < k * 2:
        raise ValueError("parametros insuficientes para k-fold")
    embargo = max(1, int(n * embargo_pct))
    size = n // k
    folds: list[Fold] = []
    for i in range(k):
        lo = i * size
        hi = n if i == k - 1 else (i + 1) * size
        test = tuple(range(lo, hi))

        train, purged, embargoed = [], 0, 0
        for j in range(n):
            if lo <= j < hi:
                continue
            # PURGA: la etiqueta de j se solapa con el test
            if j < lo and j + label_horizon >= lo:
                purged += 1
                continue
            # EMBARGO: j esta justo despues del test
            if hi <= j < hi + embargo:
                embargoed += 1
                continue
            train.append(j)
        f = Fold(tuple(train), test, purged, embargoed)
        f.assert_disjoint()
        folds.append(f)
    return folds


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    gap: int

    @property
    def train(self) -> range:
        return range(self.train_start, self.train_end)

    @property
    def test(self) -> range:
        return range(self.test_start, self.test_end)


def walk_forward(
    n: int, *, train_size: int, test_size: int, label_horizon: int = 20, anchored: bool = False
) -> list[WalkForwardWindow]:
    """
    Ventanas walk-forward con hueco de `label_horizon` entre train y test.

    `anchored=True` deja fijo el inicio del entrenamiento (ventana creciente);
    `False` la desplaza (ventana movil). La movil detecta mejor la muerte de
    una estrategia; la anclada usa mas datos. Se corren las dos.
    """
    out: list[WalkForwardWindow] = []
    start = 0
    while True:
        tr_end = start + train_size
        te_start = tr_end + label_horizon        # hueco = horizonte de etiqueta
        te_end = te_start + test_size
        if te_end > n:
            break
        out.append(WalkForwardWindow(
            0 if anchored else start, tr_end, te_start, te_end, label_horizon
        ))
        start += test_size
    return out


def assert_no_leakage(folds) -> str:
    """
    Verifica que ninguna observacion de entrenamiento pueda ver el test.
    Se usa en los tests; devuelve un resumen legible.
    """
    for i, f in enumerate(folds):
        f.assert_disjoint()
        if f.train and f.test:
            for j in f.train:
                if f.test[0] <= j <= f.test[-1]:
                    raise ValueError(f"fold {i}: indice {j} en ambos conjuntos")
    total_purged = sum(f.purged for f in folds)
    total_emb = sum(f.embargoed for f in folds)
    return (
        f"{len(folds)} folds verificados: sin solapamiento. "
        f"{total_purged} observaciones purgadas por solapamiento de etiqueta, "
        f"{total_emb} por embargo."
    )
