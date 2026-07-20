from unittest import TestCase

from backend.pipeline.agentic.regimen_arms import (
    claim_components_from_object,
    match_claim_to_arms,
    normalize_intervention_name,
    normalize_source_arms,
)


class NormalizeInterventionNameTest(TestCase):
    def test_known_drug_is_accepted_case_insensitively(self):
        self.assertEqual(normalize_intervention_name("Amivantamab"), "amivantamab")
        self.assertEqual(normalize_intervention_name("OSIMERTINIB"), "osimertinib")

    def test_unknown_generic_terms_are_rejected(self):
        """RELAY: parole generiche del testo non diventano mai un farmaco."""
        for term in ("hospitals", "double-blind", "EGFR", "enrolled", "progression-free"):
            with self.subTest(term=term):
                self.assertIsNone(normalize_intervention_name(term))

    def test_placebo_is_never_a_drug(self):
        self.assertIsNone(normalize_intervention_name("placebo"))
        self.assertIsNone(normalize_intervention_name("Placebo"))


class NormalizeSourceArmsTest(TestCase):
    def test_filters_unknown_terms_and_placebo_per_arm(self):
        arms = normalize_source_arms([
            {"arm_name": "erlotinib+placebo", "interventions": ["erlotinib", "placebo", "hospitals"]},
        ])
        self.assertEqual(arms, [{"arm_name": "erlotinib+placebo", "interventions": ["erlotinib"]}])

    def test_malformed_entries_are_ignored(self):
        arms = normalize_source_arms([
            "not-a-dict",
            {"arm_name": "", "interventions": ["erlotinib"]},
            {"interventions": ["erlotinib"]},
            {"arm_name": "valid", "interventions": "not-a-list"},
            {"arm_name": "valid-arm", "interventions": ["erlotinib"]},
        ])
        self.assertEqual(arms, [{"arm_name": "valid-arm", "interventions": ["erlotinib"]}])


class MariposaFixtureTest(TestCase):
    """PMID/studio MARIPOSA: amivantamab+lazertinib è il braccio sperimentale;
    osimertinib e lazertinib in monoterapia sono comparatori separati."""

    def _arms(self):
        return normalize_source_arms([
            {"arm_name": "amivantamab+lazertinib", "interventions": ["amivantamab", "lazertinib"]},
            {"arm_name": "osimertinib", "interventions": ["osimertinib"]},
            {"arm_name": "lazertinib", "interventions": ["lazertinib"]},
        ])

    def test_claim_amivantamab_lazertinib_is_exact_match(self):
        claim = claim_components_from_object("amivantamab + lazertinib")
        self.assertEqual(match_claim_to_arms(claim, self._arms()), "exact")

    def test_osimertinib_comparator_is_not_merged_into_experimental_arm(self):
        """Il comparatore osimertinib non deve mai far diventare la claim
        amivantamab+lazertinib qualcosa di diverso da 'exact': i farmaci dei
        bracci comparatori restano isolati nel proprio braccio."""
        arms = self._arms()
        experimental_arm = next(arm for arm in arms if arm["arm_name"] == "amivantamab+lazertinib")
        self.assertNotIn("osimertinib", experimental_arm["interventions"])
        claim = claim_components_from_object("amivantamab + lazertinib")
        self.assertEqual(match_claim_to_arms(claim, arms), "exact")

    def test_claim_osimertinib_alone_matches_the_comparator_arm(self):
        claim = claim_components_from_object("osimertinib")
        self.assertEqual(match_claim_to_arms(claim, self._arms()), "exact")


class Mariposa2FixtureTest(TestCase):
    """MARIPOSA-2: tre bracci con sovrapposizioni parziali di farmaci."""

    def _arms(self):
        return normalize_source_arms([
            {"arm_name": "arm1", "interventions": ["amivantamab", "lazertinib", "carboplatin", "pemetrexed"]},
            {"arm_name": "arm2", "interventions": ["carboplatin", "pemetrexed"]},
            {"arm_name": "arm3", "interventions": ["amivantamab", "carboplatin", "pemetrexed"]},
        ])

    def test_claim_amivantamab_carboplatin_is_partial_match(self):
        claim = claim_components_from_object("amivantamab + carboplatin")
        self.assertEqual(match_claim_to_arms(claim, self._arms()), "partial")


class RelayFixtureTest(TestCase):
    """RELAY: erlotinib+ramucirumab contro erlotinib+placebo (comparatore)."""

    def _arms(self):
        return normalize_source_arms([
            {"arm_name": "erlotinib+ramucirumab", "interventions": ["erlotinib", "ramucirumab"]},
            {"arm_name": "erlotinib+placebo", "interventions": ["erlotinib", "placebo"]},
        ])

    def test_placebo_arm_keeps_only_erlotinib(self):
        arms = self._arms()
        placebo_arm = next(arm for arm in arms if arm["arm_name"] == "erlotinib+placebo")
        self.assertEqual(placebo_arm["interventions"], ["erlotinib"])

    def test_claim_erlotinib_ramucirumab_is_exact_match(self):
        claim = claim_components_from_object("erlotinib + ramucirumab")
        self.assertEqual(match_claim_to_arms(claim, self._arms()), "exact")


class MatchClaimToArmsTest(TestCase):
    def test_no_arms_is_unknown(self):
        claim = claim_components_from_object("erlotinib + ramucirumab")
        self.assertEqual(match_claim_to_arms(claim, []), "unknown")

    def test_no_overlap_is_no_match(self):
        arms = normalize_source_arms([{"arm_name": "arm1", "interventions": ["gefitinib"]}])
        claim = claim_components_from_object("erlotinib + ramucirumab")
        self.assertEqual(match_claim_to_arms(claim, arms), "no_match")
