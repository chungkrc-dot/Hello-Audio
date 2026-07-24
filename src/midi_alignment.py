"""
midi_alignment.py
-----------------
The core mathematical engine for aligning audio to a MIDI reference using Dynamic Time Warping (DTW).
This module handles synthesizing reference audio, performing DTW alignment, calculating octave-agnostic 
pitch boundaries, and extracting precise intonation metrics bound strictly to the MIDI temporal expectations.
"""
import numpy as np

from src.stats_summary import prefixed_stats

def included_note_deviations(metrics, excluded_indices=None, key="Deviation_Cents"):
    """
    Pulls the per-note deviation values that contribute to the summary: notes that
    were detected at all, minus any the caller excluded (the UI's Include column,
    which is seeded by is_note_excluded()).

    Returned as a plain float array so it can be fed straight to the statistics
    and plotting helpers.
    """
    if not metrics:
        return np.array([])

    excluded = set(excluded_indices or [])
    vals = [m.get(key, np.nan) for m in metrics if m.get("Note_Index") not in excluded]
    arr = np.asarray(vals, dtype=float)
    return arr[~np.isnan(arr)]


def pair_note_deviations(metrics_a, metrics_b, excluded_indices=None, key="Deviation_Cents"):
    """
    Pairs two DTW metric lists note-for-note by Note_Index, keeping only notes both
    sides detected and neither side excluded. Returns (values_a, values_b, labels).

    This is the input a Bland-Altman analysis requires: two measurements of the
    *same* note, so the difference between them is attributable to the conditions
    (or engines) being compared rather than to which notes each happened to catch.
    """
    if not metrics_a or not metrics_b:
        return np.array([]), np.array([]), []

    excluded = set(excluded_indices or [])
    by_idx_a = {m["Note_Index"]: m for m in metrics_a}
    by_idx_b = {m["Note_Index"]: m for m in metrics_b}

    values_a, values_b, labels = [], [], []
    for idx in sorted(set(by_idx_a) & set(by_idx_b)):
        if idx in excluded:
            continue
        va = by_idx_a[idx].get(key, np.nan)
        vb = by_idx_b[idx].get(key, np.nan)
        if np.isnan(va) or np.isnan(vb):
            continue
        values_a.append(va)
        values_b.append(vb)
        labels.append(f"Note {idx} ({by_idx_a[idx].get('Expected_Note', '?')})")

    return np.asarray(values_a, dtype=float), np.asarray(values_b, dtype=float), labels


# Detection-yield floors below which a run is flagged for the user to check that
# the MIDI part, the audio file and the instrument setting really correspond.
#
# The thresholds are engine-specific because the two engines have different
# floors on legitimate material. Across the 41-stem URMP corpus the worst
# genuine pYIN detection yield is 70.6%, leaving 50% clear by 20 pp with no
# false positives. REAPER runs lower by architecture — epoch dropout in the
# upper register (§3B) takes one genuine track to 46.8% — so a shared 50% floor
# would fire on known-good audio and train the warning into background noise.
LOW_DETECTION_YIELD_THRESHOLDS = {"pYIN": 50.0, "REAPER": 40.0}
DEFAULT_LOW_DETECTION_YIELD = 50.0


def low_detection_yield_warning(pct_detected, pitch_engine=None, threshold=None):
    """
    Return a warning string if detection yield is low enough to suggest the
    audio and the MIDI part may not correspond, else None.

    This is advisory. A low yield has innocent causes — difficult repertoire,
    a quiet or noisy recording, an aggressive amplitude gate — so the message
    asks the user to verify rather than asserting a mistake. Its real purpose
    is to catch the one error class no range check can see: a part swap between
    two instruments of the same type (Violin I for Violin II), which collapses
    yield because the two parts play different notes.
    """
    if pct_detected is None or np.isnan(pct_detected):
        return None
    if threshold is None:
        threshold = LOW_DETECTION_YIELD_THRESHOLDS.get(
            pitch_engine, DEFAULT_LOW_DETECTION_YIELD
        )
    if pct_detected >= threshold:
        return None
    return (
        f"Only {pct_detected:.1f}% of the MIDI notes were detected in the audio "
        f"(below the {threshold:.0f}% guidance level for {pitch_engine or 'this engine'}). "
        "This is often just difficult or quiet material, but it is also what a "
        "mismatch looks like. Worth confirming that the selected MIDI track is the "
        "part actually played in this recording — parts for the same instrument "
        "(Violin I vs Violin II) sit in the same range and cannot be told apart by "
        "pitch alone — and that the audio file and instrument setting are the ones "
        "you intended."
    )


