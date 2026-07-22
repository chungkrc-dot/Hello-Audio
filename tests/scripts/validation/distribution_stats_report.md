# Distributional Statistics & Quantization Resolution Floor

Generated: 2026-07-22 21:37

## Methodology

Both engines ran the full production pipeline (extract → intonation filters → DTW alignment → harmonic folding → per-note metrics) at Engine Optimal Default parameters over all 41 bowed-string stems of the URMP corpus — the same set as `validate_slope_switchprob.py` and `validate_rms_minframes.py`. Notes excluded by `is_note_excluded()` (|dev| > 100 cents or harmonic folding applied) are dropped, matching the production summary.

REAPER serves as the **control**: it returns continuous f0, so any degeneracy present in the pYIN order statistics but absent from REAPER's is caused by the pYIN output lattice rather than by the music.

### Effective RMS threshold (adaptive override)

`analyze_intonation()` overrides the nominal `rms_threshold` with an adaptive noise floor, `effective = max(rms_threshold, 2 × P10(RMS))`. The nominal 0.005 used here is therefore not necessarily what gated the frames these statistics are computed from, and the binding rate is reported rather than assumed.

| Engine | Nominal | Median effective | Max effective | Tracks where nominal binds |
| :--- | :---: | :---: | :---: | :---: |
| pYIN | 0.0050 | 0.0058 | 0.0181 | 18/41 (44%) |
| REAPER | 0.0050 | 0.0058 | 0.0182 | 18/41 (44%) |

## 1. Descriptive Statistics

| Statistic (cents) | pYIN | REAPER | pYIN (frame-level, legacy mode) |
| :--- | :---: | :---: | :---: |
| Sample size (n) | 8197 | 6863 | 284881 |
| Mean | +7.13 | +6.57 | +6.29 |
| Standard deviation | 16.35 | 18.91 | 32.38 |
| Standard error of mean | 0.181 | 0.228 | 0.061 |
| Median | +10.00 | +9.79 | +10.00 |
| Q1 | -0.00 | -6.96 | -0.00 |
| Q3 | +20.00 | +19.35 | +20.00 |
| IQR | 20.00 | 26.32 | 20.00 |
| Median absolute deviation | 10.00 | 11.52 | 10.00 |
| 10%-trimmed mean | +7.04 | +7.09 | +6.86 |
| Skewness (G1) | -0.253 | -0.382 | -0.214 |
| Excess kurtosis (G2) | +4.175 | +1.511 | +10.477 |
| Minimum | -100.00 | -98.55 | -350.00 |
| Maximum | +100.00 | +93.04 | +310.00 |

## 2. Normality of the Deviation Distribution

| Engine | Skewness (G1) | Excess kurtosis (G2) | D'Agostino-Pearson K² | p |
| :--- | :---: | :---: | :---: | :---: |
| pYIN | -0.253 | +4.175 | 867.3 | 4.67e-189 |
| REAPER | -0.382 | +1.511 | 386.8 | 9.93e-85 |
| pYIN (frame-level, legacy mode) | -0.214 | +10.477 | 52833.9 | < 1e-300 |

At these sample sizes any formal test rejects normality on a trivial departure, so the *effect sizes* carry the argument. Excess kurtosis is the operative number: it measures how much heavier the tails are than a Gaussian's, and heavy tails are precisely the condition under which the mean and SD stop describing the typical note. See `docs/images/deviation_qq.png` for the tail behaviour directly.

## 3. Quantization Resolution Floor

`librosa.pyin()` decodes f0 on a grid of `resolution=0.1` semitones. Because the instrument `fmin` values are exact integer MIDI notes, that grid lands on integer-MIDI + 0.1k, so every **frame** deviation is an exact multiple of 10 cents. A DTW **per-note** deviation is the median of those frames, which halves the step to 5 cents on even-sized note islands.

