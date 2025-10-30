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

class DatabasePoller:
    def __init__(self):
        self.config = self.load_config_from_db()
        self.db_config = self.config['database']
        self.api_config = self.config['api']
        self.poller_config = self.config['poller']
    
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
                },
                'api': {
                    'base_url': 'http://localhost:8080/api.php',
                    'api_key': 'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                }
            }
    
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
                    a.id, a.name, a.type, a.mac,
                    a.poll_type, a.poll_username, a.poll_password, a.poll_port,
                    GROUP_CONCAT(ai.ip SEPARATOR ',') as ips
                FROM assets a
                LEFT JOIN asset_ips ai ON a.id = ai.asset_id
                WHERE a.poll_enabled = TRUE
                GROUP BY a.id, a.name, a.type, a.mac, a.poll_type, a.poll_username, a.poll_password, a.poll_port
            """)
            
            assets = cursor.fetchall()
            conn.close()
            
            # Convert to target format
            targets = []
            for asset in assets:
                # Get primary IP (first one in the list)
                ips_str = asset['ips']
                self.log_to_db('debug', f"Asset {asset['name']}: raw ips from DB = '{ips_str}'", asset['name'])
                
                ips = ips_str.split(',') if ips_str else []
                primary_ip = ips[0].strip() if ips else None
                
                self.log_to_db('debug', f"Asset {asset['name']}: parsed ips = {ips}, primary_ip = '{primary_ip}'", asset['name'])
                
                if not primary_ip:
                    self.log_to_db('warning', f"Asset {asset['name']} has polling enabled but no IP address", asset['name'])
                    continue
                
                target = {
                    'asset_id': asset['id'],
                    'name': asset['name'],
                    'host': primary_ip,
                    'type': asset['poll_type'] or 'ping',
                    'username': asset['poll_username'] or '',
                    'password': asset['poll_password'] or '',
                    'port': asset['poll_port'],
                    'device_type': asset['type']
                }
                targets.append(target)
                
                self.log_to_db('debug', f"Asset {asset['name']}: created target with host='{target['host']}'", asset['name'])
            
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
    
    def ping(self, host, timeout=None):
        """Simple ping test"""
        if timeout is None:
            timeout = self.poller_config['ping_timeout']
        try:
            socket.setdefaulttimeout(timeout)
            socket.gethostbyname(host)
            return True
        except:
            return False
    
    def unix_probe(self, target):
        """Probe Unix-like systems (Linux, *BSD, macOS) via SSH"""
        host = target['host']
        username = target.get('username')
        password = target.get('password')
        asset_type = target.get('device_type') or 'server'
        os_hint = (target.get('device_type') or target.get('os') or 'linux').lower()

        asset = {
            'id': target.get('asset_id'),
            'name': host,
            'type': asset_type or 'server',
            'ips': [host],
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
            self.log_to_db('error', f"{message}: {host}", host)
            asset['attributes']['poller']['error'] = message
            asset['attributes']['poller']['collected_at'] = current_timestamp()
            return asset

        ssh = None
        try:
            self.log_to_db('info', f"Probing Unix host {host}...", host)
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

            self.log_to_db('success', f"Successfully probed {host}: {asset['name']}", host)

        except Exception as exc:
            error_message = f"Error probing {host}: {exc}"
            self.log_to_db('error', error_message, host)
            asset['attributes']['poller']['error'] = str(exc)
        finally:
            if ssh:
                ssh.close()

        asset['attributes']['poller']['collected_at'] = current_timestamp()
        return asset
    
    def windows_probe(self, target):
        """Probe Windows system (basic implementation)"""
        host = target['host']
        info = {
            "id": target.get('asset_id'),  # Include asset ID for updates
            "name": host,
            "type": "workstation",
            "ips": [host],
            "attributes": {
                "os": {"family": "windows", "hostname": host},
                "poller": {"collected_at": current_timestamp()}
            },
            "mac": None
        }
        print(f"Basic probe for Windows host: {host}")
        return info
    
    def push_update(self, asset, online=True):
        """Push asset update to API"""
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
            host = target['host']
            asset_name = target.get('name', host)
            
            # Probe based on poll type
            if poll_type == 'ssh':
                asset = self.unix_probe(target)
            elif poll_type == 'wmi':
                asset = self.windows_probe(target)
            elif poll_type in ['snmp', 'ping']:
                # Just check online status for now
                asset = {
                    "id": target.get('asset_id'),
                    "name": asset_name,
                    "type": target.get('device_type', 'unknown'),
                    "ips": [host],
                    "mac": None,
                    "attributes": {
                        "poller": {"collected_at": current_timestamp()}
                    }
                }
            else:
                self.log_to_db('error', f"Unknown poll type: {poll_type}", host)
                continue
            
            # Check if host is online
            online = self.ping(host)
            status_msg = "online" if online else "offline"
            self.log_to_db('info', f"Asset {asset_name} ({host}) is {status_msg}", host)
            
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