# The four "effect" metrics whose condition-to-condition difference is a research
# output. Each maps a summary-table column to the per-note key it is paired on.
PAIRED_DELTA_KEYS = {
    "mean intonation deviation (Hz)": "Deviation_Hz",
    "mean intonation deviation (cents)": "Deviation_Cents",
    "mean RMS amplitude (dB FS)": "Median_RMS_dBFS",
    "mean RMS amplitude (dB A)": "Median_RMS_dBA",
}

# Below this note-level detection overlap, or beyond this yield gap, the
# independent-means delta is at risk of drift and the paired delta should be
# trusted instead. Advisory thresholds, not hard cutoffs.
PAIRED_COVERAGE_MIN_FRACTION = 0.70   # paired notes / smaller side's detected count
PAIRED_YIELD_GAP_PP = 10.0            # |detected%_a - detected%_b|


def paired_delta_summary(metrics_a, metrics_b, excluded_indices=None):
    """
    Drift-free delta between two conditions (a - b), computed **note-for-note over
    the notes both conditions detected and neither excluded** — the same pairing
    the Bland-Altman analysis uses.

    The summary table's other delta subtracts each condition's *independent* mean,
    each taken over that condition's own detected notes. When the two conditions
    detect different note sets (asymmetric yield — the norm once a real difference
    is present), that difference of independent means carries arithmetic drift
    from the non-overlapping notes: it mixes the true condition effect with the
    accident of which notes each side caught. Comparing each note to itself across
    the two conditions removes that drift and, because it cancels the large
    note-to-note variation in difficulty, also estimates the effect far more
    precisely. This is the standard paired / within-subject comparison.

    Returns a dict:
      deltas          {column_label: mean paired difference (a - b)}  (np.nan if none)
      n_paired        number of notes contributing (both detected, not excluded)
      n_detected_a/b  each condition's detected-note count
      total           expected note count
    """
    excl = set(excluded_indices or [])
    by_a = {m["Note_Index"]: m for m in (metrics_a or [])}
    by_b = {m["Note_Index"]: m for m in (metrics_b or [])}

    def detected(by):
        return sum(1 for m in by.values()
                   if not np.isnan(m.get("Deviation_Cents", np.nan)))

    shared = [
        i for i in sorted(set(by_a) & set(by_b))
        if i not in excl
        and not np.isnan(by_a[i].get("Deviation_Cents", np.nan))
        and not np.isnan(by_b[i].get("Deviation_Cents", np.nan))
    ]

    deltas = {}
    for col, key in PAIRED_DELTA_KEYS.items():
        diffs = [
            by_a[i].get(key, np.nan) - by_b[i].get(key, np.nan)
            for i in shared
        ]
        diffs = [d for d in diffs if not np.isnan(d)]
        deltas[col] = float(np.mean(diffs)) if diffs else np.nan

    total = max((m.get("Note_Index", 0) for m in list(by_a.values()) + list(by_b.values())),
                default=0)
    return {
        "deltas": deltas,
        "n_paired": len(shared),
        "n_detected_a": detected(by_a),
        "n_detected_b": detected(by_b),
        "total": len(by_a) or len(by_b),
    }


