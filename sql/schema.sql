-- MySQL 8.0+ schema

CREATE DATABASE IF NOT EXISTS asset_tracker CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE asset_tracker;

-- Users from AD are synced/created on-demand at login.
CREATE TABLE IF NOT EXISTS users (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  username      VARCHAR(190) UNIQUE NOT NULL,
  display_name  VARCHAR(190),
  email         VARCHAR(190),
  ad_dn         VARCHAR(512),
  role          ENUM('admin','user','viewer') DEFAULT 'user',
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Assets
CREATE TABLE IF NOT EXISTS assets (
  id            CHAR(36) PRIMARY KEY, -- UUID
  name          VARCHAR(190) NOT NULL,
  type          ENUM('workstation','server','iot','network','mobile','unknown') DEFAULT 'unknown',
  mac           VARCHAR(64),
  poll_address  VARCHAR(255),
  poll_enabled  BOOLEAN DEFAULT FALSE,
  poll_type     VARCHAR(32) DEFAULT 'ping',
  poll_username VARCHAR(190),
  poll_password VARCHAR(190),
  poll_port     INT NULL,
  poll_enable_password VARCHAR(255),
  owner_user_id BIGINT,
  online_status ENUM('online','offline','unknown') DEFAULT 'unknown',
  last_seen     DATETIME NULL,
  source        ENUM('manual','api','agent','poller') DEFAULT 'manual',
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE INDEX IF NOT EXISTS idx_assets_mac ON assets(mac);

-- Multiple IPv4/IPv6
CREATE TABLE IF NOT EXISTS asset_ips (
  id        BIGINT PRIMARY KEY AUTO_INCREMENT,
  asset_id  CHAR(36) NOT NULL,
  family    ENUM('ipv4','ipv6') NOT NULL,
  ip        VARCHAR(128) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE INDEX IF NOT EXISTS idx_asset_ips_ip ON asset_ips(ip);

-- Nested/complex attributes as JSON
CREATE TABLE IF NOT EXISTS asset_attributes (
  asset_id    CHAR(36) PRIMARY KEY,
  attributes  JSON NOT NULL, -- e.g., { "os": {...}, "apps": [{...}], "hardware": {...} }
  updated_by  ENUM('manual','api','agent','poller') NOT NULL DEFAULT 'manual',
  updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Change Log / Timeline
CREATE TABLE IF NOT EXISTS changes (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  asset_id    CHAR(36) NOT NULL,
  actor       VARCHAR(190) NOT NULL, -- username, api_key name, or agent token id
  source      ENUM('manual','api','agent','poller') NOT NULL,
  field       VARCHAR(190) NOT NULL, -- "name", "attributes.os.version", etc.
  old_value   JSON,
  new_value   JSON,
  changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE INDEX IF NOT EXISTS idx_changes_asset ON changes(asset_id, changed_at);

-- Agents (push model)
CREATE TABLE IF NOT EXISTS agents (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  name        VARCHAR(190) NOT NULL,
  token       CHAR(48) UNIQUE NOT NULL,
  platform    ENUM('linux','windows','other') DEFAULT 'other',
  bound_asset CHAR(36) NULL, -- optionally pin to one asset
  last_seen   DATETIME NULL,
  status      ENUM('active','disabled') DEFAULT 'active',
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (bound_asset) REFERENCES assets(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- API Keys (for pollers/integrations)
CREATE TABLE IF NOT EXISTS api_keys (
  id        BIGINT PRIMARY KEY AUTO_INCREMENT,
  name      VARCHAR(190) UNIQUE NOT NULL,
  token     CHAR(48) UNIQUE NOT NULL,
  role      ENUM('poller','integration','admin') DEFAULT 'integration',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Per-user preferences (UI settings, etc.)
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id    BIGINT NOT NULL,
  pref_key   VARCHAR(190) NOT NULL,
  pref_value JSON NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, pref_key),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Useful default API key for poller (change this in prod)
INSERT INTO api_keys (name, token, role) VALUES
  ('default-poller', 'POLLR_' 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', 'poller')
  ON DUPLICATE KEY UPDATE name=name;
