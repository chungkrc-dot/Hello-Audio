import streamlit as st
import librosa
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pretty_midi
import tempfile
import os
from numpy.lib.stride_tricks import as_strided

st.set_page_config(layout="wide")
st.title("Viterbi-Biased Pitch Tracker — Steps 1 & 2")

# --- 1. Instrument Configuration ---
instrument_config = {
    "Violin": {"fmin": 190, "fmax": 3500},
    "Viola": {"fmin": 130, "fmax": 2500},
    "Cello": {"fmin": 60, "fmax": 1500}
}

st.sidebar.header("Settings")
inst_type = st.sidebar.selectbox("Select Instrument", list(instrument_config.keys()))
participant_id = st.sidebar.text_input("Participant ID", "P01")

# --- 2. File Uploaders ---
st.header("Upload Files")
st.markdown(
    "Upload an audio recording and a **MIDI file** (.mid). "
    "This step builds the HMM state space and aligns the MIDI target to audio frames."
)

col1, col2 = st.columns(2)
with col1:
    audio_file = st.file_uploader("Audio Recording", type=['wav', 'mp3', 'm4a'])
with col2:
    midi_file = st.file_uploader("MIDI Reference File", type=['mid'])

# ===========================================================================
# STEP 1a — Define the HMM State Space
# ===========================================================================
def build_state_space(fmin, fmax, cents_resolution=10):
    """Create an array of pitch bins covering [fmin, fmax] at 10-cent resolution.

    Each bin represents a single 'voiced' HMM state. An additional unvoiced
    state is appended as the final index.

    Args:
        fmin: Minimum frequency in Hz for the instrument.
        fmax: Maximum frequency in Hz for the instrument.
        cents_resolution: Bin width in cents (default 10 = 0.1 semitones).

    Returns:
        bin_centers_midi: 1-D array of MIDI note values at the centre of each bin.
        bin_centers_hz:   1-D array of corresponding frequencies in Hz.
        n_bins:           Number of voiced pitch bins.
        step:             Bin width in semitones (cents_resolution / 100).
    """
    step = cents_resolution / 100.0  # 0.1 semitones per bin

    # Convert frequency limits to MIDI and snap to bin boundaries
    midi_lo = np.floor(librosa.hz_to_midi(fmin) / step) * step
    midi_hi = np.ceil(librosa.hz_to_midi(fmax) / step) * step

    bin_centers_midi = np.arange(midi_lo, midi_hi + step * 0.5, step)
    bin_centers_hz = librosa.midi_to_hz(bin_centers_midi)
    n_bins = len(bin_centers_midi)

    return bin_centers_midi, bin_centers_hz, n_bins, step

# ===========================================================================
# STEP 1b — Align MIDI Target Pitches to Audio STFT Frames
# ===========================================================================
def build_midi_target_track(midi_bytes, n_frames, sr, hop_length):
    """Read a MIDI file and produce a per-frame array of expected pitches.

    For each STFT time frame, the array contains the MIDI note number of the
    note that is active at that time, or NaN if no note is sounding (rest).

    Args:
        midi_bytes: Raw bytes of the uploaded .mid file.
        n_frames:   Number of STFT time frames in the audio.
        sr:         Audio sample rate.
        hop_length: STFT hop length in samples.

    Returns:
        target_midi:  1-D array (n_frames,) of MIDI note numbers (float, NaN = rest).
        target_hz:    1-D array (n_frames,) of target frequencies in Hz (NaN = rest).
        frame_times:  1-D array (n_frames,) of frame centre times in seconds.
        notes_list:   List of (start, end, pitch) tuples parsed from the MIDI file.
    """
    # Parse MIDI file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mid') as tm:
        tm.write(midi_bytes)
        m_path = tm.name

    try:
        midi = pretty_midi.PrettyMIDI(m_path)
        notes = []
        for instr in midi.instruments:
            if not instr.is_drum:
                for note in instr.notes:
                    notes.append((note.start, note.end, note.pitch))
        notes.sort(key=lambda x: x[0])
    finally:
        if os.path.exists(m_path):
            os.remove(m_path)

    # Build per-frame target arrays
    frame_times = librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=hop_length)
    target_midi = np.full(n_frames, np.nan)

    for start, end, pitch in notes:
        mask = (frame_times >= start) & (frame_times < end)
        target_midi[mask] = float(pitch)

    # Convert to Hz (NaN stays NaN)
    target_hz = np.full(n_frames, np.nan)
    active = ~np.isnan(target_midi)
    target_hz[active] = librosa.midi_to_hz(target_midi[active])

    return target_midi, target_hz, frame_times, notes

