#!/bin/bash
# ============================================
# Astra Mobility 5G Slice QoS (queues only)
# Flow rules, DSCP marking and the eMBB meter are installed by the
# RYU controller (src/astra_controller.py). This script only creates the
# Linux-HTB queues that the controller's set_queue actions point at:
#   s1-eth2 (SHORT, URLLC)  q0 URLLC   q1 mMTC
#   s1-eth1 (LONG,  eMBB)   q0 eMBB    q1 mMTC spillover
#   s3-eth1 (mMTC uplink)   q0 mMTC
# ============================================
set -e
echo "=== Astra 5G Slice QoS Setup ==="

for P in s1-eth1 s1-eth2 s3-eth1 s3-eth2; do
  sudo ovs-vsctl clear port $P qos 2>/dev/null || true
done
sudo ovs-vsctl --all destroy QoS 2>/dev/null || true
sudo ovs-vsctl --all destroy Queue 2>/dev/null || true

echo "[1] SHORT path s1-eth2: URLLC strict priority"
sudo ovs-vsctl set port s1-eth2 qos=@q -- \
    --id=@q create QoS type=linux-htb other-config:max-rate=10000000 \
        queues:0=@urllc queues:1=@mmtc -- \
    --id=@urllc create Queue other-config:min-rate=5000000 other-config:max-rate=10000000 \
        other-config:priority=0 external-ids:description="URLLC_slice" -- \
    --id=@mmtc create Queue other-config:min-rate=500000 other-config:max-rate=2000000 \
        other-config:priority=2 external-ids:description="mMTC_slice"

echo "[2] LONG path s1-eth1: eMBB rate limited"
sudo ovs-vsctl set port s1-eth1 qos=@q -- \
    --id=@q create QoS type=linux-htb other-config:max-rate=10000000 \
        queues:0=@embb queues:1=@mmtc2 -- \
    --id=@embb create Queue other-config:min-rate=2000000 other-config:max-rate=4000000 \
        other-config:priority=1 external-ids:description="eMBB_slice" -- \
    --id=@mmtc2 create Queue other-config:min-rate=500000 other-config:max-rate=1000000 \
        other-config:priority=2 external-ids:description="mMTC_spillover"

echo "[3] s3-eth1 (mMTC uplink toward the collector)"
sudo ovs-vsctl set port s3-eth1 qos=@q -- \
    --id=@q create QoS type=linux-htb other-config:max-rate=10000000 queues:0=@m -- \
    --id=@m create Queue other-config:min-rate=500000 other-config:max-rate=2000000 \
        other-config:priority=2 external-ids:description="mMTC_slice_s3"

echo "=== Queues ==="
sudo ovs-vsctl --format=table --columns=external_ids,other_config list Queue | sort -u
