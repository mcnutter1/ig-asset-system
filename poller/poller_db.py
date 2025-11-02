#!/usr/bin/env python3
"""
Database-driven Asset Tracker Poller

This poller queries the database for polling targets and status,
making it controllable from the web UI.
"""

import time
import json
import requests
import paramiko
import socket
import mysql.connector
import sys
import os
import re
import ipaddress
import copy
import hashlib
from windows_collectors import collect_windows_asset, WindowsProbeError
from cisco_collectors import collect_cisco_asset, CiscoProbeError
try:
    import dns.resolver as dns_resolver
except ImportError:  # pragma: no cover - optional dependency
    dns_resolver = None
from datetime import datetime
from config_loader import load_php_config


def safe_json_loads(data):
    if not data:
        return None
    try:
        return json.loads(data)
    except Exception:
        return None


def parse_key_value_lines(data):
    info = {}
    for line in (data or '').splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        info[key.strip()] = value.strip().strip('"')
    return info


def extract_int(value):
    if not value:
        return None
    match = re.search(r'(\d+)', str(value).replace(',', ''))
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
    for line in (raw or '').splitlines():
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
                    if not is_loopback_address(parts[1]):
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


def normalize_ip_literal(value):
    if not value:
        return ''
    base = str(value).split('%')[0]
    base = base.split('/')[0]
    return base.strip()


def is_loopback_address(value):
    literal = normalize_ip_literal(value)
    if not literal:
        return False
    try:
        return ipaddress.ip_address(literal).is_loopback
    except ValueError:
        return False


def is_ip_literal(value):
    literal = normalize_ip_literal(value)
    if not literal:
        return False
    try:
        ipaddress.ip_address(literal)
        return True
    except ValueError:
        return False


def run_ssh_command(ssh, command, timeout=10):
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    out = stdout.read().decode('utf-8', 'ignore').strip()
    err = stderr.read().decode('utf-8', 'ignore').strip()
    return out, err


