"""Adapter dai record del grafo V2 a `EvidenceStatement` V3.

Non e' una conversione di JSON. Serve a rispondere a una domanda: **il modello di
evidenza V3 riesce a rappresentare i dati che gia' abbiamo, senza perdere nulla di cio'
che c'e' e senza inventare cio' che non c'e'?**

Da qui tre regole che governano ogni mappatura.

**Nessun campo viene dedotto.** Se il record non ha `evidence_level` — e nel pilota
manca nel 54% dei casi — lo statement non ha un livello, non ne ha uno plausibile.
L'assenza e' un dato: e' cio' che misura quanto il grafo sia incompleto, e riempirla
renderebbe la V3 apparentemente migliore falsificando il punto di partenza.

**Ogni mappatura di vocabolario e' dichiarata come tabella**, non sparsa in `if`. Le
tabelle sono ispezionabili e testabili, e un valore non mappato produce `unknown` con
una nota, mai il valore piu' vicino.

**La provenienza risale sempre al record originale.** `graph_record_ids` conserva
l'identificatore V2, così ogni statement resta riconducibile alla riga da cui viene.

Il risultato non e' oggetto di questa fase: l'adapter produce dizionari validati contro
lo JSON Schema, non dataclass. Duplicare lo schema in classi Python creerebbe due
definizioni che possono divergere, e la fonte di verita' deve restare una sola.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "v3.0.0"
ADAPTER_VERSION = "v2_to_v3_adapter/1.0"

# ── Tabelle di mappatura, dichiarate ──────────────────────────────────────────

# `significance` del KG (vocabolario CIViC) -> `direction` V3.
SIGNIFICANCE_TO_DIRECTION: Mapping[str, str] = {
    "sensitivity/response": "sensitivity",
    "sensitivity": "sensitivity",
    "resistance": "resistance",
    "reduced sensitivity": "resistance",
    "adverse response": "lack_of_benefit",
    "no response": "lack_of_benefit",
    "better outcome": "prognostic",
    "poor outcome": "prognostic",
    "positive": "diagnostic",
    "negative": "diagnostic",
    "predisposition": "predisposition",
}

# `evidence_type` del KG **non** e' il disegno dello studio: nel vocabolario CIViC
# vale Predictive, Diagnostic, Prognostic, cioe' il *tipo di affermazione*. Nel modello
# V3 corrisponde a `evidence_scope`. Mapparlo su `evidence_type`, che descrive il
# disegno, sarebbe un errore di categoria.
CIVIC_TYPE_TO_SCOPE: Mapping[str, str] = {
    "predictive": "therapeutic",
    "diagnostic": "diagnostic",
    "prognostic": "prognostic",
    "predisposing": "predisposing",
    "oncogenic": "mechanistic",
    "functional": "mechanistic",
}

# `evidence_direction` del KG -> `assertion_polarity` V3.
DIRECTION_TO_POLARITY: Mapping[str, str] = {
    "supports": "supports",
    "does not support": "does_not_support",
}

# Marcatori di tipo di alterazione nel nome del profilo molecolare. L'ordine conta:
# una mutazione composta va riconosciuta prima della singola.
ALTERATION_MARKERS: Sequence[tuple[str, tuple[str, ...]]] = (
    ("fusion", ("fusion", "rearrange", "::")),
    ("amplification", ("amplification", "amplified")),
    ("deletion", ("deletion", " del ", "loss")),
    ("expression", ("expression", "overexpression")),
    ("msi", ("msi", "microsatellite")),
    ("tmb", ("tmb", "tumor mutational burden")),
)

# Il disegno dello studio **non esiste** nel grafo V2. Non va inferito dal livello di
# evidenza: un livello alto non implica uno studio randomizzato.
EVIDENCE_TYPE_WHEN_ABSENT = "unknown"


@dataclass(frozen=True)
class FieldOutcome:
    """Che cosa e' successo a un campo durante la conversione."""

    field_name: str
    status: str  # "preserved" | "absent_in_source" | "unmapped_value" | "not_representable"
    source_value: Any = None
    target_value: Any = None
    note: str = ""


