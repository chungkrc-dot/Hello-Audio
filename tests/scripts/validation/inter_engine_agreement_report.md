# Inter-Engine Agreement on Real Audio (URMP)

Generated: 2026-07-22 21:10

## Methodology

Both pYIN and REAPER ran the full production pipeline (extract → intonation filters → DTW alignment → harmonic folding → metrics) on every bowed-string track in the URMP dataset. Engine Optimal Default parameters were used for both engines (switch_prob=0.005, rms_threshold=0.005, min_frames=2/4, max_pitch_slope=0.50). Per-note `Deviation_Cents` results were paired by `Note_Index`; notes excluded by `is_note_excluded()` (|dev| > 100 cents or harmonic folding correction applied) or missed by either engine were dropped.

## Aggregate Results

- **Paired notes**: 6639
- **Pearson $r$**: 0.7256 ($p = 0.00e+00$)
- **Mean Absolute Difference (MAD)**: 10.35 cents
- **Bland-Altman bias** (pYIN − REAPER): -0.18 cents
- **95% Limits of Agreement**: [-25.78, +25.41] cents
- **SD of differences**: 13.06 cents

## Per-Track Breakdown

| Track | Instrument | MIDI Notes | Paired | Pearson r | MAD (c) | pYIN Yield | REAPER Yield |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| AuSep_1_vn_01_Jupiter | Violin | 92 | 62 | 0.2175 | 16.27 | 96.7% | 92.4% |
| AuSep_2_vc_01_Jupiter | Cello | 54 | 47 | 0.8372 | 5.46 | 98.1% | 98.1% |
| AuSep_1_vn_02_Sonata | Violin | 82 | 61 | 0.6805 | 17.91 | 93.9% | 91.5% |
| AuSep_2_vn_02_Sonata | Violin | 50 | 40 | 0.3254 | 11.21 | 94.0% | 94.0% |
| AuSep_2_vn_08_Spring | Violin | 94 | 83 | 0.7826 | 14.60 | 98.9% | 91.5% |
| AuSep_2_vn_09_Jesus | Violin | 486 | 324 | 0.6007 | 16.38 | 83.5% | 78.8% |
| AuSep_2_vc_11_Maria | Cello | 362 | 194 | 0.8543 | 7.02 | 91.4% | 91.7% |
| AuSep_1_vn_12_Spring | Violin | 432 | 128 | 0.5135 | 15.98 | 92.8% | 47.2% |
| AuSep_2_vn_12_Spring | Violin | 338 | 204 | 0.5118 | 15.47 | 98.8% | 78.1% |
| AuSep_3_vc_12_Spring | Cello | 270 | 225 | 0.7164 | 6.85 | 98.1% | 94.1% |
| AuSep_1_vn_13_Hark | Violin | 76 | 68 | 0.7211 | 16.96 | 94.7% | 94.7% |
| AuSep_2_vn_13_Hark | Violin | 73 | 68 | 0.6514 | 12.86 | 97.3% | 97.3% |
| AuSep_3_va_13_Hark | Viola | 71 | 58 | 0.7173 | 8.87 | 90.1% | 90.1% |
| AuSep_1_vn_17_Nocturne | Violin | 139 | 109 | 0.4353 | 11.15 | 97.1% | 95.0% |
| AuSep_2_vn_19_Pavane | Violin | 211 | 67 | 0.4538 | 12.89 | 91.0% | 61.1% |
| AuSep_3_vc_19_Pavane | Cello | 244 | 179 | 0.7509 | 7.01 | 92.2% | 91.0% |
| AuSep_1_vn_24_Pirates | Violin | 135 | 115 | 0.4927 | 13.17 | 99.3% | 91.1% |
| AuSep_2_vn_24_Pirates | Violin | 87 | 68 | 0.4988 | 10.69 | 94.3% | 90.8% |
| AuSep_3_va_24_Pirates | Viola | 136 | 116 | 0.6449 | 10.43 | 96.3% | 95.6% |
| AuSep_4_vc_24_Pirates | Cello | 178 | 117 | 0.8938 | 5.26 | 89.3% | 80.9% |
| AuSep_1_vn_26_King | Violin | 229 | 152 | 0.8035 | 9.47 | 96.5% | 84.3% |
| AuSep_2_vn_26_King | Violin | 211 | 191 | 0.6313 | 11.40 | 96.7% | 96.2% |
| AuSep_3_va_26_King | Viola | 217 | 191 | 0.8141 | 8.37 | 96.8% | 96.3% |
| AuSep_4_vc_26_King | Cello | 144 | 113 | 0.7139 | 5.89 | 94.4% | 95.1% |
| AuSep_1_vn_32_Fugue | Violin | 244 | 203 | 0.5944 | 12.23 | 100.0% | 95.9% |
| AuSep_2_vn_32_Fugue | Violin | 253 | 231 | 0.6742 | 9.81 | 99.6% | 99.6% |
| AuSep_3_va_32_Fugue | Viola | 214 | 162 | 0.8380 | 7.38 | 100.0% | 99.5% |
| AuSep_4_vc_32_Fugue | Cello | 187 | 169 | 0.8278 | 5.86 | 99.5% | 100.0% |
| AuSep_1_vn_36_Rondeau | Violin | 484 | 298 | 0.5140 | 12.44 | 94.6% | 75.0% |
| AuSep_2_vn_36_Rondeau | Violin | 218 | 185 | 0.4874 | 9.74 | 91.3% | 89.0% |
| AuSep_3_va_36_Rondeau | Viola | 216 | 183 | 0.7451 | 8.95 | 96.3% | 95.8% |
| AuSep_4_vc_36_Rondeau | Cello | 162 | 122 | 0.8657 | 5.08 | 90.7% | 88.9% |
| AuSep_1_vn_38_Jerusalem | Violin | 171 | 155 | 0.5949 | 11.14 | 97.7% | 94.2% |
| AuSep_2_vn_38_Jerusalem | Violin | 180 | 158 | 0.6089 | 10.75 | 92.8% | 92.8% |
| AuSep_3_va_38_Jerusalem | Viola | 167 | 129 | 0.8105 | 7.91 | 94.6% | 92.8% |
| AuSep_4_vc_38_Jerusalem | Cello | 139 | 120 | 0.8907 | 5.65 | 95.7% | 95.0% |
| AuSep_1_vn_44_K515 | Violin | 622 | 337 | 0.6438 | 12.56 | 98.9% | 70.7% |
| AuSep_2_vn_44_K515 | Violin | 477 | 304 | 0.6367 | 12.95 | 93.9% | 90.1% |
| AuSep_3_va_44_K515 | Viola | 477 | 386 | 0.7890 | 9.31 | 99.4% | 95.4% |
| AuSep_4_va_44_K515 | Viola | 514 | 258 | 0.7013 | 9.36 | 83.3% | 78.0% |
| AuSep_5_vc_44_K515 | Cello | 360 | 259 | 0.8498 | 5.65 | 96.9% | 95.6% |

## Per-Instrument Summary

| Instrument | Tracks | Paired Notes | Median r | Mean MAD (c) | Mean pYIN Yield | Mean REAPER Yield |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Violin | 23 | 3611 | 0.5949 | 12.96 | 95.4% | 86.6% |
| Viola | 8 | 1483 | 0.7671 | 8.82 | 94.6% | 93.0% |
| Cello | 10 | 1545 | 0.8435 | 5.97 | 94.7% | 93.0% |
