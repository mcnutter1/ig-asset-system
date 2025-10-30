<?php
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/utils.php';

class AssetController {
  public static function list($search='') {
    $pdo = DB::conn();
    if ($search) {
      $like = '%' . $search . '%';
      $stmt = $pdo->prepare("
        SELECT a.*, u.display_name as owner_name, u.email as owner_email 
        FROM assets a 
        LEFT JOIN users u ON a.owner_user_id = u.id 
        WHERE a.name LIKE ? OR a.mac LIKE ? OR a.id LIKE ? 
        ORDER BY a.updated_at DESC LIMIT 200
      ");
      $stmt->execute([$like,$like,$like]);
    } else {
      $stmt = $pdo->query("
        SELECT a.*, u.display_name as owner_name, u.email as owner_email 
        FROM assets a 
        LEFT JOIN users u ON a.owner_user_id = u.id 
        ORDER BY a.updated_at DESC LIMIT 200
      ");
    }
    $rows = $stmt->fetchAll();
    $count = count($rows);
    for ($i = 0; $i < $count; $i++) {
      $row = $rows[$i];
      $row['ips'] = self::ips($row['id']);
      $row['attributes'] = self::attributes($row['id']);
      try {
        $row['custom_fields'] = self::customFields($row['id']);
      } catch (Exception $e) {
        $row['custom_fields'] = [];
      }
      $rows[$i] = $row;
    }
    echo json_encode($rows);
  }

  public static function get($id) {
    $asset = self::fetchAssetById($id);
    if (!$asset) {
      http_response_code(404);
      echo json_encode(['error' => 'not_found']);
      return;
    }
    echo json_encode($asset);
  }

  public static function getByIp($ip = null, $mac = null) {
    $ipParam = trim((string)($ip ?? ''));
    $macParam = trim((string)($mac ?? ''));

    if ($ipParam === '' && $macParam === '') {
      http_response_code(400);
      echo json_encode(['error' => 'invalid_query', 'message' => 'Provide an ip or mac query parameter']);
      return;
    }

    $pdo = DB::conn();
    $matchedIds = [];

    $ipCandidates = [];

    if ($ipParam !== '') {
      $rawCandidates = preg_split('/[\s,]+/', $ipParam, -1, PREG_SPLIT_NO_EMPTY);
      foreach ($rawCandidates as $rawCandidate) {
        $candidate = trim($rawCandidate);
        if ($candidate === '') {
          continue;
        }
        $ipCandidates[] = $candidate;
      }
      if ($ipCandidates) {
        $ipCandidates = array_values(array_unique($ipCandidates));
      }
      $stmt = $pdo->prepare('SELECT DISTINCT asset_id FROM asset_ips WHERE ip = ?');
      foreach ($ipCandidates as $candidate) {
        $stmt->execute([$candidate]);
        $ids = $stmt->fetchAll(\PDO::FETCH_COLUMN);
        if ($ids) {
          $matchedIds = array_merge($matchedIds, $ids);
        }
      }
    }

    $macNormalized = null;
    if ($macParam !== '') {
      $normalizedCandidate = strtolower(preg_replace('/[^0-9a-f]/i', '', $macParam));
      if (strlen($normalizedCandidate) >= 12) {
        $macNormalized = $normalizedCandidate;
        $stmt = $pdo->prepare("SELECT id FROM assets WHERE mac IS NOT NULL AND mac <> '' AND REPLACE(REPLACE(LOWER(mac), ':', ''), '-', '') = ?");
        $stmt->execute([$macNormalized]);
        $ids = $stmt->fetchAll(\PDO::FETCH_COLUMN);
        if ($ids) {
          $matchedIds = array_merge($matchedIds, $ids);
        }
      }
    }

    $uniqueIds = array_values(array_unique(array_filter($matchedIds)));

    if (empty($uniqueIds)) {
      http_response_code(404);
      $message = [];
      if ($ipParam !== '') { $message[] = "IP: {$ipParam}"; }
      if ($macParam !== '') { $message[] = "MAC: {$macParam}"; }
      echo json_encode(['error' => 'not_found', 'message' => 'No asset found for ' . implode(' or ', $message)]);
      return;
    }

    $assets = [];
    foreach ($uniqueIds as $assetId) {
      $asset = self::fetchAssetById($assetId);
      if ($asset) {
        $assets[] = $asset;
      }
    }

    if (!$assets) {
      http_response_code(404);
      echo json_encode(['error' => 'not_found', 'message' => 'Assets were matched but could not be loaded']);
      return;
    }

    $response = [
      'count' => count($assets),
      'assets' => $assets,
      'query' => [
        'ip' => $ipCandidates,
        'mac' => $macNormalized
      ]
    ];

    if (count($assets) === 1) {
      $response['asset'] = $assets[0];
    }

    echo json_encode($response);
  }

  public static function create($data, $actor='manual') {
    $pdo = DB::conn();
    $id = uuid_v4();
    $ownerId = null;
    if (array_key_exists('owner_user_id', $data) && $data['owner_user_id'] !== '' && $data['owner_user_id'] !== null) {
      $ownerId = is_numeric($data['owner_user_id']) ? (int)$data['owner_user_id'] : null;
    }

    $pollAddress = null;
    if (array_key_exists('poll_address', $data)) {
      $value = trim((string)$data['poll_address']);
      if ($value !== '') {
        $pollAddress = $value;
      }
    }

    $stmt = $pdo->prepare("INSERT INTO assets (id,name,type,mac,poll_address,owner_user_id,source,poll_enabled,poll_type,poll_username,poll_password,poll_port) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)");
    $stmt->execute([
      $id,
      $data['name'] ?? 'Unnamed',
      $data['type'] ?? 'unknown',
      $data['mac'] ?? null,
      $pollAddress,
      $ownerId,
      $actor === 'manual' ? 'manual' : $actor,
      $data['poll_enabled'] ?? false,
      $data['poll_type'] ?? 'ping',
      $data['poll_username'] ?? null,
      $data['poll_password'] ?? null,
      $data['poll_port'] ?? null
    ]);
    if (!empty($data['ips'])) self::set_ips($id, $data['ips'], $actor);
    if (!empty($data['attributes'])) self::set_attributes($id, $data['attributes'], $actor);
    change_log($id, $_SESSION['user']['username'] ?? $actor, $actor, 'asset', null, ['created'=>true]);
    echo json_encode(['success'=>true, 'id'=>$id]);
  }

  public static function update($id, $data, $actor='manual') {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT * FROM assets WHERE id=?");
    $stmt->execute([$id]);
    $old = $stmt->fetch();
    if (!$old) { http_response_code(404); echo json_encode(['error'=>'not_found']); return; }

    $fields = ['name','type','mac','poll_address','owner_user_id','online_status','last_seen','poll_enabled','poll_type','poll_username','poll_password','poll_port'];

    if (array_key_exists('poll_address', $data)) {
      $pollAddress = trim((string)$data['poll_address']);
      $data['poll_address'] = $pollAddress === '' ? null : $pollAddress;
    }

    if (array_key_exists('owner_user_id', $data)) {
      $value = $data['owner_user_id'];
      if ($value === '' || $value === null) {
        $data['owner_user_id'] = null;
      } elseif (is_numeric($value)) {
        $data['owner_user_id'] = (int)$value;
      } else {
        $data['owner_user_id'] = null;
      }
    }
    $sets = []; $vals = [];
    foreach ($fields as $f) {
      if (array_key_exists($f, $data)) {
        $sets[] = "$f=?";
        $vals[] = $data[$f];
      }
    }
    if ($sets) {
      $vals[] = $id;
      $pdo->prepare("UPDATE assets SET " . implode(',', $sets) . " WHERE id=?")->execute($vals);
      foreach ($fields as $f) {
        if (array_key_exists($f, $data) && $old[$f] !== $data[$f]) {
          change_log($id, $_SESSION['user']['username'] ?? $actor, $actor, $f, $old[$f], $data[$f]);
        }
      }
    }
    if (isset($data['ips'])) self::set_ips($id, $data['ips'], $actor);
    if (isset($data['attributes'])) self::set_attributes($id, $data['attributes'], $actor);
    echo json_encode(['success'=>true]);
  }

  public static function delete($id) {
    $pdo = DB::conn();
    $pdo->prepare("DELETE FROM assets WHERE id=?")->execute([$id]);
    echo json_encode(['ok'=>true]);
  }

  private static function fetchAssetById($id) {
    if (!$id) {
      return null;
    }
    $pdo = DB::conn();
    $stmt = $pdo->prepare("
      SELECT a.*, u.display_name as owner_name, u.email as owner_email 
      FROM assets a 
      LEFT JOIN users u ON a.owner_user_id = u.id 
      WHERE a.id=?
    ");
    $stmt->execute([$id]);
    $asset = $stmt->fetch();
    if (!$asset) {
      return null;
    }
    $asset['ips'] = self::ips($id);
    $asset['attributes'] = self::attributes($id);
    try {
      $asset['custom_fields'] = self::customFields($id);
    } catch (Exception $e) {
      $asset['custom_fields'] = [];
    }
    $asset['changes'] = self::changes($id);
    return $asset;
  }

  private static function ips($id) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT family, ip FROM asset_ips WHERE asset_id=? ORDER BY id ASC");
    $stmt->execute([$id]);
    return $stmt->fetchAll();
  }

  private static function set_ips($id, $ips, $actor='manual') {
    $pdo = DB::conn();
    $pdo->prepare("DELETE FROM asset_ips WHERE asset_id=?")->execute([$id]);
    foreach ($ips as $ip) {
      $fam = filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6) ? 'ipv6' : 'ipv4';
      $pdo->prepare("INSERT INTO asset_ips (asset_id,family,ip) VALUES (?,?,?)")->execute([$id,$fam,$ip]);
    }
    change_log($id, $_SESSION['user']['username'] ?? $actor, $actor, 'ips', null, $ips);
  }

  private static function attributes($id) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT attributes FROM asset_attributes WHERE asset_id=?");
    $stmt->execute([$id]);
    $row = $stmt->fetch();
    return $row ? json_decode($row['attributes'], true) : new stdClass();
  }

