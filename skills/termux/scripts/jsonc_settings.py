"""Merge top-level Code settings while retaining comments and unrelated values."""
from __future__ import annotations

import json


def tokens(text: str):
    result = []
    i = 0
    decoder = json.JSONDecoder()
    while i < len(text):
        if text[i].isspace() or text[i] == '\ufeff': i += 1; continue
        if text.startswith('//', i):
            end = text.find('\n', i); i = len(text) if end < 0 else end; continue
        if text.startswith('/*', i):
            end = text.find('*/', i + 2)
            if end < 0: raise ValueError('Unterminated JSONC comment')
            i = end + 2; continue
        start = i
        if text[i] in '{}[]:,':
            i += 1
        else:
            _, i = decoder.raw_decode(text, i)
        result.append((text[start:i], start, i))
    return result


def parse(text: str):
    stream = tokens(text)
    meaningful = []
    for i, (value, _, _) in enumerate(stream):
        if value == ',' and i + 1 < len(stream) and stream[i + 1][0] in ('}', ']'):
            continue
        meaningful.append(value)
    value = json.loads(' '.join(meaningful))
    if not isinstance(value, dict): raise ValueError('Code settings must be a JSONC object')
    return value, stream


def merge(text: str, updates: dict) -> str:
    value, stream = parse(text)
    if not stream or stream[0][0] != '{' or stream[-1][0] != '}':
        raise ValueError('Code settings must be one object')
    properties = {}
    i = 1
    while i < len(stream) - 1:
        if stream[i][0] == ',': i += 1; continue
        key = json.loads(stream[i][0])
        if not isinstance(key, str) or stream[i + 1][0] != ':': raise ValueError('Invalid settings key')
        if key in properties: raise ValueError('Duplicate settings key: ' + key)
        begin = i + 2
        end = begin
        if stream[begin][0] in ('{', '['):
            depth = 0
            while end < len(stream):
                token = stream[end][0]
                if token in ('{', '['): depth += 1
                if token in ('}', ']'): depth -= 1
                if depth == 0: break
                end += 1
        properties[key] = (stream[begin][1], stream[end][2])
        i = end + 1
    edits = []
    missing = []
    for key, item in updates.items():
        rendered = json.dumps(item, ensure_ascii=False)
        if key in properties:
            if value[key] != item:
                a, b = properties[key]; edits.append((a, b, rendered))
        else: missing.append(json.dumps(key) + ': ' + rendered)
    if missing:
        insertion = '\n  ' + ',\n  '.join(missing) + '\n'
        closing = stream[-1][1]
        if properties and stream[-2][0] != ',':
            point = list(properties.values())[-1][1]
            if point == closing: insertion = ',' + insertion
            else: edits.append((point, point, ','))
        edits.append((closing, closing, insertion))
    for a, b, rendered in sorted(edits, key=lambda edit: (edit[0], edit[1]), reverse=True):
        text = text[:a] + rendered + text[b:]
    actual, _ = parse(text)
    if actual != dict(value, **updates): raise ValueError('Settings merge verification failed')
    return text
