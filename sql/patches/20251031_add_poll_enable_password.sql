-- Patch: add enable password support for network polling
ALTER TABLE assets
  ADD COLUMN poll_enable_password VARCHAR(255) NULL AFTER poll_port;

ALTER TABLE assets
  MODIFY COLUMN poll_type VARCHAR(32) DEFAULT 'ping';
