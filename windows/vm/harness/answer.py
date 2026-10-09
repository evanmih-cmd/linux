import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

from config import Config
from contract import (
    EDITION,
    INPUT_LOCALE,
    SETUP_PRODUCT_KEY,
    evaluate_autounattend,
    SETUP_UI_LANGUAGE,
    SYSTEM_LOCALE,
    TIME_ZONE,
    UI_LANGUAGE,
    USER_LOCALE,
)
from machine import unc
from media import verify_official_iso
from vbox import VBox, VBoxError


def render_autounattend(
    cfg=None,
    credentials=None,
    *,
    hostname="SECUREWS",
    account_display_name="Local owner",
    account_description="Owner-controlled local account",
):
    cfg = cfg or Config()
    if credentials is None:
        credentials = {"user": "owner"}
    # No VM/prod exception: passwords may NEVER be put in an answer file.
    if credentials.get("password"):
        raise ValueError("refusing to write any account password to installation media")
    user = escape(credentials["user"])
    hostname = escape(str(hostname).upper())
    display_name = escape(account_display_name)
    account_description = escape(account_description)
    timezone = escape(TIME_ZONE)
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend"
          xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <settings pass="windowsPE">
    <component name="Microsoft-Windows-International-Core-WinPE"
               processorArchitecture="amd64"
               publicKeyToken="31bf3856ad364e35"
               language="neutral"
               versionScope="nonSxS">
      <SetupUILanguage>
        <UILanguage>en-US</UILanguage>
      </SetupUILanguage>
      <InputLocale>0409:00000409;0419:00000419</InputLocale>
      <SystemLocale>en-US</SystemLocale>
      <UILanguage>en-US</UILanguage>
      <UserLocale>de-DE</UserLocale>
    </component>
    <component name="Microsoft-Windows-Setup"
               processorArchitecture="amd64"
               publicKeyToken="31bf3856ad364e35"
               language="neutral"
               versionScope="nonSxS">
      <ImageInstall>
        <OSImage>
          <InstallFrom>
            <MetaData wcm:action="add">
              <Key>/IMAGE/NAME</Key>
              <Value>{EDITION}</Value>
            </MetaData>
          </InstallFrom>
          <WillShowUI>Always</WillShowUI>
        </OSImage>
      </ImageInstall>
      <UserData>
        <AcceptEula>true</AcceptEula>
        <FullName>{display_name}</FullName>
        <ProductKey>
          <Key>{SETUP_PRODUCT_KEY}</Key>
          <WillShowUI>Never</WillShowUI>
        </ProductKey>
      </UserData>
    </component>
  </settings>

  <settings pass="specialize">
    <component name="Microsoft-Windows-Shell-Setup"
               processorArchitecture="amd64"
               publicKeyToken="31bf3856ad364e35"
               language="neutral"
               versionScope="nonSxS">
      <ComputerName>{hostname}</ComputerName>
      <TimeZone>{timezone}</TimeZone>
    </component>
  </settings>

  <settings pass="oobeSystem">
    <component name="Microsoft-Windows-International-Core"
               processorArchitecture="amd64"
               publicKeyToken="31bf3856ad364e35"
               language="neutral"
               versionScope="nonSxS">
      <InputLocale>0409:00000409;0419:00000419</InputLocale>
      <SystemLocale>en-US</SystemLocale>
      <UILanguage>en-US</UILanguage>
      <UserLocale>de-DE</UserLocale>
    </component>
    <component name="Microsoft-Windows-Shell-Setup"
               processorArchitecture="amd64"
               publicKeyToken="31bf3856ad364e35"
               language="neutral"
               versionScope="nonSxS">
      <TimeZone>{timezone}</TimeZone>
      <OOBE>
        <HideEULAPage>true</HideEULAPage>
        <HideOEMRegistrationScreen>true</HideOEMRegistrationScreen>
        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
        <ProtectYourPC>3</ProtectYourPC>
      </OOBE>
      <UserAccounts>
        <LocalAccounts>
          <LocalAccount wcm:action="add">
            <Name>{user}</Name>
            <DisplayName>{display_name}</DisplayName>
            <Description>{account_description}</Description>
            <Group>Administrators</Group>
          </LocalAccount>
        </LocalAccounts>
      </UserAccounts>
    </component>
  </settings>
