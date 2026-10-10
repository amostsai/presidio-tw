import codecs
from .base import FileProcessingError, FileResult


def decode_text(content, encoding):
    if encoding not in ('utf-8', 'big5'): raise FileProcessingError('編碼只支援 UTF-8 或 Big5')
    bom = b''
    if content.startswith(codecs.BOM_UTF8):
        encoding, bom = 'utf-8', codecs.BOM_UTF8
        content = content[len(bom):]
    try:
        return content.decode(encoding), encoding, bom
    except UnicodeDecodeError as exc:
        raise FileProcessingError('無法解碼文字，請選擇正確的 UTF-8 或 Big5 編碼') from exc


def encode_text(text, encoding, bom):
    try: return bom + text.encode(encoding)
    except UnicodeEncodeError as exc: raise FileProcessingError('復原內容無法以原編碼表示，請改用 UTF-8') from exc


def transform_text(content, transform, encoding):
    text, encoding, bom = decode_text(content, encoding)
    # CSV samples are often saved as .txt; require a recognized multi-column header.
    import csv,io
    try:
        dialect = csv.Sniffer().sniff(text[:8192],delimiters=',;\t|')
        header = next(csv.reader(io.StringIO(text,newline=''),delimiter=dialect.delimiter),[])
        known = getattr(transform,'is_field_key',lambda key:False)
        if len(header)>1 and any(known(value) for value in header):
            from .structured import transform_csv
            result = transform_csv(content,transform,encoding)
            return FileResult(result.content,'text/plain',result.warnings)
    except csv.Error: pass
    return FileResult(encode_text(transform(text), encoding, bom), 'text/plain')
