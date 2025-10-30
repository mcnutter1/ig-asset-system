import json
import re
import socket
import time

import paramiko
import requests
import yaml


DEFAULT_INTERVAL = 120


def ping(host, timeout=1):
    """Lightweight reachability check using DNS resolution."""
    try:
        socket.gethostbyname(host)
        return True
    except Exception:
        return False


def safe_json_loads(data):
    if not data:
        return None
    try:
        return json.loads(data)
    except Exception:
        return None


def parse_key_value_lines(data):
    info = {}
    for line in data.splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        info[key.strip()] = value.strip().strip('"')
    return info


def extract_int(value):
    if not value:
        return None
    match = re.search(r'(\d+)', value.replace(',', ''))
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def parse_ifconfig(raw):
    interfaces = []
    current = None
    mac_pattern = re.compile(r'(?:ether|lladdr|address)\s+([0-9A-Fa-f:]{6,})')
    for line in raw.splitlines():
        if not line.strip():
            continue
        if not line.startswith((' ', '\t')):
            name = line.split(':', 1)[0].strip()
            flags_section = ''
            if '<' in line and '>' in line:
                flags_section = line.split('<', 1)[1].split('>', 1)[0]
            is_up = 'UP' in flags_section.split(',') if flags_section else 'UP' in line
            current = {'name': name, 'addresses': [], 'mac': None, 'is_up': bool(is_up)}
            interfaces.append(current)
        else:
            if current is None:
                continue
            stripped = line.strip()
            if stripped.startswith('inet ') or stripped.startswith('inet6 '):
                parts = stripped.split()
                if len(parts) >= 2:
                    current['addresses'].append(parts[1])
            else:
                match = mac_pattern.search(stripped)
                if match:
                    current['mac'] = match.group(1).lower()
    return interfaces


def parse_df_output(raw):
    disks = []
    if not raw:
        return disks
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        return disks
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        filesystem = parts[0]
        try:
            size_kb = int(parts[1])
            used_kb = int(parts[2])
            avail_kb = int(parts[3])
        except (TypeError, ValueError):
            size_kb = used_kb = avail_kb = None
        capacity = parts[4]
        mount_point = ' '.join(parts[5:])
        disks.append({
            'filesystem': filesystem,
            'size_kb': size_kb,
            'used_kb': used_kb,
            'available_kb': avail_kb,
            'capacity': capacity,
            'mount': mount_point
        })
    return disks


def parse_uptime_load(raw):
    if not raw:
        return None
    match = re.search(r'load averages?:\s*([0-9.,\s]+)', raw)
    if not match:
        return None
    numbers = [item.strip() for item in match.group(1).split(',') if item.strip()]
    if len(numbers) < 3:
        return None
    try:
        return {
            '1m': float(numbers[0]),
            '5m': float(numbers[1]),
            '15m': float(numbers[2])
        }
    except (TypeError, ValueError):
        return None


def run_ssh_command(ssh, command, timeout=8):
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    out = stdout.read().decode('utf-8', 'ignore').strip()
    err = stderr.read().decode('utf-8', 'ignore').strip()
    return out, err


def connect_ssh(target):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {
        'hostname': target['host'],
        'username': target.get('username'),
        'timeout': target.get('timeout', 10)
    }
    if target.get('port'):
        kwargs['port'] = target['port']
    if target.get('password'):
        kwargs['password'] = target['password']
    if target.get('ssh_key'):
        kwargs['key_filename'] = target['ssh_key']
    ssh.connect(**kwargs)
    return ssh


