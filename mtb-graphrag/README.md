# MTB GraphRAG — Research Implementation

Research prototype developed for a Master's thesis on **evidence-grounded AI support for Molecular Tumor Boards**.

The project investigates how curated oncology knowledge, document retrieval, structured representations and language models can be combined while keeping the evidence trail inspectable by a human reviewer.

> This software is a research prototype. It does not provide autonomous therapeutic decisions and is not a substitute for clinical assessment.

## Research goals

The implementation focuses on four engineering properties:

- **structured knowledge** rather than free-text-only reasoning;
- **traceable retrieval** from curated knowledge and documentary sources;
- **explicit verification** before evidence is surfaced;
- **reproducible evaluation** of retrieval, verification and dossier-generation behaviour.

The repository also contains experimental and comparison code produced during the evolution of the thesis. Those utilities are retained for research reproducibility but are not the conceptual focus of the final thesis architecture.

## Application structure

```text
mtb-graphrag/
├── backend/
│   ├── api/
│   ├── comparison/
│   ├── evaluation/
│   ├── pipeline/
│   └── tests/
├── frontend/
└── experiments/
```

The backend contains the retrieval, orchestration, evidence-processing and evaluation components. The frontend provides an interface for inspecting cases, evidence and experimental outputs.

## Evidence-oriented workflow

At a high level, the system:

1. receives a structured molecular/clinical case;
2. retrieves relevant structured knowledge and supporting documents;
3. keeps source information attached to the retrieved evidence;
4. verifies whether candidate statements are supported by the authorized source material;
5. separates supported, uncertain and excluded evidence;
6. produces a structured dossier intended for human review.

Incomplete case information is kept explicit rather than silently reconstructed by the model.

## Running locally

Copy the environment template:

```bash
cp .env.example .env
```

Create a Python environment and install the backend dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/config/requirements.txt
uvicorn backend.api.main:app --reload
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/config/requirements.txt
uvicorn backend.api.main:app --reload
```

Start the frontend in a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

## Configuration

The live application can depend on services such as Neo4j, LLM endpoints and external evidence sources. Secrets must be supplied through environment variables and must never be committed.

Only synthetic or public cases should be used in demonstrations.

## Reproducibility

Evaluation and reproducibility assets are kept under the dedicated evaluation / experiment directories. Generated logs, temporary reports, executed-notebook copies and local databases are intentionally excluded from version control.

## Author

**Paolo Pangallo**  
M.Sc. Computer Engineering — Artificial Intelligence  
University of Calabria
