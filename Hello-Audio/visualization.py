"""
visualization.py
----------------
Dedicated rendering engine for all interactive data visualizations.
This module leverages Plotly Graph Objects to draw complex, multi-layered traces 
for both the Legacy sequential pitch tracks and the advanced DTW Diagnostic overlays.
"""
import streamlit as st
import numpy as np
import librosa
import plotly.graph_objects as go
import matplotlib.pyplot as plt

def render_plotly_fig(res_dict, title_suffix, show_raw, show_steady, show_target):
    """
    Renders an interactive Plotly graph of the pitch tracks vs time.
    """
    f0 = res_dict['f0']
    final_mask = res_dict['final_mask']
    f0_target = res_dict['f0_target']
    full_deviation = res_dict['full_deviation']
    sr = res_dict['sr']
    
    times = librosa.times_like(f0, sr=sr, hop_length=512)
    f0_steady = np.full_like(f0, np.nan)
    f0_steady[final_mask] = f0[final_mask]
    
    hover_text = []
    for d_pitch, t_pitch, dev in zip(f0_steady, f0_target, full_deviation):
        if not np.isnan(d_pitch):
            hover_text.append(f"Detected: {d_pitch:.1f} Hz<br>Target: {t_pitch:.1f} Hz<br>Dev: {dev:.1f} ¢")
        else:
            hover_text.append("")
            
    fig = go.Figure()
    
    if show_raw:
        fig.add_trace(go.Scatter(
            x=times, y=f0, mode='lines', name='Raw pYIN f0 (voiced)',
            line=dict(color='rgba(128, 128, 128, 0.3)', width=1), hoverinfo='skip'
        ))
    
    if show_steady:
        fig.add_trace(go.Scatter(
            x=times, y=f0_steady, mode='lines', name='Isolated Steady Notes',
            line=dict(color='blue', width=2), text=hover_text, hovertemplate="%{text}<extra></extra>"
        ))
    
    if show_target:
        fig.add_trace(go.Scatter(
            x=times, y=f0_target, mode='lines', name='Target Pitch (Nearest Semitone)',
            line=dict(color='red', width=2, dash='dash'), hovertemplate="Target: %{y:.1f} Hz<extra></extra>"
        ))
    
    max_y = np.nanmax(f0) if not np.all(np.isnan(f0)) else 2000
    tick_vals = np.arange(0, max_y + 500, 500)
    tick_text = [f"{v/1000:g}kHz" for v in tick_vals]
    
    fig.update_layout(
        title=f"Pitch Track vs Isolated Steady-State Notes ({title_suffix})",
        xaxis_title="Time (seconds)",
        yaxis_title="Frequency",
        yaxis=dict(tickmode='array', tickvals=tick_vals, ticktext=tick_text, range=[0, max_y + 200]),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig

def render_pitch_track_visualizations(unp_ok, plg_ok, res_unp, res_plg):
    """
    Sets up the Streamlit UI for the Plotly graphs and renders them based on checkboxes.
    """
    st.subheader("Pitch Track Visualizations")
    
    col_t1, col_t2, col_t3 = st.columns(3)
    show_raw = col_t1.checkbox("Show Raw pYIN f0 (voiced)", value=True)
    show_steady = col_t2.checkbox("Show Isolated Steady Notes", value=True)
    show_target = col_t3.checkbox("Show Target Pitch", value=True)

    if unp_ok and plg_ok:
        tab1, tab2 = st.tabs(["Unplugged Recording", "Plugged Recording"])
        with tab1:
            fig_unp = render_plotly_fig(res_unp, "Unplugged", show_raw, show_steady, show_target)
            st.plotly_chart(fig_unp, use_container_width=True)
        with tab2:
            fig_plg = render_plotly_fig(res_plg, "Plugged", show_raw, show_steady, show_target)
            st.plotly_chart(fig_plg, use_container_width=True)
    elif unp_ok:
        fig_unp = render_plotly_fig(res_unp, "Unplugged", show_raw, show_steady, show_target)
        st.plotly_chart(fig_unp, use_container_width=True)
    elif plg_ok:
        fig_plg = render_plotly_fig(res_plg, "Plugged", show_raw, show_steady, show_target)
        st.plotly_chart(fig_plg, use_container_width=True)


def plot_alignment_diagnostics(time_array, f0_midi, expected_audio_pitch, valid_dtw_mask, expected_note_index=None, show_target=True, show_extraneous=True, show_matched=True):
    """
    Renders a diagnostic plot showing the DTW expected pitch path natively 
    overlaid on the detected pYIN pitch curve using Plotly.
    Matched pitches (inside mask) are Blue, extraneous pitches (outside mask) are Yellow.
    Allows toggling individual plot elements and provides interactive hover tooltips.
    """
    import plotly.graph_objects as go
    import librosa
    
    fig = go.Figure()
    
    f0_hz = librosa.midi_to_hz(f0_midi)
    expected_hz = librosa.midi_to_hz(expected_audio_pitch)
    
    expected_notes = [librosa.midi_to_note(p) if not np.isnan(p) else "Rest" for p in expected_audio_pitch]
    if expected_note_index is not None:
        combined_notes = [f"{idx} ({note})" if idx != "" else note for idx, note in zip(expected_note_index, expected_notes)]
    else:
        combined_notes = expected_notes
        
    hover_expected_hz = [f"{hz:.2f} Hz" if not np.isnan(hz) else "N/A" for hz in expected_hz]
    hover_performed_hz = [f"{hz:.2f} Hz" if not np.isnan(hz) else "N/A" for hz in f0_hz]
    
    customdata = np.stack((combined_notes, hover_expected_hz, hover_performed_hz), axis=-1)
    
    hover_template = (
        "Time: %{x:.2f}s<br>"
        "Expected Note: %{customdata[0]}<br>"
        "Expected Freq: %{customdata[1]}<br>"
        "Performed Freq: %{customdata[2]}"
        "<extra></extra>"
    )
    
    # 1. Plot the continuous expected MIDI pitch (the grey staircase)
    if show_target:
        fig.add_trace(go.Scatter(
            x=time_array,
            y=expected_audio_pitch,
            mode='lines',
            name='DTW Bridge Target',
            line=dict(color='grey', width=4),
            opacity=0.5,
            hovertemplate=hover_template,
            customdata=customdata
        ))
    
    # 2. Plot the raw pYIN f0. We break it into two groups based on the DTW mask.
    # Group A: Extraneous notes (outside the DTW mask). Yellow.
    if show_extraneous:
        extraneous_f0 = np.copy(f0_midi)
        extraneous_f0[valid_dtw_mask] = np.nan
        
        # Break the line at any massive instantaneous jumps (> 6 semitones per frame) 
        # to prevent Plotly from drawing artificial vertical cliffs between disconnected pitch islands.
        pitch_slope_ext = np.concatenate(([0], np.abs(np.diff(extraneous_f0))))
        extraneous_f0[pitch_slope_ext > 6.0] = np.nan
        
        fig.add_trace(go.Scatter(
            x=time_array,
            y=extraneous_f0,
            mode='lines',
            name='Extraneous F0',
            line=dict(color='#ffc107', width=2),
            opacity=0.8,
            hovertemplate=hover_template,
            customdata=customdata
        ))
    
    # Group B: Matched notes (inside the DTW mask). Blue.
    if show_matched:
        matched_f0 = np.copy(f0_midi)
        matched_f0[~valid_dtw_mask] = np.nan
        fig.add_trace(go.Scatter(
            x=time_array,
            y=matched_f0,
            mode='lines',
            name='Matched F0',
            line=dict(color='#1f77b4', width=2),
            opacity=0.9,
            hovertemplate=hover_template,
            customdata=customdata
        ))

    valid_data = f0_midi[~np.isnan(f0_midi)]
    y_range = [np.min(valid_data) - 2, np.max(valid_data) + 2] if len(valid_data) > 0 else None

    fig.update_layout(
        title="Absolute-Time Bridge Diagnostics",
        xaxis_title="Time (s)",
        yaxis_title="Pitch (MIDI)",
        yaxis=dict(range=y_range) if y_range else dict(),
        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
        margin=dict(l=20, r=20, t=40, b=20),
        hovermode="closest"
    )
    
    return fig
