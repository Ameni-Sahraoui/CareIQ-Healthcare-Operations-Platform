@echo off
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run setup_windows.ps1 first.
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m streamlit run app.py
