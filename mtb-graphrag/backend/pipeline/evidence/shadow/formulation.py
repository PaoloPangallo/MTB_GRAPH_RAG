"""Contratto fra active moiety, sale e formulazione.

La 1.3 decide le relazioni di forma con una tabella di cinque suffissi. Chi
finisce dentro la tabella diventa `normalized_atomic_intervention`, cioe'
primario e con punteggio strutturale; chi resta fuori diventa `incompatible`,
cioe' respinto come un farmaco senza alcuna relazione. La tabella non e' una
fonte: e' un elenco di stringhe, e il risultato che produce oggi e' invertito
rispetto alle prove disponibili.

    infigratinib hydrochloride -> infigratinib    primary    nessuna fonte
    infigratinib phosphate     -> infigratinib    rejected   EV-BGJ398-06
    alectinib                  -> alectinib hydrochloride    primary    nessuna fonte
    neratinib                  -> neratinib maleate          rejected   nessuna fonte

L'unica coppia per cui esiste una fonte autorevole — il sale del fosfato, con
concept id `ncit:C175088` distinto dalla moiety `rxcui:2550729` — e' quella che
la tabella respinge. Le tre che promuove o respinge non hanno nessuna fonte: la
differenza fra loro e' solo quale suffisso qualcuno ha scritto nella tupla.

Il contratto sostituisce la tabella di stringhe con un registro di relazioni
verificate, e con una regola che non ammette scorciatoie:

    exact soltanto a parita' di moiety **e** di forma

Da qui discende che nessun sale e' exact rispetto alla propria moiety, che due
sali diversi non sono exact fra loro, e che una relazione non registrata non
diventa exact per il fatto di essere plausibile. Un token di forma — quello che
la 1.3 chiamava suffisso — resta utile: dice *che* le due stringhe parlano di
forme diverse. Non dice che siano lo stesso farmaco, e il contratto non lo
lascia concludere.

La conseguenza pratica va detta perche' non sorprenda: dodici claim atomici del
repository portano un intervento in forma salina e nessuno di loro ha una fonte
che lo leghi alla propria moiety. Una query sulla moiety nuda smette quindi di
raggiungerli nel bucket primario e li trova in audit. Non e' una perdita di
copertura decisa qui: e' la copertura che la tabella dei suffissi produceva
senza averne il titolo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

CONTRACT_VERSION = "intervention_formulation_contract/1.0"
REGISTRY_VERSION = "verified_formulation_registry/1.0"

REVIEW_STATUS = "first_review_complete"
REVIEW_INDEPENDENCE = "non_independent"
PROPAGATION_POLICY = "prototype_only"

# --- forme --------------------------------------------------------------------

FORM_BASE = "active_moiety"
FORM_SALT = "salt"
FORM_FORMULATION = "formulation"
FORM_HYDRATION = "hydration_state"
FORM_UNKNOWN = "unknown_form"

FORMS = (FORM_BASE, FORM_SALT, FORM_FORMULATION, FORM_HYDRATION, FORM_UNKNOWN)

# Token che *suggeriscono* una forma. Non provano nulla: servono a riconoscere
# che due stringhe potrebbero parlare di forme diverse, ed e' quel sospetto —
# non una conclusione — che manda la coppia al registro. Se il registro tace, la
# relazione resta irrisolta.
FORM_TOKENS: dict[str, str] = {
    "acetate": FORM_SALT,
    "anhydrous": FORM_HYDRATION,
    "citrate": FORM_SALT,
    "extended release": FORM_FORMULATION,
    "fumarate": FORM_SALT,
    "hcl": FORM_SALT,
    "hydrate": FORM_HYDRATION,
    "hydrochloride": FORM_SALT,
    "liposomal": FORM_FORMULATION,
    "maleate": FORM_SALT,
    "mesylate": FORM_SALT,
    "phosphate": FORM_SALT,
    "potassium": FORM_SALT,
    "sodium": FORM_SALT,
    "succinate": FORM_SALT,
    "sulfate": FORM_SALT,
    "tartrate": FORM_SALT,
    "tosylate": FORM_SALT,
}

# --- relazioni ----------------------------------------------------------------

EXACT_INTERVENTION_FORM = "exact_intervention_form"
NORMALIZED_EXACT_INTERVENTION_FORM = "normalized_exact_intervention_form"
VERIFIED_SAME_ACTIVE_MOIETY_DIFFERENT_FORM = (
    "verified_same_active_moiety_different_form"
)
VERIFIED_SALT_OF_ACTIVE_MOIETY = "verified_salt_of_active_moiety"
VERIFIED_FORMULATION_VARIANT = "verified_formulation_variant"
UNRESOLVED_FORMULATION_RELATION = "unresolved_formulation_relation"
DIFFERENT_INTERVENTION_FORM = "different_intervention_form"
INCOMPATIBLE_ACTIVE_MOIETY = "incompatible_active_moiety"

RELATION_TYPES = (
    EXACT_INTERVENTION_FORM,
    NORMALIZED_EXACT_INTERVENTION_FORM,
    VERIFIED_SAME_ACTIVE_MOIETY_DIFFERENT_FORM,
    VERIFIED_SALT_OF_ACTIVE_MOIETY,
    VERIFIED_FORMULATION_VARIANT,
    UNRESOLVED_FORMULATION_RELATION,
    DIFFERENT_INTERVENTION_FORM,
    INCOMPATIBLE_ACTIVE_MOIETY,
)

# Le sole relazioni che dichiarano identita' di forma. Il bucket primario non
# puo' contenere altro, in nessuna modalita' e con nessun punteggio.
EXACT_FORM_RELATIONS = frozenset(
    {EXACT_INTERVENTION_FORM, NORMALIZED_EXACT_INTERVENTION_FORM}
)

# Relazioni verificate che *non* sono identita'. Il registro sa qualcosa che il
# confronto di stringhe non sa, e cio' che sa e' che le due forme sono diverse.
VERIFIED_DIFFERENT_FORM_RELATIONS = frozenset(
    {
        VERIFIED_SAME_ACTIVE_MOIETY_DIFFERENT_FORM,
        VERIFIED_SALT_OF_ACTIVE_MOIETY,
        VERIFIED_FORMULATION_VARIANT,
        DIFFERENT_INTERVENTION_FORM,
    }
)

# --- stato --------------------------------------------------------------------

STATUS_VERIFIED = "verified"
STATUS_UNRESOLVED = "unresolved"
STATUS_NOT_APPLICABLE = "not_applicable"

# --- bucket -------------------------------------------------------------------

PRIMARY = "primary_ranked_results"
WARNING = "retained_with_warning"
AUDIT = "audit_only_results"
REJECTED = "rejected_by_native_constraints"

# --- codici -------------------------------------------------------------------

INTERVENTION_FORM_EXACT_MATCH = "INTERVENTION_FORM_EXACT_MATCH"
EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION = (
    "EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION"
)
INTERVENTION_FORMULATION_RELATION_UNRESOLVED = (
    "INTERVENTION_FORMULATION_RELATION_UNRESOLVED"
)
ACTIVE_MOIETY_MISMATCH = "ACTIVE_MOIETY_MISMATCH"
FORMULATION_GATE_PRECEDES_SCORING = "FORMULATION_GATE_PRECEDES_SCORING"
SALT_IS_NOT_THE_ACTIVE_MOIETY = "SALT_IS_NOT_THE_ACTIVE_MOIETY"
SUFFIX_NORMALIZATION_NOT_EVIDENCE_OF_IDENTITY = (
    "SUFFIX_NORMALIZATION_NOT_EVIDENCE_OF_IDENTITY"
)


class FormulationContractError(RuntimeError):
    """Il contratto di formulazione e' stato interrogato fuori dalle sue premesse."""


