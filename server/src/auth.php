<?php
require_once __DIR__ . '/db.php';

class Auth {
  public static function login($username, $password) {
    $cfg = require __DIR__ . '/../config/config.php';
    // First: LDAP if enabled
    if (($cfg['ldap']['enabled'] ?? false) === true) {
      if (self::ldap_auth($username, $password)) {
        return self::sync_or_create_user($username, 'user');
      }
      return null;
    }
    // Fallback: local dev login (disabled by default)
    if ($username === 'admin' && $password === 'admin') {
      return self::sync_or_create_user('admin', 'admin', 'Local Admin');
    }
    return null;
  }

  private static function ldap_auth($username, $password) {
    $cfg = require __DIR__ . '/../config/config.php';
    $conn = ldap_connect($cfg['ldap']['host'], $cfg['ldap']['port']);
    if (!$conn) return false;
    ldap_set_option($conn, LDAP_OPT_PROTOCOL_VERSION, 3);
    if (!@ldap_bind($conn, $cfg['ldap']['bind_dn'], $cfg['ldap']['bind_password'])) return false;
    $filter = "({$cfg['ldap']['user_attr']}=" . ldap_escape($username, '', LDAP_ESCAPE_FILTER) . ")";
    $sr = ldap_search($conn, $cfg['ldap']['base_dn'], $filter, ['dn','mail','displayName','sAMAccountName']);
    $entries = ldap_get_entries($conn, $sr);
    if ($entries['count'] < 1) return false;
    $dn = $entries[0]['dn'];
    if (@ldap_bind($conn, $dn, $password)) {
      return true;
    }
    return false;
  }

  private static function sync_or_create_user($username, $role='user', $display='') {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT * FROM users WHERE username=?");
    $stmt->execute([$username]);
    $user = $stmt->fetch();
    if ($user) return $user;
    $stmt = $pdo->prepare("INSERT INTO users (username, display_name, role) VALUES (?, ?, ?)");
    $stmt->execute([$username, $display ?: $username, $role]);
    $id = $pdo->lastInsertId();
    $stmt = $pdo->prepare("SELECT * FROM users WHERE id=?");
    $stmt->execute([$id]);
    return $stmt->fetch();
  }
}
