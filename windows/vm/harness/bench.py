#!/usr/bin/env python3
import json
import sys

from audit import run_audit
from config import Config
from machine import destroy_vm, reset_vm, vm_status
from media import verify_official_iso
from runner import (
    audit_only,
    bootstrap_guest,
    configure_guest,
    install,
    reinstall,
    resume_install,
    restore,
    shutdown_guest,
    snapshot,
    start_vm,
)
from unattended import detect_iso
from two_disk import prepare as prepare_two_disk, boot as boot_two_disk, status as status_two_disk
from workflow import install_contract_check, static_check


def emit(value):
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = Config()
    command = argv.pop(0) if argv else "check"

    if command == "check":
        result = static_check(cfg)
    elif command == "contract":
        result = install_contract_check(cfg)
    elif command == "iso":
        result = verify_official_iso(cfg)
    elif command == "status":
        result = vm_status(cfg)
    elif command == "two-disk-prepare":
        result = prepare_two_disk(cfg)
    elif command == "two-disk-boot":
        result = boot_two_disk(cfg)
    elif command == "two-disk-status":
        result = status_two_disk(cfg)
    elif command == "two-disk-verify":
        result = status_two_disk(cfg, verify=True)
    elif command == "reset":
        result = reset_vm(cfg)
    elif command == "detect":
        result = detect_iso(cfg)
    elif command == "install":
        result = install(cfg)
    elif command == "reinstall":
        result = reinstall(cfg)
    elif command == "resume":
        result = resume_install(cfg)
    elif command == "bootstrap":
        result = bootstrap_guest(cfg)
    elif command == "configure":
        result = configure_guest(cfg)
    elif command == "audit":
        result = audit_only(cfg)
    elif command == "start":
        result = start_vm(cfg)
    elif command == "shutdown":
        result = shutdown_guest(cfg)
    elif command == "snapshot":
        if len(argv) != 1:
            raise SystemExit("usage: bench.py snapshot NAME")
        result = snapshot(argv[0], cfg)
    elif command == "restore":
        if len(argv) != 1:
            raise SystemExit("usage: bench.py restore NAME")
        result = restore(argv[0], cfg)
    elif command == "destroy":
        result = destroy_vm(cfg)
    else:
        raise SystemExit(
            "usage: bench.py "
            "[check|contract|iso|status|two-disk-prepare|two-disk-boot|two-disk-status|two-disk-verify|reset|detect|install|reinstall|resume|bootstrap|configure|audit|"
            "start|shutdown|snapshot NAME|restore NAME|destroy]"
        )

    emit(result)
    if isinstance(result, dict) and result.get("status") == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
