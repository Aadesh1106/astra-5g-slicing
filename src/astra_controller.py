#!/usr/bin/env python3
"""
Astra Mobility 5G SDN Controller  (RYU, OpenFlow 1.3)

Use case: slice-aware 5G transport with URLLC fast failover, mobility,
traffic engineering and IoT quarantine.

Proactive two-table pipeline (no reactive learning, no flooding):

  Table 0  CLASSIFY / ACL / MARK
      - slice-isolation ACLs                                       [s5, s6]
      - eMBB: per-phone meter (4 Mbps) + DSCP 34 (AF41)            [s5]
      - URLLC: DSCP 46 (EF)                                        [s5, s6 for the mobile car]
      - mMTC: DSCP 8 (CS1)                                         [s6]
      - s1 reads the DSCP back into metadata
  Table 1  FORWARD
      - s1: URLLC -> fast-failover group (short path, backup = diagonal)
            + MIRROR copy to the probe h11 (port 5)
      - everything else: shortest-path routing computed by BFS over LINKS

Control-plane functions (this file):
  F-AMF  Mobility    : PORT_STATUS on the mobile ports re-homes h10 and rewrites
                       its downlink routes on every switch (handover).
  F-TE   Traffic eng.: s1 port stats; if the eMBB path is saturated, phone h4 is
                       moved onto the diagonal s1-s3 path (hysteresis).
  F-SEC  Quarantine  : s6 per-sensor packet rate; a flooding sensor gets a
                       temporary drop rule (hard timeout).

Flow cookies: 0x1 plumbing, 0x2 ACL, 0x3 marking, 0x4 routing, 0x5 quarantine,
0x6 traffic-engineering override.
"""

import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls, MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub

T_CLASSIFY, T_FORWARD = 0, 1

# --- slices ------------------------------------------------------------------
H1, H2 = '10.0.0.1', '10.0.0.2'          # eMBB / mMTC-collector UPF, URLLC UPF
EMBB_UE = ['10.0.0.3', '10.0.0.4']
URLLC_UE = ['10.0.0.5', '10.0.0.6', '10.0.0.10']   # .10 = mobile car
MMTC_UE = ['10.0.0.7', '10.0.0.8', '10.0.0.9']
MOBILE_UE = '10.0.0.10'
PHONE_TE = '10.0.0.4'                    # the phone moved by traffic engineering

META = {'embb': 1, 'urllc': 2}
DSCP = {'embb': 34, 'urllc': 46, 'mmtc': 8}
METER_EMBB_KBPS = 4000
METER_ID = {'10.0.0.3': 100, '10.0.0.4': 101}   # one meter per phone
GROUP_URLLC_UP = 1       # s1: UE -> URLLC UPF (short path, backup via diagonal)
GROUP_URLLC_DOWN = 2     # s4: URLLC UPF -> UE (direct, backup via s3)
PROBE_PORT = 5           # s1 port to the monitoring probe h11

# --- tunables ------------------------------------------------------------------
POLL_S = 5
TE_HIGH_MBPS = 3.0       # s1-eth1 above this -> reroute PHONE_TE
TE_LOW_MBPS = 2.0        # combined eMBB below this -> revert
QUARANTINE_PPS = 200     # one sensor above this -> quarantine
QUARANTINE_S = 30

# --- topology knowledge (matches astra_5g_topo.py) -------------------------------
LINKS = {   # switch -> {port: neighbour switch}
    1: {1: 2, 2: 4, 3: 5, 4: 3},
    2: {1: 1, 2: 3},
    3: {1: 2, 2: 4, 3: 6, 4: 1},
    4: {1: 3, 2: 1},
    5: {1: 1},
    6: {1: 3},
}
ATTACH = {   # host ip -> (switch, port)
    H1: (2, 3), H2: (4, 3),
    '10.0.0.3': (5, 2), '10.0.0.4': (5, 3), '10.0.0.5': (5, 4), '10.0.0.6': (5, 5),
    '10.0.0.7': (6, 2), '10.0.0.8': (6, 3), '10.0.0.9': (6, 4),
    MOBILE_UE: (5, 6),       # changes on handover
}
MOBILE_PORT = {5: 6, 6: 5}   # switch -> port where the mobile UE can attach


