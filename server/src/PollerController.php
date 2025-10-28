<?php
require_once __DIR__ . '/db.php';

class PollerController {
  
  public static function getStatus() {
    try {
      $pdo = DB::conn();
      
      // Check if poller is currently running (simple approach using settings)
      $stmt = $pdo->prepare("SELECT value FROM settings WHERE category = 'poller' AND name = 'status'");
      $stmt->execute();
      $result = $stmt->fetch();
      
      $status = $result ? $result['value'] : 'stopped';
      
      // Get last run time
      $stmt = $pdo->prepare("SELECT value FROM settings WHERE category = 'poller' AND name = 'last_run'");
      $stmt->execute();
      $lastRun = $stmt->fetch();
      
      // Get polling targets count from assets table
      $stmt = $pdo->prepare("SELECT COUNT(*) as count FROM assets WHERE poll_enabled = TRUE");
      $stmt->execute();
      $countResult = $stmt->fetch();
      $targetsCount = $countResult ? intval($countResult['count']) : 0;
      
      return [
        'status' => $status,
        'last_run' => $lastRun ? $lastRun['value'] : null,
        'targets_count' => $targetsCount
      ];
      
    } catch (Exception $e) {
      return ['status' => 'error', 'message' => $e->getMessage(), 'targets_count' => 0];
    }
  }
  
