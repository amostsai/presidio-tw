"""Validated, revision-aware config persistence with atomic runtime snapshots."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import tempfile
from threading import RLock
import yaml
from .config import validate_config
from .service import create_service

TEMPLATES_PATH = Path(__file__).resolve().parent.parent/'config/rule_templates.yaml'
MAX_SETTINGS_BYTES = 2 * 1024 * 1024


class SettingsConflict(ValueError):
    pass


def _revision(data): return hashlib.sha256(data).hexdigest()


def _parse(data):
    if len(data) > MAX_SETTINGS_BYTES: raise ValueError('隱私設定超過 2 MiB，請減少清單或規則數量')
    try: return validate_config(yaml.safe_load(data.decode('utf-8')))
    except (UnicodeError, yaml.YAMLError) as exc: raise ValueError('無法讀取 YAML 隱私設定') from exc


def _atomic_write(path, data, expected=None):
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+path.name+'.', delete=False) as tmp:
            name = tmp.name
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        if expected is not None and path.read_bytes() != expected:
            raise SettingsConflict('設定在儲存期間已更新，請重新載入')
        os.replace(name, path)
    finally:
        if name and os.path.exists(name): os.unlink(name)


class SettingsManager:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.lock = RLock()
        self.cfg = None
        self.service = None
        self.revision = None
        self.initial_error = None
        self.draft_runtime = None
        try: self.snapshot()
        except ValueError as exc: self.initial_error = str(exc)

    def _read(self):
        try: return self.path.read_bytes()
        except OSError as exc: raise ValueError('無法讀取隱私設定檔，請檢查檔案路徑與權限') from exc

    def _build(self, cfg):
        service = create_service(cfg)
        identity = lambda n: (n.get('model_name','ckiplab/bert-base-chinese-ner'), n.get('device',-1))
        key = identity(cfg['ner'])
        if self.service is not None:
            if key == identity(self.cfg['ner']):
                service._ner_state = self.service._ner_state
                return service
        if self.draft_runtime is not None and self.draft_runtime[0] == key:
            service._ner_state = self.draft_runtime[1]
        # Retain one alternative runtime, bounding memory while sharing preview/save.
        self.draft_runtime = (key, service._ner_state)
        return service

    def snapshot(self):
        with self.lock:
            data = self._read()
            rev = _revision(data)
            if rev != self.revision:
                cfg = _parse(data)
                service = self._build(cfg)
                self.cfg, self.service, self.revision = cfg, service, rev
                self.initial_error = None
            return deepcopy(self.cfg), self.service, self.revision

    def draft_service(self, config):
        cfg = validate_config(config)
        with self.lock: return self._build(cfg)

    def save(self, config, revision):
        cfg = validate_config(config)
        data = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False).encode('utf-8')
        if len(data) > MAX_SETTINGS_BYTES: raise ValueError('隱私設定超過 2 MiB')
        with self.lock:
            previous = self._read()
            if not isinstance(revision,str) or revision != _revision(previous):
                raise SettingsConflict('設定已被其他頁面或外部編輯更新，請重新載入後再儲存')
            service = self._build(cfg)
            try:
                _atomic_write(self.path.with_suffix(self.path.suffix+'.bak'), previous)
                # Check once more after backup, before replacing the original.
                if self._read() != previous: raise SettingsConflict('設定在儲存期間已更新，請重新載入')
                _atomic_write(self.path, data, expected=previous)
            except OSError as exc: raise ValueError('無法儲存隱私設定，請檢查資料夾寫入權限及磁碟空間；原設定保持不變') from exc
            self.cfg, self.service, self.revision = cfg, service, _revision(data)
            self.initial_error = None
            return deepcopy(cfg), self.revision


def form_choices():
    try:
        templates = yaml.safe_load(TEMPLATES_PATH.read_text(encoding='utf-8'))['templates']
    except (OSError, KeyError, TypeError, yaml.YAMLError) as exc: raise ValueError('無法讀取新增規則範本') from exc
    return {
        'templates': templates,
        'validators': [{'value':'','label':'不校驗'}, {'value':'tw_id','label':'台灣身分證校驗'}, {'value':'tw_tax_id','label':'台灣統編校驗'}],
        'entity_choices': [{'value':'PERSON','label':'姓名'}, {'value':'TW_NATIONAL_ID','label':'身分證'}, {'value':'PHONE_NUMBER','label':'手機／電話'}, {'value':'TW_TAX_ID','label':'統一編號'}, {'value':'EMAIL','label':'電子信箱'}, {'value':'LOCATION','label':'地點'}, {'value':'ORGANIZATION','label':'組織'}],
    }
