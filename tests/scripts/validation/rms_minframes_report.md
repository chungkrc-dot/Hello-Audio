# RMS Threshold & Minimum Duration Ablation Study

Generated: 2026-07-21 17:54

## Methodology

The pYIN engine was run through the full production pipeline (extract → intonation filters → DTW alignment → harmonic folding → metrics) over a full factorial grid of 6 `rms_threshold` values × 5 `min_frames` values (30 combinations). All other parameters were held at Engine Optimal Defaults (`max_pitch_slope=0.50`, `switch_prob=0.005`, `reference_pitch_hz=440.0`).

Both parameters are consumed **downstream** of `librosa.pyin()`, inside `analyze_intonation()`. The pitch extraction was therefore performed exactly once per track and reused across all 30 cells — 15 extractions rather than 450. The grid is exact, not approximated.

**Track subset.** The sweep used the same deterministic subset as the slope/`switch_prob` ablation: the first 5 tracks of each instrument in sorted path order (15 selected, 15 yielding parsable MIDI). Results are therefore directly comparable between the two studies.

**Metrics per cell:**

- **Detection yield** — % of MIDI reference notes receiving a non-NaN `Deviation_Cents`.
- **Inclusion yield** — % of *detected* notes surviving `is_note_excluded()` ($|\text{dev}| \le 100$ c and no harmonic-folding correction).
- **Median / Mean / P90 $|\text{Deviation\_Cents}|$** — over included notes only.
- **RMS gate rate** — % of voiced frames removed by the amplitude gate, measured in isolation from the duration and DTW stages.
- **Island destruction rate** — % of candidate note-islands (contiguous runs in the combined mask) shorter than `min_frames` and therefore destroyed outright by the duration filter.

### Adaptive Noise Floor

`analyze_intonation()` does not use the nominal `rms_threshold` directly. It applies an adaptive rule:

$$\tau_{\text{eff}} = \max\left(\tau_{\text{nominal}},\ 2 \cdot P_{10}(\text{RMS})\right)$$

The swept parameter is therefore only *binding* on tracks where it exceeds twice the track's 10th-percentile RMS; below that the adaptive floor governs and the nominal value has no effect at all. The **binding rate** — the % of tracks on which the nominal threshold is the operative one — is reported below and is essential to interpreting the sweep.

## Track Subset

| # | Track | Instrument |
| :---: | :--- | :---: |
| 1 | AuSep_1_vn_01_Jupiter | Violin |
| 2 | AuSep_1_vn_02_Sonata | Violin |
| 3 | AuSep_2_vn_02_Sonata | Violin |
| 4 | AuSep_2_vn_08_Spring | Violin |
| 5 | AuSep_2_vn_09_Jesus | Violin |
| 6 | AuSep_3_va_13_Hark | Viola |
| 7 | AuSep_3_va_24_Pirates | Viola |
| 8 | AuSep_3_va_25_Pirates | Viola |
| 9 | AuSep_3_va_26_King | Viola |
| 10 | AuSep_3_va_27_King | Viola |
| 11 | AuSep_2_vc_01_Jupiter | Cello |
| 12 | AuSep_2_vc_11_Maria | Cello |
| 13 | AuSep_3_vc_12_Spring | Cello |
| 14 | AuSep_3_vc_19_Pavane | Cello |
| 15 | AuSep_3_vc_20_Pavane | Cello |

## Detection Yield (%)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 95.8 | 95.7 | 95.4 | 94.3 | 86.0 |
| `0.0025` | 95.8 | 95.7 | 95.2 | 94.1 | 85.6 |
| `0.005` | 93.1 | 92.8 | 92.2 | 89.6 | 78.2 |
| `0.01` | 79.1 | 78.5 | 76.9 | 71.3 | 53.1 |
| `0.02` | 52.3 | 52.0 | 49.8 | 40.0 | 20.7 |
| `0.05` | 8.7 | 8.3 | 7.4 | 5.0 | 2.3 |

