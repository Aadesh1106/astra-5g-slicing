#!/usr/bin/env python3
"""
Astra Mobility 5G SDN Slicing Lab — Charts & Topology
Generates:
  1. 10-Switch, 15-Host Multi-Domain 5G Transport Fabric Topology
  2. Multi-phase 5G Slice Performance Comparison (Throughput, Latency, Jitter, Loss)
  3. URLLC Latency Improvement Headline Chart
"""

import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx

from matplotlib.lines import Line2D

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / 'results'
FIGURES_DIR = RESULTS_DIR / 'figures'
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
OUT = str(FIGURES_DIR)


def draw_topology():
    """Render the 10-switch, 15-host 5G transport slicing fabric topology."""
    G = nx.Graph()

    # Core Ring & Diagonal
    core_ring = [('s1', 's2'), ('s2', 's3'), ('s3', 's4'), ('s4', 's1')]
    diagonal = [('s1', 's3')]

    # Regional Gateway & DC Spine/Leaf
    gateway = [('s8', 's2'), ('s8', 's3')]
    dc_spine_leaf = [('s9', 's2'), ('s9', 's4'), ('s9', 's10')]

    # RAN Edge Uplinks
    ran_uplinks = [('s5', 's1'), ('s6', 's3'), ('s7', 's8')]

    # Host attachments
    hosts = [
        # DC Leaf Hosts (s10)
        ('h1', 's10'),   # 5G UPF (eMBB / mMTC)
        ('h14', 's10'),  # MEC Edge Application Server
        # Core & Gateway Infrastructure
        ('h2', 's4'),    # Dedicated URLLC UPF
        ('h11', 's1'),   # Lawful Intercept Mirror Probe
        ('h15', 's8'),   # NOC / OAM Telemetry Monitor
        # RAN Edge gNodeB-A Suburb (s5)
        ('h3', 's5'),    # Phone 1 (eMBB)
        ('h4', 's5'),    # Phone 2 (eMBB)
        ('h5', 's5'),    # Connected Car 1 (URLLC)
        ('h6', 's5'),    # Connected Car 2 (URLLC)
        ('h10', 's5'),   # Autonomous Mobile UE (Roams s5 <-> s6 <-> s7)
        # RAN Edge gNodeB-B Smart City (s6)
        ('h7', 's6'),    # Smart Grid Sensor (mMTC)
        ('h8', 's6'),    # CCTV Video Sensor (mMTC)
        ('h9', 's6'),    # Rogue Telemetry Sensor (mMTC)
        # RAN Edge gNodeB-C Stadium / Factory (s7)
        ('h12', 's7'),   # Industrial Robot (URLLC)
        ('h13', 's7'),   # AR/VR Headset (eMBB)
    ]

    # Explicit 2D Coordinates for clear multi-domain hierarchy
    pos = {
        # Core Ring
        's1': (0.0, 0.0),
        's2': (3.0, 0.0),
        's3': (3.0, -2.5),
        's4': (0.0, -2.5),
        # Regional Gateway & DC Domain
        's8': (5.2, -1.25),
        's9': (1.5, -4.0),
        's10': (1.5, -5.8),
        # RAN Edge Switches
        's5': (-2.5, 0.0),     # gNodeB-A Suburb
        's6': (3.0, -4.6),     # gNodeB-B Smart City
        's7': (7.5, -1.25),    # gNodeB-C Stadium
        # Infrastructure Hosts
        'h11': (-0.6, 1.4),    # Probe on s1
        'h2': (-1.5, -2.5),    # URLLC UPF on s4
        'h15': (5.2, 0.2),     # NOC Monitor on s8
        'h1': (0.3, -7.0),     # eMBB/mMTC UPF on s10
        'h14': (2.7, -7.0),    # MEC Edge Server on s10
        # gNodeB-A Hosts (s5)
        'h3': (-4.0, 1.2),
        'h4': (-4.2, 0.4),
        'h5': (-4.2, -0.4),
        'h6': (-4.0, -1.2),
        'h10': (-2.5, 1.6),    # Mobile UE
        # gNodeB-B Hosts (s6)
        'h7': (4.2, -4.0),
        'h8': (4.5, -4.6),
        'h9': (4.2, -5.2),
        # gNodeB-C Hosts (s7)
        'h12': (9.0, -0.8),
        'h13': (9.0, -1.7),
    }

    # Add edges to NetworkX graph
    for u, v in core_ring + diagonal + gateway + dc_spine_leaf + ran_uplinks:
        G.add_edge(u, v)
    for h, sw in hosts:
        G.add_edge(h, sw)

    fig, ax = plt.subplots(figsize=(16, 11), facecolor='#ffffff')

    # Draw Switch Nodes
    nx.draw_networkx_nodes(G, pos, nodelist=['s1', 's2', 's3', 's4'],
                           node_color='#d35400', node_size=1500, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['s8'],
                           node_color='#b9770e', node_size=1400, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['s9', 's10'],
                           node_color='#2c3e50', node_size=1300, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['s5', 's6', 's7'],
                           node_color='#2980b9', node_size=1400, ax=ax)

    # Draw Host Nodes by Slice / Role
    nx.draw_networkx_nodes(G, pos, nodelist=['h1', 'h2', 'h14', 'h11', 'h15'],
                           node_color='#16a085', node_size=850, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['h3', 'h4', 'h13'],
                           node_color='#8e44ad', node_size=650, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['h5', 'h6', 'h12'],
                           node_color='#c0392b', node_size=650, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['h7', 'h8', 'h9'],
                           node_color='#f39c12', node_size=650, ax=ax)
    nx.draw_networkx_nodes(G, pos, nodelist=['h10'],
                           node_color='#e74c3c', node_shape='s', node_size=750, ax=ax)

    # Draw Edges with styled widths & colors
    nx.draw_networkx_edges(G, pos, edgelist=core_ring, width=4.5, edge_color='#2c3e50', ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=diagonal, width=2.5, edge_color='#e67e22', style='dashed', ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=gateway, width=3.2, edge_color='#7f8c8d', ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=dc_spine_leaf, width=3.5, edge_color='#34495e', ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=ran_uplinks, width=3.0, edge_color='#2980b9', ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=[(h, sw) for h, sw in hosts],
                           width=1.2, edge_color='#bdc3c7', ax=ax)

    # Node Labels
    nx.draw_networkx_labels(G, pos, font_size=9, font_color='white', font_weight='bold', ax=ax)

    # Domain Annotations
    ax.text(-2.5, -0.6, 'RAN Edge:\ngNodeB-A (Suburb)', fontsize=10, ha='center',
            color='#2980b9', fontweight='bold', bbox=dict(boxstyle='round,pad=0.3', facecolor='#ebf5fb', edgecolor='none'))
    ax.text(3.0, -5.4, 'RAN Edge:\ngNodeB-B (Smart City)', fontsize=10, ha='center',
            color='#2980b9', fontweight='bold', bbox=dict(boxstyle='round,pad=0.3', facecolor='#ebf5fb', edgecolor='none'))
    ax.text(7.5, -2.0, 'RAN Edge:\ngNodeB-C (Stadium/Factory)', fontsize=10, ha='center',
            color='#2980b9', fontweight='bold', bbox=dict(boxstyle='round,pad=0.3', facecolor='#ebf5fb', edgecolor='none'))
    ax.text(1.5, -1.25, '10 Mbps Core Ring\n(2ms per hop)\nDiagonal TE Link: 6ms',
            fontsize=10, ha='center', color='#d35400', fontweight='bold')
    ax.text(1.5, -6.6, 'Data Center Domain\n(s9 Spine, s10 Leaf)', fontsize=10, ha='center',
            color='#2c3e50', fontweight='bold')

    # Visual roaming path indication for h10
    ax.annotate('', xy=pos['s6'], xytext=pos['s5'],
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.2",
                                color='#e74c3c', lw=1.5, ls=':'))
    ax.annotate('', xy=pos['s7'], xytext=pos['s6'],
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.2",
                                color='#e74c3c', lw=1.5, ls=':'))
    ax.text(0.5, 2.0, 'Mobile Handover Path (h10): s5 <-> s6 <-> s7',
            fontsize=11, color='#c0392b', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#fdedec', edgecolor='#e74c3c', lw=1))

    # Clean Legend with dedicated Line2D proxy markers
    legend_elements = [
        Line2D([0], [0], marker='o', color='none', label='Core Ring (s1-s4)',
               markerfacecolor='#d35400', markeredgecolor='#ba4a00', markersize=10),
        Line2D([0], [0], marker='o', color='none', label='Regional Gateway (s8)',
               markerfacecolor='#b9770e', markeredgecolor='#9a630b', markersize=10),
        Line2D([0], [0], marker='o', color='none', label='DC Spine / Leaf (s9-s10)',
               markerfacecolor='#2c3e50', markeredgecolor='#1b2631', markersize=10),
        Line2D([0], [0], marker='o', color='none', label='RAN gNodeBs (s5-s7)',
               markerfacecolor='#2980b9', markeredgecolor='#21618c', markersize=10),
        Line2D([0], [0], marker='o', color='none', label='Servers & Probes (UPF/MEC/NOC)',
               markerfacecolor='#16a085', markeredgecolor='#117a65', markersize=9),
        Line2D([0], [0], marker='o', color='none', label='eMBB UEs (Phones / AR)',
               markerfacecolor='#8e44ad', markeredgecolor='#6c3483', markersize=8),
        Line2D([0], [0], marker='o', color='none', label='URLLC UEs (Cars / Robot)',
               markerfacecolor='#c0392b', markeredgecolor='#922b21', markersize=8),
        Line2D([0], [0], marker='o', color='none', label='mMTC Sensors (Smart City)',
               markerfacecolor='#f39c12', markeredgecolor='#d68910', markersize=8),
        Line2D([0], [0], marker='s', color='none', label='Mobile UE (Roams s5-s6-s7)',
               markerfacecolor='#e74c3c', markeredgecolor='#c0392b', markersize=9),
    ]
    ax.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.98),
              fontsize=9.5, labelspacing=0.75, handletextpad=0.8, borderpad=0.8,
              framealpha=0.95, facecolor='#f8f9f9', edgecolor='#bdc3c7')
    ax.set_title('Astra: 5G Slice-Aware SDN Transport Fabric Topology\n'
                 '10 OpenFlow 1.3 Switches (s1-s10) | 15 Hosts (h1-h15) | Multi-Domain RAN, Core Ring & DC',
                 fontsize=14, fontweight='bold', pad=15)
    ax.set_xlim(-5.2, 10.5)
    ax.set_ylim(-7.8, 2.8)
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(OUT + '/astra_5g_topology.png', dpi=180)
    plt.close()
    print('Updated astra_5g_topology.png successfully (10 switches, 15 hosts).')


