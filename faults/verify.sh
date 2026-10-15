#!/bin/bash
# Behavioural check that a scenario is really fixed.   sudo bash faults/verify.sh 1|2|3|4
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"
fail=0
ok()  { echo "  PASS  $1"; }
bad() { echo "  FAIL  $1"; fail=$((fail+1)); }
reach() { hexec "$1" ping -c 2 -W 1 -q "$2" >/dev/null 2>&1; }
iperf_mbps() {   # host  -> integer tenths of Mbps
  hexec h1 iperf3 -s -D -1 >/dev/null 2>&1; sleep 1
  hexec "$1" iperf3 -c 10.0.0.1 -t 3 -J 2>/dev/null | python3 -c \
   'import json,sys;print(int(json.load(sys.stdin)["end"]["sum_received"]["bits_per_second"]/1e5))' 2>/dev/null || echo 0
}

case "$1" in
1)  echo "[verify 1] URLLC failover end-to-end"
    reach h5 10.0.0.2 && ok "normal path" || bad "normal path"
    sudo ip link set s1-eth2 down; sleep 1
    reach h5 10.0.0.2 && ok "h5 -> h2 survives s1-s4 cut (up + down direction)" || bad "URLLC black-holed when s1-s4 is cut"
    reach h6 10.0.0.2 && ok "h6 -> h2 survives cut" || bad "h6 black-holed during failover"
    sudo ip link set s1-eth2 up; sleep 1
    reach h5 10.0.0.2 && ok "restored" || bad "not restored" ;;
2)  echo "[verify 2] handover of h10"
    reach h10 10.0.0.2 && ok "on s5" || bad "on s5"
    bash "$ROOT/scripts/handover.sh" s6 >/dev/null; sleep 2
    reach h10 10.0.0.2 && ok "h10 reachable after handover to s6" || bad "h10 lost after handover to s6"
    bash "$ROOT/scripts/handover.sh" s5 >/dev/null; sleep 2
    reach h10 10.0.0.2 && ok "back on s5" || bad "lost after returning to s5" ;;
3)  echo "[verify 3] eMBB / QoS / diagonal"
    b=$(iperf_mbps h4); [ "${b:-0}" -ge 20 ] && ok "h4 uplink $(awk "BEGIN{print $b/10}") Mbps" || bad "h4 only $(awk "BEGIN{print ${b:-0}/10}") Mbps"
    sudo ovs-vsctl get port s1-eth1 qos | grep -qv '\[\]' && ok "queues attached to s1-eth1" || bad "no QoS on s1-eth1"
    [ "$(sudo ovs-vsctl get interface s3-eth4 ingress_policing_rate)" = "0" ] && ok "diagonal not policed" || bad "s3-eth4 is rate-policed"
    echo "  (diagonal capacity test: h4 forced over s1->s3)"
    of add-flow s1 "table=1,priority=350,cookie=0x6,ip,metadata=0x1,nw_src=10.0.0.4,nw_dst=10.0.0.1,actions=output:4" >/dev/null
    b=$(iperf_mbps h4)
    of --strict del-flows s1 "table=1,priority=350,ip,metadata=0x1,nw_src=10.0.0.4,nw_dst=10.0.0.1" >/dev/null
    [ "${b:-0}" -ge 20 ] && ok "h4 via diagonal $(awk "BEGIN{print $b/10}") Mbps" || bad "diagonal path only $(awk "BEGIN{print ${b:-0}/10}") Mbps" ;;
4)  echo "[verify 4] slice policy"
    reach h7 10.0.0.2 && bad "sensor h7 reaches URLLC UPF" || ok "h7 -> h2 blocked"
    reach h9 10.0.0.1 && ok "h9 -> h1 reachable" || bad "h9 cannot reach collector"
    for car in 10.0.0.5 10.0.0.6; do
      hexec h11 timeout 5 tcpdump -nn -c 1 -i h11-eth0 "src host $car" >/tmp/v4.txt 2>&1 &
      sleep 1; hexec $( [ $car = 10.0.0.5 ] && echo h5 || echo h6 ) ping -c 2 -W 1 -q 10.0.0.2 >/dev/null 2>&1; wait
      grep -q "$car" /tmp/v4.txt && ok "probe sees $car (URLLC pipeline)" || bad "probe does not see $car (mis-classified?)"
    done ;;
*)  echo "usage: $0 1|2|3|4"; exit 1 ;;
esac
echo; [ $fail -eq 0 ] && echo "SCENARIO $1 FIXED" || echo "$fail check(s) still failing"
exit $fail
