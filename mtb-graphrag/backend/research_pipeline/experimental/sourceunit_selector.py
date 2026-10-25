"""Selezione deterministica delle SourceUnit da mostrare al Paper Context Enricher.

**Il buco che questo modulo prova a chiudere.** Oggi le unità che raggiungono il
modello arrivano da ``bundle["source_unit_ids"]`` — un artefatto congelato,
costruito una volta dal pilot. Su un documento recuperato al volo quel bundle non
esiste, e senza di esso ``paper_selection`` esclude ogni bundle con
``TEXT_NOT_AVAILABLE_IN_CACHE``. Il recupero documentale live è già stato
dimostrato fattibile; è la scelta del passaggio che resta scoperta.

**Cosa questo componente non fa.** Non decide se una candidate sia supportata.
Non produce ``SUPPORTED``, ``AMBIGUOUS``, ``CONTRADICTED`` né alcuno status.
Risponde a una domanda sola: *quali passaggi meritano di essere mostrati al
modello?* Un'unità in cima al ranking può benissimo non contenere supporto, e
l'astensione del modello resta un esito corretto.

**Nessun LLM, nessun gold.** Il ranking usa soltanto la GraphCandidateAssertion e
il testo del documento. Non legge bundle, quote attese, esiti del validatore o
status canonici: sono tutti posteriori al grounding documentale, e usarli
significherebbe misurare la propria risposta.

**Perché lessicale e non embedding.** Un ranking lessicale si spiega a un
revisore una riga alla volta — «questa unità è stata scelta perché contiene
ABL1, V299L e dasatinib, ed è un paragrafo» — e produce lo stesso ordine a ogni
esecuzione. È la stessa proprietà che rende verificabile il resto della
pipeline. Gli embedding restano una baseline possibile, non il metodo canonico.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

SELECTOR_VERSION = "deterministic-sourceunit-selector/2.2"
# BM25 ranking with the existing section/type factors. Synthetic regression
# rejects pure BM25, which can prioritize entity repetition in Methods.
# Local comparison is exploratory; no claim of clinical superiority.
DEFAULT_RANKING_STRATEGY = "BM25_STRUCTURE"

STATUS_SELECTED = "SELECTED"
STATUS_NO_RELEVANT = "NO_RELEVANT_SOURCE_UNIT"
STATUS_NO_COMPATIBLE = "NO_COMPATIBLE_PASSAGE"

DEFAULT_TOP_K = 4

#: Okapi BM25, parametri standard. Non tarati sul gold: cambiarli per guadagnare
#: punti su 25 bundle sarebbe adattarsi al set di valutazione.
BM25_K1 = 1.5
BM25_B = 0.75

#: Peso delle feature cliniche. L'ordine riflette il potere discriminante atteso:
#: un'alterazione puntuale identifica un'affermazione molto più di una malattia,
#: che in un intero articolo di oncologia compare quasi ovunque.
WEIGHT_ALTERATION = 3.0
WEIGHT_GENE = 2.0
WEIGHT_INTERVENTION = 2.0
WEIGHT_DISEASE = 0.5
WEIGHT_LEXICAL = 1.0

#: Prior strutturale sul tipo di unità.
#:
#: Ricavato dalla forma delle unità, non dal loro tasso di gold: tarare il prior
#: sul gold di 25 bundle vorrebbe dire misurare quanto bene si riproduce il gold
#: usando il gold. Il criterio è l'auto-contenimento — quanto un'unità regge da
#: sola come citazione verificabile.
#:
#: - unità narrative complete (abstract, paragrafo, sommario di trial) reggono;
#: - i titoli enunciano la tesi ma non la argomentano;
#: - le frasi di full text sono precise ma frammentarie;
#: - intestazioni di sezione, celle e didascalie sono etichette, non affermazioni.
SECTION_PRIOR: Mapping[str, float] = {
    "ABSTRACT": 1.00,
    "BRIEF_SUMMARY": 1.00,
    "DETAILED_DESCRIPTION": 1.00,
    "FULLTEXT_PARAGRAPH": 0.95,
    "ABSTRACT_SENTENCE": 0.85,
    "TRIAL_TITLE": 0.80,
    "TITLE": 0.80,
    "INTERVENTION": 0.70,
    "CONDITION": 0.60,
    "FULLTEXT_SENTENCE": 0.60,
    "TABLE_CELL": 0.50,
    "TABLE_CAPTION": 0.50,
    "FIGURE_CAPTION": 0.50,
    "FULLTEXT_SECTION": 0.20,
}
DEFAULT_SECTION_PRIOR = 0.60

# These are ranking factors, not clinical assertions.  They only make an
# explicitly compatible passage easier to show to the Reader than a lexical
# distractor.  The verifier remains the owner of clinical support.
SECTION_FACTOR: Mapping[str, float] = {
    "RESULTS": 1.15,
    "DISCUSSION": 1.00,
    "ABSTRACT": 1.05,
    "INTRODUCTION": 0.75,
    "METHODS": 0.60,
    "TABLE": 0.85,
    "FIGURE": 0.80,
    "TITLE": 0.80,
    "OTHER": 0.70,
}
_NEGATION_RE = re.compile(
    r"\b(?:no|not|without|negative|absent|lacks?|lack of|wild[- ]?type|"
    r"no evidence|failed to (?:detect|show)|did not|didn't)\b",
    re.IGNORECASE,
)
_POSITIVE_CUE_RE = re.compile(
    r"\b(?:support(?:s|ed)?|response|respond(?:ed|s)?|benefit|effective|sensitive|"
    r"associated with|confer(?:s|red)?|improv(?:e|ed|es))\b",
    re.IGNORECASE,
)
_NEGATIVE_CUE_RE = re.compile(
    r"\b(?:does not support|not support|no response|resistan(?:ce|t)|"
    r"lack of benefit|did not respond|negative|no evidence)\b",
    re.IGNORECASE,
)
_VARIANT_TOKEN_RE = re.compile(r"^(?:[a-z]\d+[a-z]|del[a-z0-9]+|ins[a-z0-9]+|fs)$", re.IGNORECASE)
_ALTERATION_TYPE_CUES = {
    "MUTATION": ("mutation", "mutations", "variant", "variants"),
    "AMPLIFICATION": ("amplification", "amplified"),
    "DELETION": ("deletion", "deleted"),
    "FUSION": ("fusion", "fusions"),
    "REARRANGEMENT": ("rearrangement", "rearranged"),
    "EXPRESSION": ("expression", "expressed"),
    "COPY_NUMBER": ("copy number", "copy-number"),
}

#: Sotto questa lunghezza un'unità non offre contesto sufficiente perché una
#: citazione sia verificabile: "V299L" da sola è un'occorrenza, non
#: un'affermazione di autore. I bonus vengono smorzati proporzionalmente invece
#: che azzerati, così l'unità resta selezionabile se nient'altro la batte.
MIN_CONTEXT_CHARS = 80

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[><][a-z0-9]+)*", re.IGNORECASE)
#: Prefissi di nomenclatura HGVS, che indicano il sistema di coordinate e non
#: fanno parte dell'alterazione. ``rs`` non compare qui: in ``rs12345`` è parte
#: dell'identificatore dbSNP, e toglierlo produrrebbe un numero senza significato.
_ALTERATION_PREFIX_RE = re.compile(r"^(?:p\.|c\.|g\.)", re.IGNORECASE)


# --- Normalizzazione (§4) ---------------------------------------------------


def normalize_text(value: Any) -> str:
    """NFC, case folding, punteggiatura e spazi. Nessuna espansione semantica.

    Deliberatamente non fa sinonimi né riscritture: trasformare "EGFR mutation"
    in "EGFR L858R" inventerebbe un'evidenza che il documento non contiene.
    """
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.casefold()
    text = re.sub(r"[^\w\s><]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(value: Any) -> list[str]:
    return _TOKEN_RE.findall(normalize_text(value))


def normalize_gene(symbol: Any) -> str:
    """Simbolo genico: alfanumerico, senza punteggiatura, minuscolo."""
    return re.sub(r"[^a-z0-9]", "", normalize_text(symbol))


def normalize_alteration(value: Any) -> str:
    """Forma dell'alterazione, senza i prefissi di nomenclatura HGVS.

    ``p.V299L`` e ``V299L`` sono la stessa alterazione scritta in due modi; non
    lo sono ``V299L`` e ``V299M``. La normalizzazione rimuove la notazione, mai
    la sostanza.

    Il prefisso va tolto **prima** di normalizzare il testo: ``normalize_text``
    elimina la punteggiatura, e senza il punto ``p.V299L`` diventerebbe
    ``pv299l``, cioè un'alterazione che non esiste e che non combacerebbe mai.
    """
    raw = unicodedata.normalize("NFC", str(value or "")).strip()
    raw = _ALTERATION_PREFIX_RE.sub("", raw)
    return re.sub(r"[^\w><]", "", normalize_text(raw))


def normalize_drug(value: Any) -> str:
    return normalize_text(value)


def _labels(items: Iterable[Mapping[str, Any]] | None) -> tuple[str, ...]:
    out: list[str] = []
    for item in items or ():
        label = str((item or {}).get("label") or "").strip()
        if label and label not in out:
            out.append(label)
    return tuple(out)


# --- Contratto (§2) ---------------------------------------------------------


@dataclass(frozen=True)
class BiomarkerSelection:
    gene: str | None = None
    alteration: str | None = None
    alteration_type: str | None = None
    specificity: str = "UNKNOWN"
    raw_value: str | None = None


@dataclass(frozen=True)
class InterventionSelection:
    label: str
    role: str = "UNKNOWN"
    assertion_status: str = "PRESENT"


@dataclass(frozen=True)
class SourceUnitSelectionInput:
    """Tutto ciò che il selector può guardare. Nient'altro entra."""

    candidate_id: str
    document_id: str
    biomarkers: tuple[BiomarkerSelection, ...] = ()
    diseases: tuple[str, ...] = ()
    interventions_structured: tuple[InterventionSelection, ...] = ()
    graph_relation: str | None = None
    direction: str | None = None
    evidence_type: str | None = None
    nct_ids: tuple[str, ...] = ()
    companion_diagnostics: tuple[str, ...] = ()
    source_units: tuple[Mapping[str, Any], ...] = ()
    question_interventions: tuple[str, ...] = ()

    @property
    def search_interventions(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.interventions, *self.question_interventions)))

    @property
    def disease(self) -> tuple[str, ...]:
        return self.diseases

    @property
    def genes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(b.gene for b in self.biomarkers if b.gene))

    @property
    def alterations(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(b.alteration for b in self.biomarkers if b.alteration))

    @property
    def interventions(self) -> tuple[str, ...]:
        return tuple(i.label for i in self.interventions_structured if i.label)

    @classmethod
    def from_candidate(cls, candidate: Mapping[str, Any], document_id: str,
                       source_units: Sequence[Mapping[str, Any]], *,
                       selection_intent: Mapping[str, Any] | None = None) -> "SourceUnitSelectionInput":
        """Estrae le feature dalla GCA.

        ``biomarkers`` mescola geni e varianti distinguendoli con ``type``: una
        variante trattata come gene perderebbe il suo peso, ed è la feature più
        discriminante che abbiamo.
        """
        biomarkers = []
        for item in candidate.get("biomarkers") or []:
            if not isinstance(item, Mapping):
                continue
            kind = str(item.get("type") or "").upper()
            label = str(item.get("label") or item.get("raw_value") or "").strip() or None
            gene = str(item.get("gene") or "").strip() or None
            alteration = str(item.get("alteration") or "").strip() or None
            if kind in {"GENE", "GENESYMBOL"} and not gene:
                gene = label
            if kind in {"VARIANT", "ALTERATION", "MOLECULARPROFILE", "MOLECULAR_PROFILE"} and not alteration:
                alteration = label
            specificity = str(item.get("specificity_level") or ("GENE" if gene and not alteration else "VARIANT" if alteration else "UNKNOWN")).upper()
            biomarkers.append(BiomarkerSelection(
                gene=gene, alteration=alteration,
                alteration_type=str(item.get("alteration_type") or "").upper() or None,
                specificity=specificity, raw_value=label,
            ))
        interventions = tuple(
            InterventionSelection(
                label=str(item.get("label") or item.get("normalized_value") or item.get("raw_value") or "").strip(),
                role=str(item.get("role") or "UNKNOWN").upper(),
                assertion_status=str(item.get("assertion_status") or "PRESENT").upper(),
            )
            for item in candidate.get("interventions") or []
            if isinstance(item, Mapping) and str(item.get("label") or item.get("normalized_value") or item.get("raw_value") or "").strip()
        )
        diagnostics = candidate.get("companion_diagnostic") or candidate.get("companion_diagnostics") or []
        if isinstance(diagnostics, Mapping):
            diagnostics = [diagnostics]
        diagnostic_labels = tuple(str(item.get("name") or item.get("identifier") or "").strip()
                                  for item in diagnostics if isinstance(item, Mapping)
                                  and str(item.get("name") or item.get("identifier") or "").strip())
        nct_ids = tuple(str(item.get("nct") or "").strip().upper()
                        for item in candidate.get("document_identifiers") or []
                        if isinstance(item, Mapping) and item.get("nct"))
        return cls(
            candidate_id=str(candidate.get("candidate_id") or ""),
            document_id=str(document_id),
            biomarkers=tuple(biomarkers),
            diseases=_labels(candidate.get("disease")),
            interventions_structured=interventions,
            graph_relation=candidate.get("predicate"),
            direction=str(candidate.get("direction") or "").strip() or None,
            evidence_type=str(candidate.get("evidence_scope") or candidate.get("evidence_type") or "").strip() or None,
            nct_ids=nct_ids,
            companion_diagnostics=diagnostic_labels,
            source_units=tuple(source_units),
            question_interventions=tuple((selection_intent or {}).get('case_question', {}).get('interventions', [])),
        )

    def query_terms(self) -> list[str]:
        """Query lessicale, costruita solo dalla GCA."""
        terms: list[str] = []
        for group in (self.alterations, self.genes, self.search_interventions, self.disease):
            for value in group:
                terms.extend(tokenize(value))
        return terms

    def input_hash(self) -> str:
        payload = {
            "candidate_id": self.candidate_id, "document_id": self.document_id,
            "biomarkers": [b.__dict__ for b in self.biomarkers],
            "diseases": list(self.diseases),
            "interventions": [i.__dict__ for i in self.interventions_structured],
            "question_interventions": self.question_interventions,
            "graph_relation": self.graph_relation,
            "direction": self.direction,
            "evidence_type": self.evidence_type, "nct_ids": list(self.nct_ids),
            "companion_diagnostics": list(self.companion_diagnostics),
            "source_unit_ids": sorted(str(u.get("source_unit_id")) for u in self.source_units),
        }
        return _hash(payload)


