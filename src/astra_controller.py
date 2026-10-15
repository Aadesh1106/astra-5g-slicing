#!/usr/bin/env python3
"""
Astra Mobility: 5G SDN Controller (Ryu, OpenFlow 1.3)

Architecture:
  - 10 Switches (s1-s4 Core Ring, s8 Regional Gateway, s9-s10 DC Spine/Leaf, s5-s7 RAN Edge)
  - 15 Hosts (URLLC V2X, eMBB 4K/AR, mMTC IoT, MEC Edge Server, UPFs)
  - Proactive Two-Table OpenFlow Pipeline:
      Table 0: Slice Classification, DSCP Marking, Ingress Meters, Zero-Trust ACLs
      Table 1: Destination Forwarding (BFS Shortest Path), Fast-Failover Groups, Probe Mirror
  - Dynamic Control Plane Functions:
      F-AMF: 3-way UE Mobility Handover across gNodeBs (s5 <-> s6 <-> s7)
      F-TE : Traffic Engineering to divert eMBB onto diagonal when congested
      F-SEC: Automatic rate-based quarantine of abusive IoT sensors
"""

import time
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls, MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub

# Flow Tables
T_CLASSIFY = 0
T_FORWARD  = 1

# Slice Endpoints
H1, H2 = '10.0.0.1', '10.0.0.2'                     # UPF eMBB/mMTC, UPF URLLC
EMBB_UE   = ['10.0.0.3', '10.0.0.4', '10.0.0.13']    # Phones + AR Headset
URLLC_UE  = ['10.0.0.5', '10.0.0.6', '10.0.0.10', '10.0.0.12'] # Cars + Industrial Robot
MMTC_UE   = ['10.0.0.7', '10.0.0.8', '10.0.0.9']     # Sensors
MOBILE_UE = '10.0.0.10'                             # Mobile Car (roams s5 <-> s6 <-> s7)
PHONE_TE  = '10.0.0.4'                              # Phone dynamically steered by TE
PROBE_PORT = 5                                      # Mirror probe on s1 (port 5 -> h11)

# QoS Metadata & DSCP Tags
META = {'embb': 1, 'urllc': 2}
DSCP = {'embb': 34, 'urllc': 46, 'mmtc': 8}

# Rate Limits & Fast Failover IDs
METER_EMBB_KBPS = 4000
METER_ID = {'10.0.0.3': 100, '10.0.0.4': 101, '10.0.0.13': 102}
GROUP_URLLC_UP   = 1    # s1: Uplink fast-failover (short path -> backup diagonal)
GROUP_URLLC_DOWN = 2    # s4: Downlink fast-failover (short path -> backup via s3)

# Operational Thresholds
POLL_INTERVAL   = 5
TE_HIGH_MBPS    = 3.0   # Congestion trigger: reroute PHONE_TE
TE_LOW_MBPS     = 2.0   # Recovery trigger: restore PHONE_TE
QUARANTINE_PPS  = 200   # IoT DDoS trigger rate
QUARANTINE_SECS = 30    # Temporary quarantine drop duration

# Network Topology Graph: switch -> {local_port: remote_switch}
LINKS = {
    1:  {1: 2, 2: 4, 3: 5, 4: 3},
    2:  {1: 1, 2: 3, 3: 8, 4: 9},
    3:  {1: 2, 2: 4, 3: 6, 4: 1, 5: 8},
    4:  {1: 3, 2: 1, 4: 9},
    5:  {1: 1},
    6:  {1: 3},
    7:  {1: 8},
    8:  {1: 7, 2: 2, 3: 3},
    9:  {1: 2, 2: 4, 3: 10},
    10: {1: 9},
}

