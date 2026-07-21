# Slope Filter & Switch Probability Ablation Study

Generated: 2026-07-21 14:56

## Methodology

The pYIN engine was run through the full production pipeline (extract → intonation filters → DTW alignment → harmonic folding → metrics) over a full factorial grid of 6 `max_pitch_slope` values × 5 `switch_prob` values (30 combinations). All other parameters were held at Engine Optimal Defaults (`rms_threshold=0.005`, `min_frames=2`, `reference_pitch_hz=440.0`).

Because `switch_prob` is consumed inside `librosa.pyin()` while `max_pitch_slope` is applied downstream, the pitch extraction was performed once per (track, `switch_prob`) pair and reused across all slope values — the grid is therefore exact, not approximated.

**Track subset.** To keep runtime tractable the sweep used a deterministic subset: the first 5 tracks of each instrument in sorted path order (15 selected, 15 yielding parsable MIDI). Selection is fixed rather than random so the study is reproducible.

**Metrics per cell:**

- **Detection yield** — % of MIDI reference notes receiving a non-NaN `Deviation_Cents`.
- **Inclusion yield** — % of *detected* notes surviving `is_note_excluded()` ($|\text{dev}| \le 100$ c and no harmonic-folding correction).
- **Median / Mean / P90 $|\text{Deviation\_Cents}|$** — over included notes only.
- **Slope filter rejection rate** — % of voiced frame-to-frame transitions whose $|\Delta p_{midi}|$ exceeds `max_pitch_slope`, measured in isolation from the RMS, duration and DTW stages.

`max_pitch_slope = 999.0` is a sentinel above any physically realisable frame-to-frame pitch change; it is operationally equivalent to disabling the slope filter and is reported as **disabled**.

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

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 92.1 | 92.3 | 92.4 | 92.6 | 92.8 |
| `0.25` | 92.5 | 92.7 | 92.8 | 93.1 | 93.3 |
| `0.50` | 92.6 | 92.8 | 92.9 | 93.1 | 93.4 |
| `0.75` | 92.6 | 92.8 | 92.9 | 93.1 | 93.4 |
| `1.00` | 92.6 | 92.8 | 92.9 | 93.1 | 93.4 |
| disabled | 92.6 | 92.8 | 92.9 | 93.1 | 93.4 |

## Inclusion Yield (% of detected)

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 91.5 | 91.5 | 91.5 | 91.5 | 91.4 |
| `0.25` | 91.0 | 91.0 | 91.0 | 91.0 | 90.9 |
| `0.50` | 90.9 | 91.0 | 90.9 | 90.9 | 90.8 |
| `0.75` | 90.8 | 90.9 | 90.9 | 90.8 | 90.8 |
| `1.00` | 90.6 | 90.7 | 90.7 | 90.6 | 90.6 |
| disabled | 90.6 | 90.6 | 90.6 | 90.5 | 90.5 |

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

## Mean $|\text{Deviation\_Cents}|$ (included notes)

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 10.54 | 10.58 | 10.58 | 10.57 | 10.61 |
| `0.25` | 10.70 | 10.74 | 10.73 | 10.72 | 10.75 |
| `0.50` | 10.85 | 10.89 | 10.89 | 10.87 | 10.90 |
| `0.75` | 10.89 | 10.93 | 10.93 | 10.92 | 10.94 |
| `1.00` | 10.90 | 10.94 | 10.94 | 10.93 | 10.95 |
| disabled | 10.93 | 10.97 | 10.97 | 10.96 | 10.98 |

## 90th Percentile $|\text{Deviation\_Cents}|$ (included notes)

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |
| `0.25` | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |
| `0.50` | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |
| `0.75` | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |
| `1.00` | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |
| disabled | 20.00 | 20.00 | 20.00 | 20.00 | 20.00 |

## Slope Filter Rejection Rate (% of voiced frame transitions)

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 19.17 | 19.10 | 19.06 | 19.05 | 19.04 |
| `0.25` | 5.30 | 5.27 | 5.26 | 5.29 | 5.29 |
| `0.50` | 2.46 | 2.45 | 2.43 | 2.43 | 2.41 |
| `0.75` | 1.68 | 1.66 | 1.64 | 1.64 | 1.62 |
| `1.00` | 1.20 | 1.18 | 1.16 | 1.15 | 1.12 |
| disabled | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## Included Note Counts

| `max_pitch_slope` | $\beta = 0.001$ | $\beta = 0.005$ | $\beta = 0.01$ | $\beta = 0.02$ | $\beta = 0.05$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `0.10` | 2320 | 2327 | 2329 | 2334 | 2338 |
| `0.25` | 2319 | 2326 | 2327 | 2332 | 2337 |
| `0.50` | 2319 | 2326 | 2327 | 2332 | 2337 |
| `0.75` | 2317 | 2324 | 2325 | 2330 | 2335 |
| `1.00` | 2312 | 2319 | 2320 | 2325 | 2330 |
| disabled | 2311 | 2318 | 2319 | 2323 | 2328 |

