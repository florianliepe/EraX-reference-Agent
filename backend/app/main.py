from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from pathlib import Path
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import settings
from .parsers import SUPPORTED
from .service import MODEL_VERSIONS, process_job, update_result
from .store import store


app = FastAPI(title="EraX Reference Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
attempts: dict[str, deque[float]] = defaultdict(deque)


def auth(request: Request, x_pilot_password: str = Header(default="")) -> None:
    key = request.client.host if request.client else "unknown"
    now = time.time(); window = attempts[key]
    while window and window[0] < now - 60: window.popleft()
    if len(window) >= 60: raise HTTPException(429, "Rate limit exceeded; retry in one minute")
    window.append(now)
    expected = hashlib.sha256(settings.pilot_password.encode()).digest()
    supplied = hashlib.sha256(x_pilot_password.encode()).digest()
    if expected != supplied: raise HTTPException(401, "Invalid pilot password")


class Edits(BaseModel):
    values: dict[str, str]
    kpis: list[dict[str, str]] | None = None


@app.get("/health")
def health(): return {"status": "ok"}


@app.get("/auth/check", dependencies=[Depends(auth)])
def auth_check(): return {"authenticated": True}


@app.post("/upload", dependencies=[Depends(auth)])
async def upload(files: list[UploadFile] = File(...)):
    if not files: raise HTTPException(400, "At least one file is required")
    session_id = store.new_session(); records = []
    for item in files:
        suffix = Path(item.filename or "").suffix.lower()
        if suffix not in SUPPORTED: raise HTTPException(415, f"Unsupported file type: {suffix or 'none'}")
        content = await item.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(content) > settings.max_upload_mb * 1024 * 1024: raise HTTPException(413, f"{item.filename} exceeds {settings.max_upload_mb} MB")
        records.append(store.add_file(session_id, item.filename or "upload", content))
    return {"session_id": session_id, "files": records}


@app.post("/generate/{session_id}", dependencies=[Depends(auth)])
def start_generation(session_id: str, background: BackgroundTasks):
    if session_id not in store.sessions: raise HTTPException(404, "Upload session not found")
    job = store.new_job(session_id); background.add_task(process_job, job.id)
    return {"job_id": job.id}


@app.get("/status/{job_id}", dependencies=[Depends(auth)])
def status(job_id: str):
    job = store.jobs.get(job_id)
    if not job: raise HTTPException(404, "Job not found")
    return {"job_id": job.id, "status": job.status, "progress": job.progress, "error": job.error, "files": store.sessions[job.session_id]}


@app.get("/result/{job_id}", dependencies=[Depends(auth)])
def result(job_id: str):
    job = store.jobs.get(job_id)
    if not job or not job.result: raise HTTPException(404, "Result not ready")
    return {"job_id": job.id, "classification": job.classification, "fields": job.result}


@app.patch("/result/{job_id}", dependencies=[Depends(auth)])
def patch_result(job_id: str, edits: Edits):
    if job_id not in store.jobs: raise HTTPException(404, "Job not found")
    return {"fields": update_result(job_id, edits.values, edits.kpis)}


@app.get("/download/{job_id}", dependencies=[Depends(auth)])
def download(job_id: str):
    job = store.jobs.get(job_id)
    if not job or not job.output_path or not Path(job.output_path).exists(): raise HTTPException(404, "PowerPoint not ready")
    return FileResponse(job.output_path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", filename="Eraneos-client-reference.pptx")


@app.get("/audit/{job_id}", dependencies=[Depends(auth)])
def audit(job_id: str):
    job = store.jobs.get(job_id)
    if not job or not job.result: raise HTTPException(404, "Audit not ready")
    return {
        "job_id": job.id, "session_id": job.session_id, "classification": job.classification,
        "created_at": job.created_at, "completed_at": job.completed_at,
        "generator": MODEL_VERSIONS.get(job.id, "unknown"),
        "sections": {name: {"confidence": getattr(job.result, name).confidence, "edited": getattr(job.result, name).edited, "evidence": getattr(job.result, name).evidence} for name in ("title", "client", "date", "industry", "service", "situation_challenge", "approach", "outcome_impact")},
        "kpis": job.result.kpis,
    }
