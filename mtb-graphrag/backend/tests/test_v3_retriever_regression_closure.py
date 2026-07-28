"""Protegge la chiusura delle regressioni del retriever V3.

I test difendono sei cose, e ognuna e' un modo di sbagliare che la correzione
dell'asse booleano rende possibile per la prima volta.

Che l'identita' di un'espressione sia l'insieme dei suoi termini. Ordine
invertito e termini duplicati non cambiano la domanda, per OR e per AND, e la
compatibilita' dichiarata dev'essere anche quella esercitata: dire che `A AND B`
e `B AND A` sono la stessa cosa e poi lasciare che il gate a valle respinga la
seconda sull'ordine delle parole sarebbe una dichiarazione senza effetto.

Che OR non diventi AND e AND non si rilassi a OR. Un disgiunto soddisfatto
raggiunge il claim; una congiunzione soddisfatta a meta' no. Sono i due errori
simmetrici, e nessuno dei due e' impedito dall'altro.

Che i segnaposto non diventino wildcard. `FGFR2::v Fusion` e `FGFR2::? Fusion`
sono i modi in cui la fonte dice "partner non identificato": farli corrispondere
a `FGFR2::BICC1 Fusion` affermerebbe cio' da cui la fonte si e' astenuta.

Che il bucket finale non cancelli i bucket dei singoli gate. Su `evidence:8173`
la relazione di malattia e' `disease_sibling`, il suo bucket locale e' audit, il
biomarcatore e' incompatibile e l'esito e' respinto: tutte e quattro le cose
devono restare leggibili insieme, e il gate dominante dev'essere nominato.

Che la query osservabile non muti. La sostituzione interna dell'espressione
serve a interrogare il gate 1.1 sulla domanda giusta, non a riscrivere la
domanda posta.

Che la fase precedente resti riproducibile. Un retriever costruito con il gate
1.1 ricalcola i quattordici digest della fase 1.4 byte per byte, e la directory
di quella fase non e' stata toccata.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.retrieval import v3_backend as V3
from backend.pipeline.evidence.retrieval import v3_result as RESULT
from backend.pipeline.evidence.shadow import biomarker_expression as BIO
from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE11
from backend.pipeline.evidence.shadow import integrated_gates_v12 as GATE12
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation import retriever_binding_1_4 as BINDING
from benchmarks.mtb_evidence.evaluation import retriever_regression_closure as CLOSURE

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "retriever_regression_closure"
BINDING_ARTIFACTS = REPO_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "retriever_binding_1_4"
PROMOTED_CORPUS = REPO_ROOT / CONTRACT.PROMOTED_CORPUS_RELPATH

START_SHA = "637a3e33c76f379c61ff67aac742994bcdd7be23"

# Estremo di fase: il commit che la chiude, mai HEAD. Vale la stessa ragione
# annotata dalle fasi precedenti — un perimetro misurato contro l'albero di
# lavoro cresce con la fase successiva e fallisce per l'intervallo sbagliato.
PHASE_END_SHA = ""

ALLOWED_WRITE_PREFIXES = (
    "backend/pipeline/evidence/retrieval/v3_backend.py",
    "backend/pipeline/evidence/retrieval/v3_result.py",
    "backend/pipeline/evidence/shadow/biomarker_expression.py",
    "backend/pipeline/evidence/shadow/integrated_gates_v12.py",
    "backend/tests/test_v3_retriever_binding.py",
    "backend/tests/test_v3_retriever_regression_closure.py",
    "benchmarks/mtb_evidence/evaluation/retriever_regression_closure.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_retriever_regression_closure.py",
    "benchmarks/mtb_evidence/v3/retriever_regression_closure/",
)

# Cio' che questa fase non deve poter toccare. La directory della fase 1.4 e' in
# questa lista e non fra i path scrivibili: gli artefatti che descrivono il gate
# 1.1 restano validi, perche' il gate 1.1 resta eseguibile.
FROZEN_PATHS = (
    CONTRACT.PROMOTED_CORPUS_RELPATH,
    CONTRACT.REGISTRY_RELPATH,
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/shadow/integrated_gates.py",
    "backend/pipeline/evidence/shadow/integrated_gates_v11.py",
    "backend/pipeline/evidence/shadow/structural_gates.py",
    "benchmarks/mtb_evidence/evaluation/claim_type_retrieval_contract.py",
    "benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/",
    "benchmarks/mtb_evidence/v3/retriever_binding_1_4/",
)

ARBITRARILY_HIGH_SCORE = CLOSURE.ARBITRARILY_HIGH_SCORE


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class ClosureFixture(unittest.TestCase):
    """I due retriever, costruiti una volta sola: il corpus e' read-only."""

    before: V3.QualifiedClaimRetrieverV3
    after: V3.QualifiedClaimRetrieverV3

    @classmethod
    def setUpClass(cls) -> None:
        cls.before, cls.after = CLOSURE.retrievers()

    def claims_for(
        self, result: Any, graph_evidence_id: str
    ) -> list[Any]:
        return [
            item
            for item in result.all_results
            if item.graph_evidence_id == graph_evidence_id
            and item.claim_id.startswith("CLM-")
        ]

    def one_claim(self, result: Any, graph_evidence_id: str) -> Any:
        claims = self.claims_for(result, graph_evidence_id)
        self.assertEqual(len(claims), 1, f"{graph_evidence_id}: {len(claims)} claim")
        return claims[0]

    def run_after(self, **overrides: Any) -> Any:
        payload: dict[str, Any] = {
            "query_id": "T-CLOSURE",
            "claim_domain": "therapeutic",
            "disease": "NSCLC",
        }
        payload.update(overrides)
        return self.after.retrieve(payload)


