from unittest import TestCase

from backend.pipeline.agents.trial_dedup import deduplicate_trials


class DeduplicateTrialsTest(TestCase):
    def test_same_nct_id_from_multiple_matched_drugs_is_merged_into_one_record(self):
        """Riproduce il caso osservato nel run reale: NCT05047250 compare due
        volte nel risultato grezzo (una riga per farmaco corrispondente).
        Deve restare un solo record, con entrambi i farmaci uniti."""
        records = [
            {"nct_id": "NCT05047250", "title": "Trial A", "phase": "3", "status": "Recruiting", "drug_tested": "amivantamab"},
            {"nct_id": "NCT05047250", "title": "Trial A", "phase": "3", "status": "Recruiting", "drug_tested": "lazertinib"},
            {"nct_id": "NCT06000000", "title": "Trial B", "phase": "2", "status": "Recruiting", "drug_tested": "osimertinib"},
        ]
        deduplicated = deduplicate_trials(records)
        nct_ids = [record["nct_id"] for record in deduplicated]
        self.assertEqual(nct_ids.count("NCT05047250"), 1)
        self.assertEqual(len(deduplicated), 2)
        merged = next(record for record in deduplicated if record["nct_id"] == "NCT05047250")
        self.assertIn("amivantamab", merged["drug_tested"])
        self.assertIn("lazertinib", merged["drug_tested"])

    def test_records_without_nct_id_pass_through_unmerged(self):
        records = [{"nct_id": None, "title": "Untitled trial", "phase": None, "status": None, "drug_tested": None}]
        self.assertEqual(deduplicate_trials(records), records)

    def test_no_duplicates_leaves_order_and_content_unchanged(self):
        records = [
            {"nct_id": "NCT01", "title": "A", "phase": "1", "status": "Recruiting", "drug_tested": "drugA"},
            {"nct_id": "NCT02", "title": "B", "phase": "2", "status": "Active", "drug_tested": "drugB"},
        ]
        self.assertEqual(deduplicate_trials(records), records)
