# Slope Filter & Switch Probability Ablation Study

Generated: 2026-07-23 02:07

## Methodology

The pYIN engine was run through the full production pipeline (extract → intonation filters → DTW alignment → harmonic folding → metrics) over a full factorial grid of 6 `max_pitch_slope` values × 5 `switch_prob` values (30 combinations). All other parameters were held at Engine Optimal Defaults (`rms_threshold=0.005`, `min_frames=2`, `reference_pitch_hz=440.0`).

Because `switch_prob` is consumed inside `librosa.pyin()` while `max_pitch_slope` is applied downstream, the pitch extraction was performed once per (track, `switch_prob`) pair and reused across all slope values — the grid is therefore exact, not approximated.

**Corpus.** The sweep covers **every** bowed-string track in the URMP corpus — 41 stems (10 cello, 8 viola, 23 violin), 41 of which yielded a strictly resolvable MIDI part. There is no track subset and therefore no sampling choice to justify.

Each cell is summarised two ways. The **pooled** figure treats the corpus as one note population; the **per-track** figure averages the track-level statistic and carries a 95% confidence interval, taking the track rather than the note as the unit of replication. The two answer different questions — the pooled figure weights long tracks more heavily, the per-track figure weights every performance equally — and the interval on the latter is what tells you whether a difference between two cells is larger than the spread between performances.

**Metrics per cell:**

- **Detection yield** — % of MIDI reference notes receiving a non-NaN `Deviation_Cents`.
- **Inclusion yield** — % of *detected* notes surviving `is_note_excluded()` ($|\text{dev}| \le 100$ c and no harmonic-folding correction).
- **Median / Mean / P90 $|\text{Deviation\_Cents}|$** — over included notes only.
- **Slope filter rejection rate** — % of voiced frame-to-frame transitions whose $|\Delta p_{midi}|$ exceeds `max_pitch_slope`, measured in isolation from the RMS, duration and DTW stages.

`max_pitch_slope = 999.0` is a sentinel above any physically realisable frame-to-frame pitch change; it is operationally equivalent to disabling the slope filter and is reported as **disabled**.

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

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 93.3 | 93.5 | 93.5 | 93.7 | 93.7 |
| `0.25` | 94.2 | 94.4 | 94.5 | 94.6 | 94.7 |
| `0.50` | 94.3 | 94.6 | 94.6 | 94.7 | 94.8 |
| `0.75` | 94.4 | 94.6 | 94.6 | 94.8 | 94.9 |
| `1.00` | 94.4 | 94.6 | 94.7 | 94.8 | 94.9 |
| disabled | 94.4 | 94.6 | 94.7 | 94.8 | 94.9 |

## Detection Yield (%), per-track mean with 95% CI

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 94.2 [92.7, 95.7] | 94.4 [93.0, 95.8] | 94.5 [93.1, 95.9] | 94.6 [93.2, 95.9] | 94.6 [93.3, 96.0] |
| `0.25` | 94.8 [93.4, 96.1] | 95.0 [93.7, 96.2] | 95.0 [93.8, 96.3] | 95.1 [93.9, 96.3] | 95.2 [94.0, 96.4] |
| `0.50` | 94.9 [93.5, 96.2] | 95.1 [93.8, 96.3] | 95.1 [93.9, 96.3] | 95.2 [94.0, 96.4] | 95.3 [94.1, 96.4] |
| `0.75` | 94.9 [93.6, 96.2] | 95.1 [93.9, 96.3] | 95.1 [93.9, 96.3] | 95.2 [94.0, 96.4] | 95.3 [94.1, 96.4] |
| `1.00` | 94.9 [93.6, 96.2] | 95.1 [93.9, 96.3] | 95.1 [93.9, 96.3] | 95.2 [94.0, 96.4] | 95.3 [94.1, 96.5] |
| disabled | 94.9 [93.6, 96.2] | 95.1 [93.9, 96.3] | 95.1 [93.9, 96.3] | 95.2 [94.0, 96.4] | 95.3 [94.1, 96.5] |

> [!NOTE]
> Intervals are over the 41 tracks of the corpus, not over notes. The mean interval width is 2.5 pp, against a 1.1 pp spread between the best and worst cells in the grid. Every cell-to-cell difference in this study is therefore smaller than the between-performance spread: the parameter choice moves detection yield less than the choice of track does, and no ranking within the grid should be read as more than a tie-break.

## Inclusion Yield (% of detected)

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 91.8 | 91.8 | 91.8 | 91.8 | 91.8 |
| `0.25` | 91.4 | 91.4 | 91.4 | 91.3 | 91.3 |
| `0.50` | 91.3 | 91.3 | 91.3 | 91.2 | 91.2 |
| `0.75` | 91.3 | 91.3 | 91.3 | 91.2 | 91.2 |
| `1.00` | 91.3 | 91.2 | 91.2 | 91.2 | 91.2 |
| disabled | 91.3 | 91.2 | 91.2 | 91.1 | 91.1 |

