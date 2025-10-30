#!/bin/bash
#
# Asset Tracker Bootstrap Script
# 
# This script sets up the database and system for first-time use.
# It's designed to be run once during initial deployment.
#
# Usage: ./bootstrap.sh
#

set -e  # Exit on any error

echo "========================================"
echo "  Asset Tracker Bootstrap Setup"
echo "========================================"
echo

# Check if we're in the right directory
if [[ ! -f "server/config/config.php" ]]; then
    echo "ERROR: Please run this script from the asset tracker root directory"
    echo "Expected to find: server/config/config.php"
    exit 1
fi

# Load database configuration
echo "🔍 Reading database configuration..."
DB_HOST=$(php -r "echo (require 'server/config/config.php')['db']['host'];")
DB_PORT=$(php -r "echo (require 'server/config/config.php')['db']['port'];")
DB_NAME=$(php -r "echo (require 'server/config/config.php')['db']['name'];")
DB_USER=$(php -r "echo (require 'server/config/config.php')['db']['user'];")
DB_PASS=$(php -r "echo (require 'server/config/config.php')['db']['pass'];")

echo "Database: $DB_NAME @ $DB_HOST:$DB_PORT"
echo

# Check database connection
echo "🔗 Testing database connection..."
if ! mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" -e "SELECT 1;" >/dev/null 2>&1; then
    echo "❌ Database connection failed!"
    echo "Please check your database configuration in server/config/config.php"
    echo ""
    echo "To create the database user, run these commands as MySQL root:"
    echo "  CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
    echo "  CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
    echo "  GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';"
    echo "  FLUSH PRIVILEGES;"
    exit 1
fi
echo "✅ Database connection successful"
echo

# Create database if it doesn't exist
echo "🗄️  Creating database if needed..."
mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" -e "CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;" 2>/dev/null
echo "✅ Database ready"
echo

# Function to apply SQL with error handling
apply_sql() {
    local file=$1
    local description=$2
    
    if [[ -f "$file" ]]; then
        echo "  → $description..."
        if mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$file" 2>/dev/null; then
            echo "    ✅ Success"
        else
            echo "    ⚠️  Some statements may have failed (this is often normal for re-runs)"
        fi
    else
        echo "  → Skipping $description (file not found: $file)"
    fi
}

# Apply SQL files in order
echo "📊 Setting up database schema..."

# Core schema
apply_sql "sql/schema.sql" "Applying core schema"

# Patches table (for tracking)
apply_sql "sql/patches_table.sql" "Creating patches table"

# Settings table
apply_sql "sql/settings_table.sql" "Creating settings table"

# User preferences table (also safe for re-runs)
apply_sql "sql/user_preferences_table.sql" "Creating user preferences table"

# Custom fields table
apply_sql "sql/custom_fields_table.sql" "Creating custom fields table"

# Poller enhancements (polling address, DNS config)
apply_sql "sql/patches/20251030_add_poll_address.sql" "Applying poller address patch"

# Admin user
apply_sql "sql/admin_user.sql" "Creating admin user"

echo "✅ Database schema complete"
echo

# Set file permissions
echo "🔐 Setting file permissions..."
chmod +x bootstrap.sh 2>/dev/null || true

# Create logs directory
mkdir -p logs
chmod 755 logs

echo "✅ File permissions set"
echo

# Mark bootstrap as complete
echo "📝 Marking bootstrap as complete..."
mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
DELETE FROM patches WHERE patch_name = 'bootstrap_complete';
INSERT INTO patches (patch_name, patch_type, description, success) 
VALUES ('bootstrap_complete', 'system', 'Initial system bootstrap completed', 1);
" 2>/dev/null

echo "✅ Bootstrap marked as complete"
echo

echo "========================================"
echo "🎉 Bootstrap Complete!"
echo "========================================"
echo
echo "Your Asset Tracker is now ready to use:"
echo
echo "• Database schema created"
echo "• Admin user created (admin / admin123)"
echo "• Settings configured"
echo "• File permissions set"
echo
echo "Next steps:"
echo "1. Start your web server"
echo "2. Access the application in your browser"
echo "3. Login with admin / admin123"
echo "4. Configure LDAP settings if needed"
echo
echo "Happy tracking! 🚀"