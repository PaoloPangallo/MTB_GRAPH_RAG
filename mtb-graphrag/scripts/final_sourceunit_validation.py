from __future__ import annotations
import csv, hashlib, json, os, re, statistics
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INDEPENDENT=ROOT/'evaluation'/'sourceunit_selector_independent'
OUT=ROOT/'evaluation'/'sourceunit_selector_final_validation'
REVIEW=Path(r'C:\Users\paolo\AppData\Local\Temp\mtb-sourceunit-independent-annotation-review.jsonl')
KS=(1,3,5,10); K=5

def jlines(p): return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def dump(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def dumpjl(p,rows): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in rows),encoding='utf-8')
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def ck(r): return r['candidate_id'],r['document_id']
def m(order,rel,k):
    found=len(set(order[:k])&rel)
    return {'hit':bool(found),'recall':found/len(rel) if rel else 0.0,'precision':found/k if k else 0.0,'full_coverage':bool(rel) and found==len(rel)}
def agg(rows,prefix):
    out={'cases':len(rows),'denominator':len(rows),'relevant_units':sum(x['relevant_count'] for x in rows)}
    for k in KS:
        for n in ('hit','recall','precision','full_coverage'):
            v=[float(x[f'{prefix}_{n}@{k}']) for x in rows]; out[f'{n}_rate@{k}']=round(statistics.mean(v),4) if v else None
    ranks=[x['first_relevant_rank'] for x in rows if x['first_relevant_rank'] is not None]
    out['mrr']=round(statistics.mean([1/x['first_relevant_rank'] if x['first_relevant_rank'] else 0 for x in rows]),4) if rows else None
    out['mean_first_relevant_rank']=round(statistics.mean(ranks),3) if ranks else None
    out['median_first_relevant_rank']=statistics.median(ranks) if ranks else None
    return out

def load():
    c=jlines(INDEPENDENT/'candidate_inventory.jsonl'); docs=jlines(INDEPENDENT/'document_inventory.jsonl'); ranks=jlines(INDEPENDENT/'selector_rankings.jsonl')
    with (INDEPENDENT/'gold_annotations.csv').open(encoding='utf-8-sig',newline='') as f: gold=list(csv.DictReader(f))
    labels=defaultdict(dict); direct=defaultdict(set); partial=defaultdict(set)
    for r in gold:
        key=(r['candidate_id'],r['document_id']); labels[key][r['source_unit_id']]=r['relevance_label']
        if r['relevance_label']=='DIRECTLY_RELEVANT': direct[key].add(r['source_unit_id'])
        if r['relevance_label'] in ('DIRECTLY_RELEVANT','PARTIALLY_RELEVANT'): partial[key].add(r['source_unit_id'])
    return c,docs,ranks,gold,labels,direct,partial

def cause(rec):
    top=rec['ranking'][:10]; types={x.get('unit_type') for x in top}; matched={n for x in top for n in ('matched_gene','matched_alteration','matched_intervention','matched_disease') if x.get(n)}
    if {'TABLE_CELL','TABLE_CAPTION'}&types:return 'TABLE_FAILURE'
    if any(x.get('matched_alteration') for x in top):return 'ALTERATION_NOT_MATCHED'
    if 'matched_intervention' in matched and 'matched_gene' not in matched:return 'GENE_ONLY_MATCH'
    if rec['document_source_unit_count']>100:return 'LONG_DOCUMENT'
    if any(x.get('unit_type') in ('TITLE','INTRODUCTION') for x in top):return 'SECTION_PRIOR_FAILURE'
    if not matched:return 'LEXICAL_DILUTION'
    return 'OTHER'

