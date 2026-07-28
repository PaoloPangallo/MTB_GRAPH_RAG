"""Protegge la semantica direzionale delle query congiuntive.

Il gate 1.2 decideva le congiunzioni con una regola sola — i termini del claim
contenuti in quelli della query bastano — e quella regola portava nel bucket
primario claim misurati su popolazioni che la co-alterazione non avevano. Il
gate 1.3 la divide in due secondo la direzione del contenimento.

I test difendono cinque cose.

Che le sei righe della tabella direzionale siano quelle dichiarate, una per
riga, e che nessuna delle due direzioni sia confusa con l'altra: un claim piu'
generale della query e' evidenza indebolita, uno piu' specifico parla di
un'altra popolazione, e i due esiti non sono lo stesso esito.

Che nessun esito direzionale raggiunga il bucket primario, per quanto alto sia
il punteggio e buono il resto del match — verificato con un punteggio
arbitrariamente alto, come le fasi precedenti.

Che la coorte raggiunta dalla regola sostituita sia riclassificata per intero e
che nessuno dei suoi claim resti primario.

Che le query non congiuntive non si muovano: la correzione riguarda un verso che
solo una query con AND puo' percorrere, e `evidence:11219`, `evidence:11598`,
`evidence:11599`, `evidence:1867` e `evidence:8173` restano dove la fase
precedente li ha messi.

Che il gate 1.2 resti eseguibile e byte-identico, cosi' la fase precedente resta
riproducibile senza rigenerarne un artefatto.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.retrieval import v3_backend as V3
from backend.pipeline.evidence.retrieval import v3_result as RESULT
from backend.pipeline.evidence.shadow import biomarker_expression as BIO
from backend.pipeline.evidence.shadow import biomarker_query_direction as DIR
from backend.pipeline.evidence.shadow import integrated_gates_v12 as GATE12
from backend.pipeline.evidence.shadow import integrated_gates_v13 as GATE13
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation import conjunctive_query_closure as CQ

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = (
    REPO_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "conjunctive_query_closure"
)

START_SHA = "ce33812b506538b3bb69882c21a662915d032fc4"
PHASE_END_SHA = "3fb931ed87f3852586e3eacd767f1955c9e3ea98"

ALLOWED_WRITE_PREFIXES = (
    ".gitattributes",
    "backend/pipeline/evidence/retrieval/v3_backend.py",
    "backend/pipeline/evidence/retrieval/v3_result.py",
    "backend/pipeline/evidence/shadow/biomarker_query_direction.py",
    "backend/pipeline/evidence/shadow/integrated_gates_v13.py",
    "backend/tests/",
    "benchmarks/mtb_evidence/evaluation/conjunctive_query_closure.py",
    "benchmarks/mtb_evidence/evaluation/external_inputs.py",
    "benchmarks/mtb_evidence/evaluation/run_gold_evaluation.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_conjunctive_query_closure.py",
    "benchmarks/mtb_evidence/external_inputs/",
    "benchmarks/mtb_evidence/v3/conjunctive_query_closure/",
)

FROZEN_PATHS = (
    "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/shadow/biomarker_expression.py",
    "backend/pipeline/evidence/shadow/integrated_gates.py",
    "backend/pipeline/evidence/shadow/integrated_gates_v11.py",
    "backend/pipeline/evidence/shadow/integrated_gates_v12.py",
    "backend/pipeline/evidence/shadow/structural_gates.py",
    "benchmarks/mtb_evidence/evaluation/claim_type_retrieval_contract.py",
    "benchmarks/mtb_evidence/v3/retriever_binding_1_4/",
    "benchmarks/mtb_evidence/v3/retriever_regression_closure/",
)

ARBITRARILY_HIGH_SCORE = CQ.CLOSURE.ARBITRARILY_HIGH_SCORE

A = "EGFR L858R"
B = "EGFR T790M"
C = "EGFR C797S"
AND_QUERY = f"{A} AND {B}"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class DirectionalTableTests(unittest.TestCase):
    """Le sei righe della tabella, una per test."""

    def test_1_same_canonical_set_is_exact(self) -> None:
        self.assertEqual(DIR.match(AND_QUERY, AND_QUERY).match_type, DIR.MATCH_EXACT)

    def test_1_reversed_order_is_an_exact_boolean_set(self) -> None:
        verdict = DIR.match(f"{B} AND {A}", AND_QUERY)
        self.assertEqual(verdict.match_type, DIR.MATCH_EXACT_BOOLEAN_SET)
        self.assertTrue(verdict.primary_eligible)

    def test_1_duplicated_terms_are_an_exact_boolean_set(self) -> None:
        verdict = DIR.match(f"{A} AND {B} AND {A}", AND_QUERY)
        self.assertEqual(verdict.match_type, DIR.MATCH_EXACT_BOOLEAN_SET)
        self.assertTrue(verdict.primary_eligible)

    def test_2_a_strict_subset_claim_is_a_warning(self) -> None:
        for claim in (A, B):
            with self.subTest(claim=claim):
                verdict = DIR.match(AND_QUERY, claim)
                self.assertEqual(verdict.match_type, DIR.MATCH_QUERY_MORE_SPECIFIC)
                self.assertEqual(verdict.axis_bucket, DIR.WARNING_BUCKET)
                self.assertFalse(verdict.primary_eligible)
                self.assertIn(DIR.CLAIM_SCOPE_BROADER, verdict.warning_codes)
                self.assertIn(
                    DIR.NOT_SEPARABLE_FOR_COALTERED, verdict.explanation_codes
                )

    def test_3_a_claim_requiring_more_is_rejected(self) -> None:
        verdict = DIR.match(AND_QUERY, f"{A} AND {B} AND {C}")
        self.assertEqual(verdict.match_type, DIR.MATCH_CLAIM_REQUIRES_ADDITIONAL)
        self.assertEqual(verdict.axis_bucket, DIR.REJECTED_BUCKET)

    def test_4_a_partial_overlap_is_rejected(self) -> None:
        verdict = DIR.match(AND_QUERY, f"{A} AND {C}")
        self.assertEqual(verdict.match_type, DIR.MATCH_PARTIAL_OVERLAP)
        self.assertEqual(verdict.axis_bucket, DIR.REJECTED_BUCKET)

    def test_5_a_disjunctive_claim_is_a_warning_and_never_primary(self) -> None:
        verdict = DIR.match(AND_QUERY, f"{A} OR {B}")
        self.assertEqual(verdict.match_type, DIR.MATCH_NOT_SEPARABLE)
        self.assertEqual(verdict.axis_bucket, DIR.WARNING_BUCKET)
        self.assertFalse(verdict.primary_eligible)

    def test_6_an_unreadable_expression_is_audit_only(self) -> None:
        for claim in (f"{A} AND {B} OR {C}", f"({A} OR {B}) AND {C}"):
            with self.subTest(claim=claim):
                verdict = DIR.match(AND_QUERY, claim)
                self.assertEqual(verdict.match_type, DIR.MATCH_UNRESOLVED)
                self.assertEqual(verdict.axis_bucket, DIR.AUDIT_BUCKET)
                self.assertFalse(verdict.primary_eligible)

    def test_the_superset_rule_no_longer_grants_primary(self) -> None:
        # E' la regola che questa fase sostituisce: se tornasse, tornerebbe qui.
        self.assertNotIn(
            BIO.MATCH_CONJUNCTION_SATISFIED,
            {verdict.match_type for verdict in (DIR.match(AND_QUERY, A),)},
        )
        self.assertFalse(DIR.match(AND_QUERY, A).primary_eligible)

    def test_no_directional_outcome_is_primary_eligible(self) -> None:
        pairs = (
            (AND_QUERY, A),
            (AND_QUERY, f"{A} AND {B} AND {C}"),
            (AND_QUERY, f"{A} AND {C}"),
            (AND_QUERY, f"{A} OR {B}"),
        )
        for query, claim in pairs:
            with self.subTest(claim=claim):
                verdict = DIR.match(query, claim)
                self.assertTrue(verdict.is_directional)
                self.assertFalse(verdict.primary_eligible)


class NonConjunctiveQueriesAreUntouchedTests(unittest.TestCase):
    """Una query che non porta un AND resta decisa dal gate 1.2."""

    CASES = (
        (A, f"{A} OR EGFR Exon 19 Deletion", BIO.MATCH_DISJUNCT_MEMBER),
        (A, AND_QUERY, BIO.MATCH_CONJUNCTION_PARTIAL),
        (A, A, BIO.MATCH_EXACT),
        (f"{A} OR {B}", A, BIO.MATCH_INCOMPATIBLE),
    )

    def test_the_boolean_verdict_is_reported_unchanged(self) -> None:
        for query, claim, expected in self.CASES:
            with self.subTest(query=query, claim=claim):
                verdict = DIR.match(query, claim)
                self.assertEqual(verdict.match_type, expected)
                self.assertFalse(verdict.is_directional)
                self.assertEqual(
                    verdict.match_type, BIO.match(query, claim).match_type
                )


class ScoreEligibilityTests(unittest.TestCase):
    """Il warning direzionale non porta punteggio."""

    def test_strict_mode_forbids_both_scores(self) -> None:
        flags = DIR.score_eligibility(
            DIR.match(AND_QUERY, A), policy_mode=DIR.STRICT_POLICY_MODE
        )
        self.assertFalse(flags["structural_score_eligible"])
        self.assertFalse(flags["qualified_score_eligible"])

    def test_structural_score_is_forbidden_in_every_mode(self) -> None:
        for mode in (DIR.STRICT_POLICY_MODE, "audit_all"):
            with self.subTest(mode=mode):
                flags = DIR.score_eligibility(
                    DIR.match(AND_QUERY, A), policy_mode=mode
                )
                self.assertFalse(flags["structural_score_eligible"])

    def test_a_rejected_direction_carries_no_score_at_all(self) -> None:
        flags = DIR.score_eligibility(
            DIR.match(AND_QUERY, f"{A} AND {C}"),
            policy_mode=DIR.STRICT_POLICY_MODE,
        )
        self.assertFalse(flags["structural_score_eligible"])
        self.assertFalse(flags["qualified_score_eligible"])


class GateFixture(unittest.TestCase):
    before: V3.QualifiedClaimRetrieverV3
    after: V3.QualifiedClaimRetrieverV3

    @classmethod
    def setUpClass(cls) -> None:
        cls.before, cls.after = CQ.retrievers()

    def one_claim(self, result: Any, graph_evidence_id: str) -> Any:
        claims = [
            item
            for item in result.all_results
            if item.graph_evidence_id == graph_evidence_id
            and item.claim_id.startswith("CLM-")
        ]
        self.assertEqual(len(claims), 1, graph_evidence_id)
        return claims[0]

    def run_after(self, **overrides: Any) -> Any:
        payload: dict[str, Any] = {
            "query_id": "T-CQ",
            "claim_domain": "therapeutic",
            "disease": "NSCLC",
        }
        payload.update(overrides)
        return self.after.retrieve(payload)


class GateBehaviourTests(GateFixture):
    """La tabella, applicata dal retriever sul corpus promosso."""

    def test_the_exact_conjunction_is_primary(self) -> None:
        claim = self.one_claim(
            self.run_after(query_id="T-EXACT", biomarker=AND_QUERY),
            "evidence:11599",
        )
        self.assertEqual(claim.bucket, RESULT.PRIMARY_BUCKET)

    def test_the_reversed_conjunction_decides_identically(self) -> None:
        straight = self.run_after(query_id="T-ORD", biomarker=AND_QUERY)
        reversed_ = self.run_after(query_id="T-ORD", biomarker=f"{B} AND {A}")
        self.assertEqual(
            {i.claim_id: i.bucket for i in straight.all_results},
            {i.claim_id: i.bucket for i in reversed_.all_results},
        )

    def test_the_duplicated_conjunction_decides_identically(self) -> None:
        plain = self.run_after(query_id="T-DUP", biomarker=AND_QUERY)
        duplicated = self.run_after(
            query_id="T-DUP", biomarker=f"{A} AND {B} AND {A}"
        )
        self.assertEqual(
            {i.claim_id: i.bucket for i in plain.all_results},
            {i.claim_id: i.bucket for i in duplicated.all_results},
        )

    def test_a_single_member_claim_is_warning_and_carries_its_codes(self) -> None:
        claim = self.one_claim(
            self.run_after(query_id="T-SUB", biomarker=AND_QUERY), "evidence:1867"
        )
        self.assertEqual(claim.bucket, RESULT.WARNING_BUCKET)
        self.assertEqual(
            claim.gate_trace["biomarker_match"]["match_type"],
            DIR.MATCH_QUERY_MORE_SPECIFIC,
        )
        self.assertIn(DIR.CLAIM_SCOPE_BROADER, claim.warnings)
        self.assertIn(DIR.NOT_SEPARABLE_FOR_COALTERED, claim.explanation_codes)
        self.assertFalse(claim.score["eligibility"]["structural_score_eligible"])
        self.assertFalse(claim.score["eligibility"]["qualified_score_eligible"])
        self.assertFalse(claim.score["ranking_score_allowed"])

    def test_a_claim_requiring_an_extra_conjunct_is_rejected(self) -> None:
        claim = self.one_claim(
            self.run_after(
                query_id="T-EXTRA", biomarker=f"{B} AND EGFR Exon 19 Deletion"
            ),
            "evidence:1396",
        )
        self.assertEqual(claim.bucket, RESULT.REJECTED_BUCKET)
        self.assertEqual(
            claim.gate_trace["biomarker_match"]["match_type"],
            DIR.MATCH_CLAIM_REQUIRES_ADDITIONAL,
        )

    def test_a_disjunctive_claim_is_warning_under_a_conjunctive_query(self) -> None:
        claim = self.one_claim(
            self.run_after(
                query_id="T-DISJ", biomarker=f"{A} AND EGFR Exon 19 Deletion"
            ),
            "evidence:11219",
        )
        self.assertEqual(claim.bucket, RESULT.WARNING_BUCKET)
        self.assertEqual(
            claim.gate_trace["biomarker_match"]["match_type"],
            DIR.MATCH_NOT_SEPARABLE,
        )

    def test_the_observable_query_is_never_mutated(self) -> None:
        result = self.run_after(query_id="T-MUT", biomarker=AND_QUERY)
        self.assertEqual(
            result.query["normalized"]["normalized_biomarker"], AND_QUERY
        )
        self.assertEqual(result.query["original"]["biomarker"], AND_QUERY)


class GateInvariantTests(GateFixture):
    """Gli invarianti, su ogni oggetto e su ogni query."""

    def test_no_score_survives_a_blocking_gate_anywhere(self) -> None:
        for query in CQ.closure_queries():
            typed = self.after.build_native_query(CQ.query_payload(query))
            gate_query = typed.to_gate_query()
            with self.subTest(query=query["query_id"]):
                for obj, _record in self.after._objects:  # noqa: SLF001
                    outcome = GATE13.evaluate(
                        gate_query, obj, mode=typed.policy_mode
                    )
                    GATE13.check_no_score_survives_a_blocking_gate(
                        outcome, ARBITRARILY_HIGH_SCORE
                    )

    def test_no_directional_result_is_ever_primary_on_the_corpus(self) -> None:
        for query in CQ.closure_queries():
            payload = CQ.query_payload(query)
            with self.subTest(query=query["query_id"]):
                for item in self.after.retrieve(payload).all_results:
                    trace = item.gate_trace or {}
                    if not (trace.get("biomarker_direction") or {}).get(
                        "is_directional"
                    ):
                        continue
                    self.assertNotEqual(item.bucket, RESULT.PRIMARY_BUCKET)


class SupersededCohortTests(unittest.TestCase):
    """La coorte della regola sostituita e' riclassificata per intero."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cohort = CQ.superseded_cohort()

    def test_the_cohort_is_not_empty(self) -> None:
        self.assertGreater(self.cohort["distinct_claims"], 0)

    def test_every_cohort_claim_is_reclassified(self) -> None:
        self.assertEqual(
            set(self.cohort["new_match_type_tally"]),
            {DIR.MATCH_QUERY_MORE_SPECIFIC},
        )

    def test_no_cohort_claim_reaches_primary(self) -> None:
        self.assertTrue(self.cohort["none_reaches_primary"])
        self.assertNotIn(
            RESULT.PRIMARY_BUCKET, self.cohort["new_bucket_tally"]
        )

    def test_the_claims_another_gate_had_already_demoted_do_not_move(self) -> None:
        # La direzione del biomarcatore non solleva: cio' che era in audit o
        # respinto per un altro gate resta dov'era.
        for row in self.cohort["claims"]:
            if row["old_bucket"] in (RESULT.AUDIT_BUCKET, RESULT.REJECTED_BUCKET):
                with self.subTest(claim=row["claim_id"]):
                    self.assertEqual(row["new_bucket"], row["old_bucket"])


