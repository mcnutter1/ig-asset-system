-- Patches tracking table - used by bootstrap system
CREATE TABLE IF NOT EXISTS patches (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  patch_name  VARCHAR(255) UNIQUE NOT NULL,
  patch_type  ENUM('sql', 'php', 'system') NOT NULL DEFAULT 'sql',
  description TEXT,
  applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  applied_by  VARCHAR(100) DEFAULT 'bootstrap',
  success     BOOLEAN DEFAULT TRUE,
  error_log   TEXT NULL
) ENGINE=InnoDB;

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_patches_name ON patches(patch_name);
CREATE INDEX IF NOT EXISTS idx_patches_applied ON patches(applied_at);