"""
stats_summary.py
----------------
Distribution-aware summary statistics for intonation deviation data.

The engine historically reported only mean +/- standard deviation. Cent-deviation
distributions from bowed strings are not normal: vibrato, portamento residue and
occasional tracking artefacts produce heavy tails and asymmetry, so the mean and
standard deviation both overstate the typical error. This module supplies the
robust and shape statistics (median, IQR, skewness, kurtosis) alongside the
classical ones so both can be reported side by side.

RESOLUTION FLOOR (important)
    `librosa.pyin()` decodes f0 on a discrete pitch grid of `resolution=0.1`
    semitones. Because the instrument fmin values in `get_instrument_fmin_fmax()`
    are exact integer MIDI notes, that grid lands on integer-MIDI + 0.1k, so every
    *frame* deviation is an exact multiple of 10 cents (`PYIN_RESOLUTION_CENTS`).
    A per-note DTW deviation is the median of those frames, which halves the step
    to 5 cents on even-sized note islands. Order statistics (median, quartiles)
    computed over pYIN data therefore inherit that lattice and cannot resolve
    detail finer than it. `quantization_diagnostics()` measures how coarse the
    lattice is relative to the observed spread so a reported median or IQR can be
    qualified rather than over-read. REAPER is not affected: it returns
    continuous f0.
"""
import numpy as np
from scipy import stats as _scipy_stats

# Step of the librosa.pyin output lattice, in cents (resolution=0.1 semitones).
PYIN_RESOLUTION_CENTS = 10.0

# Effective step after the per-note median in DTW mode: an even-sized note island
# averages the two central grid values, landing halfway between them.
PYIN_NOTE_MEDIAN_RESOLUTION_CENTS = PYIN_RESOLUTION_CENTS / 2.0

# Proportion trimmed from *each* tail by the trimmed mean.
TRIM_PROPORTION = 0.10

# Statistic keys produced by descriptive_stats(), in report order.
STAT_KEYS = ("n", "mean", "std", "sem", "median", "q1", "q3", "iqr",
             "mad", "trimmed_mean", "skewness", "kurtosis", "min", "max")


def trimmed_mean(values, proportion=TRIM_PROPORTION, axis=None):
    """
    Symmetrically trimmed mean: discards `proportion` of the sample from each tail
    and averages the rest.

    This is the statistic that resolves the conflict quantized data creates. The
    deviation distributions are heavy-tailed, which argues for a robust estimator;
    but the median and quartiles are order statistics, so on the pYIN lattice they
    can only ever return a grid value and their sampling intervals collapse to zero
    width. The trimmed mean is an *average* of the surviving values, so it dithers
    off the lattice exactly as the ordinary mean does and remains resolvable at
    arbitrary precision — while still discarding the tails that make the ordinary
    mean unrepresentative. At proportion=0 it is the mean; at 0.5 it is the median.
    """
    arr = np.asarray(values, dtype=float)
    if axis is None:
        arr = arr.ravel()
        arr = arr[~np.isnan(arr)]
        if arr.size == 0:
            return np.nan
        return float(_scipy_stats.trim_mean(arr, proportion))
    return _scipy_stats.trim_mean(arr, proportion, axis=axis)


def _empty_stats():
    empty = {k: np.nan for k in STAT_KEYS}
    empty["n"] = 0
    return empty


