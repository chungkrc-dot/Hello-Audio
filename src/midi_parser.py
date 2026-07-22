import librosa

def read_vlq(data, idx):
    value = 0
    while True:
        if idx >= len(data):
            break
        byte = data[idx]
        idx += 1
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            break
    return value, idx

def _iter_midi_events(audio_file, target_track=None):
    """
    Core generator that parses MIDI bytes and yields structured events.
    Yields: (trk_idx, event_type, absolute_time_ticks, param1, param2, meta_type, meta_data)
    """
    audio_file.seek(0)
    data = audio_file.read()
    
    idx = 0
    if data[idx:idx+4] != b'MThd':
        return
        
    idx += 4
    header_len = int.from_bytes(data[idx:idx+4], 'big')
    idx += 4
    fmt = int.from_bytes(data[idx:idx+2], 'big')
    ntracks = int.from_bytes(data[idx+2:idx+4], 'big')
    tickdiv = int.from_bytes(data[idx+4:idx+6], 'big')
    idx += header_len
    
    yield ('header', fmt, ntracks, tickdiv, None, None, None)
    
    for trk_idx in range(ntracks):
        if idx >= len(data): break
        while idx < len(data) and data[idx:idx+4] != b'MTrk':
            idx += 1
            
        if idx >= len(data): break
        
        idx += 4
        trk_len = int.from_bytes(data[idx:idx+4], 'big')
        idx += 4
        end_idx = idx + trk_len
        
        running_status = None
        absolute_time = 0
        
        while idx < end_idx:
            delta, idx = read_vlq(data, idx)
            absolute_time += delta
            
            if idx >= end_idx: break
            
            event_byte = data[idx]
            if event_byte >= 0x80:
                status = event_byte
                idx += 1
                if status < 0xF0:
                    running_status = status
            else:
                status = running_status
                if status is None:
                    idx += 1
                    continue
                    
            if status == 0xFF:
                meta_type = data[idx]
                idx += 1
                meta_len, idx = read_vlq(data, idx)
                meta_data = data[idx:idx+meta_len]
                idx += meta_len
                yield (trk_idx, 'meta', absolute_time, None, None, meta_type, meta_data)
            elif status in (0xF0, 0xF7):
                sysex_len, idx = read_vlq(data, idx)
                idx += sysex_len
            else:
                event_type = status >> 4
                if event_type in (0x8, 0x9, 0xA, 0xB, 0xE):
                    param1 = data[idx]
                    param2 = data[idx+1]
                    idx += 2
                    if target_track is None or trk_idx == target_track:
                        yield (trk_idx, event_type, absolute_time, param1, param2, None, None)
                elif event_type in (0xC, 0xD):
                    idx += 1

def parse_midi(audio_file, target_track=None):
    all_notes = []
    for trk_idx, event_type, abs_time, p1, p2, meta_type, meta_data in _iter_midi_events(audio_file, target_track):
        if event_type == 0x9 and p2 > 0:
            all_notes.append((abs_time, p1))
    
    all_notes.sort(key=lambda x: x[0])
    return [librosa.midi_to_note(n[1]) for n in all_notes]

def parse_midi_with_timing(audio_file, target_track=None):
    generator = _iter_midi_events(audio_file, target_track)
    try:
        header = next(generator)
        if header[0] != 'header':
            return []
        tickdiv = header[3]
    except StopIteration:
        return []
        
    ticks_per_quarter = tickdiv if tickdiv > 0 else 480
    seconds_per_tick = 500000 / (ticks_per_quarter * 1000000)
    
    midi_notes = []
    active_notes = {}
    
    for trk_idx, event_type, abs_time, p1, p2, meta_type, meta_data in generator:
        if event_type == 'meta' and meta_type == 0x51 and len(meta_data) == 3:
            tempo_usec = int.from_bytes(meta_data, 'big')
            seconds_per_tick = tempo_usec / (ticks_per_quarter * 1000000)
        elif event_type == 0x9 and p2 > 0:
            if p1 not in active_notes:
                active_notes[p1] = abs_time * seconds_per_tick
        elif event_type == 0x8 or (event_type == 0x9 and p2 == 0):
            if p1 in active_notes:
                start_time = active_notes.pop(p1)
                end_time = abs_time * seconds_per_tick
                midi_notes.append({
                    'Start_Time': start_time,
                    'End_Time': end_time,
                    'Pitch': p1
                })
                
    midi_notes.sort(key=lambda x: x['Start_Time'])
    return midi_notes

