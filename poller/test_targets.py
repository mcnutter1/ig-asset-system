#!/usr/bin/env python3
"""
Test script to add sample polling targets to the database
"""

import json
import mysql.connector

def add_test_targets():
    # Database config
    db_config = {
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'asset_user',
        'password': 'asset_pass',
        'database': 'asset_tracker'
    }
    
    # Sample targets
    targets = [
        {
            'host': '127.0.0.1',
            'type': 'linux',
            'username': 'ubuntu',
            'password': ''
        },
        {
            'host': 'localhost',
            'type': 'linux',
            'username': 'ubuntu',
            'password': ''
        }
    ]
    
    # Default configuration
    config = {
        'interval': '30',
        'timeout': '10',
        'ping_timeout': '1',
        'api_url': 'http://localhost:8080/api.php',
        'api_key': 'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    }
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Insert targets
        targets_json = json.dumps(targets)
        cursor.execute("""
            INSERT INTO settings (category, name, value, description) 
            VALUES ('poller', 'targets', %s, 'Polling targets configuration')
            ON DUPLICATE KEY UPDATE value = %s, updated_at = CURRENT_TIMESTAMP
        """, (targets_json, targets_json))
        
        # Insert configuration settings
        config_descriptions = {
            'interval': 'Polling interval in seconds',
            'timeout': 'Connection timeout in seconds',
            'ping_timeout': 'Ping timeout in seconds',
            'api_url': 'API endpoint URL',
            'api_key': 'API authentication key'
        }
        
        for key, value in config.items():
            description = config_descriptions[key]
            cursor.execute("""
                INSERT INTO settings (category, name, value, description) 
                VALUES ('poller', %s, %s, %s)
                ON DUPLICATE KEY UPDATE value = %s, updated_at = CURRENT_TIMESTAMP
            """, (key, value, description, value))
        
        # Set poller to stopped initially
        cursor.execute("""
            INSERT INTO settings (category, name, value, description) 
            VALUES ('poller', 'status', 'stopped', 'Poller running status')
            ON DUPLICATE KEY UPDATE value = 'stopped', updated_at = CURRENT_TIMESTAMP
        """)
        
        conn.commit()
        conn.close()
        
        print("Test targets and configuration added successfully!")
        print(f"Added {len(targets)} targets:")
        for target in targets:
            print(f"  - {target['type']}: {target['host']}")
        print(f"Configuration:")
        for key, value in config.items():
            print(f"  - {key}: {value}")
            
    except Exception as e:
        print(f"Error adding test data: {e}")

if __name__ == "__main__":
    add_test_targets()