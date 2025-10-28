-- Create default admin user for local login
INSERT INTO users (username, display_name, email, role) VALUES
  ('admin', 'Local Administrator', 'admin@localhost', 'admin')
  ON DUPLICATE KEY UPDATE 
    display_name = 'Local Administrator',
    email = 'admin@localhost',
    role = 'admin';