class MidiTrackError(ValueError):
    """Raised when a part cannot be resolved from a MIDI file unambiguously."""


# Nominal written tessitura per instrument, as MIDI note numbers. Mirrors the
# bounds in pitch_engine.get_instrument_fmin_fmax() but expressed in MIDI space,
# since track selection reasons about note numbers rather than Hz.
INSTRUMENT_TESSITURA = {
    "violin": (55, 96),   # G3 - C7
    "viola": (48, 93),    # C3 - A6
    "cello": (36, 88),    # C2 - E6
}

# Slack allowed before a track is reported as outside an instrument's range.
# Two semitones absorbs scordatura and the occasional notated harmonic without
# masking a genuine part mix-up, which is normally off by an octave or more.
TESSITURA_SLACK = 2


def describe_midi_tracks(audio_file):
    """
    Summarise every track that carries notes.

    Returns {trk_idx: {'count', 'lo', 'hi', 'lo_note', 'hi_note', 'end_time'}},
    where lo/hi are MIDI note numbers and end_time is in seconds. Used to build
    informative track labels so a user choosing a part is not guessing from a
    note count alone.
    """
    info = {}
    generator = _iter_midi_events(audio_file)
    try:
        header = next(generator)
    except StopIteration:
        return info
    if header[0] != 'header':
        return info
    ticks_per_quarter = header[3] if header[3] > 0 else 480
    seconds_per_tick = 500000 / (ticks_per_quarter * 1000000)

    for trk_idx, event_type, abs_time, p1, p2, meta_type, meta_data in generator:
        if event_type == 'meta' and meta_type == 0x51 and len(meta_data) == 3:
            tempo_usec = int.from_bytes(meta_data, 'big')
            seconds_per_tick = tempo_usec / (ticks_per_quarter * 1000000)
        elif event_type == 0x9 and p2 > 0:
            e = info.setdefault(trk_idx, {'count': 0, 'lo': 127, 'hi': 0, 'end_tick': 0})
            e['count'] += 1
            e['lo'] = min(e['lo'], p1)
            e['hi'] = max(e['hi'], p1)
            e['end_tick'] = max(e['end_tick'], abs_time)

    for e in info.values():
        e['end_time'] = e.pop('end_tick') * seconds_per_tick
        e['lo_note'] = librosa.midi_to_note(e['lo'])
        e['hi_note'] = librosa.midi_to_note(e['hi'])
    return info


def fits_instrument(lo, hi, instrument, slack=TESSITURA_SLACK):
    """True if a track's [lo, hi] MIDI range lies within the instrument's tessitura."""
    bounds = INSTRUMENT_TESSITURA.get((instrument or "").lower())
    if bounds is None:
        return True
    return lo >= bounds[0] - slack and hi <= bounds[1] + slack


def best_fitting_instrument(lo, hi, slack=TESSITURA_SLACK):
    """Name the instrument whose tessitura best contains [lo, hi], or None."""
    fits = [n for n in INSTRUMENT_TESSITURA if fits_instrument(lo, hi, n, slack)]
    if not fits:
        return None
    # Prefer the tightest range that still contains the track.
    return min(fits, key=lambda n: INSTRUMENT_TESSITURA[n][1] - INSTRUMENT_TESSITURA[n][0])