## Marginal Effects

Each parameter's total influence, averaged over all levels of the other:

| Parameter | Detection yield range | Mean \|dev\| range |
| :--- | :---: | :---: |
| `max_pitch_slope` | 0.56 pp | 0.39 c |
| `switch_prob` | 0.79 pp | 0.06 c |

## Pareto Frontier

Cells not dominated on both axes (higher detection yield **and** lower mean $|\text{dev}|$):

| `max_pitch_slope` | `switch_prob` | Detection Yield | Mean \|dev\| (c) |
| :---: | :---: | :---: | :---: |
| 0.10 | 0.001 | 92.1% | 10.54 |
| 0.10 | 0.02 | 92.6% | 10.57 |
| 0.10 | 0.05 | 92.8% | 10.61 |
| 0.25 | 0.02 | 93.1% | 10.72 |
| 0.25 | 0.05 | 93.3% | 10.75 |
| 0.50 | 0.05 | 93.4% | 10.90 |

## Optimal Region

- **Maximum detection yield in grid**: 93.4%
- **Minimum mean $|\text{dev}|$ in grid**: 10.54 cents

The optimal region is defined as those cells simultaneously within 1.0 percentage point of the maximum detection yield **and** within 0.5 cent of the minimum mean deviation — the flat plateau of the yield/accuracy trade-off.

| `max_pitch_slope` | `switch_prob` | Detection Yield | Inclusion Yield | Mean \|dev\| (c) | Slope Reject % |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 0.10 | 0.02 | 92.6% | 91.5% | 10.57 | 19.05% |
| 0.10 | 0.05 | 92.8% | 91.4% | 10.61 | 19.04% |
| 0.25 | 0.001 | 92.5% | 91.0% | 10.70 | 5.30% |
| 0.25 | 0.005 | 92.7% | 91.0% | 10.74 | 5.27% |
| 0.25 | 0.01 | 92.8% | 91.0% | 10.73 | 5.26% |
| 0.25 | 0.02 | 93.1% | 91.0% | 10.72 | 5.29% |
| 0.25 | 0.05 | 93.3% | 90.9% | 10.75 | 5.29% |
| 0.50 | 0.001 | 92.6% | 90.9% | 10.85 | 2.46% |
| 0.50 **(Engine Optimal Default)** | 0.005 | 92.8% | 91.0% | 10.89 | 2.45% |
| 0.50 | 0.01 | 92.9% | 90.9% | 10.89 | 2.43% |
| 0.50 | 0.02 | 93.1% | 90.9% | 10.87 | 2.43% |
| 0.50 | 0.05 | 93.4% | 90.8% | 10.90 | 2.41% |
| 0.75 | 0.001 | 92.6% | 90.8% | 10.89 | 1.68% |
| 0.75 | 0.005 | 92.8% | 90.9% | 10.93 | 1.66% |
| 0.75 | 0.01 | 92.9% | 90.9% | 10.93 | 1.64% |
| 0.75 | 0.02 | 93.1% | 90.8% | 10.92 | 1.64% |
| 0.75 | 0.05 | 93.4% | 90.8% | 10.94 | 1.62% |
| 1.00 | 0.001 | 92.6% | 90.6% | 10.90 | 1.20% |
| 1.00 | 0.005 | 92.8% | 90.7% | 10.94 | 1.18% |
| 1.00 | 0.01 | 92.9% | 90.7% | 10.94 | 1.16% |
| 1.00 | 0.02 | 93.1% | 90.6% | 10.93 | 1.15% |
| 1.00 | 0.05 | 93.4% | 90.6% | 10.95 | 1.12% |
| disabled | 0.001 | 92.6% | 90.6% | 10.93 | 0.00% |
| disabled | 0.005 | 92.8% | 90.6% | 10.97 | 0.00% |
| disabled | 0.01 | 92.9% | 90.6% | 10.97 | 0.00% |
| disabled | 0.02 | 93.1% | 90.5% | 10.96 | 0.00% |
| disabled | 0.05 | 93.4% | 90.5% | 10.98 | 0.00% |

### Production Setting vs. Grid

The production configuration (`max_pitch_slope=0.50`, `switch_prob=0.005`) achieves 92.8% detection yield, 91.0% inclusion yield, and a mean $|\text{dev}|$ of 10.89 cents (2326 included notes) — inside the optimal region.

Against the librosa default `switch_prob=0.01` at the same slope: detection yield 92.9% ($\Delta = -0.1$ pp), mean $|\text{dev}|$ 10.89 cents ($\Delta = +0.00$ c).

Against a disabled slope filter at the same `switch_prob`: detection yield 92.8% ($\Delta = -0.0$ pp), mean $|\text{dev}|$ 10.97 cents ($\Delta = -0.08$ c), inclusion yield 90.6% ($\Delta = +0.3$ pp).
