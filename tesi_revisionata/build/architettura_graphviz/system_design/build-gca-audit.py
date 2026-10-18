"""Read-only census of the pinned GCA corpus; emit a standalone Italian audit."""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[3]
BACKEND = REPO / 'mtb-graphrag'
FAMILIES = {
    'EVIDENCE_STATEMENT': ('Profilo molecolare → descrizione di evidenza', 'Associazione a una descrizione curata; il testo della fonte deve ancora essere esaminato.'),
    'EVIDENCE_DRUG': ('Evidenza → farmaco', 'Collega una descrizione di evidenza a un farmaco e fornisce il riferimento per il successivo confronto con la fonte.'),
    'GENE_DRUG': ('Gene → farmaco', 'Descrive un’interazione a livello di gene, con le proprietà e la provenienza riportate nel grafo.'),
    'TRIAL_DRUG': ('Studio → intervento', 'Identifica un intervento associato a uno studio e permette di recuperarne il contesto dal registro.'),
    'TRIAL_GENE': ('Studio → gene', 'Identifica un gene associato a uno studio e indirizza la consultazione del registro.'),
    'DRUG_COMPANION_DIAGNOSTIC': ('Farmaco → test diagnostico associato', 'Conserva il collegamento diretto tra un farmaco e il test diagnostico associato.'),
    'COMPANION_DIAGNOSTIC_GENE': ('Test diagnostico → gene', 'Descrive il collegamento del test al gene nel Knowledge Graph; la storia del caso è conservata nei dati clinici.'),
}
PATHS = {'publication': 'Pubblicazione', 'registry': 'Registro', 'mixed': 'Pubblicazione e registro', 'other': 'Altro riferimento', 'kg': 'Solo provenienza nel grafo'}


def classify(record: dict) -> str:
    refs = record.get('document_identifiers') or []
    paper = any(item.get('pmid') or item.get('pmcid') or item.get('doi') for item in refs)
    trial = any(item.get('nct') for item in refs)
    return 'mixed' if paper and trial else 'publication' if paper else 'registry' if trial else 'other' if refs else 'kg'


def census(records) -> dict:
    counts = {key: Counter() for key in ('families', 'paths', 'origins', 'predicates', 'datasets', 'fields', 'context_fields', 'source_property_groups', 'path_lengths', 'node_counts', 'reference_counts', 'diseases', 'evidence_types', 'evidence_levels')}
    ids, semantics, sources = Counter(), Counter(), Counter()
    by_family = defaultdict(lambda: {'count': 0, 'paths': Counter(), 'context_nonempty': 0, 'semantic_keys': set(), 'source_rows': set()})
    entities, labels = defaultdict(set), defaultdict(set)
    entity_occurrences = defaultdict(Counter)
    documents = {key: Counter() for key in ('pmid', 'pmcid', 'nct', 'doi')}
    invalid, issues, examples = [], Counter(), {}
    total, previous, sorted_ids = 0, '', True
    for row in records:
        total += 1
        family, cid = row.get('relation_family', ''), row.get('candidate_id', '')
        ids[cid] += 1
        semantics[row.get('semantic_key', '')] += 1
        sorted_ids = sorted_ids and cid >= previous
        previous = cid
        path = classify(row)
        counts['families'][family] += 1
        counts['paths'][path] += 1
        counts['fields'].update(row.keys())
        counts['origins'][row.get('relation_origin', '')] += 1
        counts['predicates'][row.get('predicate', '')] += 1
        counts['datasets'].update(set(row.get('source_datasets') or []))
        counts['context_fields'].update(k for k, v in row.get('context', {}).items() if v not in ('', None, [], {}))
        counts['source_property_groups'].update(row.get('source_properties', {}).keys())
        counts['path_lengths'][len(row.get('graph_path') or [])] += 1
        counts['node_counts'][len(row.get('node_ids') or [])] += 1
        counts['reference_counts'][len(row.get('document_identifiers') or [])] += 1
        b = by_family[family]
        b['count'] += 1
        b['paths'][path] += 1
        b['context_nonempty'] += bool(row.get('context'))
        b['semantic_keys'].add(row.get('semantic_key', ''))
        b['source_rows'].update(row.get('source_record_ids') or [])
        sources.update(row.get('source_record_ids') or [])
        for key, counter in (('disease', 'diseases'), ('evidence_type', 'evidence_types'), ('evidence_level', 'evidence_levels')):
            value = row.get('context', {}).get(key)
            if value:
                counts[counter][str(value)] += 1
        if not row.get('subject') or not row.get('object'):
            issues['missing_endpoints'] += 1
        if not row.get('source_record_ids') or not row.get('source_datasets'):
            issues['missing_lineage'] += 1
        if not cid or not row.get('semantic_key'):
            issues['missing_identity'] += 1
        if not all(row.get(key) for key in ('predicate', 'graph_path', 'node_ids', 'edge_ids_by_dataset', 'materialization_rule', 'materializer_version')):
            issues['incomplete_structure'] += 1
        for endpoint in ('subject', 'object'):
            entity = row.get(endpoint) or {}
            eid, kind = entity.get('id', ''), entity.get('type', '')
            if not all(entity.get(key) for key in ('id', 'label', 'type')):
                issues['incomplete_endpoint_' + endpoint] += 1
            if eid:
                entities[kind].add(eid)
                labels[eid].add(entity.get('label', ''))
                entity_occurrences[kind][eid] += 1
                if eid not in row.get('node_ids', []):
                    issues['endpoint_not_in_nodes'] += 1
        for key in documents:
            documents[key].update({str(ref[key]) for ref in row.get('document_identifiers', []) if ref.get(key)})
        for ref in row.get('document_identifiers', []):
            for key, pattern in (('pmid', r'[0-9]+'), ('nct', r'NCT[0-9]{8}')):
                if ref.get(key) and not re.fullmatch(pattern, str(ref[key]), re.I):
                    invalid.append({'candidate_id': cid, 'family': family, 'field': key, 'value': ref[key], 'flagged': ref.get('valid_' + key) is False})
        examples.setdefault(family, row)
    return {
        'total': total, **{k: dict(v) for k, v in counts.items()},
        'candidate_ids_distinct': len(ids), 'candidate_id_repetitions': total - len(ids),
        'semantic_keys_distinct': len(semantics), 'semantic_key_repetitions': total - len(semantics),
        'semantic_groups_repeated': sum(n > 1 for n in semantics.values()),
        'semantic_max_multiplicity': max(semantics.values(), default=0),
        'semantic_multiplicity': dict(Counter(semantics.values())),
        'source_rows_distinct': len(sources), 'sorted_candidate_ids': sorted_ids,
        'entities_distinct_by_type': {k: len(v) for k, v in entities.items()},
        'endpoint_ids_multiple_labels': sum(len(v) > 1 for v in labels.values()),
        'family_details': {k: {**v, 'paths': dict(v['paths']), 'semantic_keys': len(v['semantic_keys']), 'source_rows': len(v['source_rows'])} for k, v in by_family.items()},
        'documents': {k: {'distinct': len(v), 'candidate_links': sum(v.values()), 'top': v.most_common(10)} for k, v in documents.items()},
        'top_entities': {kind: [{'id': eid, 'label': sorted(labels[eid])[0], 'associations': n} for eid, n in counter.most_common(10)] for kind, counter in entity_occurrences.items()},
        'issues': dict(issues), 'invalid_references': invalid, 'examples': examples,
    }


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return sha256(stream.read()).hexdigest()


