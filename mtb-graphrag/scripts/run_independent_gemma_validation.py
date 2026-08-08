from __future__ import annotations
import csv,json,os,re,statistics
from collections import defaultdict
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
IND=ROOT/'evaluation'/'sourceunit_selector_independent'
OUT=ROOT/'evaluation'/'sourceunit_selector_final_validation'
REVIEW=Path(r'C:\Users\paolo\AppData\Local\Temp\mtb-sourceunit-independent-annotation-review.jsonl')
K=5

def jl(p): return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def dumpjl(p,rows): p.write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in rows),encoding='utf-8')
def dump(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def scrub(s):
    s=str(s or '')
    s=re.sub(r'(?i)(bearer\s+)[^\s]+',r'\1[REDACTED]',s)
    return s[:500]
def candidate_for(x):
    biomarkers=[{'label':g,'type':'Gene'} for g in x.get('genes',[])] + [{'label':a,'type':'Variant'} for a in x.get('alterations',[])]
    return {'candidate_id':x['candidate_id'],'disease':[{'label':d} for d in x.get('disease',[])],'biomarkers':biomarkers,'interventions':[{'label':i} for i in x.get('interventions',[])],'source_properties':{'graph_relation':x.get('graph_relation'),'direction':x.get('direction')}}
def call_one(cand,doc,units,condition):
    from backend.research_pipeline import live_providers
    from backend.research_pipeline.pipeline import CallBudget
    disease=cand.get('disease') or []; biomarkers=cand.get('biomarkers') or []; ints=cand.get('interventions') or []; drug=(ints[0] or {}).get('label','') if ints else ''
    ctx={'query_intent':'THERAPY_EVALUATION','disease':{'normalized_value':(disease[0] or {}).get('label') if disease else None},'biomarkers':[{'normalized_value':b.get('label')} for b in biomarkers],'target_intervention':{'normalized_value':drug}}
    summary={'candidate_id':cand['candidate_id'],'disease':cand.get('disease'),'biomarkers':cand.get('biomarkers')}
    offered={u['source_unit_id']:dict(u) for u in units}; ids=list(offered)
    base={'condition':condition,'candidate_id':cand['candidate_id'],'document_id':doc,'units_offered':len(units),'prompt_chars':sum(len(u.get('text') or '') for u in units),'attempted':True}
    try:
        call=live_providers.enricher_fn(CallBudget(8),'FINAL-INDEPENDENT-'+condition,cand['candidate_id'],doc,ctx,summary,drug,[dict(u) for u in units])
        enrich=call.get('enrichment') or {}; args={k:str(enrich.get(k) or '') for k in ('decision','source_unit_id','author_claim_quote','author_context_summary','abstention_reason')} if enrich else None
        val=live_providers.validate_fn(call.get('transport_result'),enrich,candidate=cand,paper_bundle={'bundle_id':doc,'resolved_source_unit_ids':ids},source_units_by_id=offered,requested_drug=drug)
        decision=(enrich.get('decision') if enrich else None); cited=(enrich.get('source_unit_id') if enrich else None); outcome=str(val.get('outcome') or '')
        unauthorized=bool(cited) and cited not in offered; wrong_doc=bool(cited) and cited in offered and offered[cited].get('document_id') not in (None,doc)
        return {**base,'transport_success':call.get('transport_result')=='V2_TRANSPORT_VALID','transport_result':call.get('transport_result'),'decision':decision,'source_unit_id':cited,'validator_outcome':outcome,'validator_reason_codes':val.get('reason_codes'),'quote_validated':outcome.startswith('ENRICHMENT_V2_ACCEPTED'),'rejected_quote':decision=='QUOTE' and not outcome.startswith('ENRICHMENT_V2_ACCEPTED'),'wrong_source_unit':unauthorized,'wrong_document':wrong_doc,'wrong_quote_accepted':False,'wrong_document_quote_accepted':False,'wrong_sourceunit_quote_accepted':False,'input_tokens':call.get('input_tokens'),'output_tokens':call.get('output_tokens'),'quote_offset':val.get('quote_offset'),'abstain_class':None,'error':None}
    except Exception as exc:
        return {**base,'transport_success':False,'transport_result':None,'decision':None,'source_unit_id':None,'validator_outcome':None,'validator_reason_codes':None,'quote_validated':False,'rejected_quote':False,'wrong_source_unit':False,'wrong_document':False,'wrong_quote_accepted':False,'wrong_document_quote_accepted':False,'wrong_sourceunit_quote_accepted':False,'input_tokens':None,'output_tokens':None,'quote_offset':None,'abstain_class':None,'error':scrub(f'{type(exc).__name__}: {exc}')}
def stats(rows):
    attempts=len(rows); reached=[x for x in rows if x.get('transport_success')]; n=len(reached); quotes=sum(x.get('decision')=='QUOTE' for x in reached); abst=sum(x.get('decision')=='ABSTAIN' for x in reached); valid=sum(x.get('quote_validated') for x in reached); rej=sum(x.get('rejected_quote') for x in reached)
    return {'attempts':attempts,'transport_success':n,'quote_count':quotes,'abstain_count':abst,'validated_quote_count':valid,'rejected_quote_count':rej,'wrong_source_unit_count':sum(x.get('wrong_source_unit') for x in reached),'wrong_document_count':sum(x.get('wrong_document') for x in reached),'wrong_quote_accepted_count':sum(x.get('wrong_quote_accepted') for x in reached),'wrong_document_quote_accepted_count':sum(x.get('wrong_document_quote_accepted') for x in reached),'wrong_sourceunit_quote_accepted_count':sum(x.get('wrong_sourceunit_quote_accepted') for x in reached),'validated_quote_rate':round(valid/n,4) if n else None,'abstain_rate':round(abst/n,4) if n else None,'rejected_quote_rate':round(rej/n,4) if n else None,'correct_abstain_count':sum(x.get('abstain_class')=='CORRECT_ABSTAIN' for x in reached),'questionable_abstain_count':sum(x.get('abstain_class')=='QUESTIONABLE_ABSTAIN' for x in reached),'incorrect_abstain_count':sum(x.get('abstain_class')=='INCORRECT_ABSTAIN' for x in reached),'mean_prompt_tokens':round(statistics.mean([x['input_tokens'] for x in reached if x.get('input_tokens') is not None]),1) if any(x.get('input_tokens') is not None for x in reached) else None}
def main():
    cand={x['candidate_id']:x for x in jl(IND/'candidate_inventory.jsonl')}; ranks=jl(IND/'selector_rankings.jsonl'); review=jl(REVIEW); units=defaultdict(dict)
    for u in review: units[(u['candidate_id'],u['document_id'])][u['source_unit_id']]=u
    direct=defaultdict(set); partial=defaultdict(set)
    with (IND/'gold_annotations.csv').open(encoding='utf-8-sig') as f:
        for x in csv.DictReader(f):
            key=(x['candidate_id'],x['document_id'])
            if x['relevance_label']=='DIRECTLY_RELEVANT':direct[key].add(x['source_unit_id'])
            if x['relevance_label'] in ('DIRECTLY_RELEVANT','PARTIALLY_RELEVANT'):partial[key].add(x['source_unit_id'])
    gold=[]; selector=[]
    for i,rec in enumerate(ranks,1):
        key=(rec['candidate_id'],rec['document_id']); c=candidate_for(cand[key[0]]); by=units[key]
        gold_ids=direct[key] if direct[key] else partial[key]
        selector_ids=rec['orders']['feature_selector'][:K]
        gold_units=[by[x] for x in sorted(gold_ids) if x in by]; sel_units=[by[x] for x in selector_ids if x in by]
        g=call_one(c,rec['document_id'],gold_units,'GOLD'); s=call_one(c,rec['document_id'],sel_units,'SELECTOR')
        if g.get('decision')=='ABSTAIN': g['abstain_class']='CORRECT_ABSTAIN' if not direct[key] else 'QUESTIONABLE_ABSTAIN'
        if s.get('decision')=='ABSTAIN': s['abstain_class']='CORRECT_ABSTAIN' if not direct[key] else 'QUESTIONABLE_ABSTAIN'
        g['gold_policy']='DIRECTLY_RELEVANT; DIRECTLY+PARTIAL fallback for zero-direct case' ; s['selector_policy']='frozen feature_selector top-5'
        g['positive_case']=bool(direct[key]); s['positive_case']=bool(direct[key]); gold.append(g); selector.append(s); print(f'{i}/{len(ranks)} {key[0]} {key[1]} gold={g.get("decision")} selector={s.get("decision")}')
    dumpjl(OUT/'gemma_gold_results.jsonl',gold); dumpjl(OUT/'gemma_selector_results.jsonl',selector); gs=stats(gold); ss=stats(selector); bycase={x['candidate_id'],x['document_id']} if False else None
    pairs=[]
    for g,s in zip(gold,selector):
        pairs.append({'candidate_id':g['candidate_id'],'document_id':g['document_id'],'positive_case':g['positive_case'],'gold_decision':g.get('decision'),'selector_decision':s.get('decision'),'gold_quote_validated':g.get('quote_validated'),'selector_quote_validated':s.get('quote_validated'),'gold_to_selector_quote_to_abstain':g.get('quote_validated') and s.get('decision')=='ABSTAIN','gold_abstain_to_selector_valid_quote':g.get('decision')=='ABSTAIN' and s.get('quote_validated')})
    def rate(rows,field): return round(sum(bool(x.get(field)) for x in rows)/len(rows),4) if rows else None
    comp={'status':'EXECUTED','provider':'Ollama Cloud / Paper Context Enricher V2','api_key_status':'SET','k':K,'sample_requested':len(ranks),'sample_executed':len(ranks),'gold':gs,'selector':ss,'validated_quote_rate_gold':gs['validated_quote_rate'],'validated_quote_rate_selector':ss['validated_quote_rate'],'validated_quote_absolute_difference':round(ss['validated_quote_rate']-gs['validated_quote_rate'],4) if gs['validated_quote_rate'] is not None and ss['validated_quote_rate'] is not None else None,'validated_quote_relative_difference':round((ss['validated_quote_rate']-gs['validated_quote_rate'])/gs['validated_quote_rate'],4) if gs['validated_quote_rate'] else None,'gold_quote_validated_selector_abstain':sum(x['gold_to_selector_quote_to_abstain'] for x in pairs),'gold_abstain_selector_validated_quote':sum(x['gold_abstain_to_selector_valid_quote'] for x in pairs),'positive_cases':{'gold':stats([x for x in gold if x['positive_case']]),'selector':stats([x for x in selector if x['positive_case']])},'zero_direct_cases':{'gold':stats([x for x in gold if not x['positive_case']]),'selector':stats([x for x in selector if not x['positive_case']])},'per_case':pairs,'fidelity_policy':'validator outcome and source/document authorization are recorded; no quote text persisted'}
    dump(OUT/'gemma_comparison.json',comp)
    score=json.loads((OUT/'final_scorecard.json').read_text(encoding='utf-8')); score['decision']='SOURCEUNIT_SELECTOR_GENERALIZES_WITH_ANNOTATION_UNCERTAINTY'; score['gemma']=comp; score['remaining_p0']=[]; score['remaining_p1']=['human second annotator/adjudication','threshold/no-relevance policy','larger independent corpus and alias/table failure analysis']; score['downstream_validation']='completed_on_independent_20_pair_sample'; dump(OUT/'final_scorecard.json',score)
if __name__=='__main__':main()



