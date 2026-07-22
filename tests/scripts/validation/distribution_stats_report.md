# Distributional Statistics & Quantization Resolution Floor

Generated: 2026-07-22 09:05

## Methodology

Both engines ran the full production pipeline (extract → intonation filters → DTW alignment → harmonic folding → per-note metrics) at Engine Optimal Default parameters over a deterministic subset of 15 URMP bowed-string tracks (first 5 per instrument in sorted path order) — the same subset as `validate_slope_switchprob.py` and `validate_rms_minframes.py`. Notes excluded by `is_note_excluded()` (|dev| > 100 cents or harmonic folding applied) are dropped, matching the production summary.

REAPER serves as the **control**: it returns continuous f0, so any degeneracy present in the pYIN order statistics but absent from REAPER's is caused by the pYIN output lattice rather than by the music.

### Duplicate audio in the shared subset

2 of the 15 selected stems are **byte-identical** to an earlier stem. URMP reuses one recorded take across pieces that differ only in another part:

- `AuSep_3_va_25_Pirates` is identical to `AuSep_3_va_24_Pirates`
- `AuSep_3_va_27_King` is identical to `AuSep_3_va_26_King`

Their notes are therefore counted twice in the pooled population. This does not bias the location estimates — the duplicated notes carry the same values — but it inflates $n$ and so understates every confidence interval and standard error below. A de-duplicated row (13 unique stems) is reported alongside the pooled one so the two can be compared directly. **This subset is shared with `validate_slope_switchprob.py` and `validate_rms_minframes.py`, so the same duplication applies to the results of roadmap tasks #5 and #8.**

### Effective RMS threshold (adaptive override)

`analyze_intonation()` overrides the nominal `rms_threshold` with an adaptive noise floor, `effective = max(rms_threshold, 2 × P10(RMS))`. The nominal 0.005 used here is therefore not necessarily what gated the frames these statistics are computed from, and the binding rate is reported rather than assumed.

| Engine | Nominal | Median effective | Max effective | Tracks where nominal binds |
| :--- | :---: | :---: | :---: | :---: |
| pYIN | 0.0050 | 0.0050 | 0.0181 | 9/15 (60%) |
| REAPER | 0.0050 | 0.0050 | 0.0182 | 9/15 (60%) |

## 1. Descriptive Statistics

| Statistic (cents) | pYIN | REAPER | pYIN (frame-level, legacy mode) | pYIN (de-duplicated audio) |
| :--- | :---: | :---: | :---: | :---: |
| Sample size (n) | 2326 | 2140 | 75471 | 2008 |
| Mean | +1.74 | +0.29 | +2.10 | +3.40 |
| Standard deviation | 15.69 | 18.26 | 27.50 | 15.39 |
| Standard error of mean | 0.325 | 0.395 | 0.100 | 0.343 |
| Median | -0.00 | +1.41 | +0.00 | +0.00 |
| Q1 | -10.00 | -8.27 | -10.00 | -4.99 |
| Q3 | +10.00 | +15.44 | +10.00 | +10.00 |
| IQR | 20.00 | 23.71 | 20.00 | 14.99 |
| Median absolute deviation | 10.00 | 12.08 | 10.00 | 10.00 |
| 10%-trimmed mean | +1.38 | +0.79 | +1.75 | +3.09 |
| Skewness (G1) | +0.752 | -0.001 | +0.012 | +0.655 |
| Excess kurtosis (G2) | +4.812 | +1.227 | +14.513 | +5.146 |
| Minimum | -100.00 | -90.21 | -240.00 | -100.00 |
| Maximum | +100.00 | +83.66 | +240.00 | +100.00 |

## 2. Normality of the Deviation Distribution

| Engine | Skewness (G1) | Excess kurtosis (G2) | D'Agostino-Pearson K² | p |
| :--- | :---: | :---: | :---: | :---: |
| pYIN | +0.752 | +4.812 | 431.4 | 2.14e-94 |
| REAPER | -0.001 | +1.227 | 56.3 | 5.92e-13 |
| pYIN (frame-level, legacy mode) | +0.012 | +14.513 | 15897.1 | < 1e-300 |
| pYIN (de-duplicated audio) | +0.655 | +5.146 | 353.5 | 1.71e-77 |

At these sample sizes any formal test rejects normality on a trivial departure, so the *effect sizes* carry the argument. Excess kurtosis is the operative number: it measures how much heavier the tails are than a Gaussian's, and heavy tails are precisely the condition under which the mean and SD stop describing the typical note. See `docs/images/deviation_qq.png` for the tail behaviour directly.

## 3. Quantization Resolution Floor