## Inclusion Yield (% of detected)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 90.5 | 90.6 | 90.9 | 91.1 | 89.9 |
| `0.0025` | 90.5 | 90.6 | 90.9 | 91.1 | 89.9 |
| `0.005` | 90.8 | 91.0 | 91.1 | 91.4 | 89.7 |
| `0.01` | 91.5 | 91.5 | 91.5 | 91.4 | 90.4 |
| `0.02` | 92.2 | 92.3 | 92.2 | 91.4 | 89.7 |
| `0.05` | 87.6 | 89.1 | 88.7 | 91.4 | 85.7 |

## Median $|\text{Deviation\_Cents}|$ (included notes)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| `0.0025` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| `0.005` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| `0.01` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| `0.02` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| `0.05` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |

> [!IMPORTANT]
> The median takes only **1** distinct value(s) across all 30 grid cells. `librosa.pyin()` quantises $f_0$ onto a grid of `resolution = 0.1` semitones, so every `Deviation_Cents` value is a multiple of 10 cents and the median collapses onto that grid. The median is therefore **not** a usable discriminator at this scale; **mean $|\text{dev}|$ is used as the accuracy axis** for identifying the optimal region. This reproduces the finding of the slope/`switch_prob` ablation.

## Mean $|\text{Deviation\_Cents}|$ (included notes)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 10.73 | 10.72 | 10.67 | 10.60 | 10.18 |
| `0.0025` | 10.70 | 10.69 | 10.64 | 10.56 | 10.21 |
| `0.005` | 10.93 | 10.89 | 10.85 | 10.83 | 10.50 |
| `0.01` | 11.21 | 11.14 | 11.11 | 11.05 | 10.20 |
| `0.02` | 12.64 | 12.64 | 12.52 | 11.54 | 10.79 |
| `0.05` | 14.91 | 15.10 | 14.06 | 12.95 | 10.37 |

## 90th Percentile $|\text{Deviation\_Cents}|$ (included notes)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |
| `0.0025` | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |
| `0.005` | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |
| `0.01` | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |
| `0.02` | 30.00 | 30.00 | 30.00 | 20.00 | 20.00 |
| `0.05` | 30.00 | 30.00 | 30.00 | 30.00 | 20.00 |

## RMS Gate Rate (% of voiced frames removed)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 14.24 | 14.24 | 14.24 | 14.24 | 14.24 |
| `0.0025` | 15.17 | 15.17 | 15.17 | 15.17 | 15.17 |
| `0.005` | 23.26 | 23.26 | 23.26 | 23.26 | 23.26 |
| `0.01` | 44.67 | 44.67 | 44.67 | 44.67 | 44.67 |
| `0.02` | 72.16 | 72.16 | 72.16 | 72.16 | 72.16 |
| `0.05` | 96.51 | 96.51 | 96.51 | 96.51 | 96.51 |

## Adaptive-Floor Binding Rate (% of tracks where $\tau_{nominal}$ is operative)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 0 | 0 | 0 | 0 | 0 |
| `0.0025` | 7 | 7 | 7 | 7 | 7 |
| `0.005` | 60 | 60 | 60 | 60 | 60 |
| `0.01` | 93 | 93 | 93 | 93 | 93 |
| `0.02` | 100 | 100 | 100 | 100 | 100 |
| `0.05` | 100 | 100 | 100 | 100 | 100 |

## Duration Filter: Islands Destroyed (% of candidate islands)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 0.00 | 7.96 | 13.67 | 18.41 | 29.98 |
| `0.0025` | 0.00 | 7.98 | 13.82 | 18.88 | 30.79 |
| `0.005` | 0.00 | 7.83 | 13.69 | 19.34 | 34.74 |
| `0.01` | 0.00 | 6.38 | 12.56 | 23.34 | 48.07 |
| `0.02` | 0.00 | 4.43 | 11.57 | 33.26 | 69.45 |
| `0.05` | 0.00 | 5.54 | 18.24 | 47.56 | 78.83 |

