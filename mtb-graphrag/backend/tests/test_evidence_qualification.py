"""Test del layer di qualificazione: link conservativi e viste derivate.

Offline: nessun grafo, nessuna rete, nessun modello.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest import TestCase

from backend.pipeline.evidence.qualification import (
    AMBIGUOUS,
    AMBIGUOUS_MATCH,
    CONFLICTING,
    CONFLICTING_MATCH,
    EXACT_NCT,
    EXACT_PMID,
    EXACT_SOURCE_MATCH,
    NO_MATCH,
    NO_MATCH_STATUS,
    PARTIALLY_QUALIFIED,
    PROFILE_DIMENSIONS,
    UNQUALIFIED,
    build_link,
    build_links,
    build_view,
    build_views,
)
from benchmarks.mtb_evidence.evaluation.contracts import SourceClinicalProfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION_DIR = PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "qualification"


def _statement(identifier="ES-1", *, pmid="29151359", disease="advanced NSCLC",
               drug="osimertinib", **overrides):
    base = {
        "evidence_statement_id": identifier,
        "biomarker": {"label": "EGFR L858R", "gene": "EGFR", "is_compound": False},
        "alteration_type": "snv",
        "disease": {"label": disease, "specificity": "unknown"},
        "intervention": {"label": drug} if drug else None,
        "direction": "sensitivity",
        "evidence_scope": "therapeutic",
        "assertion_polarity": "supports",
        "clinical_context": {},
        "evidence_type": "unknown",
        "evidence_level": None,
        "source_references": (
            [{"source_id": f"PUBMED:{pmid}", "source_type": "pubmed",
              "external_identifier": pmid, "presence_in_snapshot": "node"}]
            if pmid else []
        ),
        "trial_references": [],
        "provenance": {"origin": "frozen_kg", "snapshot_fingerprint": "abc",
                       "graph_record_ids": ["evidence:1"]},
        "review_status": "pending_verification",
        "conflicts": [],
    }
    base.update(overrides)
    return base


def _profile(source_id="S-1", *, pmid="29151359", nct_ids=("NCT02296125",),
             disease="advanced non-small cell lung cancer",
             interventions=("osimertinib",), **overrides):
    fields = dict(
        source_id=source_id, pmid=pmid, nct_ids=tuple(nct_ids), title="FLAURA",
        disease=disease, population="previously untreated advanced NSCLC",
        stage="locally advanced or metastatic", setting="first-line advanced/metastatic",
        therapy_line="first line", prior_therapies=(),
        biomarker_requirements=("EGFR exon 19 deletion or L858R",),
        regimen="osimertinib monotherapy", interventions=tuple(interventions),
        inclusion_criteria_summary="treatment-naive",
        exclusion_criteria_summary="prior systemic therapy excluded",
        review_status="human_reviewed",
    )
    fields.update(overrides)
    return SourceClinicalProfile(**fields)


class MatchingTest(TestCase):
    def test_exact_pmid_match(self):
        link = build_link(_statement(), _profile())
        self.assertEqual(link.match_method, EXACT_PMID)
        self.assertEqual(link.match_status, EXACT_SOURCE_MATCH)
        self.assertEqual(link.matched_source_ids, ("29151359",))

    def test_no_shared_source_is_no_match(self):
        link = build_link(_statement(pmid="11111111"), _profile(pmid="22222222"))
        self.assertEqual(link.match_status, NO_MATCH_STATUS)
        self.assertEqual(link.match_method, NO_MATCH)
        self.assertEqual(link.added_dimensions, ())

    def test_statement_without_sources_cannot_match(self):
        link = build_link(_statement(pmid=None), _profile())
        self.assertEqual(link.match_status, NO_MATCH_STATUS)

    def test_nct_match_when_no_pmid_overlap(self):
        statement = _statement(pmid=None)
        statement["trial_references"] = [
            {"source_id": "NCT02296125", "source_type": "clinicaltrials_gov",
             "external_identifier": "NCT02296125"}
        ]
        link = build_link(statement, _profile(pmid=""))
        self.assertEqual(link.match_method, EXACT_NCT)

    def test_no_automatic_fuzzy_title_match(self):
        """Un titolo simile non e' la stessa fonte."""
        statement = _statement(pmid="99999999")
        statement["title"] = "FLAURA"
        self.assertEqual(build_link(statement, _profile()).match_status, NO_MATCH_STATUS)

    def test_one_pmid_can_link_several_statements(self):
        statements = [_statement("ES-A"), _statement("ES-B", drug="gefitinib")]
        links = build_links(statements, [_profile()])
        self.assertEqual({l.statement_id for l in links}, {"ES-A", "ES-B"})

    def test_links_are_sorted_deterministically(self):
        statements = [_statement("ES-B"), _statement("ES-A")]
        forward = [l.qualification_link_id for l in build_links(statements, [_profile()])]
        backward = [
            l.qualification_link_id
            for l in build_links(list(reversed(statements)), [_profile()])
        ]
        self.assertEqual(forward, backward)

    def test_no_match_links_are_not_emitted(self):
        """Emetterne uno per ogni coppia produrrebbe rumore quadratico."""
        links = build_links([_statement(pmid="11111111")], [_profile()])
        self.assertEqual(links, [])