def draw_performance():
    """Render the 4-phase benchmark comparison and headline figures."""
    json_path = RESULTS_DIR / 'astra_results.json'
    if not json_path.exists():
        print(f"Warning: {json_path} not found. Skipping performance chart generation.")
        return

    with open(json_path) as f:
        r = json.load(f)

    phase_keys = ['baseline', 'rate_limited', 'priority_qos', 'full_contention']
    phases = ['No QoS\n(Congested)', 'Rate-Limited\n(Meter Only)', 'Priority QoS\n(Queues Active)', 'Full Contention\n(All Slices)']

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

    colors = ['#e74c3c', '#f39c12', '#2980b9', '#27ae60']

    fig, axes = plt.subplots(1, 4, figsize=(22, 5.5), facecolor='#ffffff')

    # 1. Throughput Comparison
    ax = axes[0]
    x = range(len(phases))
    w = 0.25
    ax.bar([i - w for i in x], urllc_t, width=w, label='URLLC (V2X/Robotics)', color='#c0392b', yerr=urllc_t_err, capsize=4)
    ax.bar(list(x), embb_t, width=w, label='eMBB (Video/AR)', color='#8e44ad', yerr=embb_t_err, capsize=4)
    ax.bar([i + w for i in x], mmtc_t, width=w, label='mMTC (IoT Sensors)', color='#f39c12', yerr=mmtc_t_err, capsize=4)
    ax.set_title('Slice Throughput (Mbps)', fontweight='bold')
    ax.set_xticks(list(x))
    ax.set_xticklabels(phases, fontsize=9)
    ax.set_ylabel('Throughput (Mbps)')
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    ax.legend(loc='upper right', fontsize=8.5)

    # 2. URLLC Latency (Log Scale)
    ax = axes[1]
    bars = ax.bar(x, urllc_l, color=colors, yerr=urllc_l_err, capsize=4)
    ax.set_title('URLLC Latency (ms) - Log Scale', fontweight='bold')
    ax.set_xticks(list(x))
    ax.set_xticklabels(phases, fontsize=9)
    ax.set_ylabel('Latency (ms)')
    ax.set_yscale('log')
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    for i, v in enumerate(urllc_l):
        ax.text(i, v * 1.15, f'{v:.0f} ms', ha='center', fontsize=9.5, fontweight='bold')

    # 3. URLLC Jitter
    ax = axes[2]
    ax.bar(x, urllc_j, color=colors, yerr=urllc_j_err, capsize=4)
    ax.set_title('URLLC Packet Jitter (ms)', fontweight='bold')
    ax.set_xticks(list(x))
    ax.set_xticklabels(phases, fontsize=9)
    ax.set_ylabel('Jitter (ms)')
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    for i, v in enumerate(urllc_j):
        ax.text(i, v + 2, f'{v:.0f} ms', ha='center', fontsize=9.5)

    # 4. mMTC Packet Loss
    ax = axes[3]
    ax.bar(x, mmtc_loss, color=colors, yerr=mmtc_loss_err, capsize=4)
    ax.set_title('mMTC Packet Loss (%)', fontweight='bold')
    ax.set_xticks(list(x))
    ax.set_xticklabels(phases, fontsize=9)
    ax.set_ylabel('% Packet Loss')
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    for i, v in enumerate(mmtc_loss):
        ax.text(i, v + 0.5, f'{v:.1f}%', ha='center', fontsize=9.5)

    fig.suptitle('Astra Mobility 5G — Quantitative QoS & Slicing Impact Across Experimental Phases',
                 fontsize=14, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0.05, 1, 0.95])
    plt.savefig(OUT + '/astra_5g_performance.png', dpi=180)
    plt.close()
    print('Updated astra_5g_performance.png successfully.')

    # Headline Latency Chart
    fig, ax = plt.subplots(figsize=(10, 6), facecolor='#ffffff')
    ax.bar(x, urllc_l, color=colors, yerr=urllc_l_err, capsize=4, width=0.55)
    ax.set_title('URLLC Latency Under Slicing & Transport Congestion', fontsize=15, fontweight='bold', pad=12)
    ax.set_xticks(list(x))
    ax.set_xticklabels(phases, fontsize=11)
    ax.set_ylabel('Average RTT Latency (ms) - Log Scale', fontsize=12)
    ax.set_yscale('log')
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    for i, v in enumerate(urllc_l):
        ax.text(i, v * 1.25, f'{v:.0f} ms', ha='center', fontsize=12, fontweight='bold')

    ratio = urllc_l[0] / urllc_l[3] if urllc_l[3] > 0 else 0
    ax.text(0.5, 0.65, f'{ratio:.0f}x Latency Improvement\n({urllc_l[0]:.0f} ms -> {urllc_l[3]:.0f} ms)',
            transform=ax.transAxes, fontsize=18, color='#27ae60', fontweight='bold', ha='center',
            bbox=dict(facecolor='white', alpha=0.9, edgecolor='#27ae60', boxstyle='round,pad=0.5', lw=1.5))

    plt.tight_layout()
    plt.savefig(OUT + '/astra_5g_urllc_headline.png', dpi=180)
    plt.close()
    print('Updated astra_5g_urllc_headline.png successfully.')


if __name__ == '__main__':
    draw_topology()
    draw_performance()
