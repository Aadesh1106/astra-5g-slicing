#!/bin/bash
# ==============================================================================
# Comprehensive Healthcheck for Astra 5G Fabric (10 Switches, 15 Hosts)
#
# Runs 12 end-to-end operational checks across URLLC, eMBB, mMTC, MEC, and Probe.
# ==============================================================================
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"

fail=0
ok()  { echo "  [PASS] $1"; }
bad() { echo "  [FAIL] $1"; fail=$((fail+1)); }

reach() {
  hexec "$1" ping -c 2 -W 1 -q "$2" >/dev/null 2>&1
}

rtt_ms() {
  hexec "$1" ping -c 4 -i 0.2 -q "$2" 2>/dev/null | awk -F/ '/rtt/{print int($5)}'
}

measure_mbps() {
  local client_host="$1"
  local target_ip="$2"
  hexec h1 iperf3 -s -D -1 >/dev/null 2>&1
  sleep 1
  hexec "$client_host" iperf3 -c "$target_ip" -t 3 -J 2>/dev/null | python3 -c \
    'import json,sys; print(int(json.load(sys.stdin)["end"]["sum_received"]["bits_per_second"]/1e5))' 2>/dev/null || echo 0
}

echo "=== Running Astra 5G Fabric Healthcheck (12 Checks) ==="

# Check 1: URLLC Reachability (Cars -> Dedicated UPF h2)
echo "[1] URLLC Reachability (Cars h5, h6 -> h2)"
for h in h5 h6; do
  reach "$h" 10.0.0.2 && ok "$h -> URLLC UPF h2" || bad "$h -> h2 unreachable"
done

# Check 2: URLLC Latency across Fast-Path (Must be < 13ms)
echo "[2] URLLC Ultra-Low Latency Verification (< 13ms)"
for h in h5 h6; do
  r=$(rtt_ms "$h" 10.0.0.2)
  r=${r:-999}
  if [ "$r" -lt 13 ]; then
    ok "$h -> h2 RTT: ${r}ms (fast-path)"
  else
    bad "$h -> h2 RTT: ${r}ms (exceeds 13ms threshold)"
  fi
done

# Check 3: Industrial Robotics URLLC Reachability (Robot h12 -> h2)
echo "[3] Industrial Robotics URLLC Reachability (h12 -> h2)"
reach h12 10.0.0.2 && ok "Robot h12 -> URLLC UPF h2" || bad "Robot h12 -> h2 unreachable"

# Check 4: eMBB Phone Reachability (h3, h4 -> UPF h1)
echo "[4] eMBB Smartphones Reachability (h3, h4 -> h1)"
for h in h3 h4; do
  reach "$h" 10.0.0.1 && ok "$h -> eMBB UPF h1" || bad "$h -> h1 unreachable"
done

# Check 5: Stadium AR Headset Reachability (h13 -> h1)
echo "[5] Stadium AR/VR Headset Reachability (h13 -> h1)"
reach h13 10.0.0.1 && ok "AR Headset h13 -> eMBB UPF h1" || bad "AR Headset h13 -> h1 unreachable"

# Check 6: mMTC IoT Sensors Reachability (h7, h8, h9 -> Collector h1)
echo "[6] mMTC IoT Sensors Reachability (h7, h8, h9 -> h1)"
for h in h7 h8 h9; do
  reach "$h" 10.0.0.1 && ok "Sensor $h -> Collector h1" || bad "Sensor $h -> h1 unreachable"
done

# Check 7: Zero-Trust Slice Isolation (Strictly Blocked Matrix)
echo "[7] Zero-Trust Slice Isolation Enforcement"
reach h3 10.0.0.2 && bad "LEAK: Phone h3 reached URLLC UPF h2!" || ok "Phone h3 -> URLLC UPF blocked"
reach h7 10.0.0.2 && bad "LEAK: Sensor h7 reached URLLC UPF h2!" || ok "Sensor h7 -> URLLC UPF blocked"
reach h5 10.0.0.1 && bad "LEAK: Car h5 reached eMBB UPF h1!"     || ok "Car h5 -> eMBB UPF blocked"

# Check 8: eMBB Ingress Meter Rate Enforcement (~2.0 - 4.5 Mbps)
echo "[8] eMBB Ingress Meter Rate Enforcement (Phone h3)"
rate=$(measure_mbps h3 10.0.0.1)
rate=${rate:-0}
if [ "$rate" -ge 20 ] && [ "$rate" -le 45 ]; then
  ok "Phone h3 throughput is $(awk "BEGIN{print $rate/10}") Mbps (conforms to 4 Mbps cap)"
else
  bad "Phone h3 throughput is $(awk "BEGIN{print $rate/10}") Mbps (outside 2.0-4.5 Mbps range)"
fi

# Check 9: Lawful Intercept Probe Mirror (h11 captures URLLC telemetry)
echo "[9] Lawful Intercept Mirror Verification (Probe h11)"
for pair in "h5 10.0.0.5" "h6 10.0.0.6"; do
  set -- $pair
  hexec h11 timeout 4 tcpdump -nn -c 1 -i h11-eth0 "src host $2" >/tmp/hc_mirror.txt 2>&1 &
  sleep 1
  hexec "$1" ping -c 2 -W 1 -q 10.0.0.2 >/dev/null 2>&1
  wait
  if grep -q "$2" /tmp/hc_mirror.txt; then
    ok "Probe h11 successfully captured mirrored telemetry from $1"
  else
    bad "Probe h11 failed to capture mirrored telemetry from $1"
  fi
done

# Check 10: 3-Way Handover of Mobile Car h10 (s5 -> s6 -> s7 -> s5)
echo "[10] 3-Way Roaming Handover Verification for Mobile Car h10"
reach h10 10.0.0.2 && ok "h10 connected to gNodeB-A (s5)" || bad "h10 failed on s5"

bash "$ROOT/scripts/handover.sh" s6 >/dev/null 2>&1; sleep 2
reach h10 10.0.0.2 && ok "h10 reached UPF after roaming to gNodeB-B (s6)" || bad "h10 failed on s6"

bash "$ROOT/scripts/handover.sh" s7 >/dev/null 2>&1; sleep 2
reach h10 10.0.0.2 && ok "h10 reached UPF after roaming to gNodeB-C (s7)" || bad "h10 failed on s7"

bash "$ROOT/scripts/handover.sh" s5 >/dev/null 2>&1; sleep 2
reach h10 10.0.0.2 && ok "h10 restored after returning to gNodeB-A (s5)" || bad "h10 failed on return to s5"

# Check 11: MEC Edge Server Reachability (h14)
echo "[11] Low-Latency MEC Edge Server Reachability (h14 on Leaf s10)"
reach h14 10.0.0.1 && ok "MEC Server h14 reachable from DC leaf" || bad "MEC Server h14 unreachable"

# Check 12: NOC / OAM Telemetry Reachability (h15 on Regional s8)
echo "[12] NOC / OAM Telemetry Collector Reachability (h15 on Gateway s8)"
reach h15 10.0.0.1 && ok "NOC Collector h15 reachable" || bad "NOC Collector h15 unreachable"

echo
if [ "$fail" -eq 0 ]; then
  echo ">>> ALL 12 END-TO-END HEALTHCHECKS PASSED SUCCESSFULLY! <<<"
else
  echo ">>> [ALERT] $fail HEALTHCHECK(S) FAILED! <<<"
fi
exit "$fail"
