#!/usr/bin/env python3
"""
Astra Mobility 5G Core SDN Fabric
Core ring: s1-s2-s3-s4 (10 Mbps lab / 10Gbps prod)
Edge aggregation: s5 (gNodeB-A) -> s1, s6 (gNodeB-B) -> s3
Hosts:
  h1 (eMBB server/UPF) on s2
  h2 (URLLC server/UPF) on s4
  h3,h4 (smartphones) on s5
  h5,h6 (autonomous cars) on s5
  h7,h8,h9 (mMTC sensors) on s6
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel, info
import os

os.environ['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'


class Astra5GTopo(Topo):
    def build(self):
        info("*** Building Astra Mobility 5G Core Fabric\n")

        # --- UPF / Core Servers ---
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')  # eMBB UPF
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')  # URLLC UPF

        # --- UE Devices: gNodeB-A (s5) ---
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')  # Smartphone A
        h4 = self.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')  # Smartphone B
        h5 = self.addHost('h5', ip='10.0.0.5/24', mac='00:00:00:00:00:05')  # Car A
        h6 = self.addHost('h6', ip='10.0.0.6/24', mac='00:00:00:00:00:06')  # Car B

        # --- UE Devices: gNodeB-B (s6) ---
        h7 = self.addHost('h7', ip='10.0.0.7/24', mac='00:00:00:00:00:07')  # Smart meter A
        h8 = self.addHost('h8', ip='10.0.0.8/24', mac='00:00:00:00:00:08')  # Smart meter B
        h9 = self.addHost('h9', ip='10.0.0.9/24', mac='00:00:00:00:00:09')  # Toll gate

        # --- Core Ring Switches (OF1.3) ---
        s1 = self.addSwitch('s1', dpid='0000000000000001', protocols='OpenFlow13')
        s2 = self.addSwitch('s2', dpid='0000000000000002', protocols='OpenFlow13')
        s3 = self.addSwitch('s3', dpid='0000000000000003', protocols='OpenFlow13')
        s4 = self.addSwitch('s4', dpid='0000000000000004', protocols='OpenFlow13')

        # --- Edge Aggregation Switches ---
        s5 = self.addSwitch('s5', dpid='0000000000000005', protocols='OpenFlow13')  # gNodeB-A
        s6 = self.addSwitch('s6', dpid='0000000000000006', protocols='OpenFlow13')  # gNodeB-B

        # --- Core Ring Links (10 Mbps in lab, 10Gbps in prod) ---
        self.addLink(s1, s2, port1=1, bw=10, delay='2ms')   # s1-eth1 (LONG path)
        self.addLink(s2, s3, bw=10, delay='2ms')
        self.addLink(s3, s4, bw=10, delay='2ms')
        self.addLink(s4, s1, port2=2, bw=10, delay='2ms')   # s1-eth2 (SHORT path)

        # --- Edge Uplinks ---
        self.addLink(s5, s1, port2=3, bw=10, delay='1ms')   # s1-eth3 (gNodeB-A -> s1)
        self.addLink(s6, s3, bw=10, delay='1ms')   # gNodeB-B -> s3

        # --- Server Attachments ---
        self.addLink(h1, s2, delay='1ms')   # eMBB UPF
        self.addLink(h2, s4, delay='1ms')   # URLLC UPF

        # --- gNodeB-A Devices ---
        self.addLink(h3, s5, delay='1ms')   # Phone A
        self.addLink(h4, s5, delay='1ms')   # Phone B
        self.addLink(h5, s5, delay='1ms')   # Car A
        self.addLink(h6, s5, delay='1ms')   # Car B

        # --- gNodeB-B Devices ---
        self.addLink(h7, s6, delay='1ms')   # Meter A
        self.addLink(h8, s6, delay='1ms')   # Meter B
        self.addLink(h9, s6, delay='1ms')   # Toll gate


def run():
    setLogLevel('info')
    topo = Astra5GTopo()
    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6653),
        link=TCLink,
        autoSetMacs=True
    )
    net.start()

    info("\n*** Enabling STP on all switches to prevent ring loops...\n")
    for sw in net.switches:
        sw.cmd(f'ovs-vsctl set bridge {sw.name} stp_enable=true')
    # Force s1 to be the root bridge so its links to the ring (s1-eth1, s1-eth2) are never blocked
    net.get('s1').cmd('ovs-vsctl set bridge s1 other_config:stp-priority=4096')

    info("\n*** DPID check:\n")
    for sw in net.switches:
        info(f"  {sw.name}: {sw.dpid}\n")

    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
