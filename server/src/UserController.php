<?php
require_once __DIR__ . '/db.php';

class UserController {
  public static function list() {
    $pdo = DB::conn();
    $rows = $pdo->query("SELECT id, username, display_name, email, role FROM users ORDER BY id DESC LIMIT 200")->fetchAll();
    echo json_encode($rows);
  }
}
