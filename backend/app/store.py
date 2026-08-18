from __future__ import annotations

from pathlib import Path
from threading import Lock
from uuid import uuid4
from .config import settings
from .models import FileRecord, JobRecord


class PilotStore:
    def __init__(self) -> None:
        self.sessions: dict[str, list[FileRecord]] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.lock = Lock()

    def new_session(self) -> str:
        session_id = uuid4().hex
        with self.lock:
            self.sessions[session_id] = []
        (settings.data_dir / session_id).mkdir(parents=True, exist_ok=True)
        return session_id

    def add_file(self, session_id: str, name: str, content: bytes) -> FileRecord:
        file_id = uuid4().hex
        suffix = Path(name).suffix.lower()
        path = settings.data_dir / session_id / f"{file_id}{suffix}"
        path.write_bytes(content)
        record = FileRecord(id=file_id, name=Path(name).name, path=str(path), size=len(content))
        with self.lock:
            self.sessions[session_id].append(record)
        return record

    def new_job(self, session_id: str) -> JobRecord:
        job = JobRecord(id=uuid4().hex, session_id=session_id)
        with self.lock:
            self.jobs[job.id] = job
        return job


store = PilotStore()

