# Gross Error Exclusion Threshold Justification

Generated: 2026-07-21 12:21

## Methodology

The pYIN pitch engine was run through the full production pipeline (extract → intonation filters → DTW alignment → harmonic folding → metrics) on all bowed-string tracks in the URMP dataset using Engine Optimal Default parameters (switch_prob=0.005, rms_threshold=0.005, min_frames=2, max_pitch_slope=0.50). For each detected note, the absolute value of `Deviation_Cents` was collected to characterize the empirical deviation distribution and evaluate the sensitivity of the 100-cent exclusion threshold.

## Detection Summary

- **Total MIDI notes**: 12975
- **Detected**: 12277 (94.6%)
- **Missed (NaN)**: 698 (5.4%)

## Deviation Distribution (Detected Notes)

- **Median $|\text{dev}|$**: 10.00 cents
- **Mean $|\text{dev}|$**: 26.61 cents
- **90th percentile**: 30.00 cents
- **95th percentile**: 40.00 cents
- **99th percentile**: 600.00 cents
- **Maximum**: 1130.00 cents

## Threshold Sensitivity

| Threshold (cents) | Notes Exceeding | % of Detected |
| :---: | :---: | :---: |
| 25 | 1960 | 15.96% |
| 50 | 525 | 4.28% |
| 75 | 453 | 3.69% |
| 100 | 403 | 3.28% |
| 150 | 360 | 2.93% |
| 200 | 296 | 2.41% |

## Histogram of $|\text{Deviation\_Cents}|$

| Bin (cents) | Count | % of Detected |
| :---: | :---: | :---: |
| [0, 5) | 3188 | 26.0% |
| [5, 10) | 3450 | 28.1% |
| [10, 15) | 1046 | 8.5% |
| [15, 20) | 1491 | 12.1% |
| [20, 25) | 1142 | 9.3% |
| [25, 30) | 766 | 6.2% |
| [30, 40) | 480 | 3.9% |
| [40, 50) | 148 | 1.2% |
| [50, 75) | 113 | 0.9% |
| [75, 100) | 43 | 0.4% |
| [100, 150) | 50 | 0.4% |
| [150, 200) | 54 | 0.4% |
| [200, 500) | 156 | 1.3% |
| [500, 1200) | 150 | 1.2% |

## Notes Exceeding 100 Cents — Per Instrument

| Instrument | Total Detected | Exceeding 100c | % Excluded | With Correction_Applied |
| :--- | :---: | :---: | :---: | :---: |
| Violin | 7266 | 241 | 3.32% | 27 |
| Viola | 2802 | 64 | 2.28% | 6 |
| Cello | 2209 | 98 | 4.44% | 16 |

## Per-Track Breakdown