# Initial Host Attachments: host_ip -> (switch_id, switch_port)
ATTACH = {
    '10.0.0.1':  (10, 2),  # h1  (UPF eMBB / mMTC)
    '10.0.0.2':  (4,  3),  # h2  (UPF URLLC)
    '10.0.0.3':  (5,  2),  # h3  (eMBB phone 1)
    '10.0.0.4':  (5,  3),  # h4  (eMBB phone 2)
    '10.0.0.5':  (5,  4),  # h5  (URLLC car 1)
    '10.0.0.6':  (5,  5),  # h6  (URLLC car 2)
    '10.0.0.7':  (6,  2),  # h7  (mMTC sensor 1)
    '10.0.0.8':  (6,  3),  # h8  (mMTC sensor 2)
    '10.0.0.9':  (6,  4),  # h9  (mMTC sensor 3)
    '10.0.0.10': (5,  6),  # h10 (Mobile Car, hands over s5 <-> s6 <-> s7)
    '10.0.0.11': (1,  5),  # h11 (Probe mirror)
    '10.0.0.12': (7,  2),  # h12 (URLLC robot)
    '10.0.0.13': (7,  3),  # h13 (eMBB AR headset)
    '10.0.0.14': (10, 3),  # h14 (MEC Edge Server)
    '10.0.0.15': (8,  4),  # h15 (NOC OAM Monitor)
}

# Mobile UE Attachment Ports across gNodeBs
MOBILE_PORTS = {5: 6, 6: 5, 7: 4}


