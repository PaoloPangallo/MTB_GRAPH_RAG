"""Repository dei profili clinici delle fonti.

Il source verifier **legge** i profili e non li modifica mai: sono l'annotazione di
riferimento contro cui si misura la sua estrazione. Se potesse riscriverli, si
valuterebbe contro se stesso.

La ricerca e' possibile per PMID, per `source_id` e per NCT: le tre chiavi con cui i
record del grafo e le claim del gold nominano una fonte.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from ..pilot.audit_lib.normalize import norm_nct_set, norm_pmid
from .contracts import FROZEN, SourceClinicalProfile


class ProfileNotFound(KeyError):
    """Nessun profilo corrisponde alla chiave richiesta."""


class SourceClinicalProfileRepository:
    """Accesso in sola lettura ai profili, indicizzato per le tre chiavi utili."""

    def __init__(self, profiles: Iterable[SourceClinicalProfile]) -> None:
        self._profiles: tuple[SourceClinicalProfile, ...] = tuple(profiles)
        self._by_source_id: dict[str, SourceClinicalProfile] = {}
        self._by_pmid: dict[str, SourceClinicalProfile] = {}
        self._by_nct: dict[str, SourceClinicalProfile] = {}
        for profile in self._profiles:
            if profile.source_id:
                self._by_source_id[profile.source_id] = profile
            normalized = norm_pmid(profile.pmid)
            if normalized.valid:
                self._by_pmid[normalized.text] = profile
            for nct in norm_nct_set(profile.nct_ids):
                self._by_nct[nct] = profile

    def __len__(self) -> int:
        return len(self._profiles)

    def __iter__(self) -> Iterator[SourceClinicalProfile]:
        return iter(self._profiles)

    @property
    def profiles(self) -> tuple[SourceClinicalProfile, ...]:
        return self._profiles

    def by_pmid(self, pmid: object) -> SourceClinicalProfile | None:
        normalized = norm_pmid(pmid)
        return self._by_pmid.get(normalized.text) if normalized.valid else None

    def by_source_id(self, source_id: str) -> SourceClinicalProfile | None:
        return self._by_source_id.get(source_id)

    def by_nct(self, nct_id: object) -> SourceClinicalProfile | None:
        candidates = norm_nct_set(nct_id)
        for candidate in candidates:
            found = self._by_nct.get(candidate)
            if found is not None:
                return found
        return None

    def resolve(self, identifier: object) -> SourceClinicalProfile | None:
        """Cerca su tutte le chiavi, nell'ordine piu' specifico prima."""
        text = "" if identifier is None else str(identifier)
        return (
            self.by_source_id(text)
            or self.by_pmid(text)
            or self.by_nct(text)
        )

    def require(self, identifier: object) -> SourceClinicalProfile:
        profile = self.resolve(identifier)
        if profile is None:
            raise ProfileNotFound(
                f"nessun profilo clinico per {identifier!r}. "
                "I profili sono annotazione umana: vanno aggiunti a mano, non generati."
            )
        return profile

    def coverage(self, pmids: Sequence[str]) -> dict[str, bool]:
        return {pmid: self.by_pmid(pmid) is not None for pmid in pmids}

    def frozen_count(self) -> int:
        return sum(1 for profile in self._profiles if profile.review_status == FROZEN)


def load_profiles(path: Path) -> SourceClinicalProfileRepository:
    """Carica i profili da JSONL."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"profili non trovati: {target}")
    profiles = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        profiles.append(
            SourceClinicalProfile(
                source_id=payload["source_id"],
                pmid=payload.get("pmid", ""),
                nct_ids=tuple(payload.get("nct_ids", [])),
                title=payload.get("title", ""),
                disease=payload.get("disease", ""),
                population=payload.get("population", ""),
                stage=payload.get("stage", ""),
                setting=payload.get("setting", ""),
                therapy_line=payload.get("therapy_line", ""),
                prior_therapies=tuple(payload.get("prior_therapies", [])),
                biomarker_requirements=tuple(payload.get("biomarker_requirements", [])),
                regimen=payload.get("regimen", ""),
                interventions=tuple(payload.get("interventions", [])),
                inclusion_criteria_summary=payload.get("inclusion_criteria_summary", ""),
                exclusion_criteria_summary=payload.get("exclusion_criteria_summary", ""),
                source_spans=tuple(payload.get("source_spans", [])),
                extraction_method=payload.get("extraction_method", "human_annotation"),
                extractor_version=payload.get("extractor_version", "human_reviewed_v1"),
                review_status=payload.get("review_status", "human_reviewed"),
                reviewer=payload.get("reviewer", ""),
                confidence=payload.get("confidence", "medium"),
                created_at=payload.get("created_at", ""),
            )
        )
    return SourceClinicalProfileRepository(profiles)


def default_repository() -> SourceClinicalProfileRepository:
    """I profili revisionati distribuiti con il benchmark."""
    from .reviewed_profiles import REVIEWED_PROFILES

    return SourceClinicalProfileRepository(REVIEWED_PROFILES)