class ConflictTest(TestCase):
    def test_disease_subtype_conflicts_with_parent(self):
        """Il conflitto di specificita' trovato dall'audit sul caso K1."""
        link = build_link(
            _statement(disease="Cholangiolocellular Carcinoma"),
            _profile(disease="cholangiocarcinoma"),
        )
        self.assertEqual(link.match_status, CONFLICTING_MATCH)
        self.assertTrue(any(c["dimension"] == "disease" for c in link.conflicts))

    def test_intervention_mismatch_is_a_conflict(self):
        link = build_link(
            _statement(drug="alectinib"), _profile(interventions=("lorlatinib",))
        )
        self.assertTrue(any(c["dimension"] == "intervention" for c in link.conflicts))

    def test_conflict_prevents_dimensions_from_being_applied(self):
        link = build_link(_statement(drug="alectinib"), _profile(interventions=("lorlatinib",)))
        self.assertEqual(link.added_dimensions, ())
        self.assertEqual(link.applicable_profile_dimensions, ())

    def test_matching_disease_vocabulary_is_not_a_conflict(self):
        link = build_link(
            _statement(disease="advanced NSCLC"),
            _profile(disease="advanced non-small cell lung cancer"),
        )
        self.assertEqual(link.conflicts, ())


class AmbiguityTest(TestCase):
    def test_multi_intervention_profile_is_ambiguous(self):
        """Con piu' bracci non e' determinabile a quale si riferisca la linea di terapia."""
        link = build_link(
            _statement(drug="osimertinib"),
            _profile(interventions=("osimertinib", "gefitinib")),
        )
        self.assertEqual(link.match_status, AMBIGUOUS_MATCH)
        self.assertTrue(link.ambiguity_reasons)

    def test_ambiguous_dimensions_are_not_applied(self):
        link = build_link(
            _statement(), _profile(interventions=("osimertinib", "gefitinib"))
        )
        self.assertEqual(link.added_dimensions, ())
        self.assertTrue(set(link.excluded_profile_dimensions) >= set(PROFILE_DIMENSIONS))

    def test_multi_trial_profile_is_ambiguous(self):
        link = build_link(_statement(), _profile(nct_ids=("NCT1", "NCT2")))
        self.assertEqual(link.match_status, AMBIGUOUS_MATCH)


class ImmutabilityTest(TestCase):
    def test_link_does_not_modify_the_statement(self):
        statement = _statement()
        before = copy.deepcopy(statement)
        build_link(statement, _profile())
        self.assertEqual(statement, before)

    def test_link_does_not_modify_the_profile(self):
        profile = _profile()
        before = profile.as_dict()
        build_link(_statement(), profile)
        self.assertEqual(profile.as_dict(), before)

    def test_link_does_not_promote_the_statement(self):
        link = build_link(_statement(), _profile())
        self.assertEqual(link.provenance["statement_origin"], "frozen_kg")
        self.assertEqual(link.review_status, "machine_linked")


class ProvenanceTest(TestCase):
    def test_every_added_dimension_carries_full_provenance(self):
        link = build_link(_statement(), _profile())
        self.assertTrue(link.added_dimensions)
        for value in link.added_dimensions:
            self.assertEqual(value.value_origin, "reviewed_source_profile")
            self.assertEqual(value.source_profile_id, "S-1")
            self.assertEqual(value.source_identifier, "29151359")
            self.assertEqual(value.qualification_link_id, link.qualification_link_id)
            self.assertEqual(value.review_status, "human_reviewed")

    def test_match_basis_is_recorded(self):
        link = build_link(_statement(), _profile())
        self.assertIn("titolo", link.provenance["match_basis"])


