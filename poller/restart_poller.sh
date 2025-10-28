#!/bin/bash
# Restart the asset tracker poller

echo "Stopping any running poller processes..."
sudo pkill -9 -f poller_db.py 2>/dev/null
sleep 2

echo "Starting poller..."
cd /opt/ig-asset-system/poller
nohup python3 poller_db.py > /tmp/poller.log 2>&1 &

sleep 3

echo "Poller started. Checking logs..."
echo "----------------------------------------"
tail -30 /tmp/poller.log
echo "----------------------------------------"
echo ""
echo "To watch logs in real-time, run:"
echo "  tail -f /tmp/poller.log"
