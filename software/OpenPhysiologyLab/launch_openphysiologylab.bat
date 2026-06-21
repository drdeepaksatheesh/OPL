@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    echo Using local virtual environment...
    ".venv\Scripts\python.exe" openphysiolab.py
) else (
    echo Local virtual environment not found.
    echo Using system Python...
    python openphysiolab.py
)

pause