"""I tre compiti su cui i modelli vengono confrontati.

Controllo di contaminazione
---------------------------
Nessun prompt contiene claim del gold, PMID attesi, terapie attese, applicabilita'
attesa o decisioni dell'audit. Un modello che vedesse una di queste cose non
verrebbe misurato: verrebbe interrogato.

`assert_no_leakage` verifica ogni prompt costruito prima dell'invio, e i test lo
esercitano sui quattro casi reali.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..evaluation.contracts import ClinicalGoldCase, SourceClinicalProfile

PLANNER = "planner"
VERIFIER = "verifier"
FREE_REPORT = "free_report"

ROLES = (PLANNER, VERIFIER, FREE_REPORT)

# Gli strumenti che il planner puo' nominare. Un'azione fuori da questo insieme non
# e' eseguibile e viene contata come non valida.
KNOWN_TOOLS = (
    "interpret_variant",
    "identify_targets",
    "check_resistance",
    "match_trials",
    "stop",
)


class GoldLeakageError(AssertionError):
    """Un prompt contiene informazione che il modello non deve vedere."""


def case_input_text(case: ClinicalGoldCase) -> str:
    """Il testo che il sistema riceve legittimamente come input del caso.

    Domanda e contesto clinico sono cio' che un clinico scriverebbe: non sono gold.
    Se la domanda nomina un farmaco, quel farmaco e' input, non risposta.
    """
    return " ".join(
        (
            case.question,
            case.case_context,
            case.gene,
            case.variant,
            case.disease,
            case.required_context,
        )
    ).casefold()


# Termini che costituiscono una fuga **sempre**, anche se comparissero nel testo del
# caso: sono etichette del gold e decisioni dell'audit, mai input clinico.
def _always_forbidden(case: ClinicalGoldCase) -> list[str]:
    terms: list[str] = list(case.expected_pmids) + list(case.expected_nct_ids)
    for claim in case.expected_claims:
        terms.extend(
            value
            for value in (
                claim.claim_id,
                claim.pmid,
                claim.nct_id,
                claim.applicability,
                claim.documentary_status,
                claim.rationale,
                claim.prohibited_overclaim,
            )
            if value
        )
    terms.extend(("KEEP", "AMEND", "REPLACE", "REJECT", "expected_applicability"))
    return [term for term in terms if term and len(str(term)) >= 4]


def _conditionally_forbidden(case: ClinicalGoldCase) -> list[str]:
    """Termini che sono fuga solo se non compaiono gia' nell'input del caso."""
    return [term for term in case.expected_therapies if term and len(str(term)) >= 4]


def leakage_overlap(case: ClinicalGoldCase) -> list[str]:
    """Termini attesi che la domanda del caso gia' rivela.

    Non e' un errore ma un limite del caso, e va dichiarato: se la domanda nomina la
    terapia attesa, il recall su quella terapia non misura la capacita' di
    recuperarla. Per C1 la domanda cita esplicitamente osimertinib.
    """
    haystack = case_input_text(case)
    return sorted(
        {
            str(term)
            for term in _conditionally_forbidden(case)
            if str(term).casefold() in haystack
        }
    )


def assert_no_leakage(prompt: str, case: ClinicalGoldCase) -> None:
    """Fallisce se il prompt contiene informazione riservata al gold.

    Distingue due categorie. Etichette, PMID, NCT e decisioni dell'audit sono fuga
    sempre. I nomi delle terapie attese lo sono solo se non compaiono gia' nella
    domanda del caso: quando la domanda li nomina, sono input clinico legittimo, e
    l'effetto sul recall viene registrato come limite tramite `leakage_overlap`.
    """
    haystack = prompt.casefold()
    already_given = case_input_text(case)

    found = [term for term in _always_forbidden(case) if str(term).casefold() in haystack]
    found += [
        term
        for term in _conditionally_forbidden(case)
        if str(term).casefold() in haystack and str(term).casefold() not in already_given
    ]
    if found:
        raise GoldLeakageError(
            f"il prompt per {case.case_id} contiene informazione del gold: "
            f"{sorted(set(map(str, found)))[:8]}"
        )


@dataclass(frozen=True)
class RoleTask:
    """Un compito pronto per essere inviato a un modello."""

    role: str
    case_id: str
    task_id: str
    messages: tuple[Mapping[str, str], ...]
    schema: Mapping[str, Any]
    expectation: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "case_id": self.case_id,
            "task_id": self.task_id,
            "messages": [dict(message) for message in self.messages],
            "schema": dict(self.schema),
        }


# ── Ruolo 1: planner ───────────────────────────────────────────────────────────

PLANNER_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "enum": list(KNOWN_TOOLS)},
                    "reason": {"type": "string"},
                },
                "required": ["tool", "reason"],
            },
        },
        "stop_after_plan": {"type": "boolean"},
    },
    "required": ["plan", "stop_after_plan"],
}

_PLANNER_SYSTEM = (
    "Sei il pianificatore di una pipeline di interrogazione di un knowledge graph "
    "oncologico. Ricevi un caso clinico e devi decidere quali strumenti invocare, "
    "in quale ordine, e quando fermarti.\n\n"
    "Strumenti disponibili:\n"
    "- interpret_variant: interpreta gene e variante sul grafo\n"
    "- identify_targets: individua terapie associate al profilo\n"
    "- check_resistance: cerca evidenze di resistenza\n"
    "- match_trials: cerca trial clinici pertinenti\n"
    "- stop: termina senza ulteriori strumenti\n\n"
    "Invoca solo gli strumenti necessari al caso. Invocare strumenti non pertinenti "
    "e' un errore quanto ometterne di necessari."
)


def planner_task(case: ClinicalGoldCase) -> RoleTask:
    user = (
        f"Caso: {case.case_context}\n"
        f"Domanda: {case.question}\n"
        f"Gene: {case.gene}\n"
        f"Variante: {case.variant}\n"
        f"Malattia: {case.disease}\n"
        f"Contesto richiesto: {case.required_context}\n\n"
        "Restituisci il piano degli strumenti."
    )
    messages = (
        {"role": "system", "content": _PLANNER_SYSTEM},
        {"role": "user", "content": user},
    )
    prompt = "\n".join(message["content"] for message in messages)
    assert_no_leakage(prompt, case)
    return RoleTask(
        role=PLANNER,
        case_id=case.case_id,
        task_id=f"{case.case_id}::planner",
        messages=messages,
        schema=PLANNER_SCHEMA,
        expectation={
            "required_tools": list(case.required_tools),
            "unnecessary_tools": list(case.unnecessary_tools),
            "expected_abstention": case.expected_abstention,
            "category": case.category,
        },
    )


# ── Ruolo 2: source verifier ───────────────────────────────────────────────────

VERIFIER_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "documentary_status": {
            "type": "string",
            "enum": ["supported_as_written", "partially_supported", "not_supported"],
        },
        "applicability": {
            "type": "string",
            "enum": ["compatible", "not_compatible", "indeterminate"],
        },
        "setting": {"type": "string"},
        "therapy_line": {"type": "string"},
        "missing_context": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["documentary_status", "applicability", "setting", "therapy_line",
                 "missing_context", "reason"],
}

_VERIFIER_SYSTEM = (
    "Verifichi se una fonte scientifica sostiene un'affermazione e se e' applicabile "
    "a un caso clinico specifico. Sono due giudizi distinti.\n\n"
    "documentary_status riguarda solo il rapporto fra affermazione e fonte: la fonte "
    "dice questo, si' o no.\n\n"
    "applicability riguarda il rapporto fra la popolazione della fonte e il paziente "
    "del caso. Una fonte puo' essere pienamente valida e non applicabile: e' il caso "
    "di uno studio adiuvante rispetto a un paziente metastatico, o di uno studio "
    "post-progressione rispetto a un paziente mai trattato.\n\n"
    "Se il contesto non basta a decidere, dichiara indeterminate ed elenca cosa manca."
)


def verifier_tasks(
    case: ClinicalGoldCase, profiles: Sequence[SourceClinicalProfile]
) -> list[RoleTask]:
    """Un compito per ogni fonte del caso di cui esista un profilo clinico."""
    tasks: list[RoleTask] = []
    for claim in case.expected_claims:
        profile = next(
            (item for item in profiles if item.pmid and item.pmid == claim.pmid), None
        )
        if profile is None:
            continue
        statement = (
            f"{claim.subject} {claim.relation} {claim.object}"
            if claim.subject and claim.object
            else claim.subject
        )
        user = (
            f"Caso clinico: {case.case_context}\n\n"
            f"Affermazione da verificare: {statement}\n\n"
            "Profilo della fonte:\n"
            f"- titolo: {profile.title}\n"
            f"- popolazione: {profile.population}\n"
            f"- stadio: {profile.stage}\n"
            f"- setting: {profile.setting}\n"
            f"- linea di terapia: {profile.therapy_line}\n"
            f"- terapie precedenti: {', '.join(profile.prior_therapies) or 'nessuna'}\n"
            f"- criteri di inclusione: {profile.inclusion_criteria_summary}\n"
            f"- criteri di esclusione: {profile.exclusion_criteria_summary}\n\n"
            "Valuta stato documentale e applicabilita' al caso."
        )
        messages = (
            {"role": "system", "content": _VERIFIER_SYSTEM},
            {"role": "user", "content": user},
        )
        # Il PMID della claim compare legittimamente come identificatore della fonte
        # da valutare, ma l'etichetta attesa non deve mai entrare nel prompt.
        prompt = "\n".join(message["content"] for message in messages)
        for forbidden in (claim.applicability, claim.documentary_status, claim.rationale):
            if forbidden and forbidden.casefold() in prompt.casefold():
                raise GoldLeakageError(
                    f"il prompt del verifier per {claim.claim_id} contiene l'etichetta attesa"
                )
        tasks.append(
            RoleTask(
                role=VERIFIER,
                case_id=case.case_id,
                task_id=f"{claim.claim_id}::verifier",
                messages=messages,
                schema=VERIFIER_SCHEMA,
                expectation={
                    "claim_id": claim.claim_id,
                    "documentary_status": claim.documentary_status,
                    "applicability": claim.applicability,
                    "setting": profile.setting,
                    "therapy_line": profile.therapy_line,
                },
            )
        )
    return tasks


# ── Ruolo 3: free report ───────────────────────────────────────────────────────

REPORT_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "relation": {"type": "string"},
                    "object": {"type": "string"},
                    "disease": {"type": "string"},
                    "direction": {"type": "string"},
                    "pmid": {"type": "string"},
                    "qualifiers": {"type": "string"},
                },
                "required": ["subject", "relation", "object", "pmid"],
            },
        },
        "abstained": {"type": "boolean"},
        "needs_human_review": {"type": "boolean"},
    },
    "required": ["summary", "claims", "abstained", "needs_human_review"],
}

_REPORT_SYSTEM = (
    "Scrivi un report di evidenza a partire esclusivamente dai record forniti.\n\n"
    "Regole:\n"
    "- non aggiungere fatti che non siano nei record;\n"
    "- cita solo PMID presenti nei record;\n"
    "- conserva popolazione, linea di terapia e setting quando i record li riportano;\n"
    "- se i record non contengono nulla di pertinente, dichiara abstained=true e non "
    "produrre claim;\n"
    "- se il contesto non basta a giudicare l'applicabilita', dichiara "
    "needs_human_review=true."
)


def free_report_task(
    case: ClinicalGoldCase, frozen_records: Sequence[Mapping[str, Any]]
) -> RoleTask:
    """Il compito di reporting libero, sui record congelati del caso.

    I record sono gli stessi per tutti i modelli e per tutti i bracci dell'ablation,
    nello stesso ordine: e' la condizione che rende il confronto sul reporting
    indipendente dalle differenze di retrieval.
    """
    serialized = json.dumps(list(frozen_records), ensure_ascii=False, indent=2)
    user = (
        f"Domanda: {case.question}\n"
        f"Caso: {case.case_context}\n\n"
        f"Record recuperati dal knowledge graph:\n{serialized}\n\n"
        "Scrivi il report."
    )
    messages = (
        {"role": "system", "content": _REPORT_SYSTEM},
        {"role": "user", "content": user},
    )
    # I record possono legittimamente contenere PMID e farmaci che coincidono con
    # quelli attesi: vengono dal grafo, non dal gold. Si verifica solo che non siano
    # entrate le etichette e le decisioni.
    prompt = "\n".join(message["content"] for message in messages)
    for forbidden in (
        "KEEP", "AMEND", "REPLACE", "REJECT", "expected_applicability", "gold_rationale",
    ):
        if forbidden.casefold() in prompt.casefold():
            raise GoldLeakageError(
                f"il prompt del free report per {case.case_id} contiene {forbidden!r}"
            )
    return RoleTask(
        role=FREE_REPORT,
        case_id=case.case_id,
        task_id=f"{case.case_id}::free_report",
        messages=messages,
        schema=REPORT_SCHEMA,
        expectation={
            "expected_abstention": case.expected_abstention,
            "expected_human_review": case.expected_human_review,
        },
    )