# ===========================================================================
# STEP 2a — YIN CMNDF Computation & Multi-Candidate Extraction
# ===========================================================================
def _compute_yin_cmndf(frame, max_lag):
    """Compute the YIN cumulative mean normalized difference function via FFT.

    The CMNDF d’(τ) normalises the raw difference function d(τ) so that its
    expected value is 1.  Troughs (local minima) below 1 indicate periodic
    signal components; each trough yields a pitch candidate.

    Args:
        frame:   1-D audio frame (float).
        max_lag: Maximum lag to evaluate (inclusive).

    Returns:
        cmndf: 1-D array of length (max_lag + 1).
    """
    W = len(frame)
    tau_max = min(max_lag + 1, W)

    # --- FFT-based autocorrelation ---
    fft_size = 2 ** int(np.ceil(np.log2(2 * W)))
    x_fft = np.fft.rfft(frame, n=fft_size)
    acf = np.fft.irfft(x_fft * np.conj(x_fft), n=fft_size)[:tau_max]

    # --- Difference function d(τ) (vectorised) ---
    sqr = frame ** 2
    cum_sqr = np.cumsum(sqr)
    taus = np.arange(tau_max)

    # e1[τ] = Σ x[j]² for j = 0 … W−1−τ
    e1 = np.zeros(tau_max)
    valid = (W - 1 - taus) >= 0
    e1[valid] = cum_sqr[(W - 1 - taus[valid]).astype(int)]

    # e2[τ] = Σ x[j+τ]² for j = 0 … W−1−τ = cum_sqr[W-1] − cum_sqr[τ-1]
    e2 = np.zeros(tau_max)
    e2[1:] = cum_sqr[W - 1] - cum_sqr[taus[1:].astype(int) - 1]

    d = e1 + e2 - 2.0 * acf
    d[0] = 0.0

    # --- CMNDF d’(τ) (vectorised) ---
    cmndf = np.ones(tau_max)
    cum_d = np.cumsum(d)
    nonzero = (taus > 0) & (cum_d > 0)
    cmndf[nonzero] = (d[nonzero] * taus[nonzero]) / cum_d[nonzero]

    return cmndf