class Astra5GController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}
        self.attach = dict(ATTACH)
        self.te_active = False
        self.last_tx = {}       # (dpid, port) -> (time, tx_bytes)
        self.last_pkts = {}     # (dpid, src_ip) -> (time, pkt_count)
        self.quarantined = {}   # src_ip -> expiry_timestamp
        hub.spawn(self._monitoring_loop)

    # =========================================================================
    # OpenFlow Helper Functions
    # =========================================================================
    def _add_flow(self, dp, table, prio, match, actions=None, goto=None,
                  meter=None, write_meta=None, cookie=0x1, hard_timeout=0):
        """Install a flow rule with optional actions, meters, metadata, and goto."""
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = []
        if meter:
            inst.append(parser.OFPInstructionMeter(meter))
        if actions:
            inst.append(parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions))
        if write_meta is not None:
            inst.append(parser.OFPInstructionWriteMetadata(write_meta, 0xffffffffffffffff))
        if goto is not None:
            inst.append(parser.OFPInstructionGotoTable(goto))

        mod = parser.OFPFlowMod(
            datapath=dp, table_id=table, priority=prio, match=match,
            instructions=inst, cookie=cookie, hard_timeout=hard_timeout
        )
        dp.send_msg(mod)

    def _ip_match(self, parser, **kwargs):
        """Shortcut to create an IPv4 packet match."""
        return parser.OFPMatch(eth_type=0x0800, **kwargs)

    def _out_actions(self, parser, port, queue=None):
        """Shortcut to create output actions with optional queue."""
        acts = []
        if queue is not None:
            acts.append(parser.OFPActionSetQueue(queue))
        acts.append(parser.OFPActionOutput(port))
        return acts

    # =========================================================================
    # Shortest Path Routing (BFS)
    # =========================================================================
    def _calculate_next_hop(self, sw_id, dst_ip):
        """Compute the next-hop port on sw_id towards dst_ip using BFS."""
        target = self.attach.get(dst_ip)
        if not target:
            return None
        dst_sw, dst_port = target
        if sw_id == dst_sw:
            return dst_port

        # Breadth-First Search backward from destination switch
        distance = {dst_sw: 0}
        queue = [dst_sw]
        while queue:
            curr = queue.pop(0)
            for port, neighbor in LINKS.get(curr, {}).items():
                if neighbor not in distance:
                    distance[neighbor] = distance[curr] + 1
                    queue.append(neighbor)

        # Pick neighbor on sw_id that gets us 1 step closer to destination
        best_ports = [
            p for p, n in sorted(LINKS.get(sw_id, {}).items())
            if distance.get(n, 999) == distance.get(sw_id, 999) - 1
        ]
        return best_ports[0] if best_ports else None

    def _install_route(self, dp, dst_ip):
        """Program proactive Table 1 forwarding rule on datapath dp towards dst_ip."""
        parser = dp.ofproto_parser
        # s4 to gNodeB-A hosts: use downlink fast-failover group
        if dp.id == 4 and self.attach[dst_ip][0] == 5:
            acts = [parser.OFPActionGroup(GROUP_URLLC_DOWN)]
        else:
            port = self._calculate_next_hop(dp.id, dst_ip)
            if port is None:
                return
            acts = self._out_actions(parser, port)

        self._add_flow(dp, T_FORWARD, 100, self._ip_match(parser, ipv4_dst=dst_ip),
                       actions=acts, cookie=0x4)

    # =========================================================================
    # Switch Initialization & Pipeline Setup
    # =========================================================================
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        self.datapaths[dp.id] = dp
        self.logger.info("[Fabric] Switch s%d connected -> Initializing OpenFlow 1.3 pipeline", dp.id)

        # Clear existing flows, groups, and meters
        dp.send_msg(parser.OFPFlowMod(dp, table_id=ofp.OFPTT_ALL, command=ofp.OFPFC_DELETE,
                                      out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY))
        dp.send_msg(parser.OFPGroupMod(dp, command=ofp.OFPGC_DELETE, group_id=ofp.OFPG_ALL))
        dp.send_msg(parser.OFPMeterMod(dp, command=ofp.OFPMC_DELETE, flags=0, meter_id=ofp.OFPM_ALL))

        # Default table actions: Table 0 -> Table 1; Table 1 -> Drop unknown
        self._add_flow(dp, T_CLASSIFY, 0, parser.OFPMatch(), goto=T_FORWARD)
        self._add_flow(dp, T_FORWARD,  0, parser.OFPMatch(), actions=[])

        # Apply switch-specific pipelines
        setup_methods = {
            1: self._setup_s1,
            3: self._setup_s3,
            4: self._setup_s4,
            5: self._setup_s5,
            6: self._setup_s6,
            7: self._setup_s7,
            10: self._setup_s10,
        }
        if dp.id in setup_methods:
            setup_methods[dp.id](dp)

        # Install proactive routing to all 15 hosts
        for host_ip in self.attach:
            self._install_route(dp, host_ip)

    # -------------------------------------------------------------------------
    # Edge Switch Pipelines: s5 (gNodeB-A Suburb), s6 (gNodeB-B), s7 (gNodeB-C)
    # -------------------------------------------------------------------------
    def _setup_s5(self, dp):
        """gNodeB-A: Slice ACLs, DSCP classification, and per-phone eMBB meters."""
        ofp, parser = dp.ofproto, dp.ofproto_parser
        # Slice Boundary ACLs
        for phone in ['10.0.0.3', '10.0.0.4']:
            self._add_flow(dp, T_CLASSIFY, 400, self._ip_match(parser, ipv4_src=phone, ipv4_dst=H2),
                           actions=[], cookie=0x2)
        for car in ['10.0.0.5', '10.0.0.6', MOBILE_UE]:
            self._add_flow(dp, T_CLASSIFY, 400, self._ip_match(parser, ipv4_src=car, ipv4_dst=H1),
                           actions=[], cookie=0x2)

        # eMBB Ingress Meters (4 Mbps) & DSCP Marking (AF41 / 34)
        for phone in ['10.0.0.3', '10.0.0.4']:
            mid = METER_ID[phone]
            dp.send_msg(parser.OFPMeterMod(
                dp, command=ofp.OFPMC_ADD, flags=ofp.OFPMF_KBPS | ofp.OFPMF_BURST, meter_id=mid,
                bands=[parser.OFPMeterBandDrop(rate=METER_EMBB_KBPS, burst_size=400)]
            ))
            self._add_flow(dp, T_CLASSIFY, 300, self._ip_match(parser, ipv4_src=phone),
                           actions=[parser.OFPActionSetField(ip_dscp=DSCP['embb'])],
                           goto=T_FORWARD, meter=mid, cookie=0x3)

        # URLLC DSCP Marking (EF / 46)
        for car in ['10.0.0.5', '10.0.0.6', MOBILE_UE]:
            self._add_flow(dp, T_CLASSIFY, 300, self._ip_match(parser, ipv4_src=car),
                           actions=[parser.OFPActionSetField(ip_dscp=DSCP['urllc'])],
                           goto=T_FORWARD, cookie=0x3)

    def _setup_s6(self, dp):
        """gNodeB-B: IoT mMTC DSCP marking and URLLC isolation ACL."""
        parser = dp.ofproto_parser
        for sensor in MMTC_UE:
            self._add_flow(dp, T_CLASSIFY, 400, self._ip_match(parser, ipv4_src=sensor, ipv4_dst=H2),
                           actions=[], cookie=0x2)
            self._add_flow(dp, T_CLASSIFY, 300, self._ip_match(parser, ipv4_src=sensor),
                           actions=[parser.OFPActionSetField(ip_dscp=DSCP['mmtc'])],
                           goto=T_FORWARD, cookie=0x3)

        # Mobile Car support when roaming on s6
        self._add_flow(dp, T_CLASSIFY, 400, self._ip_match(parser, ipv4_src=MOBILE_UE, ipv4_dst=H1),
                       actions=[], cookie=0x2)
        self._add_flow(dp, T_CLASSIFY, 300, self._ip_match(parser, ipv4_src=MOBILE_UE),
                       actions=[parser.OFPActionSetField(ip_dscp=DSCP['urllc'])],
                       goto=T_FORWARD, cookie=0x3)

    def _setup_s7(self, dp):
        """gNodeB-C (Stadium / Industrial): Robot (URLLC) & AR Headset (eMBB) setup."""
        ofp, parser = dp.ofproto, dp.ofproto_parser
        # Robot h12 (URLLC)
        self._add_flow(dp, T_CLASSIFY, 400, self._ip_match(parser, ipv4_src='10.0.0.12', ipv4_dst=H1),
                       actions=[], cookie=0x2)
        self._add_flow(dp, T_CLASSIFY, 300, self._ip_match(parser, ipv4_src='10.0.0.12'),
                       actions=[parser.OFPActionSetField(ip_dscp=DSCP['urllc'])],
                       goto=T_FORWARD, cookie=0x3)

        # AR Headset h13 (eMBB)
        self._add_flow(dp, T_CLASSIFY, 400, self._ip_match(parser, ipv4_src='10.0.0.13', ipv4_dst=H2),
                       actions=[], cookie=0x2)
        mid = METER_ID['10.0.0.13']
        dp.send_msg(parser.OFPMeterMod(
            dp, command=ofp.OFPMC_ADD, flags=ofp.OFPMF_KBPS | ofp.OFPMF_BURST, meter_id=mid,
            bands=[parser.OFPMeterBandDrop(rate=METER_EMBB_KBPS, burst_size=400)]
        ))
        self._add_flow(dp, T_CLASSIFY, 300, self._ip_match(parser, ipv4_src='10.0.0.13'),
                       actions=[parser.OFPActionSetField(ip_dscp=DSCP['embb'])],
                       goto=T_FORWARD, meter=mid, cookie=0x3)

        # Mobile Car support when roaming on s7
        self._add_flow(dp, T_CLASSIFY, 400, self._ip_match(parser, ipv4_src=MOBILE_UE, ipv4_dst=H1),
                       actions=[], cookie=0x2)
        self._add_flow(dp, T_CLASSIFY, 300, self._ip_match(parser, ipv4_src=MOBILE_UE),
                       actions=[parser.OFPActionSetField(ip_dscp=DSCP['urllc'])],
                       goto=T_FORWARD, cookie=0x3)

    # -------------------------------------------------------------------------
    # Core & Aggregation Switch Pipelines: s1, s3, s4, s10
    # -------------------------------------------------------------------------
    def _setup_s1(self, dp):
        """s1 Ingress: Map DSCP -> Metadata, Fast-Failover Group, Probe Mirror."""
        ofp, parser = dp.ofproto, dp.ofproto_parser
        for name in ('embb', 'urllc'):
            self._add_flow(dp, T_CLASSIFY, 200, self._ip_match(parser, ip_dscp=DSCP[name]),
                           goto=T_FORWARD, write_meta=META[name], cookie=0x3)

        # Uplink Fast-Failover: Primary = port 2 (s4), Backup = port 4 (s3 diagonal)
        buckets = [
            parser.OFPBucket(watch_port=2, watch_group=ofp.OFPG_ANY,
                             actions=self._out_actions(parser, 2, queue=0)),
            parser.OFPBucket(watch_port=4, watch_group=ofp.OFPG_ANY,
                             actions=self._out_actions(parser, 4)),
        ]
        dp.send_msg(parser.OFPGroupMod(dp, command=ofp.OFPGC_ADD, type_=ofp.OFPGT_FF,
                                      group_id=GROUP_URLLC_UP, buckets=buckets))

        # URLLC: Mirror copy to Probe h11 (port 5), then output to Fast-Failover group
        self._add_flow(
            dp, T_FORWARD, 300,
            parser.OFPMatch(eth_type=0x0800, metadata=META['urllc'], ipv4_dst=H2),
            actions=[parser.OFPActionOutput(PROBE_PORT), parser.OFPActionGroup(GROUP_URLLC_UP)],
            cookie=0x4
        )
        # eMBB: Long Path queue (port 1 -> s2)
        self._add_flow(
            dp, T_FORWARD, 300,
            parser.OFPMatch(eth_type=0x0800, metadata=META['embb'], ipv4_dst=H1),
            actions=self._out_actions(parser, 1, queue=0),
            cookie=0x4
        )

    def _setup_s3(self, dp):
        """s3 Transit: Queue for mMTC uplink traffic towards collector."""
        parser = dp.ofproto_parser
        self._add_flow(dp, T_FORWARD, 300, self._ip_match(parser, ip_dscp=DSCP['mmtc'], ipv4_dst=H1),
                       actions=self._out_actions(parser, 1, queue=0), cookie=0x4)

    def _setup_s4(self, dp):
        """s4 Downlink Core: Downlink Fast-Failover (Primary: port 2, Backup: port 1)."""
        ofp, parser = dp.ofproto, dp.ofproto_parser
        buckets = [
            parser.OFPBucket(watch_port=2, watch_group=ofp.OFPG_ANY, actions=self._out_actions(parser, 2)),
            parser.OFPBucket(watch_port=1, watch_group=ofp.OFPG_ANY, actions=self._out_actions(parser, 1)),
        ]
        dp.send_msg(parser.OFPGroupMod(dp, command=ofp.OFPGC_ADD, type_=ofp.OFPGT_FF,
                                      group_id=GROUP_URLLC_DOWN, buckets=buckets))

    def _setup_s10(self, dp):
        """s10 DC Leaf: Attach HTB queue for eMBB & MEC traffic toward UPF."""
        parser = dp.ofproto_parser
        self._add_flow(dp, T_FORWARD, 200, self._ip_match(parser, ipv4_dst=H1),
                       actions=self._out_actions(parser, 2, queue=0), cookie=0x4)

    # =========================================================================
    # Control Plane Function: F-AMF (3-Way Roaming Handover)
    # =========================================================================
    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        dp, ofp = msg.datapath, msg.datapath.ofproto
        port = msg.desc.port_no
        down = bool(msg.desc.state & ofp.OFPPS_LINK_DOWN) or bool(msg.desc.config & ofp.OFPPC_PORT_DOWN)
        self.logger.warning("[PORT] s%d port %d is %s (reason %d)", dp.id, port,
                            "DOWN" if down else "UP", msg.reason)

        if MOBILE_PORTS.get(dp.id) != port:
            return
        if msg.reason == ofp.OFPPR_ADD:
            self._execute_handover(dp.id, port)
        elif msg.reason == ofp.OFPPR_DELETE and self.attach[MOBILE_UE][0] == dp.id:
            self.logger.warning("[AMF] %s detached from s%d (in-transit)", MOBILE_UE, dp.id)

    def _execute_handover(self, new_sw, new_port):
        old_sw = self.attach[MOBILE_UE][0]
        self.attach[MOBILE_UE] = (new_sw, new_port)
        self.logger.warning("[AMF] HANDOVER SUCCESS: %s moved from s%d to s%d (port %d)",
                            MOBILE_UE, old_sw, new_sw, new_port)
        # Update downlink routing on all switches to point to new location
        for dp in self.datapaths.values():
            self._install_route(dp, MOBILE_UE)

    # =========================================================================
    # Control Plane Function: F-TE (Traffic Engineering) & F-SEC (IoT Defense)
    # =========================================================================
    def _monitoring_loop(self):
        while True:
            hub.sleep(POLL_INTERVAL)
            for dpid, dp in list(self.datapaths.items()):
                parser, ofp = dp.ofproto_parser, dp.ofproto
                if dpid == 1:
                    dp.send_msg(parser.OFPPortStatsRequest(dp, 0, ofp.OFPP_ANY))
                if dpid == 6:
                    dp.send_msg(parser.OFPFlowStatsRequest(dp, table_id=T_CLASSIFY,
                                                          cookie=0x3, cookie_mask=0xff))

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply(self, ev):
        dp = ev.msg.datapath
        if dp.id != 1:
            return
        now, rate = time.time(), {}
        for st in ev.msg.body:
            if st.port_no in (1, 4):
                prev = self.last_tx.get((1, st.port_no))
                if prev:
                    rate[st.port_no] = (st.tx_bytes - prev[1]) * 8 / (now - prev[0]) / 1e6
                self.last_tx[(1, st.port_no)] = (now, st.tx_bytes)

        r1, r4 = rate.get(1, 0.0), rate.get(4, 0.0)
        if 1 not in rate:
            return
        self.logger.info("[TE] s1 eMBB Primary: %.2f Mbps, Diagonal: %.2f Mbps (Active=%s)",
                         r1, r4, self.te_active)

        if not self.te_active and r1 > TE_HIGH_MBPS:
            self.te_active = True
            self._te_reroute(dp, enable=True)
            self.logger.warning("[TE] High eMBB Congestion! Redirecting %s onto diagonal trunk", PHONE_TE)
        elif self.te_active and (r1 + r4) < TE_LOW_MBPS:
            self.te_active = False
            self._te_reroute(dp, enable=False)
            self.logger.warning("[TE] Load normalized. Restoring %s to primary path", PHONE_TE)

    def _te_reroute(self, dp, enable):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        match = parser.OFPMatch(eth_type=0x0800, metadata=META['embb'],
                                ipv4_src=PHONE_TE, ipv4_dst=H1)
        if enable:
            self._add_flow(dp, T_FORWARD, 350, match, actions=self._out_actions(parser, 4), cookie=0x6)
        else:
            dp.send_msg(parser.OFPFlowMod(dp, table_id=T_FORWARD, command=ofp.OFPFC_DELETE_STRICT,
                                          priority=350, match=match, out_port=ofp.OFPP_ANY,
                                          out_group=ofp.OFPG_ANY))

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply(self, ev):
        dp = ev.msg.datapath
        if dp.id != 6:
            return
        now = time.time()
        for st in ev.msg.body:
            if st.cookie == 0x3:
                src = st.match.get('ipv4_src')
                if src not in MMTC_UE:
                    continue
                prev = self.last_pkts.get((6, src))
                self.last_pkts[(6, src)] = (now, st.packet_count)
                if not prev:
                    continue
                pps = (st.packet_count - prev[1]) / (now - prev[0])
                if pps > QUARANTINE_PPS and self.quarantined.get(src, 0) < now:
                    self.quarantined[src] = now + QUARANTINE_SECS
                    parser = dp.ofproto_parser
                    self._add_flow(dp, T_CLASSIFY, 500, self._ip_match(parser, ipv4_src=src),
                                   actions=[], cookie=0x5, hard_timeout=QUARANTINE_SECS)
                    self.logger.warning("[SEC] IoT Flood Detected! %s sent %.0f PPS -> QUARANTINED for %ds",
                                        src, pps, QUARANTINE_SECS)
