#!/usr/bin/env python3
"""
Astra Mobility: 5G Slice-Aware Transport Fabric
10 Switches, 15 Hosts, Multi-Domain Topology (RAN Edge, Core Ring, DC Spine/Leaf)

Topology Layout:
  Core Ring & Transit : s1, s2, s3, s4 + s8 (Regional Gateway)
  DC Spine & Leaf     : s9 (Spine), s10 (MEC / UPF Leaf)
  RAN Edge (gNodeBs)  : s5 (gNodeB-A Suburb)
                        s6 (gNodeB-B Smart City)
                        s7 (gNodeB-C Stadium / Factory)

Host Roles:
  h1  : 5G UPF (eMBB + mMTC Collector)   -> s10
  h2  : 5G UPF (URLLC dedicated)         -> s4
  h3  : Phone 1 (eMBB 4K stream)         -> s5
  h4  : Phone 2 (eMBB 4K stream)         -> s5
  h5  : Connected Car 1 (URLLC V2X)      -> s5
  h6  : Connected Car 2 (URLLC V2X)      -> s5
  h7  : Smart Grid Sensor (mMTC)         -> s6
  h8  : CCTV Video Sensor (mMTC)         -> s6
  h9  : Rogue Telemetry Sensor (mMTC)    -> s6
  h10 : Autonomous Car (Mobile UE)       -> Roams: s5 <-> s6 <-> s7
  h11 : Lawful Intercept Mirror Probe    -> s1
  h12 : Industrial Robot (URLLC)         -> s7
  h13 : AR/VR Headset (eMBB)             -> s7
  h14 : MEC Edge Application Server      -> s10
  h15 : NOC / OAM Telemetry Monitor      -> s8

Pinned Switch Port Assignments:
  s1 : 1->s2, 2->s4, 3->s5, 4->s3 (diagonal), 5->h11
  s2 : 1->s1, 2->s3, 3->s8, 4->s9
  s3 : 1->s2, 2->s4, 3->s6, 4->s1 (diagonal), 5->s8
  s4 : 1->s3, 2->s1, 3->h2, 4->s9
  s5 : 1->s1, 2->h3, 3->h4, 4->h5, 5->h6, 6->h10 (mobile slot)
  s6 : 1->s3, 2->h7, 3->h8, 4->h9, 5->(mobile slot)
  s7 : 1->s8, 2->h12, 3->h13, 4->(mobile slot)
  s8 : 1->s7, 2->s2, 3->s3, 4->h15
  s9 : 1->s2, 2->s4, 3->s10
  s10: 1->s9, 2->h1, 3->h14
"""

import os
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel, info