| Sample | Assumed step (c) | Distinct values | On-lattice fraction | Max residual (c) | IQR in steps | SD | Sheppard-corrected SD |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| pYIN | 5.0 | 56 | 95.4% | 2.3948 | 4.00 | 16.35 | 16.28 |
| REAPER | 5.0 | 1052 | 0.0% | 2.4911 | 5.26 | 18.91 | 18.85 |
| pYIN (frame-level, legacy mode) | 10.0 | 63 | 100.0% | 0.0000 | 2.00 | 32.38 | 32.25 |

### Does aggregation rescue the median?

Subsamples of increasing size are drawn without replacement from the pYIN note population and the median re-estimated 200 times at each size. If the spread of those medians collapses while they remain locked on lattice multiples, the aggregate median is *stable but not resolved*.

| Subsample size | Median of medians | SD of medians | 95% range | Distinct medians observed |
| :---: | :---: | :---: | :---: | :---: |
| 25 | +10.00 | 4.69 | [-0.00, +10.00] | 12 |
| 50 | +10.00 | 4.24 | [+0.00, +10.00] | 15 |
| 100 | +10.00 | 3.76 | [+0.00, +10.00] | 16 |
| 250 | +10.00 | 2.37 | [+0.00, +10.00] | 11 |
| 500 | +10.00 | 1.13 | [+5.01, +10.00] | 10 |
| 1000 | +10.00 | 0.00 | [+10.00, +10.00] | 3 |
| 2000 | +10.00 | 0.00 | [+10.00, +10.00] | 2 |
| 8197 | +10.00 | 0.00 | [+10.00, +10.00] | 1 |

### Bootstrap intervals on the full population

A 95% percentile bootstrap interval of **zero width** is the diagnostic: it means every resample returned the same value, so the statistic cannot move and carries no resolution beyond naming one lattice cell.

| Sample | Median [95% CI] | IQR [95% CI] | 10%-trimmed mean [95% CI] | Mean [95% CI] |
| :--- | :---: | :---: | :---: | :---: |
| pYIN | +10.00 [+10.00, +10.00] | 20.00 [20.00, 20.00] | +7.04 [+6.70, +7.38] | +7.13 [+6.77, +7.47] |
| REAPER | +9.79 [+9.79, +11.96] | 26.32 [26.32, 27.11] | +7.09 [+6.67, +7.51] | +6.57 [+6.12, +7.01] |
| pYIN (frame-level, legacy mode) | +10.00 [+10.00, +10.00] | 20.00 [20.00, 20.00] | +6.86 [+6.78, +6.93] | +6.29 [+6.18, +6.41] |

**Recommendation.** On pYIN data the median and IQR are order statistics and can only return lattice values, so their intervals collapse; the mean and the 10%-trimmed mean are *averages* of many lattice values and dither off the grid, retaining full resolution. Since the distribution is heavy-tailed (§2), the ordinary mean is not representative either. The trimmed mean is the statistic that satisfies both constraints simultaneously: robust to the tails, and unaffected by the resolution floor. The median and IQR are still reported — they are what a reader expects to see, and their degeneracy is itself a reportable property of the engine — but they should not be read to two decimal places.

## 4. Bland-Altman Agreement (pYIN vs REAPER)

- **Paired notes**: 6639
- **Bias** (pYIN − REAPER): -0.18 cents
- **SD of differences**: 13.06 cents
- **95% Limits of Agreement**: [-25.78, +25.41] cents

Plot: `docs/images/bland_altman_pyin_reaper.png`. The limits of agreement, not the bias, are the number that matters: they state how far the two engines can disagree on any single note, which a correlation coefficient never reveals.

## 5. Figures

| File | Content |
| :--- | :--- |
| `docs/images/deviation_distribution.png` | Histogram + KDE per engine; pYIN against the normal its mean/SD summary assumes |
| `docs/images/deviation_qq.png` | Normal Q-Q plots showing tail behaviour |
| `docs/images/bland_altman_pyin_reaper.png` | Inter-engine agreement with 95% limits |