# --- registro -----------------------------------------------------------------


@dataclass(frozen=True)
class FormulationEntry:
    """Una relazione di forma verificata, con la fonte che la sostiene.

    Non esiste una voce senza `authoritative_source`. E' l'unico modo in cui il
    registro non puo' riempirsi di relazioni plausibili: una voce senza fonte
    non e' una relazione debole, e' una relazione che nessuno ha verificato.
    """

    canonical_active_moiety: str
    form_label: str
    form_kind: str
    relation_type: str
    authoritative_source: str
    evidence_id: str
    stable_identifier: str
    moiety_identifier: str
    limitation: str

    def __post_init__(self) -> None:
        if not self.authoritative_source or not self.evidence_id:
            raise FormulationContractError(
                f"{self.form_label}: voce di registro senza fonte autorevole"
            )
        if self.relation_type not in VERIFIED_DIFFERENT_FORM_RELATIONS:
            raise FormulationContractError(
                f"{self.form_label}: il registro non puo' dichiarare "
                f"{self.relation_type!r}, che non e' una relazione di forma verificata"
            )


# Il registro contiene esattamente le relazioni per cui una fonte esiste dentro
# gli artefatti congelati. Oggi ne esiste una sola, e questo e' il fatto
# rilevante: la tabella dei suffissi ne trattava cinque come note.
VERIFIED_FORMULATION_REGISTRY: tuple[FormulationEntry, ...] = (
    FormulationEntry(
        canonical_active_moiety="infigratinib",
        form_label="infigratinib phosphate",
        form_kind=FORM_SALT,
        relation_type=VERIFIED_SALT_OF_ACTIVE_MOIETY,
        authoritative_source="DGIdb su NCIt e RxNorm",
        evidence_id="EV-BGJ398-06",
        stable_identifier="ncit:C175088",
        moiety_identifier="rxcui:2550729",
        limitation=(
            "Il sale ha concept id proprio, distinto dalla moiety: la relazione "
            "di formulazione richiede un qualificatore e non un merge."
        ),
    ),
)


