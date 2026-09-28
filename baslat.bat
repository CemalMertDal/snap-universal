@echo off
rem Dev launcher: creates .venv on first run, reinstalls packages when requirements.txt changes.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ilk kurulum: sanal ortam olusturuluyor...
  python -m venv .venv
  if errorlevel 1 (echo Python bulunamadi. python.org'dan kur. & pause & exit /b 1)
)
fc /b requirements.txt ".venv\.req-stamp" >nul 2>&1
if errorlevel 1 (
  echo Paketler yukleniyor, biraz surebilir...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (echo Paket kurulumu basarisiz. & pause & exit /b 1)
  copy /y requirements.txt ".venv\.req-stamp" >nul
)
start "" ".venv\Scripts\pythonw.exe" -m snap
