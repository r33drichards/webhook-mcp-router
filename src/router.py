"""Offline routing kernel. This module has no network delivery implementation."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import resource
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 256 * 1024
MAX_POLICY = 32 * 1024
SYNTHETIC_SECRET = b'public-synthetic-test-key-not-for-production'

class Rejected(Exception):
    """Only fixed, credential-free errors cross the public boundary."""

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)

def digest(value):
    return hashlib.sha256(value).hexdigest()

def verify_github(raw, headers, secret):
    if not isinstance(raw, bytes) or len(raw) > MAX_BODY:
        raise Rejected('payload_limit')
    signature = headers.get('x-hub-signature-256', '')
    if not isinstance(signature, str) or not re.fullmatch(r'sha256=[0-9a-f]{64}', signature):
        raise Rejected('signature_invalid')
    expected = 'sha256=' + hmac.new(secret, raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise Rejected('signature_invalid')
    # Only parse after authenticating exact original bytes.
    try:
        body = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise Rejected('json_invalid') from None
    if not isinstance(body, dict):
        raise Rejected('json_invalid')
    for key in ('x-github-delivery', 'x-github-event'):
        if not isinstance(headers.get(key), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', headers[key]):
            raise Rejected('metadata_invalid')
    return {'provider': 'github', 'type': headers['x-github-event'], 'body': body}

def child_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    # OPA's Go runtime reserves large virtual memory; use cgroups in production.

class Policy:
    def __init__(self, source=None, binary=None):
        self.source = source or (ROOT / 'policies/routes.rego').read_text()
        self.binary = str(binary or ROOT / '.tools/opa')
        self.validate(self.source)

    @property
    def version(self):
        return digest(self.source.encode())

    def _run(self, source, event_input=None):
        if not isinstance(source, str) or len(source.encode()) > MAX_POLICY:
            raise Rejected('policy_limit')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'routes.rego'
            path.write_text(source)
            args = [self.binary]
            if event_input is None:
                args += ['check', '--strict', str(path)]
            else:
                args += ['eval', '--strict', '--strict-builtin-errors', '--timeout=200ms',
                         '--format=json', '--stdin-input', '--data', str(path),
                         'data.router.subscription_ids']
            args += ['--capabilities', str(ROOT / 'policies/capabilities.json')]
            try:
                with tempfile.TemporaryFile() as out:
                    result = subprocess.run(args, input=canonical(event_input).encode(),
                                            stdout=out, stderr=subprocess.DEVNULL,
                                            timeout=3, env={'PATH': '/usr/bin:/bin'},
                                            preexec_fn=child_limits, check=False)
                    if result.returncode:
                        raise Rejected('policy_rejected')
                    out.seek(0)
                    output = out.read(1024 * 1024 + 1)
                    if len(output) > 1024 * 1024:
                        raise Rejected('policy_output_limit')
                    return output
            except (OSError, subprocess.TimeoutExpired):
                raise Rejected('policy_unavailable') from None

    def validate(self, source):
        self._run(source)
        # Also require the decision to exist and have the expected type.
        self.evaluate({'event': {}, 'subscriptions': []}, source)
        return {'valid': True, 'version': digest(source.encode())}

    def evaluate(self, value, source=None):
        try:
            output = json.loads(self._run(self.source if source is None else source, value))
            ids = output['result'][0]['expressions'][0]['value']
        except (KeyError, IndexError, ValueError, TypeError):
            raise Rejected('decision_invalid') from None
        if not isinstance(ids, list) or len(ids) > 100 or any(not isinstance(i, str) for i in ids):
            raise Rejected('decision_invalid')
        allowed = {s['id'] for s in value['subscriptions']}
        if not set(ids) <= allowed:
            raise Rejected('decision_unknown_subscription')
        return sorted(set(ids))

    def update(self, source, expected_version):
        if expected_version != self.version:
            raise Rejected('policy_version_conflict')
        result = self.validate(source)
        self.source = source  # Process-local edit: restart restores the file.
        return result

class Router:
    def __init__(self, database, policy, owner='local-demo', clock=time.time):
        self.policy, self.owner, self.clock = policy, owner, clock
        self.db = sqlite3.connect(database)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, repository TEXT NOT NULL,
            expires REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS receipts (
            source TEXT NOT NULL, delivery TEXT NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY(source, delivery), UNIQUE(source, digest));
          CREATE TABLE IF NOT EXISTS outbox (
            position INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription TEXT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
            event_id TEXT NOT NULL, payload TEXT NOT NULL, policy_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'dry_run', UNIQUE(subscription,event_id));
        ''')

    def register_demo(self, ident, repository, ttl=3600):
        if not re.fullmatch(r'sub_[a-z0-9_-]{1,64}', ident) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise Rejected('subscription_invalid')
        if type(ttl) is not int or not 1 <= ttl <= 86400:
            raise Rejected('ttl_invalid')
        old = self.db.execute('SELECT owner FROM subscriptions WHERE id=?', (ident,)).fetchone()
        if old and old[0] != self.owner:
            raise Rejected('subscription_forbidden')
        if not old and self.db.execute('SELECT count(*) FROM subscriptions').fetchone()[0] >= 100:
            raise Rejected('subscription_limit')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO subscriptions VALUES (?,?,?,?)',
                            (ident, self.owner, repository, self.clock() + ttl))
        return {'id': ident, 'mode': 'dry_run'}

    def subscriptions(self):
        return [{'id': i, 'repository': r} for i, r in self.db.execute(
            'SELECT id,repository FROM subscriptions WHERE owner=? AND expires>?',
            (self.owner, self.clock()))]

    def remove(self, ident):
        with self.db:
            self.db.execute('DELETE FROM subscriptions WHERE id=? AND owner=?', (ident, self.owner))
        return {}

    def ingest(self, raw, headers, secret=SYNTHETIC_SECRET):
        event = verify_github(raw, headers, secret)
        # Source identity is operator configuration, never a request parameter.
        source = self.owner + ':github:synthetic'
        hashed = digest(raw)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old = self.db.execute('SELECT digest FROM receipts WHERE source=? AND delivery=?',
                                  (source, headers['x-github-delivery'])).fetchone()
            if old and old[0] != hashed:
                raise Rejected('delivery_collision')
            if old or self.db.execute('SELECT 1 FROM receipts WHERE source=? AND digest=?', (source, hashed)).fetchone():
                return {'duplicate': True, 'queued': 0}
            ids = self.policy.evaluate({'event': event, 'subscriptions': self.subscriptions()})
            if self.db.execute('SELECT count(*) FROM outbox').fetchone()[0] + len(ids) > 10000:
                raise Rejected('outbox_limit')
            if self.db.execute('SELECT count(*) FROM receipts').fetchone()[0] >= 10000:
                raise Rejected('receipt_limit')
            self.db.execute('INSERT INTO receipts VALUES (?,?,?)',
                            (source, headers['x-github-delivery'], hashed))
            event_id = 'evt_' + digest((source + ':' + hashed).encode())
            for ident in ids:
                cur = self.db.execute('INSERT INTO outbox(subscription,event_id,payload,policy_version) VALUES (?,?,?,?)',
                                      (ident, event_id, '', self.policy.version))
                envelope = {'eventId': event_id, 'name': 'webhook.received',
                            'timestamp': datetime.fromtimestamp(self.clock(), timezone.utc).isoformat().replace('+00:00', 'Z'),
                            'data': event, 'cursor': ident + ':' + str(cur.lastrowid)}
                payload = canonical(envelope)
                if len(payload.encode()) > MAX_BODY:
                    raise Rejected('envelope_limit')
                self.db.execute('UPDATE outbox SET payload=? WHERE position=?', (payload, cur.lastrowid))
        return {'duplicate': False, 'queued': len(ids), 'mode': 'dry_run'}
