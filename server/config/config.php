<?php
return [
  'db' => [
    'host' => '127.0.0.1',
    'port' => 3306,
    'name' => 'asset_tracker',
    'user' => 'asset_user',
    'pass' => 'asset_pass'
  ],
  'site' => [
    'base_url' => 'http://localhost:8080', // e.g., https://assets.yourdomain.com
    'session_name' => 'asset_sess',
    'session_secure' => false
  ],
  'security' => [
    'csrf_salt' => 'change-me',
    'token_salt' => 'change-me-too'
  ],
  'cors' => [
    'enabled' => true,
    'origins' => ['*']
  ]
];