def normalize(label: Any) -> str:
    return " ".join(str(label or "").split()).lower()


def _registry_index() -> dict[str, FormulationEntry]:
    return {normalize(entry.form_label): entry for entry in VERIFIED_FORMULATION_REGISTRY}


def form_tokens(label: str) -> tuple[str, ...]:
    """Token di forma presenti nel letterale, come candidati e non come prova.

    Il token viene cercato come parola intera in coda o isolata, non come
    sottostringa: `phosphatermine` non e' un fosfato, e riconoscerlo tale
    sarebbe la stessa inferenza di sottostringa che il contratto vieta.
    """
    text = normalize(label)
    words = text.split()
    found: list[str] = []
    for token in sorted(FORM_TOKENS):
        parts = token.split()
        if len(parts) == 1:
            if parts[0] in words:
                found.append(token)
        elif token in text and text.endswith(token):
            found.append(token)
    return tuple(found)


def form_of(label: str) -> tuple[str, tuple[str, ...]]:
    """Forma dichiarata dal letterale, piu' i token che l'hanno suggerita."""
    tokens = form_tokens(label)
    if not tokens:
        return FORM_BASE, ()
    kinds = {FORM_TOKENS[token] for token in tokens}
    if len(kinds) == 1:
        return next(iter(kinds)), tokens
    return FORM_UNKNOWN, tokens


def candidate_active_moiety(label: str) -> str:
    """Moiety *candidata*, ottenuta togliendo i token di forma.

    Il nome del campo e' deliberato. Il risultato non e' la moiety: e' cio' che
    resterebbe se i token fossero davvero token di forma, ed e' l'input di una
    domanda al registro — mai la risposta. Nessuna decisione di identita' viene
    presa su questo valore.
    """
    text = normalize(label)
    for token in sorted(FORM_TOKENS, key=len, reverse=True):
        if text.endswith(" " + token):
            text = text[: -len(token) - 1]
    return " ".join(text.split())


# --- politica per relazione ---------------------------------------------------


@dataclass(frozen=True)
class FormulationPolicy:
    bucket: str
    primary_candidate_eligible: bool
    warning_eligible: bool
    audit_only: bool
    rejected_by_native_constraints: bool
    structural_score_eligible: bool
    qualified_score_eligible: bool

    def score_eligibility(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "final_ranking_eligible": self.primary_candidate_eligible,
            "positive_score_forbidden": not (
                self.structural_score_eligible or self.qualified_score_eligible
            ),
            "qualified_score_eligible": self.qualified_score_eligible,
            "ranks_within_bucket_only": self.warning_eligible
            and self.qualified_score_eligible,
            "structural_score_eligible": self.structural_score_eligible,
        }


def _primary() -> FormulationPolicy:
    return FormulationPolicy(
        bucket=PRIMARY,
        primary_candidate_eligible=True,
        warning_eligible=False,
        audit_only=False,
        rejected_by_native_constraints=False,
        structural_score_eligible=True,
        qualified_score_eligible=True,
    )


