# Gross Error Exclusion Threshold Justification

Generated: 2026-07-22 20:30

## Methodology

The pYIN pitch engine was run through the full production pipeline (extract → intonation filters → DTW alignment → harmonic folding → metrics) on all bowed-string tracks in the URMP dataset using Engine Optimal Default parameters (switch_prob=0.005, rms_threshold=0.005, min_frames=2, max_pitch_slope=0.50). For each detected note, the absolute value of `Deviation_Cents` was collected to characterize the empirical deviation distribution and evaluate the sensitivity of the 100-cent exclusion threshold.

## Detection Summary

- **Total MIDI notes**: 9496
- **Detected**: 8979 (94.6%)
- **Missed (NaN)**: 517 (5.4%)

## Deviation Distribution (Detected Notes)

- **Median $|\text{dev}|$**: 10.00 cents
- **Mean $|\text{dev}|$**: 28.76 cents
- **90th percentile**: 30.00 cents
- **95th percentile**: 50.00 cents
- **99th percentile**: 670.01 cents
- **Maximum**: 1130.00 cents

## Threshold Sensitivity

| Threshold (cents) | Notes Exceeding | % of Detected |
| :---: | :---: | :---: |
| 25 | 1543 | 17.18% |
| 50 | 431 | 4.80% |
| 75 | 369 | 4.11% |
| 100 | 334 | 3.72% |
| 150 | 300 | 3.34% |
| 200 | 245 | 2.73% |

## Histogram of $|\text{Deviation\_Cents}|$

| Bin (cents) | Count | % of Detected |
| :---: | :---: | :---: |
| [0, 5) | 2293 | 25.5% |
| [5, 10) | 2521 | 28.1% |
| [10, 15) | 712 | 7.9% |
| [15, 20) | 1113 | 12.4% |
| [20, 25) | 797 | 8.9% |
| [25, 30) | 603 | 6.7% |
| [30, 40) | 359 | 4.0% |
| [40, 50) | 118 | 1.3% |
| [50, 75) | 94 | 1.0% |
| [75, 100) | 29 | 0.3% |
| [100, 150) | 40 | 0.4% |
| [150, 200) | 46 | 0.5% |
| [200, 500) | 128 | 1.4% |
| [500, 1200) | 126 | 1.4% |

## Notes Exceeding 100 Cents — Per Instrument

| Instrument | Total Detected | Exceeding 100c | % Excluded | With Correction_Applied |
| :--- | :---: | :---: | :---: | :---: |
| Violin | 5108 | 195 | 3.82% | 18 |
| Viola | 1887 | 49 | 2.60% | 5 |
| Cello | 1984 | 90 | 4.54% | 15 |

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
| AuSep_2_vn_19_Pavane | Violin | 211 | 192 | 19 | 3 | 1.6% |
| AuSep_3_vc_19_Pavane | Cello | 244 | 225 | 19 | 8 | 3.6% |
| AuSep_1_vn_24_Pirates | Violin | 135 | 134 | 1 | 0 | 0.0% |
| AuSep_2_vn_24_Pirates | Violin | 87 | 82 | 5 | 0 | 0.0% |
| AuSep_3_va_24_Pirates | Viola | 136 | 131 | 5 | 1 | 0.8% |
| AuSep_4_vc_24_Pirates | Cello | 178 | 159 | 19 | 20 | 12.6% |
| AuSep_1_vn_26_King | Violin | 229 | 221 | 8 | 8 | 3.6% |
| AuSep_2_vn_26_King | Violin | 211 | 204 | 7 | 6 | 2.9% |
| AuSep_3_va_26_King | Viola | 217 | 210 | 7 | 2 | 1.0% |
| AuSep_4_vc_26_King | Cello | 144 | 136 | 8 | 4 | 2.9% |
| AuSep_1_vn_32_Fugue | Violin | 244 | 244 | 0 | 0 | 0.0% |
| AuSep_2_vn_32_Fugue | Violin | 253 | 252 | 1 | 11 | 4.4% |
| AuSep_3_va_32_Fugue | Viola | 214 | 214 | 0 | 4 | 1.9% |
| AuSep_4_vc_32_Fugue | Cello | 187 | 186 | 1 | 3 | 1.6% |
| AuSep_1_vn_36_Rondeau | Violin | 484 | 458 | 26 | 14 | 3.1% |
| AuSep_2_vn_36_Rondeau | Violin | 218 | 199 | 19 | 4 | 2.0% |
| AuSep_3_va_36_Rondeau | Viola | 216 | 208 | 8 | 5 | 2.4% |
| AuSep_4_vc_36_Rondeau | Cello | 162 | 147 | 15 | 4 | 2.7% |
| AuSep_1_vn_38_Jerusalem | Violin | 171 | 167 | 4 | 2 | 1.2% |
| AuSep_2_vn_38_Jerusalem | Violin | 180 | 167 | 13 | 2 | 1.2% |
| AuSep_3_va_38_Jerusalem | Viola | 167 | 158 | 9 | 2 | 1.3% |
| AuSep_4_vc_38_Jerusalem | Cello | 139 | 133 | 6 | 2 | 1.5% |
| AuSep_1_vn_44_K515 | Violin | 622 | 615 | 7 | 22 | 3.6% |
| AuSep_2_vn_44_K515 | Violin | 477 | 448 | 29 | 41 | 9.2% |
| AuSep_3_va_44_K515 | Viola | 477 | 474 | 3 | 12 | 2.5% |
| AuSep_4_va_44_K515 | Viola | 514 | 428 | 86 | 22 | 5.1% |
| AuSep_5_vc_44_K515 | Cello | 360 | 349 | 11 | 16 | 4.6% |
