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
    
    if (empty($host) || empty($bindDn) || empty($baseDn)) {
      return ['success' => false, 'message' => 'LDAP settings incomplete. Please configure host, bind DN, and base DN.'];
    }
    
    $conn = ldap_connect($host, $port);
    if (!$conn) {
      return ['success' => false, 'message' => 'Could not connect to LDAP server'];
    }
    
    ldap_set_option($conn, LDAP_OPT_PROTOCOL_VERSION, 3);
    ldap_set_option($conn, LDAP_OPT_NETWORK_TIMEOUT, 10);
    ldap_set_option($conn, LDAP_OPT_REFERRALS, 0);
    
    if (!@ldap_bind($conn, $bindDn, $bindPassword)) {
      $error = ldap_error($conn);
      ldap_close($conn);
      return ['success' => false, 'message' => "LDAP bind failed: $error"];
    }
    
    // Default filter to find active user accounts
    // Simplified version without bitwise matching for better compatibility
    // To exclude disabled accounts, you can add: (!(userAccountControl=514))(!(userAccountControl=546))
    if (empty($searchFilter)) {
      // Try simple filter first - just users who are people
      $filter = "(&(objectClass=user)(objectCategory=person))";
    } else {
      $filter = $searchFilter;
    }
    
    error_log("LDAP Import: Searching with filter: $filter in baseDN: $baseDn");
    
    $sr = @ldap_search($conn, $baseDn, $filter, ['dn', 'mail', 'displayName', $userAttr, 'memberOf', 'userAccountControl']);
    if (!$sr) {
      $error = ldap_error($conn);
      ldap_close($conn);
      return ['success' => false, 'message' => "LDAP search failed: $error. Filter: $filter"];
    }
    
    $entries = ldap_get_entries($conn, $sr);
    error_log("LDAP Import: Found {$entries['count']} entries");
    
    $imported = 0;
    $skipped = 0;
    $errors = [];
    $pdo = DB::conn();
    
    for ($i = 0; $i < $entries['count']; $i++) {
      $entry = $entries[$i];
      
      $username = $entry[strtolower($userAttr)][0] ?? '';
      $displayName = $entry['displayname'][0] ?? $username;
      $email = $entry['mail'][0] ?? '';
      $dn = $entry['dn'];
      $uac = $entry['useraccountcontrol'][0] ?? 0;
      
      if (empty($username)) {
        error_log("LDAP Import: Skipping entry with no username - DN: $dn");
        $skipped++;
        continue;
      }
      
      // Check if account is disabled (bit 2 of userAccountControl)
      // Common values: 512 = enabled, 514 = disabled, 546 = disabled+password not required
      if ($uac && ($uac & 2)) {
        error_log("LDAP Import: Skipping disabled account: $username (UAC: $uac)");
        $skipped++;
        continue;
      }
      
      try {
        $stmt = $pdo->prepare("INSERT IGNORE INTO users (username, display_name, email, ad_dn, role) VALUES (?, ?, ?, ?, 'user')");
        if ($stmt->execute([$username, $displayName, $email, $dn])) {
          if ($stmt->rowCount() > 0) {
            $imported++;
            error_log("LDAP Import: Imported user: $username ($displayName)");
          } else {
            $skipped++;
            error_log("LDAP Import: Skipped duplicate user: $username");
          }
        }
      } catch (Exception $e) {
        $skipped++;
        $errors[] = "Error importing $username: " . $e->getMessage();
        error_log("LDAP Import: Error importing $username: " . $e->getMessage());
      }
    }
    
    ldap_close($conn);
    
    $message = "Imported $imported users, skipped $skipped (duplicates/errors)";
    if (!empty($errors) && count($errors) <= 5) {
      $message .= ". Errors: " . implode(", ", $errors);
    }
    
    return ['success' => true, 'message' => $message, 'imported' => $imported, 'skipped' => $skipped];
  }
}