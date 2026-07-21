"""Inventario dei modelli Ollama disponibili, locali e cloud.

    cd mtb-graphrag
    PYTHONPATH=. python benchmarks/mtb_evidence/model_selection/scripts/\\
inventory_ollama_models.py --output benchmarks/mtb_evidence/model_selection/results/v1

Registra ogni modello **osservato**, non ogni modello nominato: un candidato citato
nel protocollo ma assente dall'istanza compare come `available: false` con la ragione,
e non viene inventato.

Con `--allow-pull` lo script puo' scaricare i candidati mancanti, ma solo dopo aver
stampato una stima leggibile e solo entro il limite di dimensione configurato.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.pipeline.llm.model_capabilities import from_show_response  # noqa: E402
from backend.pipeline.llm.ollama_adapter import (  # noqa: E402
    OllamaClient,
    OllamaUnavailable,
    configured_endpoint,
    local_endpoint,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import write_json  # noqa: E402

# Candidati del protocollo. `current` viene risolto sul modello configurato dal
# progetto, così l'inventario non lo perde se `.env` cambia.
REQUIRED_CANDIDATES = ("current", "qwen3:14b", "gemma4:12b")
OPTIONAL_CANDIDATES = ("gemma4:31b-cloud", "gemma4:31b")

# Deve restare allineato a backend/pipeline/llm.py.
BACKEND_DEFAULT_MODEL = "gemma4:31b-cloud"

# Oltre questa soglia il download non e' automatico nemmeno con --allow-pull.
MAX_AUTO_PULL_BYTES = 20 * 1024**3

# Stime usate solo per il messaggio informativo prima del download.
PULL_SIZE_ESTIMATES_GB = {"qwen3:14b": 9.3, "gemma4:12b": 8.1}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--allow-pull",
        action="store_true",
        help="consente il download dei candidati mancanti sotto la soglia di dimensione",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def _resolve_current_model() -> str:
    """Il modello che il progetto usa oggi.

    Stesso default di `backend/pipeline/llm.py`: se `.env` non definisce
    `LLM_PIPELINE`, il backend usa comunque quel valore, e l'inventario deve
    riflettere cio' che gira davvero, non cio' che e' scritto nel file.
    """
    import os

    return (
        os.getenv("OLLAMA_PLANNER_MODEL")
        or os.getenv("LLM_PIPELINE")
        or BACKEND_DEFAULT_MODEL
    )


def _disk_free_bytes(path: Path) -> int:
    import shutil

    return shutil.disk_usage(path).free


def _pull(model: str, timeout: int = 3600) -> tuple[bool, str]:
    """Scarica un modello con la CLI ollama, che gestisce la progress bar."""
    try:
        result = subprocess.run(
            ["ollama", "pull", model], capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        return False, "CLI `ollama` non trovata nel PATH"
    except subprocess.TimeoutExpired:
        return False, f"download di {model} oltre il timeout di {timeout}s"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "errore sconosciuto").strip()[:300]
    return True, "scaricato"


def _collect(client: OllamaClient, endpoint, version: str) -> dict[str, dict]:
    """Capacita' di ogni modello elencato dall'endpoint, indicizzate per nome."""
    inventory: dict[str, dict] = {}
    for listing in client.list_models():
        name = listing.get("name") or listing.get("model") or ""
        if not name:
            continue
        try:
            show = client.show(name)
        except OllamaUnavailable as error:
            show = {"_show_error": str(error)}
        inventory[name] = from_show_response(
            name, listing, show, endpoint=endpoint, ollama_version=version
        ).as_dict()
    return inventory


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = datetime.now(timezone.utc).isoformat()

    endpoints = []
    local = local_endpoint()
    configured = configured_endpoint()
    endpoints.append(("local", local))
    if configured.base_url.rstrip("/") != local.base_url.rstrip("/"):
        endpoints.append(("configured", configured))

    discovered: dict[str, dict] = {}
    endpoint_status: list[dict] = []

    for label, endpoint in endpoints:
        client = OllamaClient(endpoint, timeout=args.timeout)
        reachable = client.reachable()
        version = client.version() if reachable else "unknown"
        status = {
            "label": label,
            "endpoint": endpoint.sanitized,
            "kind": endpoint.kind,
            "reachable": reachable,
            "ollama_version": version,
            "api_key_configured": bool(endpoint.api_key),
        }
        if reachable:
            models = _collect(client, endpoint, version)
            status["model_count"] = len(models)
            for name, payload in models.items():
                key = name if endpoint.kind == "local" else f"{name}-cloud"
                discovered.setdefault(key, payload)
        else:
            status["model_count"] = 0
            status["note"] = "endpoint non raggiungibile: nessun modello inventariato"
        endpoint_status.append(status)
        print(
            f"[{label:10s}] {endpoint.sanitized:35s} "
            f"{'OK' if reachable else 'NON RAGGIUNGIBILE':17s} "
            f"modelli={status['model_count']}"
        )

    current = _resolve_current_model()
    wanted = []
    for candidate in REQUIRED_CANDIDATES:
        wanted.append(current if candidate == "current" else candidate)
    wanted.extend(OPTIONAL_CANDIDATES)
    wanted = [w for w in dict.fromkeys(wanted) if w]

    missing = [name for name in wanted if name not in discovered]
    pull_log: list[dict] = []

    if missing:
        print(f"\nCandidati assenti: {missing}")
    if missing and args.allow_pull and local.base_url:
        free_gb = _disk_free_bytes(_PROJECT_ROOT) / 1024**3
        for name in list(missing):
            estimate = PULL_SIZE_ESTIMATES_GB.get(name)
            if name.endswith("-cloud"):
                pull_log.append({"model": name, "pulled": False,
                                 "reason": "modello cloud: non si scarica in locale"})
                continue
            if estimate is None:
                pull_log.append({"model": name, "pulled": False,
                                 "reason": "dimensione non stimabile: download non automatico"})
                continue
            if estimate * 1024**3 > MAX_AUTO_PULL_BYTES:
                pull_log.append({"model": name, "pulled": False,
                                 "reason": f"stima {estimate} GB oltre la soglia automatica"})
                continue
            print(
                f"  scarico {name}: stima ~{estimate:.1f} GB, "
                f"spazio libero {free_gb:.0f} GB"
            )
            ok, note = _pull(name)
            pull_log.append({"model": name, "pulled": ok, "reason": note,
                             "estimated_gb": estimate})
            print(f"    -> {'ok' if ok else 'FALLITO'}: {note}")
        if any(entry["pulled"] for entry in pull_log):
            client = OllamaClient(local, timeout=args.timeout)
            if client.reachable():
                discovered.update(_collect(client, local, client.version()))
    elif missing and not args.allow_pull:
        print("  (usa --allow-pull per scaricare i candidati locali mancanti)")

    candidates = []
    for name in wanted:
        payload = discovered.get(name)
        candidates.append(
            {
                "requested_name": name,
                "role_in_protocol": (
                    "current" if name == current
                    else "required" if name in REQUIRED_CANDIDATES
                    else "optional"
                ),
                "available": payload is not None,
                "unavailable_reason": None if payload else "non presente su alcun endpoint",
                "capabilities": payload,
            }
        )

    inventory = {
        "generated_at_utc": timestamp,
        "endpoints": endpoint_status,
        "configured_project_model": current,
        "candidates": candidates,
        "available_models": dict(sorted(discovered.items())),
        "available_count": len(discovered),
        "pull_log": pull_log,
        "pull_policy": {
            "allow_pull": args.allow_pull,
            "max_auto_pull_bytes": MAX_AUTO_PULL_BYTES,
            "note": "nessun download automatico oltre 20 GB, nemmeno con --allow-pull",
        },
    }

    path = write_json(args.output / "model_inventory.json", inventory)
    print(f"\nModelli osservati: {len(discovered)}")
    print(f"Candidati disponibili: {sum(1 for c in candidates if c['available'])}/{len(candidates)}")
    print(f"Scritto: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
