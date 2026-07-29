"""Loader in sola lettura del corpus V3 promosso.

Il loader e' separato dal retriever operativo e non e' importato da nessun
modulo del percorso operativo. La separazione e' l'unica cosa che tiene distinti
"promosso per il prototipo" e "in uso": se il retriever potesse arrivare qui, la
promozione avrebbe cambiato il comportamento della pipeline per il solo fatto di
essere avvenuta.

Il loader non ordina nulla. Non c'e' nessun punteggio, nessun bucket, nessun
top-k: restituisce record e indici di lookup, e chi vuole un ranking lo chiede a
un altro modulo. Un loader che classificasse sarebbe un retriever, e questo
corpus non ne ha ancora uno.

Tre rifiuti sono espliciti e non hanno un ramo permissivo:

    uno schema o una versione incompatibili
    un hash che non coincide con il manifest
    un record che non dichiara la propria propagation policy

e una modalita' di policy sconosciuta viene rifiutata invece di essere risolta
nella default. Una modalita' assente e una modalita' sbagliata non sono lo
stesso caso: risolvere la seconda nella default trasformerebbe un errore di
configurazione in una query piu' permissiva di quella chiesta.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.integrity import hash_policy as POLICY
from backend.pipeline.evidence.shadow import propagation as PROP


class PromotedCorpusError(RuntimeError):
    """Il corpus promosso non e' caricabile cosi' com'e'."""


class CorpusSchemaError(PromotedCorpusError):
    """Schema o versione del corpus incompatibili con questo loader."""


class CorpusHashMismatch(PromotedCorpusError):
    """Un file non coincide con l'hash che il manifest gli attribuisce."""


class CorpusSourceHashMismatch(CorpusHashMismatch):
    """Un sorgente della promozione non coincide con la propria forma canonica.

    Distinta dal caso generale perche' descrive un file *fuori* dal corpus: il
    corpus e' intatto, e' cambiato cio' da cui e' stato prodotto.
    """


class CorpusPolicyModeError(PromotedCorpusError):
    """La modalita' di policy richiesta non e' fra quelle ammesse."""


def _read_text(path: Path) -> str:
    if not path.exists():
        raise PromotedCorpusError(f"file assente dal corpus promosso: {path.name}")
    return path.read_text(encoding="utf-8")


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads(line) for line in _read_text(path).splitlines() if line.strip()
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(_read_text(path))


