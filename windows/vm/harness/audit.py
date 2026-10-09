import json
import re
from pathlib import Path

from audit_elevated import capture_elevated_facts
from config import Config


WALLET_EXTENSION_IDS = {
    "nkbihfbeogaeaoehlefnkodbefgpgknn",  # MetaMask
    "bfnaelmomeimhlpmgjnjophhpkkoljpa",  # Phantom
    "acmacodkjbdgmoleebolmdjonilkdbch",  # Rabby
    "egjidjbpglichdcondbcbdnbeeppgdph",  # Trust Wallet
    "aflkmfhebedbjioipglgcbcmnbpgliof",  # Backpack
    "klghhnkeealcohjjanjjdaeeggmfmlpl",  # Zerion
}


def check(name, status, actual=None, expected=None):
    return {
        "name": name,
        "status": status,
        "actual": actual,
        "expected": expected,
    }


def evaluate(facts):
    checks = []
    audit_context = facts.get("AuditContext") or {}
    is_elevated = audit_context.get("IsElevated") is True
    checks.append(check("audit-elevated", "PASS" if is_elevated else "FAIL", audit_context, "administrator access confirmed inside Windows"))

    os_info = facts.get("OS") or {}
    caption = os_info.get("Caption") or ""
    checks.append(
        check(
            "windows-11-pro",
            "PASS"
            if "Windows 11 Pro" in caption and "Windows 11 Pro N" not in caption
            else "FAIL",
            caption,
            "Windows 11 Pro (non-N)",
        )
    )
    checks.append(
        check(
            "x64",
            "PASS" if "64" in (os_info.get("OSArchitecture") or "") else "FAIL",
            os_info.get("OSArchitecture"),
            "64-bit",
        )
    )
    locale = facts.get("Locale") or {}
    checks.append(
        check(
            "ui-language-en-us",
            "PASS"
            if (locale.get("UICulture") or "").casefold() == "en-us"
            else "FAIL",
            locale.get("UICulture"),
            "en-US",
        )
    )
    checks.append(
        check(
            "regional-formats-de-de",
            "PASS"
            if (locale.get("Culture") or "").casefold() == "de-de"
            else "FAIL",
            locale.get("Culture"),
            "de-DE",
        )
    )
    checks.append(
        check(
            "home-location-germany",
            "PASS" if locale.get("HomeLocationGeoId") == 94 else "FAIL",
            locale.get("HomeLocationGeoId"),
            94,
        )
    )
    checks.append(
        check(
            "timezone-western-europe",
            "PASS"
            if locale.get("TimeZoneId") == "W. Europe Standard Time"
            else "FAIL",
            locale.get("TimeZoneId"),
            "W. Europe Standard Time",
        )
    )

    languages = locale.get("UserLanguages") or []
    language_tags = {
        (row.get("LanguageTag") or "").casefold()
        for row in languages
        if row.get("LanguageTag")
    }
    input_tips = {
        str(tip).lower()
        for row in languages
        for tip in (row.get("InputMethodTips") or [])
    }
    expected_tips = {"0409:00000409", "0419:00000419"}
    preload = {
        str(item).lower() for item in (locale.get("KeyboardPreload") or [])
    }
    russian_tag_ok = bool(language_tags & {"ru", "ru-ru"})
    allowed_language_tags = {"en-us", "ru", "ru-ru"}
    checks.append(
        check(
            "keyboard-layouts-us-russian-only",
            "PASS"
            if "en-us" in language_tags
            and russian_tag_ok
            and language_tags <= allowed_language_tags
            and input_tips == expected_tips
            and preload == {"00000409", "00000419"}
            else "FAIL",
            {
                "language_tags": sorted(language_tags),
                "input_method_tips": sorted(input_tips),
                "keyboard_preload": sorted(preload),
            },
            {
                "language_tags": ["en-us", "ru-ru"],
                "input_method_tips": sorted(expected_tips),
                "keyboard_preload": ["00000409", "00000419"],
                "forbidden": ["de-de", "00000407"],
            },
        )
    )

    secure_boot = facts.get("SecureBoot")
    secure_boot_status = "PASS" if secure_boot is True else "FAIL"
    checks.append(
        check(
            "secure-boot",
            secure_boot_status,
            secure_boot,
            True,
        )
    )

    tpm = facts.get("TPM") or {}
    tpm_version = tpm.get("SpecVersion") or ""
    tpm_status = (
        "PASS"
        if all(tpm.get(k) is True for k in ("TpmPresent", "TpmReady", "TpmEnabled", "TpmActivated"))
        and "2.0" in tpm_version
        else "FAIL"
    )
    checks.append(
        check(
            "tpm2-visible-ready",
            tpm_status,
            {
                "present": tpm.get("TpmPresent"),
                "ready": tpm.get("TpmReady"),
                "manufacturer": tpm.get("ManufacturerIdTxt"),
                "spec_version": tpm_version,
                "enabled": tpm.get("TpmEnabled"),
                "activated": tpm.get("TpmActivated"),
            },
            {"present": True, "ready": True, "enabled": True, "activated": True, "spec_version": "2.0"},
        )
    )

    defender = facts.get("Defender") or {}
    checks.append(
        check(
            "defender-realtime",
            "PASS"
            if defender.get("AntivirusEnabled") is True
            and defender.get("RealTimeProtectionEnabled") is True
            else "FAIL",
            defender,
            "AntivirusEnabled + RealTimeProtectionEnabled",
        )
    )

    firewall = facts.get("Firewall") or []
    checks.append(
        check(
            "firewall-all-profiles",
            "PASS"
            if firewall
            and all(row.get("Enabled") is True for row in firewall)
            else "FAIL",
            firewall,
            "all profiles enabled",
        )
    )

    disks = facts.get("Disks") or []
    system_disks = [row for row in disks if row.get("IsSystem")]
    checks.append(
        check(
            "system-disk-gpt",
            "PASS"
            if len(system_disks) == 1
            and system_disks[0].get("PartitionStyle") == "GPT"
            else "FAIL",
            system_disks,
            "one GPT system disk",
        )
    )

    # Prove the actual installed GPT layout, not only the unattended template.
    target_number = system_disks[0]["Number"] if len(system_disks) == 1 else None
    target_partitions = [
        row for row in (facts.get("Partitions") or [])
        if row.get("DiskNumber") == target_number
    ]
    # Setup owns the layout. Validate roles and independence, NOT sizes or
    # hardcoded partition ordinal numbers.
    esp_guid = "{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}"
    msr_guid = "{e3c9e316-0b5c-4db8-817d-f92df00215ae}"
    basic_guid = "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}"
    recovery_guid = "{de94bba4-06d1-4d40-a16a-bfd50179d6ac}"
    def matching(guid):
        return [row for row in target_partitions
                if (row.get("GptType") or "").casefold() == guid]
    esp = matching(esp_guid)
    msr = matching(msr_guid)
    windows = [row for row in matching(basic_guid)
               if row.get("DriveLetter") == "C"]
    recovery = matching(recovery_guid)
    roles_ok = (
        len(esp) == len(msr) == len(windows) == len(recovery) == 1
        and all(row.get("Size", 0) > 0 for row in
                (esp[0], msr[0], windows[0], recovery[0]))
        and esp[0].get("PartitionNumber", 0) < msr[0].get("PartitionNumber", 0)
        < windows[0].get("PartitionNumber", 0) < recovery[0].get("PartitionNumber", 0)
    )
    checks.append(check(
        "vm-independent-gpt-partitions",
        "PASS" if roles_ok else "FAIL", target_partitions,
        "target-local ESP, MSR, C: and WinRE after C:; Windows Setup chooses sizes",
    ))

    winre = facts.get("WinRE") or ""
    winre_enabled = bool(re.search(r"Windows RE status:\s*Enabled\b", winre))
    checks.append(check(
        "winre-enabled", "PASS" if winre_enabled else "FAIL", winre,
        "Windows RE status: Enabled on a target-local recovery partition",
    ))

    # Match REAgentC's actual reported location to the recovery partition's
    # measured number, not an assumed partition4 or a fixed 2 GiB size.
    winre_path = (
        f"harddisk{target_number}\\partition{recovery[0]['PartitionNumber']}\\"
        if target_number is not None and len(recovery) == 1 else None
    )
    checks.append(check(
        "winre-on-target-recovery",
        "PASS" if winre_path and winre_path.casefold() in winre.casefold()
        else "FAIL",
        winre,
        "REAgentC WinRE location matches the target disk's recovery partition",
    ))

    chrome = facts.get("Chrome") or {}
    checks.append(
        check(
            "chrome-installed",
            "PASS" if chrome.get("Installed") is True else "FAIL",
            chrome,
            "Google Chrome installed for the sensitive workload",
        )
    )

    edge = facts.get("Edge") or {}
    checks.append(
        check(
            "edge-installed",
            "PASS" if edge.get("Installed") is True else "FAIL",
            edge,
            "Microsoft Edge installed for ordinary browsing",
        )
    )

    pwsh = facts.get("PowerShell7") or {}
    checks.append(
        check(
            "powershell7-installed",
            "PASS" if pwsh.get("Installed") is True else "FAIL",
            pwsh,
            "PowerShell 7 installed via Microsoft MSIX or MSI",
        )
    )

    keepass = facts.get("KeePass") or {}
    checks.append(
        check(
            "keepass2-installed",
            "PASS" if keepass.get("Installed") is True else "FAIL",
            keepass,
            "Official KeePass 2 installed (vendor supports KDBX; opening user DB not audited)",
        )
    )

    ledger = facts.get("LedgerWallet") or {}
    checks.append(
        check(
            "ledger-wallet-desktop",
            "PASS" if ledger.get("Installed") is True else "FAIL",
            ledger,
            "Official Ledger Wallet / Ledger Live desktop installed",
        )
    )

    policy = facts.get("ChromePolicy") or {}
    wallet_entries = facts.get("WalletExtensions") or []
    installed_wallets = {
        item.get("Id"): item for item in wallet_entries
        if isinstance(item, dict) and item.get("Id")
    }
    unknown_extensions = facts.get("OtherChromeExtensionIds") or []
    wallet_checks_ok = (
        set(installed_wallets) == WALLET_EXTENSION_IDS
        and all(
            item.get("Installed") is True
            and item.get("FromWebStore") is True
            and item.get("ActivePermissions") is True
            and item.get("DisableReasons") == []
            and item.get("InstallLocation") == 6
            for item in installed_wallets.values()
        )
    )
    policy_ok = (
        policy.get("ValidJson") is True
        and set(policy.get("Ids") or []) == WALLET_EXTENSION_IDS | {"*"}
        and policy.get("DefaultMode") == "blocked"
    )
    checks.append(
        check(
            "chrome-wallets-verified-six",
            "PASS" if wallet_checks_ok and policy_ok and not unknown_extensions
            else "FAIL",
            {
                "policy_valid": policy_ok,
                "installed": {
                    wallet_id: {
                        "name": item.get("Name"),
                        "versions": item.get("Versions"),
                        "installed": item.get("Installed"),
                        "from_web_store": item.get("FromWebStore"),
                        "disable_reasons": item.get("DisableReasons"),
                    }
                    for wallet_id, item in installed_wallets.items()
                },
                "unexpected_user_extensions": unknown_extensions,
            },
            "Exact six official Chrome Store wallet IDs installed, enabled, "
            "policy-allowlisted; no unapproved user extension",
        )
    )

    fve_policy = facts.get("BitLockerPolicy") or {}
    expected_fve = {
        "UseAdvancedStartup": 1, "EnableBDEWithNoTPM": 0,
        "UseTPM": 2, "UseTPMPIN": 2,
        "UseTPMKey": 0, "UseTPMKeyPIN": 0,
        "MinimumPIN": 8,
    }
    checks.append(check(
        "bitlocker-tpm-pin-enrollment-policy",
        "PASS" if fve_policy == expected_fve else "FAIL",
        fve_policy, expected_fve,
    ))

    sandbox_feature = facts.get("SandboxFeature") or {}
    checks.append(check(
        "windows-sandbox-feature",
        "PASS" if sandbox_feature.get("Name") == "Containers-DisposableClientVM"
        and sandbox_feature.get("State") == "Enabled" else "FAIL",
        sandbox_feature,
        "Windows Sandbox optional feature enabled on Pro; guest runtime requires nested virtualization",
    ))

    bitlocker = facts.get("BitLocker") or {}
    protectors = set(bitlocker.get("KeyProtectorTypes") or [])
    checks.append(check(
        "bitlocker-tpm-immediate-protection",
        "PASS" if bitlocker.get("ProtectionStatus") == "On"
        and bitlocker.get("VolumeStatus") == "FullyEncrypted"
        and (("Tpm" in protectors) or ("TpmPin" in protectors))
        and "RecoveryPassword" in protectors else "FAIL",
        bitlocker,
        "BitLocker active with a TPM-backed protector and independent recovery password",
    ))
    bl_status = (
        "PASS"
        if bitlocker.get("ProtectionStatus") == "On"
        and bitlocker.get("VolumeStatus") == "FullyEncrypted"
        and "TpmPin" in protectors
        and "Tpm" not in protectors
        and "RecoveryPassword" in protectors
        else "FAIL"
    )
    checks.append(
        check(
            "bitlocker-vm-flow",
            bl_status,
            bitlocker,
            "FullyEncrypted; protection On; TPM+PIN and recovery password protectors",
        )
    )

    dg = facts.get("DeviceGuard") or {}
    policy = facts.get("DeviceGuardPolicy") or {}
    checks.append(check(
        "vbs-boot-policy",
        "PASS" if policy.get("EnableVBS") == 1
        and policy.get("RequirePlatformSecurityFeatures") == 1 else "FAIL",
        policy, "VBS enabled with Secure Boot requirement; UEFI Lock is hardware-only gate",
    ))
    checks.append(check(
        "hvci-boot-policy",
        "PASS" if policy.get("HVCIEnabled") == 1
        and 2 in (dg.get("SecurityServicesConfigured") or []) else "FAIL",
        {"policy": policy, "configured_services": dg.get("SecurityServicesConfigured")},
        "HVCI enabled/configured; UEFI Lock is hardware-only gate",
    ))
    vbs = dg.get("VirtualizationBasedSecurityStatus")
    checks.append(
        check(
            "vbs-runtime",
            "PASS" if vbs == 2 else "NOT_PROVABLE_IN_VM",
            vbs,
            "2 (running)",
        )
    )
    running_services = set(dg.get("SecurityServicesRunning") or [])
    checks.append(
        check(
            "hvci-runtime",
            "PASS" if 2 in running_services else "NOT_PROVABLE_IN_VM",
            sorted(running_services),
            "security service 2 running",
        )
    )

    admin = facts.get("AdministratorProtection") or {}
    checks.append(
        check(
            "administrator-protection",
            "PASS"
            if admin.get("TypeOfAdminApprovalMode") == 2
            else "FAIL",
            admin,
            "TypeOfAdminApprovalMode=2 when supported/configured",
        )
    )

    for name in (
        "pluton-hardware",
        "ess-face",
        "secure-launch-drtm-physical",
        "ledger-usb",
        "yubikey-recovery-hardware",
        "dual-physical-ssd-independence",
    ):
        checks.append(
            check(
                name,
                "NOT_PROVABLE_IN_VM",
                None,
                "bare-metal gate",
            )
        )

    failed = [row["name"] for row in checks if row["status"] == "FAIL"]
    warnings = [row["name"] for row in checks if row["status"] == "WARN"]
    not_provable = [
        row["name"]
        for row in checks
        if row["status"] == "NOT_PROVABLE_IN_VM"
    ]
    return {
        "status": "FAIL" if failed else "PASS",
        "checks": checks,
        "failed": failed,
        "warnings": warnings,
        "not_provable_in_vm": not_provable,
        "facts": facts,
    }


def run_audit(run_dir, cfg=None):
    """Use real elevated Windows admin context; never silently fall back to user access."""
    cfg = cfg or Config()
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    facts = capture_elevated_facts(cfg, run_dir)
    result = evaluate(facts)
    (run_dir / "audit.result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result