# --------------------------------------------------------------------------
# semantica booleana, isolata dal retriever
# --------------------------------------------------------------------------


class BooleanSemanticsTests(unittest.TestCase):
    """Il matcher da solo. Un caso per riga, e le righe non si coprono a vicenda."""

    OR_CLAIM = "EGFR L858R OR EGFR Exon 19 Deletion"
    AND_CLAIM = "EGFR L858R AND EGFR T790M"

    def test_a_or_b_is_reached_by_query_a(self) -> None:
        verdict = BIO.match("EGFR L858R", self.OR_CLAIM)
        self.assertEqual(verdict.match_type, BIO.MATCH_DISJUNCT_MEMBER)
        self.assertTrue(verdict.compatible)

    def test_a_or_b_is_reached_by_query_b(self) -> None:
        verdict = BIO.match("EGFR Exon 19 Deletion", self.OR_CLAIM)
        self.assertEqual(verdict.match_type, BIO.MATCH_DISJUNCT_MEMBER)
        self.assertTrue(verdict.compatible)

    def test_a_or_b_is_reached_by_b_or_a(self) -> None:
        verdict = BIO.match("EGFR Exon 19 Deletion OR EGFR L858R", self.OR_CLAIM)
        self.assertEqual(verdict.match_type, BIO.MATCH_EXACT_BOOLEAN_SET)
        self.assertTrue(verdict.compatible)

    def test_a_or_b_is_reached_with_duplicated_terms(self) -> None:
        verdict = BIO.match(
            "EGFR L858R OR EGFR Exon 19 Deletion OR EGFR L858R", self.OR_CLAIM
        )
        self.assertEqual(verdict.match_type, BIO.MATCH_EXACT_BOOLEAN_SET)
        self.assertTrue(verdict.compatible)

    def test_a_and_b_is_not_reached_by_a_alone(self) -> None:
        verdict = BIO.match("EGFR L858R", self.AND_CLAIM)
        self.assertEqual(verdict.match_type, BIO.MATCH_CONJUNCTION_PARTIAL)
        self.assertFalse(verdict.compatible)
        self.assertEqual(verdict.axis_bucket, BIO.REJECTED_BUCKET)

    def test_a_and_b_is_not_reached_by_b_alone(self) -> None:
        verdict = BIO.match("EGFR T790M", self.AND_CLAIM)
        self.assertEqual(verdict.match_type, BIO.MATCH_CONJUNCTION_PARTIAL)
        self.assertFalse(verdict.compatible)

    def test_a_and_b_is_reached_by_a_plus_b(self) -> None:
        verdict = BIO.match("EGFR L858R AND EGFR T790M", self.AND_CLAIM)
        self.assertEqual(verdict.match_type, BIO.MATCH_EXACT)
        self.assertTrue(verdict.compatible)

    def test_a_and_b_is_reached_by_b_and_a(self) -> None:
        verdict = BIO.match("EGFR T790M AND EGFR L858R", self.AND_CLAIM)
        self.assertEqual(verdict.match_type, BIO.MATCH_EXACT_BOOLEAN_SET)
        self.assertTrue(verdict.compatible)

    def test_a_and_b_is_reached_with_duplicated_terms(self) -> None:
        verdict = BIO.match(
            "EGFR L858R AND EGFR T790M AND EGFR L858R", self.AND_CLAIM
        )
        self.assertEqual(verdict.match_type, BIO.MATCH_EXACT_BOOLEAN_SET)
        self.assertTrue(verdict.compatible)

    def test_a_richer_query_satisfies_a_narrower_conjunction(self) -> None:
        verdict = BIO.match("EGFR L858R AND EGFR T790M", "EGFR L858R")
        self.assertEqual(verdict.match_type, BIO.MATCH_CONJUNCTION_SATISFIED)
        self.assertTrue(verdict.compatible)

    def test_a_disjunctive_query_does_not_reach_a_single_claim(self) -> None:
        # La domanda dice "A oppure B" e non quale dei due: sostenere che
        # raggiunga il claim su A deciderebbe al posto di chi ha chiesto.
        verdict = BIO.match(self.OR_CLAIM, "EGFR L858R")
        self.assertEqual(verdict.match_type, BIO.MATCH_INCOMPATIBLE)
        self.assertFalse(verdict.compatible)

    def test_every_compatible_type_that_is_not_literal_substitutes(self) -> None:
        # Una compatibilita' dichiarata e non esercitata verrebbe respinta dal
        # gate a valle sull'ordine delle parole.
        literal = {BIO.MATCH_EXACT, BIO.MATCH_NOT_CONSTRAINED}
        for name in sorted(BIO.COMPATIBLE_MATCH_TYPES - literal):
            with self.subTest(match_type=name):
                self.assertIn(name, BIO.SUBSTITUTING_MATCH_TYPES)

    def test_a_degenerate_expression_collapses_to_a_single_term(self) -> None:
        for literal in ("EGFR L858R OR EGFR L858R", "EGFR L858R AND EGFR L858R"):
            with self.subTest(literal=literal):
                self.assertEqual(BIO.canonical(literal).operator, BIO.OP_SINGLE)


