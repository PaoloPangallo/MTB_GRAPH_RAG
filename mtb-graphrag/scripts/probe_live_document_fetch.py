"""Sonda: il document grounding può partire dalla sola provenance della candidate?

**Domanda.** Una GraphCandidateAssertion recuperata dal grafo contiene abbastanza
provenance perché il sistema arrivi da solo al documento originale, via API
ufficiale, e consegni a Gemma testo verificabile — senza che un clinico conosca,
digiti o scarichi PMID, PMCID o NCT?

**Perché non è ovvio.** La GCA porta soltanto PMID. Nessun PMCID compare nella
sua provenance, eppure sette bundle congelati citano documenti `pmcid:`. Se il
PMCID fosse una conoscenza esterna — una tabella di mapping, un inserimento
manuale — l'automazione sarebbe impossibile. La sonda verifica l'ipotesi
alternativa: che sia PubMed stessa a dichiararlo, e che la catena
PMID → PubMed → PMCID → PMC sia percorribile per intero dalla macchina.

**Disciplina della prova.** L'identificatore viene derivato *solo* da
``candidate["document_identifiers"]``. Il ``document_id`` dei bundle congelati
non viene mai usato come input: sarebbe la risposta già scritta nel foglio. I
documenti vengono riscaricati in directory temporanee, mai dalla cache reale,
che non viene né letta come sorgente né modificata.

**Cosa questa sonda non dimostra.** Nulla di clinico. Non accuratezza, non
completezza della letteratura, non production readiness. Solo fattibilità
tecnica del percorso.

Nessuna integrazione nel runtime: `resolve_document_probe()` esiste qui e resta
qui.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.research_pipeline import data_access as da  # noqa: E402
from backend.research_pipeline.documents import cache_runtime  # noqa: E402
from backend.research_pipeline.documents.authorized_cache import (  # noqa: E402
    AuthorizedDocumentCache,
    expand_identifier,
    file_hash,
)
from backend.research_pipeline.retrieval.kg_retrieval import (  # noqa: E402
    MAX_SOURCE_UNITS_PER_DOCUMENT,
)

PROBE_VERSION = "live-document-fetch-probe/1.0"
DEFAULT_REPORT_DIR = _REPO_ROOT / "evaluation" / "live_document_fetch_probe"

CACHE_HIT = "CACHE_HIT"
CACHE_MISS = "CACHE_MISS"


# --- Provenance -------------------------------------------------------------


def candidate_pmids(candidate: Mapping[str, Any]) -> list[str]:
    """PMID dichiarati dalla candidate, espansi.

    Un campo ``pmid`` può contenere più identificatori separati da ``;``:
    ``expand_identifier`` li separa in modo deterministico. Nessuna euristica,
    nessuna ricerca: si legge ciò che la GCA porta con sé.
    """
    found: list[str] = []
    for item in candidate.get("document_identifiers") or []:
        for expanded in expand_identifier(item):
            value = str(expanded.get("pmid") or "").strip()
            if value and value not in found:
                found.append(value)
    return found


def derive_pmcid_from_pubmed(record: Mapping[str, Any]) -> str | None:
    """PMCID come dichiarato da PubMed nella risposta appena scaricata.

    È il passaggio che decide la fattibilità: se il PMCID arriva da qui, la
    catena non ha bisogno di conoscenza esterna.
    """
    value = (record.get("identifiers") or {}).get("pmcid")
    return str(value).upper() if value else None


# --- Fetch ------------------------------------------------------------------


def _endpoints(record: Mapping[str, Any]) -> list[str]:
    return [str(a.get("url")) for a in record.get("resolution_attempts") or [] if a.get("url")]


def fetch_document(root: Path, kind: str, value: str, *, delay_seconds: float) -> dict[str, Any]:
    """Scarica un documento dalla fonte ufficiale in una root temporanea."""
    cache = AuthorizedDocumentCache(root=root, network=True, delay_seconds=delay_seconds)
    resolver = {"pmid": cache.resolve_pmid, "pmcid": cache.resolve_pmc,
                "nct": cache.resolve_nct}[kind]
    started = time.monotonic()
    record = resolver(value)
    relative = record.get("local_cache_path")
    path = (root / relative) if relative else None
    return {
        "requested_kind": kind,
        "requested_value": value,
        "document_id": record.get("document_id"),
        "identifiers": record.get("identifiers"),
        "availability": record.get("availability"),
        "official_source": record.get("source"),
        "endpoints": _endpoints(record),
        "retrieved_at": record.get("retrieved_at"),
        "content_type": record.get("content_type"),
        "local_cache_path": relative,
        "raw_payload_hash": file_hash(path) if path and path.is_file() else None,
        "payload_size_bytes": path.stat().st_size if path and path.is_file() else 0,
        "fetch_success": bool(path and path.is_file()),
        "duration_seconds": round(time.monotonic() - started, 3),
        "_record": record,
    }


def parse_units(root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """Ri-parsa le SourceUnit dal payload appena scaricato."""
    cache = cache_runtime.ReadOnlyDocumentCache(root)
    try:
        units = cache.source_units_for_record(dict(record))
    except Exception as exc:  # noqa: BLE001 — un parse fallito è un dato
        return {"parser_success": False, "error": f"{type(exc).__name__}: {exc}",
                "units": [], "source_unit_count": 0, "source_units_with_text": 0}
    with_text = [u for u in units if (u.get("text") or "").strip()]
    parsers = sorted({f"{u.get('parser')}@{u.get('parser_version')}" for u in units})
    return {
        "parser_success": True,
        "parsers": parsers,
        "units": units,
        "source_unit_count": len(units),
        "source_units_with_text": len(with_text),
        "unit_types": sorted({str(u.get("unit_type")) for u in units}),
    }


# --- Cache-miss simulato (§9) ----------------------------------------------


def resolve_document_probe(document_id: str, scratch: Path, *,
                           delay_seconds: float, cache_root: Path | None = None) -> dict[str, Any]:
    """Cache-first, API-on-miss — **solo** come esperimento, fuori dal runtime.

    Il runtime canonico non fa questo: su cache miss lascia
    ``DOCUMENT_UNAVAILABLE`` e non scarica nulla. Questa funzione serve a
    misurare se il percorso alternativo sarebbe tecnicamente percorribile, non a
    proporlo come comportamento.

    ``cache_root`` permette di puntare la ricerca a una radice vuota, così da
    osservare il ramo miss su un documento che *è* recuperabile: interrogare la
    cache reale darebbe sempre hit, e il ramo resterebbe non esercitato.
    """
    manifest = {row["document_id"]: row for row in da.read_jsonl(da.document_manifest_path())}
    row = manifest.get(document_id)
    root = cache_root or cache_runtime.cache_path()
    relative = (row or {}).get("local_cache_path")

    if row and relative and (root / relative).is_file():
        return {"document_id": document_id, "path": CACHE_HIT,
                "snapshot_created": False, "fetch_performed": False,
                "payload_size_bytes": (root / relative).stat().st_size}

    kind, _, value = document_id.partition(":")
    fetched = fetch_document(scratch, kind, value, delay_seconds=delay_seconds)
    parsed = parse_units(scratch, fetched["_record"])
    return {
        "document_id": document_id,
        "path": CACHE_MISS,
        "fetch_performed": True,
        "fetch_success": fetched["fetch_success"],
        "snapshot_created": fetched["fetch_success"],
        "payload_size_bytes": fetched["payload_size_bytes"],
        "raw_payload_hash": fetched["raw_payload_hash"],
        "parser_success": parsed["parser_success"],
        "source_unit_count": parsed["source_unit_count"],
        "source_units_with_text": parsed["source_units_with_text"],
    }


# --- Gemma ------------------------------------------------------------------


def ask_gemma(candidate: Mapping[str, Any], paper_id: str,
              units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Enricher v2 e validatore deterministico, quelli reali della pipeline.

    Le unità sono quelle appena scaricate, non quelle della cache: è il punto
    dell'esperimento. Il contratto resta QUOTE oppure ABSTAIN — al modello non
    viene chiesta alcuna raccomandazione.
    """
    from backend.research_pipeline import live_providers
    from backend.research_pipeline.pipeline import CallBudget

    disease = candidate.get("disease") or []
    biomarkers = candidate.get("biomarkers") or []
    interventions = [i.get("label") for i in candidate.get("interventions") or [] if i.get("label")]
    drug = interventions[0] if interventions else ""

    case_context = {
        "query_intent": "THERAPY_EVALUATION",
        "disease": {"normalized_value": (disease[0] or {}).get("label") if disease else None},
        "biomarkers": [{"normalized_value": b.get("label")} for b in biomarkers],
        "target_intervention": {"normalized_value": drug},
    }
    summary = {"candidate_id": candidate.get("candidate_id"),
               "disease": disease, "biomarkers": biomarkers}
    selected = list(units)[:MAX_SOURCE_UNITS_PER_DOCUMENT]

    budget = CallBudget(8)
    try:
        call = live_providers.enricher_fn(
            budget, "PROBE", str(candidate.get("candidate_id")), paper_id,
            case_context, summary, drug, [dict(u) for u in selected],
        )
    except Exception as exc:  # noqa: BLE001
        return {"gemma_reached": False, "error": f"{type(exc).__name__}: {exc}"}

    enrichment = call.get("enrichment") or {}
    units_by_id = {u["source_unit_id"]: dict(u) for u in selected}
    validation = live_providers.validate_fn(
        call.get("transport_result"), enrichment,
        candidate=dict(candidate),
        paper_bundle={"bundle_id": paper_id,
                      "resolved_source_unit_ids": list(units_by_id)},
        source_units_by_id=units_by_id, requested_drug=drug,
    )
    quote = str(enrichment.get("author_claim_quote") or "")
    return {
        "gemma_reached": True,
        "model": call.get("model"),
        "endpoint": call.get("endpoint"),
        "transport_result": call.get("transport_result"),
        "finish_reason": call.get("finish_reason"),
        "status_code": call.get("status_code"),
        "input_tokens": call.get("input_tokens"),
        "output_tokens": call.get("output_tokens"),
        "source_units_offered": len(selected),
        "decision": enrichment.get("decision"),
        "source_unit_id": enrichment.get("source_unit_id"),
        "abstention_reason": enrichment.get("abstention_reason"),
        # §10/§24: lunghezza e posizione, mai il testo della quote.
        "author_claim_quote_length": len(quote),
        "quote_belongs_to_offered_units": enrichment.get("source_unit_id") in units_by_id,
        "validator": validation.get("validator"),
        "validator_outcome": validation.get("outcome"),
        "validator_reason_codes": validation.get("reason_codes"),
        "quote_offset": validation.get("quote_offset"),
        "quote_validated": str(validation.get("outcome") or "").startswith("ENRICHMENT_V2_ACCEPTED"),
        "replayed": call.get("replayed"),
    }


