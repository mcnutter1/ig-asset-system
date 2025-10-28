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
    exit 1
fi
echo "✅ Database connection successful"
echo

# Create database if it doesn't exist
echo "🗄️  Creating database if needed..."
mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" -e "CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;" 2>/dev/null
echo "✅ Database ready"
echo

# Apply SQL files in order
echo "📊 Setting up database schema..."

# Core schema
if [[ -f "sql/schema.sql" ]]; then
    echo "  → Applying core schema..."
    mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < sql/schema.sql
fi

# Patches table (for tracking)
if [[ -f "sql/patches_table.sql" ]]; then
    echo "  → Creating patches table..."
    mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < sql/patches_table.sql
fi

# Settings table
if [[ -f "sql/settings_table.sql" ]]; then
    echo "  → Creating settings table..."
    mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < sql/settings_table.sql
fi

# Admin user
if [[ -f "sql/admin_user.sql" ]]; then
    echo "  → Creating admin user..."
    mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < sql/admin_user.sql
fi

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
INSERT INTO patches (patch_name, patch_type, description, success) 
VALUES ('bootstrap_complete', 'system', 'Initial system bootstrap completed', 1)
ON DUPLICATE KEY UPDATE applied_at = CURRENT_TIMESTAMP;
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