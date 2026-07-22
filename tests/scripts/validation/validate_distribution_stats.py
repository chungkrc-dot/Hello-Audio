"""
Distributional Statistics & Quantization Resolution Floor
=========================================================
Task #6 of the academic validation roadmap. Two questions, one run:

  1. Are the intonation deviation distributions normal? The engine historically
     reported mean +/- SD, which is only a sufficient summary for a Gaussian. This
     script measures skewness, excess kurtosis and formal normality tests on the
     real URMP note population and reports what the robust alternatives
     (median, IQR) say instead.

  2. Is a median or IQR computed on pYIN output meaningful at all? Tasks #5 and
     #8 both returned a median |Deviation_Cents| of exactly 10.00 in every single
     ablation cell, because `librosa.pyin()` decodes f0 on a 0.1-semitone grid.
     Before task #6 can report medians and IQRs as headline statistics it has to
     establish where the resolution floor sits and whether aggregation over a
     large note population escapes it.

REAPER is the control. It returns continuous f0 with no output lattice, so any
degeneracy present in the pYIN statistics but absent from REAPER's is attributable
to quantization rather than to the music. Both engines run the full production
pipeline over the same deterministic 15-track subset used by
`validate_slope_switchprob.py` and `validate_rms_minframes.py`, so the three
studies are directly comparable.

The effective RMS threshold is instrumented per track: `analyze_intonation()`
silently overrides the nominal value with an adaptive noise floor
(max(rms_threshold, 2 x P10(RMS))), so the nominal 0.005 is not necessarily what
gated the frames these statistics are computed from.

Outputs:
    distribution_stats_report.md    full write-up
    distribution_stats_results.json machine-readable sidecar
    docs/images/deviation_distribution.png
    docs/images/deviation_qq.png
    docs/images/bland_altman_pyin_reaper.png

Usage:
    python tests/scripts/validation/validate_distribution_stats.py
"""

import os
import sys
import gc
import json
import hashlib
import numpy as np
import warnings
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import stats as scipy_stats

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.pitch_engine import extract_pitch_and_rms, analyze_intonation
from src.midi_parser import parse_midi_with_timing, load_part_notes, MidiTrackError
from src.midi_alignment import (
    process_dtw_alignment, calculate_dtw_metrics, is_note_excluded,
    included_note_deviations, pair_note_deviations
)
from src.stats_summary import (
    descriptive_stats, bland_altman_stats, quantization_diagnostics,
    bootstrap_ci, normality_tests, trimmed_mean,
    PYIN_RESOLUTION_CENTS, PYIN_NOTE_MEDIAN_RESOLUTION_CENTS, TRIM_PROPORTION
)

REPORT_PATH = os.path.join(SCRIPT_DIR, 'distribution_stats_report.md')
RESULTS_JSON = os.path.join(SCRIPT_DIR, 'distribution_stats_results.json')
IMAGES_DIR = os.path.join(PROJECT_ROOT, 'docs', 'images')

FIG_DISTRIBUTION = os.path.join(IMAGES_DIR, 'deviation_distribution.png')
FIG_QQ = os.path.join(IMAGES_DIR, 'deviation_qq.png')
FIG_BLAND_ALTMAN = os.path.join(IMAGES_DIR, 'bland_altman_pyin_reaper.png')

ENGINES = {
    "pYIN":   {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 2, "switch_prob": 0.005},
    "REAPER": {"rms_threshold": 0.005, "max_pitch_slope": 0.50, "min_frames": 4, "switch_prob": 0.005},
}

TOGGLES = {
    "freq_limits": True,
    "slope_filter": True,
    "duration_filter": True,
    "locked_target": True,
    "harmonic_folding": True,
    "force_global": True,
}

INST_MAP = {"vn": "Violin", "va": "Viola", "vc": "Cello"}
REFERENCE_PITCH_HZ = 440.0
TRACKS_PER_INSTRUMENT = 5

# Note-population sizes at which the aggregate median is re-estimated, to see
# whether its bootstrap interval ever narrows below the output lattice.
CONVERGENCE_SIZES = [25, 50, 100, 250, 500, 1000, 2000]

COLORS = {"pYIN": "#1f77b4", "REAPER": "#ff7f0e"}

# Decimal places retained for the raw deviation samples stored in the sidecar.
SAMPLE_DECIMALS = 4


def _round(arr):
    """Deviation sample as a plain rounded list, for compact JSON serialisation."""
    return np.round(np.asarray(arr, dtype=float), SAMPLE_DECIMALS).tolist()


def encode_sample(arr):
    """
    Lossless value/count encoding of an unordered deviation sample.

    Quantized data is enormously redundant — the 75,471 frame-level deviations take
    only 128 distinct values — so storing them as a value/count map rather than a
    flat list shrinks the sidecar by two orders of magnitude with no loss. Sample
    order is discarded, which is safe here: every statistic and figure computed
    from these samples is order-independent. Paired arrays are *not* encoded this
    way, because their note-for-note correspondence is the whole point.
    """
    arr = np.round(np.asarray(arr, dtype=float), SAMPLE_DECIMALS)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return {'values': [], 'counts': []}
    values, counts = np.unique(arr, return_counts=True)
    return {'values': values.tolist(), 'counts': counts.tolist()}


