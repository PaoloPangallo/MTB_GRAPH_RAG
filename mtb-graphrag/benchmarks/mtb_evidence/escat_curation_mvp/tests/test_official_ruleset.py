from __future__ import annotations

import json
from pathlib import Path
import unittest

from benchmarks.mtb_evidence.escat_curation_mvp.official_ruleset import (
    EXPECTED_SOURCE_SHA256,
    compare_pilot_drafts_read_only,
    load_research_ruleset,
    verify_source,
)


class OfficialRulesetResearchDraftTests(unittest.TestCase):
    def test_source_hash_and_research_classification_are_explicit(self) -> None:
        ruleset = load_research_ruleset()
        self.assertEqual(ruleset.status, "RESEARCH_DRAFT")
        self.assertFalse(ruleset.available)
        self.assertEqual(ruleset.source["sha256"], EXPECTED_SOURCE_SHA256)
        self.assertEqual(verify_source().sha256, EXPECTED_SOURCE_SHA256)

    def test_rules_have_dual_page_locators_and_no_implicit_figures(self) -> None:
        ruleset = load_research_ruleset()
        self.assertEqual(len(ruleset.rules), 11)
        self.assertTrue(all(rule.source_locators and all(locator["page_pdf"] for locator in rule.source_locators) for rule in ruleset.rules))
        self.assertTrue(all(rule.source_locators and all(locator["page_journal"] for locator in rule.source_locators) for rule in ruleset.rules))
        self.assertTrue(all(locator["figure"] is None for rule in ruleset.rules for locator in rule.source_locators))
        self.assertTrue(all(rule.requirements for rule in ruleset.rules))
        self.assertTrue(
            all(
                item["manual_interpretation_required"] is True
                for rule in ruleset.rules
                for item in rule.requirements
                if item["kind"] == "condition"
            )
        )

    def test_ambiguous_formulations_are_kept_outside_rules(self) -> None:
        ruleset = load_research_ruleset()
        ambiguity_path = Path(ruleset.ambiguity_registry_path)
        ambiguities = json.loads(ambiguity_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(ambiguities["ambiguities"]), 1)
        self.assertTrue(all(item["status"] == "REQUIRES_MANUAL_INTERPRETATION" for item in ambiguities["ambiguities"]))

    def test_read_only_comparison_does_not_select_or_assign(self) -> None:
        result = compare_pilot_drafts_read_only()
        self.assertEqual(result["draft_count"], 15)
        self.assertTrue(all(item["selected_rule_ids"] == [] for item in result["drafts"]))
        self.assertTrue(all(item["assigned_tier"] is None for item in result["drafts"]))
        self.assertTrue(all(item["assigned_subtier"] is None for item in result["drafts"]))
        self.assertTrue(all(item["assessment_status"] == "INCOMPLETE" for item in result["drafts"]))

    def test_research_ruleset_is_not_treated_as_clinically_validated(self) -> None:
        ruleset = load_research_ruleset()
        restored = type(ruleset).from_dict(ruleset.to_dict())
        self.assertEqual(restored.status, "RESEARCH_DRAFT")
        self.assertFalse(restored.available)


if __name__ == "__main__":
    unittest.main()
