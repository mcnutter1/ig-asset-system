-- Patch: add poll_address column and default poller settings
ALTER TABLE assets
  ADD COLUMN poll_address VARCHAR(255) NULL AFTER mac;

INSERT INTO settings (category, name, value, description)
VALUES ('pollers', 'default', '{"dns_servers":[]}', 'Default poller instance settings')
ON DUPLICATE KEY UPDATE description = VALUES(description);
