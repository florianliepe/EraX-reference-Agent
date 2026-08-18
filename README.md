# EraX Reference Agent

Pilot-grade, evidence-grounded generation of a single-slide Eraneos client reference from mixed project files.

## What is included

- React/Vite single-page workflow: Upload → Generate → Review → Download.
- FastAPI backend with mixed-format parsing, classification detection, provenance, confidence flags, editable review fields, audit records, and deterministic one-slide PowerPoint rendering.
- Optional OpenAI adapter behind an environment switch. The default deterministic provider works without external services and never invents missing evidence.
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
| `OPENAI_API_KEY` | Server-only model credential | unset |
| `OPENAI_MODEL` | Model used by the OpenAI adapter | `gpt-5.6-luna` |
| `VITE_API_URL` | Backend URL compiled into the frontend | localhost |

Never put model credentials or the pilot password into `VITE_*` variables.

## API

- `POST /upload`
- `POST /generate/{session_id}`
- `GET /status/{job_id}`
- `GET /result/{job_id}`
- `PATCH /result/{job_id}`
- `GET /download/{job_id}`
- `GET /audit/{job_id}`
- `GET /health`

All pilot endpoints except `/health` use the `X-Pilot-Password` header.

## Validation

```bash
pytest backend/tests
cd frontend && npm run lint && npm run build
```

## Deployment

The frontend workflow in `.github/workflows/ci.yml` builds a GitHub Pages artifact. Configure repository variable `VITE_API_URL` to the public HTTPS backend URL. Deploy the backend container from `infra/backend.Dockerfile` to any container host.

## Known pilot limitations

- Jobs and rate limits are in-process; use PostgreSQL/Redis for multiple replicas.
- OCR requires a Tesseract installation and is best-effort.
- Legacy `.doc`, `.xls`, and `.ppt` files require LibreOffice conversion; OOXML formats work natively.
- The bundled template is a fixed, brand-inspired deterministic layout. Replace `backend/app/ppt.py` layout constants with an approved corporate `.pptx` master before external production use.
- Malware handling validates file signatures and isolates uploads but is not a substitute for a production antivirus/content-disarm service.

## Azure migration

Map local blob storage to Azure Blob Storage, job state to PostgreSQL, background execution to Azure Container Apps Jobs or Functions, password access to Entra ID, and the OpenAI adapter to Azure OpenAI. The parsing, evidence, generation, and PPT modules remain unchanged behind their interfaces.

See [target-mode instructions](docs/TARGET_MODE.md) and [architecture](docs/ARCHITECTURE.md).