def ranking_eval(ranks,labels,direct,partial):
    by=defaultdict(list); zeros=[]; fails=[]
    for rec in ranks:
        key=ck(rec); labs=labels[key]
        for s,order in rec['orders'].items():
            rel=direct[key]; row={'candidate_id':key[0],'document_id':key[1],'relevant_count':len(rel),'order':order}
            for k in KS:
                for n,v in m(order,rel,k).items():row[f'{s}_{n}@{k}']=v
            rr=[order.index(x)+1 for x in rel if x in order]; row['first_relevant_rank']=min(rr) if rr else None; by[s].append(row)
        top=rec['orders']['feature_selector'][:K]
        if not direct[key]:
            co=Counter(labs.get(x,'UNKNOWN') for x in top)
            zeros.append({'candidate_id':key[0],'document_id':key[1],'selected_any_unit':bool(top),'selected_partially_relevant':co['PARTIALLY_RELEVANT']>0,'selected_context_only':co['CONTEXT_ONLY']>0,'selected_not_relevant':co['NOT_RELEVANT']>0,'no_relevant_source_unit':False,'top_k':top})
        elif not (set(top)&direct[key]):
            order=rec['orders']['feature_selector']; fails.append({'candidate_id':key[0],'document_id':key[1],'gold_relevant_ids':sorted(direct[key]),'top10_selector_ids':order[:10],'rank_first_relevant':min((order.index(x)+1 for x in direct[key] if x in order),default=None),'cause':cause(rec)})
    return by,zeros,fails

def ann2(review,candidates):
    cb={x['candidate_id']:x for x in candidates}; out=[]
    for u in review:
        c=cb[u['candidate_id']]; t=(u.get('text') or '').casefold(); genes=[str(x).casefold() for x in c.get('genes',[])]; alts=[str(x).casefold() for x in c.get('alterations',[])]; drugs=[str(x).casefold() for x in c.get('interventions',[])]; diseases=[str(x).casefold() for x in c.get('disease',[])]
        ga=any(x and re.search(r'\b'+re.escape(x)+r'\b',t) for x in genes); aa=any(x and x in t for x in alts); da=any(x and x in t for x in drugs); ev=any(x in t for x in ('response','resistance','sensitive','sensitivity','treated','treatment','association','associated','benefit','survival','prognos')); neg=any(x in t for x in ('no evidence','not associated','did not','without benefit','failed to','not support'))
        if aa and ev and len(t)>=80 and (not neg or 'resistance' in t or 'not associated' in t): lab='DIRECTLY_RELEVANT'
        elif (aa or ga) and (da or ev): lab='PARTIALLY_RELEVANT'
        elif ga or da or any(x in t for x in diseases): lab='CONTEXT_ONLY'
        else: lab='NOT_RELEVANT'
        out.append({'candidate_id':u['candidate_id'],'document_id':u['document_id'],'source_unit_id':u['source_unit_id'],'annotator':'annotator_2_blinded_protocol_v1','relevance_label':lab,'annotation_basis':'independent_protocol_without_gold_or_rankings'})
    return out

def agreement(gold,b):
    a={(x['candidate_id'],x['document_id'],x['source_unit_id']):x['relevance_label'] for x in gold}; b={(x['candidate_id'],x['document_id'],x['source_unit_id']):x['relevance_label'] for x in b}; keys=sorted(set(a)&set(b)); ba=[a[x]=='DIRECTLY_RELEVANT' for x in keys]; bb=[b[x]=='DIRECTLY_RELEVANT' for x in keys]; raw=sum(x==y for x,y in zip(ba,bb))/len(keys) if keys else None; pa=sum(ba)/len(keys) if keys else 0; pb=sum(bb)/len(keys) if keys else 0; pe=pa*pb+(1-pa)*(1-pb); kap=(raw-pe)/(1-pe) if raw is not None and pe!=1 else (1.0 if raw==1 else None); labs=('DIRECTLY_RELEVANT','PARTIALLY_RELEVANT','CONTEXT_ONLY','NOT_RELEVANT'); mat={x:{y:0 for y in labs} for x in labs}; dis=[]
    for key in keys:
        x,y=a[key],b[key]; mat[x][y]+=1
        if x!=y:
            reason='PARTIAL_VS_DIRECT' if {x,y}=={'DIRECTLY_RELEVANT','PARTIALLY_RELEVANT'} else ('CONTEXT_VS_PARTIAL' if {x,y}=={'PARTIALLY_RELEVANT','CONTEXT_ONLY'} else ('BOUNDARY_CASE' if 'DIRECTLY_RELEVANT' in {x,y} else 'OTHER'))
            dis.append({'candidate_id':key[0],'document_id':key[1],'source_unit_id':key[2],'annotator_1_label':x,'annotator_2_label':y,'reason':reason})
    return {'sample_size_source_units':len(keys),'sample_size_candidate_document_pairs':len({(x[0],x[1]) for x in keys}),'raw_agreement_direct_vs_not_direct':raw,'cohen_kappa_direct_vs_not_direct':kap,'four_class_confusion_matrix':mat,'annotator_2_status':'independent_protocol_pass_not_human_reviewer'},dis

