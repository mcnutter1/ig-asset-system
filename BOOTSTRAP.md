# Bootstrap System Documentation

## Overview

The Asset Tracker includes a simple bootstrap system that sets up the database and system for first-time use. This script is designed to be run once during initial deployment.

## Quick Start

```bash
# Run the bootstrap script
./bootstrap.sh
```

That's it! The script will:
- Check database connectivity
- Create the database if needed
- Apply all SQL schema files
- Create the admin user
- Set proper file permissions
- Mark the system as initialized

## What Bootstrap Does

### 1. **Database Setup**
- Creates the `asset_tracker` database if it doesn't exist
- Applies core schema from `sql/schema.sql`
- Creates patches tracking table from `sql/patches_table.sql`
- Sets up settings table from `sql/settings_table.sql`
- Creates user preferences table from `sql/user_preferences_table.sql`
- Creates admin user from `sql/admin_user.sql`

### 2. **System Configuration**
- Sets executable permissions on scripts
- Creates logs directory with proper permissions
- Marks bootstrap as complete in the database

### 3. **Default Credentials**
- **Username:** `admin`
- **Password:** `admin123`

## UI Integration

The application automatically detects if bootstrap has been run:

- **Not Bootstrapped:** Shows a warning overlay with instructions
- **Bootstrapped:** Normal login screen appears

## File Structure

```
/
├── bootstrap.sh              # Main bootstrap script
├── sql/
│   ├── schema.sql           # Core database schema
│   ├── patches_table.sql    # Patch tracking table
│   ├── settings_table.sql   # Application settings
│   ├── user_preferences_table.sql # Per-user UI preferences
│   └── admin_user.sql       # Default admin user
└── server/config/
    └── config.php           # Database configuration
```

## Requirements

- **MySQL/MariaDB** server running
- **PHP** installed (for reading config)
- **mysql** command line client
- Proper database credentials in `server/config/config.php`

## Troubleshooting

### Database Connection Failed
```bash
ERROR: Database connection failed!
```
**Solution:** Check your database configuration in `server/config/config.php`

### Permission Denied
```bash
./bootstrap.sh: Permission denied
```
**Solution:** Make the script executable:
```bash
chmod +x bootstrap.sh
```

### MySQL Command Not Found
```bash
mysql: command not found
```
**Solution:** Install MySQL client:
```bash
# macOS
brew install mysql-client

# Ubuntu/Debian
sudo apt-get install mysql-client

# CentOS/RHEL
sudo yum install mysql
```

## Running Bootstrap

1. **Clone the repository**
2. **Configure database** in `server/config/config.php`
3. **Run bootstrap:**
   ```bash
   ./bootstrap.sh
   ```
4. **Start your web server**
5. **Access the application** and login with `admin` / `admin123`

## Re-running Bootstrap

The bootstrap script is **idempotent** - safe to run multiple times. It uses SQL statements like:
- `CREATE TABLE IF NOT EXISTS`
- `INSERT ... ON DUPLICATE KEY UPDATE`

If you need to reset everything:
1. Drop the database
2. Run bootstrap again

## Applying Schema Updates to Existing Deployments

When a new SQL file is added (for example `sql/user_preferences_table.sql`), you can either rerun `./bootstrap.sh` or apply the file directly against your production database:

```bash
mysql -h <db_host> -P <db_port> -u <db_user> -p<db_pass> <db_name> < sql/user_preferences_table.sql
```

This command is safe to run multiple times thanks to `CREATE TABLE IF NOT EXISTS`.

## Next Steps After Bootstrap

1. **Login to the application**
2. **Change the admin password** (recommended)
3. **Configure LDAP settings** if needed
4. **Create additional users** or import from LDAP
5. **Start adding assets** to track

## Security Notes

- **Change the default admin password** in production
- **Restrict access** to the bootstrap script in production
- **Review database permissions** for the application user
- **Use HTTPS** in production environments

## Development vs Production

### Development
- Run bootstrap locally to set up your dev environment
- Safe to re-run when schema changes

### Production
- Run bootstrap once during initial deployment
- Consider backing up data before any schema changes
- Test bootstrap process in staging first

This simplified bootstrap system ensures your Asset Tracker is ready to go with a single command!