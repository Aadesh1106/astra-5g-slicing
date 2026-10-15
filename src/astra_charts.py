#!/usr/bin/env python3
"""
Astra Mobility 5G SDN Slicing Lab — Charts & Topology
Generates: topology diagram + performance comparison charts.
"""

import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / 'results'
FIGURES_DIR = RESULTS_DIR / 'figures'
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
OUT = str(FIGURES_DIR)


def draw_topology():
    G = nx.Graph()
    ring = [('s1', 's2'), ('s2', 's3'), ('s3', 's4'), ('s4', 's1')]
    edge = [('s5', 's1'), ('s6', 's3')]
    hosts = [('h1', 's2'), ('h2', 's4'),
             ('h3', 's5'), ('h4', 's5'), ('h5', 's5'), ('h6', 's5'),
             ('h7', 's6'), ('h8', 's6'), ('h9', 's6')]

    pos = {'s1': (0, 0), 's2': (2, 0), 's3': (2, -2), 's4': (0, -2)}
    pos['s5'] = (0, 2)
    pos['s6'] = (2, -4)
    hpos = {
        'h1': (3, 0.6), 'h2': (-1, -2.6),
        'h3': (-1.1, 2.7), 'h4': (-0.6, 3.2), 'h5': (0.6, 3.2), 'h6': (1.1, 2.7),
        'h7': (1.1, -4.7), 'h8': (1.6, -5.2), 'h9': (2.4, -4.7)
    }
    pos.update(hpos)

    for a, b in ring + edge:
        G.add_edge(a, b)
    for h, sw in hosts:
        G.add_edge(h, sw)

    fig, ax = plt.subplots(figsize=(13, 9))
    nx.draw_networkx_nodes(G, pos, nodelist=['s1', 's2', 's3', 's4'],
                           node_color='#d35400', node_size=1500, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['s5', 's6'],
                           node_color='#e67e22', node_size=1200, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['h1', 'h2'],
                           node_color='#16a085', node_size=800, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['h3', 'h4'],
                           node_color='#8e44ad', node_size=500, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['h5', 'h6'],
                           node_color='#c0392b', node_size=500, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['h7', 'h8', 'h9'],
                           node_color='#f39c12', node_size=500, ax=ax)

    nx.draw_networkx_edges(G, pos, edgelist=ring, width=4.0, edge_color='#2c3e50', ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=edge, width=2.5, edge_color='#7f8c8d', ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=[(h, sw) for h, sw in hosts],
                           width=1.0, edge_color='#bdc3c7', ax=ax)

    nx.draw_networkx_labels(G, pos, font_size=9, font_color='white', font_weight='bold', ax=ax)



    ax.text(0, 2.42, 'gNodeB-A', fontsize=10, ha='center', style='italic')
    ax.text(2, -4.42, 'gNodeB-B', fontsize=10, ha='center', style='italic')
    ax.text(1.05, 0.6, 'eMBB UPF (h1)  [s2]', fontsize=9, color='#16a085')
    ax.text(-1.0, -2.9, 'URLLC UPF (h2)  [s4]', fontsize=9, color='#16a085')

    legend = [
        ('#d35400', 'Core ring switch (s1-s4)'),
        ('#e67e22', 'Edge aggregator (s5-s6)'),
        ('#16a085', 'UPF server'),
        ('#8e44ad', 'eMBB UE (h3,h4)'),
        ('#c0392b', 'URLLC UE (h5,h6)'),
        ('#f39c12', 'mMTC sensor (h7-h9)'),
    ]
    for i, (c, lbl) in enumerate(legend):
        ax.plot([], [], marker='o', ms=12, color=c, ls='', label=lbl)
    ax.legend(loc='lower left', fontsize=9)

    ax.set_title('Astra Mobility 5G Core — SDN Slicing Topology\n'
                 'Ring: 10 Mbps links | gNodeB uplinks: 10 Mbps', fontsize=13)
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(OUT + '/astra_5g_topology.png', dpi=150)
    plt.close()
    print('wrote astra_5g_topology.png')


