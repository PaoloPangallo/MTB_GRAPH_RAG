"""Repository degli EvidenceStatement: conservazione, identita', indici.

Segue il pattern gia' presente nel progetto in `SourceClinicalProfileRepository`:
costruttore che costruisce gli indici, lookup `by_*` che restituiscono `None`, un
`require` che solleva un errore tipizzato, funzioni di modulo per il caricamento.

Tre proprieta' governano il disegno.

**Immutabilita'.** Il repository non modifica mai gli statement ricevuti. Non normalizza
in-place, non arricchisce, non cambia `review_status`, non deduce campi mancanti. Le
rappresentazioni normalizzate servono agli indici e vivono separate dal dato.

**Order invariance.** Nessun risultato dipende dall'ordine di ingestione. L'ordinamento
e' dichiarato, e il `content_hash` e' calcolato su un ordine canonico: due ingestioni
con ordine diverso producono lo stesso hash.

**Snapshot isolation.** Statement provenienti da grafi diversi non si mescolano per
default. Mescolarli senza dichiararlo renderebbe ogni metrica successiva non
interpretabile, perche' il denominatore verrebbe da un grafo e il numeratore da un altro.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

REPOSITORY_VERSION = "evidence_repository/1.0"

# Ordinamento dichiarato dei risultati. Non dipende dall'ingestione.
SORT_KEY_FIELDS = (
    "disease",
    "biomarker",
    "intervention",
    "first_source_identifier",
    "evidence_statement_id",
)

# Campi su cui due statement con la stessa identita' devono coincidere perche' siano
# considerati lo stesso statement. Escludono i timestamp, che cambiano a ogni run.
IDENTITY_PAYLOAD_FIELDS = (
    "biomarker",
    "alteration_type",
    "disease",
    "intervention",
    "regimen",
    "direction",
    "evidence_scope",
    "assertion_polarity",
    "evidence_type",
    "evidence_level",
    "source_references",
    "trial_references",
    "review_status",
)


class EvidenceRepositoryError(RuntimeError):
    """Errore del repository degli statement."""


class StatementNotFound(KeyError):
    """Nessuno statement corrisponde alla chiave richiesta."""


class DuplicateStatementConflict(EvidenceRepositoryError):
    """Due statement dichiarano la stessa identita' con contenuto incompatibile."""


class SnapshotMismatchError(EvidenceRepositoryError):
    """Statement provenienti da snapshot diversi in un repository a snapshot singolo."""


class RepositorySerializationError(EvidenceRepositoryError):
    """La serializzazione o il round-trip non hanno preservato il contenuto."""


class IndexConsistencyError(EvidenceRepositoryError):
    """Gli indici non corrispondono agli statement conservati."""


# ── Normalizzazione per gli indici ────────────────────────────────────────────
# Le forme normalizzate servono solo a indicizzare. Il valore originale non viene
# mai sovrascritto: e' conservato nello statement e restituito dai lookup.


def _norm(value: Any) -> str:
    from ._normalize import normalize_text

    return normalize_text(value)


def _statement_id(statement: Mapping[str, Any]) -> str:
    return str(statement.get("evidence_statement_id") or "")


def _biomarker_label(statement: Mapping[str, Any]) -> str:
    return str((statement.get("biomarker") or {}).get("label") or "")


def _biomarker_gene(statement: Mapping[str, Any]) -> str:
    return str((statement.get("biomarker") or {}).get("gene") or "")


def _disease_label(statement: Mapping[str, Any]) -> str:
    return str((statement.get("disease") or {}).get("label") or "")


def _intervention_label(statement: Mapping[str, Any]) -> str:
    intervention = statement.get("intervention") or {}
    return str(intervention.get("label") or "")


def _regimen_label(statement: Mapping[str, Any]) -> str:
    regimen = statement.get("regimen") or {}
    return str(regimen.get("label") or "")


