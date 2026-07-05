@echo off
REM ============================================================
REM  Start the warm knowledge server (THIS_WEEK.md Prompt W1).
REM  Loads the BAAI/bge-base-en-v1.5 embedding model ONCE and
REM  keeps it warm — Ask and the control-center's knowledge
REM  search both go faster automatically whenever this is
REM  running (they fall back to the old cold-start path
REM  honestly if it's not). Loopback-only (127.0.0.1) — nothing
REM  outside this machine can ever reach it.
REM
REM  Double-click to run in the foreground (close the window to
REM  stop it), or register it with Task Scheduler to start
REM  automatically at login — see the "Warm knowledge server"
REM  section in README.md for that command.
REM ============================================================
cd /d "%~dp0"
where python >nul 2>&1 && (set PY=python) || (set PY=py)
echo Starting the warm knowledge server on 127.0.0.1:%KNOWLEDGE_SERVER_PORT%...
if "%KNOWLEDGE_SERVER_PORT%"=="" echo (using default port 8787)
%PY% server.py