def extract_candidates(y, sr, hop_length, fmin, fmax, frame_length,
                       prob_threshold=0.01):
    """Extract multiple pitch candidates per frame from YIN CMNDF troughs.

    For every audio frame the full YIN cumulative mean normalised difference
    function (CMNDF) is computed, and **all** local minima (troughs) within
    the valid lag range [sr/fmax … sr/fmin] are returned as candidates.
    Each trough is refined with parabolic interpolation for sub-sample
    accuracy, and its probability is derived from the CMNDF value at the
    trough: p = max(0, 1 − cmndf_value).

    Candidates whose probability falls below `prob_threshold` are discarded.
    If the total probability mass exceeds 1.0, candidates are rescaled so
    that Σp ≤ 1 (remainder goes to the unvoiced observation in Step 2b).

    Args:
        y:              Audio time-series (mono, float).
        sr:             Sample rate.
        hop_length:     STFT hop length.
        fmin, fmax:     Instrument frequency range.
        frame_length:   YIN analysis window (samples); must cover ≥2 periods at fmin.
        prob_threshold: Minimum candidate probability to keep.

    Returns:
        candidates: list[list[(freq_hz, probability)]]  — per-frame candidate list.
        n_frames:   Number of analysis frames.
    """
    min_lag = max(2, int(np.ceil(sr / fmax)))
    max_lag = int(np.floor(sr / fmin))

    n_frames = 1 + max(0, (len(y) - frame_length) // hop_length)
    candidates = []

    for t in range(n_frames):
        start = t * hop_length
        frame = y[start:start + frame_length]
        if len(frame) < frame_length:
            frame = np.pad(frame, (0, frame_length - len(frame)))

        cmndf = _compute_yin_cmndf(frame, max_lag + 1)

        # --- Find ALL local-minimum troughs in [min_lag, max_lag] ---
        frame_cands = []
        search_hi = min(max_lag, len(cmndf) - 2)   # need τ+1 in bounds
        for tau in range(min_lag + 1, search_hi + 1):
            if cmndf[tau] < cmndf[tau - 1] and cmndf[tau] <= cmndf[tau + 1]:
                # Parabolic interpolation for sub-sample lag precision
                alpha = cmndf[tau - 1]
                beta  = cmndf[tau]
                gamma = cmndf[tau + 1]
                denom = alpha + gamma - 2.0 * beta
                if denom > 1e-12:
                    delta = 0.5 * (alpha - gamma) / denom
                    refined_tau   = tau + delta
                    refined_cmndf = beta - 0.25 * (alpha - gamma) * delta
                else:
                    refined_tau   = float(tau)
                    refined_cmndf = beta

                freq = sr / refined_tau
                prob = max(0.0, 1.0 - refined_cmndf)

                if prob >= prob_threshold and fmin * 0.95 <= freq <= fmax * 1.05:
                    frame_cands.append((freq, prob))

        # Sort by probability (descending) and cap at 10 candidates
        frame_cands.sort(key=lambda x: -x[1])
        frame_cands = frame_cands[:10]

        # Normalise so total probability mass ≤ 1.0
        total = sum(p for _, p in frame_cands)
        if total > 1.0:
            frame_cands = [(f, p / total) for f, p in frame_cands]

        candidates.append(frame_cands)

    return candidates, n_frames


# ===========================================================================
# STEP 2b — Build Observation Probability Matrix
# ===========================================================================
def build_observation_matrix(candidates, n_frames, bin_centers_midi, n_bins, step):
    """Compute per-frame observation probabilities for voiced & unvoiced states.

    State layout (per pitch bin b):
        Voiced state  = index  2*b
        Unvoiced state = index  2*b + 1
    Total states = 2 * n_bins

    Observation probabilities follow the pYIN specification:
        For each candidate, its probability mass is assigned to the nearest
        pitch-bin's *voiced* state:   P_obs(voiced, b) = 0.5 × p_candidate
        The complementary mass goes to every bin's *unvoiced* state uniformly:
                                      P_obs(unvoiced, b) = 0.5 × (1 − Σp) / n_bins
        where Σp is the total voiced probability mass for that frame.

    Args:
        candidates:      Per-frame candidate list from extract_candidates().
        n_frames:        Number of analysis frames.
        bin_centers_midi: 1-D array of bin centres (MIDI values) from Step 1a.
        n_bins:          Number of pitch bins.
        step:            Bin width in semitones.

    Returns:
        obs_prob: ndarray (n_frames, 2 * n_bins) of observation probabilities.
                  Column 2*b = voiced state for bin b,
                  Column 2*b+1 = unvoiced state for bin b.
    """
    n_states = 2 * n_bins
    obs_prob = np.zeros((n_frames, n_states))
    midi_lo = bin_centers_midi[0]

    for t in range(n_frames):
        frame_cands = candidates[t] if t < len(candidates) else []

        # --- Voiced observation: assign each candidate to its nearest bin ---
        total_voiced_prob = 0.0
        for freq, conf in frame_cands:
            midi_val = librosa.hz_to_midi(freq)
            bin_idx = int(np.round((midi_val - midi_lo) / step))
            bin_idx = np.clip(bin_idx, 0, n_bins - 1)

            voiced_col = 2 * bin_idx       # voiced state for this bin
            obs_prob[t, voiced_col] += 0.5 * conf
            total_voiced_prob += conf

        # Clamp total to [0, 1] for safety
        total_voiced_prob = min(total_voiced_prob, 1.0)

        # --- Unvoiced observation: spread complement uniformly ---
        unvoiced_per_bin = 0.5 * (1.0 - total_voiced_prob) / max(n_bins, 1)
        for b in range(n_bins):
            obs_prob[t, 2 * b + 1] = unvoiced_per_bin

    return obs_prob

# ===========================================================================
# STEP 3 — Custom Viterbi Decoder (Log-Domain, Sparse + Teleportation)
# ===========================================================================
def viterbi_decode(obs_prob, n_frames, n_bins, bin_centers_midi, bin_centers_hz,
                   step, target_midi_per_frame,
                   max_jump=25, teleport_sigma=5, p_teleport=0.10):
    """Log-domain Viterbi decoder with sparse transitions and MIDI teleportation.

    ALL arithmetic uses log-probabilities (additions instead of multiplications)
    with epsilon guards to prevent log(0). This eliminates floating-point
    underflow entirely.

    Transition model (hybrid sparse + teleportation):

    1. **Smooth (sparse)**:  Standard ±max_jump triangular window centred at
       the SOURCE bin.  Tracks fine human intonation with pitch continuity.
       Used with probability (1 − p_teleport).

    2. **Teleportation (MIDI-active frames only)**:  A Gaussian concentrated
       at the MIDI target bin (σ = teleport_sigma) that can be reached from
       ANY previous voiced state.  Enables instant large-interval jumps.
       Used with probability p_teleport.

    For each destination bin the decoder takes max(smooth, teleport).
    During rest frames (NaN target) only the smooth path is active.

    Voicing transitions:
        P(stay same voicing)  = 0.99
        P(switch voicing)     = 0.01

    Args:
        obs_prob:              (n_frames, 2*n_bins) observation matrix from Step 2b.
        n_frames:              Number of analysis frames.
        n_bins:                Number of pitch bins.
        bin_centers_midi:      1-D array of bin centres (MIDI values).
        bin_centers_hz:        1-D array of bin centres (Hz).
        step:                  Bin width in semitones.
        target_midi_per_frame: 1-D array (n_frames,) of MIDI targets (NaN = rest).
        max_jump:              Smooth-window half-width in bins (default 25).
        teleport_sigma:        Gaussian σ for the teleportation weight (bins).
        p_teleport:            Probability mass allocated to the teleport path.

    Returns:
        f0:     1-D array (n_frames,) of decoded Hz (NaN = unvoiced).
        voiced: 1-D boolean array.
        path:   1-D int array of state indices.
    """
    EPS = 1e-10
    UNVOICED = n_bins
    LOG_ZERO = -1e9
    LOG_STAY   = np.log(0.99)
    LOG_SWITCH = np.log(0.01)
    LOG_P_SMOOTH = np.log(1.0 - p_teleport)   # ≈ log(0.90)
    LOG_P_TELEPORT = np.log(p_teleport)        # ≈ log(0.10)
    midi_lo = bin_centers_midi[0]
    j_idx = np.arange(n_bins, dtype=float)

    # ---- 1. Observation log-probabilities (with epsilon guard) ----
    voiced_obs = obs_prob[:, 0::2]                       # (n_frames, n_bins)
    log_obs_v = np.log(voiced_obs + EPS)                 # safe: never -inf

    uv_obs = obs_prob[:, 1::2].sum(axis=1)               # (n_frames,)
    log_obs_u = np.log(uv_obs + EPS)

    # ---- 2. Smooth triangular kernel (sparse, ±max_jump) ----
    window_size = 2 * max_jump + 1
    k = np.arange(window_size)
    raw_tri = np.maximum(EPS, 1.0 - np.abs(k - max_jump) / max_jump)
    raw_tri /= raw_tri.sum()
    log_tri_kernel = np.log(raw_tri)                     # (window_size,)

    # Padded buffer for stride-trick windowed max (re-used every frame)
    padded = np.full(n_bins + 2 * max_jump, LOG_ZERO)

    # ---- 3. Viterbi tables ----
    n_states = n_bins + 1
    V = np.full((n_frames, n_states), LOG_ZERO)
    B = np.full((n_frames, n_states), -1, dtype=np.int32)

    V[0, :n_bins] = np.log(0.5 / n_bins + EPS) + log_obs_v[0]
    V[0, UNVOICED] = np.log(0.5 + EPS) + log_obs_u[0]

    # ---- 4. Forward pass ----
    for t in range(1, n_frames):
        prev_v = V[t - 1, :n_bins]                       # (n_bins,)
        tgt = target_midi_per_frame[t] if t < len(target_midi_per_frame) else np.nan
        has_target = not np.isnan(tgt)

        # ============================================================
        # A. SMOOTH PATH  (V→V, sparse ±max_jump window)
        # ============================================================
        # Stride-trick: create (n_bins, window_size) view into padded array.
        # windows[b_j, k] = prev_v[b_j - max_jump + k]  (LOG_ZERO if OOB)
        padded[:] = LOG_ZERO
        padded[max_jump:max_jump + n_bins] = prev_v

        stride = padded.strides[0]
        windows = as_strided(padded, shape=(n_bins, window_size),
                             strides=(stride, stride))   # (n_bins, 51)

        scores_smooth = windows + LOG_STAY + LOG_P_SMOOTH + log_tri_kernel  # (n_bins, 51)
        best_k = np.argmax(scores_smooth, axis=1)         # (n_bins,)
        smooth_val = scores_smooth[np.arange(n_bins), best_k]  # (n_bins,)
        smooth_src = np.clip(np.arange(n_bins) - max_jump + best_k, 0, n_bins - 1)

        # ============================================================
        # B. TELEPORTATION PATH  (V→V, jump from ANY state to target)
        # ============================================================
        if has_target:
            target_bin = (tgt - midi_lo) / step
            tele_gauss = np.exp(-0.5 * ((j_idx - target_bin) / teleport_sigma) ** 2)
            tele_gauss /= (tele_gauss.sum() + EPS)
            log_tele_w = np.log(tele_gauss + EPS)          # (n_bins,)

            # Best global voiced predecessor (unrestricted source)
            best_global_idx = int(np.argmax(prev_v))
            best_global_val = prev_v[best_global_idx]

            teleport_val = best_global_val + LOG_STAY + LOG_P_TELEPORT + log_tele_w
        else:
            teleport_val = np.full(n_bins, LOG_ZERO)       # no teleport during rests
            best_global_idx = 0                            # unused placeholder

        # ============================================================
        # C. Combine smooth & teleport  →  best V→V path
        # ============================================================
        tele_wins = teleport_val > smooth_val
        vv_score = np.where(tele_wins, teleport_val, smooth_val)
        vv_src   = np.where(tele_wins, best_global_idx, smooth_src).astype(np.int32)

        # ============================================================
        # D. U→V path (unvoiced → voiced)
        # ============================================================
        if has_target:
            uv_score = V[t - 1, UNVOICED] + LOG_SWITCH + log_tele_w
        else:
            uv_score = np.full(n_bins, V[t - 1, UNVOICED] + LOG_SWITCH
                               + np.log(1.0 / n_bins + EPS))

        # ============================================================
        # E. Best predecessor for each voiced destination
        # ============================================================
        uv_wins = uv_score > vv_score
        V[t, :n_bins] = np.where(uv_wins, uv_score, vv_score) + log_obs_v[t]
        B[t, :n_bins] = np.where(uv_wins, UNVOICED, vv_src)

        # ============================================================
        # F. Unvoiced destination
        # ============================================================
        best_v_for_u = int(np.argmax(prev_v))
        from_v_u = prev_v[best_v_for_u] + LOG_SWITCH
        from_u_u = V[t - 1, UNVOICED] + LOG_STAY

        if from_u_u >= from_v_u:
            V[t, UNVOICED] = from_u_u + log_obs_u[t]
            B[t, UNVOICED] = UNVOICED
        else:
            V[t, UNVOICED] = from_v_u + log_obs_u[t]
            B[t, UNVOICED] = best_v_for_u

    # ---- 5. Backtrace ----
    path = np.full(n_frames, -1, dtype=np.int32)
    path[-1] = int(np.argmax(V[-1]))
    for t in range(n_frames - 2, -1, -1):
        path[t] = B[t + 1, path[t + 1]]

    # ---- 6. Convert state path → frequency track ----
    f0 = np.full(n_frames, np.nan)
    voiced = np.zeros(n_frames, dtype=bool)
    v_mask = path < n_bins
    f0[v_mask] = bin_centers_hz[path[v_mask]]
    voiced[v_mask] = True

    return f0, voiced, path

# ===========================================================================
# --- 4. Main Execution ---
# ===========================================================================
if st.button("Run Steps 1–3", type="primary"):
    fmin = instrument_config[inst_type]["fmin"]
    fmax = instrument_config[inst_type]["fmax"]

    # ---- Step 1a: State Space ----
    bin_centers_midi, bin_centers_hz, n_bins, step = build_state_space(fmin, fmax)

    st.subheader("Step 1a — HMM State Space")
    st.markdown(f"""
    | Parameter | Value |
    |---|---|
    | Instrument | **{inst_type}** |
    | Frequency range | **{fmin} Hz** — **{fmax} Hz** |
    | MIDI range | **{bin_centers_midi[0]:.1f}** — **{bin_centers_midi[-1]:.1f}** |
    | Bin resolution | **{int(step * 100)} cents** ({step} semitones) |
    | Voiced pitch bins | **{n_bins}** |
    | + Unvoiced state | **1** |
    | **Total HMM states** | **{n_bins + 1}** |
    """)

    # Show a sample of the bin array
    sample_idx = np.linspace(0, n_bins - 1, min(20, n_bins), dtype=int)
    sample_df = pd.DataFrame({
        "Bin Index": sample_idx,
        "MIDI Value": np.round(bin_centers_midi[sample_idx], 2),
        "Frequency (Hz)": np.round(bin_centers_hz[sample_idx], 2),
        "Note Name": [librosa.midi_to_note(m) for m in bin_centers_midi[sample_idx]]
    })
    st.markdown("**Sample pitch bins** (evenly spaced across the range):")
    st.dataframe(sample_df, use_container_width=True, hide_index=True)

    # ---- Step 1b: MIDI → Frame Alignment ----
    if audio_file is None or midi_file is None:
        st.info("Upload both an audio file and a MIDI file to see the frame-aligned target.")
    else:
        audio_file.seek(0)
        midi_file.seek(0)
        audio_bytes = audio_file.getvalue()
        midi_bytes = midi_file.getvalue()

        # Load audio to determine frame count
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as ta:
            ta.write(audio_bytes)
            a_path = ta.name

        try:
            y, sr = librosa.load(a_path, sr=22050)
            hop_length = 512
            n_frames = 1 + len(y) // hop_length

            target_midi, target_hz, frame_times, notes_list = build_midi_target_track(
                midi_bytes, n_frames, sr, hop_length
            )

            st.subheader("Step 1b — MIDI-to-Frame Alignment")

            # Summary metrics
            n_active = int(np.sum(~np.isnan(target_midi)))
            n_rest = int(np.sum(np.isnan(target_midi)))
            unique_pitches = np.unique(target_midi[~np.isnan(target_midi)])

            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Total Frames", n_frames)
            col_b.metric("Active Frames", n_active)
            col_c.metric("Rest Frames", n_rest)
            col_d.metric("Unique Pitches", len(unique_pitches))

            # MIDI notes table
            st.markdown("**Parsed MIDI Notes:**")
            notes_df = pd.DataFrame(notes_list, columns=["Start (s)", "End (s)", "MIDI Pitch"])
            notes_df["Duration (s)"] = np.round(notes_df["End (s)"] - notes_df["Start (s)"], 3)
            notes_df["Frequency (Hz)"] = np.round(librosa.midi_to_hz(notes_df["MIDI Pitch"].values), 2)
            notes_df["Note Name"] = [librosa.midi_to_note(int(m)) for m in notes_df["MIDI Pitch"]]
            notes_df.insert(0, "Note #", range(1, len(notes_df) + 1))
            st.dataframe(notes_df, use_container_width=True, hide_index=True)

            # Verify: which state-space bin does each MIDI target map to?
            st.markdown("**MIDI Target → State-Space Bin Mapping:**")
            map_rows = []
            for _, row in notes_df.iterrows():
                pitch = row["MIDI Pitch"]
                bin_idx = int(np.round((pitch - bin_centers_midi[0]) / step))
                bin_idx_clamped = np.clip(bin_idx, 0, n_bins - 1)
                map_rows.append({
                    "Note #": row["Note #"],
                    "MIDI Pitch": pitch,
                    "Note Name": row["Note Name"],
                    "Target Bin Index": bin_idx_clamped,
                    "Bin Centre (MIDI)": round(bin_centers_midi[bin_idx_clamped], 2),
                    "Bin Centre (Hz)": round(bin_centers_hz[bin_idx_clamped], 2),
                    "Quantisation Error (cents)": round((pitch - bin_centers_midi[bin_idx_clamped]) * 100, 1)
                })
            map_df = pd.DataFrame(map_rows)
            st.dataframe(map_df, use_container_width=True, hide_index=True)

            # Visualise the per-frame target track
            st.markdown("**Per-Frame Target Pitch Track:**")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=frame_times, y=target_hz,
                name="MIDI Target (Hz)",
                mode="lines",
                line=dict(color="rgba(255, 165, 0, 0.8)", width=2, shape="hv"),
            ))
            fig.update_layout(
                xaxis_title="Time (s)", yaxis_title="Frequency (Hz)",
                title="MIDI Target Aligned to Audio STFT Frames",
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)

            # Raw frame-level data (collapsible)
            with st.expander("📊 Raw Frame-Level Target Array (first 200 frames)"):
                frame_df = pd.DataFrame({
                    "Frame": np.arange(min(200, n_frames)),
                    "Time (s)": np.round(frame_times[:200], 4),
                    "Target MIDI": np.round(target_midi[:200], 2),
                    "Target Hz": np.round(target_hz[:200], 2)
                })
                st.dataframe(frame_df, use_container_width=True, hide_index=True)

            # ================================================================
            # STEP 2 — Observation Probabilities
            # ================================================================
            st.divider()
            st.subheader("Step 2a — YIN CMNDF Multi-Candidate Extraction")

            frame_length = max(2048, 2 * int(np.ceil(sr / fmin)) + 1)
            frame_length = 2 ** int(np.ceil(np.log2(frame_length)))

            with st.spinner("Computing YIN CMNDF and extracting trough candidates..."):
                candidates, n_frames_cand = extract_candidates(
                    y, sr, hop_length, fmin, fmax, frame_length
                )

            # Candidate count distribution
            cand_counts = np.array([len(c) for c in candidates])
            frames_0   = int(np.sum(cand_counts == 0))
            frames_1   = int(np.sum(cand_counts == 1))
            frames_2p  = int(np.sum(cand_counts >= 2))
            avg_cands  = float(np.mean(cand_counts)) if len(cand_counts) else 0

            st.markdown(f"""
            | Parameter | Value |
            |---|---|
            | Analysis frame length | **{frame_length}** samples |
            | YIN lag range | **{max(2, int(np.ceil(sr/fmax)))}** – **{int(np.floor(sr/fmin))}** samples |
            | Total candidate frames | **{n_frames_cand}** |
            | Frames with 0 candidates | **{frames_0}** ({100*frames_0/max(n_frames_cand,1):.1f}%) |
            | Frames with exactly 1 | **{frames_1}** ({100*frames_1/max(n_frames_cand,1):.1f}%) |
            | Frames with ≥2 candidates | **{frames_2p}** ({100*frames_2p/max(n_frames_cand,1):.1f}%) |
            | Average candidates/frame | **{avg_cands:.2f}** |
            | Max candidates in a frame | **{int(np.max(cand_counts)) if len(cand_counts) else 0}** |
            """)

            # Candidate-count histogram
            st.markdown("**Candidate count distribution:**")
            count_vals, count_freq = np.unique(cand_counts, return_counts=True)
            fig_hist = go.Figure(data=go.Bar(
                x=count_vals, y=count_freq,
                text=count_freq, textposition="auto",
                marker_color="steelblue"
            ))
            fig_hist.update_layout(
                xaxis_title="Candidates per Frame",
                yaxis_title="Number of Frames",
                title="Distribution of Candidate Counts",
                height=350
            )
            st.plotly_chart(fig_hist, use_container_width=True)

            # Show sample candidates (first 30 frames that have ≥2 candidates)
            st.markdown("**Sample multi-candidate frames** (first 30 frames with ≥2 candidates):")
            sample_rows = []
            count = 0
            for t in range(n_frames_cand):
                if count >= 30:
                    break
                if len(candidates[t]) >= 2:
                    for rank, (freq, conf) in enumerate(candidates[t]):
                        midi_val = librosa.hz_to_midi(freq)
                        bin_idx = int(np.round((midi_val - bin_centers_midi[0]) / step))
                        bin_idx = np.clip(bin_idx, 0, n_bins - 1)
                        sample_rows.append({
                            "Frame": t,
                            "Time (s)": round(frame_times[t] if t < len(frame_times) else t * hop_length / sr, 4),
                            "Rank": rank + 1,
                            "Freq (Hz)": round(freq, 2),
                            "MIDI": round(midi_val, 2),
                            "Probability": round(conf, 4),
                            "Nearest Bin": bin_idx,
                            "Bin Centre (MIDI)": round(bin_centers_midi[bin_idx], 2)
                        })
                    count += 1
            if sample_rows:
                st.dataframe(pd.DataFrame(sample_rows), use_container_width=True, hide_index=True)
            else:
                st.info("No frames with ≥2 candidates found. Showing single-candidate frames instead.")
                for t in range(min(30, n_frames_cand)):
                    if len(candidates[t]) >= 1:
                        for rank, (freq, conf) in enumerate(candidates[t]):
                            midi_val = librosa.hz_to_midi(freq)
                            bin_idx = int(np.round((midi_val - bin_centers_midi[0]) / step))
                            bin_idx = np.clip(bin_idx, 0, n_bins - 1)
                            sample_rows.append({
                                "Frame": t,
                                "Time (s)": round(frame_times[t] if t < len(frame_times) else t * hop_length / sr, 4),
                                "Rank": rank + 1,
                                "Freq (Hz)": round(freq, 2),
                                "MIDI": round(midi_val, 2),
                                "Probability": round(conf, 4),
                                "Nearest Bin": bin_idx,
                                "Bin Centre (MIDI)": round(bin_centers_midi[bin_idx], 2)
                            })
                if sample_rows:
                    st.dataframe(pd.DataFrame(sample_rows), use_container_width=True, hide_index=True)

            # ---- Step 2b: Observation Matrix ----
            st.subheader("Step 2b — Observation Probability Matrix")

            with st.spinner("Building observation probability matrix..."):
                obs_prob = build_observation_matrix(
                    candidates, n_frames_cand, bin_centers_midi, n_bins, step
                )

            n_states = 2 * n_bins
            st.markdown(f"""
            | Parameter | Value |
            |---|---|
            | Pitch bins | **{n_bins}** |
            | States per bin | **2** (voiced + unvoiced) |
            | Total observation states | **{n_states}** |
            | Matrix shape | **({n_frames_cand}, {n_states})** |
            """)

            # Per-frame probability mass diagnostics
            voiced_cols = obs_prob[:, 0::2]    # all voiced columns
            unvoiced_cols = obs_prob[:, 1::2]   # all unvoiced columns
            total_per_frame = obs_prob.sum(axis=1)
            voiced_per_frame = voiced_cols.sum(axis=1)
            unvoiced_per_frame = unvoiced_cols.sum(axis=1)

            st.markdown("**Probability mass diagnostics (should sum to ≈0.5 voiced + 0.5 unvoiced = 1.0):**")
            diag_df = pd.DataFrame({
                "Statistic": ["Mean", "Std", "Min", "Max"],
                "Total P(frame)": [
                    round(np.mean(total_per_frame), 6),
                    round(np.std(total_per_frame), 6),
                    round(np.min(total_per_frame), 6),
                    round(np.max(total_per_frame), 6)
                ],
                "Voiced Σ": [
                    round(np.mean(voiced_per_frame), 6),
                    round(np.std(voiced_per_frame), 6),
                    round(np.min(voiced_per_frame), 6),
                    round(np.max(voiced_per_frame), 6)
                ],
                "Unvoiced Σ": [
                    round(np.mean(unvoiced_per_frame), 6),
                    round(np.std(unvoiced_per_frame), 6),
                    round(np.min(unvoiced_per_frame), 6),
                    round(np.max(unvoiced_per_frame), 6)
                ]
            })
            st.dataframe(diag_df, use_container_width=True, hide_index=True)

            # --- Single-frame voiced-bin verification ---
            st.markdown("---")
            st.markdown("**🔍 Single-Frame Verification — Non-Zero Voiced Bins**")

            # Find the first frame with ≥2 candidates
            verify_frame = None
            for t_check in range(n_frames_cand):
                if len(candidates[t_check]) >= 2:
                    verify_frame = t_check
                    break

            if verify_frame is not None:
                # Extract only voiced columns for this frame (even indices)
                frame_voiced = voiced_cols[verify_frame]  # shape (n_bins,)
                nonzero_bins = np.where(frame_voiced > 0)[0]

                st.markdown(
                    f"Inspecting **frame {verify_frame}** "
                    f"(time ≈ {frame_times[verify_frame] if verify_frame < len(frame_times) else verify_frame * hop_length / sr:.4f} s), "
                    f"which has **{len(candidates[verify_frame])} candidates**:"
                )

                if len(nonzero_bins) > 0:
                    verify_rows = []
                    for b in nonzero_bins:
                        verify_rows.append({
                            "Bin Index": int(b),
                            "MIDI Value": round(bin_centers_midi[b], 2),
                            "Frequency (Hz)": round(bin_centers_hz[b], 2),
                            "Note Name": librosa.midi_to_note(bin_centers_midi[b]),
                            "P(voiced)": round(float(frame_voiced[b]), 6)
                        })
                    st.dataframe(pd.DataFrame(verify_rows), use_container_width=True, hide_index=True)

                    if len(nonzero_bins) >= 2:
                        st.success(
                            f"✅ **{len(nonzero_bins)} non-zero voiced bins** found for this frame. "
                            f"Multi-candidate mapping is confirmed — ready for Step 3."
                        )
                    else:
                        st.warning(
                            f"⚠️ Only {len(nonzero_bins)} non-zero voiced bin found for this frame, "
                            f"despite {len(candidates[verify_frame])} candidates. "
                            f"Candidates may have mapped to the same bin."
                        )
                else:
                    st.warning("No non-zero voiced bins found for this frame.")
            else:
                st.info("No frames with ≥2 candidates were found in this recording.")

            # Heatmap of voiced observation probabilities
            st.markdown("**Voiced observation probability heatmap** (first 300 frames, top-active bins):")
            n_show_frames = min(300, n_frames_cand)
            # Find the bins that have the most total voiced probability
            bin_activity = voiced_cols[:n_show_frames].sum(axis=0)
            top_bins = np.argsort(bin_activity)[-40:]  # show top 40 most active bins
            top_bins = np.sort(top_bins)

            if len(top_bins) > 0:
                heatmap_data = voiced_cols[:n_show_frames, top_bins].T
                heatmap_times = frame_times[:n_show_frames] if n_show_frames <= len(frame_times) else np.arange(n_show_frames) * hop_length / sr
                heatmap_labels = [f"{bin_centers_midi[b]:.1f}" for b in top_bins]

                fig_heat = go.Figure(data=go.Heatmap(
                    z=heatmap_data,
                    x=np.round(heatmap_times, 3),
                    y=heatmap_labels,
                    colorscale="YlOrRd",
                    colorbar_title="P(voiced)"
                ))
                fig_heat.update_layout(
                    title="Voiced Observation Probabilities (top active bins)",
                    xaxis_title="Time (s)", yaxis_title="Pitch Bin (MIDI)",
                    height=500
                )
                st.plotly_chart(fig_heat, use_container_width=True)

            # Show raw matrix slice (collapsible)
            with st.expander("📊 Raw Observation Matrix (first 50 frames, top 10 bins)"):
                top10 = np.sort(np.argsort(bin_activity)[-10:])
                rows = []
                for t_idx in range(min(50, n_frames_cand)):
                    row_data = {"Frame": t_idx}
                    for b in top10:
                        midi_label = f"{bin_centers_midi[b]:.1f}"
                        row_data[f"V({midi_label})"] = round(obs_prob[t_idx, 2 * b], 6)
                        row_data[f"U({midi_label})"] = round(obs_prob[t_idx, 2 * b + 1], 6)
                    rows.append(row_data)
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # ================================================================
            # STEP 3 — Viterbi Decoding
            # ================================================================
            st.divider()
            st.subheader("Step 3 — Viterbi-Biased Pitch Track")

            with st.spinner("Running Viterbi decoder (log-domain, sparse + teleport)..."):
                f0_viterbi, voiced_viterbi, path_viterbi = viterbi_decode(
                    obs_prob, n_frames_cand, n_bins, bin_centers_midi,
                    bin_centers_hz, step, target_midi,
                    max_jump=25, teleport_sigma=5, p_teleport=0.10
                )

            # --- 3a. Summary metrics ---
            n_voiced = int(np.sum(voiced_viterbi))
            n_unvoiced = n_frames_cand - n_voiced
            pct_voiced = 100 * n_voiced / max(n_frames_cand, 1)

            # Mean deviation from MIDI target (voiced frames with active target)
            active_mask = voiced_viterbi & (~np.isnan(target_midi[:n_frames_cand]))
            if np.any(active_mask):
                f0_active = f0_viterbi[active_mask]
                tgt_active = target_hz[:n_frames_cand][active_mask]
                cents_dev = 1200.0 * np.log2(f0_active / tgt_active)
                mean_abs_cents = float(np.mean(np.abs(cents_dev)))
                mean_abs_hz = float(np.mean(np.abs(f0_active - tgt_active)))
            else:
                mean_abs_cents = np.nan
                mean_abs_hz = np.nan

            st.markdown(f"""
            | Parameter | Value |
            |---|---|
            | Smooth window | **±25 bins** (2.5 st), triangular, P = **0.90** |
            | Teleportation | Gaussian σ = **5 bins**, P = **0.10**, targets MIDI bin |
            | P(stay voicing) / P(switch) | **0.99 / 0.01** |
            | Voiced frames | **{n_voiced}** ({pct_voiced:.1f}%) |
            | Unvoiced frames | **{n_unvoiced}** ({100 - pct_voiced:.1f}%) |
            | Mean |deviation| from MIDI | **{mean_abs_cents:.1f} cents** / **{mean_abs_hz:.2f} Hz** |
            """)

            # --- 3b. Pitch track plot ---
            viterbi_times = frame_times[:n_frames_cand] if n_frames_cand <= len(frame_times) else np.arange(n_frames_cand) * hop_length / sr

            fig_v = go.Figure()

            # MIDI target (orange step)
            fig_v.add_trace(go.Scatter(
                x=viterbi_times, y=target_hz[:n_frames_cand],
                name="MIDI Target", mode="lines",
                line=dict(color="rgba(255, 165, 0, 0.5)", width=4, shape="hv"),
            ))

            # Viterbi f0 (blue solid)
            fig_v.add_trace(go.Scatter(
                x=viterbi_times, y=f0_viterbi,
                name="Viterbi-Biased f0", mode="lines",
                line=dict(color="rgba(65, 105, 225, 0.9)", width=2),
            ))

            fig_v.update_layout(
                title="Viterbi-Biased Pitch Track vs MIDI Target",
                xaxis_title="Time (s)", yaxis_title="Frequency (Hz)",
                hovermode="x unified", height=500
            )
            st.plotly_chart(fig_v, use_container_width=True)

            # --- 3c. Per-note deviation table ---
            st.markdown("**Per-Note Deviation Analysis:**")
            note_rows = []
            for idx, (n_start, n_end, n_pitch) in enumerate(notes_list):
                t_hz_note = librosa.midi_to_hz(n_pitch)
                mask_note = (
                    (viterbi_times >= n_start)
                    & (viterbi_times < n_end)
                    & voiced_viterbi[:len(viterbi_times)]
                )
                f0_in = f0_viterbi[:len(viterbi_times)][mask_note]

                if len(f0_in) == 0:
                    note_rows.append({
                        "Note #": idx + 1, "MIDI": n_pitch,
                        "Note Name": librosa.midi_to_note(n_pitch),
                        "Target (Hz)": round(t_hz_note, 2),
                        "Median f0 (Hz)": None,
                        "Deviation (cents)": None,
                        "Deviation (Hz)": None,
                        "Voiced Frames": 0
                    })
                    continue

                med = float(np.median(f0_in))
                c_dev = 1200.0 * np.log2(med / t_hz_note)
                h_dev = med - t_hz_note

                note_rows.append({
                    "Note #": idx + 1, "MIDI": n_pitch,
                    "Note Name": librosa.midi_to_note(n_pitch),
                    "Target (Hz)": round(t_hz_note, 2),
                    "Median f0 (Hz)": round(med, 2),
                    "Deviation (cents)": round(c_dev, 1),
                    "Deviation (Hz)": round(h_dev, 2),
                    "Voiced Frames": int(np.sum(mask_note))
                })

            if note_rows:
                note_df = pd.DataFrame(note_rows)
                st.dataframe(note_df, use_container_width=True, hide_index=True)

                csv_notes = note_df.to_csv(index=False)
                st.download_button(
                    "📥 Download Per-Note CSV", csv_notes,
                    file_name=f"{participant_id}_viterbi_notes.csv",
                    mime="text/csv"
                )

            # --- 3d. Raw path data (collapsible) ---
            with st.expander("📊 Raw Viterbi Path (first 200 frames)"):
                n_show = min(200, n_frames_cand)
                raw_df = pd.DataFrame({
                    "Frame": np.arange(n_show),
                    "Time (s)": np.round(viterbi_times[:n_show], 4),
                    "State": path_viterbi[:n_show],
                    "Voiced": voiced_viterbi[:n_show],
                    "f0 (Hz)": np.round(np.nan_to_num(f0_viterbi[:n_show], nan=0), 2),
                    "Target MIDI": np.round(np.nan_to_num(target_midi[:n_show], nan=0), 1),
                    "Target Hz": np.round(np.nan_to_num(target_hz[:n_show], nan=0), 2)
                })
                st.dataframe(raw_df, use_container_width=True, hide_index=True)

        finally:
            if os.path.exists(a_path):
                os.remove(a_path)
