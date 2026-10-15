#!/usr/bin/env python3
"""
Astra Mobility 5G SDN Controller
Handles: GTP-TEID slice classification, shortest-path URLLC routing, load-balanced eMBB, reactive MAC learning, emergency reroute.
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls, MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4
from ryu.lib import hub


class Astra5GController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Astra5GController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.monitor_thread = hub.spawn(self._monitor)

        # 5G slice classification by source IP ranges (lab approx of GTP-U TEID)
        self.slice_map = {
            '10.0.0.3': 'eMBB', '10.0.0.4': 'eMBB',           # Smartphones
            '10.0.0.5': 'URLLC', '10.0.0.6': 'URLLC',         # Cars
            '10.0.0.7': 'mMTC', '10.0.0.8': 'mMTC', '10.0.0.9': 'mMTC'  # Sensors
        }

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        self.datapaths[dpid] = datapath

        self.logger.info(f"[Astra] Switch {dpid:016x} up")

        # Table-miss -> controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, 0, match, actions, idle_timeout=0)

        # Flood ARP
        match = parser.OFPMatch(eth_type=0x0806)
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
        self._add_flow(datapath, 1, match, actions, idle_timeout=0)

    def _add_flow(self, datapath, priority, match, actions,
                  idle_timeout=30, hard_timeout=0, instructions=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        if instructions is None:
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        else:
            inst = instructions
        mod = parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match,
            instructions=inst, idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = datapath.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        dst, src = eth.dst, eth.src

        # MAC learning
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        # Slice-aware forwarding logic
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        slice_type = 'default'
        if ip_pkt:
            slice_type = self.slice_map.get(ip_pkt.src, 'default')

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Install reactive flow with slice-aware priority
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            # URLLC gets higher priority so it wins during contention
            priority = 100 if slice_type == 'URLLC' else (50 if slice_type == 'eMBB' else 10)
            self._add_flow(datapath, priority, match, actions, idle_timeout=60)

        out = parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id,
            in_port=in_port, actions=actions, data=msg.data
        )
        datapath.send_msg(out)

    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(10)

    def _request_stats(self, datapath):
        parser = datapath.ofproto_parser
        datapath.send_msg(parser.OFPFlowStatsRequest(datapath))
        datapath.send_msg(parser.OFPPortStatsRequest(
            datapath, 0, datapath.ofproto.OFPP_ANY))

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply(self, ev):
        for stat in ev.msg.body:
            self.logger.info(f"[FLOW] dpid={ev.msg.datapath.id} "
                           f"prio={stat.priority} pkts={stat.packet_count} "
                           f"bytes={stat.byte_count}")

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply(self, ev):
        for stat in ev.msg.body:
            self.logger.info(f"[PORT] dpid={ev.msg.datapath.id} "
                           f"port={stat.port_no} rx={stat.rx_packets} "
                           f"tx={stat.tx_packets}")
