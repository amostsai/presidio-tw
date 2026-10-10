import json
import pytest
from file_adapters import transform_file
from restoration import MappingSession, load_mapping
from pii_service import Match


def replacer(session):
    def apply(text):
        matches = []
        start = 0
        while (start := text.find('王小明', start)) >= 0:
            matches.append(Match('PERSON', start, start+3, .9))
            start += 3
        return session.replace(text, matches)
    return apply


@pytest.mark.parametrize('suffix,source', [
    ('txt', '姓名：王小明\r\n王小明\r\n'),
    ('csv', '姓名,說明\r\n"王小明","第一行\n王小明,你好"\r\n'),
    ('json', '{\n  "王小明" : "\\u738b小明", "n": 1.00, "ok": true\n}\n'),
    ('xml', '<?xml version="1.0" encoding="UTF-8"?>\n<r xmlns:x="urn:x"><x:p name="王小明"><![CDATA[王小明]]></x:p><!--keep--></r>'),
])
def test_same_format_roundtrip(suffix, source):
    s = MappingSession('sample.'+suffix)
    result = transform_file('sample.'+suffix, source.encode(), replacer(s))
    token = json.loads(s.dump())['entries'][0]['token']
    assert token.encode() in result.content
    if suffix != 'json': assert '王小明'.encode() not in result.content
    restored = transform_file('ai.'+suffix, result.content, load_mapping(s.dump()).restore)
    if suffix == 'json':
        assert list(json.loads(result.content)) == list(json.loads(source))
        assert json.loads(restored.content) == json.loads(source)
        assert b'1.00' in result.content
        assert b'\n  ' in result.content
    else:
        assert restored.content.decode() == source


@pytest.mark.parametrize('encoding,bom', [('big5', b''), ('utf-8', b'\xef\xbb\xbf')])
def test_encoding_and_crlf(encoding, bom):
    source = bom + '王小明\r\n第二行\r\n'.encode(encoding)
    s = MappingSession('text.txt')
    masked = transform_file('text.txt', source, replacer(s), encoding)
    assert transform_file('text.txt', masked.content, load_mapping(s.dump()).restore, encoding).content == source


