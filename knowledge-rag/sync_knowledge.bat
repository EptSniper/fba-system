@echo off
REM ============================================================
REM  Feed new video transcripts into the brain + dashboard.
REM  Double-click this whenever you drop new videos into your
REM  Downloads "Amazon Video Transcripts" folder.
REM  It copies them in, rebuilds the notes, and embeds the new
REM  ones into Supabase (free, local model, resumable).
REM ============================================================
cd /d "%~dp0"
where python >nul 2>&1 && (set PY=python) || (set PY=py)

echo === 1/3  Pulling in any new transcripts ===
xcopy "C:\Users\ahmet\Downloads\Amazon Video Transcripts\*.txt" "..\learning-hub\transcripts\" /D /Y /Q
echo.

echo === 2/3  Rebuilding the searchable notes ===
%PY% ingest.py
echo.

echo === 3/3  Embedding the new notes into your database ===
%PY% -m pip install fastembed requests >nul 2>&1
set "SUPABASE_URL=https://cakbzcvtqhdtxfjuxstd.supabase.co"
set "EMBED_PROVIDER=local"
set /p SUPABASE_SERVICE_KEY=Paste your Supabase service_role key, then Enter:
%PY% upload_to_supabase.py
echo.

echo ============================================================
echo  Done. Open the dashboard and hit the sync icon (top-right)
echo  to see the new totals.
echo ============================================================
pause
