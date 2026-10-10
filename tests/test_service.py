from pathlib import Path
import pytest
from pii_service import load_config, create_service


def config(tmp_path, extra=''):
    p = tmp_path / 'rules.yaml'
    p.write_text('''version: 1
ner:
  enabled: false
rules:
  - name: email
    entity: EMAIL
    patterns:
      - regex: '[a-z]+@[a-z]+\\.[a-z]+'
        score: 0.8
''' + extra)
    return p


def test_config_extension_without_code(tmp_path):
    s = create_service(load_config(config(tmp_path)))
    matches = s.analyze('聯絡 alice@example.com')
    assert [(m.entity, m.start, m.end) for m in matches] == [('EMAIL', 3, 20)]
    assert not s.analyze('聯絡 alice@example.com', entities=['PERSON'])


def test_disabled_rule(tmp_path):
    p = config(tmp_path)
    p.write_text(p.read_text().replace('name: email', 'name: email\n    enabled: false'))
    assert create_service(load_config(p)).analyze('alice@example.com') == []


@pytest.mark.parametrize('old,new', [("[a-z]+@[a-z]+\\.[a-z]+", '['), ('score: 0.8', 'score: 9'), ('entity: EMAIL', 'entity: EMAIL\n    validator: arbitrary_python')])
def test_invalid_settings(tmp_path, old, new):
    p = config(tmp_path)
    p.write_text(p.read_text().replace(old, new))
    with pytest.raises(ValueError):
        load_config(p)


def test_default_id_and_mobile():
    cfg = load_config(Path('config/rules.yaml'))
    cfg['ner']['enabled'] = False
    s = create_service(cfg)
    found = s.analyze('身分證A123456789，手機0912-345-678，錯誤A123456788')
    assert [(m.entity, '身分證A123456789，手機0912-345-678，錯誤A123456788'[m.start:m.end]) for m in found] == [('TW_NATIONAL_ID', 'A123456789'), ('PHONE_NUMBER', '0912-345-678'), ('TW_NATIONAL_ID', 'A123456788')]


def test_deny_list(tmp_path):
    p = config(tmp_path, '  - name: names\n    entity: PERSON\n    deny_list: [王小明, 李小華]\n')
    assert [m.entity for m in create_service(load_config(p)).analyze('王小明找李小華')] == ['PERSON', 'PERSON']


def test_transform_provides_complete_ranges(tmp_path):
    from pii_service import PiiTransform
    from restoration import MappingSession
    s = create_service(load_config(config(tmp_path)))
    session = MappingSession('x.txt')
    transform = PiiTransform(s, session)
    edits = transform.edits('alice@example.com')
    assert len(edits) == 1 and edits[0][:2] == (0,17)
    assert edits[0][2].startswith('[[EMAIL_')


def test_ckip_mapping_and_long_text(tmp_path):
    cfg = load_config(config(tmp_path))
    cfg['ner'].update(enabled=True, chunk_size=16, overlap=4, mapping={'PERSON':'PERSON'})
    service = create_service(cfg)
    from types import SimpleNamespace
    def driver(texts, **kwargs):
        return [[SimpleNamespace(ner='PERSON', idx=(t.index('王小明'), t.index('王小明')+3))] if '王小明' in t else [] for t in texts]
    service.ner_driver = driver
    matches = service.analyze('x'*14+'王小明'+'x'*30, ['PERSON'])
    assert [(m.start,m.end,m.entity) for m in matches] == [(14,17,'PERSON')]


def test_ner_only_config_without_rules(tmp_path):
    p = tmp_path/'rules.yaml'; p.write_text('version: 1\nner:\n  enabled: false\n')
    assert create_service(load_config(p)).analyze('test') == []


@pytest.mark.parametrize('text,expected', [('in acerd',[]),('XACER ACER1 _ACER',[]),('ACER acer (AcEr)', ['ACER','acer','AcEr']),('ACER產品與王小明找李小華',['ACER','王小明','李小華'])])
def test_dictionary_respects_english_word_boundaries(tmp_path,text,expected):
    cfg = load_config(config(tmp_path,'  - name: keywords\n    entity: CUSTOM\n    deny_list: [ACER, 王小明, 李小華]\n'))
    assert [text[m.start:m.end] for m in create_service(cfg).analyze(text)] == expected


def test_dictionary_substring_is_explicit_opt_in(tmp_path):
    cfg = load_config(config(tmp_path,'  - name: keywords\n    entity: CUSTOM\n    deny_list: [ACER]\n    deny_list_match: substring\n'))
    assert len(create_service(cfg).analyze('acerd')) == 1


def test_exclusions_override_dictionary_patterns_and_model(tmp_path):
    from types import SimpleNamespace
    cfg = load_config(config(tmp_path,'  - name: names\n    entity: PERSON\n    deny_list: [王小明, 李小華]\n'))
    cfg['ner'].update(enabled=True,mapping={'PERSON':'PERSON'})
    cfg['exclusions'] = [{'entity':'PERSON','words':['王小明']}, {'entity':'*','words':['ALICE@EXAMPLE.COM']}]
    service = create_service(cfg)
    service.ner_driver = lambda texts,**kwargs: [[SimpleNamespace(ner='PERSON',idx=(0,3))] for _ in texts]
    text = '王小明與李小華 alice@example.com bob@example.com'
    assert [text[m.start:m.end] for m in service.analyze(text)] == ['李小華','bob@example.com']
    cfg['exclusions'][0]['entity'] = 'EMAIL'
    service = create_service(cfg); service.ner_driver = lambda texts,**kwargs: [[] for _ in texts]
    assert service.analyze('王小明')


@pytest.mark.parametrize('extra', ['exclusions: [bad]', 'exclusions: [{entity: "*", words: [3]}]', 'exclusions: [{entity: invalid, words: []}]'])
def test_invalid_exclusions_rejected(tmp_path,extra):
    with pytest.raises(ValueError): load_config(config(tmp_path,extra+'\n'))


def test_invalid_dictionary_match_mode_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_config(config(tmp_path,'  - name: names\n    entity: PERSON\n    deny_list: [ACER]\n    deny_list_match: fuzzy\n'))
