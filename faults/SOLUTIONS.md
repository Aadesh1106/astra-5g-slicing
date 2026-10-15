# Astra 5G Incident Solutions Guide

Every incident has **three distinct root causes** and is remediated using **exactly 3 commands** followed by a verification run.

Alias shortcut:
```bash
of() { sudo ovs-ofctl -O OpenFlow13 "$@"; }
```

---

## Incident 1: Fast-Failover Resilience Broken

### Root Causes
1. **s1 Group 1 (Uplink Fast-Failover)**: Bucket 2 (backup path) erroneously watches and outputs to port 2 (the dead link) rather than port 4 (the diagonal backup link).
2. **s4 Group 2 (Downlink Fast-Failover)**: Bucket 2 points back to the dead port 2 instead of transit port 1 (towards `s3`).
3. **s3 Transit Missing Route**: Forwarding rule for `10.0.0.2` in Table 1 was deleted on `s3`, causing all diverted packets on the diagonal to be dropped.

### Exact Solution (3 Commands + Verify)
```bash
sudo ovs-ofctl -O OpenFlow13 mod-group s1 "group_id=1,type=ff,bucket=watch_port:2,actions=set_queue:0,output:2,bucket=watch_port:4,actions=output:4"
sudo ovs-ofctl -O OpenFlow13 mod-group s4 "group_id=2,type=ff,bucket=watch_port:2,actions=output:2,bucket=watch_port:1,actions=output:1"
sudo ovs-ofctl -O OpenFlow13 add-flow s3 "table=1,priority=100,ip,nw_dst=10.0.0.2,actions=output:2"
sudo bash faults/verify.sh 1
```

---

## Incident 2: Mobile UE Handover Downlink Pinning

### Root Causes
1. **s8 Regional Gateway**: Stale rule with priority 250 sends downlink traffic for `10.0.0.10` out port 3 (`s3`) instead of port 1 (`s7`).
2. **s1 Ingress Aggregator**: Stale priority 250 rule forces downlink packets out port 3 towards `s5`.
3. **s9 DC Spine**: Stale priority 250 rule forwards packets out port 1 towards `s2` instead of following proper shortest-path routing.

Because these rules are set to `priority=250`, they silently override the controller's dynamically installed `priority=100` mobility routes.

### Exact Solution (3 Commands + Verify)
```bash
sudo ovs-ofctl -O OpenFlow13 --strict del-flows s8 "table=1,priority=250,ip,nw_dst=10.0.0.10"
sudo ovs-ofctl -O OpenFlow13 --strict del-flows s1 "table=1,priority=250,ip,nw_dst=10.0.0.10"
sudo ovs-ofctl -O OpenFlow13 --strict del-flows s9 "table=1,priority=250,ip,nw_dst=10.0.0.10"
sudo bash faults/verify.sh 2
```

---

## Incident 3: Multi-Layer QoS Degradation

### Root Causes
1. **OpenFlow Meter 102 on s7**: Throttled from 4000 kbps down to 100 kbps, starving AR Headset `h13`.
2. **OVS Ingress Policing on s8-eth2**: A silent policing rate limit of 200 kbps throttles regional transit traffic.
3. **HTB QoS Queue Detachment**: The QoS record was removed from DC Leaf port `s10-eth1`, breaking queue isolation for UPF traffic.

### Exact Solution (3 Commands + Verify)
```bash
sudo ovs-ofctl -O OpenFlow13 mod-meter s7 "meter=102,kbps,burst,band=type=drop,rate=4000,burst_size=400"
sudo ovs-vsctl set interface s8-eth2 ingress_policing_rate=0 ingress_policing_burst=0
sudo bash src/astra_qos.sh
sudo bash faults/verify.sh 3
```

---

## Incident 4: Zero-Trust Security Policy Drift

### Root Causes
1. **Missing Boundary ACL on s6**: The rule blocking IoT sensors from reaching URLLC UPF `h2` (`10.0.0.7 -> 10.0.0.2`) was deleted.
2. **Rogue DSCP Remarking on s5**: A rogue priority-310 rule remarking car `h6` to eMBB DSCP 34 (`tos 136`), causing it to bypass Table 1 URLLC probe mirroring.
3. **Permanent Drop Rule on s6**: A rogue static drop rule for `h9` (`priority 500, cookie 0x5`) with no hard timeout, disguising itself as a legitimate security quarantine.

### Exact Solution (3 Commands + Verify)
```bash
sudo ovs-ofctl -O OpenFlow13 add-flow s6 "table=0,priority=400,cookie=0x2,ip,nw_src=10.0.0.7,nw_dst=10.0.0.2,actions=drop"
sudo ovs-ofctl -O OpenFlow13 --strict del-flows s5 "table=0,priority=310,ip,nw_src=10.0.0.6"
sudo ovs-ofctl -O OpenFlow13 --strict del-flows s6 "table=0,priority=500,ip,nw_src=10.0.0.9"
sudo bash faults/verify.sh 4
```
