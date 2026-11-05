"""Explicit backend-only environment file; no shell execution or interpolation."""
import os
import re
from pathlib import Path

_EXACT={'BASETEN_API_KEY','LIVE_AI_TEST','PORT','BIND_HOST','REQUIRE_FRONTEND','FRONTEND_DIST',
        'CORS_ORIGINS','GEOMETRY_MAX_CONCURRENCY','EXPENSIVE_REQUESTS_PER_MINUTE',
        'REQUEST_BODY_TIMEOUT_SECONDS'}


def load_environment(path=None, environ=None):
    """Load only an explicitly selected file. Existing process settings win.

    Supports KEY=value, optional export, comments and whole-value quotes.
    Values stay literal: no expansion, escapes, multiline values or execution.
    Errors identify only a line number/code, never its content or credentials.
    """
    env=os.environ if environ is None else environ
    selected=path if path is not None else env.get('MFT_ENV_FILE')
    if not selected:return
    try:
        with Path(selected).open('rb') as source:raw=source.read(65537)
    except OSError:raise ValueError('environment_file_unavailable') from None
    if len(raw)>65536:raise ValueError('environment_file_too_large')
    try:text=raw.decode('utf-8')
    except UnicodeError:raise ValueError('environment_file_invalid_encoding') from None
    parsed={}
    for number,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('export '):line=line[7:].lstrip()
        key,separator,value=line.partition('=');key=key.strip();value=value.strip()
        if (not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*',key)
                or not (key in _EXACT or key.startswith(('AI_','SEGMENTATION_','RECOMMENDATION_')))
                or key in parsed or any(ord(c)<32 for c in value)):
            raise ValueError(f'environment_file_invalid_line_{number}')
        if value[:1] in ('"',"'"):
            if len(value)<2 or value[-1]!=value[0]:raise ValueError(f'environment_file_invalid_line_{number}')
            value=value[1:-1]
        parsed[key]=value
    # Validate the entire file before applying any settings; never override a host secret.
    for key,value in parsed.items():env.setdefault(key,value)