class UnresolvedExpressionTests(unittest.TestCase):
    """Cio' che il parser non legge finisce in audit, mai fra i respinti."""

    UNREADABLE = (
        "EGFR L858R AND EGFR T790M OR EGFR C797S",
        "(EGFR L858R OR EGFR T790M) AND EGFR C797S",
        "[EGFR L858R OR EGFR T790M]",
        "EGFR L858R OR  OR EGFR T790M",
    )

    def test_an_unreadable_claim_expression_goes_to_audit(self) -> None:
        for literal in self.UNREADABLE:
            with self.subTest(literal=literal):
                verdict = BIO.match("EGFR L858R", literal)
                self.assertEqual(verdict.match_type, BIO.MATCH_UNRESOLVED)
                self.assertEqual(verdict.axis_bucket, BIO.AUDIT_BUCKET)
                self.assertFalse(verdict.compatible)
                self.assertFalse(verdict.substitutes)

    def test_an_unreadable_query_expression_goes_to_audit(self) -> None:
        for literal in self.UNREADABLE:
            with self.subTest(literal=literal):
                verdict = BIO.match(literal, "EGFR L858R")
                self.assertEqual(verdict.match_type, BIO.MATCH_UNRESOLVED)
                self.assertEqual(verdict.axis_bucket, BIO.AUDIT_BUCKET)

    def test_unresolved_is_never_rejected_and_never_incompatible(self) -> None:
        self.assertNotEqual(
            BIO.match("EGFR L858R", self.UNREADABLE[0]).match_type,
            BIO.MATCH_INCOMPATIBLE,
        )
        self.assertEqual(
            BIO.boolean_semantics_contract()["match_type_axis_bucket"][
                BIO.MATCH_UNRESOLVED
            ],
            BIO.AUDIT_BUCKET,
        )

    def test_the_promoted_corpus_contains_no_unreadable_expression(self) -> None:
        # Il ramo esiste per la prima espressione che arrivera'. Che oggi non ce
        # ne siano e' un fatto misurato, non un'assunzione.
        for row in CLOSURE.boolean_semantics_rows():
            with self.subTest(literal=row["literal"]):
                self.assertTrue(row["interpretable"])


class PlaceholderTests(unittest.TestCase):
    """`v` e `?` sono segnaposto della fonte, non jolly del matcher."""

    PLACEHOLDER_CLAIM = "FGFR2::v Fusion OR FGFR2::? Fusion"

    def test_a_named_fusion_does_not_match_an_unnamed_partner(self) -> None:
        verdict = BIO.match("FGFR2::BICC1 Fusion", self.PLACEHOLDER_CLAIM)
        self.assertEqual(verdict.match_type, BIO.MATCH_INCOMPATIBLE)
        self.assertFalse(verdict.compatible)

    def test_the_placeholder_disjuncts_still_match_themselves(self) -> None:
        verdict = BIO.match("FGFR2::v Fusion", self.PLACEHOLDER_CLAIM)
        self.assertEqual(verdict.match_type, BIO.MATCH_DISJUNCT_MEMBER)

    def test_no_placeholder_reaches_a_named_partner_in_the_corpus(self) -> None:
        for row in CLOSURE.boolean_semantics_rows():
            if "::v " not in row["literal"] and "::? " not in row["literal"]:
                continue
            with self.subTest(literal=row["literal"]):
                self.assertFalse(
                    BIO.match("FGFR2::BICC1 Fusion", row["literal"]).compatible
                )


# --------------------------------------------------------------------------
# gli endpoint protetti
# --------------------------------------------------------------------------