def collect() -> dict:
    loader = BACKEND / 'backend/research_pipeline/data_access.py'
    expected = re.search(r'_EXPECTED_CANDIDATES_SHA256\s*=\s*"([a-f0-9]+)"', loader.read_text(encoding='utf-8')).group(1)
    root = Path(os.environ.get('RESEARCH_PIPELINE_DATA_ROOT') or BACKEND).expanduser().resolve()
    folder = root / 'benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/4.0'
    corpus = folder / 'candidates.jsonl'
    observed = digest(corpus)
    if observed != expected:
        raise ValueError('Corpus differs from the pinned runtime loader')
    with corpus.open(encoding='utf-8') as stream:
        audit = census(json.loads(line) for line in stream if line.strip())
    manifest = read_json(folder / 'manifest.json')
    reports = {name: read_json(folder / (name + '.json')) for name in ('coverage_report', 'validation_report', 'source_distribution', 'semantic_diff_v2_v4', 'determinism_report')}
    checks = {
        'loader_hash': observed == expected == manifest['candidates_sha256'],
        'total': audit['total'] == manifest['summary']['materialized_candidates'],
        'families': audit['families'] == {k: v['materialized'] for k, v in reports['coverage_report']['coverage'].items()},
        'datasets': audit['datasets'] == {k: v['candidate_count'] for k, v in reports['source_distribution'].items()},
        'duplicate_ids': audit['candidate_id_repetitions'] == reports['validation_report']['duplicate_candidate_ids'],
        'semantic_repetitions': audit['semantic_key_repetitions'] == reports['semantic_diff_v2_v4']['v4_duplicate_semantic_keys'],
        'invalid_pmid_rows': len({v['candidate_id'] for v in audit['invalid_references'] if v['field'] == 'pmid'}) == reports['validation_report']['invalid_pmid'],
        'invalid_nct_rows': len({v['candidate_id'] for v in audit['invalid_references'] if v['field'] == 'nct'}) == reports['validation_report']['invalid_nct'],
        'graph_only': audit['paths'].get('kg', 0) == manifest['summary']['document_coverage']['candidates_only_kg'],
    }
    if not all(checks.values()):
        raise ValueError('Published reports disagree with census: ' + str(checks))
    from document_audit import cache_root
    resolution = cache_root(root) / 'manifests/runtime_v2_pmid_resolution.jsonl'
    resolution_info = {'available': resolution.is_file()}
    if resolution.is_file():
        with resolution.open(encoding='utf-8') as stream:
            mapping = {str(r['pmid']): r for line in stream if line.strip() for r in [json.loads(line)]}
        with corpus.open(encoding='utf-8') as stream:
            pmids = {str(ref['pmid']) for line in stream if line.strip() for ref in json.loads(line)['document_identifiers'] if ref.get('pmid')}
        statuses = Counter(mapping.get(pmid, {}).get('final_document_status') or 'NON_PRESENTE_NEL_MANIFEST' for pmid in pmids)
        resolution_info.update({'sha256': digest(resolution), 'statuses': dict(statuses), 'denominator': len(pmids)})
    audit.update({'checks': checks, 'reports': reports, 'materialization_summary': manifest['summary'], 'resolution_snapshot': resolution_info,
                  'provenance': {'repository_version': manifest['repository_version'], 'corpus': str(corpus), 'sha256': observed,
                                 'files': {str(p.relative_to(BACKEND)) if p.is_relative_to(BACKEND) else str(p): digest(p) for p in [loader, BACKEND / 'mtb_gca_v4.py', folder / 'manifest.json', *[folder / (n + '.json') for n in reports]]},
                                 'scope': 'Census of pinned records; no live document retrieval, source rematerialization or clinical validation performed.'}})
    return audit