def descriptive_stats(values):
    """
    Full descriptive summary of a 1-D sample, NaNs dropped.

    Returns a dict with:
      n         sample size after NaN removal
      mean/std  classical location and scale (std is the sample SD, ddof=1)
      sem       standard error of the mean
      median    robust location
      q1/q3/iqr robust scale (linear-interpolated quartiles)
      mad       median absolute deviation from the median (raw, not scaled)
      skewness  bias-corrected sample skewness (G1); 0 for a symmetric sample
      kurtosis  bias-corrected sample *excess* kurtosis (G2); 0 for a Gaussian
      min/max   observed range

    Skewness needs n >= 3 and kurtosis n >= 4 to be defined; below that they are
    NaN rather than a misleading 0.
    """
    arr = np.asarray(values, dtype=float).ravel()
    arr = arr[~np.isnan(arr)]
    n = arr.size

    if n == 0:
        return _empty_stats()

    q1, median, q3 = np.percentile(arr, [25, 50, 75])

    out = {
        "n": n,
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if n > 1 else np.nan,
        "sem": float(np.std(arr, ddof=1) / np.sqrt(n)) if n > 1 else np.nan,
        "median": float(median),
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(q3 - q1),
        "mad": float(np.median(np.abs(arr - median))),
        "trimmed_mean": trimmed_mean(arr),
        "skewness": float(_scipy_stats.skew(arr, bias=False)) if n >= 3 else np.nan,
        "kurtosis": float(_scipy_stats.kurtosis(arr, bias=False, fisher=True)) if n >= 4 else np.nan,
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }
    return out


def prefixed_stats(values, prefix):
    """
    descriptive_stats() with every key prefixed, e.g. prefix='dev_cents' yields
    'dev_cents_median'. Used to flatten several distributions into one results
    dict without collisions.
    """
    return {f"{prefix}_{k}": v for k, v in descriptive_stats(values).items()}


def bland_altman_stats(a, b):
    """
    Bland & Altman (1986) agreement statistics for two paired measurements of the
    same quantity — here, the same note scored by two pitch engines.

    Pairs containing a NaN in either array are dropped. Returns bias (mean signed
    difference a - b), the SD of those differences, the 95% limits of agreement
    (bias +/- 1.96 SD), and the mean/difference arrays for plotting.

    The limits of agreement describe where 95% of *individual* disagreements fall.
    They are far more informative than a correlation coefficient, which only shows
    that two engines rank notes similarly, not that they return the same number.
    """
    a = np.asarray(a, dtype=float).ravel()
    b = np.asarray(b, dtype=float).ravel()
    if a.size != b.size:
        raise ValueError(f"Paired arrays must be the same length ({a.size} vs {b.size})")

    valid = ~np.isnan(a) & ~np.isnan(b)
    a, b = a[valid], b[valid]
    n = a.size

    if n < 2:
        return {"n": n, "bias": np.nan, "sd_diff": np.nan,
                "loa_lower": np.nan, "loa_upper": np.nan,
                "means": np.array([]), "diffs": np.array([])}

    diffs = a - b
    means = (a + b) / 2.0
    bias = float(np.mean(diffs))
    sd_diff = float(np.std(diffs, ddof=1))

    return {
        "n": n,
        "bias": bias,
        "sd_diff": sd_diff,
        "loa_lower": bias - 1.96 * sd_diff,
        "loa_upper": bias + 1.96 * sd_diff,
        "means": means,
        "diffs": diffs,
    }


# Decimal places to which values are rounded before counting distinct outputs.
# Deviations reach cents through hz -> MIDI -> cents in float64, so two results
# that represent the same decoded pitch can differ in the last few bits. Counting
# raw float equality inflates the distinct-value count with representation noise
# rather than measuring the encoder, which is what this diagnostic is for.
DISTINCT_VALUE_DECIMALS = 4


