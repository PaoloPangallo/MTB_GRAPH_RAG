"""Census of paper and trial identifiers, graph metadata and local payloads."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
from statistics import median
from xml.etree import ElementTree as ET


def cache_root(data_root: Path) -> Path:
    for name in ('RESEARCH_DOCUMENT_CACHE_PATH', 'RESEARCH_PIPELINE_CACHE_ROOT'):
        value = os.getenv(name)
        if value and value.strip():
            return Path(value.strip()).expanduser().resolve()
    return (data_root / 'data_cache/document_grounding').resolve()


class Inputs:
    """Read each payload once and preserve the digest of the bytes inspected."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.hashes: dict[str, str] = {}
        self.payloads: dict[str, bytes] = {}

    def read(self, relative: str) -> bytes | None:
        path = Path(relative)
        if path.is_absolute():
            raise ValueError('Absolute cache payload path')
        path = (self.root / path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Cache payload outside selected root')
        key = path.relative_to(self.root).as_posix()
        if key in self.payloads:
            return self.payloads[key]
        if not path.is_file():
            return None
        data = path.read_bytes()
        self.hashes[key] = sha256(data).hexdigest()
        self.payloads[key] = data
        return data

    def json(self, relative: str):
        payload = self.read(relative)
        if payload is None:
            return None, 'FILE_ASSENTE'
        try:
            return json.loads(payload), 'LEGGIBILE'
        except (ValueError, UnicodeDecodeError):
            return None, 'JSON_DA_ESAMINARE'

    def xml(self, relative: str):
        payload = self.read(relative)
        if payload is None:
            return None, 'FILE_ASSENTE'
        try:
            root = ET.fromstring(payload)
            for item in root.iter():
                item.tag = item.tag.rsplit('}', 1)[-1]
            return root, 'LEGGIBILE'
        except ET.ParseError:
            return None, 'XML_DA_ESAMINARE'


def xml_text(element) -> str:
    return ''.join(element.itertext()).strip() if element is not None else ''


def values(value) -> list[str]:
    if value in (None, ''):
        return []
    items = value if isinstance(value, list) else re.split(r'\s*\|\s*', str(value))
    return [str(item).strip() for item in items if str(item).strip()]


def latest_manifest(payload: bytes | None) -> tuple[dict, Counter]:
    latest, occurrences = {}, Counter()
    if payload:
        for line in payload.decode('utf-8').splitlines():
            if line.strip():
                row = json.loads(line)
                key = row.get('document_id', '')
                latest[key] = row
                occurrences[key] += 1
    return latest, occurrences


def check_manifest(inputs: Inputs, record: dict | None) -> dict:
    if record is None:
        return {'state': 'VOCE_ASSENTE'}
    relative = record.get('local_cache_path')
    if not relative:
        return {'state': 'PERCORSO_ASSENTE', 'availability': record.get('availability')}
    try:
        payload = inputs.read(relative)
    except ValueError:
        return {'state': 'PERCORSO_DA_ESAMINARE'}
    if payload is None:
        return {'state': 'FILE_ASSENTE'}
    observed = sha256(payload).hexdigest()
    expected = record.get('content_hash')
    return {'state': 'IMPRONTA_CONFORME' if expected == observed else 'IMPRONTA_DA_ESAMINARE' if expected else 'IMPRONTA_DICHIARATA_ASSENTE',
            'availability': record.get('availability'), 'path': relative, 'observed_sha256': observed, 'expected_sha256': expected}


def corpus_links(corpus: Path):
    papers = defaultdict(lambda: {'gca_ids': set(), 'families': Counter(), 'pmcids': set(), 'evidence_ids': set()})
    trials = defaultdict(lambda: {'gca_ids': set(), 'families': Counter(), 'source': defaultdict(set), 'genes': set(), 'drugs': set()})
    malformed = []
    for line in corpus.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        refs = row.get('document_identifiers') or []
        for pmid in {str(ref['pmid']) for ref in refs if ref.get('pmid')}:
            if not re.fullmatch(r'[0-9]+', pmid):
                malformed.append({'candidate_id': row['candidate_id'], 'field': 'pmid', 'value': pmid})
                continue
            item = papers[pmid]
            item['gca_ids'].add(row['candidate_id'])
            item['families'][row['relation_family']] += 1
            item['pmcids'].update(str(ref['pmcid']) for ref in refs if ref.get('pmid') == pmid and ref.get('pmcid'))
            evidence = row.get('source_properties', {}).get('evidence', {})
            if evidence.get('evidence_id'):
                item['evidence_ids'].add(str(evidence['evidence_id']))
        for nct in {str(ref['nct']) for ref in refs if ref.get('nct')}:
            if not re.fullmatch(r'NCT[0-9]{8}', nct, re.I):
                malformed.append({'candidate_id': row['candidate_id'], 'field': 'nct', 'value': nct})
                continue
            item = trials[nct]
            item['gca_ids'].add(row['candidate_id'])
            item['families'][row['relation_family']] += 1
            source = row.get('source_properties', {}).get('trial') or {}
            for key in ('title','conditions','interventions','status','phase'):
                item['source'][key].update(values(source.get(key)))
            if row['relation_family'] == 'TRIAL_GENE':
                item['genes'].add(row['object']['label'])
            if row['relation_family'] == 'TRIAL_DRUG':
                item['drugs'].add(row['object']['label'])
    return papers, trials, malformed


def sizes(rows, key):
    numbers = [row[key] for row in rows if row.get(key)]
    return {'records': len(numbers), 'min': min(numbers, default=0), 'median': median(numbers) if numbers else 0, 'max': max(numbers, default=0)}


def distribution(rows, key, multi=False) -> dict:
    result = Counter()
    for row in rows:
        value = row.get(key)
        if multi:
            result.update(set(value or []))
        else:
            result[value or 'VALORE_ASSENTE'] += 1
    return dict(result)


def collect(corpus: Path, root: Path) -> dict:
    if not root.is_dir() or not all((root / name).is_dir() for name in ('pubmed','pmc','clinical_trials')):
        raise ValueError('Selected document cache is unavailable or has an incomplete layout')
    papers, trials, malformed = corpus_links(corpus)
    inputs = Inputs(root)
    manifest, history = latest_manifest(inputs.read('manifests/documents.jsonl'))
    resolution_payload = inputs.read('manifests/runtime_v2_pmid_resolution.jsonl')
    resolution = {str(row['pmid']): row for line in (resolution_payload or b'').decode('utf-8').splitlines() if line.strip() for row in [json.loads(line)]}
    paper_rows, trial_rows = [], []
    pmc_cache = {}
    for pmid, link in sorted(papers.items()):
        row = {'pmid': pmid, 'gca_count': len(link['gca_ids']), 'candidate_ids': sorted(link['gca_ids']), 'families': dict(link['families']), 'evidence_count': len(link['evidence_ids']), 'evidence_ids': sorted(link['evidence_ids']),
               'pmcids_in_corpus': sorted(link['pmcids']), 'title': '', 'snapshot_status': resolution.get(pmid, {}).get('final_document_status') or 'VOCE_ASSENTE'}
        data, state = inputs.json(f'pubmed/metadata/{pmid}.json')
        entry = (data.get('result') or {}).get(pmid) if isinstance(data, dict) else None
        identity = str(entry.get('uid', '')) if isinstance(entry, dict) else ''
        row['metadata_check'] = 'IDENTITA_CONFORME' if identity == pmid else 'IDENTITA_DA_ESAMINARE' if state == 'LEGGIBILE' else state
        if row['metadata_check'] == 'IDENTITA_CONFORME':
            ids = entry.get('articleids') or []
            year = re.search(r'\b(\d{4})\b', entry.get('pubdate') or '')
            row.update({'title': entry.get('title') or '', 'journal': entry.get('fulljournalname') or entry.get('source') or '',
                        'year': year.group(1) if year else '', 'languages': sorted(set(entry.get('lang') or [])),
                        'publication_types': sorted(set(entry.get('pubtype') or [])),
                        'doi': sorted({item['value'] for item in ids if item.get('idtype') == 'doi' and item.get('value')}),
                        'authors_count': len(entry.get('authors') or [])})
        abstract, abstract_state = inputs.xml(f'pubmed/abstracts/{pmid}.xml')
        abstract_ids = {xml_text(el) for el in abstract.findall('.//MedlineCitation/PMID')} if abstract is not None else set()
        row['abstract_check'] = 'IDENTITA_CONFORME' if abstract_ids == {pmid} else 'IDENTITA_DA_ESAMINARE' if abstract_state == 'LEGGIBILE' else abstract_state
        text_nodes = abstract.findall('.//Article/Abstract/AbstractText') if abstract is not None and row['abstract_check'] == 'IDENTITA_CONFORME' else []
        row['abstract_chars'] = sum(len(xml_text(el)) for el in text_nodes)
        row['abstract_parts'] = len([el for el in text_nodes if xml_text(el)])
        pmcids = set(link['pmcids'])
        if resolution.get(pmid, {}).get('pmcid'):
            pmcids.add(str(resolution[pmid]['pmcid']))
        if isinstance(entry, dict) and row['metadata_check'] == 'IDENTITA_CONFORME':
            pmcids.update(item['value'] for item in entry.get('articleids') or [] if item.get('idtype') == 'pmc' and item.get('value'))
        pmc_checks = []
        for pmcid in sorted(pmcids):
            if not re.fullmatch(r'PMC\d+', pmcid):
                pmc_checks.append({'pmcid': pmcid, 'state': 'FORMATO_DA_ESAMINARE'})
                continue
            if pmcid not in pmc_cache:
                xml, xml_state = inputs.xml(f'pmc/xml/{pmcid}.xml')
                article = xml if xml is not None and xml.tag == 'article' else xml.find('.//article') if xml is not None else None
                meta = article.find('front/article-meta') if article is not None else None
                identifiers = defaultdict(set)
                if meta is not None:
                    for element in meta.findall('article-id'):
                        identifiers[element.get('pub-id-type', '')].add(xml_text(element))
                pmc_cache[pmcid] = {'state': xml_state, 'identifiers': dict(identifiers),
                                    'body_chars': len(xml_text(article.find('body'))) if article is not None else 0}
            cached = pmc_cache[pmcid]
            idset = cached['identifiers']
            pmc_identity = {value if value.startswith('PMC') else 'PMC' + value for value in [*idset.get('pmc', []), *idset.get('pmcid', [])]}
            correct = cached['state'] == 'LEGGIBILE' and set(idset.get('pmid', [])) == {pmid} and pmc_identity == {pmcid}
            pmc_checks.append({'pmcid': pmcid, 'state': 'IDENTITA_CONFORME' if correct else 'IDENTITA_DA_ESAMINARE' if cached['state'] == 'LEGGIBILE' else cached['state'],
                               'body_chars': cached['body_chars'] if correct else 0,
                               'manifest_check': check_manifest(inputs, manifest.get('pmcid:' + pmcid))})
        row['pmc_checks'] = pmc_checks
        row['fulltext_available'] = any(item.get('body_chars', 0) > 0 and item['state'] == 'IDENTITA_CONFORME' for item in pmc_checks)
        row['manifest_check'] = check_manifest(inputs, manifest.get('pmid:' + pmid))
        paper_rows.append(row)
    for nct, link in sorted(trials.items()):
        row = {'nct': nct, 'gca_count': len(link['gca_ids']), 'candidate_ids': sorted(link['gca_ids']), 'families': dict(link['families']),
               'source': {key: sorted(value) for key,value in link['source'].items()}, 'genes': sorted(link['genes']), 'drugs': sorted(link['drugs'])}
        payload, state = inputs.json(f'clinical_trials/{nct}.json')
        protocol = payload.get('protocolSection') or {} if isinstance(payload, dict) else {}
        identity = protocol.get('identificationModule', {}).get('nctId')
        row['payload_check'] = 'IDENTITA_CONFORME' if identity == nct else 'IDENTITA_DA_ESAMINARE' if state == 'LEGGIBILE' else state
        row['manifest_check'] = check_manifest(inputs, manifest.get('nct:' + nct))
        if identity == nct:
            ident, design = protocol.get('identificationModule') or {}, protocol.get('designModule') or {}
            eligibility = protocol.get('eligibilityModule') or {}
            arms = protocol.get('armsInterventionsModule') or {}
            description = protocol.get('descriptionModule') or {}
            outcomes = protocol.get('outcomesModule') or {}
            enrollment = design.get('enrollmentInfo', {}).get('count')
            row.update({'title': ident.get('briefTitle') or '', 'study_type': design.get('studyType') or '',
                        'status': protocol.get('statusModule', {}).get('overallStatus') or '',
                        'phases': sorted(set(design.get('phases') or [])), 'conditions': sorted(set(protocol.get('conditionsModule', {}).get('conditions') or [])),
                        'intervention_types': sorted({i['type'] for i in arms.get('interventions') or [] if i.get('type')}),
                        'interventions_count': len(arms.get('interventions') or []), 'arm_groups_count': len(arms.get('armGroups') or []),
                        'interventions_with_arm_labels': sum(bool(i.get('armGroupLabels')) for i in arms.get('interventions') or []),
                        'has_brief_summary': bool(description.get('briefSummary')), 'has_detailed_description': bool(description.get('detailedDescription')),
                        'has_eligibility_criteria': bool(eligibility.get('eligibilityCriteria')), 'has_sex': bool(eligibility.get('sex')),
                        'has_age': bool(eligibility.get('minimumAge') or eligibility.get('maximumAge')),
                        'has_primary_outcomes': bool(outcomes.get('primaryOutcomes')), 'has_secondary_outcomes': bool(outcomes.get('secondaryOutcomes')),
                        'has_results': payload.get('hasResults') if type(payload.get('hasResults')) is bool else None,
                        'enrollment': enrollment if type(enrollment) is int and enrollment > 0 else 0,
                        'countries': sorted({item['country'] for item in protocol.get('contactsLocationsModule', {}).get('locations') or [] if item.get('country')}),
                        'sponsor_class': protocol.get('sponsorCollaboratorsModule', {}).get('leadSponsor', {}).get('class') or ''})
            source_statuses = link['source'].get('status', set())
            row['status_comparison'] = 'COINCIDENTE' if row['status'] in source_statuses and len(source_statuses) == 1 else 'VALORI_DIVERSI' if row['status'] and source_statuses else 'CAMPO_DA_COMPLETARE'
        trial_rows.append(row)
    valid_metadata = [row for row in paper_rows if row['metadata_check'] == 'IDENTITA_CONFORME']
    valid_trials = [row for row in trial_rows if row['payload_check'] == 'IDENTITA_CONFORME']
    paper_summary = {'unique_pmids': len(paper_rows), 'gca_links': sum(row['gca_count'] for row in paper_rows),
        'metadata_checks': distribution(paper_rows,'metadata_check'), 'abstract_checks': distribution(paper_rows,'abstract_check'),
        'abstracts_with_text': sum(row['abstract_chars'] > 0 for row in paper_rows), 'fulltexts_with_body': sum(row['fulltext_available'] for row in paper_rows),
        'metadata_fields': {key: sum(bool(row.get(key)) for row in valid_metadata) for key in ('title','journal','year','doi','languages','publication_types','authors_count')},
        'years': distribution(valid_metadata,'year'), 'journals': distribution(valid_metadata,'journal'),
        'languages': distribution(valid_metadata,'languages',True), 'publication_types': distribution(valid_metadata,'publication_types',True),
        'manifest_checks': dict(Counter(row['manifest_check']['state'] for row in paper_rows)),
        'pmc_checks': dict(Counter(check['state'] for row in paper_rows for check in row['pmc_checks'])),
        'snapshot_statuses': distribution(paper_rows,'snapshot_status'), 'abstract_length': sizes(paper_rows,'abstract_chars'),
        'association_multiplicity': sizes(paper_rows,'gca_count'), 'families': dict(sum((Counter(row['families']) for row in paper_rows), Counter()))}
    trial_summary = {'unique_ncts': len(trial_rows), 'gca_links': sum(row['gca_count'] for row in trial_rows),
        'payload_checks': distribution(trial_rows,'payload_check'), 'manifest_checks': dict(Counter(row['manifest_check']['state'] for row in trial_rows)),
        'graph_statuses': dict(Counter(value for row in trial_rows for value in row['source'].get('status',[]))),
        'graph_phases': dict(Counter(value for row in trial_rows for raw in row['source'].get('phase',[]) for value in {v.strip() for v in raw.split(',') if v.strip()})),
        'graph_fields': {key: sum(bool(row['source'].get(key)) for row in trial_rows) for key in ('title','conditions','interventions','status','phase')},
        'cached_fields': {key: sum(bool(row.get(key)) for row in valid_trials) for key in ('title','study_type','status','phases','conditions','has_brief_summary','has_detailed_description','has_eligibility_criteria','has_sex','has_age','has_primary_outcomes','has_secondary_outcomes','arm_groups_count','interventions_count')},
        'status_comparison': distribution(valid_trials,'status_comparison'), 'cached_statuses': distribution(valid_trials,'status'),
        'study_types': distribution(valid_trials,'study_type'), 'phases': distribution(valid_trials,'phases',True),
        'conditions': distribution(valid_trials,'conditions',True), 'intervention_types': distribution(valid_trials,'intervention_types',True),
        'countries': distribution(valid_trials,'countries',True), 'sponsor_classes': distribution(valid_trials,'sponsor_class'),
        'results': dict(Counter('RISULTATI_DEPOSITATI' if row.get('has_results') is True else 'CAMPO_HASRESULTS_FALSE' if row.get('has_results') is False else 'CAMPO_ASSENTE' for row in valid_trials)),
        'enrollment': sizes(valid_trials,'enrollment'), 'association_multiplicity': sizes(trial_rows,'gca_count'),
        'families': dict(sum((Counter(row['families']) for row in trial_rows), Counter()))}
    relevant = {'pmid:' + key for key in papers} | {'nct:' + key for key in trials} | {'pmcid:' + check['pmcid'] for row in paper_rows for check in row['pmc_checks']}
    return {'papers': {'summary': paper_summary, 'inventory': paper_rows}, 'trials': {'summary': trial_summary, 'inventory': trial_rows},
        'malformed_references': malformed,
        'provenance': {'corpus_sha256': sha256(corpus.read_bytes()).hexdigest(), 'cache_root': str(root.resolve()),
                       'cache_selection': 'RESEARCH_DOCUMENT_CACHE_PATH' if os.getenv('RESEARCH_DOCUMENT_CACHE_PATH','').strip() else 'RESEARCH_PIPELINE_CACHE_ROOT' if os.getenv('RESEARCH_PIPELINE_CACHE_ROOT','').strip() else 'DEFAULT_DATA_ROOT',
                       'files_sha256': dict(sorted(inputs.hashes.items())), 'latest_manifest_policy': 'Last row for each document_id, matching AuthorizedDocumentCache._cached_manifest',
                       'manifest_rows_relevant': sum(count for key,count in history.items() if key in relevant),
                       'manifest_document_ids_relevant': sum(key in relevant for key in history),
                       'source_files': ['backend/research_pipeline/documents/cache_runtime.py','backend/research_pipeline/documents/authorized_cache.py','backend/research_pipeline/documents/trial_resolution.py'],
                       'scope': 'Complete corpus reference census and read-only inspection of local payloads. Clinical outcomes belong to case-level source analysis.'}}


def render(audit, base_html, table, section, number, percent) -> str:
    p, t = audit['papers']['summary'], audit['trials']['summary']
    pden, tden = p['metadata_checks'].get('IDENTITA_CONFORME',0), t['payload_checks'].get('IDENTITA_CONFORME',0)
    sections = []
    def dist(title, data, denominator, limit=None):
        rows = sorted(data.items(),key=lambda pair:(-pair[1],str(pair[0])))
        if limit:
            rows = rows[:limit]
        return '<h3>' + escape(title) + '</h3>' + table(['Valore','Documenti o studi','% dell’insieme indicato'],[[k,number(v),percent(v,denominator)] for k,v in rows])
    def fields(data, denominator):
        return table(['Campo valorizzato','Record','% dell’insieme indicato'],[[k,number(v),percent(v,denominator)] for k,v in data.items()])
    sections.append(section('perimetro','Due insiemi, due unità di lettura','Una pubblicazione è identificata dal PMID; uno studio dal codice NCT. Il censimento raggruppa tutte le GCA che condividono lo stesso identificativo e poi esamina i metadati e i file conservati nella cache locale.',
        '<p>Per le pubblicazioni si contano ' + number(p['unique_pmids']) + ' PMID numerici distinti; i valori DOI presenti nel campo PMID restano elencati tra i riferimenti da ricondurre al tipo corretto. Per gli studi si contano ' + number(t['unique_ncts']) + ' codici NCT distinti. Le statistiche bibliografiche usano i ' + number(pden) + ' record PubMed con identità verificata; quelle sui contenuti degli studi usano i ' + number(tden) + ' payload NCT con identità verificata.</p><p>Il grafo conserva i metadati della propria esportazione; la cache conserva gli snapshot delle fonti recuperate. Le due provenienze sono presentate separatamente. Gli stati di reclutamento descrivono lo snapshot letto e la valutazione di eleggibilità individuale appartiene all’analisi del caso.</p>'))
    paper_body = table(['Misura','Valore','Insieme di riferimento'],[
        ['Pubblicazioni con PMID numerico',number(p['unique_pmids']),'PMID distinti nel corpus'],['Collegamenti alle GCA',number(p['gca_links']),'GCA che citano questi PMID'],
        ['Metadati con identità conforme',number(pden),number(p['unique_pmids'])+' PMID'],['Abstract con testo e identità conforme',number(p['abstracts_with_text']),number(p['unique_pmids'])+' PMID'],
        ['Testo completo PMC con corpo e identità conforme',number(p['fulltexts_with_body']),number(p['unique_pmids'])+' PMID']])
    paper_body += '<p>Il controllo del PMID confronta il codice richiesto con uid nei metadati e con MedlineCitation/PMID nell’XML PubMed. Per il testo PMC vengono confrontati entrambi i codici, PMID e PMCID, dichiarati nel frontespizio XML. Il corpo dell’articolo e l’abstract vengono poi esaminati per la presenza di testo.</p>'
    paper_body += '<p>Il controllo ha trovato ' + number(p['pmc_checks'].get('IDENTITA_CONFORME',0)) + ' collegamenti PMID–PMCID con identità conforme; per ' + number(p['fulltexts_with_body']) + ' pubblicazioni è disponibile anche il corpo testuale dell’articolo.</p>'
    paper_body += dist('Metadati PubMed: presenza e identità',p['metadata_checks'],p['unique_pmids']) + dist('Abstract PubMed: presenza e identità',p['abstract_checks'],p['unique_pmids'])
    paper_body += '<h3>Campi bibliografici disponibili</h3><p>Denominatore: '+number(pden)+' metadati con identità conforme.</p>' + fields(p['metadata_fields'],pden)
    paper_body += dist('Anni di pubblicazione',p['years'],pden) + dist('Riviste più rappresentate · prime 15',p['journals'],pden,15)
    paper_body += '<p>Tipi di pubblicazione e lingue possono avere più valori nello stesso record: ogni valore è contato una volta per pubblicazione.</p>' + dist('Tipi di pubblicazione · primi 15',p['publication_types'],pden,15) + dist('Lingue',p['languages'],pden)
    paper_body += dist('Disponibilità dichiarata nello snapshot di risoluzione',p['snapshot_statuses'],p['unique_pmids'])
    paper_body += '<p>Lo snapshot descrive la risoluzione registrata; i controlli sui file descrivono il contenuto locale letto dall’audit. La tabella delle impronte confronta il file indicato dall’ultima voce del manifest con l’hash dichiarato.</p>' + dist('Impronte del payload principale indicato nel manifest',p['manifest_checks'],p['unique_pmids'])
    paper_body += '<h3>Verifiche delle coppie PMID–PMCID</h3><p>Qui l’unità di conteggio è il collegamento tra una pubblicazione e un codice PMC dichiarato nel corpus, nel manifest di risoluzione o nei metadati verificati. Una pubblicazione può avere più collegamenti.</p>' + dist('Contenuti XML PMC associati',p['pmc_checks'],sum(p['pmc_checks'].values()))
    sections.append(section('paper','Pubblicazioni · contenuti e copertura','Il PMID collega la relazione del grafo alla scheda bibliografica e al materiale testuale usato dal sistema: abstract PubMed o articolo completo PMC. L’audit segue questo collegamento fino al file locale.',paper_body))
    trial_body = table(['Misura','Valore','Insieme di riferimento'],[
        ['Studi NCT distinti',number(t['unique_ncts']),'Codici NCT nel corpus'],['Collegamenti alle GCA',number(t['gca_links']),'GCA che citano questi studi'],
        ['Payload con identità conforme',number(tden),number(t['unique_ncts'])+' NCT'],['Studi con criteri testuali',number(t['cached_fields']['has_eligibility_criteria']),number(tden)+' payload conformi'],
        ['Studi con risultati depositati',number(t['results'].get('RISULTATI_DEPOSITATI',0)),number(tden)+' payload conformi']])
    trial_body += '<p>Il codice NCT atteso viene confrontato con protocolSection/identificationModule/nctId nel JSON. Il controllo dell’impronta usa il file indicato dal manifest. I criteri di ammissione sono descrizioni dello studio; i risultati depositati sono rilevati dal campo hasResults.</p>'
    trial_body += dist('Payload del registro: presenza e identità',t['payload_checks'],t['unique_ncts']) + dist('Impronte dichiarate nel manifest',t['manifest_checks'],t['unique_ncts'])
    trial_body += '<h3>Metadati conservati nel grafo</h3><p>Denominatore: '+number(t['unique_ncts'])+' NCT. Ogni valore è contato una volta per studio; eventuali valori diversi conservati per lo stesso NCT rimangono nell’inventario.</p>' + fields(t['graph_fields'],t['unique_ncts'])
    trial_body += dist('Stato registrato nel grafo',t['graph_statuses'],t['unique_ncts']) + dist('Fasi registrate nel grafo',t['graph_phases'],t['unique_ncts'])
    trial_body += '<h3>Contenuti del registro conservati nella cache</h3><p>Denominatore: '+number(tden)+' payload con identità conforme. Fasi, condizioni, tipi di intervento e paesi possono contribuire a più categorie.</p>' + fields(t['cached_fields'],tden)
    trial_body += dist('Tipo di studio',t['study_types'],tden) + dist('Stato nello snapshot della cache',t['cached_statuses'],tden) + dist('Fasi nello snapshot della cache',t['phases'],tden)
    trial_body += dist('Condizioni più rappresentate · prime 15',t['conditions'],tden,15) + dist('Tipi di intervento',t['intervention_types'],tden)
    trial_body += dist('Risultati depositati nel registro',t['results'],tden) + dist('Classi degli sponsor principali',t['sponsor_classes'],tden) + dist('Paesi rappresentati · primi 15',t['countries'],tden,15)
    trial_body += '<h3>Confronto dello stato tra grafo e cache</h3><p>Si confrontano i valori testuali del campo di stato nei due snapshot. Valori diversi indicano un punto da leggere nelle rispettive versioni della fonte. Il confronto conserva il perimetro dei '+number(tden)+' studi con payload conforme.</p>' + dist('Corrispondenza dello stato',t['status_comparison'],tden)
    trial_body += '<p>Il registro descrive obiettivi, disegno, interventi, bracci e criteri dello studio. L’attribuzione di un risultato a una relazione terapeutica richiede l’analisi delle osservazioni e dei relativi controlli. Il backend mantiene separati lo stato dello studio e l’eleggibilità del caso.</p>'
    sections.append(section('nct','Studi NCT · struttura e contenuti','Il codice NCT identifica uno studio registrato. Le GCA lo collegano a geni o interventi; il JSON del registro ne descrive protocollo, popolazione, bracci, criteri e risultati depositati.',trial_body))
    stats_rows = []
    for label,measure,unit in [('GCA per pubblicazione',p['association_multiplicity'],'GCA'),('Caratteri negli abstract',p['abstract_length'],'caratteri'),('GCA per studio',t['association_multiplicity'],'GCA'),('Arruolamento dichiarato',t['enrollment'],'partecipanti dichiarati')]:
        stats_rows.append([label,number(measure['records']),str(measure['min']),str(measure['median']),str(measure['max']),unit])
    sections.append(section('distribuzioni','Dimensioni e concentrazione delle fonti','Queste misure aiutano a capire quanto materiale e quante associazioni si concentrano attorno alla stessa fonte. Gli arruolamenti descrivono il valore dichiarato da ciascuno studio nello snapshot.',
        table(['Misura','Valori valorizzati','Minimo','Mediana','Massimo','Unità'],stats_rows) + dist('GCA per famiglia collegate alle pubblicazioni',p['families'],p['gca_links']) + dist('GCA per famiglia collegate agli studi',t['families'],t['gca_links']) + '<p>Le frequenze delle associazioni descrivono la composizione del corpus. Le misure bibliografiche e di protocollo forniscono il contesto per l’analisi delle fonti.</p>'))
    examples = []
    for kind,key in [('papers','28891408'),('trials','NCT02279004')]:
        row = next((row for row in audit[kind]['inventory'] if row.get('pmid',row.get('nct')) == key),None)
        if row:
            examples.append('<h3>'+key+'</h3><pre>'+escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre>')
    sections.append(section('esempi-fonti','Le fonti dell’esempio BRAF','Le due schede seguenti riportano il risultato del censimento per la pubblicazione e il registro già usati nella spiegazione dell’architettura. Le osservazioni e gli esiti del caso sono consultabili nel percorso BRAF.', ''.join(examples)))
    anomalies = []
    for kind in ('papers','trials'):
        for row in audit[kind]['inventory']:
            identifier = row.get('pmid',row.get('nct'))
            for field in ('metadata_check','abstract_check','payload_check'):
                if row.get(field) in ('IDENTITA_DA_ESAMINARE','JSON_DA_ESAMINARE','XML_DA_ESAMINARE'):
                    anomalies.append([identifier,field,row[field]])
            if row['manifest_check']['state'] in ('IMPRONTA_DA_ESAMINARE','PERCORSO_DA_ESAMINARE'):
                anomalies.append([identifier,'manifest_check',row['manifest_check']['state']])
            for item in row.get('pmc_checks',[]):
                if item['state'] in ('IDENTITA_DA_ESAMINARE','FORMATO_DA_ESAMINARE','XML_DA_ESAMINARE'):
                    anomalies.append([identifier+' / '+item['pmcid'],'pmc_check',item['state']])
                if item.get('manifest_check',{}).get('state') in ('IMPRONTA_DA_ESAMINARE','PERCORSO_DA_ESAMINARE'):
                    anomalies.append([identifier+' / '+item['pmcid'],'pmc_manifest_check',item['manifest_check']['state']])
    malformed = audit['malformed_references']
    body = table(['Record GCA','Campo','Valore da ricondurre al tipo corretto'],[[row['candidate_id'],row['field'],row['value']] for row in malformed])
    body += '<h3>Controlli da esaminare sui contenuti locali</h3>' + (table(['Identificatore','Controllo','Esito'],anomalies) if anomalies else '<p>I contenuti letti hanno superato i controlli di formato e identità elencati. Le disponibilità dei file sono descritte nelle tabelle di copertura.</p>')
    body += '<p>Le verifiche di identità e impronta descrivono la corrispondenza del contenuto alla fonte dichiarata. Il significato scientifico della relazione viene esaminato nei successivi controlli dell’architettura.</p>'
    sections.append(section('integrita-fonti','Integrità dei riferimenti e dei contenuti','Ogni identificatore viene seguito dal record GCA al contenuto locale disponibile. Le stringhe DOI collocate nel campo PMID sono conservate qui con il record di provenienza.',body))
    sections.append(section('inventari','Inventari completi e metodo','Le tabelle di sintesi derivano dal censimento completo degli identificativi del corpus. Gli inventari scaricabili contengono una riga per pubblicazione o studio, con copertura, controlli e proprietà utili alla lettura.',
        '<p><a href="verifica/paper-audit-inventario.csv" download>Inventario delle pubblicazioni · CSV</a> · <a href="verifica/nct-audit-inventario.csv" download>Inventario degli studi · CSV</a> · <a href="verifica/fonti-audit.json" download>Audit completo con impronte · JSON</a></p><p>Il censimento legge i file della cache selezionata con le stesse variabili del runtime. Per ogni document_id del manifest usa l’ultima voce registrata, come il lettore del backend. Il JSON conserva l’impronta di ogni file letto. Gli stati PubMed e NCT descrivono i rispettivi snapshot locali; le valutazioni cliniche del caso appartengono al dossier.</p><details><summary>Provenienza e criteri di lettura</summary><pre>' + escape(json.dumps({key:value for key,value in audit['provenance'].items() if key != 'files_sha256'},ensure_ascii=False,indent=2)) + '</pre></details>'))
    nav = '<nav class="audit-nav" aria-label="Sezioni audit fonti">' + ''.join('<a href="#'+key+'">'+label+'</a>' for key,label in [('perimetro','Perimetro'),('paper','Pubblicazioni'),('nct','Studi NCT'),('distribuzioni','Distribuzioni'),('esempi-fonti','Esempio BRAF'),('integrita-fonti','Integrità'),('inventari','Inventari e metodo')]) + '</nav>'
    cards = '<div class="audit-stats">' + ''.join('<div><strong>'+number(value)+'</strong><span>'+label+'</span></div>' for value,label in [(p['unique_pmids'],'PMID numerici distinti'),(p['abstracts_with_text'],'pubblicazioni con abstract leggibile'),(t['unique_ncts'],'studi NCT distinti'),(tden,'studi con payload e identità conforme')]) + '</div>'
    main = '<main class="audit-main" id="main"><p>Audit delle fonti · pubblicazioni e studi registrati</p><h1>Dentro le pubblicazioni e gli studi NCT</h1><p>Dai riferimenti delle GCA ai metadati e ai contenuti conservati nella cache.</p>'+nav+cards+''.join(sections)+'</main>'
    result = re.sub(r'<main class="audit-main" id="main">.*?</main>',lambda _:main,base_html,flags=re.S)
    result = result.replace('<title>Audit GCA · struttura e corpus</title>','<title>Audit delle pubblicazioni e degli studi NCT</title>')
    result = result.replace('</header>', '<a href="Audit_GCA_per_il_relatore.html">Audit GCA</a></header>', 1)
    return result


def write(audit: dict, folder: Path):
    (folder / 'fonti-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    fields = {
        'papers': ('paper-audit-inventario.csv', ['pmid','title','gca_count','candidate_ids','evidence_count','evidence_ids','families','pmcids_in_corpus','snapshot_status','metadata_check','abstract_check','abstract_chars','abstract_parts','fulltext_available','year','journal','doi','publication_types','languages','manifest_check','pmc_checks']),
        'trials': ('nct-audit-inventario.csv', ['nct','gca_count','candidate_ids','families','source','genes','drugs','payload_check','manifest_check','title','study_type','status','phases','conditions','has_brief_summary','has_eligibility_criteria','has_results','arm_groups_count','interventions_count','enrollment','status_comparison'])}
    for kind,(name,keys) in fields.items():
        with (folder / name).open('w',encoding='utf-8-sig',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=keys)
            writer.writeheader()
            for row in audit[kind]['inventory']:
                values_to_write = {}
                for key in keys:
                    value = row.get(key,'')
                    value = json.dumps(value,ensure_ascii=False,sort_keys=True) if isinstance(value,(dict,list)) else value
                    if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')):
                        value = "'" + value
                    values_to_write[key] = value
                writer.writerow(values_to_write)
