"""Soglie di ammissibilita' e punteggi per ruolo.

Due passaggi distinti, in quest'ordine. Prima le **soglie**: un modello che non
produce output validi, o che inventa citazioni, o che non sa astenersi, e' escluso a
prescindere da quanto sia bravo altrove. Poi la **classifica** fra i soli ammessi.

Ordinare prima e filtrare dopo permetterebbe a un modello con ottime medie e un
difetto disqualificante di vincere. Ordinare per una sola metrica aggregata avrebbe
lo stesso effetto in modo meno visibile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

ROLE_PLANNER = "planner"
ROLE_VERIFIER = "verifier"
ROLE_REPORT = "free_report"

STATUS_QUALIFIED = "qualified"
STATUS_REJECTED = "rejected"
STATUS_NO_MODEL_QUALIFIED = "no_model_qualified"

# Soglie di ammissibilita'. Non vengono abbassate automaticamente: se nessun modello
# le supera, l'esito e' "no_model_qualified" e la decisione torna a un umano.
ADMISSIBILITY_THRESHOLDS: Mapping[str, Mapping[str, float]] = {
    ROLE_PLANNER: {"valid_action_rate": 0.95},
    ROLE_VERIFIER: {"valid_output_rate": 0.95},
    ROLE_REPORT: {"valid_output_rate": 0.95, "citation_accuracy": 0.95},
}

# Requisiti qualitativi che non sono semplici soglie numeriche.
STRUCTURAL_REQUIREMENTS = (
    "nessuna fuga del gold nei prompt",
    "nessuna omissione sistematica dei qualificatori nei casi C1 e A2",
    "astensione corretta su N1 in almeno 2 run su 3",
)

# Pesi delle classifiche. Le penalita' sono sottratte, non usate come filtro:
# un difetto moderato deve pesare, non annullare.
PLANNER_WEIGHTS: Mapping[str, float] = {
    "task_completion": 0.30,
    "conditional_step_accuracy": 0.25,
    "required_tool_recall": 0.20,
    "stop_condition_accuracy": 0.15,
    "run_to_run_agreement": 0.10,
}
PLANNER_PENALTIES: Mapping[str, float] = {
    "unnecessary_tool_rate": 0.15,
    "planner_failure_rate": 0.20,
}

VERIFIER_WEIGHTS: Mapping[str, float] = {
    "documentary_status_accuracy": 0.30,
    "applicability_status_accuracy": 0.30,
    "qualifier_extraction_accuracy": 0.20,
    "missing_context_detection": 0.10,
    "run_to_run_agreement": 0.10,
}
VERIFIER_PENALTIES: Mapping[str, float] = {"compatible_overstatement_rate": 0.25}

REPORT_WEIGHTS: Mapping[str, float] = {
    "claim_precision": 0.25,
    "claim_recall": 0.20,
    "citation_accuracy": 0.20,
    "qualifier_preservation": 0.20,
    "abstention_accuracy": 0.10,
    "run_to_run_agreement": 0.05,
}
REPORT_PENALTIES: Mapping[str, float] = {
    "unsupported_claim_rate": 0.25,
    "context_omission_rate": 0.15,
}

ROLE_FORMULAS = {
    ROLE_PLANNER: (PLANNER_WEIGHTS, PLANNER_PENALTIES),
    ROLE_VERIFIER: (VERIFIER_WEIGHTS, VERIFIER_PENALTIES),
    ROLE_REPORT: (REPORT_WEIGHTS, REPORT_PENALTIES),
}

# Un modello unico e' ammesso solo se resta entro questa distanza dal migliore di
# ogni ruolo: la semplicita' di deployment non vale una perdita arbitraria.
SINGLE_MODEL_TOLERANCE = 0.05


@dataclass(frozen=True)
class AdmissibilityCheck:
    model: str
    role: str
    passed: bool
    failures: tuple[str, ...] = ()
    missing_metrics: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "role": self.role,
            "passed": self.passed,
            "failures": list(self.failures),
            "missing_metrics": list(self.missing_metrics),
        }


def check_admissibility(
    model: str,
    role: str,
    metrics: Mapping[str, float | None],
    *,
    structural_failures: Sequence[str] = (),
) -> AdmissibilityCheck:
    """Verifica le soglie. Una metrica mancante e' un fallimento, non un passaggio.

    Trattare l'assenza come successo premierebbe un modello che non e' stato
    misurato rispetto a uno misurato e imperfetto.
    """
    thresholds = ADMISSIBILITY_THRESHOLDS.get(role, {})
    failures: list[str] = list(structural_failures)
    missing: list[str] = []
    for name, minimum in thresholds.items():
        value = metrics.get(name)
        if value is None:
            missing.append(name)
            failures.append(f"{name} non misurata")
            continue
        if value < minimum:
            failures.append(f"{name}={value:.3f} sotto la soglia {minimum}")
    return AdmissibilityCheck(
        model=model,
        role=role,
        passed=not failures,
        failures=tuple(failures),
        missing_metrics=tuple(missing),
    )


@dataclass(frozen=True)
class RoleScore:
    model: str
    role: str
    score: float
    components: Mapping[str, float] = field(default_factory=dict)
    penalties: Mapping[str, float] = field(default_factory=dict)
    admissible: bool = True
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "role": self.role,
            "score": round(self.score, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "penalties": {k: round(v, 4) for k, v in self.penalties.items()},
            "admissible": self.admissible,
            "notes": list(self.notes),
        }


def score_role(
    model: str,
    role: str,
    metrics: Mapping[str, float | None],
    *,
    admissible: bool = True,
) -> RoleScore:
    """Punteggio pesato del ruolo, con i contributi visibili.

    Le metriche non misurate contribuiscono 0 e vengono annotate: un punteggio alto
    ottenuto perche' meta' delle metriche mancano deve essere riconoscibile.
    """
    weights, penalty_weights = ROLE_FORMULAS[role]
    components: dict[str, float] = {}
    notes: list[str] = []
    total = 0.0
    for name, weight in weights.items():
        value = metrics.get(name)
        if value is None:
            notes.append(f"{name} non misurata: contributo 0")
            components[name] = 0.0
            continue
        contribution = weight * float(value)
        components[name] = contribution
        total += contribution

    penalties: dict[str, float] = {}
    for name, weight in penalty_weights.items():
        value = metrics.get(name)
        if value is None:
            continue
        deduction = weight * float(value)
        penalties[name] = deduction
        total -= deduction

    return RoleScore(
        model=model,
        role=role,
        score=max(total, 0.0),
        components=components,
        penalties=penalties,
        admissible=admissible,
        notes=tuple(notes),
    )


def rank(scores: Sequence[RoleScore]) -> list[RoleScore]:
    """Classifica decrescente fra i soli ammessi, con ordine stabile a parita'."""
    admissible = [score for score in scores if score.admissible]
    return sorted(admissible, key=lambda item: (-item.score, item.model))


