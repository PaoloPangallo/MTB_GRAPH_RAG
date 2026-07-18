"""
Script: download_benchmark_papers_v2.py
Scopo:  Scarica abstract, metadati e (se disponibile) full text open access
        per i 30 PMID del dataset benchmark MTB esteso.
        - Casi 001-010: Tier I-A baseline (varianti azionabili classiche)
        - Casi 011-020: Tier I-A/II resistenza acquisita e tumor-agnostic
        - Casi 021-030: Tier II off-label e profili complessi

        Usa NCBI E-utilities + PubMed Central (PMC) + Unpaywall come fallback.

NUOVI PMID (tutti verificati su PubMed):
  BENCH-011  EGFR T790M    NSCLC          Osimertinib    PMID 27959700 (AURA3)
  BENCH-012  KRAS G12C     NSCLC          Sotorasib      PMID 34161704 (CodeBreaK100)
  BENCH-013  ALK G1202R    NSCLC          Lorlatinib     PMID 33207094 (CROWN)
  BENCH-014  ABL1 T315I    CML            Ponatinib      PMID 23154516 (PACE)
  BENCH-015  RET Fusion    NSCLC          Selpercatinib  PMID 32846060 (LIBRETTO-001)
  BENCH-016  NTRK Fusion   Tumor-agnostic Larotrectinib  PMID 29466156 (Drilon NEJM)
  BENCH-017  MSI-H         Colorectal     Pembrolizumab  PMID 33264544 (KEYNOTE-177)
  BENCH-018  KRAS G12C     Colorectal     Sotorasib+Pani PMID 37870968 (CodeBreaK300)
  BENCH-019  KIT V654A     GIST           Sunitinib      PMID 16624552 (resistenza)
  BENCH-020  BRAF V600E    NSCLC          Dabra+Trame    PMID 27283860 (off-label NSCLC)

  BENCH-021  ERBB2 Amp     Gastric        Trastuzumab    PMID 20728210 (ToGA)
  BENCH-022  BRCA2 Mut     Prostate       Olaparib       PMID 32343890 (PROfound)
  BENCH-023  PIK3CA Mut    Colorectal     Alpelisib      PMID 22421194 (off-label)
  BENCH-024  EGFR Exon19   NSCLC          Osimertinib    PMID 29151359 (FLAURA)
  BENCH-025  IDH1 R132     AML            Ivosidenib     PMID 29860938 (AG120)
  BENCH-026  FGFR2 Fusion  Cholangioca.   Pemigatinib    PMID 32203698 (FIGHT-202)
  BENCH-027  MET Exon14    NSCLC          Capmatinib     PMID 32877583 (GEOMETRY)
  BENCH-028  ROS1 Fusion   NSCLC          Crizotinib     PMID 25264305 (PROFILE)
  BENCH-029  BRAF V600E    Thyroid        Dabra+Trame    PMID 29072975 (off-label)
  BENCH-030  HER2 Amp      Gastric        Tras-deruxtecan PMID 32469182 (DESTINY)

Requisiti:
  pip install requests rich
"""

import os
import json
import time
import requests
import csv
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

# ============================================================================
# CONFIGURAZIONE
# ============================================================================

NCBI_API_KEY = "cced7273c4852e482e80f0eeb52b3849fa08"
UNPAYWALL_EMAIL = "paolo.pangallo23@gmail.com"
OUTPUT_DIR = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\benchmark_papers")
SLEEP_TIME = 0.34 if not NCBI_API_KEY else 0.11

# ============================================================================
# PMID DEL BENCHMARK ESTESO — 30 casi MTB
# ============================================================================

