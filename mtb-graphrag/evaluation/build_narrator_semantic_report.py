"""Build a traceable semantic audit, preserving both model-assisted readings."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from evaluation.run_narrator_semantic_audit import (
    REPO, evidence_paths, judge_errors, prepare_cases, resolve_pointer,
)

HERE = REPO / 'evaluation'
WEB = REPO.parent / 'tesi_revisionata/build/architettura_graphviz/system_design'
OUT = HERE / 'narrator_semantic_audit_v11'
LABELS = {'ACCEPTABLE': 'Accettabile', 'ACCEPTABLE_WITH_NOTES': 'Accettabile con note',
          'REVISION_REQUIRED': 'Da rivedere', 'UNASSESSABLE': 'Giudizio inutilizzabile'}
NAMES = {'concordant_results': 'Risultati concordanti', 'contrasting_results': 'Risultati contrastanti',
         'different_populations': 'Popolazioni diverse', 'combination_and_monotherapy': 'Monoterapia e combinazione',
         'two_passages_one_study': 'Due passaggi dello stesso studio',
         'excluded_second_observation': 'Osservazione esclusa',
         'BRAF_three_relations': 'BRAF · tre relazioni documentate'}


def build_audit():
    provider_path = OUT / 'results.json'
    provider = json.loads(provider_path.read_text(encoding='utf-8'))
    review_path = HERE / 'narrator_semantic_codex_review.json'
    review = json.loads(review_path.read_text(encoding='utf-8'))
    original_path = REPO / review['source_file']
    if sha256(original_path.read_bytes()).hexdigest() != review['source_sha256']:
        raise ValueError('Reviewed dossier responses changed')
    prepared = prepare_cases()
    by_name = {row['name']: row for row in provider['cases'] if 'expected_verdict' not in row}
    codex = {row['name']: row for row in review['cases']}
    expected = {row['name'] for row in prepared}
    if set(by_name) != expected or set(codex) != expected:
        raise ValueError('Semantic audit case coverage mismatch')
    rows = []
    for row in prepared:
        raw = by_name[row['name']]
        if raw['payload'] != row['payload']:
            raise ValueError('Provider reviewed a different payload')
        judgement = raw['judge_call'].get('judgement')
        errors = judge_errors(judgement, row['payload']) if judgement else ['JUDGEMENT_UNAVAILABLE']
        paths = evidence_paths(row['payload'])
        for finding in codex[row['name']]['findings']:
            for kind in ('narrative', 'input'):
                pointer = finding[kind + '_pointer']
                if pointer not in paths[kind] or finding[kind + '_excerpt'] not in resolve_pointer(row['payload'], pointer):
                    raise ValueError('Codex review evidence does not match saved data')
        rows.append({**row, 'codex_review': codex[row['name']],
                     'provider_review': judgement if not errors else None,
                     'provider_evidence_errors': errors,
                     'provider_model': raw['judge_call']['model']})
    calibration = []
    for row in provider['cases']:
        if 'expected_verdict' not in row:
            continue
        call = row['judge_call']; judgement = call.get('judgement')
        errors = judge_errors(judgement, row['payload']) if judgement else ['JUDGEMENT_UNAVAILABLE']
        calibration.append({'name': row['name'], 'expected_verdict': row['expected_verdict'],
            'observed_verdict': (judgement or {}).get('verdict'), 'evidence_errors': errors,
            'matches_expected': not errors and judgement['verdict'] == row['expected_verdict']})
    summary = {'audited_cases': len(rows), 'mechanical_passes': sum(row['mechanical_status'] == 'PASS' for row in rows),
        'codex_verdicts': dict(Counter(row['codex_review']['verdict'] for row in rows)),
        'provider_verdicts': dict(Counter((row['provider_review'] or {}).get('verdict', 'UNASSESSABLE') for row in rows)),
        'calibration_total': len(calibration), 'calibration_usable': sum(not row['evidence_errors'] for row in calibration),
        'calibration_error_cases': sum(row['expected_verdict'] == 'REVISION_REQUIRED' for row in calibration),
        'calibration_error_cases_detected': sum(row['matches_expected'] and row['expected_verdict'] == 'REVISION_REQUIRED' for row in calibration),
        'calibration_clean_controls': sum(row['expected_verdict'] == 'ACCEPTABLE' for row in calibration),
        'calibration_clean_controls_accepted': sum(row['matches_expected'] and row['expected_verdict'] == 'ACCEPTABLE' for row in calibration)}
    summary['total_judgements'] = len(rows) + len(calibration)
    summary['usable_judgements'] = (sum(row['provider_review'] is not None for row in rows)
                                     + summary['calibration_usable'])
    prior_path = HERE / 'narrator_semantic_audit_v1/results.json'
    prior = json.loads(prior_path.read_text(encoding='utf-8'))
    prior_calls = [row['judge_call'] for row in prior['cases']]
    return {'scope': 'SEMANTIC_FIDELITY_TO_SUPPLIED_DOSSIER', 'production_gate_changed': False,
            'human_or_clinical_gold_standard': False, 'same_model_as_narrator': provider['same_model_as_narrator'],
            'summary': summary, 'cases': rows, 'calibration': calibration,
            'first_trial': {'calls': len(prior_calls),
                'unusable_evidence_records_as_recorded': sum(not call['usable_judgement'] for call in prior_calls),
                'clinical_recommendation_missed': any(row['name'] == 'clinical_recommendation'
                    and row['judge_call']['judgement']['verdict'] == 'ACCEPTABLE' for row in prior['cases'])},
            'provenance': [{'file': p.relative_to(REPO).as_posix(), 'sha256': sha256(p.read_bytes()).hexdigest()}
                           for p in (original_path, review_path, provider_path, prior_path,
                                     HERE / 'run_narrator_semantic_audit.py', Path(__file__).resolve(),
                                     HERE / 'semantic_audit_protocol.md')]}


def p(text):
    return '<p>' + escape(str(text)) + '</p>'


def table(headers, rows):
    return ('<div class="table-scroll"><table class="audit-table"><thead><tr>' +
        ''.join('<th scope="col">' + escape(value) + '</th>' for value in headers) + '</tr></thead><tbody>' +
        ''.join('<tr>' + ''.join('<td>' + escape(str(value)) + '</td>' for value in row) + '</tr>' for row in rows) +
        '</tbody></table></div>')


def finding_html(finding, provider=False):
    html = '<article>' + p(finding['explanation'])
    html += '<p><strong>Passaggio della spiegazione</strong></p><blockquote>' + escape(finding['narrative_excerpt']) + '</blockquote>'
    html += '<p><strong>Dato di riferimento</strong></p><blockquote>' + escape(finding['input_excerpt']) + '</blockquote>'
    if finding.get('suggested_revision'):
        html += '<p><strong>Formulazione proposta per la revisione</strong></p>' + p(finding['suggested_revision'])
    html += '<details><summary>Riferimenti esatti del rilievo</summary><pre>' + escape(json.dumps({
        'severity': finding['severity'], 'category': finding['category'],
        'narrative_pointer': finding['narrative_pointer'], 'input_pointer': finding['input_pointer']}, indent=2)) + '</pre></details></article>'
    return html


def render_html(report):
    summary = report['summary']
    counts = summary['codex_verdicts']
    provider_counts = summary['provider_verdicts']
    provider_description = '; '.join(str(provider_counts.get(key, 0)) + ' ' + label for key, label in (
        ('ACCEPTABLE', 'accettabili'), ('ACCEPTABLE_WITH_NOTES', 'con note'),
        ('REVISION_REQUIRED', 'da rivedere'), ('UNASSESSABLE', 'giudizi inutilizzabili')))
    joint_revision = [NAMES.get(row['name'], row['name'].replace('BRAF_', 'BRAF · PMID '))
                      for row in report['cases'] if row['codex_review']['verdict'] == 'REVISION_REQUIRED'
                      and (row['provider_review'] or {}).get('verdict') == 'REVISION_REQUIRED']
    html = '<main class="audit-main" id="main"><h1>Fedeltà semantica del dossier</h1>'
    html += p(f"{summary['mechanical_passes']} risposte su {summary['audited_cases']} superano i controlli deterministici. "
              f"La revisione Codex individua {counts.get('REVISION_REQUIRED', 0)} risposte da rivedere: "
              'il risultato della pubblicazione è conservato, ma il raccordo con la domanda del caso perde informazioni importanti.')
    html += p('La valutazione confronta la spiegazione con i dati ricevuti. La verifica scientifica degli studi e '
              'l’applicabilità clinica richiedono un’analisi distinta delle pubblicazioni complete.')
    html += '<p><a href="Prove_narratore_per_il_relatore.html">Torna alle risposte effettive</a> · '
    html += '<a href="Prompt_di_sistema_per_il_relatore.html#narratore">Ruolo del narratore</a></p>'
    html += '<section><h2>Che cosa emerge</h2>' + table(['Lettura', 'Esito sulle dieci risposte'], [
        ['Controlli deterministici', str(summary['mechanical_passes']) + ' risposte conformi'],
        ['Revisione Codex, assistita da modello', str(counts.get('ACCEPTABLE', 0)) + ' accettabili; ' +
         str(counts.get('ACCEPTABLE_WITH_NOTES', 0)) + ' con note; ' + str(counts.get('REVISION_REQUIRED', 0)) + ' da rivedere'],
        ['Seconda lettura automatica', provider_description]])
    if joint_revision:
        html += p('Entrambe le letture chiedono revisione per: ' + '; '.join(joint_revision) + '.')
    html += p('La tabella e i rilievi affiancano le due letture, conservando anche giudizi differenti '
              'e osservazioni individuate da una sola lettura.')
    html += p('Sei risposte provengono da fixture sintetiche e quattro da sottoinsiemi archiviati. Questi ultimi '
              'riutilizzano tre pubblicazioni: il caso con tre relazioni non aggiunge studi indipendenti. '
              'I test su più studi della stessa relazione sono sintetici. Registri NCT e sola provenienza nel grafo '
              'restano fuori da questo campione semantico.') + '</section>'
    html += '<section><h2>Le correzioni motivate dai dati</h2><ol>'
    for text in ('Esplicitare stadio III adiuvante e caso metastatico, spiegando la differenza di contesto.',
                 'Distinguere trametinib singolo agente, vemurafenib e combinazione dabrafenib–trametinib rispetto alla domanda.',
                 'Descrivere il controllo come corrispondenza della malattia da confermare, mantenendo distinta la diagnosi della fonte.',
                 'Scrivere “pazienti con V600E oppure V600K”, preservando la composizione molecolare alternativa.',
                 'Conservare i limiti rilevanti anche quando aumenta il numero di relazioni, con una frase comune quando appropriato.'):
        html += '<li>' + escape(text) + '</li>'
    html += '</ol>' + p('Le formulazioni proposte sotto sono suggerimenti di revisione. Le risposte originali restano quelle effettivamente prodotte dal modello.') + '</section>'
    html += '<section><h2>Esiti per caso</h2>' + table(['Caso', 'Dati', 'Revisione Codex', 'Seconda lettura'], [
        [NAMES.get(row['name'], row['name'].replace('BRAF_', 'BRAF · PMID ')),
         'Sintetici' if row['origin'] == 'SYNTHETIC_CONTRACT_FIXTURE' else 'Sottoinsieme archiviato',
         LABELS[row['codex_review']['verdict']], LABELS[(row['provider_review'] or {}).get('verdict', 'UNASSESSABLE')]]
        for row in report['cases']]) + '</section>'
    for row in sorted(report['cases'], key=lambda row: row['codex_review']['verdict'] == 'ACCEPTABLE'):
        title = NAMES.get(row['name'], row['name'].replace('BRAF_', 'BRAF · PMID '))
        review = row['codex_review']
        if review['findings']:
            html += '<section><h2>' + escape(title) + '</h2>'
        else:
            html += '<details><summary>' + escape(title) + ' · accettabile</summary>'
        html += p(review['summary'])
        for finding in review['findings']:
            html += finding_html(finding)
        html += '<details><summary>Seconda lettura: giudizio e rilievi</summary>'
        second = row['provider_review']
        if second:
            html += p(second['summary'])
            for finding in second['findings']:
                html += finding_html(finding, provider=True)
        else:
            html += p('Il giudizio automatico ha riferimenti inutilizzabili e rimane distinto da un’accettazione.')
        html += '</details>'
        html += '</section>' if review['findings'] else '</details>'
    html += '<section><h2>Quanto è affidabile il valutatore automatico?</h2>'
    model_description = ('Il valutatore utilizza lo stesso modello configurato per il narratore, con un prompt diverso. '
                         if report['same_model_as_narrator'] else 'Il valutatore utilizza un modello diverso da quello del narratore. ')
    html += p(model_description +
              'La revisione Codex è anch’essa assistita da modello. Sono due letture con ruoli distinti, '
              'senza revisione umana o gold standard clinico.')
    html += p(f"Nella prova finale riconosce {summary['calibration_error_cases_detected']} errori intenzionali "
              f"su {summary['calibration_error_cases']} e accetta {summary['calibration_clean_controls_accepted']} "
              f"controlli fedeli su {summary['calibration_clean_controls']}. "
              f"Estratti e riferimenti sono verificabili per {summary['usable_judgements']} giudizi su {summary['total_judgements']}. "
              'Questi risultati '
              'descrivono un campione piccolo e costruito, utile per un controllo iniziale.')
    html += p('La seconda calibrazione riutilizza controlli già esaminati per correggere il valutatore. '
              'La capacità di generalizzare richiede un insieme separato di prove.')
    html += table(['Controllo sintetico', 'Esito atteso', 'Esito del valutatore'], [
        [row['name'], LABELS[row['expected_verdict']], LABELS.get(row['observed_verdict'], 'Giudizio assente')]
        for row in report['calibration']])
    html += '<details><summary>Primo tentativo e limiti emersi</summary>'
    html += p('Il primo tentativo ha mancato la raccomandazione terapeutica introdotta nel controllo sintetico. '
              'In ' + str(report['first_trial']['unusable_evidence_records_as_recorded']) + ' giudizi su venti '
              'i riferimenti alle prove erano inutilizzabili. Il secondo tentativo vincola i riferimenti '
              'ai campi reali e chiarisce il criterio sulle raccomandazioni. Entrambi i tentativi sono conservati; '
              'le spiegazioni del narratore sono rimaste le stesse. Il controllo sintetico sul falso accordo '
              'fra studi è stato corretto per assegnare identità documentali coerenti alle due fonti.') + '</details>'
    html += p('Stabilità fra esecuzioni, copertura delle altre famiglie di relazioni e completezza rispetto '
              'alla letteratura richiedono prove ulteriori. Il verificatore di produzione mantiene il proprio '
              'esito deterministico; questa valutazione aggiunge un audit con motivazioni verificabili.') + '</section>'
    html += '<section><h2>Dati e riproducibilità</h2><p><a href="verifica/narratore-audit-semantico.json" download>'
    html += 'Giudizi, estratti, confronti e provenienza · JSON</a></p></section></main>'
    base = (WEB / 'Audit_GCA_per_il_relatore.html').read_text(encoding='utf-8')
    page = re.sub(r'<main class="audit-main" id="main">.*?</main>', lambda _: html, base, flags=re.S)
    return re.sub(r'<title>.*?</title>', '<title>Fedeltà semantica del dossier</title>', page, count=1)


def main():
    audit = build_audit()
    serialized = json.dumps(audit, ensure_ascii=False, indent=2)
    (OUT / 'audit.json').write_text(serialized, encoding='utf-8')
    (WEB / 'verifica/narratore-audit-semantico.json').write_text(serialized, encoding='utf-8')
    (WEB / 'Audit_semantico_del_dossier.html').write_text(render_html(audit), encoding='utf-8')
    print(json.dumps(audit['summary'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