class Astra5GController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Astra5GController, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.attach = dict(ATTACH)
        self.te_active = False
        self.last_tx = {}        # (dpid, port) -> (time, bytes)
        self.last_pkts = {}      # (dpid, src ip) -> (time, pkts)
        self.quarantined = {}    # src ip -> expiry time
        hub.spawn(self._monitor)

    # ------------------------------------------------------------------ helpers
    def _flow(self, dp, table, prio, match, actions=None, goto=None, meter=None,
              write_meta=None, cookie=0x1, hard_timeout=0):
        ofp, p = dp.ofproto, dp.ofproto_parser
        inst = []
        if meter:
            inst.append(p.OFPInstructionMeter(meter))
        if actions:
            inst.append(p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions))
        if write_meta is not None:
            inst.append(p.OFPInstructionWriteMetadata(write_meta, 0xffffffffffffffff))
        if goto is not None:
            inst.append(p.OFPInstructionGotoTable(goto))
        dp.send_msg(p.OFPFlowMod(datapath=dp, table_id=table, priority=prio,
                                 match=match, instructions=inst, cookie=cookie,
                                 hard_timeout=hard_timeout))

    def _ip(self, p, **kw):
        return p.OFPMatch(eth_type=0x0800, **kw)

    def _out(self, p, port, queue=None):
        acts = []
        if queue is not None:
            acts.append(p.OFPActionSetQueue(queue))
        acts.append(p.OFPActionOutput(port))
        return acts

    def _route(self, sw, ip):
        """Output port on `sw` toward host `ip` (shortest path, lowest port on ties)."""
        att = self.attach.get(ip)
        if att is None:
            return None
        if sw == att[0]:
            return att[1]
        dist, todo = {att[0]: 0}, [att[0]]
        for cur in todo:                       # BFS from the destination switch
            for nb in LINKS[cur].values():
                if nb not in dist:
                    dist[nb] = dist[cur] + 1
                    todo.append(nb)
        best = [port for port, nb in sorted(LINKS[sw].items()) if dist.get(nb, 99) == dist[sw] - 1]
        return best[0] if best else None

    def _install_route(self, dp, ip):
        p = dp.ofproto_parser
        # s4 -> phones/cars on gNodeB-A: fast-failover group instead of a single port
        if dp.id == 4 and self.attach[ip][0] == 5:
            acts = [p.OFPActionGroup(GROUP_URLLC_DOWN)]
        else:
            port = self._route(dp.id, ip)
            if port is None:
                return
            acts = self._out(p, port)
        self._flow(dp, T_FORWARD, 100, self._ip(p, ipv4_dst=ip), actions=acts, cookie=0x4)

    # ------------------------------------------------------------ switch bring-up
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, p = dp.ofproto, dp.ofproto_parser
        self.datapaths[dp.id] = dp
        self.logger.info("[Astra] s%d up - installing proactive pipeline", dp.id)

        dp.send_msg(p.OFPFlowMod(datapath=dp, table_id=ofp.OFPTT_ALL,
                                 command=ofp.OFPFC_DELETE, out_port=ofp.OFPP_ANY,
                                 out_group=ofp.OFPG_ANY, match=p.OFPMatch()))
        dp.send_msg(p.OFPGroupMod(datapath=dp, command=ofp.OFPGC_DELETE,
                                  group_id=ofp.OFPG_ALL))
        dp.send_msg(p.OFPMeterMod(datapath=dp, command=ofp.OFPMC_DELETE,
                                  flags=0, meter_id=ofp.OFPM_ALL))

        self._flow(dp, T_CLASSIFY, 0, p.OFPMatch(), goto=T_FORWARD)
        self._flow(dp, T_FORWARD, 0, p.OFPMatch(), actions=[])       # default: drop

        {1: self._setup_s1, 3: self._setup_s3, 4: self._setup_s4,
         5: self._setup_s5, 6: self._setup_s6}.get(dp.id, lambda d: None)(dp)

        for ip in self.attach:
            self._install_route(dp, ip)

    # ---- s5 / gNodeB-A: ACL + marking + per-phone meters ---------------------
    def _setup_s5(self, dp):
        ofp, p = dp.ofproto, dp.ofproto_parser
        for ue in EMBB_UE:                      # phones may not reach the URLLC UPF
            self._flow(dp, T_CLASSIFY, 400, self._ip(p, ipv4_src=ue, ipv4_dst=H2),
                       actions=[], cookie=0x2)
        for ue in URLLC_UE:                     # cars may not reach the eMBB UPF
            self._flow(dp, T_CLASSIFY, 400, self._ip(p, ipv4_src=ue, ipv4_dst=H1),
                       actions=[], cookie=0x2)

        for ue in EMBB_UE:
            mid = METER_ID[ue]
            dp.send_msg(p.OFPMeterMod(
                datapath=dp, command=ofp.OFPMC_ADD,
                flags=ofp.OFPMF_KBPS | ofp.OFPMF_BURST, meter_id=mid,
                bands=[p.OFPMeterBandDrop(rate=METER_EMBB_KBPS, burst_size=400)]))
            self._flow(dp, T_CLASSIFY, 300, self._ip(p, ipv4_src=ue),
                       actions=[p.OFPActionSetField(ip_dscp=DSCP['embb'])],
                       goto=T_FORWARD, meter=mid, cookie=0x3)
        for ue in URLLC_UE:
            self._flow(dp, T_CLASSIFY, 300, self._ip(p, ipv4_src=ue),
                       actions=[p.OFPActionSetField(ip_dscp=DSCP['urllc'])],
                       goto=T_FORWARD, cookie=0x3)

    # ---- s6 / gNodeB-B: ACL + marking (+ the car when it has handed over) --------
    def _setup_s6(self, dp):
        p = dp.ofproto_parser
        self.last_pkts = {k: v for k, v in self.last_pkts.items() if k[0] != 6}
        self.quarantined.clear()
        for ue in MMTC_UE:
            self._flow(dp, T_CLASSIFY, 400, self._ip(p, ipv4_src=ue, ipv4_dst=H2),
                       actions=[], cookie=0x2)
            self._flow(dp, T_CLASSIFY, 300, self._ip(p, ipv4_src=ue),
                       actions=[p.OFPActionSetField(ip_dscp=DSCP['mmtc'])],
                       goto=T_FORWARD, cookie=0x3)
        # the mobile car must be handled identically whichever gNodeB it sits on
        self._flow(dp, T_CLASSIFY, 400, self._ip(p, ipv4_src=MOBILE_UE, ipv4_dst=H1),
                   actions=[], cookie=0x2)
        self._flow(dp, T_CLASSIFY, 300, self._ip(p, ipv4_src=MOBILE_UE),
                   actions=[p.OFPActionSetField(ip_dscp=DSCP['urllc'])],
                   goto=T_FORWARD, cookie=0x3)

    # ---- s1 / core ingress: DSCP -> metadata, slice routing, failover, mirror ----
    def _setup_s1(self, dp):
        ofp, p = dp.ofproto, dp.ofproto_parser
        self.te_active = False
        self.last_tx.clear()

        for name in ('embb', 'urllc'):
            self._flow(dp, T_CLASSIFY, 200, self._ip(p, ip_dscp=DSCP[name]),
                       goto=T_FORWARD, write_meta=META[name], cookie=0x3)

        # FF group: bucket 1 = SHORT path (port 2, s4), bucket 2 = diagonal (port 4, s3 -> s4)
        buckets = [
            p.OFPBucket(watch_port=2, watch_group=ofp.OFPG_ANY, actions=self._out(p, 2, queue=0)),
            p.OFPBucket(watch_port=4, watch_group=ofp.OFPG_ANY, actions=self._out(p, 4)),
        ]
        dp.send_msg(p.OFPGroupMod(datapath=dp, command=ofp.OFPGC_ADD,
                                  type_=ofp.OFPGT_FF, group_id=GROUP_URLLC_UP, buckets=buckets))

        # URLLC: mirror a copy to the probe, then the failover group
        self._flow(dp, T_FORWARD, 300,
                   p.OFPMatch(eth_type=0x0800, metadata=META['urllc'], ipv4_dst=H2),
                   actions=[p.OFPActionOutput(PROBE_PORT), p.OFPActionGroup(GROUP_URLLC_UP)],
                   cookie=0x4)
        # eMBB: LONG path (port 1) in its own queue
        self._flow(dp, T_FORWARD, 300,
                   p.OFPMatch(eth_type=0x0800, metadata=META['embb'], ipv4_dst=H1),
                   actions=self._out(p, 1, queue=0), cookie=0x4)

    def _te_override(self, dp, enable):
        """Move PHONE_TE onto the diagonal (s1 port 4) or back."""
        ofp, p = dp.ofproto, dp.ofproto_parser
        match = p.OFPMatch(eth_type=0x0800, metadata=META['embb'],
                           ipv4_src=PHONE_TE, ipv4_dst=H1)
        if enable:
            self._flow(dp, T_FORWARD, 350, match, actions=self._out(p, 4), cookie=0x6)
        else:
            dp.send_msg(p.OFPFlowMod(datapath=dp, table_id=T_FORWARD,
                                     command=ofp.OFPFC_DELETE_STRICT, priority=350,
                                     match=match, out_port=ofp.OFPP_ANY,
                                     out_group=ofp.OFPG_ANY))

    # ---- s3: mMTC uplink queue ---------------------------------------------------
    def _setup_s3(self, dp):
        p = dp.ofproto_parser
        self._flow(dp, T_FORWARD, 300, self._ip(p, ip_dscp=DSCP['mmtc'], ipv4_dst=H1),
                   actions=self._out(p, 1, queue=0), cookie=0x4)

    # ---- s4 / URLLC UPF edge: downlink failover ------------------------------------
    def _setup_s4(self, dp):
        ofp, p = dp.ofproto, dp.ofproto_parser
        buckets = [
            p.OFPBucket(watch_port=2, watch_group=ofp.OFPG_ANY, actions=self._out(p, 2)),
            p.OFPBucket(watch_port=1, watch_group=ofp.OFPG_ANY, actions=self._out(p, 1)),
        ]
        dp.send_msg(p.OFPGroupMod(datapath=dp, command=ofp.OFPGC_ADD,
                                  type_=ofp.OFPGT_FF, group_id=GROUP_URLLC_DOWN, buckets=buckets))

    # ---------------------------------------------------------- F-AMF: mobility
    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        dp, ofp = msg.datapath, msg.datapath.ofproto
        port = msg.desc.port_no
        down = bool(msg.desc.state & ofp.OFPPS_LINK_DOWN) or bool(msg.desc.config & ofp.OFPPC_PORT_DOWN)
        self.logger.warning("[LINK] s%d port %d is %s (reason %d)", dp.id, port,
                            "DOWN" if down else "UP", msg.reason)

        if MOBILE_PORT.get(dp.id) != port:
            return
        if msg.reason == ofp.OFPPR_ADD:
            self._handover(dp.id, port)
        elif msg.reason == ofp.OFPPR_DELETE and self.attach[MOBILE_UE][0] == dp.id:
            self.logger.warning("[AMF] %s detached from s%d (handover gap)", MOBILE_UE, dp.id)

    def _handover(self, sw, port):
        old = self.attach[MOBILE_UE][0]
        self.attach[MOBILE_UE] = (sw, port)
        self.logger.warning("[AMF] HANDOVER %s: gNodeB s%d -> s%d, rewriting downlink routes",
                            MOBILE_UE, old, sw)
        for dp in self.datapaths.values():
            self._install_route(dp, MOBILE_UE)

    # ----------------------------------------------------- monitoring loop (TE, SEC)
    def _monitor(self):
        while True:
            hub.sleep(POLL_S)
            for dpid, dp in list(self.datapaths.items()):
                p, ofp = dp.ofproto_parser, dp.ofproto
                if dpid == 1:
                    dp.send_msg(p.OFPPortStatsRequest(dp, 0, ofp.OFPP_ANY))
                dp.send_msg(p.OFPFlowStatsRequest(dp, table_id=T_CLASSIFY,
                                                  cookie=0x2, cookie_mask=0xff))
                if dpid == 6:
                    dp.send_msg(p.OFPFlowStatsRequest(dp, table_id=T_CLASSIFY,
                                                      cookie=0x3, cookie_mask=0xff))

    # F-TE ------------------------------------------------------------------------
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
        if 1 not in rate:
            return
        r1, r4 = rate[1], rate.get(4, 0.0)
        self.logger.info("[TE] s1 eMBB path %.2f Mbps, diagonal %.2f Mbps (override=%s)",
                         r1, r4, self.te_active)
        if not self.te_active and r1 > TE_HIGH_MBPS:
            self.te_active = True
            self._te_override(dp, True)
            self.logger.warning("[TE] eMBB path congested -> %s moved to diagonal s1-s3", PHONE_TE)
        elif self.te_active and r1 + r4 < TE_LOW_MBPS:
            self.te_active = False
            self._te_override(dp, False)
            self.logger.warning("[TE] load dropped -> %s back on the primary eMBB path", PHONE_TE)

    # F-SEC + ACL counters ----------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply(self, ev):
        dp = ev.msg.datapath
        now = time.time()
        for st in ev.msg.body:
            if st.cookie == 0x2 and st.packet_count:
                self.logger.info("[ACL] s%d blocked %d pkts  %s", dp.id, st.packet_count, st.match)
            elif st.cookie == 0x3 and dp.id == 6:
                src = st.match.get('ipv4_src')
                if src not in MMTC_UE:
                    continue
                prev = self.last_pkts.get((6, src))
                self.last_pkts[(6, src)] = (now, st.packet_count)
                if not prev:
                    continue
                pps = (st.packet_count - prev[1]) / (now - prev[0])
                if pps > QUARANTINE_PPS and self.quarantined.get(src, 0) < now:
                    self.quarantined[src] = now + QUARANTINE_S
                    p = dp.ofproto_parser
                    self._flow(dp, T_CLASSIFY, 500, self._ip(p, ipv4_src=src), actions=[],
                               cookie=0x5, hard_timeout=QUARANTINE_S)
                    self.logger.warning("[SEC] %s sends %.0f pps -> QUARANTINED for %ds",
                                        src, pps, QUARANTINE_S)
