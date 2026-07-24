"""
Functional test: distributional summary statistics.

Verifies the statistics added in roadmap task #6 against distributions whose
population values are known in closed form, plus the two behaviours that motivated
the task: correct handling of the pYIN output lattice, and the propagation of the
new statistics through analyze_intonation() and summarize_dtw_metrics().
"""
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.stats_summary import (
    descriptive_stats, bland_altman_stats, quantization_diagnostics,
    bootstrap_ci, normality_tests,
    PYIN_RESOLUTION_CENTS, PYIN_NOTE_MEDIAN_RESOLUTION_CENTS
)
from src.midi_alignment import summarize_dtw_metrics, pair_note_deviations


def test_descriptive_stats_known_values():
    """Statistics of a fixed small sample, checked against hand-computed values."""
    x = np.array([1.0, 2.0, 3.0, 4.0, 100.0])

    s = descriptive_stats(x)
    assert s['n'] == 5
    assert np.isclose(s['mean'], 22.0)
    assert np.isclose(s['median'], 3.0)
    assert np.isclose(s['q1'], 2.0) and np.isclose(s['q3'], 4.0)
    assert np.isclose(s['iqr'], 2.0)
    assert np.isclose(s['mad'], 1.0)
    assert np.isclose(s['min'], 1.0) and np.isclose(s['max'], 100.0)
    # Sample SD, ddof=1.
    assert np.isclose(s['std'], np.std(x, ddof=1))
    assert np.isclose(s['sem'], np.std(x, ddof=1) / np.sqrt(5))
    # One extreme value on the right: strongly positive skew, and the mean sits
    # far above the median. This is exactly the failure mode the task addresses.
    assert s['skewness'] > 1.0
    assert s['mean'] > 7 * s['median']

    print(f"Known sample: mean={s['mean']:.2f} median={s['median']:.2f} "
          f"IQR={s['iqr']:.2f} G1={s['skewness']:+.3f} G2={s['kurtosis']:+.3f}")


def test_descriptive_stats_gaussian_recovers_population():
    """On a large Gaussian sample the shape statistics must sit near zero."""
    rng = np.random.default_rng(42)
    x = rng.normal(loc=5.0, scale=12.0, size=200_000)

    s = descriptive_stats(x)
    assert abs(s['mean'] - 5.0) < 0.2
    assert abs(s['std'] - 12.0) < 0.2
    assert abs(s['median'] - 5.0) < 0.2
    # IQR of a normal is 2 * 0.6745 * sigma.
    assert abs(s['iqr'] - 1.349 * 12.0) < 0.3
    assert abs(s['skewness']) < 0.05
    assert abs(s['kurtosis']) < 0.05

    print(f"Gaussian(5, 12): median={s['median']:.3f} IQR={s['iqr']:.3f} "
          f"G1={s['skewness']:+.4f} G2={s['kurtosis']:+.4f}")


def test_descriptive_stats_edge_cases():
    """Empty, single-value and NaN-laden inputs must not raise."""
    empty = descriptive_stats([])
    assert empty['n'] == 0 and np.isnan(empty['median'])

    single = descriptive_stats([7.0])
    assert single['n'] == 1
    assert np.isclose(single['median'], 7.0)
    assert np.isnan(single['std'])
    # Undefined rather than a misleading zero.
    assert np.isnan(single['skewness']) and np.isnan(single['kurtosis'])

    with_nans = descriptive_stats([1.0, np.nan, 3.0, np.nan])
    assert with_nans['n'] == 2
    assert np.isclose(with_nans['mean'], 2.0)

    print("Edge cases (empty / single / NaN-laden) handled without error.")


