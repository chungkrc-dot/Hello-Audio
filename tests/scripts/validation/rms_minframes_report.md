# RMS Threshold & Minimum Duration Ablation Study

Generated: 2026-07-23 01:20

## Methodology

The pYIN engine was run through the full production pipeline (extract → intonation filters → DTW alignment → harmonic folding → metrics) over a full factorial grid of 6 `rms_threshold` values × 5 `min_frames` values (30 combinations). All other parameters were held at Engine Optimal Defaults (`max_pitch_slope=0.50`, `switch_prob=0.005`, `reference_pitch_hz=440.0`).

Both parameters are consumed **downstream** of `librosa.pyin()`, inside `analyze_intonation()`. The pitch extraction was therefore performed exactly once per track and reused across all 30 cells — 41 extractions rather than 1230. The grid is exact, not approximated.

**Corpus.** The sweep covers **every** bowed-string track in the URMP corpus — 41 stems (10 cello, 8 viola, 23 violin), 41 of which yielded a strictly resolvable MIDI part — the same set the slope/`switch_prob` ablation uses, so the two studies are directly comparable. There is no track subset and therefore no sampling choice to justify.

Each cell is summarised two ways. The **pooled** figure treats the corpus as one note population; the **per-track** figure averages the track-level statistic and carries a 95% confidence interval, taking the track rather than the note as the unit of replication.

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

## Corpus

| # | Track | Instrument |
| :---: | :--- | :---: |
| 1 | AuSep_1_vn_01_Jupiter | Violin |
| 2 | AuSep_2_vc_01_Jupiter | Cello |
| 3 | AuSep_1_vn_02_Sonata | Violin |
| 4 | AuSep_2_vn_02_Sonata | Violin |
| 5 | AuSep_2_vn_08_Spring | Violin |
| 6 | AuSep_2_vn_09_Jesus | Violin |
| 7 | AuSep_2_vc_11_Maria | Cello |
| 8 | AuSep_1_vn_12_Spring | Violin |
| 9 | AuSep_2_vn_12_Spring | Violin |
| 10 | AuSep_3_vc_12_Spring | Cello |
| 11 | AuSep_1_vn_13_Hark | Violin |
| 12 | AuSep_2_vn_13_Hark | Violin |
| 13 | AuSep_3_va_13_Hark | Viola |
| 14 | AuSep_1_vn_17_Nocturne | Violin |
| 15 | AuSep_2_vn_19_Pavane | Violin |
| 16 | AuSep_3_vc_19_Pavane | Cello |
| 17 | AuSep_1_vn_24_Pirates | Violin |
| 18 | AuSep_2_vn_24_Pirates | Violin |
| 19 | AuSep_3_va_24_Pirates | Viola |
| 20 | AuSep_4_vc_24_Pirates | Cello |
| 21 | AuSep_1_vn_26_King | Violin |
| 22 | AuSep_2_vn_26_King | Violin |
| 23 | AuSep_3_va_26_King | Viola |
| 24 | AuSep_4_vc_26_King | Cello |
| 25 | AuSep_1_vn_32_Fugue | Violin |
| 26 | AuSep_2_vn_32_Fugue | Violin |
| 27 | AuSep_3_va_32_Fugue | Viola |
| 28 | AuSep_4_vc_32_Fugue | Cello |
| 29 | AuSep_1_vn_36_Rondeau | Violin |
| 30 | AuSep_2_vn_36_Rondeau | Violin |
| 31 | AuSep_3_va_36_Rondeau | Viola |
| 32 | AuSep_4_vc_36_Rondeau | Cello |
| 33 | AuSep_1_vn_38_Jerusalem | Violin |
| 34 | AuSep_2_vn_38_Jerusalem | Violin |
| 35 | AuSep_3_va_38_Jerusalem | Viola |
| 36 | AuSep_4_vc_38_Jerusalem | Cello |
| 37 | AuSep_1_vn_44_K515 | Violin |
| 38 | AuSep_2_vn_44_K515 | Violin |
| 39 | AuSep_3_va_44_K515 | Viola |
| 40 | AuSep_4_va_44_K515 | Viola |
| 41 | AuSep_5_vc_44_K515 | Cello |