def select_single_model(
    by_role: Mapping[str, Sequence[RoleScore]],
    *,
    tolerance: float = SINGLE_MODEL_TOLERANCE,
) -> tuple[str | None, str]:
    """Un solo modello per tutti i ruoli, se la perdita resta entro la tolleranza."""
    ranked = {role: rank(scores) for role, scores in by_role.items()}
    if not all(ranked.values()):
        return None, "almeno un ruolo non ha modelli ammissibili"

    best_per_role = {role: items[0] for role, items in ranked.items()}
    candidates = set.intersection(
        *[{item.model for item in items} for items in ranked.values()]
    )
    if not candidates:
        return None, "nessun modello e' ammissibile in tutti i ruoli"

    viable: list[tuple[float, str]] = []
    for model in sorted(candidates):
        losses = []
        for role, items in ranked.items():
            best = best_per_role[role].score
            mine = next(item.score for item in items if item.model == model)
            losses.append(best - mine if best > 0 else 0.0)
        worst_loss = max(losses)
        if worst_loss <= tolerance:
            viable.append((worst_loss, model))
    if not viable:
        return None, (
            f"nessun modello resta entro il {tolerance:.0%} del migliore in ogni ruolo"
        )
    viable.sort()
    loss, model = viable[0]
    return model, f"perdita massima {loss:.3f} rispetto al migliore di ogni ruolo"


def selection_status(by_role: Mapping[str, Sequence[RoleScore]]) -> str:
    if any(rank(scores) for scores in by_role.values()):
        return STATUS_QUALIFIED
    return STATUS_NO_MODEL_QUALIFIED
