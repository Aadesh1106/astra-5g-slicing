#!/bin/bash
# ==============================================================================
# Behavioral Verification for Astra 5G Troubleshooting Incidents
#
# Usage:
#   sudo bash faults/verify.sh 1|2|3|4
# ==============================================================================
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"

fail=0
ok()  { echo "  [PASS] $1"; }
bad() { echo "  [FAIL] $1"; fail=$((fail+1)); }

reach() {
  hexec "$1" ping -c 2 -W 1 -q "$2" >/dev/null 2>&1
}

measure_mbps() {
  local client_host="$1"
  local target_ip="$2"
  hexec h1 iperf3 -s -D -1 >/dev/null 2>&1
  sleep 1
  hexec "$client_host" iperf3 -c "$target_ip" -t 3 -J 2>/dev/null | python3 -c \
    'import json,sys; print(int(json.load(sys.stdin)["end"]["sum_received"]["bits_per_second"]/1e5))' 2>/dev/null || echo 0
}

case "$1" in
# ------------------------------------------------------------------------------
# INC-1 Verification: Fast-Failover & Ring Resilience
# ------------------------------------------------------------------------------
1)
  echo "=== [Verify Incident 1] URLLC Fast-Failover Resilience ==="
  reach h5 10.0.0.2 && ok "Normal path: h5 -> URLLC UPF reachable" || bad "Normal path unreachable"
  
  echo "  Simulating fiber cut on primary trunk (s1-eth2 down)..."
  sudo ip link set s1-eth2 down
  sleep 1
  
  reach h5 10.0.0.2 && ok "h5 -> h2 survives fiber cut via backup diagonal" || bad "h5 black-holed during fiber cut"
  reach h6 10.0.0.2 && ok "h6 -> h2 survives fiber cut via backup diagonal" || bad "h6 black-holed during fiber cut"
  reach h12 10.0.0.2 && ok "Robot h12 -> h2 reaches URLLC UPF" || bad "Robot h12 cannot reach h2"
  
  echo "  Restoring primary trunk (s1-eth2 up)..."
  sudo ip link set s1-eth2 up
  sleep 1
  reach h5 10.0.0.2 && ok "Primary trunk traffic restored" || bad "Primary trunk traffic not restored"
  ;;

# ------------------------------------------------------------------------------
# INC-2 Verification: 3-Way Roaming & Handover Downlink Routing
# ------------------------------------------------------------------------------
2)
  echo "=== [Verify Incident 2] Mobile UE 3-Way Roaming & Downlink Routing ==="
  reach h10 10.0.0.2 && ok "h10 reachable on gNodeB-A (s5)" || bad "h10 unreachable on s5"
  
  echo "  Executing handover to gNodeB-B (s6)..."
  bash "$ROOT/scripts/handover.sh" s6 >/dev/null 2>&1
  sleep 2
  reach h10 10.0.0.2 && ok "h10 reachable after handover to s6" || bad "h10 lost on s6"

  echo "  Executing handover to gNodeB-C (s7)..."
  bash "$ROOT/scripts/handover.sh" s7 >/dev/null 2>&1
  sleep 2
  reach h10 10.0.0.2 && ok "h10 reachable after handover to s7" || bad "h10 lost on s7 (downlink route stuck?)"
  
  echo "  Returning h10 back to home base (s5)..."
  bash "$ROOT/scripts/handover.sh" s5 >/dev/null 2>&1
  sleep 2
  reach h10 10.0.0.2 && ok "h10 back on s5" || bad "h10 lost after returning to s5"
  ;;

# ------------------------------------------------------------------------------
# INC-3 Verification: Cross-Layer QoS (Meter + Policing + HTB)
# ------------------------------------------------------------------------------
3)
  echo "=== [Verify Incident 3] Cross-Layer QoS & Throughput ==="
  # Check AR Headset h13 throughput (cap is 4 Mbps)
  rate=$(measure_mbps h13 10.0.0.1)
  if [ "${rate:-0}" -ge 20 ]; then
    ok "AR Headset h13 throughput is $(awk "BEGIN{print $rate/10}") Mbps (>= 2 Mbps)"
  else
    bad "AR Headset h13 throttled: only $(awk "BEGIN{print ${rate:-0}/10}") Mbps (expected ~4 Mbps)"
  fi

  # Check DC Leaf QoS Queue attachment
  if sudo ovs-vsctl get port s10-eth1 qos | grep -qv '\[\]'; then
    ok "Hardware QoS queues correctly bound to DC Leaf trunk s10-eth1"
  else
    bad "No QoS queues attached to s10-eth1 (slice isolation broken)"
  fi

  # Check interface ingress policing rate on regional trunk s8-eth2
  policing=$(sudo ovs-vsctl get interface s8-eth2 ingress_policing_rate 2>/dev/null || echo "0")
  if [ "$policing" = "0" ]; then
    ok "Regional trunk interface s8-eth2 is not choked by ingress policing"
  else
    bad "Interface s8-eth2 has rogue ingress policing active: ${policing} kbps"
  fi
  ;;

# ------------------------------------------------------------------------------
# INC-4 Verification: Zero-Trust Security Boundary & Policy Drift
# ------------------------------------------------------------------------------
4)
  echo "=== [Verify Incident 4] Zero-Trust Boundary & Security Policy ==="
  # Check 1: IoT Sensor h7 MUST be blocked from URLLC UPF h2
  if reach h7 10.0.0.2; then
    bad "SECURITY LEAK: Sensor h7 can ping isolated URLLC UPF h2!"
  else
    ok "Zero-trust verified: Sensor h7 -> URLLC UPF h2 is strictly blocked"
  fi

  # Check 2: Smart Meter h9 MUST reach collector h1
  reach h9 10.0.0.1 && ok "Sensor h9 -> UPF collector h1 reachable" || bad "Sensor h9 is silently blackholed"

  # Check 3: Lawful Intercept Probe h11 sees mirrored traffic from both cars
  for car_ip in 10.0.0.5 10.0.0.6; do
    host_name=$([ "$car_ip" = "10.0.0.5" ] && echo "h5" || echo "h6")
    hexec h11 timeout 4 tcpdump -nn -c 1 -i h11-eth0 "src host $car_ip" >/tmp/v4_probe.txt 2>&1 &
    sleep 1
    hexec "$host_name" ping -c 2 -W 1 -q 10.0.0.2 >/dev/null 2>&1
    wait
    if grep -q "$car_ip" /tmp/v4_probe.txt; then
      ok "Probe h11 captured mirrored telemetry from $host_name ($car_ip)"
    else
      bad "Probe h11 saw nothing from $host_name (TOS/DSCP misclassified?)"
    fi
  done
  ;;

*)
  echo "Usage: $0 1|2|3|4"
  exit 1
  ;;
esac

echo
if [ "$fail" -eq 0 ]; then
  echo ">>> [SUCCESS] SCENARIO $1 RESOLUTION VERIFIED AND CONFIRMED! <<<"
else
  echo ">>> [ATTENTION] $fail CHECK(S) STILL FAILING IN SCENARIO $1 <<<"
fi
exit "$fail"
