# Asset Tracker

A simple, web-based asset tracking system with LDAP authentication support.

## Quick Start

1. **Configure Database**
   ```bash
   cp server/config/config.sample.php server/config/config.php
   # Edit database settings in config.php
   ```

2. **Run Bootstrap**
   ```bash
   ./bootstrap.sh
   ```

3. **Start Web Server**
   ```bash
   # Development (PHP built-in server)
   cd server/public
   php -S localhost:8080
   
   # Or use Apache/Nginx pointing to server/public/
   ```

4. **Access Application**
   - Open http://localhost:8080
   - Login with: `admin` / `admin123`

## Features

- **Asset Management**: Track computers, servers, IoT devices, etc.
- **LDAP Integration**: Authenticate against Active Directory
- **User Management**: Role-based access (admin, user, viewer)
- **RESTful API**: For integrations and agents
- **Bootstrap System**: Simple setup with `./bootstrap.sh`
- **Responsive UI**: Works on desktop and mobile

## System Requirements

- **PHP 7.4+** with PDO MySQL extension
- **MySQL 8.0+** or MariaDB 10.3+
- **Web Server** (Apache, Nginx, or PHP built-in)
- **LDAP extension** (optional, for LDAP auth)

## Configuration

### Database Settings
Edit `server/config/config.php`:
```php
'db' => [
  'host' => '127.0.0.1',
  'port' => 3306,
  'name' => 'asset_tracker',
  'user' => 'asset_user',
  'pass' => 'asset_pass'
]
```

### LDAP Settings
Configure via the web UI (Settings page) after logging in as admin.

## API Usage

### Authentication
```bash
curl -X POST http://localhost:8080/api.php?action=login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### List Assets
```bash
curl http://localhost:8080/api.php?action=assets \
  -H "Cookie: PHPSESSID=your_session_id"
```

### Create Asset
```bash
curl -X POST http://localhost:8080/api.php?action=asset_create \
  -H "Content-Type: application/json" \
  -H "Cookie: PHPSESSID=your_session_id" \
  -d '{"name":"My Computer","type":"workstation","mac":"00:11:22:33:44:55"}'
```

## File Structure

```
/
├── bootstrap.sh              # Setup script
├── BOOTSTRAP.md             # Bootstrap documentation
├── server/
│   ├── config/config.php    # Configuration
│   ├── public/              # Web root
│   │   ├── index.php       # Main app
│   │   ├── api.php         # REST API
│   │   └── assets/         # Frontend files
│   └── src/                # PHP classes
├── sql/                    # Database schema
├── agents/                 # Agent scripts
├── poller/                 # Network polling
└── frontend/              # Source frontend files
```

## Agents

Deploy agents on systems to automatically report asset information:

### Linux Agent
```bash
# Generate agent with token
curl "http://localhost:8080/api.php?action=agent_download_linux&token=YOUR_TOKEN" > agent.py
chmod +x agent.py
./agent.py
```

### Windows Agent
Compile the C# agent in `agents/windows/` with your API token.

## Development

### Adding Features
1. **Backend**: Add controllers in `server/src/`
2. **API**: Add endpoints in `server/public/api.php`
3. **Frontend**: Modify files in `frontend/` then copy to `server/public/assets/`
4. **Database**: Create SQL files in `sql/` and update bootstrap

### Database Changes
For schema changes, update the relevant SQL file in `sql/` and re-run bootstrap or apply manually.

## Security Notes

- **Change default admin password** in production
- **Use HTTPS** in production
- **Restrict database access** to application user only
- **Configure firewall** to limit API access
- **Review LDAP permissions** for service account

## Troubleshooting

### Bootstrap Fails
- Check database connection in `config.php`
- Ensure MySQL server is running
- Verify user has CREATE DATABASE privileges

### Login Issues
- Check if bootstrap completed successfully
- Verify database tables exist
- Check PHP error logs

### LDAP Problems
- Test connection via Settings page
- Verify LDAP extension is installed: `php -m | grep ldap`
- Check LDAP service account permissions

## License

MIT License - see LICENSE file for details.