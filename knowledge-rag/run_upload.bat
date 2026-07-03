@echo off
REM Double-click this to fill your Supabase knowledge database (free, via Gemini).
REM It asks for 2 keys at runtime and stores nothing in this file.
cd /d "%~dp0"
where python >nul 2>&1 && (set PY=python) || (set PY=py)
echo Installing dependency (one-time)...
%PY% -m pip install requests >nul 2>&1
echo.
echo This embeds your 1,234 knowledge chunks and uploads them to Supabase.
echo It is FREE on Gemini's tier. You'll paste 2 keys:
echo.
echo   - Supabase service_role key:  https://supabase.com/dashboard/project/cakbzcvtqhdtxfjuxstd/settings/api
echo   - Gemini API key:             https://aistudio.google.com  (Get API key)
echo.
set /p SUPABASE_SERVICE_KEY=1^) Paste Supabase service_role key, then Enter:
set /p GEMINI_API_KEY=2^) Paste Gemini API key, then Enter:
set SUPABASE_URL=https://cakbzcvtqhdtxfjuxstd.supabase.co
echo.
echo Working... (you'll see "uploaded chunks 100/1234", etc.)
echo.
%PY% upload_to_supabase.py
echo.
echo ============================================================
echo Done. Copy everything above and paste it to Claude to verify.
echo ============================================================
pause
