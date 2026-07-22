"""
Regression tests for MIDI part selection.

The URMP corpus mixes two conventions: 14 pieces ship a condensed full score
copied into every part folder, while 44_K515 ships hand-exported single-part
files. Both must resolve to the correct part, and an ambiguous file must raise
rather than silently analysing the wrong one.

The corpus sweep at the end is the standing check that the part-index mapping
still holds; it replaces a manual inspection.
"""
import os
import sys
import struct

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.midi_alignment import low_detection_yield_warning  # noqa: E402
from src.midi_parser import (  # noqa: E402
    MidiTrackError,
    best_fitting_instrument,
    describe_midi_tracks,
    fits_instrument,
    format_track_label,
    load_part_notes,
    resolve_target_track,
)

DATASET = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'dataset (Strings only)')
)

INST_CODES = {"vn": "Violin", "va": "Viola", "vc": "Cello"}


# ----------------------------------------------------------------------
# Synthetic MIDI construction
# ----------------------------------------------------------------------

def _track(events):
    data = b''.join(events) + b'\x00\xff\x2f\x00'
    return b'MTrk' + struct.pack('>I', len(data)) + data


def _note(pitch, delta=0, dur=96):
    return (bytes([delta]) + bytes([0x90, pitch, 64])
            + bytes([dur]) + bytes([0x80, pitch, 0]))


def _midi(tracks, tickdiv=96):
    header = b'MThd' + struct.pack('>IHHH', 6, 1, len(tracks), tickdiv)
    return header + b''.join(_track(t) for t in tracks)


def _write(tmp_path, name, blob):
    p = tmp_path / name
    p.write_bytes(blob)
    return str(p)


# ----------------------------------------------------------------------
# Layer 1 — arity
# ----------------------------------------------------------------------

def test_single_track_file_is_used_as_is(tmp_path):
    """A single-part MIDI is the correct part, whatever index was requested."""
    path = _write(tmp_path, "solo.mid", _midi([[_note(69)]]))
    with open(path, 'rb') as f:
        track, info = resolve_target_track(f, part_index=4)
    assert track == 0
    assert len(info) == 1


def test_single_track_ignores_requested_track(tmp_path):
    path = _write(tmp_path, "solo.mid", _midi([[_note(69)]]))
    with open(path, 'rb') as f:
        assert resolve_target_track(f, requested_track=7)[0] == 0


def test_conductor_track_convention_maps_part_to_track(tmp_path):
    """Silent track 0, parts on 1..n — part N resolves to track N."""
    blob = _midi([[], [_note(76)], [_note(64)], [_note(50)]])
    path = _write(tmp_path, "score.mid", blob)
    for part in (1, 2, 3):
        with open(path, 'rb') as f:
            assert resolve_target_track(f, part_index=part)[0] == part


# ----------------------------------------------------------------------
# Layer 4 — fail loudly, never fall back
# ----------------------------------------------------------------------

def test_notes_on_track_zero_rejects_part_index(tmp_path):
    """Without a silent conductor track the mapping is off by one: refuse."""
    blob = _midi([[_note(76)], [_note(64)], [_note(50)]])
    path = _write(tmp_path, "noconductor.mid", blob)
    with open(path, 'rb') as f:
        with pytest.raises(MidiTrackError, match="off by one"):
            resolve_target_track(f, part_index=2)


def test_empty_requested_track_raises_instead_of_falling_back(tmp_path):
    """The old loader silently retried track 0 then track 1 — Violin I."""
    blob = _midi([[], [_note(76)], [_note(64)]])
    path = _write(tmp_path, "score.mid", blob)
    with open(path, 'rb') as f:
        with pytest.raises(MidiTrackError, match="carries no notes"):
            resolve_target_track(f, requested_track=5)


def test_multi_track_without_selection_raises(tmp_path):
    blob = _midi([[], [_note(76)], [_note(64)]])
    path = _write(tmp_path, "score.mid", blob)
    with open(path, 'rb') as f:
        with pytest.raises(MidiTrackError, match="selected explicitly"):
            resolve_target_track(f)


def test_file_with_no_notes_raises(tmp_path):
    path = _write(tmp_path, "empty.mid", _midi([[]]))
    with open(path, 'rb') as f:
        with pytest.raises(MidiTrackError, match="no note events"):
            resolve_target_track(f)


