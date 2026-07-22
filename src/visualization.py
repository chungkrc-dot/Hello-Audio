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
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=40, b=80),
        hovermode="closest"
    )

    return fig


# ==========================================
# Distributional Diagnostics
# ==========================================
# The summary tables report median, IQR, skewness and kurtosis, but a shape
# statistic is only persuasive next to the shape itself. These two plots are the
# standard evidence a reader expects: the marginal distribution of the deviations,
# and — when two conditions are measured on the same notes — a Bland-Altman plot
# of their agreement rather than a correlation coefficient.

def _gaussian_kde_curve(values, n_points=256, pad_factor=0.15):
    """
    Scott's-rule Gaussian KDE evaluated on a padded grid.

    Written out rather than taken from scipy so the visualisation layer keeps the
    same dependency surface as the rest of the module, and so the bandwidth is
    visible: on quantized data the bandwidth is what decides whether the curve
    shows the true shape or the output lattice.
    """
    arr = np.asarray(values, dtype=float).ravel()
    arr = arr[~np.isnan(arr)]
    n = arr.size
    if n < 2:
        return np.array([]), np.array([]), np.nan

    std = np.std(arr, ddof=1)
    if std <= 0:
        return np.array([]), np.array([]), np.nan

    bandwidth = std * n ** (-1.0 / 5.0)  # Scott's rule for a 1-D sample

    span = arr.max() - arr.min()
    pad = pad_factor * span if span > 0 else 1.0
    grid = np.linspace(arr.min() - pad, arr.max() + pad, n_points)

    z = (grid[:, None] - arr[None, :]) / bandwidth
    density = np.exp(-0.5 * z ** 2).sum(axis=1) / (n * bandwidth * np.sqrt(2 * np.pi))

    return grid, density, bandwidth


def plot_deviation_distribution(series, title="Intonation Deviation Distribution",
                                unit="cents", bin_width=None, show_kde=True):
    """
    Histogram (probability density) with an optional KDE overlay and median /
    quartile reference lines, for one or more labelled deviation samples.

    `series` is a dict of {label: array_of_deviations}. `bin_width` defaults to
    the pYIN lattice step so that each bar corresponds to exactly one attainable
    output value — binning quantized data more finely than its own grid produces
    a comb of empty bins that looks like structure but is pure artefact.
    """
    from src.stats_summary import PYIN_RESOLUTION_CENTS

    if bin_width is None:
        bin_width = PYIN_RESOLUTION_CENTS if unit == "cents" else None

    palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    fig = go.Figure()

    for i, (label, values) in enumerate(series.items()):
        arr = np.asarray(values, dtype=float).ravel()
        arr = arr[~np.isnan(arr)]
        if arr.size == 0:
            continue

        color = palette[i % len(palette)]

        fig.add_trace(go.Histogram(
            x=arr,
            name=f"{label} (n={arr.size})",
            histnorm='probability density',
            opacity=0.55,
            marker=dict(color=color),
            xbins=dict(size=bin_width) if bin_width else None
        ))

        if show_kde:
            grid, density, _ = _gaussian_kde_curve(arr)
            if grid.size:
                fig.add_trace(go.Scatter(
                    x=grid, y=density, mode='lines', name=f"{label} KDE",
                    line=dict(color=color, width=2), hoverinfo='skip'
                ))

        median = float(np.median(arr))
        fig.add_vline(x=median, line=dict(color=color, width=2, dash='dash'),
                      annotation_text=f"{label} median {median:.1f}",
                      annotation_position="top")

    fig.update_layout(
        title=title,
        xaxis_title=f"Deviation ({unit})",
        yaxis_title="Probability density",
        barmode='overlay',
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=40, b=80),
        hovermode="x"
    )
    return fig