@dataclass
class AdaptationResult:
    """Esito della conversione di un singolo record."""

    statement: dict[str, Any] | None
    record_id: str
    converted: bool
    reason: str = ""
    field_outcomes: list[FieldOutcome] = field(default_factory=list)

    @property
    def preserved_fields(self) -> list[str]:
        return [f.field_name for f in self.field_outcomes if f.status == "preserved"]

    @property
    def absent_fields(self) -> list[str]:
        return [f.field_name for f in self.field_outcomes if f.status == "absent_in_source"]

    @property
    def unmapped_fields(self) -> list[FieldOutcome]:
        return [f for f in self.field_outcomes if f.status == "unmapped_value"]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _lower(value: Any) -> str:
    return _text(value).casefold()


def is_evidence_record(record: Mapping[str, Any]) -> bool:
    """Un record e' convertibile se e' un'evidenza, non un trial o un farmaco.

    Il criterio e' la presenza di `evidence_id`: i record di trial hanno `nct_id` e
    descrivono uno studio, non una proposizione clinica, e diventeranno
    `trial_references` di altri statement invece di statement a se'.
    """
    return record.get("evidence_id") is not None


def infer_alteration_type(profile_name: str, is_compound: bool) -> tuple[str, str]:
    """Tipo di alterazione dal nome del profilo, con la ragione della scelta.

    Restituisce `unknown` quando nessun marcatore e' presente: un profilo che nomina
    solo una variante puntiforme *sembra* uno SNV, ma il grafo non lo dichiara, e
    dedurlo dalla notazione sarebbe un'inferenza non sostenuta dal dato.
    """
    if is_compound:
        return "compound_mutation", "profilo con piu' varianti proteiche"
    lowered = profile_name.casefold()
    for alteration_type, markers in ALTERATION_MARKERS:
        if any(marker in lowered for marker in markers):
            return alteration_type, f"marcatore '{markers[0]}' nel nome del profilo"
    return "unknown", "nessun marcatore di tipo nel nome del profilo"


def build_source_references(
    record: Mapping[str, Any], presence: Mapping[str, str] | None = None
) -> tuple[list[dict[str, Any]], list[FieldOutcome]]:
    """Costruisce i riferimenti alle fonti dalle citazioni del record.

    `presence` associa a ogni PMID il suo stato nello snapshot: `node` se esiste come
    nodo Publication, `citation_only` se compare solo qui, `absent` altrimenti. E' la
    distinzione emersa dall'audit, dove tutti i PMID del caso A2 esistono soltanto come
    citazione, e senza di essa il grafo sembrerebbe coprirli pienamente.
    """
    raw = record.get("citation_id") or record.get("pmids") or []
    if isinstance(raw, (str, bytes)):
        raw = [raw]
    flattened: list[str] = []
    for item in raw:
        if isinstance(item, (list, tuple)):
            flattened.extend(_text(sub) for sub in item)
        else:
            flattened.append(_text(item))

    outcomes: list[FieldOutcome] = []
    references: list[dict[str, Any]] = []
    unrecognised: list[str] = []

    for citation in dict.fromkeys(value for value in flattened if value):
        source_type, identifier = classify_citation(citation)
        if source_type is None:
            unrecognised.append(citation)
            continue
        references.append(
            {
                "source_id": f"{source_type.upper()}:{identifier}",
                "source_type": source_type,
                "external_identifier": identifier,
                "title": None,
                "publication_date": None,
                "version": None,
                "access_date": None,
                "source_hash": None,
                # Lo stato di presenza e' noto solo per i PMID: e' l'unica famiglia di
                # identificatori per cui l'audit ha interrogato il grafo.
                "presence_in_snapshot": (
                    (presence or {}).get(identifier, "unknown")
                    if source_type == "pubmed" else "unknown"
                ),
            }
        )

    if references:
        outcomes.append(
            FieldOutcome("source_references", "preserved", flattened, len(references))
        )
    else:
        outcomes.append(
            FieldOutcome(
                "source_references", "absent_in_source", flattened or None, None,
                "nessuna citazione riconoscibile: non convertibile in uno statement",
            )
        )
    if unrecognised:
        outcomes.append(
            FieldOutcome(
                "source_references.unrecognised", "unmapped_value", unrecognised, None,
                "identificatori non riconducibili a PMID, PMCID o DOI",
            )
        )
    return references, outcomes


