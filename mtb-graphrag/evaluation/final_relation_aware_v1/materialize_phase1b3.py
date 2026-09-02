"""Rebuild only Phase 1B.3 SourceUnit-derived artifacts from frozen cache."""
import os,json,hashlib,statistics,datetime,shutil
from pathlib import Path
from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache
O=Path(__file__).parent;D=O/'documents';S=O/'sourceunits';os.environ['DOCUMENT_GROUNDING_CACHE']=str(D/'canonical_cache')
def hs(b):return hashlib.sha256(b).hexdigest()
def jl(p):return [json.loads(x) for x in Path(p).read_text(encoding='utf8').splitlines() if x]
def main():
 docs=jl(D/'document_manifest.jsonl'); sc=jl(O/'rq3_scoring_unit_manifest.jsonl')
 by_key={(x['candidate_id'],x['document_id']):x for x in sc}
 cache=AuthorizedDocumentCache(root=D/'canonical_cache',network=False); su=[]
 old=S/'sourceunits.jsonl'; archive=S/'invalidated_pre_fix'; archive.mkdir(parents=True,exist_ok=True)
 if old.exists() and not (archive/'sourceunits.jsonl').exists(): shutil.copy2(old,archive/'sourceunits.jsonl')
 for x in docs:
  if x['resolution_class'] not in {'FULLTEXT','ABSTRACT_ONLY'}: continue
  score=by_key[(x['candidate_id'],x['document_id'])]; r=cache._cached_manifest(x['document_id'])
  if not isinstance(r,dict): raise RuntimeError(f"missing frozen cache manifest: {x['document_id']}")
  for i,u in enumerate(cache.source_units_for_record(dict(r))):
   z={'sample_partition':x['sample_partition'],'sample_index':x['sample_index'],'candidate_id':x['candidate_id'],'scoring_unit_id':score['scoring_unit_id'],'PMID':x['PMID'],'document_id':x['document_id'],'document_kind':x['document_kind'],'source_unit_id':u['source_unit_id'],'source_unit_type':u.get('unit_type'),'section':u.get('section'),'ordinal':i,'text':u.get('text'),'canonical_document_hash':x['canonical_document_hash']};z['sourceunit_hash']=hs(json.dumps(z,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode());su.append(z)
 out=S/'sourceunits.jsonl'; out.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in su),encoding='utf8')
 counts={x['scoring_unit_id']:0 for x in sc}
 for x in su: counts[x['scoring_unit_id']]+=1
 dup=sum(len({u['source_unit_id'] for u in [z for z in su if z['scoring_unit_id']==sid]}) != n for sid,n in counts.items() if n)
 full=sum(1 for x in su if x['document_kind']=='FULLTEXT'); abstract=sum(1 for x in su if x['document_kind']=='ABSTRACT_ONLY')
 m={'SOURCE_FREEZE_SEAL_SHA256':hs((D/'source_freeze_seal.json').read_bytes()),'RQ3_SCORING_UNIT_MANIFEST_SHA256':hs((O/'rq3_scoring_unit_manifest.jsonl').read_bytes()),'available_scoring_units':sum(x['document_available'] for x in sc),'error_scoring_units':sum(not x['document_available'] for x in sc),'total_sourceunits':len(su),'fulltext_sourceunits':full,'abstract_sourceunits':abstract,'available_with_zero_sourceunits':sum(x['document_available'] and counts[x['scoring_unit_id']]==0 for x in sc),'duplicate_source_unit_ids_within_document':dup,'sourceunits_sha256':hs(out.read_bytes()),'parser':'AuthorizedDocumentCache.source_units_for_record','generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'network_calls':0}
 manifest=S/'sourceunit_manifest.json'; manifest.write_text(json.dumps(m,indent=2)+'\n',encoding='utf8')
 seal={'inputs':{'source_freeze_seal':m['SOURCE_FREEZE_SEAL_SHA256'],'scoring':m['RQ3_SCORING_UNIT_MANIFEST_SHA256'],'sourceunits':m['sourceunits_sha256'],'manifest':hs(manifest.read_bytes())},'network_calls_after_document_freeze':0,'canonical_parser_only':True}
 (S/'sourceunit_freeze_seal.json').write_text(json.dumps(seal,indent=2)+'\n',encoding='utf8')
 print(json.dumps({**m,'sourceunit_manifest_sha256':hs(manifest.read_bytes()),'sourceunit_freeze_sha256':hs((S/'sourceunit_freeze_seal.json').read_bytes())}))
if __name__=='__main__':main()