def paired_coverage_advisory(pct_detected_a, pct_detected_b, n_paired,
                             n_detected_a, n_detected_b):
    """
    Return an advisory string when the two conditions' detected note sets diverge
    enough that the independent-means delta is unreliable and the paired delta
    should be preferred, else None. Fires on a large yield gap or a small paired
    overlap relative to the smaller condition.
    """
    smaller = min(n_detected_a, n_detected_b)
    if smaller <= 0:
        return None
    coverage = n_paired / smaller
    gap = abs((pct_detected_a or 0.0) - (pct_detected_b or 0.0))
    if gap < PAIRED_YIELD_GAP_PP and coverage >= PAIRED_COVERAGE_MIN_FRACTION:
        return None
    return (
        f"The two takes detected different notes (yields {pct_detected_a:.0f}% vs "
        f"{pct_detected_b:.0f}%; {n_paired} notes in common). The **paired** Delta "
        "compares only those shared notes and is the trustworthy effect here; the "
        "independent-means Delta mixes in notes only one take caught and can drift. "
        "Report the paired figure, and treat a large yield gap as a data-quality "
        "signal worth checking."
    )


def summarize_dtw_metrics(metrics, excluded_indices=None):
    """
    Aggregates the note-by-note DTW metrics into one overall performance summary.

    Reports detection and inclusion yields, mean loudness, and a full
    distributional summary of the deviation in both cents and Hz — median, IQR,
    skewness and kurtosis as well as mean and SD, because cent-deviation
    distributions across a real performance are typically heavy-tailed and
    asymmetric, and a mean alone misrepresents them.

    Keys are flat: 'dev_cents_median', 'dev_hz_iqr', and so on (see
    src/stats_summary.STAT_KEYS).
    """
    summary = {
        "total_expected": 0,
        "detected_count": 0,
        "included_count": 0,
        "pct_detected": np.nan,
        "pct_included": np.nan,
        "mean_rms_dbfs": np.nan,
        "mean_rms_dba": np.nan,
    }
    summary.update(prefixed_stats([], 'dev_cents'))
    summary.update(prefixed_stats([], 'dev_hz'))

    if not metrics:
        return summary

    excluded = set(excluded_indices or [])

    total_expected = len(metrics)
    detected_count = sum(1 for m in metrics if not np.isnan(m.get("Deviation_Cents", np.nan)))

    filtered = [m for m in metrics if m.get("Note_Index") not in excluded]
    included_count = sum(1 for m in filtered if not np.isnan(m.get("Deviation_Cents", np.nan)))

    summary["total_expected"] = total_expected
    summary["detected_count"] = detected_count
    summary["included_count"] = included_count
    summary["pct_detected"] = (detected_count / total_expected * 100) if total_expected > 0 else np.nan
    summary["pct_included"] = (included_count / detected_count * 100) if detected_count > 0 else np.nan

    if not filtered:
        return summary

    dbfs = np.asarray([m.get("Median_RMS_dBFS", np.nan) for m in filtered], dtype=float)
    dba = np.asarray([m.get("Median_RMS_dBA", np.nan) for m in filtered], dtype=float)
    summary["mean_rms_dbfs"] = float(np.nanmean(dbfs)) if np.any(~np.isnan(dbfs)) else np.nan
    summary["mean_rms_dba"] = float(np.nanmean(dba)) if np.any(~np.isnan(dba)) else np.nan

    summary.update(prefixed_stats(
        included_note_deviations(metrics, excluded, "Deviation_Cents"), 'dev_cents'))
    summary.update(prefixed_stats(
        included_note_deviations(metrics, excluded, "Deviation_Hz"), 'dev_hz'))

    return summary


def is_note_excluded(note_dict):
    """
    Centralized logic for determining if a note should be excluded from summary metrics.
    Excludes gross tracking errors (>100 cents) and notes where harmonic folding was applied.
    """
    dev_cents = note_dict.get("Deviation_Cents", float('nan'))
    corr_applied = note_dict.get("Correction_Applied", False)
    
    if np.isnan(dev_cents):
        return True # Missing note
        
    if abs(dev_cents) > 100 or corr_applied:
        return True
        
    return False

