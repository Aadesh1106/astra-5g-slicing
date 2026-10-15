#!/usr/bin/env python3
"""
Astra Mobility 5G Transport Fabric (use case: slice-aware transport with URLLC fast failover)

Core ring : s1-s2-s3-s4 (10 Mbps links)
Edge      : s5 (gNodeB-A) -> s1,  s6 (gNodeB-B) -> s3
Hosts     : h1 eMBB UPF (s2)      h2 URLLC UPF (s4)
            h3,h4 phones (s5)     h5,h6 cars (s5)
            h7,h8,h9 sensors (s6)

All port numbers are pinned explicitly because the controller's forwarding
tables (src/astra_controller.py) are built from them.

    s1: 1->s2  2->s4  3->s5  4->s3 (diagonal)  5->h11 (probe)
    s2: 1->s1  2->s3  3->h1
    s3: 1->s2  2->s4  3->s6  4->s1 (diagonal)
    s4: 1->s3  2->s1  3->h2
    s5: 1->s1  2->h3  3->h4  4->h5  5->h6  6->h10 (mobile port)
    s6: 1->s3  2->h7  3->h8  4->h9  5->(mobile port, empty until handover)

Handover = moving s5's port 6 (netdev s5-eth6, the h10 link) to s6 port 5;
see scripts/handover.sh. The controller notices via OFPT_PORT_STATUS.

There is NO STP and NO flooding: the controller programs every path
proactively, and ARP is static, so the ring cannot loop.
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel, info
import os

os.environ['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'

HOSTS = {  # name: (ip, mac)
    'h1': ('10.0.0.1', '00:00:00:00:00:01'),
    'h2': ('10.0.0.2', '00:00:00:00:00:02'),
    'h3': ('10.0.0.3', '00:00:00:00:00:03'),
    'h4': ('10.0.0.4', '00:00:00:00:00:04'),
    'h5': ('10.0.0.5', '00:00:00:00:00:05'),
    'h6': ('10.0.0.6', '00:00:00:00:00:06'),
    'h7': ('10.0.0.7', '00:00:00:00:00:07'),
    'h8': ('10.0.0.8', '00:00:00:00:00:08'),
    'h9': ('10.0.0.9', '00:00:00:00:00:09'),
    'h10': ('10.0.0.10', '00:00:00:00:00:0a'),   # mobile car (hands over s5 <-> s6)
    'h11': ('10.0.0.11', '00:00:00:00:00:0b'),   # monitoring probe (mirror of URLLC)
}


class Astra5GTopo(Topo):
    def build(self):
        info("*** Building Astra Mobility 5G Core Fabric\n")

        for name, (ip, mac) in HOSTS.items():
            self.addHost(name, ip=ip + '/24', mac=mac)

        for i in range(1, 7):
            self.addSwitch('s%d' % i, dpid='%016x' % i, protocols='OpenFlow13')

        # --- Core ring (10 Mbps, 2 ms) ---
        self.addLink('s1', 's2', port1=1, port2=1, bw=10, delay='2ms')
        self.addLink('s2', 's3', port1=2, port2=1, bw=10, delay='2ms')
        self.addLink('s3', 's4', port1=2, port2=1, bw=10, delay='2ms')
        self.addLink('s4', 's1', port1=2, port2=2, bw=10, delay='2ms')   # SHORT path

        # --- Edge uplinks ---
        self.addLink('s5', 's1', port1=1, port2=3, bw=10, delay='1ms')
        self.addLink('s6', 's3', port1=1, port2=3, bw=10, delay='1ms')

        # --- diagonal core link: alternate eMBB path / backup for URLLC ---
        self.addLink('s1', 's3', port1=4, port2=4, bw=10, delay='6ms')

        # --- monitoring probe on s1 (receives mirrored URLLC) ---
        self.addLink('h11', 's1', port2=5, delay='1ms')

        # --- UPFs ---
        self.addLink('h1', 's2', port2=3, delay='1ms')
        self.addLink('h2', 's4', port2=3, delay='1ms')

        # --- gNodeB-A UEs ---
        for port, h in zip((2, 3, 4, 5, 6), ('h3', 'h4', 'h5', 'h6', 'h10')):
            self.addLink(h, 's5', port2=port, delay='1ms')

        # --- gNodeB-B UEs ---
        for port, h in zip((2, 3, 4), ('h7', 'h8', 'h9')):
            self.addLink(h, 's6', port2=port, delay='1ms')


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

    # Static ARP: no broadcast ever enters the ring.
    info("*** Installing static ARP entries\n")
    for h in net.hosts:
        for other, (ip, mac) in HOSTS.items():
            if other != h.name:
                h.cmd('arp -s %s %s' % (ip, mac))

    info("*** Fail-secure OVS bridges, no STP\n")
    for sw in net.switches:
        sw.cmd('ovs-vsctl set-fail-mode %s secure' % sw.name)

    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
