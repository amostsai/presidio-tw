"""Generate synthetic fixtures for manual rendering; no real PII is used."""
from pathlib import Path
import pymupdf
from tests.test_pdf_formats import pdf_sample, PdfMask
from file_adapters import transform_file
from restoration import MappingSession, load_mapping

root = Path('tmp/verification')
root.mkdir(parents=True, exist_ok=True)
source = pdf_sample()
s = MappingSession('sample.pdf')
masked = transform_file('sample.pdf', source, PdfMask(s)).content
restored = transform_file('sample.pdf', masked, load_mapping(s.dump()).restore).content
for name, data in [('original',source),('masked',masked),('restored',restored)]:
    (root/f'{name}.pdf').write_bytes(data)
    with pymupdf.open(stream=data, filetype='pdf') as doc:
        doc[0].get_pixmap(matrix=pymupdf.Matrix(2,2)).save(root/f'{name}.png')
print('Rendered synthetic original, masked, restored PDF pages to tmp/verification')
