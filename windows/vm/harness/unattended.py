import os

from config import Config
from machine import unc
from media import load_or_create_credentials, verify_official_iso
from vbox import VBox, VBoxError


def select_windows_11_pro_image(names, indices):
    if len(names) != len(indices):
        raise RuntimeError(
            f"VirtualBox image name/index mismatch: {len(names)} != {len(indices)}"
        )
    rows = [(str(name).strip(), int(index)) for name, index in zip(names, indices)]

    exact = [
        row for row in rows
        if row[0].casefold() in {"windows 11 pro", "windows 11 professional"}
    ]
    if len(exact) == 1:
        return exact[0]

    candidates = []
    for name, index in rows:
        lower = name.casefold()
        if "windows 11" not in lower or "pro" not in lower:
            continue
        if any(
            bad in lower
            for bad in (" pro n", "education", "workstation", "enterprise")
        ):
            continue
        candidates.append((name, index))

    if len(candidates) != 1:
        available = ", ".join(f"{idx}:{name}" for name, idx in rows)
        raise RuntimeError(
            "cannot select exactly one standard Windows 11 Pro image; "
            f"available: {available}"
        )
    return candidates[0]


def _set(box, unattended, attr, value):
    box._vals(
        f"IUnattended_set{attr}",
        [("_this", unattended), (attr[0].lower() + attr[1:], value)],
    )


def detect_iso(cfg=None):
    cfg = cfg or Config()
    verify_official_iso(cfg)
    box = VBox(cfg)
    try:
        unattended = box._vals(
            "IVirtualBox_createUnattendedInstaller",
            [("_this", box.handle)],
        )[0]
        _set(box, unattended, "IsoPath", unc(cfg.official_iso))
        box._vals("IUnattended_detectIsoOS", [("_this", unattended)])
        names = box._vals(
            "IUnattended_getDetectedImageNames", [("_this", unattended)]
        )
        indices = box._vals(
            "IUnattended_getDetectedImageIndices", [("_this", unattended)]
        )
        selected_name, selected_index = select_windows_11_pro_image(
            names, indices
        )
        languages = box._vals(
            "IUnattended_getDetectedOSLanguages", [("_this", unattended)]
        )
        return {
            "images": [
                {"name": name, "index": int(index)}
                for name, index in zip(names, indices)
            ],
            "selected": {
                "name": selected_name,
                "index": selected_index,
            },
            "languages": languages,
        }
    finally:
        box.logoff()


def prepare_unattended(cfg=None):
    cfg = cfg or Config()
    verify_official_iso(cfg)
    credentials = load_or_create_credentials(cfg)
    box = VBox(cfg, require_machine=True)
    try:
        if box.state() != "PoweredOff":
            raise VBoxError(
                f"unattended preparation requires PoweredOff VM, got {box.state()}"
            )

        unattended = box._vals(
            "IVirtualBox_createUnattendedInstaller",
            [("_this", box.handle)],
        )[0]
        _set(box, unattended, "IsoPath", unc(cfg.official_iso))
        box._vals("IUnattended_detectIsoOS", [("_this", unattended)])

        names = box._vals(
            "IUnattended_getDetectedImageNames", [("_this", unattended)]
        )
        indices = box._vals(
            "IUnattended_getDetectedImageIndices", [("_this", unattended)]
        )
        image_name, image_index = select_windows_11_pro_image(names, indices)

        _set(box, unattended, "Machine", box.machine)
        _set(box, unattended, "ImageIndex", str(image_index))
        _set(box, unattended, "User", credentials["user"])
        _set(box, unattended, "UserPassword", credentials["password"])
        _set(box, unattended, "AdminPassword", credentials["password"])
        _set(box, unattended, "FullUserName", cfg.guest_full_name)
        _set(box, unattended, "Hostname", cfg.guest_hostname + ".local")
        _set(box, unattended, "Locale", "en_US")
        _set(box, unattended, "Country", "US")
        _set(box, unattended, "Language", "en-US")
        # VirtualBox 7.2 exposes KeyboardLayout in the interface but returns
        # E_NOTIMPL for its setter on this host. The verified ISO is en-US and
        # its unattended Windows defaults already select the US keyboard.
        _set(box, unattended, "TimeZone", cfg.guest_timezone)
        _set(box, unattended, "InstallGuestAdditions", "true")
        _set(box, unattended, "AvoidUpdatesOverNetwork", "true")

        product_key = os.environ.get("DESKTOP_WINDOWS_PRODUCT_KEY", "").strip()
        if product_key:
            _set(box, unattended, "ProductKey", product_key)

        supported = box._vals(
            "IUnattended_getIsUnattendedInstallSupported",
            [("_this", unattended)],
        )
        if supported and supported[0] != "true":
            raise VBoxError(
                "VirtualBox reports unattended installation unsupported "
                f"for image {image_name!r}"
            )

        box._vals("IUnattended_prepare", [("_this", unattended)])
        box._vals("IUnattended_constructMedia", [("_this", unattended)])
        box._vals("IUnattended_reconfigureVM", [("_this", unattended)])
        box._vals("IUnattended_done", [("_this", unattended)])

        return {
            "status": "PASS",
            "image": image_name,
            "image_index": image_index,
            "guest_user": credentials["user"],
            "password_embedded_in_source": False,
            "guest_additions_requested": True,
            "network_updates_during_setup": False,
            "product_key_supplied": bool(product_key),
        }
    finally:
        box.logoff()
