"""Confronto forense: vecchio percorso LIVE contro nuovo runtime canonico.

La domanda a cui questo script risponde è una sola, e non è «funziona ancora».
È: **il routing è cambiato e il risultato no?** Rimuovere un'alternativa di
instradamento non deve spostare di un identificatore ciò che la pipeline
produce, e l'unico modo di affermarlo è eseguire gli stessi ingressi sui due
commit e confrontare gli artefatti.

    python scripts/compare_canonical_vs_legacy_live.py --out FILE.json
    # eseguito una volta per worktree, poi:
    python scripts/compare_canonical_vs_legacy_live.py --diff VECCHIO.json NUOVO.json

**Auto-contenuto di proposito.** Deve girare identico su un checkout di
``f52bbf5``, dove ``run_case`` ha ancora ``execution_mode`` e nessun
``research_frozen_artifacts``: non importa nulla dai test né da moduli
introdotti dal refactor, e si adatta alla firma che trova. Un comparatore che
esistesse solo sul nuovo albero non potrebbe confrontare niente.

**Nessuna rete.** Il trasporto HTTP è sostituito da payload fissi; tutto il
resto — scrittura dello snapshot, manifest, riletura dal disco, parsing,
selettore, gate, dossier — è codice di produzione. Cinque fixture:

    cache_hit · cache_miss_api · pmid_to_pmcid · degraded_to_abstract · selector

Ciò che viene confrontato: candidate id, document id, SourceUnit id, unità
selezionate dal selettore, hash del ranking, K, id mostrati al modello, esito
dei gate e degli status, hash del dossier canonico.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.pipeline.agentic.ledger import EventLedger  # noqa: E402
from backend.research_pipeline import orchestrator  # noqa: E402
from backend.research_pipeline.documents.authorized_cache import (  # noqa: E402
    AuthorizedDocumentCache,
)
from backend.research_pipeline.documents.live_resolution import DocumentRuntime  # noqa: E402
from backend.research_pipeline.pipeline import CallBudget  # noqa: E402

PMID = "24658966"
PMCID = "PMC3999999"

ESUMMARY = json.dumps({"result": {PMID: {
    "title": "ABL1 V299L and dasatinib in chronic myeloid leukemia",
    "authors": [], "fulljournalname": "Journal of Test Oncology",
    "pubdate": "2014", "lang": ["eng"], "pubtype": ["Journal Article"],
}}}).encode("utf-8")

EFETCH = f"""<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle>
  <MedlineCitation><Article>
    <ArticleTitle>ABL1 V299L and dasatinib in chronic myeloid leukemia</ArticleTitle>
    <Abstract>
      <AbstractText>Patients carrying the ABL1 V299L mutation and treated with
      dasatinib showed a reduced response in chronic myeloid leukemia.</AbstractText>
      <AbstractText>The resistance pattern was observed consistently across the
      dasatinib cohort described in this chronic myeloid leukemia study.</AbstractText>
    </Abstract>
  </Article></MedlineCitation>
  <PubmedData><ArticleIdList>
    <ArticleId IdType="pubmed">{PMID}</ArticleId>
    <ArticleId IdType="pmc">{PMCID}</ArticleId>
  </ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>
""".encode("utf-8")

PMC_XML = b"""<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><GetRecord><record><metadata>
  <article xmlns="http://jats.nlm.nih.gov">
    <front><article-meta><title-group>
      <article-title>ABL1 V299L and dasatinib in chronic myeloid leukemia</article-title>
    </title-group></article-meta></front>
    <body><sec>
      <title>Results</title>
      <p>ABL1 V299L confers reduced sensitivity to dasatinib in chronic myeloid leukemia.</p>
      <p>The full text describes the dasatinib cohort and the observed ABL1 V299L pattern.</p>
      <p>A third paragraph reports the chronic myeloid leukemia outcomes in detail.</p>
      <p>A fourth paragraph discusses dasatinib exposure across the study population.</p>
      <p>A fifth paragraph summarises the ABL1 V299L resistance findings.</p>
      <p>A sixth paragraph lists the limitations of the chronic myeloid leukemia analysis.</p>
    </sec></body>
  </article>
