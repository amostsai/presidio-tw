from pathlib import Path
import re
from copy import deepcopy
import yaml
import regex
from .recognizers import VALIDATORS

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / 'config' / 'rules.yaml'


def _score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError('score 必須介於 0 與 1')


def validate_config(config) -> dict:
    """Validate a copy so testing/editing a draft cannot mutate active settings."""
    cfg = deepcopy(config)
    if not isinstance(cfg, dict) or type(cfg.get('version')) is not int or cfg['version'] != 1:
        raise ValueError('設定 version 必須為 1')
    rules = cfg.setdefault('rules', [])
    if not isinstance(rules, list): raise ValueError('rules 必須為清單')
    names = set()
    for rule in rules:
        if not isinstance(rule, dict): raise ValueError('規則必須為物件')
        name = rule.get('name')
        try:
            if not isinstance(name, str) or not name or name in names: raise ValueError('name 缺漏或重複')
            names.add(name)
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,39}', str(rule.get('entity', ''))): raise ValueError('entity 必須是大寫英文代碼')
            if not isinstance(rule.get('enabled', True), bool): raise ValueError('enabled 必須是布林值')
            if rule.get('validator') and (not isinstance(rule['validator'], str) or rule['validator'] not in VALIDATORS): raise ValueError('未知 validator')
            patterns = rule.get('patterns', [])
            words = rule.get('deny_list', [])
            if not isinstance(patterns, list) or not isinstance(words, list): raise ValueError('patterns/deny_list 必須為清單')
            if rule.get('deny_list_match', 'word') not in ('word', 'substring'): raise ValueError('deny_list_match 必須為 word 或 substring')
            if not patterns and not words: raise ValueError('缺少 patterns 或 deny_list')
            for pattern in patterns:
                if not isinstance(pattern, dict) or not isinstance(pattern.get('regex'), str): raise ValueError('regex 必須是字串')
                regex.compile(pattern['regex'])
                _score(pattern.get('score', .8))
            if any(not isinstance(w, str) or not w for w in words): raise ValueError('deny_list 必須是非空字串清單')
            if not isinstance(rule.get('context', []), list) or any(not isinstance(w, str) for w in rule.get('context', [])): raise ValueError('context 必須是字串清單')
            _score(rule.get('deny_list_score', .9))
            for key_option in ('json_keys','field_keys'):
                keys = rule.get(key_option, [])
                if not isinstance(keys,list) or any(not isinstance(k,str) or not k.strip() for k in keys): raise ValueError(f'{key_option} 必須是非空欄位名稱清單')
            for regex_option in ('json_value_regex','field_value_regex'):
                if regex_option in rule:
                    if not isinstance(rule[regex_option],str) or not rule[regex_option]: raise ValueError(f'{regex_option} 必須是非空字串')
                    regex.compile(rule[regex_option])
        except (ValueError, regex.error) as exc:
            raise ValueError(f'規則 {name!r}: {exc}') from exc
    ner = cfg.setdefault('ner', {'enabled': False})
    if not isinstance(ner, dict) or not isinstance(ner.get('enabled', False), bool): raise ValueError('ner.enabled 必須是布林值')
    ner.setdefault('mapping', {'PERSON': 'PERSON', 'ORG': 'ORGANIZATION', 'GPE': 'LOCATION', 'LOC': 'LOCATION'})
    if not isinstance(ner['mapping'], dict) or (ner.get('enabled', False) and not ner['mapping']) or any(not isinstance(k, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,39}', str(v)) for k,v in ner['mapping'].items()): raise ValueError('ner.mapping 不合法')
    _score(ner.get('score', .85))
    size, overlap = ner.get('chunk_size', 400), ner.get('overlap', 64)
    if not isinstance(size, int) or not isinstance(overlap, int) or not 16 <= size <= 450 or not 0 <= overlap < size: raise ValueError('NER chunk_size / overlap 不合法')
    if not isinstance(ner.get('device', -1), int): raise ValueError('ner.device 必須是整數')
    if not isinstance(ner.get('model_name', 'ckiplab/bert-base-chinese-ner'), str): raise ValueError('ner.model_name 必須是字串')
    exclusions = cfg.setdefault('exclusions', [])
    if not isinstance(exclusions, list): raise ValueError('exclusions 必須為清單')
    for group in exclusions:
        if not isinstance(group, dict): raise ValueError('排除清單必須是物件')
        entity = group.get('entity', '*')
        if not isinstance(entity, str) or (entity != '*' and not re.fullmatch(r'[A-Z][A-Z0-9_]{0,39}', entity)): raise ValueError('排除清單的類型不合法')
        words = group.get('words')
        if not isinstance(words, list) or any(not isinstance(w, str) or not w.strip() for w in words): raise ValueError('排除清單 words 必須是非空字串清單')
    return cfg

def load_config(path=DEFAULT_CONFIG) -> dict:
    try:
        cfg = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError('無法讀取 YAML 規則設定檔') from exc
    return validate_config(cfg)