def _warning() -> FormulationPolicy:
    """Visibile e ordinabile dentro il proprio bucket, mai primario.

    `structural_score_eligible` resta falso perche' il punteggio strutturale e'
    riservato all'identita': concederlo a una forma diversa rimetterebbe in
    gioco, come numero, la distinzione che il gate ha appena fatto.
    """
    return FormulationPolicy(
        bucket=WARNING,
        primary_candidate_eligible=False,
        warning_eligible=True,
        audit_only=False,
        rejected_by_native_constraints=False,
        structural_score_eligible=False,
        qualified_score_eligible=True,
    )


def _audit() -> FormulationPolicy:
    return FormulationPolicy(
        bucket=AUDIT,
        primary_candidate_eligible=False,
        warning_eligible=False,
        audit_only=True,
        rejected_by_native_constraints=False,
        structural_score_eligible=False,
        qualified_score_eligible=False,
    )


def _rejected() -> FormulationPolicy:
    return FormulationPolicy(
        bucket=REJECTED,
        primary_candidate_eligible=False,
        warning_eligible=False,
        audit_only=False,
        rejected_by_native_constraints=True,
        structural_score_eligible=False,
        qualified_score_eligible=False,
    )


POLICY_BY_RELATION: dict[str, FormulationPolicy] = {
    EXACT_INTERVENTION_FORM: _primary(),
    NORMALIZED_EXACT_INTERVENTION_FORM: _primary(),
    VERIFIED_SAME_ACTIVE_MOIETY_DIFFERENT_FORM: _warning(),
    VERIFIED_SALT_OF_ACTIVE_MOIETY: _warning(),
    VERIFIED_FORMULATION_VARIANT: _warning(),
    DIFFERENT_INTERVENTION_FORM: _warning(),
    UNRESOLVED_FORMULATION_RELATION: _audit(),
    INCOMPATIBLE_ACTIVE_MOIETY: _rejected(),
}

REASON_BY_RELATION = {
    EXACT_INTERVENTION_FORM: INTERVENTION_FORM_EXACT_MATCH,
    NORMALIZED_EXACT_INTERVENTION_FORM: INTERVENTION_FORM_EXACT_MATCH,
    VERIFIED_SAME_ACTIVE_MOIETY_DIFFERENT_FORM: EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION,
    VERIFIED_SALT_OF_ACTIVE_MOIETY: SALT_IS_NOT_THE_ACTIVE_MOIETY,
    VERIFIED_FORMULATION_VARIANT: EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION,
    DIFFERENT_INTERVENTION_FORM: EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION,
    UNRESOLVED_FORMULATION_RELATION: INTERVENTION_FORMULATION_RELATION_UNRESOLVED,
    INCOMPATIBLE_ACTIVE_MOIETY: ACTIVE_MOIETY_MISMATCH,
}

WARNING_BY_RELATION = {
    VERIFIED_SAME_ACTIVE_MOIETY_DIFFERENT_FORM: EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION,
    VERIFIED_SALT_OF_ACTIVE_MOIETY: EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION,
    VERIFIED_FORMULATION_VARIANT: EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION,
    DIFFERENT_INTERVENTION_FORM: EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION,
}


# --- risoluzione --------------------------------------------------------------


@dataclass(frozen=True)
class FormulationRelation:
    """Relazione di forma fra il letterale della query e quello del claim."""

    query_literal: str
    claim_literal: str
    canonical_active_moiety: str
    query_form: str
    claim_form: str
    query_form_tokens: tuple[str, ...]
    claim_form_tokens: tuple[str, ...]
    relation_type: str
    relation_status: str
    authoritative_source: str
    stable_identifier: str
    bucket: str
    primary_candidate_eligible: bool
    warning_eligible: bool
    audit_only: bool
    rejected_by_native_constraints: bool
    structural_score_eligible: bool
    qualified_score_eligible: bool
    score_eligibility: dict[str, Any] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION

    @property
    def is_exact_form(self) -> bool:
        return self.relation_type in EXACT_FORM_RELATIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_only": self.audit_only,
            "authoritative_source": self.authoritative_source,
            "bucket": self.bucket,
            "canonical_active_moiety": self.canonical_active_moiety,
            "claim_form": self.claim_form,
            "claim_form_tokens": list(self.claim_form_tokens),
            "claim_literal": self.claim_literal,
            "contract_version": self.contract_version,
            "is_exact_form": self.is_exact_form,
            "primary_candidate_eligible": self.primary_candidate_eligible,
            "provenance": dict(self.provenance),
            "qualified_score_eligible": self.qualified_score_eligible,
            "query_form": self.query_form,
            "query_form_tokens": list(self.query_form_tokens),
            "query_literal": self.query_literal,
            "reason_codes": list(self.reason_codes),
            "rejected_by_native_constraints": self.rejected_by_native_constraints,
            "relation_status": self.relation_status,
            "relation_type": self.relation_type,
            "score_eligibility": dict(self.score_eligibility),
            "stable_identifier": self.stable_identifier,
            "structural_score_eligible": self.structural_score_eligible,
            "warning_codes": list(self.warning_codes),
            "warning_eligible": self.warning_eligible,
        }


