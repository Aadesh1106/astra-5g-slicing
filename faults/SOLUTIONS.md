# Solutions (spoilers) - each incident needs 3 fixes + a verification run

`of` below = `sudo ovs-ofctl -O OpenFlow13`.

---
## INC-1 Failover chain broken (3 fixes + verify)

**Root causes**
1. `s1` group 1: bucket 2 is a copy of bucket 1 (watches and outputs port 2, the dead link) instead of the diagonal (port 4).
2. `s4` group 2 (downlink): same mistake, bucket 2 outputs the dead port 2 instead of port 1 (via s3).
3. `s3` lost its `table 1, nw_dst=10.0.0.2 -> output:2` route, so even a correct failover is dropped at s3. (This also breaks h10 -> h2 once it hands over to s6, a red herring pointing at "handover".)

**How to find it**: `scripts/test_failover.sh` fails; `of dump-groups s1`, `of dump-groups s4`, `of dump-flows s3 table=1`.

**Fix**
```bash
of mod-group s1 "group_id=1,type=ff,bucket=watch_port:2,actions=set_queue:0,output:2,bucket=watch_port:4,actions=output:4"
of mod-group s4 "group_id=2,type=ff,bucket=watch_port:2,actions=output:2,bucket=watch_port:1,actions=output:1"
of add-flow s3 "table=1,priority=100,ip,nw_dst=10.0.0.2,actions=output:2"
sudo bash faults/verify.sh 1
```

---
## INC-2 Stale handover state (3 fixes + verify)

**Root cause**: three leftover priority-200 downlink rules for h10 (`10.0.0.10`) pin the old path
`s3 -> s1 -> s5 -> port 6`. They out-prioritise the controller's priority-100 routes, so after the car
moves to s6 the replies are sent to a gNodeB that no longer has it. Everything works while h10 is on s5, which is why nobody noticed.

**How to find it**: `scripts/test_handover.sh`; trace the reply hop by hop with `of dump-flows sN table=1 | grep 10.0.0.10` on s4, s3, s1, s5, and spot the `priority=200` entries (the controller only installs 100).

**Fix**
```bash
of --strict del-flows s3 "table=1,priority=200,ip,nw_dst=10.0.0.10"
of --strict del-flows s1 "table=1,priority=200,ip,nw_dst=10.0.0.10"
of --strict del-flows s5 "table=1,priority=200,ip,nw_dst=10.0.0.10"
sudo bash faults/verify.sh 2
```
(After deleting them, the next handover makes the controller reinstall correct priority-100 routes; if h10 is currently on s6 run `scripts/handover.sh s5` then `s6` again.)

---
## INC-3 Multi-layer QoS fault (3 fixes + verify)

**Root causes (one per layer)**
1. **Meter**: meter 101 (h4's cap) on s5 was cut from 4000 to 100 kbps -> h4 crawls. (`of dump-meters s5`)
2. **Interface**: OVS ingress policing 200 kbps on `s3-eth4` throttles the diagonal. Invisible until TE moves h4 onto it (or a URLLC failover uses it). (`sudo ovs-vsctl list interface s3-eth4 | grep policing`)
3. **Queueing**: the QoS record was removed from `s1-eth1`, so eMBB has no HTB queue/isolation. (`sudo ovs-vsctl get port s1-eth1 qos` -> `[]`)

**Fix**
```bash
of mod-meter s5 "meter=101,kbps,burst,band=type=drop,rate=4000,burst_size=400"
sudo ovs-vsctl set interface s3-eth4 ingress_policing_rate=0 ingress_policing_burst=0
sudo bash src/astra_qos.sh
sudo bash faults/verify.sh 3
```

---
## INC-4 Security policy drift (3 fixes + verify)

**Root causes**
1. The s6 ACL `h7 -> h2` (priority 400, cookie 0x2) was deleted, so a sensor reaches the URLLC UPF.
2. A rogue priority-310 rule on s5 re-marks car `h6` as DSCP 34 (eMBB, `tos 136`). At `s1` it is no longer classified URLLC, so it bypasses the failover group **and** the mirror to h11. Traffic still flows, which is why it is silent.
3. A permanent drop for `h9` at s6, priority 500 and cookie 0x5, disguised as a quarantine rule but with no timeout. The controller never logged `[SEC]` for it because it never created it.

**How to find it**: `healthcheck.sh` checks [4], [5], [8]; `of dump-flows s5 table=0`, `of dump-flows s6 table=0` (look for unexpected priorities 310 / 500 and compare with controller cookies).

**Fix**
```bash
of add-flow s6 "table=0,priority=400,cookie=0x2,ip,nw_src=10.0.0.7,nw_dst=10.0.0.2,actions=drop"
of --strict del-flows s5 "table=0,priority=310,ip,nw_src=10.0.0.6"
of --strict del-flows s6 "table=0,priority=500,ip,nw_src=10.0.0.9"
sudo bash faults/verify.sh 4
```
