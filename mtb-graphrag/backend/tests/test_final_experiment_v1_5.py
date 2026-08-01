from copy import deepcopy
import unittest
from benchmarks.mtb_evidence.evaluation.normalization_v1_5 import semantic_sha256,validate_runtime_fields
class V15NormalizationTests(unittest.TestCase):
 def setUp(self): self.b={"metadata":{"start_time":"a","end_time":"b","replica":1,"run_id":"x","run_key":"rk_x","elapsed_ms":1},"result":{"latency_ms":{"total":1},"observability":{"latency_ms":{"total":1}},"payload":{"latency_ms":{"total":1},"primary_ranked_results":[{"claim_id":"c","bucket":"primary","score":1,"rank":1,"source":{"pmid":"1","locator":"a"},"qualifiers":{"q":"a"}}]}}}
 def test_latency_paths_runtime_only(self):
  for path in [('result','latency_ms'),('result','observability','latency_ms'),('result','payload','latency_ms')]:
   x=deepcopy(self.b);c=x
   for k in path[:-1]:c=c[k]
   c[path[-1]]={'total':99};self.assertEqual(semantic_sha256(self.b),semantic_sha256(x))
 def test_all_latency_together(self):
  x=deepcopy(self.b);x['result']['latency_ms']={'total':2};x['result']['observability']['latency_ms']={'total':3};x['result']['payload']['latency_ms']={'total':4};self.assertEqual(semantic_sha256(self.b),semantic_sha256(x))
 def test_optional_path(self):
  x=deepcopy(self.b);del x['result']['observability'];self.assertNotEqual(semantic_sha256(self.b),semantic_sha256(x))
 def test_semantic_mutations(self):
  for fn in [lambda x:x['result']['payload']['primary_ranked_results'][0].update(bucket='warning'),lambda x:x['result']['payload']['primary_ranked_results'][0].update(score=2),lambda x:x['result']['payload']['primary_ranked_results'][0].update(rank=2),lambda x:x['result']['payload']['primary_ranked_results'][0]['source'].update(pmid='2'),lambda x:x['result']['payload']['primary_ranked_results'][0]['qualifiers'].update(q='b')]:
   x=deepcopy(self.b);fn(x);self.assertNotEqual(semantic_sha256(self.b),semantic_sha256(x))
  x=deepcopy(self.b);x['result']['payload']['primary_ranked_results'].append({'claim_id':'d','bucket':'primary'});y=deepcopy(x);y['result']['payload']['primary_ranked_results'].reverse();self.assertNotEqual(semantic_sha256(x),semantic_sha256(y))
 def test_unknown_runtime(self):
  x=deepcopy(self.b);x['metadata']['unexpected']='x'
  with self.assertRaises(ValueError):validate_runtime_fields(x)
if __name__=='__main__':unittest.main()
