import os
import pandas as pd
import re

ARTIFACTS_DIR = "/Users/conradchung/.gemini/antigravity/brain/144bb055-59e2-4a86-9b79-cd054e17846b"
appendix_path = os.path.join(ARTIFACTS_DIR, "scratch", "appendix.md")

with open(appendix_path, "r") as f:
    lines = f.readlines()

reaper_data = []
pyin_data = []
current_engine = None

for line in lines:
    line = line.strip()
    if line.startswith("#### REAPER Engine Results"):
        current_engine = "REAPER"
        continue
    elif line.startswith("#### pYIN Engine Results"):
        current_engine = "pYIN"
        continue
    
    if current_engine and line.startswith("|") and not "Yield (%)" in line and not ":---" in line:
        parts = [p.strip() for p in line.split("|")][1:-1]
        if len(parts) == 7:
            ds = parts[0]
            part = parts[1]
            inst = parts[2]
            det = int(parts[3])
            exp = int(parts[4])
            yield_pct_str = parts[5].replace("%", "")
            try:
                yield_pct = float(yield_pct_str)
                mean_dev = float(parts[6])
            except ValueError:
                continue
                
            row = {
                'Dataset': ds,
                'Track': part,
                'Instrument': inst,
                'detected_count': det,
                'total_expected': exp,
                'yield_pct': yield_pct,
                'mean_dev_hz': mean_dev
            }
            if current_engine == "REAPER":
                reaper_data.append(row)
            else:
                pyin_data.append(row)

df_reaper = pd.DataFrame(reaper_data)
df_pyin = pd.DataFrame(pyin_data)

df_reaper.to_csv(os.path.join(ARTIFACTS_DIR, "all_strings_reaper_batch_results.csv"), index=False)
df_pyin.to_csv(os.path.join(ARTIFACTS_DIR, "all_strings_pyin_batch_results.csv"), index=False)

print(f"Reconstructed REAPER rows: {len(df_reaper)}")
print(f"Reconstructed pYIN rows: {len(df_pyin)}")
