# Incident tickets (symptoms only)

Inject with `sudo bash faults/inject.sh <n>` (or `all` for a bad day), investigate, fix, then
`sudo bash faults/verify.sh <n>`. Each incident has **more than one cause**: a fix is not done
until `verify.sh` passes.

## INC-1 - "Autonomous cars lost connectivity during the fibre cut"
Maintenance cut the s1-s4 fibre. The URLLC failover was signed off last quarter, but the safety
team reports cars `h5`/`h6` lost the URLLC UPF for the entire outage. Normal-day traffic looks perfect.
Also: after a recent handover trial, the mobile car `h10` seems to have trouble too.
*Hint: reproduce the cut with `scripts/test_failover.sh` and follow the packet hop by hop.*

## INC-2 - "Mobile car goes deaf after handover"
`h10` pings fine on gNodeB-A. After `scripts/handover.sh s6` it can still send uplink traffic (the
UPF sees it) but receives nothing back. Moving it back to `s5` fixes it. The controller log shows
the `[AMF] HANDOVER` line and no errors.
*Hint: the return path crosses several switches - check each one's table 1.*

## INC-3 - "Phone B is slow, and it got worse when we load-balanced"
Phone `h4` only reaches ~0.1 Mbps while `h3` is fine. Someone fixed "the obvious thing", after which
`h4` was fine alone but collapsed again whenever both phones ran and the controller logged
`[TE] ... moved to diagonal`. Capacity planning also says eMBB is no longer isolated on the long path.
*Hint: three independent problems at three layers (meter, interface, queueing).*

## INC-4 - "Security audit: slices are leaking, and one sensor is silently dead"
Audit found a sensor can reach the URLLC UPF. Separately, sensor `h9` has been unreachable for days
although the controller never logged a `[SEC]` quarantine for it. Finally, the probe `h11` never
sees traffic from car `h6`, so lawful-intercept coverage is incomplete.
*Hint: look at cookies and priorities in s5/s6 table 0.*