</unattend>
"""
    ET.fromstring(xml)
    return xml


def _iso_root_names(path):
    data = Path(path).read_bytes()
    result = {"primary": [], "joliet": [], "has_joliet": False}

    def descriptor(desc_type):
        for sector in range(16, 64):
            block = data[sector * 2048 : (sector + 1) * 2048]
            if len(block) < 2048 or block[1:6] != b"CD001":
                continue
            if block[0] != desc_type:
                continue
            if desc_type == 2 and block[88:91] not in (
                b"%/@",
                b"%/C",
                b"%/E",
            ):
                continue
            return block
        return None

    def names_from(block, joliet=False):
        if block is None:
            return []
        root = block[156:190]
        extent = int.from_bytes(root[2:6], "little")
        size = int.from_bytes(root[10:14], "little")
        directory = data[extent * 2048 : extent * 2048 + size]
        names = []
        offset = 0
        while offset < len(directory):
            length = directory[offset]
            if length == 0:
                offset = ((offset // 2048) + 1) * 2048
                continue
            record = directory[offset : offset + length]
            if len(record) < 34:
                break
            name_length = record[32]
            raw = record[33 : 33 + name_length]
            if raw not in (b"\x00", b"\x01"):
                if joliet:
                    names.append(raw.decode("utf-16-be"))
                else:
                    names.append(raw.decode("ascii", "replace"))
            offset += length
        return names

    primary = descriptor(1)
    supplementary = descriptor(2)
    result["primary"] = names_from(primary)
    result["joliet"] = names_from(supplementary, joliet=True)
    result["has_joliet"] = supplementary is not None
    return result


def verify_answer_media_iso(path):
    names = _iso_root_names(path)
    expected = "Autounattend.xml"
    if not names["has_joliet"]:
        raise RuntimeError(
            "answer media has no Joliet namespace; Windows would only see "
            f"the ISO9660 names {names['primary']!r}"
        )
    if names["joliet"] != [expected]:
        raise RuntimeError(
            "answer media root must expose exactly "
            f"{expected!r} through Joliet; got {names['joliet']!r}"
        )
    return {
        "status": "PASS",
        "expected": expected,
        "primary_names": names["primary"],
        "joliet_names": names["joliet"],
        "has_joliet": names["has_joliet"],
    }


def build_answer_media(cfg=None):
    cfg = cfg or Config()
    source = verify_official_iso(cfg)
    # Same account/OOBE semantics for VM and ASUS; the final owner chooses
    # a password interactively later. Never read/create test credentials here.
    credentials = {"user": "owner"}
    root = cfg.bench / "answer-media"
    root.mkdir(parents=True, exist_ok=True)
    answer = root / "Autounattend.xml"
    answer.write_text(
        render_autounattend(
            cfg,
            credentials,
            hostname="SECUREWS",
            account_display_name="Local owner",
            account_description="Owner-controlled local account",
        ),
        encoding="utf-8",
    )

    payload = answer.read_bytes()
    # Fail closed on renderer/output drift. The exact same XML applies to
    # both VM and ASUS; never build a VM-specific answer variant.
    canonical = cfg.repo / "windows/vm/deployment/Autounattend.xml"
    if not canonical.is_file() or canonical.read_bytes() != payload:
        raise RuntimeError("generated answer differs from canonical password-free XML")
    iso = cfg.bench / "Autounattend.iso"
    iso.unlink(missing_ok=True)

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(cfg.xorriso_lib)
    proc = subprocess.run(
        [
            str(cfg.xorriso),
            "-as",
            "mkisofs",
            "-quiet",
            "-J",
            "-joliet-long",
            "-V",
            "WINAUTO",
            "-o",
            str(iso),
            str(root),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "xorriso failed: " + (proc.stderr or proc.stdout).strip()
        )

    iso_verification = verify_answer_media_iso(iso)
    xml_contract = evaluate_autounattend(
        payload.decode("utf-8"),
    )
    if xml_contract["status"] != "PASS":
        raise RuntimeError(
            "generated Autounattend.xml failed install contract: "
            + ", ".join(xml_contract["failed"])
        )

    return {
        "answer": answer,
        "iso": iso,
        "user": credentials["user"],
        "source": source,
        "no_account_password_on_installation_media": True,
        "iso_verification": iso_verification,
        "xml_contract_status": xml_contract["status"],
        "xml_contract_failed": xml_contract["failed"],
    }


def attach_install_media(cfg=None, *, ports=(1, 2, 3)):
    cfg = cfg or Config()
    media = build_answer_media(cfg)
    box = VBox(cfg, require_machine=True)
    try:
        if box.state() != "PoweredOff":
            raise VBoxError(
                f"install media attachment requires PoweredOff VM, got {box.state()}"
            )

        official = box._vals(
            "IVirtualBox_openMedium",
            [
                ("_this", box.handle),
                ("location", unc(cfg.official_iso)),
                ("deviceType", "DVD"),
                ("accessMode", "ReadOnly"),
                ("forceNewUuid", "false"),
            ],
        )[0]
        answer = box._vals(
            "IVirtualBox_openMedium",
            [
                ("_this", box.handle),
                ("location", unc(media["iso"])),
                ("deviceType", "DVD"),
                ("accessMode", "ReadOnly"),
                ("forceNewUuid", "false"),
            ],
        )[0]

        props = box._vals(
            "IVirtualBox_getSystemProperties", [("_this", box.handle)]
        )[0]
        additions_path = box._vals(
            "ISystemProperties_getDefaultAdditionsISO", [("_this", props)]
        )[0]
        additions = box._vals(
            "IVirtualBox_openMedium",
            [
                ("_this", box.handle),
                ("location", additions_path),
                ("deviceType", "DVD"),
                ("accessMode", "ReadOnly"),
                ("forceNewUuid", "false"),
            ],
        )[0]

        session = box.lock("Write")
        try:
            machine = box.session_machine(session)

            for port, medium in zip(ports, (official, answer, additions), strict=True):
                box._vals(
                    "IMachine_attachDevice",
                    [
                        ("_this", machine),
                        ("name", "SATA"),
                        ("controllerPort", str(port)),
                        ("device", "0"),
                        ("type", "DVD"),
                        ("medium", medium),
                    ],
                )

            box._vals(
                "IMachine_setBootOrder",
                [("_this", machine), ("position", "1"), ("device", "DVD")],
            )
            box._vals(
                "IMachine_setBootOrder",
                [("_this", machine), ("position", "2"), ("device", "HardDisk")],
            )
            box.save_settings(machine)
        finally:
            box.unlock(session)

        return {
            "status": "PASS",
            "mechanism": "official-dvd-plus-joliet-autounattend-dvd",
            "image": "Windows 11 Pro",
            "official_iso": str(cfg.official_iso),
            "answer_media": str(media["iso"]),
            "answer_media_type": "DVD",
            "guest_user": media["user"],
            "no_account_password_on_installation_media": True,
            "guest_additions_media_attached": True,
            "source": media["source"],
            "answer_media_verification": media["iso_verification"],
            "xml_contract_status": media["xml_contract_status"],
            "xml_contract_failed": media["xml_contract_failed"],
        }
    finally:
        box.logoff()