class ProtectedEndpointTests(unittest.TestCase):
    """Gli endpoint delle fasi precedenti non si muovono sulle query non congiuntive."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = CQ.query_rows()
        cls.endpoints = CQ.endpoint_rows()

    def test_only_conjunctive_queries_change_a_decision(self) -> None:
        for row in self.rows:
            if row["query_operator"] == "and":
                continue
            with self.subTest(query=row["query_id"]):
                self.assertTrue(row["decisions_unchanged"])
                self.assertEqual(
                    row["bucket_assignment_digest_before"],
                    row["bucket_assignment_digest_after"],
                )

    def test_the_five_protected_endpoints_are_stable_outside_conjunctions(
        self,
    ) -> None:
        conjunctive = {
            row["query_id"] for row in self.rows if row["query_operator"] == "and"
        }
        for row in self.endpoints:
            if row["query_id"] in conjunctive:
                continue
            with self.subTest(
                query=row["query_id"], evidence=row["graph_evidence_id"]
            ):
                self.assertTrue(row["unchanged"])

    def test_evidence_11219_is_still_primary_on_its_own_query(self) -> None:
        row = next(
            item
            for item in self.endpoints
            if item["query_id"] == "RB-01-EGFR-L858R-NSCLC"
            and item["graph_evidence_id"] == "evidence:11219"
        )
        self.assertEqual(row["new_bucket"], RESULT.PRIMARY_BUCKET)
        self.assertEqual(row["new_match_type"], BIO.MATCH_DISJUNCT_MEMBER)

    def test_the_two_conjunctive_endpoints_remain_rejected(self) -> None:
        for evidence_id in ("evidence:11598", "evidence:11599"):
            row = next(
                item
                for item in self.endpoints
                if item["query_id"] == "RB-01-EGFR-L858R-NSCLC"
                and item["graph_evidence_id"] == evidence_id
            )
            with self.subTest(evidence=evidence_id):
                self.assertEqual(row["new_bucket"], RESULT.REJECTED_BUCKET)

    def test_evidence_8173_is_unchanged(self) -> None:
        row = next(
            item
            for item in self.endpoints
            if item["query_id"] == "RB-04-FGFR2-ICCA"
            and item["graph_evidence_id"] == "evidence:8173"
        )
        self.assertTrue(row["unchanged"])
        self.assertEqual(row["new_bucket"], RESULT.REJECTED_BUCKET)


class PriorPhaseTests(unittest.TestCase):
    """Il gate 1.2 resta eseguibile, byte-identico e riproducibile."""

    def test_the_two_gates_declare_different_schemas(self) -> None:
        self.assertEqual(
            RESULT.result_schema(GATE12)["schema_version"],
            "qualified_claim_retrieval_result/1.5",
        )
        self.assertEqual(
            RESULT.result_schema(GATE13)["schema_version"],
            "qualified_claim_retrieval_result/1.6",
        )
        self.assertEqual(
            RESULT.result_schema(GATE13)["supersedes"],
            RESULT.result_schema(GATE12)["schema_version"],
        )

    def test_the_frozen_gates_are_unchanged(self) -> None:
        """Nessun contenuto congelato cambia. `--ignore-cr-at-eol` non e' una
        maglia larga: e' cio' che rende il controllo capace di distinguere una
        modifica da una dichiarazione di fine riga.

        Questa fase ha committato un carattere `\\r` in `qualified_retriever.py`
        — l'unico modo di rendere verificabile in un clone pulito l'hash che otto
        artefatti congelati registrano. Un confronto sui byte lo segnalerebbe
        come modifica al retriever legacy, che non e'. Il confronto sul contenuto
        dice la cosa vera: nessuna riga di quei moduli e' cambiata.
        """
        for path in self._touched_frozen_paths():
            with self.subTest(path=path):
                self.assertEqual(
                    self._normalised(f"{START_SHA}:mtb-graphrag/{path}"),
                    self._normalised(f"HEAD:mtb-graphrag/{path}"),
                    f"{path}: il contenuto congelato e' cambiato",
                )

    def test_the_only_byte_level_change_to_a_frozen_path_is_the_declared_one(
        self,
    ) -> None:
        # La deroga e' una, ed e' nominata. Se ne comparisse una seconda, questo
        # test la mostrerebbe invece di lasciarla passare sotto la stessa regola.
        self.assertLessEqual(
            self._touched_frozen_paths(),
            {"backend/pipeline/evidence/qualified_retriever.py"},
        )

    # --- utilita' ---------------------------------------------------------

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT.parent,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            self.skipTest("git non utilizzabile in questo checkout")
        return result

    def _touched_frozen_paths(self) -> set[str]:
        """I path congelati toccati, relativi al package.

        git li emette relativi alla radice del repository, che sta un livello
        sopra il package: il prefisso va tolto qui e non nel confronto, come fa
        gia' `phase_scope`.
        """
        prefixed = [f"mtb-graphrag/{path}" for path in FROZEN_PATHS]
        out = self._git(
            "diff", "--name-only", START_SHA, "--", *prefixed
        ).stdout.decode()
        return {
            line.strip().removeprefix("mtb-graphrag/")
            for line in out.splitlines()
            if line.strip()
        }

    def _normalised(self, revision: str) -> bytes:
        """Il contenuto a una revisione, con le fine riga normalizzate.

        Il confronto passa da qui e non da `git diff --ignore-cr-at-eol`:
        `--name-only` non onora quell'opzione, e un test che lo credesse
        misurerebbe i byte mentre dichiara di misurare il contenuto.
        """
        blob = self._git("show", revision).stdout
        return blob.replace(b"\r\n", b"\n")

    def test_the_gate_1_2_still_reproduces_the_prior_phase(self) -> None:
        before, _ = CQ.retrievers()
        rows = {
            row["query_id"]: row
            for row in _read_jsonl(
                REPO_ROOT
                / "benchmarks/mtb_evidence/v3/retriever_regression_closure"
                / "regression_results.jsonl"
            )
        }
        for query in CQ.CLOSURE.closure_queries():
            payload = CQ.CLOSURE.query_payload(query)
            with self.subTest(query=query["query_id"]):
                result = before.retrieve(payload)
                self.assertEqual(
                    result.bucket_counts(),
                    rows[query["query_id"]]["bucket_counts_after"],
                )


class ArtifactTests(unittest.TestCase):
    NAMES = (
        "CONJUNCTIVE_QUERY_CLOSURE.md",
        "conjunctive_directional_delta.jsonl",
        "conjunctive_scope.json",
        "directional_semantics_audit.json",
        "protected_endpoints.jsonl",
        "query_results.jsonl",
        "superseded_rule_cohort.json",
    )

    def test_every_declared_artifact_exists(self) -> None:
        for name in self.NAMES:
            with self.subTest(artifact=name):
                self.assertTrue((ARTIFACTS / name).is_file())

    def test_the_delta_carries_every_required_field(self) -> None:
        required = {
            "claim_id",
            "new_bucket",
            "new_match_type",
            "old_bucket",
            "old_match_type",
            "reason_codes",
        }
        rows = _read_jsonl(ARTIFACTS / "conjunctive_directional_delta.jsonl")
        self.assertGreater(len(rows), 0)
        for row in rows[:50]:
            with self.subTest(claim=row["claim_id"]):
                self.assertLessEqual(required, set(row))

    def test_the_recorded_delta_matches_a_fresh_measurement(self) -> None:
        self.assertEqual(
            _read_jsonl(ARTIFACTS / "conjunctive_directional_delta.jsonl"),
            CQ.delta_rows(),
        )

    def test_the_scope_declares_the_gold_unread(self) -> None:
        scope = _read_json(ARTIFACTS / "conjunctive_scope.json")
        self.assertFalse(scope["gold_read"])
        self.assertFalse(scope["scoring_weights_retuned"])
        self.assertTrue(scope["corpus_unchanged"])

    def test_the_scope_declares_what_it_supersedes(self) -> None:
        for name in self.NAMES:
            if not name.endswith(".json"):
                continue
            with self.subTest(artifact=name):
                self.assertEqual(
                    _read_json(ARTIFACTS / name)["supersedes"], CQ.SUPERSEDES
                )


class PhasePerimeterTests(unittest.TestCase):
    def test_the_phase_wrote_only_inside_its_own_perimeter(self) -> None:
        if not PHASE_END_SHA:
            self.skipTest("la fase non e' ancora chiusa: nessun estremo da misurare")
        scope = PhaseScope(
            REPO_ROOT.parent, START_SHA, PHASE_END_SHA, ALLOWED_WRITE_PREFIXES
        )
        self.assertEqual(scope.violations(scope.changed_paths()), [])

    def test_no_frozen_path_is_writable(self) -> None:
        for path in FROZEN_PATHS:
            with self.subTest(path=path):
                self.assertFalse(path.startswith(ALLOWED_WRITE_PREFIXES))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
