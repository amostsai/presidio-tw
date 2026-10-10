import json
import pymupdf
import pytest
from pathlib import Path
from file_adapters import transform_file
from restoration import MappingSession, load_mapping
from pii_service import Match


def pdf_sample(rotation=0):
    doc = pymupdf.open()
    p = doc.new_page(width=500, height=300)
    p.insert_text((30, 40), 'TITLE - unchanged', fontsize=14)
    p.insert_text((30, 90), '王小明', fontname='china-t', fontsize=12)
    p.insert_text((30, 140), 'A123456789', fontsize=12)
    p.insert_text((30, 190), 'KEEP 42', fontsize=12)
    p.set_rotation(rotation)
    return doc.tobytes()


class PdfMask:
    def __init__(self, session): self.session = session
    def edits(self,text):
        edits = []
        for entity,value in [('PERSON','王小明'),('TW_NATIONAL_ID','A123456789')]:
            start = text.find(value)
            if start >= 0:
                replacement = self.session.replace(value,[Match(entity,0,len(value),.9)])
                edits.append((start,start+len(value),replacement))
        return sorted(edits)
    def __call__(self,text):
        for a,b,v in reversed(self.edits(text)): text = text[:a]+v+text[b:]
        return text


@pytest.mark.parametrize('rotation',[0,90])
def test_pdf_real_removal_restore_and_page_size(rotation):
    source = pdf_sample(rotation)
    s = MappingSession('sample.pdf')
    masked = transform_file('sample.pdf',source,PdfMask(s))
    tokens = [e['token'] for e in json.loads(s.dump())['entries']]
    with pymupdf.open(stream=masked.content,filetype='pdf') as doc:
        text = ''.join(p.get_text() for p in doc)
        assert '王小明' not in text and 'A123456789' not in text
        assert all(t in text for t in tokens)
        assert 'TITLE - unchanged' in text and 'KEEP 42' in text
        assert doc[0].rotation == rotation
        assert doc[0].mediabox.width == 500
    result = transform_file('ai.pdf',masked.content,load_mapping(s.dump()).restore)
    with pymupdf.open(stream=result.content,filetype='pdf') as doc:
        text = ''.join(p.get_text() for p in doc)
        assert '王小明' in text and 'A123456789' in text
        assert 'KEEP 42' in text
        assert not any(t in text for t in tokens)


def test_reject_scan_pdf():
    doc = pymupdf.open(); doc.new_page()
    with pytest.raises(ValueError,match='OCR|文字層'): transform_file('scan.pdf',doc.tobytes(),lambda x:x)


def test_pdf_impossible_fit_rejected():
    doc = pymupdf.open(); p = doc.new_page(width=100,height=100)
    p.insert_text((40,40),'王小明',fontname='china-t',fontsize=8)
    p.insert_text((64,40),'KEEP',fontsize=8)
    s = MappingSession('small.pdf')
    with pytest.raises(ValueError,match='容納|空間'): transform_file('small.pdf',doc.tobytes(),PdfMask(s))


def test_invalid_pdf_rejected():
    with pytest.raises(ValueError): transform_file('bad.pdf',b'bad',lambda x:x)


def test_pdf_rejects_redaction_that_would_delete_neighbor():
    doc = pymupdf.open(); page = doc.new_page(width=500,height=300)
    page.insert_text((30,90),'A123456789',fontsize=12)
    page.insert_text((30,95),'KEEP',fontsize=6)
    with pytest.raises(ValueError,match='相鄰|鄰近'):
        transform_file('close.pdf',doc.tobytes(),PdfMask(MappingSession('close.pdf')))