def format_track_label(trk_idx, entry, instrument=None):
    """Human-readable track label: note count, pitch range, duration, and fit."""
    label = (f"Track {trk_idx} — {entry['count']} notes, "
             f"{entry['lo_note']}–{entry['hi_note']}, {entry['end_time']:.1f} s")
    if instrument:
        if fits_instrument(entry['lo'], entry['hi'], instrument):
            label += f"  ✓ fits {instrument}"
        else:
            alt = best_fitting_instrument(entry['lo'], entry['hi'])
            label += f"  ✗ outside {instrument}" + (f" (fits {alt.capitalize()})" if alt else "")
    return label


def get_midi_tracks(audio_file, instrument=None):
    """
    Map of track index to display label, for tracks carrying notes.

    Labels include pitch range and duration so that selecting a part from a
    condensed score is an informed choice rather than a guess.
    """
    info = describe_midi_tracks(audio_file)
    return {i: format_track_label(i, e, instrument) for i, e in info.items()}


def resolve_target_track(audio_file, requested_track=None, part_index=None):
    """
    Decide which MIDI track holds the part to analyse, or fail loudly.

    Resolution order:
      1. Exactly one track carries notes -> that track, regardless of what was
         requested. A single-part MIDI is taken to be the correct part, which is
         the assumption the application is built on.
      2. An explicit `requested_track` -> honoured if it carries notes, else
         MidiTrackError. There is deliberately no fallback to another track:
         silently analysing the wrong part is worse than refusing.
      3. A `part_index` (the URMP part number) -> mapped onto the track of the
         same index, valid only under the conductor-track convention where
         track 0 is silent. If track 0 carries notes the convention does not
         hold and the mapping would be off by one, so this raises instead.

    Returns (track_index, track_info_dict).
    """
    info = describe_midi_tracks(audio_file)
    if not info:
        raise MidiTrackError("MIDI file contains no note events.")

    if len(info) == 1:
        only = next(iter(info))
        return only, info

    if requested_track is not None:
        if requested_track not in info:
            raise MidiTrackError(
                f"Requested track {requested_track} carries no notes. "
                f"Tracks with notes: {sorted(info)}."
            )
        return requested_track, info

    if part_index is not None:
        if 0 in info:
            raise MidiTrackError(
                "Cannot map part index onto track index: this file has notes on "
                "track 0, so it does not use the silent-conductor-track "
                f"convention and part {part_index} would be off by one. "
                f"Tracks with notes: {sorted(info)}. Select a track explicitly."
            )
        if part_index not in info:
            raise MidiTrackError(
                f"Part {part_index} maps to track {part_index}, which carries no "
                f"notes. Tracks with notes: {sorted(info)}."
            )
        return part_index, info

    raise MidiTrackError(
        f"MIDI file has {len(info)} tracks with notes ({sorted(info)}); "
        "a track must be selected explicitly."
    )


def load_part_notes(midi_path, part_index=None, requested_track=None):
    """
    Load the timed notes of one part from a MIDI file, resolving the track
    strictly. Raises MidiTrackError rather than falling back to another track.

    This is the loader for batch and validation runs, where a wrong-part
    analysis would otherwise surface as a merely mediocre yield rather than an
    error. Returns (notes, resolved_track_index).
    """
    with open(midi_path, 'rb') as f:
        track, _info = resolve_target_track(
            f, requested_track=requested_track, part_index=part_index
        )
    with open(midi_path, 'rb') as f:
        return parse_midi_with_timing(f, target_track=track), track

def get_midi_tempo(midi_file_path):
    with open(midi_file_path, 'rb') as f:
        for trk_idx, event_type, abs_time, p1, p2, meta_type, meta_data in _iter_midi_events(f):
            if event_type == 'meta' and meta_type == 0x51 and len(meta_data) == 3:
                tempo_usec = int.from_bytes(meta_data, 'big')
                return 60000000 / tempo_usec
    return 120.0