BENCHMARK_PMIDS = {
    # ---- CASI BASELINE 001-010 (Tier I-A classici) ----
    "BENCH-001": {"pmid": "37937763", "case": "EGFR L858R — NSCLC — Osimertinib",
                  "gene": "EGFR", "variant": "L858R", "tumor": "NSCLC",
                  "expected_drug": "Osimertinib", "escat": "I-A", "category": "baseline"},
    "BENCH-002": {"pmid": "28586279", "case": "ALK Fusion — NSCLC — Alectinib (ALEX)",
                  "gene": "ALK", "variant": "Fusion", "tumor": "NSCLC",
                  "expected_drug": "Alectinib", "escat": "I-A", "category": "baseline"},
    "BENCH-003": {"pmid": "21639808", "case": "BRAF V600E — Melanoma — Vemurafenib",
                  "gene": "BRAF", "variant": "V600E", "tumor": "Melanoma",
                  "expected_drug": "Vemurafenib/Dabrafenib+Trametinib", "escat": "I-A", "category": "baseline"},
    "BENCH-004": {"pmid": "26874901", "case": "ERBB2 Amplification — Breast HER2+ — Trastuzumab",
                  "gene": "ERBB2", "variant": "Amplification", "tumor": "Breast Cancer HER2+",
                  "expected_drug": "Trastuzumab+Pertuzumab", "escat": "I-A", "category": "baseline"},
    "BENCH-005": {"pmid": "30345884", "case": "BRCA1 Mutation — Ovarian — Olaparib",
                  "gene": "BRCA1", "variant": "Mutation", "tumor": "Ovarian Cancer",
                  "expected_drug": "Olaparib", "escat": "I-A", "category": "baseline"},
    "BENCH-006": {"pmid": "11423618", "case": "BCR-ABL1 Fusion — CML — Imatinib",
                  "gene": "ABL1", "variant": "BCR-ABL1 Fusion", "tumor": "CML",
                  "expected_drug": "Imatinib", "escat": "I-A", "category": "baseline"},
    "BENCH-007": {"pmid": "31566309", "case": "BRAF V600E — mCRC — Encorafenib+Cetuximab",
                  "gene": "BRAF", "variant": "V600E", "tumor": "Colorectal Cancer",
                  "expected_drug": "Encorafenib+Cetuximab", "escat": "I-A", "category": "baseline"},
    "BENCH-008": {"pmid": "31091374", "case": "PIK3CA Mutation — Breast HR+ — Alpelisib+Fulvestrant",
                  "gene": "PIK3CA", "variant": "Mutation", "tumor": "Breast Cancer HR+",
                  "expected_drug": "Alpelisib+Fulvestrant", "escat": "I-A", "category": "baseline"},
    "BENCH-009": {"pmid": "14645423", "case": "KIT Exon 11 — GIST — Imatinib",
                  "gene": "KIT", "variant": "Exon 11 Mutation", "tumor": "GIST",
                  "expected_drug": "Imatinib", "escat": "I-A", "category": "baseline"},
    "BENCH-010": {"pmid": "31665578", "case": "FLT3 ITD — AML — Gilteritinib",
                  "gene": "FLT3", "variant": "ITD", "tumor": "AML",
                  "expected_drug": "Gilteritinib", "escat": "I-A", "category": "baseline"},

    # ---- CASI RESISTENZA ACQUISITA E TUMOR-AGNOSTIC 011-020 ----
    "BENCH-011": {"pmid": "27959700", "case": "EGFR T790M — NSCLC — Osimertinib (resistenza)",
                  "gene": "EGFR", "variant": "T790M", "tumor": "NSCLC",
                  "expected_drug": "Osimertinib", "escat": "I-A", "category": "resistance"},
    "BENCH-012": {"pmid": "34096690", "case": "KRAS G12C — NSCLC — Sotorasib (CodeBreaK100 fase2)",
                  "gene": "KRAS", "variant": "G12C", "tumor": "NSCLC",
                  "expected_drug": "Sotorasib", "escat": "I-A", "category": "new_target"},
    "BENCH-013": {"pmid": "33207094", "case": "ALK G1202R — NSCLC — Lorlatinib (resistenza)",
                  "gene": "ALK", "variant": "G1202R", "tumor": "NSCLC",
                  "expected_drug": "Lorlatinib", "escat": "I-A", "category": "resistance"},
    "BENCH-014": {"pmid": "24180494", "case": "BCR-ABL1 T315I — CML — Ponatinib (PACE trial)",
                  "gene": "ABL1", "variant": "T315I", "tumor": "CML",
                  "expected_drug": "Ponatinib", "escat": "I-A", "category": "resistance"},
    "BENCH-015": {"pmid": "32846060", "case": "RET Fusion — NSCLC — Selpercatinib",
                  "gene": "RET", "variant": "Fusion", "tumor": "NSCLC",
                  "expected_drug": "Selpercatinib", "escat": "I-A", "category": "new_target"},
    "BENCH-016": {"pmid": "29466156", "case": "NTRK Fusion — Tumor-agnostic — Larotrectinib",
                  "gene": "NTRK1", "variant": "Fusion", "tumor": "Solid Tumor",
                  "expected_drug": "Larotrectinib", "escat": "I-C", "category": "tumor_agnostic"},
    "BENCH-017": {"pmid": "33264544", "case": "MSI-H — Colorectal — Pembrolizumab",
                  "gene": "MMR", "variant": "MSI-High", "tumor": "Colorectal Cancer",
                  "expected_drug": "Pembrolizumab", "escat": "I-A", "category": "biomarker"},
    "BENCH-018": {"pmid": "37870968", "case": "KRAS G12C — mCRC — Sotorasib+Panitumumab",
                  "gene": "KRAS", "variant": "G12C", "tumor": "Colorectal Cancer",
                  "expected_drug": "Sotorasib+Panitumumab", "escat": "I-A", "category": "new_target"},
    "BENCH-019": {"pmid": "16624552", "case": "KIT Exon 9 — GIST — Sunitinib (resistenza imatinib)",
                  "gene": "KIT", "variant": "Exon 9 Mutation", "tumor": "GIST",
                  "expected_drug": "Sunitinib", "escat": "II", "category": "resistance"},
    "BENCH-020": {"pmid": "27283860", "case": "BRAF V600E — NSCLC — Dabrafenib+Trametinib (off-label)",
                  "gene": "BRAF", "variant": "V600E", "tumor": "NSCLC",
                  "expected_drug": "Dabrafenib+Trametinib", "escat": "I-B", "category": "off_label"},

    # ---- CASI TIER II OFF-LABEL E PROFILI COMPLESSI 021-030 ----
    "BENCH-021": {"pmid": "20728210", "case": "ERBB2 Amp — Gastric — Trastuzumab (ToGA)",
                  "gene": "ERBB2", "variant": "Amplification", "tumor": "Gastric Cancer",
                  "expected_drug": "Trastuzumab", "escat": "I-A", "category": "off_label"},
    "BENCH-022": {"pmid": "32343890", "case": "BRCA2 Mut — Prostate — Olaparib (PROfound)",
                  "gene": "BRCA2", "variant": "Mutation", "tumor": "Prostate Cancer",
                  "expected_drug": "Olaparib", "escat": "I-A", "category": "off_label"},
    "BENCH-023": {"pmid": "32919526", "case": "TMB-High — Solid Tumor — Pembrolizumab (KEYNOTE-158)",
                  "gene": "TMB", "variant": "TMB-High", "tumor": "Solid Tumor",
                  "expected_drug": "Pembrolizumab", "escat": "I-C", "category": "tumor_agnostic"},
    "BENCH-024": {"pmid": "29151359", "case": "EGFR Exon 19 del — NSCLC — Osimertinib (FLAURA)",
                  "gene": "EGFR", "variant": "Exon 19 Deletion", "tumor": "NSCLC",
                  "expected_drug": "Osimertinib", "escat": "I-A", "category": "baseline"},
    "BENCH-025": {"pmid": "29860938", "case": "IDH1 R132 — AML — Ivosidenib",
                  "gene": "IDH1", "variant": "R132", "tumor": "AML",
                  "expected_drug": "Ivosidenib", "escat": "I-A", "category": "new_target"},
    "BENCH-026": {"pmid": "32203698", "case": "FGFR2 Fusion — Cholangiocarcinoma — Pemigatinib",
                  "gene": "FGFR2", "variant": "Fusion", "tumor": "Cholangiocarcinoma",
                  "expected_drug": "Pemigatinib", "escat": "I-A", "category": "new_target"},
    "BENCH-027": {"pmid": "32877583", "case": "MET Exon 14 skipping — NSCLC — Capmatinib",
                  "gene": "MET", "variant": "Exon 14 Skipping", "tumor": "NSCLC",
                  "expected_drug": "Capmatinib", "escat": "I-A", "category": "new_target"},
    "BENCH-028": {"pmid": "25264305", "case": "ROS1 Fusion — NSCLC — Crizotinib",
                  "gene": "ROS1", "variant": "Fusion", "tumor": "NSCLC",
                  "expected_drug": "Crizotinib", "escat": "I-A", "category": "new_target"},
    "BENCH-029": {"pmid": "29072975", "case": "BRAF V600E — Thyroid — Dabrafenib+Trametinib (off-label)",
                  "gene": "BRAF", "variant": "V600E", "tumor": "Thyroid Cancer",
                  "expected_drug": "Dabrafenib+Trametinib", "escat": "II", "category": "off_label"},
    "BENCH-030": {"pmid": "32469182", "case": "HER2 Amp — Gastric — Trastuzumab deruxtecan (DESTINY)",
                  "gene": "ERBB2", "variant": "Amplification", "tumor": "Gastric Cancer",
                  "expected_drug": "Trastuzumab deruxtecan", "escat": "I-A", "category": "new_target"},
}

