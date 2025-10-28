<?php
require_once __DIR__ . '/db.php';

class Auth {
  public static function login($username, $password) {
    $cfg = require __DIR__ . '/../config/config.php';
    
    // Get LDAP settings from database
    $ldapSettings = self::getLdapSettings();
    
    // First: LDAP if enabled
    if (($ldapSettings['enabled'] ?? false) === 'true') {
      if (self::ldap_auth($username, $password, $ldapSettings)) {
        return self::sync_or_create_user($username, 'user');
      }
      return null;
    }
    // Fallback: local dev login (change default password in production!)
    if ($username === 'admin' && $password === 'admin123') {
      return self::sync_or_create_user('admin', 'admin', 'Local Admin');
    }
    return null;
  }

  private static function getLdapSettings() {
    try {
      $pdo = DB::conn();
      $stmt = $pdo->prepare("SELECT name, value FROM settings WHERE category = 'ldap'");
      $stmt->execute();
      
      $settings = [];
      while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $settings[$row['name']] = $row['value'];
      }
      return $settings;
    } catch (Exception $e) {
      // Fallback to config file if database settings not available
      $cfg = require __DIR__ . '/../config/config.php';
      return $cfg['ldap'] ?? [];
    }
  }

  private static function ldap_auth($username, $password, $ldapSettings) {
    if (!function_exists('ldap_connect')) {
      return false;
    }
    
    $host = $ldapSettings['host'] ?? '';
    $port = intval($ldapSettings['port'] ?? 389);
    $bindDn = $ldapSettings['bind_dn'] ?? '';
    $bindPassword = $ldapSettings['bind_password'] ?? '';
    $baseDn = $ldapSettings['base_dn'] ?? '';
    $userAttr = $ldapSettings['user_attr'] ?? 'sAMAccountName';
    
    $conn = ldap_connect($host, $port);
    if (!$conn) return false;
    ldap_set_option($conn, LDAP_OPT_PROTOCOL_VERSION, 3);
    if (!@ldap_bind($conn, $bindDn, $bindPassword)) return false;
    $filter = "({$userAttr}=" . ldap_escape($username, '', LDAP_ESCAPE_FILTER) . ")";
    $sr = ldap_search($conn, $baseDn, $filter, ['dn','mail','displayName','sAMAccountName']);
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
