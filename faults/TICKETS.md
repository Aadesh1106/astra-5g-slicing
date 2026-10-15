# Astra 5G Fabric — NOC Operational Incident Tickets

Each incident represents a realistic production network degradation.
Inject using `sudo bash faults/inject.sh <1|2|3|4>`.
Each incident is solvable in **exactly 3 targeted commands**, verified with `sudo bash faults/verify.sh <1|2|3|4>`.

---

## INC-1 - "Autonomous Vehicles & Industrial Robots Disconnected During Fiber Cut"
- **Severity**: P1 - Critical Outage
- **Reported By**: Connected Mobility & Smart Factory Operations
- **Symptoms**:
  - Scheduled maintenance severed the direct trunk (`s1-eth2`) between Aggregator `s1` and Core South `s4`.
  - The safety team reports that autonomous vehicles (`h5`, `h6`) and factory robotics (`h12`) completely lost connectivity to the Dedicated URLLC UPF (`h2`).
  - During normal baseline operations with the trunk up, reachability was 100%. The fast-failover backup mechanism failed to route packets around the ring via the diagonal link.
- **Diagnostic Hint**:
  - Run `scripts/test_failover.sh` to simulate the link cut and inspect OpenFlow Fast-Failover groups on `s1` (`group 1`) and `s4` (`group 2`). Check transit forwarding on `s3`.

---

## INC-2 - "Mobile Car Goes Deaf After Handover to gNodeB-C Stadium"
- **Severity**: P2 - Major Degradation
- **Reported By**: 5G Core AMF / Mobility Engineering
- **Symptoms**:
  - Mobile test car `h10` communicates normally on Suburban gNodeB-A (`s5`).
  - After roaming to Stadium gNodeB-C (`sudo bash scripts/handover.sh s7`), the car can send uplink packets to the MEC Server (`h14`) and UPF (`h1`), but receives zero downlink responses back.
  - Returning the car to `s5` restores service immediately.
  - The Ryu controller logs report `[AMF] HANDOVER SUCCESS` without any exceptions.
- **Diagnostic Hint**:
  - Trace the return path from the Core towards `h10` (`10.0.0.10`). Inspect table 1 flow rules on transit switches (`s8`, `s1`, `s9`) and look for anomalous high-priority entries overriding the controller.

---

## INC-3 - "AR/VR Headsets Choked to 0.1 Mbps, QoS Isolation Collapsed"
- **Severity**: P2 - Performance Degradation
- **Reported By**: Stadium Broadcast Media Team & Capacity Planning
- **Symptoms**:
  - 8K AR/VR headset stream (`h13`) crawls at ~0.1 Mbps instead of its provisioned 4 Mbps bandwidth profile.
  - Capacity planning warns that hardware queue isolation is broken on the Data Center edge, threatening UPF traffic isolation.
  - When traffic engineering routes excess load across regional transit trunks, throughput degrades further.
- **Diagnostic Hint**:
  - Multiple independent bottlenecks exist across different layers:
    1. Inspect OpenFlow meters on `s7` (`sudo ovs-ofctl -O OpenFlow13 dump-meters s7`).
    2. Check OVS interface ingress policing on `s8-eth2` (`sudo ovs-vsctl list interface s8-eth2`).
    3. Verify HTB QoS port bindings on `s10-eth1` (`sudo ovs-vsctl list port s10-eth1`).

---

## INC-4 - "Security Audit Alarm: Slice Boundary Leaks and Rogue Blackholes"
- **Severity**: P1 - Security & Compliance Violation
- **Reported By**: Zero-Trust Security Operations & Lawful Intercept Compliance
- **Symptoms**:
  - Automated security scanners detected that an untrusted IoT sensor (`h7`) can ping the isolated URLLC UPF (`h2`).
  - The Lawful Intercept probe (`h11`) has stopped capturing mirrored telemetry packets from car `h6`.
  - Smart meter `h9` has gone completely dark, yet the controller has no log of a dynamic security quarantine.
- **Diagnostic Hint**:
  - Review OpenFlow Table 0 classification and ACL rules on edge switches `s5` and `s6`:
    1. Look for missing drop rules between slices on `s6`.
    2. Check DSCP/ToS remarking rules on `s5` (look for cookies and priorities).
    3. Check for static unmetered drop rules masquerading as quarantines on `s6`.
