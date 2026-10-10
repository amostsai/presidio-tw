"""Request-local, reversible tokens. Mapping files contain private original data."""
import json
import re
import secrets
from collections import Counter
from pathlib import Path

MAX_MAPPING_BYTES = 10 * 1024 * 1024
MAX_ENTRIES = 100_000
TOKEN = re.compile(r'\[\[[A-Z][A-Z0-9_]{0,39}_[a-f0-9]{8,32}_[0-9]{4,6}\]\]')
TOKEN_LIKE = re.compile(r'\[\[[^\[\]\r\n]{1,200}\]\]')
ENTITY = re.compile(r'[A-Z][A-Z0-9_]{0,39}')


def _unique_object(pairs):
    out = {}
    for k,v in pairs:
        if k in out: raise ValueError('JSON 包含重複欄位')
        out[k] = v
    return out


class MappingSession:
    def __init__(self, filename):
        self.filename = filename
        # PDF table cells cannot accommodate long entity labels. The mapping
        # retains the real entity; compact tokens still include the session ID.
        self.compact = Path(filename).suffix.lower() == '.pdf'
        self.session_id = secrets.token_hex(4)
        self.entries = []
        self.by_value = {}
        self.counts = Counter()

    def replace(self, text, matches):
        # Prevent accidental interpretation of pre-existing token-like content.
        if f'_{self.session_id}_' in text:
            if self.entries: raise ValueError('原文與此工作代碼衝突，請重新執行')
            self.session_id = secrets.token_hex(8)
        edits = []
        previous = 0
        for match in sorted(matches, key=lambda m: m.start):
            if not ENTITY.fullmatch(match.entity) or not 0 <= match.start < match.end <= len(text) or match.start < previous:
                raise ValueError('辨識結果的範圍或類型不合法')
            previous = match.end
            original = text[match.start:match.end]
            key = (match.entity, original)
            if key not in self.by_value:
                if len(self.entries) >= MAX_ENTRIES: raise ValueError('還原映射超過 100,000 筆')
                label = 'P' if self.compact else match.entity
                token = f'[[{label}_{self.session_id}_{len(self.entries)+1:04d}]]'
                self.by_value[key] = token
                self.entries.append({'token': token, 'entity': match.entity, 'original': original})
            self.counts[match.entity] += 1
            edits.append((match.start, match.end, self.by_value[key]))
        for start,end,replacement in reversed(edits): text = text[:start]+replacement+text[end:]
        return text

    def dump(self):
        data = json.dumps({'version': 2 if self.compact else 1, 'session_id': self.session_id, 'filename': self.filename, 'entries': self.entries}, ensure_ascii=False, indent=2).encode('utf-8')
        if len(data) > MAX_MAPPING_BYTES: raise ValueError('還原檔超過 10 MiB，請分割文件')
        return data

    def report(self):
        return {'matched_count': sum(self.counts.values()), 'unique_count': len(self.entries), 'entities': dict(self.counts)}


class RestorationMap:
    def __init__(self, entries):
        self.values = {e['token']: e['original'] for e in entries}
        self.restored_count = 0
        self.unresolved = set()

    def edits(self, text):
        edits = []
        for m in TOKEN_LIKE.finditer(text):
            token = m.group()
            if token in self.values:
                self.restored_count += 1
                edits.append((m.start(), m.end(), self.values[token]))
            else:
                self.unresolved.add(token)
        return edits

    def restore(self, text):
        for a,b,replacement in reversed(self.edits(text)):
            text = text[:a]+replacement+text[b:]
        return text

    def report(self):
        return {'restored_count': self.restored_count, 'unresolved_tokens': sorted(self.unresolved)}


def load_mapping(data):
    if len(data) > MAX_MAPPING_BYTES: raise ValueError('還原檔超過 10 MiB')
    try:
        d = json.loads(data.decode('utf-8-sig'), object_pairs_hook=_unique_object)
        if not isinstance(d, dict) or type(d.get('version')) is not int or d['version'] not in (1,2): raise ValueError('還原檔版本不支援')
        sid = d.get('session_id')
        if not isinstance(sid, str) or not re.fullmatch('[a-f0-9]{8,32}', sid): raise ValueError('還原檔工作識別碼不合法')
        if not isinstance(d.get('filename'), str): raise ValueError('還原檔缺少檔名')
        entries = d.get('entries')
        if not isinstance(entries, list) or len(entries) > MAX_ENTRIES: raise ValueError('還原映射數量不合法')
        seen = set()
        for e in entries:
            if not isinstance(e, dict) or not isinstance(e.get('entity'), str) or not ENTITY.fullmatch(e['entity']): raise ValueError('還原映射類型不合法')
            token = e.get('token')
            label = 'P' if d['version'] == 2 else e['entity']
            if not isinstance(token, str) or not TOKEN.fullmatch(token) or not re.fullmatch(r'\[\['+re.escape(label+'_'+sid)+r'_[0-9]{4,6}\]\]', token): raise ValueError('還原代碼不合法')
            if token in seen: raise ValueError('還原映射有重複或衝突代碼')
            if not isinstance(e.get('original'), str) or not e['original']: raise ValueError('還原映射缺少原文')
            seen.add(token)
        return RestorationMap(entries)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('無法讀取 JSON 還原檔') from exc
