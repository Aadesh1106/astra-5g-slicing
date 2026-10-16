# Astra 5G Fabric — NOC Operational Incident Tickets

Each incident represents a realistic production network degradation across multiple SDN layers (Port link states, Group tables, Meter bands, Flow rewriting, and Queue policies).
Inject using `sudo bash faults/inject.sh <1|2|3|4>`.
Each incident is solvable in **3 to 4 targeted commands**, verified with `sudo bash faults/verify.sh <1|2|3|4>`.

---

## INC-1 - "Autonomous Vehicles & Industrial Robots Disconnected During Fiber Cut"
- **Severity**: P1 - Critical Outage
- **Reported By**: Connected Mobility & Smart Factory Operations
- **Symptoms**:
  - Scheduled maintenance severed the direct trunk (`s1-eth2`) between Ingress Aggregator `s1` and Core South `s4`.
  - Autonomous vehicles (`h5`, `h6` attached to gNodeB-A `s5`, which uplinks to `s1`) and factory robotics (`h12` on `s7`) lost connectivity to the Dedicated URLLC UPF (`h2` attached to `s4`).
  - Because `s1` is the transit ingress connecting `s5` to the core fabric, the severed `s1` $\leftrightarrow$ `s4` link breaks the primary URLLC path (`h5`/`h6` $\rightarrow$ `s5` $\rightarrow$ `s1` $\rightarrow$ `s4` $\rightarrow$ `h2`).
  - The OpenFlow Fast-Failover group on `s1` misbehaved by routing backup traffic back into dead port 2 instead of the diagonal backup link (`s1` $\rightarrow$ `s3` $\rightarrow$ `s4`), blackholing URLLC traffic.
- **Diagnostic Hint**:
  - Inspect OpenFlow Fast-Failover groups on `s1` (`group 1`) and `s4` (`group 2`). Check transit forwarding and priority queueing on `s3`.

---

## INC-2 - "Mobile Car Goes Deaf After Handover to gNodeB-C Stadium"
- **Severity**: P2 - Major Degradation
- **Reported By**: 5G Core AMF / Mobility Engineering
- **Symptoms**:
  - Mobile test car `h10` communicates normally on Suburban gNodeB-A (`s5`).
  - After roaming to Stadium gNodeB-C (`sudo bash scripts/handover.sh s7`), the car transmits uplinks to the MEC Server (`h14`) and UPF (`h1`), but receives zero downlink responses back.
  - Returning the car to `s5` restores service immediately.
- **Diagnostic Hint**:
  - Check the physical port configuration on Regional Gateway `s8` (`dump-ports-desc s8 1`).
  - Trace return flows for `10.0.0.10` on DC Spine `s9` and Stadium Edge `s7` (look for corrupted MAC rewrite actions).

---

## INC-3 - "AR/VR Headsets Choked to 0.1 Mbps, QoS Isolation Collapsed"
- **Severity**: P2 - Performance Degradation
- **Reported By**: Stadium Broadcast Media Team & Capacity Planning
- **Symptoms**:
  - 8K AR/VR headset stream (`h13`) crawls at ~0.1 Mbps instead of its provisioned 4 Mbps bandwidth profile.
  - Capacity planning warns that hardware queue isolation is broken on the Data Center edge, threatening UPF traffic isolation.
  - When traffic engineering routes excess load across regional transit trunks, throughput degrades further.
- **Diagnostic Hint**:
  - Inspect OpenFlow meters on `s7` (`sudo ovs-ofctl -O OpenFlow13 dump-meters s7`).
  - Check OVS interface ingress policing on `s8-eth2` (`sudo ovs-vsctl list interface s8-eth2`).
  - Verify HTB QoS port bindings on `s10-eth1` (`sudo ovs-vsctl list port s10-eth1`).

---

## INC-4 - "Security Audit Alarm: Slice Boundary Leaks and Rogue Blackholes"
- **Severity**: P1 - Security & Compliance Violation
- **Reported By**: Zero-Trust Security Operations & Lawful Intercept Compliance
- **Symptoms**:
  - Automated security scanners detected that an untrusted IoT sensor (`h7`) can ping the isolated URLLC UPF (`h2`).
  - The Lawful Intercept probe (`h11`) has stopped capturing mirrored telemetry packets from car `h6`.
  - Smart meter `h9` has gone completely dark due to meter starvation.
  - Sensor `h8` traffic has lost its QoS DSCP classification tag on `s6`.
- **Diagnostic Hint**:
  - Review OpenFlow Table 0 classification and ACL rules on edge switches `s5` and `s6`.
  - Check OpenFlow meters on `s6` (`sudo ovs-ofctl -O OpenFlow13 dump-meters s6`).
  - Check DSCP/ToS remarking rules on `s5` and flow classifications on `s6`.
