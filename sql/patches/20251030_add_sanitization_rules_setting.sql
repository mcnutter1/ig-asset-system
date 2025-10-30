INSERT INTO settings (category, name, value, description)
VALUES (
  'poller',
  'sanitization_rules',
  '{"version":1,"meta":{"description":"Default poller sanitization rules"},"rules":{"ip_addresses":{"exclude":{"cidr":["127.0.0.0/8","::1/128","fe80::/10"],"exact":[],"prefix":[],"suffix":[]}}}}',
  'Poller sanitization rules JSON'
)
ON DUPLICATE KEY UPDATE description = VALUES(description);