@dataclass(frozen=True)
class RankedSourceUnit:
    """Una riga del ranking, con tutto ciò che serve per contestarla."""

    source_unit_id: str
    rank: int
    score_total: float
    score_lexical: float
    section_prior: float
    unit_type: str
    text_length: int
    matched_gene: tuple[str, ...] = ()
    matched_alteration: tuple[str, ...] = ()
    matched_intervention: tuple[str, ...] = ()
    matched_disease: tuple[str, ...] = ()
    matched_biomarker_pairs: tuple[str, ...] = ()
    alteration_specificity: str = "UNKNOWN"
    intervention_compatibility: float = 0.0
    disease_compatibility: float = 0.0
    direction_compatibility: float = 0.0
    negation_status: str = "UNKNOWN"
    polarity_relevance: str = ""
    section_factor: float = 1.0
    context_factor: float = 1.0
    selection_reason: str = ""
    selected: bool = False
    exclusion_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_unit_id": self.source_unit_id, "rank": self.rank,
            "score_total": round(self.score_total, 6),
            "score_lexical": round(self.score_lexical, 6),
            "section_prior": self.section_prior,
            "unit_type": self.unit_type, "text_length": self.text_length,
            "matched_gene": list(self.matched_gene),
            "matched_alteration": list(self.matched_alteration),
            "matched_intervention": list(self.matched_intervention),
            "matched_disease": list(self.matched_disease),
            "matched_biomarker_pairs": list(self.matched_biomarker_pairs),
            "alteration_specificity": self.alteration_specificity,
            "intervention_compatibility": round(self.intervention_compatibility, 6),
            "disease_compatibility": round(self.disease_compatibility, 6),
            "direction_compatibility": round(self.direction_compatibility, 6),
            "negation_status": self.negation_status,
            "polarity_relevance": self.polarity_relevance,
            "section_factor": self.section_factor,
            "context_factor": round(self.context_factor, 4),
            "selection_reason": self.selection_reason,
            "selected": self.selected,
            "exclusion_reason": self.exclusion_reason,
        }


