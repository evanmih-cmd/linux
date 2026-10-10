"""Create and verify the synthetic SSD1 GPT via documented VirtualBox IMediumIO.

This is *not* a production disk-layout utility. Only newly allocated, isolated
throwaway VirtualBox media may be initialized, before attachment to any VM.
An authentic GPT plus raw partition data sentinel protects against silent
destructive Setup targeting of disk 0.
"""
import base64
import hashlib
import struct
import uuid
import zlib

SECTOR = 512
ENTRY_COUNT = 128
ENTRY_SIZE = 128
GPT_TABLE_BYTES = ENTRY_COUNT * ENTRY_SIZE
ESP = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
MSR = "e3c9e316-0b5c-4db8-817d-f92df00215ae"
BASIC = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"
RECOVERY = "de94bba4-06d1-4d40-a16a-bfd50179d6ac"
SENTINEL = b"WINDOWS-BENCH-SSD1-PRESERVATION-DO-NOT-WIPE:"


def _guid_bytes(value):
    return uuid.UUID(value).bytes_le


def gpt_sectors(size_bytes, disk_guid=None):
    if size_bytes % SECTOR or size_bytes < 4 * 1024**3:
        raise ValueError("synthetic protected disk requires aligned >=4 GiB")
    count = size_bytes // SECTOR
    last = count - 1
    first_usable, last_usable = 34, last - 33
    disk_guid = disk_guid or uuid.uuid4()

    # Deliberate independent Home-like GPT with sentinel in a BasicData area.
    # These are test partitions only, not a claimed Windows Home filesystem.
    start = 2048
    specs = [
        (ESP, start, start + 260 * 2048 - 1, "Home ESP"),
    ]
    start = specs[-1][2] + 1
    specs.append((MSR, start, start + 16 * 2048 - 1, "Home MSR"))
    start = specs[-1][2] + 1
    specs.append((BASIC, start, start + 2 * 1024**3 // SECTOR - 1, "Home Data Sentinel"))
    start = specs[-1][2] + 1
    specs.append((RECOVERY, start, start + 768 * 2048 - 1, "Home Recovery"))
    if specs[-1][2] > last_usable:
        raise ValueError("protected GPT partitions exceed disk")

    entries = bytearray(GPT_TABLE_BYTES)
    for i, (type_guid, begin, end, name) in enumerate(specs):
        struct.pack_into("<16s16sQQQ72s", entries, i * ENTRY_SIZE,
                         _guid_bytes(type_guid), uuid.uuid4().bytes_le,
                         begin, end, 0, name.encode("utf-16-le").ljust(72, b"\0"))
    entries_crc = zlib.crc32(entries)

    def header(current, backup, table_lba):
        b = bytearray(SECTOR)
        struct.pack_into("<8sIIIIQQQQ16sQIII", b, 0, b"EFI PART",
                         0x10000, 92, 0, 0, current, backup, first_usable,
                         last_usable, disk_guid.bytes_le, table_lba,
                         ENTRY_COUNT, ENTRY_SIZE, entries_crc)
        struct.pack_into("<I", b, 16, zlib.crc32(b[:92]))
        return bytes(b)

    mbr = bytearray(SECTOR)
    struct.pack_into("<B3sB3sII", mbr, 446, 0, b"\0\2\0", 0xEE,
                     b"\xff\xff\xff", 1, min(last, 0xFFFFFFFF))
    mbr[510:512] = b"\x55\xaa"
    sentinel = SENTINEL + str(disk_guid).encode("ascii")
    data_lba = specs[2][1] + 1
    return {
        "disk_guid": str(disk_guid),
        "sentinel_lba": data_lba,
        "sentinel_sha256": hashlib.sha256(sentinel).hexdigest(),
        "sentinel_bytes": sentinel,
        "partition_count": len(specs),
        "writes": [
            (0, bytes(mbr)),
            (SECTOR, header(1, last, 2)),
            (2 * SECTOR, bytes(entries[:SECTOR])),
            ((last - 32) * SECTOR, bytes(entries[:SECTOR])),
            (last * SECTOR, header(last, 1, last - 32)),
            (data_lba * SECTOR, sentinel.ljust(SECTOR, b"\0")),
        ],
    }


def _write(box, mediumio, offset, data):
    # A 16-KiB GPT table must be broken into sector writes: SOAP octet[]
    # transport is serial and large XML payloads are costly on NEM hosts.
    for n in range(0, len(data), SECTOR):
        chunk = data[n:n+SECTOR]
        values = box._vals("IMediumIO_write",
                           [("_this", mediumio), ("offset", str(offset+n)),
                            ("data", base64.b64encode(chunk).decode("ascii"))])
        if not values or int(values[0]) != len(chunk):
            raise RuntimeError(f"IMediumIO write failed at offset {offset+n}")


def initialize_protected_medium(box, medium, size_bytes):
    info = gpt_sectors(size_bytes)
    io = box._vals("IMedium_openForIO",
                   [("_this", medium), ("writable", "true"), ("password", "")])[0]
    try:
        for offset, data in info["writes"]:
            _write(box, io, offset, data)
    finally:
        box.call("IMediumIO_close", [("_this", io)])
    return {key: value for key, value in info.items()
            if key not in ("writes", "sentinel_bytes")}


def _read(box, io, offset, size):
    root = box._raw("IMediumIO_read",
                    [("_this", io), ("offset", str(offset)), ("size", str(size))])
    values = [node.text or "" for node in root.findall(".//returnval")]
    if len(values) != 1:
        raise RuntimeError(f"IMediumIO byte-string count {len(values)} != 1")
    raw = base64.b64decode(values[0])
    if len(raw) != size:
        raise RuntimeError(f"IMediumIO read length {len(raw)} != {size}")
    return raw


def verify_protected_medium(box, medium, info):
    io = box._vals("IMedium_openForIO",
                   [("_this", medium), ("writable", "false"), ("password", "")])[0]
    try:
        lba = info["sentinel_lba"]
        sector = _read(box, io, lba*SECTOR, SECTOR)
        expected = SENTINEL + info["disk_guid"].encode("ascii")
        header = _read(box, io, SECTOR, SECTOR)
        mbr = _read(box, io, 0, SECTOR)
        intact = (
            sector[:len(expected)] == expected
            and header.startswith(b"EFI PART")
            and mbr[510:512] == b"\x55\xaa"
        )
        return {
            "status": "PASS" if intact else "FAIL",
            "disk_guid": info["disk_guid"],
            "sentinel_lba": lba,
            "sentinel_sha256": hashlib.sha256(sector[:len(expected)]).hexdigest(),
            "gpt_header_present": header.startswith(b"EFI PART"),
            "protective_mbr_present": mbr[510:512] == b"\x55\xaa",
        }
    finally:
        box.call("IMediumIO_close", [("_this", io)])
