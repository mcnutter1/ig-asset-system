-- User preferences table stores per-user UI and feature settings
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id    BIGINT NOT NULL,
  pref_key   VARCHAR(190) NOT NULL,
  pref_value JSON NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, pref_key),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
