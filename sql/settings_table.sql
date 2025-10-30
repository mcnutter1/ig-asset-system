-- Settings table to store application configuration including LDAP
CREATE TABLE IF NOT EXISTS settings (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  category    VARCHAR(100) NOT NULL,
  name        VARCHAR(100) NOT NULL,
  value       TEXT,
  description TEXT,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY unique_setting (category, name)
) ENGINE=InnoDB;

INSERT INTO settings (category, name, value, description) VALUES
  ('ldap', 'enabled', 'false', 'Enable LDAP authentication'),
  ('ldap', 'port', '389', 'LDAP server port'),
  ('ldap', 'bind_dn', 'CN=ldap-reader,OU=Service Accounts,DC=example,DC=com', 'LDAP bind DN for authentication'),
  ('ldap', 'bind_password', '', 'LDAP bind password'),
  ('ldap', 'base_dn', 'DC=example,DC=com', 'LDAP base DN for user searches'),
  ('ldap', 'user_attr', 'sAMAccountName', 'LDAP user attribute for login'),
  ('pollers', 'default', '{"dns_servers":[]}', 'Default poller instance settings'),
  (
    'poller',
    'sanitization_rules',
    '{"version":1,"meta":{"description":"Default poller sanitization rules"},"rules":{"ip_addresses":{"exclude":{"cidr":["127.0.0.0/8","::1/128","fe80::/10"],"exact":[],"prefix":[],"suffix":[]}}}}',
    'Poller sanitization rules JSON'
  )
ON DUPLICATE KEY UPDATE description = VALUES(description);