def get_midi_chroma(midi_notes, sr, hop_length):
    """
    Synthesizes a basic sine-wave audio track from the MIDI score and extracts 12-bin Chroma CQT.
    """
    import numpy as np
    import librosa
    
    if not midi_notes:
        return np.array([])
        
    # We force first_start to 0 so that the synthesized MIDI track preserves leading rests/silence.
    # Otherwise, DTW maps the audio's leading silence to the first MIDI note!
    first_start = 0
    last_end = midi_notes[-1]['End_Time'] if isinstance(midi_notes[-1], dict) else getattr(midi_notes[-1], 'End_Time', 0)
    
    duration = last_end - first_start
    total_samples = int(np.ceil(duration * sr))
    y_midi = np.zeros(total_samples)
    
    t = np.arange(total_samples) / sr
    
    for note in midi_notes:
        start_time = note['Start_Time'] if isinstance(note, dict) else getattr(note, 'Start_Time', 0)
        end_time = note['End_Time'] if isinstance(note, dict) else getattr(note, 'End_Time', 0)
        pitch = note['Pitch'] if isinstance(note, dict) else getattr(note, 'Pitch', np.nan)
        
        if np.isnan(pitch):
            continue
            
        freq = librosa.midi_to_hz(pitch)
        
        local_start = start_time - first_start
        local_end = end_time - first_start
        
        start_sample = int(np.floor(local_start * sr))
        end_sample = int(np.ceil(local_end * sr))
        
        start_sample = max(0, start_sample)
        end_sample = min(total_samples, end_sample)
        
        if start_sample < end_sample:
            note_t = t[start_sample:end_sample] - local_start
            wave = np.sin(2 * np.pi * freq * note_t)
            y_midi[start_sample:end_sample] += wave
            
    chroma = librosa.feature.chroma_cqt(y=y_midi, sr=sr, hop_length=hop_length, fmin=65.4)
    chroma = np.nan_to_num(chroma, nan=0.0)
    return chroma + 1e-6

def get_audio_chroma(audio_y, sr, hop_length):
    """
    Extracts the 12-bin Chroma CQT from the raw audio waveform.
    """
    import numpy as np
    import librosa
    chroma = librosa.feature.chroma_cqt(y=audio_y, sr=sr, hop_length=hop_length, fmin=65.4)
    chroma = np.nan_to_num(chroma, nan=0.0)
    return chroma + 1e-6

def compute_dtw_path(midi_chroma, audio_chroma, force_global=False):
    """
    Computes the Dynamic Time Warping (DTW) path between MIDI and Audio Chroma.
    Automatically handles sequence length swapping to satisfy librosa's subseq requirements,
    unless force_global=True which forces a global alignment.

    Uses Müller's Sigma_2 step pattern {(1,1),(2,1),(1,2)} with weights (2,1,1)
    to prevent degenerate warping paths.
    """
    import numpy as np
    import librosa

    # Müller (2015) Sigma_2: eliminates pure horizontal/vertical steps,
    # constraining the warping path slope to [1/2, 2].
    step_sizes_sigma = np.array([[1, 1], [2, 1], [1, 2]], dtype=np.uint32)
    weights_mul = np.array([2.0, 1.0, 1.0], dtype=np.float64)

    # Subsequence DTW requires the shorter query sequence to be the first argument (X)
    # and the longer reference sequence to be the second argument (Y).
    # We dynamically swap them so the algorithm is mathematically robust to any tempo.

    len_midi = midi_chroma.shape[1]
    len_audio = audio_chroma.shape[1]

    if force_global:
        # Force global alignment, anchoring the start and end of both sequences.
        D, wp = librosa.sequence.dtw(
            midi_chroma,
            audio_chroma,
            metric='cosine',
            step_sizes_sigma=step_sizes_sigma,
            weights_mul=weights_mul,
            subseq=False
        )
        wp = np.fliplr(wp)
    elif len_midi <= len_audio:
        # MIDI is shorter (student played slow). Normal configuration.
        D, wp = librosa.sequence.dtw(
            midi_chroma,
            audio_chroma,
            metric='cosine',
            step_sizes_sigma=step_sizes_sigma,
            weights_mul=weights_mul,
            subseq=True
        )
        # wp has shape (N, 2), where column 0 = MIDI, column 1 = Audio.
        # Downstream expects (Audio, MIDI), so we flip it.
        wp = np.fliplr(wp)
    else:
        # Audio is shorter (student played fast). Swapped configuration.
        D, wp = librosa.sequence.dtw(
            audio_chroma,
            midi_chroma,
            metric='cosine',
            step_sizes_sigma=step_sizes_sigma,
            weights_mul=weights_mul,
            subseq=True
        )
        # wp has shape (N, 2), where column 0 = Audio, column 1 = MIDI.
        # This is already the downstream expected format (Audio, MIDI), so no flip is needed!
        pass

    return wp


