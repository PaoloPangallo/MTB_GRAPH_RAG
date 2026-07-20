"""Esecuzione comparativa delle due architetture proposte nella tesi.

La modalità ``demo`` non richiede Neo4j o un endpoint LLM ed espone un caso
sintetico dichiarato. La modalità ``live`` usa i componenti reali del backend:
planner dinamico, strumenti tipizzati, ledger persistente, vista canonica,
rendering deterministico e verifica claim--fonte su due assi indipendenti
(supporto documentale e applicabilità al caso).
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from backend.api.schemas import (
    ArchitectureComparisonRequest,
    ArchitectureComparisonResponse,
    ArchitectureMetrics,
    ArchitectureRun,
    ClaimCheck,
    ClinicalDossier,
    ComparisonSummary,
    DossierCaseField,
    DossierEvidence,
    DossierFinding,
    EvidenceItem,
    TraceStep,
)


DISCLAIMER = (
    "Dimostratore di ricerca per preparazione e revisione dell'evidenza. "
    "Non produce raccomandazioni terapeutiche e non sostituisce il Molecular Tumor Board."
)

# Titoli delle 5 sezioni cliniche del dossier, derivati dal campo
# ``dossier_section`` di ogni ``DossierEvidence``. Usati sia per il report
# testuale sia — con la stessa chiave — dal frontend per il rendering.
SECTION_TITLES: dict[str, str] = {
    "supported_compatible": "Evidenze supportate e compatibili con il contesto dichiarato",
    "supported_indeterminate": "Evidenze supportate con applicabilità indeterminata",
    "supported_not_compatible": "Evidenze supportate ma non compatibili con il contesto dichiarato",
    "review": "Evidenze con supporto documentale incerto",
    "excluded": "Claim non supportate dalla fonte",
}

_APPLICABILITY_LABELS = {
    "compatible": "compatibile con il contesto dichiarato",
    "indeterminate": "indeterminata",
    "not_compatible": "non compatibile con il contesto dichiarato",
}


def _case_label(req: ArchitectureComparisonRequest) -> str:
    gene = req.gene or "biomarker"
    return f"{gene} {req.variant} · {req.tumor_type} · {req.therapy_line}"


def _sources(items: list[EvidenceItem]) -> set[str]:
    return {item.source_id for item in items if item.source_id}


def _summary(deterministic: ArchitectureRun, agentic: ArchitectureRun) -> ComparisonSummary:
    fixed = _sources(deterministic.evidence)
    planned = _sources(agentic.evidence)
    return ComparisonSummary(
        shared_sources=sorted(fixed & planned),
        deterministic_only_sources=sorted(fixed - planned),
        agentic_only_sources=sorted(planned - fixed),
        explanation=(
            "Le due architetture possono recuperare le stesse fonti: la differenza principale "
            "riguarda chi decide il percorso e quali controlli separano raccolta, rendering e "
            "verifica. Fonti condivise non significano architetture equivalenti e non provano "
            "da sole la correttezza clinica."
        ),
    )


def _claim_text(item: EvidenceItem) -> str:
    return f"{item.subject} — {item.relation} — {item.object} ({item.context})."


def _canonical_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """Deduplica senza perdere la provenienza necessaria alla verifica."""
    canonical: list[EvidenceItem] = []
    seen: set[tuple[str, str, str, str, str | None]] = set()
    for item in items:
        key = (
            item.subject,
            item.relation,
            item.object,
            item.context,
            item.source_id,
        )
        if key not in seen:
            seen.add(key)
            canonical.append(item)
    return canonical


def _render_candidate_report(case_label: str, items: list[EvidenceItem]) -> str:
    """Prima proiezione deterministica, ancora soggetta al claim verifier."""
    if not items:
        return f"Caso: {case_label}.\nNessuna evidenza candidata disponibile."
    lines = [f"Caso: {case_label}.", "Evidenze candidate:"]
    for item in items:
        source = f" [{item.source_id}]" if item.source_id else " [fonte assente]"
        lines.append(f"- {_claim_text(item)}{source}")
    return "\n".join(lines)


def _render_verified_report(
    case_label: str,
    items: list[EvidenceItem],
    verifications: list[Any],
) -> str:
    """Rendering finale: emette le claim con supporto documentale, mostrando
    sempre entrambi gli assi (supporto e applicabilità) e i prerequisiti
    della fonte quando noti — senza mai generalizzare una fonte oltre il
    proprio campo né usare formulazioni di raccomandazione per record con
    applicabilità non compatibile."""
    supported = [
        (item, verification)
        for item, verification in zip(items, verifications)
        if verification.source_support_status == "supported"
    ]
    if not supported:
        return (
            f"Caso: {case_label}.\n"
            "Nessuna evidenza con provenienza sufficiente per generare claim fattuali. "
            "È richiesta la revisione dell'oncologo."
        )

    lines = [f"Caso: {case_label}.", "Evidenze documentalmente supportate:"]
    for item, verification in supported:
        prerequisites = ", ".join(
            part for part in (
                verification.source_population,
                verification.source_line,
                verification.source_setting,
                verification.source_prerequisites,
            ) if part
        )
        header = f"- {_claim_text(item)} [{item.source_id}]"
        if prerequisites:
            header += f" — contesto della fonte: {prerequisites}."
        lines.append(header)
        lines.append(f"  Supporto documentale: {verification.source_support_reason}")
        lines.append(
            "  Applicabilità al contesto richiesto: "
            f"{_APPLICABILITY_LABELS.get(verification.applicability_status, verification.applicability_status)} "
            f"— {verification.applicability_reason}"
        )

    if any(v.applicability_status == "compatible" for _item, v in supported):
        lines.append(
            "Solo le evidenze compatibili con il contesto dichiarato sono da considerare come "
            "possibili opzioni per il caso; restano comunque soggette a revisione del "
            "Molecular Tumor Board."
        )
    if any(v.applicability_status != "compatible" for _item, v in supported):
        lines.append(
            "Le evidenze supportate ma non compatibili o con applicabilità indeterminata restano "
            "visibili come contesto documentale: non sono opzioni per il caso e non vanno lette "
            "come fonti false."
        )
    lines.append(
        "Il report organizza l'evidenza disponibile e deve essere revisionato "
        "dal Molecular Tumor Board; non costituisce una raccomandazione terapeutica."
    )
    return "\n".join(lines)


def _support_from_check_status(status: str) -> str:
    return {
        "supported": "supported",
        "blocked": "unsupported",
        "insufficient": "uncertain",
        "not_checked": "uncertain",
    }.get(status, "uncertain")


def _dossier_bucket(source_support_status: str, applicability_status: str) -> str:
    """Funzione pura di bucketing: deriva la sezione clinica del dossier dai
    due assi indipendenti. Nessuna evidenza compare in più di una sezione."""
    if source_support_status == "unsupported":
        return "excluded"
    if source_support_status == "uncertain":
        return "review"
    if applicability_status == "not_compatible":
        return "supported_not_compatible"
    if applicability_status == "indeterminate":
        return "supported_indeterminate"
    return "supported_compatible"


def _checks_from_verifications(
    items: list[EvidenceItem],
    verifications: list,
) -> list[ClaimCheck]:
    if not items:
        return [ClaimCheck(
            claim="Nessuna claim fattuale emessa.",
            status="insufficient",
            reason="La vista canonica non contiene record utilizzabili.",
            verification_level="canonical_view",
            requires_human_review=True,
        )]
    checks: list[ClaimCheck] = []
    for item, verification in zip(items, verifications):
        status = {
            "supported": "supported",
            "unsupported": "blocked",
            "uncertain": "insufficient",
        }.get(verification.source_support_status, "insufficient")
        checks.append(ClaimCheck(
            claim=_claim_text(item),
            status=status,
            reason=verification.source_support_reason,
            source_id=item.source_id,
            verification_level=verification.verification_level,
            requires_human_review=verification.requires_source_review,
        ))
    return checks


def _text_value(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "Presenti" if value else "Assenti"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else None
    return str(value)


def _case_summary(req: ArchitectureComparisonRequest) -> list[DossierCaseField]:
    fields = [
        ("molecular_profile", "Profilo molecolare", f"{req.gene or 'Biomarker'} {req.variant}"),
        ("tumor_type", "Tumore", req.tumor_type),
        ("therapy_line", "Linea richiesta", req.therapy_line),
        ("disease_stage", "Stadio", req.disease_stage),
        ("disease_setting", "Setting", req.disease_setting),
        ("prior_therapies", "Trattamenti precedenti", req.prior_therapies),
        ("prior_response", "Risposta precedente", req.prior_response),
        ("ecog_status", "ECOG performance status", req.ecog_status),
        ("cns_metastases", "Metastasi SNC", req.cns_metastases),
        ("co_alterations", "Co-alterazioni", req.co_alterations),
        ("jurisdiction", "Contesto regolatorio", req.jurisdiction),
        ("mtb_goal", "Obiettivo MTB", req.mtb_goal),
    ]
    return [
        DossierCaseField(
            key=key,
            label=label,
            value=_text_value(value),
            confirmed=_text_value(value) is not None,
        )
        for key, label, value in fields
    ]


def _dossier_finding(record: dict, kind: str) -> DossierFinding:
    if kind == "trial":
        nct_id = record.get("nct_id") or "Trial senza identificatore"
        title = f"{nct_id}: {record.get('title', 'titolo non disponibile')}"
        details = [record.get("phase"), record.get("status"), record.get("drug_tested")]
        return DossierFinding(
            title=title,
            detail=" · ".join(str(value) for value in details if value) or "Dettagli non disponibili.",
        )
    pmid = record.get("pmid")
    details = [record.get("disease"), record.get("evidence_level"), record.get("statement")]
    return DossierFinding(
        title=str(record.get("variant") or "Meccanismo di resistenza"),
        detail=" · ".join(str(value) for value in details if value) or "Dettagli non disponibili.",
        source_id=f"PMID:{pmid}" if pmid else None,
    )


def _build_dossier(
    req: ArchitectureComparisonRequest,
    items: list[EvidenceItem],
    checks: list[ClaimCheck],
    *,
    verifications: list[Any] | None = None,
    state: dict | None = None,
) -> ClinicalDossier:
    """Costruisce la vista canonica unica delle evidenze (``ClinicalDossier.evidence``).

    Quando ``verifications`` è disponibile (percorso live agentico, allineato
    1:1 posizionalmente con ``items``), ogni evidenza riceve i due assi reali
    prodotti dal verificatore. Quando non lo è (demo, traversal
    deterministico — architetture che non eseguono mai un verificatore
    fonte-per-fonte), l'applicabilità resta onestamente "indeterminate": non
    viene mai fabbricato un "compatible" di default.
    """
    summary = _case_summary(req)
    missing = [field.label for field in summary if not field.confirmed]
    evidence: list[DossierEvidence] = []
    matched_checks: set[int] = set()

    for position, item in enumerate(items):
        check = None
        if position < len(checks) and (
            len(checks) == len(items)
            or checks[position].source_id == item.source_id
        ):
            check = checks[position]
            matched_checks.add(position)
        verification = (
            verifications[position]
            if verifications is not None and position < len(verifications)
            else None
        )

        if verification is not None:
            support_status = verification.source_support_status
            support_reason = verification.source_support_reason
            applicability_status = verification.applicability_status
            applicability_reason = verification.applicability_reason
            requires_source_review = verification.requires_source_review
            requires_clinical_review = verification.requires_clinical_review
            population = verification.source_population
            source_line = verification.source_line
            source_setting = verification.source_setting
            prerequisites = verification.source_prerequisites
            derived_verified_claim = verification.derived_verified_claim
        elif check is not None:
            support_status = _support_from_check_status(check.status)
            support_reason = check.reason
            applicability_status = "indeterminate"
            applicability_reason = (
                "Applicabilità non valutata: questa architettura non esegue un "
                "verificatore fonte-per-fonte separato dal supporto documentale."
            )
            requires_source_review = support_status != "supported"
            requires_clinical_review = True
            population = source_line = source_setting = prerequisites = None
            derived_verified_claim = None
        else:
            support_status = "uncertain"
            support_reason = "Record recuperato, ma non sottoposto a verifica claim-by-claim."
            applicability_status = "indeterminate"
            applicability_reason = "Applicabilità non valutata: nessuna verifica eseguita su questo record."
            requires_source_review = True
            requires_clinical_review = True
            population = source_line = source_setting = prerequisites = None
            derived_verified_claim = None

        evidence.append(DossierEvidence(
            evidence_id=f"{item.source_id or 'unsourced'}-{position}",
            claim=_claim_text(item),
            therapy=item.object,
            setting=item.context,
            source_id=item.source_id,
            evidence_level=item.evidence_level,
            source_support_status=support_status,
            source_support_reason=support_reason,
            source_population=population,
            source_line=source_line,
            source_setting=source_setting,
            source_prerequisites=prerequisites,
            derived_verified_claim=derived_verified_claim,
            applicability_status=applicability_status,
            applicability_reason=applicability_reason,
            requires_source_review=requires_source_review,
            requires_clinical_review=requires_clinical_review,
            dossier_section=_dossier_bucket(support_status, applicability_status),
        ))

    for index, check in enumerate(checks):
        if index in matched_checks or check.status not in {"blocked", "insufficient"}:
            continue
        support_status = _support_from_check_status(check.status)
        evidence.append(DossierEvidence(
            evidence_id=f"synthetic-{index}",
            claim=check.claim,
            therapy="Non determinata",
            setting=req.tumor_type,
            source_id=check.source_id,
            evidence_level=None,
            source_support_status=support_status,
            source_support_reason=check.reason,
            applicability_status="indeterminate",
            applicability_reason="Applicabilità non valutata: claim priva di un record di evidenza associato.",
            requires_source_review=support_status != "supported",
            requires_clinical_review=True,
            dossier_section=_dossier_bucket(support_status, "indeterminate"),
        ))

    state = state or {}
    resistance = [
        _dossier_finding(record, "resistance")
        for record in state.get("resistance_data", [])
    ]
    trials = [
        _dossier_finding(record, "trial")
        for record in state.get("trial_candidates", [])
    ]

    by_section: dict[str, list[DossierEvidence]] = {}
    for entry in evidence:
        by_section.setdefault(entry.dossier_section, []).append(entry)
    has_supported = bool(
        by_section.get("supported_compatible")
        or by_section.get("supported_indeterminate")
        or by_section.get("supported_not_compatible")
    )

    questions = []
    if missing:
        questions.append("Completare i dati clinici mancanti: " + ", ".join(missing) + ".")
    if by_section.get("review") or by_section.get("supported_indeterminate"):
        questions.append(
            "Revisionare le evidenze con supporto documentale incerto o con "
            "applicabilità individuale indeterminata."
        )
    if by_section.get("excluded"):
        questions.append("Revisionare le evidenze escluse e la relativa motivazione.")
    if by_section.get("supported_not_compatible"):
        questions.append(
            "Valutare se le evidenze supportate ma non compatibili con il contesto "
            "dichiarato siano comunque rilevanti per il MTB, senza considerarle opzioni per il caso."
        )
    if by_section.get("supported_compatible"):
        questions.append(
            "Valutare nel MTB tossicità e stato regolatorio delle evidenze supportate e compatibili."
        )
    if not has_supported:
        questions.append("Stabilire se ampliare la ricerca: nessuna evidenza documentale è risultata supportata.")

    return ClinicalDossier(
        case_summary=summary,
        missing_data=missing,
        evidence=evidence,
        resistance_findings=resistance,
        trial_findings=trials,
        mtb_questions=questions,
    )


def _demo_evidence(req: ArchitectureComparisonRequest) -> list[EvidenceItem]:
    is_egfr_example = (
        (req.gene or "").upper() == "EGFR"
        and req.variant.upper().replace("P.", "") == "L858R"
        and any(token in req.tumor_type.lower() for token in ("lung", "nsclc"))
    )
    if not is_egfr_example:
        return []
    return [
        EvidenceItem(
            subject="EGFR p.L858R",
            relation="sensitivity association",
            object="osimertinib",
            context="NSCLC / lung adenocarcinoma",
            source_id="PMID:29151359",
            provenance="Fixture dimostrativa derivata da una fonte pubblica; verificare il record originale.",
        )
    ]


def _demo_deterministic(req: ArchitectureComparisonRequest) -> ArchitectureRun:
    # Ambito demo invariato: la fixture EGFR/osimertinib e la fault injection
    # MET restano quelle esistenti — qui si adatta solo la forma del dossier
    # al nuovo contratto, senza usare questa fixture come prova clinica.
    evidence = _demo_evidence(req)
    has_evidence = bool(evidence)
    report = (
        "Il percorso tipizzato ha recuperato un'associazione tra EGFR p.L858R e "
        "osimertinib nel contesto NSCLC, collegata a PMID 29151359. Il reperto deve "
        "essere revisionato dall'oncologo."
        if has_evidence
        else "La fixture dimostrativa non contiene evidenze per questo caso."
    )
    checks = [
        ClaimCheck(
            claim="EGFR p.L858R è associata a osimertinib nel contesto NSCLC.",
            status="not_checked",
            reason="La fonte è stata recuperata, ma questa architettura non applica un verificatore claim-by-claim al testo finale.",
            source_id="PMID:29151359",
            requires_human_review=True,
        )
    ] if has_evidence else [
        ClaimCheck(
            claim="Nessuna claim fattuale emessa.",
            status="insufficient",
            reason="Il caso non appartiene alla fixture dimostrativa.",
        )
    ]
    trace = [
        TraceStep(order=1, stage="Normalizzazione", actor="Regole", detail="Gene, variante, tumore e intento sono canonizzati."),
        TraceStep(order=2, stage="Instradamento", actor="Router", detail="L'intento seleziona un template noto, non un piano libero."),
        TraceStep(order=3, stage="Template tipizzato", actor="Piano fisso", detail="Variant → Drug → Evidence → Publication."),
        TraceStep(order=4, stage="Traversal", actor="Knowledge graph", detail="Esecuzione della query tipizzata sullo snapshot."),
        TraceStep(order=5, stage="Contesto", actor="Adapter", detail=f"Costruiti {len(evidence)} record con provenienza."),
        TraceStep(order=6, stage="Sintesi vincolata", actor="LLM", detail="L'LLM verbalizza soltanto il contesto recuperato."),
        TraceStep(order=7, stage="Revisione", actor="Oncologo", detail="Controllo della fonte e pertinenza per il caso."),
    ]
    return ArchitectureRun(
        architecture_id="deterministic",
        title="Traversal deterministico",
        subtitle="Domanda focalizzata, template tipizzato, recupero ripetibile",
        llm_roles=["Lettore e sintetizzatore vincolato al contesto"],
        trace=trace,
        evidence=evidence,
        report=report,
        dossier=_build_dossier(req, evidence, checks),
        claim_checks=checks,
        metrics=ArchitectureMetrics(
            elapsed_ms=34,
            tool_calls=1,
            evidence_count=len(evidence),
            verified_claims=sum(c.status == "supported" for c in checks),
            blocked_claims=sum(c.status == "blocked" for c in checks),
            review_claims=sum(c.requires_human_review for c in checks),
            source_supported_count=sum(c.status == "supported" for c in checks),
            source_uncertain_count=sum(c.status in ("insufficient", "not_checked") for c in checks),
            source_unsupported_count=sum(c.status == "blocked" for c in checks),
            applicability_indeterminate_count=len(evidence),
        ),
        limitations=[
            "La modalità demo non interroga il database live.",
            "Il determinismo riguarda il retrieval; la formulazione LLM può variare.",
        ],
    )


def _demo_agentic(req: ArchitectureComparisonRequest) -> ArchitectureRun:
    evidence = _demo_evidence(req)
    has_evidence = bool(evidence)
    unsupported_claim = "Il caso presenta amplificazione di MET."
    report = (
        "Reperto: EGFR p.L858R. Evidenza supportata: associazione con osimertinib "
        "nel contesto NSCLC (PMID 29151359). Resistenze e trial: non determinabili "
        "dalla fixture; richiedono ulteriori strumenti o dati del paziente."
        if has_evidence
        else "Il ledger dimostrativo non contiene evidenze per questo caso; è richiesta revisione umana."
    )
    checks = [
        ClaimCheck(
            claim="EGFR p.L858R è associata a osimertinib nel contesto NSCLC.",
            status="supported" if has_evidence else "insufficient",
            reason="Claim ancorata al ledger." if has_evidence else "Nessun record canonico disponibile.",
            source_id="PMID:29151359" if has_evidence else None,
        ),
        ClaimCheck(
            claim=unsupported_claim,
            status="blocked",
            reason="L'amplificazione non compare nei dati del caso o nel ledger.",
        ),
    ]
    trace = [
        TraceStep(order=1, stage="Controller", actor="Regole di autonomia", detail="Richiesta composta: attivata raccolta multi-step."),
        TraceStep(order=2, stage="Pianificazione", actor="LLM agente", detail="Interpreta variante, farmaci, resistenze, trial e fonti."),
        TraceStep(order=3, stage="Strumenti", actor="LLM agente + KG", detail="Selezione iterativa degli strumenti tipizzati."),
        TraceStep(order=4, stage="Event log append-only", actor="Data plane", detail=f"Registrati {len(evidence)} eventi fattuali immutabili."),
        TraceStep(order=5, stage="Vista canonica", actor="Regole", detail="Deduplicazione e conservazione dei conflitti."),
        TraceStep(order=6, stage="Proiezione pertinente", actor="Regole", detail="Solo i record utili al caso entrano nel report."),
        TraceStep(order=7, stage="Rendering deterministico", actor="Renderer", detail="Il report candidato è costruito dai record ammessi."),
        TraceStep(order=8, stage="Verifica delle claim", actor="Claim verifier", detail="La claim non supportata su MET è stata bloccata.", status="warning"),
        TraceStep(order=9, stage="Riparazione", actor="Regole", detail="La claim bloccata non raggiunge il report verificato."),
        TraceStep(order=10, stage="Narrazione opzionale", actor="LLM + nuova verifica", detail="Una riscrittura LLM è ammessa solo se supera di nuovo il verificatore."),
        TraceStep(order=11, stage="Revisione", actor="Oncologo", detail="Valutazione di evidenze, lacune e conflitti."),
    ]
    return ArchitectureRun(
        architecture_id="agentic",
        title="Raccolta agentica verificabile",
        subtitle="Obiettivo ampio, strumenti iterativi, ledger e controllo delle claim",
        llm_roles=["Pianificatore e selettore di strumenti", "Narratore opzionale post-verifica"],
        trace=trace,
        evidence=evidence,
        report=report,
        dossier=_build_dossier(req, evidence, checks),
        claim_checks=checks,
        metrics=ArchitectureMetrics(
            elapsed_ms=91,
            tool_calls=4,
            evidence_count=len(evidence),
            verified_claims=sum(c.status == "supported" for c in checks),
            blocked_claims=sum(c.status == "blocked" for c in checks),
            review_claims=sum(c.requires_human_review for c in checks),
            source_supported_count=sum(c.status == "supported" for c in checks),
            source_uncertain_count=sum(c.status in ("insufficient", "not_checked") for c in checks),
            source_unsupported_count=sum(c.status == "blocked" for c in checks),
            applicability_indeterminate_count=len(evidence),
        ),
        limitations=[
            "La modalità demo illustra il contratto previsto, non una validazione clinica.",
            "La claim su MET è una fault injection dichiarata, usata per rendere visibile il blocco.",
        ],
    )


def _evidence_from_state(state: dict) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for record in state.get("variant_data", {}).get("evidence_records", []):
        source = f"PMID:{record['pmid']}" if record.get("pmid") else None
        therapies = [therapy for therapy in record.get("therapies", []) if therapy]
        clinical_object = (
            ", ".join(sorted(therapies))
            if therapies
            else record.get("molecular_profile", "clinical evidence")
        )
        items.append(EvidenceItem(
            subject=f"{state.get('gene', '')} {state.get('variant', '')}".strip(),
            relation=record.get("significance", "evidence"),
            object=clinical_object,
            context=record.get("disease", state.get("tumor_type", "")),
            source_id=source,
            provenance="Neo4j/CIViC snapshot tramite query tipizzata.",
            evidence_statement=record.get("evidence_statement"),
            citation_text=record.get("citation_text"),
            evidence_level=record.get("evidence_level"),
        ))
    return items


def _initial_state(req: ArchitectureComparisonRequest) -> dict:
    return {
        "gene": req.gene or "",
        "variant": req.variant,
        "tumor_type": req.tumor_type,
        "alteration_type": req.alteration_type,
        "therapy_line": req.therapy_line,
        "disease_stage": req.disease_stage,
        "disease_setting": req.disease_setting,
        "prior_therapies": req.prior_therapies,
        "prior_response": req.prior_response,
        "ecog_status": req.ecog_status,
        "cns_metastases": req.cns_metastases,
        "co_alterations": req.co_alterations,
        "jurisdiction": req.jurisdiction,
        "mtb_goal": req.mtb_goal,
        "enrich_with_oncokb": req.enrich_with_oncokb,
        "driver_variant": req.driver_variant or "",
        "complexity": "low",
        "variant_data": {},
        "drug_candidates": [],
        "trial_candidates": [],
        "resistance_data": [],
        "oncokb_enrichment": [],
        "report": "",
        "cited_pmids": [],
        "escat_tier": "non determinato",
    }


def _evidence_payload(item: EvidenceItem) -> dict:
    return {
        "subject": item.subject,
        "relation": item.relation,
        "object": item.object,
        "context": item.context,
        "source_id": item.source_id,
        "provenance": item.provenance,
        "evidence_statement": item.evidence_statement,
        "citation_text": item.citation_text,
        "evidence_level": item.evidence_level,
    }


def _live_deterministic(req: ArchitectureComparisonRequest) -> ArchitectureRun:
    from backend.pipeline.agents.resistance_checker import resistance_checker
    from backend.pipeline.agents.synthesizer import synthesizer
    from backend.pipeline.agents.target_identifier import target_identifier
    from backend.pipeline.agents.trial_matcher import trial_matcher
    from backend.pipeline.agents.variant_interpreter import variant_interpreter_low

    started = perf_counter()
    state = _initial_state(req)
    # Piano esplicito e stabile. Il componente interpreter recupera l'evidenza;
    # l'LLM resta usato per classificazione/sintesi come dichiarato nei limiti.
    state = variant_interpreter_low(state)
    state = target_identifier(state)
    state = trial_matcher(state)
    state = resistance_checker(state)
    retrieval_ms = int((perf_counter() - started) * 1000)
    synthesis_started = perf_counter()
    state = synthesizer(state)
    synthesis_ms = int((perf_counter() - synthesis_started) * 1000)
    evidence = _canonical_evidence(_evidence_from_state(state))
    checks = [ClaimCheck(
        claim="Il contenuto clinico del report coincide con le evidenze recuperate.",
        status="not_checked",
        reason=(
            "Il filtro corrente controlla gli identificatori PMID, ma non verifica "
            "l'aderenza semantica di ogni claim al record sorgente."
        ),
    )]
    dossier_started = perf_counter()
    dossier = _build_dossier(req, evidence, checks, state=state)
    dossier_ms = int((perf_counter() - dossier_started) * 1000)
    elapsed = int((perf_counter() - started) * 1000)
    return ArchitectureRun(
        architecture_id="deterministic",
        title="Traversal deterministico",
        subtitle="Piano fisso sui componenti reali del backend",
        llm_roles=["Classificatore ESCAT", "Sintetizzatore vincolato"],
        trace=[
            TraceStep(order=1, stage="Normalizzazione", actor="Input adapter", detail="Caso convertito nello stato canonico."),
            TraceStep(order=2, stage="Traversal", actor="Query tipizzate", detail="Evidenze, farmaci, trial e resistenze interrogati in ordine fisso."),
            TraceStep(order=3, stage="Sintesi", actor="LLM", detail="Report costruito dal contesto strutturato."),
            TraceStep(order=4, stage="Filtro PMID", actor="Regole", detail="Rimossi identificatori non presenti nel KG."),
        ],
        evidence=evidence,
        report=state.get("report", ""),
        dossier=dossier,
        claim_checks=checks,
        metrics=ArchitectureMetrics(
            elapsed_ms=elapsed,
            tool_calls=5,
            evidence_count=len(evidence),
            verified_claims=0,
            blocked_claims=0,
            review_claims=len(evidence),
            stage_timings_ms={
                "retrieval": retrieval_ms,
                "synthesis": synthesis_ms,
                "dossier": dossier_ms,
            },
            source_supported_count=0,
            source_uncertain_count=len(evidence),
            source_unsupported_count=0,
            applicability_indeterminate_count=len(evidence),
        ),
        limitations=["Il classificatore ESCAT live usa un LLM; il retrieval rimane vincolato alle query tipizzate."],
    )


def _agentic_trace(
    collection: Any,
    evidence: list[EvidenceItem],
    events: list[dict],
    ledger_valid: bool,
    supported: int,
    blocked: int,
    uncertain: int,
    compatible: int = 0,
    indeterminate_applicability: int = 0,
    not_compatible: int = 0,
) -> list[TraceStep]:
    """Costruisce la trace in modo condizionale su ``planning_mode``: non deve
    mai descrivere un'esecuzione in ``safe_fallback`` come pianificazione
    dinamica riuscita, né affermare che ogni osservazione ha guidato la
    decisione successiva quando il planner non è più stato interpellato."""
    dynamic = collection.planning_mode == "llm_dynamic"
    if dynamic:
        planning_detail = "Il planner ha scelto iterativamente gli strumenti."
        planning_status = "completed"
        collection_detail = (
            f"Completate {len(collection.tool_path)} chiamate; ogni osservazione ha "
            "alimentato la decisione successiva del planner."
        )
        collection_status = "completed"
    else:
        planning_detail = (
            "È stato eseguito un piano tipizzato predefinito; questa esecuzione non "
            "dimostra pianificazione agentica dinamica."
        )
        planning_status = "warning"
        collection_detail = (
            f"Completate {len(collection.tool_path)} chiamate secondo l'ordine di sicurezza "
            f"predefinito (motivo del fallback: {collection.fallback_reason})."
        )
        collection_status = "warning"

    mandatory_tools = getattr(collection, "mandatory_tools", []) or []
    missing_mandatory_tools = getattr(collection, "missing_mandatory_tools", []) or []
    incompleteness_reason = getattr(collection, "incompleteness_reason", None)
    completed_mandatory = [tool for tool in mandatory_tools if tool not in missing_mandatory_tools]
    collection_detail += (
        f" Policy minima per l'obiettivo — obbligatori: {', '.join(mandatory_tools) or 'nessuno'}; "
        f"completati: {', '.join(completed_mandatory) or 'nessuno'}; "
        f"mancanti: {', '.join(missing_mandatory_tools) or 'nessuno'}."
    )
    if missing_mandatory_tools:
        collection_detail += f" Motivo dell'incompletezza: {incompleteness_reason or 'non specificato'}."
        collection_status = "warning"

    return [
        TraceStep(order=1, stage="Controller di autonomia", actor="Policy", detail="Definiti strumenti consentiti, dipendenze e massimo numero di passi."),
        TraceStep(order=2, stage="Pianificazione dinamica", actor="LLM planner", detail=planning_detail, status=planning_status),
        TraceStep(order=3, stage="Raccolta iterativa", actor="Agente + strumenti KG", detail=collection_detail, status=collection_status),
        TraceStep(order=4, stage="Event log append-only", actor="SQLite hash-chain", detail=f"Persistiti {len(events)} eventi durante l'esecuzione; catena integra: {'sì' if ledger_valid else 'no'}.", status="completed" if ledger_valid else "blocked"),
        TraceStep(order=5, stage="Vista canonica", actor="Regole", detail=f"Deduplicazione completata: {len(evidence)} record canonici."),
        TraceStep(order=6, stage="Proiezione pertinente", actor="Regole", detail="Selezionati i record relativi al caso con statement clinico e provenienza."),
        TraceStep(order=7, stage="Rendering candidato", actor="Renderer deterministico", detail="Costruito esclusivamente dalla proiezione canonica."),
        TraceStep(
            order=8,
            stage="Verifica claim–fonte",
            actor="Regole + LLM",
            detail=(
                f"Il verificatore produce due assi indipendenti. Supporto documentale — PubMed/CIViC: "
                f"{supported} supportate, {blocked} bloccate, {uncertain} inviate a revisione. "
                f"Applicabilità al caso — {compatible} compatibili, {indeterminate_applicability} indeterminate, "
                f"{not_compatible} non compatibili."
            ),
            status="warning" if (blocked or uncertain or indeterminate_applicability or not_compatible) else "completed",
        ),
        TraceStep(
            order=9,
            stage="Riparazione",
            actor="Regole",
            detail=(
                "Le fonti con supporto documentale incerto o non supportato sono escluse dal report "
                "documentale. Le fonti supportate ma non compatibili (o con applicabilità indeterminata) "
                "restano visibili come contesto, non come opzioni per il caso."
            ),
        ),
        TraceStep(
            order=10,
            stage="Report verificato",
            actor="Renderer deterministico",
            detail=(
                "\"Verificato\" significa verificato rispetto al supporto documentale della fonte, non "
                "clinicamente raccomandato: sono emesse soltanto le claim che hanno superato provenienza, "
                "regole cliniche e verifica semantica."
            ),
        ),
        TraceStep(order=11, stage="Narrazione opzionale", actor="LLM + nuova verifica", detail="Non applicata in questa esecuzione: viene mostrato il report deterministico."),
        TraceStep(order=12, stage="Revisione", actor="Oncologo", detail="Gli esiti incerti sono esplicitamente destinati alla revisione umana."),
    ]


def _agentic_guarantees(collection: Any) -> list[str]:
    """Costruisce le garanzie in modo condizionale su ``planning_mode``: non
    deve mai descrivere una pianificazione dinamica riuscita quando è stato
    eseguito il piano sicuro predefinito, né il contrario."""
    if collection.planning_mode == "llm_dynamic":
        guarantees = ["Il planner ha scelto iterativamente gli strumenti."]
    else:
        guarantees = [
            "È stato eseguito il piano sicuro predefinito; questa esecuzione non "
            "dimostra pianificazione agentica dinamica."
        ]
    guarantees.append(
        f"Il ledger è persistito durante ogni decisione e tool call con catena SHA-256 verificata ({collection.run_id})."
    )
    guarantees.append(
        "Il verificatore è fail-closed su due assi indipendenti — supporto documentale e applicabilità al caso: "
        "fonte assente o esito incerto richiedono revisione umana su almeno uno dei due assi."
    )
    if collection.planning_mode == "safe_fallback":
        guarantees.append(
            "Il planner LLM non ha completato un piano valido; è stato eseguito il piano sicuro predefinito "
            f"(motivo: {collection.fallback_reason}; tentativi: {collection.planner_attempts}; "
            f"tempo planner: {collection.planner_elapsed_ms} ms)."
        )
    if collection.errors:
        guarantees.append("Escalation runtime: " + "; ".join(collection.errors))
    return guarantees


def _source_profile_cache() -> Any:
    """Cache di processo, condivisa fra le richieste: un PMID già verificato
    con lo stesso prompt/modello non causa mai una nuova chiamata LLM solo
    perché cambia il caso clinico richiesto."""
    from backend.pipeline.agentic.source_profile_cache import SourceProfileCache
    global _SOURCE_PROFILE_CACHE
    if _SOURCE_PROFILE_CACHE is None:
        _SOURCE_PROFILE_CACHE = SourceProfileCache()
    return _SOURCE_PROFILE_CACHE


_SOURCE_PROFILE_CACHE: Any = None


def _live_agentic(req: ArchitectureComparisonRequest) -> ArchitectureRun:
    from backend.pipeline.agentic.ledger import EventLedger
    from backend.pipeline.agentic.runtime import run_agentic_collection
    from backend.pipeline.agentic.source_verifier import verify_evidence_items

    started = perf_counter()
    collection = run_agentic_collection(_initial_state(req))
    collection_ms = int((perf_counter() - started) * 1000)
    projection_started = perf_counter()
    state = collection.state
    collected = _evidence_from_state(state)
    evidence = _canonical_evidence(collected)
    ledger = EventLedger()
    ledger.append(collection.run_id, "canonical_view_created", "canonicalizer", {
        "records_in": len(collected),
        "records_out": len(evidence),
        "records": [_evidence_payload(item) for item in evidence],
    })
    candidate_report = _render_candidate_report(_case_label(req), evidence)
    ledger.append(collection.run_id, "candidate_report_rendered", "deterministic_renderer", {
        "report": candidate_report,
    })
    projection_ms = int((perf_counter() - projection_started) * 1000)
    verification_started = perf_counter()
    verifier_metrics: dict[str, int] = {}
    verifications = verify_evidence_items(
        evidence,
        metrics=verifier_metrics,
        profile_cache=_source_profile_cache(),
        case_context={
            "gene": req.gene or "",
            "variant": req.variant,
            "tumor_type": req.tumor_type,
            "alteration_type": req.alteration_type,
            "therapy_line": req.therapy_line,
            "disease_stage": req.disease_stage or "",
            "disease_setting": req.disease_setting or "",
            "prior_therapies": ", ".join(req.prior_therapies),
            "prior_response": req.prior_response or "",
            "ecog_status": "" if req.ecog_status is None else str(req.ecog_status),
            "cns_metastases": "" if req.cns_metastases is None else str(req.cns_metastases),
            "co_alterations": ", ".join(req.co_alterations),
            "jurisdiction": req.jurisdiction or "",
            "mtb_goal": req.mtb_goal or "",
        },
    )
    checks = _checks_from_verifications(evidence, verifications)
    verification_ms = int((perf_counter() - verification_started) * 1000)
    ledger.append(collection.run_id, "claims_verified", "source_verifier", {
        "checks": [{
            "claim": _claim_text(item),
            "source_id": item.source_id,
            "source_support_status": verification.source_support_status,
            "source_support_reason": verification.source_support_reason,
            "source_population": verification.source_population,
            "source_line": verification.source_line,
            "source_setting": verification.source_setting,
            "source_prerequisites": verification.source_prerequisites,
            "applicability_status": verification.applicability_status,
            "applicability_reason": verification.applicability_reason,
            "verification_level": verification.verification_level,
        } for item, verification in zip(evidence, verifications)],
    })
    rendering_started = perf_counter()
    report = _render_verified_report(_case_label(req), evidence, verifications)
    ledger.append(collection.run_id, "verified_report_rendered", "deterministic_renderer", {
        "report": report,
    })
    dossier = _build_dossier(req, evidence, checks, verifications=verifications, state=state)
    rendering_ms = int((perf_counter() - rendering_started) * 1000)
    events = ledger.events(collection.run_id)
    ledger_valid = ledger.verify_chain(collection.run_id)
    elapsed = int((perf_counter() - started) * 1000)

    supported = sum(v.source_support_status == "supported" for v in verifications)
    blocked = sum(v.source_support_status == "unsupported" for v in verifications)
    uncertain = sum(v.source_support_status == "uncertain" for v in verifications)
    compatible = sum(v.applicability_status == "compatible" for v in verifications)
    indeterminate_applicability = sum(v.applicability_status == "indeterminate" for v in verifications)
    not_compatible = sum(v.applicability_status == "not_compatible" for v in verifications)

    trace = _agentic_trace(
        collection, evidence, events, ledger_valid,
        supported, blocked, uncertain,
        compatible, indeterminate_applicability, not_compatible,
    )

    guarantees = _agentic_guarantees(collection)

    return ArchitectureRun(
        architecture_id="agentic",
        title="Architettura agentica verificabile",
        subtitle="Raccolta adattiva, ledger canonico, rendering e verifica separati",
        llm_roles=["Controller della raccolta", "Narratore opzionale post-verifica"],
        trace=trace,
        evidence=evidence,
        report=report,
        dossier=dossier,
        claim_checks=checks,
        metrics=ArchitectureMetrics(
            elapsed_ms=elapsed,
            tool_calls=len(collection.tool_path),
            evidence_count=len(evidence),
            verified_claims=supported,
            blocked_claims=blocked,
            review_claims=uncertain,
            ledger_events=len(events),
            stage_timings_ms={
                "collection": collection_ms,
                "projection": projection_ms,
                "verification": verification_ms,
                "rendering": rendering_ms,
            },
            source_supported_count=supported,
            source_uncertain_count=uncertain,
            source_unsupported_count=blocked,
            applicability_compatible_count=compatible,
            applicability_indeterminate_count=indeterminate_applicability,
            applicability_not_compatible_count=not_compatible,
            cache_hits=verifier_metrics.get("cache_hits", 0),
            cache_misses=verifier_metrics.get("cache_misses", 0),
            verifier_batches=verifier_metrics.get("verifier_batches", 0),
            failed_batches=verifier_metrics.get("failed_batches", 0),
            retry_items=verifier_metrics.get("retry_items", 0),
            recovered_items=verifier_metrics.get("recovered_items", 0),
            permanently_failed_items=verifier_metrics.get("permanently_failed_items", 0),
            source_profile_elapsed_ms=verifier_metrics.get("source_profile_elapsed_ms", 0),
            applicability_elapsed_ms=verifier_metrics.get("applicability_elapsed_ms", 0),
        ),
        limitations=guarantees,
        run_id=collection.run_id,
        ledger_valid=ledger_valid,
        planning_mode=collection.planning_mode,
        fallback_reason=collection.fallback_reason,
        planner_attempts=collection.planner_attempts,
        planner_elapsed_ms=collection.planner_elapsed_ms,
        tool_call_timings=collection.tool_call_timings,
    )


def compare_architectures(req: ArchitectureComparisonRequest) -> ArchitectureComparisonResponse:
    if req.execution_mode == "demo":
        deterministic = _demo_deterministic(req)
        agentic = _demo_agentic(req)
    else:
        deterministic = _live_deterministic(req)
        agentic = _live_agentic(req)
    return ArchitectureComparisonResponse(
        execution_mode=req.execution_mode,
        case_label=_case_label(req),
        disclaimer=DISCLAIMER,
        deterministic=deterministic,
        agentic=agentic,
        summary=_summary(deterministic, agentic),
    )