## Median $|\text{Deviation\_Cents}|$ (included notes)

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| `0.25` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| `0.50` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| `0.75` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| `1.00` | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| disabled | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |

> [!IMPORTANT]
> The median takes only **1** distinct value(s) across all 30 grid cells. `librosa.pyin()` quantises $f_0$ onto a grid of `resolution = 0.1` semitones, so every `Deviation_Cents` value is a multiple of 10 cents and the median collapses onto that grid. The median is therefore **not** a usable discriminator at this scale; **mean $|\text{dev}|$ is used as the accuracy axis** for identifying the optimal region.

## Mean $|\text{Deviation\_Cents}|$ (included notes), pooled

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 12.75 | 12.76 | 12.76 | 12.76 | 12.76 |
| `0.25` | 12.89 | 12.90 | 12.91 | 12.90 | 12.91 |
| `0.50` | 12.95 | 12.97 | 12.97 | 12.96 | 12.96 |
| `0.75` | 12.99 | 13.01 | 13.01 | 13.00 | 13.00 |
| `1.00` | 13.01 | 13.02 | 13.03 | 13.02 | 13.02 |
| disabled | 13.04 | 13.05 | 13.06 | 13.05 | 13.05 |

## Mean $|\text{Deviation\_Cents}|$, per-track mean with 95% CI

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 12.15 [11.03, 13.26] | 12.15 [11.04, 13.27] | 12.15 [11.03, 13.27] | 12.15 [11.03, 13.26] | 12.15 [11.04, 13.27] |
| `0.25` | 12.28 [11.17, 13.40] | 12.29 [11.17, 13.40] | 12.29 [11.17, 13.41] | 12.28 [11.16, 13.40] | 12.29 [11.17, 13.40] |
| `0.50` | 12.32 [11.22, 13.43] | 12.33 [11.22, 13.44] | 12.33 [11.22, 13.44] | 12.32 [11.21, 13.43] | 12.33 [11.22, 13.43] |
| `0.75` | 12.35 [11.24, 13.46] | 12.36 [11.25, 13.46] | 12.36 [11.25, 13.47] | 12.35 [11.24, 13.45] | 12.35 [11.24, 13.46] |
| `1.00` | 12.35 [11.25, 13.46] | 12.36 [11.25, 13.47] | 12.36 [11.25, 13.47] | 12.35 [11.24, 13.46] | 12.35 [11.25, 13.46] |
| disabled | 12.37 [11.26, 13.48] | 12.37 [11.26, 13.48] | 12.38 [11.27, 13.49] | 12.37 [11.26, 13.47] | 12.37 [11.26, 13.48] |

## 90th Percentile $|\text{Deviation\_Cents}|$ (included notes)

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| `0.25` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| `0.50` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| `0.75` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| `1.00` | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |
| disabled | 30.00 | 30.00 | 30.00 | 30.00 | 30.00 |

## Slope Filter Rejection Rate (% of voiced frame transitions)

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 16.68 | 16.69 | 16.68 | 16.67 | 16.63 |
| `0.25` | 4.47 | 4.49 | 4.50 | 4.52 | 4.51 |
| `0.50` | 2.06 | 2.07 | 2.08 | 2.09 | 2.07 |
| `0.75` | 1.33 | 1.34 | 1.35 | 1.35 | 1.34 |
| `1.00` | 0.91 | 0.91 | 0.91 | 0.91 | 0.89 |
| disabled | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## Included Note Counts

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 8131 | 8152 | 8156 | 8164 | 8170 |
| `0.25` | 8175 | 8191 | 8195 | 8202 | 8209 |
| `0.50` | 8181 | 8197 | 8199 | 8206 | 8213 |
| `0.75` | 8184 | 8200 | 8202 | 8209 | 8216 |
| `1.00` | 8183 | 8199 | 8201 | 8208 | 8215 |
| disabled | 8181 | 8197 | 8199 | 8205 | 8213 |

## Marginal Effects

Each parameter's total influence, averaged over all levels of the other:

| Parameter | Detection yield range | Mean \|dev\| range |
| :--- | :---: | :---: |
| `max_pitch_slope` | 1.14 pp | 0.29 c |
| `switch_prob` | 0.50 pp | 0.02 c |

## Pareto Frontier

Cells not dominated on both axes (higher detection yield **and** lower mean $|\text{dev}|$):

