"""Sigillo dell'emendamento A01, separato da quello del protocollo padre."""
import hashlib
import json
import pathlib
from datetime import datetime, timezone

HERE = pathlib.Path("evaluation/final_protocol/amendments/A01")

NORMATIVE = (
    "amendment.md",
    "operational_scenario_bindings.json",
    "parser_failure_fixture.json",
    "selector_failure_fixture.json",
    "cache_seed_contract.json",
    "provenance.json",
    "check_amendment_consistency.py",
)


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


files = {name: sha(HERE / name) for name in sorted(NORMATIVE)}
joined = "\n".join(f"{n}:{d}" for n, d in sorted(files.items()))
amendment_sha = hashlib.sha256(joined.encode("utf-8")).hexdigest()
provenance = json.loads((HERE / "provenance.json").read_text(encoding="utf-8"))
review = provenance["human_review"]

payload = {
    "amendment_id": "mtb-graphrag-final-evaluation/1.1-A01",
    "parent_protocol_version": "mtb-graphrag-final-evaluation/1.1",
    "parent_protocol_sha256": "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889",
    "parent_freeze_commit": "7b0b396b10d10794ac802325f8e7e2ff5ce33e28",
    "runtime_commit": "3d2251f82a586535f79f3d0b3725c16330c365ba",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "hash_algorithm": "sha256",
    "file_hash_rule": "sha256 dei byte del file con CRLF normalizzato a LF",
    "amendment_hash_rule": "sha256 delle righe 'nome:sha' ordinate e unite da \\n",
    "files": files,
    "amendment_sha256": amendment_sha,
    "parent_protocol_sha256_recomputed": False,
    "evaluation_identity": {
        "PARENT_PROTOCOL_SHA": provenance["parent_protocol_sha256"],
        "AMENDMENT_A01_SHA": amendment_sha,
        "required_on_every_future_final_artifact": True,
    },
    "human_review": {
        "reviewer": review["reviewer"],
        "review_date": review["review_date"],
        "review_verdict": review["review_verdict"],
        "approved_scenario_count": sum(
            status == "APPROVED" for status in review["scenario_approvals"].values()
        ),
    },
    "final_results_observed_before_A01_freeze":
        provenance["final_results_observed_before_A01_freeze"],
    "frozen": provenance["frozen"],
    "freeze_timestamp": provenance["freeze_timestamp"],
    "freeze_scope": provenance["freeze_scope"],
    "freeze_note": (
        "A01 congelato dopo human review ACCEPTED. Qualunque modifica futura al materiale "
        "protetto richiede A02 oppure una nuova versione del protocollo."
    ),
}

(HERE / "amendment_hash.json").write_text(
    json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

print("amendment_sha256 :", amendment_sha)
print("file sigillati   :", len(files))
for n, d in sorted(files.items()):
    print(f"  {n:38s} {d[:16]}")