def n(value) -> str:
    return f'{value:,}'.replace(',', '.')


def pct(value, denominator) -> str:
    return f'{100 * value / denominator:.2f}%'.replace('.', ',') if denominator else '—'


def table(headers, rows) -> str:
    rows=list(rows)
    numeric=lambda value: bool(re.fullmatch(r'\d[\d.,]*%?',str(value)))
    numeric_columns={index for index in range(len(headers)) if rows and all(index<len(row) and (numeric(row[index]) or str(row[index]) in ('—','')) for row in rows)}
    heading=''.join('<th scope="col"'+(' class="is-numeric"' if index in numeric_columns else '')+'>'+escape(str(value))+'</th>' for index,value in enumerate(headers))
    body=[]
    for row in rows:
        cells=[]
        for index,value in enumerate(row):
            tag='th' if index==0 else 'td'
            attrs=(' scope="row"' if index==0 else '')+(' class="is-numeric"' if index in numeric_columns else '')
            content=escape(str(value))
            if index==0 and '_' in str(value):
                content='<code>'+content+'</code>'
            cells.append('<'+tag+attrs+'>'+content+'</'+tag+'>')
        body.append('<tr>'+''.join(cells)+'</tr>')
    return '<div class="table-scroll" tabindex="0" role="region" aria-label="Tabella: '+escape(str(headers[0]),quote=True)+'"><table class="audit-table"><thead><tr>'+heading+'</tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'


def section(key, title, text, body='') -> str:
    return f'<section id="{key}"><h2>{escape(title)}</h2><p>{escape(text)}</p>{body}</section>'


def chart(counts, labels, total) -> str:
    maximum = max(counts.values(), default=1)
    return '<div class="bars" role="list">' + ''.join(f'<div class="bar-row" role="listitem"><span>{escape(labels.get(k, k))}</span><div class="track"><div style="width:{100*v/maximum:.3f}%"></div></div><strong>{n(v)} <small>· {pct(v,total)}</small></strong></div>' for k, v in sorted(counts.items(), key=lambda pair: -pair[1])) + '</div>'


def graph_assets() -> str:
    folder = BASE / 'figure/audit-gca'
    folder.mkdir(parents=True, exist_ok=True)
    dot = '''digraph G {
graph [rankdir=LR,bgcolor="white",pad="0.2",nodesep="0.3",ranksep="0.5"];
node [shape=box,style="rounded,filled",fillcolor="#e8f3ef",color="#afc4c8",fontname="Arial",fontsize=16,margin="0.18,0.14"];
edge [color="#617e87",arrowsize=0.7];
gca [label="Una GCA\\nRelazione candidata con provenienza",fillcolor="#eaf0f5"];
relation [label="Relazione\\nSoggetto → predicato → oggetto\\nFamiglia e contesto"];
identity [label="Identità del record\\nIdentificativo + chiave semantica\\nRegola di materializzazione"];
lineage [label="Provenienza\\nDataset e righe sorgente\\nNodi, archi e percorso nel grafo"];
document [label="Riferimenti della fonte\\nPubblicazione, registro\\noppure nessun documento",fillcolor="#f0ebf6"];
gca -> relation; gca -> identity; gca -> lineage; gca -> document;
}'''
    (folder / 'anatomia.dot').write_text(dot, encoding='utf-8')
    executable = shutil.which('dot') or r'C:\Program Files\Graphviz\bin\dot.exe'
    for fmt in ('svg', 'pdf'):
        subprocess.run([executable, '-T' + fmt, str(folder / 'anatomia.dot'), '-o', str(folder / ('anatomia.' + fmt))], check=True)
    svg = (folder / 'anatomia.svg').read_text(encoding='utf-8')
    return svg[svg.index('<svg'):]


