-- Custom fields table for dynamic asset properties
CREATE TABLE IF NOT EXISTS custom_fields (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE COMMENT 'Field identifier (snake_case)',
  label VARCHAR(200) NOT NULL COMMENT 'Display label for UI',
  field_type ENUM('text', 'number', 'date', 'select', 'textarea', 'checkbox', 'url', 'email') NOT NULL DEFAULT 'text',
  is_required BOOLEAN DEFAULT FALSE,
  default_value TEXT NULL,
  select_options JSON NULL COMMENT 'For select type: ["option1", "option2"]',
  applies_to_types JSON NULL COMMENT 'Asset types this field applies to. NULL = all types. e.g. ["server", "workstation"]',
  display_order INT DEFAULT 0 COMMENT 'Order to display in UI',
  help_text VARCHAR(500) NULL COMMENT 'Help text shown in UI',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_display_order (display_order),
  INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Custom field values table (stores actual values for each asset)
CREATE TABLE IF NOT EXISTS custom_field_values (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  asset_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  field_id BIGINT NOT NULL,
  value TEXT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY unique_asset_field (asset_id, field_id),
  INDEX idx_asset_id (asset_id),
  INDEX idx_field_id (field_id),
  CONSTRAINT fk_custom_field_asset FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
  CONSTRAINT fk_custom_field_field FOREIGN KEY (field_id) REFERENCES custom_fields(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sample custom fields (only insert if they don't exist)
INSERT IGNORE INTO custom_fields (name, label, field_type, is_required, applies_to_types, display_order, help_text) VALUES
('department', 'Department', 'select', FALSE, NULL, 10, 'Which department uses this asset'),
('cost_center', 'Cost Center', 'text', FALSE, NULL, 20, 'Cost center code for billing'),
('purchase_date', 'Purchase Date', 'date', FALSE, NULL, 30, 'Date asset was purchased'),
('warranty_expiration', 'Warranty Expiration', 'date', FALSE, NULL, 40, 'When warranty expires'),
('serial_number', 'Serial Number', 'text', FALSE, NULL, 50, 'Manufacturer serial number'),
('asset_tag', 'Asset Tag', 'text', FALSE, NULL, 60, 'Physical asset tag number'),
('location', 'Location', 'text', FALSE, NULL, 70, 'Physical location of asset'),
('notes', 'Notes', 'textarea', FALSE, NULL, 80, 'Additional notes about this asset');

-- Add sample select options for department
UPDATE custom_fields SET select_options = JSON_ARRAY('IT', 'HR', 'Finance', 'Sales', 'Marketing', 'Operations', 'Executive') WHERE name = 'department';