| Track | Instrument | MIDI Notes | Detected | Missed | >100c | % >100c |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| AuSep_1_vn_01_Jupiter | Violin | 92 | 89 | 3 | 8 | 9.0% |
| AuSep_2_vc_01_Jupiter | Cello | 54 | 53 | 1 | 2 | 3.8% |
| AuSep_1_vn_02_Sonata | Violin | 82 | 77 | 5 | 10 | 13.0% |
| AuSep_2_vn_02_Sonata | Violin | 50 | 47 | 3 | 7 | 14.9% |
| AuSep_2_vn_08_Spring | Violin | 94 | 93 | 1 | 0 | 0.0% |
| AuSep_2_vn_09_Jesus | Violin | 486 | 406 | 80 | 41 | 10.1% |
| AuSep_2_vc_11_Maria | Cello | 362 | 331 | 31 | 19 | 5.7% |
| AuSep_1_vn_12_Spring | Violin | 432 | 401 | 31 | 6 | 1.5% |
| AuSep_2_vn_12_Spring | Violin | 338 | 334 | 4 | 3 | 0.9% |
| AuSep_3_vc_12_Spring | Cello | 270 | 265 | 5 | 12 | 4.5% |
| AuSep_1_vn_13_Hark | Violin | 76 | 72 | 4 | 3 | 4.2% |
| AuSep_2_vn_13_Hark | Violin | 73 | 71 | 2 | 1 | 1.4% |
| AuSep_3_va_13_Hark | Viola | 71 | 64 | 7 | 1 | 1.6% |
| AuSep_1_vn_17_Nocturne | Violin | 139 | 135 | 4 | 3 | 2.2% |
| AuSep_1_vn_18_Nocturne | Violin | 139 | 135 | 4 | 3 | 2.2% |
| AuSep_2_vn_19_Pavane | Violin | 211 | 192 | 19 | 3 | 1.6% |
| AuSep_3_vc_19_Pavane | Cello | 244 | 225 | 19 | 8 | 3.6% |
| AuSep_2_vn_20_Pavane | Violin | 211 | 192 | 19 | 3 | 1.6% |
| AuSep_3_vc_20_Pavane | Cello | 244 | 225 | 19 | 8 | 3.6% |
| AuSep_1_vn_24_Pirates | Violin | 135 | 134 | 1 | 0 | 0.0% |
| AuSep_2_vn_24_Pirates | Violin | 87 | 82 | 5 | 0 | 0.0% |
| AuSep_3_va_24_Pirates | Viola | 136 | 131 | 5 | 1 | 0.8% |
| AuSep_4_vc_24_Pirates | Cello | 178 | 159 | 19 | 20 | 12.6% |
| AuSep_1_vn_25_Pirates | Violin | 135 | 134 | 1 | 0 | 0.0% |
| AuSep_2_vn_25_Pirates | Violin | 87 | 82 | 5 | 0 | 0.0% |
| AuSep_3_va_25_Pirates | Viola | 136 | 131 | 5 | 1 | 0.8% |
| AuSep_1_vn_26_King | Violin | 229 | 221 | 8 | 8 | 3.6% |
| AuSep_2_vn_26_King | Violin | 211 | 204 | 7 | 6 | 2.9% |
| AuSep_3_va_26_King | Viola | 217 | 210 | 7 | 2 | 1.0% |
| AuSep_4_vc_26_King | Cello | 144 | 136 | 8 | 4 | 2.9% |
| AuSep_1_vn_27_King | Violin | 229 | 221 | 8 | 8 | 3.6% |
| AuSep_2_vn_27_King | Violin | 211 | 204 | 7 | 6 | 2.9% |
| AuSep_3_va_27_King | Viola | 217 | 210 | 7 | 2 | 1.0% |
| AuSep_1_vn_32_Fugue | Violin | 244 | 244 | 0 | 0 | 0.0% |
| AuSep_2_vn_32_Fugue | Violin | 253 | 252 | 1 | 11 | 4.4% |
| AuSep_3_va_32_Fugue | Viola | 214 | 214 | 0 | 4 | 1.9% |
| AuSep_4_vc_32_Fugue | Cello | 187 | 186 | 1 | 3 | 1.6% |
| AuSep_1_vn_35_Rondeau | Violin | 484 | 458 | 26 | 14 | 3.1% |
| AuSep_2_vn_35_Rondeau | Violin | 218 | 199 | 19 | 4 | 2.0% |
| AuSep_3_va_35_Rondeau | Viola | 216 | 208 | 8 | 5 | 2.4% |
| AuSep_1_vn_36_Rondeau | Violin | 484 | 458 | 26 | 14 | 3.1% |
| AuSep_2_vn_36_Rondeau | Violin | 218 | 199 | 19 | 4 | 2.0% |
| AuSep_3_va_36_Rondeau | Viola | 216 | 208 | 8 | 5 | 2.4% |
| AuSep_4_vc_36_Rondeau | Cello | 162 | 147 | 15 | 4 | 2.7% |
| AuSep_2_vn_37_Rondeau | Violin | 218 | 199 | 19 | 4 | 2.0% |
| AuSep_3_va_37_Rondeau | Viola | 216 | 208 | 8 | 5 | 2.4% |
| AuSep_1_vn_38_Jerusalem | Violin | 171 | 167 | 4 | 2 | 1.2% |
| AuSep_2_vn_38_Jerusalem | Violin | 180 | 167 | 13 | 2 | 1.2% |
| AuSep_3_va_38_Jerusalem | Viola | 167 | 158 | 9 | 2 | 1.3% |
| AuSep_4_vc_38_Jerusalem | Cello | 139 | 133 | 6 | 2 | 1.5% |
| AuSep_1_vn_39_Jerusalem | Violin | 171 | 167 | 4 | 2 | 1.2% |
| AuSep_2_vn_39_Jerusalem | Violin | 180 | 167 | 13 | 2 | 1.2% |
| AuSep_3_va_39_Jerusalem | Viola | 167 | 158 | 9 | 2 | 1.3% |
| AuSep_1_vn_44_K515 | Violin | 622 | 615 | 7 | 22 | 3.6% |
| AuSep_2_vn_44_K515 | Violin | 477 | 448 | 29 | 41 | 9.2% |
| AuSep_3_va_44_K515 | Viola | 477 | 474 | 3 | 12 | 2.5% |
| AuSep_4_va_44_K515 | Viola | 514 | 428 | 86 | 22 | 5.1% |
| AuSep_5_vc_44_K515 | Cello | 360 | 349 | 11 | 16 | 4.6% |
