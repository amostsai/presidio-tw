from dataclasses import dataclass, field
from threading import Lock
import regex
from presidio_analyzer import Pattern, PatternRecognizer
from .recognizers import VALIDATORS


@dataclass(frozen=True)
class Match:
    entity: str
    start: int
    end: int
    score: float


class ConfiguredRecognizer(PatternRecognizer):
    def __init__(self, rule):
        self.validator = VALIDATORS.get(rule.get('validator'))
        patterns = [Pattern(p.get('name', f'pattern_{i}'), p['regex'], p.get('score', .8)) for i,p in enumerate(rule.get('patterns', []))]
        # Presidio's default deny-list word boundaries exclude adjacent Chinese.
        if rule.get('deny_list'):
            literals = []
            for word in sorted(rule['deny_list'], key=len, reverse=True):
                literal = regex.escape(word)
                if rule.get('deny_list_match', 'word') == 'word':
                    if regex.fullmatch(r'[A-Za-z0-9_]', word[0]): literal = r'(?<![A-Za-z0-9_])' + literal
                    if regex.fullmatch(r'[A-Za-z0-9_]', word[-1]): literal += r'(?![A-Za-z0-9_])'
                literals.append(literal)
            patterns.append(Pattern('dictionary', '|'.join(literals), rule.get('deny_list_score', .9)))
        super().__init__(name=rule['name'], supported_entity=rule['entity'], patterns=patterns, context=rule.get('context', []), supported_language='zh')

    def validate_result(self, text):
        return self.validator(text) if self.validator else None


@dataclass
class NerRuntime:
    driver: object = None
    lock: object = field(default_factory=Lock)


class PiiService:
    def __init__(self, config):
        self.config = config
        self.recognizers = [ConfiguredRecognizer(r) for r in config['rules'] if r.get('enabled', True)]
        self._ner_state = NerRuntime()
        self.exclusions = {}
        for group in config.get('exclusions', []):
            self.exclusions.setdefault(group.get('entity', '*'), set()).update(w.casefold() for w in group['words'])

    @property
    def ner_driver(self): return self._ner_state.driver

    @ner_driver.setter
    def ner_driver(self, value): self._ner_state.driver = value

    @property
    def lock(self): return self._ner_state.lock

    @property
    def entities(self):
        entities = {r.supported_entities[0] for r in self.recognizers}
        if self.config['ner'].get('enabled', False): entities.update(self.config['ner']['mapping'].values())
        return sorted(entities)

    def is_field_key(self, key):
        return any(rule.get('enabled',True) and key.strip().casefold() in {
            k.casefold() for k in rule.get('field_keys',rule.get('json_keys',[]))
        } for rule in self.config['rules'])

    def analyze(self, text, entities=None, field_key=None):
        if not text.strip(): return []
        if len(text) > 2_000_000: raise ValueError('文字過長，最多 2,000,000 字元')
        requested = set(self.entities if entities is None else entities)
        found = []
        if field_key is not None:
            for rule in self.config['rules']:
                if not rule.get('enabled',True) or rule['entity'] not in requested: continue
                if field_key.strip().casefold() not in {key.casefold() for key in rule.get('field_keys',rule.get('json_keys',[]))}: continue
                pattern = rule.get('field_value_regex',rule.get('json_value_regex'))
                if pattern and regex.fullmatch(pattern,text):
                    found.append(Match(rule['entity'],0,len(text),1.0))
        for r in self.recognizers:
            if r.supported_entities[0] not in requested: continue
            for m in r.analyze(text, list(requested)):
                if m.end <= m.start: continue
                score = m.score
                nearby = text[max(0,m.start-24):m.end+24].lower()
                if any(c.lower() in nearby for c in (r.context or [])): score = min(1., score+.05)
                found.append(Match(m.entity_type, m.start, m.end, score))
        ner = self.config['ner']
        if ner.get('enabled', False) and requested.intersection(ner['mapping'].values()):
            with self.lock:
                if self.ner_driver is None:
                    from ckip_transformers.nlp import CkipNerChunker
                    self.ner_driver = CkipNerChunker(model_name=ner.get('model_name', 'ckiplab/bert-base-chinese-ner'), device=ner.get('device', -1))
                size = ner.get('chunk_size', 400)
                step = size - ner.get('overlap', 64)
                starts = list(range(0, len(text), step))
                # Small batches bound model memory even for long documents.
                for offset in range(0, len(starts), 16):
                    batch = starts[offset:offset+16]
                    outputs = self.ner_driver([text[i:i+size] for i in batch], show_progress=False)
                    for start, results in zip(batch, outputs):
                        for ent in results:
                            target = ner['mapping'].get(ent.ner)
                            if target in requested:
                                a,b = ent.idx
                                if 0 <= a < b <= len(text[start:start+size]): found.append(Match(target, start+a, start+b, ner.get('score', .85)))
        accepted = []
        for m in sorted(set(found), key=lambda m: (-m.score, -(m.end-m.start), m.start, m.entity)):
            original = text[m.start:m.end].casefold()
            if original in self.exclusions.get('*', ()) or original in self.exclusions.get(m.entity, ()): continue
            if not any(m.start < a.end and a.start < m.end for a in accepted): accepted.append(m)
        return sorted(accepted, key=lambda m: m.start)


def create_service(config):
    return PiiService(config)


class PiiTransform:
    """Expose full replacement spans so PDF/Office never infer PII boundaries."""
    def __init__(self, service, session, entities=None):
        self.service, self.session, self.entities = service, session, entities

    def edits(self, text):
        edits = []
        for match in self.service.analyze(text, self.entities):
            original = text[match.start:match.end]
            replacement = self.session.replace(original, [Match(match.entity, 0, len(original), match.score)])
            edits.append((match.start, match.end, replacement))
        return edits

    def __call__(self, text):
        for start,end,replacement in reversed(self.edits(text)):
            text = text[:start]+replacement+text[end:]
        return text

    def for_field(self, text, key):
        return self.session.replace(text, self.service.analyze(text,self.entities,field_key=key))

    def is_field_key(self, key):
        return self.service.is_field_key(key)
