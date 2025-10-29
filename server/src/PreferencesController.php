<?php
require_once __DIR__ . '/db.php';

class PreferencesController {
  public static function get(int $userId, string $key, $default = null) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT pref_value FROM user_preferences WHERE user_id = ? AND pref_key = ? LIMIT 1");
    $stmt->execute([$userId, $key]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$row) {
      return $default;
    }
    $decoded = json_decode($row['pref_value'], true);
    return $decoded === null && $row['pref_value'] !== 'null' ? $default : $decoded;
  }

  public static function set(int $userId, string $key, $value): bool {
    $pdo = DB::conn();
    $json = json_encode($value, JSON_UNESCAPED_UNICODE);
    $stmt = $pdo->prepare(
      "INSERT INTO user_preferences (user_id, pref_key, pref_value) VALUES (?, ?, CAST(? AS JSON))
       ON DUPLICATE KEY UPDATE pref_value = VALUES(pref_value), updated_at = CURRENT_TIMESTAMP"
    );
    return $stmt->execute([$userId, $key, $json]);
  }

  public static function delete(int $userId, string $key): bool {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("DELETE FROM user_preferences WHERE user_id = ? AND pref_key = ?");
    return $stmt->execute([$userId, $key]);
  }
}