def draw_performance():
    json_path = RESULTS_DIR / 'astra_results.json'
    with open(json_path) as f:
        r = json.load(f)

    phase_keys = ['baseline', 'rate_limited', 'priority_qos', 'full_contention']
    phases = ['No QoS', 'Rate-Limited', 'Priority QoS', 'Full\nContention']
    
    urllc_t = [r[p]['urllc_t_mean'] for p in phase_keys]
    urllc_t_err = [r[p]['urllc_t_std'] for p in phase_keys]
    
    embb_t = [r[p]['embb_t_mean'] for p in phase_keys]
    embb_t_err = [r[p]['embb_t_std'] for p in phase_keys]
    
    mmtc_t = [r[p]['mmtc_t_mean'] for p in phase_keys]
    mmtc_t_err = [r[p]['mmtc_t_std'] for p in phase_keys]
    
    urllc_l = [r[p]['urllc_l_avg_mean'] for p in phase_keys]
    urllc_l_err = [r[p]['urllc_l_avg_std'] for p in phase_keys]
    
    urllc_j = [r[p]['urllc_l_jitter_mean'] for p in phase_keys]
    urllc_j_err = [r[p]['urllc_l_jitter_std'] for p in phase_keys]
    
    mmtc_loss = [r[p]['mmtc_loss_mean'] for p in phase_keys]
    mmtc_loss_err = [r[p]['mmtc_loss_std'] for p in phase_keys]

    colors = ['#bdc3c7', '#f39c12', '#27ae60', '#e74c3c']

    fig, axes = plt.subplots(1, 4, figsize=(20, 5))

    # 1. Throughput
    ax = axes[0]
    x = range(len(phases))
    w = 0.25
    ax.bar([i - w for i in x], urllc_t, width=w, label='URLLC', color='#c0392b', yerr=urllc_t_err, capsize=4)
    ax.bar(list(x), embb_t, width=w, label='eMBB', color='#8e44ad', yerr=embb_t_err, capsize=4)
    ax.bar([i + w for i in x], mmtc_t, width=w, label='mMTC', color='#f39c12', yerr=mmtc_t_err, capsize=4)
    ax.set_title('Slice Throughput (Mbps)')
    ax.set_xticks(list(x)); ax.set_xticklabels(phases)
    ax.set_ylabel('Mbps'); ax.legend(loc='upper right', fontsize=8)

    # 2. Latency
    ax = axes[1]
    ax.bar(x, urllc_l, color=colors, yerr=urllc_l_err, capsize=4)
    ax.set_title('URLLC Avg Latency (ms)')
    ax.set_xticks(list(x)); ax.set_xticklabels(phases)
    ax.set_ylabel('ms')
    ax.set_yscale('log')
    
    # 3. Jitter
    ax = axes[2]
    ax.bar(x, urllc_j, color=colors, yerr=urllc_j_err, capsize=4)
    ax.set_title('URLLC Jitter (ms)')
    ax.set_xticks(list(x)); ax.set_xticklabels(phases)
    ax.set_ylabel('ms')
    
    # 4. mMTC Loss
    ax = axes[3]
    ax.bar(x, mmtc_loss, color=colors, yerr=mmtc_loss_err, capsize=4)
    ax.set_title('mMTC Packet Loss (%)')
    ax.set_xticks(list(x)); ax.set_xticklabels(phases)
    ax.set_ylabel('% Loss')

    fig.suptitle('Astra Mobility 5G — QoS Impact on Slice Performance', fontsize=15)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(OUT + '/astra_5g_performance.png', dpi=150)
    plt.close()
    print('wrote astra_5g_performance.png')

    # Headline Chart
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x, urllc_l, color=colors, yerr=urllc_l_err, capsize=4)
    ax.set_title('URLLC Latency Under Congestion', fontsize=16)
    ax.set_xticks(list(x)); ax.set_xticklabels(phases, fontsize=12)
    ax.set_ylabel('Latency (ms) - Log Scale', fontsize=12)
    ax.set_yscale('log')
    
    for i, v in enumerate(urllc_l):
        ax.text(i, v * 1.15, f'{v:.0f}ms', ha='center', fontsize=12)
        
    ratio = urllc_l[0] / urllc_l[3] if urllc_l[3] > 0 else 0
    ax.text(0.5, 0.6, f'{ratio:.0f}x Improvement', transform=ax.transAxes, fontsize=24,
            color='#27ae60', fontweight='bold', ha='center',
            bbox=dict(facecolor='white', alpha=0.8, edgecolor='none', pad=5))
            
    plt.tight_layout()
    plt.savefig(OUT + '/astra_5g_urllc_headline.png', dpi=150)
    plt.close()
    print('wrote astra_5g_urllc_headline.png')

if __name__ == '__main__':
    draw_topology()
    draw_performance()
