import re
import time
from typing import Any, Dict, List, Optional, Tuple

import paramiko

__all__ = ["collect_cisco_asset", "CiscoProbeError"]


class CiscoProbeError(RuntimeError):
    """Raised when the Cisco probe cannot gather data."""


_PROMPT_RE = re.compile(r"[>#] ?$")
_READ_CHUNK = 8192
_DEFAULT_TIMEOUT = 10


def collect_cisco_asset(target: Dict[str, Any]) -> Dict[str, Any]:
    host = target.get("host")
    username = target.get("username")
    password = target.get("password")
    port = int(target.get("port") or 22)
    enable_password = target.get("enable_password") or target.get("enablePassword")
    timeout = int(target.get("timeout") or _DEFAULT_TIMEOUT)

    if not host:
        raise CiscoProbeError("Missing host for Cisco target")
    if not username:
        raise CiscoProbeError("Missing username for Cisco target")
    if password is None:
        raise CiscoProbeError("Missing password for Cisco target")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    warnings: List[str] = []

    try:
        ssh.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            allow_agent=False,
            look_for_keys=False,
            timeout=timeout,
        )
        shell = ssh.invoke_shell()
        try:
            _read_until_prompt(shell, timeout)
            _run_command(shell, "terminal length 0", timeout)

            enabled = False
            if enable_password:
                enabled = _try_enable(shell, enable_password, timeout)
                if not enabled:
                    warnings.append("Enable password may be invalid; continuing without privilege mode")
            else:
                # Attempt enable without password to detect if prompt already privileged
                enabled = _is_privileged_prompt(shell)

            show_version = _run_command(shell, "show version", timeout)
            show_inventory = _run_command(shell, "show inventory", timeout, allow_failure=True)
            int_brief = _run_command(shell, "show ip interface brief", timeout)
            int_desc = _run_command(shell, "show interface description", timeout, allow_failure=True)

            version_info = _parse_show_version(show_version)
            inventory_info = _parse_show_inventory(show_inventory) if show_inventory else {}
            interfaces = _parse_interface_brief(int_brief)
            descriptions = _parse_interface_descriptions(int_desc)

            for iface in interfaces:
                name = iface["name"]
                if name in descriptions:
                    iface["description"] = descriptions[name].get("description")
                    iface["status"] = descriptions[name].get("status", iface.get("status"))
                    iface["protocol"] = descriptions[name].get("protocol", iface.get("protocol"))

            hostname = target.get("host_display") or version_info.get("hostname") or inventory_info.get("hostname")
            if version_info.get("hostname"):
                hostname = version_info["hostname"]

            ips: List[str] = []
            for iface in interfaces:
                for addr in iface.get("addresses", []):
                    if addr and addr not in ips:
                        ips.append(addr)

            hardware: Dict[str, Any] = {
                "vendor": "Cisco",
            }
            if version_info.get("model"):
                hardware["model"] = version_info["model"]
            elif inventory_info.get("model"):
                hardware["model"] = inventory_info["model"]
            if version_info.get("serial"):
                hardware["serial"] = version_info["serial"]
            elif inventory_info.get("serial"):
                hardware["serial"] = inventory_info["serial"]
            if version_info.get("base_mac"):
                hardware["base_mac"] = version_info["base_mac"]

            os_info: Dict[str, Any] = {
                "family": "network",
                "vendor": "Cisco",
            }
            if version_info.get("version"):
                os_info["version"] = version_info["version"]
            if version_info.get("image"):
                os_info["image"] = version_info["image"]
            if hostname:
                os_info["hostname"] = hostname
            if version_info.get("uptime"):
                os_info["uptime"] = version_info["uptime"]

            result: Dict[str, Any] = {
                "name": hostname or host,
                "os": {k: v for k, v in os_info.items() if v},
                "hardware": {k: v for k, v in hardware.items() if v},
                "network": {"interfaces": interfaces} if interfaces else None,
                "ips": ips,
                "mac": version_info.get("base_mac"),
                "metrics": None,
                "applications": None,
                "probe_source": "cisco-ssh",
            }
            if warnings:
                result["warnings"] = warnings

            return result
        finally:
            try:
                shell.close()
            except Exception:
                pass
    except (paramiko.AuthenticationException, paramiko.SSHException) as exc:
        raise CiscoProbeError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        raise CiscoProbeError(str(exc)) from exc
    finally:
        ssh.close()


def _run_command(channel: paramiko.Channel, command: str, timeout: int, allow_failure: bool = False) -> str:
    channel.send(command + "\n")
    time.sleep(0.1)
    raw = _read_until_prompt(channel, timeout)
    output = _strip_command_output(command, raw)
    if not allow_failure and output.strip().startswith("%"):
        raise CiscoProbeError(f"Command '{command}' failed: {output.strip()}")
    return output


def _try_enable(channel: paramiko.Channel, enable_password: str, timeout: int) -> bool:
    before = _read_remaining(channel)
    channel.send("enable\n")
    time.sleep(0.1)
    prompt = _read_until(channel, "Password", timeout)
    if "Password" in prompt:
        channel.send(enable_password + "\n")
        time.sleep(0.2)
    response = _read_until_prompt(channel, timeout)
    if "Password" in response and "%" in response:
        return False
    return _is_privileged_prompt(channel)