# --- Selezione dei casi -----------------------------------------------------


def select_candidates() -> dict[str, Any]:
    """Sceglie tre candidate reali con criteri, non a mano.

    A — la provenance porta un PMID il cui articolo non ha PMC: percorso abstract.
    B — la provenance porta **solo** un PMID, ma l'articolo ha un PMC: è il caso
        che obbliga la catena a derivare il PMCID invece di riceverlo.
    C — la provenance porta un PMID il cui PMC risulta non ottenibile: il caso in
        cui il sistema deve degradare senza inventare nulla.
    """
    manifest = {row["document_id"]: row for row in da.read_jsonl(da.document_manifest_path())}
    bundles = da.read_jsonl(da.evidence_bundles_path())
    wanted_ids = {b["candidate_id"] for b in bundles}
    candidates = {row["candidate_id"]: row for row in da.iter_jsonl(da.candidates_path())
                  if row["candidate_id"] in wanted_ids}

    def pmcid_of(pmid: str) -> str | None:
        row = manifest.get(f"pmid:{pmid}")
        return (row.get("identifiers") or {}).get("pmcid") if row else None

    def availability_of(document_id: str) -> str | None:
        row = manifest.get(document_id)
        return row.get("availability") if row else None

    picks: dict[str, dict[str, Any]] = {}
    for bundle in sorted(bundles, key=lambda b: b["bundle_id"]):
        candidate = candidates.get(bundle["candidate_id"])
        if candidate is None:
            continue
        pmids = candidate_pmids(candidate)
        if not pmids:
            continue
        for pmid in pmids:
            if availability_of(f"pmid:{pmid}") != "ABSTRACT_AVAILABLE":
                continue
            pmcid = pmcid_of(pmid)
            pmc_availability = availability_of(f"pmcid:{pmcid}") if pmcid else None
            slot = ("A" if pmcid is None
                    else "B" if pmc_availability == "PMC_XML_AVAILABLE"
                    else "C" if pmc_availability == "PMC_RESOLUTION_FAILED"
                    else None)
            if slot and slot not in picks:
                picks[slot] = {
                    "slot": slot,
                    "candidate_id": candidate["candidate_id"],
                    "bundle_id": bundle["bundle_id"],
                    "bundle_type": bundle.get("bundle_type"),
                    "bundle_document_id_NOT_USED_AS_INPUT": bundle["document_id"],
                    "provenance_pmids": pmids,
                    "selected_pmid": pmid,
                    "pmcid_expected_from_baseline": pmcid,
                    "pmc_availability_baseline": pmc_availability,
                    "disease": candidate.get("disease"),
                    "biomarkers": candidate.get("biomarkers"),
                    "interventions": candidate.get("interventions"),
                    "predicate": candidate.get("predicate"),
                    "direction": candidate.get("direction"),
                    "document_identifiers": candidate.get("document_identifiers"),
                    "_candidate": candidate,
                }
    return picks


