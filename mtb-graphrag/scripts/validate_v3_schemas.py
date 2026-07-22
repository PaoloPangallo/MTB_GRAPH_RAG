"""Valida gli artefatti di specifica della V3.

    cd mtb-graphrag
    python scripts/validate_v3_schemas.py

Non valida l'implementazione — la V3 non e' implementata. Valida che i contratti
siano ben formati e che gli esempi li rispettino, che e' l'unica cosa verificabile
su una specifica congelata.

Se `jsonschema` non e' installato, la validazione strutturale viene saltata con un
avviso invece di fallire: la libreria non e' fra le dipendenze dichiarate del
progetto, e aggiungerla per uno script di specifica non si giustifica.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
EXAMPLE_DIR = SCHEMA_DIR / "examples"

# Quale schema valida quale esempio.
EXAMPLE_SCHEMA_MAP = {
    "evidence_statement_fgfr2.json": "evidence_statement.schema.json",
    "evidence_statement_alk_resistance.json": "evidence_statement.schema.json",
    "case_graph_context_dependent.json": "case_graph.schema.json",
    "sufficiency_decision_sufficient.json": "sufficiency_decision.schema.json",
    "sufficiency_decision_refinement_required.json": "sufficiency_decision.schema.json",
    "sufficiency_decision_backend_failure.json": "sufficiency_decision.schema.json",
}

# Pattern di possibili identificatori personali. Gli esempi devono essere sintetici.
PII_PATTERNS = (
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b")),
    ("codice_fiscale", re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")),
    ("codice_paziente", re.compile(r"\b(?:MRN|cartella)\s*[:#]?\s*\d+", re.IGNORECASE)),
    ("data_di_nascita", re.compile(r"\bnat[oa]\s+il\b", re.IGNORECASE)),
)

# Frasi che presenterebbero il sistema come decisore clinico.
FORBIDDEN_CLINICAL_CLAIMS = (
    "recommended therapy",
    "correct therapy",
    "patient should receive",
    "clinically validated recommendation",
    "terapia raccomandata",
    "terapia corretta",
    "validazione clinica",
)


class Failure(Exception):
    pass


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise Failure(f"{path.name}: JSON non valido ({error.msg} a riga {error.lineno})")


def check_schemas() -> list[str]:
    notes: list[str] = []
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        payload = _load(path)
        declared = payload.get("$schema", "")
        if "json-schema.org" not in declared:
            raise Failure(f"{path.name}: nessuna draft dichiarata in $schema")
        if "title" not in payload or "description" not in payload:
            raise Failure(f"{path.name}: title o description mancanti")
        if payload.get("type") == "object" and "additionalProperties" not in payload:
            raise Failure(
                f"{path.name}: additionalProperties non dichiarato al livello radice. "
                "Va deciso consapevolmente, non lasciato implicito."
            )
        notes.append(f"  {path.name}: draft {declared.rsplit('/', 2)[-2]}, ok")
    return notes


def check_examples_validate() -> list[str]:
    try:
        import jsonschema
    except ImportError:
        return [
            "  jsonschema non installato: validazione strutturale saltata.",
            "  Installare con `pip install jsonschema` per il controllo completo.",
        ]

    notes: list[str] = []
    for example_name, schema_name in sorted(EXAMPLE_SCHEMA_MAP.items()):
        example_path = EXAMPLE_DIR / example_name
        schema_path = SCHEMA_DIR / schema_name
        if not example_path.is_file():
            raise Failure(f"esempio mancante: {example_name}")
        validator_cls = jsonschema.validators.validator_for(_load(schema_path))
        validator = validator_cls(_load(schema_path))
        errors = sorted(validator.iter_errors(_load(example_path)), key=lambda e: e.path)
        if errors:
            first = errors[0]
            location = "/".join(str(part) for part in first.path) or "(radice)"
            raise Failure(
                f"{example_name} non valida contro {schema_name}: "
                f"{location}: {first.message[:200]}"
            )
        notes.append(f"  {example_name} valida contro {schema_name}")
    return notes


def check_no_personal_data() -> list[str]:
    notes: list[str] = []
    for path in sorted(EXAMPLE_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for label, pattern in PII_PATTERNS:
            if pattern.search(text):
                raise Failure(f"{path.name}: possibile identificatore personale ({label})")
        notes.append(f"  {path.name}: nessun identificatore personale")
    return notes


def check_examples_are_marked_illustrative() -> list[str]:
    """Gli esempi non devono poter essere scambiati per gold o per predizioni."""
    notes: list[str] = []
    for path in sorted(EXAMPLE_DIR.glob("*.json")):
        payload = _load(path)
        identifier = str(
            payload.get("evidence_statement_id")
            or payload.get("case_id")
            or payload.get("decision_id")
            or ""
        )
        if "ILLUSTRATIVE" not in identifier.upper():
            raise Failure(
                f"{path.name}: l'identificatore {identifier!r} non e' marcato come "
                "illustrativo e potrebbe essere scambiato per un caso gold"
            )
        notes.append(f"  {path.name}: marcato illustrativo")
    return notes


def check_no_frozen_unverified_evidence() -> list[str]:
    """Nessun esempio deve presentare come congelato un fatto non verificato."""
    notes: list[str] = []
    for path in sorted(EXAMPLE_DIR.glob("evidence_statement_*.json")):
        payload = _load(path)
        status = payload.get("review_status")
        promotion = (payload.get("provenance") or {}).get("promotion")
        if status == "frozen" and not promotion:
            raise Failure(
                f"{path.name}: review_status 'frozen' senza azione di promozione. "
                "Uno statement non puo' diventare congelato senza promozione esplicita."
            )
        notes.append(f"  {path.name}: review_status {status!r} coerente")
    return notes


# Marcatori che, sulla **stessa riga**, indicano che la frase e' citata per essere
# negata o vietata invece che affermata.
_NEGATION_MARKERS = (
    "non ", "mai ", "vietat", "non usare", "non e'", "non è", "invece di",
    "sostituto", "esclude", "not ", "never ", "forbidden", "must not",
)


def check_no_clinical_decision_claims() -> list[str]:
    """Cerca formulazioni che presenterebbero il sistema come decisore clinico.

    Il controllo e' per riga, non per documento: un documento che *vieta* una frase
    la contiene necessariamente, e cercarla a livello di file segnalerebbe proprio i
    testi che fanno la cosa giusta. Solo un uso affermativo e' un problema.
    """
    notes: list[str] = []
    targets = list(EXAMPLE_DIR.glob("*.json")) + list(SCHEMA_DIR.glob("*.schema.json"))
    targets += list((ROOT / "docs").glob("V3_*.md"))
    for path in sorted(targets):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            lowered = line.casefold()
            for phrase in FORBIDDEN_CLINICAL_CLAIMS:
                if phrase not in lowered:
                    continue
                if any(marker in lowered for marker in _NEGATION_MARKERS):
                    continue
                raise Failure(
                    f"{path.name}:{number}: uso affermativo della formulazione "
                    f"vietata {phrase!r}"
                )
        notes.append(f"  {path.name}: nessun uso affermativo")
    return notes


CHECKS = (
    ("Schema ben formati", check_schemas),
    ("Esempi validi contro gli schema", check_examples_validate),
    ("Nessun dato personale", check_no_personal_data),
    ("Esempi marcati come illustrativi", check_examples_are_marked_illustrative),
    ("Nessuna evidenza congelata senza promozione", check_no_frozen_unverified_evidence),
    ("Nessuna affermazione di decisione clinica", check_no_clinical_decision_claims),
)


def main() -> int:
    failures = 0
    for title, check in CHECKS:
        print(f"\n{title}")
        try:
            for note in check():
                print(note)
        except Failure as error:
            print(f"  FALLITO: {error}")
            failures += 1
    print("\n" + ("OK: tutti i controlli superati" if not failures
                  else f"FALLITI: {failures} controlli"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