def connect_ssh(target, timeout=10):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {
        'hostname': target['host'],
        'username': target.get('username') or None,
        'timeout': timeout
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
            os_info['id'] = kv.get('ID') or os_info.get('id')
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
                clean_name = name.strip()
                os_info['name'] = clean_name
                os_info.setdefault('distribution', clean_name)
                os_info.setdefault('id', clean_name.lower())

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
                if is_loopback_address(local):
                    continue
                formatted = f"{local}/{prefix}" if prefix is not None else local
                addresses.append(formatted)
                normalized_local = normalize_ip_literal(local)
                if normalized_local and normalized_local not in ip_addresses:
                    ip_addresses.append(normalized_local)
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
                    ip = normalize_ip_literal(addr)
                    if ip and not is_loopback_address(ip) and ip not in ip_addresses:
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
                    ip = normalize_ip_literal(addr)
                    if ip and not is_loopback_address(ip) and ip not in ip_addresses:
                        ip_addresses.append(ip)
                mac = iface.get('mac')
                if mac and not primary_mac and not iface['name'].startswith(('lo', 'lo0')):
                    primary_mac = mac

    if not ip_addresses:
        for iface in interfaces:
            for addr in iface.get('addresses', []):
                ip = normalize_ip_literal(addr)
                if ip and not is_loopback_address(ip) and ip not in ip_addresses:
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

    os_family_lower = (os_family or '').lower()
    if os_family_lower.startswith('bsd'):
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
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


DEFAULT_SANITIZATION_RULES = {
    "version": 1,
    "meta": {
        "description": "Default poller sanitization rules"
    },
    "rules": {
        "ip_addresses": {
            "exclude": {
                "cidr": ["127.0.0.0/8", "::1/128", "fe80::/10"],
                "exact": [],
                "prefix": [],
                "suffix": []
            }
        }
    }
}


class SanitizationManager:
    def __init__(self, path):
        self.path = path
        self.rules = copy.deepcopy(DEFAULT_SANITIZATION_RULES)
        self.exclude_cidrs = []
        self.exclude_exact = set()
        self.exclude_prefix = []
        self.exclude_suffix = []
        self.load()

    def current_checksum(self):
        if not self.path or not os.path.exists(self.path):
            return ''
        try:
            with open(self.path, 'rb') as handle:
                return hashlib.sha1(handle.read()).hexdigest()
        except Exception:
            return ''

    def write_raw(self, raw):
        if not self.path:
            return False
        directory = os.path.dirname(self.path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as handle:
            if raw.endswith('\n'):
                handle.write(raw)
            else:
                handle.write(raw + '\n')
        return True

    def _merge_dicts(self, base, override):
        if not isinstance(base, dict) or not isinstance(override, dict):
            return base
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = self._merge_dicts(base.get(key, {}), value)
            else:
                base[key] = value
        return base

    def _normalize_rules(self, rules):
        normalized = copy.deepcopy(DEFAULT_SANITIZATION_RULES)
        if isinstance(rules, dict):
            normalized = self._merge_dicts(normalized, rules)

        exclude = normalized.get('rules', {}).get('ip_addresses', {}).get('exclude', {})
        for key in ('cidr', 'exact', 'prefix', 'suffix'):
            values = exclude.get(key, [])
            if not isinstance(values, list):
                values = [values]
            cleaned = []
            seen = set()
            for value in values:
                text = str(value).strip()
                if not text:
                    continue
                marker = text.lower()
                if marker in seen:
                    continue
                seen.add(marker)
                cleaned.append(text)
            exclude[key] = cleaned
        normalized['rules']['ip_addresses']['exclude'] = exclude
        if not isinstance(normalized.get('meta'), dict):
            normalized['meta'] = copy.deepcopy(DEFAULT_SANITIZATION_RULES['meta'])
        if not isinstance(normalized.get('version'), (int, float)):
            normalized['version'] = DEFAULT_SANITIZATION_RULES['version']
        return normalized

    def _rebuild_indexes(self):
        exclude = self.rules.get('rules', {}).get('ip_addresses', {}).get('exclude', {})
        self.exclude_cidrs = []
        for value in exclude.get('cidr', []) or []:
            try:
                network = ipaddress.ip_network(str(value).strip(), strict=False)
                self.exclude_cidrs.append(network)
            except (ValueError, TypeError):
                continue
        self.exclude_exact = set(str(value).strip().lower() for value in (exclude.get('exact', []) or []))
        self.exclude_prefix = [str(value).strip().lower() for value in (exclude.get('prefix', []) or []) if str(value).strip()]
        self.exclude_suffix = [str(value).strip().lower() for value in (exclude.get('suffix', []) or []) if str(value).strip()]

    def load(self):
        data = None
        path_exists = bool(self.path and os.path.exists(self.path))
        if path_exists:
            try:
                with open(self.path, 'r', encoding='utf-8') as handle:
                    data = json.load(handle)
            except Exception:
                data = None

        self.rules = self._normalize_rules(data or {})
        self._rebuild_indexes()

        if not path_exists and self.path:
            try:
                pretty = json.dumps(self.rules, indent=2)
                self.write_raw(pretty)
            except Exception:
                pass

        return self.rules

    def should_exclude(self, value):
        literal = normalize_ip_literal(value)
        if not literal:
            return False
        lowered = literal.lower()
        if lowered in self.exclude_exact:
            return True
        for prefix in self.exclude_prefix:
            if lowered.startswith(prefix):
                return True
        for suffix in self.exclude_suffix:
            if lowered.endswith(suffix):
                return True
        try:
            ip_obj = ipaddress.ip_address(literal)
        except ValueError:
            return False
        for network in self.exclude_cidrs:
            if ip_obj in network:
                return True
        return False

    def filter_summary_ips(self, addresses):
        if not isinstance(addresses, list):
            return []
        filtered = []
        seen = set()
        for value in addresses:
            literal = normalize_ip_literal(value)
            if not literal or self.should_exclude(literal):
                continue
            marker = literal.lower()
            if marker in seen:
                continue
            seen.add(marker)
            filtered.append(literal)
        return filtered

    def filter_interface_addresses(self, addresses):
        if not isinstance(addresses, list):
            return []
        filtered = []
        seen = set()
        for value in addresses:
            literal = normalize_ip_literal(value)
            if not literal or self.should_exclude(literal):
                continue
            marker = literal.lower()
            if marker in seen:
                continue
            seen.add(marker)
            filtered.append(value)
        return filtered

    def sanitize_interfaces(self, interfaces):
        if not isinstance(interfaces, list):
            return interfaces
        sanitized = []
        for iface in interfaces:
            if isinstance(iface, dict):
                updated = dict(iface)
                ipv4_addresses = self.filter_interface_addresses(iface.get('ipv4_addresses', []))
                ipv6_addresses = self.filter_interface_addresses(iface.get('ipv6_addresses', []))
                addresses = self.filter_interface_addresses(iface.get('addresses', []))

                if not addresses:
                    merged = []
                    for addr in ipv4_addresses + ipv6_addresses:
                        if addr not in merged:
                            merged.append(addr)
                    addresses = merged

                updated['ipv4_addresses'] = ipv4_addresses if ipv4_addresses else []
                updated['ipv6_addresses'] = ipv6_addresses if ipv6_addresses else []
                updated['addresses'] = addresses if addresses else []
                sanitized.append(updated)
            else:
                sanitized.append(iface)
        return sanitized

    def sanitize_network_info(self, info):
        if not isinstance(info, dict):
            return info or {}
        sanitized = dict(info)
        sanitized['addresses'] = self.filter_summary_ips(info.get('addresses', []))
        sanitized['interfaces'] = self.sanitize_interfaces(info.get('interfaces', []))
        return sanitized

class DatabasePoller:
    def __init__(self):
        self.poller_name = os.getenv('POLLER_NAME', 'default')
        self._dns_warning_logged = False
        self._dns_error_hosts = set()
        self._dns_cache = {}
        self.sanitization_rules_path = os.path.join(os.path.dirname(__file__), 'sanitization_rules.json')
        self.sanitizer = SanitizationManager(self.sanitization_rules_path)

        self.config = self.load_config_from_db()
        self.db_config = self.config['database']
        self.api_config = self.config['api']
        self.poller_config = self.config['poller']
        self.poller_dns_servers = self.poller_config.get('dns_servers', [])
        self.refresh_sanitization_rules(fetch_from_server=True)
    
    def get_setting(self, conn, category, name, default=None):
        """Get a setting from the database"""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE category = %s AND name = %s", (category, name))
            result = cursor.fetchone()
            return result[0] if result else default
        except Exception as e:
            print(f"Error getting setting {category}.{name}: {e}")
            return default
    
    def load_db_config(self):
        """Load database configuration from config file or environment"""
        # Try to load from PHP config first
        try:
            config = load_php_config()
            return config['database']
        except:
            # Fallback to defaults
            return {
                'host': os.getenv('DB_HOST', '127.0.0.1'),
                'port': int(os.getenv('DB_PORT', 3306)),
                'user': os.getenv('DB_USER', 'asset_user'),
                'password': os.getenv('DB_PASSWORD', 'asset_pass'),
                'database': os.getenv('DB_NAME', 'asset_tracker')
            }
    
    def load_config_from_db(self):
        """Load all configuration from database settings"""
        # First get basic DB connection
        db_config = self.load_db_config()
        
        try:
            conn = mysql.connector.connect(**db_config)
            
            # Load poller configuration from database
            config = {
                'database': db_config,
                'poller': {
                    'interval': int(self.get_setting(conn, 'poller', 'interval', '30')),
                    'timeout': int(self.get_setting(conn, 'poller', 'timeout', '10')),
                    'ping_timeout': int(self.get_setting(conn, 'poller', 'ping_timeout', '1')),
                },
                'api': {
                    'base_url': self.get_setting(conn, 'poller', 'api_url', 'http://localhost:8080/api.php'),
                    'api_key': self.get_setting(conn, 'poller', 'api_key', 'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
                }
            }

            poller_specific_raw = self.get_setting(conn, 'pollers', self.poller_name, None)
            dns_servers = self.parse_dns_servers(poller_specific_raw)
            if not dns_servers and self.poller_name != 'default':
                default_raw = self.get_setting(conn, 'pollers', 'default', None)
                dns_servers = self.parse_dns_servers(default_raw)

            config['poller']['dns_servers'] = dns_servers
            config['poller']['name'] = self.poller_name
            
            # Check if we have a valid agent token, if not try to get/create one
            agent_token = self.ensure_agent_token(conn)
            if agent_token:
                config['api']['api_key'] = agent_token
                print(f"Using agent token: {agent_token[:10]}...")
            else:
                print(f"WARNING: No valid agent token found, using API key from settings: {config['api']['api_key'][:10]}...")
            
            conn.close()
            return config
            
        except Exception as e:
            print(f"Error loading config from database: {e}")
            # Return defaults if database is unavailable
            return {
                'database': db_config,
                'poller': {
                    'interval': 30,
                    'timeout': 10,
                    'ping_timeout': 1,
                    'dns_servers': [],
                    'name': self.poller_name
                },
                'api': {
                    'base_url': 'http://localhost:8080/api.php',
                    'api_key': 'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                }
            }
    
    def parse_dns_servers(self, raw):
        if raw is None:
            return []

        source = raw
        if isinstance(raw, str):
            trimmed = raw.strip()
            if trimmed == '':
                return []
            try:
                decoded = json.loads(trimmed)
                source = decoded
            except Exception:
                source = trimmed

        if isinstance(source, dict):
            candidates = source.get('dns_servers')
            if candidates is None and 'dns_server' in source:
                candidates = source['dns_server']
        elif isinstance(source, list):
            candidates = source
        else:
            candidates = source

        if isinstance(candidates, str):
            parts = re.split(r'[\s,]+', candidates)
        elif isinstance(candidates, list):
            parts = candidates
        else:
            parts = []

        cleaned = []
        for item in parts:
            value = str(item).strip()
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned

    def ensure_agent_token(self, conn):
        """Ensure we have a valid agent token, create if needed"""
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Check if 'poller' agent exists
            cursor.execute("SELECT token FROM agents WHERE name='poller' AND status='active'")
            result = cursor.fetchone()
            
            if result:
                return result['token']
            
            # Check if there's a token in settings we can use to register
            cursor.execute("SELECT value FROM settings WHERE category='poller' AND name='api_key'")
            api_key_result = cursor.fetchone()
            
            if not api_key_result:
                print("No API key found in settings, cannot auto-register agent")
                return None
                
            return api_key_result['value']
            
        except Exception as e:
            print(f"Error checking agent token: {e}")
            return None
    
    def get_db_connection(self):
        """Get database connection"""
        return mysql.connector.connect(**self.db_config)

    def resolve_host(self, address):
        literal = (address or '').strip()
        if literal in self._dns_cache:
            return self._dns_cache[literal]

        if literal == '':
            self._dns_cache[literal] = ''
            return ''

        normalized = normalize_ip_literal(literal)
        if is_ip_literal(normalized):
            self._dns_cache[literal] = normalized
            return normalized

        dns_servers = self.poller_dns_servers or []
        if not dns_servers:
            self._dns_cache[literal] = literal
            return literal

        if dns_resolver is None:
            if not self._dns_warning_logged:
                self.log_to_db('warning', f"Custom DNS servers configured but dnspython is not installed; using system resolver for {literal}")
                self._dns_warning_logged = True
            self._dns_cache[literal] = literal
            return literal

        resolved = None
        errors = []
        timeout = max(1, min(self.poller_config.get('timeout', 10), 15))

        for server in dns_servers:
            server = (server or '').strip()
            if not server:
                continue
            try:
                resolver = dns_resolver.Resolver(configure=False)
                resolver.nameservers = [server]
                resolver.timeout = timeout
                resolver.lifetime = timeout

                for record_type in ('A', 'AAAA'):
                    try:
                        answers = resolver.resolve(literal, record_type)
                        for answer in answers:
                            candidate = normalize_ip_literal(str(answer))
                            if candidate:
                                resolved = candidate
                                break
                        if resolved:
                            break
                    except Exception as exc:
                        errors.append(f"{server} {record_type}: {exc}")
                        continue

                if resolved:
                    break

            except Exception as exc:
                errors.append(f"{server}: {exc}")
                continue

        if resolved:
            self._dns_cache[literal] = resolved
            if literal in self._dns_error_hosts:
                self._dns_error_hosts.discard(literal)
            return resolved

        if errors and literal not in self._dns_error_hosts:
            self.log_to_db('debug', f"DNS lookup for {literal} via custom servers failed ({errors[0]})", literal)
            self._dns_error_hosts.add(literal)

        self._dns_cache[literal] = literal
        return literal

    def download_sanitization_rules(self):
        if not self.api_config.get('base_url') or not self.api_config.get('api_key'):
            return False

        timeout = max(2, int(self.poller_config.get('timeout', 10))) if isinstance(self.poller_config, dict) else 10

        try:
            response = requests.get(
                self.api_config['base_url'],
                params={'action': 'poller_sanitization_get', 'token': self.api_config['api_key']},
                timeout=timeout
            )
        except Exception as exc:
            self.log_to_db('warning', f"Failed to download sanitization rules: {exc}")
            return False

        if response.status_code != 200:
            self.log_to_db('warning', f"Failed to download sanitization rules (HTTP {response.status_code})")
            return False

        try:
            payload = response.json()
        except ValueError as exc:
            self.log_to_db('warning', f"Invalid sanitization rules response: {exc}")
            return False

        if payload.get('success') is False:
            message = payload.get('message') or payload.get('error') or 'Unknown error'
            self.log_to_db('warning', f"Server rejected sanitization rules request: {message}")
            return False

        raw = payload.get('raw')
        if not raw and 'rules' in payload:
            try:
                raw = json.dumps(payload['rules'], indent=2)
            except Exception:
                raw = ''

        if not raw or not raw.strip():
            self.log_to_db('warning', "Sanitization rules response did not include data")
            return False

        if self.sanitizer:
            existing_checksum = self.sanitizer.current_checksum()
            remote_checksum = payload.get('checksum')
            new_checksum = hashlib.sha1(raw.encode('utf-8')).hexdigest()
            if remote_checksum and existing_checksum == remote_checksum:
                self.log_to_db('debug', "Sanitization rules already current (checksum match)")
                return False
            if not remote_checksum and existing_checksum == new_checksum:
                self.log_to_db('debug', "Sanitization rules unchanged")
                return False
            try:
                self.sanitizer.write_raw(raw)
            except Exception as exc:
                self.log_to_db('warning', f"Failed to persist sanitization rules: {exc}")
                return False

            self.log_to_db('info', "Sanitization rules updated from server")
            return True

        return False

    def refresh_sanitization_rules(self, fetch_from_server=False):
        if self.sanitizer is None:
            self.sanitizer = SanitizationManager(self.sanitization_rules_path)
        if fetch_from_server:
            self.download_sanitization_rules()
        try:
            self.sanitizer.load()
        except Exception as exc:
            self.log_to_db('warning', f"Failed to load sanitization rules: {exc}")

    def sanitize_ip_list(self, addresses):
        if not self.sanitizer:
            return addresses or []
        return self.sanitizer.filter_summary_ips(addresses or [])

    def sanitize_network_info(self, info):
        if not self.sanitizer:
            return info or {}
        return self.sanitizer.sanitize_network_info(info or {})

    def sanitize_asset_payload(self, asset):
        if not self.sanitizer or not isinstance(asset, dict):
            return asset
        if 'ips' in asset:
            asset['ips'] = self.sanitize_ip_list(asset.get('ips') or [])
        attributes = asset.get('attributes')
        if isinstance(attributes, dict):
            network = attributes.get('network')
            if isinstance(network, dict):
                interfaces = network.get('interfaces')
                if interfaces is not None:
                    network['interfaces'] = self.sanitizer.sanitize_interfaces(interfaces)
        return asset
    
    def should_run(self):
        """Check if poller should be running"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE category = 'poller' AND name = 'status'")
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0] == 'running':
                return True
            return False
        except Exception as e:
            print(f"Error checking poller status: {e}")
            return False
    
    def get_targets(self):
        """Get polling targets from assets table"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Query assets that have polling enabled
            cursor.execute("""
                SELECT 
                    a.id, a.name, a.type, a.mac, a.poll_address,
                    a.poll_type, a.poll_username, a.poll_password, a.poll_port, a.poll_enable_password,
                    GROUP_CONCAT(ai.ip SEPARATOR ',') as ips
                FROM assets a
                LEFT JOIN asset_ips ai ON a.id = ai.asset_id
                WHERE a.poll_enabled = TRUE
                GROUP BY a.id, a.name, a.type, a.mac, a.poll_address, a.poll_type, a.poll_username, a.poll_password, a.poll_port, a.poll_enable_password
            """)
            
            assets = cursor.fetchall()
            conn.close()
            
            # Convert to target format
            targets = []
            for asset in assets:
                # Get primary IP (first one in the list)
                ips_str = asset['ips']
                self.log_to_db('debug', f"Asset {asset['name']}: raw ips from DB = '{ips_str}'", asset['name'])
                
                ips = [ip.strip() for ip in ips_str.split(',') if ip.strip()] if ips_str else []
                primary_ip = ips[0] if ips else None
                poll_address = (asset.get('poll_address') or '').strip()

                self.log_to_db('debug', f"Asset {asset['name']}: parsed ips = {ips}, primary_ip = '{primary_ip}', poll_address = '{poll_address}'", asset['name'])

                poll_target = poll_address or primary_ip

                if not poll_target:
                    self.log_to_db('warning', f"Asset {asset['name']} has polling enabled but no polling address or IP", asset['name'])
                    continue
                
                resolved_host = self.resolve_host(poll_target)

                target = {
                    'asset_id': asset['id'],
                    'name': asset['name'],
                    'host': resolved_host,
                    'resolved_host': resolved_host,
                    'poll_address': poll_address or None,
                    'host_display': poll_target,
                    'known_ips': ips,
                    'last_known_ip': primary_ip,
                    'type': asset['poll_type'] or 'ping',
                    'username': asset['poll_username'] or '',
                    'password': asset['poll_password'] or '',
                    'port': asset['poll_port'],
                    'device_type': asset['type'],
                    'enable_password': asset.get('poll_enable_password')
                }
                targets.append(target)
                
                self.log_to_db('debug', f"Asset {asset['name']}: created target with poll_address='{poll_address}' resolved_host='{target['host']}'", asset['name'])
            
            return targets
            
        except Exception as e:
            self.log_to_db('error', f"Error getting targets from assets table: {e}")
            return []
    
    def log_to_db(self, level, message, target=None):
        """Write log message to database"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO poller_logs (level, message, target) VALUES (%s, %s, %s)",
                (level, message, target)
            )
            conn.commit()
            conn.close()
            print(f"[{level.upper()}] {message}")
        except Exception as e:
            print(f"[ERROR] Failed to write log: {e}")
    
    def update_last_run(self):
        """Update last run timestamp"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                INSERT INTO settings (category, name, value, description) 
                VALUES ('poller', 'last_run', %s, 'Last poller execution time')
                ON DUPLICATE KEY UPDATE value = %s, updated_at = CURRENT_TIMESTAMP
            """, (now, now))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error updating last run: {e}")
    
    def ping(self, host_label, resolved_host=None, timeout=None):
        """Simple reachability check via DNS resolution"""
        if timeout is None:
            timeout = self.poller_config['ping_timeout']

        candidate = resolved_host or self.resolve_host(host_label)
        if not candidate:
            return False

        try:
            socket.setdefaulttimeout(timeout)
            if is_ip_literal(candidate):
                socket.getaddrinfo(candidate, None)
            else:
                socket.gethostbyname(candidate)
            return True
        except Exception:
            return False
    
    def unix_probe(self, target):
        """Probe Unix-like systems (Linux, *BSD, macOS) via SSH"""
        resolved_host = target.get('resolved_host') or target.get('host')
        poll_address = target.get('poll_address') or target.get('host_display') or resolved_host
        host = resolved_host or poll_address
        username = target.get('username')
        password = target.get('password')
        asset_type = target.get('device_type') or 'server'
        os_hint = (target.get('device_type') or target.get('os') or 'linux').lower()

        asset = {
            'id': target.get('asset_id'),
            'name': poll_address or host,
            'type': asset_type or 'server',
            'ips': [resolved_host] if resolved_host else ([poll_address] if poll_address else []),
            'attributes': {
                'os': {
                    'family': os_hint
                },
                'poller': {}
            },
            'mac': None
        }

        if not username:
            message = 'Missing SSH username for target'
            self.log_to_db('error', f"{message}: {poll_address or host}", poll_address or host)
            asset['attributes']['poller']['error'] = message
            asset['attributes']['poller']['collected_at'] = current_timestamp()
            return asset

        ssh = None
        try:
            self.log_to_db('info', f"Probing Unix host {poll_address or host} (resolved: {host})...", poll_address or host)
            ssh = connect_ssh({
                'host': host,
                'username': username,
                'password': password,
                'port': target.get('port'),
                'ssh_key': target.get('ssh_key')
            }, timeout=self.poller_config['timeout'])

            os_info = collect_unix_os_info(ssh, os_hint)
            asset['attributes']['os'] = os_info
            if os_info.get('hostname'):
                asset['name'] = os_info['hostname']

            network_info = collect_unix_network_info(ssh)
            network_info = self.sanitize_network_info(network_info)
            if network_info.get('interfaces'):
                asset['attributes']['network'] = {'interfaces': network_info['interfaces']}
            ips = network_info.get('addresses') or []
            if ips:
                asset['ips'] = ips
            primary_mac = network_info.get('primary_mac')
            if primary_mac:
                asset['mac'] = primary_mac

            hardware_info = collect_unix_hardware_info(ssh, os_info.get('family'))
            if hardware_info:
                asset['attributes']['hardware'] = hardware_info

            metrics_info = collect_unix_resource_metrics(ssh, os_info.get('family'))
            if metrics_info:
                asset['attributes']['metrics'] = metrics_info

            self.log_to_db('success', f"Successfully probed {poll_address or host}: {asset['name']}", poll_address or host)

        except Exception as exc:
            error_message = f"Error probing {poll_address or host}: {exc}"
            self.log_to_db('error', error_message, poll_address or host)
            asset['attributes']['poller']['error'] = str(exc)
        finally:
            if ssh:
                ssh.close()

        asset['attributes']['poller']['collected_at'] = current_timestamp()
        return self.sanitize_asset_payload(asset)
    
    def windows_probe(self, target):
        """Probe Windows system using WMI/WinRM collectors."""
        resolved_host = target.get('resolved_host') or target.get('host')
        poll_address = target.get('poll_address') or target.get('host_display') or resolved_host
        host = resolved_host or poll_address

        asset = {
            "id": target.get('asset_id'),
            "name": poll_address or host,
            "type": target.get('device_type') or 'workstation',
            "ips": [resolved_host] if resolved_host else ([poll_address] if poll_address else []),
            "attributes": {
                "os": {"family": "windows", "hostname": host},
                "poller": {}
            },
            "mac": None
        }

        poller_meta = asset['attributes']['poller']
        username = (target.get('username') or '').strip()
        password = target.get('password')

        if not username:
            message = 'Missing Windows username for target'
            self.log_to_db('error', f"{message}: {poll_address or host}", poll_address or host)
            poller_meta['error'] = message
            poller_meta['collected_at'] = current_timestamp()
            asset['ips'] = self.sanitize_ip_list(asset.get('ips') or [])
            return self.sanitize_asset_payload(asset)

        if password in (None, ''):
            message = 'Missing Windows password for target'
            self.log_to_db('error', f"{message}: {poll_address or host}", poll_address or host)
            poller_meta['error'] = message
            poller_meta['collected_at'] = current_timestamp()
            asset['ips'] = self.sanitize_ip_list(asset.get('ips') or [])
            return self.sanitize_asset_payload(asset)

        self.log_to_db('info', f"Probing Windows host {poll_address or host} (resolved: {host})...", poll_address or host)

        def _normalize_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in ('true', '1', 'yes', 'y', 'on'):
                    return True
                if lowered in ('false', '0', 'no', 'n', 'off'):
                    return False
            return None

        collector_target = {
            'host': host,
            'username': username,
            'password': password,
            'domain': target.get('domain'),
            'hashes': target.get('hashes'),
            'kerberos': target.get('kerberos'),
            'kdc_host': target.get('kdc_host'),
            'collect_applications': target.get('collect_applications'),
            'applications_limit': target.get('applications_limit'),
            'winrm_transport': target.get('winrm_transport'),
            'winrm_use_ssl': target.get('winrm_use_ssl'),
            'winrm_validate_cert': target.get('winrm_validate_cert'),
            'winrm_read_timeout': target.get('winrm_read_timeout'),
            'winrm_operation_timeout': target.get('winrm_operation_timeout'),
            'wmi_namespace': target.get('wmi_namespace'),
        }

        for flag in ('collect_applications', 'winrm_use_ssl', 'winrm_validate_cert', 'kerberos'):
            value = collector_target.get(flag)
            parsed = _normalize_bool(value)
            if parsed is not None:
                collector_target[flag] = parsed
            elif isinstance(value, str) and value.strip() == '':
                collector_target[flag] = None

        for numeric_key in ('applications_limit', 'winrm_read_timeout', 'winrm_operation_timeout'):
            value = collector_target.get(numeric_key)
            if value is None or value == '':
                collector_target[numeric_key] = None
                continue
            try:
                collector_target[numeric_key] = int(value)
            except (TypeError, ValueError):
                self.log_to_db('warning', f"Invalid value '{value}' for {numeric_key} on {poll_address or host}", poll_address or host)
                collector_target[numeric_key] = None

        transport_value = collector_target.get('winrm_transport')
        if isinstance(transport_value, str):
            trimmed = transport_value.strip()
            collector_target['winrm_transport'] = trimmed.lower() if trimmed else None

        for text_key in ('domain', 'hashes', 'kdc_host', 'wmi_namespace'):
            value = collector_target.get(text_key)
            if isinstance(value, str) and value.strip() == '':
                collector_target[text_key] = None

        port_value = target.get('port')
        if port_value:
            try:
                port_int = int(port_value)
                collector_target['winrm_port'] = port_int
                # Auto-set SSL based on common ports if not supplied
                if collector_target.get('winrm_use_ssl') is None:
                    if port_int in (5986, 443):
                        collector_target['winrm_use_ssl'] = True
                    elif port_int in (5985, 80):
                        collector_target['winrm_use_ssl'] = False
            except (TypeError, ValueError):
                self.log_to_db('warning', f"Invalid WinRM port '{port_value}' for {poll_address or host}", poll_address or host)

        try:
            windows_data = collect_windows_asset(collector_target)

            os_info = windows_data.get('os') or {}
            if os_info:
                asset['attributes']['os'] = os_info
            asset['attributes']['os'].setdefault('family', 'windows')
            resolved_name = windows_data.get('name')
            if resolved_name:
                asset['name'] = resolved_name
                asset['attributes']['os']['hostname'] = resolved_name

            ips = windows_data.get('ips') or []
            if ips:
                asset['ips'] = self.sanitize_ip_list(ips)

            mac = windows_data.get('mac')
            if mac:
                asset['mac'] = mac

            hardware = windows_data.get('hardware')
            if hardware:
                asset['attributes']['hardware'] = hardware

            network = windows_data.get('network')
            if network:
                asset['attributes']['network'] = self.sanitize_network_info(network)

            metrics = windows_data.get('metrics')
            if metrics:
                asset['attributes']['metrics'] = metrics

            applications = windows_data.get('applications')
            if applications:
                asset['attributes']['apps'] = applications

            poller_meta['source'] = windows_data.get('probe_source')
            warnings = windows_data.get('warnings')
            if warnings:
                poller_meta['warnings'] = warnings

            self.log_to_db('success', f"Windows probe succeeded for {poll_address or host}", poll_address or host)

        except WindowsProbeError as exc:
            message = f"Windows probe error: {exc}"
            self.log_to_db('error', message, poll_address or host)
            poller_meta['error'] = str(exc)
        except Exception as exc:
            message = f"Windows probe failure: {exc}"
            self.log_to_db('error', message, poll_address or host)
            poller_meta['error'] = message

        poller_meta['collected_at'] = current_timestamp()
        asset['ips'] = self.sanitize_ip_list(asset.get('ips') or [])
        return self.sanitize_asset_payload(asset)

    def cisco_probe(self, target):
        """Probe Cisco network devices over SSH."""
        resolved_host = target.get('resolved_host') or target.get('host')
        poll_address = target.get('poll_address') or target.get('host_display') or resolved_host
        host = resolved_host or poll_address

        asset = {
            "id": target.get('asset_id'),
            "name": poll_address or host,
            "type": target.get('device_type') or 'network',
            "ips": [resolved_host] if resolved_host else ([poll_address] if poll_address else []),
            "attributes": {
                "os": {"family": "network", "vendor": "Cisco"},
                "poller": {}
            },
            "mac": None
        }

        poller_meta = asset['attributes']['poller']
        username = (target.get('username') or '').strip()
        password = target.get('password')

        if not username:
            message = 'Missing SSH username for Cisco target'
            self.log_to_db('error', f"{message}: {poll_address or host}", poll_address or host)
            poller_meta['error'] = message
            poller_meta['collected_at'] = current_timestamp()
            asset['ips'] = self.sanitize_ip_list(asset.get('ips') or [])
            return self.sanitize_asset_payload(asset)

        if password in (None, ''):
            message = 'Missing SSH password for Cisco target'
            self.log_to_db('error', f"{message}: {poll_address or host}", poll_address or host)
            poller_meta['error'] = message
            poller_meta['collected_at'] = current_timestamp()
            asset['ips'] = self.sanitize_ip_list(asset.get('ips') or [])
            return self.sanitize_asset_payload(asset)

        self.log_to_db('info', f"Probing Cisco host {poll_address or host} (resolved: {host})...", poll_address or host)

        collector_target = {
            'host': host,
            'host_display': poll_address or host,
            'username': username,
            'password': password,
            'enable_password': target.get('enable_password'),
            'port': target.get('port') or 22,
            'timeout': self.poller_config.get('timeout', 10)
        }

        try:
            cisco_data = collect_cisco_asset(collector_target)

            os_info = cisco_data.get('os') or {}
            if os_info:
                asset['attributes']['os'] = os_info
            resolved_name = cisco_data.get('name')
            if resolved_name:
                asset['name'] = resolved_name
                asset['attributes']['os']['hostname'] = resolved_name

            ips = cisco_data.get('ips') or []
            if ips:
                asset['ips'] = self.sanitize_ip_list(ips)

            mac = cisco_data.get('mac')
            if mac:
                asset['mac'] = mac

            hardware = cisco_data.get('hardware')
            if hardware:
                asset['attributes']['hardware'] = hardware

            network = cisco_data.get('network')
            if network:
                asset['attributes']['network'] = self.sanitize_network_info(network)

            metrics = cisco_data.get('metrics')
            if metrics:
                asset['attributes']['metrics'] = metrics

            warnings = cisco_data.get('warnings')
            if warnings:
                poller_meta['warnings'] = warnings

            poller_meta['source'] = cisco_data.get('probe_source', 'cisco-ssh')
            self.log_to_db('success', f"Cisco probe succeeded for {poll_address or host}", poll_address or host)

        except CiscoProbeError as exc:
            message = f"Cisco probe error: {exc}"
            self.log_to_db('error', message, poll_address or host)
            poller_meta['error'] = str(exc)
        except Exception as exc:
            message = f"Cisco probe failure: {exc}"
            self.log_to_db('error', message, poll_address or host)
            poller_meta['error'] = message

        poller_meta['collected_at'] = current_timestamp()
        asset['ips'] = self.sanitize_ip_list(asset.get('ips') or [])
        return self.sanitize_asset_payload(asset)
    
    def push_update(self, asset, online=True):
        """Push asset update to API"""
        asset = self.sanitize_asset_payload(asset)
        url = f"{self.api_config['base_url']}?action=agent_push&token={self.api_config['api_key']}"
        
        payload = {
            "asset": asset,
            "online_status": "online" if online else "offline"
        }
        
        try:
            self.log_to_db('info', f"Pushing update for {asset.get('name', 'unknown')}: {url}", asset.get('name'))
            self.log_to_db('debug', f"Payload: {payload}", asset.get('name'))
            
            response = requests.post(url, json=payload, timeout=self.poller_config['timeout'])
            
            self.log_to_db('info', f"API Response Status: {response.status_code}", asset.get('name'))
            
            if response.status_code == 200:
                self.log_to_db('success', f"Successfully updated asset: {asset.get('name')}", asset.get('name'))
            elif response.status_code == 401:
                try:
                    error_data = response.json()
                    self.log_to_db('error', f"Authentication failed (401): {error_data}. API Key: {self.api_config['api_key'][:10]}...", asset.get('name'))
                except:
                    self.log_to_db('error', f"Authentication failed (401): {response.text}. API Key: {self.api_config['api_key'][:10]}...", asset.get('name'))
            else:
                try:
                    error_data = response.json()
                    self.log_to_db('error', f"Failed to update asset (HTTP {response.status_code}): {error_data}", asset.get('name'))
                except:
                    error_text = response.text[:500] if response.text else '(empty response)'
                    self.log_to_db('error', f"Failed to update asset (HTTP {response.status_code}): {error_text}", asset.get('name'))
                    
        except requests.exceptions.Timeout:
            self.log_to_db('error', f"Timeout pushing update to API (timeout={self.poller_config['timeout']}s)", asset.get('name'))
        except requests.exceptions.ConnectionError as e:
            self.log_to_db('error', f"Connection error pushing update: {str(e)}", asset.get('name'))
        except Exception as e:
            self.log_to_db('error', f"Error pushing update: {type(e).__name__}: {str(e)}", asset.get('name'))
    
    def poll_targets(self):
        """Poll all configured targets"""
        targets = self.get_targets()
        
        if not targets:
            self.log_to_db('warning', "No assets enabled for polling")
            return
        
        self.log_to_db('info', f"Starting poll cycle for {len(targets)} assets")
        
        for target in targets:
            poll_type = target.get('type', 'ping')
            resolved_host = target.get('resolved_host') or target.get('host')
            poll_address = target.get('poll_address') or target.get('host_display') or resolved_host
            host = resolved_host or poll_address
            asset_name = target.get('name', poll_address or host)
            
            # Probe based on poll type
            if poll_type == 'ssh':
                asset = self.unix_probe(target)
            elif poll_type in ('ssh_cisco', 'cisco', 'ssh-cisco'):
                asset = self.cisco_probe(target)
            elif poll_type in ('wmi', 'winrm', 'windows'):
                asset = self.windows_probe(target)
            elif poll_type in ['snmp', 'ping']:
                # Just check online status for now
                asset = {
                    "id": target.get('asset_id'),
                    "name": asset_name,
                    "type": target.get('device_type', 'unknown'),
                    "ips": [resolved_host] if resolved_host else ([poll_address] if poll_address else []),
                    "mac": None,
                    "attributes": {
                        "poller": {"collected_at": current_timestamp()}
                    }
                }
            else:
                self.log_to_db('error', f"Unknown poll type: {poll_type}", host)
                continue

            asset = self.sanitize_asset_payload(asset)
            
            # Check if host is online
            online = self.ping(poll_address or host, resolved_host)
            status_msg = "online" if online else "offline"
            label = poll_address or host
            self.log_to_db('info', f"Asset {asset_name} ({label} -> {resolved_host or 'unresolved'}) is {status_msg}", label)
            
            # Push update to API
            self.push_update(asset, online)
        
        self.log_to_db('info', f"Poll cycle completed for {len(targets)} assets")
    
    def reload_config(self):
        """Reload configuration from database"""
        try:
            old_interval = self.poller_config['interval']
            self.config = self.load_config_from_db()
            self.poller_config = self.config['poller']
            self.api_config = self.config['api']
            self.poller_dns_servers = self.poller_config.get('dns_servers', [])
            self.refresh_sanitization_rules(fetch_from_server=True)
            self._dns_cache.clear()
            self._dns_error_hosts.clear()
            
            if old_interval != self.poller_config['interval']:
                print(f"Updated polling interval: {old_interval}s -> {self.poller_config['interval']}s")
        except Exception as e:
            print(f"Error reloading config: {e}")
    
    def run(self):
        """Main polling loop"""
        self.log_to_db('info', "Database-driven Asset Tracker Poller starting...")
        config_reload_counter = 0
        
        while True:
            try:
                # Reload config every 10 cycles to pick up changes
                if config_reload_counter >= 10:
                    self.reload_config()
                    config_reload_counter = 0
                
                if self.should_run():
                    self.poll_targets()
                    self.update_last_run()
                else:
                    self.log_to_db('info', "Poller is disabled, waiting...")
                
                config_reload_counter += 1
                
            except KeyboardInterrupt:
                self.log_to_db('info', "Poller stopped by user")
                break
            except Exception as e:
                self.log_to_db('error', f"Error in poll cycle: {str(e)}")
            
            # Wait before next cycle using configurable interval
            time.sleep(self.poller_config['interval'])

if __name__ == "__main__":
    poller = DatabasePoller()
    poller.run()