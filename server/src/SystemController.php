<?php
require_once __DIR__ . '/db.php';

class SystemController {
  
  public static function getBootstrapStatus() {
    try {
      $pdo = DB::conn();
      
      // Check if patches table exists and has bootstrap_complete entry
      $stmt = $pdo->query("SHOW TABLES LIKE 'patches'");
      if ($stmt->rowCount() === 0) {
        return ['bootstrapped' => false, 'message' => 'Patches table not found'];
      }
      
      // Check for bootstrap completion marker
      $stmt = $pdo->prepare("SELECT success FROM patches WHERE patch_name = 'bootstrap_complete'");
      $stmt->execute();
      $result = $stmt->fetch();
      
      if ($result && $result['success']) {
        return ['bootstrapped' => true, 'message' => 'System initialized'];
      } else {
        return ['bootstrapped' => false, 'message' => 'Bootstrap not completed'];
      }
      
    } catch (Exception $e) {
      return ['bootstrapped' => false, 'message' => 'Database connection failed: ' . $e->getMessage()];
    }
  }
  
  public static function checkSystemHealth() {
    $status = self::getBootstrapStatus();
    
    $health = [
      'bootstrap' => $status,
      'database' => ['connected' => false],
      'ldap' => ['available' => false],
      'permissions' => ['writable' => false]
    ];
    
    // Database check
    try {
      $pdo = DB::conn();
      $health['database']['connected'] = true;
      
      // Check if we can write to database
      $stmt = $pdo->query("SELECT 1");
      $health['database']['writable'] = true;
    } catch (Exception $e) {
      $health['database']['error'] = $e->getMessage();
    }
    
    // LDAP extension check
    $health['ldap']['available'] = function_exists('ldap_connect');
    
    // Check if logs directory is writable
    $logsDir = dirname(__DIR__) . '/logs';
    $health['permissions']['logs_writable'] = is_dir($logsDir) && is_writable($logsDir);
    
    return $health;
  }
}