# ----------------------------------------------------------------------
# Layers 2 & 3 — labels and tessitura
# ----------------------------------------------------------------------

def test_tessitura_accepts_and_rejects_by_instrument():
    assert fits_instrument(55, 96, "Violin")
    assert not fits_instrument(36, 60, "Violin")     # cello range
    assert fits_instrument(36, 88, "Cello")
    assert fits_instrument(55, 96, "unknown-instrument")  # unconstrained


def test_best_fitting_instrument_identifies_cello_range():
    assert best_fitting_instrument(38, 54) == "cello"


def test_track_label_reports_range_and_fit(tmp_path):
    blob = _midi([[], [_note(40)]])
    path = _write(tmp_path, "low.mid", blob)
    with open(path, 'rb') as f:
        info = describe_midi_tracks(f)
    label = format_track_label(1, info[1], "Violin")
    assert "1 notes" in label and "outside Violin" in label and "Cello" in label


# ----------------------------------------------------------------------
# Corpus sweep — the standing regression check
# ----------------------------------------------------------------------

def test_low_yield_warning_fires_below_threshold():
    assert low_detection_yield_warning(31.0, "pYIN") is not None
    assert low_detection_yield_warning(70.6, "pYIN") is None


def test_low_yield_threshold_is_engine_specific():
    """REAPER's floor is lower by architecture, so 46.8% must not fire."""
    assert low_detection_yield_warning(46.76, "REAPER") is None
    assert low_detection_yield_warning(46.76, "pYIN") is not None


def test_low_yield_warning_handles_missing_values():
    assert low_detection_yield_warning(None, "pYIN") is None
    assert low_detection_yield_warning(float('nan'), "pYIN") is None


def test_low_yield_warning_is_advisory_not_accusatory():
    msg = low_detection_yield_warning(20.0, "pYIN")
    assert "Violin I" in msg          # names the error it exists to catch
    assert "often just difficult" in msg   # does not assert a mistake


def test_no_corpus_stem_triggers_the_warning():
    """
    The thresholds must not fire on any genuine corpus track, for either
    engine. A warning that cries wolf is one users learn to dismiss.
    """
    csv_path = os.path.join(os.path.dirname(__file__), 'outputs',
                            'batch_results', 'appendix_a_results.csv')
    if not os.path.exists(csv_path):
        pytest.skip("batch results not present")
    import csv as _csv
    with open(csv_path) as fh:
        for row in _csv.DictReader(fh):
            for engine in ("pYIN", "REAPER"):
                yield_pct = float(row[f"Det_Yield_{engine}"])
                assert low_detection_yield_warning(yield_pct, engine) is None, (
                    f"false positive: {row['Filename']} {engine} at {yield_pct}%"
                )


def _corpus_stems():
    if not os.path.isdir(DATASET):
        return []
    out = []
    for root, _dirs, files in os.walk(DATASET):
        for fn in sorted(files):
            if not fn.startswith("AuSep_") or not fn.endswith(".wav"):
                continue
            parts = os.path.splitext(fn)[0].split('_')
            if len(parts) < 3 or parts[2] not in INST_CODES:
                continue
            mids = [f for f in os.listdir(root) if f.endswith(".mid")]
            if mids:
                out.append((os.path.splitext(fn)[0], int(parts[1]),
                            INST_CODES[parts[2]], os.path.join(root, mids[0])))
    return out


@pytest.mark.skipif(not _corpus_stems(), reason="URMP dataset not present")
@pytest.mark.parametrize("stem,part,instrument,midi_path", _corpus_stems())
def test_every_corpus_stem_resolves_to_its_instrument(stem, part, instrument, midi_path):
    """
    Every stem must resolve to a non-empty part whose range fits its labelled
    instrument. This catches an off-by-one in the part mapping and a wrong-class
    part swap; it cannot catch a Violin I / Violin II swap, which only shows up
    as collapsed alignment yield.
    """
    notes, _track = load_part_notes(midi_path, part_index=part)
    assert notes, f"{stem}: resolved part carries no notes"
    pitches = [n['Pitch'] for n in notes]
    lo, hi = min(pitches), max(pitches)
    assert fits_instrument(lo, hi, instrument), (
        f"{stem}: resolved range {lo}-{hi} outside {instrument} "
        f"(best fit: {best_fitting_instrument(lo, hi)})"
    )