@dataclass(frozen=True)
class SourceUnitSelectionResult:
    candidate_id: str
    document_id: str
    status: str
    top_k: int
    selected_source_unit_ids: tuple[str, ...]
    ranked_source_units: tuple[RankedSourceUnit, ...]
    selector_version: str
    input_hash: str
    ranking_hash: str
    selected_ids_hash: str
    selection_reason: str
    matched_features: Mapping[str, Any] = field(default_factory=dict)

    @property
    def selection_scores(self) -> dict[str, float]:
        return {u.source_unit_id: round(u.score_total, 6) for u in self.ranked_source_units}

    def to_dict(self, *, ranking_limit: int | None = 20) -> dict[str, Any]:
        ranked = self.ranked_source_units[:ranking_limit] if ranking_limit else self.ranked_source_units
        return {
            "candidate_id": self.candidate_id, "document_id": self.document_id,
            "status": self.status, "top_k": self.top_k,
            "selected_source_unit_ids": list(self.selected_source_unit_ids),
            "ranked_source_units": [u.to_dict() for u in ranked],
            "selection_scores": self.selection_scores,
            "matched_features": dict(self.matched_features),
            "selection_reason": self.selection_reason,
            "selector_version": self.selector_version,
            "input_hash": self.input_hash,
            "ranking_hash": self.ranking_hash,
            "selected_ids_hash": self.selected_ids_hash,
        }


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- BM25 (§28) -------------------------------------------------------------