`librosa.pyin()` decodes f0 on a grid of `resolution=0.1` semitones. Because the instrument `fmin` values are exact integer MIDI notes, that grid lands on integer-MIDI + 0.1k, so every **frame** deviation is an exact multiple of 10 cents. A DTW **per-note** deviation is the median of those frames, which halves the step to 5 cents on even-sized note islands.

| Sample | Assumed step (c) | Distinct values | On-lattice fraction | Max residual (c) | IQR in steps | SD | Sheppard-corrected SD |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| pYIN | 5.0 | 29 | 95.9% | 0.0650 | 4.00 | 15.69 | 15.62 |
| REAPER | 5.0 | 395 | 0.0% | 2.4911 | 4.74 | 18.26 | 18.20 |
| pYIN (frame-level, legacy mode) | 10.0 | 48 | 100.0% | 0.0000 | 2.00 | 27.50 | 27.35 |
| pYIN (de-duplicated audio) | 5.0 | 29 | 96.1% | 0.0650 | 3.00 | 15.39 | 15.32 |

### Does aggregation rescue the median?

Subsamples of increasing size are drawn without replacement from the pYIN note population and the median re-estimated 200 times at each size. If the spread of those medians collapses while they remain locked on lattice multiples, the aggregate median is *stable but not resolved*.

| Subsample size | Median of medians | SD of medians | 95% range | Distinct medians observed |
| :---: | :---: | :---: | :---: | :---: |
| 25 | +0.00 | 3.58 | [-0.00, +10.00] | 10 |
| 50 | +0.00 | 1.20 | [-0.00, +0.06] | 11 |
| 100 | +0.00 | 0.56 | [-0.00, +0.00] | 5 |
| 250 | +0.00 | 0.00 | [-0.00, +0.00] | 3 |
| 500 | +0.00 | 0.00 | [-0.00, +0.00] | 3 |
| 1000 | +0.00 | 0.00 | [+0.00, +0.00] | 1 |
| 2000 | +0.00 | 0.00 | [+0.00, +0.00] | 1 |
| 2326 | +0.00 | 0.00 | [+0.00, +0.00] | 1 |

### Bootstrap intervals on the full population

A 95% percentile bootstrap interval of **zero width** is the diagnostic: it means every resample returned the same value, so the statistic cannot move and carries no resolution beyond naming one lattice cell.

| Sample | Median [95% CI] | IQR [95% CI] | 10%-trimmed mean [95% CI] | Mean [95% CI] |
| :--- | :---: | :---: | :---: | :---: |
| pYIN | +0.00 [+0.00, +0.00] | 20.00 [20.00, 20.00] | +1.38 [+0.76, +1.98] | +1.74 [+1.10, +2.37] |
| REAPER | +1.41 [-0.51, +1.41] | 23.71 [21.76, 25.67] | +0.79 [+0.02, +1.58] | +0.29 [-0.48, +1.05] |
| pYIN (frame-level, legacy mode) | +0.00 [+0.00, +0.00] | 20.00 [20.00, 20.00] | +1.75 [+1.63, +1.89] | +2.10 [+1.91, +2.30] |
| pYIN (de-duplicated audio) | +0.00 [+0.00, +0.00] | 14.99 [10.00, 20.00] | +3.09 [+2.53, +3.65] | +3.40 [+2.72, +4.06] |

**Recommendation.** On pYIN data the median and IQR are order statistics and can only return lattice values, so their intervals collapse; the mean and the 10%-trimmed mean are *averages* of many lattice values and dither off the grid, retaining full resolution. Since the distribution is heavy-tailed (§2), the ordinary mean is not representative either. The trimmed mean is the statistic that satisfies both constraints simultaneously: robust to the tails, and unaffected by the resolution floor. The median and IQR are still reported — they are what a reader expects to see, and their degeneracy is itself a reportable property of the engine — but they should not be read to two decimal places.

## 4. Bland-Altman Agreement (pYIN vs REAPER)

- **Paired notes**: 2066
- **Bias** (pYIN − REAPER): +0.70 cents
- **SD of differences**: 12.77 cents
- **95% Limits of Agreement**: [-24.34, +25.74] cents

Plot: `docs/images/bland_altman_pyin_reaper.png`. The limits of agreement, not the bias, are the number that matters: they state how far the two engines can disagree on any single note, which a correlation coefficient never reveals.

## 5. Figures

| File | Content |
| :--- | :--- |
| `docs/images/deviation_distribution.png` | Histogram + KDE per engine; pYIN against the normal its mean/SD summary assumes |
| `docs/images/deviation_qq.png` | Normal Q-Q plots showing tail behaviour |
| `docs/images/bland_altman_pyin_reaper.png` | Inter-engine agreement with 95% limits |
