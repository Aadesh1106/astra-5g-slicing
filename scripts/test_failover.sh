#!/bin/bash
# Demonstrates URLLC fast failover: cut the SHORT path, watch traffic move to the LONG path.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
echo "--- before: RTT on SHORT path"; hexec h5 ping -c 3 -q 10.0.0.2 | tail -1
echo "--- cutting s1-eth2 (s1 <-> s4)"
sudo ip link set s1-eth2 down; sleep 1
echo "--- after: RTT on diagonal backup path s1->s3->s4 (expect higher RTT, 0% loss)"; hexec h5 ping -c 3 -q 10.0.0.2 | tail -2
echo "--- group stats on s1"; of dump-group-stats s1 | head -5
echo "--- restoring"; sudo ip link set s1-eth2 up; sleep 1
hexec h5 ping -c 3 -q 10.0.0.2 | tail -1