def quantization_diagnostics(values, step=PYIN_RESOLUTION_CENTS):
    """
    Quantifies how badly a discrete output lattice constrains the order statistics
    of a sample. Answers the question a panel will ask about any median or IQR
    computed on pYIN output: "can that number actually move?"

    Returns:
      step               assumed lattice step, cents
      n_distinct         number of distinct observed values, counted after
                         rounding to DISTINCT_VALUE_DECIMALS so that float64
                         representation noise is not mistaken for encoder output
      lattice_fraction   fraction of samples sitting exactly on a multiple of
                         `step` (1.0 = fully quantized, ~0 = continuous)
      max_residual       largest distance from any sample to the nearest lattice
                         point; ~0 confirms the lattice, large values refute it
      iqr_in_steps       observed IQR expressed in lattice steps. This is the
                         decisive number: below ~2 the IQR is degenerate and can
                         only take a handful of values; above ~3 the lattice acts
                         as an ordinary binning error rather than a floor.
      sheppard_std       standard deviation with Sheppard's correction for
                         grouping applied, sqrt(max(var - step^2/12, 0)). The
                         correction removes the variance the lattice itself adds.
    """
    arr = np.asarray(values, dtype=float).ravel()
    arr = arr[~np.isnan(arr)]
    n = arr.size

    if n == 0:
        return {"step": step, "n": 0, "n_distinct": 0, "lattice_fraction": np.nan,
                "max_residual": np.nan, "iqr_in_steps": np.nan, "sheppard_std": np.nan}

    residual = np.abs(arr - np.round(arr / step) * step)
    # Tolerance absorbs float round-trips through hz -> MIDI -> cents.
    on_lattice = residual < 1e-6

    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1

    var = np.var(arr, ddof=1) if n > 1 else np.nan
    sheppard_var = max(var - (step ** 2) / 12.0, 0.0) if n > 1 else np.nan

    return {
        "step": step,
        "n": n,
        "n_distinct": int(np.unique(np.round(arr, DISTINCT_VALUE_DECIMALS)).size),
        "lattice_fraction": float(np.mean(on_lattice)),
        "max_residual": float(np.max(residual)),
        "iqr_in_steps": float(iqr / step) if step > 0 else np.nan,
        "sheppard_std": float(np.sqrt(sheppard_var)) if n > 1 else np.nan,
    }


def bootstrap_ci(values, statistic=np.median, n_boot=5000, alpha=0.05, seed=0):
    """
    Percentile bootstrap confidence interval for any statistic.

    Provided specifically for the median on quantized data: a parametric interval
    assumes a continuous distribution and is not defensible on a 10-cent lattice,
    whereas the bootstrap interval honestly reports the discrete set of values the
    median can take. If the interval collapses to a single lattice point, the
    median is pinned and should not be interpreted as a fine-grained measurement.
    """
    arr = np.asarray(values, dtype=float).ravel()
    arr = arr[~np.isnan(arr)]
    n = arr.size
    if n < 2:
        return {"point": float(statistic(arr)) if n else np.nan,
                "lower": np.nan, "upper": np.nan, "n_boot": 0}

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boot = statistic(arr[idx], axis=1)

    lower, upper = np.percentile(boot, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {
        "point": float(statistic(arr)),
        "lower": float(lower),
        "upper": float(upper),
        "n_boot": n_boot,
    }


def normality_tests(values):
    """
    Tests the normality assumption behind reporting mean +/- SD.

    Runs D'Agostino-Pearson (an omnibus test built directly from skewness and
    kurtosis, valid for large n) and, when n <= 5000, Shapiro-Wilk. Note that on
    the sample sizes this project works with (thousands of notes) any real test
    will reject normality on a trivial departure, so the *effect size* — the
    skewness and excess kurtosis themselves — carries the argument, and the
    p-values are reported only for completeness.
    """
    arr = np.asarray(values, dtype=float).ravel()
    arr = arr[~np.isnan(arr)]
    n = arr.size

    out = {"n": n, "dagostino_stat": np.nan, "dagostino_p": np.nan,
           "shapiro_stat": np.nan, "shapiro_p": np.nan}

    if n >= 8:
        stat, p = _scipy_stats.normaltest(arr)
        out["dagostino_stat"], out["dagostino_p"] = float(stat), float(p)

    if 3 <= n <= 5000:
        stat, p = _scipy_stats.shapiro(arr)
        out["shapiro_stat"], out["shapiro_p"] = float(stat), float(p)

    return out
