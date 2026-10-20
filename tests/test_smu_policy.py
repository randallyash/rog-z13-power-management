#!/usr/bin/env python3
"""The SMU helper accepts only clamped PPT and curve-optimizer requests."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "service"))

from z13_power_hw import parse_smu_request  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        raise SystemExit(f"FAIL {name}: {detail}")
    print(f"ok {name}")


def main() -> None:
    check("ppt floor 45", parse_smu_request("ppt 45 45 45") == ("ppt", (45, 45, 45)))
    check("perf fast", parse_smu_request("ppt 75 93 75") == ("ppt", (75, 93, 75)))
    check("reject 10W", isinstance(parse_smu_request("ppt 10 10 10"), str))
    check("reject 20W", isinstance(parse_smu_request("ppt 20 20 20"), str))
    check("reject 28W", isinstance(parse_smu_request("ppt 28 32 28"), str))
    check("reject 27W", isinstance(parse_smu_request("ppt 27 32 27"), str))
    check("reject pl1 93", isinstance(parse_smu_request("ppt 93 93 93"), str))
    check("co -20", parse_smu_request("co -20") == ("co", (-20,)))
    check("co 0", parse_smu_request("co 0") == ("co", (0,)))
    check("reject co -41", isinstance(parse_smu_request("co -41"), str))
    check("reject raw opcode", isinstance(parse_smu_request("cmd 20 1"), str))
    check("reject smn", isinstance(parse_smu_request("smn 0"), str))
    check("ping", parse_smu_request("ping") == ("ping", ()))

    rule = open(os.path.join(ROOT, "contrib/ryzen-smu/99-ryzen-smu.rules"), encoding="utf-8").read()
    check("udev does not chmod a+w", "a+w" not in rule and "chmod 777" not in rule)
    check("udev locks via helper script", "lock-smu-sysfs" in rule)
    script = open(os.path.join(ROOT, "scripts/z13-power"), encoding="utf-8").read()
    check("setup-undervolt does not chmod a+w", "chmod a+w" not in script)
    access = open(os.path.join(ROOT, "contrib/udev/99-z13power-access.rules"), encoding="utf-8").read()
    check("access rule is not group users", 'GROUP="users"' not in access and "chgrp users" not in access)
    check("access rule uses z13-power", 'GROUP="z13-power"' in access)
    service = open(os.path.join(ROOT, "service/z13-power-service"), encoding="utf-8").read()
    check("quiet recipe is the bios floor", 'QUIET_TDP = "28 32 45"' in service)
    check("quiet apply skips the mailbox", '--no-smu' in service and "smu=(profile != \"quiet\")" in service)
    check("cli quiet skips the mailbox", "tdp --set 28 --pl2 32 --pl3 45 --no-smu" in script)
    print("smu policy tests passed")


if __name__ == "__main__":
    main()
