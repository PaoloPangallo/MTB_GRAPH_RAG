from copy import deepcopy
import unittest
from benchmarks.mtb_evidence.evaluation.metadata_contract_v1_6 import build_metadata,validate_metadata,REGISTRY,PROTOCOL_VALUES
from benchmarks.mtb_evidence.evaluation.normalization_v1_6 import semantic_sha256
class V16ContractTests(unittest.TestCase):
 def setUp(self):
  self.md=build_metadata(**PROTOCOL_VALUES,protocol_commit='p',protocol_tag='t',corpus_version='c',corpus_hash='h',gate_version='g',retriever_version='r',scoring_version='s',query_id='q',benchmark_id='b',gold_read_count=0,os='Windows',python='3.12',host='h',run_id='id',run_key='rk',replica=1,start_time='a',end_time='b',elapsed_ms=1)
  self.raw={'metadata':self.md,'result':{'latency_ms':{'total':1},'observability':{'latency_ms':{'total':1}},'payload':{'latency_ms':{'total':1},'primary_ranked_results':[{'claim_id':'c','bucket':'primary','score':1,'rank':1,'source':{'pmid':'1'},'qualifiers':{'q':'a'}}]}}}
 def test_envelope_registry_parity(self): validate_metadata(self.md);self.assertEqual(set(self.md),set(REGISTRY))
 def test_protocol_mismatch(self):
  for k in PROTOCOL_VALUES:
   x=deepcopy(self.raw);x['metadata'][k]='wrong'
   with self.assertRaises(ValueError):validate_metadata(x['metadata'])
 def test_runtime_os_python(self):
  x=deepcopy(self.raw);x['metadata']['os']='Linux';self.assertEqual(semantic_sha256(self.raw),semantic_sha256(x));x['metadata']['python']='3.13';self.assertEqual(semantic_sha256(self.raw),semantic_sha256(x))
 def test_unknown(self):
  x=deepcopy(self.md);x['new']='x'
  with self.assertRaises(ValueError):validate_metadata(x)
 def test_latency_and_semantic_mutations(self):
  for path in [('result','latency_ms'),('result','observability','latency_ms'),('result','payload','latency_ms')]:
   x=deepcopy(self.raw);c=x
   for k in path[:-1]:c=c[k]
   c[path[-1]]={'total':9};self.assertEqual(semantic_sha256(self.raw),semantic_sha256(x))
  for fn in [lambda x:x['result']['payload']['primary_ranked_results'][0].update(bucket='warning'),lambda x:x['result']['payload']['primary_ranked_results'][0].update(score=2),lambda x:x['result']['payload']['primary_ranked_results'][0].update(rank=2),lambda x:x['result']['payload']['primary_ranked_results'][0]['source'].update(pmid='2'),lambda x:x['result']['payload']['primary_ranked_results'][0]['qualifiers'].update(q='b')]:
   x=deepcopy(self.raw);fn(x);self.assertNotEqual(semantic_sha256(self.raw),semantic_sha256(x))
  x=deepcopy(self.raw);x['result']['payload']['primary_ranked_results'].append({'claim_id':'d'});y=deepcopy(x);y['result']['payload']['primary_ranked_results'].reverse();self.assertNotEqual(semantic_sha256(x),semantic_sha256(y))
if __name__=='__main__':unittest.main()