def classify_citation(citation: str) -> tuple[str | None, str]:
    """Riconosce il tipo di identificatore di una citazione.

    Il campo `citation_id` del grafo non e' omogeneo: contiene quasi sempre PMID, ma
    almeno un record porta un DOI. Trattarlo come PMID lo scarterebbe, e lo schema
    prevede gia' `doi` fra i tipi di fonte: la varieta' e' nel dato, non un caso
    limite da ignorare.
    """
    import re

    value = _text(citation)
    if not value:
        return None, ""
    if re.fullmatch(r"(?i)pmc\d+", value):
        return "pmc", value.upper()
    if re.fullmatch(r"(?i)10\.\d{4,9}/\S+", value):
        return "doi", value
    if re.fullmatch(r"\d+", value):
        # Gli zeri iniziali si tolgono **prima** del controllo di plausibilita':
        # "0022277784" e' lo stesso PMID di "22277784", e verificare la lunghezza
        # sulla forma non normalizzata lo scarterebbe.
        stripped = value.lstrip("0") or "0"
        if len(stripped) <= 9:
            return "pubmed", stripped
    return None, value


def build_trial_references(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_nct_set

    return [
        {
            "source_id": nct,
            "source_type": "clinicaltrials_gov",
            "external_identifier": nct,
            "title": None,
            "publication_date": None,
            "version": None,
            "access_date": None,
            "source_hash": None,
            "presence_in_snapshot": "unknown",
        }
        for nct in norm_nct_set(record.get("nct_id") or record.get("nct_ids") or [])
    ]


def adapt_record(
    record: Mapping[str, Any],
    *,
    snapshot_fingerprint: str = "",
    source_presence: Mapping[str, str] | None = None,
    now: str | None = None,
) -> AdaptationResult:
    """Converte un singolo record del grafo in un `EvidenceStatement`."""
    from benchmarks.mtb_evidence.pilot.audit_lib.classify import classify_variant_form
    from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_drug, norm_text

    record_id = _text(record.get("record_id")) or (
        f"evidence:{record.get('evidence_id')}" if record.get("evidence_id") else ""
    )

    if not is_evidence_record(record) and not record.get("record_id"):
        return AdaptationResult(
            None, record_id, False,
            "record non di evidenza: nessun evidence_id",
        )

    outcomes: list[FieldOutcome] = []

    # ── Biomarcatore ──────────────────────────────────────────────────────────
    profile = _text(record.get("molecular_profile") or record.get("subject"))
    if not profile:
        return AdaptationResult(
            None, record_id, False, "nessun profilo molecolare: biomarcatore assente"
        )
    form = classify_variant_form(profile)
    is_compound = bool(record.get("is_compound_mutation")) or form.is_compound
    outcomes.append(FieldOutcome("biomarker.label", "preserved", profile, profile))

    alteration_type, alteration_reason = infer_alteration_type(profile, is_compound)
    outcomes.append(
        FieldOutcome(
            "alteration_type",
            "preserved" if alteration_type != "unknown" else "absent_in_source",
            profile, alteration_type, alteration_reason,
        )
    )

    # ── Malattia ──────────────────────────────────────────────────────────────
    disease_label = _text(record.get("disease"))
    if disease_label:
        outcomes.append(FieldOutcome("disease.label", "preserved", disease_label, disease_label))
    else:
        outcomes.append(FieldOutcome("disease.label", "absent_in_source"))

    # ── Direzione, ambito, polarita' ──────────────────────────────────────────
    significance = _lower(record.get("significance") or record.get("relation"))
    direction = SIGNIFICANCE_TO_DIRECTION.get(significance)
    if direction is None:
        direction = "unknown"
        if significance:
            outcomes.append(
                FieldOutcome(
                    "direction", "unmapped_value", significance, "unknown",
                    "valore di significance non presente nella tabella di mappatura",
                )
            )
        else:
            outcomes.append(FieldOutcome("direction", "absent_in_source"))
    else:
        outcomes.append(FieldOutcome("direction", "preserved", significance, direction))

    civic_type = _lower(record.get("evidence_type"))
    scope = CIVIC_TYPE_TO_SCOPE.get(civic_type, "unknown")
    if civic_type and scope == "unknown":
        outcomes.append(FieldOutcome("evidence_scope", "unmapped_value", civic_type, "unknown"))
    elif civic_type:
        outcomes.append(FieldOutcome("evidence_scope", "preserved", civic_type, scope))
    else:
        outcomes.append(FieldOutcome("evidence_scope", "absent_in_source"))

    raw_direction = _lower(record.get("evidence_direction") or record.get("direction"))
    polarity = DIRECTION_TO_POLARITY.get(raw_direction, "unknown")
    if raw_direction and polarity == "unknown":
        outcomes.append(
            FieldOutcome("assertion_polarity", "unmapped_value", raw_direction, "unknown")
        )
    elif raw_direction:
        outcomes.append(FieldOutcome("assertion_polarity", "preserved", raw_direction, polarity))
    else:
        outcomes.append(FieldOutcome("assertion_polarity", "absent_in_source"))

    # ── Intervento ────────────────────────────────────────────────────────────
    drug = _text(record.get("drug") or record.get("drug_name"))
    intervention = None
    if drug:
        intervention = {
            "label": norm_drug(drug),
            "normalized_identifier": _text(record.get("drug_concept_id")) or None,
            "identifier_system": "rxnorm" if _text(record.get("drug_concept_id")).startswith("rxcui") else None,
            "intervention_class": None,
        }
        outcomes.append(FieldOutcome("intervention.label", "preserved", drug, intervention["label"]))
    else:
        outcomes.append(FieldOutcome("intervention.label", "absent_in_source"))

    # ── Livello di evidenza: preservato, mai dedotto ──────────────────────────
    raw_level = _text(record.get("evidence_level"))
    evidence_level = None
    if raw_level:
        # Il KG mescola scale: A/B/C/D sono CIViC, LEVEL_1/LEVEL_2 sono OncoKB.
        system = "oncokb" if raw_level.upper().startswith("LEVEL") else "civic"
        evidence_level = {
            "system": system,
            "original_value": raw_level,
            # Nessuna normalizzazione: la mappatura fra scale richiede una decisione
            # clinica (open decision E1) e inventarla qui creerebbe un ordinamento
            # che nessuna delle due tassonomie sostiene.
            "normalized_tier": None,
            "interpretation": None,
            "provenance": f"valore originale del grafo V2, scala {system}",
        }
        outcomes.append(FieldOutcome("evidence_level", "preserved", raw_level, raw_level))
    else:
        outcomes.append(
            FieldOutcome(
                "evidence_level", "absent_in_source", None, None,
                "il record non porta un livello: non viene dedotto",
            )
        )

    # ── Fonti ─────────────────────────────────────────────────────────────────
    references, reference_outcomes = build_source_references(record, source_presence)
    outcomes.extend(reference_outcomes)
    if not references:
        return AdaptationResult(
            None, record_id, False,
            "nessuna citazione: uno statement richiede almeno una fonte",
            outcomes,
        )

    # ── Contesto clinico: quasi tutto assente nel V2 ──────────────────────────
    # Nessuno di questi campi esiste nello schema del grafo. Restano ai default
    # 'unknown' e l'esito lo registra: e' la misura di quanto il KG sia incompleto
    # sui qualificatori, ed e' esattamente cio' che la V3 esiste per colmare.
    for absent in ("clinical_context.disease_setting", "clinical_context.stage",
                   "clinical_context.therapy_line", "clinical_context.resection_status",
                   "clinical_context.population"):
        outcomes.append(
            FieldOutcome(absent, "not_representable", None, "unknown",
                         "campo non modellato dallo schema del grafo V2")
        )

    timestamp = now or datetime.now(timezone.utc).isoformat()
    statement: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_statement_id": f"ES-V2-{record_id.replace(':', '-')}",
        "statement_version": 1,
        "biomarker": {
            "label": profile,
            "gene": None,
            "normalized_identifier": None,
            "identifier_system": None,
            "is_compound": is_compound,
            "component_biomarkers": list(form.variants),
        },
        "alteration_type": alteration_type,
        "disease": {
            "label": disease_label or "unknown",
            "ontology": None,
            "ontology_id": None,
            "parent_concept": None,
            "specificity": "unknown",
        },
        "intervention": intervention,
        "regimen": None,
        "direction": direction,
        "evidence_scope": scope,
        "assertion_polarity": polarity,
        "clinical_context": {},
        "evidence_type": EVIDENCE_TYPE_WHEN_ABSENT,
        "evidence_level": evidence_level,
        "source_references": references,
        "trial_references": build_trial_references(record),
        "regulatory_context": None,
        "source_spans": [],
        "provenance": {
            "origin": "frozen_kg",
            "snapshot_fingerprint": snapshot_fingerprint or None,
            "graph_record_ids": [record_id] if record_id else [],
            "extraction_action_id": ADAPTER_VERSION,
            "retrieval_action_id": None,
            "reviewer": None,
            "reviewed_at": None,
            "promotion": None,
        },
        # Un record importato dal grafo non e' revisionato: e' materiale gia' curato
        # a monte, ma la V3 non lo dichiara frozen senza una promozione esplicita.
        "review_status": "pending_verification",
        "validity": None,
        "conflicts": [],
        "created_at": timestamp,
        "updated_at": None,
    }

    outcomes.append(FieldOutcome("provenance.graph_record_ids", "preserved", record_id, record_id))
    return AdaptationResult(statement, record_id, True, "", outcomes)


