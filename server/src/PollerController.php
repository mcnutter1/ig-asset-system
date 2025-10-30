<?php
require_once __DIR__ . '/db.php';

class PollerController {

  private static function defaultSanitizationRules() {
    return [
      'version' => 1,
      'meta' => [
        'description' => 'Default poller sanitization rules',
      ],
      'rules' => [
        'ip_addresses' => [
          'exclude' => [
            'cidr' => ['127.0.0.0/8', '::1/128', 'fe80::/10'],
            'exact' => [],
            'prefix' => [],
            'suffix' => []
          ]
        ]
      ]
    ];
  }

  private static function normalizeSanitizationRules($rules) {
    $defaults = self::defaultSanitizationRules();
    if (!is_array($rules)) {
      return $defaults;
    }

    $normalized = array_replace_recursive($defaults, $rules);

    $buckets = ['cidr', 'exact', 'prefix', 'suffix'];
    foreach ($buckets as $bucket) {
      $items = $normalized['rules']['ip_addresses']['exclude'][$bucket] ?? [];
      if (!is_array($items)) {
        $items = [$items];
      }
      $items = array_values(array_unique(array_filter(array_map(function ($value) {
        return trim((string)$value);
      }, $items), function ($value) {
        return $value !== '';
      })));
      $normalized['rules']['ip_addresses']['exclude'][$bucket] = $items;
    }

    if (!isset($normalized['version']) || !is_numeric($normalized['version'])) {
      $normalized['version'] = $defaults['version'];
    }

    if (!isset($normalized['meta']) || !is_array($normalized['meta'])) {
      $normalized['meta'] = $defaults['meta'];
    }

    return $normalized;
  }

