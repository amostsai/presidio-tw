"""Lexical edits keep surrounding source layout instead of serializing documents."""
import csv
import io
import json
import re
from xml.sax.saxutils import escape, unescape
from .text import decode_text, encode_text
from .base import FileResult, FileProcessingError, replace_spans

JSON_STRING = re.compile(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"')
JSON_LEXEME = re.compile(JSON_STRING.pattern + r'|[{}\[\],:]')
JSON_KEY_SEPARATOR = re.compile(r'\s*:')
XML_TOKEN = re.compile(r'<!--[\s\S]*?-->|<!\[CDATA\[[\s\S]*?\]\]>|<\?[\s\S]*?\?>|<(?:[^>"\']|"[^"]*"|\'[^\']*\')*>|[^<]+')
XML_ATTR = re.compile(r'(\s[^\s=<>/]+\s*=\s*)(["\'])(.*?)\2', re.DOTALL)


def _json_object(pairs):
    out = {}
    for k,v in pairs:
        if k in out: raise FileProcessingError('JSON 鍵名稱重複或替換後發生碰撞')
        out[k] = v
    return out


def _validate_json(text):
    try:
        return json.loads(text, object_pairs_hook=_json_object, parse_constant=lambda _: (_ for _ in ()).throw(FileProcessingError('JSON 不允許 NaN/Infinity')))
    except (json.JSONDecodeError, RecursionError) as exc: raise FileProcessingError('JSON 格式不合法') from exc


def transform_json(content, transform, encoding):
    text, encoding, bom = decode_text(content, encoding)
    _validate_json(text)
    spans = []
    stack = []
    for token in JSON_LEXEME.finditer(text):
        raw = token.group()
        field = stack[-1]['key'] if stack else None
        if raw in ('{','['):
            stack.append({'kind':raw,'key':field if raw == '[' else None})
            continue
        if raw in ('}',']'):
            stack.pop(); continue
        if raw == ',':
            if stack and stack[-1]['kind'] == '{': stack[-1]['key'] = None
            continue
        if raw == ':': continue
        value = json.loads(raw)
        if JSON_KEY_SEPARATOR.match(text,token.end()):
            stack[-1]['key'] = value
            continue
        changed = transform.for_field(value,field) if callable(getattr(transform,'for_field',None)) else transform(value)
        if changed != value: spans.append((token.start(), token.end(), json.dumps(changed, ensure_ascii=False)))
    result = replace_spans(text, spans)
    _validate_json(result)
    return FileResult(encode_text(result, encoding, bom), 'application/json')


def transform_csv(content, transform, encoding):
    text, encoding, bom = decode_text(content, encoding)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t|')
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ','
    # Validate first; scanner below retains all original separators and newlines.
    try: rows = list(csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True))
    except csv.Error as exc: raise FileProcessingError('CSV 格式不合法') from exc
    header_index = next((i for i,row in enumerate(rows) if row),None)
    headers = rows[header_index] if header_index is not None else []
    known = getattr(transform,'is_field_key',lambda key:False)
    has_header = any(known(value) for value in headers)
    edits = []
    pos = 0
    row_index = column = 0
    while pos < len(text):
        if text[pos] in '\r\n':
            pos += 2 if text[pos:pos+2] == '\r\n' else 1
            row_index += 1; column = 0; continue
        start = pos
        quoted = text[pos] == '"'
        if quoted:
            pos += 1
            while pos < len(text):
                if text[pos] == '"':
                    if pos+1 < len(text) and text[pos+1] == '"': pos += 2; continue
                    pos += 1; break
                pos += 1
            if pos > len(text) or not text[start:pos].endswith('"'): raise FileProcessingError('CSV 引號未閉合')
            raw = text[start:pos]
            value = raw[1:-1].replace('""', '"')
            if pos < len(text) and text[pos] not in delimiter+'\r\n': raise FileProcessingError('CSV 引號後內容不合法')
        else:
            while pos < len(text) and text[pos] not in delimiter+'\r\n': pos += 1
            value = text[start:pos]
        key = headers[column] if has_header and column < len(headers) else None
        if has_header and row_index == header_index: changed = value
        else: changed = transform.for_field(value,key) if callable(getattr(transform,'for_field',None)) else transform(value)
        if changed != value:
            if quoted or any(c in changed for c in delimiter+'"\r\n'):
                changed = '"'+changed.replace('"','""')+'"'
            edits.append((start, pos, changed))
        if pos < len(text) and text[pos] == delimiter: pos += 1; column += 1
    result = replace_spans(text, edits)
    try: list(csv.reader(io.StringIO(result, newline=''), delimiter=delimiter, strict=True))
    except csv.Error as exc: raise FileProcessingError('CSV 替換後格式不合法') from exc
    return FileResult(encode_text(result, encoding, bom), 'text/csv')