  public static function start() {
    try {
      $pdo = DB::conn();
      
      // Set poller status to running
      $stmt = $pdo->prepare("
        INSERT INTO settings (category, name, value, description) 
        VALUES ('poller', 'status', 'running', 'Poller running status')
        ON DUPLICATE KEY UPDATE value = 'running', updated_at = CURRENT_TIMESTAMP
      ");
      $stmt->execute();
      
      return ['success' => true, 'message' => 'Poller started'];
      
    } catch (Exception $e) {
      return ['success' => false, 'message' => $e->getMessage()];
    }
  }
  
  public static function stop() {
    try {
      $pdo = DB::conn();
      
      // Set poller status to stopped
      $stmt = $pdo->prepare("
        INSERT INTO settings (category, name, value, description) 
        VALUES ('poller', 'status', 'stopped', 'Poller running status')
        ON DUPLICATE KEY UPDATE value = 'stopped', updated_at = CURRENT_TIMESTAMP
      ");
      $stmt->execute();
      
      return ['success' => true, 'message' => 'Poller stopped'];
      
    } catch (Exception $e) {
      return ['success' => false, 'message' => $e->getMessage()];
    }
  }
  
  public static function getConfig() {
    try {
      $pdo = DB::conn();
      $stmt = $pdo->prepare("SELECT name, value FROM settings WHERE category = 'poller'");
      $stmt->execute();
      $results = $stmt->fetchAll(PDO::FETCH_KEY_PAIR);
      
      // Set defaults for missing values
      $defaults = [
        'status' => 'stopped',
        'interval' => '30',
        'timeout' => '10', 
        'ping_timeout' => '1',
        'api_url' => 'http://localhost:8080/api.php',
        'api_key' => 'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
        'targets' => '[]'
      ];
      
      return array_merge($defaults, $results);
      
    } catch (Exception $e) {
      return [];
    }
  }
  
  public static function updateConfig($config) {
    try {
      $pdo = DB::conn();
      
      $pdo->beginTransaction();
      
      $stmt = $pdo->prepare("
        INSERT INTO settings (category, name, value, description) 
        VALUES ('poller', ?, ?, ?)
        ON DUPLICATE KEY UPDATE value = VALUES(value), updated_at = CURRENT_TIMESTAMP
      ");
      
      $descriptions = [
        'interval' => 'Polling interval in seconds',
        'timeout' => 'Connection timeout in seconds',
        'ping_timeout' => 'Ping timeout in seconds', 
        'api_url' => 'API endpoint URL',
        'api_key' => 'API authentication key',
        'targets' => 'Polling targets configuration'
      ];
      
      foreach ($config as $key => $value) {
        if ($key !== 'status') { // Don't allow updating status through config
          $description = $descriptions[$key] ?? "Poller $key setting";
          $stmt->execute([$key, $value, $description]);
        }
      }
      
      $pdo->commit();
      return ['success' => true, 'message' => 'Configuration updated'];
      
    } catch (Exception $e) {
      $pdo->rollback();
      return ['success' => false, 'message' => $e->getMessage()];
    }
  }
  
  public static function getTargets() {
    try {
      $pdo = DB::conn();
      
      $stmt = $pdo->prepare("SELECT value FROM settings WHERE category = 'poller' AND name = 'targets'");
      $stmt->execute();
      $result = $stmt->fetch();
      
      if ($result) {
        return json_decode($result['value'], true) ?: [];
      }
      
      return [];
      
    } catch (Exception $e) {
      return [];
    }
  }
  
  public static function updateTargets($targets) {
    try {
      $pdo = DB::conn();
      
      $stmt = $pdo->prepare("
        INSERT INTO settings (category, name, value, description) 
        VALUES ('poller', 'targets', ?, 'Polling targets configuration')
        ON DUPLICATE KEY UPDATE value = ?, updated_at = CURRENT_TIMESTAMP
      ");
      $targetsJson = json_encode($targets);
      $stmt->execute([$targetsJson, $targetsJson]);
      
      return ['success' => true, 'message' => 'Targets updated'];
      
    } catch (Exception $e) {
      return ['success' => false, 'message' => $e->getMessage()];
    }
  }
  
  public static function addTarget($target) {
    $targets = self::getTargets();
    $targets[] = $target;
    return self::updateTargets($targets);
  }
  
  public static function removeTarget($index) {
    $targets = self::getTargets();
    if (isset($targets[$index])) {
      array_splice($targets, $index, 1);
      return self::updateTargets($targets);
    }
    return ['success' => false, 'message' => 'Target not found'];
  }
  
  public static function updateLastRun() {
    try {
      $pdo = DB::conn();
      
      $stmt = $pdo->prepare("
        INSERT INTO settings (category, name, value, description) 
        VALUES ('poller', 'last_run', NOW(), 'Last poller execution time')
        ON DUPLICATE KEY UPDATE value = NOW(), updated_at = CURRENT_TIMESTAMP
      ");
      $stmt->execute();
      
      return true;
      
    } catch (Exception $e) {
      return false;
    }
  }
  
  public static function getLogs($since = null) {
    try {
      $pdo = DB::conn();
      
      if ($since) {
        $stmt = $pdo->prepare("
          SELECT id, timestamp, level, message, target 
          FROM poller_logs 
          WHERE id > ? 
          ORDER BY id ASC 
          LIMIT 100
        ");
        $stmt->execute([$since]);
      } else {
        $stmt = $pdo->prepare("
          SELECT id, timestamp, level, message, target 
          FROM poller_logs 
          ORDER BY id DESC 
          LIMIT 100
        ");
        $stmt->execute();
      }
      
      return $stmt->fetchAll(PDO::FETCH_ASSOC);
      
    } catch (Exception $e) {
      return [];
    }
  }
  
  public static function addLog($level, $message, $target = null) {
    try {
      $pdo = DB::conn();
      
      $stmt = $pdo->prepare("
        INSERT INTO poller_logs (level, message, target) 
        VALUES (?, ?, ?)
      ");
      $stmt->execute([$level, $message, $target]);
      
      // Clean up old logs (keep last 1000)
      $stmt = $pdo->prepare("
        DELETE FROM poller_logs 
        WHERE id < (
          SELECT id FROM (
            SELECT id FROM poller_logs ORDER BY id DESC LIMIT 1 OFFSET 1000
          ) AS tmp
        )
      ");
      $stmt->execute();
      
      return true;
      
    } catch (Exception $e) {
      return false;
    }
  }
}