## Duration Filter: Frames Lost (% of candidate island frames)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 0.00 | 0.28 | 0.75 | 1.65 | 6.55 |
| `0.0025` | 0.00 | 0.29 | 0.78 | 1.75 | 6.90 |
| `0.005` | 0.00 | 0.31 | 0.86 | 2.08 | 9.29 |
| `0.01` | 0.00 | 0.30 | 1.01 | 3.86 | 17.50 |
| `0.02` | 0.00 | 0.29 | 1.46 | 9.28 | 35.35 |
| `0.05` | 0.00 | 0.49 | 3.23 | 16.84 | 45.58 |

## Included Note Counts

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 2388 | 2388 | 2387 | 2365 | 2129 |
| `0.0025` | 2387 | 2387 | 2384 | 2361 | 2119 |
| `0.005` | 2331 | 2326 | 2314 | 2255 | 1934 |
| `0.01` | 1995 | 1980 | 1939 | 1795 | 1322 |
| `0.02` | 1330 | 1323 | 1264 | 1008 | 512 |
| `0.05` | 211 | 205 | 180 | 127 | 54 |

## Marginal Effects

Each parameter's total influence, averaged over all levels of the other:

| Parameter | Detection yield range | Mean \|dev\| range |
| :--- | :---: | :---: |
| `rms_threshold` | 87.06 pp | 2.92 c |
| `min_frames` | 16.52 pp | 1.49 c |

## Pareto Frontier

Cells not dominated on both axes (higher detection yield **and** lower mean $|\text{dev}|$):

| `rms_threshold` | `min_frames` | Detection Yield | Mean \|dev\| (c) |
| :---: | :---: | :---: | :---: |
| 0.001 | 1 | 95.8% | 10.73 |
| 0.001 | 4 | 95.4% | 10.67 |
| 0.001 | 8 | 94.3% | 10.60 |
| 0.001 | 16 | 86.0% | 10.18 |
| 0.0025 | 1 | 95.8% | 10.70 |
| 0.0025 | 2 | 95.7% | 10.69 |
| 0.0025 | 4 | 95.2% | 10.64 |
| 0.0025 | 8 | 94.1% | 10.56 |

## Optimal Region

- **Maximum detection yield in grid**: 95.8%
- **Minimum mean $|\text{dev}|$ in grid**: 10.18 cents

The optimal region is defined as those cells simultaneously within 1.0 percentage point of the maximum detection yield **and** within 0.5 cent of the minimum mean deviation — the flat plateau of the yield/accuracy trade-off.

| `rms_threshold` | `min_frames` | Detection Yield | Inclusion Yield | Mean \|dev\| (c) | Islands Destroyed |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 0.001 | 4 | 95.4% | 90.9% | 10.67 | 13.67% |
| 0.0025 | 4 | 95.2% | 90.9% | 10.64 | 13.82% |

### Production Setting vs. Grid

The production configuration (`rms_threshold=0.005`, `min_frames=2`) achieves 92.8% detection yield, 91.0% inclusion yield, and a mean $|\text{dev}|$ of 10.89 cents (2326 included notes) — outside the optimal region. The nominal RMS threshold is binding on 60% of tracks (mean effective threshold 0.00641).

- Against REAPER's `min_frames=4` at the same RMS threshold: detection yield 92.2% ($\Delta = +0.65$ pp), mean $|\text{dev}|$ 10.85 c ($\Delta = +0.04$ c), inclusion yield 91.1% ($\Delta = -0.17$ pp).
- Against no duration filtering (`min_frames=1`): detection yield 93.1% ($\Delta = -0.33$ pp), mean $|\text{dev}|$ 10.93 c ($\Delta = -0.04$ c), inclusion yield 90.8% ($\Delta = +0.12$ pp).
- Against the loosest amplitude gate (`rms_threshold=0.001`): detection yield 95.7% ($\Delta = -2.90$ pp), mean $|\text{dev}|$ 10.72 c ($\Delta = +0.17$ c), inclusion yield 90.6% ($\Delta = +0.41$ pp).
- Against the tightest amplitude gate (`rms_threshold=0.05`): detection yield 8.3% ($\Delta = +84.46$ pp), mean $|\text{dev}|$ 15.10 c ($\Delta = -4.21$ c), inclusion yield 89.1% ($\Delta = +1.84$ pp).
