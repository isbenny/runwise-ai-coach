#!/usr/bin/env python3
"""Verify and install only the Skill in an explicit project. No global edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    records=[]
    for line in (root/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts:raise RuntimeError('MANIFEST_PATH_INVALID')
        path=root/rel
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('CHECKSUM_MISMATCH')
        records.append((name,digest))
    return records


def install(workspace,apply=False):
    records=verify();workspace=workspace.absolute()
    if not workspace.is_dir() or workspace.is_symlink():raise RuntimeError('EXISTING_PROJECT_WORKSPACE_REQUIRED')
    parent=workspace/'.agents/skills';destination=parent/'runwise-coach'
    for folder in [workspace/'.agents',parent,destination]:
        if folder.is_symlink():raise RuntimeError('SYMLINK_TARGET_NOT_ALLOWED')
    if destination.exists():
        existing={str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        expected={name for name,_ in records}|{'SHA256SUMS'}
        if existing!=expected or any((destination/n).is_symlink() or hashlib.sha256((destination/n).read_bytes()).hexdigest()!=d for n,d in records):raise RuntimeError('EXISTING_SKILL_DIFFERS_PRESERVED')
        if (destination/'SHA256SUMS').read_bytes()!=(ROOT/'SHA256SUMS').read_bytes():raise RuntimeError('EXISTING_MANIFEST_DIFFERS_PRESERVED')
        return dict(status='unchanged',destination=str(destination),files=len(expected))
    result=dict(status='preview',version='0.1.0',destination=str(destination),files=[n for n,_ in records]+['SHA256SUMS'],
                host_checks_required=['Skill installation available','MCP transport + tools enabled','safe local authentication or official OAuth','private persistent storage'],
                install_dependencies=False,configure_mcp=False,network=False,global_config_changes=False,
                next_step='Show this preview, obtain person confirmation, then rerun with --apply. MCP/auth are separate confirmed steps.')
    if not apply:return result
    parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.runwise-',dir=parent));stage.chmod(0o700)
    try:
        for name,_ in records:
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);target.chmod(0o600)
        shutil.copyfile(ROOT/'SHA256SUMS',stage/'SHA256SUMS');(stage/'SHA256SUMS').chmod(0o600)
        if destination.exists():raise RuntimeError('TARGET_APPEARED_PRESERVED')
        stage.rename(destination)
    finally:
        if stage.exists():shutil.rmtree(stage)
    return dict(result,status='installed',files=len(records)+1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args();os.umask(0o077)
    try:print(json.dumps(install(a.workspace,a.apply),ensure_ascii=False,indent=2))
    except (RuntimeError,ValueError,OSError) as exc:print(json.dumps({'status':'error','code':str(exc) if isinstance(exc,RuntimeError) else 'LOCAL_INSTALL_FAILED'}));sys.exit(2)
