from copy import deepcopy
import unittest
from benchmarks.mtb_evidence.evaluation.normalization_v1_4 import semantic_sha256, validate_runtime_fields
class V14NormalizationTests(unittest.TestCase):
 def setUp(self): self.base={"metadata":{"start_time":"a","end_time":"b","replica":1,"run_id":"x","run_key":"rk_x","elapsed_ms":1},"result":{"query_id":"A","primary_ranked_results":[{"claim_id":"c","bucket":"primary","score":1.0,"rank":1,"source":{"pmid":"1"},"qualifiers":{"scope":"x"}}]}}
 def test_runtime_only(self):
  x=deepcopy(self.base); x["metadata"].update(start_time="c",end_time="d",replica=2,run_id="y",run_key="rk_y",elapsed_ms=2); self.assertEqual(semantic_sha256(self.base),semantic_sha256(x))
 def test_bucket_score_rank_source_qualifier(self):
  for mutate in [lambda x:x["result"]["primary_ranked_results"][0].update(bucket="warning"),lambda x:x["result"]["primary_ranked_results"][0].update(score=2),lambda x:x["result"]["primary_ranked_results"][0].update(rank=2),lambda x:x["result"]["primary_ranked_results"][0]["source"].update(pmid="2"),lambda x:x["result"]["primary_ranked_results"][0]["qualifiers"].update(scope="y")]:
   x=deepcopy(self.base); mutate(x); self.assertNotEqual(semantic_sha256(self.base),semantic_sha256(x))
 def test_order_is_semantic(self):
  x=deepcopy(self.base); x["result"]["primary_ranked_results"].append({"claim_id":"d","bucket":"primary","score":.5,"rank":2}); y=deepcopy(x); y["result"]["primary_ranked_results"].reverse(); self.assertNotEqual(semantic_sha256(x),semantic_sha256(y))
 def test_unregistered_runtime_field(self):
  x=deepcopy(self.base); x["metadata"]["unexpected"]="x"
  with self.assertRaises(ValueError): validate_runtime_fields(x)
if __name__=="__main__": unittest.main()
