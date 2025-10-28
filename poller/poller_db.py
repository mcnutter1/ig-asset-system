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
from datetime import datetime
from config_loader import load_php_config

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
    
    def linux_probe(self, target):
        """Probe Linux system via SSH"""
        host = target['host']
        user = target.get('username', 'ubuntu')
        password = target.get('password', '')
        
        info = {
            "id": target.get('asset_id'),  # Include asset ID for updates
            "name": host,
            "type": "server",
            "ips": [host],
            "attributes": {"os": {"family": "linux"}},
            "mac": None
        }
        
        try:
            self.log_to_db('info', f"Probing Linux host {host}...", host)
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, username=user, password=password, timeout=self.poller_config['timeout'])
            
            commands = {
                "uname": "uname -a",
                "hostname": "hostname",
                "ip": "hostname -I || ip -4 -o addr show | awk '{print $4}'",
                "mac": "ip link | awk '/ether/ {print $2; exit}'",
            }
            
            result = {}
            for key, cmd in commands.items():
                stdin, stdout, stderr = ssh.exec_command(cmd, timeout=self.poller_config['timeout'])
                result[key] = stdout.read().decode().strip()
            
            info["name"] = result.get("hostname") or host
            if result.get("ip"):
                info["ips"] = [ip for ip in result["ip"].split() if ip]
            info["mac"] = result.get("mac") or None
            info["attributes"]["os"]["kernel"] = result.get("uname", "").strip()
            
            ssh.close()
            self.log_to_db('success', f"Successfully probed {host}: {info['name']}", host)
            
        except Exception as e:
            self.log_to_db('error', f"Error probing {host}: {str(e)}", host)
        
        return info
    
    def windows_probe(self, target):
        """Probe Windows system (basic implementation)"""
        host = target['host']
        info = {
            "id": target.get('asset_id'),  # Include asset ID for updates
            "name": host,
            "type": "workstation",
            "ips": [host],
            "attributes": {"os": {"family": "windows"}},
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
                asset = self.linux_probe(target)
            elif poll_type == 'wmi':
                asset = self.windows_probe(target)
            elif poll_type in ['snmp', 'ping']:
                # Just check online status for now
                asset = {
                    "id": target.get('asset_id'),
                    "name": asset_name,
                    "type": target.get('device_type', 'unknown'),
                    "ips": [{"ip": host}],
                    "mac": None,
                    "attributes": {}
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