def _xml_decode(value):
    entities = {'amp':'&', 'lt':'<', 'gt':'>', 'quot':'"', 'apos':"'"}
    def replace(m):
        key = m[1]
        if key.startswith('#x'): return chr(int(key[2:],16))
        if key.startswith('#'): return chr(int(key[1:]))
        return entities[key]
    return re.sub(r'&(amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);', replace, value)


def validate_xml(content):
    from lxml import etree
    if re.search(br'<!\s*(DOCTYPE|ENTITY)', content, re.IGNORECASE): raise FileProcessingError('XML 不支援 DTD 或外部實體')
    try:
        root = etree.fromstring(content, parser=etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, strip_cdata=False))
        if root.getroottree().docinfo.doctype: raise FileProcessingError('XML 不支援 DTD 或外部實體')
        return root
    except (etree.XMLSyntaxError, ValueError) as exc: raise FileProcessingError('XML 格式不合法') from exc


def transform_xml(content, transform, encoding):
    text, encoding, bom = decode_text(content, encoding)
    # Unicode validation bypasses a Big5 encoding name unsupported by some libxml builds.
    declaration = re.match(r'\s*<\?xml[^?]*\?>', text)
    validation_text = re.sub(r'encoding\s*=\s*(["\']).*?\1', 'encoding="UTF-8"', text, count=1) if declaration else text
    validate_xml(validation_text.encode('utf-8'))
    edits = []
    parents = []
    def field_value(value,key):
        return transform.for_field(value,key) if callable(getattr(transform,'for_field',None)) else transform(value)
    for token in XML_TOKEN.finditer(text):
        raw = token.group()
        if raw.startswith(('<!--', '<?')): continue
        if raw.startswith('<![CDATA['):
            value = raw[9:-3]
            changed = field_value(value,parents[-1] if parents else None)
            if changed != value: edits.append((token.start(), token.end(), '<![CDATA['+changed.replace(']]>', ']]]]><![CDATA[>')+']]>'))
        elif raw.startswith('<'):
            for attr in XML_ATTR.finditer(raw):
                attr_name = attr[1].strip().split('=', 1)[0].strip()
                if attr_name == 'xmlns' or attr_name.startswith('xmlns:'): continue
                value = _xml_decode(attr[3])
                changed = field_value(value,attr_name.split(':')[-1])
                if changed != value:
                    escaped = escape(changed, {'"':'&quot;', "'":'&apos;'})
                    edits.append((token.start()+attr.start(3), token.start()+attr.end(3), escaped))
            if raw.startswith('</'):
                if parents: parents.pop()
            elif not raw.endswith('/>'):
                name = re.match(r'<\s*([^\s/>]+)',raw)
                if name: parents.append(name[1].split(':')[-1])
        else:
            value = _xml_decode(raw)
            changed = field_value(value,parents[-1] if parents else None)
            if changed != value: edits.append((token.start(), token.end(), escape(changed)))
    result = replace_spans(text, edits)
    check = re.sub(r'encoding\s*=\s*(["\']).*?\1', 'encoding="UTF-8"', result, count=1) if declaration else result
    validate_xml(check.encode('utf-8'))
    return FileResult(encode_text(result, encoding, bom), 'application/xml')
