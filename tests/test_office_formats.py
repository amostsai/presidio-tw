import io
import json
import zipfile
import pytest
from lxml import etree
from file_adapters import transform_file
from restoration import MappingSession, load_mapping
from tests.fixtures import docx_sample, xlsx_sample, package
from tests.test_text_formats import replacer


@pytest.mark.parametrize('ext,factory', [('docx', docx_sample), ('xlsx', xlsx_sample)])
def test_office_same_format_and_preserve_untouched_parts(ext, factory):
    source = factory()
    session = MappingSession('sample.'+ext)
    output = transform_file('sample.'+ext, source, replacer(session))
    token = json.loads(session.dump())['entries'][0]['token']
    restored = transform_file('ai.'+ext, output.content, load_mapping(session.dump()).restore)
    with zipfile.ZipFile(io.BytesIO(source)) as before, zipfile.ZipFile(io.BytesIO(output.content)) as after, zipfile.ZipFile(io.BytesIO(restored.content)) as recovered:
        assert after.namelist() == before.namelist()
        for name in before.namelist():
            if 'styles' in name or '/media/' in name:
                assert after.read(name) == before.read(name) == recovered.read(name)
            if name.endswith('.xml'):
                orig = etree.fromstring(before.read(name))
                masked = etree.fromstring(after.read(name))
                back = etree.fromstring(recovered.read(name))
                orig_text = ''.join(orig.itertext())
                masked_text = ''.join(masked.itertext())
                assert '王小明' not in masked_text
                if '王小明' in orig_text: assert token in masked_text
                assert ''.join(back.itertext()) == orig_text
        if ext == 'docx': assert etree.fromstring(after.read('word/document.xml')).xpath('count(//*[local-name()="b"])') == 1
        else:
            page = etree.fromstring(after.read('xl/worksheets/sheet1.xml'))
            assert page.xpath('string(//*[local-name()="f"])') == '1+1'
            assert page.xpath('string(//*[local-name()="col"]/@width)') == '20'
            assert page.xpath('string(//*[local-name()="mergeCell"]/@ref)') == 'A2:B2'


@pytest.mark.parametrize('data', [b'not-a-zip', package({'word/document.xml':'<x/>'}), package({'[Content_Types].xml':'<Types/>', 'vbaProject.bin': b'macro'})])
def test_invalid_office_rejected(data):
    with pytest.raises(ValueError): transform_file('x.docx', data, lambda s:s)


@pytest.mark.parametrize('ext',['docx','xlsx'])
def test_office_name_column_uses_header_for_every_row(ext):
    from pii_service import load_config,create_service,PiiTransform
    cfg = load_config(); cfg['ner']['enabled'] = False
    base = docx_sample() if ext == 'docx' else xlsx_sample()
    with zipfile.ZipFile(io.BytesIO(base)) as z: parts = {n:z.read(n) for n in z.namelist()}
    if ext == 'docx':
        rows = ''.join('<w:tr>'+''.join(f'<w:tc><w:p><w:r><w:t>{v}</w:t></w:r></w:p></w:tc>' for v in row)+'</w:tr>' for row in [('姓名','備註'),('陳建華','保留'),('Jane Doe','保留')])
        parts['word/document.xml'] = f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>{rows}</w:tbl></w:body></w:document>'
    else:
        parts['xl/sharedStrings.xml'] = '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>姓名</t></si><si><t>備註</t></si><si><t>陳建華</t></si><si><r><rPr><b/></rPr><t>Jane Doe</t></r></si><si><t>保留</t></si></sst>'
        parts['xl/worksheets/sheet1.xml'] = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>4</v></c></row><row r="3"><c r="A3" t="s" s="1"><v>3</v></c><c r="B3" t="s"><v>4</v></c></row></sheetData></worksheet>'
    source = package(parts); session = MappingSession('x.'+ext)
    out = transform_file('x.'+ext,source,PiiTransform(create_service(cfg),session))
    entries = json.loads(session.dump())['entries']
    assert [e['original'] for e in entries] == ['陳建華','Jane Doe']
    with zipfile.ZipFile(io.BytesIO(out.content)) as z:
        xml = z.read('word/document.xml' if ext=='docx' else 'xl/worksheets/sheet1.xml')
        assert all(e['token'].encode() in xml for e in entries)
        assert '陳建華'.encode() not in b''.join(z.read(n) for n in z.namelist() if n.endswith('.xml'))
        if ext == 'xlsx': assert etree.fromstring(xml).xpath('string(//*[local-name()="c"][@r="A3"]/@s)')=='1'
    restored = transform_file('x.'+ext,out.content,load_mapping(session.dump()).restore)
    with zipfile.ZipFile(io.BytesIO(restored.content)) as z:
        xml = z.read('word/document.xml' if ext=='docx' else 'xl/worksheets/sheet1.xml')
        assert all(e['original'].encode() in xml for e in entries)


def test_cross_run_ai_tokens_restore():
    source = docx_sample()
    session = MappingSession('sample.docx')
    transform_file('sample.docx', source, replacer(session))
    token = json.loads(session.dump())['entries'][0]['token']
    xml = f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{token[:10]}</w:t></w:r><w:r><w:t>{token[10:]}</w:t></w:r></w:p></w:body></w:document>'
    ai = package({'[Content_Types].xml':zipfile.ZipFile(io.BytesIO(source)).read('[Content_Types].xml'), 'word/document.xml':xml})
    out = transform_file('ai.docx', ai, load_mapping(session.dump()).restore)
    with zipfile.ZipFile(io.BytesIO(out.content)) as z:
        assert ''.join(etree.fromstring(z.read('word/document.xml')).itertext()) == '王小明'


@pytest.mark.parametrize('separator',['tab','br','cr'])
def test_docx_tabs_and_breaks_do_not_merge_phone_digits(separator):
    from pii_service import load_config, create_service, PiiTransform
    cfg = load_config(); cfg['ner']['enabled'] = False
    source = docx_sample()
    with zipfile.ZipFile(io.BytesIO(source)) as z: types = z.read('[Content_Types].xml')
    xml = f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>0912345678</w:t><w:{separator}/><w:t>42</w:t></w:r></w:p></w:body></w:document>'
    doc = package({'[Content_Types].xml':types, 'word/document.xml':xml})
    session = MappingSession('x.docx')
    out = transform_file('x.docx',doc,PiiTransform(create_service(cfg),session,['PHONE_NUMBER']))
    assert session.report()['matched_count'] == 1
    with zipfile.ZipFile(io.BytesIO(out.content)) as z:
        root = etree.fromstring(z.read('word/document.xml'))
        assert '0912345678' not in ''.join(root.itertext())
        assert root.xpath(f'count(//*[local-name()="{separator}"])') == 1
