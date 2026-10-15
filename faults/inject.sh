#!/bin/bash
# Inject troubleshooting scenarios into a RUNNING, healthy lab.
#   sudo bash faults/inject.sh 1|2|3|4|all
# Tickets (symptoms only): faults/TICKETS.md      Answers: faults/SOLUTIONS.md
# Do not read the commands below if you want to troubleshoot blind.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/common.sh"

inc1() {
  of mod-group s1 "group_id=1,type=ff,bucket=watch_port:2,actions=set_queue:0,output:2,bucket=watch_port:2,actions=output:2"
  of mod-group s4 "group_id=2,type=ff,bucket=watch_port:2,actions=output:2,bucket=watch_port:2,actions=output:2"
  of --strict del-flows s3 "table=1,priority=100,ip,nw_dst=10.0.0.2"
}
inc2() {
  of add-flow s3 "table=1,priority=200,cookie=0x4,ip,nw_dst=10.0.0.10,actions=output:4"
  of add-flow s1 "table=1,priority=200,ip,nw_dst=10.0.0.10,actions=output:3"
  of add-flow s5 "table=1,priority=200,ip,nw_dst=10.0.0.10,actions=output:6"
}
inc3() {
  of mod-meter s5 "meter=101,kbps,burst,band=type=drop,rate=100,burst_size=10"
  sudo ovs-vsctl set interface s3-eth4 ingress_policing_rate=200 ingress_policing_burst=20
  sudo ovs-vsctl clear port s1-eth1 qos
}
inc4() {
  of --strict del-flows s6 "table=0,priority=400,ip,nw_src=10.0.0.7,nw_dst=10.0.0.2"
  of add-flow s5 "table=0,priority=310,cookie=0x3,ip,nw_src=10.0.0.6,actions=mod_nw_tos:136,goto_table:1"
  of add-flow s6 "table=0,priority=500,cookie=0x5,ip,nw_src=10.0.0.9,actions=drop"
}

case "$1" in
  1|2|3|4) inc$1 >/dev/null 2>&1 ;;
  all) inc1; inc2; inc3; inc4 ;;
  *) echo "usage: $0 1|2|3|4|all"; exit 1 ;;
esac >/dev/null 2>&1
echo "Scenario $1 injected. Read faults/TICKETS.md, then investigate."