class Evidence11219Tests(ClosureFixture):
    """La discrepanza che ha aperto la fase, e la sua chiusura."""

    def test_the_rejection_under_gate_1_1_came_from_the_biomarker_gate(self) -> None:
        result = self.before.retrieve(
            CLOSURE.query_payload(
                next(
                    q
                    for q in CLOSURE.closure_queries()
                    if q["query_id"] == CLOSURE.QUERY_11219
                )
            )
        )
        claim = self.one_claim(result, "evidence:11219")
        self.assertEqual(claim.bucket, RESULT.REJECTED_BUCKET)
        self.assertIn("NATIVE_BIOMARKER_MISMATCH", claim.reason_codes)
        # Nessun altro gate aveva qualcosa da eccepire: la malattia era un alias
        # verificato, e l'intervento non era vincolato.
        self.assertEqual(
            claim.provenance["disease_relation_provenance"]["relation_type"],
            "verified_disease_alias",
        )
        self.assertEqual(claim.gate["blocking_gates"], ["biomarker"])

    def test_it_is_primary_on_l858r_nsclc(self) -> None:
        result = self.after.retrieve(
            CLOSURE.query_payload(
                next(
                    q
                    for q in CLOSURE.closure_queries()
                    if q["query_id"] == CLOSURE.QUERY_11219
                )
            )
        )
        claim = self.one_claim(result, "evidence:11219")
        self.assertEqual(claim.bucket, RESULT.PRIMARY_BUCKET)
        self.assertEqual(
            claim.gate_trace["biomarker_match"]["match_type"],
            BIO.MATCH_DISJUNCT_MEMBER,
        )
        self.assertEqual(
            claim.provenance["disease_relation_provenance"]["relation_type"],
            "verified_disease_alias",
        )
        self.assertNotIn("NATIVE_BIOMARKER_MISMATCH", claim.reason_codes)

    def test_it_is_warning_on_l858r_luad(self) -> None:
        # Il biomarcatore non compensa la relazione di malattia: LUAD e' figlia
        # di NSCLC, e il claim resta trattenuto con avviso.
        result = self.after.retrieve(
            CLOSURE.query_payload(
                next(
                    q
                    for q in CLOSURE.closure_queries()
                    if q["query_id"] == CLOSURE.QUERY_11219_PARENT
                )
            )
        )
        claim = self.one_claim(result, "evidence:11219")
        self.assertEqual(claim.bucket, RESULT.WARNING_BUCKET)
        self.assertEqual(claim.gate_trace["dominant_gate"], "disease")

    def test_the_other_disjunct_reaches_the_same_claim(self) -> None:
        result = self.run_after(
            query_id="T-EX19", biomarker="EGFR Exon 19 Deletion"
        )
        claim = self.one_claim(result, "evidence:11219")
        self.assertEqual(claim.bucket, RESULT.PRIMARY_BUCKET)


class ConjunctionTests(ClosureFixture):
    """AND non si rilassa a OR: 11598 e 11599 restano respinti a meta'."""

    def test_11599_is_rejected_by_l858r_alone(self) -> None:
        result = self.run_after(query_id="T-AND-A", biomarker="EGFR L858R")
        claim = self.one_claim(result, "evidence:11599")
        self.assertEqual(claim.bucket, RESULT.REJECTED_BUCKET)
        self.assertEqual(
            claim.gate_trace["biomarker_match"]["match_type"],
            BIO.MATCH_CONJUNCTION_PARTIAL,
        )
        self.assertEqual(claim.gate_trace["dominant_gate"], "biomarker")

    def test_11599_is_rejected_by_t790m_alone(self) -> None:
        result = self.run_after(query_id="T-AND-B", biomarker="EGFR T790M")
        claim = self.one_claim(result, "evidence:11599")
        self.assertEqual(claim.bucket, RESULT.REJECTED_BUCKET)

    def test_11598_is_rejected_by_t790m_alone(self) -> None:
        result = self.run_after(query_id="T-AND-C", biomarker="EGFR T790M")
        claim = self.one_claim(result, "evidence:11598")
        self.assertEqual(claim.bucket, RESULT.REJECTED_BUCKET)
        self.assertEqual(
            claim.gate_trace["biomarker_match"]["match_type"],
            BIO.MATCH_CONJUNCTION_PARTIAL,
        )

    def test_11599_is_primary_when_both_members_are_asked(self) -> None:
        result = self.run_after(
            query_id="T-AND-AB", biomarker="EGFR L858R AND EGFR T790M"
        )
        claim = self.one_claim(result, "evidence:11599")
        self.assertEqual(claim.bucket, RESULT.PRIMARY_BUCKET)

    def test_the_member_order_does_not_change_a_single_decision(self) -> None:
        straight = self.run_after(
            query_id="T-ORDER", biomarker="EGFR L858R AND EGFR T790M"
        )
        reversed_ = self.run_after(
            query_id="T-ORDER", biomarker="EGFR T790M AND EGFR L858R"
        )
        self.assertEqual(
            CLOSURE.bucket_assignment(straight),
            CLOSURE.bucket_assignment(reversed_),
        )

    def test_duplicated_members_do_not_change_a_single_decision(self) -> None:
        plain = self.run_after(
            query_id="T-DUP", biomarker="EGFR L858R AND EGFR T790M"
        )
        duplicated = self.run_after(
            query_id="T-DUP", biomarker="EGFR L858R AND EGFR T790M AND EGFR L858R"
        )
        self.assertEqual(
            CLOSURE.bucket_assignment(plain),
            CLOSURE.bucket_assignment(duplicated),
        )


