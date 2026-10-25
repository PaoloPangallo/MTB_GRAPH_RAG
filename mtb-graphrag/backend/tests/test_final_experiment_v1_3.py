import unittest
from benchmarks.mtb_evidence.evaluation.metrics_v1_3 import score_query, macro_bucket_accuracy

class V13MetricTests(unittest.TestCase):
    def test_perfect_and_wrong_bucket(self):
        self.assertEqual(score_query([{'claim_id':'c1','bucket':'primary','evaluable':True}], [{'claim_id':'c1','bucket':'primary'}])['bucket_accuracy'], 1.0)
        self.assertEqual(score_query([{'claim_id':'c1','bucket':'primary','evaluable':True}], [{'claim_id':'c1','bucket':'warning'}])['wrong_bucket_count'], 1)
    def test_missing_extra(self):
        s=score_query([{'claim_id':'c1','bucket':'primary','evaluable':True}], [{'claim_id':'c2','bucket':'warning'}])
        self.assertEqual((s['missing_claim_count'],s['extra_claim_count']), (1,1))
    def test_empty_policy_and_provenance(self):
        s=score_query([{'expected_abstention':True}], []); self.assertEqual(s['bucket_accuracy'],1.0)
        s=score_query([{'candidate_kind':'provenance_container','claim_id':'p'}], []); self.assertEqual(s['provenance_container_count'],1)
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError): score_query([{'claim_id':'c','bucket':'primary','evaluable':True},{'claim_id':'c','bucket':'warning','evaluable':True}], [])
    def test_macro(self): self.assertEqual(macro_bucket_accuracy([{'bucket_accuracy':1.0},{'bucket_accuracy':0.0}]),0.5)