def _source_references(statement: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(statement.get("source_references") or [])


def _trial_references(statement: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(statement.get("trial_references") or [])


def _graph_record_ids(statement: Mapping[str, Any]) -> list[str]:
    return [str(item) for item in (statement.get("provenance") or {}).get("graph_record_ids") or []]


def _snapshot(statement: Mapping[str, Any]) -> str:
    return str((statement.get("provenance") or {}).get("snapshot_fingerprint") or "")


def _origin(statement: Mapping[str, Any]) -> str:
    return str((statement.get("provenance") or {}).get("origin") or "")


def _first_source_identifier(statement: Mapping[str, Any]) -> str:
    references = _source_references(statement)
    identifiers = sorted(str(ref.get("external_identifier") or "") for ref in references)
    return identifiers[0] if identifiers else ""


def sort_key(statement: Mapping[str, Any]) -> tuple[str, ...]:
    """Chiave di ordinamento dichiarata, indipendente dall'ingestione."""
    return (
        _norm(_disease_label(statement)),
        _norm(_biomarker_label(statement)),
        _norm(_intervention_label(statement)),
        _first_source_identifier(statement),
        _statement_id(statement),
    )


def identity_payload(statement: Mapping[str, Any]) -> dict[str, Any]:
    """Il contenuto che definisce l'identita', senza i campi volatili.

    `created_at` e `updated_at` cambiano a ogni esecuzione dell'adapter: includerli
    farebbe sembrare conflittuali due ingestioni dello stesso statement.
    """
    return {field: statement.get(field) for field in IDENTITY_PAYLOAD_FIELDS}


@dataclass(frozen=True)
class RepositoryManifest:
    repository_version: str
    schema_version: str
    snapshot_fingerprint: str
    source_adapter_version: str
    created_at: str
    statement_count: int
    content_hash: str
    multi_snapshot: bool = False
    snapshots: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository_version": self.repository_version,
            "schema_version": self.schema_version,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "source_adapter_version": self.source_adapter_version,
            "created_at": self.created_at,
            "statement_count": self.statement_count,
            "content_hash": self.content_hash,
            "multi_snapshot": self.multi_snapshot,
            "snapshots": list(self.snapshots),
        }


class EvidenceStatementRepository:
    """Conservazione e interrogazione degli EvidenceStatement, offline.

    Gli statement sono dizionari conformi a `schemas/evidence_statement.schema.json`.
    Non vengono convertiti in dataclass: lo schema e' l'unica fonte di verita', e
    duplicarlo in classi creerebbe due definizioni che possono divergere.
    """

    def __init__(
        self,
        statements: Iterable[Mapping[str, Any]] = (),
        *,
        allow_multiple_snapshots: bool = False,
        source_adapter_version: str = "",
        created_at: str | None = None,
    ) -> None:
        self._allow_multiple_snapshots = allow_multiple_snapshots
        self._source_adapter_version = source_adapter_version
        self._created_at = created_at or datetime.now(timezone.utc).isoformat()
        self._statements: dict[str, dict[str, Any]] = {}
        self._indices: dict[str, dict[str, list[str]]] = {}
        self._reset_indices()
        self.add_many(statements)

    # ── Ingestione ────────────────────────────────────────────────────────────

    def _reset_indices(self) -> None:
        self._indices = {
            name: defaultdict(list)  # type: ignore[misc]
            for name in (
                "graph_evidence_id", "gene", "biomarker", "alteration", "alteration_type",
                "disease", "intervention", "regimen", "direction", "evidence_scope",
                "assertion_polarity", "pmid", "doi", "nct", "source_identifier",
                "origin", "review_status", "snapshot",
            )
        }

    def add(self, statement: Mapping[str, Any]) -> str:
        """Aggiunge uno statement. Non modifica l'oggetto ricevuto.

        Solleva `DuplicateStatementConflict` se la stessa identita' arriva con un
        contenuto diverso: scegliere fra i due renderebbe il repository dipendente
        dall'ordine di ingestione.
        """
        identifier = _statement_id(statement)
        if not identifier:
            raise EvidenceRepositoryError(
                "statement senza evidence_statement_id: identita' non determinabile"
            )

        snapshot = _snapshot(statement)
        if not self._allow_multiple_snapshots:
            known = {value for value in (_snapshot(s) for s in self._statements.values()) if value}
            if snapshot and known and snapshot not in known:
                raise SnapshotMismatchError(
                    f"lo statement {identifier} viene dallo snapshot {snapshot[:16]} "
                    f"mentre il repository contiene {sorted(k[:16] for k in known)}. "
                    "Mescolarli renderebbe le metriche non interpretabili: usa "
                    "allow_multiple_snapshots=True se e' voluto."
                )

        existing = self._statements.get(identifier)
        if existing is not None:
            if identity_payload(existing) != identity_payload(statement):
                raise DuplicateStatementConflict(
                    f"due statement con id {identifier} hanno contenuto incompatibile. "
                    "Il repository non sceglie: correggi la sorgente o usa "
                    "identificatori distinti."
                )
            return identifier  # duplicato identico: gia' presente

        # Copia difensiva: il chiamante puo' continuare a usare il suo oggetto.
        self._statements[identifier] = copy.deepcopy(dict(statement))
        self._index_statement(self._statements[identifier])
        return identifier

    def add_many(self, statements: Iterable[Mapping[str, Any]]) -> list[str]:
        return [self.add(statement) for statement in statements]

    def _index_statement(self, statement: Mapping[str, Any]) -> None:
        identifier = _statement_id(statement)

        def put(index: str, key: str) -> None:
            if key:
                bucket = self._indices[index][key]
                if identifier not in bucket:
                    bucket.append(identifier)

        for record_id in _graph_record_ids(statement):
            put("graph_evidence_id", record_id)
        put("gene", _norm(_biomarker_gene(statement)))
        put("biomarker", _norm(_biomarker_label(statement)))
        put("alteration", _norm(_biomarker_label(statement)))
        put("alteration_type", _norm(statement.get("alteration_type")))
        put("disease", _norm(_disease_label(statement)))
        put("intervention", _norm(_intervention_label(statement)))
        put("regimen", _norm(_regimen_label(statement)))
        put("direction", _norm(statement.get("direction")))
        put("evidence_scope", _norm(statement.get("evidence_scope")))
        put("assertion_polarity", _norm(statement.get("assertion_polarity")))
        put("origin", _norm(_origin(statement)))
        put("review_status", _norm(statement.get("review_status")))
        put("snapshot", _snapshot(statement))

        for reference in _source_references(statement) + _trial_references(statement):
            identifier_value = str(reference.get("external_identifier") or "")
            source_type = str(reference.get("source_type") or "")
            put("source_identifier", identifier_value)
            if source_type == "pubmed":
                put("pmid", identifier_value)
            elif source_type == "doi":
                put("doi", identifier_value.casefold())
            elif source_type == "clinicaltrials_gov":
                put("nct", identifier_value.upper())

    # ── Accesso ───────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._statements)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.all())

    def count(self) -> int:
        return len(self._statements)

    def all(self) -> list[dict[str, Any]]:
        """Tutti gli statement, ordinati e come copie difensive."""
        return [copy.deepcopy(s) for s in sorted(self._statements.values(), key=sort_key)]

    def _resolve(self, identifiers: Sequence[str]) -> list[dict[str, Any]]:
        found = [self._statements[i] for i in identifiers if i in self._statements]
        return [copy.deepcopy(s) for s in sorted(found, key=sort_key)]

    def get_by_statement_id(self, statement_id: str) -> dict[str, Any] | None:
        statement = self._statements.get(str(statement_id))
        return copy.deepcopy(statement) if statement is not None else None

    def require(self, statement_id: str) -> dict[str, Any]:
        statement = self.get_by_statement_id(statement_id)
        if statement is None:
            raise StatementNotFound(f"nessuno statement con id {statement_id!r}")
        return statement

    def get_by_graph_evidence_id(self, evidence_id: object) -> list[dict[str, Any]]:
        key = str(evidence_id)
        if not key.startswith("evidence:"):
            key = f"evidence:{key}"
        return self._resolve(self._indices["graph_evidence_id"].get(key, []))

    def find_by_source_identifier(self, identifier: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["source_identifier"].get(str(identifier), []))

    def find_by_pmid(self, pmid: object) -> list[dict[str, Any]]:
        from ._normalize import normalize_pmid

        key = normalize_pmid(pmid)
        return self._resolve(self._indices["pmid"].get(key, [])) if key else []

    def find_by_doi(self, doi: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["doi"].get(str(doi).casefold(), []))

    def find_by_nct(self, nct_id: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["nct"].get(str(nct_id).upper(), []))

    def find_by_gene(self, gene: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["gene"].get(_norm(gene), []))

    def find_by_biomarker(self, biomarker: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["biomarker"].get(_norm(biomarker), []))

    def find_by_alteration_type(self, alteration_type: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["alteration_type"].get(_norm(alteration_type), []))

    def find_by_disease(self, disease: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["disease"].get(_norm(disease), []))

    def find_by_intervention(self, intervention: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["intervention"].get(_norm(intervention), []))

    def find_by_direction(self, direction: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["direction"].get(_norm(direction), []))

    def find_by_evidence_scope(self, scope: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["evidence_scope"].get(_norm(scope), []))

    def find_by_assertion_polarity(self, polarity: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["assertion_polarity"].get(_norm(polarity), []))

    def find_by_origin(self, origin: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["origin"].get(_norm(origin), []))

    def find_by_review_status(self, review_status: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["review_status"].get(_norm(review_status), []))

    def find_by_snapshot_fingerprint(self, fingerprint: object) -> list[dict[str, Any]]:
        return self._resolve(self._indices["snapshot"].get(str(fingerprint), []))

    # ── Query composte ────────────────────────────────────────────────────────

    _FILTER_INDEX = {
        "gene": "gene",
        "biomarker": "biomarker",
        "alteration_type": "alteration_type",
        "disease": "disease",
        "intervention": "intervention",
        "regimen": "regimen",
        "direction": "direction",
        "evidence_scope": "evidence_scope",
        "assertion_polarity": "assertion_polarity",
        "origin": "origin",
        "review_status": "review_status",
    }
    _FILTER_EXACT = {
        "pmid": "pmid",
        "doi": "doi",
        "nct": "nct",
        "source_identifier": "source_identifier",
        "snapshot_fingerprint": "snapshot",
        "graph_evidence_id": "graph_evidence_id",
    }

    def query(self, **filters: Any) -> list[dict[str, Any]]:
        """Filtri combinati in AND. Risultato deterministico.

        Un filtro con chiave sconosciuta e' un errore, non un filtro ignorato: una
        query silenziosamente piu' larga di quanto chiesto restituirebbe risultati che
        il chiamante crede filtrati.
        """
        unknown = set(filters) - set(self._FILTER_INDEX) - set(self._FILTER_EXACT)
        if unknown:
            raise EvidenceRepositoryError(
                f"filtri non riconosciuti: {sorted(unknown)}. "
                f"Ammessi: {sorted(set(self._FILTER_INDEX) | set(self._FILTER_EXACT))}"
            )

        selected: set[str] | None = None
        for name, value in filters.items():
            if value is None:
                continue
            if name in self._FILTER_INDEX:
                key = _norm(value)
                bucket = set(self._indices[self._FILTER_INDEX[name]].get(key, []))
            else:
                index = self._FILTER_EXACT[name]
                raw = str(value)
                if index == "doi":
                    raw = raw.casefold()
                elif index == "nct":
                    raw = raw.upper()
                elif index == "graph_evidence_id" and not raw.startswith("evidence:"):
                    raw = f"evidence:{raw}"
                elif index == "pmid":
                    from ._normalize import normalize_pmid

                    raw = normalize_pmid(raw)
                bucket = set(self._indices[index].get(raw, []))
            selected = bucket if selected is None else (selected & bucket)
            if not selected:
                return []
        if selected is None:
            return self.all()
        return self._resolve(sorted(selected))

    # ── Indici ────────────────────────────────────────────────────────────────

    def index_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._indices))

    def rebuild_indices(self) -> None:
        """Ricostruisce gli indici dagli statement. Sono derivati, non la fonte."""
        self._reset_indices()
        for statement in self._statements.values():
            self._index_statement(statement)

    def validate_indices(self) -> list[str]:
        """Verifica la coerenza degli indici. Restituisce i problemi trovati."""
        problems: list[str] = []

        for name, index in self._indices.items():
            for key, identifiers in index.items():
                for identifier in identifiers:
                    if identifier not in self._statements:
                        problems.append(
                            f"indice {name}[{key!r}] punta a {identifier}, che non esiste"
                        )
                if len(identifiers) != len(set(identifiers)):
                    problems.append(f"indice {name}[{key!r}] contiene duplicati")

        # Ogni statement deve comparire negli indici che lo riguardano.
        for identifier, statement in self._statements.items():
            if _statement_id(statement) not in self._indices["review_status"].get(
                _norm(statement.get("review_status")), []
            ):
                problems.append(f"{identifier} assente dall'indice review_status")

        # La ricostruzione deve produrre gli stessi indici.
        before = {
            name: {key: sorted(values) for key, values in index.items() if values}
            for name, index in self._indices.items()
        }
        self.rebuild_indices()
        after = {
            name: {key: sorted(values) for key, values in index.items() if values}
            for name, index in self._indices.items()
        }
        if before != after:
            problems.append("la ricostruzione degli indici produce un risultato diverso")
        return problems

    # ── Manifest e serializzazione ────────────────────────────────────────────

    def content_hash(self) -> str:
        """Hash del contenuto, su un ordine canonico indipendente dall'ingestione."""
        from benchmarks.mtb_evidence.pilot.audit_lib.serialize import fingerprint

        ordered = [
            self._statements[key] for key in sorted(self._statements)
        ]
        return fingerprint(ordered)

    def snapshots(self) -> tuple[str, ...]:
        return tuple(sorted({s for s in (_snapshot(v) for v in self._statements.values()) if s}))

    def manifest(self, *, schema_version: str = "v3.0.0") -> RepositoryManifest:
        snapshots = self.snapshots()
        return RepositoryManifest(
            repository_version=REPOSITORY_VERSION,
            schema_version=schema_version,
            snapshot_fingerprint=snapshots[0] if len(snapshots) == 1 else "",
            source_adapter_version=self._source_adapter_version,
            created_at=self._created_at,
            statement_count=len(self._statements),
            content_hash=self.content_hash(),
            multi_snapshot=self._allow_multiple_snapshots,
            snapshots=snapshots,
        )

    def to_jsonl(self, path: Path) -> Path:
        from benchmarks.mtb_evidence.pilot.audit_lib.serialize import write_jsonl

        return write_jsonl(Path(path), [self._statements[k] for k in sorted(self._statements)])

    @classmethod
    def from_jsonl(
        cls,
        path: Path,
        *,
        allow_multiple_snapshots: bool = False,
        source_adapter_version: str = "",
        created_at: str | None = None,
    ) -> "EvidenceStatementRepository":
        from benchmarks.mtb_evidence.pilot.audit_lib.serialize import read_jsonl

        return cls(
            read_jsonl(Path(path)),
            allow_multiple_snapshots=allow_multiple_snapshots,
            source_adapter_version=source_adapter_version,
            created_at=created_at,
        )

    def round_trip_ok(self, path: Path) -> tuple[bool, str]:
        """Serializza, rilegge e verifica che il contenuto sia identico."""
        original_hash = self.content_hash()
        self.to_jsonl(path)
        reloaded = EvidenceStatementRepository.from_jsonl(
            path,
            allow_multiple_snapshots=self._allow_multiple_snapshots,
            source_adapter_version=self._source_adapter_version,
            created_at=self._created_at,
        )
        if reloaded.count() != self.count():
            return False, f"conteggio diverso: {reloaded.count()} contro {self.count()}"
        if reloaded.content_hash() != original_hash:
            return False, "content_hash diverso dopo il round-trip"
        return True, "round-trip identico"


def load_statements(path: Path) -> EvidenceStatementRepository:
    """Carica un repository da un JSONL di statement."""
    return EvidenceStatementRepository.from_jsonl(Path(path))