def test_narrow_pdf_table_masks_full_fields_and_wrapped_address():
    from pii_service import load_config, create_service, PiiTransform
    source = Path('tests/ddd/臺灣測試資料標準範本 (PDF).pdf').read_bytes()
    config = load_config()
    config['ner']['enabled'] = False
    session = MappingSession('table.pdf')
    masked = transform_file('table.pdf', source, PiiTransform(create_service(config), session))
    entries = json.loads(session.dump())['entries']
    assert session.report()['entities'] == {'PERSON':5, 'TW_NATIONAL_ID':5, 'PHONE_NUMBER':5, 'LOCATION':5}
    assert any(e['original'] == '100011 臺北市中正區重慶南路一段122號' for e in entries)
    with pymupdf.open(stream=masked.content, filetype='pdf') as doc:
        text = doc[0].get_text()
        assert all(e['token'] in text and e['original'] not in text for e in entries)
        assert '重慶南路' not in text and '122' not in text
        assert all(h in text for h in ['姓名','身分證編號','通訊地址'])
        assert all(s['size'] >= 5 for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans'])
    mapping = load_mapping(session.dump())
    restored = transform_file('reply.pdf', masked.content, mapping.restore)
    with pymupdf.open(stream=restored.content, filetype='pdf') as doc:
        text = doc[0].get_text()
        assert all(e['original'] in text and e['token'] not in text for e in entries)
    assert mapping.report()['restored_count'] == 20


def test_pdf_inline_token_can_rewrite_line_without_clipping_suffix():
    doc = pymupdf.open(); page = doc.new_page(width=500, height=200)
    page.insert_text((30,60), '姓名：王小明，備註：保留', fontname='china-t', fontsize=10)
    session = MappingSession('inline.pdf')
    masked = transform_file('inline.pdf', doc.tobytes(), PdfMask(session))
    token = json.loads(session.dump())['entries'][0]['token']
    with pymupdf.open(stream=masked.content, filetype='pdf') as result:
        assert f'姓名：{token}，備註：保留' in result[0].get_text()
        assert '王小明' not in result[0].get_text()
    restored = transform_file('inline.pdf', masked.content, load_mapping(session.dump()).restore)
    with pymupdf.open(stream=restored.content, filetype='pdf') as result:
        text = result[0].get_text()
        assert all(part in text for part in ['姓名：','王小明','，備註：保留'])
        assert token not in text
        name = result[0].search_for('王小明')[0]
        suffix = result[0].search_for('，備註：保留')[0]
        assert name.x1 <= suffix.x0


def test_pdf_restore_mixed_chinese_address_stays_inside_page():
    address = '100011 臺北市中正區重慶南路一段122號'
    session = MappingSession('address.pdf')
    token = session.replace(address, [Match('LOCATION',0,len(address),1)])
    doc = pymupdf.open(); page = doc.new_page(width=500,height=200)
    page.insert_text((300,60), token, fontsize=9)
    result = transform_file('reply.pdf', doc.tobytes(), load_mapping(session.dump()).restore)
    with pymupdf.open(stream=result.content, filetype='pdf') as output:
        assert address in output[0].get_text()
        for b in output[0].get_text('dict')['blocks']:
            if b['type']==0: assert b['bbox'][2] <= 490.1


def test_pdf_restore_accented_name_does_not_overlap_letters():
    name = 'Émilie'
    session = MappingSession('name.pdf')
    token = session.replace(name,[Match('PERSON',0,len(name),1)])
    doc = pymupdf.open(); page = doc.new_page()
    page.insert_text((30,60),token,fontsize=10)
    result = transform_file('reply.pdf',doc.tobytes(),load_mapping(session.dump()).restore)
    with pymupdf.open(stream=result.content,filetype='pdf') as output:
        assert name in output[0].get_text()
        chars = [c for b in output[0].get_text('rawdict')['blocks'] if b['type']==0
                 for l in b['lines'] for s in l['spans'] for c in s['chars']]
        assert all(a['bbox'][2] <= b['bbox'][0]+.01 for a,b in zip(chars,chars[1:]))


@pytest.mark.parametrize('horizontal',[False,True])
def test_pdf_form_labels_never_skip_sensitive_values(horizontal):
    from pii_service import load_config,create_service,PiiTransform
    cfg = load_config(); cfg['ner']['enabled'] = False
    doc = pymupdf.open(); page = doc.new_page(width=600,height=300)
    values = ['姓名','王小明','身分證','A123456789']
    if horizontal:
        for x,value in zip([30,130,230,330],values):
            page.insert_text((x,60),value,fontname='china-t',fontsize=12)
    else:
        page.insert_text((30,40),'\n'.join(values),fontname='china-t',fontsize=12)
    session = MappingSession('form.pdf')
    result = transform_file('form.pdf',doc.tobytes(),PiiTransform(create_service(cfg),session))
    with pymupdf.open(stream=result.content,filetype='pdf') as output:
        assert 'A123456789' not in output[0].get_text()
        assert all(label in output[0].get_text() for label in ['姓名','身分證'])
    assert session.report()['entities']['TW_NATIONAL_ID'] == 1
