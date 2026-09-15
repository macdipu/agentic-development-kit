"""Validate production-readiness evidence, never grant deployment authority."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re

STAGE_CONTROLS = {
    'OBSERVE': ['read_only_identity', 'audit', 'data_handling'],
    'PREPARE': ['worker_isolation', 'credential_scope', 'verification', 'artifact_integrity'],
    'APPROVED_EXECUTION': ['authenticated_approval', 'durable_jobs', 'effect_reconciliation',
                           'health_checks', 'rollback', 'kill_switch', 'alerting', 'backup_restore'],
    'BOUNDED_AUTONOMY': ['standing_authorization', 'operation_limits', 'canary', 'periodic_revalidation'],
}


def required_controls(stage):
    if stage not in STAGE_CONTROLS:
        raise ValueError('Unknown production stage')
    controls = []
    for name, items in STAGE_CONTROLS.items():
        controls.extend(items)
        if name == stage:
            return controls


def check_readiness(document, evidence_root, now=None):
    if not isinstance(document, dict):
        raise ValueError('Readiness document must be an object')
    stage = document.get('stage')
    required = required_controls(stage)
    root = Path(evidence_root).resolve()
    current = now or datetime.now(timezone.utc)
    problems = []
    if type(document.get('schema_version')) is not int or document.get('schema_version') != 1:
        problems.append('schema_version must be 1')
    for field in ('environment', 'owner'):
        if not isinstance(document.get(field), str) or not document[field].strip():
            problems.append('Missing ' + field)
    digest = document.get('change_sha256', '')
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        problems.append('change_sha256 must identify the exact reviewed change/artifact')
    operations = document.get('operations')
    if not isinstance(operations, list) or not operations or any(not isinstance(op, str) or not op.strip() or '*' in op for op in operations):
        problems.append('operations must list explicit bounded operation IDs without wildcards')
    controls = document.get('controls', {})
    if not isinstance(controls, dict):
        raise ValueError('controls must be an object')
    for name in required:
        control = controls.get(name)
        if not isinstance(control, dict) or control.get('status') != 'VERIFIED':
            problems.append(name + ': missing verified evidence')
            continue
        try:
            verified = datetime.fromisoformat(control['verified_at'])
            expires = datetime.fromisoformat(control['expires_at'])
            if verified.tzinfo is None or expires.tzinfo is None or not verified <= current < expires:
                raise ValueError('evidence is future-dated, expired, or lacks a timezone')
            if not isinstance(control.get('reviewer'), str) or not control['reviewer'].strip():
                raise ValueError('reviewer reference missing')
            if (control.get('environment') != document.get('environment') or
                    control.get('change_sha256') != digest or control.get('operations') != operations):
                raise ValueError('evidence is not bound to this environment, change, and operations')
            path = (root / control['path']).resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size == 0:
                raise ValueError('evidence must be a nonempty file inside the evidence directory')
            if hashlib.sha256(path.read_bytes()).hexdigest() != control.get('sha256'):
                raise ValueError('evidence hash mismatch')
        except (KeyError, TypeError, ValueError, OSError) as exc:
            problems.append(name + ': ' + str(exc))
    if stage == 'BOUNDED_AUTONOMY':
        limits = document.get('limits', {})
        if not isinstance(limits, dict):
            limits = {}
        for field in ('max_actions', 'max_seconds', 'max_affected_resources'):
            if type(limits.get(field)) is not int or limits[field] <= 0:
                problems.append('limits.' + field + ' must be a positive integer')
    return {'stage': stage, 'status': 'BLOCKED' if problems else 'EVIDENCE_COMPLETE',
            'blocking_issues': problems, 'required_controls': required,
            'deployment_authorized': False,
            'boundary': 'Local evidence checks do not authenticate reviewers or exercise external controls. Execution requires a separate enforcing adapter.'}