def _build(
    *,
    query_literal: str,
    claim_literal: str,
    moiety: str,
    query_form: str,
    claim_form: str,
    query_tokens: tuple[str, ...],
    claim_tokens: tuple[str, ...],
    relation_type: str,
    status: str,
    entry: FormulationEntry | None,
) -> FormulationRelation:
    policy = POLICY_BY_RELATION[relation_type]
    reasons = [REASON_BY_RELATION[relation_type]]
    if relation_type not in EXACT_FORM_RELATIONS:
        reasons.append(FORMULATION_GATE_PRECEDES_SCORING)
    if relation_type == UNRESOLVED_FORMULATION_RELATION:
        reasons.append(SUFFIX_NORMALIZATION_NOT_EVIDENCE_OF_IDENTITY)
    warnings = (
        [WARNING_BY_RELATION[relation_type]]
        if relation_type in WARNING_BY_RELATION
        else []
    )
    return FormulationRelation(
        query_literal=query_literal,
        claim_literal=claim_literal,
        canonical_active_moiety=moiety,
        query_form=query_form,
        claim_form=claim_form,
        query_form_tokens=query_tokens,
        claim_form_tokens=claim_tokens,
        relation_type=relation_type,
        relation_status=status,
        authoritative_source=entry.authoritative_source if entry else "",
        stable_identifier=entry.stable_identifier if entry else "",
        bucket=policy.bucket,
        primary_candidate_eligible=policy.primary_candidate_eligible,
        warning_eligible=policy.warning_eligible,
        audit_only=policy.audit_only,
        rejected_by_native_constraints=policy.rejected_by_native_constraints,
        structural_score_eligible=policy.structural_score_eligible,
        qualified_score_eligible=policy.qualified_score_eligible,
        score_eligibility=policy.score_eligibility(),
        reason_codes=tuple(sorted(set(reasons))),
        warning_codes=tuple(sorted(set(warnings))),
        provenance={
            "contract_version": CONTRACT_VERSION,
            "decided_by_edit_distance": False,
            "decided_by_string_similarity": False,
            "decided_by_suffix_stripping": False,
            "evidence_id": entry.evidence_id if entry else "",
            "limitation": entry.limitation if entry else "",
            "moiety_identifier": entry.moiety_identifier if entry else "",
            "propagation_policy": PROPAGATION_POLICY,
            "registry_version": REGISTRY_VERSION,
            "review_independence": REVIEW_INDEPENDENCE,
            "review_status": REVIEW_STATUS,
        },
    )


