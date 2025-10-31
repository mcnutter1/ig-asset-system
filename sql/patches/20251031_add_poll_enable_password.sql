-- Patch: add enable password support for network polling
ALTER TABLE assets
  ADD COLUMN poll_enable_password VARCHAR(255) NULL AFTER poll_port;