def collect_unix_os_info(ssh, os_hint='linux'):
    hint = (os_hint or 'unknown').lower()
    if 'bsd' in hint:
        hint = 'bsd'
    os_info = {'family': hint}

    uname_s, _ = run_ssh_command(ssh, 'uname -s')
    kernel_name = (uname_s or '').strip()
    kernel_lower = kernel_name.lower()
    if kernel_name:
        os_info['kernel_name'] = kernel_name
        if kernel_lower in ('openbsd', 'freebsd', 'netbsd', 'dragonfly'):
            os_info['family'] = 'bsd'
            distro = kernel_name if kernel_name else kernel_lower
            os_info['distribution'] = distro
            os_info['id'] = kernel_lower
        elif 'bsd' in kernel_lower:
            os_info['family'] = 'bsd'
            os_info['distribution'] = kernel_name
        elif kernel_lower in ('linux', 'gnu/linux'):
            os_info['family'] = 'linux'
        elif kernel_lower in ('darwin', 'macos', 'mac os x'):
            os_info['family'] = 'macos'
        else:
            os_info['family'] = kernel_lower or os_info['family']

    uname_r, _ = run_ssh_command(ssh, 'uname -r')
    if uname_r:
        os_info['kernel_release'] = uname_r
    uname_m, _ = run_ssh_command(ssh, 'uname -m')
    if uname_m:
        os_info['architecture'] = uname_m
    hostname, _ = run_ssh_command(ssh, 'hostname')
    if hostname:
        os_info['hostname'] = hostname

    os_release_raw, _ = run_ssh_command(ssh, 'cat /etc/os-release')
    if os_release_raw:
        kv = parse_key_value_lines(os_release_raw)
        if kv:
            os_info['name'] = kv.get('PRETTY_NAME') or kv.get('NAME')
            os_info['version'] = kv.get('VERSION') or kv.get('VERSION_ID')
            os_info['id'] = kv.get('ID')
            if kv.get('ID'):
                distro_id = kv['ID'].lower()
                if 'bsd' in distro_id:
                    os_info['family'] = 'bsd'
                    os_info['distribution'] = kv.get('NAME') or kernel_name or distro_id
                else:
                    os_info['family'] = distro_id
    else:
        if 'bsd' in kernel_lower or 'bsd' in hint:
            os_info['family'] = 'bsd'
            vers, _ = run_ssh_command(ssh, 'sysctl -n kern.version')
            if vers:
                os_info['version'] = vers.strip()
            name, _ = run_ssh_command(ssh, 'sysctl -n kern.ostype')
            if name:
                os_info['name'] = name.strip()
                os_info.setdefault('distribution', name.strip())
                os_info.setdefault('id', name.strip().lower())

    if 'bsd' in os_info.get('family', '') and not os_info.get('distribution') and kernel_name:
        os_info['distribution'] = kernel_name
    if os_info.get('distribution') and not os_info.get('id'):
        os_info['id'] = os_info['distribution'].lower().replace(' ', '-')

    return os_info


def collect_unix_network_info(ssh):
    interfaces = []
    ip_addresses = []
    primary_mac = None

    addr_raw, _ = run_ssh_command(ssh, 'ip -j addr show')
    addr_data = safe_json_loads(addr_raw)
    if isinstance(addr_data, list):
        link_raw, _ = run_ssh_command(ssh, 'ip -j link show')
        link_data = safe_json_loads(link_raw) or []
        mac_lookup = {item.get('ifname'): item.get('address') for item in link_data if item.get('ifname')}
        for iface in addr_data:
            name = iface.get('ifname')
            if not name:
                continue
            addresses = []
            for addr in iface.get('addr_info', []):
                local = addr.get('local')
                if not local:
                    continue
                prefix = addr.get('prefixlen')
                formatted = f"{local}/{prefix}" if prefix is not None else local
                addresses.append(formatted)
                if local not in ip_addresses:
                    ip_addresses.append(local)
            entry = {
                'name': name,
                'addresses': addresses,
                'mac': mac_lookup.get(name),
                'is_up': 'UP' in (iface.get('flags') or [])
            }
            interfaces.append(entry)
        for entry in interfaces:
            mac = entry.get('mac')
            if mac and not primary_mac and not entry['name'].startswith(('lo', 'lo0')):
                primary_mac = mac

    if not interfaces:
        ifconfig_raw, _ = run_ssh_command(ssh, 'ifconfig -a')
        if ifconfig_raw.strip():
            interfaces = parse_ifconfig(ifconfig_raw)
            for iface in interfaces:
                for addr in iface.get('addresses', []):
                    ip = addr.split('%')[0].split('/')[0]
                    if ip and ip not in ip_addresses:
                        ip_addresses.append(ip)
                mac = iface.get('mac')
                if mac and not primary_mac and not iface['name'].startswith(('lo', 'lo0')):
                    primary_mac = mac
    if not interfaces:
        ifconfig_raw, _ = run_ssh_command(ssh, 'ifconfig')
        if ifconfig_raw.strip():
            interfaces = parse_ifconfig(ifconfig_raw)
            for iface in interfaces:
                for addr in iface.get('addresses', []):
                    ip = addr.split('%')[0].split('/')[0]
                    if ip and ip not in ip_addresses:
                        ip_addresses.append(ip)
                mac = iface.get('mac')
                if mac and not primary_mac and not iface['name'].startswith(('lo', 'lo0')):
                    primary_mac = mac

    if not ip_addresses:
        for iface in interfaces:
            for addr in iface.get('addresses', []):
                ip = addr.split('%')[0].split('/')[0]
                if ip and ip not in ip_addresses:
                    ip_addresses.append(ip)

    return {
        'interfaces': interfaces,
        'primary_mac': primary_mac,
        'addresses': ip_addresses
    }


