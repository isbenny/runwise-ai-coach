#!/usr/bin/env python3
"""Read-only local checks. Executable presence is NOT MCP/Skill proof."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);a=p.parse_args()
print(json.dumps(dict(python_version=sys.version.split()[0],python_for_calculations=sys.version_info>=(3,10),
    jsonschema_available=importlib.util.find_spec('jsonschema') is not None,
    existing_workspace=a.workspace.is_dir(),executables={name:shutil.which(name) is not None for name in ['codex','claude','uv']},
    host_capabilities='must verify from current AI tool inventory / client UI; not inferred from executable',
    required=['Skill installation','selected MCP transport','authorization entry','private storage'],
    changes_made=False),ensure_ascii=False,indent=2))
