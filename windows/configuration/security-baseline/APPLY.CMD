@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem WinOps static Microsoft Security Baseline 26H2 v2: native LGPO, no UEFI-lock.
set "ROOT=%~dp0"
set "LGPO=%ROOT%Tools\LGPO.exe"
if not exist "%LGPO%" (
  echo FAIL: official Microsoft LGPO.exe is missing from Tools.
  exit /b 2
)
if not exist "%ROOT%WinOps-26H2v2.lgpo.txt" exit /b 3
if not exist "%ROOT%WinOps-26H2v2-Computer.inf" exit /b 3
if not exist "%ROOT%WinOps-26H2v2-audit.csv" exit /b 3
whoami /groups | findstr /i /c:"S-1-16-12288" >nul
if errorlevel 1 (
  echo FAIL: elevated administrative context required after Windows Hello setup.
  exit /b 4
)
"%LGPO%" /e mitigation /e audit /e zone /e DGVBS
if errorlevel 1 goto fail
"%LGPO%" /t "%ROOT%WinOps-26H2v2.lgpo.txt"
if errorlevel 1 goto fail
"%LGPO%" /s "%ROOT%WinOps-26H2v2-Computer.inf"
if errorlevel 1 goto fail
"%LGPO%" /a "%ROOT%WinOps-26H2v2-audit.csv"
if errorlevel 1 goto fail
gpupdate /target:computer /force
if errorlevel 1 goto fail
echo BASELINE=PASS
exit /b 0
:fail
echo BASELINE=FAIL
exit /b 1