def collect_unix_hardware_info(ssh, os_family):
    hardware = {}

    lscpu_json_raw, _ = run_ssh_command(ssh, 'lscpu -J')
    lscpu_data = safe_json_loads(lscpu_json_raw)
    if isinstance(lscpu_data, dict):
        for entry in lscpu_data.get('lscpu', []):
            field = (entry.get('field') or '').strip(':').lower()
            data = entry.get('data')
            if not field or data is None:
                continue
            if field == 'model name':
                hardware['cpu_model'] = data
            elif field == 'cpu(s)':
                try:
                    hardware['cpu_count'] = int(data)
                except (TypeError, ValueError):
                    hardware['cpu_count'] = data
            elif field == 'architecture':
                hardware['architecture'] = data

    if 'cpu_model' not in hardware or 'cpu_count' not in hardware:
        lscpu_text, _ = run_ssh_command(ssh, 'lscpu')
        for line in lscpu_text.splitlines():
            if 'Model name' in line and 'cpu_model' not in hardware:
                hardware['cpu_model'] = line.split(':', 1)[1].strip()
            elif 'CPU(s):' in line and 'cpu_count' not in hardware:
                value = line.split(':', 1)[1].strip()
                if value.isdigit():
                    hardware['cpu_count'] = int(value)
            elif 'Architecture:' in line and 'architecture' not in hardware:
                hardware['architecture'] = line.split(':', 1)[1].strip()

    if 'cpu_count' not in hardware:
        nproc_raw, _ = run_ssh_command(ssh, 'nproc')
        if nproc_raw.strip().isdigit():
            hardware['cpu_count'] = int(nproc_raw.strip())

    if os_family.startswith('bsd'):
        model, _ = run_ssh_command(ssh, 'sysctl -n hw.model')
        if model and 'cpu_model' not in hardware:
            hardware['cpu_model'] = model.strip()
        cpu_count, _ = run_ssh_command(ssh, 'sysctl -n hw.ncpu')
        if cpu_count.strip().isdigit():
            hardware['cpu_count'] = int(cpu_count.strip())
        mem_raw, _ = run_ssh_command(ssh, 'sysctl -n hw.memsize')
        if not mem_raw.strip():
            mem_raw, _ = run_ssh_command(ssh, 'sysctl -n hw.physmem')
        mem_bytes = extract_int(mem_raw)
        if mem_bytes:
            hardware['memory_bytes'] = mem_bytes
    else:
        meminfo_raw, _ = run_ssh_command(ssh, 'grep MemTotal /proc/meminfo')
        mem_kb = extract_int(meminfo_raw)
        if mem_kb:
            hardware['memory_bytes'] = mem_kb * 1024

    if 'cpu_model' in hardware:
        hardware['cpu_model'] = hardware['cpu_model'].strip()

    return hardware


def collect_unix_resource_metrics(ssh, os_family):
    metrics = {}

    uptime_raw, _ = run_ssh_command(ssh, 'uptime')
    load = parse_uptime_load(uptime_raw)
    if load:
        metrics['cpu_load'] = load

    family = (os_family or '').lower()
    memory = {}
    if family.startswith('bsd'):
        physmem_raw, _ = run_ssh_command(ssh, 'sysctl -n hw.physmem')
        total_bytes = extract_int(physmem_raw)
        if total_bytes:
            memory['total_bytes'] = total_bytes
        usermem_raw, _ = run_ssh_command(ssh, 'sysctl -n hw.usermem')
        user_bytes = extract_int(usermem_raw)
        if user_bytes:
            memory['user_bytes'] = user_bytes
        pagesize_raw, _ = run_ssh_command(ssh, 'sysctl -n hw.pagesize')
        page_size = extract_int(pagesize_raw)
        free_pages_raw, _ = run_ssh_command(ssh, 'sysctl -n vm.stats.vm.v_free_count')
        free_pages = extract_int(free_pages_raw)
        if page_size and free_pages:
            memory['free_bytes'] = page_size * free_pages
        swap_list_raw, _ = run_ssh_command(ssh, 'swapctl -l -k')
        swap_total_kb = 0
        swap_free_kb = 0
        if swap_list_raw:
            lines = [line for line in swap_list_raw.splitlines() if line.strip()]
            for line in lines[1:]:
                parts = line.split()
                if len(parts) < 4:
                    continue
                try:
                    total_kb = int(parts[1])
                    used_kb = int(parts[2])
                    avail_kb = int(parts[3])
                except (TypeError, ValueError):
                    continue
                swap_total_kb += total_kb
                swap_free_kb += avail_kb
        if swap_total_kb:
            memory['swap_total_bytes'] = swap_total_kb * 1024
        if swap_free_kb:
            memory['swap_free_bytes'] = swap_free_kb * 1024
    else:
        meminfo_raw, _ = run_ssh_command(ssh, 'cat /proc/meminfo')
        if meminfo_raw:
            meminfo = {}
            for line in meminfo_raw.splitlines():
                if ':' not in line:
                    continue
                key, value = line.split(':', 1)
                key = key.strip()
                num = extract_int(value)
                if num is None:
                    continue
                if 'kb' in value.lower():
                    num *= 1024
                meminfo[key] = num
            if meminfo:
                memory['total_bytes'] = meminfo.get('MemTotal')
                memory['available_bytes'] = meminfo.get('MemAvailable')
                memory['free_bytes'] = meminfo.get('MemFree')
                memory['swap_total_bytes'] = meminfo.get('SwapTotal')
                memory['swap_free_bytes'] = meminfo.get('SwapFree')
    if memory:
        metrics['memory'] = {k: v for k, v in memory.items() if v is not None}

    df_raw, _ = run_ssh_command(ssh, 'df -P -k')
    disks = parse_df_output(df_raw)
    if disks:
        metrics['disks'] = disks

    return metrics


