import pandas as pd
import os
import re

ARTIFACTS_DIR = "/Users/conradchung/.gemini/antigravity/brain/144bb055-59e2-4a86-9b79-cd054e17846b"
reaper_csv = os.path.join(ARTIFACTS_DIR, "all_strings_reaper_batch_results.csv")
pyin_csv = os.path.join(ARTIFACTS_DIR, "all_strings_pyin_batch_results.csv")

df_reaper = pd.read_csv(reaper_csv)
df_pyin = pd.read_csv(pyin_csv)

# Filter out Double Bass again just in case
df_pyin = df_pyin[df_pyin['Instrument'] != 'Double Bass'].copy()
df_reaper = df_reaper[df_reaper['Instrument'] != 'Double Bass'].copy()

def standardize_track(row):
    part_num = re.search(r'^(\d+)_', row['Track']).group(1)
    if row['Instrument'] == 'Violin':
        return f"{part_num}_vn"
    elif row['Instrument'] == 'Viola':
        return f"{part_num}_va"
    elif row['Instrument'] == 'Cello':
        return f"{part_num}_vc"
    return row['Track']

# Fix pYIN Track naming to match REAPER format
df_pyin['Track'] = df_pyin.apply(standardize_track, axis=1)

df_pyin['UID'] = df_pyin['Dataset'] + "_" + df_pyin['Track']
df_reaper['UID'] = df_reaper['Dataset'] + "_" + df_reaper['Track']

# To remove duplicates cleanly, keep the row with the largest total_expected (which is the full unshortened track)
df_pyin_clean = df_pyin.sort_values('total_expected', ascending=False).drop_duplicates('UID').sort_index()
df_reaper_clean = df_reaper.sort_values('total_expected', ascending=False).drop_duplicates('UID').sort_index()

pyin_uids = set(df_pyin_clean['UID'])
reaper_uids = set(df_reaper_clean['UID'])

print("\nTracks in pYIN but not REAPER:", pyin_uids - reaper_uids)
print("Tracks in REAPER but not pYIN:", reaper_uids - pyin_uids)

# Keep only intersection
intersection = pyin_uids.intersection(reaper_uids)
df_pyin_clean = df_pyin_clean[df_pyin_clean['UID'].isin(intersection)]
df_reaper_clean = df_reaper_clean[df_reaper_clean['UID'].isin(intersection)]

# Drop UID column before saving
df_pyin_clean = df_pyin_clean.drop(columns=['UID']).sort_values(['Dataset', 'Track'])
df_reaper_clean = df_reaper_clean.drop(columns=['UID']).sort_values(['Dataset', 'Track'])

print(f"\nFinal pYIN track count: {len(df_pyin_clean)}")
print(f"Final REAPER track count: {len(df_reaper_clean)}")

df_pyin_clean.to_csv(pyin_csv, index=False)
df_reaper_clean.to_csv(reaper_csv, index=False)

print("\nCSVs cleaned, perfectly synced, and overwritten successfully.")
