#!/bin/bash
# ==============================================================================
# 3-Way Handover of the Mobile Vehicle (h10) across gNodeBs
#
# Usage:
#   sudo bash scripts/handover.sh s5   # Move h10 to gNodeB-A Suburb (port 6)
#   sudo bash scripts/handover.sh s6   # Move h10 to gNodeB-B Smart City (port 5)
#   sudo bash scripts/handover.sh s7   # Move h10 to gNodeB-C Stadium (port 4)
# ==============================================================================
set -e

DEST_SW="$1"
case "$DEST_SW" in
  s5) TARGET_PORT=6 ;;
  s6) TARGET_PORT=5 ;;
  s7) TARGET_PORT=4 ;;
  *)
    echo "Usage: $0 s5|s6|s7"
    exit 1
    ;;
esac

# Find which switch currently has the host veth link (s5-eth6)
CURRENT_SW=$(sudo ovs-vsctl port-to-br s5-eth6 2>/dev/null || echo "")

if [ "$CURRENT_SW" = "$DEST_SW" ]; then
  echo "h10 is already connected to $DEST_SW (port $TARGET_PORT)"
  exit 0
fi

if [ -n "$CURRENT_SW" ]; then
  sudo ovs-vsctl del-port "$CURRENT_SW" s5-eth6
fi

# Attach port to destination switch with pinned OpenFlow port number
sudo ovs-vsctl add-port "$DEST_SW" s5-eth6 -- set Interface s5-eth6 ofport_request="$TARGET_PORT"
echo "Handover successful: h10 is now anchored to $DEST_SW on port $TARGET_PORT"
