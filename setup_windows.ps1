$ErrorActionPreference = "Stop"
python --version
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Write-Host "CareIQ environment is ready. Run: python -m streamlit run app.py"
