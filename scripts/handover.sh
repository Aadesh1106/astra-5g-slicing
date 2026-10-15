#!/bin/bash
# Handover of the mobile car h10 between gNodeBs.
#   sudo bash scripts/handover.sh s6     # s5 -> s6  (port s5-eth6 becomes s6 port 5)
#   sudo bash scripts/handover.sh s5     # back      (s5 port 6)
# The controller sees OFPT_PORT_STATUS and rewrites h10's downlink routes ([AMF] in logs/ryu.log).
case "$1" in
  s6) FROM=s5; TO=s6; PORT=5 ;;
  s5) FROM=s6; TO=s5; PORT=6 ;;
  *) echo "usage: $0 s5|s6"; exit 1 ;;
esac
ovs-vsctl --if-exists del-port $FROM s5-eth6
ovs-vsctl add-port $TO s5-eth6 -- set Interface s5-eth6 ofport_request=$PORT
echo "h10 now attached to $TO (port $PORT)"
