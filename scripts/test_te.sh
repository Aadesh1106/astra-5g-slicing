#!/bin/bash
# Traffic engineering: two phones saturate the eMBB path -> controller moves h4 to the diagonal.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; source "$ROOT/scripts/common.sh"
hexec h1 iperf3 -s -p 5201 -D -1; hexec h1 iperf3 -s -p 5202 -D -1; sleep 1
hexec h3 iperf3 -c 10.0.0.1 -p 5201 -t 20 >/tmp/te_h3.txt 2>&1 &
hexec h4 iperf3 -c 10.0.0.1 -p 5202 -t 20 >/tmp/te_h4.txt 2>&1 &
sleep 14
echo "--- s1 flows for h4 (expect an output:4 override, cookie 0x6):"
of dump-flows s1 table=1 | grep "nw_src=10.0.0.4"
wait
grep TE "$ROOT/logs/ryu.log" | tail -5
echo "--- iperf receiver sums:"; grep -h receiver /tmp/te_h3.txt /tmp/te_h4.txt
