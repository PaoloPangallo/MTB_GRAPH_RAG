"""Read-only reconstruction and census of source units from audited local sources."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import csv
import gzip
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from statistics import median
import sys

BASE = Path(__file__).resolve().parent
BACKEND = BASE.parents[3] / 'mtb-graphrag'
LOCATORS = ('section','subsection','paragraph_index','sentence_index','char_start','char_end','page','table_id','row','column','figure_id','caption','bbox')
CSV_FIELDS = ['source_unit_id','document_id','ordinal','unit_type','text_chars','text_sha256','content_hash','parser','parser_version','locator_confidence',*[key for key in LOCATORS if key!='caption'],'has_caption','offset_check']


def populated(value):
    return value is not None and value != '' and value != []


def signature(unit):
    return tuple(unit.get(key) for key in ('document_id','unit_type','section','subsection','paragraph_index','sentence_index','page','table_id','row','column','figure_id','char_start','char_end'))


def offset_check(unit, all_units, parent_index=None):
    start,end = unit.get('char_start'),unit.get('char_end')
    if start is None and end is None:
        return 'LOCALIZZAZIONE_STRUTTURALE'
    if type(start) is not int or type(end) is not int or start < 0 or end < start:
        return 'INTERVALLO_DA_ESAMINARE'
    kind = unit.get('unit_type')
    if kind == 'ABSTRACT':
        parents = [unit.get('text') or '']
    elif kind in ('ABSTRACT_SECTION','ABSTRACT_SENTENCE'):
        parents = parent_index.get(('ABSTRACT',),[]) if parent_index is not None else [u.get('text') or '' for u in all_units if u.get('unit_type') == 'ABSTRACT']
    elif kind == 'FULLTEXT_SENTENCE':
        key=('FULLTEXT_PARAGRAPH',unit.get('section'),unit.get('subsection'),unit.get('paragraph_index'))
        parents = parent_index.get(key,[]) if parent_index is not None else [u.get('text') or '' for u in all_units if u.get('unit_type') == 'FULLTEXT_PARAGRAPH' and all(u.get(k) == unit.get(k) for k in ('section','subsection','paragraph_index'))]
    else:
        return 'INTERVALLO_PRESENTE_CONTESTO_SPECIFICO'
    if len(parents) != 1:
        return 'CONTENITORE_DA_IDENTIFICARE'
    if end > len(parents[0]):
        return 'INTERVALLO_DA_ESAMINARE'
    span = parents[0][start:end]
    if span == unit.get('text'):
        return 'CORRISPONDENZA_LETTERALE'
    if span.strip() == (unit.get('text') or ''):
        return 'CORRISPONDENZA_CON_SPAZI_ESTERNI'
    return 'INTERVALLO_DA_ESAMINARE'


def summarize_index(path):
    if not path.is_file():
        return {'available':False},set(),set()
    payload=path.read_bytes()
    rows=[json.loads(line) for line in payload.decode('utf-8').splitlines() if line.strip()]
    ids=Counter(row.get('source_unit_id') for row in rows)
    return {'available':True,'file':str(path),'sha256':sha256(payload).hexdigest(),'units':len(rows),
            'documents':len({row.get('document_id') for row in rows}), 'types':dict(Counter(row.get('unit_type') for row in rows)),
            'parsers':dict(Counter(str(row.get('parser'))+' / '+str(row.get('parser_version')) for row in rows)),
            'with_text':sum(bool(row.get('text')) for row in rows),'duplicate_ids':sum(ids.values())-len(ids)},set(ids),{signature(row) for row in rows}


def describe_lengths(values):
    ordered=sorted(values)
    return {'count':len(ordered),'min':ordered[0] if ordered else 0,'median':median(ordered) if ordered else 0,
            'p95':ordered[max(0,(95*len(ordered)+99)//100-1)] if ordered else 0,'max':ordered[-1] if ordered else 0}


def audit_units(document_id,units,seen_ids=None):
    seen_ids=seen_ids if seen_ids is not None else set()
    counters={key:Counter() for key in ('types','parsers','confidence','locators','offsets','issues','sections')}
    lengths=defaultdict(list)
    same_text,same_type_text,hashes=Counter(),Counter(),Counter()
    parent_index=defaultdict(list)
    for unit in units:
        if unit.get('unit_type')=='ABSTRACT':
            parent_index[('ABSTRACT',)].append(unit.get('text') or '')
        if unit.get('unit_type')=='FULLTEXT_PARAGRAPH':
            parent_index[('FULLTEXT_PARAGRAPH',unit.get('section'),unit.get('subsection'),unit.get('paragraph_index'))].append(unit.get('text') or '')
    rows=[]
    for ordinal,unit in enumerate(units):
        text=str(unit.get('text') or '')
        text_digest=sha256(text.encode('utf-8')).hexdigest()
        identity=unit.get('source_unit_id','')
        kind=unit.get('unit_type','')
        if identity in seen_ids:
            counters['issues']['IDENTIFICATIVO_RIPETUTO']+=1
        seen_ids.add(identity)
        if not re.fullmatch(r'SU-[0-9a-f]{24}',identity):
            counters['issues']['FORMATO_IDENTIFICATIVO_DA_ESAMINARE']+=1
        if not re.fullmatch(r'[0-9a-f]{64}',str(unit.get('content_hash',''))):
            counters['issues']['FORMATO_CONTENT_HASH_DA_ESAMINARE']+=1
        canonical={key:value for key,value in unit.items() if key not in ('source_unit_id','content_hash')}
        payload={'document_id':document_id,'final_ordinal':ordinal,'canonical_sourceunit_content':canonical}
        expected='SU-'+sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()[:24]
        if identity!=expected:
            counters['issues']['IDENTITA_OCCORRENZA_DA_ESAMINARE']+=1
        if unit.get('document_id')!=document_id:
            counters['issues']['DOCUMENTO_DA_ESAMINARE']+=1
        if not text.strip():
            counters['issues']['TESTO_VUOTO']+=1
        location=offset_check(unit,units,parent_index)
        counters['types'][kind]+=1
        counters['parsers'][str(unit.get('parser'))+' / '+str(unit.get('parser_version'))]+=1
        counters['confidence'][unit.get('locator_confidence') or 'VALORE_ASSENTE']+=1
        counters['offsets'][location]+=1
        for key in LOCATORS:
            counters['locators'][key]+=populated(unit.get(key))
        if unit.get('section'):
            counters['sections'][unit['section']]+=1
        lengths[kind].append(len(text))
        same_text[text_digest]+=1
        same_type_text[(kind,text_digest)]+=1
        hashes[unit.get('content_hash')]+=1
        row={key:unit.get(key,'') for key in CSV_FIELDS}
        row.update({'ordinal':ordinal,'text_chars':len(text),'text_sha256':text_digest,'has_caption':bool(unit.get('caption')),'offset_check':location})
        rows.append(row)
    result={key:dict(value) for key,value in counters.items()}
    result.update({'units':len(units),'text_repetitions_within_document':sum(v-1 for v in same_text.values()),
                   'same_type_text_repetitions':sum(v-1 for v in same_type_text.values()),'content_hash_repetitions':sum(v-1 for v in hashes.values()),
                   'lengths':dict(lengths)})
    return result,rows


def records_from_audit(audit,manifest):
    eligible=set()
    for paper in audit['papers']['inventory']:
        if paper['manifest_check']['state']=='IMPRONTA_CONFORME' and paper['abstract_check']=='IDENTITA_CONFORME':
            eligible.add('pmid:'+paper['pmid'])
        for pmc in paper['pmc_checks']:
            if pmc['state']=='IDENTITA_CONFORME' and pmc.get('manifest_check',{}).get('state')=='IMPRONTA_CONFORME':
                eligible.add('pmcid:'+pmc['pmcid'])
    for trial in audit['trials']['inventory']:
        if trial['payload_check']=='IDENTITA_CONFORME' and trial['manifest_check']['state']=='IMPRONTA_CONFORME':
            eligible.add('nct:'+trial['nct'])
    return [deepcopy(manifest[key]) for key in sorted(eligible) if key in manifest]


def collect(audit,verification):
    sys.path.insert(0,str(BACKEND))
    from backend.research_pipeline.documents.cache_runtime import ReadOnlyDocumentCache
    from document_audit import Inputs,cache_root,latest_manifest
    data_root=Path(__import__('os').environ.get('RESEARCH_PIPELINE_DATA_ROOT') or BACKEND).expanduser().resolve()
    root=cache_root(data_root)
    if root!=Path(audit['provenance']['cache_root']).resolve():
        raise ValueError('Refresh the paper/NCT audit for the selected cache')
    inputs=Inputs(root)
    raw_manifest=inputs.read('manifests/documents.jsonl')
    manifest_digest=sha256(raw_manifest or b'').hexdigest()
    if manifest_digest!=audit['provenance']['files_sha256'].get('manifests/documents.jsonl'):
        raise ValueError('Refresh paper/NCT audit: the document manifest changed')
    manifest,_=latest_manifest(raw_manifest)
    records=records_from_audit(audit,manifest)
    cache=ReadOnlyDocumentCache(root)
    index=data_root/'benchmarks/mtb_evidence/document_grounded_claims/authorized_document_cache_pilot/source_unit_index.jsonl'
    historical,old_ids,old_locators=summarize_index(index)
    counters={key:Counter() for key in ('types','parsers','confidence','locators','offsets','issues','sections','document_kinds','documents_by_kind')}
    lengths=defaultdict(list)
    seen_ids=set()
    docs,examples,anomalies=[],{},[]
    totals=Counter()
    file_hashes={}
    fieldnames=list(dict.fromkeys(CSV_FIELDS))
    with gzip.open(verification/'sourceunit-inventario.csv.gz','wt',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fieldnames)
        writer.writeheader()
        for index,record in enumerate(records):
            document_id=record['document_id']
            relative=record.get('local_cache_path')
            payload=inputs.read(relative) if relative else None
            observed=sha256(payload).hexdigest() if payload is not None else ''
            expected=audit['provenance']['files_sha256'].get(str(Path(relative).as_posix())) if relative else None
            if observed!=expected or observed!=record.get('content_hash'):
                raise ValueError('Refresh source audits: payload changed for '+document_id)
            file_hashes[str(Path(relative).as_posix())]=observed
            try:
                units=cache.source_units_for_record(record)
                summary,unit_rows=audit_units(document_id,units,seen_ids)
            except Exception as error:
                docs.append({'document_id':document_id,'state':'PARSER_DA_ESAMINARE','units':0,'error':type(error).__name__+': '+str(error)})
                counters['issues']['ERRORE_PARSER']+=1
                continue
            kind=document_id.split(':',1)[0]
            counters['documents_by_kind'][kind]+=1
            counters['document_kinds'][kind]+=len(units)
            for key in ('types','parsers','confidence','locators','offsets','issues','sections'):
                counters[key].update(summary[key])
            for key,values in summary['lengths'].items():
                lengths[key].extend(values)
            for key in ('text_repetitions_within_document','same_type_text_repetitions','content_hash_repetitions'):
                totals[key]+=summary[key]
            doc={'document_id':document_id,'state':'UNITA_RICOSTRUITE' if units else 'DOCUMENTO_SENZA_UNITA','units':len(units),'types':summary['types'],'offsets':summary['offsets'],'issues':summary['issues'],'payload_sha256':observed}
            docs.append(doc)
            for unit,row in zip(units,unit_rows):
                totals['historical_id_matches']+=unit['source_unit_id'] in old_ids
                totals['historical_locator_matches']+=signature(unit) in old_locators
                kind=unit['unit_type']
                if kind not in examples or (document_id in ('pmid:28891408','nct:NCT02279004') and examples[kind]['document_id'] not in ('pmid:28891408','nct:NCT02279004')):
                    examples[kind]={'source_unit_id':unit['source_unit_id'],'document_id':document_id,'unit_type':kind,'text_excerpt':str(unit.get('text') or '')[:200],
                                    'text_chars':len(unit.get('text') or ''),'locators':{key:unit[key] for key in LOCATORS if populated(unit.get(key))},'parser':unit.get('parser'),'parser_version':unit.get('parser_version')}
                if row['offset_check'] in ('INTERVALLO_DA_ESAMINARE','CONTENITORE_DA_IDENTIFICARE') and len(anomalies)<50:
                    anomalies.append({key:row[key] for key in ('source_unit_id','document_id','unit_type','ordinal','char_start','char_end','text_chars','offset_check')})
                for key,value in row.items():
                    if isinstance(value,(list,dict)):
                        row[key]=json.dumps(value,ensure_ascii=False)
                    if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')):
                        row[key]="'"+value
                writer.writerow(row)
            if (index+1)%250==0:
                print(f'Source unit: {index+1}/{len(records)} documenti esaminati.',flush=True)
    summary={key:dict(value) for key,value in counters.items()}
    summary.update({'units':sum(counters['types'].values()),'document_records':len(records),'documents_with_units':sum(row['units']>0 for row in docs),
                    'unique_source_unit_ids':len(seen_ids),**dict(totals),'lengths':{key:describe_lengths(value) for key,value in lengths.items()}})
    code=['documents/models.py','documents/parsers.py','documents/sentence_spans.py','documents/authorized_cache.py','documents/cache_runtime.py','retrieval/live_sourceunit_selection.py','enrichment/validator_v3.py']
    return {'summary':summary,'historical_index':historical,'documents':docs,'examples':examples,'offset_examples':anomalies,
            'provenance':{'corpus_sha256':audit['provenance']['corpus_sha256'],'cache_root':str(root),'manifest_sha256':manifest_digest,
                          'payload_sha256':file_hashes,'implementation_sha256':{key:sha256((BACKEND/'backend/research_pipeline'/key).read_bytes()).hexdigest() for key in code},
                          'scope':'Current parser reconstruction over corpus-linked payloads with verified source identity and manifest digest. Historical locator index is described separately.'}}


def write(audit,verification):
    (verification/'sourceunit-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    with (verification/'sourceunit-documenti.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['document_id','state','units','types','offsets','issues','payload_sha256','error'])
        writer.writeheader()
        for row in audit['documents']:
            writer.writerow({key:json.dumps(value,ensure_ascii=False,sort_keys=True) if isinstance(value,dict) else value for key,value in row.items()})


def render(audit,base_html,table,section,number,percent):
    s,h=audit['summary'],audit['historical_index']
    total=s['units']
    sections=[]
    def dist(title,values,denominator,limit=None):
        rows=sorted(values.items(),key=lambda pair:(-pair[1],str(pair[0])))
        if limit:
            rows=rows[:limit]
        return '<h3>'+escape(title)+'</h3>'+table(['Valore','Occorrenze','% dell’insieme indicato'],[[key,number(value),percent(value,denominator)] for key,value in rows])
    maximum=max(s['types'].values(),default=1)
    type_chart='<div class="bars" role="list">'+''.join('<div class="bar-row" role="listitem"><span>'+escape(key)+'</span><div class="track" aria-hidden="true"><div style="width:'+str(100*value/maximum)+'%"></div></div><strong>'+number(value)+' <small>· '+percent(value,total)+'</small></strong></div>' for key,value in sorted(s['types'].items(),key=lambda pair:-pair[1]))+'</div>'
    sections.append(section('unita','Che cos’è una source unit','Una source unit è una porzione di contenuto documentale che il sistema può selezionare, leggere e citare. Conserva il testo insieme al documento di origine, al tipo di contenuto e alle coordinate utili a ritrovarlo.',
        '<p>Una stessa pubblicazione offre più livelli di lettura: abstract, paragrafo, frase, cella di tabella o didascalia. Un registro offre campi come titolo, sintesi, condizioni e interventi. Questa organizzazione permette al selettore di scegliere passaggi pertinenti e al validatore di verificare la citazione nella specifica unità.</p>'))
    scope=table(['Insieme','Unità','Documenti','Criterio'],[
        ['Ricostruzione attuale',number(total),number(s['documents_with_units']),'Parser attuali sui payload collegati al corpus, con identità e impronta verificate nell’audit delle fonti'],
        ['Indice storico dei locatori',number(h.get('units',0)),number(h.get('documents',0)),'Indice congelato del progetto, con coordinate e metadati dei parser della relativa versione']])
    sections.append(section('perimetro-su','Come è stato costruito questo censimento','Il censimento ricostruisce le unità direttamente dai contenuti locali usando il percorso di parsing del backend in sola lettura. Le statistiche descrivono il materiale disponibile alla selezione; la scelta dei passaggi per una singola relazione dipende dalla domanda e dalla configurazione.',
        scope+'<p>Abstract PubMed, articoli PMC e registri sono contati per document_id. Abstract e testo completo della stessa pubblicazione costituiscono due rappresentazioni documentali. L’indice storico è presentato come insieme autonomo, con la propria impronta e le proprie versioni dei parser.</p><p>Nel descrittore della cache del backend, il campo source_unit_count conta le righe di source_unit_index.jsonl. Questa pagina affianca a quel conteggio la ricostruzione estesa delle unità testuali dai payload disponibili.</p>'))
    fields=[('source_unit_id','Identifica una specifica occorrenza del contenuto nel documento.'),('document_id','Collega l’unità alla fonte PubMed, PMC o NCT.'),('unit_type e text','Descrivono il livello di contenuto e conservano il testo che può essere letto e citato.'),('section e subsection','Mantengono il contesto strutturale della fonte.'),('paragraph_index e sentence_index','Individuano paragrafo e frase nel contesto indicato.'),('char_start e char_end','Definiscono un intervallo di caratteri: l’estremo finale è esclusivo. Nelle frasi full text il riferimento è il paragrafo; nelle frasi dell’abstract è l’abstract completo.'),('page, bbox, table_id, row, column, figure_id, caption','Localizzano pagine, celle, figure e didascalie quando il formato li rende disponibili. Gli indici pari a zero sono valori validi.'),('parser, parser_version, locator_confidence','Descrivono il componente che ha estratto l’unità e il tipo di localizzazione disponibile.'),('content_hash','Impronta conservata dalla costruzione del contenuto; la provenienza e la versione del parser ne spiegano la convenzione.')]
    sections.append(section('struttura-su','Come è fatta una source unit','Il modello riunisce testo, identità e localizzazione nello stesso oggetto serializzabile.',table(['Campo','Funzione'],fields)))
    sections.append(section('tipi-su','Quali contenuti vengono estratti','Le quantità seguenti usano come denominatore tutte le '+number(total)+' unità ricostruite. Le unità conservano livelli di granularità diversi, che possono contenere porzioni dello stesso testo.',
        type_chart+dist('Tipi di unità',s['types'],total)+dist('Unità per origine documentale',s['document_kinds'],total)+dist('Documenti ricostruiti per origine',s['documents_by_kind'],sum(s['documents_by_kind'].values()))+
        '<p>PubMed produce titolo, abstract, sezioni riconosciute e frasi. JATS produce paragrafi e frasi del corpo, unità dell’abstract, intestazioni, celle, didascalie e contenuti supplementari. Per gli NCT il percorso corrente produce titolo, sintesi breve, descrizione dettagliata, condizioni e nomi degli interventi; gli altri campi del protocollo sono trattati dai componenti dedicati al registro.</p>'))
    sections.append(section('identita-su','Come si riconosce una specifica occorrenza','Dopo il parsing, il backend assegna l’identificativo finale usando documento, posizione nell’ordine canonico delle unità e contenuto strutturato. Due occorrenze con testo identico mantengono così identità proprie.',
        table(['Misura','Valore'],[['Unità ricostruite',number(total)],['Identificativi distinti',number(s['unique_source_unit_ids'])],['Testi ripetuti nello stesso documento, oltre la prima occorrenza',number(s.get('text_repetitions_within_document',0))],['Testi ripetuti nello stesso documento e tipo',number(s.get('same_type_text_repetitions',0))],['Ricorrenze di content_hash',number(s.get('content_hash_repetitions',0))]])+
        '<p>Il testo può ricorrere perché un paragrafo contiene le frasi che lo compongono, oppure perché una tabella ripete un valore. L’identità dell’occorrenza consente di conservare entrambe le posizioni. content_hash e source_unit_id svolgono ruoli complementari: il primo conserva l’impronta della costruzione del contenuto; il secondo distingue le occorrenze dopo la finalizzazione. Nei campi NCT, content_hash deriva dalla costruzione iniziale come ABSTRACT e l’etichetta del campo viene poi assegnata dal parser: l’audit conserva questa convenzione del codice.</p>'))
    location=table(['Campo di localizzazione valorizzato','Unità','% di tutte le unità'],[[key,number(value),percent(value,total)] for key,value in s['locators'].items()])
    location+=dist('Qualità di localizzazione dichiarata dal parser',s['confidence'],total)+dist('Verifica degli intervalli rispetto al contenitore',s['offsets'],total)
    location+='<p>La verifica posizionale confronta il testo con l’intervallo nel suo contenitore: abstract completo o paragrafo full text. La categoria degli spazi esterni indica che il ritaglio coincide dopo la rimozione degli spazi ai margini. Le unità localizzate attraverso celle, campi del registro o didascalie usano soprattutto coordinate strutturali. locator_confidence descrive la localizzazione del passaggio; i controlli sulla relazione producono gli esiti scientifici.</p>'
    if audit['offset_examples']:
        location+='<details><summary>Primi esempi di intervalli da esaminare · massimo 50</summary><pre>'+escape(json.dumps(audit['offset_examples'],ensure_ascii=False,indent=2))+'</pre></details>'
    sections.append(section('locatori-su','Come si ritrova il passaggio nella fonte','La localizzazione segue la struttura del documento. Le tabelle descrivono quali coordinate sono disponibili e come gli intervalli di caratteri corrispondono al testo estratto.',location))
    sections.append(section('dimensioni-su','Lunghezza e distribuzione dei passaggi','Le lunghezze sono misurate in caratteri del testo estratto. Mediana e 95° percentile aiutano a confrontare la granularità dei diversi tipi.',
        table(['Tipo','Unità','Minimo','Mediana','95° percentile','Massimo'],[[key,number(value['count']),str(value['min']),str(value['median']),str(value['p95']),str(value['max'])] for key,value in sorted(s['lengths'].items())])+dist('Sezioni più rappresentate · prime 15',s['sections'],total,15)+
        '<p>Le frequenze delle sezioni contano le unità che riportano quella stessa etichetta originale. Una sezione con molti paragrafi o frasi contribuisce quindi a più occorrenze.</p>'))
    sections.append(section('parser-su','Parser e confronto con l’indice storico','Ogni insieme conserva le versioni dei componenti che lo hanno prodotto. Questo permette di interpretare le differenze di segmentazione e identificazione nel tempo.',
        dist('Parser della ricostruzione attuale',s['parsers'],total)+dist('Parser dell’indice storico',h.get('parsers',{}),h.get('units',0))+
        '<p>Nei campi NCT, il valore fixture/text è il nome predefinito conservato dal costruttore SourceUnit, usato dal percorso reale del registro. Il tipo di campo e il documento NCT ne identificano la provenienza.</p>'+
        table(['Confronto degli insiemi','Valore','Lettura'],[['Identificativi storici incontrati nella ricostruzione',number(s.get('historical_id_matches',0)),'Confronto esatto di source_unit_id'],['Occorrenze attuali con firma strutturale presente nell’indice storico',number(s.get('historical_locator_matches',0)),'Firma: documento, tipo e coordinate; descrive una corrispondenza strutturale'],['Unità con testo nell’indice storico',number(h.get('with_text',0)),'Il file storico è un indice dei locatori']])+
        '<p>Gli identificativi del file storico seguono il prefisso dell’impronta del contenuto; il percorso attuale finalizza l’identità della specifica occorrenza. Il confronto delle firme strutturali riguarda i metadati di posizione, mentre la verifica delle citazioni usa il testo delle unità ricostruite. Copertura dei documenti, convenzioni di identità e versioni dei parser permettono di leggere insieme i due insiemi.</p>'))
    sections.append(section('uso-su','Dalla source unit alla citazione','Le unità sono il materiale su cui lavorano selezione, Reader e autenticazione della citazione.',
        table(['Passaggio','Come usa le unità'],[['Selezione','Il percorso predefinito ordina i passaggi con BM25 strutturale e MedCPT e fonde le classifiche con RRF. Si applicano filtri, limiti e vincoli di sovrapposizione. Quando MedCPT è indisponibile, il percorso usa BM25 strutturale.'],['Reader','Riceve i passaggi selezionati per la relazione e restituisce un’osservazione con citazione oppure un’astensione.'],['Autenticazione','Verifica che source_unit_id appartenga al documento e all’insieme ammesso, e che la citazione sia presente letteralmente nel testo dell’unità.'],['Controlli sulla relazione','Valutano poi gli argomenti e il significato dell’osservazione secondo la famiglia della relazione.'],['Configurazioni opzionali','focused-v1 aggiunge pianificazione documentale e tratta i registri risolti come fatti strutturati, con osservazioni costruite dal codice. Il censimento descrive le unità disponibili prima delle scelte per una specifica domanda.']])+
        '<p>Le statistiche di questa pagina descrivono il contenuto ricostruito. Le classifiche, i passaggi effettivamente letti e gli esiti documentali appartengono all’analisi del singolo caso.</p>'))
    examples=''
    for key,value in sorted(audit['examples'].items()):
        examples+='<details><summary>'+escape(key)+' · '+escape(value['document_id'])+'</summary><p>Estratto dei primi 200 caratteri dell’unità; il campo text_chars indica la lunghezza completa.</p><pre>'+escape(json.dumps(value,ensure_ascii=False,indent=2))+'</pre></details>'
    sections.append(section('esempi-su','Esempi di unità reali','Gli esempi mostrano testo e coordinate prodotti dai parser. Per abstract e registri sono privilegiati, quando disponibili, i documenti dell’esempio BRAF.',examples))
    issues=table(['Controllo da esaminare','Occorrenze'],[[key,number(value)] for key,value in s['issues'].items()]) if s['issues'] else '<p>I controlli su formato, identità dell’occorrenza, documento e presenza del testo sono conformi per tutte le unità ricostruite.</p>'
    sections.append(section('integrita-su','Controlli di integrità e inventari','L’audit confronta l’impronta dei payload con lo snapshot delle fonti, ricostruisce gli identificativi delle occorrenze e verifica forma e localizzazione delle unità.',issues+
        '<p><a href="verifica/sourceunit-documenti.csv" download>Inventario per documento · CSV</a> · <a href="verifica/sourceunit-inventario.csv.gz" download>Inventario completo dei locatori · CSV compresso</a> · <a href="verifica/sourceunit-audit.json" download>Statistiche, esempi e impronte · JSON</a></p><p>L’inventario dei locatori conserva una riga per unità, con identificativo, documento, tipo, lunghezza, impronta del testo e coordinate. I testi integrali rimangono nei documenti della cache; gli estratti della pagina servono a illustrare la struttura.</p><details><summary>Provenienza della ricostruzione</summary><pre>'+escape(json.dumps({key:value for key,value in audit['provenance'].items() if key!='payload_sha256'},ensure_ascii=False,indent=2))+'</pre></details>'))
    nav='<nav class="audit-nav" aria-label="Sezioni audit source unit">'+''.join('<a href="#'+key+'">'+label+'</a>' for key,label in [('unita','Definizione'),('perimetro-su','Perimetro'),('struttura-su','Struttura'),('tipi-su','Tipi'),('identita-su','Identità'),('locatori-su','Locatori'),('dimensioni-su','Dimensioni'),('parser-su','Parser'),('uso-su','Uso'),('esempi-su','Esempi'),('integrita-su','Inventari')])+'</nav>'
    cards='<div class="audit-stats">'+''.join('<div><strong>'+number(value)+'</strong><span>'+label+'</span></div>' for value,label in [(total,'source unit ricostruite'),(s['documents_with_units'],'documenti con unità'),(len(s['types']),'tipi di unità'),(h.get('units',0),'locatori nell’indice storico')])+'</div>'
    main='<main class="audit-main" id="main"><p>Audit del contenuto documentale</p><h1>Dentro le source unit</h1><p>Come il sistema rappresenta, localizza e seleziona i passaggi delle fonti.</p>'+nav+cards+''.join(sections)+'</main>'
    html=re.sub(r'<main class="audit-main" id="main">.*?</main>',lambda _:main,base_html,flags=re.S)
    html=html.replace('<title>Audit GCA · struttura e corpus</title>','<title>Audit completo delle source unit</title>')
    html = html.replace('</header>', '<a href="Audit_GCA_per_il_relatore.html">Audit GCA</a><a href="Audit_paper_NCT_per_il_relatore.html">Paper e NCT</a></header>', 1)
    return html


def write_view(audit,base_html=None):
    import importlib.util
    spec=importlib.util.spec_from_file_location('gca_render',BASE/'build-gca-audit.py')
    gca=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gca)
    html=render(audit,base_html or (BASE/'Audit_GCA_per_il_relatore.html').read_text(encoding='utf-8'),gca.table,gca.section,gca.n,gca.pct)
    (BASE/'Audit_source_unit_per_il_relatore.html').write_text(html,encoding='utf-8')


def build(source_audit=None,base_html=None):
    verification=BASE/'verifica'
    source_audit=source_audit or json.loads((verification/'fonti-audit.json').read_text(encoding='utf-8'))
    audit=collect(source_audit,verification)
    write(audit,verification)
    write_view(audit,base_html)
    print(f"Audit source unit: {audit['summary']['units']} unità, {audit['summary']['documents_with_units']} documenti.",flush=True)
    return audit


if __name__=='__main__':
    if '--render-only' in sys.argv:
        write_view(json.loads((BASE/'verifica/sourceunit-audit.json').read_text(encoding='utf-8')))
    else:
        build()
