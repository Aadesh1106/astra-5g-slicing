#!/usr/bin/env python3
"""
Astra Mobility 5G Performance Test
Before/after QoS: throughput, latency, jitter per slice.
Commands are executed inside Mininet host namespaces via mnexec.
"""

import subprocess
import json
import time
import statistics
import os


def host_pid(host):
    try:
        out = subprocess.run(['pgrep', '-f', 'mininet:' + host],
                             capture_output=True, text=True).stdout.strip()
        return out.split()[0] if out else None
    except Exception:
        return None


def host_cmd(host, *args):
    """Run a command inside a Mininet host's network namespace."""
    pid = host_pid(host)
    if not pid:
        return subprocess.run(args, capture_output=True, text=True)
    return subprocess.run(['mnexec', '-a', pid, '--'] + list(args),
                          capture_output=True, text=True, timeout=120)


class AstraPerfTest:
    def __init__(self):
        pass

    def iperf3(self, client_host, server_host, port, duration=10, bandwidth='100M', udp=False):
        cmd = ['iperf3', '-c', '10.0.0.' + server_host.strip('h'),
               '-p', str(port), '-t', str(duration), '-J']
        if bandwidth:
            cmd.extend(['-b', bandwidth])
        if udp:
            cmd.append('-u')
        try:
            pid = host_pid(client_host)
            if not pid: return {'mbps': 0.0, 'retrans': 0, 'loss': 0.0}
            r = subprocess.run(['mnexec', '-a', pid, '--'] + cmd,
                               capture_output=True, text=True, timeout=30)
            d = json.loads(r.stdout)
            if udp:
                mbps = d['end']['sum']['bits_per_second'] / 1e6
                loss = d['end']['sum'].get('lost_percent', 0.0)
                return {'mbps': mbps, 'loss': loss}
            else:
                mbps = d['end']['sum_received']['bits_per_second'] / 1e6
                retrans = d['end']['sum_sent'].get('retransmits', 0)
                return {'mbps': mbps, 'retrans': retrans}
        except Exception as e:
            print(f"[WARN] iperf3 {client_host}->{server_host} failed: {e}")
            return {'mbps': 0.0, 'retrans': 0, 'loss': 0.0}

    def ping(self, from_host, target, count=20):
        cmd = ['ping', '-c', str(count), '-i', '0.2', target]
        try:
            pid = host_pid(from_host)
            if not pid: return {'avg': 0.0, 'jitter': 0.0, 'min': 0.0, 'max': 0.0}
            r = subprocess.run(['mnexec', '-a', pid, '--'] + cmd,
                               capture_output=True, text=True, timeout=10)
            latencies = []
            for line in r.stdout.split('\n'):
                if 'time=' in line:
                    latencies.append(float(line.split('time=')[1].split(' ')[0]))
            if len(latencies) >= 2:
                return {
                    'avg': statistics.mean(latencies),
                    'jitter': statistics.stdev(latencies),
                    'min': min(latencies),
                    'max': max(latencies)
                }
            return {'avg': 0.0, 'jitter': 0.0, 'min': 0.0, 'max': 0.0}
        except Exception as e:
            print(f"[WARN] ping {from_host}->{target} failed: {e}")
            return {'avg': 0.0, 'jitter': 0.0, 'min': 0.0, 'max': 0.0}

    def start_servers(self):
        # measurement ports 5001/5002/5005 + dedicated saturator ports 5003/5004/5006
        for host, port in [('h1', 5001), ('h2', 5002),
                           ('h1', 5003), ('h2', 5004),
                           ('h2', 5005), ('h2', 5006)]:
            pid = host_pid(host)
            if pid:
                subprocess.Popen(['mnexec', '-a', pid, '--', 'iperf3', '-s',
                                  '-p', str(port), '-D'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

    def stop_servers(self):
        subprocess.run(['sudo', 'pkill', '-f', 'iperf3 -s'])
        time.sleep(1)

    def qos_off(self):
        print("  [Setup] Tearing down QoS...")
        for prio in (500, 400, 300):
            subprocess.run(['sudo', 'ovs-ofctl', '-O', 'OpenFlow13', 'del-flows',
                            's1', 'priority=%d' % prio],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['curl', '-s', '-X', 'POST', '-d',
                        '{"dpid":1,"meter_id":100}',
                        'http://localhost:8080/stats/meterentry/delete'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for port in ('s1-eth1', 's1-eth2', 's3-eth1', 's3-eth2'):
            subprocess.run(['sudo', 'ovs-vsctl', '--if-exists', 'clear', 'port', port, 'qos'],
                           stdout=subprocess.DEVNULL)
        subprocess.run(['sudo', 'ovs-vsctl', '--all', 'destroy', 'QoS'], stdout=subprocess.DEVNULL)
        subprocess.run(['sudo', 'ovs-vsctl', '--all', 'destroy', 'Queue'], stdout=subprocess.DEVNULL)
        subprocess.run(['sudo', 'ovs-ofctl', '-O', 'OpenFlow13', 'del-flows',
                        's3', 'priority=300'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)

    def qos_on(self):
        print("  [Setup] Deploying slice QoS...")
        subprocess.run(['bash', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             'astra_qos.sh')],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        
    def setup_rate_limit(self):
        self.qos_off()
        print("  [Setup] Deploying rate limit...")
        subprocess.run(['curl', '-s', '-X', 'POST', '-d',
                        '{"dpid":1,"flags":"KBPS","meter_id":100,"bands":'
                        '[{"type":"DROP","rate":4000,"burst_size":400}]}',
                        'http://localhost:8080/stats/meterentry/add'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for ip in ('10.0.0.3', '10.0.0.4'):
            subprocess.run(['sudo', 'ovs-ofctl', '-O', 'OpenFlow13', 'add-flow',
                            's1', 'priority=400,ip,nw_src=%s actions=meter:100,output:1' % ip],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)

    def saturate(self, client_host, server_ip, port, bandwidth, duration=25, udp=False):
        pid = host_pid(client_host)
        if not pid: return
        cmd = ['mnexec', '-a', pid, '--', 'iperf3',
               '-c', server_ip, '-p', str(port), '-t', str(duration),
               '-b', bandwidth]
        if udp:
            cmd.append('-u')
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run_phase(self, do_saturate=True, full_contention=False):
        self.start_servers()

        if do_saturate:
            print("  [Step 1] Saturating ring with eMBB (h4->h1 @ 80M)...")
            self.saturate('h4', '10.0.0.1', 5003, '80M')
            if full_contention:
                print("  [Step 1b] Saturating ring with mMTC (h8->h2 @ 5M UDP)...")
                self.saturate('h8', '10.0.0.2', 5006, '5M', udp=True)
            time.sleep(3)

        print("  [Step 2] Measuring URLLC (h5->h2) & mMTC (h9->h2)...")
        pid_h9 = host_pid('h9')
        if pid_h9:
            mmtc_proc = subprocess.Popen(['mnexec', '-a', pid_h9, '--', 'iperf3',
                                          '-c', '10.0.0.2', '-p', '5005', '-t', '10',
                                          '-b', '1M', '-u', '-J'],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            mmtc_proc = None

        r_urllc = self.iperf3('h5', 'h2', 5002, duration=10, bandwidth='20M')
        l_urllc = self.ping('h5', '10.0.0.2')

        if mmtc_proc:
            try:
                mmtc_out, mmtc_err = mmtc_proc.communicate(timeout=30)
                d = json.loads(mmtc_out)
                r_mmtc = {
                    'mbps': d['end']['sum']['bits_per_second'] / 1e6,
                    'loss': d['end']['sum'].get('lost_percent', 0.0),
                    'jitter': d['end']['sum'].get('jitter_ms', 0.0)
                }
            except Exception as e:
                mmtc_proc.kill()
                print(f"[WARN] iperf3 mMTC h9->h2 failed: {e}")
                r_mmtc = {'mbps': 0.0, 'loss': 0.0, 'jitter': 0.0}
        else:
            r_mmtc = {'mbps': 0.0, 'loss': 0.0, 'jitter': 0.0}

        print("  [Step 3] Measuring eMBB (h3->h1) throughput...")
        r_embb = self.iperf3('h3', 'h1', 5001, duration=10, bandwidth='80M')
        l_embb = self.ping('h3', '10.0.0.1')

        print(f"\n  URLLC (Car):  {r_urllc['mbps']:.1f} Mbps | Latency: {l_urllc['avg']:.2f}ms | Jitter: {l_urllc['jitter']:.2f}ms")
        print(f"  eMBB (Phone): {r_embb['mbps']:.1f} Mbps | Latency: {l_embb['avg']:.2f}ms | Jitter: {l_embb['jitter']:.2f}ms")
        print(f"  mMTC (IoT):   {r_mmtc['mbps']:.1f} Mbps | Loss: {r_mmtc['loss']:.1f}% | Jitter: {r_mmtc['jitter']:.2f}ms")

        self.stop_servers()
        return {
            'urllc_t': r_urllc['mbps'],
            'urllc_l': l_urllc,
            'embb_t': r_embb['mbps'],
            'mmtc_t': r_mmtc['mbps'],
            'mmtc_loss': r_mmtc['loss']
        }


def aggregate_results(samples):
    aggregated = {}
    for key in ['urllc_t', 'embb_t', 'mmtc_t', 'mmtc_loss']:
        vals = [s[key] for s in samples]
        aggregated[key + '_mean'] = statistics.mean(vals)
        aggregated[key + '_std'] = statistics.stdev(vals) if len(vals) > 1 else 0.0
        aggregated[key + '_samples'] = vals

    for lat_metric in ['avg', 'jitter', 'min', 'max']:
        vals = [s['urllc_l'][lat_metric] for s in samples]
        aggregated[f'urllc_l_{lat_metric}_mean'] = statistics.mean(vals)
        aggregated[f'urllc_l_{lat_metric}_std'] = statistics.stdev(vals) if len(vals) > 1 else 0.0
        aggregated[f'urllc_l_{lat_metric}_samples'] = vals
    
    return aggregated

if __name__ == '__main__':
    N_REPS = 1
    final_results = {}
    
    t = AstraPerfTest()
    
    phases = [
        ('baseline', 'PHASE 1: NO QoS (Congested)', t.qos_off, False),
        ('rate_limited', 'PHASE 2: RATE LIMITING (eMBB hard-capped)', t.setup_rate_limit, False),
        ('priority_qos', 'PHASE 3: PRIORITY QUEUING (URLLC short path + priority queue)', t.qos_on, False),
        ('full_contention', 'PHASE 4: FULL CONTENTION (Priority QoS + eMBB/mMTC saturated)', t.qos_on, True)
    ]
    
    for phase, name, setup_fn, full_cont in phases:
        print("\n" + "=" * 70)
        print(name)
        print("=" * 70)
        setup_fn()
        
        samples = []
        for i in range(N_REPS):
            print(f"\n--- Repetition {i+1}/{N_REPS} ---")
            res = t.run_phase(do_saturate=True, full_contention=full_cont)
            samples.append(res)
            time.sleep(2)
        
        final_results[phase] = aggregate_results(samples)
        
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    results_dir = os.path.join(project_root, 'results')

    os.makedirs(results_dir, exist_ok=True)


    out_file = os.path.join(results_dir, 'astra_results.json')

    with open(out_file, 'w') as f:
        json.dump(final_results, f, indent=2)
    print(f"\nResults saved to {out_file}")
