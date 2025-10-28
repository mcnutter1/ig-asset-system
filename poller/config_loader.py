#!/usr/bin/env python3
"""
Configuration loader for the database poller

Reads configuration from the PHP config file to ensure consistency
"""

import re
import os

def load_php_config():
    """Load database config from PHP config file"""
    config_path = '../server/config/config.php'
    
    # Default configuration
    config = {
        'database': {
            'host': '127.0.0.1',
            'port': 3306,
            'user': 'asset_user',
            'password': 'asset_pass',
            'database': 'asset_tracker'
        },
        'api': {
            'base_url': 'http://localhost:8080/api.php',
            'api_key': 'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        }
    }
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                content = f.read()
                
                # Extract database settings using regex
                db_patterns = {
                    'host': r"'host'\s*=>\s*'([^']*)'",
                    'user': r"'user'\s*=>\s*'([^']*)'", 
                    'password': r"'password'\s*=>\s*'([^']*)'",
                    'database': r"'database'\s*=>\s*'([^']*)'",
                    'port': r"'port'\s*=>\s*(\d+)"
                }
                
                for key, pattern in db_patterns.items():
                    match = re.search(pattern, content)
                    if match:
                        value = match.group(1)
                        if key == 'port':
                            config['database'][key] = int(value)
                        else:
                            config['database'][key] = value
                
                # Extract site base URL for API
                site_pattern = r"'base_url'\s*=>\s*'([^']*)\'"
                match = re.search(site_pattern, content)
                if match:
                    base_url = match.group(1)
                    config['api']['base_url'] = f"{base_url}/api.php"
                    
    except Exception as e:
        print(f"Warning: Could not read PHP config, using defaults: {e}")
    
    return config

if __name__ == "__main__":
    config = load_php_config()
    print("Loaded configuration:")
    print(f"Database: {config['database']['user']}@{config['database']['host']}:{config['database']['port']}/{config['database']['database']}")
    print(f"API: {config['api']['base_url']}")