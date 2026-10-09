import xml.etree.ElementTree as ET

UNATTEND_NS = "urn:schemas-microsoft-com:unattend"
NS = {"u": UNATTEND_NS}

EDITION = "Windows 11 Pro"
SETUP_PRODUCT_KEY = "W269N-WFGWX-YVC9B-4J6C9-T83GX"
SETUP_UI_LANGUAGE = "en-US"
UI_LANGUAGE = "en-US"
SYSTEM_LOCALE = "en-US"
USER_LOCALE = "de-DE"
INPUT_LOCALE = "0409:00000409;0419:00000419"
US_INPUT = "0409:00000409"
RU_INPUT = "0419:00000419"
GERMAN_INPUT = "0407:00000407"
GERMANY_GEOID = 94
TIME_ZONE = "W. Europe Standard Time"

BUSINESS_REQUIREMENT_OWNERS = {
    1: "hardware architecture / ASUS binding",
    2: "physical disk target/offline gate + independent ESP/WinRE",
    3: "product trust architecture",
    4: "post-install isolation + VBS/vault/Ledger",
    5: "TPM/Pluton/VBS + bare-metal proof",
    6: "UEFI/Secure Boot + BitLocker/Secure Launch",
    7: "BitLocker post-install",
    8: "independent volume protectors; no auto-unlock",
    9: "BitLocker TPM+startup PIN",
    10: "startup PIN separate from Hello",
    11: "Hello/ESS bare-metal proof",
    12: "VBS vault gate",
    13: "trusted-context design",
    14: "v1 accepted compromise + phase 2 trusted display",
    15: "Ledger/YubiKey independent trust domains",
    16: "offline recovery + independent token",
    17: "official media + reproducible provisioning",
    18: "known-good media + offline recovery material",
    19: "offline-capable setup start; network later",
    20: "maintenance/sensitive-work gate",
    21: "supported vendor maintenance channels",
    22: "supported Windows mechanisms/minimal custom plumbing",
    23: "Autounattend + desired state + audit",
    24: "VM proof separated from bare-metal proof",
    25: "fail-closed destructive target resolution",
    26: "official source/provenance",
    27: "workload validation",
    28: "product outcome/economics over mechanism",
    29: "TPM-backed BitLocker activation + separate owner PIN/recovery",
    30: "Administrator Protection mandatory, operational proof",
    31: "physical ASUS VBS/HVCI runtime and UEFI Lock",
    32: "two minimally connected Windows Sandbox profiles",
    33: "networked Sandbox host/LAN/VPN isolation gate",
    34: "suspect process connection logging plus enforced deny/prompt",
    35: "ordinary Edge vs sensitive Chrome and verified wallet products",
    36: "owner USB; verified answer, safe targeting and postinstall release gate",
}


def _check(checks, name, condition, actual=None, expected=None):
    checks.append(
        {
            "name": name,
            "status": "PASS" if condition else "FAIL",
            "actual": actual,
            "expected": expected,
        }
    )


def _settings(root, pass_name):
    rows = root.findall("u:settings", NS)
    matches = [x for x in rows if x.get("pass") == pass_name]
    if len(matches) != 1:
        raise ValueError(
            f"expected one settings pass {pass_name!r}, got {len(matches)}"
        )
    return matches[0]


def _component(settings, name):
    rows = [
        x
        for x in settings.findall("u:component", NS)
        if x.get("name") == name
    ]
    if len(rows) != 1:
        raise ValueError(
            f"expected one component {name!r}, got {len(rows)}"
        )
    return rows[0]


def _text(parent, path):
    node = parent.find(path, NS)
    return None if node is None else (node.text or "").strip()