def record_identifier(record: Mapping[str, Any]) -> str:
    return _text(record.get("record_id")) or (
        f"evidence:{record.get('evidence_id')}" if record.get("evidence_id") else ""
    )


def merge_duplicate_records(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Fonde i record che descrivono la stessa evidenza, unendo i campi.

    Lo stesso `evidence_id` compare in piu' query dell'audit con proiezioni diverse:
    una restituisce `evidence_level`, un'altra no, perche' selezionano colonne diverse.
    Tenere arbitrariamente la prima o l'ultima occorrenza scarterebbe campi che il
    grafo *possiede*, facendolo sembrare piu' povero di quanto sia.

    L'unione e' conservativa: un valore gia' presente non viene sovrascritto, e i campi
    lista vengono uniti preservando l'ordine di prima apparizione. Cosi' il risultato
    non dipende dall'ordine in cui le query sono state eseguite.
    """
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for record in records:
        identifier = record_identifier(record)
        if not identifier:
            # Senza identita' non e' fondibile: passa così com'e'.
            order.append(f"__anon__{len(order)}")
            merged[order[-1]] = dict(record)
            continue
        if identifier not in merged:
            merged[identifier] = dict(record)
            order.append(identifier)
            continue
        target = merged[identifier]
        for key, value in record.items():
            if value in (None, "", [], {}):
                continue
            existing = target.get(key)
            if existing in (None, "", [], {}):
                target[key] = value
            elif isinstance(existing, list) and isinstance(value, list):
                target[key] = existing + [item for item in value if item not in existing]
    return [merged[key] for key in order]


def adapt_records(
    records: Sequence[Mapping[str, Any]],
    *,
    snapshot_fingerprint: str = "",
    source_presence: Mapping[str, str] | None = None,
    now: str | None = None,
) -> list[AdaptationResult]:
    """Converte una sequenza di record, fondendo prima i duplicati."""
    return [
        adapt_record(
            record, snapshot_fingerprint=snapshot_fingerprint,
            source_presence=source_presence, now=now,
        )
        for record in merge_duplicate_records(records)
    ]
