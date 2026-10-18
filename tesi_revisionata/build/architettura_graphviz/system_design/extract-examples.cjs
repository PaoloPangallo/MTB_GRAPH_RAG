'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const readline = require('node:readline');
const assert = require('node:assert/strict');
const base = __dirname;
const sourceRoot = path.resolve(base, '../../../../mtb-graphrag');
const dataRoot = process.env.RESEARCH_PIPELINE_DATA_ROOT ? path.resolve(process.env.RESEARCH_PIPELINE_DATA_ROOT) : sourceRoot;
const corpus = path.join(dataRoot, 'benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/4.0/candidates.jsonl');
const archive = path.resolve(sourceRoot, '../experiments_real/remaining_fixes_20261015/live4/E2E20-16');
const ids = [
  'GCA4-9a002e06fa9adfdb6fa49a8a',
  'GCA4-55e94d5dfe5e8cc4831e24b7',
  'GCA4-90e1b87741de703c9b2274d4',
  'GCA4-1d0d2b23a0b1216b14a49011',
  'GCA4-04b330bf787c3fb25a0f4abe'
];
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function readArchive(file) {
  const bytes = fs.readFileSync(path.join(archive, file));
  return { file, sha256: digest(bytes), value: JSON.parse(bytes.toString('utf8')) };
}
async function extract() {
  const loader = fs.readFileSync(path.join(sourceRoot, 'backend/research_pipeline/data_access.py'), 'utf8');
  const expected = loader.match(/_EXPECTED_CANDIDATES_SHA256\s*=\s*"([a-f0-9]+)"/)[1];
  const hash = crypto.createHash('sha256');
  const stream = fs.createReadStream(corpus);
  stream.on('data', bytes => hash.update(bytes));
  const records = [];
  const wanted = new Set(ids);
  for await (const line of readline.createInterface({ input: stream, crlfDelay: Infinity })) {
    if (!line.trim()) continue;
    const row = JSON.parse(line);
    if (wanted.has(row.candidate_id)) records.push(row);
  }
  const actual = hash.digest('hex');
  assert.equal(actual, expected, 'The runtime candidate corpus must match the loader contract');
  assert.equal(records.length, ids.length, 'All examples must exist in the runtime corpus');
  const byId = new Map(records.map(row => [row.candidate_id, row]));
  const saved = ['input.json', 'run.json', 'dossier.json'].map(readArchive);
  const input = saved[0].value;
  const run = saved[1].value;
  const dossier = saved[2].value.dossier;
  assert.match(input.clinical_text, /sintetico/);
  const paper = dossier.paper_evidence.find(row => row.candidate_id === ids[0]);
  const trial = dossier.clinical_trials.find(row => row.candidate_id === ids[3]);
  const diagnostic = dossier.kg_only_relations.find(row => row.candidate_id === ids[4]);
  assert.ok(paper && trial && diagnostic, 'Examples must also be present in the archived analysis');
  assert.equal(paper.document_id, 'pmid:28891408');
  assert.equal(paper.quote_valid, true);
  assert.equal(paper.claim.status, 'NO_SUPPORT');
  assert.match(paper.quote, /stage III melanoma/);
  assert.equal(byId.get(ids[0]).subject.label, 'BRAF V600K');
  for (const id of ids.slice(1, 3)) {
    assert.equal(byId.get(id).subject.id, byId.get(ids[0]).object.id);
    assert.ok(byId.get(id).document_identifiers.some(item => item.pmid === '28891408'));
  }
  assert.equal(trial.nct_id, 'NCT02279004');
  assert.equal(trial.eligibility_status, 'NOT_EVALUATED');
  assert.equal((byId.get(ids[4]).document_identifiers || []).length, 0);
  assert.equal(diagnostic.object.label, 'BRAF');
  const observation = paper.evidence_records[0].observed_relation;
  assert.equal(observation.disease, 'stage III melanoma');
  const selection = run.stages.find(stage => stage.stage_id === 'stage_8_paper_selection')
    .output_preview.selections.find(item => item.candidate_id === ids[0]);
  const selectedPassages = selection.selected_papers.flatMap(item => item.resolved_source_unit_ids || []);
  const resolution = run.stages.find(stage => stage.stage_id === 'stage_4_retrieval_plan').output_preview.entity_resolution;
  const resolvedDisease = resolution.diseases[0];
  const resolvedGene = resolution.biomarkers[0].gene;
  const resolvedVariant = resolution.biomarkers[0].variant;
  const resolvedIntervention = resolution.interventions[0];
  assert.ok(resolvedDisease.concept_ids.includes('DOID:1909'));
  assert.equal(resolvedDisease.residual_context, 'metastatic');
  assert.ok(resolvedGene.concept_ids.includes('NCBIGene:673'));
  assert.ok(resolvedVariant.concept_ids.includes('CIViCVariant:563'));
  assert.equal(resolvedIntervention.status, 'UNMAPPED');
  const gateStatus = run.stages.find(stage => stage.stage_id === 'stage_12_status')
    .output_preview.statuses.find(item => item.candidate_id === ids[0]);
  assert.equal(gateStatus.status, 'AMBIGUOUS');
  assert.ok(gateStatus.warnings.includes('NO_VALIDATED_ENRICHMENT_AVAILABLE'));
  const calls = run.stages.find(stage => stage.stage_id === 'stage_9_paper_context_enricher').output_preview.calls;
  const statuses = run.stages.find(stage => stage.stage_id === 'stage_12_status').output_preview.statuses;
  const trialCall = calls.find(row => row.candidate_id === ids[3]);
  const trialGate = statuses.find(row => row.candidate_id === ids[3]);
  assert.equal(trialCall.model_call_count, 0);
  assert.equal(trialCall.model, null);
  assert.ok(trialCall.trial_facts);
  assert.equal(trialGate.status, 'AMBIGUOUS');
  assert.equal(trial.claim.status, 'TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE');
  assert.equal(calls.some(row => row.candidate_id === ids[4]), false);
  assert.equal(statuses.some(row => row.candidate_id === ids[4]), false);
  const compactResolution = record => Object.fromEntries(['raw_value','status','method','concept_ids','residual_context'].filter(key => key in record).map(key => [key, record[key]]));
  const proof = {
    corpus: { file: corpus, sha256: actual, loader: 'backend/research_pipeline/data_access.py' },
    records: records.map(row => ({ candidate_id: row.candidate_id, semantic_key: row.semantic_key, record_sha256: digest(JSON.stringify(row)), record: row })),
    execution: { runId: run.run_id, caseId: input.case_id, syntheticCase: true, startedAt: run.started_at,
      files: saved.map(({ file, sha256 }) => ({ file: path.join(archive, file), sha256 })),
      stageStatuses: run.stages.map(stage => ({ id: stage.stage_id, status: stage.status })) },
    newExecutionPerformed: false,
    entityResolution: { disease: compactResolution(resolvedDisease), gene: compactResolution(resolvedGene), variant: compactResolution(resolvedVariant), intervention: compactResolution(resolvedIntervention) },
    operationalGateExample: gateStatus,
    paper: { candidateId: paper.candidate_id, documentId: paper.document_id, quote: paper.quote,
      quoteAuthenticated: paper.quote_valid, claimSupport: paper.claim.status, observation, selectedPassages,
      archivePointer: '/dossier/paper_evidence/' + dossier.paper_evidence.indexOf(paper) },
    trial: { candidateId: trial.candidate_id, code: trial.nct_id, title: trial.title, savedStatus: trial.status,
      conditions: trial.conditions, eligibility: trial.eligibility_status, claimSupport: trial.claim.status,
      modelCalls: trialCall.model_call_count, structuredFacts: trialCall.trial_facts, operationalGate: trialGate },
    diagnostic: { candidateId: diagnostic.candidate_id, name: diagnostic.subject.label, gene: diagnostic.object.label, sourceAvailable: false },
    counts: { associations: saved[2].value.candidate_count, publications: dossier.paper_evidence.length,
      trials: dossier.clinical_trials.length, graphOnly: dossier.kg_only_relations.length }
  };
  fs.mkdirSync(path.join(base, 'verifica'), { recursive: true });
  fs.writeFileSync(path.join(base, 'verifica/esempi.json'), JSON.stringify(proof, null, 2));
  const examples = {
    date: '15 ottobre 2026',
    description: 'Associazioni presenti nel Knowledge Graph in uso, collegate a un’analisi registrata su un caso sintetico. Non sono dati di un paziente reale e non è stata eseguita una nuova analisi.',
    caseSummary: [ ['Malattia', dossier.case_summary.disease], ['Gene', dossier.case_summary.gene],
      ['Variante', dossier.case_summary.variant], ['Interesse della ricerca', dossier.case_summary.intervention] ],
    caseText: input.clinical_text,
    counts: proof.counts,
    items: [
      { id: 'melanoma', label: 'Melanoma e BRAF V600K', title: 'Una pubblicazione da confrontare con il caso',
        lead: 'Il Knowledge Graph collega BRAF V600K alla descrizione di uno studio e alla pubblicazione 28891408. Due ulteriori collegamenti, riferiti alla stessa descrizione, indicano dabrafenib e trametinib.',
        path: ['BRAF V600K', 'Descrizione dello studio', 'Pubblicazione 28891408'],
        facts: [['Nel caso', 'Melanoma metastatico; BRAF V600K.'], ['Nella fonte osservata', 'Melanoma di stadio III; trattamento adiuvante; varianti V600E oppure V600K.'],
          ['Passaggi scelti', String(selectedPassages.length) + ' per la pubblicazione nell’analisi registrata.'],
          ['Esito registrato', 'Citazione autenticata; supporto non attribuito alla relazione conservata.']],
        quote: paper.quote.split(/\s+/).slice(0, 23).join(' ') + '…',
        limitation: 'La citazione non dimostra che il risultato sia trasferibile al caso metastatico o che riguardi separatamente la sola variante V600K. Le differenze di contesto restano da esaminare; non sono presentate come la causa accertata dell’esito registrato.',
        sourceLabel: 'Pubblicazione PubMed 28891408', sourceUrl: 'https://pubmed.ncbi.nlm.nih.gov/28891408/',
        provenance: 'Tre associazioni effettivamente presenti nel Knowledge Graph; osservazione e citazione conservate nell’analisi del 15 ottobre 2026.',
        kind: 'Pubblicazione scientifica' },
      { id: 'studio', label: 'Uno studio sul sangue', title: 'Un collegamento a uno studio, non una prova di efficacia',
        lead: 'Tra le associazioni del caso compare uno studio che valuta la genotipizzazione del plasma nel tumore del polmone e nel melanoma. Il collegamento riguarda BRAF.',
        path: ['BRAF', 'Studio sul plasma', 'Informazioni del registro'],
        facts: [['Studio', trial.nct_id], ['Titolo registrato', trial.title], ['Condizioni registrate', trial.conditions.map(value => value === 'NSCLC' ? 'Carcinoma polmonare non a piccole cellule' : value).join('; ')],
          ['Eleggibilità personale', 'Non valutata. Il collegamento non stabilisce che il caso possa partecipare.']],
        limitation: 'Il registro descrive uno studio e i suoi obiettivi. Questa associazione non è una prova di efficacia di dabrafenib o trametinib. Le informazioni appartengono alla copia consultata allora, non a una verifica attuale del reclutamento.',
        sourceLabel: 'Registro dello studio ' + trial.nct_id, sourceUrl: 'https://clinicaltrials.gov/study/' + trial.nct_id,
        provenance: 'Associazione tra lo studio e BRAF presente nel Knowledge Graph; informazioni del registro conservate nell’analisi del 15 ottobre 2026.',
        kind: 'Registro di uno studio' },
      { id: 'diagnostica', label: 'Un collegamento diagnostico', title: 'Un’informazione utile anche senza pubblicazione associata',
        lead: 'Il Knowledge Graph collega FoundationOne CDx al gene BRAF. In questa associazione non sono presenti riferimenti a una pubblicazione o a uno studio clinico.',
        path: ['FoundationOne CDx', 'Collegamento diagnostico', 'BRAF', 'Provenienza nel Knowledge Graph'],
        facts: [['Test indicato nel grafo', diagnostic.subject.label], ['Gene collegato', diagnostic.object.label],
          ['Pubblicazione associata', 'Non presente in questa associazione.'], ['Livello del collegamento', 'Riferito al gene BRAF; non viene reso specifico per V600K.']],
        limitation: 'Il sistema conserva il collegamento e la sua origine. Non simula una lettura della letteratura e non inventa una citazione per rafforzarlo.',
        sourceLabel: 'Associazione diagnostica nel Knowledge Graph', sourceUrl: null,
        provenance: 'Associazione effettivamente presente nel Knowledge Graph e conservata nel dossier del 15 ottobre 2026.',
        kind: 'Sola provenienza nel Knowledge Graph' }
    ]
  };
  const text = '(function(root){const examples=' + JSON.stringify(examples, null, 2) + ';if(typeof module!=="undefined"&&module.exports)module.exports=examples;root.ArchitectureExamples=examples;})(globalThis);\n';
  fs.writeFileSync(path.join(base, 'examples.js'), text);
  console.log(`Verificati ${records.length} record, ${saved.length} file archiviati; ${examples.items.length} esempi reali estratti. Caso sintetico esplicito.`);
}
extract().catch(error => { console.error(error); process.exitCode = 1; });
