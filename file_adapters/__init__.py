from pathlib import Path
from .base import BoundedTransform, FileProcessingError, FileResult, MAX_FILE_BYTES
from .text import transform_text
from .structured import transform_json, transform_csv, transform_xml

SUPPORTED = ('docx', 'xlsx', 'pdf', 'txt', 'csv', 'json', 'xml')


def transform_file(filename, content, transform, encoding='utf-8'):
    if len(content) > MAX_FILE_BYTES: raise FileProcessingError('檔案超過 10 MiB')
    if not content: raise FileProcessingError('檔案內容不可為空')
    suffix = Path(filename).suffix.lower().lstrip('.')
    bounded = BoundedTransform(transform)
    if suffix == 'txt': return transform_text(content, bounded, encoding)
    if suffix == 'json': return transform_json(content, bounded, encoding)
    if suffix == 'csv': return transform_csv(content, bounded, encoding)
    if suffix == 'xml': return transform_xml(content, bounded, encoding)
    if suffix in ('docx', 'xlsx'):
        from .office import transform_docx, transform_xlsx
        return (transform_docx if suffix == 'docx' else transform_xlsx)(content, bounded)
    if suffix == 'pdf':
        from .pdf import transform_pdf
        return transform_pdf(content, bounded)
    raise FileProcessingError('不支援此格式；請上傳 DOCX、XLSX、PDF、TXT、CSV、JSON 或 XML')