def resolve(query_literal: object, claim_literal: object) -> FormulationRelation:
    """Relazione di forma fra due letterali, sul solo registro verificato.

    L'ordine dei rami e' la politica. L'identita' letterale viene prima di tutto;
    poi l'identita' dopo normalizzazione di spazi e maiuscole, che non e' una
    decisione sulla forma ma sulla scrittura; poi il registro; e soltanto alla
    fine l'assenza di relazione, che non e' un fallimento ma un esito.
    """
    query_text = "" if query_literal is None else str(query_literal)
    claim_text = "" if claim_literal is None else str(claim_literal)
    query_norm = normalize(query_text)
    claim_norm = normalize(claim_text)

    query_form, query_tokens = form_of(query_text)
    claim_form, claim_tokens = form_of(claim_text)
    registry = _registry_index()

    common = {
        "query_literal": query_text,
        "claim_literal": claim_text,
        "query_form": query_form,
        "claim_form": claim_form,
        "query_tokens": query_tokens,
        "claim_tokens": claim_tokens,
    }

    if query_text.strip() == claim_text.strip() and query_text.strip():
        return _build(
            moiety=candidate_active_moiety(claim_text),
            relation_type=EXACT_INTERVENTION_FORM,
            status=STATUS_NOT_APPLICABLE,
            entry=None,
            **common,
        )
    if query_norm and query_norm == claim_norm:
        return _build(
            moiety=candidate_active_moiety(claim_text),
            relation_type=NORMALIZED_EXACT_INTERVENTION_FORM,
            status=STATUS_NOT_APPLICABLE,
            entry=None,
            **common,
        )

    query_entry = registry.get(query_norm)
    claim_entry = registry.get(claim_norm)

    # Sale registrato contro la propria moiety, in entrambi i versi.
    if query_entry and normalize(query_entry.canonical_active_moiety) == claim_norm:
        return _build(
            moiety=query_entry.canonical_active_moiety,
            relation_type=query_entry.relation_type,
            status=STATUS_VERIFIED,
            entry=query_entry,
            **common,
        )
    if claim_entry and normalize(claim_entry.canonical_active_moiety) == query_norm:
        return _build(
            moiety=claim_entry.canonical_active_moiety,
            relation_type=claim_entry.relation_type,
            status=STATUS_VERIFIED,
            entry=claim_entry,
            **common,
        )
    # Due forme registrate della stessa moiety: diverse fra loro, e il registro
    # lo dice invece di lasciarlo dedurre.
    if (
        query_entry
        and claim_entry
        and normalize(query_entry.canonical_active_moiety)
        == normalize(claim_entry.canonical_active_moiety)
    ):
        return _build(
            moiety=query_entry.canonical_active_moiety,
            relation_type=DIFFERENT_INTERVENTION_FORM,
            status=STATUS_VERIFIED,
            entry=query_entry,
            **common,
        )

    # Nessuna voce di registro. Se almeno uno dei due letterali porta un token
    # di forma, la relazione e' *irrisolta*: le due stringhe parlano forse della
    # stessa moiety in forme diverse, e nessuna fonte lo conferma. Chiudere qui
    # con `incompatible` nasconderebbe la differenza fra "non correlato" e "non
    # verificato", che e' esattamente cio' che questa fase deve separare.
    if query_tokens or claim_tokens:
        return _build(
            moiety="",
            relation_type=UNRESOLVED_FORMULATION_RELATION,
            status=STATUS_UNRESOLVED,
            entry=None,
            **common,
        )

    return _build(
        moiety="",
        relation_type=INCOMPATIBLE_ACTIVE_MOIETY,
        status=STATUS_NOT_APPLICABLE,
        entry=None,
        **common,
    )


def best_relation(
    query_literals: Iterable[object], claim_literals: Iterable[object]
) -> FormulationRelation:
    """La relazione meno restrittiva fra tutte le coppie possibili.

    Un claim aggregato o un regime hanno piu' letterali, e la query puo' averne
    piu' di uno. Prendere la coppia migliore e' corretto perche' il gate di
    identita' ha gia' deciso *se* il claim sia raggiungibile: questa funzione
    decide soltanto in che forma lo e'.
    """
    order = {
        EXACT_INTERVENTION_FORM: 0,
        NORMALIZED_EXACT_INTERVENTION_FORM: 1,
        VERIFIED_SAME_ACTIVE_MOIETY_DIFFERENT_FORM: 2,
        VERIFIED_SALT_OF_ACTIVE_MOIETY: 3,
        VERIFIED_FORMULATION_VARIANT: 4,
        DIFFERENT_INTERVENTION_FORM: 5,
        UNRESOLVED_FORMULATION_RELATION: 6,
        INCOMPATIBLE_ACTIVE_MOIETY: 7,
    }
    queries = [item for item in query_literals] or [""]
    claims = [item for item in claim_literals] or [""]
    relations = [resolve(query, claim) for query in queries for claim in claims]
    return min(relations, key=lambda relation: order[relation.relation_type])