class Evidence1867Tests(ClosureFixture):
    """L'atomico su T790M resta raggiungibile solo da chi afferma T790M."""

    def test_it_is_primary_on_t790m(self) -> None:
        result = self.run_after(
            query_id="T-1867",
            biomarker="EGFR T790M",
            disease="Lung Non-small Cell Carcinoma",
        )
        claim = self.one_claim(result, "evidence:1867")
        self.assertEqual(claim.bucket, RESULT.PRIMARY_BUCKET)
        self.assertEqual(
            claim.gate_trace["biomarker_match"]["match_type"], BIO.MATCH_EXACT
        )

    def test_it_is_not_reached_by_l858r(self) -> None:
        result = self.run_after(query_id="T-1867-B", biomarker="EGFR L858R")
        claim = self.one_claim(result, "evidence:1867")
        self.assertEqual(claim.bucket, RESULT.REJECTED_BUCKET)

    def test_it_is_not_reached_by_the_disjunctive_expression(self) -> None:
        result = self.run_after(
            query_id="T-1867-C", biomarker="EGFR L858R OR EGFR Exon 19 Deletion"
        )
        claim = self.one_claim(result, "evidence:1867")
        self.assertEqual(claim.bucket, RESULT.REJECTED_BUCKET)


class Evidence8173Tests(ClosureFixture):
    """Il bucket finale non cancella i risultati dei singoli gate."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.result = cls.after.retrieve(
            CLOSURE.query_payload(
                next(
                    q
                    for q in CLOSURE.closure_queries()
                    if q["query_id"] == CLOSURE.QUERY_8173
                )
            )
        )

    def test_the_four_results_survive_together(self) -> None:
        claim = self.one_claim(self.result, "evidence:8173")
        trace = claim.gate_trace
        self.assertEqual(
            claim.provenance["disease_relation_provenance"]["relation_type"],
            "disease_sibling",
        )
        self.assertEqual(trace["gate_local_buckets"]["disease"], RESULT.AUDIT_BUCKET)
        self.assertEqual(
            trace["biomarker_match"]["match_type"], BIO.MATCH_INCOMPATIBLE
        )
        self.assertEqual(claim.bucket, RESULT.REJECTED_BUCKET)
        self.assertEqual(trace["dominant_gate"], "biomarker")

    def test_the_disease_provenance_is_still_visible(self) -> None:
        claim = self.one_claim(self.result, "evidence:8173")
        provenance = claim.provenance["disease_relation_provenance"]
        self.assertTrue(provenance["relation_verified"])
        self.assertTrue(provenance["relation_source"])
        self.assertTrue(provenance["relation_source_version"])
        self.assertEqual(provenance["relation_direction"], "lateral")

    def test_the_biomarker_is_genuinely_incompatible(self) -> None:
        # Non e' respinto per una svista del parser: nessuno dei due disgiunti
        # e' la fusione chiesta.
        verdict = BIO.match("FGFR2::BICC1 Fusion", "FGFR2::v Fusion OR FGFR2::? Fusion")
        self.assertFalse(verdict.compatible)

    def test_no_score_flag_survives_the_rejection(self) -> None:
        claim = self.one_claim(self.result, "evidence:8173")
        self.assertFalse(claim.score["ranking_score_allowed"])
        self.assertTrue(claim.score["eligibility"]["positive_score_forbidden"])


class DiagnosticEndpointTests(ClosureFixture):
    """1846 e 1847 non si muovono: nessuna delle loro espressioni e' booleana."""

    def test_they_land_in_the_same_bucket_under_both_gates(self) -> None:
        for row in CLOSURE.regression_rows():
            for evidence_id in ("evidence:1846", "evidence:1847"):
                before = {
                    item["claim_id"]: item["bucket"]
                    for item in row["endpoints_before"]
                    if item["graph_evidence_id"] == evidence_id
                }
                after = {
                    item["claim_id"]: item["bucket"]
                    for item in row["endpoints_after"]
                    if item["graph_evidence_id"] == evidence_id
                }
                with self.subTest(query=row["query_id"], evidence=evidence_id):
                    self.assertEqual(before, after)


# --------------------------------------------------------------------------
# invarianti del gate
# --------------------------------------------------------------------------


