<?php
class DB {
  private static $pdo = null;

  public static function conn() {
    if (self::$pdo) return self::$pdo;
    $cfg = require __DIR__ . '/../config/config.php';
    $dsn = "mysql:host={$cfg['db']['host']};port={$cfg['db']['port']};dbname={$cfg['db']['name']};charset=utf8mb4";
    self::$pdo = new PDO($dsn, $cfg['db']['user'], $cfg['db']['pass'], [
      PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
      PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    return self::$pdo;
  }
}