@pytest.mark.parametrize('filename,data', [('bad.exe', b'x'), ('bad.json', b'{'), ('bad.xml', b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>')])
def test_reject_bad_inputs(filename,data):
    with pytest.raises(ValueError): transform_file(filename,data,lambda s:s)


def test_json_keys_are_never_sent_to_transform():
    source = b'{"name": "value", "id":1, "nested": {"address": "place"}}'
    seen = []
    result = transform_file('x.json',source,lambda s: seen.append(s) or 'MASK')
    assert seen == ['value','place']
    assert json.loads(result.content) == {'name':'MASK','id':1,'nested':{'address':'MASK'}}


def test_json_field_rules_mask_values_preserve_keys_layout_and_roundtrip():
    from pathlib import Path
    from pii_service import create_service,load_config,PiiTransform
    config = load_config(Path('config/rules.yaml'))
    config['ner']['enabled'] = False
    source = '{\r\n  "users": [{"id": 1.00, "name": "李小華", "gender": "M", "address": "100011 臺北市中正區重慶南路一段122號", "id_number": "B223456781"}]\r\n}\r\n'
    session = MappingSession('x.json')
    result = transform_file('x.json', source.encode(), PiiTransform(create_service(config),session))
    masked = json.loads(result.content)['users'][0]
    assert list(masked) == ['id','name','gender','address','id_number']
    assert masked['name'].startswith('[[PERSON_')
    assert masked['address'].startswith('[[LOCATION_') and masked['address'].endswith(']]')
    assert masked['id_number'].startswith('[[TW_NATIONAL_ID_')
    assert masked['gender'] == 'M'
    assert b'1.00' in result.content and b'\r\n  ' in result.content
    assert transform_file('x.json',result.content,load_mapping(session.dump()).restore).content == source.encode()


def test_json_nested_arrays_pass_correct_field_context_without_touching_keys():
    class Fields:
        def __call__(self,text): return text
        def for_field(self,text,key): return (key or 'root') + ':' + text
    source = b'{"na\\u006de":["A",["B"],{"other":"C"}],"next":"D"}'
    result = transform_file('x.json',source,Fields())
    assert json.loads(result.content) == {'name':['name:A',['name:B'],{'other':'other:C'}],'next':'next:D'}
    assert b'"na\\u006de"' in result.content


@pytest.mark.parametrize('suffix,delimiter', [('csv',','),('csv',';'),('csv','\t'),('txt',',')])
def test_csv_name_column_masks_every_row_and_keeps_headers(suffix,delimiter):
    import csv,io
    from pathlib import Path
    from pii_service import create_service,load_config,PiiTransform
    cfg = load_config(Path('config/rules.yaml')); cfg['ner']['enabled'] = False
    source = delimiter.join(['"姓名"','"備註"'])+'\r\n'+delimiter.join(['"陳建華"','"第一行\n第二行"'])+'\r\n'+delimiter.join(['"Jane Doe"','"保留"'])+'\r\n'
    session = MappingSession('x.'+suffix)
    result = transform_file('x.'+suffix,source.encode(),PiiTransform(create_service(cfg),session))
    rows = list(csv.reader(io.StringIO(result.content.decode(),newline=''),delimiter=delimiter))
    assert rows[0] == ['姓名','備註']
    assert all(row[0].startswith('[[PERSON_') for row in rows[1:])
    assert rows[1][1] == '第一行\n第二行' and rows[2][1] == '保留'
    assert transform_file('x.'+suffix,result.content,load_mapping(session.dump()).restore).content == source.encode()


def test_headerless_mixed_type_csv_does_not_skip_first_sensitive_row():
    source = '王小明,foo\n0912345678,1\n0987654321,2\n'.encode()
    session = MappingSession('x.csv')
    result = transform_file('x.csv',source,replacer(session))
    assert json.loads(session.dump())['entries'][0]['original'] == '王小明'
    assert result.content.startswith(b'[[PERSON_')


def test_xml_name_and_address_fields_use_tag_and_attribute_names():
    from pathlib import Path
    from pii_service import create_service,load_config,PiiTransform
    from lxml import etree
    cfg = load_config(Path('config/rules.yaml')); cfg['ner']['enabled'] = False
    source = '<users><user name="Jane Doe"><name><![CDATA[陳建華]]></name><address>測試地址五段99號</address></user></users>'.encode()
    session = MappingSession('x.xml')
    result = transform_file('x.xml',source,PiiTransform(create_service(cfg),session))
    user = etree.fromstring(result.content)[0]
    assert user.get('name').startswith('[[PERSON_')
    assert user.find('name').text.startswith('[[PERSON_')
    assert user.find('address').text.startswith('[[LOCATION_')
    assert transform_file('x.xml',result.content,load_mapping(session.dump()).restore).content == source


def test_xml_special_characters_are_escaped():
    out = transform_file('x.xml', b'<r a="token">token</r>', lambda s:'A&B<"' if s=='token' else s)
    from lxml import etree
    root = etree.fromstring(out.content)
    assert root.text == root.get('a') == 'A&B<"'


def test_big5_unencodable_restore_rejected():
    with pytest.raises(ValueError): transform_file('x.txt', b'hello', lambda s:'😀', 'big5')


def test_xml_amp_escaped_numeric_entity_decodes_once():
    out = transform_file('x.xml',b'<r>&amp;#65;</r>',lambda t:t.replace('&#65;','CHANGED'))
    from lxml import etree
    assert etree.fromstring(out.content).text == 'CHANGED'


def test_xml_namespace_attributes_are_structural():
    out = transform_file('x.xml',b'<r xmlns:x="urn:alice@example.com"><x:p a="alice@example.com"/></r>',lambda t:t.replace('alice@example.com','MASK'))
    from lxml import etree
    root = etree.fromstring(out.content)
    assert root.nsmap['x'] == 'urn:alice@example.com'
    assert root[0].get('a') == 'MASK'
