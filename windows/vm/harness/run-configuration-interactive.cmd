@echo off
set WORK=C:\ProgramData\DesktopWindows
set RCFILE=%WORK%\configuration-task.rc
del /q "%RCFILE%" 2>nul
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%WORK%\apply-configuration.ps1" -ConfigurationPath "%WORK%\workstation.winget"
set RC=%ERRORLEVEL%
> "%RCFILE%" echo %RC%
exit /b %RC%