## Detection Yield (%), pooled over all notes

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 95.8 | 95.6 | 94.9 | 92.2 | 77.6 |
| `0.0025` | 95.7 | 95.5 | 94.9 | 92.1 | 77.4 |
| `0.005` | 94.8 | 94.6 | 93.9 | 90.5 | 74.5 |
| `0.01` | 86.8 | 86.3 | 84.7 | 78.3 | 56.7 |
| `0.02` | 55.6 | 54.7 | 51.9 | 42.4 | 25.2 |
| `0.05` | 9.9 | 9.5 | 8.5 | 6.0 | 2.7 |

## Detection Yield (%), per-track mean with 95% CI

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 95.8 [94.8, 96.8] | 95.7 [94.6, 96.7] | 95.2 [94.0, 96.4] | 93.3 [91.4, 95.3] | 81.7 [77.3, 86.0] |
| `0.0025` | 95.8 [94.8, 96.8] | 95.6 [94.5, 96.7] | 95.2 [94.0, 96.4] | 93.2 [91.3, 95.2] | 81.5 [77.1, 85.8] |
| `0.005` | 95.3 [94.1, 96.4] | 95.1 [93.8, 96.3] | 94.6 [93.2, 96.0] | 92.2 [90.1, 94.4] | 79.2 [74.8, 83.7] |
| `0.01` | 89.0 [86.2, 91.8] | 88.6 [85.7, 91.5] | 87.4 [84.3, 90.4] | 82.3 [78.4, 86.3] | 63.8 [57.3, 70.3] |
| `0.02` | 61.1 [55.8, 66.5] | 60.3 [54.9, 65.6] | 57.4 [52.0, 62.8] | 48.5 [42.9, 54.2] | 31.8 [25.6, 38.1] |
| `0.05` | 12.8 [9.5, 16.2] | 12.5 [9.2, 15.8] | 11.3 [8.2, 14.4] | 8.4 [5.7, 11.1] | 4.3 [2.2, 6.3] |

> [!NOTE]
> Intervals are over the 41 tracks of the corpus, not over notes. The mean interval width is 6.1 pp, against a 91.5 pp spread between the best and worst cells in the grid. Differences exceeding the interval width are resolvable against the between-performance spread; smaller ones are not.

## Inclusion Yield (% of detected)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 91.2 | 91.3 | 91.4 | 91.6 | 90.7 |
| `0.0025` | 91.2 | 91.3 | 91.4 | 91.6 | 90.7 |
| `0.005` | 91.2 | 91.3 | 91.4 | 91.6 | 90.5 |
| `0.01` | 91.2 | 91.2 | 91.2 | 90.9 | 90.1 |
| `0.02` | 89.8 | 89.8 | 89.9 | 89.4 | 88.1 |
| `0.05` | 87.8 | 88.0 | 88.0 | 87.5 | 84.0 |

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

## Mean $|\text{Deviation\_Cents}|$ (included notes), pooled

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 12.92 | 12.88 | 12.84 | 12.71 | 12.51 |
| `0.0025` | 12.94 | 12.89 | 12.84 | 12.71 | 12.53 |
| `0.005` | 13.00 | 12.97 | 12.92 | 12.81 | 12.66 |
| `0.01` | 13.17 | 13.11 | 13.10 | 12.97 | 12.68 |
| `0.02` | 13.87 | 13.82 | 13.65 | 13.41 | 13.34 |
| `0.05` | 14.67 | 14.49 | 14.24 | 14.27 | 13.82 |

## Mean $|\text{Deviation\_Cents}|$, per-track mean with 95% CI

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 12.29 [11.18, 13.40] | 12.27 [11.17, 13.37] | 12.25 [11.15, 13.36] | 12.21 [11.11, 13.31] | 12.26 [11.12, 13.40] |
| `0.0025` | 12.31 [11.19, 13.44] | 12.30 [11.18, 13.41] | 12.27 [11.16, 13.38] | 12.22 [11.11, 13.33] | 12.27 [11.13, 13.41] |
| `0.005` | 12.35 [11.24, 13.46] | 12.33 [11.22, 13.44] | 12.30 [11.20, 13.41] | 12.25 [11.15, 13.35] | 12.30 [11.17, 13.44] |
| `0.01` | 12.59 [11.46, 13.71] | 12.53 [11.41, 13.64] | 12.54 [11.40, 13.67] | 12.48 [11.34, 13.62] | 12.41 [11.22, 13.61] |
| `0.02` | 13.34 [12.09, 14.59] | 13.31 [12.05, 14.57] | 13.15 [11.87, 14.43] | 12.97 [11.69, 14.24] | 13.12 [11.70, 14.54] |
| `0.05` | 16.26 [13.54, 18.98] | 16.17 [13.50, 18.83] | 15.93 [13.35, 18.50] | 15.41 [13.22, 17.60] | 15.34 [12.16, 18.53] |