  private static function customFields($id) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("
      SELECT cf.id, cf.name, cf.label, cf.field_type, cf.is_required, 
             cf.select_options, cf.help_text, cf.default_value, cfv.value
      FROM custom_fields cf
      LEFT JOIN custom_field_values cfv ON cf.id = cfv.field_id AND cfv.asset_id = ?
      ORDER BY cf.display_order ASC, cf.id ASC
    ");
    $stmt->execute([$id]);
    $fields = $stmt->fetchAll();
    
    // Decode JSON fields and structure the result
    $result = [];
    foreach ($fields as $field) {
      if ($field['select_options']) {
        $field['select_options'] = json_decode($field['select_options'], true);
      }
      $result[] = $field;
    }
    
    return $result;
  }

  private static function set_attributes($id, $attrs, $actor='manual') {
    $pdo = DB::conn();
    $json = json_encode($attrs);
    $stmt = $pdo->prepare("INSERT INTO asset_attributes (asset_id, attributes, updated_by) VALUES (?, CAST(? AS JSON), ?) ON DUPLICATE KEY UPDATE attributes=VALUES(attributes), updated_by=VALUES(updated_by)");
    $stmt->execute([$id, $json, $actor]);
    change_log($id, $_SESSION['user']['username'] ?? $actor, $actor, 'attributes', null, $attrs);
  }

  private static function changes($id) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT actor, source, field, old_value, new_value, changed_at FROM changes WHERE asset_id=? ORDER BY changed_at DESC LIMIT 200");
    $stmt->execute([$id]);
    return $stmt->fetchAll();
  }
}
