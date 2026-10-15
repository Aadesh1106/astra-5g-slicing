#!/usr/bin/env python3
"""
Astra Mobility 5G Traffic Monitor
Captures ring traffic, proves URLLC bypasses eMBB congestion.
"""

import subprocess
import time
import json


import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PCAPS_DIR = BASE_DIR / "pcaps"
PCAPS_DIR.mkdir(parents=True, exist_ok=True)


class AstraMonitor:
    def __init__(self):
        self.pcap_short = str(PCAPS_DIR / "astra_short_path.pcap")   # s1-eth2: s1->s4
        self.pcap_long = str(PCAPS_DIR / "astra_long_path.pcap")     # s1-eth1: s1->s2

    def start_captures(self, duration=30):
        print(f"\n[{'='*60}]")
        print(f"Capturing both ring paths for {duration}s")
        print(f"[{'='*60}]\n")

        subprocess.Popen(['sudo', 'timeout', str(duration), 'tcpdump', '-i', 's1-eth2',
                          '-w', self.pcap_short, '-nn'], stdout=subprocess.DEVNULL)
        subprocess.Popen(['sudo', 'timeout', str(duration), 'tcpdump', '-i', 's1-eth1',
                          '-w', self.pcap_long, '-nn'], stdout=subprocess.DEVNULL)
        return duration

    def analyze_dscp(self, pcap_file, label):
        print(f"\n--- DSCP Analysis: {label} ---")
        try:
            cmd = ['tshark', '-r', pcap_file, '-T', 'fields',
                   '-e', 'ip.src', '-e', 'ip.dsfield.dscp', '-e', 'frame.len', '-Y', 'ip']
            r = subprocess.run(cmd, capture_output=True, text=True)
            lines = r.stdout.strip().split('\n')

            counts = {46: 0, 34: 0, 0: 0, 'other': 0}
            bytes_map = {46: 0, 34: 0, 0: 0, 'other': 0}

            for line in lines:
                if not line.strip():
                    continue
                parts = line.split('\t')
                if len(parts) >= 3:
                    try:
                        dscp = int(parts[1]) if parts[1] else 0
                        length = int(parts[2]) if parts[2] else 0
                    except:
                        continue
                    key = dscp if dscp in counts else 'other'
                    counts[key] += 1
                    bytes_map[key] += length

            total = sum(counts.values())
            print(f"  Total packets: {total}")
            print(f"  DSCP 46 (EF/URLLC):  {counts[46]:>5} pkts, {bytes_map[46]:>10} bytes")
            print(f"  DSCP 34 (AF41/eMBB): {counts[34]:>5} pkts, {bytes_map[34]:>10} bytes")
            print(f"  DSCP 0  (BE/mMTC):   {counts[0]:>5} pkts, {bytes_map[0]:>10} bytes")

        except FileNotFoundError:
            print("  tshark not installed. Run: sudo apt install tshark")

    def get_queue_stats(self):
        print(f"\n[{'='*60}]")
        print("OVS Queue Statistics")
        print(f"[{'='*60}]")
        r = subprocess.run(['sudo', 'ovs-vsctl', 'list', 'Queue'],
                           capture_output=True, text=True)
        print(r.stdout)

    def get_flow_stats(self, dpid=1):
        print(f"\n--- Flow Stats: s{dpid} ---")
        import urllib.request
        try:
            url = f"http://localhost:8080/stats/flow/{dpid}"
            with urllib.request.urlopen(url) as resp:
                data = json.loads(resp.read().decode())
                for flow in data.get(str(dpid), []):
                    match = flow.get('match', {})
                    actions = flow.get('actions', [])
                    src = match.get('ipv4_src', 'any')
                    pkts = flow.get('packet_count', 0)
                    bytes_cnt = flow.get('byte_count', 0)
                    prio = flow.get('priority', 0)

                    queue = 'none'
                    for a in actions:
                        if isinstance(a, dict):
                            if a.get('type') == 'SET_QUEUE':
                                queue = a.get('queue_id', 'none')
                        elif isinstance(a, str) and 'SET_QUEUE' in a:
                            queue = a.split(':')[1]

                    if queue != 'none':
                        print(f"  prio={prio:<3} src={src:<15} queue={queue}  pkts={pkts:<6} bytes={bytes_cnt}")
        except Exception as e:
            print(f"  Error: {e}")

    def run(self, duration=30):
        self.start_captures(duration)
        time.sleep(duration + 2)
        self.analyze_dscp(self.pcap_short, "SHORT path (s1->s4) - URLLC should dominate")
        self.analyze_dscp(self.pcap_long, "LONG path (s1->s2) - eMBB should dominate")
        self.get_queue_stats()
        self.get_flow_stats(1)


if __name__ == '__main__':
    m = AstraMonitor()
    m.run(30)
