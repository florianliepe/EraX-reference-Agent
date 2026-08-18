# Architecture

```mermaid
flowchart LR
  UI[React static UI] -->|password header + HTTPS| API[FastAPI API]
  API --> STORE[Blob/job storage adapter]
  API --> WORKER[Background job runner]
  WORKER --> PARSE[Parsers + OCR fallback]
  PARSE --> STRUCT[Canonical schema + evidence]
  STRUCT --> GEN[Grounded generation provider]
  GEN --> CHECK[Grounding + length validation]
  CHECK --> PPT[One-slide PPT renderer]
  PPT --> STORE
  API -. optional event .-> N8N[n8n notifications / cleanup]
```

The pilot uses an in-process runner and local storage. Both are narrow seams: replace them with Redis/Container Apps Jobs and Blob/PostgreSQL without moving core business logic. n8n does not own parsing or generation.