def bm25_scores(query_terms: Sequence[str],
                unit_tokens: Sequence[Sequence[str]]) -> list[float]:
    """Okapi BM25 sul solo documento in esame.

    Il corpus è il documento, non l'intera letteratura: l'IDF misura quanto un
    termine sia raro *in questo articolo*, che è la domanda giusta quando si
    cerca il passaggio da citare.
    """
    total = len(unit_tokens)
    if total == 0 or not query_terms:
        return [0.0] * total
    lengths = [len(tokens) for tokens in unit_tokens]
    avg_length = (sum(lengths) / total) or 1.0

    document_frequency: dict[str, int] = {}
    token_sets = [set(tokens) for tokens in unit_tokens]
    for term in set(query_terms):
        document_frequency[term] = sum(1 for tokens in token_sets if term in tokens)

    scores: list[float] = []
    for index, tokens in enumerate(unit_tokens):
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        score = 0.0
        for term in query_terms:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            df = document_frequency.get(term, 0)
            idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
            norm = BM25_K1 * (1 - BM25_B + BM25_B * lengths[index] / avg_length)
            score += idf * (frequency * (BM25_K1 + 1)) / (frequency + norm)
        scores.append(score)
    return scores


# --- Matching delle feature (§5) --------------------------------------------


def _contains_token(unit_tokens: set[str], normalized: str) -> bool:
    if not normalized:
        return False
    parts = normalized.split()
    return all(part in unit_tokens for part in parts) if parts else False


def _contains_disease_phrase(unit_text: str, disease: str) -> bool:
    """Require a contiguous disease phrase, not unordered generic tokens."""
    phrase = normalize_text(disease)
    text = normalize_text(unit_text)
    if not phrase:
        return False
    for match in re.finditer(rf"\b{re.escape(phrase)}\b", text):
        prefix = text[:match.start()].split()
        if prefix and prefix[-1] == "non" and phrase.startswith("small cell "):
            continue
        if phrase == "lung cancer" and prefix[-3:] in (
            ["non", "small", "cell"], ["small", "cell"],
        ):
            continue
        return True
    return False


