# Worker boundary

The pilot executes `backend.app.service.process_job` through FastAPI background tasks. This directory marks the extraction point for a dedicated worker image. For scale-out, invoke the same function from RQ/Celery or an Azure Container Apps Job; do not duplicate parsing or generation logic here.