class GateInvariantTests(ClosureFixture):
    """Le invarianti, verificate su ogni oggetto e su ogni query."""

    def test_no_score_survives_a_blocking_gate_anywhere(self) -> None:
        for query in CLOSURE.closure_queries():
            typed = self.after.build_native_query(CLOSURE.query_payload(query))
            gate_query = typed.to_gate_query()
            with self.subTest(query=query["query_id"]):
                for obj, _record in self.after._objects:  # noqa: SLF001
                    outcome = GATE12.evaluate(
                        gate_query, obj, mode=typed.policy_mode
                    )
                    GATE12.check_no_score_survives_a_blocking_gate(
                        outcome, ARBITRARILY_HIGH_SCORE
                    )

    def test_the_dominant_gate_is_the_most_restrictive_axis(self) -> None:
        for query in CLOSURE.closure_queries():
            typed = self.after.build_native_query(CLOSURE.query_payload(query))
            gate_query = typed.to_gate_query()
            with self.subTest(query=query["query_id"]):
                for obj, _record in self.after._objects:  # noqa: SLF001
                    outcome = GATE12.evaluate(
                        gate_query, obj, mode=typed.policy_mode
                    )
                    self.assertEqual(
                        outcome.dominant_gate,
                        GATE12.dominant_gate(outcome.gate_local_buckets),
                    )

    def test_every_axis_reports_a_known_bucket_or_declares_it_unevaluated(self) -> None:
        known = set(GATE12.BUCKET_PRECEDENCE) | {GATE12.NOT_EVALUATED}
        result = self.run_after(query_id="T-AXES", biomarker="EGFR L858R")
        for item in result.all_results:
            with self.subTest(claim=item.claim_id):
                self.assertEqual(
                    set(item.gate_trace["gate_local_buckets"]), set(GATE12.GATE_NAMES)
                )
                self.assertLessEqual(
                    set(item.gate_trace["gate_local_buckets"].values()), known
                )

    def test_a_claim_bucket_is_the_composition_of_its_axes(self) -> None:
        result = self.run_after(query_id="T-COMPOSE", biomarker="EGFR L858R")
        for item in result.all_results:
            if not item.claim_id.startswith("CLM-"):
                continue
            with self.subTest(claim=item.claim_id):
                buckets = [
                    bucket
                    for bucket in item.gate_trace["gate_local_buckets"].values()
                    if bucket != GATE12.NOT_EVALUATED
                ]
                composed = min(buckets, key=GATE12.BUCKET_PRECEDENCE.index)
                self.assertEqual(item.bucket, composed)


class QueryIsNotMutatedTests(ClosureFixture):
    """La sostituzione interna non riscrive la domanda posta."""

    def test_the_observable_query_keeps_the_original_biomarker(self) -> None:
        result = self.run_after(query_id="T-MUT", biomarker="EGFR L858R")
        self.assertEqual(
            result.query["normalized"]["normalized_biomarker"], "EGFR L858R"
        )
        self.assertEqual(result.query["original"]["biomarker"], "EGFR L858R")

    def test_the_substitution_is_recorded_in_full(self) -> None:
        result = self.run_after(query_id="T-SUB", biomarker="EGFR L858R")
        claim = self.one_claim(result, "evidence:11219")
        substitution = claim.gate_trace["biomarker_substitution"]
        self.assertEqual(
            sorted(substitution),
            [
                "claim_biomarker_expression",
                "effective_biomarker_passed_to_v11",
                "original_query_biomarker",
                "substitution_reason",
            ],
        )
        self.assertEqual(substitution["original_query_biomarker"], "egfr l858r")
        self.assertEqual(
            substitution["effective_biomarker_passed_to_v11"],
            "egfr l858r or egfr exon 19 deletion",
        )
        self.assertEqual(
            substitution["substitution_reason"], BIO.MATCH_DISJUNCT_MEMBER
        )

    def test_no_substitution_is_declared_when_none_happened(self) -> None:
        result = self.run_after(query_id="T-NOSUB", biomarker="EGFR L858R")
        claim = self.one_claim(result, "evidence:1867")
        self.assertEqual(
            claim.gate_trace["biomarker_substitution"]["substitution_reason"], "none"
        )

    def test_two_queries_differing_only_in_form_run_the_same(self) -> None:
        composed = self.after.retrieve(
            {
                "query_id": "T-FORM",
                "claim_domain": "therapeutic",
                "gene": "EGFR",
                "alteration": "L858R",
                "disease": "NSCLC",
            }
        )
        explicit = self.run_after(query_id="T-FORM", biomarker="EGFR L858R")
        self.assertEqual(
            CLOSURE.bucket_assignment(composed), CLOSURE.bucket_assignment(explicit)
        )


# --------------------------------------------------------------------------
# la fase precedente resta riproducibile
# --------------------------------------------------------------------------