def test_quantization_detects_the_pyin_lattice():
    """
    The diagnostic must identify a 10-cent grid as fully quantized and continuous
    data as not quantized. This is the check that keeps the resolution-floor
    argument honest.
    """
    rng = np.random.default_rng(0)
    continuous = rng.normal(0, 25, 5000)
    quantized = np.round(continuous / PYIN_RESOLUTION_CENTS) * PYIN_RESOLUTION_CENTS

    q = quantization_diagnostics(quantized, step=PYIN_RESOLUTION_CENTS)
    assert np.isclose(q['lattice_fraction'], 1.0)
    assert q['max_residual'] < 1e-9
    # Sheppard's correction removes the variance the grid itself adds, so the
    # corrected SD must sit below the raw SD and closer to the true sigma.
    assert q['sheppard_std'] < np.std(quantized, ddof=1)
    assert abs(q['sheppard_std'] - 25.0) < abs(np.std(quantized, ddof=1) - 25.0)

    c = quantization_diagnostics(continuous, step=PYIN_RESOLUTION_CENTS)
    assert c['lattice_fraction'] < 0.01
    assert c['n_distinct'] > q['n_distinct']

    print(f"Quantized: {q['n_distinct']} distinct, {q['lattice_fraction']*100:.1f}% on-grid, "
          f"SD {np.std(quantized, ddof=1):.2f} -> Sheppard {q['sheppard_std']:.2f}")
    print(f"Continuous: {c['n_distinct']} distinct, {c['lattice_fraction']*100:.1f}% on-grid")


def test_distinct_count_ignores_float_representation_noise():
    """
    Regression: `n_distinct` is the headline evidence that pYIN quantizes its
    output, so it must count *decoded pitches*, not float64 bit patterns.

    Deviations reach cents through Hz -> MIDI -> cents in floating point, so two
    results representing the same grid value can differ in the last few bits. A
    naive unique() on the raw floats reported more than double the true count.
    """
    from src.stats_summary import quantization_diagnostics

    rng = np.random.default_rng(5)
    clean = np.repeat([-20.0, -10.0, 0.0, 10.0, 20.0], 400)
    # Perturb by ~1e-13, the scale of the hz->midi->cents round trip.
    noisy = clean + rng.normal(0, 1e-13, clean.size)

    assert np.unique(noisy).size > 500, "test premise: raw floats look near-all-distinct"

    q = quantization_diagnostics(noisy, step=PYIN_RESOLUTION_CENTS)
    assert q['n_distinct'] == 5, f"expected 5 decoded values, got {q['n_distinct']}"
    # The noise must not disturb the lattice verdict either.
    assert np.isclose(q['lattice_fraction'], 1.0)

    print(f"Noisy lattice sample: raw unique()={np.unique(noisy).size}, "
          f"n_distinct={q['n_distinct']} (true value 5)")


def test_aggregation_pins_the_median_rather_than_freeing_it():
    """
    The finding that drove this task, and it runs opposite to the intuition the
    roadmap started from: aggregating over a *larger* note population does not
    rescue the median from the output lattice, it locks it on harder.

    The median's sampling error is roughly 1.253 * sigma / sqrt(n). While that
    error exceeds the lattice step the median can still land on different grid
    points from sample to sample, so a bootstrap interval spans several cells.
    Once sqrt(n) drives it below the step, every resample returns the same grid
    point: the median becomes perfectly stable and completely unresolved. It is
    then a label for one lattice cell, not a measurement.
    """
    rng = np.random.default_rng(1)
    sigma = 60.0

    def quantize(a):
        return np.round(a / PYIN_RESOLUTION_CENTS) * PYIN_RESOLUTION_CENTS

    small = quantize(rng.normal(0.0, sigma, 25))
    large = quantize(rng.normal(0.0, sigma, 4000))

    ci_small = bootstrap_ci(small, np.median, n_boot=2000)
    ci_large = bootstrap_ci(large, np.median, n_boot=2000)

    se_small = 1.253 * sigma / np.sqrt(25)
    se_large = 1.253 * sigma / np.sqrt(4000)
    assert se_small > PYIN_RESOLUTION_CENTS > se_large, "test premise"

    # Small n: sampling error exceeds the step, so the interval spans grid cells.
    assert ci_small['upper'] - ci_small['lower'] >= PYIN_RESOLUTION_CENTS
    # Large n: sampling error is below the step, so the interval collapses.
    assert np.isclose(ci_large['lower'], ci_large['upper'])
    assert np.isclose(ci_large['point'] % PYIN_RESOLUTION_CENTS, 0.0)

    print(f"n=25   (SE~{se_small:.1f}c > {PYIN_RESOLUTION_CENTS:.0f}c step): "
          f"median CI [{ci_small['lower']:+.1f}, {ci_small['upper']:+.1f}] — resolved")
    print(f"n=4000 (SE~{se_large:.1f}c < {PYIN_RESOLUTION_CENTS:.0f}c step): "
          f"median CI [{ci_large['lower']:+.1f}, {ci_large['upper']:+.1f}] — pinned")
    print("Aggregation makes the pinning worse, not better.")