def _section_class(unit: Mapping[str, Any]) -> str:
    unit_type = str(unit.get("unit_type") or "").upper()
    section = normalize_text(unit.get("section") or "")
    if not section:
        text_prefix = normalize_text(str(unit.get("text") or "").split(":", 1)[0])
        if text_prefix in {"results", "methods", "discussion", "introduction", "background"}:
            section = text_prefix
    if unit_type in {"TABLE_CELL", "TABLE_CAPTION"}:
        return "TABLE"
    if unit_type == "FIGURE_CAPTION":
        return "FIGURE"
    if unit_type in {"TITLE", "TRIAL_TITLE"}:
        return "TITLE"
    if unit_type in {"ABSTRACT", "ABSTRACT_SECTION", "ABSTRACT_SENTENCE", "BRIEF_SUMMARY"}:
        return "ABSTRACT"
    for label, names in {
        "RESULTS": ("result", "results", "outcome", "findings"),
        "METHODS": ("method", "methods", "materials", "patients and methods"),
        "DISCUSSION": ("discussion", "conclusion", "conclusions"),
        "INTRODUCTION": ("introduction", "background"),
    }.items():
        if section in names or any(name in section for name in names):
            return label
    return "OTHER"


def _section_factor(unit: Mapping[str, Any]) -> float:
    return SECTION_FACTOR.get(_section_class(unit), SECTION_FACTOR["OTHER"])


def _text_window(text: str, terms: Sequence[str], radius: int = 90) -> str:
    normalized = normalize_text(text)
    positions = [normalized.find(normalize_text(term)) for term in terms if normalize_text(term)]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return normalized
    start = max(0, min(positions) - radius)
    end = min(len(normalized), max(positions) + radius)
    return normalized[start:end]


def _negation_status(text: str, terms: Sequence[str]) -> str:
    window = _text_window(text, terms)
    if _NEGATION_RE.search(window):
        return "NEGATED"
    if _POSITIVE_CUE_RE.search(window):
        return "POSITIVE_CUE"
    return "UNKNOWN"


def _direction_expected(direction: Any) -> str:
    normalized = normalize_text(direction)
    if not normalized:
        return "UNKNOWN"
    if any(token in normalized for token in ("does not support", "not support", "negative", "resistance", "lack")):
        return "NEGATIVE"
    if any(token in normalized for token in ("support", "sensitive", "response", "benefit", "effective")):
        return "POSITIVE"
    return "UNKNOWN"


def _explicit_alteration_types(text: str) -> set[str]:
    normalized = normalize_text(text)
    return {kind for kind, cues in _ALTERATION_TYPE_CUES.items()
            if any(cue in normalized for cue in cues)}


def _variant_tokens(text: str) -> set[str]:
    return {token for token in tokenize(text) if _VARIANT_TOKEN_RE.fullmatch(token)}


def _pair_distance(text: str, gene: str, alteration: str) -> int | None:
    normalized = normalize_text(text)
    gene_norm, alteration_norm = normalize_gene(gene), normalize_alteration(alteration)
    gene_positions = [match.start() for match in re.finditer(re.escape(gene_norm), normalized)]
    alteration_positions = [match.start() for match in re.finditer(re.escape(alteration_norm), normalized)]
    if not gene_positions or not alteration_positions:
        return None
    return min(abs(left - right) for left in gene_positions for right in alteration_positions)


def _candidate_pairs(selection: SourceUnitSelectionInput) -> tuple[tuple[str, str | None, str | None], ...]:
    return tuple((b.gene or "", b.alteration, b.alteration_type) for b in selection.biomarkers
                 if b.gene or b.alteration)


