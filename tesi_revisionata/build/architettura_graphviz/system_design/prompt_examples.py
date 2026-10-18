"""Readable response examples drawn from archives and an explicit test fixture."""
from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path

EXPLANATIONS = {
    'parser': {
        'task': 'Legge il testo del caso e organizza le informazioni dichiarate: malattia, gene, variante e intervento oggetto della domanda.',
        'why': 'Serve a trasformare una descrizione libera in un caso che il sistema possa usare per cercare le relazioni pertinenti, conservando le parole e il contesto originali.',
        'flow': 'Testo del caso → informazioni estratte → controllo del testo → riconoscimento delle entità → ricerca nel grafo',
        'controls': 'Ogni informazione estratta viene ricondotta al testo del caso. Il sistema verifica le citazioni e riconosce le entità da utilizzare nella ricerca; eventuali ambiguità restano visibili.',
    },
    'reader': {
        'task': 'Legge i passaggi selezionati di una fonte e descrive ciò che riportano, accompagnando l’osservazione con una citazione. Può anche astenersi quando il materiale è insufficiente.',
        'why': 'Serve a passare dalla relazione trovata nel grafo al contenuto della fonte: popolazione studiata, alterazioni considerate, trattamento e osservazione riportata.',
        'flow': 'Passaggi della fonte → osservazione con citazione → controllo della citazione → verifiche sulla relazione',
        'controls': 'Il sistema controlla che la citazione appartenga alla fonte e valuta separatamente il collegamento con la relazione cercata. La lettura conserva il contesto dello studio e i suoi limiti.',
    },
    'semantica': {
        'task': 'Confronta la relazione cercata con ciò che il passaggio della fonte afferma. Distingue, per esempio, un risultato osservato dalla semplice descrizione di come è organizzato uno studio.',
        'why': 'La presenza dello stesso gene e dello stesso farmaco rende una fonte interessante. Per capire quale relazione sostenga, occorre confrontare anche popolazione, intervento, direzione e contesto dell’affermazione.',
        'flow': 'Relazione da verificare + passaggio della fonte → confronto del significato → decisione del codice',
        'controls': 'Nel percorso attuale questo confronto riguarda specifiche relazioni fra evidenza e farmaco, dopo i controlli preliminari. Il codice verifica i passaggi citati e usa il confronto per decidere come conservare l’evidenza nel dossier.',
    },
    'narratore': {
        'task': 'Riceve il contenuto del dossier e lo spiega in italiano: la domanda, le relazioni esaminate, le osservazioni delle fonti, i controlli e i limiti.',
        'why': 'Serve a collegare le informazioni in un racconto leggibile. Il prompt è in inglese e richiede di usare esclusivamente il dossier ricevuto, mantenendo il significato dei risultati.',
        'flow': 'Dossier → schede delle fonti + spiegazione in italiano → verifica delle schede e del testo → presentazione',
        'controls': 'Il codice conserva le schede delle fonti e i dati di ogni osservazione. Ogni spiegazione include un raccordo esplicito con popolazione e trattamento del caso. Più studi della stessa relazione richiedono un confronto. Il limite sull’applicabilità clinica compare una sola volta. Il verificatore controlla presenza e vincoli su fonti, citazioni e quantità; la valutazione semantica esamina separatamente il significato delle parafrasi.',
    },
}