def test_trimmed_mean_escapes_the_lattice_and_resists_tails():
    """
    The trimmed mean is the statistic this task recommends, and it has to earn that
    on both counts at once:

      1. It must stay resolvable on quantized data, where the median is pinned —
         because it averages the surviving values rather than selecting one.
      2. It must resist heavy tails, where the ordinary mean is dragged off —
         because it discards them.
    """
    from src.stats_summary import trimmed_mean, TRIM_PROPORTION

    rng = np.random.default_rng(11)
    quantized = np.round(rng.normal(3.0, 25.0, 4000) / PYIN_RESOLUTION_CENTS) * PYIN_RESOLUTION_CENTS

    # 1. Resolution: the median is stuck on the grid, the trimmed mean is not.
    ci_median = bootstrap_ci(quantized, np.median, n_boot=1500)
    ci_trimmed = bootstrap_ci(quantized, trimmed_mean, n_boot=1500)
    assert np.isclose(ci_median['lower'], ci_median['upper'])
    assert ci_trimmed['upper'] - ci_trimmed['lower'] > 0.1
    assert not np.isclose(trimmed_mean(quantized) % PYIN_RESOLUTION_CENTS, 0.0)

    # 2. Robustness: inject a contaminating tail into a clean sample.
    clean = rng.normal(0.0, 10.0, 2000)
    contaminated = np.concatenate([clean, rng.normal(300.0, 10.0, 100)])
    assert abs(np.mean(contaminated)) > 10.0, "the tail must actually move the mean"
    # The trimmed mean must track the median — the reference robust estimator —
    # rather than the mean, which the 5% contamination drags an order of magnitude
    # away from the true centre.
    assert abs(trimmed_mean(contaminated)) < 2.0
    assert abs(trimmed_mean(contaminated) - np.median(contaminated)) < 1.0
    assert abs(trimmed_mean(contaminated)) < abs(np.mean(contaminated)) / 5

    # Degenerate proportions bracket the two familiar estimators.
    assert np.isclose(trimmed_mean(clean, proportion=0.0), np.mean(clean))

    print(f"Quantized (n=4000): median CI width "
          f"{ci_median['upper'] - ci_median['lower']:.2f} (pinned), "
          f"{TRIM_PROPORTION:.0%}-trimmed mean CI width "
          f"{ci_trimmed['upper'] - ci_trimmed['lower']:.2f} (resolved)")
    print(f"Contaminated sample: mean {np.mean(contaminated):+.2f}, "
          f"trimmed mean {trimmed_mean(contaminated):+.2f} (true centre 0)")


def test_bland_altman_recovers_a_known_offset():
    """A constant offset between two methods must appear as the bias, with the
    limits of agreement bracketing the injected noise."""
    rng = np.random.default_rng(7)
    truth = rng.normal(0, 20, 4000)
    a = truth + 3.0
    b = truth + rng.normal(0, 5.0, 4000)

    ba = bland_altman_stats(a, b)
    assert ba['n'] == 4000
    assert abs(ba['bias'] - 3.0) < 0.3
    assert abs(ba['sd_diff'] - 5.0) < 0.3
    assert ba['loa_lower'] < ba['bias'] < ba['loa_upper']
    assert abs((ba['loa_upper'] - ba['loa_lower']) - 2 * 1.96 * 5.0) < 1.2

    # NaNs in either array drop the whole pair, keeping the comparison paired.
    a2 = a.copy(); a2[:10] = np.nan
    b2 = b.copy(); b2[5:15] = np.nan
    assert bland_altman_stats(a2, b2)['n'] == 4000 - 15

    print(f"Bland-Altman: bias {ba['bias']:+.3f} (injected +3.00), "
          f"LoA [{ba['loa_lower']:+.2f}, {ba['loa_upper']:+.2f}]")


