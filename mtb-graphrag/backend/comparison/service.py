"""Esecuzione comparativa delle due architetture proposte nella tesi.

La modalità ``demo`` non richiede Neo4j o un endpoint LLM ed espone un caso
sintetico dichiarato. La modalità ``live`` usa i componenti reali del backend.
Per l'architettura agentica rende esplicita la distanza tra la raccolta adattiva
corrente e il contratto verificabile proposto, senza presentare il solo routing
LangGraph come un agente completo.
"""

from __future__ import annotations

from time import perf_counter

from backend.api.schemas import (
    ArchitectureComparisonRequest,
    ArchitectureComparisonResponse,
    ArchitectureMetrics,
    ArchitectureRun,
    ClaimCheck,
    ComparisonSummary,
    EvidenceItem,
    TraceStep,
)


DISCLAIMER = (
    "Dimostratore di ricerca per preparazione e revisione dell'evidenza. "
    "Non produce raccomandazioni terapeutiche e non sostituisce il Molecular Tumor Board."
)


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


def _render_verified_report(case_label: str, items: list[EvidenceItem]) -> str:
    """Rendering deterministico: emette solo record dotati di fonte."""
    supported = [item for item in items if item.source_id]
    if not supported:
        return (
            f"Caso: {case_label}.\n"
            "Nessuna evidenza con provenienza sufficiente per generare claim fattuali. "
            "È richiesta la revisione dell'oncologo."
        )
    lines = [f"Caso: {case_label}.", "Evidenze ammesse nel report verificato:"]
    for item in supported:
        lines.append(f"- {_claim_text(item)} [{item.source_id}]")
    lines.append(
        "Il report organizza l'evidenza disponibile e deve essere revisionato "
        "dal Molecular Tumor Board; non costituisce una raccomandazione terapeutica."
    )
    return "\n".join(lines)