def decode_sample(encoded):
    """Inverse of encode_sample(); also accepts a plain list from older sidecars."""
    if isinstance(encoded, dict):
        return np.repeat(np.asarray(encoded['values'], dtype=float),
                         np.asarray(encoded['counts'], dtype=int))
    return np.asarray(encoded, dtype=float)


# ==========================================
# Pipeline
# ==========================================

def effective_rms_threshold(rms, rms_threshold):
    """
    Reproduces the adaptive noise-floor override inside `analyze_intonation()`:
    effective = max(rms_threshold, 2 x P10(RMS)). Returned so the report can state
    what actually gated the frames rather than what was nominally requested.
    """
    if len(rms) == 0:
        return rms_threshold, False
    floor = float(np.percentile(rms, 10)) * 2.0
    return max(rms_threshold, floor), rms_threshold >= floor


def run_pipeline(audio_path, midi_notes, instrument, engine, params):
    """Full production path: extract -> filters -> DTW -> folding -> per-note metrics."""
    with open(audio_path, 'rb') as af:
        y, sr, f0, voiced_flag, rms, voicing_prob = extract_pitch_and_rms(
            af,
            instrument=instrument,
            switch_prob=params['switch_prob'],
            enable_freq_limits=TOGGLES['freq_limits'],
            pitch_engine=engine
        )

    eff_rms, binding = effective_rms_threshold(rms, params['rms_threshold'])

    res = analyze_intonation(
        y, sr, f0, voiced_flag, rms,
        rms_threshold=params['rms_threshold'],
        min_frames=params['min_frames'],
        max_pitch_slope=params['max_pitch_slope'],
        toggles=TOGGLES,
        voicing_prob=voicing_prob,
        reference_pitch_hz=REFERENCE_PITCH_HZ
    )
    final_mask = res['final_mask']

    # Legacy-mode frame deviations, kept separately: these are the raw frame-level
    # values that sit directly on the pYIN lattice, before any per-note median.
    legacy_frame_devs = np.asarray(res.get('deviation_cents_list', []), dtype=float)

    time_array, expected, warped, _, folded_f0_hz, _, _, correction_array = process_dtw_alignment(
        midi_notes, f0, y, sr, final_mask, TOGGLES, params['max_pitch_slope']
    )

    dtw_metrics = calculate_dtw_metrics(
        midi_notes, time_array, folded_f0_hz, rms, final_mask, warped,
        correction_array, voicing_prob, REFERENCE_PITCH_HZ
    )

    del y, sr, f0, voiced_flag, rms, voicing_prob, res, final_mask
    del time_array, expected, warped, folded_f0_hz, correction_array
    gc.collect()

    return dtw_metrics, legacy_frame_devs, eff_rms, binding


def auto_excluded_indices(metrics):
    """Note indices dropped by the production exclusion rule (|dev|>100c or folded)."""
    return [m['Note_Index'] for m in metrics if is_note_excluded(m)]


# ==========================================
# Dataset discovery (shared conventions)
# ==========================================

def discover_tracks(dataset_dir):
    tracks = []
    for audio_path in sorted(dataset_dir.rglob("AuSep_*.wav")):
        stem = audio_path.stem
        if stem.startswith('AuMix'):
            continue
        parts = stem.split('_')
        try:
            target_track = int(parts[1])
            inst_code = parts[2]
        except (IndexError, ValueError):
            continue
        instrument = INST_MAP.get(inst_code)
        if instrument is None:
            continue
        midi_files = list(audio_path.parent.glob("*.mid"))
        if not midi_files:
            print(f"  [!] No MIDI found for {stem}, skipping")
            continue
        tracks.append({
            'audio_path': str(audio_path),
            'midi_path': str(midi_files[0]),
            'stem': stem,
            'target_track': target_track,
            'instrument': instrument,
        })
    return tracks


def select_subset(tracks, per_instrument):
    """First `per_instrument` tracks of each instrument, in sorted path order."""
    subset = []
    for inst in ["Violin", "Viola", "Cello"]:
        inst_tracks = [t for t in tracks if t['instrument'] == inst]
        if len(inst_tracks) < per_instrument:
            print(f"  [!] Only {len(inst_tracks)} {inst} tracks available "
                  f"(requested {per_instrument})")
        subset.extend(inst_tracks[:per_instrument])
    return subset


def mark_duplicate_audio(tracks):
    """
    Flags tracks whose audio file is byte-identical to one already seen.

    URMP reuses the same recorded stem across pieces that differ only in another
    part — 24_Pirates and 25_Pirates share one viola take, as do 26_King and
    27_King. Any statistic computed over the pooled note population therefore
    counts those notes twice, which does not bias the location estimates but does
    inflate n and so understates every confidence interval. This is a property of
    the shared 15-track subset, so it applies equally to the slope/switch_prob and
    rms/min_frames studies that use it. Detected rather than assumed, and reported
    alongside a de-duplicated statistic set.
    """
    seen = {}
    for t in tracks:
        with open(t['audio_path'], 'rb') as f:
            digest = hashlib.md5(f.read()).hexdigest()
        t['audio_md5'] = digest
        t['duplicate_of'] = seen.get(digest)
        if digest not in seen:
            seen[digest] = t['stem']
    return tracks


def load_midi_notes(midi_path, target_track):
    """Strictly resolve one part; raises MidiTrackError rather than guessing."""
    midi_notes, _ = load_part_notes(midi_path, part_index=target_track)
    return midi_notes


