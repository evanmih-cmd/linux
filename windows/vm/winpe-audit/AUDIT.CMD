@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Stock Windows Setup WinPE only: CMD, DiskPart, FSUTIL, BCDEdit,
rem REAgentC (from installed Windows), FIND. No FC (absent in stock WinPE).  NO disk/volume/BCD/registry writes.
rem All scratch files go to WinPE RAM disk X:; stdout may be redirected to USB.
rem Usage: AUDIT.CMD TARGET PROTECTED ESP_LETTER OS_LETTER WINRE_LETTER ANSWER_LETTER
set "PASS=0"
set "FAIL=0"
set "NP=0"
set "TARGET=%~1"
set "PROTECTED=%~2"
set "ESP=%~3"
set "OS=%~4"
set "RE=%~5"
set "ANSWER=%~6"
set "TVALID="
set "PVALID="
for %%N in (0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31) do (
  if "%TARGET%"=="%%N" set "TVALID=1"
  if "%PROTECTED%"=="%%N" set "PVALID=1"
)
if not defined TVALID goto :usage
if not defined PVALID goto :usage
if "%TARGET%"=="%PROTECTED%" goto :usage
for %%V in (ESP OS RE ANSWER) do (
  set "VALUE=!%%V!"
  set "VALID="
  for %%L in (A B C D E F G H I J K L M N O P Q R S T U V W Y Z) do if /I "!VALUE!"=="%%L" set "VALID=1"
  if not defined VALID goto :usage
  for %%Z in ("!VALUE!") do set "%%V=%%~Z"
)
if not exist X:\Windows\System32\wpeutil.exe (
  echo FATAL: This first-phase audit needs official installer WinPE.
  exit /b 2
)
set "BASE=X:\Windows\Temp\winpe-accept"
if not exist "%BASE%" mkdir "%BASE%"
set "QUERY=%BASE%\query.txt"
set "DPLOG=%BASE%\diskpart.txt"
echo WINPE_AUDIT_CMD_V5 target=%TARGET% protected=%PROTECTED% letters=%ESP%:%OS%:%RE%:%ANSWER%:
echo READ_ONLY_INTERNAL_DISKS True
echo SCRATCH_DIRECTORY %BASE%
rem AUDIT THIS BLOCK: exclusively read-only DiskPart commands.
> "%QUERY%" echo list disk
>>"%QUERY%" echo select disk %TARGET%
>>"%QUERY%" echo uniqueid disk
>>"%QUERY%" echo detail disk
>>"%QUERY%" echo list partition
>>"%QUERY%" echo select partition 1
>>"%QUERY%" echo detail partition
>>"%QUERY%" echo select partition 2
>>"%QUERY%" echo detail partition
>>"%QUERY%" echo select partition 3
>>"%QUERY%" echo detail partition
>>"%QUERY%" echo select partition 4
>>"%QUERY%" echo detail partition
rem Protected DiskPart evidence is kept SEPARATE so target type GUID
rem checks cannot accidentally pass using partitions of SSD1.
> "%BASE%\protected-query.txt" echo list disk
>>"%BASE%\protected-query.txt" echo select disk %PROTECTED%
>>"%BASE%\protected-query.txt" echo detail disk
>>"%BASE%\protected-query.txt" echo list partition
>>"%BASE%\protected-query.txt" echo list volume
echo === Disks and partition evidence ===
diskpart /s "%QUERY%" > "%DPLOG%" 2>&1
set "DPEXIT=!errorlevel!"
type "%DPLOG%"
if not "!DPEXIT!"=="0" (
 call :fail diskpart.query "Read-only DiskPart query failed"
 goto :done
)
call :pass diskpart.query "Only LIST/SELECT/DETAIL commands used"
diskpart /s "%BASE%\protected-query.txt" > "%BASE%\protected-diskpart.txt" 2>&1
if errorlevel 1 (
  call :fail protected.diskpart_query "Protected read-only diskpart query failed"
) else (
  call :pass protected.diskpart_query "Protected list/detail query succeeded"
)
type "%BASE%\protected-diskpart.txt"
rem Sanity-check partition rows in DiskPart listing.  Exact raw GPT CRC
rem and GUID-volume-to-physical-disk mapping cannot be proved via CMD.
for %%N in (1 2 3 4) do (
 find /I "Partition %%N " "%DPLOG%" >nul 2>&1
 if errorlevel 1 (call :fail target.partition_%%N "Partition missing") else (call :pass target.partition_%%N "Partition listed")
)
find /I "c12a7328-f81f-11d2-ba4b-00a0c93ec93b" "%DPLOG%" >nul 2>&1
if errorlevel 1 (call :fail target.esp_guid "ESP type missing") else (call :pass target.esp_guid "EFI System GUID present")
find /I "e3c9e316-0b5c-4db8-817d-f92df00215ae" "%DPLOG%" >nul 2>&1
if errorlevel 1 (call :np target.msr_guid "MSR is shown as Reserved, GUID not exposed by this DiskPart output") else (call :pass target.msr_guid "MSR GUID present")
find /I "de94bba4-06d1-4d40-a16a-bfd50179d6ac" "%DPLOG%" >nul 2>&1
if errorlevel 1 (call :fail target.winre_guid "Recovery GUID missing") else (call :pass target.winre_guid "Recovery GUID present")
find /I "8000000000000001" "%DPLOG%" >nul 2>&1
if errorlevel 1 (call :fail target.winre_attrs "Expected GPT Recovery attributes not found") else (call :pass target.winre_attrs "Recovery GPT flags visible")
rem DiskPart's list partition uses human-rounded sizes. Do not claim byte-exact PASS!
call :np target.gpt_crc "Stock CMD/DiskPart does not expose raw primary/backup GPT CRC"
call :np protected.byte_preservation "No pre-install full-disk raw hash available in stock CMD"
rem LIST DISK row is read-only current-state evidence. The status row
rem includes a space immediately after the decimal disk number.
find /I "Disk %PROTECTED% " "%BASE%\protected-diskpart.txt" | find /I "Offline" >nul 2>&1
if errorlevel 1 (
 call :fail protected.offline "Protected disk is not Offline"
) else (
 call :pass protected.offline "Protected physical disk is Offline"
)
rem File system declarations from Windows native FSUTIL. No formatting.
for %%V in (ESP OS RE) do (
 set "DRIVE=!%%V!"
 fsutil fsinfo volumeinfo "!DRIVE!:" > "%BASE%\fs-%%V.txt" 2>&1
 if errorlevel 1 (
   call :np volume.%%V "FSUTIL volumeinfo unavailable"
 ) else (
   if "%%V"=="ESP" (set "FS=FAT32") else (set "FS=NTFS")
   find /I "!FS!" "%BASE%\fs-%%V.txt" >nul
   if errorlevel 1 (call :fail volume.%%V "Wrong filesystem") else (call :pass volume.%%V "!FS!")
 )
)
rem File existence and validation (DRIVE letters were selected by operator).
if exist "%ESP%:\EFI\Microsoft\Boot\BCD" (call :pass esp.bcd "Target ESP has BCD") else (call :fail esp.bcd "BCD missing")
if exist "%ESP%:\EFI\Microsoft\Boot\bootmgfw.efi" (call :pass esp.bootmgfw "Microsoft EFI loader") else (call :fail esp.bootmgfw "EFI loader missing")
if exist "%ESP%:\EFI\Boot\bootx64.efi" (call :pass esp.fallback "UEFI fallback loader") else (call :fail esp.fallback "Fallback loader missing")
bcdedit /store "%ESP%:\EFI\Microsoft\Boot\BCD" /enum all > "%BASE%\bcd.txt" 2>&1
if errorlevel 1 (
 call :fail esp.bcd_semantics "BCDEdit could not parse store"
) else (
 find /I "winload.efi" "%BASE%\bcd.txt" >nul
 if errorlevel 1 (call :fail esp.bcd_semantics "No Windows UEFI loader in BCD") else (call :pass esp.bcd_semantics "BCDEdit validates Windows EFI loader")
)
if exist "%OS%:\Windows\System32\ntoskrnl.exe" (call :pass windows.kernel "Windows NT kernel found") else (call :fail windows.kernel "Kernel missing")
if exist "%OS%:\Windows\System32\winload.efi" (call :pass windows.winload "Windows EFI OS loader found") else (call :fail windows.winload "Windows loader missing")
if exist "%OS%:\Windows\System32\config\SYSTEM" (call :pass windows.registry "Installed SYSTEM hive present") else (call :fail windows.registry "SYSTEM hive missing")
if exist "%RE%:\Recovery\WindowsRE\Winre.wim" (call :pass recovery.winre "Target recovery WIM present") else (call :fail recovery.winre "WinRE WIM missing")
if exist "!OS!:\Windows\System32\Recovery\ReAgent.xml" (
 find /I "\Recovery\WindowsRE" "!OS!:\Windows\System32\Recovery\ReAgent.xml" >nul
 if errorlevel 1 (call :fail recovery.reagent_registration "WinRE registration path not found") else (call :pass recovery.reagent_registration "WinRE path present in ReAgent XML")
) else (
 call :fail recovery.reagent_registration "ReAgent XML missing"
)
"%OS%:\Windows\System32\ReAgentC.exe" /info /target "%OS%:\Windows" > "%BASE%\reagentc.txt" 2>&1
if errorlevel 1 (call :fail recovery.reagentc_query "REAgentC query failed") else (call :pass recovery.reagentc_query "REAgentC queried, Disabled allowed in WinPE")
if not exist "%OS%:\Windows\Panther\Unattend.xml" (
 call :fail windows.canonical_unattend "Panther Unattend.xml missing"
 call :fail windows.answer_identity "Nothing to compare"
) else (
 find /I "specialize" "%OS%:\Windows\Panther\Unattend.xml" >nul 2>&1
 if errorlevel 1 (
   call :fail windows.canonical_unattend "Missing specialize pass"
 ) else (
   find /I "oobeSystem" "%OS%:\Windows\Panther\Unattend.xml" >nul 2>&1
   if errorlevel 1 (
     call :fail windows.canonical_unattend "Missing oobeSystem pass"
   ) else (
     find /I "DiskConfiguration" "%OS%:\Windows\Panther\Unattend.xml" >nul 2>&1
     if not errorlevel 1 (
       call :fail windows.canonical_unattend "Unexpected disk configuration in answer"
     ) else (
       call :pass windows.canonical_unattend "Panther XML has specialize/OOBE and no DiskConfiguration"
     )
   )
 )
 rem Byte-for-byte answer comparison is done in EXTRA.JS using native FSO.
)
rem Four extra proofs without an EXE: WinPE built-in Windows Script Host only.
rem EXTRA.JS is read-only: FSO Unicode byte pairs, MSXML, WMI disks/volumes.
if not exist "%~dp0EXTRA.JS" (
  call :fail script.extra_missing "Missing co-located auditable EXTRA.JS"
) else (
  cscript //nologo "%~dp0EXTRA.JS" "%TARGET%" "%ESP%" "%OS%" "%RE%" "%ANSWER%" "%DPLOG%" > "%BASE%\extra.txt" 2>&1
  if errorlevel 1 (
    type "%BASE%\extra.txt"
    call :fail script.extra_execution "Stock cscript additional audit failed"
  ) else (
    set "COUNT=0"
    for /f "usebackq tokens=1,2,3,*" %%A in ("%BASE%\extra.txt") do (
      if "%%A"=="WSHCHECK" (
        set /a COUNT+=1 >nul
        if "%%C"=="PASS" call :pass %%B "%%D"
        if "%%C"=="FAIL" call :fail %%B "%%D"
        if "%%C"=="NOT_PROVABLE" call :np %%B "%%D"
      )
    )
    if not "!COUNT!"=="4" call :fail script.extra_count "Expected exactly four WSH evidence records"
  )
)
call :np boot.independent "Requires booting Windows Pro from target without SSD1"
call :np boot.secureboot "Requires Secure Boot check in booted Windows"
call :np windows.edition_pro "Requires edition check after first boot"
call :np recovery.winre_enabled "Requires REAgentC Enabled after specialize"
:done
echo SUMMARY PASS=!PASS! FAIL=!FAIL! NOT_PROVABLE=!NP!
if !FAIL! GTR 0 exit /b 1
if !NP! GTR 0 exit /b 4
exit /b 0
:pass
echo CHECK %~1 PASS %~2
set /a PASS+=1 >nul
exit /b 0
:fail
echo CHECK %~1 FAIL %~2
set /a FAIL+=1 >nul
exit /b 0
:np
echo CHECK %~1 NOT_PROVABLE %~2
set /a NP+=1 >nul
exit /b 0
:usage
echo USAGE: AUDIT.CMD TARGET PROTECTED ESP_LETTER OS_LETTER RE_LETTER ANSWER_LETTER
echo EXAMPLE FOR VM ONLY: AUDIT.CMD 1 0 S W R G
exit /b 2
