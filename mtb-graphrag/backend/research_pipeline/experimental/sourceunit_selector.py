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
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

SELECTOR_VERSION = "deterministic-sourceunit-selector/1.0"

STATUS_SELECTED = "SELECTED"
STATUS_NO_RELEVANT = "NO_RELEVANT_SOURCE_UNIT"

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
class SourceUnitSelectionInput:
    """Tutto ciò che il selector può guardare. Nient'altro entra."""

    candidate_id: str
    document_id: str
    disease: tuple[str, ...] = ()
    genes: tuple[str, ...] = ()
    alterations: tuple[str, ...] = ()
    interventions: tuple[str, ...] = ()
    graph_relation: str | None = None
    source_units: tuple[Mapping[str, Any], ...] = ()

    @classmethod
    def from_candidate(cls, candidate: Mapping[str, Any], document_id: str,
                       source_units: Sequence[Mapping[str, Any]]) -> "SourceUnitSelectionInput":
        """Estrae le feature dalla GCA.

        ``biomarkers`` mescola geni e varianti distinguendoli con ``type``: una
        variante trattata come gene perderebbe il suo peso, ed è la feature più
        discriminante che abbiamo.
        """
        biomarkers = candidate.get("biomarkers") or []
        genes = _labels([b for b in biomarkers if str(b.get("type") or "").lower() == "gene"])
        alterations = _labels([b for b in biomarkers if str(b.get("type") or "").lower() != "gene"])
        return cls(
            candidate_id=str(candidate.get("candidate_id") or ""),
            document_id=str(document_id),
            disease=_labels(candidate.get("disease")),
            genes=genes,
            alterations=alterations,
            interventions=_labels(candidate.get("interventions")),
            graph_relation=candidate.get("predicate"),
            source_units=tuple(source_units),
        )

    def query_terms(self) -> list[str]:
        """Query lessicale, costruita solo dalla GCA."""
        terms: list[str] = []
        for group in (self.alterations, self.genes, self.interventions, self.disease):
            for value in group:
                terms.extend(tokenize(value))
        return terms

    def input_hash(self) -> str:
        payload = {
            "candidate_id": self.candidate_id, "document_id": self.document_id,
            "disease": list(self.disease), "genes": list(self.genes),
            "alterations": list(self.alterations), "interventions": list(self.interventions),
            "graph_relation": self.graph_relation,
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
    context_factor: float = 1.0
    selection_reason: str = ""

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
            "context_factor": round(self.context_factor, 4),
            "selection_reason": self.selection_reason,
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
    diseases = tuple(d for d in selection.disease if _contains_token(tokens, normalize_text(d)))
    return {"gene": genes, "alteration": alterations,
            "intervention": interventions, "disease": diseases}


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


def rank(selection: SourceUnitSelectionInput) -> list[RankedSourceUnit]:
    """Ranking completo, deterministico.

    Il tie-break è ``source_unit_id``: due unità con lo stesso punteggio devono
    ordinarsi allo stesso modo comunque siano arrivate, altrimenti permutare
    l'input cambierebbe la selezione.
    """
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
        context = min(1.0, len(text) / MIN_CONTEXT_CHARS) if MIN_CONTEXT_CHARS else 1.0

        bonus = (WEIGHT_ALTERATION * len(matches["alteration"])
                 + WEIGHT_GENE * len(matches["gene"])
                 + WEIGHT_INTERVENTION * len(matches["intervention"])
                 + WEIGHT_DISEASE * len(matches["disease"])) * context
        total = (WEIGHT_LEXICAL * lexical[index] + bonus) * prior

        ranked = RankedSourceUnit(
            source_unit_id=str(unit.get("source_unit_id") or ""),
            rank=0, score_total=total, score_lexical=lexical[index],
            section_prior=prior, unit_type=unit_type, text_length=len(text),
            matched_gene=matches["gene"], matched_alteration=matches["alteration"],
            matched_intervention=matches["intervention"], matched_disease=matches["disease"],
            context_factor=context,
            selection_reason=_reason(matches, unit_type, lexical[index]),
        )
        scored.append((total, ranked.source_unit_id, ranked))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [RankedSourceUnit(**{**r.__dict__, "rank": position})
            for position, (_, _, r) in enumerate(scored, start=1)]


def select(selection: SourceUnitSelectionInput, *, top_k: int = DEFAULT_TOP_K,
           min_score: float = 0.0) -> SourceUnitSelectionResult:
    """Top-K unità, oppure ``NO_RELEVANT_SOURCE_UNIT``.

    ``min_score`` è disattivato per default. Una soglia va introdotta solo se i
    punteggi separano davvero le unità rilevanti dalle altre: sceglierla per far
    quadrare le metriche significherebbe tararla sul gold.
    """
    ranked = rank(selection)
    eligible = [u for u in ranked if u.score_total > min_score]
    selected = tuple(u.source_unit_id for u in eligible[:top_k])

    status = STATUS_SELECTED if selected else STATUS_NO_RELEVANT
    if selected:
        head = eligible[0]
        reason = f"{len(selected)} unità su {len(ranked)} · prima: {head.selection_reason}"
    else:
        reason = ("nessuna unità supera la soglia minima: il documento non offre "
                  "materiale pertinente alla candidate")

    return SourceUnitSelectionResult(
        candidate_id=selection.candidate_id, document_id=selection.document_id,
        status=status, top_k=top_k, selected_source_unit_ids=selected,
        ranked_source_units=tuple(ranked), selector_version=SELECTOR_VERSION,
        input_hash=selection.input_hash(),
        ranking_hash=_hash([u.source_unit_id for u in ranked]),
        selected_ids_hash=_hash(list(selected)),
        selection_reason=reason,
        matched_features={
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
