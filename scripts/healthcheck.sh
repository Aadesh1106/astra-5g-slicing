#!/bin/bash
# 10 end-to-end checks of the slicing use case. Prints PASS/FAIL per check.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
fail=0
ok()  { echo "  PASS  $1"; }
bad() { echo "  FAIL  $1"; fail=$((fail+1)); }

reach() { hexec "$1" ping -c 2 -W 1 -q "$2" >/dev/null 2>&1; }
rtt()   { hexec "$1" ping -c 5 -i 0.2 -q "$2" 2>/dev/null | awk -F/ '/rtt/{print int($5)}'; }

echo "[1] URLLC reachability (cars -> URLLC UPF h2)"
for h in h5 h6; do reach $h 10.0.0.2 && ok "$h -> h2" || bad "$h -> h2 unreachable"; done

echo "[2] URLLC uses the SHORT path (RTT must be < 13 ms)"
for h in h5 h6; do
  r=$(rtt $h 10.0.0.2); r=${r:-999}
  [ "$r" -lt 13 ] && ok "$h -> h2 RTT ${r}ms" || bad "$h -> h2 RTT ${r}ms (long path?)"
done

echo "[3] eMBB reachability (phones -> h1)"
for h in h3 h4; do reach $h 10.0.0.1 && ok "$h -> h1" || bad "$h -> h1 unreachable"; done

echo "[4] mMTC reachability (sensors -> collector h1)"
for h in h7 h8 h9; do reach $h 10.0.0.1 && ok "$h -> h1" || bad "$h -> h1 unreachable"; done

echo "[5] Slice isolation (these MUST be blocked)"
reach h3 10.0.0.2 && bad "phone h3 reached URLLC UPF" || ok "h3 -> h2 blocked"
reach h7 10.0.0.2 && bad "sensor h7 reached URLLC UPF" || ok "h7 -> h2 blocked"
reach h5 10.0.0.1 && bad "car h5 reached eMBB UPF"     || ok "h5 -> h1 blocked"

echo "[6] eMBB meter: throughput should be ~3-4.5 Mbps (cap 4 Mbps)"
hexec h1 iperf3 -s -D -1 >/dev/null 2>&1; sleep 1
bw=$(hexec h3 iperf3 -c 10.0.0.1 -t 3 -J 2>/dev/null | python3 -c \
  'import json,sys;print(int(json.load(sys.stdin)["end"]["sum_received"]["bits_per_second"]/1e6*10))' 2>/dev/null)
bw=${bw:-0}
if [ "$bw" -ge 20 ] && [ "$bw" -le 45 ]; then ok "eMBB $(awk "BEGIN{print $bw/10}") Mbps"; else bad "eMBB throughput $(awk "BEGIN{print $bw/10}") Mbps (expected 2-4.5)"; fi

echo "[7] URLLC from both cars"
reach h6 10.0.0.2 && ok "h6 -> h2 again" || bad "h6 -> h2"

echo "[8] Mirror: probe h11 sees URLLC traffic from both cars (proves URLLC pipeline classification)"
for pair in "h5 10.0.0.5" "h6 10.0.0.6"; do
  set -- $pair
  hexec h11 timeout 5 tcpdump -nn -c 1 -i h11-eth0 "src host $2" >/tmp/mirror.txt 2>&1 &
  sleep 1; hexec $1 ping -c 2 -W 1 -q 10.0.0.2 >/dev/null 2>&1; wait
  grep -q "$2" /tmp/mirror.txt && ok "probe captured $1" || bad "probe saw nothing from $1"
done

echo "[9] Handover: mobile car h10 keeps URLLC service on s6, then returns"
reach h10 10.0.0.2 && ok "h10 -> h2 on s5" || bad "h10 -> h2 on s5"
bash "$ROOT/scripts/handover.sh" s6 >/dev/null; sleep 2
reach h10 10.0.0.2 && ok "h10 -> h2 on s6" || bad "h10 -> h2 after handover"
bash "$ROOT/scripts/handover.sh" s5 >/dev/null; sleep 2
reach h10 10.0.0.2 && ok "h10 -> h2 back on s5" || bad "h10 -> h2 after return"

echo "[10] Second phone h4 throughput"
hexec h1 iperf3 -s -D -1 >/dev/null 2>&1; sleep 1
bw=$(hexec h4 iperf3 -c 10.0.0.1 -t 3 -J 2>/dev/null | python3 -c   'import json,sys;print(int(json.load(sys.stdin)["end"]["sum_received"]["bits_per_second"]/1e5))' 2>/dev/null)
bw=${bw:-0}
[ "$bw" -ge 20 ] && [ "$bw" -le 45 ] && ok "h4 $(awk "BEGIN{print $bw/10}") Mbps" || bad "h4 throughput $(awk "BEGIN{print $bw/10}") Mbps (expected 2-4.5)"

echo; [ $fail -eq 0 ] && echo "ALL CHECKS PASSED" || echo "$fail CHECK(S) FAILED"
exit $fail
