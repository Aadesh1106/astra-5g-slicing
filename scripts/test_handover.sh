#!/bin/bash
# Mobile car h10 keeps reaching the URLLC UPF across a handover.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; source "$ROOT/scripts/common.sh"
echo "--- on s5:";  hexec h10 ping -c 3 -q 10.0.0.2 | tail -2
bash "$ROOT/scripts/handover.sh" s6; sleep 2
echo "--- on s6:";  hexec h10 ping -c 3 -q 10.0.0.2 | tail -2
echo "--- s3 route to h10 / s6 route:"; of dump-flows s6 table=1 | grep "10.0.0.10"
bash "$ROOT/scripts/handover.sh" s5; sleep 2
echo "--- back on s5:"; hexec h10 ping -c 3 -q 10.0.0.2 | tail -2
grep AMF "$ROOT/logs/ryu.log" | tail -4
