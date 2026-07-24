# Appendix A tables (generated)

Source: `tests/outputs/batch_results/appendix_a_results.csv` — 41 stems 10 cello, 8 viola, 23 violin.

## 1. Overall Batch Performance

| Engine | Detected Yield (%) | Included Yield (%) | Mean Deviation (Hz) |
| :--- | :---: | :---: | :---: |
| **REAPER** | 89.40% | 77.30% | +1.49 Hz |
| **pYIN** | 95.06% | 87.85% | +1.47 Hz |

## 2. Analysis by Instrument

| Instrument | REAPER Det. (%) | REAPER Inc. (%) | REAPER Dev (Hz) | pYIN Det. (%) | pYIN Inc. (%) | pYIN Dev (Hz) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Cello** | 93.04% | 79.82% | +0.44 | 94.66% | 86.24% | +0.65 |
| **Viola** | 92.95% | 83.46% | +0.40 | 94.60% | 82.97% | +0.48 |
| **Violin** | 86.58% | 74.07% | +2.33 | 95.41% | 90.25% | +2.17 |

## 2b. Engine comparison by cell

| Instrument | Metric | REAPER | pYIN | Leader | Margin (pp) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| Cello | Detected | 93.04% | 94.66% | **pYIN** | 1.62 |
| Cello | Included | 79.82% | 86.24% | **pYIN** | 6.43 |
| Viola | Detected | 92.95% | 94.60% | **pYIN** | 1.64 |
| Viola | Included | 83.46% | 82.97% | **REAPER** | 0.48 |
| Violin | Detected | 86.58% | 95.41% | **pYIN** | 8.83 |
| Violin | Included | 74.07% | 90.25% | **pYIN** | 16.18 |

**Verdict:** pYIN leads REAPER on every instrument class and metric except viola included yield, where REAPER leads by 0.48 pp.

## 3a. Problem tracks

7 tracks show REAPER detection yields below 80%.

| Track | Inst. | REAPER Det | REAPER Inc | pYIN Det | pYIN Inc |
| :--- | :--- | :---: | :---: | :---: | :---: |
| AuSep_1_vn_12_Spring | Violin | 47.22% | 29.86% | 92.82% | 91.44% |
| AuSep_1_vn_36_Rondeau | Violin | 75.00% | 61.57% | 94.63% | 91.32% |
| AuSep_1_vn_44_K515 | Violin | 70.74% | 54.50% | 98.87% | 94.37% |
| AuSep_2_vn_09_Jesus | Violin | 78.81% | 67.08% | 83.54% | 74.28% |
| AuSep_2_vn_12_Spring | Violin | 78.11% | 60.36% | 98.82% | 97.93% |
| AuSep_2_vn_19_Pavane | Violin | 61.14% | 31.75% | 91.00% | 89.10% |
| AuSep_4_va_44_K515 | Viola | 78.02% | 64.01% | 83.27% | 56.61% |

## 3b. Low-yield advisory floors

| Engine | Worst detected yield | Track |
| :--- | :---: | :--- |
| pYIN | 83.27% | `AuSep_4_va_44_K515` |
| REAPER | 47.22% | `AuSep_1_vn_12_Spring` |

## 4. REAPER Engine Results