def evaluate_autounattend(xml):
    checks = []
    try:
        root = ET.fromstring(xml)
    except Exception as exc:
        return {
            "status": "FAIL",
            "failed": ["xml-well-formed"],
            "checks": [
                {
                    "name": "xml-well-formed",
                    "status": "FAIL",
                    "actual": repr(exc),
                    "expected": "valid XML",
                }
            ],
        }

    try:
        winpe = _settings(root, "windowsPE")
        specialize = _settings(root, "specialize")
        oobe = _settings(root, "oobeSystem")

        intl_pe = _component(
            winpe, "Microsoft-Windows-International-Core-WinPE"
        )
        setup = _component(winpe, "Microsoft-Windows-Setup")
        shell_specialize = _component(
            specialize, "Microsoft-Windows-Shell-Setup"
        )
        intl_oobe = _component(
            oobe, "Microsoft-Windows-International-Core"
        )
        shell_oobe = _component(oobe, "Microsoft-Windows-Shell-Setup")
    except Exception as exc:
        _check(
            checks,
            "required-passes-components",
            False,
            repr(exc),
            "windowsPE/specialize/oobeSystem canonical components",
        )
        return {
            "status": "FAIL",
            "failed": [x["name"] for x in checks],
            "checks": checks,
        }

    _check(
        checks,
        "setup-ui-en-us",
        _text(intl_pe, "u:SetupUILanguage/u:UILanguage")
        == SETUP_UI_LANGUAGE,
        _text(intl_pe, "u:SetupUILanguage/u:UILanguage"),
        SETUP_UI_LANGUAGE,
    )
    for label, component in (
        ("winpe", intl_pe),
        ("oobe", intl_oobe),
    ):
        _check(
            checks,
            f"{label}-input-us-ru-only",
            _text(component, "u:InputLocale") == INPUT_LOCALE,
            _text(component, "u:InputLocale"),
            INPUT_LOCALE,
        )
        _check(
            checks,
            f"{label}-ui-en-us",
            _text(component, "u:UILanguage") == UI_LANGUAGE,
            _text(component, "u:UILanguage"),
            UI_LANGUAGE,
        )
        _check(
            checks,
            f"{label}-system-locale-en-us",
            _text(component, "u:SystemLocale") == SYSTEM_LOCALE,
            _text(component, "u:SystemLocale"),
            SYSTEM_LOCALE,
        )
        _check(
            checks,
            f"{label}-formats-de-de",
            _text(component, "u:UserLocale") == USER_LOCALE,
            _text(component, "u:UserLocale"),
            USER_LOCALE,
        )

    xml_lower = xml.lower()
    _check(
        checks,
        "german-keyboard-absent",
        GERMAN_INPUT.lower() not in xml_lower
        and "00000407" not in xml_lower,
        "present" if "00000407" in xml_lower else "absent",
        "absent",
    )

    for label, component in (
        ("specialize", shell_specialize),
        ("oobe", shell_oobe),
    ):
        _check(
            checks,
            f"{label}-timezone",
            _text(component, "u:TimeZone") == TIME_ZONE,
            _text(component, "u:TimeZone"),
            TIME_ZONE,
        )

    hostname = _text(shell_specialize, "u:ComputerName")
    _check(
        checks,
        "explicit-computer-name",
        bool(hostname) and hostname != "*",
        hostname,
        "explicit environment-bound hostname",
    )

    # An operator, not the XML, chooses the only destructive target.
    # No disk operations execute before the Windows Setup selection UI.
    _check(
        checks, "no-automatic-disk-configuration",
        setup.find("u:DiskConfiguration", NS) is None,
        "absent" if setup.find("u:DiskConfiguration", NS) is None else "present",
        "absent",
    )
    prohibited_disk_tags = {
        "DiskID", "PartitionID", "WillWipeDisk", "CreatePartitions",
        "ModifyPartitions", "InstallTo", "InstallToAvailablePartition",
    }
    found_disk_tags = sorted({
        element.tag.rsplit("}", 1)[-1] for element in setup.iter()
        if element.tag.rsplit("}", 1)[-1] in prohibited_disk_tags
    })
    _check(
        checks, "no-unattended-disk-target-or-layout",
        not found_disk_tags, found_disk_tags, [],
    )

    image = setup.find("u:ImageInstall/u:OSImage", NS)
    image_name = (
        _text(image, "u:InstallFrom/u:MetaData/u:Value")
        if image is not None
        else None
    )
    image_key = (
        _text(image, "u:InstallFrom/u:MetaData/u:Key")
        if image is not None
        else None
    )
    _check(
        checks,
        "edition-pro-non-n",
        image_key == "/IMAGE/NAME" and image_name == EDITION,
        {"key": image_key, "value": image_name},
        {"key": "/IMAGE/NAME", "value": EDITION},
    )
    _check(
        checks, "operator-selects-install-destination",
        image is not None and _text(image, "u:WillShowUI") == "Always",
        _text(image, "u:WillShowUI") if image is not None else None,
        "Always",
    )

    _check(
        checks,
        "accept-eula",
        _text(setup, "u:UserData/u:AcceptEula") == "true",
        _text(setup, "u:UserData/u:AcceptEula"),
        "true",
    )
    _check(
        checks,
        "setup-public-pro-key",
        _text(setup, "u:UserData/u:ProductKey/u:Key")
        == SETUP_PRODUCT_KEY
        and _text(setup, "u:UserData/u:ProductKey/u:WillShowUI")
        == "Never",
        {
            "key": _text(setup, "u:UserData/u:ProductKey/u:Key"),
            "will_show_ui": _text(
                setup,
                "u:UserData/u:ProductKey/u:WillShowUI",
            ),
        },
        {
            "key": SETUP_PRODUCT_KEY,
            "will_show_ui": "Never",
        },
    )

    oobe_node = shell_oobe.find("u:OOBE", NS)
    expected_oobe = {
        "HideEULAPage": "true",
        "HideOEMRegistrationScreen": "true",
        "HideOnlineAccountScreens": "true",
        "HideWirelessSetupInOOBE": "true",
        "ProtectYourPC": "3",
    }
    actual_oobe = {
        key: _text(oobe_node, f"u:{key}")
        if oobe_node is not None
        else None
        for key in expected_oobe
    }
    _check(
        checks,
        "oobe-supported-suppression",
        actual_oobe == expected_oobe,
        actual_oobe,
        expected_oobe,
    )
    _check(
        checks,
        "unsupported-oobe-bypasses-absent",
        "skipmachineoobe" not in xml_lower
        and "skipuseroobe" not in xml_lower
        and "bypassnro" not in xml_lower,
        {
            "SkipMachineOOBE": "skipmachineoobe" in xml_lower,
            "SkipUserOOBE": "skipuseroobe" in xml_lower,
            "BYPASSNRO": "bypassnro" in xml_lower,
        },
        "all absent",
    )

    local = shell_oobe.find(
        "u:UserAccounts/u:LocalAccounts/u:LocalAccount", NS
    )
    local_name = _text(local, "u:Name") if local is not None else None
    local_group = _text(local, "u:Group") if local is not None else None
    local_password = (
        _text(local, "u:Password/u:Value") if local is not None else None
    )
    _check(
        checks,
        "local-owner-without-password",
        bool(local_name)
        and local_group == "Administrators"
        and local is not None
        and local.find("u:Password", NS) is None,
        {
            "name_present": bool(local_name),
            "group": local_group,
            "password_present": bool(local_password),
        },
        {
            "name_present": True,
            "group": "Administrators",
            "password_present": False,
        },
    )

    # One canonical XML: no VM-only commands, automatic logon, or guest
    # extension anywhere in the answer, even on the disposable VM.
    forbidden_access = {
        "AutoLogon", "FirstLogonCommands", "LogonCommands",
        "RunSynchronous", "RunAsynchronous", "SynchronousCommand",
        "AsynchronousCommand", "CommandLine",
    }
    access_nodes = sorted({
        node.tag.rsplit("}", 1)[-1] for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] in forbidden_access
    })
    _check(checks, "no-environment-access-extension",
           not access_nodes and "vboxwindowsadditions" not in xml_lower,
           access_nodes, [])

    failed = [x["name"] for x in checks if x["status"] == "FAIL"]
    return {
        "status": "FAIL" if failed else "PASS",
        "failed": failed,
        "checks": checks,
        "runtime_gates": {
            "home_location_geoid": GERMANY_GEOID,
            "german_keyboard_forbidden": GERMAN_INPUT,
            "winre_enabled": True,
            "language_page_must_not_appear": True,
            "physical_ssd1_offline": "BARE_METAL_ONLY",
            "physical_target_identity": "BARE_METAL_ONLY",
            "operator_selection": "MANUAL_VM_AND_ASUS",
            "partition_sizes": "MICROSOFT_SETUP_DEFAULT",
        },
        "business_requirements": {
            str(key): value
            for key, value in BUSINESS_REQUIREMENT_OWNERS.items()
        },
    }
