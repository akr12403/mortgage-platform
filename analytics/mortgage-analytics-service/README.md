# Mortgage Analytics Service

Python 3.11 service providing portfolio analytics, data normalization, S3 document storage integration, and REST endpoints.

## Local Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8000