## 90th Percentile $|\text{Deviation\_Cents}|$ (included notes)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| `0.0025` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| `0.005` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| `0.01` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| `0.02` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| `0.05` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |

## RMS Gate Rate (% of voiced frames removed)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 18.98 | 18.98 | 18.98 | 18.98 | 18.98 |
| `0.0025` | 19.35 | 19.35 | 19.35 | 19.35 | 19.35 |
| `0.005` | 23.14 | 23.14 | 23.14 | 23.14 | 23.14 |
| `0.01` | 39.48 | 39.48 | 39.48 | 39.48 | 39.48 |
| `0.02` | 71.09 | 71.09 | 71.09 | 71.09 | 71.09 |
| `0.05` | 96.52 | 96.52 | 96.52 | 96.52 | 96.52 |

## Adaptive-Floor Binding Rate (% of tracks where $\tau_{nominal}$ is operative)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 0 | 0 | 0 | 0 | 0 |
| `0.0025` | 5 | 5 | 5 | 5 | 5 |
| `0.005` | 44 | 44 | 44 | 44 | 44 |
| `0.01` | 78 | 78 | 78 | 78 | 78 |
| `0.02` | 100 | 100 | 100 | 100 | 100 |
| `0.05` | 100 | 100 | 100 | 100 | 100 |

## Mean Effective Threshold $\tau_{\text{eff}}$

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 0.00675 | 0.00675 | 0.00675 | 0.00675 | 0.00675 |
| `0.0025` | 0.00678 | 0.00678 | 0.00678 | 0.00678 | 0.00678 |
| `0.005` | 0.00738 | 0.00738 | 0.00738 | 0.00738 | 0.00738 |
| `0.01` | 0.01062 | 0.01062 | 0.01062 | 0.01062 | 0.01062 |
| `0.02` | 0.02000 | 0.02000 | 0.02000 | 0.02000 | 0.02000 |
| `0.05` | 0.05000 | 0.05000 | 0.05000 | 0.05000 | 0.05000 |

This is the axis the sweep actually traverses. Where the mean effective threshold sits above the nominal value in the row label, the adaptive floor — not the swept parameter — is what gated the frames, and the corresponding row of every table above is measuring the floor rather than `rms_threshold`.

| Nominal $\tau$ | Binding on | Mean $\tau_{\text{eff}}$ | Min $\tau_{\text{eff}}$ | Max $\tau_{\text{eff}}$ |
| :---: | :---: | :---: | :---: | :---: |
| `0.001` | 0% of tracks | 0.00675 | 0.00182 | 0.01812 |
| `0.0025` | 5% of tracks | 0.00678 | 0.00250 | 0.01812 |
| `0.005` | 44% of tracks | 0.00738 | 0.00500 | 0.01812 |
| `0.01` | 78% of tracks | 0.01062 | 0.01000 | 0.01812 |
| `0.02` | 100% of tracks | 0.02000 | 0.02000 | 0.02000 |
| `0.05` | 100% of tracks | 0.05000 | 0.05000 | 0.05000 |

The nominal threshold is **entirely inert** at `0.001` — on no track in the corpus does it exceed twice the 10th-percentile RMS. The pipeline is deterministic, so those rows are not merely similar but **identical**: they all ran at the same adaptive floor. Reading them as a sensitivity curve for `rms_threshold` would be reading an axis the sweep never moved along.

## Duration Filter: Islands Destroyed (% of candidate islands)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 0.00 | 6.58 | 11.83 | 20.24 | 39.18 |
| `0.0025` | 0.00 | 6.60 | 11.94 | 20.46 | 39.50 |
| `0.005` | 0.00 | 6.02 | 11.24 | 20.24 | 40.97 |
| `0.01` | 0.00 | 5.26 | 11.45 | 24.84 | 52.02 |
| `0.02` | 0.00 | 5.59 | 14.55 | 36.85 | 67.48 |
| `0.05` | 0.00 | 5.35 | 18.72 | 46.59 | 78.86 |

## Duration Filter: Frames Lost (% of candidate island frames)

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 0.00 | 0.22 | 0.64 | 2.16 | 9.52 |
| `0.0025` | 0.00 | 0.22 | 0.66 | 2.21 | 9.67 |
| `0.005` | 0.00 | 0.21 | 0.67 | 2.41 | 10.94 |
| `0.01` | 0.00 | 0.23 | 0.91 | 4.13 | 17.62 |
| `0.02` | 0.00 | 0.35 | 1.75 | 9.29 | 30.17 |
| `0.05` | 0.00 | 0.47 | 3.43 | 16.81 | 47.49 |

