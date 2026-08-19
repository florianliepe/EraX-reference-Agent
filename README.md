# EraX Reference Agent

Pilot-grade, evidence-grounded generation of a single-slide Eraneos client reference from mixed project files.

## What is included

- React/Vite single-page workflow: Upload → Generate → Review → Human approval → Download.
- FastAPI backend with mixed-format parsing, classification detection, provenance, confidence flags, editable review fields, audit records, and deterministic one-slide PowerPoint rendering.
- Flexible, evidence-backed KPI extraction for project revenue, improvements, savings, FTE effects, and other quantified outcomes; reviewers can edit the extracted name/value pairs before export.
- Optional OpenAI adapter behind an environment switch. The default deterministic provider works without external services and never invents missing evidence.
- Code-controlled seven-stage agent workflow with typed evidence, entity/metric linking, permission-filtered retrieval, claim aggregation, writing, independent verification, and JSON-LD publication.
- Docker Compose, GitHub Actions, GitHub Pages deployment, and an optional n8n notification/cleanup workflow.

## Local run

Requirements: Node 20+, Python 3.11+, and optionally Tesseract for OCR.

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:5173` and enter the password configured in `PILOT_PASSWORD`.

Without Docker:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload

cd frontend
npm ci
npm run dev
```

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `PILOT_PASSWORD` | Shared pilot access secret | `change-me` |
| `DATA_DIR` | Temporary upload/output storage | `./data` |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins | localhost |
| `MAX_UPLOAD_MB` | Per-file size limit | `25` |
| `LLM_PROVIDER` | `deterministic` or `openai` | `deterministic` |
| `OPENAI_API_KEY` | Server-only OpenAI-compatible model credential | unset |
| `OPENAI_BASE_URL` | OpenAI-compatible API base URL; use `https://ai-gateway.eraneos.com` for the Eraneos AI Gateway | unset |
| `OPENAI_MODEL` | Model used by the OpenAI adapter | `gpt-5-mini` |
| `AGENT_REQUEST_TIMEOUT_SECONDS` | Maximum duration of one agent call before grounded fallback | `20` |
| `AGENT_WORKFLOW_TIMEOUT_SECONDS` | Total agentic workflow deadline | `120` |
| `AGENTIC_WORKFLOW_ENABLED` | Enable the typed multi-stage LLM workflow | `false` |
| `CANONICAL_LANGUAGE` | Working/output language; original evidence remains unchanged | `en` |
| `CROSS_PROJECT_REUSE_ENABLED` | Allow retrieval of approved, opt-in claims | `false` |
| `EXTERNAL_WEB_ENRICHMENT_ENABLED` | Reserved safety switch; keep disabled for this pilot | `false` |
| `AZURE_SEARCH_ENDPOINT` | Existing Azure AI Search endpoint | unset |
| `AZURE_SEARCH_API_KEY` | Server-only Azure AI Search credential | unset |
| `AZURE_SEARCH_INDEX_EVIDENCE` | Isolated evidence index | `erax-evidence-v1` |
| `AZURE_SEARCH_INDEX_REFERENCES` | Isolated approved-claim index | `erax-references-v1` |
| `KNOWLEDGE_BLOB_CONTAINER_URL` | Server-only Blob container URL with write SAS for JSON-LD bundles | unset |
| `VITE_API_URL` | Backend URL compiled into the frontend | localhost |

Never put model credentials or the pilot password into `VITE_*` variables.

## API

- `POST /upload`
- `POST /generate/{session_id}`
- `GET /status/{job_id}`
- `GET /result/{job_id}`
- `PATCH /result/{job_id}`
- `POST /approve/{job_id}`
- `GET /download/{job_id}`
- `GET /knowledge/{job_id}`
- `GET /audit/{job_id}`
- `GET /health`

All pilot endpoints except `/health` use the `X-Pilot-Password` header.

The login gate uses `GET /auth/check`. On GitHub Pages, the frontend deliberately refuses to call `localhost`; `VITE_API_URL` must be configured with the deployed backend's public HTTPS URL.

## Validation

```bash
pytest backend/tests
cd frontend && npm run lint && npm run build
```

## Deployment

The frontend workflow in `.github/workflows/ci.yml` builds a GitHub Pages artifact. Configure repository variable `VITE_API_URL` to the public HTTPS backend URL. Deploy the backend container from `infra/backend.Dockerfile` to any container host. For a concrete Azure Container Apps pilot deployment, follow [the backend deployment runbook](docs/DEPLOY_BACKEND.md).

## Known pilot limitations

- Jobs and rate limits are in-process; use PostgreSQL/Redis for multiple replicas.
- OCR requires a Tesseract installation and is best-effort.
- Legacy `.doc`, `.xls`, and `.ppt` files require LibreOffice conversion; OOXML formats work natively.
- PowerPoint output uses the supplied approved `Reference Template.pptx` master and preserves its inherited layout, typography, tables, logo, and image frame. An uploaded PNG/JPG replaces the template image; otherwise the approved template image remains.
- Malware handling validates file signatures and isolates uploads but is not a substitute for a production antivirus/content-disarm service.

## Azure migration

Map local blob storage to Azure Blob Storage, job state to PostgreSQL, background execution to Azure Container Apps Jobs or Functions, password access to Entra ID, and the OpenAI adapter to Azure OpenAI. The parsing, evidence, generation, and PPT modules remain unchanged behind their interfaces.

See [target-mode instructions](docs/TARGET_MODE.md) and [architecture](docs/ARCHITECTURE.md).
The agentic knowledge design, typed contracts, prompts, repair rules, and acceptance gates are in [Agentic Reference Intelligence target mode](docs/TARGET_MODE_AGENTIC_KNOWLEDGE.md).