</metadata></record></GetRecord></OAI-PMH>
"""

PMC_CLOSED = b"""<?xml version="1.0"?>
<OAI-PMH><error code="idDoesNotExist">record not open access</error></OAI-PMH>
"""

CLINICAL_TEXT = (
    "Paziente con chronic myeloid leukemia e mutazione ABL1 V299L. "
    "Si vuole valutare dasatinib."
)


def _span(quote: str) -> list[dict[str, Any]]:
    start = CLINICAL_TEXT.index(quote)
    return [{"quote": quote, "start_offset": start, "end_offset": start + len(quote)}]


def _case_context() -> dict[str, Any]:
    return {
        "query_intent": "THERAPY_EVALUATION",
        "disease": {"raw_value": "chronic myeloid leukemia",
                    "normalized_value": "Chronic Myeloid Leukemia",
                    "source_spans": _span("chronic myeloid leukemia")},
        "biomarkers": [{"gene": "ABL1", "normalized_value": "ABL1 V299L",
                        "raw_value": "ABL1 V299L", "source_spans": _span("ABL1 V299L")}],
        "target_intervention": {"raw_value": "dasatinib", "normalized_value": "dasatinib",
                                "source_spans": _span("dasatinib")},
    }


def _candidate() -> dict[str, Any]:
    return {
        "candidate_id": "GCA-forensic",
        "candidate_version": "2.0",
        "disease": [{"label": "Chronic Myeloid Leukemia"}],
        "biomarkers": [{"label": "ABL1", "type": "Gene"}, {"label": "V299L", "type": "Variant"}],
        "interventions": [{"label": "dasatinib"}],
        "document_identifiers": [{"pmid": PMID}],
        "predicate": "has_evidence_statement",
        "direction": "Supports",
    }


def _association() -> dict[str, Any]:
    candidate = _candidate()
    return {
        "candidate_id": candidate["candidate_id"],
        "candidate": candidate,
        "available_bundles": [{
            "bundle_id": f"live:{candidate['candidate_id']}:pmid:{PMID}",
            "document_id": f"pmid:{PMID}",
            "provenance_identifier": {"pmid": PMID},
            "source_unit_ids": ["FROZEN-MUST-NOT-BE-READ"],
        }],
    }


def _responder(pmc: bytes | None):
    def request(url: str):
        if "esummary.fcgi" in url:
            return ESUMMARY, {"status": 200, "url": url}
        if "efetch.fcgi" in url:
            return EFETCH, {"status": 200, "url": url}
        if "pmc/oai" in url:
            return (pmc, {"status": 200, "url": url}) if pmc else (None, {"status": 404, "url": url})
        return None, {"status": 404, "url": url}

    return request


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


# --- Adattamento alla firma del runtime che si trova ------------------------

_PARAMS = inspect.signature(orchestrator.run_case).parameters
_LEGACY_SIGNATURE = "execution_mode" in _PARAMS


def _runtime_flavour() -> str:
    return "LEGACY_LIVE" if _LEGACY_SIGNATURE else "CANONICAL"


def _run(cache: AuthorizedDocumentCache, ledger_path: Path) -> tuple[Any, list[list[str]]]:
    """Esegue la pipeline sul runtime presente, qualunque sia la sua firma."""
    shown_to_model: list[list[str]] = []

    def parser(budget, case_id, text):
        return {"transport_result": "FORCED_TOOL_VALID", "case_context_raw": _case_context(),
                "model": "FORENSIC_PARSER", "prompt_version": "forensic/1.0"}

    def enricher(budget, case_id, candidate_id, paper_id, case_context,
                 candidate, requested_drug, paper_units, *args, **kwargs):
        shown_to_model.append([unit.get("source_unit_id") for unit in paper_units])
        return {"transport_result": "V2_TRANSPORT_VALID", "enrichment": None,
                "model": "FORENSIC_ENRICHER", "prompt_version": "forensic/1.0"}

    runtime = DocumentRuntime(
        cache=cache, manifest_by_document_id={},
        descriptor={"document_cache_available": True,
                    "retrieval_mode": "CACHE_FIRST_API_ON_MISS", "manifest_hash": "forensic"},
        network_enabled=True,
    )

    kwargs: dict[str, Any] = {
        "case_id": "CASE-forensic", "clinical_text": CLINICAL_TEXT,
        "call_parser_fn": parser, "call_enricher_fn": enricher,
        "source_units_by_id": {}, "budget": CallBudget(5),
        "ledger": EventLedger(ledger_path), "document_runtime": runtime,
        "validate_fn": lambda *a, **k: {"outcome": "ENRICHMENT_V2_ABSTAINED"},
        "call_narrator_fn": lambda *a, **k: {"transport_result": "NO_NARRATIVE",
                                             "narrative": None},
    }
    if _LEGACY_SIGNATURE:
        # Il vecchio runtime pretende la modalità e, in LIVE, chiama il retrieval
        # con ``document_mode``. Il nuovo non ha né l'una né l'altro.
        kwargs["execution_mode"] = "LIVE"

    def retrieve(case_context, **_ignored):
        return {"associations": [_association()], "excluded_candidates": [], "no_match": False}

    with mock.patch.object(orchestrator.retrieval_mod, "retrieve", retrieve):
        run = orchestrator.run_case(**kwargs)
    return run, shown_to_model


def _observe(run: Any, shown_to_model: list[list[str]]) -> dict[str, Any]:
    """Gli artefatti che devono restare identici fra i due percorsi."""
    stages = {stage.stage_id: stage for stage in run.stages}

    def preview(stage_id: str) -> dict[str, Any]:
        stage = stages.get(stage_id)
        return dict(stage.output_preview or {}) if stage is not None else {}

    retrieval = preview("stage_5_kg_retrieval")
    documents = preview("stage_6_document_resolution").get("documents", [])
    units = preview("stage_7_source_units").get("source_units", [])
    selections = preview("stage_8_paper_selection").get("selections", [])
    gates = preview("stage_11_deterministic_gates").get("checks_by_candidate", [])
    statuses = preview("stage_12_status").get("statuses", [])
    dossier = preview("stage_13_dossier").get("dossier")

    selected_ids: list[str] = []
    ranking: list[Any] = []
    for selection in selections:
        for paper in selection.get("selected_papers", []):
            selected_ids.extend(paper.get("resolved_source_unit_ids", []))
            selector = paper.get("selector") or {}
            ranking.append(selector.get("ranking"))

    return {
        "status": run.status,
        "stopped_at": run.stopped_at,
        "candidate_ids": sorted(a["candidate_id"] for a in retrieval.get("associations", [])),
        "document_ids": sorted(d.get("document_id") for d in documents),
        "document_availability": sorted(
            f"{d.get('document_id')}={d.get('availability')}" for d in documents),
        "degradation": sorted(
            code for d in documents for code in (d.get("reason_codes") or [])
            if code.startswith("PMC_")),
        "derived_pmcid": sorted({
            str((d.get("lineage") or {}).get("derived_pmcid"))
            for d in documents if (d.get("lineage") or {}).get("derived_pmcid")}),
        "source_unit_ids": sorted(u.get("source_unit_id") for u in units),
        "selector_selected_ids": sorted(selected_ids),
        "selector_k": len(selected_ids),
        "ranking_hash": _digest(ranking),
        "model_input_source_unit_ids": sorted(
            uid for call in shown_to_model for uid in call),
        "gate_support_masks": _digest([g.get("support_mask") for g in gates]),
        "status_assignments": _digest(
            [{"candidate_id": s.get("candidate_id"), "status": s.get("status"),
              "gate_bucket": s.get("gate_bucket")} for s in statuses]),
        "dossier_hash": _digest(dossier),
    }


FIXTURES: dict[str, dict[str, Any]] = {
    # Ogni fixture dichiara cosa mette alla prova, così un diff che scatta dice
    # anche quale proprietà ha smesso di valere.
    "cache_miss_api": {"pmc": PMC_XML, "warm": False,
                       "asserts": "acquisizione autorizzata sul miss"},
    "cache_hit": {"pmc": PMC_XML, "warm": True,
                  "asserts": "seconda run sullo stesso documento, senza rete"},
    "pmid_to_pmcid": {"pmc": PMC_XML, "warm": False,
                      "asserts": "risoluzione PMID→PMCID e preferenza per il full text"},
    "degraded_to_abstract": {"pmc": PMC_CLOSED, "warm": False,
                             "asserts": "degradazione dichiarata ad abstract"},
    "selector": {"pmc": PMC_XML, "warm": False,
                 "asserts": "unità selezionate, ranking e K"},
}


def observe_all() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, fixture in FIXTURES.items():
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = AuthorizedDocumentCache(root=root / "cache", network=True, delay_seconds=0)
            cache._request = _responder(fixture["pmc"])  # type: ignore[method-assign]
            if fixture["warm"]:
                # Prima esecuzione solo per popolare la cache: ciò che si osserva
                # è la seconda, che deve trovare tutto già lì.
                _run(cache, root / "warm.sqlite3")
            run, shown = _run(cache, root / "ledger.sqlite3")
            observation = _observe(run, shown)
            observation["asserts"] = fixture["asserts"]
            results[name] = observation
    return {"runtime_flavour": _runtime_flavour(),
            "run_case_parameters": sorted(_PARAMS),
            "fixtures": results}


# --- Diff --------------------------------------------------------------------

#: Campi il cui **cambiamento è l'oggetto stesso** di questa fase. Restano fuori
#: dal confronto semantico: confrontarli direbbe soltanto che il refactor è
#: avvenuto, cosa che già sappiamo.
_ROUTING_FIELDS = frozenset({"runtime_flavour", "run_case_parameters"})


def diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    names = sorted(set(old["fixtures"]) | set(new["fixtures"]))
    for name in names:
        before, after = old["fixtures"].get(name, {}), new["fixtures"].get(name, {})
        for key in sorted(set(before) | set(after)):
            if before.get(key) != after.get(key):
                differences.append({"fixture": name, "field": key,
                                    "old": before.get(key), "new": after.get(key)})
    return {
        "routing_changed": old.get("runtime_flavour") != new.get("runtime_flavour"),
        "old_runtime": old.get("runtime_flavour"),
        "new_runtime": new.get("runtime_flavour"),
        "removed_parameters": sorted(
            set(old.get("run_case_parameters", [])) - set(new.get("run_case_parameters", []))),
        "added_parameters": sorted(
            set(new.get("run_case_parameters", [])) - set(old.get("run_case_parameters", []))),
        "semantic_result_unchanged": not differences,
        "differences": differences,
        "fixtures_compared": names,
        "excluded_from_semantic_comparison": sorted(_ROUTING_FIELDS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="dove scrivere l'osservazione di questo runtime")
    parser.add_argument("--diff", nargs=2, type=Path, metavar=("VECCHIO", "NUOVO"),
                        help="confronta due osservazioni già prodotte")
    args = parser.parse_args()

    if args.diff:
        old = json.loads(args.diff[0].read_text(encoding="utf-8"))
        new = json.loads(args.diff[1].read_text(encoding="utf-8"))
        report = diff(old, new)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["semantic_result_unchanged"] else 1

    observation = observe_all()
    payload = json.dumps(observation, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"scritto {args.out} ({observation['runtime_flavour']})")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
