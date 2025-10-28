<?php
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/utils.php';
require_once __DIR__ . '/AssetController.php';

class AgentController {
  private static function token() {
    return bin2hex(random_bytes(24));
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
    $actor = 'agent';
    $asset_id = $asset['id'] ?? null;

    if ($asset_id) {
      AssetController::update($asset_id, [
        'name' => $asset['name'] ?? null,
        'mac'  => $asset['mac'] ?? null,
        'type' => $asset['type'] ?? null,
        'owner_user_id' => $asset['owner_user_id'] ?? null,
        'last_seen' => date('Y-m-d H:i:s'),
        'online_status' => ($payload['online_status'] ?? true) ? 'online' : 'offline',
        'ips' => $asset['ips'] ?? null,
        'attributes' => $asset['attributes'] ?? null
      ], $actor);
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
        AssetController::update($asset_id, [
          'name' => $asset['name'] ?? null,
          'mac'  => $asset['mac'] ?? null,
          'type' => $asset['type'] ?? null,
          'owner_user_id' => $asset['owner_user_id'] ?? null,
          'last_seen' => date('Y-m-d H:i:s'),
          'online_status' => ($payload['online_status'] ?? true) ? 'online' : 'offline',
          'ips' => $asset['ips'] ?? null,
          'attributes' => $asset['attributes'] ?? null
        ], $actor);
        echo json_encode(['ok'=>true]);
        return;
      }
    }
  }
}