def test_normality_tests_discriminate():
    """A Gaussian sample must not be flagged; a heavy-tailed one must be."""
    rng = np.random.default_rng(3)
    gauss = normality_tests(rng.normal(0, 1, 3000))
    heavy = normality_tests(rng.standard_t(df=3, size=3000))

    assert gauss['dagostino_p'] > 0.01
    assert heavy['dagostino_p'] < 1e-6

    print(f"Normality p-values: Gaussian {gauss['dagostino_p']:.3f}, "
          f"heavy-tailed {heavy['dagostino_p']:.2e}")


def test_dtw_summary_reports_the_new_statistics():
    """
    summarize_dtw_metrics() must aggregate only detected, non-excluded notes and
    expose the full statistic set under the flattened dev_cents_* keys.
    """
    devs = [10.0, -20.0, 30.0, 0.0, np.nan, 50.0, -10.0, 20.0]
    metrics = [
        {'Note_Index': i + 1, 'Expected_Note': 'A4', 'Deviation_Cents': d,
         'Deviation_Hz': d * 0.25, 'Median_RMS_dBFS': -20.0, 'Median_RMS_dBA': -19.0}
        for i, d in enumerate(devs)
    ]

    s = summarize_dtw_metrics(metrics, excluded_indices=[6])

    assert s['total_expected'] == 8
    assert s['detected_count'] == 7          # one NaN
    assert s['included_count'] == 6          # minus the excluded note 6
    assert s['dev_cents_n'] == 6

    kept = np.array([10.0, -20.0, 30.0, 0.0, -10.0, 20.0])
    assert np.isclose(s['dev_cents_mean'], kept.mean())
    assert np.isclose(s['dev_cents_median'], np.median(kept))
    assert np.isclose(s['dev_cents_iqr'],
                      np.percentile(kept, 75) - np.percentile(kept, 25))
    for key in ('dev_cents_skewness', 'dev_cents_kurtosis',
                'dev_hz_median', 'dev_hz_iqr'):
        assert key in s, f"missing {key}"

    # An empty input must still return the full key set rather than a bare dict,
    # so downstream table rendering has nothing to special-case.
    empty = summarize_dtw_metrics([])
    assert empty['dev_cents_n'] == 0 and np.isnan(empty['dev_cents_median'])

    print(f"DTW summary: n={s['dev_cents_n']} mean={s['dev_cents_mean']:+.2f} "
          f"median={s['dev_cents_median']:+.2f} IQR={s['dev_cents_iqr']:.2f}")


def test_pairing_keeps_only_mutually_detected_notes():
    """Bland-Altman input must be paired note-for-note, not merely equal in length."""
    a = [{'Note_Index': 1, 'Expected_Note': 'A4', 'Deviation_Cents': 10.0},
         {'Note_Index': 2, 'Expected_Note': 'B4', 'Deviation_Cents': np.nan},
         {'Note_Index': 3, 'Expected_Note': 'C5', 'Deviation_Cents': -5.0},
         {'Note_Index': 4, 'Expected_Note': 'D5', 'Deviation_Cents': 20.0}]
    b = [{'Note_Index': 1, 'Expected_Note': 'A4', 'Deviation_Cents': 12.0},
         {'Note_Index': 2, 'Expected_Note': 'B4', 'Deviation_Cents': 3.0},
         {'Note_Index': 3, 'Expected_Note': 'C5', 'Deviation_Cents': np.nan},
         {'Note_Index': 4, 'Expected_Note': 'D5', 'Deviation_Cents': 18.0}]

    va, vb, labels = pair_note_deviations(a, b, excluded_indices=[4])
    # Note 2 missed by a, note 3 missed by b, note 4 excluded -> only note 1 survives.
    assert va.size == vb.size == 1
    assert np.isclose(va[0], 10.0) and np.isclose(vb[0], 12.0)
    assert labels == ['Note 1 (A4)']

    print(f"Pairing kept {va.size} of 4 notes: {labels}")


