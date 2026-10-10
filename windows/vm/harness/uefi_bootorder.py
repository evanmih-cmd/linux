"""Read and reorder existing VirtualBox UEFI boot options on disposable VM.

Only changes persistent BootOrder. Never touches SATA attachment or VDI data.
"""
import base64
import struct

OWNER = "8be4df61-93ca-11d2-aa0d-00e098032b8c"

def store_of(box):
    nvram = box._vals("IMachine_getNonVolatileStore",
                      [("_this", box.machine)])[0]
    return box._vals("INvramStore_getUefiVariableStore",
                     [("_this", nvram)])[0]


def names_of(box, store):
    root = box._raw("IUefiVariableStore_queryVariables", [("_this", store)])
    return [x.text for x in root.iter() if x.tag == "names"]


def variable_of(box, store, name):
    root = box._raw("IUefiVariableStore_queryVariableByName",
                    [("_this", store), ("name", name)])
    return {
        "owner": root.findtext(".//owner"),
        "attributes": [x.text for x in root.iter() if x.tag == "attributes"],
        "data": base64.b64decode(root.findtext(".//data") or ""),
    }


def _boot_label(raw):
    if len(raw) < 10:
        raise ValueError("truncated EFI_LOAD_OPTION")
    pos = 6
    while pos + 2 <= len(raw):
        if raw[pos:pos+2] == bytes(2):
            return raw[6:pos].decode("utf-16-le")
        pos += 2
    raise ValueError("EFI_LOAD_OPTION missing null-terminated label")


def _expected_medium_label(box, port):
    medium = box._vals("IMachine_getMedium", [
        ("_this", box.machine), ("name", "SATA"),
        ("controllerPort", str(port)), ("device", "0")])[0]
    medium_id = box._vals("IMedium_getId", [("_this", medium)])[0]
    return "VB" + medium_id[:8] + "-" + bytes.fromhex(medium_id[-8:])[::-1].hex()


def promote_existing_target_boot_option(box):
    """Reorder the two *existing* firmware hard-disk entries, nothing else."""
    if box.state() != "PoweredOff":
        raise RuntimeError("persistent BootOrder edits require PoweredOff VM")
    session = box.lock("Write")
    original_machine = box.machine
    try:
        box.machine = box.session_machine(session)
        store = store_of(box)
        options = names_of(box, store)
        required = ("BootOrder", "Boot0004", "Boot0005")
        if not all(name in options for name in required):
            raise RuntimeError("the expected firmware boot entries are missing")
        current = variable_of(box, store, "BootOrder")
        if current["owner"].lower() != OWNER:
            raise RuntimeError("unexpected UEFI BootOrder variable owner")
        order_bytes = current["data"]
        if len(order_bytes) % 2:
            raise RuntimeError("invalid BootOrder byte count")
        order = list(struct.unpack("<" + "H" * (len(order_bytes)//2),
                                   order_bytes))
        if order.count(4) != 1 or order.count(5) != 1:
            raise RuntimeError("unexpected hard-disk entries in BootOrder")

        for option, port in (("Boot0004", 0), ("Boot0005", 1)):
            actual = _boot_label(variable_of(box, store, option)["data"])
            expected = _expected_medium_label(box, port)
            if expected not in actual:
                raise RuntimeError(
                    f"unexpected firmware disk for {option}: {actual!r}"
                )

        reordered = [number for number in order if number != 5]
        reordered.insert(reordered.index(4), 5)
        data = struct.pack("<" + "H" * len(reordered), *reordered)
        if data != order_bytes:
            try:
                box.call("IUefiVariableStore_changeVariable", [
                    ("_this", store), ("name", "BootOrder"),
                    ("data", base64.b64encode(data).decode("ascii"))])
                if variable_of(box, store, "BootOrder")["data"] != data:
                    raise RuntimeError("BootOrder readback mismatch")
                box.save_settings(box.machine)
            except Exception:
                box.call("IUefiVariableStore_changeVariable", [
                    ("_this", store), ("name", "BootOrder"),
                    ("data", base64.b64encode(order_bytes).decode("ascii"))])
                raise
        return {
            "status": "PASS", "changed": data != order_bytes,
            "original": [f"Boot{x:04X}" for x in order],
            "current": [f"Boot{x:04X}" for x in reordered],
            "disk_priority": ["target SATA1", "protected SATA0"],
        }
    finally:
        box.machine = original_machine
        box.unlock(session)
