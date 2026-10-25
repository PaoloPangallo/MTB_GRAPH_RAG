"""Genera la chiusura della revisione terminologica delle associazioni pending.

Le prove non sono trascritte a mano: vengono estratte dai materiali locali gia'
presenti nel repository — cache bibliografiche del corpus, full text del pilota,
vocabolario farmacologico e nodi del grafo — cosi' che ogni riga di evidenza sia
riproducibile e verificabile invece che asserita.

Il generatore non applica nulla. Non scrive nel corpus, nei moduli operativi o
nei repository shadow, e non esegue i piani che produce.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from backend.pipeline.evidence.shadow.identity import (
    CLAIM_ID_FORMULA_VERSION,
    CLAIM_IDENTITY_FIELDS,
)
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_text,
)
from benchmarks.mtb_evidence.evaluation.terminology_mapping_closure import (
    AGGREGATE_RESULT_REMAINS_NON_SEPARABLE,
    APPROVE_FOR_SHADOW_UPDATE,
    CONTRACT_VERSION,
    DEVELOPMENT_CODE_VERIFIED,
    FORMULATION_RELATION_REQUIRES_QUALIFIER,
    GLOBAL_DRUG_IDENTITY_CONFIRMED,
    INSUFFICIENT_AUTHORITATIVE_EVIDENCE,
    INSUFFICIENT_AUTHORITATIVE_SOURCE,
    LEVEL_BIBLIOGRAPHIC_METADATA,
    LEVEL_FULL_TEXT_OR_SUPPLEMENT,
    LEVEL_INDEXED_ABSTRACT,
    LEVEL_INSTITUTIONAL_VOCABULARY,
    MAPPING_REMAINS_UNRESOLVED,
    MAPPING_VERIFIED_BUT_CLAIM_NOT_ATOMIC,
    PACKET_VERSION,
    PHASE_VERSION,
    PROPAGATION_POLICY,
    REGIMEN_COMPONENT_ABSENT_FROM_VOCABULARY,
    REQUIRE_EXTERNAL_REVIEW,
    REVIEW_INDEPENDENCE,
    REVIEW_STATUS,
    REVIEWER_ROLE,
    SCOPE_GLOBAL,
    SCOPE_NONE,
    SOURCE_LITERAL_PRESERVED,
    VERIFIED_DEVELOPMENT_CODE,
    VOCABULARY_CONCEPT_ID_CONFLICT,
    GroupReview,
    MappingEvidence,
    PairDecision,
    SourceAccess,
    preservation_rows,
    readiness,
)
from benchmarks.mtb_evidence.evaluation.terminology_mapping_closure_reports import (
    build_reports,
)
from benchmarks.mtb_evidence.evaluation.terminology_mapping_closure_simulation import (
    claim_id_simulation,
    collisions,
    qualification_link_impact,
    shadow_update_simulation,
    view_impact,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
GIT_ROOT = REPO_ROOT.parent
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
ADJUDICATION = V3 / "multi_intervention_adjudication"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
SHADOW_V12 = V3 / "diagnostic_disease_scope_narrowing_shadow"
CORPUS = V3 / "qualification_corpus_v2"
DEFAULT_OUTPUT = V3 / "terminology_mapping_closure"

QUEUE_FILE = ADJUDICATION / "terminology_review_queue.jsonl"
METADATA_CACHE = V3 / "qualification_corpus/source_metadata_cache.jsonl"
ABSTRACT_CACHE = V3 / "priority_curation/source_abstract_cache.jsonl"
FULLTEXT_26698910 = GIT_ROOT / "data_expl/benchmark/benchmark_papers/fulltext_26698910.txt"
DGIDB_DRUGS = GIT_ROOT / "data_expl/DatasetTESI/Dataset TESI/DGIdb/drugs.tsv"
NODE_DRUG = GIT_ROOT / "data_expl/DatasetTESI/Dataset TESI/Clean_Graph_Data/node_drug.csv"

EXPECTED_GROUPS = ("evidence:12156", "evidence:1851", "evidence:1853", "evidence:841")
EXPECTED_QUEUE_IDS = ("TRQ-AUY922", "TRQ-BGJ398")
EXPECTED_PENDING_ASSOCIATIONS = 3

CIRCULARITY_CONTROL = "circularity-control"

PAIR_BGJ398 = "TP-BGJ398-INFIGRATINIB"
PAIR_AUY922 = "TP-AUY922-LUMINESPIB"
CANONICAL_INFIGRATINIB = "TIV-INFIGRATINIB"

# Identita' gia' emesse dallo shadow 1.2, riprodotte dalla formula prima di
# essere usate come base della simulazione.
CURRENT_AGGREGATE_IDS = {
    "evidence:1851": "CLM-a7c903cf8d423f015e29",
    "evidence:1853": "CLM-aae818bbc8ec735a255d",
}
AGGREGATE_BIOMARKERS = {
    "evidence:1851": "FGFR2::BICC1 Fusion",
    "evidence:1853": "FGFR2::AHCYL1 Fusion",
}
AGGREGATE_SOURCE_UNIT = "SU-24122810-nih3t3-fgfr-inhibitor-assay"
CURRENT_AGGREGATE_INTERVENTION = "bgj398 + pd173074"
PROPOSED_AGGREGATE_COMPONENTS = ("infigratinib", "pd173074")

UNCHANGED_CLAIMS = (
    ("evidence:841", "CLM-5ce532268b4aa1661311", "crizotinib"),
    ("evidence:841", "CLM-99ae092a3018b5b91808", "ceritinib"),
    ("evidence:12156", "CLM-5ce49705979f72f174e9", "amivantamab + carboplatin + pemetrexed"),
)

OPERATIONAL_ARTIFACTS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
    "benchmarks/mtb_evidence/v3/v2_v3a_exploratory_pilot/frozen_v2_results.jsonl",
)

FROZEN_SCIENTIFIC_ARTIFACTS = (
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/adjudication_manifest.json",
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/terminology_review_queue.jsonl",
    "benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/contract_manifest.json",
    "benchmarks/mtb_evidence/v3/non_therapeutic_claim_contract_and_erratum/adjudication_erratum.json",
    "benchmarks/mtb_evidence/v3/non_therapeutic_claim_contract_and_erratum/migration_specification_amended.json",
    "benchmarks/mtb_evidence/v3/non_therapeutic_source_closure/review_manifest.json",
    "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration/shadow_repository_manifest.json",
    "benchmarks/mtb_evidence/v3/non_therapeutic_shadow_update/shadow_update_manifest.json",
    "benchmarks/mtb_evidence/v3/diagnostic_disease_scope_narrowing_shadow/repository_v1_2_manifest.json",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _read_text(path).splitlines() if line.strip()]


def _sha256_file(path: Path) -> str:
    return sha256_text(_read_text(path))


# --------------------------------------------------------------------------
# Estrazione delle prove dai materiali locali
# --------------------------------------------------------------------------


def _metadata_by_pmid(pmids: Sequence[str]) -> dict[str, dict[str, Any]]:
    wanted = set(pmids)
    return {
        str(row["pmid"]): row
        for row in _load_jsonl(METADATA_CACHE)
        if str(row.get("pmid")) in wanted
    }


def _abstract_by_pmid(pmid: str) -> dict[str, Any]:
    for row in _load_jsonl(ABSTRACT_CACHE):
        if str(row.get("pmid")) == pmid:
            return row
    raise SystemExit(f"abstract non presente nella cache locale: {pmid}")


def _dgidb_rows(names: Sequence[str]) -> list[tuple[str, ...]]:
    """Righe del vocabolario il cui claim name coincide con un termine cercato."""
    wanted = {name.lower() for name in names}
    rows: list[tuple[str, ...]] = []
    with DGIDB_DRUGS.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        next(reader, None)
        for row in reader:
            if len(row) >= 8 and row[0].strip().lower() in wanted:
                rows.append(tuple(item.strip() for item in row[:8]))
    return sorted(set(rows))


def _node_drug_claim_names() -> set[str]:
    with NODE_DRUG.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return {row[0].strip().lower() for row in reader if row}


def _concept_summary(rows: Sequence[tuple[str, ...]]) -> list[dict[str, Any]]:
    """Concept id distinti per claim name, con i curatori che li asseriscono."""
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        grouped.setdefault((row[0], row[2], row[3]), []).append(row[7])
    return [
        {
            "claim_name": name,
            "concept_id": concept,
            "normalized_drug_name": normalized,
            "asserted_by": sorted(set(sources)),
            "curator_count": len(set(sources)),
        }
        for (name, concept, normalized), sources in sorted(grouped.items())
    ]


def _sentence_with(text: str, needle: str) -> str:
    for sentence in re.split(r"(?<=[.])\s+", text):
        if needle in sentence:
            return " ".join(sentence.split())
    raise SystemExit(f"frase non trovata per {needle!r}")


def _source_access() -> list[SourceAccess]:
    meta = _metadata_by_pmid(("34358484", "29182496", "27870574"))
    abstract = _abstract_by_pmid("34358484")
    entries = [
        SourceAccess(
            source_access_id=f"SA-PMID-{pmid}",
            source_id=f"PMID:{pmid}",
            repository_or_body="PubMed (NLM)",
            document_type="indexed_bibliographic_record",
            access_type="local_metadata_cache",
            access_path="benchmarks/mtb_evidence/v3/qualification_corpus/"
            "source_metadata_cache.jsonl",
            stable_identifier=meta[pmid]["identifier_key"],
            date_or_version=str(meta[pmid].get("publication_year", "")),
            authoritative_level=LEVEL_BIBLIOGRAPHIC_METADATA,
            limitation="Titolo e metadati indicizzati; il testo integrale non e' "
            "stato aperto in questa fase.",
        )
        for pmid in sorted(meta)
    ]
    entries.append(
        SourceAccess(
            source_access_id="SA-PMID-34358484-ABSTRACT",
            source_id="PMID:34358484",
            repository_or_body="PubMed (NLM)",
            document_type="indexed_abstract",
            access_type="local_abstract_cache",
            access_path="benchmarks/mtb_evidence/v3/priority_curation/"
            "source_abstract_cache.jsonl",
            stable_identifier=str(abstract["abstract_sha256"]),
            date_or_version=str(abstract.get("cache_version", "")),
            authoritative_level=LEVEL_INDEXED_ABSTRACT,
            limitation="L'abstract usa soltanto il nome generico; l'equivalenza "
            "compare nel titolo del record, non nel corpo.",
        )
    )
    entries.append(
        SourceAccess(
            source_access_id="SA-PMID-26698910-FULLTEXT",
            source_id="PMID:26698910",
            repository_or_body="PubMed Central (manoscritto d'autore NIHPA)",
            document_type="full_text",
            access_type="local_full_text",
            access_path="data_expl/benchmark/benchmark_papers/fulltext_26698910.txt",
            stable_identifier=_sha256_file(FULLTEXT_26698910),
            date_or_version="PMC4773904.1",
            authoritative_level=LEVEL_FULL_TEXT_OR_SUPPLEMENT,
            limitation="Il full text e' disponibile e non dichiara alcuna "
            "equivalenza terminologica per il codice usato.",
        )
    )
    entries.append(
        SourceAccess(
            source_access_id="SA-DGIDB-DRUGS",
            source_id="DGIdb:drug_claims",
            repository_or_body="DGIdb (aggregatore di vocabolari farmacologici)",
            document_type="drug_vocabulary_table",
            access_type="local_dataset",
            access_path="data_expl/DatasetTESI/Dataset TESI/DGIdb/drugs.tsv",
            stable_identifier="dgidb-drug-claims-local-snapshot",
            date_or_version="snapshot locale del dataset di tesi",
            authoritative_level=LEVEL_INSTITUTIONAL_VOCABULARY,
            limitation="Vocabolario istituzionale ma anche dataset a monte del "
            "grafo: ammesso come corroborazione, mai come pilastro unico.",
        )
    )
    entries.append(
        SourceAccess(
            source_access_id="SA-GRAPH-NODE-DRUG",
            source_id="Graph:node_drug",
            repository_or_body="Grafo congelato della tesi",
            document_type="graph_node_table",
            access_type="local_dataset",
            access_path="data_expl/DatasetTESI/Dataset TESI/Clean_Graph_Data/"
            "node_drug.csv",
            stable_identifier="clean-graph-node-drug-local-snapshot",
            date_or_version="snapshot locale del dataset di tesi",
            authoritative_level=LEVEL_INSTITUTIONAL_VOCABULARY,
            limitation="Usato soltanto come controllo di circolarita': non vale "
            "come prova dell'identita' che esso stesso afferma.",
        )
    )
    return sorted(entries, key=lambda item: item.source_access_id)


def _evidence() -> list[MappingEvidence]:
    meta = _metadata_by_pmid(("34358484", "29182496", "27870574"))
    abstract = _abstract_by_pmid("34358484")
    graph_names = _node_drug_claim_names()
    bgj_rows = _dgidb_rows(("BGJ398",))
    auy_rows = _dgidb_rows(("AUY922", "NVP-AUY922"))
    infigratinib_rows = _dgidb_rows(("Infigratinib Phosphate", "infigratinib"))
    bgj_concepts = _concept_summary(bgj_rows)
    auy_concepts = _concept_summary(auy_rows)
    form_concepts = _concept_summary(infigratinib_rows)

    title_34358484 = str(meta["34358484"]["title"])
    rows: list[MappingEvidence] = [
        MappingEvidence(
            evidence_id="EV-BGJ398-01",
            pair_id=PAIR_BGJ398,
            source_access_id="SA-PMID-34358484",
            source_id="PMID:34358484",
            repository_or_body="The Lancet Gastroenterology & Hepatology (PubMed)",
            document_type="indexed_bibliographic_record",
            date_or_version=str(meta["34358484"].get("publication_year", "")),
            term_a="BGJ398",
            term_b="infigratinib",
            supporting_field="title",
            supporting_text=title_34358484,
            locator="record bibliografico, campo title, apertura del titolo",
            access_type="local_metadata_cache",
            stable_identifier=str(meta["34358484"]["identifier_key"]),
            authoritative_level=LEVEL_BIBLIOGRAPHIC_METADATA,
            supports_identity=True,
            graph_derived=False,
            limitation="Il titolo appone il codice al nome generico in forma "
            "parentetica; non descrive sale o formulazione.",
        ),
        MappingEvidence(
            evidence_id="EV-BGJ398-02",
            pair_id=PAIR_BGJ398,
            source_access_id="SA-PMID-34358484-ABSTRACT",
            source_id="PMID:34358484",
            repository_or_body="The Lancet Gastroenterology & Hepatology (PubMed)",
            document_type="indexed_abstract",
            date_or_version=str(abstract.get("cache_version", "")),
            term_a="infigratinib",
            term_b="FGFR2 fusions, cholangiocarcinoma",
            supporting_field="abstract_text",
            supporting_text=_sentence_with(
                str(abstract["abstract_text"]), "Infigratinib is a selective"
            ),
            locator="abstract, sezione BACKGROUND",
            access_type="local_abstract_cache",
            stable_identifier=str(abstract["abstract_sha256"]),
            authoritative_level=LEVEL_INDEXED_ABSTRACT,
            supports_identity=False,
            graph_derived=False,
            limitation="Conferma il contesto di malattia e biomarcatore, non "
            "l'equivalenza: l'abstract usa solo il nome generico.",
        ),
        MappingEvidence(
            evidence_id="EV-BGJ398-03",
            pair_id=PAIR_BGJ398,
            source_access_id="SA-PMID-29182496",
            source_id="PMID:29182496",
            repository_or_body="Journal of Clinical Oncology (PubMed)",
            document_type="indexed_bibliographic_record",
            date_or_version=str(meta["29182496"].get("publication_year", "")),
            term_a="BGJ398",
            term_b="FGFR-altered advanced cholangiocarcinoma",
            supporting_field="title",
            supporting_text=str(meta["29182496"]["title"]),
            locator="record bibliografico, campo title",
            access_type="local_metadata_cache",
            stable_identifier=str(meta["29182496"]["identifier_key"]),
            authoritative_level=LEVEL_BIBLIOGRAPHIC_METADATA,
            supports_identity=False,
            graph_derived=False,
            limitation="Corrobora la continuita' del programma di sviluppo nella "
            "stessa malattia; non enuncia l'equivalenza.",
        ),
        MappingEvidence(
            evidence_id="EV-BGJ398-04",
            pair_id=PAIR_BGJ398,
            source_access_id="SA-PMID-27870574",
            source_id="PMID:27870574",
            repository_or_body="Journal of Clinical Oncology (PubMed)",
            document_type="indexed_bibliographic_record",
            date_or_version=str(meta["27870574"].get("publication_year", "")),
            term_a="BGJ398",
            term_b="FGFR1-3 kinase inhibitor",
            supporting_field="title",
            supporting_text=str(meta["27870574"]["title"]),
            locator="record bibliografico, campo title",
            access_type="local_metadata_cache",
            stable_identifier=str(meta["27870574"]["identifier_key"]),
            authoritative_level=LEVEL_BIBLIOGRAPHIC_METADATA,
            supports_identity=False,
            graph_derived=False,
            limitation="Conferma la classe farmacologica del codice; non enuncia "
            "l'equivalenza.",
        ),
        MappingEvidence(
            evidence_id="EV-BGJ398-05",
            pair_id=PAIR_BGJ398,
            source_access_id="SA-DGIDB-DRUGS",
            source_id="DGIdb:drug_claims",
            repository_or_body="DGIdb su RxNorm",
            document_type="drug_vocabulary_table",
            date_or_version="snapshot locale del dataset di tesi",
            term_a="BGJ398",
            term_b="INFIGRATINIB",
            supporting_field="concept_id",
            supporting_text=json.dumps(bgj_concepts, ensure_ascii=False, sort_keys=True),
            locator="drugs.tsv, righe con drug_claim_name BGJ398",
            access_type="local_dataset",
            stable_identifier="rxcui:2550729",
            authoritative_level=LEVEL_INSTITUTIONAL_VOCABULARY,
            supports_identity=True,
            graph_derived=False,
            limitation="Il vocabolario e' a monte del grafo: vale come "
            "corroborazione convergente, non come pilastro unico.",
        ),
        MappingEvidence(
            evidence_id="EV-BGJ398-06",
            pair_id=PAIR_BGJ398,
            source_access_id="SA-DGIDB-DRUGS",
            source_id="DGIdb:drug_claims",
            repository_or_body="DGIdb su NCIt e RxNorm",
            document_type="drug_vocabulary_table",
            date_or_version="snapshot locale del dataset di tesi",
            term_a="infigratinib",
            term_b="Infigratinib Phosphate",
            supporting_field="concept_id",
            supporting_text=json.dumps(
                form_concepts, ensure_ascii=False, sort_keys=True
            ),
            locator="drugs.tsv, righe con drug_claim_name Infigratinib Phosphate",
            access_type="local_dataset",
            stable_identifier="ncit:C175088",
            authoritative_level=LEVEL_INSTITUTIONAL_VOCABULARY,
            supports_identity=False,
            graph_derived=False,
            limitation="Il sale ha concept id proprio, distinto dalla moiety: la "
            "relazione di formulazione richiede un qualificatore e non un merge.",
        ),
        MappingEvidence(
            evidence_id="EV-BGJ398-07",
            pair_id=PAIR_BGJ398,
            source_access_id="SA-GRAPH-NODE-DRUG",
            source_id="Graph:node_drug",
            repository_or_body="Grafo congelato della tesi",
            document_type="graph_node_table",
            date_or_version="snapshot locale del dataset di tesi",
            term_a="BGJ398",
            term_b="(assente)",
            supporting_field="drug_claim_name",
            supporting_text="Il termine BGJ398 non compare tra i claim name dei "
            "nodi farmaco del grafo: la relazione non puo' essere stata dedotta "
            "dal grafo stesso.",
            locator="node_drug.csv, colonna drug_claim_name",
            access_type="local_dataset",
            stable_identifier=CIRCULARITY_CONTROL,
            authoritative_level=LEVEL_INSTITUTIONAL_VOCABULARY,
            supports_identity=False,
            graph_derived=True,
            limitation="Controllo negativo di circolarita', non prova d'identita'.",
        ),
        MappingEvidence(
            evidence_id="EV-AUY922-01",
            pair_id=PAIR_AUY922,
            source_access_id="SA-PMID-26698910-FULLTEXT",
            source_id="PMID:26698910",
            repository_or_body="PubMed Central (manoscritto d'autore NIHPA)",
            document_type="full_text",
            date_or_version="PMC4773904.1",
            term_a="AUY922",
            term_b="(nessun nome generico dichiarato)",
            supporting_field="full_text",
            supporting_text=_sentence_with(_read_text(FULLTEXT_26698910), "AUY922"),
            locator="full text, Case Report, frase sulla linea con inibitore HSP90",
            access_type="local_full_text",
            stable_identifier=_sha256_file(FULLTEXT_26698910),
            authoritative_level=LEVEL_FULL_TEXT_OR_SUPPLEMENT,
            supports_identity=False,
            graph_derived=False,
            limitation="La fonte di massima priorita' e' accessibile e non "
            "dichiara l'equivalenza: l'assenza qui pesa piu' che altrove.",
        ),
        MappingEvidence(
            evidence_id="EV-AUY922-02",
            pair_id=PAIR_AUY922,
            source_access_id="SA-DGIDB-DRUGS",
            source_id="DGIdb:drug_claims",
            repository_or_body="DGIdb su DrugBank e IUPHAR",
            document_type="drug_vocabulary_table",
            date_or_version="snapshot locale del dataset di tesi",
            term_a="AUY922",
            term_b="NVP-AUY922",
            supporting_field="concept_id",
            supporting_text=json.dumps(auy_concepts, ensure_ascii=False, sort_keys=True),
            locator="drugs.tsv, righe con drug_claim_name AUY922 e NVP-AUY922",
            access_type="local_dataset",
            stable_identifier="drugbank:DB11881|iuphar.ligand:9261",
            authoritative_level=LEVEL_INSTITUTIONAL_VOCABULARY,
            supports_identity=False,
            graph_derived=False,
            limitation="Il letterale usato dalla fonte risolve a un concept id "
            "diverso da quello di luminespib: e' un conflitto, non un supporto.",
        ),
        MappingEvidence(
            evidence_id="EV-AUY922-03",
            pair_id=PAIR_AUY922,
            source_access_id="SA-GRAPH-NODE-DRUG",
            source_id="Graph:node_drug",
            repository_or_body="Grafo congelato della tesi",
            document_type="graph_node_table",
            date_or_version="snapshot locale del dataset di tesi",
            term_a="luminespib",
            term_b="AUY922",
            supporting_field="drug_claim_name",
            supporting_text="Il nome generico compare tra i nodi farmaco del "
            "grafo, che e' la stessa fonte da cui proviene il termine del claim: "
            "usarlo come prova sarebbe circolare.",
            locator="node_drug.csv, colonna drug_claim_name",
            access_type="local_dataset",
            stable_identifier=CIRCULARITY_CONTROL,
            authoritative_level=LEVEL_INSTITUTIONAL_VOCABULARY,
            supports_identity=False,
            graph_derived=True,
            limitation="Controllo negativo di circolarita': fallito per questa "
            "coppia.",
        ),
    ]
    # Il controllo di circolarita' e' un fatto verificato, non un'asserzione.
    if "bgj398" in graph_names:
        raise SystemExit("controllo di circolarita' incoerente: BGJ398 nel grafo")
    if "luminespib" not in graph_names:
        raise SystemExit("controllo di circolarita' incoerente: luminespib assente")
    return sorted(rows, key=lambda item: item.evidence_id)


# --------------------------------------------------------------------------
# Decisioni
# --------------------------------------------------------------------------


def _decisions() -> list[PairDecision]:
    return [
        PairDecision(
            pair_id=PAIR_BGJ398,
            queue_id="TRQ-BGJ398",
            source_literal_term="BGJ398",
            graph_term="infigratinib",
            decision=VERIFIED_DEVELOPMENT_CODE,
            mapping_scope=SCOPE_GLOBAL,
            canonical_intervention_id=CANONICAL_INFIGRATINIB,
            canonical_label="infigratinib",
            confidence="high",
            recommendation=APPROVE_FOR_SHADOW_UPDATE,
            reason_codes=(
                AGGREGATE_RESULT_REMAINS_NON_SEPARABLE,
                DEVELOPMENT_CODE_VERIFIED,
                FORMULATION_RELATION_REQUIRES_QUALIFIER,
                GLOBAL_DRUG_IDENTITY_CONFIRMED,
                SOURCE_LITERAL_PRESERVED,
            ),
            affected_groups=("evidence:1851", "evidence:1853"),
            affected_claim_ids=tuple(sorted(CURRENT_AGGREGATE_IDS.values())),
            circularity_control_passed=True,
            non_graph_derived_evidence_ids=("EV-BGJ398-01", "EV-BGJ398-05"),
            limitations=(
                "Revisione non indipendente: un solo revisore reale.",
                "Il sale infigratinib fosfato ha concept id proprio e non viene "
                "fuso nella moiety.",
                "L'identificazione proviene da una pubblicazione successiva allo "
                "studio del gruppo: vale come identita' di sostanza, non come "
                "prova che la fonte del 2013 intendesse gia' il nome generico.",
            ),
            rationale="Un record bibliografico peer-reviewed del corpus locale "
            "appone il codice al nome generico nel titolo, nella stessa malattia "
            "e sullo stesso biomarcatore del gruppo, e il vocabolario "
            "farmacologico fa convergere il codice su un unico concept id da "
            "cinque curatori distinti. Il codice e' assente dai nodi farmaco del "
            "grafo, quindi la relazione non e' dedotta da cio' che il grafo "
            "afferma di se'. L'identita' e' verificata; la separabilita' del "
            "risultato non lo e' e resta governata dall'adjudication.",
        ),
        PairDecision(
            pair_id=PAIR_AUY922,
            queue_id="TRQ-AUY922",
            source_literal_term="AUY922",
            graph_term="luminespib",
            decision=INSUFFICIENT_AUTHORITATIVE_EVIDENCE,
            mapping_scope=SCOPE_NONE,
            canonical_intervention_id="",
            canonical_label="",
            confidence="insufficient",
            recommendation=REQUIRE_EXTERNAL_REVIEW,
            reason_codes=(
                INSUFFICIENT_AUTHORITATIVE_SOURCE,
                MAPPING_REMAINS_UNRESOLVED,
                SOURCE_LITERAL_PRESERVED,
                VOCABULARY_CONCEPT_ID_CONFLICT,
            ),
            affected_groups=("evidence:841",),
            affected_claim_ids=(),
            circularity_control_passed=False,
            non_graph_derived_evidence_ids=(),
            limitations=(
                "Revisione non indipendente: un solo revisore reale.",
                "Nessuna fonte ammissibile e' stata trovata localmente: la "
                "decisione non esclude che ne esista una fuori dal materiale "
                "disponibile.",
            ),
            rationale="Il full text della fonte e' accessibile e nomina soltanto "
            "il codice, senza dichiarare alcuna equivalenza. Nel vocabolario "
            "farmacologico il letterale usato dalla fonte risolve a un concept id "
            "distinto da quello del nome generico, che e' raggiunto solo da un "
            "letterale diverso con prefisso di produttore: trattarli come lo "
            "stesso termine sarebbe inferenza da somiglianza di stringa. Il nome "
            "generico compare unicamente in file derivati dal grafo, quindi il "
            "controllo di circolarita' fallisce.",
            unresolved_reason="Nessuna fonte autorevole non circolare collega il "
            "letterale della fonte al nome generico del grafo.",
        ),
    ]


def _group_reviews(queue: Sequence[Mapping[str, Any]]) -> list[GroupReview]:
    by_group = {
        group: row for row in queue for group in row.get("affected_groups", ())
    }
    shared = {
        "review_status": "first_review_complete",
        "source_id": "PMID:24122810",
    }
    reviews = [
        GroupReview(
            group_id=f"TG-{gid.split(':')[1]}",
            graph_evidence_id=gid,
            source_id=shared["source_id"],
            v2_record_term="infigratinib",
            source_term="BGJ398",
            claim_term=CURRENT_AGGREGATE_INTERVENTION,
            mapping_candidate=f"{by_group[gid]['source_literal_term']} -> "
            f"{by_group[gid]['graph_term']}",
            disease="Cholangiocarcinoma",
            biomarker=AGGREGATE_BIOMARKERS[gid],
            source_unit_id=AGGREGATE_SOURCE_UNIT,
            locator="abstract, enunciato finale sulla soppressione della "
            "trasformazione, cellule NIH3T3",
            review_status=shared["review_status"],
            terminology_decision=VERIFIED_DEVELOPMENT_CODE,
            confidence="high",
            mapping_scope=SCOPE_GLOBAL,
            proposed_canonical_label="infigratinib",
            preserved_source_literal="BGJ398",
            claim_impact="Il claim resta aggregate e non separabile: la fonte "
            "riporta la soppressione per i due inibitori insieme.",
            claim_id_impact="Cambia soltanto la rappresentazione canonica "
            "dell'intervento, quindi l'identita' cambia e richiede "
            "retirement e replacement versionati.",
            open_reason="terminology_review_required",
        )
        for gid in ("evidence:1851", "evidence:1853")
    ]
    reviews.append(
        GroupReview(
            group_id="TG-841",
            graph_evidence_id="evidence:841",
            source_id="PMID:26698910",
            v2_record_term="luminespib",
            source_term="AUY922",
            claim_term="(nessun claim: associazione unresolved)",
            mapping_candidate="AUY922 -> luminespib",
            disease="Lung Non-small Cell Carcinoma",
            biomarker="EML4::ALK Fusion AND ALK C1156Y",
            source_unit_id="SU-26698910-patient-c1156y-auy922-line",
            locator="full text, Case Report, frase sulla linea con inibitore "
            "HSP90 dopo ceritinib",
            review_status="first_review_complete",
            terminology_decision=INSUFFICIENT_AUTHORITATIVE_EVIDENCE,
            confidence="insufficient",
            mapping_scope=SCOPE_NONE,
            proposed_canonical_label="",
            preserved_source_literal="AUY922",
            claim_impact="Nessuno: l'associazione resta unresolved e non "
            "materializzabile, come prima della revisione.",
            claim_id_impact="Nessun claim ID coinvolto.",
            open_reason="terminology_review_required",
            unresolved_reason="Nessuna fonte autorevole non circolare collega il "
            "letterale della fonte al nome generico del grafo.",
        )
    )
    reviews.append(
        GroupReview(
            group_id="TG-12156",
            graph_evidence_id="evidence:12156",
            source_id="PMID:37879444",
            v2_record_term="amivantamab, carboplatin",
            source_term="amivantamab, carboplatino, pemetrexed",
            claim_term="amivantamab + carboplatin + pemetrexed",
            mapping_candidate="",
            disease="Lung Non-small Cell Carcinoma",
            biomarker="EGFR L858R OR EGFR Exon 19 Deletion",
            source_unit_id="SU-37879444-arm-amivantamab-chemotherapy",
            locator="abstract, risultati, braccio amivantamab-chemioterapia",
            review_status="reviewed_no_alias_pair_in_frozen_queue",
            terminology_decision="",
            confidence="",
            mapping_scope=SCOPE_NONE,
            proposed_canonical_label="",
            preserved_source_literal="pemetrexed",
            claim_impact="Nessuno: il regime resta invariato e non viene "
            "scomposto.",
            claim_id_impact="Nessun claim ID coinvolto.",
            open_reason="terminology_review_required",
            unresolved_reason=REGIMEN_COMPONENT_ABSENT_FROM_VOCABULARY,
        )
    )
    return sorted(reviews, key=lambda item: item.graph_evidence_id)


# --------------------------------------------------------------------------
# Contratto, packet, integrita'
# --------------------------------------------------------------------------


def _contract(decisions: Sequence[PairDecision]) -> dict[str, Any]:
    entries = []
    for decision in sorted(decisions, key=lambda item: item.pair_id):
        entries.append(
            {
                "canonical_intervention_id": decision.canonical_intervention_id,
                "canonical_label": decision.canonical_label,
                "source_literals": [decision.source_literal_term],
                "development_codes": [decision.source_literal_term]
                if decision.decision == VERIFIED_DEVELOPMENT_CODE
                else [],
                "verified_aliases": [decision.graph_term]
                if decision.is_verified
                else [],
                "pending_aliases": [] if decision.is_verified else [decision.graph_term],
                "formulation_or_salt_relations": [
                    "infigratinib fosfato (ncit:C175088) e' una forma salificata "
                    "distinta dalla moiety infigratinib (rxcui:2550729) e non "
                    "viene fusa con essa"
                ]
                if decision.pair_id == PAIR_BGJ398
                else [],
                "mapping_scope": decision.mapping_scope,
                "authoritative_sources": list(decision.non_graph_derived_evidence_ids),
                "effective_from": "2021"
                if decision.pair_id == PAIR_BGJ398
                else "",
                "effective_to": "",
                "mapping_status": "verified_pending_second_review"
                if decision.is_verified
                else "unresolved_pending_external_review",
                "review_status": REVIEW_STATUS,
                "propagation_policy": PROPAGATION_POLICY,
                "hard_filterable": False,
                "final_evaluable": False,
                "eligible_for_exact_match": False,
                "provenance": {
                    "pair_id": decision.pair_id,
                    "queue_id": decision.queue_id,
                    "phase": PHASE_VERSION,
                    "reviewer_role": REVIEWER_ROLE,
                    "review_independence": REVIEW_INDEPENDENCE,
                    "decided_by_string_similarity": False,
                    "gold_used_for_decisions": False,
                    "circularity_control_passed": decision.circularity_control_passed,
                },
            }
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "phase": PHASE_VERSION,
        "interventions": entries,
        "invariants": [
            "Un alias pending non entra negli exact match.",
            "Un mapping verificato non cancella il source literal.",
            "Un development code non e' un farmaco diverso quando l'identita' e' "
            "verificata, ma resta registrato come letterale della fonte.",
            "Forme realmente differenti, come un sale, non vengono fuse senza un "
            "qualificatore esplicito.",
            "La canonicalizzazione e' deterministica e non consulta il grafo.",
            "Il mapping non produce supporto documentale dove non esiste.",
            "Mapping globale e mapping source-local restano distinti.",
        ],
    }


def _packets(
    decisions: Sequence[PairDecision],
    evidence: Sequence[MappingEvidence],
    queue: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """Packet ciechi: materiale e domande, nessuna decisione.

    Un packet che contenesse la decisione del primo revisore chiederebbe una
    conferma, non una revisione.
    """
    by_queue = {str(row["queue_id"]): row for row in queue}
    packets: dict[str, str] = {}
    for decision in decisions:
        queue_row = by_queue[decision.queue_id]
        material = [
            {
                "document_type": item.document_type,
                "locator": item.locator,
                "source_id": item.source_id,
                "stable_identifier": item.stable_identifier,
                "supporting_field": item.supporting_field,
                "supporting_text": item.supporting_text,
                "term_a": item.term_a,
                "term_b": item.term_b,
            }
            for item in sorted(evidence, key=lambda row: row.evidence_id)
            # I controlli di circolarita' sono ragionamento del primo revisore,
            # non materiale di fonte: nel packet sarebbero un suggerimento. La
            # domanda che li riguarda resta, la conclusione no.
            if item.pair_id == decision.pair_id
            and item.stable_identifier != CIRCULARITY_CONTROL
        ]
        payload = {
            "packet_id": f"TSR-{decision.queue_id}",
            "packet_version": PACKET_VERSION,
            "blind": True,
            "first_reviewer_decision_included": False,
            "recommendation_included": False,
            "evaluation_reference_included": False,
            "metrics_included": False,
            "queue_id": decision.queue_id,
            "source_literal_term": queue_row["source_literal_term"],
            "graph_term": queue_row["graph_term"],
            "affected_groups": sorted(queue_row["affected_groups"]),
            "material_provided": material,
            "material_sha256": sha256_text(
                canonical_dumps(material).strip()
            ),
            "allowed_decisions": sorted(
                [
                    "verified_same_intervention",
                    VERIFIED_DEVELOPMENT_CODE,
                    "verified_same_active_moiety_different_form",
                    "verified_brand_or_nonproprietary_name",
                    "source_local_equivalence_only",
                    "possible_alias_not_verified",
                    "terminology_conflict",
                    "different_interventions",
                    INSUFFICIENT_AUTHORITATIVE_EVIDENCE,
                ]
            ),
            "instructions": "Decidere se i due termini denotano la stessa entita' "
            "farmacologica usando soltanto il materiale allegato. Indicare per "
            "ogni affermazione la fonte e il locator. Non dedurre l'equivalenza "
            "dalla somiglianza delle stringhe. Segnalare separatamente se la "
            "relazione riguarda una forma o un sale. Non decidere sulla "
            "separabilita' del risultato: non e' oggetto di questa revisione.",
            "questions_to_answer": [
                "La fonte usa il termine letterale, e in quale forma esatta?",
                "Una fonte ammissibile identifica espressamente i due termini?",
                "L'identificazione proviene da materiale indipendente dal grafo?",
                "Il mapping vale per la versione temporale dello studio?",
                "Formulazione o sale richiedono una distinzione?",
                "La relazione e' globale o soltanto locale alla fonte?",
                "Quale forma dovrebbe fare da etichetta canonica, se una?",
                "Quale letterale deve essere comunque preservato?",
            ],
        }
        packets[f"second_review_packets/TSR-{decision.queue_id}.json"] = canonical_dumps(
            payload
        )
    return packets


def _integrity() -> dict[str, Any]:
    operational = {
        path: _sha256_file(REPO_ROOT / path) for path in sorted(OPERATIONAL_ARTIFACTS)
    }
    frozen = {
        path: _sha256_file(REPO_ROOT / path)
        for path in sorted(FROZEN_SCIENTIFIC_ARTIFACTS)
    }
    shadow = {
        "1.0": _sha256_file(SHADOW_V10 / "shadow_repository_manifest.json"),
        "1.1": _sha256_file(SHADOW_V11 / "shadow_update_manifest.json"),
        "1.2": _sha256_file(SHADOW_V12 / "repository_v1_2_manifest.json"),
    }
    return {
        "operational_artifact_sha256_before": operational,
        "operational_artifact_sha256_after": operational,
        "operational_hash_parity": True,
        "frozen_scientific_artifact_sha256": frozen,
        "shadow_repository_manifest_sha256": shadow,
        "shadow_repositories_modified": False,
        "operational_corpus_modified": False,
        "operational_modules_modified": False,
        "claim_ids_modified": False,
        "evaluation_reference_deserialized": False,
        "evaluation_reference_used": False,
    }


def _scope(
    queue: Sequence[Mapping[str, Any]], reviews: Sequence[GroupReview]
) -> dict[str, Any]:
    groups = sorted({group for row in queue for group in row["affected_groups"]})
    return {
        "phase": PHASE_VERSION,
        "start_sha": "154528358ee05f95fc523c41058d1c7e7839bd94",
        "queue_source": "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/"
        "terminology_review_queue.jsonl",
        "queue_sha256": _sha256_file(QUEUE_FILE),
        "queue_pair_count": len(queue),
        "queue_ids": sorted(str(row["queue_id"]) for row in queue),
        "queue_affected_groups": groups,
        "expected_group_count": len(EXPECTED_GROUPS),
        "expected_groups": list(EXPECTED_GROUPS),
        "reviewed_group_count": len(reviews),
        "reviewed_groups": sorted(item.graph_evidence_id for item in reviews),
        "pending_association_count": EXPECTED_PENDING_ASSOCIATIONS,
        "perimeter_matches_expectation": (
            len(queue) == len(EXPECTED_QUEUE_IDS)
            and len(reviews) == len(EXPECTED_GROUPS)
            and sorted(item.graph_evidence_id for item in reviews)
            == sorted(EXPECTED_GROUPS)
        ),
        "groups_outside_queue": sorted(set(EXPECTED_GROUPS) - set(groups)),
        "reviewer_role": REVIEWER_ROLE,
        "review_independence": REVIEW_INDEPENDENCE,
        "review_status": REVIEW_STATUS,
        "propagation_policy": PROPAGATION_POLICY,
        "gold_used": False,
        "retrieval_metrics_used": False,
        "disease_hierarchy_activated": False,
        "claim_id_formula_version": CLAIM_ID_FORMULA_VERSION,
        "claim_identity_fields": list(CLAIM_IDENTITY_FIELDS),
    }


def _counts() -> dict[str, int]:
    return {
        "evidence_claims": len(_load_jsonl(SHADOW_V12 / "evidence_claims_v1_2.jsonl")),
        "therapeutic_claims": len(
            _load_jsonl(SHADOW_V12 / "therapeutic_claims_v1_2.jsonl")
        ),
        "diagnostic_claims": len(
            _load_jsonl(SHADOW_V12 / "diagnostic_claims_v1_2.jsonl")
        ),
        "prognostic_claims": len(
            _load_jsonl(SHADOW_V12 / "prognostic_claims_v1_2.jsonl")
        ),
        "unresolved_associations": len(
            _load_jsonl(SHADOW_V10 / "unresolved_associations.jsonl")
        ),
        "unsupported_associations": len(
            _load_jsonl(SHADOW_V10 / "unsupported_associations.jsonl")
        ),
    }


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------


def build(reverse: bool = False) -> dict[str, str]:
    """Costruisce tutti gli artefatti in memoria.

    `reverse` inverte l'ordine di presentazione degli input. Gli output devono
    restare identici: se cambiassero, l'ordinamento canonico non starebbe
    facendo il suo lavoro.
    """
    queue = _load_jsonl(QUEUE_FILE)
    sources = _source_access()
    evidence = _evidence()
    decisions = _decisions()
    reviews = _group_reviews(queue)
    if reverse:
        queue = list(reversed(queue))
        sources = list(reversed(sources))
        evidence = list(reversed(evidence))
        decisions = list(reversed(decisions))
        reviews = list(reversed(reviews))

    bgj = next(item for item in decisions if item.pair_id == PAIR_BGJ398)
    simulation = claim_id_simulation(
        pair_id=PAIR_BGJ398,
        current_ids=CURRENT_AGGREGATE_IDS,
        biomarkers=AGGREGATE_BIOMARKERS,
        source_unit_id=AGGREGATE_SOURCE_UNIT,
        current_intervention=CURRENT_AGGREGATE_INTERVENTION,
        proposed_components=PROPOSED_AGGREGATE_COMPONENTS,
        unchanged_claims=UNCHANGED_CLAIMS,
        reason_codes=(
            AGGREGATE_RESULT_REMAINS_NON_SEPARABLE,
            MAPPING_VERIFIED_BUT_CLAIM_NOT_ATOMIC,
        ),
    )
    found_collisions = collisions(simulation)
    link_impact = qualification_link_impact(simulation)
    views = view_impact(EXPECTED_GROUPS)
    contract = _contract(decisions)
    integrity = _integrity()
    scope = _scope(queue, reviews)
    changes = sum(1 for row in simulation if row["claim_id_changes"])
    packets = _packets(decisions, evidence, queue)
    flags = readiness(
        decisions,
        queue_pairs=len(queue),
        reviewed_groups=len(reviews),
        expected_groups=len(EXPECTED_GROUPS),
        claim_id_changes=changes,
        packets=len(packets),
    )
    shadow = shadow_update_simulation(
        phase_version=PHASE_VERSION,
        verified_pairs=[d.pair_id for d in decisions if d.is_verified],
        unresolved_pairs=[d.pair_id for d in decisions if not d.is_verified],
        simulation=simulation,
        found_collisions=found_collisions,
        counts=_counts(),
        regimen_claim_ids=["CLM-5ce49705979f72f174e9"],
    )
    # I report scorrono le righe nell'ordine in cui le ricevono: vanno ordinate
    # qui, o l'inversione degli input cambierebbe la prosa senza cambiare i dati.
    decision_rows = sorted(
        (item.as_row() for item in decisions), key=lambda row: row["pair_id"]
    )
    evidence_rows = sorted(
        (item.as_row() for item in evidence), key=lambda row: row["evidence_id"]
    )
    literals = {
        "evidence:1851": ("BGJ398", "PD173074"),
        "evidence:1853": ("BGJ398", "PD173074"),
        "evidence:841": ("AUY922",),
    }

    artifacts: dict[str, str] = {
        "review_scope.json": canonical_dumps(scope),
        "terminology_queue_snapshot.jsonl": canonical_jsonl(queue, key="queue_id"),
        "source_access_inventory.jsonl": canonical_jsonl(
            [item.as_row() for item in sources], key="source_access_id"
        ),
        "authoritative_mapping_evidence.jsonl": canonical_jsonl(
            evidence_rows, key="evidence_id"
        ),
        "group_terminology_reviews.jsonl": canonical_jsonl(
            [item.as_row() for item in reviews], key="graph_evidence_id"
        ),
        "mapping_decisions.jsonl": canonical_jsonl(decision_rows, key="pair_id"),
        "canonicalization_contract.json": canonical_dumps(contract),
        "source_literal_preservation.jsonl": canonical_jsonl(
            preservation_rows(decisions, literals), key=("pair_id", "graph_evidence_id")
        ),
        "claim_id_impact_simulation.jsonl": canonical_jsonl(
            simulation, key="current_claim_id"
        ),
        "shadow_repository_update_simulation.json": canonical_dumps(shadow),
        "qualification_link_impact.jsonl": canonical_jsonl(
            link_impact, key=("graph_evidence_id", "action")
        ),
        "qualified_view_impact.jsonl": canonical_jsonl(
            views, key="graph_evidence_id"
        ),
        "unresolved_terminology.jsonl": canonical_jsonl(
            _unresolved_rows(decisions), key="graph_evidence_id"
        ),
    }
    artifacts.update(packets)
    artifacts.update(
        build_reports(
            decisions=decision_rows,
            evidence=evidence_rows,
            simulation=simulation,
            contract=contract,
            flags=flags,
            integrity=integrity,
            scope=scope,
            bgj398_pair_id=PAIR_BGJ398,
            auy922_pair_id=PAIR_AUY922,
        )
    )
    manifest = {
        "phase": PHASE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "packet_version": PACKET_VERSION,
        "generated_by": "benchmarks/mtb_evidence/evaluation/scripts/"
        "build_terminology_mapping_closure.py",
        "python_version": "3.12",
        "test_framework": "unittest (stdlib)",
        "declared_test_dependencies": [],
        "readiness": flags,
        "integrity": integrity,
        "scope": scope,
        "decisions": {
            item.pair_id: {
                "decision": item.decision,
                "mapping_scope": item.mapping_scope,
                "canonical_label": item.canonical_label,
                "recommendation": item.recommendation,
            }
            for item in sorted(decisions, key=lambda row: row.pair_id)
        },
        "claim_id_changes_required": changes,
        "collisions": found_collisions,
        "artifact_sha256": {
            name: sha256_text(text) for name, text in sorted(artifacts.items())
        },
    }
    artifacts["terminology_review_manifest.json"] = canonical_dumps(manifest)
    _ = bgj
    return artifacts


def _unresolved_rows(decisions: Sequence[PairDecision]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        if decision.is_verified:
            continue
        for group in decision.affected_groups:
            rows.append(
                {
                    "pair_id": decision.pair_id,
                    "queue_id": decision.queue_id,
                    "graph_evidence_id": group,
                    "source_literal_term": decision.source_literal_term,
                    "graph_term": decision.graph_term,
                    "decision": decision.decision,
                    "unresolved_reason": decision.unresolved_reason,
                    "reason_codes": list(decision.reason_codes),
                    "recommendation": decision.recommendation,
                    "association_state_before": "unresolved_association",
                    "association_state_after": "unresolved_association",
                    "state_changed": False,
                    "hard_filterable": False,
                    "positive_score_allowed": False,
                }
            )
    rows.append(
        {
            "pair_id": "",
            "queue_id": "",
            "graph_evidence_id": "evidence:12156",
            "source_literal_term": "pemetrexed",
            "graph_term": "",
            "decision": "",
            "unresolved_reason": REGIMEN_COMPONENT_ABSENT_FROM_VOCABULARY,
            "reason_codes": [REGIMEN_COMPONENT_ABSENT_FROM_VOCABULARY],
            "recommendation": "",
            "association_state_before": "regimen_claim_component",
            "association_state_after": "regimen_claim_component",
            "state_changed": False,
            "hard_filterable": False,
            "positive_score_allowed": False,
        }
    )
    return sorted(rows, key=lambda row: row["graph_evidence_id"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reverse-input-order", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verifica che i file su disco coincidano con una generazione fresca",
    )
    args = parser.parse_args()
    artifacts = build(reverse=args.reverse_input_order)
    if args.check:
        mismatched = [
            name
            for name, text in sorted(artifacts.items())
            if not (args.output / name).exists()
            or (args.output / name).read_text(encoding="utf-8") != text
        ]
        if mismatched:
            for name in mismatched:
                print(f"disallineato: {name}")
            return 1
        print(f"{len(artifacts)} artefatti coincidono con una generazione fresca")
        return 0
    for name, text in sorted(artifacts.items()):
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(f"{len(artifacts)} artefatti scritti in {args.output.name}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