| `max_pitch_slope` | `switch_prob` | Detection Yield | Mean \|dev\| (c) |
| :---: | :---: | :---: | :---: |
| 0.10 | 0.001 | 93.3% | 12.75 |
| 0.10 | 0.005 | 93.5% | 12.76 |
| 0.10 | 0.01 | 93.5% | 12.76 |
| 0.10 | 0.02 | 93.7% | 12.76 |
| 0.10 | 0.05 | 93.7% | 12.76 |
| 0.25 | 0.001 | 94.2% | 12.89 |
| 0.25 | 0.005 | 94.4% | 12.90 |
| 0.25 | 0.02 | 94.6% | 12.90 |
| 0.25 | 0.05 | 94.7% | 12.91 |
| 0.50 | 0.02 | 94.7% | 12.96 |
| 0.50 | 0.05 | 94.8% | 12.96 |
| 0.75 | 0.05 | 94.9% | 13.00 |
| 1.00 | 0.05 | 94.9% | 13.02 |

## Optimal Region

- **Maximum detection yield in grid**: 94.9%
- **Minimum mean $|\text{dev}|$ in grid**: 12.75 cents

The optimal region is defined as those cells simultaneously within 1.0 percentage point of the maximum detection yield **and** within 0.5 cent of the minimum mean deviation — the flat plateau of the yield/accuracy trade-off.

| `max_pitch_slope` | `switch_prob` | Detection Yield | Inclusion Yield | Mean \|dev\| (c) | Slope Reject % |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 0.25 | 0.001 | 94.2% | 91.4% | 12.89 | 4.47% |
| 0.25 | 0.005 | 94.4% | 91.4% | 12.90 | 4.49% |
| 0.25 | 0.01 | 94.5% | 91.4% | 12.91 | 4.50% |
| 0.25 | 0.02 | 94.6% | 91.3% | 12.90 | 4.52% |
| 0.25 | 0.05 | 94.7% | 91.3% | 12.91 | 4.51% |
| 0.50 | 0.001 | 94.3% | 91.3% | 12.95 | 2.06% |
| 0.50 **(Engine Optimal Default)** | 0.005 | 94.6% | 91.3% | 12.97 | 2.07% |
| 0.50 | 0.01 | 94.6% | 91.3% | 12.97 | 2.08% |
| 0.50 | 0.02 | 94.7% | 91.2% | 12.96 | 2.09% |
| 0.50 | 0.05 | 94.8% | 91.2% | 12.96 | 2.07% |
| 0.75 | 0.001 | 94.4% | 91.3% | 12.99 | 1.33% |
| 0.75 | 0.005 | 94.6% | 91.3% | 13.01 | 1.34% |
| 0.75 | 0.01 | 94.6% | 91.3% | 13.01 | 1.35% |
| 0.75 | 0.02 | 94.8% | 91.2% | 13.00 | 1.35% |
| 0.75 | 0.05 | 94.9% | 91.2% | 13.00 | 1.34% |
| 1.00 | 0.001 | 94.4% | 91.3% | 13.01 | 0.91% |
| 1.00 | 0.005 | 94.6% | 91.2% | 13.02 | 0.91% |
| 1.00 | 0.01 | 94.7% | 91.2% | 13.03 | 0.91% |
| 1.00 | 0.02 | 94.8% | 91.2% | 13.02 | 0.91% |
| 1.00 | 0.05 | 94.9% | 91.2% | 13.02 | 0.89% |
| disabled | 0.001 | 94.4% | 91.3% | 13.04 | 0.00% |
| disabled | 0.005 | 94.6% | 91.2% | 13.05 | 0.00% |
| disabled | 0.01 | 94.7% | 91.2% | 13.06 | 0.00% |
| disabled | 0.02 | 94.8% | 91.1% | 13.05 | 0.00% |
| disabled | 0.05 | 94.9% | 91.1% | 13.05 | 0.00% |

### Production Setting vs. Grid

The production configuration (`max_pitch_slope=0.50`, `switch_prob=0.005`) achieves 94.6% detection yield, 91.3% inclusion yield, and a mean $|\text{dev}|$ of 12.97 cents (8197 included notes) — inside the optimal region. Per track that is a detection yield of 95.1% (95% CI [93.8, 96.3]) over 41 tracks, and a mean $|\text{dev}|$ of 12.33 c (95% CI [11.22, 13.44]).

Against the librosa default `switch_prob=0.01` at the same slope: detection yield 94.6% ($\Delta = -0.0$ pp), mean $|\text{dev}|$ 12.97 cents ($\Delta = -0.00$ c).

Against a disabled slope filter at the same `switch_prob`: detection yield 94.6% ($\Delta = -0.1$ pp), mean $|\text{dev}|$ 13.05 cents ($\Delta = -0.09$ c), inclusion yield 91.2% ($\Delta = +0.1$ pp).