def match_features(unit_text: str, selection: SourceUnitSelectionInput) -> dict[str, tuple[str, ...]]:
    """Quali feature della GCA compaiono letteralmente nell'unità.

    Il confronto è per token interi: cercare ``V299L`` come sottostringa
    troverebbe anche ``V299LX``, e un match di comodo su un'alterazione è
    esattamente l'errore che rende inutile un grounding documentale.
    """
    tokens = set(tokenize(unit_text))
    normalized_units = {normalize_gene(t) for t in tokens} | {normalize_alteration(t) for t in tokens}

    genes = tuple(g for g in selection.genes if normalize_gene(g) in normalized_units)
    alterations = tuple(a for a in selection.alterations
                        if normalize_alteration(a) in normalized_units)
    interventions = tuple(i for i in selection.interventions
                          if _contains_token(tokens, normalize_drug(i)))
    diseases = tuple(d for d in selection.disease if _contains_disease_phrase(unit_text, d))
    pair_labels: list[str] = []
    hard_reasons: list[str] = []
    mismatch_reasons: list[str] = []
    specificity = "UNKNOWN"
    nearby_variants = _variant_tokens(unit_text)
    for gene, alteration, alteration_type in _candidate_pairs(selection):
        gene_present = bool(gene and normalize_gene(gene) in normalized_units)
        alteration_present = bool(alteration and normalize_alteration(alteration) in normalized_units)
        if gene and alteration and gene_present and alteration_present and (_pair_distance(unit_text, gene, alteration) or 0) <= 120:
            pair_labels.append(f"{gene}:{alteration}")
            specificity = "VARIANT_EXACT"
        elif gene and alteration and gene_present:
            other = {v for v in nearby_variants if normalize_alteration(v) != normalize_alteration(alteration)}
            if other:
                mismatch_reasons.append("EXPLICIT_ALTERATION_MISMATCH")
                specificity = "VARIANT_MISMATCH"
        elif gene_present and not alteration:
            specificity = "GENE_EXACT"
    explicit_types = _explicit_alteration_types(unit_text)
    incompatible_types = {
        "MUTATION": {"AMPLIFICATION", "DELETION", "FUSION", "REARRANGEMENT", "EXPRESSION", "COPY_NUMBER"},
        "AMPLIFICATION": {"MUTATION", "DELETION", "FUSION", "REARRANGEMENT", "EXPRESSION"},
        "FUSION": {"MUTATION", "AMPLIFICATION", "DELETION", "REARRANGEMENT", "EXPRESSION"},
        "DELETION": {"MUTATION", "AMPLIFICATION", "FUSION", "REARRANGEMENT", "EXPRESSION"},
        "REARRANGEMENT": {"MUTATION", "AMPLIFICATION", "DELETION", "FUSION", "EXPRESSION"},
        "EXPRESSION": {"MUTATION", "AMPLIFICATION", "DELETION", "FUSION", "REARRANGEMENT"},
    }
    for biomarker in selection.biomarkers:
        requested = (biomarker.alteration_type or "").upper()
        if requested and requested in incompatible_types and explicit_types & incompatible_types[requested]:
            if biomarker.gene and normalize_gene(biomarker.gene) in normalized_units:
                mismatch_reasons.append("ALTERATION_TYPE_MISMATCH")
    if not pair_labels:
        hard_reasons.extend(mismatch_reasons)
    negation_terms = tuple(selection.genes + selection.alterations + selection.interventions)
    negation = _negation_status(unit_text, negation_terms)
    expected_direction = _direction_expected(selection.direction or selection.graph_relation)
    molecular_compatible = (
        (not selection.genes or bool(genes))
        and (not selection.alterations or bool(alterations))
        and (not selection.interventions or bool(interventions))
    )
    has_other_disease = bool(
        selection.disease and not diseases
        and re.search(
            r"\b(?:[a-z0-9]+ ){0,3}(?:cancer|carcinoma|melanoma|leukemia|lymphoma|sarcoma)\b",
            normalize_text(unit_text),
        )
    )
    relational_cue = bool(re.search(
        r"\b(?:response|sensitivity|resistance|predict|associated|support|benefit)\b",
        normalize_text(unit_text),
    ))
    contrastive = molecular_compatible and not has_other_disease and relational_cue
    polarity_relevance = ""
    direction_compatibility = 0.0
    # A statistical stopping boundary is a qualification of an endpoint,
    # not a negated molecular relation. Preserve it as document context.
    statistical_boundary = re.compile(
        r"\bdid not (?:cross|meet|reach|exceed) (?:the )?"
        r"(?:pre ?specified )?(?:interim analysis |statistical |significance )*"
        r"(?:boundary|threshold)\b"
    )
    normalized_unit = normalize_text(unit_text)
    statistical_caution = bool(
        not has_other_disease and not hard_reasons
        and re.search(r"\b(?:survival|recurrence|response|hazard ratio)\b", normalized_unit)
        and statistical_boundary.search(normalized_unit)
        and not _NEGATION_RE.search(statistical_boundary.sub("", normalized_unit))
    )
    if statistical_caution:
        polarity_relevance = "STATISTICAL_CAUTION"
    elif expected_direction == "POSITIVE":
        direction_compatibility = -1.0 if negation == "NEGATED" else 1.0 if negation == "POSITIVE_CUE" else 0.0
        if negation == "NEGATED":
            if contrastive:
                polarity_relevance = "POLARITY_OPPOSITE_BUT_RELEVANT"
            else:
                hard_reasons.append("EXPLICIT_NEGATION_MISMATCH")
    elif expected_direction == "NEGATIVE":
        direction_compatibility = -1.0 if negation == "POSITIVE_CUE" else 1.0 if negation == "NEGATED" else 0.0
        if negation == "POSITIVE_CUE":
            if contrastive:
                polarity_relevance = "POLARITY_OPPOSITE_BUT_RELEVANT"
            else:
                hard_reasons.append("EXPLICIT_POLARITY_MISMATCH")
    return {"gene": genes, "alteration": alterations,
            "intervention": interventions, "disease": diseases,
            "biomarker_pair": tuple(pair_labels),
            "alteration_specificity": (specificity,),
            "negation_status": (negation,),
            "direction_compatibility": (str(direction_compatibility),),
            "polarity_relevance": (polarity_relevance,),
            "hard_incompatibility": tuple(dict.fromkeys(hard_reasons))}


