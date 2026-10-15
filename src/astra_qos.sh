#!/bin/bash
# ==============================================================================
# Astra Mobility 5G Slice QoS Setup (Linux-HTB Queues)
#
# Hardware queue assignments on key trunks:
#   s1-eth2 (SHORT URLLC):   q0 = URLLC strict priority, q1 = mMTC best effort
#   s1-eth1 (LONG eMBB):     q0 = eMBB bandwidth cap,    q1 = mMTC spillover
#   s3-eth1 (mMTC uplink):   q0 = mMTC rate guaranteed
#   s10-eth1 (DC Leaf trunk): q0 = eMBB/MEC high priority, q1 = mMTC
#   s8-eth1 (gNodeB-C trunk): q0 = URLLC robot priority, q1 = AR eMBB
# ==============================================================================
set -e
echo "=== Configuring Astra 5G Linux-HTB Queues ==="

# Clean up previous QoS bindings
for P in s1-eth1 s1-eth2 s3-eth1 s3-eth2 s8-eth1 s8-eth2 s10-eth1; do
  sudo ovs-vsctl clear port "$P" qos 2>/dev/null || true
done
sudo ovs-vsctl --all destroy QoS 2>/dev/null || true
sudo ovs-vsctl --all destroy Queue 2>/dev/null || true

# 1. s1-eth2: URLLC Fast Path
echo "[1] s1-eth2: URLLC strict priority (Queue 0: 5-10 Mbps, prio 0)"
sudo ovs-vsctl set port s1-eth2 qos=@q -- \
    --id=@q create QoS type=linux-htb other-config:max-rate=10000000 \
        queues:0=@urllc queues:1=@mmtc -- \
    --id=@urllc create Queue other-config:min-rate=5000000 other-config:max-rate=10000000 \
        other-config:priority=0 external-ids:description="URLLC_slice" -- \
    --id=@mmtc create Queue other-config:min-rate=500000 other-config:max-rate=2000000 \
        other-config:priority=2 external-ids:description="mMTC_slice"

# 2. s1-eth1: eMBB Long Path
echo "[2] s1-eth1: eMBB rate-limited trunk (Queue 0: 2-4 Mbps, prio 1)"
sudo ovs-vsctl set port s1-eth1 qos=@q -- \
    --id=@q create QoS type=linux-htb other-config:max-rate=10000000 \
        queues:0=@embb queues:1=@mmtc2 -- \
    --id=@embb create Queue other-config:min-rate=2000000 other-config:max-rate=4000000 \
        other-config:priority=1 external-ids:description="eMBB_slice" -- \
    --id=@mmtc2 create Queue other-config:min-rate=500000 other-config:max-rate=1000000 \
        other-config:priority=2 external-ids:description="mMTC_spillover"

# 3. s3-eth1: mMTC Uplink
echo "[3] s3-eth1: mMTC sensor uplink toward UPF"
sudo ovs-vsctl set port s3-eth1 qos=@q -- \
    --id=@q create QoS type=linux-htb other-config:max-rate=10000000 queues:0=@m -- \
    --id=@m create Queue other-config:min-rate=500000 other-config:max-rate=2000000 \
        other-config:priority=2 external-ids:description="mMTC_slice_s3"

# 4. s10-eth1: Data Center Leaf Trunk
echo "[4] s10-eth1: DC Leaf UPF/MEC trunk (Queue 0: eMBB/MEC priority)"
sudo ovs-vsctl set port s10-eth1 qos=@q -- \
    --id=@q create QoS type=linux-htb other-config:max-rate=10000000 queues:0=@upf -- \
    --id=@upf create Queue other-config:min-rate=3000000 other-config:max-rate=10000000 \
        other-config:priority=1 external-ids:description="UPF_MEC_slice"

# 5. s8-eth1: Regional gNodeB-C Trunk
echo "[5] s8-eth1: Regional Stadium/Factory trunk (Queue 0: Robot URLLC, Queue 1: AR eMBB)"
sudo ovs-vsctl set port s8-eth1 qos=@q -- \
    --id=@q create QoS type=linux-htb other-config:max-rate=10000000 \
        queues:0=@robot queues:1=@ar -- \
    --id=@robot create Queue other-config:min-rate=4000000 other-config:max-rate=10000000 \
        other-config:priority=0 external-ids:description="URLLC_robot" -- \
    --id=@ar create Queue other-config:min-rate=2000000 other-config:max-rate=4000000 \
        other-config:priority=1 external-ids:description="eMBB_AR"

echo "=== Configured HTB Queues ==="
sudo ovs-vsctl --format=table --columns=external_ids,other_config list Queue | sort -u
