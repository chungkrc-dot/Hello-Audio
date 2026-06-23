import streamlit as st
import librosa
import numpy as np
import pandas as pd
import pretty_midi
import tempfile
import os
import plotly.graph_objects as go

st.title("Acoustic Analysis (Optimized for Strings)")

# 1. Sidebar - Instrument Configuration
instrument_config = {
    "Violin": {"fmin": 190, "fmax": 3500},
    "Viola": {"fmin": 130, "fmax": 2500},
    "Cello": {"fmin": 60, "fmax": 1500}
}

st.sidebar.header("Settings")
inst_type = st.sidebar.selectbox("Select Instrument", list(instrument_config.keys()))
participant_id = st.sidebar.text_input("Participant ID", "P01")

audio_file = st.file_uploader("Upload Audio", type=['wav', 'mp3', 'm4a'])
midi_file = st.file_uploader("Upload MIDI", type=['mid'])

# Only proceed with the analysis if both audio and MIDI files have been uploaded
if audio_file and midi_file:
    if st.button("Extract Data"):
        with st.spinner("Analyzing with optimized pYIN..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as ta:
                ta.write(audio_file.read()); a_path = ta.name
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mid') as tm:
                tm.write(midi_file.read()); m_path = tm.name

            try:
                y, sr = librosa.load(a_path, sr=22050)
                hop_length = 512
                
                # Calculate mean RMS amplitude
                rms_data = librosa.feature.rms(y=y, hop_length=hop_length)
                mean_rms = np.mean(rms_data)
                
                # 2. Optimized pYIN Parameters
                f0, voiced, _ = librosa.pyin(
                    y, 
                    fmin=instrument_config[inst_type]["fmin"], 
                    fmax=instrument_config[inst_type]["fmax"], 
                    hop_length=hop_length,
                    no_trough_prob=0.01, # More forgiving of weak signals
                    switch_prob=0.001    # More stable state transitions
                )
                
                # 3. MIDI Target & DTW Alignment
                midi = pretty_midi.PrettyMIDI(m_path)
                fps = sr / hop_length
                target_f0 = np.zeros_like(f0)
                for instrument in midi.instruments:
                    if not instrument.is_drum:
                        for note in instrument.notes:
                            start_idx, end_idx = int(note.start * fps), int(note.end * fps)
                            target_f0[start_idx:min(end_idx, len(target_f0))] = librosa.midi_to_hz(note.pitch)

                f0_clean = np.nan_to_num(f0, nan=0.0)
                weights_mul = np.array([2.0, 1.0, 2.0]) # Prevent flat lines
                _, wp = librosa.sequence.dtw(X=f0_clean.reshape(1, -1), Y=target_f0.reshape(1, -1), metric='euclidean', weights_mul=weights_mul)
                
                aligned_target = np.zeros_like(f0_clean)
                for f0_idx, target_idx in wp[::-1]:
                    aligned_target[f0_idx] = target_f0[target_idx]

                # 4. Octave-Wrapped Cents Deviation
                mask = (f0_clean > 0) & (aligned_target > 0)
                if np.any(mask):
                    raw_dev = 1200 * np.log2(f0_clean[mask] / aligned_target[mask])
                    wrapped_dev = (raw_dev + 600) % 1200 - 600 # Fixes octave jumps
                    mean_cents = np.mean(np.abs(wrapped_dev))
                else: mean_cents = 0

                # 5. Compute Summary Metrics
                mean_rms_dbfs = 20 * np.log10(mean_rms) if mean_rms > 0 else -100.0
                
                # Mean intonation deviation in Hz (only for active frames)
                mask_hz = (f0_clean > 0) & (aligned_target > 0)
                if np.any(mask_hz):
                    mean_dev_hz = np.mean(np.abs(f0_clean[mask_hz] - aligned_target[mask_hz]))
                else:
                    mean_dev_hz = 0.0
                
                df = pd.DataFrame({
                    "Amplitude (Linear RMS)": [round(float(mean_rms), 6)],
                    "Amplitude (dB Full Scale)": [round(float(mean_rms_dbfs), 2)],
                    "Intonation Deviation (Cents)": [round(float(mean_cents), 2)],
                    "Intonation Deviation (Hz)": [round(float(mean_dev_hz), 2)]
                })
                
                # 6. Visualizations & Summary Table
                tab_chart, tab_raw_midi, tab_midi = st.tabs(["📊 Pitch Deviation Plot", "🎵 Raw MIDI Target Curve", "🎹 MIDI Target Data Points"])
                
                with tab_raw_midi:
                    fig_raw = go.Figure()
                    fig_raw.add_trace(go.Scatter(
                        y=np.where(target_f0 == 0, np.nan, target_f0),
                        name="Raw MIDI Target",
                        line=dict(color='orange', shape='hv')
                    ))
                    fig_raw.update_layout(
                        xaxis_title="Frame Index", yaxis_title="Frequency (Hz)",
                        title="Raw MIDI Target Frequency Curve"
                    )
                    st.plotly_chart(fig_raw, use_container_width=True)
                
                with tab_chart:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(y=np.where(aligned_target==0, np.nan, aligned_target), name="Target", line=dict(color='orange', shape='hv')))
                    fig.add_trace(go.Scatter(y=np.where(f0_clean==0, np.nan, f0_clean), name="Performed", line=dict(color='blue')))
                    fig.update_layout(xaxis_title="Frame Index", yaxis_title="Frequency (Hz)", legend_title="Legend")
                    st.plotly_chart(fig, use_container_width=True)
                
                with tab_midi:
                    # Build a table of the aligned MIDI target data points
                    midi_times = np.round(np.arange(len(aligned_target)) * hop_length / sr, 3)
                    midi_df = pd.DataFrame({
                        "Frame Index": np.arange(len(aligned_target)),
                        "Time (s)": midi_times,
                        "Target Frequency (Hz)": np.round(np.where(aligned_target == 0, np.nan, aligned_target), 2),
                        "Performed Frequency (Hz)": np.round(np.where(f0_clean == 0, np.nan, f0_clean), 2)
                    })
                    st.dataframe(midi_df, use_container_width=True, hide_index=True)
                
                st.subheader("Summary")
                st.dataframe(df, use_container_width=True, hide_index=True)
                
            finally:
                os.remove(a_path); os.remove(m_path)