class QualifiedViewTest(TestCase):
    def test_base_statement_is_unchanged(self):
        statement = _statement()
        view = build_view(statement, build_links([statement], [_profile()]))
        self.assertEqual(view.base_statement["clinical_context"], {})
        self.assertEqual(view.base_statement["review_status"], "pending_verification")

    def test_qualifiers_appear_in_the_view_not_in_the_statement(self):
        statement = _statement()
        view = build_view(statement, build_links([statement], [_profile()]))
        self.assertIn("therapy_line", view.qualified_dimensions)
        self.assertEqual(view.qualified_dimensions["therapy_line"].value, "first line")
        self.assertEqual(statement["clinical_context"], {})

    def test_status_is_partially_qualified_when_some_dimensions_remain(self):
        statement = _statement()
        view = build_view(statement, build_links([statement], [_profile()]))
        self.assertEqual(view.qualification_status, PARTIALLY_QUALIFIED)
        self.assertIn("resection_status", view.unresolved_dimensions)

    def test_no_links_is_unqualified(self):
        view = build_view(_statement(), [])
        self.assertEqual(view.qualification_status, UNQUALIFIED)
        self.assertEqual(view.qualified_dimensions, {})

    def test_conflicting_link_makes_the_view_conflicting(self):
        statement = _statement(drug="alectinib")
        view = build_view(statement, build_links([statement], [_profile(interventions=("lorlatinib",))]))
        self.assertEqual(view.qualification_status, CONFLICTING)

    def test_ambiguous_link_makes_the_view_ambiguous(self):
        # L'intervento dello statement e' fra quelli del profilo: nessun conflitto,
        # solo ambiguita' su quale braccio i qualificatori descrivano.
        statement = _statement(drug="osimertinib")
        links = build_links(
            [statement], [_profile(interventions=("osimertinib", "gefitinib"))]
        )
        self.assertEqual(build_view(statement, links).qualification_status, AMBIGUOUS)

    def test_two_profiles_agreeing_qualify_once(self):
        statement = _statement()
        links = build_links([statement], [_profile("S-1"), _profile("S-2")])
        view = build_view(statement, links)
        self.assertEqual(view.qualified_dimensions["therapy_line"].value, "first line")
        self.assertEqual(len(view.linked_source_profile_ids), 2)

    def test_two_profiles_disagreeing_do_not_overwrite(self):
        """Scegliere fra due fonti revisionate e' un giudizio umano."""
        statement = _statement()
        links = build_links(
            [statement],
            [_profile("S-1", therapy_line="first line"),
             _profile("S-2", therapy_line="second line")],
        )
        view = build_view(statement, links)
        self.assertNotIn("therapy_line", view.qualified_dimensions)
        self.assertTrue(any(c["dimension"] == "therapy_line" for c in view.conflicts))
        self.assertEqual(view.qualification_status, CONFLICTING)

    def test_unknown_stays_unknown(self):
        statement = _statement()
        view = build_view(statement, build_links([statement], [_profile()]))
        # Il profilo non porta resection_status: non viene inventato.
        self.assertNotIn("resection_status", view.qualified_dimensions)

    def test_view_serialisation_is_deterministic(self):
        statement = _statement()
        links = build_links([statement], [_profile()])
        first = json.dumps(build_view(statement, links).as_dict(), sort_keys=True)
        second = json.dumps(build_view(statement, links).as_dict(), sort_keys=True)
        self.assertEqual(first, second)

    def test_provenance_by_dimension_is_complete(self):
        statement = _statement()
        payload = build_view(statement, build_links([statement], [_profile()])).as_dict()
        for name, provenance in payload["provenance_by_dimension"].items():
            for key in ("value_origin", "source_profile_id", "source_identifier",
                        "qualification_link_id", "review_status"):
                self.assertIn(key, provenance, name)

    def test_build_views_covers_every_statement(self):
        statements = [_statement("ES-A"), _statement("ES-B", pmid="99999999")]
        views = build_views(statements, build_links(statements, [_profile()]))
        self.assertEqual(len(views), 2)
        self.assertEqual(views[1].qualification_status, UNQUALIFIED)


class PilotArtefactTest(TestCase):
    """Controlli sugli artefatti prodotti dallo script di collegamento."""

    def _metrics(self):
        path = QUALIFICATION_DIR / "qualification_metrics.json"
        if not path.is_file():
            self.skipTest("artefatti di qualificazione non generati")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_nothing_was_modified(self):
        metrics = self._metrics()
        self.assertTrue(metrics["statements_unchanged"])
        self.assertTrue(metrics["profiles_unchanged"])
        self.assertTrue(metrics["no_promotion"])

    def test_all_eight_profiles_are_loaded(self):
        self.assertEqual(self._metrics()["profiles_loaded"], 8)

    def test_provenance_completeness_is_total(self):
        self.assertEqual(self._metrics()["qualifier_provenance_completeness"], 1.0)

    def test_linking_precision_is_not_invented(self):
        """Senza un gold di collegamento, precision e recall non sono calcolabili."""
        metrics = self._metrics()
        self.assertEqual(metrics["linking_precision"], "not_evaluated")
        self.assertEqual(metrics["linking_recall"], "not_evaluated")

    def test_unmatched_profiles_are_the_sources_absent_from_the_snapshot(self):
        """Coerenza con l'audit: FLAURA e FOENIX-CCA2 non sono nel grafo."""
        self.assertEqual(sorted(self._metrics()["unmatched_profiles"]), ["S-C1-1", "S-K1-3"])

    def test_coverage_before_is_zero_on_every_dimension(self):
        coverage = self._metrics()["coverage"]
        self.assertEqual(set(coverage["before_frozen_kg"].values()), {0})
