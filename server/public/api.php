<?php
header('Content-Type: application/json');
require_once __DIR__ . '/../src/db.php';
require_once __DIR__ . '/../src/utils.php';
require_once __DIR__ . '/../src/auth.php';
require_once __DIR__ . '/../src/AssetController.php';
require_once __DIR__ . '/../src/AgentController.php';
require_once __DIR__ . '/../src/UserController.php';
require_once __DIR__ . '/../src/SettingsController.php';
require_once __DIR__ . '/../src/SystemController.php';
require_once __DIR__ . '/../src/PollerController.php';
require_once __DIR__ . '/../src/CustomFieldsController.php';
require_once __DIR__ . '/../src/PreferencesController.php';

cors_headers();
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

$action = $_GET['action'] ?? '';

switch ($action) {

  case 'login':
    $in = json_input();
    $u = $in['username'] ?? '';
    $p = $in['password'] ?? '';
    $user = Auth::login($u, $p);
    if ($user) {
      session_start();
      $_SESSION['user'] = $user;
      echo json_encode(['ok'=>true, 'user'=>$user]);
    } else {
      http_response_code(401);
      echo json_encode(['error'=>'invalid_credentials']);
    }
    break;

  case 'me':
    session_start();
    echo json_encode(['user'=> ($_SESSION['user'] ?? null)]);
    break;

  case 'logout':
    session_start();
    $_SESSION = [];
    session_destroy();
    echo json_encode(['ok'=>true]);
    break;

  case 'assets':
    require_login();
    $q = $_GET['q'] ?? '';
    AssetController::list($q);
    break;

  case 'asset_get':
    require_login(); require_role('user');
    AssetController::get($_GET['id'] ?? '');
    break;

  case 'asset_get_by_ip':
    require_login(); require_role('user');
    AssetController::getByIp($_GET['ip'] ?? '');
    break;

  case 'asset_create':
    require_login(); require_role('user');
    AssetController::create(json_input(), 'manual');
    break;

  case 'asset_update':
    require_login(); require_role('user');
    $in = json_input();
    $id = $in['id'] ?? '';
    unset($in['id']);
    AssetController::update($id, $in, 'manual');
    break;

  case 'asset_delete':
    require_login(); require_role('admin');
    AssetController::delete($_GET['id'] ?? '');
    break;

  case 'users':
    require_login(); // Allow all logged-in users to see user list for asset ownership
    UserController::list();
    break;

  case 'agent_register':
    require_login(); require_role('admin');
    $in = json_input();
    AgentController::register($in['name'] ?? 'agent', $in['platform'] ?? 'other', $in['bind_asset'] ?? null);
    break;

  case 'agent_push':
    $token = $_SERVER['HTTP_X_AGENT_TOKEN'] ?? ($_GET['token'] ?? '');
    $payload = json_input();
    AgentController::push($token, $payload);
    break;

  case 'agent_download_linux':
    // Generate a tokenized Linux agent script on the fly
    $tok = $_GET['token'] ?? '';
    header('Content-Type: text/x-python');
    echo "#!/usr/bin/env python3\nTOKEN = '" . addslashes($tok) . "'\nAPI_URL = '"
      . addslashes((require __DIR__ . '/../config/config.php')['site']['base_url']) . "/api.php?action=agent_push'\n"
      . file_get_contents(__DIR__ . '/assets/agent_linux_template.py');
    break;

  case 'agent_download_windows':
    // Provide instructions (binary build left to developer), include token placeholder
    echo json_encode([
      'message' => 'Fetch the Windows C# agent from the repo and set the token in app.config or ENV.',
      'token' => $_GET['token'] ?? ''
    ]);
    break;

  case 'settings_get':
    require_login(); require_role('admin');
    $category = $_GET['category'] ?? null;
    echo json_encode(SettingsController::getSettings($category));
    break;

  case 'settings_update':
    require_login(); require_role('admin');
    $in = json_input();
    $category = $in['category'] ?? '';
    $settings = $in['settings'] ?? [];
    $success = SettingsController::updateSettings($category, $settings);
    echo json_encode(['success' => $success]);
    break;

  case 'ldap_test':
    require_login(); require_role('admin');
    $in = json_input();
    $result = SettingsController::testLdapConnection($in['settings'] ?? null);
    echo json_encode($result);
    break;

  case 'ldap_import':
    require_login(); require_role('admin');
    $in = json_input();
    $filter = $in['filter'] ?? null;
    $result = SettingsController::importLdapUsers($filter);
    echo json_encode($result);
    break;

  case 'system_status':
    echo json_encode(SystemController::getBootstrapStatus());
    break;

  case 'system_health':
    require_login(); require_role('admin');
    echo json_encode(SystemController::checkSystemHealth());
    break;

  case 'poller_status':
    require_login();
    echo json_encode(PollerController::getStatus());
    break;

  case 'poller_start':
    require_login(); require_role('admin');
    echo json_encode(PollerController::start());
    break;

  case 'poller_stop':
    require_login(); require_role('admin');
    echo json_encode(PollerController::stop());
    break;

  case 'poller_targets':
    require_login(); require_role('admin');
    echo json_encode(PollerController::getTargets());
    break;

  case 'poller_config':
    require_login(); require_role('admin');
    echo json_encode(PollerController::getConfig());
    break;

  case 'poller_config_update':
    require_login(); require_role('admin');
    $in = json_input();
    echo json_encode(PollerController::updateConfig($in));
    break;

  case 'poller_add_target':
    require_login(); require_role('admin');
    $in = json_input();
    echo json_encode(PollerController::addTarget($in));
    break;

  case 'poller_remove_target':
    require_login(); require_role('admin');
    $index = intval($_GET['index'] ?? 0);
    echo json_encode(PollerController::removeTarget($index));
    break;

  case 'poller_logs':
    require_login();
    $since = $_GET['since'] ?? null;
    echo json_encode(PollerController::getLogs($since));
    break;

  // Custom Fields Management
  case 'custom_fields':
    require_login(); require_role('user');
    CustomFieldsController::list();
    break;

  case 'custom_field_get':
    require_login(); require_role('user');
    CustomFieldsController::get($_GET['id'] ?? '');
    break;

  case 'custom_field_create':
    require_login(); require_role('admin');
    CustomFieldsController::create(json_input());
    break;

  case 'custom_field_update':
    require_login(); require_role('admin');
    $in = json_input();
    $id = $in['id'] ?? '';
    unset($in['id']);
    CustomFieldsController::update($id, $in);
    break;

  case 'custom_field_delete':
    require_login(); require_role('admin');
    CustomFieldsController::delete($_GET['id'] ?? '');
    break;

  case 'custom_field_values':
    require_login(); require_role('user');
    CustomFieldsController::getValues($_GET['asset_id'] ?? '');
    break;

  case 'custom_field_set_value':
    require_login(); require_role('user');
    $in = json_input();
    CustomFieldsController::setValue($in['asset_id'] ?? '', $in['field_id'] ?? '', $in['value'] ?? '');
    break;

  case 'custom_fields_for_type':
    require_login(); require_role('user');
    CustomFieldsController::getFieldsForType($_GET['type'] ?? '');
    break;

  case 'asset_columns_get':
    require_login();
    $allowedColumns = ['name','type','ips','mac','owner','status','last_seen','source','created_at','updated_at'];
    $defaultColumns = ['name','type','ips','mac','owner','status','last_seen'];
    $userId = intval($_SESSION['user']['id']);
    $columns = PreferencesController::get($userId, 'asset_table_columns', $defaultColumns);
    if (!is_array($columns)) {
      $columns = $defaultColumns;
    }
    $columns = array_values(array_intersect(array_unique(array_map('strval', $columns)), $allowedColumns));
    if (empty($columns)) {
      $columns = $defaultColumns;
    }
    echo json_encode([
      'columns' => $columns,
      'default' => $defaultColumns,
      'allowed' => $allowedColumns
    ]);
    break;

  case 'asset_columns_save':
    require_login();
    $allowedColumns = ['name','type','ips','mac','owner','status','last_seen','source','created_at','updated_at'];
    $defaultColumns = ['name','type','ips','mac','owner','status','last_seen'];
    $userId = intval($_SESSION['user']['id']);
    $in = json_input();
    $columns = isset($in['columns']) && is_array($in['columns']) ? $in['columns'] : [];
    $columns = array_values(array_intersect(array_unique(array_map('strval', $columns)), $allowedColumns));
    if (empty($columns)) {
      $columns = $defaultColumns;
    }
    PreferencesController::set($userId, 'asset_table_columns', $columns);
    echo json_encode(['success' => true, 'columns' => $columns]);
    break;

  default:
    echo json_encode(['error'=>'unknown_action']);
}