  private static function loadSanitizationRulesFromDb() {
    $defaults = self::defaultSanitizationRules();
    $prettyDefaults = json_encode($defaults, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);

    try {
      $pdo = DB::conn();
      $stmt = $pdo->prepare("SELECT value, updated_at FROM settings WHERE category = 'poller' AND name = 'sanitization_rules' LIMIT 1");
      $stmt->execute();
      $row = $stmt->fetch(PDO::FETCH_ASSOC);

      if ($row && isset($row['value'])) {
        $raw = trim((string)$row['value']);
        $decoded = json_decode($raw, true);
        if (!is_array($decoded)) {
          $decoded = $defaults;
        } else {
          $decoded = self::normalizeSanitizationRules($decoded);
        }
        $normalizedRaw = json_encode($decoded, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
        return [
          'rules' => $decoded,
          'raw' => $normalizedRaw,
          'updated_at' => $row['updated_at'] ?? null
        ];
      }
    } catch (Exception $e) {
      return [
        'rules' => $defaults,
        'raw' => $prettyDefaults,
        'updated_at' => null,
        'error' => $e->getMessage()
      ];
    }

    return [
      'rules' => $defaults,
      'raw' => $prettyDefaults,
      'updated_at' => null
    ];
  }

  public static function getSanitizationRules() {
    $loaded = self::loadSanitizationRulesFromDb();
    $response = [
      'success' => empty($loaded['error']),
      'rules' => $loaded['rules'],
      'raw' => $loaded['raw'],
      'updated_at' => $loaded['updated_at']
    ];

    if (!empty($loaded['error'])) {
      $response['message'] = $loaded['error'];
    }

    return $response;
  }

  public static function saveSanitizationRules($payload) {
    $raw = '';

    if (is_string($payload)) {
      $raw = $payload;
    } elseif (is_array($payload)) {
      if (isset($payload['raw'])) {
        $raw = (string)$payload['raw'];
      } elseif (isset($payload['rules'])) {
        $raw = json_encode($payload['rules']);
      }
    }

    $raw = trim((string)$raw);
    if ($raw === '') {
      return ['success' => false, 'message' => 'Rules JSON cannot be empty'];
    }

    $decoded = json_decode($raw, true);
    if (!is_array($decoded)) {
      return ['success' => false, 'message' => 'Rules must be valid JSON'];
    }

    $normalized = self::normalizeSanitizationRules($decoded);
    $stored = json_encode($normalized, JSON_UNESCAPED_SLASHES);
    $pretty = json_encode($normalized, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);

    try {
      $pdo = DB::conn();
      $stmt = $pdo->prepare("INSERT INTO settings (category, name, value, description) VALUES ('poller', 'sanitization_rules', ?, 'Poller sanitization rules') ON DUPLICATE KEY UPDATE value = VALUES(value), description = VALUES(description), updated_at = CURRENT_TIMESTAMP");
      $stmt->execute([$stored]);

      return [
        'success' => true,
        'rules' => $normalized,
        'raw' => $pretty
      ];
    } catch (Exception $e) {
      return ['success' => false, 'message' => $e->getMessage()];
    }
  }

  public static function getSanitizationRulesForAgent() {
    $loaded = self::loadSanitizationRulesFromDb();
    return [
      'success' => empty($loaded['error']),
      'rules' => $loaded['rules'],
      'raw' => $loaded['raw'],
      'checksum' => sha1($loaded['raw']),
      'updated_at' => $loaded['updated_at']
    ];
  }

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

  public static function listPollers() {
    try {
      $pdo = DB::conn();
      $stmt = $pdo->prepare("SELECT name, value, description FROM settings WHERE category = 'pollers' ORDER BY name ASC");
      $stmt->execute();
      $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

      $pollers = [];
      foreach ($rows as $row) {
        $config = [];
        if (!empty($row['value'])) {
          $decoded = json_decode($row['value'], true);
          if (is_array($decoded)) {
            $config = $decoded;
          }
        }

        $dnsServers = [];
        if (isset($config['dns_servers'])) {
          $raw = is_array($config['dns_servers']) ? $config['dns_servers'] : [$config['dns_servers']];
          $dnsServers = array_values(array_filter(array_map(function ($server) {
            return trim((string)$server);
          }, $raw)));
        } elseif (isset($config['dns_server'])) {
          $value = trim((string)$config['dns_server']);
          if ($value !== '') {
            $dnsServers = [$value];
          }
        }

        $pollers[] = [
          'name' => $row['name'],
          'dns_servers' => $dnsServers,
          'description' => $row['description'],
        ];
      }

      return ['success' => true, 'pollers' => $pollers];
    } catch (Exception $e) {
      return ['success' => false, 'message' => $e->getMessage()];
    }
  }

  public static function savePoller($data) {
    $name = trim((string)($data['name'] ?? ''));
    if ($name === '') {
      return ['success' => false, 'message' => 'Poller name is required'];
    }

    $dnsInput = $data['dns_servers'] ?? [];
    if (is_string($dnsInput)) {
      $dnsCandidates = array_map('trim', preg_split('/[\s,]+/', $dnsInput, -1, PREG_SPLIT_NO_EMPTY));
    } elseif (is_array($dnsInput)) {
      $dnsCandidates = array_map(function ($item) {
        return trim((string)$item);
      }, $dnsInput);
    } else {
      $dnsCandidates = [];
    }

    $dnsServers = array_values(array_unique(array_filter($dnsCandidates, function ($value) {
      return $value !== '';
    })));

    $payload = ['dns_servers' => $dnsServers];
    $description = trim((string)($data['description'] ?? 'Poller instance settings'));
    if ($description === '') {
      $description = 'Poller instance settings';
    }

    try {
      $pdo = DB::conn();
      $stmt = $pdo->prepare("INSERT INTO settings (category, name, value, description) VALUES ('pollers', ?, ?, ?) ON DUPLICATE KEY UPDATE value = VALUES(value), description = VALUES(description), updated_at = CURRENT_TIMESTAMP");
      $stmt->execute([$name, json_encode($payload), $description]);

      return [
        'success' => true,
        'poller' => [
          'name' => $name,
          'dns_servers' => $dnsServers,
          'description' => $description
        ]
      ];
    } catch (Exception $e) {
      return ['success' => false, 'message' => $e->getMessage()];
    }
  }

  public static function deletePoller($name) {
    $trimmed = trim((string)$name);
    if ($trimmed === '' || strtolower($trimmed) === 'default') {
      return ['success' => false, 'message' => 'Cannot delete default poller'];
    }

    try {
      $pdo = DB::conn();
      $stmt = $pdo->prepare("DELETE FROM settings WHERE category = 'pollers' AND name = ?");
      $stmt->execute([$trimmed]);

      return ['success' => $stmt->rowCount() > 0];
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