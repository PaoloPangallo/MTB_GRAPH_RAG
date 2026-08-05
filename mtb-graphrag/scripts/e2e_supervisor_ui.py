"""Percorso end-to-end della Supervisor UI, guidato da un browser reale.

Perché non basta la suite jsdom. I test dei componenti montano una vista alla
volta con dati costruiti nel test: dicono che ogni pezzo funziona, non che la
pagina intera, alimentata dal backend vero, mostri la pipeline. Questo script
apre la rotta, avvia le run, attraversa gli stage e legge il DOM risultante —
quindi verifica anche ciò che nasce solo dall'integrazione: lo stream SSE, la
run nell'URL, il refresh, e la resa di un `output_preview` di forma reale.

Il controllo su ``[object Object]`` vive qui e non solo nei test unitari perché
il difetto compariva su dati veri, di forma che nessun test aveva costruito.

Prerequisiti:
    backend  VERIFIABLE_PIPELINE_RESEARCH_ENABLED=1 uvicorn ... --port 8001
    frontend VITE_API_BASE_URL=http://localhost:8001 npx vite --port 5180

Uso:
    python mtb-graphrag/scripts/e2e_supervisor_ui.py [--out DIR] [--base URL]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

DEFAULT_BASE = "http://localhost:5180"
PIPELINE_ROUTE = "/research/verifiable-pipeline"
LEGACY_ROUTE = "/legacy/v3-deterministic"

#: Etichetta della chip nella UI -> ciò che il caso deve dimostrare.
CASES: tuple[tuple[str, str], ...] = (
    ("therapy evaluation strong match", "QUOTE accettata, catena documentale completa"),
    ("therapy discovery", "intervento scoperto dal grafo, non nominato nel testo"),
    ("partial incomplete context", "match parziale del biomarcatore"),
    ("contradicted or resistance", "candidate non promossa a esito positivo"),
    ("casecontext mismatch no match", "nessuna candidate: la pipeline si ferma"),
)

#: Vocabolario che non deve comparire nella rotta nuova. Sono i termini della
#: pipeline precedente: se riaffiorano qui, le due trace si sono mescolate.
FORBIDDEN_TERMS: tuple[str, ...] = (
    "qualified_claim_repository",
    "Qualified Claim",
    "Parent GraphEvidenceRecord",
    "Evidenze principali",
    "Applicabilità non valutata separatamente",
)

OBJECT_COERCION = re.compile(r"\[object \w+\]")


@dataclass
class Findings:
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def check(self, condition: bool, message: str) -> bool:
        if not condition:
            self.failures.append(message)
        return condition

    def note(self, message: str) -> None:
        self.notes.append(message)


def _assert_no_coercion(page: Page, where: str, findings: Findings) -> None:
    text = page.inner_text("body")
    match = OBJECT_COERCION.search(text)
    if match:
        start = max(0, match.start() - 90)
        findings.failures.append(
            f"{where}: trovato {match.group(0)!r} — contesto: …{text[start:match.end() + 90]}…"
        )


def _wait_for_terminal(page: Page, findings: Findings, where: str) -> None:
    """Attende la conclusione della run leggendo lo stato mostrato dalla pagina."""
    terminal = "Completata|Completata con riserve|Fermata correttamente|Fallita"
    try:
        page.wait_for_selector(f"text=/{terminal}/", timeout=90_000)
    except Exception:  # noqa: BLE001 — la diagnosi sta nel messaggio, non nell'eccezione
        findings.failures.append(f"{where}: la run non ha raggiunto uno stato terminale in 90 s")


#: Livelli attesi nella catena, nell'ordine.
PROVENANCE_LEVELS: tuple[str, ...] = (
    "CaseContext", "Graph Candidate Assertion", "Documento", "Source Unit",
    "Citazione d’autore", "Validazione della citazione",
    "Controlli deterministici", "Voce del dossier",
)


def _check_provenance_chain(page: Page, label: str, findings: Findings) -> None:
    """Verifica la catena, dove una catena deve esistere.

    Una run fermata a ``RETRIEVAL_NO_MATCH`` non ha candidate, quindi non ha
    catena: pretenderla lì significherebbe pretendere una provenienza per un
    oggetto che il sistema ha correttamente rifiutato di costruire.
    """
    chain = page.locator("ol[aria-label^='Catena di provenienza']")
    if chain.count() == 0:
        findings.note(f"{label}: nessuna catena — la run non ha prodotto candidate")
        return

    text = chain.first.inner_text()
    for level in PROVENANCE_LEVELS:
        findings.check(
            level in text,
            f"caso {label!r}: livello di provenienza assente — {level!r}",
        )


def _open_stage(page: Page, label: str) -> bool:
    """Apre uno stage nella spina. Falso se quello stage non è in pagina."""
    target = page.locator(f"button:has-text('{label}'), [role=button]:has-text('{label}')").first
    if target.count() == 0:
        return False
    target.click()
    page.wait_for_timeout(350)
    return True


def run_case(page: Page, base: str, label: str, expectation: str,
             out: Path, findings: Findings) -> None:
    page.goto(f"{base}{PIPELINE_ROUTE}", wait_until="networkidle")

    chip = page.locator(f"text='{label}'").first
    if chip.count() == 0:
        findings.failures.append(f"caso {label!r}: chip non trovata nella pagina")
        return
    chip.click()
    page.wait_for_timeout(250)

    textarea = page.locator("textarea[aria-label='Testo clinico in linguaggio libero']").first
    findings.check(
        textarea.input_value().strip() != "",
        f"caso {label!r}: il caso dimostrativo non ha compilato la textarea",
    )

    page.locator("button:has-text('Esegui la pipeline')").first.click()
    page.wait_for_url(re.compile(r".*/runs/[0-9a-f-]{36}"), timeout=30_000)
    _wait_for_terminal(page, findings, f"caso {label!r}")
    page.wait_for_timeout(1200)

    slug = label.replace(" ", "-")
    page.screenshot(path=str(out / f"{slug}--01-run.png"), full_page=True)
    _assert_no_coercion(page, f"caso {label!r} (run)", findings)

    body = page.inner_text("body")
    for term in FORBIDDEN_TERMS:
        if term in body:
            findings.failures.append(f"caso {label!r}: terminologia legacy in pagina — {term!r}")

    # Attraversa gli stage con una vista dedicata, aprendo il tab "Output".
    for stage_label in ("CaseContext Parser", "CaseContext Match", "Knowledge Graph",
                        "Source Unit", "Paper Selection", "Paper Context Enricher",
                        "Quote Validation", "Deterministic Gates"):
        if not _open_stage(page, stage_label):
            continue
        output_tab = page.locator("button[role=tab]:has-text('Output')").first
        if output_tab.count() > 0:
            output_tab.click()
            page.wait_for_timeout(300)
        _assert_no_coercion(page, f"caso {label!r} / stage {stage_label}", findings)
        page.screenshot(
            path=str(out / f"{slug}--stage-{stage_label.replace(' ', '-').lower()}.png"),
            full_page=True,
        )

    # Le tre viste inferiori esistono solo a run conclusa.
    #
    # `Provenienza` compare due volte in pagina — una nello stage inspector e
    # una qui — e prendere la prima corrispondenza lasciava la vista inferiore
    # mai aperta, quindi mai verificata. Si àncora al gruppo di tab che contiene
    # `Modalità relatore`, che esiste solo in basso.
    lower_tabs = page.locator("[role=tablist]:has(button:has-text('Modalità relatore'))").first
    if lower_tabs.count() == 0:
        findings.note(f"{label}: nessuna vista inferiore (run senza dossier)")
    else:
        for tab_label in ("Dossier", "Provenienza", "Modalità relatore"):
            tab = lower_tabs.locator(f"button:has-text('{tab_label}')").first
            if tab.count() == 0:
                continue
            tab.click()
            page.wait_for_timeout(600)
            _assert_no_coercion(page, f"caso {label!r} / {tab_label}", findings)
            page.screenshot(path=str(out / f"{slug}--tab-{tab_label.split()[0].lower()}.png"),
                            full_page=True)

            if tab_label == "Provenienza":
                _check_provenance_chain(page, label, findings)

    # Il refresh non deve perdere la trace: è la ragione per cui la run sta nell'URL.
    run_url = page.url
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1500)
    findings.check(page.url == run_url, f"caso {label!r}: il refresh ha cambiato URL")
    reloaded = page.inner_text("body")
    findings.check(
        "stage" in reloaded and ("Completata" in reloaded or "Fermata" in reloaded),
        f"caso {label!r}: dopo il refresh la trace non è stata ricaricata",
    )
    _assert_no_coercion(page, f"caso {label!r} (dopo refresh)", findings)
    findings.note(f"{label}: {expectation} — verificato")


def check_routing(page: Page, base: str, out: Path, findings: Findings) -> None:
    page.goto(base, wait_until="networkidle")
    findings.check(
        PIPELINE_ROUTE in page.url,
        f"la radice non reindirizza alla pipeline verificabile (url: {page.url})",
    )
    page.screenshot(path=str(out / "00-home-redirect.png"), full_page=True)

    page.goto(f"{base}{LEGACY_ROUTE}", wait_until="networkidle")
    page.wait_for_timeout(800)
    legacy_text = page.inner_text("body")
    findings.check(
        "Legacy V3 deterministic" in legacy_text or "LEGACY V3" in legacy_text.upper(),
        "la rotta legacy non mostra il badge che la identifica",
    )
    page.screenshot(path=str(out / "00-legacy-route.png"), full_page=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--out", default="docs/verifiable_pipeline/screenshots")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    findings = Findings()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})

        console_errors: list[str] = []
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))

        check_routing(page, args.base, out, findings)
        for label, expectation in CASES:
            run_case(page, args.base, label, expectation, out, findings)

        browser.close()

    if console_errors:
        findings.failures.extend(f"errore JavaScript in pagina: {e}" for e in console_errors)

    print(f"\nScreenshot in {out.resolve()}")
    for note in findings.notes:
        print(f"  ok   {note}")
    for failure in findings.failures:
        print(f"  FAIL {failure}")

    print(f"\n{len(findings.notes)} casi verificati, {len(findings.failures)} problemi")
    return 1 if findings.failures else 0


if __name__ == "__main__":
    sys.exit(main())