os.environ['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'

# 15 Hosts: IP and MAC addresses
HOSTS = {
    'h1':  ('10.0.0.1',  '00:00:00:00:00:01'),
    'h2':  ('10.0.0.2',  '00:00:00:00:00:02'),
    'h3':  ('10.0.0.3',  '00:00:00:00:00:03'),
    'h4':  ('10.0.0.4',  '00:00:00:00:00:04'),
    'h5':  ('10.0.0.5',  '00:00:00:00:00:05'),
    'h6':  ('10.0.0.6',  '00:00:00:00:00:06'),
    'h7':  ('10.0.0.7',  '00:00:00:00:00:07'),
    'h8':  ('10.0.0.8',  '00:00:00:00:00:08'),
    'h9':  ('10.0.0.9',  '00:00:00:00:00:09'),
    'h10': ('10.0.0.10', '00:00:00:00:00:0a'),
    'h11': ('10.0.0.11', '00:00:00:00:00:0b'),
    'h12': ('10.0.0.12', '00:00:00:00:00:0c'),
    'h13': ('10.0.0.13', '00:00:00:00:00:0d'),
    'h14': ('10.0.0.14', '00:00:00:00:00:0e'),
    'h15': ('10.0.0.15', '00:00:00:00:00:0f'),
}


class Astra5GTopo(Topo):
    def build(self):
        info("*** Adding 15 Hosts\n")
        for name, (ip, mac) in HOSTS.items():
            self.addHost(name, ip=f"{ip}/24", mac=mac)

        info("*** Adding 10 OpenFlow 1.3 Switches (s1 to s10)\n")
        for i in range(1, 11):
            self.addSwitch(f"s{i}", dpid=f"{i:016x}", protocols="OpenFlow13")

        # -------------------------------------------------------------
        # Core Ring (10 Mbps, 2ms)
        # -------------------------------------------------------------
        self.addLink('s1', 's2', port1=1, port2=1, bw=10, delay='2ms')
        self.addLink('s2', 's3', port1=2, port2=1, bw=10, delay='2ms')
        self.addLink('s3', 's4', port1=2, port2=1, bw=10, delay='2ms')
        self.addLink('s4', 's1', port1=2, port2=2, bw=10, delay='2ms')  # SHORT fast-path

        # Diagonal Link (s1 <-> s3, backup & TE path)
        self.addLink('s1', 's3', port1=4, port2=4, bw=10, delay='6ms')

        # -------------------------------------------------------------
        # Regional Gateway & DC Spine/Leaf
        # -------------------------------------------------------------
        # s8 Regional Gateway -> connects s7 (gNodeB-C) to Core Ring (s2, s3)
        self.addLink('s8', 's2', port1=2, port2=3, bw=10, delay='2ms')
        self.addLink('s8', 's3', port1=3, port2=5, bw=10, delay='2ms')

        # DC Spine s9 -> connects Core (s2, s4) to Leaf s10
        self.addLink('s9', 's2', port1=1, port2=4, bw=10, delay='2ms')
        self.addLink('s9', 's4', port1=2, port2=4, bw=10, delay='2ms')
        self.addLink('s9', 's10', port1=3, port2=1, bw=10, delay='1ms')

        # -------------------------------------------------------------
        # RAN Edge gNodeB Uplinks
        # -------------------------------------------------------------
        self.addLink('s5', 's1', port1=1, port2=3, bw=10, delay='1ms')  # gNodeB-A -> s1
        self.addLink('s6', 's3', port1=1, port2=3, bw=10, delay='1ms')  # gNodeB-B -> s3
        self.addLink('s7', 's8', port1=1, port2=1, bw=10, delay='1ms')  # gNodeB-C -> s8

        # -------------------------------------------------------------
        # Server & Monitoring Host Links
        # -------------------------------------------------------------
        self.addLink('h11', 's1', port2=5, delay='1ms')  # Lawful intercept mirror probe
        self.addLink('h2', 's4', port2=3, delay='1ms')   # URLLC UPF
        self.addLink('h15', 's8', port2=4, delay='1ms')  # NOC OAM telemetry
        self.addLink('h1', 's10', port2=2, delay='1ms')  # eMBB / mMTC UPF
        self.addLink('h14', 's10', port2=3, delay='1ms') # MEC Edge Server

        # -------------------------------------------------------------
        # Access UEs (Phones, Cars, Sensors, Robots)
        # -------------------------------------------------------------
        # s5 (gNodeB-A Suburb): h3, h4, h5, h6, h10 (mobile UE starts here)
        for port, host in zip((2, 3, 4, 5, 6), ('h3', 'h4', 'h5', 'h6', 'h10')):
            self.addLink(host, 's5', port2=port, delay='1ms')

        # s6 (gNodeB-B Smart City): h7, h8, h9 (port 5 reserved for mobile handover)
        for port, host in zip((2, 3, 4), ('h7', 'h8', 'h9')):
            self.addLink(host, 's6', port2=port, delay='1ms')

        # s7 (gNodeB-C Stadium): h12, h13 (port 4 reserved for mobile handover)
        for port, host in zip((2, 3), ('h12', 'h13')):
            self.addLink(host, 's7', port2=port, delay='1ms')


def run():
    setLogLevel('info')
    net = Mininet(
        topo=Astra5GTopo(),
        switch=OVSSwitch,
        controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6653),
        link=TCLink,
        autoSetMacs=False,
    )
    net.start()

    info("*** Installing static ARP across all 15 hosts (zero broadcast loop)\n")
    for h in net.hosts:
        for other, (ip, mac) in HOSTS.items():
            if other != h.name:
                h.cmd(f"arp -s {ip} {mac}")

    info("*** Setting fail-secure mode on OVS bridges (proactive OpenFlow only)\n")
    for sw in net.switches:
        sw.cmd(f"ovs-vsctl set-fail-mode {sw.name} secure")

    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
