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
  'ldap' => [
    'enabled' => false,
    'host' => 'ldap://ad.example.com',
    'port' => 389,
    'bind_dn' => 'CN=ldap-reader,OU=Service Accounts,DC=example,DC=com',
    'bind_password' => 'REDACTED',
    'base_dn' => 'DC=example,DC=com',
    'user_attr' => 'sAMAccountName'
  ],
  'cors' => [
    'enabled' => true,
    'origins' => ['*']
  ];
