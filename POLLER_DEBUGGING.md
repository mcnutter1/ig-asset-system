# Poller 401 Error - Debugging Guide

## Problem
The poller is getting a 401 (Unauthorized) error when trying to push updates to the API.

## Root Cause
The `agent_push` API endpoint requires a valid agent token that exists in the `agents` table with `status='active'`. The poller was configured with an API key in settings, but there was no corresponding agent record in the database.

## Solution

### Step 1: Set up the poller agent token

Run this SQL script on the remote database:

```bash
sshpass -p 'UkM3.D67RKw!7FZiUX*2' ssh rmcnutt@20.55.91.131 \
  "mysql -u asset_user -p'UkM3.D67RKw!7FZiUX*2' asset_tracker < /path/to/setup_poller_agent.sql"
```

Or manually execute:
```sql
INSERT INTO agents (id, name, platform, token, status, created_at, last_seen)
VALUES (
    'poller-agent-001',
    'poller',
    'linux',
    'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
    'active',
    NOW(),
    NOW()
)
ON DUPLICATE KEY UPDATE
    token = 'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
    status = 'active';
```

### Step 2: Deploy the enhanced poller

The updated `poller_db.py` includes:

1. **Enhanced logging** - Shows:
   - Full URL being called
   - HTTP status codes
   - Error messages from API responses
   - First 10 characters of the API key being used
   - Detailed error types (timeout, connection error, etc.)

2. **Agent token checking** - Automatically checks for a valid agent token in the database

3. **Better error handling** - Catches and logs different error types separately

Deploy it:
```bash
sshpass -p 'UkM3.D67RKw!7FZiUX*2' scp poller/poller_db.py rmcnutt@20.55.91.131:/tmp/
sshpass -p 'UkM3.D67RKw!7FZiUX*2' ssh rmcnutt@20.55.91.131 \
  "echo 'UkM3.D67RKw!7FZiUX*2' | sudo -S mv /tmp/poller_db.py /opt/ig-asset-system/poller/poller_db.py"
```

### Step 3: Restart the poller

```bash
sshpass -p 'UkM3.D67RKw!7FZiUX*2' ssh rmcnutt@20.55.91.131
# Find and kill the old poller process
sudo pkill -f poller_db.py

# Start the new poller
cd /opt/ig-asset-system/poller
nohup python3 poller_db.py > /tmp/poller.log 2>&1 &

# Watch the logs
tail -f /tmp/poller.log
```

### Step 4: Check the logs in the UI

The enhanced logging will now show in the web UI's log viewer:
- URL being called
- API response status
- Detailed error messages
- API key (first 10 chars for security)

## What the logs will show

**Before the fix (401 error):**
```
[INFO] Pushing update for MyAsset: http://localhost:8080/api.php?action=agent_push&token=POLLR_ABCD...
[INFO] API Response Status: 401
[ERROR] Authentication failed (401): {"error":"invalid_agent_token"}. API Key: POLLR_ABCD...
```

**After the fix (success):**
```
[INFO] Pushing update for MyAsset: http://localhost:8080/api.php?action=agent_push&token=POLLR_ABCD...
[INFO] API Response Status: 200
[SUCCESS] Successfully updated asset: MyAsset
```

## Verification

Check that the agent exists:
```sql
SELECT id, name, token, status, last_seen FROM agents WHERE name = 'poller';
```

Should return:
```
+------------------+--------+--------------------------------------------+--------+---------------------+
| id               | name   | token                                      | status | last_seen           |
+------------------+--------+--------------------------------------------+--------+---------------------+
| poller-agent-001 | poller | POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 | active | 2025-10-28 12:34:56 |
+------------------+--------+--------------------------------------------+--------+---------------------+
```

## Additional Debugging

If you still see 401 errors after this fix:

1. **Check the API URL** - Verify it points to the correct server
2. **Check the token matches** - Agent token in DB must match what's in settings
3. **Check agent status** - Must be 'active', not 'disabled' or 'revoked'
4. **Check API endpoint** - Verify `/api.php?action=agent_push` is accessible

The enhanced logging will show you exactly what's happening at each step.