def _checks_from_ledger(items: list[EvidenceItem]) -> list[ClaimCheck]:
    if not items:
        return [ClaimCheck(
            claim="Nessuna claim fattuale emessa.",
            status="insufficient",
            reason="La vista canonica non contiene record utilizzabili.",
        )]
    return [ClaimCheck(
        claim=_claim_text(item),
        status="supported" if item.source_id else "blocked",
        reason=(
            "Claim ricostruita dal record canonico e ancorata alla fonte."
            if item.source_id
            else "Claim esclusa dal rendering perché priva di una fonte verificabile."
        ),
        source_id=item.source_id,
    ) for item in items]


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
        claim_checks=checks,
        metrics=ArchitectureMetrics(
            elapsed_ms=34,
            tool_calls=1,
            evidence_count=len(evidence),
            verified_claims=sum(c.status == "supported" for c in checks),
            blocked_claims=sum(c.status == "blocked" for c in checks),
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
        claim_checks=checks,
        metrics=ArchitectureMetrics(
            elapsed_ms=91,
            tool_calls=4,
            evidence_count=len(evidence),
            verified_claims=sum(c.status == "supported" for c in checks),
            blocked_claims=sum(c.status == "blocked" for c in checks),
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
        items.append(EvidenceItem(
            subject=f"{state.get('gene', '')} {state.get('variant', '')}".strip(),
            relation=record.get("significance", "evidence"),
            object=record.get("molecular_profile", "clinical evidence"),
            context=record.get("disease", state.get("tumor_type", "")),
            source_id=source,
            provenance="Neo4j/CIViC snapshot tramite query tipizzata.",
        ))
    return items


def _initial_state(req: ArchitectureComparisonRequest) -> dict:
    return {
        "gene": req.gene or "",
        "variant": req.variant,
        "tumor_type": req.tumor_type,
        "alteration_type": req.alteration_type,
        "therapy_line": req.therapy_line,
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
    state = synthesizer(state)
    elapsed = int((perf_counter() - started) * 1000)
    evidence = _evidence_from_state(state)
    checks = [ClaimCheck(
        claim="Il contenuto clinico del report coincide con le evidenze recuperate.",
        status="not_checked",
        reason=(
            "Il filtro corrente controlla gli identificatori PMID, ma non verifica "
            "l'aderenza semantica di ogni claim al record sorgente."
        ),
    )]
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
        claim_checks=checks,
        metrics=ArchitectureMetrics(elapsed_ms=elapsed, tool_calls=5, evidence_count=len(evidence), verified_claims=0, blocked_claims=0),
        limitations=["Il classificatore ESCAT live usa un LLM; il retrieval rimane vincolato alle query tipizzate."],
    )


def _live_agentic(req: ArchitectureComparisonRequest) -> ArchitectureRun:
    from backend.pipeline.graph import run_pipeline

    started = perf_counter()
    state = run_pipeline(_initial_state(req))
    collected = _evidence_from_state(state)
    evidence = _canonical_evidence(collected)
    checks = _checks_from_ledger(evidence)
    report = _render_verified_report(_case_label(req), evidence)
    elapsed = int((perf_counter() - started) * 1000)

    path = ["complexity_check", "variant_interpreter"]
    if state.get("complexity") in ("moderate", "high"):
        path.extend(["target_identifier", "trial_matcher", "resistance_checker"])
    path.extend(["synthesizer", "oncokb_enricher"])

    supported = sum(check.status == "supported" for check in checks)
    blocked = sum(check.status == "blocked" for check in checks)
    trace = [
        TraceStep(order=1, stage="Controller di autonomia", actor="Regole + LLM", detail=f"Complessità {state.get('complexity', 'non determinata')}: selezionato il percorso di raccolta."),
        TraceStep(order=2, stage="Raccolta adattiva", actor="LangGraph + strumenti KG", detail=f"Eseguiti i nodi: {', '.join(path)}."),
        TraceStep(order=3, stage="Event log", actor="Adapter sperimentale", detail=f"Acquisiti {len(collected)} record dalla raccolta corrente."),
        TraceStep(order=4, stage="Vista canonica", actor="Regole", detail=f"Deduplicazione completata: {len(evidence)} record canonici."),
        TraceStep(order=5, stage="Proiezione pertinente", actor="Regole", detail="Selezionati i record utilizzabili per il caso e dotati di provenienza."),
        TraceStep(order=6, stage="Rendering deterministico", actor="Renderer", detail="Il report verificabile è generato dai record canonici, non dal testo libero dell'LLM."),
        TraceStep(order=7, stage="Verifica delle claim", actor="Claim verifier", detail=f"Claim supportate: {supported}; claim bloccate: {blocked}."),
        TraceStep(order=8, stage="Narrazione opzionale", actor="LLM + nuova verifica", detail="Non applicata in questa esecuzione: viene mostrato il report deterministico."),
        TraceStep(order=9, stage="Revisione", actor="Oncologo", detail="Il clinico controlla evidenze, provenienza, lacune e conflitti."),
    ]
    return ArchitectureRun(
        architecture_id="agentic",
        title="Architettura agentica verificabile",
        subtitle="Raccolta adattiva, ledger canonico, rendering e verifica separati",
        llm_roles=["Controller della raccolta", "Narratore opzionale post-verifica"],
        trace=trace,
        evidence=evidence,
        report=report,
        claim_checks=checks,
        metrics=ArchitectureMetrics(
            elapsed_ms=elapsed,
            tool_calls=len(path),
            evidence_count=len(evidence),
            verified_claims=supported,
            blocked_claims=blocked,
        ),
        limitations=[
            "La raccolta live usa ancora il routing condizionale LangGraph: la pianificazione libera degli strumenti non è implementata.",
            "L'event log è derivato dallo stato finale e non è ancora persistito append-only durante l'esecuzione.",
            "Il verificatore controlla il supporto rispetto al ledger del KG, non la correttezza clinica della fonte.",
        ],
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
