# Deployment

## Local Windows deployment

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

## Local macOS/Linux deployment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m streamlit run app.py
```

## Docker

```bash
docker compose up --build
```

## Environment variables

See `.env.example`. The app reads `CAREIQ_DB_PATH` through the configuration package. Streamlit deployments can also define `CAREIQ_DB_PATH` in secrets.

## Online hosting

Deploy the repository to a Python/Streamlit hosting service or a container platform. The packaged demonstration uses a local SQLite file. A production-scale implementation should use controlled persistent storage, secrets management, authentication, encryption, audit logging and a managed relational database.

## Production boundary

The included deployment files demonstrate application engineering only. They do not make CareIQ compliant for handling real health information. A real deployment requires legal, privacy, security, clinical-governance and operational review.
