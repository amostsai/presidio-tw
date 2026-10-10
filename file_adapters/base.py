from dataclasses import dataclass, field
from difflib import SequenceMatcher

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_UNPACKED_BYTES = 50 * 1024 * 1024


class FileProcessingError(ValueError):
    pass


@dataclass
class FileResult:
    content: bytes
    media_type: str
    warnings: list[str] = field(default_factory=list)


def replace_spans(text, spans):
    last = 0
    for a,b,_ in sorted(spans):
        if not last <= a <= b <= len(text): raise FileProcessingError('文字修改範圍不合法')
        last = b
    for a,b,value in sorted(spans, reverse=True): text = text[:a]+value+text[b:]
    return text


def compute_edits(text, transform):
    owner = getattr(transform, '__self__', transform)
    if callable(getattr(owner, 'edits', None)):
        return owner.edits(text)
    output = transform(text)
    return [(a,b,output[c:d]) for op,a,b,c,d in SequenceMatcher(None, text, output).get_opcodes() if op != 'equal']


class BoundedTransform:
    def __init__(self, transform):
        self.transform = transform
        self.total = 0

    def account(self, text):
        self.total += len(text)
        if self.total > MAX_TEXT_CHARS: raise FileProcessingError('文件文字超過 2,000,000 字元')

    def __call__(self, text):
        self.account(text)
        return self.transform(text)

    def edits(self, text):
        self.account(text)
        return compute_edits(text, self.transform)

    def for_field(self, text, key):
        self.account(text)
        handler = getattr(self.transform, 'for_field', None)
        return handler(text, key) if callable(handler) else self.transform(text)

    def is_field_key(self, key):
        handler = getattr(self.transform, 'is_field_key', None)
        return bool(handler(key)) if callable(handler) else False