def test_paired_delta_removes_drift_the_independent_means_delta_shows():
    """
    The headline case for the paired delta. True effect is zero: both conditions
    play notes 1-6 identically. But the "plugged" take misses notes 5-6, which
    happen to be sharp. The difference of independent means then shows a phantom
    effect, while the paired delta over the shared notes correctly reads zero.
    """
    from src.midi_alignment import (paired_delta_summary, paired_coverage_advisory,
                                     summarize_dtw_metrics)

    devs = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 40.0, 6: 40.0}  # notes 5-6 sharp
    unp = [{'Note_Index': i, 'Expected_Note': 'A4', 'Deviation_Cents': d,
            'Deviation_Hz': d * 0.25, 'Median_RMS_dBFS': -20.0, 'Median_RMS_dBA': -19.0}
           for i, d in devs.items()]
    # Plugged is identical on the notes it caught, but missed 5 and 6 (NaN).
    plg = [{'Note_Index': i, 'Expected_Note': 'A4',
            'Deviation_Cents': (d if i <= 4 else np.nan),
            'Deviation_Hz': (d * 0.25 if i <= 4 else np.nan),
            'Median_RMS_dBFS': (-20.0 if i <= 4 else np.nan),
            'Median_RMS_dBA': (-19.0 if i <= 4 else np.nan)}
           for i, d in devs.items()]

    # Independent means: unplugged averages all six (mean +13.3), plugged the
    # four it caught (mean 0) -> a phantom +13.3 c "effect".
    u = summarize_dtw_metrics(unp)
    p = summarize_dtw_metrics(plg)
    indep_delta = u['dev_cents_mean'] - p['dev_cents_mean']
    assert indep_delta > 10.0  # the drift the naive delta invents

    # Paired: only notes 1-4 are shared; every per-note difference is 0.
    pdelta = paired_delta_summary(unp, plg)
    assert pdelta['n_paired'] == 4
    assert np.isclose(pdelta['deltas']['mean intonation deviation (cents)'], 0.0)
    assert np.isclose(pdelta['deltas']['mean RMS amplitude (dB FS)'], 0.0)
    assert np.isclose(pdelta['deltas']['mean intonation deviation (Hz)'], 0.0)

    # The yield gap (100% vs 67%) must trip the advisory.
    adv = paired_coverage_advisory(u['pct_detected'], p['pct_detected'],
                                   pdelta['n_paired'], pdelta['n_detected_a'],
                                   pdelta['n_detected_b'])
    assert adv is not None and 'paired' in adv.lower()

    # When both takes catch the same notes, the advisory stays silent and the two
    # deltas coincide.
    quiet = paired_coverage_advisory(95.0, 96.0, 40, 40, 41)
    assert quiet is None

    print(f"Paired delta {pdelta['deltas']['mean intonation deviation (cents)']:+.1f}c "
          f"(true 0) vs independent-means {indep_delta:+.1f}c (phantom)")


def test_note_median_lattice_constant_is_half_the_frame_lattice():
    """Guards the constant the resolution-floor argument in the manual rests on."""
    assert np.isclose(PYIN_NOTE_MEDIAN_RESOLUTION_CENTS, PYIN_RESOLUTION_CENTS / 2.0)
    assert np.isclose(PYIN_RESOLUTION_CENTS, 10.0)


if __name__ == "__main__":
    tests = [
        test_descriptive_stats_known_values,
        test_descriptive_stats_gaussian_recovers_population,
        test_descriptive_stats_edge_cases,
        test_quantization_detects_the_pyin_lattice,
        test_distinct_count_ignores_float_representation_noise,
        test_aggregation_pins_the_median_rather_than_freeing_it,
        test_trimmed_mean_escapes_the_lattice_and_resists_tails,
        test_bland_altman_recovers_a_known_offset,
        test_normality_tests_discriminate,
        test_dtw_summary_reports_the_new_statistics,
        test_pairing_keeps_only_mutually_detected_notes,
        test_paired_delta_removes_drift_the_independent_means_delta_shows,
        test_note_median_lattice_constant_is_half_the_frame_lattice,
    ]
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        t()
    print(f"\nPASSED: {len(tests)} distributional statistics tests.")
