<?php
require_once __DIR__ . '/db.php';

class CustomFieldsController {
  
  // List all custom fields
  public static function list() {
    $pdo = DB::conn();
    $stmt = $pdo->query("SELECT * FROM custom_fields ORDER BY display_order ASC, id ASC");
    $fields = $stmt->fetchAll();
    
    // Decode JSON fields
    foreach ($fields as &$field) {
      if ($field['select_options']) {
        $field['select_options'] = json_decode($field['select_options'], true);
      }
      if ($field['applies_to_types']) {
        $field['applies_to_types'] = json_decode($field['applies_to_types'], true);
      }
    }
    
    echo json_encode($fields);
  }
  
  // Get a single custom field
  public static function get($id) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT * FROM custom_fields WHERE id=?");
    $stmt->execute([$id]);
    $field = $stmt->fetch();
    
    if (!$field) {
      http_response_code(404);
      echo json_encode(['error' => 'not_found']);
      return;
    }
    
    // Decode JSON fields
    if ($field['select_options']) {
      $field['select_options'] = json_decode($field['select_options'], true);
    }
    if ($field['applies_to_types']) {
      $field['applies_to_types'] = json_decode($field['applies_to_types'], true);
    }
    
    echo json_encode($field);
  }
  
  // Create a new custom field
  public static function create($data) {
    $pdo = DB::conn();
    
    // Encode JSON fields
    $select_options = self::prepareJsonField($data['select_options'] ?? null);
    $applies_to_types = self::prepareJsonField($data['applies_to_types'] ?? null);
    $is_required = self::normalizeBoolean($data['is_required'] ?? false);
    $display_order = self::normalizeInteger($data['display_order'] ?? 0);
    
    $stmt = $pdo->prepare("
      INSERT INTO custom_fields 
      (name, label, field_type, is_required, default_value, select_options, applies_to_types, display_order, help_text)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ");
    
    $stmt->execute([
      $data['name'] ?? '',
      $data['label'] ?? '',
      $data['field_type'] ?? 'text',
      $is_required,
      $data['default_value'] ?? null,
      $select_options,
      $applies_to_types,
      $display_order,
      $data['help_text'] ?? null
    ]);
    
    $id = $pdo->lastInsertId();
    echo json_encode(['id' => $id, 'message' => 'Custom field created']);
  }
  
  // Update a custom field
  public static function update($id, $data) {
    $pdo = DB::conn();
    
    // Check if field exists
    $stmt = $pdo->prepare("SELECT id FROM custom_fields WHERE id=?");
    $stmt->execute([$id]);
    if (!$stmt->fetch()) {
      http_response_code(404);
      echo json_encode(['error' => 'not_found']);
      return;
    }
    
    // Encode JSON fields
    $select_options = self::prepareJsonField($data['select_options'] ?? null);
    $applies_to_types = self::prepareJsonField($data['applies_to_types'] ?? null);
    $is_required = self::normalizeBoolean($data['is_required'] ?? false);
    $display_order = self::normalizeInteger($data['display_order'] ?? 0);
    
    $stmt = $pdo->prepare("
      UPDATE custom_fields SET
        name = ?,
        label = ?,
        field_type = ?,
        is_required = ?,
        default_value = ?,
        select_options = ?,
        applies_to_types = ?,
        display_order = ?,
        help_text = ?
      WHERE id = ?
    ");
    
    $stmt->execute([
      $data['name'] ?? '',
      $data['label'] ?? '',
      $data['field_type'] ?? 'text',
      $is_required,
      $data['default_value'] ?? null,
      $select_options,
      $applies_to_types,
      $display_order,
      $data['help_text'] ?? null,
      $id
    ]);
    
    echo json_encode(['message' => 'Custom field updated']);
  }
  
  // Delete a custom field
  public static function delete($id) {
    $pdo = DB::conn();
    
    // Check if field exists
    $stmt = $pdo->prepare("SELECT id FROM custom_fields WHERE id=?");
    $stmt->execute([$id]);
    if (!$stmt->fetch()) {
      http_response_code(404);
      echo json_encode(['error' => 'not_found']);
      return;
    }
    
    // Delete the field (cascade will delete values)
    $stmt = $pdo->prepare("DELETE FROM custom_fields WHERE id=?");
    $stmt->execute([$id]);
    
    echo json_encode(['message' => 'Custom field deleted']);
  }
  
  // Get custom field values for an asset
  public static function getValues($asset_id) {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("
      SELECT cf.id, cf.name, cf.label, cf.field_type, cf.is_required, cf.select_options, cf.help_text, cfv.value
      FROM custom_fields cf
      LEFT JOIN custom_field_values cfv ON cf.id = cfv.field_id AND cfv.asset_id = ?
      ORDER BY cf.display_order ASC, cf.id ASC
    ");
    $stmt->execute([$asset_id]);
    $fields = $stmt->fetchAll();
    
    // Decode JSON fields
    foreach ($fields as &$field) {
      if ($field['select_options']) {
        $field['select_options'] = json_decode($field['select_options'], true);
      }
    }
    
    echo json_encode($fields);
  }
  
  // Set custom field value for an asset
  public static function setValue($asset_id, $field_id, $value) {
    $pdo = DB::conn();
    
    // Upsert the value
    $stmt = $pdo->prepare("
      INSERT INTO custom_field_values (asset_id, field_id, value)
      VALUES (?, ?, ?)
      ON DUPLICATE KEY UPDATE value = VALUES(value)
    ");
    
    $stmt->execute([$asset_id, $field_id, $value]);
    
    echo json_encode(['message' => 'Value saved']);
  }
  
  // Get fields applicable to a specific asset type
  public static function getFieldsForType($asset_type) {
    $pdo = DB::conn();
    $stmt = $pdo->query("SELECT * FROM custom_fields ORDER BY display_order ASC, id ASC");
    $all_fields = $stmt->fetchAll();
    
    $applicable_fields = [];
    foreach ($all_fields as $field) {
      $applies_to = $field['applies_to_types'] ? json_decode($field['applies_to_types'], true) : null;
      
      // If applies_to_types is NULL, it applies to all types
      // If asset_type is in the array, it applies
      if ($applies_to === null || in_array($asset_type, $applies_to)) {
        if ($field['select_options']) {
          $field['select_options'] = json_decode($field['select_options'], true);
        }
        $applicable_fields[] = $field;
      }
    }
    
    echo json_encode($applicable_fields);
  }

  private static function normalizeBoolean($value): int {
    if (is_bool($value)) {
      return $value ? 1 : 0;
    }
    if (is_numeric($value)) {
      return ((int) $value) ? 1 : 0;
    }
    if (is_string($value)) {
      $normalized = strtolower(trim($value));
      if ($normalized === '') {
        return 0;
      }
      return in_array($normalized, ['1', 'true', 'yes', 'on'], true) ? 1 : 0;
    }
    return 0;
  }

  private static function normalizeInteger($value, $default = 0): int {
    if (is_numeric($value)) {
      return (int) $value;
    }
    if (is_string($value)) {
      $trimmed = trim($value);
      return is_numeric($trimmed) ? (int) $trimmed : (int) $default;
    }
    return (int) $default;
  }

  private static function prepareJsonField($value): ?string {
    if ($value === null) {
      return null;
    }
    if (is_string($value)) {
      $trimmed = trim($value);
      if ($trimmed === '') {
        return null;
      }
      $decoded = json_decode($trimmed, true);
      if (json_last_error() === JSON_ERROR_NONE) {
        $value = $decoded;
      } else {
        return json_encode($trimmed);
      }
    }
    return json_encode($value);
  }
}
?>
