USE asset_tracker;
INSERT INTO users (username, display_name, role) VALUES ('admin','Admin User','admin')
  ON DUPLICATE KEY UPDATE username=username;