def _reason(matches: Mapping[str, tuple[str, ...]], unit_type: str, lexical: float) -> str:
    parts: list[str] = []
    for label, key in (("alterazione", "alteration"), ("gene", "gene"),
                       ("farmaco", "intervention"), ("malattia", "disease")):
        if matches[key]:
            parts.append(f"{label}: {', '.join(matches[key])}")
    if not parts:
        parts.append(f"nessuna feature clinica; solo affinità lessicale {lexical:.2f}")
    parts.append(f"tipo unità: {unit_type}")
    return " · ".join(parts)


# --- Selector ---------------------------------------------------------------


def rank(selection: SourceUnitSelectionInput, *, ranking_strategy: str | None = None) -> list[RankedSourceUnit]:
    """Ranking completo, deterministico.

    Il tie-break è ``source_unit_id``: due unità con lo stesso punteggio devono
    ordinarsi allo stesso modo comunque siano arrivate, altrimenti permutare
    l'input cambierebbe la selezione.
    """
    strategy = ranking_strategy or DEFAULT_RANKING_STRATEGY
    if strategy not in {"CLINICAL", "BM25", "BM25_STRUCTURE"}:
        raise ValueError(f"Unsupported SourceUnit ranking strategy: {strategy}")
    units = list(selection.source_units)
    texts = [str(u.get("text") or "") for u in units]
    unit_tokens = [tokenize(t) for t in texts]
    lexical = bm25_scores(selection.query_terms(), unit_tokens)

    scored: list[tuple[float, str, RankedSourceUnit]] = []
    for index, unit in enumerate(units):
        text = texts[index]
        matches = match_features(text, selection)
        unit_type = str(unit.get("unit_type") or "")
        prior = SECTION_PRIOR.get(unit_type, DEFAULT_SECTION_PRIOR)
        section_factor = _section_factor(unit)
        context = min(1.0, len(text) / MIN_CONTEXT_CHARS) if MIN_CONTEXT_CHARS else 1.0
        direction = float(matches["direction_compatibility"][0])
        hard_reasons = tuple(matches["hard_incompatibility"])
        pair_bonus = 5.0 * len(matches["biomarker_pair"])
        specificity_bonus = 2.0 if matches["alteration_specificity"] == ("VARIANT_EXACT",) else 0.5 if matches["alteration_specificity"] == ("GENE_EXACT",) else 0.0
        bonus = (pair_bonus + specificity_bonus
                 + WEIGHT_INTERVENTION * len(matches["intervention"])
                 + WEIGHT_DISEASE * len(matches["disease"])
                 + (2.5 if matches["negation_status"] == ("POSITIVE_CUE",) else 0.0)
                 + (2.5 if matches["polarity_relevance"] == ("POLARITY_OPPOSITE_BUT_RELEVANT",) else 0.0)) * context
        total = (WEIGHT_LEXICAL * lexical[index] + bonus + 2.0 * direction) * section_factor * prior
        if strategy == "BM25":
            total = lexical[index]
        elif strategy == "BM25_STRUCTURE":
            total = lexical[index] * section_factor * prior
        if hard_reasons:
            total = -1_000_000.0

        ranked = RankedSourceUnit(
            source_unit_id=str(unit.get("source_unit_id") or ""),
            rank=0, score_total=total, score_lexical=lexical[index],
            section_prior=prior, unit_type=unit_type, text_length=len(text),
            matched_gene=matches["gene"], matched_alteration=matches["alteration"],
            matched_intervention=matches["intervention"], matched_disease=matches["disease"],
            matched_biomarker_pairs=matches["biomarker_pair"],
            alteration_specificity=matches["alteration_specificity"][0],
            intervention_compatibility=1.0 if matches["intervention"] else 0.0,
            disease_compatibility=1.0 if matches["disease"] else 0.0,
            direction_compatibility=direction,
            negation_status=matches["negation_status"][0],
            polarity_relevance=matches["polarity_relevance"][0],
            section_factor=section_factor,
            context_factor=context,
            selection_reason=(f"{strategy} ranking; identity checks retained · " if strategy != "CLINICAL" else "") + _reason(matches, unit_type, lexical[index]),
            exclusion_reason=hard_reasons[0] if hard_reasons else "",
        )
        scored.append((total, ranked.source_unit_id, ranked))

    scored.sort(key=lambda item: (item[0] < 0, -item[0], item[1]))
    return [RankedSourceUnit(**{**r.__dict__, "rank": position})
            for position, (_, _, r) in enumerate(scored, start=1)]


def _redundant(candidate: RankedSourceUnit, selected: Sequence[RankedSourceUnit], units_by_id: Mapping[str, Mapping[str, Any]]) -> bool:
    text = normalize_text(units_by_id.get(candidate.source_unit_id, {}).get("text"))
    if not text:
        return True
    for other in selected:
        other_text = normalize_text(units_by_id.get(other.source_unit_id, {}).get("text"))
        if not other_text:
            continue
        if text == other_text or text in other_text or other_text in text:
            return True
    return False


