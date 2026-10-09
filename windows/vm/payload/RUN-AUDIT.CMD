@echo off
setlocal
echo Desktop Windows installed-system audit
echo The report remains on THIS computer:
echo   C:\ProgramData\DesktopWindows\Audit\report.txt
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-audit.ps1"
set "RESULT=%errorlevel%"
if exist "%ProgramData%\DesktopWindows\Audit\report.txt" (
  start "" notepad.exe "%ProgramData%\DesktopWindows\Audit\report.txt"
)
echo.
echo Audit process exit code: %RESULT%
echo Historical audit runs: %ProgramData%\DesktopWindows\Audit\runs
pause
exit /b %RESULT%
