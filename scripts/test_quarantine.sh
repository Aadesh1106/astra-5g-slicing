#!/bin/bash
# IoT quarantine: sensor h8 floods the collector, controller drops it for 30 s; h7 is unaffected.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; source "$ROOT/scripts/common.sh"
echo "--- h8 flood (500 pps for 8 s)"
hexec h8 ping -q -i 0.002 -c 4000 10.0.0.1 >/dev/null 2>&1 &
sleep 12
grep SEC "$ROOT/logs/ryu.log" | tail -2
echo "--- quarantine rule on s6:"; of dump-flows s6 table=0 | grep "priority=500"
hexec h8 ping -c 2 -W 1 -q 10.0.0.1 | tail -2 | head -1 | sed 's/^/h8 -> h1: /'
hexec h7 ping -c 2 -W 1 -q 10.0.0.1 | tail -2 | head -1 | sed 's/^/h7 -> h1: /'
wait
echo "--- rule expires by itself after 30 s (hard timeout)"
