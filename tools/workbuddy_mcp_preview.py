#!/usr/bin/env python3
"""Stage a private merged WorkBuddy MCP document for the official settings UI.

Does not install software, edit the live config, trust tools, authenticate, or
read training data. Existing Garmin source must be chosen explicitly by owner.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid


def read_config(path: Path) -> tuple[dict, bytes]:
    if path.is_symlink():
        raise ValueError('SYMLINK_REJECTED')
    raw = path.read_bytes() if path.exists() else b''
    data = json.loads(raw) if raw else {'mcpServers': {}}
    if not isinstance(data, dict) or not isinstance(data.get('mcpServers'), dict):
        raise ValueError('INVALID_CONFIG')
    return data, raw


def add_entry(data: dict, name: str, entry: dict):
    current = data['mcpServers'].get(name)
    if current is not None and current != entry:
        raise ValueError('PRODUCT_ENTRY_CONFLICT')
    data['mcpServers'][name] = entry


def merged(current: dict, source: dict | None = None, *, coros=False) -> dict:
    data = copy.deepcopy(current)
    if source is not None:
        entry = copy.deepcopy(source)
        command = entry.get('command')
        if not isinstance(command, str) or not Path(command).is_absolute():
            raise ValueError('ABSOLUTE_STDIO_COMMAND_REQUIRED')
        if not isinstance(entry.get('args', []), list) or not isinstance(entry.get('env', {}), dict) or not isinstance(entry.get('disabledTools', []), list):
            raise ValueError('INVALID_STDIO_ENTRY')
        if entry.get('url') or entry.get('headers'):
            raise ValueError('LOCAL_STDIO_SOURCE_REQUIRED')
        # A private source may reference an existing cache path, never embed secrets.
        for name, value in entry.get('env', {}).items():
            if name in {'GARMINTOKENS', 'GARMINTOKENS_BASE64'}:
                if not isinstance(value, str) or not Path(value).is_absolute():
                    raise ValueError('CREDENTIAL_PATH_REQUIRED_NOT_TOKEN')
            elif name not in {'GARMIN_IS_CN', 'GARMIN_MCP_TRANSPORT', 'GARMIN_ENABLED_TOOLS'}:
                raise ValueError('REVIEW_ENVIRONMENT_BEFORE_IMPORT')
        for value in [command, *entry.get('args', [])]:
            if not isinstance(value, str) or any(word in value.lower() for word in ['--password', '--token=', 'bearer ']):
                raise ValueError('CREDENTIAL_ARGUMENT_REJECTED')
        entry['disabledTools'] = sorted(set(entry.get('disabledTools', [])) | {'sync_recent'})
        add_entry(data, 'runwise-garmin', entry)
    if coros:
        add_entry(data, 'runwise-coros', {'type': 'streamableHttp', 'url': 'https://mcpcn.coros.com/mcp'})
    return data


def private_write(path: Path, raw: bytes):
    if path.is_symlink() or any(parent.is_symlink() for parent in (path.parent, *path.parent.parents)):
        raise ValueError('SYMLINK_REJECTED')
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.stat().st_mode & 0o077:
        raise ValueError('PRIVATE_OUTPUT_DIRECTORY_REQUIRED')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'wb') as handle:
        handle.write(raw)


def stage(config: Path, output: Path, *, source_config=None, source_name=None, coros=False) -> dict:
    if output.resolve() == config.resolve():
        raise ValueError('PREVIEW_MUST_NOT_REPLACE_CONFIG')
    current, before = read_config(config)
    source = None
    if source_config is not None:
        source_data, _ = read_config(source_config)
        source = source_data['mcpServers'].get(source_name)
        if not isinstance(source, dict):
            raise ValueError('SOURCE_ENTRY_NOT_FOUND')
    if source is None and not coros:
        raise ValueError('SELECT_A_CONNECTION')
    data = merged(current, source, coros=coros)
    raw = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()
    if output.exists() or output.is_symlink():
        if output.is_symlink() or output.read_bytes() != raw:
            raise ValueError('PREVIEW_OUTPUT_CONFLICT')
        return {'status': 'unchanged', 'config_modified': False, 'preview_sha256': hashlib.sha256(raw).hexdigest()}
    private_write(output, raw)
    backup = output.parent / ('mcp-before-' + uuid.uuid4().hex + '.json')
    if before:
        private_write(backup, before)
    manifest = {'original_sha256': hashlib.sha256(before).hexdigest(),
                'preview_sha256': hashlib.sha256(raw).hexdigest(),
                'original_existed': bool(before), 'config_modified': False,
                'added_server_names': sorted(set(data['mcpServers']) - set(current['mcpServers'])),
                'existing_server_names': sorted(current['mcpServers'])}
    private_write(output.with_suffix(output.suffix + '.manifest.json'), (json.dumps(manifest, indent=2) + '\n').encode())
    return {'status': 'preview_ready', **manifest}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True, help='Live WorkBuddy config path shown by its UI; read only')
    p.add_argument('--output', type=Path, required=True, help='Private staged JSON; not live config')
    p.add_argument('--garmin-source-config', type=Path)
    p.add_argument('--garmin-source-name')
    p.add_argument('--coros', action='store_true')
    a = p.parse_args()
    try:
        if a.garmin_source_config is not None and not a.garmin_source_name:
            raise ValueError('EXPLICIT_SOURCE_NAME_REQUIRED')
        result = stage(a.config, a.output, source_config=a.garmin_source_config, source_name=a.garmin_source_name, coros=a.coros)
    except (ValueError, OSError, KeyError, TypeError) as e:
        # No source configuration, full path or credential values in errors.
        code = str(e) if isinstance(e, ValueError) and str(e).isupper() else 'PREVIEW_FAILED'
        print(json.dumps({'status': 'error', 'code': code, 'config_modified': False}));return 2
    print(json.dumps(result));return 0

if __name__ == '__main__':
    sys.exit(main())
