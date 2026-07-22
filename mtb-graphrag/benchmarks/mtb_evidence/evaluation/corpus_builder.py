"""Costruzione dello scope, delle unita' di annotazione e dei packet.

Tre scelte reggono questo modulo, e sono tutte scelte di metodo prima che di
codice.

**Lo scope e' un censimento, non un campione.** Tutte le fonti citate dai 147
statement entrano nel corpus. Con 102 fonti il censimento e' sostenibile, e
rende strutturalmente impossibile la selezione opportunistica: non esiste un
criterio da cui una fonte scomoda possa essere esclusa, perche' non esiste un
criterio.

**Il registro asserisce, non deduce.** Dai metadati bibliografici si ricava solo
cio' che il registro afferma: titolo e disegno dello studio. Setting, linea di
terapia, stadio e popolazione restano `unknown` finche' una persona non legge la
fonte. Dedurli dal titolo produrrebbe profili plausibili e non verificati, che e'
la cosa peggiore che questo corpus possa contenere: un valore sbagliato non si
distingue da uno giusto guardando il file.

**Il packet e' cieco.** L'annotatore non vede il clinical gold, le terapie attese,
le metriche del sistema ne' lo strato della fonte. Se li vedesse, saprebbe quale
risposta fa comodo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from backend.pipeline.evidence.profile_unit import (
    AWAITING_SOURCE_REVIEW,
    COHORT_SINGLE,
    COHORT_UNRESOLVED,
    MACHINE_EXTRACTED,
    UNKNOWN,
    FieldProvenance,
    SourceClinicalProfileUnit,
    blind_id,
    from_reviewed_profile,
    unit_id,
)

from .source_inventory import SourceInventoryEntry

SCOPE_VERSION = "qualification_scope/1.0"

# Disegni asseriti dal registro. `not_determinable_from_registry` e' un valore a
# pieno titolo e non un ripiego: l'assenza di un tipo di pubblicazione clinico
# **non** dimostra che lo studio sia preclinico, e marcarlo tale sarebbe
# un'inferenza che il registro non autorizza.
DESIGN_BY_PUBLICATION_TYPE = (
    ("Randomized Controlled Trial", "randomized_controlled_trial"),
    ("Clinical Trial, Phase IV", "clinical_trial_phase_4"),
    ("Clinical Trial, Phase III", "clinical_trial_phase_3"),
    ("Clinical Trial, Phase II", "clinical_trial_phase_2"),
    ("Clinical Trial, Phase I", "clinical_trial_phase_1"),
    ("Clinical Trial", "clinical_trial_unspecified_phase"),
    ("Validation Study", "validation_study"),
    ("Comparative Study", "comparative_study"),
    ("Case Reports", "case_report"),
    ("Review", "review"),
)
DESIGN_UNDETERMINED = "not_determinable_from_registry"

INCLUDED = "included"
EXCLUDED = "excluded"


def evidence_design_from_metadata(record: Mapping[str, Any] | None) -> tuple[str, str]:
    """Disegno dello studio e motivazione, dai soli tipi di pubblicazione."""
    if not record:
        return DESIGN_UNDETERMINED, "nessun metadato di registro disponibile"
    types = set(record.get("publication_types") or [])
    for label, design in DESIGN_BY_PUBLICATION_TYPE:
        if label in types:
            return design, f"tipo di pubblicazione asserito dal registro: {label}"
    return (
        DESIGN_UNDETERMINED,
        "nessun tipo di pubblicazione riconducibile a un disegno; l'assenza non prova "
        "che lo studio sia preclinico",
    )


@dataclass
class ScopeDecision:
    """Perche' una fonte e' nel corpus, o perche' non lo e'."""

    canonical_source_id: str
    included: bool
    inclusion_reason: str = ""
    exclusion_reason: str = ""
    strata: tuple[str, ...] = ()
    expected_annotation_unit: str = ""
    expected_unit_count: int = 1
    blind_annotation_id: str = ""
    annotation_priority: int = 3

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_source_id": self.canonical_source_id,
            "included": self.included,
            "excluded": not self.included,
            "inclusion_reason": self.inclusion_reason,
            "exclusion_reason": self.exclusion_reason,
            "stratum": list(self.strata),
            "expected_annotation_unit": self.expected_annotation_unit,
            "expected_unit_count": self.expected_unit_count,
            "blind_annotation_id": self.blind_annotation_id,
            "annotation_priority": self.annotation_priority,
        }


def build_scope(
    entries: Sequence[SourceInventoryEntry],
    *,
    orphan_profiles: Sequence[Any] = (),
) -> list[ScopeDecision]:
    """Scope come censimento delle fonti citate dagli statement.

    `orphan_profiles` sono i profili gia' revisionati la cui fonte **non** compare
    in nessuno dei 147 statement. Vengono registrati come esclusi con motivazione
    esplicita invece di essere ignorati: l'assenza di quelle fonti dallo snapshot
    e' un risultato dell'audit, e cancellarla dallo scope la renderebbe invisibile.
    """
    decisions: list[ScopeDecision] = []
    for entry in entries:
        unit_kind = "cohort" if entry.requires_cohort_split else "whole_source"
        decisions.append(
            ScopeDecision(
                canonical_source_id=entry.canonical_source_id,
                included=True,
                inclusion_reason=(
                    "fonte citata da almeno uno dei 147 EvidenceStatement congelati; "
                    "lo scope e' un censimento e non ammette esclusioni discrezionali"
                ),
                strata=entry.strata,
                expected_annotation_unit=unit_kind,
                expected_unit_count=1,
                blind_annotation_id=blind_id(entry.canonical_source_id, "cohort-1"),
                annotation_priority=entry.annotation_priority,
            )
        )

    for profile in orphan_profiles:
        source_id = getattr(profile, "source_id", "")
        pmid = getattr(profile, "pmid", "")
        canonical = f"PMID:{pmid}" if pmid else f"PROFILE:{source_id}"
        decisions.append(
            ScopeDecision(
                canonical_source_id=canonical,
                included=False,
                exclusion_reason=(
                    f"profilo revisionato {source_id} la cui fonte non e' citata da nessuno "
                    "dei 147 statement: la fonte e' assente dallo snapshot e non viene "
                    "inserita artificialmente nel repository V3-A"
                ),
                expected_annotation_unit="whole_source",
                expected_unit_count=0,
                blind_annotation_id=blind_id(canonical, "cohort-1"),
                annotation_priority=3,
            )
        )

    decisions.sort(key=lambda item: (not item.included, item.canonical_source_id))
    return decisions


def build_units(
    entries: Sequence[SourceInventoryEntry],
    *,
    metadata: Mapping[str, Mapping[str, Any]],
    profiles_by_source_id: Mapping[str, Any],
    created_at: str,
) -> list[SourceClinicalProfileUnit]:
    """Una unita' per fonte, o una unita' irrisolta se le coorti non sono separabili."""
    units: list[SourceClinicalProfileUnit] = []

    for entry in entries:
        canonical = entry.canonical_source_id
        statement_ids = entry.statement_ids

        if entry.profile_ids:
            # Il profilo umano preesistente vince: declassarlo perderebbe l'unica
            # revisione reale che il corpus possiede.
            profile = profiles_by_source_id.get(entry.profile_ids[0])
            if profile is not None:
                unit = from_reviewed_profile(
                    profile, canonical_source_id=canonical, statement_ids=statement_ids
                )
                units.append(unit)
                continue

        record = None
        for key in entry.identity.keys:
            if key in metadata:
                record = metadata[key]
                break

        design, design_reason = evidence_design_from_metadata(record)
        provenance: list[FieldProvenance] = []
        if design != DESIGN_UNDETERMINED and record:
            provenance.append(
                FieldProvenance(
                    field_name="evidence_design",
                    value_origin="registry_metadata",
                    source_locator=str(record.get("locator") or ""),
                    access_date=str(record.get("access_date") or ""),
                    asserted_by=str(record.get("retrieved_from") or "registry"),
                    note=design_reason,
                )
            )

        reasons: list[str] = ["nessuna lettura umana della fonte primaria"]
        cohort_state = COHORT_SINGLE
        if entry.requires_cohort_split:
            cohort_state = COHORT_UNRESOLVED
            reasons.append(
                "possibili coorti multiple: " + (entry.cohort_split_reason or "motivo non specificato")
            )

        units.append(
            SourceClinicalProfileUnit(
                profile_unit_id=unit_id(canonical, "cohort-1"),
                canonical_source_id=canonical,
                pmids=entry.identity.pmids,
                dois=entry.identity.dois,
                ncts=entry.identity.ncts,
                title=entry.title,
                cohort_id="cohort-1",
                cohort_state=cohort_state,
                cohort_note=entry.cohort_split_reason,
                evidence_design=design if design != DESIGN_UNDETERMINED else UNKNOWN,
                statement_ids=statement_ids,
                extraction_status=MACHINE_EXTRACTED,
                review_status=AWAITING_SOURCE_REVIEW,
                requires_human_review=True,
                human_review_reasons=tuple(reasons),
                provenance=tuple(provenance),
                blind_annotation_id=blind_id(canonical, "cohort-1"),
                created_at=created_at,
            )
        )

    units.sort(key=lambda unit: unit.profile_unit_id)
    return units


# --- annotation packets -------------------------------------------------------

FIELDS_TO_FILL = (
    ("disease", "Malattia studiata, con la denominazione usata dalla fonte."),
    ("biomarker_requirements", "Alterazioni richieste per l'arruolamento."),
    ("intervention", "Farmaci o interventi somministrati in questo braccio."),
    ("regimen", "Regime completo, incluse le combinazioni."),
    ("comparator", "Braccio di confronto, se esiste."),
    ("population", "Popolazione arruolata."),
    ("stage", "Stadio di malattia."),
    ("setting", "Setting: adiuvante, neoadiuvante, metastatico, altro."),
    ("therapy_line", "Linea di terapia."),
    ("prior_therapies", "Terapie precedenti richieste o ammesse."),
    ("resection_status", "Stato di resezione, se la fonte lo specifica."),
    ("inclusion_criteria", "Criteri di inclusione, in sintesi."),
    ("exclusion_criteria", "Criteri di esclusione, in sintesi."),
    ("evidence_design", "Disegno dello studio."),
)

INSTRUCTIONS = (
    "1. Leggi la fonte primaria. Non compilare nulla da memoria.",
    "2. Compila un campo solo se la fonte lo afferma. Se non lo afferma, lascia "
    "`unknown`: un campo mancante blocca un filtro, un campo sbagliato produce una "
    "raccomandazione applicata al paziente sbagliato.",
    "3. Per ogni campo compilato indica il locator dello span (sezione, tabella, "
    "paragrafo). Un valore senza locator non e' verificabile.",
    "4. Se la fonte descrive piu' coorti, compila una unita' per coorte. Se le "
    "coorti non sono separabili con i dati disponibili, non sceglierne una: "
    "marca `cohort_not_separable` e spiega il problema.",
    "5. Non dedurre da titolo o abstract cio' che il testo non afferma.",
)


def build_packet(
    unit: SourceClinicalProfileUnit,
    *,
    entry: SourceInventoryEntry,
    statements_by_id: Mapping[str, Mapping[str, Any]],
    metadata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Pacchetto di annotazione cieco per una unita'.

    Contiene volutamente **meno** informazione dell'inventario: strato,
    priorita', conteggi e metriche del sistema sono omessi, perche' rivelerebbero
    quanto quella fonte pesa sul risultato.
    """
    record = None
    for key in entry.identity.keys:
        if key in metadata:
            record = metadata[key]
            break

    candidates = []
    for statement_id in unit.statement_ids:
        statement = statements_by_id.get(statement_id)
        if not statement:
            continue
        candidates.append(
            {
                "statement_id": statement_id,
                "disease": (statement.get("disease") or {}).get("label", ""),
                "biomarker": (statement.get("biomarker") or {}).get("label", ""),
                "intervention": (statement.get("intervention") or {}).get("label", ""),
                "direction": statement.get("direction", ""),
                "assertion_polarity": statement.get("assertion_polarity", ""),
            }
        )

    return {
        "blind_annotation_id": unit.blind_annotation_id,
        "profile_unit_id": unit.profile_unit_id,
        "source": {
            "pmids": list(unit.pmids),
            "dois": list(unit.dois),
            "ncts": list(unit.ncts),
            "title": unit.title,
            "locator": str(record.get("locator") or "") if record else "",
            "journal": str(record.get("journal") or "") if record else "",
            "publication_year": str(record.get("publication_year") or "") if record else "",
            "publication_types": list(record.get("publication_types") or []) if record else [],
        },
        "candidate_statements": candidates,
        "fields_to_fill": [
            {"field": name, "guidance": guidance, "value": UNKNOWN, "source_locator": ""}
            for name, guidance in FIELDS_TO_FILL
        ],
        "allowed_unknown": True,
        "detected_issues": list(unit.human_review_reasons),
        "instructions": list(INSTRUCTIONS),
        "contains_clinical_gold": False,
        "contains_expected_therapies": False,
        "contains_system_metrics": False,
        "contains_keep_amend_reject": False,
    }


