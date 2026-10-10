from pathlib import Path
import yaml
from pii_service import create_service
import pytest

ADDRESSES = [
    '臺北市中正區重慶南路一段122號',
    '臺中市西屯區臺灣大道三段99號',
    '臺南市安平區永華路二段6號',
    '高雄市苓雅區四維三路2號',
    '新北市板橋區中山路一段161號',
]


def template_service(template_id):
    templates = yaml.safe_load(Path('config/rule_templates.yaml').read_text())['templates']
    rule = next(t['rule'] for t in templates if t['id'] == template_id)
    return create_service({'rules':[rule], 'ner':{'enabled':False}, 'exclusions':[]})


def test_name_field_masks_value_without_model_or_hardcoded_name():
    service = template_service('name-field')
    for name in ['李小華','歐陽小明']:
        text = f'【紀錄 1】\r\n姓名：{name}\r\n其他欄位：保留\r\n'
        matches = service.analyze(text)
        assert [(m.entity,text[m.start:m.end]) for m in matches] == [('PERSON',name)]
    assert service.analyze('姓名：\n其他欄位：保留') == []
    assert service.analyze('這段文字沒有姓名欄位') == []


def test_address_field_masks_full_value_including_postcode_and_house_number():
    service = template_service('address-field')
    address = '100011 臺北市中正區重慶南路一段122號'
    text = f'通訊地址：{address}\n其他欄位：保留'
    matches = service.analyze(text)
    assert [(m.entity,text[m.start:m.end]) for m in matches] == [('LOCATION',address)]
    assert service.analyze('通訊地址：\n其他欄位：保留') == []


def test_default_national_id_template_masks_format_even_with_invalid_checksum():
    service = template_service('national-id')
    text = '身分證字號：A123456789 B223456781 D123456787 E223456788 F123456785'
    assert [text[m.start:m.end] for m in service.analyze(text)] == [
        'A123456789','B223456781','D123456787','E223456788','F123456785']
    assert service.entities == ['TW_NATIONAL_ID']


def test_default_config_has_enabled_national_id_without_checksum_gate():
    cfg = yaml.safe_load(Path('config/rules.yaml').read_text())
    rule = next(r for r in cfg['rules'] if r['entity'] == 'TW_NATIONAL_ID')
    assert rule.get('enabled', True)
    assert not rule.get('validator')


@pytest.mark.parametrize('address',ADDRESSES)
def test_complete_address_matches_without_field_label(address):
    service = template_service('address-field')
    text = '請寄到' + address + '，謝謝。'
    assert [(m.entity,text[m.start:m.end]) for m in service.analyze(text)] == [('LOCATION',address)]


def test_address_includes_postcode_lane_alley_house_and_floor_without_extra_sentence():
    service = template_service('address-field')
    address = '100011 臺北市中正區重慶南路一段12巷3弄122之2號3樓'
    text = '地址為' + address + '。電話另行提供。'
    assert [text[m.start:m.end] for m in service.analyze(text)] == [address]


def test_generic_json_array_masks_each_full_address_with_one_restorable_token():
    import json
    from file_adapters import transform_file
    from pii_service import PiiTransform
    from restoration import MappingSession,load_mapping
    session = MappingSession('addresses.json')
    source = json.dumps({'notes':ADDRESSES},ensure_ascii=False).encode()
    result = transform_file('addresses.json',source,PiiTransform(template_service('address-field'),session))
    values = json.loads(result.content)['notes']
    assert all(value.startswith('[[LOCATION_') and value.endswith(']]') and value.count('[[')==1 for value in values)
    assert [e['original'] for e in json.loads(session.dump())['entries']] == ADDRESSES
    assert json.loads(transform_file('addresses.json',result.content,load_mapping(session.dump()).restore).content) == json.loads(source)
