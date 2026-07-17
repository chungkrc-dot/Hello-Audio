import csv
from collections import defaultdict

def calculate_stats():
    csv_path = 'tests/outputs/batch_results/appendix_a_results.csv'
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    print(f"Total rows parsed: {len(rows)}")
    
    overall = defaultdict(lambda: {'baseline': 0.0, 'inclusion': 0.0, 'cents': 0.0, 'count': 0})
    by_inst = defaultdict(lambda: defaultdict(lambda: {'baseline': 0.0, 'inclusion': 0.0, 'cents': 0.0, 'count': 0}))
    
    detailed_md = []
    
    for r in rows:
        engine = r['Engine']
        inst = r['Instrument']
        
        baseline = float(r['Baseline Yield (%)'])
        inclusion = float(r['Inclusion Yield (%)'])
        cents = float(r['Mean Cent Error'])
        
        overall[engine]['baseline'] += baseline
        overall[engine]['inclusion'] += inclusion
        overall[engine]['cents'] += cents
        overall[engine]['count'] += 1
        
        by_inst[inst][engine]['baseline'] += baseline
        by_inst[inst][engine]['inclusion'] += inclusion
        by_inst[inst][engine]['cents'] += cents
        by_inst[inst][engine]['count'] += 1
        
        sign = "+" if cents > 0 else ""
        detailed_md.append(f"| {r['Filename']} | {r['Instrument Folder']} | {inst} | {engine} | {baseline:.2f}% | {inclusion:.2f}% | {sign}{cents:.2f} |")
        
    print("\n--- 1. Overall Batch Performance ---")
    for eng in ['REAPER', 'pYIN']:
        cnt = overall[eng]['count']
        b_mean = overall[eng]['baseline'] / cnt
        i_mean = overall[eng]['inclusion'] / cnt
        c_mean = overall[eng]['cents'] / cnt
        sign = "+" if c_mean > 0 else ""
        print(f"| {eng} | {cnt} | {b_mean:.2f}% | {i_mean:.2f}% | {sign}{c_mean:.2f} |")
        
    print("\n--- 2. Analysis by Instrument ---")
    for inst in ['Violin', 'Viola', 'Cello']:
        for eng in ['REAPER', 'pYIN']:
            cnt = by_inst[inst][eng]['count']
            b_mean = by_inst[inst][eng]['baseline'] / cnt
            i_mean = by_inst[inst][eng]['inclusion'] / cnt
            c_mean = by_inst[inst][eng]['cents'] / cnt
            sign = "+" if c_mean > 0 else ""
            print(f"| {inst} | {eng} | {b_mean:.2f}% | {i_mean:.2f}% | {sign}{c_mean:.2f} |")

calculate_stats()
