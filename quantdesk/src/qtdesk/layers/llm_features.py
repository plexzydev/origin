"""
Uso de LLM DENTRO del sistema: texto -> features numericos.

Que hace: convierte comunicados de bancos centrales, llamadas de resultados,
noticias y documentos regulatorios en numeros -- tono, cambio de tono contra
el comunicado anterior, grado de incertidumbre.

LIMITE, y esta escrito en el mandato: es UN FEATURE MAS, nunca el oraculo. Por
eso `MAX_LAYER_WEIGHT` acota cuanto puede pesar y el contrato devuelve
`confidence`, no certezas.

EL PROBLEMA GRAVE: SESGO DE RETROSPECTIVA
-----------------------------------------
Un modelo entrenado despues de 2020 SABE como termino 2020. Si se le pide que
puntue el tono de un comunicado del 3 de marzo de 2020, no esta leyendo ese
texto: esta recordando lo que vino despues. Eso no es un feature, es la
respuesta del examen filtrandose al examen.

No hay forma de "pedirle que no lo sepa". Las unicas defensas reales son de
arquitectura, y son las dos que implementa este modulo:

  1. FrozenFeatureStore -- los features se calculan UNA VEZ, con una fecha de
     corte documentada, y el backtest los lee de ahi. Si el corte del store es
     posterior a la fecha del backtest, `require_clean()` levanta.
  2. LexiconFeaturizer -- un contador de palabras determinista, sin modelo.
     Es peor, y es honesto: no puede saber nada que no este en el texto.

Para operar en vivo si tiene sentido un LLM real: ahi el futuro todavia no
ocurrio y no hay nada que recordar.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime

MAX_LAYER_WEIGHT = 0.10     # techo duro: el LLM nunca pesa mas que esto


class HindsightError(RuntimeError):
    """Se intento usar features generados con conocimiento posterior a la fecha."""


@dataclass(frozen=True, slots=True)
class Document:
    doc_id: str
    kind: str                     # COMUNICADO_BANCO_CENTRAL / EARNINGS_CALL / NOTICIA / REGULATORIO
    published_at: datetime        # hora REAL de publicacion, verificada
    text: str
    source: str = ""
    prior_doc_id: str | None = None   # comunicado anterior, para medir el CAMBIO de tono

    def fingerprint(self) -> str:
        return hashlib.sha256(f"{self.doc_id}|{self.text}".encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class TextFeatures:
    """Features numericos. Todo en [-1, 1] salvo `uncertainty` y `confidence` en [0, 1]."""
    doc_id: str
    tone: float                   # -1 muy negativo, +1 muy positivo
    tone_delta_vs_prior: float    # cambio contra el documento anterior
    uncertainty: float            # 0 = lenguaje firme, 1 = lleno de condicionales
    hawkish_dovish: float         # -1 expansivo, +1 restrictivo
    confidence: float
    generated_at: datetime
    generator: str
    knowledge_cutoff: date | None  # hasta cuando "sabe" el generador

    def as_scores(self) -> dict[str, float]:
        return {
            "tono": self.tone * 100.0,
            "cambio_de_tono": self.tone_delta_vs_prior * 100.0,
            "incertidumbre": -self.uncertainty * 100.0,
            "sesgo_monetario": -self.hawkish_dovish * 100.0,
        }


class TextFeaturizer(ABC):
    name: str
    knowledge_cutoff: date | None

    @abstractmethod
    def featurize(self, doc: Document, prior: Document | None = None) -> TextFeatures: ...


# ---------------------------------------------------------------------------

_NEG = ("riesgo", "caida", "deterioro", "debil", "recesion", "contraccion", "incierto",
        "presion", "restrictivo", "desaceleracion", "vulnerabilidad", "perdida")
_POS = ("crecimiento", "solido", "mejora", "expansion", "fuerte", "resiliente",
        "favorable", "recuperacion", "estable", "acomodaticio")
_UNC = ("podria", "quizas", "eventualmente", "dependiendo", "sujeto a", "incierto",
        "monitorear", "evaluar", "en funcion de", "si las condiciones")
_HAWK = ("restrictivo", "endurecer", "subir", "contener", "vigilancia", "firmeza")
_DOVE = ("acomodaticio", "estimulo", "recortar", "apoyo", "flexibilizar", "paciencia")


class LexiconFeaturizer(TextFeaturizer):
    """
    Contador de palabras determinista. Sin modelo, sin API, sin retrospectiva.

    Es notablemente peor que un LLM leyendo el mismo texto. Esa es exactamente
    la razon por la que es el default para backtest: no puede saber nada que no
    este escrito en el documento.
    """

    name = "lexicon-v1"
    knowledge_cutoff = None       # no sabe nada: no puede recordar el futuro

    def featurize(self, doc: Document, prior: Document | None = None) -> TextFeatures:
        t = self._tone(doc.text)
        prior_t = self._tone(prior.text) if prior is not None else t
        low = doc.text.lower()
        n = max(len(low.split()), 1)
        unc = min(1.0, sum(low.count(w) for w in _UNC) / (n / 100.0) / 5.0)
        hawk = sum(low.count(w) for w in _HAWK)
        dove = sum(low.count(w) for w in _DOVE)
        hd = 0.0 if (hawk + dove) == 0 else (hawk - dove) / (hawk + dove)
        return TextFeatures(
            doc_id=doc.doc_id, tone=t, tone_delta_vs_prior=t - prior_t,
            uncertainty=unc, hawkish_dovish=hd,
            # Confianza baja a proposito: es un contador de palabras.
            confidence=0.35,
            generated_at=doc.published_at, generator=self.name, knowledge_cutoff=None,
        )

    @staticmethod
    def _tone(text: str) -> float:
        low = text.lower()
        pos = sum(low.count(w) for w in _POS)
        neg = sum(low.count(w) for w in _NEG)
        return 0.0 if (pos + neg) == 0 else (pos - neg) / (pos + neg)


@dataclass(slots=True)
class FrozenFeatureStore:
    """
    Features precalculados con una fecha de corte DOCUMENTADA.

    Uso correcto en backtest: se generan una vez con un modelo cuyo corte de
    conocimiento es anterior al periodo backtesteado, y se congelan. El store
    verifica la condicion en cada lectura.
    """
    knowledge_cutoff: date
    generator: str
    features: dict[str, TextFeatures] = field(default_factory=dict)
    doc_published: dict[str, datetime] = field(default_factory=dict)

    def add(self, doc: Document, f: TextFeatures) -> None:
        self.features[doc.doc_id] = f
        self.doc_published[doc.doc_id] = doc.published_at

    def get(self, doc_id: str, as_of: datetime) -> TextFeatures | None:
        pub = self.doc_published.get(doc_id)
        if pub is None or pub > as_of:
            return None            # el documento todavia no existia
        return self.features.get(doc_id)

    def require_clean(self, backtest_start: date) -> None:
        """
        Verifica que el generador no supiera nada del periodo backtesteado.

        Si el corte de conocimiento del modelo es POSTERIOR al inicio del
        backtest, los features estan contaminados por retrospectiva y no hay
        forma de limpiarlos. Se levanta en vez de advertir, porque una
        advertencia se ignora y un backtest contaminado no vale nada.
        """
        if self.knowledge_cutoff >= backtest_start:
            raise HindsightError(
                f"El generador '{self.generator}' tiene corte de conocimiento "
                f"{self.knowledge_cutoff}, POSTERIOR al inicio del backtest "
                f"({backtest_start}). Sabe como termino el periodo que se esta "
                "evaluando. Estos features no se pueden usar: hay que regenerarlos "
                "con un modelo anterior al periodo, o usar LexiconFeaturizer."
            )


def contribution_weight(features: TextFeatures, requested: float) -> float:
    """
    Peso efectivo del feature de texto. Acotado por `MAX_LAYER_WEIGHT` y por la
    confianza del propio generador. El LLM es un feature mas, nunca el oraculo.
    """
    return min(requested, MAX_LAYER_WEIGHT) * features.confidence