# ==========================================
# Analysis
# ==========================================

def median_convergence(values, sizes, n_repeats=200, seed=0):
    """
    Does the aggregate median stabilise as the note population grows, and does its
    sampling interval ever become narrower than the output lattice?

    For each subsample size, draws `n_repeats` subsamples without replacement and
    records the spread of the resulting medians. If the spread collapses to zero
    while remaining locked on a lattice multiple, the median is pinned: it is
    *stable* but not *resolved*, and reporting it to two decimal places would
    imply a precision the encoder cannot deliver.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    rng = np.random.default_rng(seed)
    rows = []

    for size in sizes:
        if size > arr.size:
            continue
        medians = np.array([np.median(rng.choice(arr, size=size, replace=False))
                            for _ in range(n_repeats)])
        rows.append({
            'size': size,
            'median_of_medians': float(np.median(medians)),
            'sd_of_medians': float(np.std(medians, ddof=1)),
            'p2_5': float(np.percentile(medians, 2.5)),
            'p97_5': float(np.percentile(medians, 97.5)),
            'n_distinct_medians': int(np.unique(medians).size),
        })

    rows.append({
        'size': int(arr.size),
        'median_of_medians': float(np.median(arr)),
        'sd_of_medians': 0.0,
        'p2_5': float(np.median(arr)),
        'p97_5': float(np.median(arr)),
        'n_distinct_medians': 1,
    })
    return rows


def analyse_sample(values, label, step=None):
    """Descriptive + normality + quantization + bootstrap for one deviation sample."""
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    out = {
        'label': label,
        'descriptive': descriptive_stats(arr),
        'normality': normality_tests(arr),
        'bootstrap_median': bootstrap_ci(arr, np.median),
        'bootstrap_iqr': bootstrap_ci(
            arr, lambda a, axis=None: (np.percentile(a, 75, axis=axis) -
                                       np.percentile(a, 25, axis=axis))),
        # The comparison that decides what this system should report: an order
        # statistic (median) against an average of the same robust core
        # (trimmed mean) on identical data.
        'bootstrap_trimmed_mean': bootstrap_ci(arr, trimmed_mean),
        'bootstrap_mean': bootstrap_ci(arr, np.mean),
    }
    if step is not None:
        out['quantization'] = quantization_diagnostics(arr, step=step)
    return out


# ==========================================
# Figures
# ==========================================

def _style(ax, title, xlabel, ylabel):
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.grid(alpha=0.25, linestyle=':')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def plot_distribution(samples, path):
    """
    Histogram + KDE per engine, on a shared axis.

    Bin edges are placed on the pYIN lattice (10-cent width, centred on the
    multiples) so that each bar corresponds to exactly one attainable pYIN output
    value. Binning finer than the lattice would draw a comb of empty bins that
    reads as structure but is pure encoder artefact.
    """
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Bin width matches the *per-note* lattice (5 c), not the frame lattice (10 c):
    # these are DTW note medians, so 10-cent bins would merge adjacent attainable
    # values and conceal the very quantization this figure is meant to expose.
    step = PYIN_NOTE_MEDIAN_RESOLUTION_CENTS
    bins = np.arange(-100 - step / 2, 100 + step, step)

    ax = axes[0]
    for label, arr in samples.items():
        if arr.size == 0:
            continue
        ax.hist(arr, bins=bins, density=True, alpha=0.5,
                color=COLORS.get(label, None), label=f"{label} (n={arr.size})")
        if arr.size > 2 and np.std(arr) > 0:
            kde = scipy_stats.gaussian_kde(arr)
            grid = np.linspace(-100, 100, 400)
            ax.plot(grid, kde(grid), color=COLORS.get(label, None), lw=2)
        ax.axvline(np.median(arr), color=COLORS.get(label, None), ls='--', lw=1.5)
    ax.axvline(0, color='grey', lw=1)
    _style(ax, "Per-note deviation distribution (DTW mode)",
           "Deviation from MIDI target (cents)", "Probability density")
    ax.legend(fontsize=9, frameon=False)

    # Crop to the occupied range rather than the full +/-100 exclusion gate, so the
    # shape of the body of the distribution is legible.
    populated = np.concatenate([a for a in samples.values() if a.size])
    x_lo = max(-100, np.percentile(populated, 0.5) - 15)
    x_hi = min(100, np.percentile(populated, 99.5) + 15)
    ax.set_xlim(x_lo, x_hi)

    # Right panel: the same pYIN sample against a fitted normal, which is the
    # distribution the mean +/- SD summary implicitly assumes.
    ax = axes[1]
    arr = samples.get("pYIN", np.array([]))
    if arr.size > 2:
        ax.hist(arr, bins=bins, density=True, alpha=0.5, color=COLORS["pYIN"],
                label=f"pYIN observed (n={arr.size})")
        grid = np.linspace(-100, 100, 400)
        ax.plot(grid, scipy_stats.norm.pdf(grid, np.mean(arr), np.std(arr, ddof=1)),
                color='#d62728', lw=2, ls='-',
                label=f"Normal fit ($\\mu$={np.mean(arr):.1f}, $\\sigma$={np.std(arr, ddof=1):.1f})")
        q1, med, q3 = np.percentile(arr, [25, 50, 75])
        ax.axvspan(q1, q3, color='grey', alpha=0.15, label=f"IQR [{q1:.0f}, {q3:.0f}]")
        ax.axvline(med, color='k', ls='--', lw=1.5, label=f"Median {med:.1f}")
    _style(ax, "pYIN deviations vs the normal the mean/SD summary assumes",
           "Deviation from MIDI target (cents)", "Probability density")
    ax.legend(fontsize=8, frameon=False)
    ax.set_xlim(x_lo, x_hi)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_qq(samples, path):
    """Normal Q-Q plot per engine — the standard visual evidence for tail behaviour."""
    n_panels = len(samples)
    fig, axes = plt.subplots(1, n_panels, figsize=(6.5 * n_panels, 5))
    if n_panels == 1:
        axes = [axes]

    for ax, (label, arr) in zip(axes, samples.items()):
        if arr.size < 3:
            continue
        osm, osr = scipy_stats.probplot(arr, dist='norm', fit=False)
        ax.scatter(osm, osr, s=8, alpha=0.4, color=COLORS.get(label, "#2ca02c"))
        # Reference line through the robust centre and scale, so it is not itself
        # dragged off by the outliers whose presence the plot is meant to reveal.
        # The line spans the theoretical-quantile axis only; osm is in standard
        # deviations and osr in cents, so a shared limit would be meaningless.
        slope = scipy_stats.iqr(arr) / (scipy_stats.norm.ppf(0.75) * 2)
        intercept = np.median(arr)
        x_lim = np.array([osm.min(), osm.max()])
        ax.plot(x_lim, intercept + slope * x_lim, color='#d62728', lw=1.5,
                label='Robust normal reference')
        skew = scipy_stats.skew(arr, bias=False)
        kurt = scipy_stats.kurtosis(arr, bias=False)
        _style(ax, f"{label}: normal Q-Q (n={arr.size})\nG1={skew:+.2f}  G2={kurt:+.2f}",
               "Theoretical normal quantile", "Observed deviation (cents)")
        ax.legend(fontsize=9, frameon=False)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_bland_altman(ba, path):
    """Bland-Altman plot of the paired pYIN / REAPER note deviations."""
    fig, ax = plt.subplots(figsize=(8, 5.5))

    ax.scatter(ba['means'], ba['diffs'], s=10, alpha=0.35, color=COLORS['pYIN'])
    ax.axhline(ba['bias'], color='#d62728', lw=2,
               label=f"Bias {ba['bias']:+.2f} c")
    ax.axhline(ba['loa_upper'], color='grey', lw=1.5, ls='--',
               label=f"95% LoA [{ba['loa_lower']:+.1f}, {ba['loa_upper']:+.1f}] c")
    ax.axhline(ba['loa_lower'], color='grey', lw=1.5, ls='--')
    ax.axhline(0, color='k', lw=0.8, alpha=0.4)

    _style(ax, f"Bland-Altman: pYIN vs REAPER per-note deviation (n={ba['n']})",
           "Mean of the two engines (cents)", "pYIN − REAPER (cents)")
    ax.legend(fontsize=9, frameon=False, loc='upper right')

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ==========================================
# Report
# ==========================================

def fmt(value, spec="{:.2f}"):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return spec.format(value)


def stats_table(samples):
    rows = [
        ("Sample size (n)", 'n', "{:.0f}"),
        ("Mean", 'mean', "{:+.2f}"),
        ("Standard deviation", 'std', "{:.2f}"),
        ("Standard error of mean", 'sem', "{:.3f}"),
        ("Median", 'median', "{:+.2f}"),
        ("Q1", 'q1', "{:+.2f}"),
        ("Q3", 'q3', "{:+.2f}"),
        ("IQR", 'iqr', "{:.2f}"),
        ("Median absolute deviation", 'mad', "{:.2f}"),
        (f"{TRIM_PROPORTION:.0%}-trimmed mean", 'trimmed_mean', "{:+.2f}"),
        ("Skewness (G1)", 'skewness', "{:+.3f}"),
        ("Excess kurtosis (G2)", 'kurtosis', "{:+.3f}"),
        ("Minimum", 'min', "{:+.2f}"),
        ("Maximum", 'max', "{:+.2f}"),
    ]
    labels = list(samples.keys())
    lines = ["| Statistic (cents) | " + " | ".join(labels) + " |",
             "| :--- | " + " | ".join([":---:"] * len(labels)) + " |"]
    for label, key, spec in rows:
        cells = [fmt(samples[l]['descriptive'].get(key), spec) for l in labels]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines


def generate_report(payload):
    a = payload['analyses']
    lines = []
    lines.append("# Distributional Statistics & Quantization Resolution Floor")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append(f"Both engines ran the full production pipeline (extract → intonation filters → "
                 f"DTW alignment → harmonic folding → per-note metrics) at Engine Optimal Default "
                 f"parameters over a deterministic subset of {payload['n_tracks']} URMP bowed-string "
                 f"tracks (first {TRACKS_PER_INSTRUMENT} per instrument in sorted path order) — the "
                 f"same subset as `validate_slope_switchprob.py` and `validate_rms_minframes.py`. "
                 f"Notes excluded by `is_note_excluded()` (|dev| > 100 cents or harmonic folding "
                 f"applied) are dropped, matching the production summary.")
    lines.append("")
    lines.append(f"REAPER serves as the **control**: it returns continuous f0, so any degeneracy "
                 f"present in the pYIN order statistics but absent from REAPER's is caused by the "
                 f"pYIN output lattice rather than by the music.")
    lines.append("")

    dupes = payload.get('duplicate_audio') or []
    if dupes:
        lines.append("### Duplicate audio in the shared subset")
        lines.append("")
        lines.append(f"{len(dupes)} of the {payload['n_tracks']} selected stems are "
                     f"**byte-identical** to an earlier stem. URMP reuses one recorded take "
                     f"across pieces that differ only in another part:")
        lines.append("")
        for d in dupes:
            lines.append(f"- `{d['stem']}` is identical to `{d['duplicate_of']}`")
        lines.append("")
        lines.append(f"Their notes are therefore counted twice in the pooled population. This does "
                     f"not bias the location estimates — the duplicated notes carry the same values "
                     f"— but it inflates $n$ and so understates every confidence interval and "
                     f"standard error below. A de-duplicated row "
                     f"({payload['n_unique_tracks']} unique stems) is reported alongside the pooled "
                     f"one so the two can be compared directly. **This subset is shared with "
                     f"`validate_slope_switchprob.py` and `validate_rms_minframes.py`, so the same "
                     f"duplication applies to the results of roadmap tasks #5 and #8.**")
        lines.append("")

    # --- Adaptive RMS instrumentation ---
    lines.append("### Effective RMS threshold (adaptive override)")
    lines.append("")
    lines.append("`analyze_intonation()` overrides the nominal `rms_threshold` with an adaptive "
                 "noise floor, `effective = max(rms_threshold, 2 × P10(RMS))`. The nominal 0.005 "
                 "used here is therefore not necessarily what gated the frames these statistics "
                 "are computed from, and the binding rate is reported rather than assumed.")
    lines.append("")
    lines.append("| Engine | Nominal | Median effective | Max effective | Tracks where nominal binds |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for engine, info in payload['rms_instrumentation'].items():
        lines.append(f"| {engine} | {ENGINES[engine]['rms_threshold']:.4f} | "
                     f"{info['median_effective']:.4f} | {info['max_effective']:.4f} | "
                     f"{info['binding_count']}/{info['n_tracks']} "
                     f"({info['binding_pct']:.0f}%) |")
    lines.append("")

    # --- Descriptive statistics ---
    lines.append("## 1. Descriptive Statistics")
    lines.append("")
    lines.extend(stats_table(a))
    lines.append("")

    # --- Normality ---
    lines.append("## 2. Normality of the Deviation Distribution")
    lines.append("")
    lines.append("| Engine | Skewness (G1) | Excess kurtosis (G2) | D'Agostino-Pearson K² | p |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for label, entry in a.items():
        d, nt = entry['descriptive'], entry['normality']
        p = nt['dagostino_p']
        p_str = "< 1e-300" if (p is not None and not np.isnan(p) and p == 0) else fmt(p, "{:.2e}")
        lines.append(f"| {label} | {fmt(d['skewness'], '{:+.3f}')} | "
                     f"{fmt(d['kurtosis'], '{:+.3f}')} | {fmt(nt['dagostino_stat'], '{:.1f}')} | "
                     f"{p_str} |")
    lines.append("")
    lines.append("At these sample sizes any formal test rejects normality on a trivial departure, "
                 "so the *effect sizes* carry the argument. Excess kurtosis is the operative number: "
                 "it measures how much heavier the tails are than a Gaussian's, and heavy tails are "
                 "precisely the condition under which the mean and SD stop describing the typical "
                 "note. See `docs/images/deviation_qq.png` for the tail behaviour directly.")
    lines.append("")

    # --- Quantization ---
    lines.append("## 3. Quantization Resolution Floor")
    lines.append("")
    lines.append(f"`librosa.pyin()` decodes f0 on a grid of `resolution=0.1` semitones. Because the "
                 f"instrument `fmin` values are exact integer MIDI notes, that grid lands on "
                 f"integer-MIDI + 0.1k, so every **frame** deviation is an exact multiple of "
                 f"{PYIN_RESOLUTION_CENTS:.0f} cents. A DTW **per-note** deviation is the median of "
                 f"those frames, which halves the step to "
                 f"{PYIN_NOTE_MEDIAN_RESOLUTION_CENTS:.0f} cents on even-sized note islands.")
    lines.append("")
    lines.append("| Sample | Assumed step (c) | Distinct values | On-lattice fraction | Max residual (c) | IQR in steps | SD | Sheppard-corrected SD |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for label, entry in a.items():
        q = entry.get('quantization')
        if not q:
            continue
        d = entry['descriptive']
        lines.append(f"| {label} | {q['step']:.1f} | {q['n_distinct']} | "
                     f"{q['lattice_fraction']*100:.1f}% | {q['max_residual']:.4f} | "
                     f"{q['iqr_in_steps']:.2f} | {fmt(d['std'])} | {fmt(q['sheppard_std'])} |")
    lines.append("")

    # --- Median convergence ---
    lines.append("### Does aggregation rescue the median?")
    lines.append("")
    lines.append("Subsamples of increasing size are drawn without replacement from the pYIN note "
                 "population and the median re-estimated 200 times at each size. If the spread of "
                 "those medians collapses while they remain locked on lattice multiples, the "
                 "aggregate median is *stable but not resolved*.")
    lines.append("")
    lines.append("| Subsample size | Median of medians | SD of medians | 95% range | Distinct medians observed |")
    lines.append("| :---: | :---: | :---: | :---: | :---: |")
    for row in payload['median_convergence']:
        lines.append(f"| {row['size']} | {row['median_of_medians']:+.2f} | "
                     f"{row['sd_of_medians']:.2f} | "
                     f"[{row['p2_5']:+.2f}, {row['p97_5']:+.2f}] | "
                     f"{row['n_distinct_medians']} |")
    lines.append("")

    lines.append("### Bootstrap intervals on the full population")
    lines.append("")
    lines.append("A 95% percentile bootstrap interval of **zero width** is the diagnostic: it means "
                 "every resample returned the same value, so the statistic cannot move and carries "
                 "no resolution beyond naming one lattice cell.")
    lines.append("")
    lines.append("| Sample | Median [95% CI] | IQR [95% CI] | "
                 f"{TRIM_PROPORTION:.0%}-trimmed mean [95% CI] | Mean [95% CI] |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for label, entry in a.items():
        bm, bi = entry['bootstrap_median'], entry['bootstrap_iqr']
        bt, bmu = entry['bootstrap_trimmed_mean'], entry['bootstrap_mean']
        lines.append(f"| {label} | {bm['point']:+.2f} [{bm['lower']:+.2f}, {bm['upper']:+.2f}] | "
                     f"{bi['point']:.2f} [{bi['lower']:.2f}, {bi['upper']:.2f}] | "
                     f"{bt['point']:+.2f} [{bt['lower']:+.2f}, {bt['upper']:+.2f}] | "
                     f"{bmu['point']:+.2f} [{bmu['lower']:+.2f}, {bmu['upper']:+.2f}] |")
    lines.append("")
    lines.append(f"**Recommendation.** On pYIN data the median and IQR are order statistics and "
                 f"can only return lattice values, so their intervals collapse; the mean and the "
                 f"{TRIM_PROPORTION:.0%}-trimmed mean are *averages* of many lattice values and "
                 f"dither off the grid, retaining full resolution. Since the distribution is "
                 f"heavy-tailed (§2), the ordinary mean is not representative either. The trimmed "
                 f"mean is the statistic that satisfies both constraints simultaneously: robust to "
                 f"the tails, and unaffected by the resolution floor. The median and IQR are still "
                 f"reported — they are what a reader expects to see, and their degeneracy is itself "
                 f"a reportable property of the engine — but they should not be read to two "
                 f"decimal places.")
    lines.append("")

    # --- Bland-Altman ---
    ba = payload['bland_altman']
    lines.append("## 4. Bland-Altman Agreement (pYIN vs REAPER)")
    lines.append("")
    if ba['n'] >= 2:
        lines.append(f"- **Paired notes**: {ba['n']}")
        lines.append(f"- **Bias** (pYIN − REAPER): {ba['bias']:+.2f} cents")
        lines.append(f"- **SD of differences**: {ba['sd_diff']:.2f} cents")
        lines.append(f"- **95% Limits of Agreement**: [{ba['loa_lower']:+.2f}, {ba['loa_upper']:+.2f}] cents")
        lines.append("")
        lines.append("Plot: `docs/images/bland_altman_pyin_reaper.png`. The limits of agreement, not "
                     "the bias, are the number that matters: they state how far the two engines can "
                     "disagree on any single note, which a correlation coefficient never reveals.")
    else:
        lines.append("Insufficient paired data.")
    lines.append("")

    lines.append("## 5. Figures")
    lines.append("")
    lines.append("| File | Content |")
    lines.append("| :--- | :--- |")
    lines.append("| `docs/images/deviation_distribution.png` | Histogram + KDE per engine; pYIN against the normal its mean/SD summary assumes |")
    lines.append("| `docs/images/deviation_qq.png` | Normal Q-Q plots showing tail behaviour |")
    lines.append("| `docs/images/bland_altman_pyin_reaper.png` | Inter-engine agreement with 95% limits |")
    lines.append("")

    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(lines))


# ==========================================
# Main
# ==========================================

def main():
    print("=" * 64)
    print("Distributional Statistics & Quantization Resolution Floor")
    print("Engines: pYIN (quantized) vs REAPER (continuous control)")
    print("=" * 64)

    dataset_dir = Path(os.path.join(PROJECT_ROOT, 'dataset (Strings only)'))
    if not dataset_dir.exists():
        print(f"Error: Dataset not found at {dataset_dir}")
        sys.exit(1)

    os.makedirs(IMAGES_DIR, exist_ok=True)

    tracks = mark_duplicate_audio(select_subset(discover_tracks(dataset_dir),
                                                TRACKS_PER_INSTRUMENT))
    duplicates = [t for t in tracks if t['duplicate_of']]
    print(f"\n[INFO] {len(tracks)} tracks selected.")
    if duplicates:
        print(f"[WARN] {len(duplicates)} track(s) are byte-identical duplicates of an "
              f"earlier stem — statistics are reported both pooled and de-duplicated:")
        for t in duplicates:
            print(f"         {t['stem']} == {t['duplicate_of']}")
    print()
    if not tracks:
        sys.exit(1)

    note_devs = {"pYIN": [], "REAPER": []}
    unique_note_devs = {"pYIN": [], "REAPER": []}
    frame_devs = {"pYIN": [], "REAPER": []}
    paired_pyin, paired_reaper = [], []
    rms_records = {"pYIN": [], "REAPER": []}

    for i, t in enumerate(tracks, 1):
        print(f"[{i}/{len(tracks)}] {t['stem']} ({t['instrument']})", flush=True)

        midi_notes = load_midi_notes(t['midi_path'], t['target_track'])
        if not midi_notes:
            print("  [!] No MIDI notes, skipping")
            continue

        per_engine_metrics = {}
        for engine, params in ENGINES.items():
            metrics, legacy, eff_rms, binding = run_pipeline(
                t['audio_path'], midi_notes, t['instrument'], engine, params
            )
            per_engine_metrics[engine] = metrics
            rms_records[engine].append({'stem': t['stem'], 'effective': eff_rms,
                                        'binding': bool(binding)})

            devs = included_note_deviations(metrics, auto_excluded_indices(metrics))
            note_devs[engine].append(devs)
            if not t['duplicate_of']:
                unique_note_devs[engine].append(devs)
            frame_devs[engine].append(legacy)
            print(f"    {engine:<6} included notes: {devs.size:4d}  "
                  f"effective rms={eff_rms:.5f} ({'nominal' if binding else 'adaptive'})")

        # Union of both engines' exclusions, so the paired comparison is symmetric.
        excl = set(auto_excluded_indices(per_engine_metrics['pYIN'])) | \
               set(auto_excluded_indices(per_engine_metrics['REAPER']))
        pa, pb, _ = pair_note_deviations(per_engine_metrics['pYIN'],
                                         per_engine_metrics['REAPER'], excl)
        paired_pyin.append(pa)
        paired_reaper.append(pb)
        print(f"    paired notes: {pa.size}")

        del per_engine_metrics
        gc.collect()

    samples = {engine: np.concatenate(v) if v else np.array([])
               for engine, v in note_devs.items()}
    unique_samples = {engine: np.concatenate(v) if v else np.array([])
                      for engine, v in unique_note_devs.items()}
    pyin_frames = np.concatenate(frame_devs['pYIN']) if frame_devs['pYIN'] else np.array([])

    # --- Analyses ---
    analyses = {
        "pYIN": analyse_sample(samples['pYIN'], "pYIN",
                               step=PYIN_NOTE_MEDIAN_RESOLUTION_CENTS),
        "REAPER": analyse_sample(samples['REAPER'], "REAPER",
                                 step=PYIN_NOTE_MEDIAN_RESOLUTION_CENTS),
    }
    analyses["pYIN (frame-level, legacy mode)"] = analyse_sample(
        pyin_frames, "pYIN frames", step=PYIN_RESOLUTION_CENTS)
    if duplicates:
        analyses["pYIN (de-duplicated audio)"] = analyse_sample(
            unique_samples['pYIN'], "pYIN unique", step=PYIN_NOTE_MEDIAN_RESOLUTION_CENTS)

    ba = bland_altman_stats(np.concatenate(paired_pyin) if paired_pyin else np.array([]),
                            np.concatenate(paired_reaper) if paired_reaper else np.array([]))

    convergence = median_convergence(samples['pYIN'], CONVERGENCE_SIZES)

    rms_instrumentation = {}
    for engine, recs in rms_records.items():
        effs = np.array([r['effective'] for r in recs])
        binding = sum(1 for r in recs if r['binding'])
        rms_instrumentation[engine] = {
            'n_tracks': len(recs),
            'median_effective': float(np.median(effs)) if effs.size else float('nan'),
            'max_effective': float(np.max(effs)) if effs.size else float('nan'),
            'binding_count': binding,
            'binding_pct': (binding / len(recs) * 100) if recs else float('nan'),
        }

    # --- Console summary ---
    print("\n" + "=" * 64)
    print("AGGREGATE RESULTS")
    print("=" * 64)
    for label, entry in analyses.items():
        d = entry['descriptive']
        q = entry.get('quantization', {})
        print(f"\n  {label} (n={d['n']}):")
        print(f"    mean {d['mean']:+.2f}  SD {d['std']:.2f}  |  "
              f"median {d['median']:+.2f}  IQR {d['iqr']:.2f}")
        print(f"    skewness G1={d['skewness']:+.3f}  excess kurtosis G2={d['kurtosis']:+.3f}")
        if q:
            print(f"    lattice: {q['n_distinct']} distinct values, "
                  f"{q['lattice_fraction']*100:.1f}% on-grid, "
                  f"IQR = {q['iqr_in_steps']:.2f} steps of {q['step']:.1f}c")

    if ba['n'] >= 2:
        print(f"\n  Bland-Altman (pYIN − REAPER), n={ba['n']}:")
        print(f"    bias {ba['bias']:+.2f}c   95% LoA [{ba['loa_lower']:+.2f}, {ba['loa_upper']:+.2f}]c")

    # --- Figures ---
    print("\n[INFO] Rendering figures...")
    plot_distribution(samples, FIG_DISTRIBUTION)
    # The frame-level sample gets its own Q-Q panel: it is where the heavy tails
    # live, because per-note medians average them away before the DTW summary
    # ever sees them.
    plot_qq({**samples, "pYIN frames (legacy)": pyin_frames}, FIG_QQ)
    if ba['n'] >= 2:
        plot_bland_altman(ba, FIG_BLAND_ALTMAN)

    # --- Persist ---
    payload = {
        'generated': datetime.now().isoformat(timespec='seconds'),
        'n_tracks': len(tracks),
        'tracks': [t['stem'] for t in tracks],
        'duplicate_audio': [{'stem': t['stem'], 'duplicate_of': t['duplicate_of']}
                            for t in duplicates],
        'n_unique_tracks': len(tracks) - len(duplicates),
        'engines': ENGINES,
        'analyses': analyses,
        'bland_altman': {k: v for k, v in ba.items() if k not in ('means', 'diffs')},
        'median_convergence': convergence,
        'rms_instrumentation': rms_instrumentation,
        # Raw samples travel with the results so the report and every figure can be
        # regenerated (`--figures-only`) without a 15-track re-run, and so a reader
        # can verify the statistics rather than take them on trust. Rounded to
        # SAMPLE_DECIMALS: pYIN values are exact multiples of 5 or 10 cents and
        # REAPER's continuous output is meaningless below ~0.01 cents, so full
        # float64 text would inflate the file by an order of magnitude for no
        # recoverable information.
        'sample_decimals': SAMPLE_DECIMALS,
        'samples': {
            'pyin_notes': encode_sample(samples['pYIN']),
            'reaper_notes': encode_sample(samples['REAPER']),
            'pyin_frames': encode_sample(pyin_frames),
            'pyin_notes_unique': encode_sample(unique_samples['pYIN']),
            'reaper_notes_unique': encode_sample(unique_samples['REAPER']),
            # Kept as flat, index-aligned lists: Bland-Altman needs the pairing.
            'paired_pyin': _round(np.concatenate(paired_pyin) if paired_pyin else np.array([])),
            'paired_reaper': _round(np.concatenate(paired_reaper) if paired_reaper else np.array([])),
        },
    }

    with open(RESULTS_JSON, 'w') as f:
        json.dump(payload, f, indent=2, default=float)

    payload['bland_altman'] = ba  # report needs the means/diffs-free view above
    generate_report(payload)

    print(f"\n[+] Report  : {REPORT_PATH}")
    print(f"[+] Sidecar : {RESULTS_JSON}")
    print(f"[+] Figures : {FIG_DISTRIBUTION}")
    print(f"              {FIG_QQ}")
    print(f"              {FIG_BLAND_ALTMAN}")
    print("=" * 64)


def rebuild_from_sidecar():
    """
    Regenerates every figure and the report from `distribution_stats_results.json`,
    without touching the audio. Used when the presentation changes but the
    measurement has not — a re-run of the pipeline would be 15 tracks x 2 engines
    for no new data, and would risk figures drifting from the reported numbers.
    """
    if not os.path.exists(RESULTS_JSON):
        print(f"Error: no sidecar at {RESULTS_JSON}. Run the full study first.")
        sys.exit(1)

    with open(RESULTS_JSON) as f:
        payload = json.load(f)

    raw = payload.get('samples')
    if not raw:
        print("Error: sidecar predates raw-sample persistence. Run the full study first.")
        sys.exit(1)

    samples = {
        "pYIN": decode_sample(raw['pyin_notes']),
        "REAPER": decode_sample(raw['reaper_notes']),
    }

    pyin_frames = decode_sample(raw['pyin_frames'])
    ba = bland_altman_stats(np.asarray(raw['paired_pyin'], dtype=float),
                            np.asarray(raw['paired_reaper'], dtype=float))

    # Recomputed rather than reused from the sidecar, so that adding a statistic
    # does not require a pipeline re-run and the report can never carry a stale
    # analysis alongside fresh figures.
    analyses = {
        "pYIN": analyse_sample(samples['pYIN'], "pYIN",
                               step=PYIN_NOTE_MEDIAN_RESOLUTION_CENTS),
        "REAPER": analyse_sample(samples['REAPER'], "REAPER",
                                 step=PYIN_NOTE_MEDIAN_RESOLUTION_CENTS),
        "pYIN (frame-level, legacy mode)": analyse_sample(
            pyin_frames, "pYIN frames", step=PYIN_RESOLUTION_CENTS),
    }
    if raw.get('pyin_notes_unique') and payload.get('duplicate_audio'):
        analyses["pYIN (de-duplicated audio)"] = analyse_sample(
            decode_sample(raw['pyin_notes_unique']), "pYIN unique",
            step=PYIN_NOTE_MEDIAN_RESOLUTION_CENTS)
    payload['analyses'] = analyses

    os.makedirs(IMAGES_DIR, exist_ok=True)
    plot_distribution(samples, FIG_DISTRIBUTION)
    plot_qq({**samples, "pYIN frames (legacy)": pyin_frames}, FIG_QQ)
    if ba['n'] >= 2:
        plot_bland_altman(ba, FIG_BLAND_ALTMAN)

    payload['bland_altman'] = ba
    generate_report(payload)

    print(f"[+] Rebuilt report and figures from {RESULTS_JSON}")


if __name__ == "__main__":
    if "--figures-only" in sys.argv:
        rebuild_from_sidecar()
    else:
        main()
