#!/usr/bin/env python3
"""Manual runner for the Windows collector.

This script lets you invoke `collect_windows_asset` from the command line so you
can validate connectivity, credentials, and WinRM/WMI behavior without running
the full poller loop.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore

import windows_collectors as collectors
from windows_collectors import WindowsProbeError

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yml")


def _load_yaml_config(path: str) -> Dict[str, Any]:
    if not yaml:
        raise RuntimeError("PyYAML is required to load config files (pip install pyyaml)")
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _find_windows_targets(config: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    windows_targets = config.get("windows")
    if isinstance(windows_targets, list):
        for entry in windows_targets:
            if isinstance(entry, dict):
                yield entry
    for entry in config.get("targets", []) or []:
        if isinstance(entry, dict) and str(entry.get("os", "")).lower() == "windows":
            yield entry


def _merge_overrides(target: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(target)
    for key, value in overrides.items():
        if value is not None:
            result[key] = value
    return result


def _bool(value: Optional[bool]) -> Optional[bool]:
    return bool(value) if value is not None else None


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Manual Windows collector runner")
    parser.add_argument("--host", help="Hostname or IP of the Windows target")
    parser.add_argument("--username", help="Username for authentication")
    parser.add_argument("--password", help="Password for authentication")
    parser.add_argument("--domain", help="Domain (optional)")
    parser.add_argument("--hashes", help="LM:NT hash pair for pass-the-hash auth")
    parser.add_argument("--kerberos", action="store_true", help="Use Kerberos for WMI/WinRM")
    parser.add_argument("--kdc-host", help="Explicit KDC host for Kerberos")
    parser.add_argument("--winrm-transport", help="WinRM transport (ntlm, kerberos, credssp)")
    parser.add_argument("--winrm-port", type=int, help="WinRM port override")
    parser.add_argument("--winrm-use-ssl", action="store_true", help="Force WinRM over HTTPS")
    parser.add_argument("--winrm-validate-cert", action="store_true", help="Validate HTTPS certificates")
    parser.add_argument("--winrm-read-timeout", type=int, help="WinRM read timeout (seconds)")
    parser.add_argument("--winrm-operation-timeout", type=int, help="WinRM operation timeout (seconds)")
    parser.add_argument("--collect-applications", dest="collect_applications", action="store_true", help="Enumerate installed applications")
    parser.add_argument("--no-collect-applications", dest="collect_applications", action="store_false", help="Skip installed applications")
    parser.add_argument("--applications-limit", type=int, help="Max installed apps to collect")
    parser.add_argument("--wmi-namespace", help="Custom WMI namespace (default //./root/cimv2)")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="YAML config file to seed defaults (default: poller/config.yml)")
    parser.add_argument("--target-index", type=int, default=0, help="Which Windows target in the config to use (default: 0)")
    parser.add_argument("--json-target", help="Path to JSON file containing a full collector target")
    parser.add_argument("--skip-wmi", action="store_true", help="Disable WMI/DCOM attempts (forces WinRM)")
    parser.add_argument("--skip-winrm", action="store_true", help="Disable WinRM fallback")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    parser.set_defaults(collect_applications=None)

    args = parser.parse_args(argv)

    target: Dict[str, Any] = {}

    if args.json_target:
        with open(args.json_target, "r", encoding="utf-8") as handle:
            target = json.load(handle)
    elif args.config and os.path.exists(args.config):
        config = _load_yaml_config(args.config)
        windows_targets = list(_find_windows_targets(config))
        if windows_targets and 0 <= args.target_index < len(windows_targets):
            target = dict(windows_targets[args.target_index])
        elif not windows_targets:
            print("No Windows targets found in config", file=sys.stderr)
        else:
            print(f"Target index {args.target_index} out of range (found {len(windows_targets)} targets)", file=sys.stderr)

    overrides: Dict[str, Any] = {
        "host": args.host,
        "username": args.username,
        "password": args.password,
        "domain": args.domain,
        "hashes": args.hashes,
        "kerberos": args.kerberos,
        "kdc_host": args.kdc_host,
        "winrm_transport": args.winrm_transport,
        "winrm_port": args.winrm_port,
        "winrm_use_ssl": _bool(args.winrm_use_ssl),
        "winrm_validate_cert": _bool(args.winrm_validate_cert),
        "winrm_read_timeout": args.winrm_read_timeout,
        "winrm_operation_timeout": args.winrm_operation_timeout,
        "collect_applications": args.collect_applications,
        "applications_limit": args.applications_limit,
        "wmi_namespace": args.wmi_namespace,
    }

    target = _merge_overrides(target, overrides)

    missing = [key for key in ("host", "username", "password") if not target.get(key)]
    if missing:
        parser.error(f"Missing required fields after merging config/overrides: {', '.join(missing)}")

    if args.skip_wmi:
        collectors.DCOMConnection = None  # type: ignore
        collectors.imp_wmi = None  # type: ignore

    if args.skip_winrm:
        collectors.winrm = None  # type: ignore

    try:
        result = collectors.collect_windows_asset(target)
    except WindowsProbeError as exc:
        print(f"[WINDOWS_PROBE_ERROR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - runtime errors
        print(f"[UNEXPECTED_ERROR] {exc}", file=sys.stderr)
        return 3

    if args.pretty:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
