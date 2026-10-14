# MTB GraphRAG

<div align="center">

![AI Research](https://img.shields.io/badge/AI_Research-8B5CF6?style=for-the-badge)
![GraphRAG](https://img.shields.io/badge/GraphRAG-07A8AA?style=for-the-badge)
![Evidence](https://img.shields.io/badge/Evidence_Verification-1C9E75?style=for-the-badge)
![Human Review](https://img.shields.io/badge/Human--in--the--loop-F09D4E?style=for-the-badge)

**Knowledge graphs · controlled retrieval · provenance · claim verification**

[**Architecture overview →**](docs/ARCHITECTURE_OVERVIEW.md) · [**Research implementation →**](mtb-graphrag/README.md)

</div>

**Evidence-grounded AI architecture for Molecular Tumor Board support**

MTB GraphRAG is a research prototype developed as part of my Master's thesis in Artificial Intelligence at the University of Calabria. The project explores how structured oncology knowledge, document retrieval and language models can be combined while keeping the evidence trail inspectable and reproducible.

> This repository is a research prototype. It does not provide autonomous therapeutic decisions or replace clinical assessment.

## Why this project

Molecular Tumor Boards combine genomic alterations, clinical context, scientific literature and trial information. A useful AI system in this setting needs more than fluent generation: it must preserve where evidence came from, separate supported information from uncertainty and make intermediate decisions auditable.

The project therefore focuses on **evidence-grounded reasoning** rather than unconstrained generation.

## Architecture

The current research pipeline is located in `mtb-graphrag/`.

At a high level, it combines:

- structured case parsing;
- ontology-aware / graph-based retrieval;
- evidence retrieval from curated knowledge and literature;
- deterministic and agentic orchestration strategies;
- explicit provenance tracking;
- evidence validation before presentation;
- a structured dossier designed for human review.

The repository also contains experiments and evaluation assets used during the thesis work.

## Core ideas

### Structured knowledge
Oncology entities and relations are represented explicitly rather than being left only inside free text.

### Evidence retrieval
Relevant knowledge and documents are retrieved for the molecular and clinical context of the case.

### Verifiable orchestration
The project explores both deterministic execution and an agentic architecture with allow-listed tools and an append-only event ledger.

### Claim-level verification
Statements are checked against the available evidence before they are surfaced in the final dossier.

### Human-in-the-loop output
Uncertain, incomplete or unsupported findings are separated from supported evidence instead of being silently promoted to conclusions.

## Repository structure

```text
MTB_GRAPH_RAG/
├── mtb-graphrag/
│   ├── backend/
│   │   ├── api/
│   │   ├── comparison/
│   │   ├── evaluation/
│   │   ├── pipeline/
│   │   └── tests/
│   ├── frontend/
│   └── experiments/
├── DatasetTESI/
├── benchmark/
└── esperimenti_science/
```

The active application and its detailed setup instructions are in:

[`mtb-graphrag/README.md`](mtb-graphrag/README.md)

## Tech stack

- **Python**
- **FastAPI**
- **Neo4j / Cypher**
- **LLMs**
- **Retrieval-Augmented Generation**
- **Knowledge Graphs**
- **Information Retrieval**
- **React / frontend tooling**
- **SQLite-based execution ledger**
- **Automated evaluation and reproducibility scripts**

## Running the application

From `mtb-graphrag/`:

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r backend/config/requirements.txt
uvicorn backend.api.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Then open `http://localhost:5173`.

See the inner README for environment configuration and the distinction between demo and live execution.

## Research focus

This project investigates a broader question: **how can LLM-assisted decision-support systems remain useful when traceability, reproducibility and evidence quality matter as much as answer quality?**

The main contribution is therefore architectural: combining retrieval, structured knowledge, controlled orchestration and verification into a pipeline whose intermediate evidence can be inspected by a human reviewer.

## Author

**Paolo Pangallo**  
M.Sc. candidate in Computer Engineering — Artificial Intelligence  
University of Calabria