def get_alignment_mask(midi_notes, time_array, audio_y, sr, hop_length=512, force_global=False):
    """
    Main orchestration function for DTW alignment. 
    1. Synthesizes a reference audio track from the MIDI sequence.
    2. Runs DTW between the real audio and synthetic MIDI audio using Chroma CQT features.
    3. Back-projects the MIDI temporal boundaries onto the real audio timeline.
    4. Generates an inclusion mask that perfectly aligns with the expected notes.
    """
    import numpy as np
    import librosa
    
    # 1. Generate multi-dimensional Chroma features for robust DTW
    midi_chroma = get_midi_chroma(midi_notes, sr, hop_length)
    audio_chroma = get_audio_chroma(audio_y, sr, hop_length)
    
    # 2. Compute DTW on Chroma
    # wp is formatted as [audio_frame, midi_frame]
    wp = compute_dtw_path(midi_chroma, audio_chroma, force_global=force_global)
    
    # 3. Convert DTW path to absolute time mapping
    # Since we set first_start to 0 in get_midi_chroma, the MIDI times are already absolute!
    first_start = 0
    audio_times = librosa.frames_to_time(wp[:, 0], sr=sr, hop_length=hop_length)
    midi_times = librosa.frames_to_time(wp[:, 1], sr=sr, hop_length=hop_length) + first_start
    
    # Ensure audio_times is strictly increasing for np.interp by picking unique audio frames
    unique_audio_times, unique_indices = np.unique(audio_times, return_index=True)
    unique_midi_times = midi_times[unique_indices]
    
    # 4. Interpolate to find exactly where every audio frame lands on the MIDI timeline
    warped_midi_timeline = np.interp(time_array, unique_audio_times, unique_midi_times)
    
    # 5. Build the mask and the expected audio pitch array natively on the audio timeline
    valid_dtw_mask = np.zeros(len(time_array), dtype=bool)
    expected_audio_pitch = np.full(len(time_array), np.nan)
    expected_note_index = np.full(len(time_array), "", dtype=object)
    
    for i, note in enumerate(midi_notes):
        start_time = note['Start_Time'] if isinstance(note, dict) else getattr(note, 'Start_Time', 0)
        end_time = note['End_Time'] if isinstance(note, dict) else getattr(note, 'End_Time', 0)
        pitch = note['Pitch'] if isinstance(note, dict) else getattr(note, 'Pitch', np.nan)
        
        # Find which audio frames' warped timeline falls within this note's duration
        note_mask = (warped_midi_timeline >= start_time) & (warped_midi_timeline < end_time)
        
        valid_dtw_mask[note_mask] = True
        expected_audio_pitch[note_mask] = pitch
        expected_note_index[note_mask] = f"Note {i+1}"
        
    return valid_dtw_mask, expected_audio_pitch, warped_midi_timeline, expected_note_index