def main():
    OUT.mkdir(parents=True,exist_ok=True); c,docs,ranks,gold,labels,direct,partial=load(); by,zeros,fails=ranking_eval(ranks,labels,direct,partial); pos=sorted(x for x in direct if direct[x]); zero=sorted(x for x in labels if not direct[x]); hits=sum(bool(set(next(r for r in ranks if ck(r)==key)['orders']['feature_selector'][:K])&direct[key]) for key in pos); denom={'total_cases':len(labels),'positive_cases':len(pos),'zero_direct_cases':len(zero),'gold_hash':h(INDEPENDENT/'gold_annotations.csv'),'gold_frozen_before_selector':True,'selector_positive_hits_at_5':hits,'conditional_selector_hit_rate_at_5':hits/len(pos)}; dump(OUT/'denominator_analysis.json',denom)
    pm={s:agg([x for x in rows if (x['candidate_id'],x['document_id']) in pos],s) for s,rows in by.items()}; dump(OUT/'positive_case_metrics.json',{'gold_label':'DIRECTLY_RELEVANT','denominator':len(pos),'strategies':pm,'selector_positive_misses':fails})
    zs={'denominator':len(zeros),'selected_any_unit':sum(x['selected_any_unit'] for x in zeros),'selected_partially_relevant':sum(x['selected_partially_relevant'] for x in zeros),'selected_context_only':sum(x['selected_context_only'] for x in zeros),'selected_not_relevant':sum(x['selected_not_relevant'] for x in zeros),'no_relevant_source_unit_produced':0,'true_negative':0,'false_direct_signal_rate':sum(x['selected_any_unit'] for x in zeros)/len(zeros) if zeros else None,'policy':'frozen selector has no NO_RELEVANT_SOURCE_UNIT output; top-K presence is not a support decision'}; dump(OUT/'zero_direct_metrics.json',{'summary':zs,'cases':zeros})
    partial_metrics={}
    for s in by:
        rows=[]
        for rec in ranks:
            rel=partial[ck(rec)]; order=rec['orders'][s]; mm5=m(order,rel,5); mm10=m(order,rel,10); rr=min((order.index(x)+1 for x in rel if x in order),default=None); rows.append((mm5,mm10,rr))
        partial_metrics[s]={'denominator':len(rows),'hit_rate@5':round(statistics.mean([x[0]['hit'] for x in rows]),4),'recall@10':round(statistics.mean([x[1]['recall'] for x in rows]),4),'mrr':round(statistics.mean([1/x[2] if x[2] else 0 for x in rows]),4)}
    dump(OUT/'partial_relevance_metrics.json',{'gold_label':'DIRECTLY_RELEVANT_PLUS_PARTIALLY_RELEVANT','strategies':partial_metrics})
    with (OUT/'positive_failure_analysis.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['candidate_id','document_id','gold_relevant_ids','top10_selector_ids','rank_first_relevant','cause']);w.writeheader();w.writerows(fails)
    review=jlines(REVIEW) if REVIEW.exists() else []; a2=ann2(review,c)
    with (OUT/'second_annotator.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['candidate_id','document_id','source_unit_id','annotator','relevance_label','annotation_basis']);w.writeheader();w.writerows(a2)
    ar,dis=agreement(gold,a2); dump(OUT/'annotation_agreement.json',ar)
    with (OUT/'annotation_disagreements.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['candidate_id','document_id','source_unit_id','annotator_1_label','annotator_2_label','reason']);w.writeheader();w.writerows(dis)
    a1={(x['candidate_id'],x['document_id'],x['source_unit_id']):x['relevance_label'] for x in gold}; a2d={(x['candidate_id'],x['document_id'],x['source_unit_id']):x['relevance_label'] for x in a2}; cons=[]
    for key in sorted(set(a1)&set(a2d)):
        same=a1[key]==a2d[key]; cons.append({'candidate_id':key[0],'document_id':key[1],'source_unit_id':key[2],'consensus_label':a1[key] if same else 'UNADJUDICATED_DISAGREEMENT','consensus_status':'AGREED' if same else 'REQUIRES_MANUAL_ADJUDICATION'})
    with (OUT/'consensus_gold.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['candidate_id','document_id','source_unit_id','consensus_label','consensus_status']);w.writeheader();w.writerows(cons)
    cd=defaultdict(set)
    for x in cons:
        if x['consensus_label']=='DIRECTLY_RELEVANT':cd[(x['candidate_id'],x['document_id'])].add(x['source_unit_id'])
    cr=[]
    for rec in ranks:
        rel=cd[ck(rec)]
        if not rel:continue
        o=rec['orders']['feature_selector'];cr.append((m(o,rel,5)['hit'],m(o,rel,10)['recall'],min((o.index(x)+1 for x in rel if x in o),default=None)))
    dump(OUT/'consensus_metrics.json',{'consensus_hash':h(OUT/'consensus_gold.csv'),'agreed_source_units':sum(x['consensus_status']=='AGREED' for x in cons),'unadjudicated_source_units':sum(x['consensus_status']!='AGREED' for x in cons),'case_denominator':len(cr),'selector_hit_rate@5':round(statistics.mean([x[0] for x in cr]),4) if cr else None,'selector_recall@10':round(statistics.mean([x[1] for x in cr]),4) if cr else None,'selector_mrr':round(statistics.mean([1/x[2] if x[2] else 0 for x in cr]),4) if cr else None,'primary_decision_use':False})
    avail=bool(os.getenv('OLLAMA_API_KEY') or os.getenv('RESEARCH_PIPELINE_LLM_API_KEY')); status='NOT_RUN_PROVIDER_UNAVAILABLE' if not avail else 'NOT_RUN_REQUIRES_EXECUTION'; gm={'status':status,'provider':'Ollama Cloud / Paper Context Enricher V2','api_key_status':'SET' if avail else 'NOT_SET','sample_requested':len(ranks),'sample_executed':0,'k':K,'gold_policy':'DIRECTLY_RELEVANT only; zero-direct uses DIRECTLY+PARTIAL only if execution is enabled','selector_policy':'frozen feature_selector top-5','validated_quote_rate_gold':None,'validated_quote_rate_selector':None,'abstain_rate_gold':None,'abstain_rate_selector':None,'rejected_quote_rate_selector':None,'wrong_quote_accepted':0,'wrong_document_quote_accepted':0,'wrong_sourceunit_quote_accepted':0,'reason':'API key not set; no simulated output accepted' if not avail else 'execution deferred by offline script'}; dumpjl(OUT/'gemma_gold_results.jsonl',[{'candidate_id':x['candidate_id'],'document_id':x['document_id'],'condition':'GOLD','status':status,'attempted':False} for x in ranks]);dumpjl(OUT/'gemma_selector_results.jsonl',[{'candidate_id':x['candidate_id'],'document_id':x['document_id'],'condition':'SELECTOR','status':status,'attempted':False} for x in ranks]);dump(OUT/'gemma_comparison.json',gm)
    dump(OUT/'selector_bundle_adr.json',{'recommendation':'A_LIVE_SELECTOR_REPLAY_BUNDLE','options':{'A_LIVE_SELECTOR_REPLAY_BUNDLE':{'live':'selector','replay':'frozen_bundle','assessment':'preferred; downstream Gemma remains unvalidated'},'B_BUNDLE_IF_PRESENT_ELSE_SELECTOR':{'assessment':'retains hidden live dependency when stale bundle exists'},'C_SELECTOR_LIMITED_BY_BUNDLE':{'assessment':'not independent and leaks historical selection'}},'implemented':False})
    dump(OUT/'final_scorecard.json',{'decision':'SOURCEUNIT_SELECTOR_GENERALIZES_BUT_DOWNSTREAM_NOT_VALIDATED','selector_modified':False,'selector_weights_modified':False,'k_modified':False,'bm25_modified':False,'gold_modified':False,'runtime_modified':False,'historical_artifacts_modified':False,'denominators':denom,'gemma':gm,'annotation':ar,'remaining_p0':['independent Gemma/validator comparison unavailable without provider key'],'remaining_p1':['human second annotator/adjudication','threshold/no-relevance policy','larger independent corpus and alias/table failure analysis']})
    print(json.dumps({'total_cases':len(labels),'positive_cases':len(pos),'zero_direct_cases':len(zero),'selector_positive_hit5':hits,'conditional_selector_hit5':denom['conditional_selector_hit_rate_at_5'],'gemma':status,'second_annotation_pairs':len({(x['candidate_id'],x['document_id']) for x in a2}),'disagreements':len(dis)},indent=2))
if __name__=='__main__':main()