def current_timestamp():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def unix_probe(target, os_hint='linux'):
    host = target['host']
    asset = {
        'name': host,
        'type': target.get('asset_type') or ('server' if os_hint not in ('workstation', 'desktop') else 'workstation'),
        'ips': [host],
        'attributes': {'os': {'family': os_hint}},
        'mac': None
    }

    if target.get('asset_id'):
        asset['id'] = target['asset_id']

    username = target.get('username')
    if not username:
        asset['attributes'].setdefault('poller', {})['error'] = 'Missing SSH username'
        asset['attributes']['poller']['collected_at'] = current_timestamp()
        return asset

    ssh = None
    try:
        ssh = connect_ssh(target)
        os_info = collect_unix_os_info(ssh, os_hint or 'linux')
        asset['attributes']['os'] = os_info
        if os_info.get('hostname'):
            asset['name'] = os_info['hostname']

        network_info = collect_unix_network_info(ssh)
        interfaces = network_info.get('interfaces', [])
        if interfaces:
            asset['attributes']['network'] = {'interfaces': interfaces}
        ips = network_info.get('addresses') or []
        if ips:
            asset['ips'] = ips
        primary_mac = network_info.get('primary_mac')
        if primary_mac:
            asset['mac'] = primary_mac

        hardware_info = collect_unix_hardware_info(ssh, os_info.get('family', ''))
        if hardware_info:
            asset['attributes']['hardware'] = hardware_info

        metrics_info = collect_unix_resource_metrics(ssh, os_info.get('family', ''))
        if metrics_info:
            asset['attributes']['metrics'] = metrics_info

    except Exception as exc:
        asset.setdefault('attributes', {}).setdefault('poller', {})['error'] = str(exc)
    finally:
        if ssh:
            ssh.close()

    asset.setdefault('attributes', {}).setdefault('poller', {})['collected_at'] = current_timestamp()
    return asset


def windows_probe(target):
    host = target['host']
    asset = {
        'name': host,
        'type': target.get('asset_type') or 'workstation',
        'ips': [host],
        'attributes': {
            'os': {
                'family': 'windows',
                'hostname': host
            }
        },
        'mac': None
    }
    if target.get('asset_id'):
        asset['id'] = target['asset_id']
    asset['attributes'].setdefault('poller', {})['collected_at'] = current_timestamp()
    return asset


def iterate_targets(cfg):
    if isinstance(cfg.get('targets'), list):
        for entry in cfg['targets']:
            yield entry
        return
    for key in ('linux', 'bsd', 'openbsd', 'freebsd', 'netbsd', 'windows'):
        for entry in cfg.get(key, []) or []:
            enriched = dict(entry)
            enriched.setdefault('os', key)
            yield enriched


def push_update(cfg, asset, online=True):
    url = cfg['api']['base_url'] + '?action=agent_push&token=' + cfg['api']['api_key']
    try:
        requests.post(url, json={'asset': asset, 'online_status': online}, timeout=10)
    except Exception:
        pass


def main():
    with open('config.yml', 'r') as fh:
        cfg = yaml.safe_load(fh)
    interval = cfg.get('interval_seconds', DEFAULT_INTERVAL)

    while True:
        for target in iterate_targets(cfg):
            os_hint = (target.get('os') or target.get('type') or '').lower()
            if os_hint in ('windows', 'win', 'win32'):
                asset = windows_probe(target)
            else:
                asset = unix_probe(target, os_hint or 'linux')
            online = ping(target['host'])
            push_update(cfg, asset, online)
        time.sleep(interval)


if __name__ == '__main__':
    main()
