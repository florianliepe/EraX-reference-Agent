from io import BytesIO
from docx import Document
from fastapi.testclient import TestClient
from backend.app.config import settings
from backend.app.main import app


def test_full_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    document = Document()
    document.add_paragraph("Client: Contoso Energy")
    document.add_paragraph("Project title: Grid operations redesign")
    document.add_paragraph("Challenge: Fragmented processes delayed incident response.")
    document.add_paragraph("Approach: Redesigned workflows and introduced a governed analytics platform.")
    document.add_paragraph("Outcome: Incident triage time reduced by 25 percent.")
    payload = BytesIO(); document.save(payload)
    client = TestClient(app); headers = {"X-Pilot-Password": settings.pilot_password}
    uploaded = client.post("/upload", files={"files": ("reference.docx", payload.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, headers=headers)
    assert uploaded.status_code == 200
    started = client.post(f"/generate/{uploaded.json()['session_id']}", headers=headers)
    job_id = started.json()["job_id"]
    result = client.get(f"/result/{job_id}", headers=headers)
    assert result.status_code == 200
    assert result.json()["fields"]["client"]["value"] == "Contoso Energy"
    download = client.get(f"/download/{job_id}", headers=headers)
    assert download.status_code == 200

