#!/bin/bash
# ==============================================================================
# Inject Troubleshooting Incidents into a Running Astra 5G Fabric
#
# Usage:
#   sudo bash faults/inject.sh 1|2|3|4|all
#
# Incidents:
#   1: Fast-failover chain broken (s1/s4 groups + s3 transit route)
#   2: Mobile UE handover downlink stuck due to high-priority stale rules
#   3: Multi-layer QoS degradation (Meter 101 + Ingress policing + HTB queue)
#   4: Zero-trust security drift (Slice boundary leak + Rogue DSCP remark + Rogue drop)
# ==============================================================================
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"

# Incident 1: Break Fast-Failover Groups, s3 Transit, and Queue Assignment
inject_inc1() {
  echo "[Inject 1] Breaking fast-failover backup buckets, s3 transit, and queue..."
  of mod-group s1 "group_id=1,type=ff,bucket=watch_port:2,actions=set_queue:0,output:2,bucket=watch_port:2,actions=output:2"
  of mod-group s4 "group_id=2,type=ff,bucket=watch_port:2,actions=output:2,bucket=watch_port:2,actions=output:2"
  of --strict del-flows s3 "table=1,priority=100,ip,nw_dst=10.0.0.2"
  of add-flow s3 "table=1,priority=100,ip,nw_dst=10.0.0.2,actions=output:1"
}

# Incident 2: Port Down, Stale DC Spine Route, L2 MAC Tampering, and Aggregator Pin
inject_inc2() {
  echo "[Inject 2] Disabling gateway port, pinning stale DC routes, and corrupting L2 MAC..."
  of mod-port s8 1 down
  of add-flow s9 "table=1,priority=250,cookie=0x4,ip,nw_dst=10.0.0.10,actions=output:1"
  of add-flow s7 "table=1,priority=200,cookie=0x4,ip,nw_dst=10.0.0.10,actions=mod_dl_dst:de:ad:be:ef:00:00,output:4"
  of add-flow s1 "table=1,priority=250,cookie=0x4,ip,nw_dst=10.0.0.10,actions=output:3"
}

# Incident 3: Multi-Layer QoS Degradation
inject_inc3() {
  echo "[Inject 3] Choking meter, applying ingress policing, and detaching queue..."
  of mod-meter s7 "meter=102,kbps,burst,band=type=drop,rate=100,burst_size=10"
  sudo ovs-vsctl set interface s8-eth2 ingress_policing_rate=200 ingress_policing_burst=20
  sudo ovs-vsctl clear port s10-eth1 qos
}

# Incident 4: Zero-Trust Security Drift, Meter Starvation, DSCP Strip, and Corrupted Tag
inject_inc4() {
  echo "[Inject 4] Deleting sensor ACL, starving meter 109, remarking car DSCP, and corrupting tag..."
  of --strict del-flows s6 "table=0,priority=400,ip,nw_src=10.0.0.7,nw_dst=10.0.0.2"
  of add-meter s6 "meter=109,kbps,burst,band=type=drop,rate=1,burst_size=1"
  of add-flow s6 "table=0,priority=500,cookie=0x5,ip,nw_src=10.0.0.9,actions=meter:109,goto_table:1"
  of add-flow s5 "table=0,priority=310,cookie=0x3,ip,nw_src=10.0.0.6,actions=mod_nw_tos:136,goto_table:1"
  of add-flow s6 "table=0,priority=305,cookie=0x3,ip,nw_src=10.0.0.8,actions=goto_table:1"
}

case "$1" in
  1) inject_inc1 ;;
  2) inject_inc2 ;;
  3) inject_inc3 ;;
  4) inject_inc4 ;;
  all)
    inject_inc1
    inject_inc2
    inject_inc3
    inject_inc4
    ;;
  *)
    echo "Usage: $0 1|2|3|4|all"
    exit 1
    ;;
esac

echo "Scenario $1 successfully injected. Read faults/TICKETS.md to begin investigation."