def render(audit: dict, svg: str) -> str:
    total = audit['total']
    sections = []
    sections.append(section('lettura', 'Che cos’è una GCA', 'Una GCA è un record che rappresenta un’associazione candidata ricavata dal Knowledge Graph: collega un soggetto a un oggetto attraverso una relazione e conserva le informazioni sulla sua origine. È l’unità che il sistema recupera quando cerca associazioni pertinenti a un caso clinico. Da questo record partono la consultazione della fonte, i controlli e la costruzione del dossier.',
        '<p>Per esempio, una GCA può collegare BRAF a un farmaco, uno studio a un gene oppure un profilo molecolare a una descrizione di evidenza. Famiglia, contesto e riferimenti indicano al sistema come proseguire l’analisi.</p><p>Questa pagina descrive l’intero corpus congelato caricato dal runtime. L’esempio BRAF permette poi di riconoscere alcuni di questi record nel percorso dell’architettura. Ogni percentuale sulle GCA usa come denominatore ' + n(total) + ' record, salvo diversa indicazione.</p>'))
    fields = [
        ('subject, predicate, object', 'Chi è collegato a chi e con quale relazione; ogni estremità conserva tipo, identità e nome.'),
        ('relation_family, relation_origin', 'Famiglia scientifica e origine della relazione. DIRECT indica un collegamento diretto materializzato dal grafo; il supporto documentale viene valutato nelle verifiche successive.'),
        ('context', 'Contesto esplicito della relazione, quando disponibile: malattia, tipo e livello di evidenza. Le proprietà sorgenti possono conservare ulteriori informazioni anche quando questo campo è vuoto.'),
        ('candidate_id, semantic_key', 'Identità del singolo record e chiave di raggruppamento. La chiave semantica può ricorrere in record provenienti da unità sorgenti distinte.'),
        ('document_identifiers', 'Riferimenti bibliografici o del registro che indirizzano il recupero della fonte. Accessibilità del testo, autenticità della citazione e supporto vengono controllati durante l’analisi documentale.'),
        ('source_datasets, source_record_ids', 'Tabelle e righe sorgenti che consentono di risalire all’origine della materializzazione.'),
        ('source_properties', 'Proprietà originali di nodi e archi conservate insieme al record. Il Reader aggiunge successivamente le osservazioni ricavate dalla fonte.'),
        ('graph_path, node_ids, edge_ids_by_dataset', 'Nodi e archi che ricostruiscono il contesto e la provenienza nel grafo. graph_path raccoglie la sequenza serializzata dal materializzatore; gli archi effettivi sono indicati in edge_ids_by_dataset.'),
        ('materialization_rule, materializer_version', 'Regola e versione del processo che ha prodotto il record.')]
    sections.append(section('struttura', 'Come è fatta una GCA', 'Il record tiene distinti contenuto della relazione, identità, provenienza e riferimenti documentali.',
        '<figure>' + svg + '<figcaption>Schema del record · <a href="figure/audit-gca/anatomia.dot">DOT</a> · <a href="figure/audit-gca/anatomia.svg">SVG</a> · <a href="figure/audit-gca/anatomia.pdf">PDF vettoriale</a></figcaption></figure>' + table(['Campi', 'Significato'], fields) + '<details><summary>Presenza dei singoli campi in tutti i record</summary><p>La tabella conta i record che contengono ciascuna chiave. Il valore associato può essere valorizzato oppure vuoto.</p>' + table(['Campo','Record in cui è presente','% corpus'],[[k,n(v),pct(v,total)] for k,v in sorted(audit['fields'].items())]) + '</details>'))
    family_rows = []
    for family, count in sorted(audit['families'].items(), key=lambda pair: -pair[1]):
        detail = audit['family_details'][family]
        family_rows.append([FAMILIES.get(family, (family, ''))[0], family, n(count), pct(count,total), n(detail['semantic_keys']), FAMILIES.get(family, ('',''))[1]])
    sections.append(section('famiglie', 'Le famiglie di relazioni', 'Una famiglia identifica il tipo di associazione da cercare e verificare. Frequenza nel corpus e forza scientifica sono grandezze diverse.',
        chart(audit['families'], {k:v[0] for k,v in FAMILIES.items()}, total) + table(['Relazione', 'Nome tecnico', 'GCA', '% corpus', 'Chiavi distinte', 'Come interpretarla'], family_rows)))
    path_rows = [[family, *[n(detail['paths'].get(path,0)) for path in PATHS]] for family, detail in sorted(audit['family_details'].items())]
    sections.append(section('fonti', 'I percorsi delle fonti', 'I riferimenti presenti nel record determinano il percorso della fonte: pubblicazione, registro o sola provenienza nel grafo. La categoria “solo grafo” raccoglie i record con elenco document_identifiers vuoto e conserva la provenienza del collegamento nel Knowledge Graph. La copertura della letteratura sul tema richiede una ricerca dedicata.',
        '<p><a href="Audit_paper_NCT_per_il_relatore.html">Apri la sezione dedicata: audit delle pubblicazioni e degli studi NCT →</a></p>' + chart(audit['paths'], PATHS, total) + table(['Famiglia', *PATHS.values()], path_rows) + table(['Identificatore', 'Valori distinti', 'Legami GCA–identificatore'], [[key.upper(), n(value['distinct']), n(value['candidate_links'])] for key,value in audit['documents'].items()]) + '<p>Una pubblicazione o uno studio possono essere citati da molte GCA: per questo la tabella mostra sia gli identificatori distinti sia il numero di associazioni che li citano. PMID, PMCID e DOI offrono identificatori diversi della stessa pubblicazione; il conteggio dei documenti unici richiede di ricondurli alla medesima fonte. I valori grezzi comprendono anche gli identificatori segnalati nella sezione Integrità.</p>'))
    resolution = audit['resolution_snapshot']
    if resolution.get('statuses'):
        sections.append(section('risoluzione', 'Disponibilità delle pubblicazioni nello snapshot documentale', 'L’incrocio tra i PMID distinti del corpus e il manifest locale mostra quale materiale documentale era disponibile nello snapshot conservato.',
            table(['Stato nel manifest', 'PMID distinti', '% dei PMID del corpus'], [[key,n(value),pct(value,resolution['denominator'])] for key,value in sorted(resolution['statuses'].items())]) + '<p>Il denominatore comprende tutti i PMID grezzi distinti, inclusi quelli segnalati come malformati. ABSTRACT_ONLY indica la disponibilità dell’abstract; FULL_TEXT_PMC quella del testo completo in PMC. Pertinenza e supporto alla relazione vengono valutati nei passaggi successivi dell’architettura.</p>'))
    integrity = [[ 'Identificativi di record ripetuti', n(audit['candidate_id_repetitions']), 'Duplicati dell’identificativo del singolo record.'],
                 ['Chiavi semantiche distinte', n(audit['semantic_keys_distinct']), 'Gruppi di record individuati dalla chiave definita nel materializzatore.'],
                 ['Ripetizioni oltre la prima della chiave semantica', n(audit['semantic_key_repetitions']), 'Totale record meno chiavi distinte: misura le ricorrenze della relazione tra unità sorgenti.'],
                 ['Gruppi con chiave ripetuta', n(audit['semantic_groups_repeated']), 'Numero di chiavi presenti in almeno due record.'],
                 ['Molteplicità massima di una chiave', n(audit['semantic_max_multiplicity']), 'Numero massimo di record nello stesso gruppo.'],
                 ['Righe sorgenti distinte', n(audit['source_rows_distinct']), 'Identificativi di provenienza conservati nei record.'],
                 ['Estremità mancanti', n(audit['issues'].get('missing_endpoints',0)), 'Soggetto o oggetto assente.'],
                 ['Record senza provenienza minima', n(audit['issues'].get('missing_lineage',0)), 'Mancano tabelle o righe sorgenti.'],
                 ['Record con struttura incompleta', n(audit['issues'].get('incomplete_structure',0)), 'Manca almeno uno dei campi strutturali controllati.'],
                 ['Identità di estremità con più etichette', n(audit['endpoint_ids_multiple_labels']), 'Identificativi associati a etichette diverse, da interpretare attraverso il vocabolario delle identità.']]
    invalid = audit['invalid_references']
    sections.append(section('integrita', 'Integrità, ripetizioni e anomalie', 'Le misure sono ricalcolate su tutti i record. Si distinguono duplicati di record, ricorrenze della stessa relazione e identificatori documentali malformati.',
        table(['Controllo', 'Valore', 'Definizione'], integrity) + '<p>Il report di validazione conta le unità sorgenti duplicate; il confronto tra versioni conta le ricorrenze di semantic_key. Una stessa chiave può quindi comparire in più record, ciascuno con la propria unità sorgente e il proprio identificativo. La chiave di EVIDENCE_STATEMENT è costruita dalla famiglia e dall’identità dell’evidenza; nelle altre famiglie include soggetto e oggetto. Il candidate_id incorpora anche l’unità sorgente.</p>' +
        table(['Riferimento anomalo', 'Famiglia', 'Record', 'Segnalato nel record'], [[v['field'].upper() + ': ' + str(v['value']),v['family'],v['candidate_id'],'Sì' if v['flagged'] else 'No'] for v in invalid]) + '<p>Le anomalie elencate sono ' + n(len(invalid)) + ' occorrenze in record, relative a ' + n(len({(v['field'],str(v['value'])) for v in invalid})) + ' valori distinti. Nel corpus corrente sono stringhe DOI collocate nel campo PMID. L’audit conserva questi valori e i relativi segnali, così da renderli rintracciabili durante il recupero documentale. La valutazione biologica della relazione appartiene all’analisi della fonte.</p>'))
    sections.append(section('copertura', 'Quante unità del grafo diventano GCA', 'La copertura esprime la quota delle unità semantiche ammesse dal materializzatore che è stata trasformata in record GCA.',
        table(['Famiglia', 'Unità ammesse', 'Materializzate', 'Escluse', 'Copertura'], [[k,n(v['eligible']),n(v['materialized']),n(v['excluded']),str(v['coverage_percent'])+'%'] for k,v in audit['reports']['coverage_report']['coverage'].items()]) + '<p>Il denominatore comprende le associazioni autonome delle sette famiglie. Gli archi strutturali gene–variante e variante–profilo arricchiscono la provenienza dei record. I collegamenti farmaco–test e test–gene conservano ciascuno la propria relazione diretta. Il 100% indica che tutte le unità ammesse sono state materializzate; precisione del recupero e validità scientifica richiedono valutazioni dedicate.</p><h3>Da quali tabelle provengono le associazioni</h3>' + table(['Dataset sorgente dichiarato','GCA','% corpus'],[[k,n(v),pct(v,total)] for k,v in sorted(audit['datasets'].items())]) + '<h3>Origine e predicato</h3>' + table(['relation_origin','GCA','% corpus'],[[k,n(v),pct(v,total)] for k,v in sorted(audit['origins'].items())]) + table(['Predicato','GCA','% corpus'],[[k,n(v),pct(v,total)] for k,v in sorted(audit['predicates'].items())])))
    stats = table(['Tipo delle estremità', 'Identità distinte'], [[k,n(v)] for k,v in sorted(audit['entities_distinct_by_type'].items())])
    stats += '<p>La tabella conta le identità presenti come soggetto o oggetto delle relazioni. I nodi aggiuntivi della provenienza sono descritti dalle distribuzioni strutturali più avanti. Gene e GeneSymbol, oppure Drug e DrugName, conservano lo spazio di identità previsto dalla sorgente.</p>'
    stats += table(['Campo context valorizzato', 'GCA', '% corpus'], [[k,n(v),pct(v,total)] for k,v in sorted(audit['context_fields'].items())])
    stats += table(['Famiglia', 'context valorizzato', 'Record della famiglia'], [[k,n(v['context_nonempty']),n(v['count'])] for k,v in sorted(audit['family_details'].items())])
    for key, title in [('diseases','Malattie più frequenti in context'),('evidence_types','Tipi di evidenza in context'),('evidence_levels','Livelli sorgenti in context')]:
        values = audit[key]
        stats += '<h3>' + title + '</h3><p>Le GCA sono contate mantenendo le etichette originali della sorgente. I livelli di evidenza descrivono le proprietà già presenti nel dataset; gli esiti del verificatore sono prodotti durante l’analisi documentale.</p>' + table(['Valore sorgente','GCA','% dei valori valorizzati'], [[k,n(v),pct(v,sum(values.values()))] for k,v in sorted(values.items(), key=lambda pair:-pair[1])[:12]])
    stats += '<h3>Distribuzioni strutturali</h3>'
    for key,title in [('path_lengths','Elementi di graph_path'),('node_counts','Elementi di node_ids'),('reference_counts','Riferimenti documentali per GCA')]:
        stats += table([title,'GCA','% corpus'], [[k,n(v),pct(v,total)] for k,v in sorted(audit[key].items(),key=lambda pair:int(pair[0]))])
    sections.append(section('statistiche', 'Identità, contesto e dimensioni dei record', 'Queste distribuzioni mostrano quali entità compaiono nelle relazioni e quanto contesto è conservato nei record. Le informazioni sono distribuite tra i campi espliciti e le proprietà originali della sorgente.', stats))
    tops = ''
    for kind in ('Gene','GeneSymbol','Drug','DrugName'):
        tops += '<h3>' + escape(kind) + '</h3>' + table(['Nome sorgente','Identità','Presenze nelle estremità delle GCA'], [[v['label'],v['id'],n(v['associations'])] for v in audit['top_entities'].get(kind,[])])
    for key in ('pmid','nct'):
        tops += '<h3>' + key.upper() + '</h3>' + table(['Riferimento','GCA che lo citano'], [[k,n(v)] for k,v in audit['documents'][key]['top']])
    sections.append(section('concentrazione', 'Dove si concentra il corpus', 'Le tabelle mostrano le dieci identità e i dieci riferimenti più frequenti nelle associazioni. Permettono di riconoscere i temi maggiormente rappresentati dalle sorgenti del grafo. Efficacia e qualità delle evidenze vengono esaminate attraverso il contenuto delle fonti.', tops))
    examples = ''
    for family,row in sorted(audit['examples'].items()):
        examples += '<details><summary>' + escape(FAMILIES.get(family,(family,''))[0]) + ' · record reale</summary><p>Il primo record della famiglia nell’ordine del corpus permette di osservare la struttura completa dei campi. Le statistiche precedenti descrivono invece l’intera famiglia.</p><pre>' + escape(json.dumps(row,ensure_ascii=False,indent=2)) + '</pre></details>'
    proof = read_json(BASE / 'verifica/esempi.json')
    braf_rows = []
    for row in proof['records']:
        record = row['record']
        braf_rows.append([record['relation_family'],record['subject']['label'][:95],record['object']['label'][:95],PATHS[classify(record)],record['candidate_id']])
    sections.append(section('esempi', 'Esempi reali e collegamento con BRAF', 'I cinque record già documentati nella pagina dell’architettura appartengono a questo stesso corpus. Qui si mostra la loro struttura; gli esiti dell’analisi del caso restano separati dalle statistiche globali.',
        table(['Famiglia','Soggetto (estratto)','Oggetto (estratto)','Percorso','Record'],braf_rows) + '<p>La tabella presenta un estratto delle etichette più lunghe. Qui sotto è disponibile un record completo per ciascuna famiglia, riportato con il contenuto originale.</p>' + examples))
    diff = audit['reports']['semantic_diff_v2_v4']
    sections.append(section('versioni', 'Come è cambiato il corpus tra le versioni', 'Il report congelato di confronto tra versioni documenta le variazioni nel numero e nella composizione delle associazioni. La tabella riprende quei risultati storici e permette di seguire l’evoluzione del corpus.',
        table(['Famiglia','Record v2','Record v4','Solo v2','Solo v4'], [[k,n(v['v2']),n(v['v4']),n(v['v2_only']),n(v['v4_only'])] for k,v in diff['by_family'].items()])))
    provenance = '<details><summary>File, impronte e controlli riproducibili</summary><pre>' + escape(json.dumps({'provenance':audit['provenance'],'checks':audit['checks'],'resolution_snapshot':audit['resolution_snapshot']},ensure_ascii=False,indent=2)) + '</pre></details>'
    sections.append(section('metodo', 'Come sono stati ottenuti i numeri', 'Il censimento legge tutti i record di candidates.jsonl, verifica l’impronta richiesta dal loader e confronta i conteggi con i report congelati. Ogni statistica globale è calcolata sull’intero corpus.',
        '<p>Il perimetro dell’audit è la struttura e la coerenza interna del corpus materializzato. La disponibilità documentale è ricavata dal manifest locale conservato, identificato dalla propria impronta. La ricostruzione dai CSV originali, la consultazione aggiornata delle fonti e la valutazione scientifica delle relazioni costituiscono attività di verifica dedicate.</p>' + table(['Controllo di concordanza','Esito'],[[k,'Conforme' if v else 'Divergente'] for k,v in audit['checks'].items()]) + provenance + '<p><a href="verifica/gca-audit.json" download>Dati completi dell’audit · JSON</a> · <a href="verifica/gca-audit-tabelle.csv" download>Tabelle principali · CSV</a> · <a href="build-gca-audit.py">Generatore versionabile</a></p>'))
    nav = ''.join(f'<a href="#{key}">{title}</a>' for key,title in [('lettura','Perimetro'),('struttura','Record'),('famiglie','Famiglie'),('fonti','Fonti'),('integrita','Integrità'),('copertura','Copertura'),('statistiche','Statistiche'),('concentrazione','Concentrazione'),('esempi','Esempi'),('versioni','Versioni'),('metodo','Metodo')])
    cards = ''.join(f'<div><strong>{n(value)}</strong><span>{label}</span></div>' for value,label in [(total,'associazioni candidate'),(len(audit['families']),'famiglie di relazioni'),(audit['semantic_keys_distinct'],'chiavi semantiche distinte'),(len(invalid),'riferimenti malformati nei record')])
    css = (BASE / 'styles.css').read_text(encoding='utf-8')
    extra = '''body{background:#f6f8f8}.audit-header{border-bottom:1px solid var(--rule);background:white;padding:22px max(24px,calc((100vw - 1180px)/2));display:flex;gap:20px;align-items:center;justify-content:space-between}.audit-main{max-width:1180px;margin:auto;padding:36px 24px}.audit-main h1{max-width:30ch}.audit-main section{padding:34px 0;border-top:1px solid var(--rule);scroll-margin-top:20px}.audit-main p{max-width:90ch}.audit-main figure{margin:24px 0;padding:22px;background:white;border:1px solid var(--rule);border-radius:12px;overflow:auto}.audit-main figure svg{width:100%;height:auto;min-width:650px}.audit-main details{background:white;padding:16px;margin:12px 0;border:1px solid var(--rule);border-radius:8px}.audit-main summary{cursor:pointer;font-weight:bold}.audit-main pre{max-height:600px;overflow:auto}.audit-nav{display:flex;flex-wrap:wrap;gap:10px 22px;margin:25px 0}.audit-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:32px 0}.audit-stats>div{padding:22px;background:white;border:1px solid var(--rule);border-radius:10px}.audit-stats strong{display:block;font-size:32px;line-height:1.3}.audit-stats span{font-size:13px;color:var(--muted)}.bar-row{display:grid;grid-template-columns:minmax(200px,1fr) minmax(80px,1fr) 145px;gap:16px;align-items:center;margin:14px 0}.track{height:14px;background:#e1eae8;border-radius:4px;overflow:hidden}.track>div{height:100%;background:#116f64}.bar-row strong{text-align:right;font-size:14px}.bar-row small{font-weight:normal}.audit-main td,.audit-main th{overflow-wrap:anywhere}.audit-main .table-scroll{margin:22px 0}.audit-main table{min-width:580px}.audit-main figcaption{margin-top:18px;font-size:13px}@media(max-width:700px){.audit-stats{grid-template-columns:repeat(2,1fr)}.bar-row{grid-template-columns:1fr 110px;gap:6px}.bar-row .track{grid-column:1;grid-row:auto}.bar-row strong{grid-column:2;grid-row:auto}.bar-row>span{grid-column:1/-1}.audit-header{flex-wrap:wrap}.audit-main{padding:24px 16px}}@media print{body{background:white}.audit-header,.audit-nav{display:none}.audit-main{max-width:none;padding:0}.audit-main section{break-before:auto}.audit-main h2,.audit-main h3{break-after:avoid}.audit-stats>div{padding:10px}.audit-stats strong{font-size:22px}.audit-main table{min-width:0;font-size:9pt}.audit-main .table-scroll{overflow:visible}.audit-main figure svg{min-width:0}.audit-main details{break-inside:avoid}.audit-main pre{max-height:none}.bar-row{break-inside:avoid}.audit-main section{padding:18px 0}#print-book{display:none!important}}'''
    return '<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Audit GCA · struttura e corpus</title><style>' + css + '\n' + extra + '</style></head><body><header class="audit-header"><a href="Architettura_per_il_relatore.html">← Architettura per il relatore</a></header><main class="audit-main" id="main"><p>Knowledge Graph · corpus GCA</p><h1>Dentro le associazioni candidate</h1><p>Struttura, provenienza e statistiche dell’intero corpus in uso. Ogni numero ha un denominatore esplicito; le anomalie restano visibili.</p><nav class="audit-nav" aria-label="Sezioni audit">' + nav + '</nav><div class="audit-stats">' + cards + '</div>' + ''.join(sections) + '</main></body></html>'