| Dataset Piece | Part | Instrument | Det. Yield (%) | Inc. Yield (%) | Mean Dev. (Hz) |
| :--- | :--- | :--- | :---: | :---: | :---: |
| AuSep_1_vn_01_Jupiter | 1_vn | Violin | 92.39% | 67.39% | +4.67 |
| AuSep_1_vn_02_Sonata | 1_vn | Violin | 91.46% | 74.39% | -3.31 |
| AuSep_1_vn_12_Spring | 1_vn | Violin | 47.22% | 29.86% | +8.68 |
| AuSep_1_vn_13_Hark | 1_vn | Violin | 94.74% | 89.47% | +0.58 |
| AuSep_1_vn_17_Nocturne | 1_vn | Violin | 94.96% | 78.42% | +5.63 |
| AuSep_1_vn_24_Pirates | 1_vn | Violin | 91.11% | 85.19% | -0.18 |
| AuSep_1_vn_26_King | 1_vn | Violin | 84.28% | 67.69% | +0.46 |
| AuSep_1_vn_32_Fugue | 1_vn | Violin | 95.90% | 83.20% | +3.45 |
| AuSep_1_vn_36_Rondeau | 1_vn | Violin | 75.00% | 61.57% | +3.76 |
| AuSep_1_vn_38_Jerusalem | 1_vn | Violin | 94.15% | 90.64% | +4.57 |
| AuSep_1_vn_44_K515 | 1_vn | Violin | 70.74% | 54.50% | +3.78 |
| AuSep_2_vc_01_Jupiter | 2_vc | Cello | 98.15% | 87.04% | +0.64 |
| AuSep_2_vc_11_Maria | 2_vc | Cello | 91.71% | 56.63% | +0.41 |
| AuSep_2_vn_02_Sonata | 2_vn | Violin | 94.00% | 80.00% | +3.81 |
| AuSep_2_vn_08_Spring | 2_vn | Violin | 91.49% | 89.36% | -0.88 |
| AuSep_2_vn_09_Jesus | 2_vn | Violin | 78.81% | 67.08% | +0.75 |
| AuSep_2_vn_12_Spring | 2_vn | Violin | 78.11% | 60.36% | -0.54 |
| AuSep_2_vn_13_Hark | 2_vn | Violin | 97.26% | 93.15% | -0.14 |
| AuSep_2_vn_19_Pavane | 2_vn | Violin | 61.14% | 31.75% | +4.77 |
| AuSep_2_vn_24_Pirates | 2_vn | Violin | 90.80% | 78.16% | +4.41 |
| AuSep_2_vn_26_King | 2_vn | Violin | 96.21% | 90.52% | -2.67 |
| AuSep_2_vn_32_Fugue | 2_vn | Violin | 99.60% | 91.70% | +3.53 |
| AuSep_2_vn_36_Rondeau | 2_vn | Violin | 88.99% | 84.86% | +5.35 |
| AuSep_2_vn_38_Jerusalem | 2_vn | Violin | 92.78% | 88.33% | +1.44 |
| AuSep_2_vn_44_K515 | 2_vn | Violin | 90.15% | 66.04% | +1.61 |
| AuSep_3_va_13_Hark | 3_va | Viola | 90.14% | 85.92% | -0.87 |
| AuSep_3_va_24_Pirates | 3_va | Viola | 95.59% | 90.44% | -1.22 |
| AuSep_3_va_26_King | 3_va | Viola | 96.31% | 91.71% | -1.25 |
| AuSep_3_va_32_Fugue | 3_va | Viola | 99.53% | 83.64% | +2.26 |
| AuSep_3_va_36_Rondeau | 3_va | Viola | 95.83% | 87.50% | +1.17 |
| AuSep_3_va_38_Jerusalem | 3_va | Viola | 92.81% | 82.04% | +1.17 |
| AuSep_3_va_44_K515 | 3_va | Viola | 95.39% | 82.39% | +0.31 |
| AuSep_3_vc_12_Spring | 3_vc | Cello | 94.07% | 84.44% | +1.17 |
| AuSep_3_vc_19_Pavane | 3_vc | Cello | 90.98% | 78.28% | +0.13 |
| AuSep_4_va_44_K515 | 4_va | Viola | 78.02% | 64.01% | +1.66 |
| AuSep_4_vc_24_Pirates | 4_vc | Cello | 80.90% | 73.03% | -0.23 |
| AuSep_4_vc_26_King | 4_vc | Cello | 95.14% | 83.33% | -0.19 |
| AuSep_4_vc_32_Fugue | 4_vc | Cello | 100.00% | 92.51% | +0.65 |
| AuSep_4_vc_36_Rondeau | 4_vc | Cello | 88.89% | 79.63% | +0.88 |
| AuSep_4_vc_38_Jerusalem | 4_vc | Cello | 94.96% | 86.33% | +0.58 |
| AuSep_5_vc_44_K515 | 5_vc | Cello | 95.56% | 76.94% | +0.36 |

## 5. pYIN Engine Results

