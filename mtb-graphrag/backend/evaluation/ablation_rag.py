"""
ablation_rag.py — Condizione 2: RAG Testuale Classico.

Esegue il dump delle fonti del KG (Evidence, Publication, Drug, ClinicalTrial, CompanionDiagnostic)
sotto forma di prosa testuale naturale non strutturata.
Esegue indicizzazione semantica via sentence-transformers (all-MiniLM-L6-v2) e retrieval top-k.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer
from langchain_core.messages import SystemMessage, HumanMessage

from backend.pipeline.llm import llm
from backend.pipeline.helpers import run_cypher
from backend.pipeline.agents.synthesizer import SYNTHESIZER_SYSTEM

# ── Query per il Dump del KG ──────────────────────────────────
CYPHER_EVIDENCE = """
MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)
WHERE toLower(mp.name) CONTAINS toLower($gene)
OPTIONAL MATCH (e)-[:CITED_IN]->(p:Publication)
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
WITH mp, e, collect(DISTINCT p.pmid) AS pmids, collect(DISTINCT p.citation_text) AS citations, collect(DISTINCT d.drug_name) AS drugs
RETURN mp.name AS mp_name,
       e.evidence_level AS level,
       e.significance AS significance,
       e.disease AS disease,
       e.evidence_statement AS statement,
       pmids,
       citations,
       drugs
"""

CYPHER_TRIALS = """
MATCH (ct:ClinicalTrial)-[:ASSOCIATED_GENE]->(g:Gene {hugo_symbol: $gene})
OPTIONAL MATCH (ct)-[:TESTS_DRUG]->(d:Drug)
WITH ct, collect(DISTINCT g.hugo_symbol) AS genes, collect(DISTINCT d.drug_name) AS drugs
RETURN ct.nct_id AS nct_id,
       ct.title AS title,
       ct.phase AS phase,
       ct.status AS status,
       ct.conditions AS conditions,
       ct.keywords AS keywords,
       genes,
       drugs
"""

CYPHER_CDX = """
MATCH (d:Drug)-[:HAS_COMPANION_DIAGNOSTIC]->(cd:CompanionDiagnostic)
RETURN d.drug_name AS drug_name,
       cd.device_name AS device_name,
       cd.platform_type AS platform_type
