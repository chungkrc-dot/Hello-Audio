import csv

lines = []
with open('tests/batch_results/appendix_a_results.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        lines.append(row)

# Overall Performance
reaper_det = sum(float(r['Det_Yield_REAPER']) for r in lines) / len(lines)
reaper_inc = sum(float(r['Inc_Yield_REAPER']) for r in lines) / len(lines)
reaper_dev = sum(float(r['Dev_Hz_REAPER']) for r in lines) / len(lines)
pyin_det = sum(float(r['Det_Yield_pYIN']) for r in lines) / len(lines)
pyin_inc = sum(float(r['Inc_Yield_pYIN']) for r in lines) / len(lines)
pyin_dev = sum(float(r['Dev_Hz_pYIN']) for r in lines) / len(lines)

with open('appendix_a_draft.md', 'w') as out:
    out.write("### 1. Overall Batch Performance\n")
    out.write("| Engine | Detected Yield (%) | Included Yield (%) | Mean Deviation (Hz) |\n")
    out.write("| :--- | :---: | :---: | :---: |\n")
    out.write(f"| **REAPER** | {reaper_det:.2f}% | {reaper_inc:.2f}% | {reaper_dev:+.2f} Hz |\n")
    out.write(f"| **pYIN** | {pyin_det:.2f}% | {pyin_inc:.2f}% | {pyin_dev:+.2f} Hz |\n\n")

    out.write("### 2. Analysis by Instrument\n")
    out.write("| Instrument | REAPER Det. (%) | REAPER Inc. (%) | REAPER Dev (Hz) | pYIN Det. (%) | pYIN Inc. (%) | pYIN Dev (Hz) |\n")
    out.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n")
    instruments = sorted(list(set(r['Instrument'] for r in lines)))
    for inst in instruments:
        inst_lines = [r for r in lines if r['Instrument'] == inst]
        r_d = sum(float(r['Det_Yield_REAPER']) for r in inst_lines) / len(inst_lines)
        r_i = sum(float(r['Inc_Yield_REAPER']) for r in inst_lines) / len(inst_lines)
        r_v = sum(float(r['Dev_Hz_REAPER']) for r in inst_lines) / len(inst_lines)
        p_d = sum(float(r['Det_Yield_pYIN']) for r in inst_lines) / len(inst_lines)
        p_i = sum(float(r['Inc_Yield_pYIN']) for r in inst_lines) / len(inst_lines)
        p_v = sum(float(r['Dev_Hz_pYIN']) for r in inst_lines) / len(inst_lines)
        out.write(f"| **{inst}** | {r_d:.2f}% | {r_i:.2f}% | {r_v:+.2f} | {p_d:.2f}% | {p_i:.2f}% | {p_v:+.2f} |\n")
    out.write("\n")

    out.write("### 3. Detailed Track Results\n\n")
    out.write("#### REAPER Engine Results\n")
    out.write("| Dataset Piece | Part | Instrument | Det. Yield (%) | Inc. Yield (%) | Mean Dev. (Hz) |\n")
    out.write("| :--- | :--- | :--- | :---: | :---: | :---: |\n")
    for r in lines:
        piece = r['Filename']
        out.write(f"| {piece} | {r['Piece']} | {r['Instrument']} | {float(r['Det_Yield_REAPER']):.2f}% | {float(r['Inc_Yield_REAPER']):.2f}% | {float(r['Dev_Hz_REAPER']):+.2f} |\n")
    out.write("\n")

    out.write("#### pYIN Engine Results\n")
    out.write("| Dataset Piece | Part | Instrument | Det. Yield (%) | Inc. Yield (%) | Mean Dev. (Hz) |\n")
    out.write("| :--- | :--- | :--- | :---: | :---: | :---: |\n")
    for r in lines:
        piece = r['Filename']
        out.write(f"| {piece} | {r['Piece']} | {r['Instrument']} | {float(r['Det_Yield_pYIN']):.2f}% | {float(r['Inc_Yield_pYIN']):.2f}% | {float(r['Dev_Hz_pYIN']):+.2f} |\n")
    
