"""Confronto campo per campo fra gold provvisorio e record del grafo.

Regola centrale, presa alla lettera dalla specifica dell'audit: farmaco e PMID
coincidenti **non** bastano a dichiarare una claim corrispondente. Il farmaco e il
PMID sono solo l'ancora che individua i candidati; perche' la corrispondenza sia
completa devono coincidere anche variante/profilo, malattia, direzione, setting,
linea e fonte, per ogni dimensione presente su entrambi i lati.

Nessuna funzione qui modifica il gold. Le divergenze diventano dati; le proposte di
modifica le costruisce `report.py`, e restano proposte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .classify import (
    NOT_MODELLED_QUALIFIERS,
    Classification,
    alteration_types,
    classify_setting,
    classify_variant_form,
    qualifier_status,
)
from .disease import DIFFERENT_SPECIFICITY, disease_relation, diseases_match
from .gold import GoldCase, GoldClaim
from .normalize import norm_drug, norm_nct_set, norm_pmid_set, norm_text

FULL = "full"
PARTIAL = "partial"
UNMATCHED = "unmatched"

# Dimensioni confrontate per stabilire una corrispondenza completa.
COMPARISON_DIMENSIONS = (
    "variant_profile",
    "disease",
    "direction",
    "setting",
    "line",
    "source",
)


@dataclass(frozen=True)
class GraphClaim:
    """Un record di evidenza del grafo, normalizzato per il confronto."""

    record_id: str
    subject: str
    relation: str
    drug: str
    disease: str
    direction: str
    pmids: tuple[str, ...]
    nct_ids: tuple[str, ...]
    setting: Classification
    is_compound: bool
    source_kind: str
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "subject": self.subject,
            "relation": self.relation,
            "drug": self.drug,
            "disease": self.disease,
            "direction": self.direction,
            "pmids": list(self.pmids),
            "nct_ids": list(self.nct_ids),
            "setting": {
                "label": self.setting.label,
                "classification_basis": self.setting.classification_basis,
                "matched_spans": list(self.setting.matched_spans),
                "note": self.setting.note,
            },
            "is_compound_mutation": self.is_compound,
            "source_kind": self.source_kind,
        }


def graph_claim_from_record(
    record: Mapping[str, Any],
    *,
    alias_table: dict[str, str] | None = None,
    source_kind: str = "evidence",
) -> GraphClaim:
    """Costruisce una claim normalizzata da un record grezzo del grafo.

    I nomi di campo seguono gli alias reali restituiti dalle query dell'audit; il
    testo dello statement alimenta le sole euristiche testuali.
    """
    statement = str(record.get("evidence_statement") or "")
    profile = record.get("molecular_profile") or record.get("variant") or ""
    # La forma della variante si legge dal solo nome del profilo: lo statement cita
    # spesso altre varianti di contesto, e includerlo trasformerebbe una mutazione
    # singola in una falsa mutazione composta.
    return GraphClaim(
        record_id=str(record.get("record_id") or record.get("evidence_id") or ""),
        subject=norm_text(profile),
        relation=norm_text(record.get("significance")),
        drug=norm_drug(record.get("drug"), alias_table),
        disease=norm_text(record.get("disease")),
        direction=norm_text(record.get("evidence_direction")),
        pmids=norm_pmid_set(record.get("citation_id")),
        nct_ids=norm_nct_set(record.get("nct_id")),
        setting=classify_setting(statement),
        is_compound=classify_variant_form(profile).is_compound,
        source_kind=source_kind,
        raw=dict(record),
    )


@dataclass(frozen=True)
class FieldComparison:
    dimension: str
    gold_value: str
    graph_value: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "dimension": self.dimension,
            "gold_value": self.gold_value,
            "graph_value": self.graph_value,
            "status": self.status,
            "detail": self.detail,
        }


def _compare_variant_profile(claim: GoldClaim, candidate: GraphClaim) -> FieldComparison:
    gold_form = classify_variant_form(claim.subject)
    gold_value = norm_text(claim.subject)
    if not gold_value or not candidate.subject:
        return FieldComparison(
            "variant_profile", gold_value, candidate.subject, "present_not_compared",
            "un lato non espone il profilo",
        )
    if gold_form.is_compound != candidate.is_compound:
        return FieldComparison(
            "variant_profile",
            gold_value,
            candidate.subject,
            "present_and_conflicts",
            "mutazione singola e mutazione composta non sono la stessa entita'",
        )
    variant_tokens = [token.casefold() for token in gold_form.variants]
    by_variant = any(token in candidate.subject for token in variant_tokens)
    by_substring = gold_value in candidate.subject or candidate.subject in gold_value

    # Quando il gold non nomina una variante puntuale ma un tipo di alterazione
    # ("FGFR2 fusion/rearrangement"), il confronto avviene sul tipo. Le classi
    # restano distinte: una fusione non fa match con una mutazione generica.
    gold_types = alteration_types(claim.subject)
    graph_types = alteration_types(candidate.subject)
    shared_types = gold_types & graph_types
    by_alteration = bool(shared_types)

    agrees = by_variant or by_substring or by_alteration
    if agrees:
        detail = f"tipo di alterazione condiviso: {sorted(shared_types)}" if (
            by_alteration and not (by_variant or by_substring)
        ) else ""
    else:
        detail = (
            f"profilo del grafo non riconducibile al soggetto del gold "
            f"(gold {sorted(gold_types) or 'n/d'}, grafo {sorted(graph_types) or 'n/d'})"
        )
    return FieldComparison(
        "variant_profile",
        gold_value,
        candidate.subject,
        qualifier_status("variant_profile", True, agrees),
        detail,
    )


def _compare_disease(claim: GoldClaim, candidate: GraphClaim) -> FieldComparison:
    gold_value = norm_text(claim.disease)
    if not gold_value or not candidate.disease:
        return FieldComparison(
            "disease", gold_value, candidate.disease, "present_not_compared",
            "un lato non espone la malattia",
        )
    relation = disease_relation(gold_value, candidate.disease)
    agrees = diseases_match(gold_value, candidate.disease)
    detail = f"relazione: {relation}"
    if relation == DIFFERENT_SPECIFICITY:
        detail += " (sottotipo e genitore non sono equivalenti)"
    return FieldComparison(
        "disease",
        gold_value,
        candidate.disease,
        qualifier_status("disease", True, agrees),
        detail,
    )


def _compare_direction(claim: GoldClaim, candidate: GraphClaim) -> FieldComparison:
    gold_value = norm_text(claim.direction)
    if not gold_value or not candidate.direction:
        return FieldComparison(
            "direction", gold_value, candidate.direction, "present_not_compared",
            "un lato non espone la direzione",
        )
    agrees = gold_value.startswith(candidate.direction[:7]) or candidate.direction.startswith(
        gold_value[:7]
    )
    return FieldComparison(
        "direction", gold_value, candidate.direction,
        qualifier_status("direction", True, agrees),
    )


def _compare_source(claim: GoldClaim, candidate: GraphClaim) -> FieldComparison:
    gold_pmids = norm_pmid_set(claim.pmid)
    shared = sorted(set(gold_pmids) & set(candidate.pmids))
    agrees = bool(shared)
    return FieldComparison(
        "source",
        ",".join(gold_pmids),
        ",".join(candidate.pmids),
        qualifier_status("source", bool(candidate.pmids), agrees),
        f"PMID condivisi: {shared}" if shared else "nessun PMID condiviso",
    )


def _compare_unmodelled(dimension: str, claim: GoldClaim, candidate: GraphClaim) -> FieldComparison:
    """Setting e linea: lo schema non li rappresenta, l'euristica e' solo indicativa."""
    return FieldComparison(
        dimension,
        norm_text(claim.mandatory_qualifiers)[:200],
        candidate.setting.label,
        "not_modelled_by_schema",
        "ricavato solo per euristica testuale su evidence_statement; "
        f"span: {list(candidate.setting.matched_spans)}",
    )


@dataclass(frozen=True)
class ClaimMatch:
    claim_id: str
    match_level: str
    matched_record_ids: tuple[str, ...]
    field_comparisons: tuple[FieldComparison, ...]
    conflicting_dimensions: tuple[str, ...]
    unverifiable_dimensions: tuple[str, ...] = ()
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "match_level": self.match_level,
            "matched_record_ids": list(self.matched_record_ids),
            "field_comparisons": [item.as_dict() for item in self.field_comparisons],
            "conflicting_dimensions": list(self.conflicting_dimensions),
            "unverifiable_dimensions": list(self.unverifiable_dimensions),
            "note": self.note,
        }


def _compare_all(claim: GoldClaim, candidate: GraphClaim) -> tuple[FieldComparison, ...]:
    return (
        _compare_variant_profile(claim, candidate),
        _compare_disease(claim, candidate),
        _compare_direction(claim, candidate),
        _compare_unmodelled("setting", claim, candidate),
        _compare_unmodelled("line", claim, candidate),
        _compare_source(claim, candidate),
    )


def _match_abstention_claim(
    claim: GoldClaim, graph_claims: Sequence[GraphClaim]
) -> ClaimMatch:
    """Valuta una claim che afferma l'*assenza* di un'associazione.

    Per una claim di astensione il criterio e' rovesciato: la corrispondenza e'
    completa quando il grafo non produce nulla, e viene meno appena compare un
    percorso terapeutico. Applicare la regola normale la marcherebbe `unmatched`
    proprio quando il gold ha ragione.
    """
    therapeutic = [c for c in graph_claims if c.drug]
    if not therapeutic:
        return ClaimMatch(
            claim_id=claim.claim_id,
            match_level=FULL,
            matched_record_ids=(),
            field_comparisons=(),
            conflicting_dimensions=(),
            note=(
                "claim di astensione confermata dall'assenza: il traversal non "
                "restituisce alcun percorso gene -> evidenza -> terapia"
            ),
        )
    return ClaimMatch(
        claim_id=claim.claim_id,
        match_level=UNMATCHED,
        matched_record_ids=tuple(c.record_id for c in therapeutic),
        field_comparisons=(),
        conflicting_dimensions=("direction",),
        note=(
            f"claim di astensione contraddetta: trovati {len(therapeutic)} percorsi "
            "terapeutici nello snapshot"
        ),
    )


def match_claim(
    claim: GoldClaim,
    graph_claims: Sequence[GraphClaim],
    *,
    alias_table: dict[str, str] | None = None,
) -> ClaimMatch:
    """Classifica una claim del gold in full / partial / unmatched.

    L'ancora e' farmaco + PMID. Se non individua alcun candidato la claim resta
    `unmatched`, e la nota riporta le quasi-corrispondenze (solo farmaco, solo PMID)
    perche' sono l'informazione utile al revisore.
    """
    if norm_text(claim.direction) == "does_not_assert":
        return _match_abstention_claim(claim, graph_claims)

    gold_drug = norm_drug(claim.object, alias_table)
    gold_pmids = set(norm_pmid_set(claim.pmid))

    drug_only = [c for c in graph_claims if gold_drug and c.drug == gold_drug]
    pmid_only = [c for c in graph_claims if gold_pmids & set(c.pmids)]
    anchored = [c for c in drug_only if gold_pmids & set(c.pmids)]

    if not anchored:
        note = (
            f"nessun record con farmaco e PMID insieme; "
            f"record con solo farmaco: {len(drug_only)}, con solo PMID: {len(pmid_only)}"
        )
        best = drug_only or pmid_only
        comparisons = _compare_all(claim, best[0]) if best else ()
        return ClaimMatch(
            claim_id=claim.claim_id,
            match_level=UNMATCHED,
            matched_record_ids=tuple(c.record_id for c in best),
            field_comparisons=comparisons,
            conflicting_dimensions=(),
            note=note,
        )

    scored: list[tuple[int, GraphClaim, tuple[FieldComparison, ...]]] = []
    for candidate in anchored:
        comparisons = _compare_all(claim, candidate)
        conflicts = sum(1 for c in comparisons if c.status == "present_and_conflicts")
        scored.append((conflicts, candidate, comparisons))
    scored.sort(key=lambda item: (item[0], item[1].record_id))

    _, _, comparisons = scored[0]
    conflicting = tuple(
        c.dimension for c in comparisons if c.status == "present_and_conflicts"
    )
    unverifiable = tuple(
        c.dimension for c in comparisons if c.status == "not_modelled_by_schema"
    )

    # La corrispondenza si giudica sulle dimensioni presenti su entrambi i lati.
    # Setting e linea non sono modellati dallo schema: non possono smentire la
    # corrispondenza strutturale, ma nemmeno confermarla, e restano segnalati come
    # non verificabili. "Strutturalmente corrispondente" non significa "applicabile".
    level = FULL if not conflicting else PARTIAL
    note = ""
    if unverifiable:
        note = (
            f"corrispondenza strutturale; i qualificatori {list(unverifiable)} non sono "
            "modellati dallo schema e restano non verificabili sullo snapshot: "
            "l'applicabilita' va decisa da un revisore"
        )
    return ClaimMatch(
        claim_id=claim.claim_id,
        match_level=level,
        matched_record_ids=tuple(c.record_id for _, c, _ in scored),
        field_comparisons=comparisons,
        conflicting_dimensions=conflicting,
        unverifiable_dimensions=unverifiable,
        note=note,
    )


def _diff(expected: Iterable[str], found: Iterable[str]) -> dict[str, list[str]]:
    expected_set, found_set = set(expected), set(found)
    return {
        "expected": sorted(expected_set),
        "found": sorted(found_set),
        "missing": sorted(expected_set - found_set),
        "extra": sorted(found_set - expected_set),
    }


def compare_case(
    case: GoldCase,
    graph_claims: Sequence[GraphClaim],
    *,
    alias_table: dict[str, str] | None = None,
    found_pmids: Iterable[str] = (),
    found_nct_ids: Iterable[str] = (),
    found_therapies: Iterable[str] = (),
    audit_warnings: Sequence[str] = (),
    extra_blockers: Sequence[str] = (),
) -> dict[str, Any]:
    """Costruisce il contenuto di `comparison_with_gold.json` per un caso."""
    therapies = _diff(
        (norm_drug(item, alias_table) for item in case.expected_therapies), found_therapies
    )
    pmids = _diff(norm_pmid_set(case.expected_pmids), found_pmids)
    ncts = _diff(norm_nct_set(case.expected_nct_ids), found_nct_ids)

    matches = [match_claim(claim, graph_claims, alias_table=alias_table) for claim in case.claims]
    full = [m for m in matches if m.match_level == FULL]
    partial = [m for m in matches if m.match_level == PARTIAL]
    unmatched = [m for m in matches if m.match_level == UNMATCHED]

    qualifiers_found: list[dict[str, str]] = []
    qualifiers_missing: list[dict[str, str]] = []
    for match in matches:
        for comparison in match.field_comparisons:
            entry = {"claim_id": match.claim_id, **comparison.as_dict()}
            if comparison.status in {"present_and_agrees", "present_and_conflicts"}:
                qualifiers_found.append(entry)
            else:
                qualifiers_missing.append(entry)

    # Solo le claim che hanno effettivamente un candidato producono conflitti. Per una
    # claim senza riscontro i confronti sono puramente informativi - sono calcolati
    # contro una quasi-corrispondenza - e contarli come conflitti duplicherebbe il
    # blocker "claim senza alcun record corrispondente".
    conflicts = [
        {
            "claim_id": match.claim_id,
            "dimension": comparison.dimension,
            "gold_value": comparison.gold_value,
            "graph_value": comparison.graph_value,
            "detail": comparison.detail,
        }
        for match in matches
        if match.match_level != UNMATCHED
        for comparison in match.field_comparisons
        if comparison.status == "present_and_conflicts"
    ]

    blockers: list[str] = list(extra_blockers)

    if case.expected_abstention:
        # Il gold e' un'astensione limitata allo snapshot: qui il grafo la conferma
        # restando vuoto. Cio' che blocca il freeze e' il contrario, cioe' trovare
        # una terapia o una fonte dove il gold ne nega l'esistenza.
        if therapies["found"]:
            blockers.append(
                f"il caso e' annotato come astensione ma il grafo restituisce terapie: "
                f"{therapies['found']}"
            )
        if pmids["found"] or ncts["found"]:
            blockers.append(
                "il caso e' annotato come astensione ma il grafo restituisce fonti: "
                f"PMID {pmids['found']}, NCT {ncts['found']}"
            )
        if unmatched:
            blockers.append(
                f"claim di astensione contraddette dallo snapshot: "
                f"{[m.claim_id for m in unmatched]}"
            )
        graph_complete = not unmatched
    else:
        if pmids["missing"]:
            blockers.append(f"PMID attesi assenti dallo snapshot: {pmids['missing']}")
        if ncts["missing"]:
            blockers.append(f"NCT attesi assenti dallo snapshot: {ncts['missing']}")
        if therapies["missing"]:
            blockers.append(f"terapie attese non raggiunte dal traversal: {therapies['missing']}")
        if unmatched:
            blockers.append(
                f"claim senza alcun record corrispondente: {[m.claim_id for m in unmatched]}"
            )
        graph_complete = not (
            pmids["missing"] or ncts["missing"] or therapies["missing"] or unmatched
        )

    if conflicts:
        blockers.append(
            f"conflitti di qualificatore non risolti: {sorted({c['dimension'] for c in conflicts})}"
        )

    # I qualificatori non modellati non bloccano il freeze - non sono un difetto del
    # gold - ma vanno dichiarati: una corrispondenza strutturale non dimostra
    # l'applicabilita' clinica quando setting e linea non sono rappresentabili.
    unverifiable = sorted(
        {
            dimension
            for match in matches
            for dimension in match.unverifiable_dimensions
        }
    )
    warnings = list(audit_warnings)
    if unverifiable and (full or partial):
        warnings.append(
            f"dimensioni non verificabili sullo snapshot per le claim corrispondenti: "
            f"{unverifiable}. La corrispondenza e' strutturale, non una conferma di "
            "applicabilita': serve il giudizio del secondo revisore."
        )

    return {
        "case_id": case.case_id,
        "expected_therapies": therapies["expected"],
        "found_therapies": therapies["found"],
        "missing_therapies": therapies["missing"],
        "extra_therapies": therapies["extra"],
        "expected_pmids": pmids["expected"],
        "found_pmids": pmids["found"],
        "missing_pmids": pmids["missing"],
        "extra_pmids": pmids["extra"],
        "expected_nct_ids": ncts["expected"],
        "found_nct_ids": ncts["found"],
        "missing_nct_ids": ncts["missing"],
        "extra_nct_ids": ncts["extra"],
        "expected_claims": [claim.claim_id for claim in case.claims],
        "structurally_matching_claims": [m.as_dict() for m in full],
        "partially_matching_claims": [m.as_dict() for m in partial],
        "unmatched_claims": [m.as_dict() for m in unmatched],
        "qualifiers_found": qualifiers_found,
        "qualifiers_missing": qualifiers_missing,
        "conflicts": conflicts,
        "unverifiable_dimensions": unverifiable,
        "graph_complete": graph_complete,
        "audit_warnings": warnings,
        "freeze_ready": not blockers,
        "freeze_blockers": blockers,
        "matching_rule": (
            "farmaco e PMID sono solo l'ancora; la corrispondenza e' completa solo se "
            "coincidono anche variante/profilo, malattia, direzione, setting, linea e fonte "
            "per ogni dimensione presente su entrambi i lati"
        ),
        "not_modelled_by_schema": sorted(NOT_MODELLED_QUALIFIERS),
    }
