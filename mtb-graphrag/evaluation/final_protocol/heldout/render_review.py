"""Rendering del documento di review umana dell'held-out.

Il documento è generato dagli artefatti congelati, non scritto a mano: se un
caso cambia, la tabella cambia con lui e non può divergere in silenzio.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
HELDOUT_DIR = Path(__file__).resolve().parent
OUT_PATH = REPO_ROOT / "docs/final_evaluation/heldout_review.md"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _cell(value: Any) -> str:
    """Testo sicuro per una cella di tabella markdown."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sì" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value) or "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _summarize(text: str, limit: int = 120) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def render() -> str:
    cases = _json(HELDOUT_DIR / "architectural_challenge_cases.json")
    gold = {row["case_id"]: row for row in _json(HELDOUT_DIR / "architectural_challenge_gold.json")["gold"]}
    narrative = _json(HELDOUT_DIR / "narrative_heldout_cases.json")
    narrative_gold = {row["case_id"]: row for row in _json(HELDOUT_DIR / "narrative_heldout_gold.json")["gold"]}
    control = _json(HELDOUT_DIR / "narrative_heldout_valid_control.json")
    overlap = _json(HELDOUT_DIR / "overlap_report.json")
    manifest = _json(HELDOUT_DIR / "heldout_manifest.json")
    hashes = _json(HELDOUT_DIR / "heldout_hashes.json")

    overlap_by_case: dict[str, list[str]] = {}
    for hit in overlap["boilerplate_overlap"] + overlap["substantive_overlap"]:
        overlap_by_case.setdefault(hit["heldout"], []).append(
            f"{hit['dev_case']} ({hit['count']}×5-gram)")

    lines: list[str] = []
    add = lines.append

    add("# Held-out challenge set — documento di review")
    add("")
    add("```")
    add(f"protocol_version      : {manifest['protocol_version']}")
    add(f"runtime_commit        : {manifest['runtime_commit']}")
    add(f"runtime_freeze        : {manifest['runtime_freeze_timestamp']}")
    add(f"creation_timestamp    : {manifest['creation_timestamp']}")
    add(f"heldout_bundle_sha256 : {hashes['heldout_bundle_sha256']}")
    add(f"overlap_verdict       : {manifest['overlap_verdict']}")
    add(f"frozen                : {str(manifest['frozen']).lower()}")
    add("```")
    add("")
    add("Questo documento esiste per essere **rifiutato o corretto prima delle run**.")
    add("Dopo il freeze nessun caso potrà essere modificato, sostituito, escluso o")
    add("rietichettato sulla base dei risultati.")
    add("")
    add("Cosa il revisore deve verificare, in ordine di importanza:")
    add("")
    add("1. l'`EXPECTED_PATH` è difendibile **senza** conoscere l'output del sistema?")
    add("2. il caso richiede un giudizio terapeutico che non abbiamo? (in tal caso va rifiutato)")
    add("3. il testo è una riformulazione mascherata di un caso di sviluppo?")
    add("4. per i casi `COMPLETE` e `NEGATIVE_POLARITY_STRESS`: il legame con la candidate")
    add("   citata è corretto?")
    add("")
    add("Il gold è stato scritto dall'assistente sotto direzione dell'autore della tesi e")
    add("copre **solo proprietà architetturali osservabili**. Nessun caso afferma quale")
    add("terapia sia clinicamente corretta.")
    add("")

    add("## 1. Architectural challenge set")
    add("")
    add(f"N = {cases['n_cases']} · " + " · ".join(
        f"{k} {v}" for k, v in sorted(cases["by_category"].items())))
    add("")
    add(f"**{cases['label']}** — non è un campione a prevalenza clinica.")
    add("")

    for category in sorted(cases["by_category"]):
        rows = [c for c in cases["cases"] if c["category"] == category]
        add(f"### {category} · N = {len(rows)}")
        add("")
        add("| CASE_ID | INPUT_SUMMARY | EXPECTED_PATH | GOLD_RATIONALE | OVERLAP | NOTES |")
        add("|---|---|---|---|---|---|")
        for case in rows:
            g = gold[case["case_id"]]
            retrieval = g["expected_retrieval_allowed"]
            path = (
                f"eligibility ∈ {{{_cell(g['expected_eligibility'])}}}; "
                f"retrieval={'null (vedi hard_property)' if retrieval is None else _cell(retrieval)}; "
                f"stop={_cell(g.get('expected_stop_stage'))}; "
                f"run={_cell(g['expected_run_state'])}"
            )
            notes: list[str] = []
            if case.get("source_reference"):
                ref = case["source_reference"]
                notes.append(
                    f"candidate {ref['candidate_id']}, direction={ref['evidence_direction']}, "
                    f"significance={ref['significance']}, level={ref['evidence_level']}, "
                    f"PMID {', '.join(ref['pmids'])}")
            else:
                notes.append(
                    "nessuna candidate ancorata: la proprietà valutata è il percorso, "
                    "non il contenuto documentale")
            if g.get("hard_property"):
                notes.append(f"HARD: {g['hard_property']} — {g['hard_observable']}")
            if case.get("resolution_class"):
                notes.append(f"resolution_class={case['resolution_class']}")
            add("| `{id}` | {summary} | {path} | {rationale} | {overlap} | {notes} |".format(
                id=case["case_id"],
                summary=_cell(_summarize(case["text"], 150)),
                path=_cell(path),
                rationale=_cell(_summarize(g["rationale"], 200)),
                overlap=_cell(overlap_by_case.get(case["case_id"])),
                notes=_cell(" — ".join(notes)),
            ))
        add("")

    add("## 2. Narrative held-out — casi ostili")
    add("")
    add(f"N = {narrative['n_cases']} · " + " · ".join(
        f"{k} {v}" for k, v in sorted(narrative["by_mutation_type"].items())))
    add("")
    add("| CASE_ID | BASE | MUTATION_TYPE | MUTATED_FIELD_OR_CLAIM | EXPECTED_VERDICT | RATIONALE |")
    add("|---|---|---|---|---|---|")
    for case in narrative["cases"]:
        g = narrative_gold[case["case_id"]]
        add("| `{id}` | {base} | {mtype} | {field} | {verdict} | {rationale} |".format(
            id=case["case_id"],
            base=f"{case['base_id']} ({case['base_dossier']['canonical_status']})",
            mtype=_cell(case["mutation_type"]),
            field=_cell(case["mutated_field_or_claim"]),
            verdict=_cell(g["expected_verdict"]),
            rationale=_cell(case["mutation_instruction"]),
        ))
    add("")

    add("## 3. Narrative held-out — controlli positivi (file separato)")
    add("")
    add(control["purpose"])
    add("")
    add("| CASE_ID | BASE | MUTATION_TYPE | EXPECTED_VERDICT | RATIONALE |")
    add("|---|---|---|---|---|")
    control_gold = {row["case_id"]: row for row in control["gold"]}
    for case in control["cases"]:
        g = control_gold[case["case_id"]]
        add("| `{id}` | {base} | {mtype} | {verdict} | {rationale} |".format(
            id=case["case_id"],
            base=f"{case['base_id']} ({case['base_dossier']['canonical_status']})",
            mtype=_cell(case["mutation_type"]),
            verdict=_cell(g["expected_verdict"]),
            rationale=_cell(case["mutation_instruction"]),
        ))
    add("")

    add("## 4. Base dossier")
    add("")
    add("Specifiche deterministiche derivate da candidate congelate. **Non sono output")
    add("di run**: né il narratore né il verifier li hanno mai visti.")
    add("")
    add("| BASE_ID | CANDIDATE | STATUS | BUCKET | QUOTE VALIDATA | CAVEAT CANONICI | HASH |")
    add("|---|---|---|---|---|---|---|")
    for base in narrative["base_dossiers"]:
        add("| {bid} | {cid} | {status} | {bucket} | {quote} | {caveats} | `{h}` |".format(
            bid=base["base_id"],
            cid=f"{base['candidate_id']}<br>{base['disease']} · {base['biomarker']} · {base['intervention']}",
            status=_cell(base["canonical_status"]),
            bucket=_cell(base["gate_bucket"]),
            quote="sì" if base["validated_quote"] else "no",
            caveats=_cell(base["canonical_caveats"]),
            h=narrative["base_dossier_hashes"][base["base_id"]][:16] + "…",
        ))
    add("")

    add("## 5. Overlap con i corpus di sviluppo")
    add("")
    add("| CONTROLLO | ESITO |")
    add("|---|---|")
    add(f"| exact text overlap | {len(overlap['exact_text_overlap'])} |")
    add(f"| normalized text overlap | {len(overlap['normalized_text_overlap'])} |")
    add(f"| case-id collisions | {len(overlap['case_id_collisions'])} |")
    for corpus, ids in sorted(overlap["candidate_overlap_by_corpus"].items()):
        add(f"| candidate overlap · {corpus} | {len(ids)} |")
    add(f"| near-duplicate 5-grammi · sostanziali | {len(overlap['substantive_overlap'])} |")
    add(f"| near-duplicate 5-grammi · boilerplate | {len(overlap['boilerplate_overlap'])} |")
    add(f"| **verdetto** | **{overlap['overlap_verdict']}** |")
    add("")
    add("Ogni hit, per esteso:")
    add("")
    add("| HELD-OUT | CORPUS | CASO DI SVILUPPO | 5-GRAMMI CONDIVISI | CLASSE |")
    add("|---|---|---|---|---|")
    for label, hits in (("sostanziale", overlap["substantive_overlap"]),
                        ("boilerplate", overlap["boilerplate_overlap"])):
        for hit in hits:
            add("| `{h}` | {c} | `{d}` | {g} | {l} |".format(
                h=hit["heldout"], c=hit["corpus"], d=hit["dev_case"],
                g=_cell(hit["shared_5grams"]), l=label))
    add("")
    add(f"> {overlap['boilerplate_rule']['honesty_note']}")
    add("")
    add("Sovrapposizioni dichiarate e volute:")
    add("")
    add(f"* {overlap['declared_shared_properties']['note']}")
    add(f"* {overlap['declared_shared_properties']['entity_reuse_within_heldout']}")
    add("")

    grounded = _json(HELDOUT_DIR / "grounded_review.json")

    add("## 6. Revisione meccanica dei casi grounded")
    add("")
    add(grounded["method"])
    add("")
    add(f"Criterio: {grounded['criterion']}")
    add("")
    add(f"**Esito: {grounded['n_approvable']}/{grounded['n_cases']} approvabili — "
        f"`{grounded['verdict']}`**")
    add("")
    add("| CASE_ID | GCA_ID | DISEASE | BIOMARKER / ALTERATION | INTERVENTION | DIRECTION | SIG | LVL | DOC | D | B | I | DIR |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in grounded["rows"]:
        add("| `{cid}` | `{gca}` | {dis} | {bio} | {inter} | {dirn} | {sig} | {lvl} | {doc} | {d} | {b} | {i} | {dr} |".format(
            cid=row["CASE_ID"], gca=row["GCA_ID"],
            dis=_cell(row["GCA_DISEASE"]), bio=_cell(row["GCA_BIOMARKER"]),
            inter=_cell(row["GCA_INTERVENTION"]), dirn=_cell(row["GCA_EVIDENCE_DIRECTION"]),
            sig=_cell(row["GCA_SIGNIFICANCE"]), lvl=_cell(row["GCA_LEVEL"]),
            doc=_cell(row["GCA_DOCUMENT_IDENTIFIER"]),
            d="✓" if row["TEXT_DISEASE_MATCH"] else "✗",
            b="✓" if row["TEXT_BIOMARKER_MATCH"] else "✗",
            i="✓" if row["TEXT_INTERVENTION_MATCH"] else "✗",
            dr="✓" if row["EXPECTED_DIRECTION_MATCH"] else "✗"))
    add("")
    add(f"Normalizzazione applicata: {grounded['normalization']}.")
    add("")
    add("Note di match, per caso:")
    add("")
    for row in grounded["rows"]:
        add(f"* `{row['CASE_ID']}` — disease: {row['TEXT_DISEASE_NOTE']}; "
            f"biomarker: {row['TEXT_BIOMARKER_NOTE']}; "
            f"intervento: {row['TEXT_INTERVENTION_NOTE']}; "
            f"direzione: {row['EXPECTED_DIRECTION_NOTE']}.")
    add("")
    for case_id, note in grounded["intentional_discordance"].items():
        add(f"> **Discordanza intenzionale — `{case_id}`.** {note}")
        add("")

    revised = manifest.get("revision_summary", {})
    add("## 7. Revisione applicata")
    add("")
    add(f"`revised_in = {revised.get('revised_in')}` · "
        f"applicata **prima** di osservare qualunque output del sistema.")
    add("")
    add("| CORPUS | INVARIATI APPROVATI | REVISIONATI |")
    add("|---|---|---|")
    add(f"| architectural | {revised.get('architectural_unchanged')} | "
        f"{len(revised.get('architectural_revised', []))} |")
    add(f"| narrative hostile | {revised.get('narrative_unchanged')} | "
        f"{len(revised.get('narrative_revised', []))} |")
    add(f"| positive controls | {len(control['cases'])} | "
        f"{len(revised.get('positive_controls_revised', []))} |")
    add("")
    add("| CASE_ID | ID PRECEDENTE | CONTENUTO PRECEDENTE | MOTIVO |")
    add("|---|---|---|---|")
    for case in cases["cases"] + narrative["cases"]:
        rev = case.get("revision")
        if not rev:
            continue
        add("| `{cid}` | {prev} | {content} | {reason} |".format(
            cid=case["case_id"],
            prev=_cell(rev.get("previous_case_id") or rev.get("previous_base_id")),
            content=_cell(_summarize(rev.get("previous_content", ""), 110)),
            reason=_cell(_summarize(rev["reason"], 260))))
    add("")

    add("## 8. Esito della review")
    add("")
    add("| CAMPO | VALORE |")
    add("|---|---|")
    add("| review_status | **REVISION_APPLIED_PENDING_FINAL_APPROVAL** |")
    add(f"| architectural | {revised.get('architectural_unchanged')} invariati approvati, "
        f"{len(revised.get('architectural_revised', []))} revisionati |")
    add(f"| narrative hostile | {revised.get('narrative_unchanged')} invariati approvati, "
        f"{len(revised.get('narrative_revised', []))} revisionato |")
    add(f"| positive controls | {len(control['cases'])} invariati approvati |")
    add(f"| grounded mechanical review | {grounded['n_approvable']}/{grounded['n_cases']} |")
    add(f"| overlap verdict | {overlap['overlap_verdict']} |")
    add("| frozen | false |")
    add("")
    add("Da compilare dall'approvazione finale. Finché `review_status` non diventa")
    add("`ACCEPTED`, `frozen` resta `false` e la final evaluation non parte.")
    add("")
    add("| CAMPO | VALORE |")
    add("|---|---|")
    add("| revisore | |")
    add("| data | |")
    add("| casi ancora contestati | |")
    add("| gold ancora contestati | |")
    add("| esito finale | ACCEPTED / REVISION_REQUIRED |")
    add("")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    text = render()
    with OUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"scritto {OUT_PATH.relative_to(REPO_ROOT)} — {len(text.splitlines())} righe")
