<?php
function uuid_v4() {
  $data = random_bytes(16);
  $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
  $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
  return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}

function json_input() {
  $raw = file_get_contents('php://input');
  $data = json_decode($raw, true);
  return $data ?: [];
}

function require_login() {
  session_start();
  if (!isset($_SESSION['user'])) {
    http_response_code(401);
    echo json_encode(['error' => 'not_authenticated']);
    exit;
  }
}

function require_role($role) {
  if (!isset($_SESSION['user'])) {
    http_response_code(401);
    echo json_encode(['error' => 'not_authenticated']);
    exit;
  }
  $roles = ['viewer'=>1,'user'=>2,'admin'=>3];
  $have = $roles[$_SESSION['user']['role'] ?? 'viewer'] ?? 1;
  $need = $roles[$role] ?? 3;
  if ($have < $need) {
    http_response_code(403);
    echo json_encode(['error' => 'forbidden']);
    exit;
  }
}

function cors_headers() {
  $cfg = require __DIR__ . '/../config/config.php';
  if (($cfg['cors']['enabled'] ?? false) === true) {
    $origins = $cfg['cors']['origins'] ?? ['*'];
    header('Access-Control-Allow-Origin: ' . implode(',', $origins));
    header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
    header('Access-Control-Allow-Headers: Content-Type, Authorization, X-API-Key, X-Agent-Token');
    header('Access-Control-Allow-Credentials: true');
  }
}

function change_log($asset_id, $actor, $source, $field, $old, $new) {
  $pdo = DB::conn();
  $stmt = $pdo->prepare("INSERT INTO changes (asset_id, actor, source, field, old_value, new_value) VALUES (?, ?, ?, ?, CAST(? AS JSON), CAST(? AS JSON))");
  $stmt->execute([$asset_id, $actor, $source, $field, json_encode($old), json_encode($new)]);
}