def apply_harmonic_folding(f0_hz, expected_midi_pitch):
    """
    Algorithm to mathematically fold the raw extracted pitch (f0) into the target pitch.
    This corrects algorithmic "octave errors" and harmonic confusion (e.g. tracking a Perfect 5th 
    instead of the fundamental) inherent in pYIN when tracking rich acoustic instruments.
    """
    import numpy as np
    import librosa
    
    f0_midi = librosa.hz_to_midi(f0_hz)
    valid_mask = ~np.isnan(f0_midi) & ~np.isnan(expected_midi_pitch)
    
    # 1. Calculate raw deviation
    raw_dev = np.zeros_like(f0_midi)
    raw_dev[valid_mask] = f0_midi[valid_mask] - expected_midi_pitch[valid_mask]
    
    # Gate: only fold if absolute raw deviation >= 11.5 semitones
    # This protects genuine performance errors (e.g., misplaying a 6th or 7th) from being masked as harmonic artifacts
    fold_gate = valid_mask & (np.abs(raw_dev) >= 11.5)
    
    # Start with f0_midi_oct as the unfolded f0_midi
    f0_midi_oct = np.copy(f0_midi)
    
    # 2. Octave Folding (only for those that pass the gate)
    octave_offsets = np.zeros_like(f0_midi)
    octave_offsets[fold_gate] = np.round(raw_dev[fold_gate] / 12.0)
    
    f0_midi_oct[fold_gate] = f0_midi[fold_gate] - (octave_offsets[fold_gate] * 12.0)
    
    # 3. Harmonic Folding (only for those that pass the gate)
    # Recompute residual deviation after octave folding
    dev = np.zeros_like(f0_midi)
    dev[fold_gate] = f0_midi_oct[fold_gate] - expected_midi_pitch[fold_gate]
    
    # Perfect 5th confusion (e.g. 3rd, 6th harmonics) mathematically folds to around -5.0
    is_fifth_harmonic = fold_gate & (dev >= -5.5) & (dev <= -4.5)
    f0_midi_oct[is_fifth_harmonic] += 5.0
    
    # Major 3rd confusion (e.g. 5th harmonic) mathematically folds to around +4.0
    is_third_harmonic = fold_gate & (dev >= 3.5) & (dev <= 4.5)
    f0_midi_oct[is_third_harmonic] -= 4.0
    
    folded_f0_hz = librosa.midi_to_hz(f0_midi_oct)
    
    correction_array = np.full(len(f0_midi), "None", dtype=object)
    for i in range(len(f0_midi)):
        if not fold_gate[i]:
            continue
            
        oct_val = int(np.abs(octave_offsets[i]))
        is_5th = is_fifth_harmonic[i]
        is_3rd = is_third_harmonic[i]
        
        if oct_val == 0 and not is_5th and not is_3rd:
            continue
            
        parts = []
        if oct_val > 0:
            parts.append(f"Octave (x{oct_val})" if oct_val > 1 else "Octave")
        
        if is_5th:
            parts.append("Perfect 5th")
        elif is_3rd:
            parts.append("Major 3rd")
            
        correction_array[i] = " + ".join(parts)
    
    return folded_f0_hz, f0_midi_oct, correction_array