| Dataset Piece | Part | Instrument | Det. Yield (%) | Inc. Yield (%) | Mean Dev. (Hz) |
| :--- | :--- | :--- | :---: | :---: | :---: |
| AuSep_1_vn_01_Jupiter | 1_vn | Violin | 96.74% | 86.96% | +3.16 |
| AuSep_1_vn_02_Sonata | 1_vn | Violin | 93.90% | 81.71% | -1.71 |
| AuSep_1_vn_12_Spring | 1_vn | Violin | 92.82% | 91.44% | +8.83 |
| AuSep_1_vn_13_Hark | 1_vn | Violin | 94.74% | 89.47% | -0.10 |
| AuSep_1_vn_17_Nocturne | 1_vn | Violin | 97.12% | 94.24% | +5.52 |
| AuSep_1_vn_24_Pirates | 1_vn | Violin | 99.26% | 98.52% | -0.89 |
| AuSep_1_vn_26_King | 1_vn | Violin | 96.51% | 90.39% | -0.99 |
| AuSep_1_vn_32_Fugue | 1_vn | Violin | 100.00% | 98.36% | +1.94 |
| AuSep_1_vn_36_Rondeau | 1_vn | Violin | 94.63% | 91.32% | +3.13 |
| AuSep_1_vn_38_Jerusalem | 1_vn | Violin | 97.66% | 95.91% | +3.49 |
| AuSep_1_vn_44_K515 | 1_vn | Violin | 98.87% | 94.37% | +6.32 |
| AuSep_2_vc_01_Jupiter | 2_vc | Cello | 98.15% | 94.44% | +0.83 |
| AuSep_2_vc_11_Maria | 2_vc | Cello | 91.44% | 77.35% | +0.83 |
| AuSep_2_vn_02_Sonata | 2_vn | Violin | 94.00% | 80.00% | +3.05 |
| AuSep_2_vn_08_Spring | 2_vn | Violin | 98.94% | 97.87% | +0.54 |
| AuSep_2_vn_09_Jesus | 2_vn | Violin | 83.54% | 74.28% | -0.19 |
| AuSep_2_vn_12_Spring | 2_vn | Violin | 98.82% | 97.93% | +1.32 |
| AuSep_2_vn_13_Hark | 2_vn | Violin | 97.26% | 94.52% | -0.48 |
| AuSep_2_vn_19_Pavane | 2_vn | Violin | 91.00% | 89.10% | +5.88 |
| AuSep_2_vn_24_Pirates | 2_vn | Violin | 94.25% | 94.25% | +3.36 |
| AuSep_2_vn_26_King | 2_vn | Violin | 96.68% | 93.36% | -2.06 |
| AuSep_2_vn_32_Fugue | 2_vn | Violin | 99.60% | 94.07% | +3.54 |
| AuSep_2_vn_36_Rondeau | 2_vn | Violin | 91.28% | 89.45% | +4.62 |
| AuSep_2_vn_38_Jerusalem | 2_vn | Violin | 92.78% | 89.44% | +0.74 |
| AuSep_2_vn_44_K515 | 2_vn | Violin | 93.92% | 68.76% | +0.97 |
| AuSep_3_va_13_Hark | 3_va | Viola | 90.14% | 81.69% | -0.55 |
| AuSep_3_va_24_Pirates | 3_va | Viola | 96.32% | 88.97% | -1.63 |
| AuSep_3_va_26_King | 3_va | Viola | 96.77% | 90.78% | -1.48 |
| AuSep_3_va_32_Fugue | 3_va | Viola | 100.00% | 78.97% | +2.75 |
| AuSep_3_va_36_Rondeau | 3_va | Viola | 96.30% | 89.81% | +1.08 |
| AuSep_3_va_38_Jerusalem | 3_va | Viola | 94.61% | 82.63% | +1.32 |
| AuSep_3_va_44_K515 | 3_va | Viola | 99.37% | 94.34% | +0.62 |
| AuSep_3_vc_12_Spring | 3_vc | Cello | 98.15% | 92.22% | +1.60 |
| AuSep_3_vc_19_Pavane | 3_vc | Cello | 92.21% | 84.43% | +0.51 |
| AuSep_4_va_44_K515 | 4_va | Viola | 83.27% | 56.61% | +1.76 |
| AuSep_4_vc_24_Pirates | 4_vc | Cello | 89.33% | 73.03% | -0.36 |
| AuSep_4_vc_26_King | 4_vc | Cello | 94.44% | 87.50% | -0.01 |
| AuSep_4_vc_32_Fugue | 4_vc | Cello | 99.47% | 95.19% | +0.91 |
| AuSep_4_vc_36_Rondeau | 4_vc | Cello | 90.74% | 80.86% | +0.98 |
| AuSep_4_vc_38_Jerusalem | 4_vc | Cello | 95.68% | 93.53% | +0.81 |
| AuSep_5_vc_44_K515 | 5_vc | Cello | 96.94% | 83.89% | +0.44 |
