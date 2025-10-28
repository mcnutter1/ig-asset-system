<?php
require_once __DIR__ . '/db.php';

class SettingsController {
  
  public static function getSettings($category = null) {
    $pdo = DB::conn();
    
    if ($category) {
      $stmt = $pdo->prepare("SELECT name, value, description FROM settings WHERE category = ? ORDER BY name");
      $stmt->execute([$category]);
    } else {
      $stmt = $pdo->prepare("SELECT category, name, value, description FROM settings ORDER BY category, name");
      $stmt->execute();
    }
    
    $settings = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
      if ($category) {
        $settings[$row['name']] = [
          'value' => $row['value'],
          'description' => $row['description']
        ];
      } else {
        $settings[$row['category']][$row['name']] = [
          'value' => $row['value'],
          'description' => $row['description']
        ];
      }
    }
    
    return $settings;
  }
  
  public static function updateSetting($category, $name, $value) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE category = ? AND name = ?");
    return $stmt->execute([$value, $category, $name]);
  }
  
  public static function updateSettings($category, $settings) {
    $pdo = DB::conn();
    $pdo->beginTransaction();
    
    try {
      $stmt = $pdo->prepare("UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE category = ? AND name = ?");
      
      foreach ($settings as $name => $value) {
        $stmt->execute([$value, $category, $name]);
      }
      
      $pdo->commit();
      return true;
    } catch (Exception $e) {
      $pdo->rollback();
      return false;
    }
  }
  
  public static function testLdapConnection($settings = null) {
    if (!$settings) {
      $settings = self::getSettings('ldap');
    }
    
    if (!function_exists('ldap_connect')) {
      return ['success' => false, 'message' => 'LDAP extension not installed'];
    }
    
    $host = $settings['host']['value'] ?? '';
    $port = intval($settings['port']['value'] ?? 389);
    $bindDn = $settings['bind_dn']['value'] ?? '';
    $bindPassword = $settings['bind_password']['value'] ?? '';
    
    if (empty($host) || empty($bindDn)) {
      return ['success' => false, 'message' => 'LDAP host and bind DN are required'];
    }
    
    $conn = ldap_connect($host, $port);
    if (!$conn) {
      return ['success' => false, 'message' => 'Could not connect to LDAP server'];
    }
    
    ldap_set_option($conn, LDAP_OPT_PROTOCOL_VERSION, 3);
    ldap_set_option($conn, LDAP_OPT_NETWORK_TIMEOUT, 5);
    
    if (!@ldap_bind($conn, $bindDn, $bindPassword)) {
      return ['success' => false, 'message' => 'LDAP bind failed: ' . ldap_error($conn)];
    }
    
    ldap_close($conn);
    return ['success' => true, 'message' => 'LDAP connection successful'];
  }
  
  public static function importLdapUsers($searchFilter = null) {
    $settings = self::getSettings('ldap');
    
    if (!function_exists('ldap_connect')) {
      return ['success' => false, 'message' => 'LDAP extension not installed'];
    }
    
    $host = $settings['host']['value'] ?? '';
    $port = intval($settings['port']['value'] ?? 389);
    $bindDn = $settings['bind_dn']['value'] ?? '';
    $bindPassword = $settings['bind_password']['value'] ?? '';
    $baseDn = $settings['base_dn']['value'] ?? '';
    $userAttr = $settings['user_attr']['value'] ?? 'sAMAccountName';
    
    $conn = ldap_connect($host, $port);
    if (!$conn) {
      return ['success' => false, 'message' => 'Could not connect to LDAP server'];
    }
    
    ldap_set_option($conn, LDAP_OPT_PROTOCOL_VERSION, 3);
    
    if (!@ldap_bind($conn, $bindDn, $bindPassword)) {
      return ['success' => false, 'message' => 'LDAP bind failed'];
    }
    
    // Default filter to find user accounts
    $filter = $searchFilter ?: "(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2))";
    
    $sr = ldap_search($conn, $baseDn, $filter, ['dn', 'mail', 'displayName', $userAttr]);
    if (!$sr) {
      return ['success' => false, 'message' => 'LDAP search failed'];
    }
    
    $entries = ldap_get_entries($conn, $sr);
    $imported = 0;
    $pdo = DB::conn();
    
    for ($i = 0; $i < $entries['count']; $i++) {
      $entry = $entries[$i];
      
      $username = $entry[$userAttr][0] ?? '';
      $displayName = $entry['displayname'][0] ?? $username;
      $email = $entry['mail'][0] ?? '';
      $dn = $entry['dn'];
      
      if (!empty($username)) {
        try {
          $stmt = $pdo->prepare("INSERT IGNORE INTO users (username, display_name, email, ad_dn, role) VALUES (?, ?, ?, ?, 'user')");
          if ($stmt->execute([$username, $displayName, $email, $dn])) {
            $imported++;
          }
        } catch (Exception $e) {
          // Skip duplicate users
        }
      }
    }
    
    ldap_close($conn);
    return ['success' => true, 'message' => "Imported $imported users from LDAP"];
  }
}