def calculate_dtw_metrics(midi_notes, time_array, f0, rms, final_mask, warped_midi_timeline, correction_array=None, voicing_prob=None, reference_pitch_hz=440.0):
    """
    Extracts the final intonation and amplitude metrics for every note in the sequence.
    It isolates the exact temporal island of the note using the DTW warped timeline, 
    applies the strict pYIN/slope masks, and computes the mathematically robust Median 
    to filter out transient attacks and glissandos.
    """
    import numpy as np
    import librosa
    
    dtw_results = []
    
    # We loop through the exact sequence of true MIDI notes
    for i, note in enumerate(midi_notes):
        start_time = note['Start_Time'] if isinstance(note, dict) else getattr(note, 'Start_Time', 0)
        end_time = note['End_Time'] if isinstance(note, dict) else getattr(note, 'End_Time', 0)
        pitch = note['Pitch'] if isinstance(note, dict) else getattr(note, 'Pitch', np.nan)
        note_name = librosa.midi_to_note(pitch) if not np.isnan(pitch) else "Rest"
        
        # Isolate the audio frames warped to this exact note's time boundary
        note_mask = (warped_midi_timeline >= start_time) & (warped_midi_timeline < end_time)
        
        # Apply the legacy final_mask to strictly filter out transients and slides
        strict_note_mask = note_mask & final_mask
        
        if np.any(strict_note_mask):
            # Extract values
            note_f0 = f0[strict_note_mask]
            note_rms = rms[strict_note_mask]
            
            # Median f0 inside this strict, folded island
            median_f0 = np.nanmedian(note_f0)
            median_midi = librosa.hz_to_midi(median_f0)
            tuning_offset = 1200 * np.log2(reference_pitch_hz / 440.0) / 100.0
            median_midi_corrected = median_midi - tuning_offset

            # Deviation from the TRUE MIDI pitch (cents)
            deviation_cents = (median_midi_corrected - pitch) * 100
            
            # Convert deviation to Hz — shift expected frequency by tuning ratio
            expected_hz = librosa.midi_to_hz(pitch) * (reference_pitch_hz / 440.0)
            deviation_hz = median_f0 - expected_hz
            
            # RMS in dBFS
            median_rms_dbfs = 20 * np.log10(np.nanmedian(note_rms) + 1e-10)
            
            # RMS in dBA
            median_rms_dba = median_rms_dbfs + librosa.A_weighting(median_f0)
            
            # Correction logic
            correction_applied = False
            correction_type = "None"
            if correction_array is not None:
                note_corrections = correction_array[strict_note_mask]
                # Filter out "None"
                actual_corrections = [c for c in note_corrections if c != "None"]
                if actual_corrections:
                    from collections import Counter
                    # Get the most common correction type in this note island
                    correction_type = Counter(actual_corrections).most_common(1)[0][0]
                    correction_applied = True
            
            median_confidence = np.nanmedian(voicing_prob[strict_note_mask]) if voicing_prob is not None else np.nan

            dtw_results.append({
                'Note_Index': i + 1,
                'Expected_Note': note_name,
                'Median_Detected_Pitch_Hz': median_f0,
                'Expected_Target_Pitch_Hz': expected_hz,
                'Deviation_Cents': deviation_cents,
                'Deviation_Hz': deviation_hz,
                'Median_RMS_dBFS': median_rms_dbfs,
                'Median_RMS_dBA': median_rms_dba,
                'Median_Confidence': median_confidence,
                'Correction_Applied': correction_applied,
                'Correction_Type': correction_type
            })
        else:
            # Safeguard for completely empty arrays (Missed or completely filtered out)
            dtw_results.append({
                'Note_Index': i + 1,
                'Expected_Note': note_name,
                'Median_Detected_Pitch_Hz': np.nan,
                'Expected_Target_Pitch_Hz': librosa.midi_to_hz(pitch) * (reference_pitch_hz / 440.0) if not np.isnan(pitch) else np.nan,
                'Deviation_Cents': np.nan,
                'Deviation_Hz': np.nan,
                'Median_RMS_dBFS': np.nan,
                'Median_RMS_dBA': np.nan,
                'Median_Confidence': np.nan,
                'Correction_Applied': False,
                'Correction_Type': "None"
            })
            
    return dtw_results

def process_dtw_alignment(midi_timing, f0_hz, audio_y, sr, final_mask, toggles, max_pitch_slope, hop_length=512):
    """
    Encapsulates the full DTW alignment, harmonic folding, and mask recalculation logic.
    Returns all variables required by the visualizer and metric calculator.
    """
    import librosa
    import numpy as np
    
    time_array = librosa.times_like(f0_hz, sr=sr, hop_length=hop_length)
    
    # 1. Alignment Mask
    force_global = toggles.get('force_global', True)
    mask, expected_pitch, warped_timeline, expected_note_index = get_alignment_mask(
        midi_timing, time_array, audio_y, sr, hop_length=hop_length, force_global=force_global
    )
    
    # 2. Harmonic Folding
    if toggles.get('harmonic_folding', True):
        folded_f0_hz, folded_f0_midi, correction_array = apply_harmonic_folding(f0_hz, expected_pitch)
    else:
        folded_f0_hz = f0_hz
        folded_f0_midi = librosa.hz_to_midi(folded_f0_hz)
        correction_array = np.full(len(f0_hz), "None", dtype=object)
        
    # 3. Slope Mask Recalculation
    folded_pitch_slope = np.concatenate(([0], np.abs(np.diff(folded_f0_midi))))
    if toggles.get('slope_filter', True):
        folded_slope_mask = (folded_pitch_slope <= max_pitch_slope) | np.isnan(folded_pitch_slope)
    else:
        folded_slope_mask = np.ones_like(folded_pitch_slope, dtype=bool)
        
    # 4. Strict Mask for visualization
    strict_mask = mask & final_mask & folded_slope_mask
    
    return time_array, expected_pitch, warped_timeline, expected_note_index, folded_f0_hz, folded_f0_midi, strict_mask, correction_array