# --- Confronto cache / fetch ------------------------------------------------


def compare_units(cache_units: Iterable[Mapping[str, Any]],
                  fetch_units: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    cached = {u["source_unit_id"]: u for u in cache_units}
    fetched = {u["source_unit_id"]: u for u in fetch_units}
    common = set(cached) & set(fetched)
    drift = [uid for uid in common
             if (cached[uid].get("text") or "") != (fetched[uid].get("text") or "")]
    return {
        "source_unit_count_cache": len(cached),
        "source_unit_count_fetch": len(fetched),
        "id_intersection": len(common),
        "id_missing_from_fetch": len(set(cached) - set(fetched)),
        "id_new_in_fetch": len(set(fetched) - set(cached)),
        "text_drift_on_common_ids": len(drift),
    }


def cache_units_for(document_id: str) -> list[dict[str, Any]]:
    manifest = {row["document_id"]: row for row in da.read_jsonl(da.document_manifest_path())}
    row = manifest.get(document_id)
    if row is None or not row.get("local_cache_path"):
        return []
    cache = cache_runtime.open_read_only()
    if not (cache.root / row["local_cache_path"]).is_file():
        return []
    return cache.source_units_for_record(dict(row))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _strip(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Rimuove i campi interni e ogni testo prima della serializzazione."""
    return {k: v for k, v in payload.items() if not k.startswith("_") and k != "units"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sonda di fattibilità del fetch documentale live.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--delay-seconds", type=float, default=0.34)
    parser.add_argument("--skip-gemma", action="store_true",
                        help="Esegue fetch e parsing senza chiamare il modello.")
    args = parser.parse_args(argv)

    picks = select_candidates()
    missing = [s for s in ("A", "B", "C") if s not in picks]
    write_json(args.report_dir / "selected_candidates.json", {
        "probe_version": PROBE_VERSION,
        "selection_is_automatic": True,
        "bundle_document_id_used_as_input": False,
        "slots_found": sorted(picks),
        "slots_missing": missing,
        "candidates": {s: _strip(p) for s, p in sorted(picks.items())},
    })
    print(f"casi selezionati: {sorted(picks)}  mancanti: {missing}")

    bundle_units_by_id = {b["bundle_id"]: list(b.get("source_unit_ids") or [])
                          for b in da.read_jsonl(da.evidence_bundles_path())}
    provenance: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    comparisons: dict[str, Any] = {}
    gemma: dict[str, Any] = {}

    for slot in sorted(picks):
        pick = picks[slot]
        pmid = pick["selected_pmid"]
        scratch = Path(tempfile.mkdtemp(prefix=f"mtb-probe-{slot}-"))
        try:
            # Passo 1 — dalla sola provenance della candidate a PubMed.
            pubmed = fetch_document(scratch, "pmid", pmid, delay_seconds=args.delay_seconds)
            pubmed_units = parse_units(scratch, pubmed["_record"])
            derived_pmcid = derive_pmcid_from_pubmed(pubmed["_record"])
            provenance.append({**_strip(pubmed), "slot": slot,
                               "derived_pmcid_from_pubmed": derived_pmcid,
                               "parser_success": pubmed_units["parser_success"],
                               "source_unit_count": pubmed_units["source_unit_count"]})

            entry: dict[str, Any] = {
                "slot": slot,
                "candidate_id": pick["candidate_id"],
                "provenance_pmids": pick["provenance_pmids"],
                "selected_pmid": pmid,
                "human_identifier_input_required": False,
                "pubmed": {**_strip(pubmed), **{k: v for k, v in pubmed_units.items() if k != "units"}},
                "derived_pmcid_from_pubmed": derived_pmcid,
                "pmcid_matches_baseline": (derived_pmcid == pick["pmcid_expected_from_baseline"]),
            }

            active_units = pubmed_units["units"]
            active_document_id = pubmed["document_id"]

            # Passo 2 — se PubMed dichiara un PMC, si prova il full text.
            if derived_pmcid:
                pmc = fetch_document(scratch, "pmcid", derived_pmcid, delay_seconds=args.delay_seconds)
                pmc_units = parse_units(scratch, pmc["_record"]) if pmc["fetch_success"] else {
                    "parser_success": False, "units": [], "source_unit_count": 0,
                    "source_units_with_text": 0}
                provenance.append({**_strip(pmc), "slot": slot,
                                   "parser_success": pmc_units["parser_success"],
                                   "source_unit_count": pmc_units["source_unit_count"]})
                entry["pmc"] = {**_strip(pmc),
                                **{k: v for k, v in pmc_units.items() if k != "units"}}
                if pmc["fetch_success"] and pmc_units["source_units_with_text"]:
                    active_units = pmc_units["units"]
                    active_document_id = pmc["document_id"]
                    entry["degraded_to_abstract"] = False
                else:
                    # PMC nega il full text: si resta sull'abstract già ottenuto.
                    # Nessun documento alternativo viene cercato.
                    entry["degraded_to_abstract"] = True
                    entry["degradation_reason"] = pmc["availability"]

            entry["document_used_for_gemma"] = active_document_id
            entry["source_units_available_for_gemma"] = len(
                [u for u in active_units if (u.get("text") or "").strip()])

            # Passo 3 — confronto con la cache, senza toccarla.
            comparisons[slot] = {
                "document_id": active_document_id,
                **compare_units(cache_units_for(active_document_id), active_units),
            }

            # Passo 4 — Gemma sulle unità appena scaricate.
            #
            # Due selezioni, perché misurano cose diverse. "naive" prende le
            # prime unità del documento: è ciò che potrebbe fare un'architettura
            # cache-miss, che di bundle non ne ha. "curated" usa le unità che il
            # bundle congelato indica, prelevate però dal documento appena
            # scaricato. Se la prima astiene e la seconda cita, il limite non è
            # nel recupero del documento ma nella scelta del passaggio.
            if not args.skip_gemma and active_units:
                by_id = {u["source_unit_id"]: u for u in active_units}
                naive = list(active_units)[:MAX_SOURCE_UNITS_PER_DOCUMENT]
                gemma[slot] = {
                    "document_id": active_document_id,
                    "naive_selection": {
                        "strategy": "primi N del documento, nessun bundle",
                        "offered_unit_ids": [u["source_unit_id"] for u in naive],
                        **ask_gemma(pick["_candidate"], pick["bundle_id"], naive),
                    },
                }
                curated_ids = [uid for uid in (bundle_units_by_id.get(pick["bundle_id"]) or [])
                               if uid in by_id]
                if curated_ids and set(curated_ids) != {u["source_unit_id"] for u in naive}:
                    curated = [by_id[uid] for uid in curated_ids]
                    gemma[slot]["curated_selection"] = {
                        "strategy": "unita indicate dal bundle congelato, prese dal documento scaricato",
                        "offered_unit_ids": curated_ids,
                        "bundle_units_present_in_fetch": len(curated_ids),
                        "bundle_units_declared": len(bundle_units_by_id.get(pick["bundle_id"]) or []),
                        **ask_gemma(pick["_candidate"], pick["bundle_id"], curated),
                    }
            results[slot] = entry
            naive_decision = (gemma.get(slot, {}).get("naive_selection") or {}).get("decision", "skipped")
            curated_decision = (gemma.get(slot, {}).get("curated_selection") or {}).get("decision", "n/a")
            print(f"  [{slot}] pmid:{pmid} -> pmcid={derived_pmcid or '--'} "
                  f"units={entry['source_units_available_for_gemma']} "
                  f"gemma naive={naive_decision} curated={curated_decision}")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    # Cache-first / API-on-miss: i tre rami che una futura architettura
    # incontrerebbe. Il ramo miss viene esercitato due volte, perché "recuperabile"
    # e "non recuperabile" sono esiti diversi e vanno distinti entrambi.
    scratch = Path(tempfile.mkdtemp(prefix="mtb-probe-miss-"))
    empty_root = Path(tempfile.mkdtemp(prefix="mtb-probe-emptycache-"))
    try:
        document_a = f"pmid:{picks['A']['selected_pmid']}" if "A" in picks else None
        hit = resolve_document_probe(document_a, scratch,
                                     delay_seconds=args.delay_seconds) if document_a else {}
        miss_ok = resolve_document_probe(document_a, scratch, cache_root=empty_root,
                                         delay_seconds=args.delay_seconds) if document_a else {}
        unfetchable = next((r["document_id"] for r in da.read_jsonl(da.document_manifest_path())
                            if not r.get("local_cache_path")), None)
        miss_ko = resolve_document_probe(unfetchable, scratch, cache_root=empty_root,
                                         delay_seconds=args.delay_seconds) if unfetchable else {}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(empty_root, ignore_errors=True)
    miss = {"retrievable_document": miss_ok, "unretrievable_document": miss_ko}

    write_json(args.report_dir / "pubmed_probe.json", results.get("A", {}))
    write_json(args.report_dir / "pmc_probe.json", results.get("B", {}))
    write_json(args.report_dir / "unavailable_probe.json", {
        "case_c": results.get("C", {}),
        "cache_miss_simulation": {"cache_hit_path": hit, "cache_miss_path": miss},
    })
    write_json(args.report_dir / "cache_vs_fetch.json", comparisons)
    write_json(args.report_dir / "gemma_probe.json", gemma)
    write_json(args.report_dir / "provenance_probe.json",
               {"probe_version": PROBE_VERSION, "documents": provenance})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