"""


import torch
# Limita i thread di PyTorch per evitare thread contention su CPU e velocizzare l'elaborazione
torch.set_num_threads(4)

class RAGRetriever:
    _instance = None

    @classmethod
    def get_instance(cls, gene: str = None) -> RAGRetriever:
        if cls._instance is None:
            print(f"  [RAG] Inizializzazione RAGRetriever per {gene}...")
            cls._instance = RAGRetriever()
            cls._instance.build_index(gene)
        return cls._instance

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.chunks: list[str] = []
        self.chunk_embeddings: np.ndarray | None = None

    def build_index(self, gene: str):
        """Scarica i dati del gene specifico da Neo4j e costruisce i chunk."""
        raw_evidence = run_cypher(CYPHER_EVIDENCE, {"gene": gene})
        raw_trials = run_cypher(CYPHER_TRIALS, {"gene": gene})
        raw_cdx = run_cypher(CYPHER_CDX)

        chunks = []
        
        # 1. Chunk evidenze
        for r in raw_evidence:
            mp = r.get("mp_name") or ""
            lvl = r.get("level") or ""
            sig = r.get("significance") or ""
            disease = r.get("disease") or ""
            stmt = r.get("statement") or ""
            pmids = r.get("pmids") or []
            cits = r.get("citations") or []
            drugs = r.get("drugs") or []

            chunk = f"Il profilo molecolare {mp} presenta evidenza di livello {lvl} per la significatività {sig} nel tumore {disease}."
            if stmt:
                chunk += f" Lo studio documenta che: {stmt}"
            if pmids:
                pmids_str = ", ".join(str(p) for p in pmids)
                chunk += f" Questa evidenza è riportata nella pubblicazione PMID {pmids_str}"
                valid_cits = [c for c in cits if c]
                if valid_cits:
                    chunk += f" ({'; '.join(valid_cits)})"
            if drugs:
                drugs_str = ", ".join(drugs)
                chunk += f" ed è associata al farmaco {drugs_str}."
            chunks.append(chunk)

        # 2. Chunk trial clinici
        for r in raw_trials:
            nct = r.get("nct_id") or ""
            title = r.get("title") or ""
            phase = r.get("phase") or ""
            status = r.get("status") or ""
            conds = r.get("conditions") or []
            kws = r.get("keywords") or []
            genes = r.get("genes") or []
            drugs = r.get("drugs") or []

            conds_str = ", ".join(conds) if isinstance(conds, list) else str(conds)
            kws_str = ", ".join(kws) if isinstance(kws, list) else str(kws)

            chunk = f"Il trial clinico {nct} intitolato '{title}' si trova in Fase {phase} con stato di avanzamento {status}."
            if conds_str:
                chunk += f" Tratta le condizioni: {conds_str}."
            if kws_str:
                chunk += f" Parole chiave associate: {kws_str}."
            if genes:
                genes_str = ", ".join(genes)
                chunk += f" È associato al gene {genes_str}."
            if drugs:
                drugs_str = ", ".join(drugs)
                chunk += f" Riguarda la sperimentazione del farmaco {drugs_str}."
            chunks.append(chunk)

        # 3. Chunk companion diagnostic
        # Filtriamo le companion diagnostic solo per i farmaci citati nei chunk precedenti per ridurre il rumore
        referenced_drugs = set()
        for chunk in chunks:
            for r in raw_cdx:
                if r["drug_name"] and r["drug_name"].lower() in chunk.lower():
                    referenced_drugs.add(r["drug_name"])

        for r in raw_cdx:
            if r["drug_name"] in referenced_drugs:
                drug = r.get("drug_name") or ""
                dev = r.get("device_name") or ""
                plat = r.get("platform_type") or ""
                chunk = f"Il farmaco {drug} ha associato come companion diagnostic (CDx) il dispositivo {dev} (piattaforma tecnologica: {plat})."
                chunks.append(chunk)

        self.chunks = chunks
        if chunks:
            print(f"  [RAG] Generati {len(chunks)} chunk testuali per il gene {gene}. Inizio codifica embeddings...")
            self.chunk_embeddings = self.model.encode(chunks, convert_to_numpy=True, show_progress_bar=False)
            print(f"  [RAG] Indicizzazione completata ({len(chunks)} chunk).")
        else:
            print(f"  [RAG] Attenzione: nessun chunk generato per il gene {gene}.")
            self.chunk_embeddings = np.zeros((0, 384))

    def retrieve(self, query: str, top_k: int = 15) -> list[str]:
        """Recupera i top-k chunk più pertinenti usando la somiglianza del coseno."""
        if not self.chunks or self.chunk_embeddings is None or len(self.chunks) == 0:
            return []
        
        query_emb = self.model.encode(query, convert_to_numpy=True)
        
        # Somiglianza del coseno
        dots = np.dot(self.chunk_embeddings, query_emb)
        norms = np.linalg.norm(self.chunk_embeddings, axis=1) * np.linalg.norm(query_emb)
        norms[norms == 0] = 1e-9  # evita divisione per zero
        sims = dots / norms
        
        top_indices = np.argsort(sims)[::-1][:top_k]
        return [self.chunks[idx] for idx in top_indices]


def run_rag_testuale(gene: str, variant: str, tumor_type: str, alteration_type: str, therapy_line: str) -> str:
    """Interroga il vector index semantico, crea il contesto testuale discorsivo e genera il report."""
    retriever = RAGRetriever()
    retriever.build_index(gene)
    
    # Costruisci la query di ricerca
    query = f"{gene} {variant} {tumor_type}"
    print(f"  [RAG RAG_TESTUALE] Eseguo semantic retrieval per: '{query}'...")
    
    retrieved_chunks = retriever.retrieve(query, top_k=15)
    
    # Costruisci il contesto
    ctx = [
        f"=== VARIANTE ===\n"
        f"Gene: {gene} | Variante: {variant} | "
        f"Tipo: {alteration_type} | Tumore: {tumor_type} | "
        f"Linea: {therapy_line}\n"
    ]
    
    if retrieved_chunks:
        ctx.append("=== EVIDENZE DA RECUPERO RAG TESTUALE ===\n" + "\n\n".join(retrieved_chunks))
    else:
        ctx.append("=== EVIDENZE DA RECUPERO RAG TESTUALE ===\nNessun documento o evidenza trovato.")
        
    ctx.append(
        "=== NOTA ===\nUsa esclusivamente le evidenze fornite nel contesto testuale sopra. "
        "Non puoi filtrare i dati in base a significatività o tier tramite database, "
        "affidati unicamente alla corrispondenza semantica testuale. Cita i PMID inline [PMID: XXXXXX]."
    )
    
    # Invocazione dell'LLM con il prompt standard
    response = llm.invoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content="\n\n".join(ctx))
    ])
    
    return response.content
