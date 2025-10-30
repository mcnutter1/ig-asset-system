import datetime
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency
    from impacket.dcerpc.v5.dcomrt import DCOMConnection  # type: ignore
    from impacket.dcerpc.v5.dcom import wmi as imp_wmi  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    DCOMConnection = None  # type: ignore
    imp_wmi = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import winrm  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    winrm = None  # type: ignore


__all__ = ["collect_windows_asset", "WindowsProbeError"]


class WindowsProbeError(RuntimeError):
    """Raised when the Windows probe cannot gather data."""


_WINRM_COLLECTION_SCRIPT_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'

function Get-AppInventory {
    param([int]$MaxItems = 200)
    $paths = @(
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    $items = foreach ($path in $paths) {
        if (Test-Path $path) {
            Get-ItemProperty -Path $path |
                Where-Object { $_.DisplayName -and $_.DisplayName.Trim() -ne '' } |
                Select-Object DisplayName, DisplayVersion, Publisher, InstallDate
        }
    }
    if (-not $items) { return @() }
    $items | Sort-Object DisplayName -Unique | Select-Object -First $MaxItems
}

$os = Get-CimInstance -ClassName Win32_OperatingSystem |
      Select-Object Caption, Version, BuildNumber, CSName, OSArchitecture, LastBootUpTime, TotalVisibleMemorySize, FreePhysicalMemory
$computer = Get-CimInstance -ClassName Win32_ComputerSystem |
            Select-Object Manufacturer, Model, TotalPhysicalMemory, NumberOfProcessors, NumberOfLogicalProcessors, Name
$processors = Get-CimInstance -ClassName Win32_Processor |
             Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed
$interfaces = Get-CimInstance -ClassName Win32_NetworkAdapterConfiguration -Filter "IPEnabled = TRUE" |
             Select-Object Description, MACAddress, IPAddress, IPSubnet, DefaultIPGateway, DHCPEnabled
$disks = Get-CimInstance -ClassName Win32_LogicalDisk |
         Where-Object { $_.DriveType -eq 3 } |
         Select-Object DeviceID, Size, FreeSpace, FileSystem, VolumeName
$applications = Get-AppInventory -MaxItems __APP_LIMIT__

$payload = @{
    os = $os
    computer = $computer
    processors = $processors
    interfaces = $interfaces
    disks = $disks
    applications = $applications
}

$payload | ConvertTo-Json -Depth 5
"""


def collect_windows_asset(target: Dict[str, Any]) -> Dict[str, Any]:
    """Collect Windows asset data using WMI first, falling back to WinRM."""
    errors: List[str] = []
    data: Optional[Dict[str, Any]] = None
    source: Optional[str] = None

    if DCOMConnection and imp_wmi:
        try:
            data = _collect_via_wmi(target)
            source = "wmi"
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"WMI error: {exc}")
    else:
        errors.append("WMI error: impacket not installed")

    if data is None:
        if winrm:
            try:
                data = _collect_via_winrm(target)
                source = "winrm"
            except Exception as exc:  # pragma: no cover - network dependent
                errors.append(f"WinRM error: {exc}")
        else:
            errors.append("WinRM error: pywinrm not installed")

    if data is None:
        raise WindowsProbeError("; ".join(errors) or "Unable to collect Windows data")

    data.setdefault("probe_source", source)
    if errors:
        data["warnings"] = errors
    return data


def _collect_via_wmi(target: Dict[str, Any]) -> Dict[str, Any]:
    if not DCOMConnection or not imp_wmi:  # pragma: no cover - guard
        raise WindowsProbeError("impacket is required for WMI collection")

    auth = _auth_context(target)
    host = target.get("host")
    if not host:
        raise WindowsProbeError("Missing host for Windows target")

    hashes = target.get("hashes") or ""
    lmhash, nthash = _split_hashes(hashes)

    use_kerberos = bool(target.get("kerberos"))
    kdc_host = target.get("kdc_host")

    namespace = target.get("wmi_namespace", "//./root/cimv2")

    dcom = None
    services = None
    try:
        dcom = DCOMConnection(
            host,
            auth["username"],
            auth["password"],
            auth["domain"],
            lmhash,
            nthash,
            oxidResolver=True,
            doKerberos=use_kerberos,
            kdcHost=kdc_host,
        )
        i_interface = dcom.CoCreateInstanceEx(imp_wmi.CLSID_WbemLevel1Login, imp_wmi.IID_IWbemLevel1Login)
        i_wbem_login = imp_wmi.IWbemLevel1Login(i_interface)
        services = i_wbem_login.NTLMLogin(namespace, None, None)
        i_wbem_login.RemRelease()

        os_rows = _wmi_query(services, "SELECT Caption, Version, BuildNumber, CSName, OSArchitecture, LastBootUpTime, TotalVisibleMemorySize, FreePhysicalMemory FROM Win32_OperatingSystem")
        computer_rows = _wmi_query(services, "SELECT Manufacturer, Model, TotalPhysicalMemory, NumberOfProcessors, NumberOfLogicalProcessors, Name FROM Win32_ComputerSystem")
        processor_rows = _wmi_query(services, "SELECT Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed FROM Win32_Processor")
        interface_rows = _wmi_query(services, "SELECT Description, MACAddress, IPAddress, IPSubnet, DefaultIPGateway, DHCPEnabled FROM Win32_NetworkAdapterConfiguration WHERE IPEnabled = TRUE")
        disk_rows = _wmi_query(services, "SELECT DeviceID, Size, FreeSpace, FileSystem, VolumeName FROM Win32_LogicalDisk WHERE DriveType = 3")

        apps_rows: List[Dict[str, Any]] = []
        collect_apps = _bool_with_default(target.get("collect_applications"), True)
        if collect_apps:
            app_limit = _int_with_default(target.get("applications_limit"), 200)
            if app_limit > 0:
                try:
                    apps_rows = _wmi_query(
                        services,
                        "SELECT Name, Version, Vendor, InstallDate FROM Win32_Product",
                        limit=app_limit,
                    )
                except Exception:  # pragma: no cover - Win32_Product may be disabled
                    apps_rows = []
    finally:
        if services is not None:
            try:
                services.RemRelease()
            except Exception:  # pragma: no cover - cleanup best effort
                pass
        if dcom is not None:
            try:
                dcom.disconnect()
            except Exception:  # pragma: no cover - cleanup best effort
                pass

    return _normalize_windows_payload(
        target,
        os_rows,
        computer_rows,
        processor_rows,
        interface_rows,
        disk_rows,
        apps_rows,
    )


def _collect_via_winrm(target: Dict[str, Any]) -> Dict[str, Any]:
    if not winrm:  # pragma: no cover - guard
        raise WindowsProbeError("pywinrm is required for WinRM collection")

    auth = _auth_context(target)
    host = target.get("host")
    if not host:
        raise WindowsProbeError("Missing host for Windows target")

    use_ssl = _bool_with_default(target.get("winrm_use_ssl"), False)
    port = _int_with_default(target.get("winrm_port"), 5986 if use_ssl else 5985)
    transport_value = target.get("winrm_transport")
    transport = transport_value.strip() if isinstance(transport_value, str) else transport_value
    if not transport:
        transport = "ntlm"
    elif isinstance(transport, str):
        transport = transport.lower()
    validate_cert = _bool_with_default(target.get("winrm_validate_cert"), False)
    read_timeout = _int_with_default(target.get("winrm_read_timeout"), 30)
    operation_timeout = _int_with_default(target.get("winrm_operation_timeout"), 20)

    endpoint = f"http{'s' if use_ssl else ''}://{host}:{port}/wsman"
    session = winrm.Session(
        endpoint,
        auth=(auth["winrm_username"], auth["password"]),
        transport=transport,
        server_cert_validation="validate" if validate_cert else "ignore",
        read_timeout_sec=read_timeout,
        operation_timeout_sec=operation_timeout,
    )

    collect_apps = _bool_with_default(target.get("collect_applications"), True)
    app_limit = _int_with_default(target.get("applications_limit"), 200)
    if not collect_apps or app_limit <= 0:
        app_limit = 0
    script = _WINRM_COLLECTION_SCRIPT_TEMPLATE.replace("__APP_LIMIT__", str(app_limit))
    result = session.run_ps(script)

    if result.status_code != 0:
        stderr = (result.std_err or b"").decode("utf-8", "ignore").strip()
        raise WindowsProbeError(stderr or f"WinRM returned status {result.status_code}")

    stdout = (result.std_out or b"").decode("utf-8", "ignore").strip()
    if not stdout:
        raise WindowsProbeError("WinRM returned no data")

    payload = json.loads(stdout)

    return _normalize_windows_payload_from_json(target, payload)


def _normalize_windows_payload(
    target: Dict[str, Any],
    os_rows: Sequence[Dict[str, Any]],
    computer_rows: Sequence[Dict[str, Any]],
    processor_rows: Sequence[Dict[str, Any]],
    interface_rows: Sequence[Dict[str, Any]],
    disk_rows: Sequence[Dict[str, Any]],
    apps_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    os_entry = os_rows[0] if os_rows else {}
    computer_entry = computer_rows[0] if computer_rows else {}

    os_info: Dict[str, Any] = {
        "family": "windows",
        "caption": os_entry.get("Caption"),
        "version": os_entry.get("Version"),
        "build": os_entry.get("BuildNumber"),
        "architecture": os_entry.get("OSArchitecture"),
    }

    hostname = os_entry.get("CSName") or computer_entry.get("Name")
    if hostname:
        os_info["hostname"] = hostname

    last_boot = _parse_wmi_datetime(os_entry.get("LastBootUpTime"))
    if last_boot:
        os_info["last_boot"] = last_boot

    memory_metrics: Dict[str, Any] = {}
    total_visible = _to_int(os_entry.get("TotalVisibleMemorySize"))
    free_physical = _to_int(os_entry.get("FreePhysicalMemory"))
    if total_visible:
        memory_metrics["total_bytes"] = total_visible * 1024
    if free_physical is not None:
        memory_metrics["free_bytes"] = free_physical * 1024

    hardware: Dict[str, Any] = {}
    if computer_entry.get("Manufacturer"):
        hardware["manufacturer"] = computer_entry["Manufacturer"]
    if computer_entry.get("Model"):
        hardware["model"] = computer_entry["Model"]
    total_physical = _to_int(computer_entry.get("TotalPhysicalMemory"))
    if total_physical:
        hardware["memory_bytes"] = total_physical
    logical_processors = _to_int(computer_entry.get("NumberOfLogicalProcessors"))
    if logical_processors is not None:
        hardware["logical_processors"] = logical_processors
    physical_processors = _to_int(computer_entry.get("NumberOfProcessors"))
    if physical_processors is not None:
        hardware["physical_processors"] = physical_processors

    processors: List[Dict[str, Any]] = []
    for row in processor_rows:
        name = _clean_string(row.get("Name"))
        if not name:
            continue
        entry: Dict[str, Any] = {"name": name}
        cores = _to_int(row.get("NumberOfCores"))
        if cores is not None:
            entry["cores"] = cores
        logical = _to_int(row.get("NumberOfLogicalProcessors"))
        if logical is not None:
            entry["logical_processors"] = logical
        clock = _to_int(row.get("MaxClockSpeed"))
        if clock is not None:
            entry["max_clock_mhz"] = clock
        processors.append(entry)
    if processors:
        hardware["processors"] = processors

    interfaces: List[Dict[str, Any]] = []
    ips: List[str] = []
    primary_mac: Optional[str] = None

    for row in interface_rows:
        addresses = _ensure_list(row.get("IPAddress"))
        normalized_addresses = [_clean_string(addr) for addr in addresses if _clean_string(addr)]
        mac = _clean_mac(row.get("MACAddress"))
        entry = {
            "name": _clean_string(row.get("Description")) or "interface",
            "addresses": normalized_addresses,
            "mac": mac,
            "is_up": True,
            "dhcp": bool(row.get("DHCPEnabled")),
        }
        subnet = _ensure_list(row.get("IPSubnet"))
        if normalized_addresses and subnet and len(subnet) == len(normalized_addresses):
            entry["prefixes"] = [s for s in subnet if s]
        gateway = _ensure_list(row.get("DefaultIPGateway"))
        if gateway:
            entry["gateways"] = [g for g in gateway if g]
        interfaces.append(entry)
        for addr in normalized_addresses:
            if addr and addr not in ips:
                ips.append(addr)
        if mac and not primary_mac and not mac.startswith("00:00:00"):
            primary_mac = mac

    disks: List[Dict[str, Any]] = []
    for row in disk_rows:
        size_bytes = _to_int(row.get("Size"))
        free_bytes = _to_int(row.get("FreeSpace"))
        used_bytes = size_bytes - free_bytes if size_bytes is not None and free_bytes is not None else None
        capacity = None
        if size_bytes and used_bytes is not None and size_bytes > 0:
            capacity = f"{(used_bytes / size_bytes) * 100:.1f}%"
        disk_entry = {
            "filesystem": _clean_string(row.get("FileSystem")) or _clean_string(row.get("DeviceID")),
            "mount": _clean_string(row.get("DeviceID")),
            "size_kb": size_bytes // 1024 if size_bytes else None,
            "used_kb": used_bytes // 1024 if used_bytes is not None else None,
            "available_kb": free_bytes // 1024 if free_bytes is not None else None,
            "capacity": capacity,
            "volume_name": _clean_string(row.get("VolumeName")),
        }
        disks.append({k: v for k, v in disk_entry.items() if v is not None})

    applications: List[Dict[str, Any]] = []
    seen_apps: set = set()
    for row in apps_rows:
        name = _clean_string(row.get("Name"))
        if not name or name.lower() in seen_apps:
            continue
        seen_apps.add(name.lower())
        entry: Dict[str, Any] = {"name": name}
        version = _clean_string(row.get("Version"))
        if version:
            entry["version"] = version
        vendor = _clean_string(row.get("Vendor"))
        if vendor:
            entry["publisher"] = vendor
        install = _parse_install_date(row.get("InstallDate"))
        if install:
            entry["install_date"] = install
        applications.append(entry)

    metrics: Dict[str, Any] = {}
    if memory_metrics:
        metrics["memory"] = memory_metrics
    if disks:
        metrics["disks"] = disks

    return {
        "name": hostname or target.get("host"),
        "os": {k: v for k, v in os_info.items() if v},
        "hardware": hardware or None,
        "network": {"interfaces": interfaces} if interfaces else None,
        "ips": ips,
        "mac": primary_mac,
        "metrics": metrics or None,
        "applications": applications,
    }


def _normalize_windows_payload_from_json(target: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    os_entry = _as_dict(payload.get("os"))
    computer_entry = _as_dict(payload.get("computer"))
    processor_entries = _as_list(payload.get("processors"))
    interface_entries = _as_list(payload.get("interfaces"))
    disk_entries = _as_list(payload.get("disks"))
    apps_entries = _as_list(payload.get("applications"))

    os_info: Dict[str, Any] = {
        "family": "windows",
        "caption": _clean_string(os_entry.get("Caption")),
        "version": _clean_string(os_entry.get("Version")),
        "build": _clean_string(os_entry.get("BuildNumber")),
        "architecture": _clean_string(os_entry.get("OSArchitecture")),
    }
    hostname = _clean_string(os_entry.get("CSName")) or _clean_string(computer_entry.get("Name"))
    if hostname:
        os_info["hostname"] = hostname
    last_boot = _parse_wmi_datetime(os_entry.get("LastBootUpTime"))
    if last_boot:
        os_info["last_boot"] = last_boot

    memory_metrics: Dict[str, Any] = {}
    total_visible = _to_int(os_entry.get("TotalVisibleMemorySize"))
    free_physical = _to_int(os_entry.get("FreePhysicalMemory"))
    if total_visible:
        memory_metrics["total_bytes"] = total_visible * 1024
    if free_physical is not None:
        memory_metrics["free_bytes"] = free_physical * 1024

    hardware: Dict[str, Any] = {}
    if computer_entry.get("Manufacturer"):
        hardware["manufacturer"] = _clean_string(computer_entry.get("Manufacturer"))
    if computer_entry.get("Model"):
        hardware["model"] = _clean_string(computer_entry.get("Model"))
    total_physical = _to_int(computer_entry.get("TotalPhysicalMemory"))
    if total_physical:
        hardware["memory_bytes"] = total_physical
    logical_processors = _to_int(computer_entry.get("NumberOfLogicalProcessors"))
    if logical_processors is not None:
        hardware["logical_processors"] = logical_processors
    physical_processors = _to_int(computer_entry.get("NumberOfProcessors"))
    if physical_processors is not None:
        hardware["physical_processors"] = physical_processors

    processors: List[Dict[str, Any]] = []
    for row in processor_entries:
        name = _clean_string(row.get("Name"))
        if not name:
            continue
        entry: Dict[str, Any] = {"name": name}
        cores = _to_int(row.get("NumberOfCores"))
        if cores is not None:
            entry["cores"] = cores
        logical = _to_int(row.get("NumberOfLogicalProcessors"))
        if logical is not None:
            entry["logical_processors"] = logical
        clock = _to_int(row.get("MaxClockSpeed"))
        if clock is not None:
            entry["max_clock_mhz"] = clock
        processors.append(entry)
    if processors:
        hardware["processors"] = processors

    interfaces: List[Dict[str, Any]] = []
    ips: List[str] = []
    primary_mac: Optional[str] = None
    for row in interface_entries:
        addresses = [_clean_string(addr) for addr in _ensure_list(row.get("IPAddress")) if _clean_string(addr)]
        mac = _clean_mac(row.get("MACAddress"))
        entry = {
            "name": _clean_string(row.get("Description")) or "interface",
            "addresses": addresses,
            "mac": mac,
            "is_up": True,
            "dhcp": bool(row.get("DHCPEnabled")),
        }
        subnet = _as_list(row.get("IPSubnet"))
        if subnet:
            entry["prefixes"] = [s for s in subnet if s]
        gateways = _as_list(row.get("DefaultIPGateway"))
        if gateways:
            entry["gateways"] = [g for g in gateways if g]
        interfaces.append(entry)
        for addr in addresses:
            if addr and addr not in ips:
                ips.append(addr)
        if mac and not primary_mac and not mac.startswith("00:00:00"):
            primary_mac = mac

    disks: List[Dict[str, Any]] = []
    for row in disk_entries:
        size_bytes = _to_int(row.get("Size"))
        free_bytes = _to_int(row.get("FreeSpace"))
        used_bytes = size_bytes - free_bytes if size_bytes is not None and free_bytes is not None else None
        capacity = None
        if size_bytes and used_bytes is not None and size_bytes > 0:
            capacity = f"{(used_bytes / size_bytes) * 100:.1f}%"
        disk_entry = {
            "filesystem": _clean_string(row.get("FileSystem")) or _clean_string(row.get("DeviceID")),
            "mount": _clean_string(row.get("DeviceID")),
            "size_kb": size_bytes // 1024 if size_bytes else None,
            "used_kb": used_bytes // 1024 if used_bytes is not None else None,
            "available_kb": free_bytes // 1024 if free_bytes is not None else None,
            "capacity": capacity,
            "volume_name": _clean_string(row.get("VolumeName")),
        }
        disks.append({k: v for k, v in disk_entry.items() if v is not None})

    applications: List[Dict[str, Any]] = []
    seen_apps: set = set()
    for row in apps_entries:
        name = _clean_string(row.get("DisplayName")) or _clean_string(row.get("Name"))
        if not name or name.lower() in seen_apps:
            continue
        seen_apps.add(name.lower())
        entry: Dict[str, Any] = {"name": name}
        version = _clean_string(row.get("DisplayVersion")) or _clean_string(row.get("Version"))
        if version:
            entry["version"] = version
        publisher = _clean_string(row.get("Publisher")) or _clean_string(row.get("Vendor"))
        if publisher:
            entry["publisher"] = publisher
        install = _parse_install_date(row.get("InstallDate"))
        if install:
            entry["install_date"] = install
        applications.append(entry)

    metrics: Dict[str, Any] = {}
    if memory_metrics:
        metrics["memory"] = memory_metrics
    if disks:
        metrics["disks"] = disks

    return {
        "name": hostname or target.get("host"),
        "os": {k: v for k, v in os_info.items() if v},
        "hardware": hardware or None,
        "network": {"interfaces": interfaces} if interfaces else None,
        "ips": ips,
        "mac": primary_mac,
        "metrics": metrics or None,
        "applications": applications,
    }


def _wmi_query(service: Any, query: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    enum = service.ExecQuery(query)
    try:
        count = 0
        while True:
            try:
                items = enum.Next(0xFFFFFFFF, 1)
            except Exception:
                break
            if not items:
                break
            obj = items[0]
            props = obj.getProperties()
            results.append(_extract_wmi_properties(props))
            obj.RemRelease()
            count += 1
            if limit and count >= limit:
                break
    finally:
        try:
            enum.RemRelease()
        except Exception:  # pragma: no cover - cleanup best effort
            pass
    return results


def _extract_wmi_properties(props: Dict[str, Any]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for key in ("properties", "systemProperties"):
        for entry in props.get(key, []):
            name = entry.get("name")
            if not name:
                continue
            if name in data:
                continue
            value = entry.get("value")
            data[name] = _normalize_wmi_value(value)
    return data


def _normalize_wmi_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore").strip()
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        normalized = []
        for item in value:
            norm = _normalize_wmi_value(item)
            if norm not in (None, ""):
                normalized.append(norm)
        return normalized
    return value


def _auth_context(target: Dict[str, Any]) -> Dict[str, Any]:
    raw_username = target.get("username")
    password = target.get("password")
    if not raw_username:
        raise WindowsProbeError("Missing username for Windows target")
    if password is None:
        raise WindowsProbeError("Missing password for Windows target")

    domain = target.get("domain") or ""
    username = raw_username
    winrm_username = raw_username

    if "\\" in raw_username:
        domain_part, user_part = raw_username.split("\\", 1)
        username = user_part
        if not domain:
            domain = domain_part
    elif "@" in raw_username:
        user_part, domain_part = raw_username.split("@", 1)
        username = user_part
        if not domain:
            domain = domain_part
    else:
        if domain:
            winrm_username = f"{domain}\\{raw_username}"

    if not winrm_username:
        winrm_username = f"{domain}\\{username}" if domain else username

    return {
        "username": username,
        "password": password,
        "domain": domain,
        "winrm_username": winrm_username,
    }


def _split_hashes(hashes: str) -> Tuple[str, str]:
    if not hashes:
        return "", ""
    parts = hashes.split(":")
    if len(parts) == 2:
        return parts[0] or "", parts[1] or ""
    return "", parts[0]


def _clean_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _clean_mac(value: Any) -> Optional[str]:
    text = _clean_string(value)
    if not text:
        return None
    text = text.replace("-", ":").lower()
    if len(text) == 12 and ":" not in text:
        text = ":".join(text[i : i + 2] for i in range(0, 12, 2))
    return text


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, dict) else {}
    return {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _int_with_default(value: Any, default: int) -> int:
    parsed = _to_int(value)
    return parsed if parsed is not None else default


def _bool_with_default(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "y", "on"):
            return True
        if lowered in ("false", "0", "no", "n", "off"):
            return False
        return default if lowered == "" else bool(lowered)
    return bool(value)


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            if value.lower().startswith("0x"):
                return int(value, 16)
            return int(float(value))
        except ValueError:
            return None
    return None


def _parse_wmi_datetime(value: Any) -> Optional[str]:
    text = _clean_string(value)
    if not text:
        return None
    try:
        base = text[:14]
        dt = datetime.datetime.strptime(base, "%Y%m%d%H%M%S")
        if len(text) >= 22 and text[14] == ".":
            micro = int(text[15:21])
            dt = dt.replace(microsecond=micro)
        if len(text) >= 25:
            sign = 1 if text[21] == "+" else -1
            minutes = int(text[22:25])
            offset = datetime.timedelta(minutes=minutes * sign)
            dt = dt.replace(tzinfo=datetime.timezone(offset))
        return dt.isoformat()
    except Exception:
        return text


def _parse_install_date(value: Any) -> Optional[str]:
    text = _clean_string(value)
    if not text:
        return None
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.datetime.strptime(text, "%Y%m%d").date().isoformat()
        if len(text) == 14 and text.isdigit():
            return datetime.datetime.strptime(text[:8], "%Y%m%d").date().isoformat()
    except Exception:
        return None
    return None