# ============================================================================
# SETUP
# ============================================================================

console = Console(width=95, legacy_windows=False)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def build_params(extra={}):
    params = {"retmode": "json"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    params.update(extra)
    return params

# ============================================================================
# FUNZIONI CORE (identiche allo script v1)
# ============================================================================

def fetch_abstract_and_metadata(pmid: str) -> dict:
    url = f"{BASE_URL}/efetch.fcgi"
    params = build_params({"db": "pubmed", "id": pmid, "rettype": "xml", "retmode": "xml"})
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        xml_content = response.text
    except requests.RequestException as e:
        return {"pmid": pmid, "error": str(e), "status": "fetch_failed"}
    time.sleep(SLEEP_TIME)

    url_summary = f"{BASE_URL}/esummary.fcgi"
    params_summary = build_params({"db": "pubmed", "id": pmid})
    try:
        resp_summary = requests.get(url_summary, params=params_summary, timeout=30)
        resp_summary.raise_for_status()
        summary_data = resp_summary.json()
    except requests.RequestException:
        summary_data = {}
    time.sleep(SLEEP_TIME)

    result = summary_data.get("result", {})
    doc = result.get(pmid, {})
    abstract = extract_abstract_from_xml(xml_content)

    return {
        "pmid": pmid, "status": "ok",
        "title": doc.get("title", ""),
        "authors": [a.get("name", "") for a in doc.get("authors", [])],
        "journal": doc.get("fulljournalname", ""),
        "pub_date": doc.get("pubdate", ""),
        "doi": next((uid.get("value", "") for uid in doc.get("articleids", [])
                     if uid.get("idtype") == "doi"), ""),
        "pmc_id": next((uid.get("value", "") for uid in doc.get("articleids", [])
                        if uid.get("idtype") == "pmc"), ""),
        "abstract": abstract,
    }


def extract_abstract_from_xml(xml_content: str) -> str:
    import re
    abstract_texts = re.findall(r'<AbstractText[^>]*>(.*?)</AbstractText>', xml_content, re.DOTALL)
    if not abstract_texts:
        return "Abstract non disponibile."
    abstract_labels = re.findall(r'<AbstractText\s+Label="([^"]+)"', xml_content)
    if abstract_labels and len(abstract_labels) == len(abstract_texts):
        parts = []
        for label, text in zip(abstract_labels, abstract_texts):
            clean_text = re.sub(r'<[^>]+>', '', text).strip()
            parts.append(f"{label}: {clean_text}")
        return "\n\n".join(parts)
    else:
        return re.sub(r'<[^>]+>', '', abstract_texts[0]).strip()


def fetch_fulltext_pmc(pmc_id: str, pmid: str) -> tuple:
    if not pmc_id:
        return "", "not_in_pmc"
    pmc_clean = pmc_id.replace("PMC", "").strip()
    url = f"{BASE_URL}/efetch.fcgi"
    params = build_params({"db": "pmc", "id": pmc_clean, "rettype": "full", "retmode": "xml"})
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        if len(response.text) < 500:
            return "", "not_available"
        import re
        text = re.sub(r'<[^>]+>', ' ', response.text)
        text = re.sub(r'\s+', ' ', text).strip()
        time.sleep(SLEEP_TIME)
        return text[:50000], "ok"
    except requests.RequestException as e:
        return "", f"error: {str(e)}"


def fetch_fulltext_unpaywall(doi: str, pmid: str) -> tuple:
    if not doi:
        return "", "no_doi", ""
    if not UNPAYWALL_EMAIL or UNPAYWALL_EMAIL == "tuaemail@esempio.com":
        return "", "no_email_configured", ""
    unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
    try:
        resp = requests.get(unpaywall_url, timeout=20)
        if resp.status_code == 404:
            return "", "not_found_unpaywall", ""
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return "", f"unpaywall_error: {str(e)}", ""
    time.sleep(0.5)

    if not data.get("is_oa", False):
        return "", "not_oa", ""
    best_oa_location = data.get("best_oa_location", {})
    oa_url = best_oa_location.get("url_for_pdf") or best_oa_location.get("url")
    if not oa_url:
        for loc in data.get("oa_locations", []):
            candidate = loc.get("url_for_pdf") or loc.get("url")
            if candidate:
                oa_url = candidate
                break
    if not oa_url:
        return "", "no_url_found", ""

    try:
        headers = {"User-Agent": "Mozilla/5.0 (research bot - tesi magistrale)"}
        resp_paper = requests.get(oa_url, timeout=30, headers=headers, allow_redirects=True)
        resp_paper.raise_for_status()
        content_type = resp_paper.headers.get("content-type", "")
        if "pdf" in content_type.lower():
            try:
                from io import BytesIO
                from pdfminer.high_level import extract_text as pdf_extract
                text = pdf_extract(BytesIO(resp_paper.content))
                return text[:50000], "ok_pdf", oa_url
            except ImportError:
                return f"[PDF da {oa_url} — installa pdfminer.six]", "ok_pdf_raw", oa_url
            except Exception as e:
                return f"[PDF errore estrazione: {e}]", "ok_pdf_error", oa_url
        elif "html" in content_type.lower() or "text" in content_type.lower():
            import re
            text = re.sub(r'<[^>]+>', ' ', resp_paper.text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:50000], "ok_html", oa_url
        else:
            return "", f"unknown_content_type: {content_type}", oa_url
    except requests.RequestException as e:
        return "", f"download_error: {str(e)}", oa_url


def verify_pmid_exists(pmid: str) -> bool:
    url = f"{BASE_URL}/esearch.fcgi"
    params = build_params({"db": "pubmed", "term": pmid + "[uid]", "retmax": 1})
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        count = int(data.get("esearchresult", {}).get("count", 0))
        time.sleep(SLEEP_TIME)
        return count > 0
    except Exception:
        return False


# ============================================================================
# MAIN
# ============================================================================

def main():
    ncbi_status = "[green]Configurata[/]" if NCBI_API_KEY else "[yellow]Non configurata[/]"
    unpaywall_configured = UNPAYWALL_EMAIL and UNPAYWALL_EMAIL != "tuaemail@esempio.com"
    unp_status = f"[green]{UNPAYWALL_EMAIL}[/]" if unpaywall_configured else "[yellow]Non configurata[/]"

    console.print(Panel(
        f"[bold white]Download Paper Benchmark MTB ESTESO[/]\n"
        f"PMID da scaricare: [bold cyan]{len(BENCHMARK_PMIDS)}[/]\n"
        f"Output directory: [green]{OUTPUT_DIR}[/]\n"
        f"API Key NCBI: {ncbi_status}\n"
        f"Unpaywall email: {unp_status}",
        title="[bold cyan]NCBI PubMed Downloader — Benchmark 30 casi[/]",
        border_style="cyan"
    ))

    summary_rows = []
    not_available = []

    for case_id, info in BENCHMARK_PMIDS.items():
        pmid = info["pmid"]
        console.print(f"\n[bold cyan]>> {case_id}[/] -- {info['case']} (PMID: {pmid})")

        if not verify_pmid_exists(pmid):
            console.print(f"  [bold red]NOK PMID {pmid} non trovato[/]")
            not_available.append(f"{case_id} | PMID {pmid} | Non trovato")
            continue

        console.print(f"  [yellow]Scaricando metadati e abstract...[/]")
        metadata = fetch_abstract_and_metadata(pmid)
        if metadata.get("status") == "fetch_failed":
            console.print(f"  [red]NOK Errore: {metadata.get('error')}[/]")
            not_available.append(f"{case_id} | PMID {pmid} | Errore fetch")
            continue

        metadata.update({
            "case_id": case_id, "benchmark_gene": info["gene"],
            "benchmark_variant": info["variant"], "benchmark_tumor": info["tumor"],
            "benchmark_expected_drug": info["expected_drug"],
            "benchmark_escat": info["escat"], "benchmark_category": info["category"],
        })

        pmc_id = metadata.get("pmc_id", "")
        doi = metadata.get("doi", "")
        fulltext_status = "not_in_pmc"
        fulltext_source = ""
        fulltext = ""

        if pmc_id:
            console.print(f"  [yellow]PMC ID {pmc_id}, provo PMC...[/]")
            fulltext, fulltext_status = fetch_fulltext_pmc(pmc_id, pmid)
            if fulltext_status == "ok":
                fulltext_source = "PMC"
                console.print(f"  [green]OK Full text da PMC ({len(fulltext):,} char)[/]")
            else:
                console.print(f"  [yellow]>> PMC fallito, provo Unpaywall...[/]")

        if not fulltext and doi:
            console.print(f"  [yellow]Unpaywall per DOI {doi}...[/]")
            fulltext, fulltext_status, oa_url = fetch_fulltext_unpaywall(doi, pmid)
            if fulltext_status.startswith("ok"):
                fulltext_source = f"Unpaywall ({oa_url})"
                console.print(f"  [green]OK Full text da Unpaywall ({fulltext_status})[/]")
                metadata["unpaywall_oa_url"] = oa_url
            elif fulltext_status == "not_oa":
                console.print(f"  [red]PAYWALL confermato[/]")
                not_available.append(f"{case_id} | PMID {pmid} | Paywall (DOI: {doi})")
            else:
                not_available.append(f"{case_id} | PMID {pmid} | Unpaywall: {fulltext_status}")
        elif not fulltext and not doi:
            not_available.append(f"{case_id} | PMID {pmid} | Nessun DOI")

        if fulltext and fulltext_status.startswith("ok"):
            fulltext_path = OUTPUT_DIR / f"fulltext_{pmid}.txt"
            fulltext_path.write_text(
                f"Fonte: {fulltext_source}\nPMID: {pmid}\nDOI: {doi}\n{'=' * 60}\n\n" + fulltext,
                encoding="utf-8")
            console.print(f"  [green]OK Salvato fulltext_{pmid}.txt[/]")

        metadata["fulltext_status"] = fulltext_status
        metadata["fulltext_available"] = fulltext_status.startswith("ok")
        metadata["fulltext_source"] = fulltext_source

        meta_path = OUTPUT_DIR / f"metadata_{pmid}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        console.print(f"  [green]OK Metadata salvato[/]")
        if metadata.get("title"):
            console.print(f"  [dim]{metadata['title'][:75]}[/]")

        summary_rows.append({
            "case_id": case_id, "pmid": pmid, "gene": info["gene"],
            "variant": info["variant"], "tumor": info["tumor"],
            "expected_drug": info["expected_drug"], "escat": info["escat"],
            "category": info["category"], "title": metadata.get("title", "")[:80],
            "journal": metadata.get("journal", ""), "pub_date": metadata.get("pub_date", ""),
            "doi": doi, "pmc_id": pmc_id,
            "abstract_available": bool(metadata.get("abstract") and
                                       metadata["abstract"] != "Abstract non disponibile."),
            "fulltext_available": fulltext_status.startswith("ok"),
            "fulltext_source": fulltext_source,
        })

    # SALVA CSV
    if summary_rows:
        csv_path = OUTPUT_DIR.parent / "benchmark_papers_summary_30.csv"
        fieldnames = list(summary_rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summary_rows)

        table = Table(title="[bold cyan]Riepilogo Benchmark 30 casi[/]",
                      border_style="cyan", box=box.ROUNDED, show_lines=False)
        table.add_column("Case", style="bold cyan")
        table.add_column("Gene", style="bold green")
        table.add_column("Variant")
        table.add_column("Categoria", style="dim")
        table.add_column("Abs", justify="center")
        table.add_column("Full", justify="center")
        for row in summary_rows:
            a = "[green]OK[/]" if row["abstract_available"] else "[red]NO[/]"
            f = "[green]OK[/]" if row["fulltext_available"] else "[red]pw[/]"
            table.add_row(row["case_id"], row["gene"], row["variant"][:18],
                          row["category"], a, f)
        console.print("\n")
        console.print(table)

        n_abstract = sum(1 for r in summary_rows if r["abstract_available"])
        n_fulltext = sum(1 for r in summary_rows if r["fulltext_available"])
        console.print(Panel(
            f"Paper processati: [bold cyan]{len(summary_rows)}/{len(BENCHMARK_PMIDS)}[/]\n"
            f"Abstract: [bold green]{n_abstract}[/]\n"
            f"Full text: [bold green]{n_fulltext}[/]\n"
            f"Paywall: [bold yellow]{len(BENCHMARK_PMIDS) - n_fulltext}[/]\n\n"
            f"CSV: [green]{csv_path}[/]",
            title="[bold green]Completato[/]", border_style="green"))

    if not_available:
        not_avail_path = OUTPUT_DIR.parent / "benchmark_papers_not_available_30.txt"
        with open(not_avail_path, "w", encoding="utf-8") as f:
            f.write("Paper non disponibili come full text open access\n")
            f.write("=" * 60 + "\n\n")
            for line in not_available:
                f.write(line + "\n")
        console.print(f"\n[yellow]>> {len(not_available)} paper con limitazioni: {not_avail_path}[/]")


if __name__ == "__main__":
    main()