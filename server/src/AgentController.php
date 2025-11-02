<?php
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/utils.php';
require_once __DIR__ . '/AssetController.php';

class AgentController {
  private static function token() {
    return bin2hex(random_bytes(24));
  }

  public static function getAgentByToken($token, $updateLastSeen = false) {
    $trimmed = trim((string)$token);
    if ($trimmed === '') {
      return null;
    }

    try {
      $pdo = DB::conn();
      $stmt = $pdo->prepare("SELECT * FROM agents WHERE token = ? AND status = 'active'");
      $stmt->execute([$trimmed]);
      $agent = $stmt->fetch(PDO::FETCH_ASSOC);

      if ($agent && $updateLastSeen) {
        $update = $pdo->prepare("UPDATE agents SET last_seen = NOW() WHERE id = ?");
        $update->execute([$agent['id']]);
      }

      return $agent ?: null;
    } catch (Exception $e) {
      return null;
    }
  }

  public static function register($name, $platform, $bind_asset=null) {
    $pdo = DB::conn();
    $tok = self::token();
    $stmt = $pdo->prepare("INSERT INTO agents (name, token, platform, bound_asset) VALUES (?,?,?,?)");
    $stmt->execute([$name, $tok, $platform, $bind_asset]);
    $id = $pdo->lastInsertId();
    $cfg = require __DIR__ . '/../config/config.php';
    $base = rtrim($cfg['site']['base_url'], '/');
    $downloads = [
      'linux' => "$base/api.php?action=agent_download_linux&token=$tok",
      'windows' => "$base/api.php?action=agent_download_windows&token=$tok"
    ];
    echo json_encode(['id'=>$id,'token'=>$tok,'downloads'=>$downloads]);
  }

  public static function push($token, $payload) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT * FROM agents WHERE token=? AND status='active'");
    $stmt->execute([$token]);
    $agent = $stmt->fetch();
    if (!$agent) { http_response_code(401); echo json_encode(['error'=>'invalid_agent_token']); return; }

    $pdo->prepare("UPDATE agents SET last_seen=NOW() WHERE id=?")->execute([$agent['id']]);

    // Accept payload: { asset: { id|name|mac|ips|attributes|owner_user_id|type }, heartbeat: true/false, online_status }
    $asset = $payload['asset'] ?? [];
    if (!is_array($asset)) {
      http_response_code(400);
      echo json_encode(['error' => 'invalid_payload', 'message' => 'Asset payload must be an object']);
      return;
    }
    $actor = 'agent';
    $asset_id = $asset['id'] ?? null;

    $currentTimestamp = date('Y-m-d H:i:s');
    $onlineStatus = ($payload['online_status'] ?? true) ? 'online' : 'offline';

    $updateData = [
      'last_seen' => $currentTimestamp,
      'online_status' => $onlineStatus
    ];

    if (!empty($asset['mac'])) {
      $updateData['mac'] = $asset['mac'];
    }

    if (isset($asset['ips'])) {
      $ips = is_array($asset['ips']) ? array_values(array_filter($asset['ips'])) : [];
      if (!empty($ips)) {
        $updateData['ips'] = $ips;
      }
    }

    $attributesPayload = null;
    $attributeArray = [];
    if (isset($asset['attributes']) && (is_array($asset['attributes']) || is_object($asset['attributes']))) {
      $attributesPayload = $asset['attributes'];
      $attributeArray = json_decode(json_encode($attributesPayload), true) ?: [];
    }

    $pollerMeta = $attributeArray['poller'] ?? null;
    $pollerErrorMessage = null;
    if (is_array($pollerMeta) && array_key_exists('error', $pollerMeta)) {
      $pollerErrorMessage = trim((string)$pollerMeta['error']);
    }

    if ($pollerErrorMessage) {
      http_response_code(422);
      echo json_encode([
        'error' => 'probe_failed',
        'message' => $pollerErrorMessage ?: 'Poller reported an error and no data was collected',
        'timestamp' => $currentTimestamp
      ]);
      return;
    }

    $hasSubstantiveAttributes = false;
    if ($attributeArray) {
      $nonPollerKeys = array_diff(array_keys($attributeArray), ['poller']);
      if (!empty($nonPollerKeys)) {
        $hasSubstantiveAttributes = true;
      } else {
        if (is_array($pollerMeta)) {
          $pollerMetaCopy = $pollerMeta;
          unset($pollerMetaCopy['collected_at'], $pollerMetaCopy['warnings']);
          $pollerMetaCopy = array_filter($pollerMetaCopy, function ($value) {
            if (is_array($value)) {
              $innerFiltered = array_filter($value, function ($inner) {
                return $inner !== null && $inner !== '' && $inner !== [];
              });
              return !empty($innerFiltered);
            }
            return $value !== null && $value !== '';
          });
          if (!empty($pollerMetaCopy)) {
            $hasSubstantiveAttributes = true;
          }
        }
      }
    }

    if ($hasSubstantiveAttributes) {
      $updateData['attributes'] = $attributesPayload;
    }

    $hasMeaningfulUpdate = isset($updateData['mac']) || isset($updateData['ips']) || isset($updateData['attributes']) || ($onlineStatus === 'offline');

    if (!$hasMeaningfulUpdate) {
      http_response_code(422);
      echo json_encode([
        'error' => 'empty_update',
        'message' => 'Probe did not collect any asset changes; update rejected',
        'timestamp' => $currentTimestamp
      ]);
      return;
    }

    if ($asset_id) {
      AssetController::update($asset_id, $updateData, $actor);
      echo json_encode(['ok'=>true]);
      return;
    } else {
      // Upsert by MAC or name if id not provided
      if (!empty($asset['mac'])) {
        $s = $pdo->prepare("SELECT id FROM assets WHERE mac=? LIMIT 1");
        $s->execute([$asset['mac']]);
        $row = $s->fetch();
        if ($row) $asset_id = $row['id'];
      }
      if (!$asset_id && !empty($asset['name'])) {
        $s = $pdo->prepare("SELECT id FROM assets WHERE name=? LIMIT 1");
        $s->execute([$asset['name']]);
        $row = $s->fetch();
        if ($row) $asset_id = $row['id'];
      }
      if (!$asset_id) {
        // create
        AssetController::create([
          'name' => $asset['name'] ?? ('agent-' . substr($token,0,6)),
          'type' => $asset['type'] ?? 'unknown',
          'mac'  => $asset['mac'] ?? null,
          'owner_user_id' => $asset['owner_user_id'] ?? null,
          'ips' => $asset['ips'] ?? [],
          'attributes' => $asset['attributes'] ?? new stdClass()
        ], $actor);
        return;
      } else {
        AssetController::update($asset_id, $updateData, $actor);
        echo json_encode(['ok'=>true]);
        return;
      }
    }
  }
}