def render_packet_markdown(packet: Mapping[str, Any]) -> str:
    source = packet["source"]
    lines = [
        f"# Annotazione {packet['blind_annotation_id']}",
        "",
        "## Fonte",
        "",
        f"- **Titolo:** {source.get('title') or '(non disponibile)'}",
        f"- **PMID:** {', '.join(source.get('pmids') or []) or '—'}",
        f"- **DOI:** {', '.join(source.get('dois') or []) or '—'}",
        f"- **NCT:** {', '.join(source.get('ncts') or []) or '—'}",
        f"- **Rivista:** {source.get('journal') or '—'}",
        f"- **Anno:** {source.get('publication_year') or '—'}",
        f"- **Locator:** {source.get('locator') or '—'}",
        "",
        "## Proposizioni candidate",
        "",
        "| statement | malattia | biomarcatore | intervento | direzione |",
        "| --- | --- | --- | --- | --- |",
    ]
    for candidate in packet["candidate_statements"]:
        lines.append(
            f"| `{candidate['statement_id']}` | {candidate['disease']} | "
            f"{candidate['biomarker']} | {candidate['intervention']} | {candidate['direction']} |"
        )

    lines += ["", "## Campi da compilare", "", "| campo | indicazione |", "| --- | --- |"]
    for item in packet["fields_to_fill"]:
        lines.append(f"| `{item['field']}` | {item['guidance']} |")

    if packet["detected_issues"]:
        lines += ["", "## Problemi rilevati automaticamente", ""]
        lines += [f"- {issue}" for issue in packet["detected_issues"]]

    lines += ["", "## Istruzioni", ""]
    lines += [f"{index}. {text.split('. ', 1)[-1] if text[0].isdigit() else text}"
              for index, text in enumerate(packet["instructions"], start=1)]
    lines += [
        "",
        "---",
        "",
        "Questo pacchetto non contiene il clinical gold, le terapie attese, le metriche",
        "del sistema ne' una decisione KEEP/AMEND/REJECT. E' deliberato: sapere quale",
        "valore migliora il sistema renderebbe l'annotazione non indipendente.",
        "",
    ]
    return "\n".join(lines)