def select(selection: SourceUnitSelectionInput, *, top_k: int = DEFAULT_TOP_K,
           min_score: float = 0.0, ranking_strategy: str | None = None,
           ranked_source_units: Sequence[RankedSourceUnit] | None = None) -> SourceUnitSelectionResult:
    """Top-K unità, oppure ``NO_RELEVANT_SOURCE_UNIT``.

    ``min_score`` è disattivato per default. Una soglia va introdotta solo se i
    punteggi separano davvero le unità rilevanti dalle altre: sceglierla per far
    quadrare le metriche significherebbe tararla sul gold.
    """
    strategy = ranking_strategy or DEFAULT_RANKING_STRATEGY
    ranked = (list(ranked_source_units) if ranked_source_units is not None
              else rank(selection, ranking_strategy=strategy))
    if ranked_source_units is not None:
        allowed = {str(u.get("source_unit_id")) for u in selection.source_units}
        ids = [u.source_unit_id for u in ranked]
        if len(ids) != len(set(ids)) or not set(ids).issubset(allowed):
            raise ValueError("Duplicate or unauthorized SourceUnit in supplied ranking")
    units_by_id = {str(u.get("source_unit_id")): u for u in selection.source_units}
    eligible = [u for u in ranked if u.score_total > min_score and not u.exclusion_reason]
    chosen: list[RankedSourceUnit] = []
    # Keep a genuine contrary relation and an endpoint caveat separately when
    # the budget permits, leaving at least one slot for ordinary retrieval.
    reserved = []
    for kind in ("POLARITY_OPPOSITE_BUT_RELEVANT", "STATISTICAL_CAUTION"):
        item = next((item for item in eligible if item.polarity_relevance == kind), None)
        if item is not None and len(reserved) < top_k - 1 and not _redundant(item, reserved, units_by_id):
            reserved.append(item)
    reserved_ids = {item.source_unit_id for item in reserved}

    def fill(limit: int, *, protect_reserved: bool) -> None:
        for item in eligible:
            if len(chosen) >= limit:
                break
            if item.source_unit_id in {row.source_unit_id for row in chosen}:
                continue
            if protect_reserved and (item.source_unit_id in reserved_ids
                                     or _redundant(item, reserved, units_by_id)):
                continue
            if _redundant(item, chosen, units_by_id):
                continue
            chosen.append(item)

    fill(top_k - len(reserved), protect_reserved=True)
    for item in reserved:
        if not _redundant(item, chosen, units_by_id):
            chosen.append(item)
    fill(top_k, protect_reserved=False)
    chosen.sort(key=lambda item: item.rank)
    selected_ids = {item.source_unit_id for item in chosen}
    traced: list[RankedSourceUnit] = []
    for item in ranked:
        if item.exclusion_reason:
            traced.append(item)
        elif item.score_total <= min_score:
            traced.append(replace(item, exclusion_reason="SCORE_BELOW_THRESHOLD"))
        elif item.source_unit_id in selected_ids:
            traced.append(replace(item, selected=True))
        elif _redundant(item, chosen, units_by_id):
            traced.append(replace(item, exclusion_reason="REDUNDANT_SOURCE_UNIT"))
        else:
            traced.append(replace(item, exclusion_reason="TOP_K_BUDGET"))
    selected = tuple(u.source_unit_id for u in chosen)

    status = STATUS_SELECTED if selected else STATUS_NO_COMPATIBLE if ranked and all(u.exclusion_reason for u in ranked) else STATUS_NO_RELEVANT
    if selected:
        head = eligible[0]
        reason = f"{len(selected)} unità su {len(ranked)} · prima: {head.selection_reason}"
    else:
        reason = ("nessuna unità supera la soglia minima: il documento non offre "
                  "materiale pertinente alla candidate")

    return SourceUnitSelectionResult(
        candidate_id=selection.candidate_id, document_id=selection.document_id,
        status=status, top_k=top_k, selected_source_unit_ids=selected,
        ranked_source_units=tuple(traced), selector_version=(SELECTOR_VERSION if strategy == DEFAULT_RANKING_STRATEGY else SELECTOR_VERSION + "/" + strategy),
        input_hash=selection.input_hash(),
        ranking_hash=_hash([u.source_unit_id for u in ranked]),
        selected_ids_hash=_hash(list(selected)),
        selection_reason=reason,
        matched_features={
            "ranking_strategy": strategy,
            "genes": list(selection.genes), "alterations": list(selection.alterations),
            "interventions": list(selection.interventions), "disease": list(selection.disease),
            "query_terms": sorted(set(selection.query_terms())),
        },
    )


# --- Baseline di confronto (§12) --------------------------------------------


def select_first_k(selection: SourceUnitSelectionInput, *, top_k: int = DEFAULT_TOP_K) -> tuple[str, ...]:
    """BASELINE A — le prime K unità del documento, nell'ordine del parser."""
    return tuple(str(u.get("source_unit_id")) for u in selection.source_units[:top_k])


def select_bm25(selection: SourceUnitSelectionInput, *, top_k: int = DEFAULT_TOP_K) -> tuple[str, ...]:
    """BASELINE C — BM25 puro, senza feature cliniche e senza prior."""
    units = list(selection.source_units)
    scores = bm25_scores(selection.query_terms(), [tokenize(u.get("text") or "") for u in units])
    order = sorted(
        ((scores[i], str(u.get("source_unit_id"))) for i, u in enumerate(units)),
        key=lambda item: (-item[0], item[1]),
    )
    return tuple(uid for _, uid in order[:top_k])