class PriorPhaseTests(ClosureFixture):
    """Il gate 1.1 ricalcola la fase 1.4 senza che un artefatto sia stato toccato."""

    def test_the_gate_1_1_reproduces_the_recorded_digests(self) -> None:
        rows = {
            row["query_id"]: row
            for row in _read_jsonl(BINDING_ARTIFACTS / "v3_regression_results.jsonl")
        }
        for query in BINDING.REGRESSION_QUERIES:
            payload = {k: v for k, v in query.items() if k != "expectation"}
            with self.subTest(query=query["query_id"]):
                result = self.before.retrieve(payload)
                recorded = rows[query["query_id"]]
                self.assertEqual(result.canonical_digest(), recorded["result_digest"])
                self.assertEqual(result.bucket_counts(), recorded["bucket_counts"])

    def test_the_1_4_artifacts_are_untouched(self) -> None:
        changed = subprocess.run(
            ["git", "diff", "--name-only", START_SHA, "--", "."],
            cwd=BINDING_ARTIFACTS,
            capture_output=True,
            text=True,
            check=False,
        )
        if changed.returncode != 0:
            self.skipTest("git non utilizzabile in questo checkout")
        self.assertEqual(changed.stdout.strip(), "")

    def test_the_two_gates_declare_different_result_schemas(self) -> None:
        self.assertEqual(self.before.result_schema_version, "qualified_claim_retrieval_result/1.4")
        self.assertEqual(self.after.result_schema_version, "qualified_claim_retrieval_result/1.5")
        self.assertEqual(
            RESULT.result_schema(GATE12)["supersedes"],
            RESULT.result_schema(GATE11)["schema_version"],
        )

    def test_the_gate_1_1_result_carries_no_gate_trace(self) -> None:
        result = self.before.retrieve(
            {
                "query_id": "T-NOTRACE",
                "claim_domain": "therapeutic",
                "biomarker": "EGFR L858R",
                "disease": "NSCLC",
            }
        )
        for item in result.all_results[:20]:
            with self.subTest(claim=item.claim_id):
                self.assertIsNone(item.gate_trace)
                self.assertNotIn("gate_trace", item.to_dict())

    def test_the_gate_1_1_module_is_unchanged(self) -> None:
        changed = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                START_SHA,
                "--",
                "backend/pipeline/evidence/shadow/integrated_gates_v11.py",
                "backend/pipeline/evidence/shadow/integrated_gates.py",
                "backend/pipeline/evidence/shadow/structural_gates.py",
                "benchmarks/mtb_evidence/evaluation/claim_type_retrieval_contract.py",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if changed.returncode != 0:
            self.skipTest("git non utilizzabile in questo checkout")
        self.assertEqual(changed.stdout.strip(), "")


# --------------------------------------------------------------------------
# che cosa si muove, e che cosa no
# --------------------------------------------------------------------------


class RegressionScopeTests(ClosureFixture):
    """La differenza fra i due gate e' circoscritta e misurata."""

    EXPECTED_MOVERS = {
        "RB-01-EGFR-L858R-NSCLC",
        "RB-02-EGFR-L858R-LUAD",
        "RB-12-UNKNOWN-DRUG-CODE",
        "RB-13-UNKNOWN-DISEASE",
        "RC-02-EGFR-EXON19-NSCLC",
        "RC-03-EGFR-L858R-AND-T790M",
        "RC-04-EGFR-T790M-AND-L858R",
    }

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.rows = CLOSURE.regression_rows()

    def test_only_the_expected_queries_change_a_decision(self) -> None:
        movers = {
            row["query_id"] for row in self.rows if not row["decisions_unchanged"]
        }
        self.assertEqual(movers, self.EXPECTED_MOVERS)

    def test_the_untouched_queries_keep_the_same_assignment_digest(self) -> None:
        for row in self.rows:
            if row["query_id"] in self.EXPECTED_MOVERS:
                continue
            with self.subTest(query=row["query_id"]):
                self.assertEqual(
                    row["bucket_assignment_digest_before"],
                    row["bucket_assignment_digest_after"],
                )

    def test_the_expected_bucket_deltas_hold(self) -> None:
        expected = {
            "RB-01-EGFR-L858R-NSCLC": {
                "audit_only_results": 2,
                "primary_ranked_results": 10,
                "rejected_by_native_constraints": -13,
                "retained_with_warning": 1,
            },
            "RB-02-EGFR-L858R-LUAD": {
                "audit_only_results": 2,
                "primary_ranked_results": 1,
                "rejected_by_native_constraints": -13,
                "retained_with_warning": 10,
            },
            "RB-12-UNKNOWN-DRUG-CODE": {
                "audit_only_results": 2,
                "rejected_by_native_constraints": -2,
            },
            "RB-13-UNKNOWN-DISEASE": {
                "audit_only_results": 2,
                "rejected_by_native_constraints": -2,
            },
        }
        rows = {row["query_id"]: row for row in self.rows}
        for query_id, deltas in sorted(expected.items()):
            row = rows[query_id]
            with self.subTest(query=query_id):
                actual = {
                    key: row["bucket_counts_after"][key] - value
                    for key, value in row["bucket_counts_before"].items()
                    if row["bucket_counts_after"][key] != value
                }
                self.assertEqual(actual, deltas)

    def test_no_claim_ever_moves_from_audit_to_rejected(self) -> None:
        # Il bucket di audit e' il posto in cui un candidato escluso resta
        # recuperabile: perderne il contenuto sarebbe una regressione anche se
        # ogni singola decisione fosse difendibile.
        for row in self.rows:
            for claim_id, movement in row["moved_claims"].items():
                with self.subTest(query=row["query_id"], claim=claim_id):
                    self.assertFalse(
                        movement["before"] == RESULT.AUDIT_BUCKET
                        and movement["after"] == RESULT.REJECTED_BUCKET
                    )

    def test_the_corpus_hash_is_the_same_on_both_sides(self) -> None:
        self.assertEqual(self.before.corpus_hash, self.after.corpus_hash)