## Included Note Counts

| `rms_threshold` | $m = 1$ | $m = 2$ | $m = 4$ | $m = 8$ | $m = 16$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.001` | 8297 | 8282 | 8241 | 8020 | 6686 |
| `0.0025` | 8293 | 8277 | 8235 | 8009 | 6664 |
| `0.005` | 8216 | 8197 | 8148 | 7869 | 6404 |
| `0.01` | 7514 | 7476 | 7340 | 6759 | 4849 |
| `0.02` | 4743 | 4669 | 4428 | 3600 | 2107 |
| `0.05` | 822 | 797 | 707 | 498 | 216 |

## Marginal Effects

Each parameter's total influence, averaged over all levels of the other:

| Parameter | Detection yield range | Mean \|dev\| range |
| :--- | :---: | :---: |
| `rms_threshold` | 83.92 pp | 1.53 c |
| `min_frames` | 20.75 pp | 0.50 c |

## Pareto Frontier

Cells not dominated on both axes (higher detection yield **and** lower mean $|\text{dev}|$):

| `rms_threshold` | `min_frames` | Detection Yield | Mean \|dev\| (c) |
| :---: | :---: | :---: | :---: |
| 0.001 | 1 | 95.8% | 12.92 |
| 0.001 | 2 | 95.6% | 12.88 |
| 0.001 | 4 | 94.9% | 12.84 |
| 0.001 | 8 | 92.2% | 12.71 |
| 0.001 | 16 | 77.6% | 12.51 |

## Optimal Region

- **Maximum detection yield in grid**: 95.8%
- **Minimum mean $|\text{dev}|$ in grid**: 12.51 cents

The optimal region is defined as those cells simultaneously within 1.0 percentage point of the maximum detection yield **and** within 0.5 cent of the minimum mean deviation — the flat plateau of the yield/accuracy trade-off.

| `rms_threshold` | `min_frames` | Detection Yield | Inclusion Yield | Mean \|dev\| (c) | Islands Destroyed |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 0.001 | 1 | 95.8% | 91.2% | 12.92 | 0.00% |
| 0.001 | 2 | 95.6% | 91.3% | 12.88 | 6.58% |
| 0.001 | 4 | 94.9% | 91.4% | 12.84 | 11.83% |
| 0.0025 | 1 | 95.7% | 91.2% | 12.94 | 0.00% |
| 0.0025 | 2 | 95.5% | 91.3% | 12.89 | 6.60% |
| 0.0025 | 4 | 94.9% | 91.4% | 12.84 | 11.94% |
| 0.005 | 1 | 94.8% | 91.2% | 13.00 | 0.00% |

### Production Setting vs. Grid

The production configuration (`rms_threshold=0.005`, `min_frames=2`) achieves 94.6% detection yield, 91.3% inclusion yield, and a mean $|\text{dev}|$ of 12.97 cents (8197 included notes) — outside the optimal region. Per track that is a detection yield of 95.1% (95% CI [93.8, 96.3]) over 41 tracks. The nominal RMS threshold is binding on 44% of tracks (mean effective threshold 0.00738).

- Against REAPER's `min_frames=4` at the same RMS threshold: detection yield 93.9% ($\Delta = +0.68$ pp), mean $|\text{dev}|$ 12.92 c ($\Delta = +0.04$ c), inclusion yield 91.4% ($\Delta = -0.12$ pp).
- Against no duration filtering (`min_frames=1`): detection yield 94.8% ($\Delta = -0.26$ pp), mean $|\text{dev}|$ 13.00 c ($\Delta = -0.04$ c), inclusion yield 91.2% ($\Delta = +0.04$ pp).
- Against the loosest amplitude gate (`rms_threshold=0.001`): detection yield 95.6% ($\Delta = -1.01$ pp), mean $|\text{dev}|$ 12.88 c ($\Delta = +0.09$ c), inclusion yield 91.3% ($\Delta = +0.03$ pp).
- Against the tightest amplitude gate (`rms_threshold=0.05`): detection yield 9.5% ($\Delta = +85.01$ pp), mean $|\text{dev}|$ 14.49 c ($\Delta = -1.53$ c), inclusion yield 88.0% ($\Delta = +3.32$ pp).