def main() -> None:
    import csv
    audit = collect()
    verification = BASE / 'verifica'
    verification.mkdir(exist_ok=True)
    (verification / 'gca-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    with (verification / 'gca-audit-tabelle.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['sezione','categoria','conteggio','denominatore','percentuale'])
        for group in ('families','paths','datasets','origins','predicates','context_fields','entities_distinct_by_type'):
            for key,value in sorted(audit[group].items()):
                denom = '' if group == 'entities_distinct_by_type' else audit['total']
                writer.writerow([group,key,value,denom,pct(value,denom) if denom else ''])
    from document_audit import cache_root, collect as collect_sources, render as render_sources, write as write_sources
    corpus = Path(audit['provenance']['corpus'])
    data_root = Path(os.environ.get('RESEARCH_PIPELINE_DATA_ROOT') or BACKEND).expanduser().resolve()
    source_audit = collect_sources(corpus,cache_root(data_root))
    if source_audit['provenance']['corpus_sha256'] != audit['provenance']['sha256']:
        raise ValueError('Source audit corpus differs from GCA audit')
    if len(source_audit['malformed_references']) != len(audit['invalid_references']):
        raise ValueError('Reference audit differs from GCA audit')
    write_sources(source_audit,verification)
    html = render(audit,graph_assets())
    (BASE / 'Audit_GCA_per_il_relatore.html').write_text(html,encoding='utf-8')
    (BASE / 'Audit_paper_NCT_per_il_relatore.html').write_text(render_sources(source_audit,html,table,section,n,pct),encoding='utf-8')
    from sourceunit_audit import build as build_sourceunit_audit
    build_sourceunit_audit(source_audit,html)
    print(f"Audit GCA: {audit['total']} record, {len(audit['families'])} famiglie; {audit['semantic_key_repetitions']} ricorrenze di chiave, {len(audit['invalid_references'])} riferimenti malformati.")
    print(f"Audit fonti: {source_audit['papers']['summary']['unique_pmids']} PMID numerici; {source_audit['trials']['summary']['unique_ncts']} studi NCT.")


if __name__ == '__main__':
    main()