# --------------------------------------------------------------------------
# artefatti e perimetro
# --------------------------------------------------------------------------


class ArtifactTests(unittest.TestCase):
    """Gli artefatti dicono cio' che e' stato misurato, e non piu' di quello."""

    NAMES = (
        "RERUN_BLOCKER_CLOSURE.md",
        "biomarker_boolean_semantics_audit.json",
        "evidence_11219_gate_trace.json",
        "evidence_8173_gate_trace.json",
        "finding_resolution.json",
        "regression_results.jsonl",
        "regression_scope.json",
    )

    def test_every_declared_artifact_exists(self) -> None:
        for name in self.NAMES:
            with self.subTest(artifact=name):
                self.assertTrue((ARTIFACTS / name).is_file())

    def test_every_artifact_declares_what_it_supersedes(self) -> None:
        for name in self.NAMES:
            if not name.endswith(".json"):
                continue
            with self.subTest(artifact=name):
                self.assertEqual(
                    _read_json(ARTIFACTS / name)["supersedes"], CLOSURE.SUPERSEDES
                )

    def test_the_scope_declares_the_gold_unread(self) -> None:
        scope = _read_json(ARTIFACTS / "regression_scope.json")
        self.assertFalse(scope["gold_read"])
        self.assertFalse(scope["scoring_weights_retuned"])
        self.assertTrue(scope["corpus_unchanged"])

    def test_the_recorded_rows_match_a_fresh_measurement(self) -> None:
        recorded = _read_jsonl(ARTIFACTS / "regression_results.jsonl")
        self.assertEqual(recorded, CLOSURE.regression_rows())

    def test_the_11219_trace_names_the_query_that_produced_it(self) -> None:
        trace = _read_json(ARTIFACTS / "evidence_11219_gate_trace.json")
        self.assertEqual(trace["query_id"], CLOSURE.QUERY_11219)
        self.assertEqual(trace["normalized_query"]["normalized_biomarker"], "EGFR L858R")
        self.assertEqual(trace["original_query"]["gene"], "EGFR")
        self.assertEqual(trace["original_query"]["alteration"], "L858R")

    def test_the_8173_trace_keeps_the_disease_relation(self) -> None:
        trace = _read_json(ARTIFACTS / "evidence_8173_gate_trace.json")
        claim = next(
            item for item in trace["after"]["claims"] if item["claim_id"].startswith("CLM-")
        )
        self.assertEqual(
            claim["provenance"]["disease_relation_provenance"]["relation_type"],
            "disease_sibling",
        )
        self.assertEqual(claim["gate_trace"]["dominant_gate"], "biomarker")


class CorpusUntouchedTests(unittest.TestCase):
    """Il corpus promosso non e' stato toccato, e il gold non e' stato letto."""

    def test_the_promoted_corpus_files_match_their_manifest(self) -> None:
        manifest = _read_json(PROMOTED_CORPUS / CONTRACT.MANIFEST_FILE)
        for name, expected in sorted(manifest["artifact_sha256"].items()):
            with self.subTest(artifact=name):
                actual = hashlib.sha256(
                    (PROMOTED_CORPUS / name).read_text(encoding="utf-8").encode("utf-8")
                ).hexdigest()
                self.assertEqual(actual, expected)

    def test_the_registry_still_declares_the_retriever_unbound(self) -> None:
        entry = _read_json(PROMOTED_CORPUS / "corpus_registry_entry.json")
        self.assertFalse(entry["operational_retriever_bound"])
        self.assertFalse(entry["clinical_readiness"])
        self.assertFalse(entry["final_evaluable"])

    def test_no_phase_module_reads_the_gold(self) -> None:
        sources = (
            REPO_ROOT / "backend/pipeline/evidence/shadow/biomarker_expression.py",
            REPO_ROOT / "backend/pipeline/evidence/shadow/integrated_gates_v12.py",
            REPO_ROOT / "benchmarks/mtb_evidence/evaluation/retriever_regression_closure.py",
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/scripts/build_retriever_regression_closure.py",
        )
        for path in sources:
            body = path.read_text(encoding="utf-8")
            with self.subTest(module=path.name):
                self.assertNotIn("mtb_evidence_gold", body)
                self.assertNotIn("provisional_gold", body)
                self.assertNotIn("gold_pilot", body)


class PhasePerimeterTests(unittest.TestCase):
    """Il perimetro della fase, misurato su un intervallo chiuso di commit."""

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

    def test_the_prior_phase_directory_is_frozen(self) -> None:
        self.assertIn("benchmarks/mtb_evidence/v3/retriever_binding_1_4/", FROZEN_PATHS)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
