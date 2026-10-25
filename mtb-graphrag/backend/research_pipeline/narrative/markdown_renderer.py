"""Human-readable projection of the canonical dossier.

This module is deliberately deterministic and has no model, retrieval, or
clinical decision logic.  It renders information already present in the
canonical dossier so a clinician can inspect the case without reading JSON.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..dossier.reading import build_reading_guide, source_url, VERIFICATION_NOTE


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _label(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("label") or value.get("normalized_value") or value.get("id"))
    return _text(value)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value is None else [value])


def _join(value: Any) -> str:
    parts = []
    for item in _list(value):
        label = _label(item) if isinstance(item, dict) else _text(item)
        if label:
            parts.append(label)
    return ", ".join(parts)


def _bullet(label: str, value: Any) -> str:
    rendered = _join(value) if isinstance(value, (list, tuple, dict)) else _text(value)
    return f"- **{label}:** {rendered or 'non disponibile'}"


_PUBLIC_SOURCE_ID_PATTERNS = (
    ("PMID", re.compile(r"^pmid:(\d+)$", re.IGNORECASE)),
    ("PMCID", re.compile(r"^pmcid:(PMC\d+)$", re.IGNORECASE)),
    ("NCT", re.compile(r"^nct:(NCT\d+)$", re.IGNORECASE)),
    ("DOI", re.compile(r"^doi:(10\.\d{4,9}/\S+)$", re.IGNORECASE)),
)


def _public_source_identity(record: dict[str, Any]) -> tuple[str, str] | None:
    """Return a validated public identifier; internal bundle IDs are never labels."""
    for key in ("public_source_identity", "declared_source_identity", "requested_document_id",
                "document_id", "paper_id"):
        value = _text(record.get(key))
        for kind, pattern in _PUBLIC_SOURCE_ID_PATTERNS:
            match = pattern.fullmatch(value)
            if match:
                return kind, f"{kind}:{match.group(1)}"
    return None


def _evidence_status(record: dict[str, Any]) -> str:
    support = record.get("candidate_support") or {}
    verification = record.get("document_verification") or {}
    return _text(support.get("result") or record.get("support_result") or record.get("support_level")
                 or verification.get("support_result")) or "UNVERIFIABLE"


def _detail_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            rendered = _detail_text(item)
            if rendered:
                parts.append(f"{key}: {rendered}")
        return "; ".join(parts)
    if isinstance(value, list):
        return "; ".join(filter(None, (_detail_text(item) for item in value)))
    return _text(value)


def _technical_details(title: str, value: Any) -> list[str]:
    return [f'<details><summary>{title}</summary>', '', '```json',
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), '```', '', '</details>', '']


def _render_documentary_finding(finding: dict[str, Any], reading: dict[str, Any] | None = None) -> list[str]:
    source, observed, checks = (finding.get(key) or {} for key in ('source', 'observed', 'checks'))
    retained = finding.get('disposition') == 'RETAINED_RECORD'
    identity = source.get('public_source_identity') or source.get('document_id') or source.get('paper_id')
    url = source_url(identity)
    lines = ['#### Osservazione conservata' if retained else '#### Osservazione esclusa',
             _bullet('Fonte', f'[{identity}]({url})' if url else identity),
             _bullet('Source Unit', source.get('source_unit_id'))]
    if reading:
        lines.extend([_bullet('Patologia richiesta', reading.get('requested_disease')),
                      _bullet('Patologia estratta dalla fonte', reading.get('observed_disease')),
                      _bullet('Intervento richiesto', reading.get('requested_intervention')),
                      _bullet('Intervento estratto dalla fonte', reading.get('observed_intervention'))])
        lines.extend(f'- **Da verificare:** {notice["message"]}' for notice in reading['notices'])
    if retained and (checks.get('quotation') or {}).get('status') == 'AUTHENTICATED' and finding.get('quotation'):
        # Preserve the exact quote, including multiline passages, as a blockquote.
        lines.extend(['', *('> ' + line for line in finding['quotation'].splitlines()), ''])
    else:
        lines.append('Nessuna citazione ammessa alla sintesi. Non dimostra assenza di effetto.')
    for key, label in (('intervention', 'Intervento osservato'), ('disease', 'Popolazione o malattia osservata'),
                       ('effect_direction', 'Classificazione generale del risultato'), ('molecular_composition', 'Composizione molecolare'),
                       ('intervention_composition', 'Composizione dell’intervento'), ('uncertainty', 'Incertezza'),
                       ('caveats', 'Limitazioni riportate')):
        if observed.get(key):
            lines.append(_bullet(label, observed[key]))
    lines.extend([_bullet('Autenticazione della citazione', (checks.get('quotation') or {}).get('status')),
                  _bullet('Controllo strutturale', (checks.get('structural') or {}).get('status')),
                  _bullet('Verifica semantica', (checks.get('semantic') or {}).get('status')),
                  'Applicabilità al paziente non valutata.', ''])
    lines.extend(_technical_details('Schema originale e tracciabilità', {
        key: value for key, value in finding.items() if key != 'legacy_classification'}))
    return lines


def _render_evidence_details(entry: dict[str, Any]) -> list[str]:
    accepted_records = entry.get("accepted_evidence_records")
    records = accepted_records if isinstance(accepted_records, list) else []
    legacy_unreconciled = bool(entry.get("evidence_records")) and not records
    unique: dict[str, dict[str, Any]] = {}
    conflicts: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        identity = _text(record.get("evidence_id")) or f"anonymous-{index}"
        if identity not in unique:
            unique[identity] = record
        elif unique[identity] != record:
            conflicts.append(identity)
            unique[f"{identity}#conflict-{len(conflicts)}"] = record
    by_status: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for identity, record in unique.items():
        by_status.setdefault(_evidence_status(record), []).append((identity, record))
    source_counts: dict[tuple[str, str], int] = {}
    for record in unique.values():
        document = _text(record.get("document_id") or record.get("paper_id"))
        source_unit = _text(record.get("source_unit_id") or record.get("quote_source_unit_id"))
        if document and source_unit:
            key = (document, source_unit)
            source_counts[key] = source_counts.get(key, 0) + 1
    order = ("FULL_SUPPORT", "PARTIAL_SUPPORT", "CONTRADICTORY", "NO_SUPPORT",
             "INSUFFICIENT_INFORMATION", "UNVERIFIABLE")
    lines = []
    if unique:
        lines.extend(["#### Dettaglio delle evidenze documentali", ""])
        for identity in sorted(set(conflicts)):
            lines.append(f"- **Anomalia di tracciabilità:** Evidence ID duplicato con contenuti discordanti ({identity}); non è conteggiato come conferma indipendente.")
        if conflicts:
            lines.append("")
        for status in (*order, *sorted(set(by_status) - set(order))):
            group = by_status.get(status) or []
            if not group:
                continue
            lines.extend([f"##### {status}", ""])
            for identity, record in group:
                display_identity = identity.split("#conflict-", 1)[0]
                document_id = record.get("document_id") or record.get("requested_document_id")
                source_unit = record.get("source_unit_id") or record.get("quote_source_unit_id")
                public_identity = _public_source_identity(record)
                public_label, public_value = public_identity if public_identity else ("Identità fonte", "non disponibile")
                lines.extend([
                    f"- **Evidence ID:** {display_identity}",
                    f"  **{public_label}:** {public_value}; **Documento:** {_text(document_id) or 'non disponibile'}; "
                    f"**SourceUnit:** {_text(source_unit) or 'non disponibile'}; **Stato:** {status}.",
                ])
                source_key = (_text(document_id or record.get("paper_id")), _text(source_unit))
                if source_key in source_counts and source_counts[source_key] > 1:
                    lines.append("  **Nota di conteggio:** stessa SourceUnit; non costituisce una conferma indipendente.")
                quote_valid = record.get("quote_valid") is True or record.get("presentation_state") == "VALIDATED_QUOTE"
                quote = _text(record.get("quote") or record.get("author_claim_quote")) if quote_valid else ""
                if quote:
                    lines.append(f"  **Citazione validata:** “{quote}”")
                verification = record.get("document_verification") or {}
                verification_status = _text(
                    record.get("verification_status") or verification.get("verification_status"))
                final_admission = _text(
                    record.get("final_admission") or verification.get("final_admission"))
                verification_reasons = (record.get("verification_reason_codes")
                                        or record.get("reason_codes")
                                        or verification.get("admission_reason_codes") or [])
                if verification_status or final_admission or verification_reasons:
                    details = list(dict.fromkeys(
                        value for value in (verification_status, final_admission) if value))
                    if verification_reasons:
                        details.append("motivi: " + _join(verification_reasons))
                    lines.append(f"  **Verifica:** {'; '.join(details)}")
                limitation = verification.get("support_limitation") or record.get("support_limitation")
                if limitation:
                    lines.append(f"  **Limitazione:** {_detail_text(limitation)}")
                for key, label in (("study_context", "Contesto dello studio"),
                                   ("applicability_to_case", "Applicabilità al caso")):
                    value = verification.get(key) or record.get(key)
                    if value:
                        lines.append(f"  **{label}:** {_detail_text(value)}")
                provenance = record.get("provenance") or record.get("document_provenance")
                if provenance:
                    lines.append(f"  **Provenienza:** {_detail_text(provenance)}")
            lines.append("")
    rejected = entry.get("rejected_evidence") or []
    if rejected:
        lines.extend(["#### Evidenze escluse dalla sintesi", ""])
        seen = set()
        for record in rejected:
            if not isinstance(record, dict):
                continue
            identity = _text(record.get("evidence_id"))
            if identity and identity in seen:
                continue
            if identity:
                seen.add(identity)
            support_state = _evidence_status(record)
            public_identity = _public_source_identity(record)
            public_label, public_value = public_identity if public_identity else ("Identità fonte", "non disponibile")
            document_id = _text(record.get("document_id") or record.get("requested_document_id")) or "non disponibile"
            source_unit = _text(record.get("source_unit_id")) or "non disponibile"
            lines.append(
                f"- **Evidence ID:** {identity or 'non disponibile'}; **esito di dossier:** NON AMMESSA; "
                f"**stato registrato (non ammesso):** {support_state}; **{public_label}:** {public_value}; "
                f"**Documento:** {document_id}; "
                f"**SourceUnit:** {source_unit}; **motivo:** "
                f"{_text(record.get('rejection_reason') or record.get('reason')) or 'non specificato'}."
            )
    if legacy_unreconciled:
        lines.extend(["", "#### Record storici non riconciliati (non ammessi)", "",
                      "Schema precedente: i record grezzi non sono trattati come evidenze ammesse; "
                      "servono solo a mantenere la tracciabilità storica.", ""])
        rejected_ids = {_text(item.get("evidence_id")) for item in rejected if isinstance(item, dict)}
        for index, record in enumerate(entry.get("evidence_records") or []):
            if not isinstance(record, dict):
                continue
            identity = _text(record.get("evidence_id")) or f"anonymous-{index}"
            if identity in rejected_ids:
                continue
            document_id = _text(record.get("document_id") or record.get("requested_document_id"))
            document = document_id or _text(record.get("paper_id")) or "non disponibile"
            source_unit = _text(record.get("source_unit_id") or record.get("quote_source_unit_id")) or "non disponibile"
            public_identity = _public_source_identity(record)
            public_label, public_value = public_identity if public_identity else ("Identità fonte", "non disponibile")
            lines.append(
                f"- **Evidence ID:** {identity}; **esito di dossier:** NON RICONCILIATO / NON AMMESSO; "
                f"**{public_label}:** {public_value}; **Documento:** {document}; **SourceUnit:** {source_unit}; "
                f"**stato registrato:** {_evidence_status(record)}."
            )
    return lines


def render_dossier_markdown(
    dossier: dict[str, Any] | None,
    narrative: dict[str, Any] | None = None,
    presentation_mode: str | None = None,
    verification: dict[str, Any] | None = None,
) -> str:
    """Render the dossier as a clinician-oriented Markdown document."""
    from ..dossier.accounting import apply_publication_integrity

    dossier = apply_publication_integrity(dossier or {})
    reading_guide = build_reading_guide(dossier)
    if not ((verification or {}).get("status") == "PASS" and narrative
            and presentation_mode in {"VERIFIED_NARRATIVE", "DETERMINISTIC_NARRATIVE_FALLBACK"}):
        narrative = None
        presentation_mode = "STRUCTURED_DOSSIER_FALLBACK"
    context = dossier.get("case_summary") or {}
    lines = ["# Dossier clinico-documentale", "", VERIFICATION_NOTE, ""]
    if dossier.get("documentary_projection_migration"):
        lines.extend(["> Proiezione pubblica aggiornata per correggere la serializzazione. "
                      "Osservazioni e ledger originali invariati; non costituisce una nuova verifica scientifica.", ""])
    integrity = dossier.get("publication_integrity") or {}
    if dossier.get("publication_status") == "INCOMPLETE":
        lines.extend([
            ("## Dossier incompleto: esecuzione parziale" if integrity.get("reconciliation_status") == "PASS"
             else "## Dossier incompleto: riconciliazione non confermata"), "",
            "La pubblicazione del dossier è incompleta. I record e la diagnostica restano disponibili.",
            _bullet("Stato tecnico della run", dossier.get("technical_run_status")),
            _bullet("Stato riconciliazione", integrity.get("reconciliation_status")),
            _bullet("Reason codes", integrity.get("reason_codes")),
            "```json", json.dumps(integrity.get("diagnostic"), ensure_ascii=False, sort_keys=True, indent=2),
            "```", "",
        ])
    lines.extend([
        "## Caso", "",
        _bullet("Case ID", context.get("case_id") or dossier.get("case_id")),
        _bullet("Malattia", context.get("disease")),
        _bullet("Biomarcatori", context.get("biomarkers") or context.get("gene")),
        _bullet("Alterazione", context.get("variant") or context.get("alteration")),
        _bullet("Intervento", context.get("intervention")),
        "",
    ])
    for item in context.get('molecular_resolution') or []:
        lines.append(_bullet('Partner di fusione dichiarati', item.get('fusion_partners')))
        lines.append('Profilo di fusione risolto nel registro.' if item.get('fusion_status') == 'RESOLVED'
                     else 'Profilo di fusione non risolto nel registro disponibile; partner conservati senza attribuire un’identità.')
    retrieval = dossier.get("retrieval_summary") or {}
    if retrieval:
        lines.extend([
            "## Recupero delle evidenze", "",
            _bullet("Candidate totali", retrieval.get("total_candidates")),
            _bullet("Candidate selezionate", retrieval.get("selected_total")),
            _bullet("Paper", retrieval.get("paper_candidates")),
            _bullet("Associazioni candidate a trial", retrieval.get("trial_candidates")),
            _bullet("KG_ONLY", retrieval.get("kg_only_candidates")),
            "",
        ])

    paper_entries = [e for e in dossier.get("paper_evidence") or [] if isinstance(e, dict)]
    lines.extend(["## Evidenza dai paper", ""])
    if not paper_entries:
        lines.append("Nessuna evidenza documentale da paper disponibile.")
    for index, entry in enumerate(paper_entries, 1):
        if dossier.get("documentary_contract_version"):
            lines.extend([f"### Relazione documentale {index}",
                          _bullet("Candidate", entry.get("candidate_id")),
                          _bullet('Target del grafo', (entry.get('documentary_target') or {}).get('subject')),
                          'Il target del grafo non è una conclusione della fonte.', ''])
            for finding_index, finding in enumerate(entry.get("documentary_findings") or []):
                reading = next((item for item in reading_guide['findings']
                                if item['paper_index'] == index - 1 and item['finding_index'] == finding_index), None)
                lines.extend(_render_documentary_finding(finding, reading))
            if not entry.get("documentary_findings"):
                lines.append("Nessuna osservazione documentale conservata. Non implica assenza biologica di effetto.")
            lines.extend(_technical_details('Target della ricerca e tentativi Reader', {
                'target': entry.get('documentary_target') or {}, 'attempts': entry.get('documentary_attempts') or []}))
            lines.extend(_technical_details('Compatibilita tecnica storica (non giudizio scientifico)', entry.get('legacy_aggregate') or {}))
            continue
        lines.extend([
            f"### Paper {index}",
            _bullet("Candidate", entry.get("candidate_id")),
            _bullet("Relazione", entry.get("relation")),
            _bullet("Stato", entry.get("support_level") or entry.get("support_status")),
            _bullet("Composizione evidenze", json.dumps(
                entry.get("evidence_composition") or {}, ensure_ascii=False, sort_keys=True)),
            _bullet("Documento", entry.get("representative_document_id")
                    or entry.get("document_id") or entry.get("requested_document_id")),
            _bullet("PMCID", entry.get("pmcid")),
            _bullet("SourceUnit", entry.get("quote_source_unit_id")),
        ])
        distinct_source_count = entry.get("distinct_source_unit_count")
        if distinct_source_count is not None:
            lines.append(_bullet("SourceUnit distinte tra le evidenze ammesse", distinct_source_count))
        has_recorded_evidence = bool(entry.get("accepted_evidence_records") or entry.get("evidence_records"))
        quote = _text(entry.get("quote")) if entry.get("quote_valid") and not has_recorded_evidence else ""
        if quote:
            lines.append(f'- **Quote validata:** “{quote}”')
        elif has_recorded_evidence:
            lines.append("- **Quote validata:** consultare il dettaglio per-evidenza")
        else:
            lines.append("- **Quote validata:** non disponibile")
        fields = entry.get("support_fields") or {}
        if fields:
            lines.append(_bullet("Supporto per campo", "; ".join(f"{k}={v}" for k, v in fields.items())))
        if entry.get("support_reason"):
            lines.append(_bullet("Motivazione", entry["support_reason"]))
        lines.extend(_render_evidence_details(entry))
        lines.append("")

    trial_entries = [e for e in dossier.get("clinical_trials") or [] if isinstance(e, dict)]
    lines.extend(["## Trial clinici", ""])
    if not trial_entries:
        lines.append("Nessun trial clinico associato disponibile.")
    lines.extend([
        _bullet('Studi identificati distinti', reading_guide['identified_study_count']),
        _bullet('Associazioni a trial', reading_guide['trial_association_count']),
        _bullet('Associazioni senza NCT verificabile', reading_guide['unidentified_trial_association_count']),
        'Le associazioni allo stesso NCT non sono studi indipendenti. Eleggibilità del paziente non valutata.', '',
    ])
    for index, group in enumerate(reading_guide['trial_groups'], 1):
        entries = [trial_entries[i] for i in group['entry_indexes']]
        nct = group['nct_id']
        lines.extend([f"### Studio {index}" if nct else f"### Associazione senza NCT {index}",
                      _bullet('NCT', nct),
                      _bullet('Fonte del registro', f'[{nct}]({source_url(nct)})' if nct else None),
                      _bullet('Associazioni nel grafo', len(entries)), ''])
        if group['conflicting_snapshots']:
            lines.extend(['**Dati di registro discordanti:** snapshot riportati separatamente, senza fondere i bracci.', ''])
        for snapshot_number, entry_index in enumerate(group['snapshot_indexes'], 1):
            entry = trial_entries[entry_index]
            if group['conflicting_snapshots']:
                lines.extend([f'#### Dati registrati {snapshot_number}', ''])
            lines.extend([_bullet('Titolo', entry.get('title')),
                          _bullet('Fase', entry.get('phase')),
                          _bullet('Stato', entry.get('status') or entry.get('recruitment_status')),
                          _bullet('Risoluzione', entry.get('trial_resolution_status')), ''])
            arms = entry.get('arm_groups') or []
            lines.extend(['<details><summary>Condizioni e interventi dello studio complessivo</summary>', '',
                          _bullet('Condizioni', entry.get('conditions')),
                          _bullet('Interventi', [item.get('name') if isinstance(item, dict) else item
                                                 for item in _list(entry.get('interventions'))]),
                          '', 'L’elenco globale non attribuisce trattamenti a una specifica popolazione.', '</details>', ''])
            if arms:
                lines.extend([f'<details><summary>Bracci registrati ({len(arms)})</summary>', ''])
                for arm in arms:
                    lines.extend([_bullet('Braccio', arm.get('label')),
                                  _bullet('Popolazione o descrizione del braccio', arm.get('description')),
                                  _bullet('Interventi di questo braccio', arm.get('interventionNames')), ''])
                lines.extend(['</details>', ''])
            else:
                lines.extend(['Bracci e associazione fra popolazioni e interventi non disponibili; gli interventi elencati appartengono allo studio complessivo.', ''])
        lines.extend(['Associazione a trial: non costituisce prova di efficacia terapeutica né verifica dell’eleggibilità. Lo stato registrato non garantisce disponibilità locale.', ''])
        for entry in entries:
            document_ids = entry.get('document_ids') or [entry.get('document_id') or entry.get('resolved_document_id')]
            source_units = _list(entry.get('source_unit_ids') or entry.get('selected_source_unit_ids'))
            references = []
            if any(document_ids):
                references.append('Documento: ' + _join(document_ids))
            if any(source_units):
                references.append('SourceUnit: ' + _join(source_units))
            if references:
                lines.append(_bullet('Provenienza ' + _text(entry.get('candidate_id')), '; '.join(references)))
        lines.append('')
        lines.extend(_technical_details('Associazioni originali e provenienza', [
            {key: value for key, value in entry.items() if key not in (
                'arm_groups', 'conditions', 'interventions', 'trial_structure_provenance')}
            for entry in entries]))
        # Large snapshots occur once per distinct version, not once per graph association.
        lines.extend(_technical_details('Snapshot e provenienza del registro', [
            trial_entries[i] for i in group['snapshot_indexes']]))

    kg_entries = [e for e in dossier.get("kg_only_relations") or [] if isinstance(e, dict)]
    lines.extend(["## Relazioni Knowledge Graph", ""])
    if not kg_entries:
        lines.append("Nessuna relazione KG_ONLY disponibile.")
    for index, entry in enumerate(kg_entries, 1):
        provenance = entry.get("graph_provenance") or {}
        lines.extend([
            f"### Relazione KG {index}",
            _bullet("Candidate", entry.get("candidate_id")),
            _bullet("Soggetto", entry.get("subject")),
            _bullet("Relazione", entry.get("relation")),
            _bullet("Oggetto", entry.get("object")),
            _bullet("Malattia/contesto", entry.get("disease_context")),
            _bullet("Database sorgente", entry.get("source_database")),
            _bullet("Verifica", entry.get("verification_status") or "KG_ONLY"),
            _bullet("Provenienza documentale", entry.get("document_provenance") or "NOT_AVAILABLE"),
            _bullet("Graph path", provenance.get("graph_path")),
            _bullet("Graph edge", provenance.get("edge_ids")),
            "",
        ])

    limitations = dossier.get("limitations") or []
    lines.extend(["## Limitazioni", ""])
    lines.extend(f"- {item}" for item in limitations if item)
    if not limitations:
        lines.append("Nessuna limitazione registrata.")
    lines.append("")

    if narrative:
        title = "## Sintesi dal dossier" if presentation_mode == "DETERMINISTIC_NARRATIVE_FALLBACK" else "## Sintesi narrativa: fedeltà al dossier verificata"
        lines.extend([title, "", _text(narrative.get("narrative_summary")), ""])
        lines.extend([VERIFICATION_NOTE, "", "<details><summary>Narrativa registrata per relazione</summary>", ""])
        for entry in narrative.get("candidate_narratives") or []:
            if isinstance(entry, dict):
                lines.extend([f"### {entry.get('candidate_id', 'Candidate')}", _text(entry.get("text")), ""])
        lines.extend(["</details>", ""])
        if narrative.get("limitations_summary"):
            lines.extend(["### Limitazioni narrative", _text(narrative["limitations_summary"]), ""])
        if narrative.get("closing_note"):
            lines.extend([_text(narrative["closing_note"]), ""])
    else:
        lines.extend(["## Presentazione", "", "La narrativa non è disponibile; viene mostrato il dossier strutturato.", ""])

    if presentation_mode:
        lines.extend([f"**Modalità di presentazione:** `{presentation_mode}`", ""])
    if verification and verification.get("status"):
        lines.extend([f"**Verifica di fedeltà narrativa al dossier:** `{verification['status']}`", ""])
    lines.append("_Questa scheda è informativa e non costituisce una raccomandazione terapeutica._")
    return "\n".join(lines)