def load_examples(root: Path) -> dict:
    archive = root / 'experiments_real/remaining_fixes_20261015/live4/E2E20-16'
    run_path = archive / 'run.json'
    dossier_path = archive / 'dossier.json'
    run = json.loads(run_path.read_text(encoding='utf-8'))
    parser = next(stage['output_preview']['case_context'] for stage in run['stages']
                  if 'casecontext_parser' in stage.get('stage_id', ''))
    dossier = json.loads(dossier_path.read_text(encoding='utf-8'))['dossier']
    finding = next(finding for entry in dossier['paper_evidence']
                   for finding in entry.get('documentary_findings', [])
                   if finding['source']['public_source_identity'] == 'pmid:28891408')
    fixture_path = root / 'mtb-graphrag/backend/research_pipeline/tests/test_semantic_admission_contract.py'
    tree = ast.parse(fixture_path.read_text(encoding='utf-8'))
    text_node = next(node for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == 'TEXT' for target in node.targets))
    text = ast.literal_eval(text_node.value)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'assessment')
    # Read the literal fixture's return expression, substituting its two parameters.
    returned = function.body[-1].value
    assessment = {}
    for key, value in zip(returned.keys, returned.values):
        if key is None:  # **changes is empty for the fixture's default example
            continue
        assessment[ast.literal_eval(key)] = text if isinstance(value, ast.Name) and value.id == 'text' else ast.literal_eval(value)
    live_path = root / 'mtb-graphrag/evaluation/multistudy_narrator_v51_verified/results.json'
    live = json.loads(live_path.read_text(encoding='utf-8'))
    narrated = next(row for row in live['cases'] if row['name'] == 'BRAF_22663011')
    narrative = narrated['call']['narrative']['candidate_narratives'][0]

    def origin(path):
        return {'file': path.relative_to(root).as_posix(), 'sha256': sha256(path.read_bytes()).hexdigest()}

    return {
        'parser': {
            'label': 'Estratto del risultato archiviato, presentato in forma leggibile.',
            'input': 'Il testo del caso dichiara melanoma metastatico, BRAF V600K e dabrafenib e trametinib come intervento oggetto della ricerca.',
            'rows': [['Malattia', parser['disease']['raw_value']],
                     ['Gene', parser['biomarkers'][0]['gene']],
                     ['Variante associata al gene', parser['biomarkers'][0]['alteration']],
                     ['Intervento oggetto della ricerca', parser['target_intervention']['raw_value']],
                     ['Trattamenti precedenti estratti', 'Nessuno riportato nel risultato']],
            'meaning': 'Il risultato conserva i dettagli del testo e la coppia gene–variante. L’intervento è ciò su cui verte la domanda: la sua somministrazione e il suo beneficio richiedono informazioni esplicite.',
            'raw_response': parser, 'source': origin(run_path),
            'kind': 'ARCHIVED_PARSER_RESULT_READABLE_EXTRACT',
        },
        'reader': {
            'label': 'Osservazione effettivamente registrata dal Reader · pubblicazione PMID 28891408.',
            'input': 'Il Reader riceve i passaggi selezionati della pubblicazione sulla combinazione dabrafenib e trametinib.',
            'rows': [['Contesto descritto dalla fonte', finding['observed']['disease']],
                     ['Trattamento osservato', finding['observed']['intervention']],
                     ['Varianti descritte', 'V600E oppure V600K'],
                     ['Tipo di osservazione', 'Risultato osservato in una coorte']],
            'quotation': finding['quotation'],
            'meaning': 'L’osservazione riguarda il contesto adiuvante nello stadio III descritto dalla fonte. La corrispondenza con il caso metastatico viene valutata nei controlli successivi.',
            'raw_response': {'observed': finding['observed'], 'quotation': finding['quotation']},
            'source': origin(dossier_path), 'kind': 'ARCHIVED_READER_OBSERVATION',
        },
        'semantica': {
            'label': 'Esempio sintetico tratto dai test del contratto: mostra la forma della risposta attesa.',
            'input': text,
            'rows': [['Confronto della relazione', 'La fonte descrive la stessa relazione cercata'],
                     ['Tipo di informazione', 'Un risultato osservato, affermato direttamente'],
                     ['Profilo molecolare, popolazione e intervento', 'Corrispondono al bersaglio del confronto'],
                     ['Passaggio che giustifica il confronto', assessment['decisive_text']]],
            'meaning': 'In questo caso di test il codice ammette il supporto documentale. Se il passaggio descrivesse soltanto il disegno dello studio, il confronto avrebbe un esito diverso. È un esempio del controllo, distinto da una risposta misurata sul caso BRAF.',
            'raw_response': assessment, 'source': origin(fixture_path),
            'kind': 'SYNTHETIC_CONTRACT_TEST_EXPECTED_RESPONSE',
        },
        'narratore': {
            'label': 'Risposta effettiva del modello · trametinib, pubblicazione PMID 22663011. La scheda bibliografica viene composta dai dati della fonte.',
            'input': 'Una voce del dossier su BRAF V600K e trametinib, con osservazione della fonte, autenticazione della citazione e limiti della valutazione.',
            'response_text': '\n\n'.join([narrative['text']] + [value for item in narrative.get('observation_narratives') or []
                for value in (item['text'], item.get('case_relevance')) if value]
                + [narrated['call']['narrative']['limitations_summary']]),
            'source_cards': narrated['narrator_input']['candidates'][0]['source_cards'],
            'meaning': 'La spiegazione collega la relazione esaminata, ciò che riporta la fonte e i limiti dei controlli. Questo estratto appartiene a una risposta che supera le regole del verificatore, con il perimetro semantico descritto nella pagina delle prove.',
            'raw_response': narrative, 'source': origin(live_path),
            'kind': 'RECORDED_MODEL_NARRATIVE_EXCERPT',
        },
    }
