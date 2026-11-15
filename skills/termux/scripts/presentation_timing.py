#!/usr/bin/env python3
"""Offline SurfaceFlinger actualPresent analysis; never connects to a device."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

from device_transport import atomic_json

INT64_MAX = (1 << 63) - 1


def parse_latency(text):
    """Parse period + desired/actual/ready rows; only actual has frame semantics."""
    lines = [line.strip() for line in text.lstrip('\ufeff').splitlines() if line.strip()]
    result = {'reported_period_ns': None, 'rows': 0, 'invalid_actual_rows': 0,
              'duplicate_actual_rows': 0, 'actual_present_ns': []}
    if not lines:
        return result
    try:
        if len(lines[0].split()) != 1:
            raise ValueError()
        period = int(lines[0])
        if not 0 <= period < INT64_MAX:
            raise ValueError()
    except ValueError as error:
        raise ValueError('Expected the numeric --latency period on the first line') from error
    result['reported_period_ns'] = period
    actual = set()
    for line_number, line in enumerate(lines[1:], 2):
        fields = line.split()
        try:
            if len(fields) != 3:
                raise ValueError()
            _, timestamp, _ = map(int, fields)
        except ValueError as error:
            raise ValueError(f'Expected desired/actual/ready integers on row {line_number}') from error
        result['rows'] += 1
        if not 0 < timestamp < INT64_MAX:
            result['invalid_actual_rows'] += 1
        elif timestamp in actual:
            result['duplicate_actual_rows'] += 1
        else:
            actual.add(timestamp)
    result['actual_present_ns'] = sorted(actual)
    return result


def validate_window(start_ns, end_ns):
    if (type(start_ns) is not int or type(end_ns) is not int
            or not 0 <= start_ns < end_ns < INT64_MAX):
        raise ValueError('Require 0 <= start-ns < end-ns < INT64_MAX in the device timestamp clock')


def analyze(before_text, after_text, *, layer, start_ns, end_ns):
    validate_window(start_ns, end_ns)
    if not isinstance(layer, str) or not layer.strip() or any(ord(c) < 32 for c in layer):
        raise ValueError('Record one exact, nonempty SurfaceView/BLAST layer name')
    before, after = parse_latency(before_text), parse_latency(after_text)
    last_before = max(before['actual_present_ns'], default=0)
    # Ring history can wrap or reorder. Never treat older unseen timestamps as new.
    new = [t for t in after['actual_present_ns'] if t > last_before]
    selected = [t for t in new if start_ns <= t <= end_ns]
    result = {
        'status': 'pending',
        'measurement': 'Selected-layer actualPresent intervals, not whole-test FPS or pixel correctness',
        'layer': layer,
        'layer_identity': 'Caller supplied; plain --latency text cannot verify the layer or boot identity',
        'window_ns': {'start': start_ns, 'end': end_ns},
        'snapshots': {label: {key: value for key, value in record.items() if key != 'actual_present_ns'}
                      for label, record in (('before', before), ('after', after))},
        'new_actual_present_count': len(new),
        'selected_actual_present_count': len(selected),
        'first_actual_present_ns': selected[0] if selected else None,
        'last_actual_present_ns': selected[-1] if selected else None,
        'observed_span_ns': selected[-1] - selected[0] if selected else None,
        'interval_ms': None,
        'limitations': [
            'Finite history may cover only the motion tail; timestamps do not establish complete coverage.',
            'The first line reports a scheduling period, not this layer\'s measured frame rate.',
            'Uniform intervals do not prove correct pixels, input latency or absence of trails.',
        ],
    }
    if len(selected) < 2:
        result['reason'] = 'Fewer than two new valid actualPresent timestamps inside the recorded window; no rate inferred'
        return result
    intervals = [b - a for a, b in zip(selected, selected[1:])]
    ordered = sorted(intervals)
    result['status'] = 'collected'
    result['interval_ms'] = {
        'min': ordered[0] / 1e6,
        'p50': statistics.median(ordered) / 1e6,
        'p95': ordered[math.ceil(.95 * len(ordered)) - 1] / 1e6,
        'max': ordered[-1] / 1e6,
    }
    result['percentile_method'] = 'p50 median; p95 nearest rank'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True, help='UTF-8 --latency snapshot before motion')
    parser.add_argument('--after', type=Path, required=True, help='UTF-8 snapshot for the same boot and layer')
    parser.add_argument('--layer', required=True, help='Exact layer name used for both captures')
    parser.add_argument('--start-ns', type=int, required=True, help='Motion start in device monotonic nanoseconds')
    parser.add_argument('--end-ns', type=int, required=True, help='Motion end in the same device clock')
    parser.add_argument('--state', type=Path, required=True, help='Private output JSON outside the skill')
    args = parser.parse_args(argv)
    try:
        validate_window(args.start_ns, args.end_ns)
        if args.state.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
            raise ValueError('Keep evidence outside the public skill directory')
        if args.state.resolve() in (args.before.resolve(), args.after.resolve()):
            raise ValueError('Output must not overwrite either raw snapshot')
    except ValueError as error:
        parser.error(str(error))
    summary = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    result = {'status': 'failed', 'input_summary': summary,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        texts = []
        for label, path in (('before', args.before), ('after', args.after)):
            raw = path.read_bytes()
            summary[label + '_sha256'] = hashlib.sha256(raw).hexdigest()
            texts.append(raw.decode('utf-8-sig'))
        result.update(analyze(*texts, layer=args.layer, start_ns=args.start_ns, end_ns=args.end_ns))
    except (OSError, ValueError) as error:
        result.update(status='failed', error=str(error))
    result['input_sha256'] = hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest()
    try:
        atomic_json(args.state, result)
    except OSError as error:
        result.update(status='failed', error='Cannot write result: ' + str(error))
    print(json.dumps(result, ensure_ascii=False))
    return {'collected': 0, 'pending': 3, 'failed': 1}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