def _is_privileged_prompt(channel: paramiko.Channel) -> bool:
    snapshot = _read_remaining(channel)
    last_line = snapshot.strip().splitlines()[-1] if snapshot.strip() else ""
    return last_line.endswith("#")


def _read_until_prompt(channel: paramiko.Channel, timeout: int) -> str:
    end = time.time() + timeout
    buf = ""
    while time.time() < end:
        if channel.recv_ready():
            chunk = channel.recv(_READ_CHUNK).decode("utf-8", "ignore")
            buf += chunk
            if _PROMPT_RE.search(buf.splitlines()[-1] if buf.splitlines() else ""):
                time.sleep(0.1)
                while channel.recv_ready():
                    buf += channel.recv(_READ_CHUNK).decode("utf-8", "ignore")
                break
        else:
            time.sleep(0.1)
    return buf


def _read_remaining(channel: paramiko.Channel) -> str:
    buf = ""
    while channel.recv_ready():
        buf += channel.recv(_READ_CHUNK).decode("utf-8", "ignore")
    return buf


def _read_until(channel: paramiko.Channel, marker: str, timeout: int) -> str:
    end = time.time() + timeout
    buf = ""
    while time.time() < end:
        if channel.recv_ready():
            chunk = channel.recv(_READ_CHUNK).decode("utf-8", "ignore")
            buf += chunk
            if marker in buf:
                break
        else:
            time.sleep(0.1)
    return buf


def _strip_command_output(command: str, output: str) -> str:
    lines = output.splitlines()
    cleaned: List[str] = []
    for line in lines:
        stripped = line.rstrip()
        if stripped.strip().lower() == command.lower():
            continue
        if _PROMPT_RE.match(stripped.strip()):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _parse_show_version(output: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if not output:
        return data

    version_match = re.search(r"Version\s+([\w\d\.()\-]+)", output)
    if version_match:
        data["version"] = version_match.group(1)

    model_match = re.search(r"^cisco\s+([\w\-]+)\s+\(", output, re.IGNORECASE | re.MULTILINE)
    if model_match:
        data["model"] = model_match.group(1)
    else:
        model_alt = re.search(r"^Model number\s*:\s*(\S+)", output, re.MULTILINE)
        if model_alt:
            data["model"] = model_alt.group(1)

    serial_match = re.search(r"Processor board ID\s+(\S+)", output)
    if serial_match:
        data["serial"] = serial_match.group(1)
    else:
        serial_alt = re.search(r"System serial number\s*:\s*(\S+)", output)
        if serial_alt:
            data["serial"] = serial_alt.group(1)

    mac_match = re.search(r"Base ethernet MAC Address\s*:\s*([0-9a-fA-F\.:-]+)", output)
    if mac_match:
        data["base_mac"] = _normalize_mac(mac_match.group(1))

    hostname_match = re.search(r"^(\S+) uptime is", output, re.MULTILINE)
    if hostname_match:
        data["hostname"] = hostname_match.group(1)

    uptime_match = re.search(r"uptime is\s+(.+)$", output, re.MULTILINE)
    if uptime_match:
        data["uptime"] = uptime_match.group(1).strip()

    image_match = re.search(r"System image file is\s+\"?([^\s\"]+)\"?", output)
    if image_match:
        data["image"] = image_match.group(1)

    return data


def _parse_show_inventory(output: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if not output:
        return data
    chassis_match = re.search(r"NAME:\s*\"Chassis\".*?PID:\s*([^,\s]+).*?SN:\s*(\S+)", output, re.DOTALL)
    if chassis_match:
        data["model"] = chassis_match.group(1)
        data["serial"] = chassis_match.group(2)
    return data


def _parse_interface_brief(output: str) -> List[Dict[str, Any]]:
    interfaces: List[Dict[str, Any]] = []
    if not output:
        return interfaces

    for line in output.splitlines():
        line = line.rstrip()
        if not line or line.lower().startswith("interface"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        name = parts[0]
        ip = parts[1]
        status = " ".join(parts[4:-1]) if len(parts) > 5 else parts[4]
        protocol = parts[-1]
        entry: Dict[str, Any] = {
            "name": name,
            "addresses": [] if ip.lower() == "unassigned" else [ip],
            "status": status,
            "protocol": protocol,
        }
        interfaces.append(entry)
    return interfaces


def _parse_interface_descriptions(output: str) -> Dict[str, Dict[str, str]]:
    results: Dict[str, Dict[str, str]] = {}
    if not output:
        return results
    lines = output.splitlines()
    if lines and "Interface" in lines[0] and "Description" in lines[0]:
        lines = lines[1:]
    for line in lines:
        if not line.strip():
            continue
        parts = line.rstrip().split(None, 3)
        if len(parts) < 4:
            continue
        iface, status, protocol, description = parts[0], parts[1], parts[2], parts[3].strip()
        results[iface] = {
            "status": status,
            "protocol": protocol,
            "description": description,
        }
    return results


def _normalize_mac(value: str) -> str:
    text = value.replace(".", "").replace("-", "").replace(":", "")
    text = text.lower()
    if len(text) == 12:
        return ":".join(text[i : i + 2] for i in range(0, 12, 2))
    return value