-- Create or update the poller agent token
-- This allows the poller to authenticate with the API

-- Insert or update the poller agent
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
    status = 'active',
    last_seen = NOW();

-- Update settings to use the same token
INSERT INTO settings (category, name, value, description)
VALUES ('poller', 'api_key', 'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', 'API key for poller to authenticate')
ON DUPLICATE KEY UPDATE value = 'POLLR_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';

-- Verify the setup
SELECT 'Agent registration:' as step;
SELECT id, name, platform, token, status, last_seen FROM agents WHERE name = 'poller';

SELECT 'Poller settings:' as step;
SELECT category, name, value FROM settings WHERE category = 'poller';
