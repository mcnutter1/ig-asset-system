<?php
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/utils.php';

class AssetController {
  public static function list($search='') {
    $pdo = DB::conn();
    if ($search) {
      $like = '%' . $search . '%';
      $stmt = $pdo->prepare("SELECT * FROM assets WHERE name LIKE ? OR mac LIKE ? OR id LIKE ? ORDER BY updated_at DESC LIMIT 200");
      $stmt->execute([$like,$like,$like]);
    } else {
      $stmt = $pdo->query("SELECT * FROM assets ORDER BY updated_at DESC LIMIT 200");
    }
    $rows = $stmt->fetchAll();
    foreach ($rows as &$r) {
      $r['ips'] = self::ips($r['id']);
      $r['attributes'] = self::attributes($r['id']);
    }
    echo json_encode($rows);
  }

  public static function get($id) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT * FROM assets WHERE id=?");
    $stmt->execute([$id]);
    $asset = $stmt->fetch();
    if (!$asset) { http_response_code(404); echo json_encode(['error'=>'not_found']); return; }
    $asset['ips'] = self::ips($id);
    $asset['attributes'] = self::attributes($id);
    $asset['changes'] = self::changes($id);
    echo json_encode($asset);
  }

  public static function create($data, $actor='manual') {
    $pdo = DB::conn();
    $id = uuid_v4();
    $stmt = $pdo->prepare("INSERT INTO assets (id,name,type,mac,owner_user_id,source) VALUES (?,?,?,?,?,?)");
    $stmt->execute([
      $id,
      $data['name'] ?? 'Unnamed',
      $data['type'] ?? 'unknown',
      $data['mac'] ?? null,
      $data['owner_user_id'] ?? null,
      $actor === 'manual' ? 'manual' : $actor
    ]);
    if (!empty($data['ips'])) self::set_ips($id, $data['ips'], $actor);
    if (!empty($data['attributes'])) self::set_attributes($id, $data['attributes'], $actor);
    change_log($id, $_SESSION['user']['username'] ?? $actor, $actor, 'asset', null, ['created'=>true]);
    echo json_encode(['id'=>$id]);
  }

  public static function update($id, $data, $actor='manual') {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT * FROM assets WHERE id=?");
    $stmt->execute([$id]);
    $old = $stmt->fetch();
    if (!$old) { http_response_code(404); echo json_encode(['error'=>'not_found']); return; }

    $fields = ['name','type','mac','owner_user_id','online_status','last_seen'];
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
    echo json_encode(['ok'=>true]);
  }

  public static function delete($id) {
    $pdo = DB::conn();
    $pdo->prepare("DELETE FROM assets WHERE id=?")->execute([$id]);
    echo json_encode(['ok'=>true]);
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
