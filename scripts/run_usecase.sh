#!/bin/bash
# ==============================================================================
# Start the Complete Astra 5G Fabric (10 Switches, 15 Hosts)
#
# Launches:
#   1. Ryu OpenFlow 1.3 Controller
#   2. Mininet 10-switch, 15-host Topology
#   3. Linux-HTB QoS Queues
#   4. End-to-End Healthcheck
# ==============================================================================
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RYU_BIN="${RYU_BIN:-$ROOT/.venv/bin/ryu-manager}"
mkdir -p "$ROOT/logs"

echo "=== Cleaning up previous instances and stale OVS bridges ==="
sudo pkill -f '[r]yu-manager' || true
sudo pkill -f '[a]stra_5g_topo' || true
for s in s1 s2 s3 s4 s5 s6 s7 s8 s9 s10; do
  sudo ovs-vsctl del-br "$s" 2>/dev/null || true
done
sudo mn -c >/dev/null 2>&1

echo "== 1. Launching Ryu 5G SDN Controller =="
$RYU_BIN "$ROOT/src/astra_controller.py" > "$ROOT/logs/ryu.log" 2>&1 &
sleep 3

echo "== 2. Starting Mininet Topology (10 Switches, 15 Hosts) =="
rm -f "$ROOT/mn_fifo"
mkfifo "$ROOT/mn_fifo"
nohup sudo python3 "$ROOT/src/astra_5g_topo.py" < "$ROOT/mn_fifo" > "$ROOT/logs/mn.log" 2>&1 &
( exec 3>"$ROOT/mn_fifo"; sleep 86400 ) &
sleep 8

echo "== 3. Applying Linux-HTB QoS Queues =="
sudo bash "$ROOT/src/astra_qos.sh" > "$ROOT/logs/qos.log" 2>&1 && echo "QoS Queues Active."

echo "== 4. Running End-to-End Baseline Healthcheck =="
sudo bash "$ROOT/scripts/healthcheck.sh"