def _index(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    return {str(row[key]): row for row in rows}


def _group(
    rows: Sequence[Mapping[str, Any]], key: str
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        grouped.setdefault(str(value), []).append(row)
    return {key: tuple(value) for key, value in grouped.items()}


@dataclass(frozen=True)
class PromotedCorpus:
    """Il corpus promosso caricato, con i suoi indici di lookup.

    La struttura e' congelata e non espone nessun metodo di scrittura. Il loader
    apre i file in lettura e non li riapre mai: un corpus che potesse essere
    modificato dal proprio lettore non sarebbe un artefatto versionato.
    """

    root: Path
    manifest: Mapping[str, Any]
    registry_entry: Mapping[str, Any]
    policy_mode: str
    claims: tuple[Mapping[str, Any], ...]
    parents: tuple[Mapping[str, Any], ...]
    deprecated: tuple[Mapping[str, Any], ...]
    lineage: tuple[Mapping[str, Any], ...]
    links: tuple[Mapping[str, Any], ...]
    views: tuple[Mapping[str, Any], ...]
    unsupported: tuple[Mapping[str, Any], ...]
    unresolved: tuple[Mapping[str, Any], ...]
    terminology_registry: Mapping[str, Any]
    disease_relation_registry: Mapping[str, Any]
    formulation_registry: tuple[Mapping[str, Any], ...]

    # --- identita' del corpus ---------------------------------------------

    @property
    def repository_version(self) -> str:
        return str(self.manifest["repository_version"])

    @property
    def model_version(self) -> str:
        return str(self.manifest["model_version"])

    @property
    def schema_version(self) -> str:
        return str(self.manifest["schema_version"])

    @property
    def operational_retriever_bound(self) -> bool:
        return bool(self.manifest["operational_retriever_bound"])

    # --- lookup -------------------------------------------------------------

    def claim(self, claim_id: str) -> Mapping[str, Any] | None:
        """Un claim attivo per ID. I ritirati non compaiono nel lookup primario."""
        return _index(self.claims, "claim_id").get(str(claim_id))

    def retired_claim(self, claim_id: str) -> Mapping[str, Any] | None:
        return _index(self.deprecated, "claim_id").get(str(claim_id))

    def is_retired(self, claim_id: str) -> bool:
        return str(claim_id) in {str(row["claim_id"]) for row in self.deprecated}

    def redirect(self, claim_id: str) -> str | None:
        """Il claim attivo che sostituisce un ID ritirato, o `None` se non lo e'."""
        return {
            str(row["old_claim_id"]): str(row["new_claim_id"]) for row in self.lineage
        }.get(str(claim_id))

    def resolve(self, claim_id: str) -> Mapping[str, Any] | None:
        """Il claim attivo dietro un ID, seguendo il redirect quando serve."""
        direct = self.claim(claim_id)
        if direct is not None:
            return direct
        target = self.redirect(claim_id)
        return None if target is None else self.claim(target)

    def parent(self, parent_id: str) -> Mapping[str, Any] | None:
        return _index(self.parents, "parent_id").get(str(parent_id))

    def claims_for_parent(self, parent_id: str) -> tuple[Mapping[str, Any], ...]:
        return _group(self.claims, "parent_id").get(str(parent_id), ())

    def claims_for_evidence(self, graph_evidence_id: str) -> tuple[Mapping[str, Any], ...]:
        return _group(self.claims, "graph_evidence_id").get(str(graph_evidence_id), ())

    def claims_for_legacy_statement(
        self, statement_id: str
    ) -> tuple[Mapping[str, Any], ...]:
        wanted = str(statement_id)
        return tuple(
            claim
            for claim in self.claims
            if wanted in {str(item) for item in (claim.get("legacy_statement_ids") or ())}
        )

    def parents_without_claims(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            parent for parent in self.parents if not parent.get("child_claim_ids")
        )

    def unsupported_for_evidence(
        self, graph_evidence_id: str
    ) -> tuple[Mapping[str, Any], ...]:
        return _group(self.unsupported, "graph_evidence_id").get(str(graph_evidence_id), ())

    def unresolved_for_evidence(
        self, graph_evidence_id: str
    ) -> tuple[Mapping[str, Any], ...]:
        return _group(self.unresolved, "graph_evidence_id").get(str(graph_evidence_id), ())

    def links_for_claim(self, claim_id: str) -> tuple[Mapping[str, Any], ...]:
        wanted = str(claim_id)
        return tuple(link for link in self.links if link.get("target_claim_id") == wanted)

    def views_for_claim(self, claim_id: str) -> tuple[Mapping[str, Any], ...]:
        wanted = str(claim_id)
        return tuple(view for view in self.views if view.get("claim_id") == wanted)

    def counts(self) -> dict[str, int]:
        """Conteggi ricavati dai record caricati, non letti dal manifest."""
        by_domain: dict[str, int] = {}
        for claim in self.claims:
            domain = str(claim["claim_domain"])
            by_domain[domain] = by_domain.get(domain, 0) + 1
        return {
            "active_claims_total": len(self.claims),
            "deprecated_claims": len(self.deprecated),
            "diagnostic_claims": by_domain.get("diagnostic", 0),
            "lineage_rows": len(self.lineage),
            "links": len(self.links),
            "parents": len(self.parents),
            "parents_without_claims": len(self.parents_without_claims()),
            "prognostic_claims": by_domain.get("prognostic", 0),
            "therapeutic_claims": by_domain.get("therapeutic", 0),
            "unresolved_associations": len(self.unresolved),
            "unsupported_associations": len(self.unsupported),
            "views": len(self.views),
        }


def _verify_hashes(root: Path, manifest: Mapping[str, Any]) -> None:
    declared = manifest.get("artifact_sha256") or {}
    if not declared:
        raise CorpusSchemaError("il manifest non dichiara nessun hash di artefatto")
    mismatched = []
    for name, digest in sorted(declared.items()):
        path = root / name
        if not path.exists():
            raise PromotedCorpusError(
                f"file assente dal corpus promosso: {name}"
            )
        if POLICY.canonical_lf_sha256(path) != digest:
            mismatched.append(name)
    if mismatched:
        raise CorpusHashMismatch(
            f"hash non coincidenti con il manifest: {mismatched}"
        )


def _read_overlay() -> Mapping[str, Any]:
    """L'overlay di integrita', o un errore che dice cosa manca.

    Il path e' quello del contratto e non uno derivato dalla radice passata a
    `load()`: una copia temporanea del corpus deve verificare contro l'overlay
    del repository, non contro un file che quella copia non ha.
    """
    path = CONTRACT.OVERLAY_PATH
    if not path.is_file():
        raise CorpusSchemaError(
            f"overlay di integrita' assente: {CONTRACT.OVERLAY_RELPATH}. "
            f"Rigeneralo con benchmarks.mtb_evidence.evaluation.scripts."
            f"build_corpus_integrity_overlay"
        )
    overlay = json.loads(path.read_text(encoding="utf-8"))
    if overlay.get("hash_policy_version") != POLICY.POLICY_VERSION:
        raise CorpusSchemaError(
            f"overlay scritto sotto {overlay.get('hash_policy_version')!r}, "
            f"questo loader verifica sotto {POLICY.POLICY_VERSION!r}"
        )
    if overlay.get("normalization") != POLICY.NORMALIZATION:
        raise CorpusSchemaError(
            f"overlay normalizzato a {overlay.get('normalization')!r}, "
            f"atteso {POLICY.NORMALIZATION!r}"
        )
    return overlay


def _verify_source_artifacts(manifest: Mapping[str, Any]) -> None:
    """I sorgenti della promozione, verificati nella forma canonica LF.

    Il manifest dichiara l'impronta di diciotto sorgenti, e quattro di quelle
    impronte furono prese nella forma CRLF: nessun checkout pulito le riproduce.
    Confrontare i sorgenti direttamente con il manifest fallirebbe sempre, e
    riscrivere il manifest significherebbe cancellare cio' che la promozione
    misuro' davvero.

    L'overlay tiene le due cose separate: l'impronta storica resta nel manifest,
    quella canonica sta nell'overlay, e la verifica passa da quest'ultima. Le
    quattro divergenze sono dichiarate una per una con il proprio `reason_code`,
    non assorbite in un confronto piu' debole.
    """
    declared = manifest.get("source_artifact_sha256") or {}
    if not declared:
        raise CorpusSchemaError(
            "il manifest non dichiara nessun hash di artefatto sorgente"
        )
    overlay = _read_overlay()
    entries = overlay.get("source_artifact_sha256") or {}

    uncovered = sorted(set(declared) - set(entries))
    if uncovered:
        raise CorpusSchemaError(
            f"l'overlay non copre etichette che il manifest dichiara: {uncovered}"
        )

    mismatched: list[str] = []
    drifted: list[str] = []
    for label, digest in sorted(declared.items()):
        entry = entries[label]
        # L'overlay deve continuare a descrivere *questo* manifest: se il
        # manifest cambiasse, l'overlay diventerebbe una promessa su un altro.
        if entry["declared_sha256"] != digest:
            drifted.append(label)
            continue
        path = CONTRACT.REPO_ROOT / str(entry["path"])
        if not path.is_file():
            raise PromotedCorpusError(f"sorgente della promozione assente: {path}")
        if POLICY.canonical_lf_sha256(path) != entry["canonical_lf_sha256"]:
            mismatched.append(label)

    if drifted:
        raise CorpusHashMismatch(
            f"l'overlay non descrive questo manifest, etichette: {drifted}"
        )
    if mismatched:
        raise CorpusSourceHashMismatch(
            f"sorgenti della promozione non coincidenti con l'overlay nella "
            f"forma canonica {POLICY.NORMALIZATION}: {mismatched}"
        )


def _check_versions(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != CONTRACT.SCHEMA_VERSION:
        raise CorpusSchemaError(
            f"schema_version {manifest.get('schema_version')!r} non compatibile con "
            f"{CONTRACT.SCHEMA_VERSION!r}"
        )
    if manifest.get("repository_version") != CONTRACT.REPOSITORY_VERSION:
        raise CorpusSchemaError(
            f"repository_version {manifest.get('repository_version')!r} non "
            f"compatibile con {CONTRACT.REPOSITORY_VERSION!r}"
        )
    if manifest.get("model_version") != CONTRACT.MODEL_VERSION:
        raise CorpusSchemaError(
            f"model_version {manifest.get('model_version')!r} non compatibile con "
            f"{CONTRACT.MODEL_VERSION!r}"
        )


def load(
    root: Path = CONTRACT.PROMOTED_CORPUS,
    *,
    policy_mode: str | None = None,
    verify_hashes: bool = True,
    verify_sources: bool = True,
) -> PromotedCorpus:
    """Carica il corpus promosso, o solleva. Non scrive nulla e non ordina nulla."""
    root = Path(root)
    if not root.is_dir():
        raise PromotedCorpusError(f"corpus promosso assente: {root}")

    try:
        mode = CONTRACT.validate_policy_mode(policy_mode)
    except CONTRACT.PromotionContractError as error:
        raise CorpusPolicyModeError(str(error)) from error

    manifest = _read_json(root / CONTRACT.MANIFEST_FILE)
    _check_versions(manifest)
    if verify_hashes:
        _verify_hashes(root, manifest)
    if verify_sources:
        _verify_source_artifacts(manifest)

    claims = _read_jsonl(root / "evidence_claims.jsonl")
    deprecated = _read_jsonl(root / "deprecated_claims.jsonl")
    for record in claims + deprecated:
        try:
            PROP.validate_record(record)
        except PROP.PropagationSchemaError as error:
            raise CorpusSchemaError(str(error)) from error

    corpus = PromotedCorpus(
        root=root,
        manifest=manifest,
        registry_entry=_read_json(root / "corpus_registry_entry.json"),
        policy_mode=mode,
        claims=claims,
        parents=_read_jsonl(root / "graph_evidence_parents.jsonl"),
        deprecated=deprecated,
        lineage=_read_jsonl(root / "claim_replacement_lineage.jsonl"),
        links=_read_jsonl(root / "qualification_links.jsonl"),
        views=_read_jsonl(root / "qualified_evidence_views.jsonl"),
        unsupported=_read_jsonl(root / "unsupported_associations.jsonl"),
        unresolved=_read_jsonl(root / "unresolved_associations.jsonl"),
        terminology_registry=_read_json(root / "terminology_registry.json"),
        disease_relation_registry=_read_json(root / "disease_relation_registry.json"),
        formulation_registry=_read_jsonl(root / "formulation_registry.jsonl"),
    )

    retired = {str(row["claim_id"]) for row in corpus.deprecated}
    active = {str(row["claim_id"]) for row in corpus.claims}
    leaked = sorted(retired & active)
    if leaked:
        raise PromotedCorpusError(
            f"claim ritirati presenti nel lookup primario: {leaked}"
        )
    return corpus


def load_from_registry(
    registry_path: Path = CONTRACT.REGISTRY_PATH,
    *,
    policy_mode: str | None = None,
    verify_hashes: bool = True,
    verify_sources: bool = True,
) -> PromotedCorpus:
    """Carica il corpus che il registro prototipale dichiara attivo.

    Il loader passa dal registro e non da un path costante perche' il registro
    e' cio' che il rollback modifica: dopo un rollback non c'e' nessun corpus
    attivo, e questa funzione lo dice invece di caricare comunque i file rimasti
    sul disco.
    """
    registry_path = Path(registry_path)
    registry = _read_json(registry_path)
    version = registry.get("active_prototype_corpus")
    if version is None:
        raise PromotedCorpusError(
            "il registro prototipale non dichiara nessun corpus attivo"
        )
    entry = (registry.get("entries") or {})[version]
    root = CONTRACT.REPO_ROOT / str(entry["corpus_path"])
    return load(
        root,
        policy_mode=policy_mode,
        verify_hashes=verify_hashes,
        verify_sources=verify_sources,
    )


__all__ = [
    "CorpusHashMismatch",
    "CorpusPolicyModeError",
    "CorpusSchemaError",
    "CorpusSourceHashMismatch",
    "PromotedCorpus",
    "PromotedCorpusError",
    "load",
    "load_from_registry",
]
