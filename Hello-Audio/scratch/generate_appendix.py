import os
import pandas as pd

ARTIFACTS_DIR = "/Users/conradchung/.gemini/antigravity/brain/144bb055-59e2-4a86-9b79-cd054e17846b"
reaper_csv = os.path.join(ARTIFACTS_DIR, "all_strings_reaper_batch_results.csv")
pyin_csv = os.path.join(ARTIFACTS_DIR, "all_strings_pyin_batch_results.csv")

df_reaper = pd.read_csv(reaper_csv)
df_pyin = pd.read_csv(pyin_csv)
df_pyin = df_pyin[df_pyin['Instrument'] != 'Double Bass']

def calc_stats(df):
    overall_yield = (df['detected_count'].sum() / df['total_expected'].sum()) * 100
    overall_dev = df['mean_dev_hz'].mean()
    
    inst_stats = []
    for inst in ['Violin', 'Viola', 'Cello']:
        inst_df = df[df['Instrument'] == inst]
        y = (inst_df['detected_count'].sum() / inst_df['total_expected'].sum()) * 100
        d = inst_df['mean_dev_hz'].mean()
        inst_stats.append((inst, y, d))
    return overall_yield, overall_dev, inst_stats

ry, rd, r_inst = calc_stats(df_reaper)
py, pd_dev, p_inst = calc_stats(df_pyin)

md = []
md.append("## Appendix A: Exploratory Batch Test Results (REAPER vs. pYIN)")
md.append("\nThis appendix documents the exhaustive batch test results across the URMP string ensemble dataset for both the REAPER and pYIN pitch tracking engines. This side-by-side comparison serves as the empirical evidence for transitioning the primary string extraction architecture to REAPER.")
md.append("\n### Testing Methodology")
md.append("The evaluation was conducted on 34 isolated monophonic string tracks from the URMP dataset. Both engines were evaluated using the same temporal warping mask (DTW) to align the acoustic output to the MIDI ground truth. The algorithms were run with their experimentally derived optimal parameters.")
md.append("\n**Optimal Parameters (pYIN):**")
md.append("- `frame_length`: 2048")
md.append("- `hop_length`: 512")
md.append("- `switch_prob`: 0.005")
md.append("- `rms_threshold`: 0.005")
md.append("- `max_pitch_slope`: 0.50")
md.append("- `min_frames`: 2")
md.append("- `enable_freq_limits`: True")
md.append("- `harmonic_folding`: True")
md.append("\n**Optimal Parameters (REAPER):**")
md.append("- `frame_period`: ~11.6ms (512 samples at 44.1kHz)")
md.append("- `rms_threshold`: 0.005")
md.append("- `max_pitch_slope`: 0.50")
md.append("- `min_frames`: 4")
md.append("- `enable_freq_limits`: True")
md.append("- `harmonic_folding`: True")

md.append("\n### 1. Overall Batch Performance")
md.append("| Engine | Detection Yield | Mean Deviation (Hz) |")
md.append("| :--- | :---: | :---: |")
md.append(f"| **REAPER** | {ry:.2f}% | {rd:+.2f} Hz |")
md.append(f"| **pYIN** | {py:.2f}% | {pd_dev:+.2f} Hz |")

md.append("\n### 2. Analysis by Instrument")
md.append("| Instrument | REAPER Yield | REAPER Dev (Hz) | pYIN Yield | pYIN Dev (Hz) |")
md.append("| :--- | :---: | :---: | :---: | :---: |")
for i in range(3):
    md.append(f"| **{r_inst[i][0]}** | {r_inst[i][1]:.2f}% | {r_inst[i][2]:+.2f} | {p_inst[i][1]:.2f}% | {p_inst[i][2]:+.2f} |")

md.append("\n### 3. Detailed Track Results")
md.append("The following table provides the exhaustive breakdown of the detection yield and intonation deviation for each individual audio track analyzed in the batch test.")

md.append("\n#### REAPER Engine Results")
md.append("| Dataset Piece | Part | Instrument | Notes Detected | Notes Expected | Yield (%) | Mean Deviation (Hz) |")
md.append("| :--- | :--- | :--- | :---: | :---: | :---: | :---: |")
for _, row in df_reaper.iterrows():
    md.append(f"| {row['Dataset']} | {row['Track']} | {row['Instrument']} | {row['detected_count']} | {row['total_expected']} | {row['yield_pct']:.2f}% | {row['mean_dev_hz']:.2f} |")

md.append("\n#### pYIN Engine Results")
md.append("| Dataset Piece | Part | Instrument | Notes Detected | Notes Expected | Yield (%) | Mean Deviation (Hz) |")
md.append("| :--- | :--- | :--- | :---: | :---: | :---: | :---: |")
for _, row in df_pyin.iterrows():
    md.append(f"| {row['Dataset']} | {row['Track']} | {row['Instrument']} | {row['detected_count']} | {row['total_expected']} | {row['yield_pct']:.2f}% | {row['mean_dev_hz']:.2f} |")

md.append("")

with open(os.path.join(ARTIFACTS_DIR, "scratch", "appendix.md"), "w") as f:
    f.write("\n".join(md))

print("Done")
