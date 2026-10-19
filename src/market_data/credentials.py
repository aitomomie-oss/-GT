"""Resolve credentials relative to this app, never relative to the launch directory.

Only safe status codes/paths cross the diagnostic boundary. No exception text or
secret values are logged, returned by credential_status, or written to SQLite.
"""
from pathlib import Path
import os
import tomllib
from collections.abc import Mapping

PROJECT_ROOT=Path(__file__).resolve().parents[2]


def _validate(value):
    if value is None or value=='': return '',None
    if not isinstance(value,str): return '','key_type_invalid'
    value=value.strip()
    if not value: return '',None
    if len(value)>8192 or any(not 33<=ord(c)<=126 for c in value): return '','key_format_invalid'
    return value,None


def _extract(mapping):
    value=mapping.get('JQUANTS_API_KEY')
    key,issue=_validate(value)
    if key: return key,None
    section=mapping.get('jquants',{})
    if isinstance(section,Mapping):
        nested,nested_issue=_validate(section.get('api_key'))
        if nested: return nested,None
        issue=issue or nested_issue
    return '',issue


def _resolve():
    project_file=PROJECT_ROOT/'.streamlit/secrets.toml'
    status=dict(configured=False,source='none',project_file=str(project_file),project_file_exists=False,
                working_directory=str(Path.cwd()),issues=[])
    def found(key,source):
        status.update(configured=True,source=source)
        return key,status
    file_bad=False
    try:
        status['project_file_exists']=project_file.is_file()
        if status['project_file_exists']:
            # utf-8-sig accepts files created by Windows editors that add a BOM.
            with project_file.open('r',encoding='utf-8-sig') as handle: data=tomllib.loads(handle.read())
            key,issue=_extract(data)
            if issue: status['issues'].append(issue)
            if key: return found(key,'project_secrets')
            status['issues'].append('project_key_not_found')
    except (OSError,UnicodeError,tomllib.TOMLDecodeError):
        status['issues'].append('project_secrets_unreadable');file_bad=True
    # A malformed local TOML can also make st.secrets fail. Do not reparse it there,
    # and never display the parser exception (which can contain a source line).
    if not file_bad:
        try:
            import streamlit as st
            key,issue=_extract(st.secrets)
            if issue: status['issues'].append(issue)
            if key: return found(key,'streamlit_secrets')
        except Exception:
            status['issues'].append('streamlit_secrets_unavailable')
    key,issue=_validate(os.environ.get('JQUANTS_API_KEY'))
    if issue: status['issues'].append(issue)
    if key: return found(key,'environment')
    status['issues']=list(dict.fromkeys(status['issues']))
    return '',status


def jquants_key():
    return _resolve()[0]


def credential_status():
    """Safe to display: deliberately excludes values, lengths, hashes and file text."""
    return _resolve()[1]