def plot_bland_altman(a, b, label_a="A", label_b="B", unit="cents",
                      title="Bland-Altman Agreement", point_labels=None):
    """
    Bland-Altman (1986) plot of two paired measurements of the same notes:
    the difference (a - b) against the mean of the pair, with the bias and the
    95% limits of agreement drawn in.

    This is the correct diagram for a method-comparison question. A scatter of a
    against b with a correlation coefficient answers "do these two rank notes the
    same way?", which is not the question — the question is "by how much can they
    disagree on any one note?", which is exactly the width of the limits.
    """
    from src.stats_summary import bland_altman_stats

    ba = bland_altman_stats(a, b)
    fig = go.Figure()

    if ba["n"] < 2:
        fig.update_layout(title=f"{title} — insufficient paired data")
        return fig, ba

    hover = None
    if point_labels is not None:
        valid_a = np.asarray(a, dtype=float)
        valid_b = np.asarray(b, dtype=float)
        keep = ~np.isnan(valid_a) & ~np.isnan(valid_b)
        hover = [str(l) for l, k in zip(point_labels, keep) if k]

    fig.add_trace(go.Scatter(
        x=ba["means"], y=ba["diffs"], mode='markers',
        name=f"Notes (n={ba['n']})",
        marker=dict(color='#1f77b4', size=6, opacity=0.6),
        text=hover,
        hovertemplate=("Mean: %{x:.1f}<br>Difference: %{y:.1f}" +
                       ("<br>%{text}" if hover else "") + "<extra></extra>")
    ))

    fig.add_hline(y=ba["bias"], line=dict(color='#d62728', width=2),
                  annotation_text=f"Bias {ba['bias']:+.2f}", annotation_position="right")
    fig.add_hline(y=ba["loa_upper"], line=dict(color='grey', width=2, dash='dash'),
                  annotation_text=f"+1.96 SD {ba['loa_upper']:+.2f}", annotation_position="right")
    fig.add_hline(y=ba["loa_lower"], line=dict(color='grey', width=2, dash='dash'),
                  annotation_text=f"−1.96 SD {ba['loa_lower']:+.2f}", annotation_position="right")

    fig.update_layout(
        title=f"{title} ({label_a} − {label_b})",
        xaxis_title=f"Mean of {label_a} and {label_b} ({unit})",
        yaxis_title=f"Difference {label_a} − {label_b} ({unit})",
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=40, b=80),
        hovermode="closest"
    )
    return fig, ba


def render_distribution_diagnostics(series, paired=None, unit="cents",
                                    key_prefix="dist", bin_width=None):
    """
    Streamlit block wrapping the two diagnostic plots. `series` is
    {label: deviations} for the distribution plot; `paired` is an optional
    (values_a, values_b, label_a, label_b, point_labels) tuple for Bland-Altman.

    `bin_width` should match the lattice of the data being plotted: 10 cents for
    raw frame deviations (legacy mode), 5 cents for DTW per-note medians.
    """
    st.subheader("Deviation Distribution Diagnostics")
    st.caption("Cent-deviation distributions are typically non-normal, so the summary tables "
               "report median and IQR alongside the mean. These plots show the shape those "
               "statistics describe.")

    show_kde = st.checkbox("Overlay kernel density estimate", value=True,
                           key=f"{key_prefix}_kde")

    if any(np.asarray(v, dtype=float).size for v in series.values()):
        fig = plot_deviation_distribution(series, unit=unit, show_kde=show_kde,
                                          bin_width=bin_width)
        st.plotly_chart(fig, use_container_width=True)
        if unit == "cents":
            width = bin_width if bin_width else 10.0
            st.caption(f"Bin width is fixed at {width:g} cents, the spacing of the pYIN output "
                       "lattice for this data. Each bar is one attainable output value; finer "
                       "bins would show empty gaps that are an artefact of the grid, not of the "
                       "performance.")
    else:
        st.info("No deviation data available to plot.")

    if paired is not None:
        values_a, values_b, label_a, label_b, point_labels = paired
        arr_a = np.asarray(values_a, dtype=float)
        arr_b = np.asarray(values_b, dtype=float)
        if arr_a.size and arr_b.size and arr_a.size == arr_b.size:
            fig_ba, ba = plot_bland_altman(arr_a, arr_b, label_a, label_b, unit=unit,
                                           point_labels=point_labels)
            st.plotly_chart(fig_ba, use_container_width=True)
            if ba["n"] >= 2:
                st.caption(
                    f"Bias {ba['bias']:+.2f} {unit} with 95% limits of agreement "
                    f"[{ba['loa_lower']:+.2f}, {ba['loa_upper']:+.2f}] {unit} over {ba['n']} "
                    f"paired notes. The limits, not the bias, describe how far the two "
                    f"conditions can disagree on any single note."
                )
