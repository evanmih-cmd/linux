# AMD RAID boot-critical path for WinOps — reconciled with current runbook

**Status:** instructions for a *future/repeated* WinOps deployment on ASUS TUF A14 FA401EA. This document complements the **single authoritative** [deployment README](README.md), rather than replacing the partitioning, split-WIM, WinRE backup, unattended XML or acceptance procedures there. Supersedes the incompatible draft procedure in [PR #10](https://github.com/evanmih-cmd/linux/pull/10). **Do not reinstall or repartition an already working SECUREWS to follow this document.**

## Non-negotiable facts and gates

AMD RAID boot is a **three-image** problem. The three images are independent:

| Image/environment | How to prepare it | When needed |
| --- | --- | --- |
| Windows Setup **WinPE**, inside the USB \`sources\boot.wim\` | Integrate the **official signed ASUS x64 AMD RAID driver** into the actual Windows Setup image index *before booting USB*. Preserve the original WIM off the USB and verify the replaced file by hash. | Only if the existing prepared WinPE does not already expose the **virtual WinOps RAID LUN** |
| **Offline newly deployed WinOps** at \`W:\Windows\` | Stage the same suitable boot-critical drivers via native \`DISM /Image:W:\ /Add-Driver\` *after* \`DISM /Apply-Image\` and *before* initial OS boot. | Every fresh deployment from stock install.swm/WIM/ESD unless the applied image already contains them |
| **Windows RE** \`winre.wim\` | Use the separately prepared, verified, **externally retained** \`U:\Recovery\WinRE\winre.wim\` with AMD RAID support. Copy it to the target's last recovery partition only as directed by README §3. | Every fresh deployment or recovery-partition recreation |

**DO NOT** source WinRE from \`W:\Windows\System32\Recovery\winre.wim\` as the routine reinstal­lation/recovery plan. Windows Setup can move/remove that transient OS copy; wiping C:/Recovery destroys it. WinRE is an independently backed up release artifact with recorded Windows image version, driver identity and SHA-256, retained **outside SSD2/WinOps**; see README §0/§3 and [Microsoft Customize Windows RE](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/customize-windows-re?view=windows-11). If this verified external WinRE image is absent, **STOP before deleting anything**. It must be prepared from a trusted original Windows RE WIM with the required official driver packages using the documented DISM image-servicing procedure; do not silently substitute a clean WIM without RAID drivers.

The original ASUS media path recorded earlier was \`DRIVERS\Raid_ROG_AMD_J_V9.3.3.00267_46073_20261010165456\` containing \`rcbottom\rcbottom.inf\`, \`rcraid\rcraid.inf\`, \`rccfg\rccfg.inf\`. Later observations of WinRE on SECUREWS report **actual driver version 9.3.3.291**. Package-folder name, installed DriverVer and version of a copied image are *not* interchangeable evidence. **Inspect the actual official ASUS driver package, its INF DriverVer, digital signatures, amd64 architecture and hardware IDs for this RAID controller** before using it; do not assume that a historical folder name is the right current source. The commands below are an example for the recorded USB folder **only after it has been positively verified**. If the controller ID/boot requirements do not match, STOP. Do not use unsigned drivers, force signature bypass, hand-write service StartType, or touch SSD1.

## 1. Windows Setup boot.wim — prepare from WinHome, before booting USB

If the already-prepared USB has booted on the ASUS and WinPE **actually enumerates the independent WinOps RAID LUN**, **do not modify \`boot.wim\` again**; proceed to §2. \`drvload rcbottom.inf\` reporting *driver requires reboot* is **not** evidence that WinPE can see the LUN.

If preparation is required, work on the existing Windows 11 installation in an **elevated CMD**, on a **new empty temporary folder**, never on SSD2. First find the actual USB drive letter (below \`U:\` is an example) and verify the package using vendor provenance/INF, not its directory name alone:

~~~cmd
set "MEDIA=U:"
set "RAID=%MEDIA%\DRIVERS\Raid_ROG_AMD_J_V9.3.3.00267_46073_20261010165456"
dir "%RAID%\rcbottom\rcbottom.inf"
dir "%RAID%\rcraid\rcraid.inf"
dir "%RAID%\rccfg\rccfg.inf"
dism /Get-WimInfo /WimFile:"%MEDIA%\sources\boot.wim"
~~~

The **Windows Setup** index is commonly index 2, **but must be confirmed from actual WIM info**. On a pristine USB, make *two distinct copies* from the **original** Microsoft's \`boot.wim\`: immutable \`boot.original.wim\` and working \`boot.wim\`. If the USB is **already modified**, **do not** relabel its current \`boot.wim\` as the pristine original. Recover original WIM from the already preserved original or the official Microsoft image when needed.

~~~cmd
md C:\WinOps-WinPE
md C:\WinOps-WinPE\mount
copy /v "%MEDIA%\sources\boot.wim" C:\WinOps-WinPE\boot.original.wim
copy /v C:\WinOps-WinPE\boot.original.wim C:\WinOps-WinPE\boot.wim
certutil -hashfile C:\WinOps-WinPE\boot.original.wim SHA256
dism /Mount-Image /ImageFile:C:\WinOps-WinPE\boot.wim /Index:2 /MountDir:C:\WinOps-WinPE\mount
dism /Image:C:\WinOps-WinPE\mount /Add-Driver /Driver:"%RAID%\rcbottom\rcbottom.inf"
dism /Image:C:\WinOps-WinPE\mount /Add-Driver /Driver:"%RAID%\rcraid\rcraid.inf"
dism /Image:C:\WinOps-WinPE\mount /Add-Driver /Driver:"%RAID%\rccfg\rccfg.inf"
dism /Image:C:\WinOps-WinPE\mount /Get-Drivers /Format:List
~~~

**Do not mechanically execute this entire block** unless the WIM is an **unchanged original**, the mount directory is empty and \`/Index:2\` is the confirmed Setup index. Check each DISM result, and check that all three original INF filenames are present in \`/Get-Drivers\`. \`/Get-DriverInfo /Driver:<path-to-source.inf>\` separately examines a driver's properties, and alone does **not** show that it was staged in the mounted image:

~~~cmd
dism /Image:C:\WinOps-WinPE\mount /Get-DriverInfo /Driver:"%RAID%\rcbottom\rcbottom.inf"
dism /Image:C:\WinOps-WinPE\mount /Get-DriverInfo /Driver:"%RAID%\rcraid\rcraid.inf"
dism /Image:C:\WinOps-WinPE\mount /Get-DriverInfo /Driver:"%RAID%\rccfg\rccfg.inf"
~~~

\`rcbottom\` and \`rcraid\` must be a compatible **boot storage** path (check \`Boot Critical\`, INF configuration and hardware identity); \`rccfg\` is the configuration component and is not required to report \`Boot Critical: Yes\`. If any action fails, **STOP** and, for a still-mounted working copy, roll it back via \`dism /Unmount-Image /MountDir:C:\WinOps-WinPE\mount /Discard\`. Preserve immutable original. Otherwise commit the modified *working copy* and verify the USB readback:

~~~cmd
dism /Unmount-Image /MountDir:C:\WinOps-WinPE\mount /Commit
certutil -hashfile C:\WinOps-WinPE\boot.wim SHA256
copy /v C:\WinOps-WinPE\boot.wim "%MEDIA%\sources\boot.wim"
certutil -hashfile "%MEDIA%\sources\boot.wim" SHA256
~~~

The two working hashes must agree. This is the **only deliberate modification of a Microsoft image on USB**; leave \`install.swm/install2.swm\` unchanged. Do not recreate the whole USB merely for this driver.

**Read-only hardware gate before manual DiskPart partitioning:** boot the USB on ASUS, Shift+F10:

~~~cmd
diskpart
rescan
list disk
exit
~~~

Use \`detail disk\` on identified entries as necessary. Confirm the **virtual RAID LUN** of the configured WinOps logical size, not the raw physical Lexar NVMe (~3.7 TB, previously shown \`Unknown/MBR\`). Until the virtual LUN is unambiguously identified **and SSD1 is Offline**, do **not** \`clean\`, \`convert gpt\` or format any disk. Protect RAID metadata.

## 2. New OS: add RAID to offline WinOps immediately after Apply-Image

Follow README §1–§3 and identify the target **by actual disk identity**, not the historical VM disk number. Apply Windows 11 Pro (not N) from the **actual USB split-WIM**, using the correct \`install.swm\` and \`/SWMFile\` and the index shown by \`/Get-ImageInfo\` (alternatives for WIM/ESD are already in README).

**Insertion point:** exactly after a successful \`dism /Apply-Image\` to the verified target \`W:\`, **before \`bcdboot\` and first reboot**. \`U:\` below is a drive-letter example for the *same positively verified ASUS driver source*; Windows/USB letters must be rediscovered in the current WinPE session:

~~~cmd
dir W:\Windows\System32\config\SYSTEM
set "RAID=U:\DRIVERS\Raid_ROG_AMD_J_V9.3.3.00267_46073_20261010165456"
dir "%RAID%\rcbottom\rcbottom.inf"
dir "%RAID%\rcraid\rcraid.inf"
dir "%RAID%\rccfg\rccfg.inf"
dism /Image:W:\ /Add-Driver /Driver:"%RAID%\rcbottom\rcbottom.inf"
dism /Image:W:\ /Add-Driver /Driver:"%RAID%\rcraid\rcraid.inf"
dism /Image:W:\ /Add-Driver /Driver:"%RAID%\rccfg\rccfg.inf"
dism /Image:W:\ /Get-Drivers /Format:List
~~~

Confirm three packages actually staged by \`Original File Name\` / \`Published Name\`. Check that needed storage drivers are boot-critical and match target hardware; \`rccfg\` may not be:

~~~cmd
dism /Image:W:\ /Get-DriverInfo /Driver:"%RAID%\rcbottom\rcbottom.inf"
dism /Image:W:\ /Get-DriverInfo /Driver:"%RAID%\rcraid\rcraid.inf"
dism /Image:W:\ /Get-DriverInfo /Driver:"%RAID%\rccfg\rccfg.inf"
~~~

If \`rcbottom\`/\`rcraid\` are incompatible or fail the expected boot-critical checks, **STOP** rather than changing registry service StartType. DISM \`/Get-Drivers\` confirms **staging**, \`/Get-DriverInfo\` confirms **package properties**, and **only a real OS boot** demonstrates functional AMD RAID startup. As \`W:\Windows\` is a deployed offline OS and not a mounted WIM, \`/Unmount-Image /Commit\` is **not** required.

Then return to README §3: target-local \`bcdboot W:\Windows /s S: /f UEFI\`, *externally preserved* WinRE WIM copy to R:, \`reagentc /setreimage\`, copy the one canonical XML and run \`AUDIT.CMD\` before first reboot. **Never rebuild WinRE from the volatile newly installed \`W:\Windows\System32\Recovery\winre.wim\` as a substitute for the verified external recovery image.** The WinRE backup already recorded in the main runbook is the authority, not the older PR #10's copy command.

## 3. Read-only acceptance and boundaries

- Before first reboot: virtual WinOps LUN confirmed, protected SSD1 Offline, offline W: contains the three verified packages, ESP/BCD and WinRE on target, backup WinRE has known hash and vendor drivers; invoke WinPE \`AUDIT.CMD\` exactly as shown in the main runbook. \`FAIL=0\` for checks available in WinPE is necessary, not sufficient.
- Boot the target **physical/RAID LUN** through ASUS firmware's Boot Menu. Read-only check after OS boot: device manager sees AMD RAID controller/bottom/config; \`reagentc /info\` points to the target recovery partition. Then actually boot WinRE and verify it can access the RAID LUN; separately verify WinHome boots on SSD1.
- The prior physical ASUS journal [#9](https://github.com/evanmih-cmd/linux/issues/9) already records that WinOps is installed and that WinRE was **Enabled** by 2026-10-11. **Do not reinterpret this supplement as authorizing a new installation, rewrite of a live WinRE or modification of the existing ASUS.** Any future real recovery/installation observation is separate from this static guide.

## Microsoft and vendor sources

- [AMD RAID Quick Start Guide for Windows](https://docs.amd.com/api/khub/documents/Zy_ez138iRvYDQQqWYA0ug/content): driver ordering and RAID metadata protection.
- [Microsoft: Add and remove drivers from an offline Windows image](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/add-and-remove-drivers-to-an-offline-windows-image?view=windows-11).
- [Microsoft: DISM driver inventory](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/take-inventory-of-an-image-or-component-using-dism).
- [Microsoft: Customize Windows RE](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/customize-windows-re?view=windows-11).
