import ast
import json
import re
from pathlib import Path


class BenchInvariantError(RuntimeError):
    pass


WHY_TCP_IS_FORBIDDEN = (
    "TCP serial is forbidden on this VM bench because it has repeatedly made "
    "VirtualBox launch unreliable: server mode can block launchVMProcess waiting "
    "for a client, and client mode has failed with VERR_TIMEOUT. The supported "
    "COM1 transport is RawFile only."
)


def validate_source_tree(root):
    root = Path(root)
    violations = []
    for path in sorted(root.glob("*.py")):
        if path.name == "invariants.py":
            continue
        source = path.read_text()
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            raise BenchInvariantError(
                f"VM bench invariant check cannot parse {path}:{exc.lineno}: "
                f"{exc.msg}. Fix the harness before starting a VM cycle."
            ) from exc

        forbidden = re.compile(
            r"\bTCP\b|tcp_serial|serialterm",
            re.IGNORECASE,
        )
        for lineno, line in enumerate(source.splitlines(), 1):
            if forbidden.search(line):
                violations.append(
                    f"{path.name}:{lineno}: forbidden TCP-serial reference: "
                    f"{line.strip()}"
                )

    if violations:
        detail = "\n  - ".join(violations)
        raise BenchInvariantError(
            "VM bench invariant violation detected before reset/build/launch.\n"
            f"  - {detail}\n"
            f"Reason: {WHY_TCP_IS_FORBIDDEN}\n"
            "Required fix: remove the TCP serial path and keep COM1 on RawFile "
            "to the bench serial.log, then rerun bench.py run."
        )


def validate_runtime_serial(serial_config, expected_path, phase):
    expected = {
        "enabled": "true",
        "host_mode": "RawFile",
        "path": str(expected_path),
        "io_address": "1016",
        "irq": "4",
    }
    mismatches = {
        key: {"expected": value, "actual": serial_config.get(key)}
        for key, value in expected.items()
        if serial_config.get(key) != value
    }
    if not mismatches:
        return

    raise BenchInvariantError(
        f"VM bench COM1 invariant violation during {phase}. "
        "The VM will not be started.\n"
        f"Reason: {WHY_TCP_IS_FORBIDDEN}\n"
        "Allowed configuration is COM1 RawFile only. "
        f"Mismatch: {json.dumps(mismatches, sort_keys=True)}\n"
        f"Actual COM1: {json.dumps(serial_config, sort_keys=True)}"
    )