def relation_definitions() -> dict[str, Any]:
    """Descrizione serializzabile del contratto, per il manifest della fase."""
    return {
        "contract_version": CONTRACT_VERSION,
        "edit_distance_can_produce_exact": False,
        "exact_form_relations": sorted(EXACT_FORM_RELATIONS),
        "exact_rule": (
            "Primary exact soltanto quando la active moiety coincide e la forma "
            "canonica coincide, oppure quando un alias exact gia' verificato "
            "esiste per la stessa forma."
        ),
        "form_kinds": list(FORMS),
        "form_tokens": dict(sorted(FORM_TOKENS.items())),
        "form_tokens_are_candidates_not_proof": True,
        "never_exact": [
            "active moiety contro sale",
            "sale contro active moiety",
            "due sali differenti",
            "due formulazioni differenti",
        ],
        "registry_version": REGISTRY_VERSION,
        "relations": [
            {
                "audit_eligible": POLICY_BY_RELATION[relation].audit_only,
                "bucket": POLICY_BY_RELATION[relation].bucket,
                "is_exact": relation in EXACT_FORM_RELATIONS,
                "primary_eligible": POLICY_BY_RELATION[
                    relation
                ].primary_candidate_eligible,
                "qualified_score_eligible": POLICY_BY_RELATION[
                    relation
                ].qualified_score_eligible,
                "reason_code": REASON_BY_RELATION[relation],
                "relation_type": relation,
                "structural_score_eligible": POLICY_BY_RELATION[
                    relation
                ].structural_score_eligible,
                "warning_code": WARNING_BY_RELATION.get(relation),
                "warning_eligible": POLICY_BY_RELATION[relation].warning_eligible,
            }
            for relation in RELATION_TYPES
        ],
        "substring_can_produce_exact": False,
        "suffix_stripping_can_produce_exact": False,
        "verified_different_form_relations": sorted(VERIFIED_DIFFERENT_FORM_RELATIONS),
    }


def registry_snapshot() -> list[dict[str, Any]]:
    """Il registro, riga per riga, con la fonte di ciascuna voce."""
    return [
        {
            "authoritative_source": entry.authoritative_source,
            "canonical_active_moiety": entry.canonical_active_moiety,
            "evidence_id": entry.evidence_id,
            "form_kind": entry.form_kind,
            "form_label": entry.form_label,
            "limitation": entry.limitation,
            "moiety_identifier": entry.moiety_identifier,
            "registry_version": REGISTRY_VERSION,
            "relation_status": STATUS_VERIFIED,
            "relation_type": entry.relation_type,
            "review_independence": REVIEW_INDEPENDENCE,
            "review_status": REVIEW_STATUS,
            "stable_identifier": entry.stable_identifier,
        }
        for entry in sorted(
            VERIFIED_FORMULATION_REGISTRY, key=lambda item: item.form_label
        )
    ]


__all__ = [
    "ACTIVE_MOIETY_MISMATCH",
    "CONTRACT_VERSION",
    "DIFFERENT_INTERVENTION_FORM",
    "EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION",
    "EXACT_FORM_RELATIONS",
    "EXACT_INTERVENTION_FORM",
    "FORMS",
    "FORM_BASE",
    "FORM_FORMULATION",
    "FORM_SALT",
    "FORM_TOKENS",
    "INCOMPATIBLE_ACTIVE_MOIETY",
    "INTERVENTION_FORMULATION_RELATION_UNRESOLVED",
    "NORMALIZED_EXACT_INTERVENTION_FORM",
    "REGISTRY_VERSION",
    "RELATION_TYPES",
    "STATUS_UNRESOLVED",
    "STATUS_VERIFIED",
    "UNRESOLVED_FORMULATION_RELATION",
    "VERIFIED_DIFFERENT_FORM_RELATIONS",
    "VERIFIED_FORMULATION_REGISTRY",
    "VERIFIED_FORMULATION_VARIANT",
    "VERIFIED_SALT_OF_ACTIVE_MOIETY",
    "VERIFIED_SAME_ACTIVE_MOIETY_DIFFERENT_FORM",
    "FormulationContractError",
    "FormulationEntry",
    "FormulationRelation",
    "best_relation",
    "candidate_active_moiety",
    "form_of",
    "form_tokens",
    "normalize",
    "registry_snapshot",
    "relation_definitions",
    "resolve",
]
