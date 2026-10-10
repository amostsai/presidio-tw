import json
import pytest
from pii_service import Match
from restoration import MappingSession, load_mapping


def test_stable_unique_tokens_and_ai_reordering():
    session = MappingSession('names.txt')
    masked = session.replace('王小明與李小華、王小明', [Match('PERSON', 0, 3, .9), Match('PERSON', 4, 7, .9), Match('PERSON', 8, 11, .9)])
    mapping = json.loads(session.dump())
    a, b = [e['token'] for e in mapping['entries']]
    assert masked == f'{a}與{b}、{a}'
    restored = load_mapping(session.dump())
    assert restored.restore(f'{b}回覆{a}：{a}') == '李小華回覆王小明：王小明'
    assert restored.report()['restored_count'] == 3


def test_restore_is_single_pass():
    s = MappingSession('text.txt')
    literal = '[[PERSON_01234567_0001]]'
    token = s.replace(literal, [Match('PERSON', 0, len(literal), .9)])
    assert token != literal
    assert load_mapping(s.dump()).restore(token) == literal


def test_unknown_tokens_and_no_guessing():
    s = MappingSession('text.txt')
    s.replace('王小明', [Match('PERSON', 0, 3, .9)])
    m = load_mapping(s.dump())
    other = '[[PERSON_deadbeef_0099]]'
    assert m.restore(other) == other
    assert m.report()['unresolved_tokens'] == [other]


@pytest.mark.parametrize('mutation', ['duplicate', 'version', 'token', 'missing'])
def test_reject_invalid_mapping(mutation):
    s = MappingSession('text.txt')
    s.replace('王小明', [Match('PERSON', 0, 3, .9)])
    d = json.loads(s.dump())
    if mutation == 'duplicate': d['entries'].append(dict(d['entries'][0], original='李小華'))
    if mutation == 'version': d['version'] = 99
    if mutation == 'token': d['entries'][0]['token'] = '王'
    if mutation == 'missing': del d['entries'][0]['original']
    with pytest.raises(ValueError): load_mapping(json.dumps(d).encode())


def test_reject_duplicate_json_keys():
    with pytest.raises(ValueError): load_mapping(b'{"version":1,"version":1}')


def test_pdf_compact_tokens_keep_entity_and_restore_ai_text():
    session = MappingSession('table.PDF')
    token = session.replace('王小明', [Match('PERSON', 0, 3, .9)])
    data = json.loads(session.dump())
    assert token == f'[[P_{session.session_id}_0001]]'
    assert data['version'] == 2
    assert data['entries'][0]['entity'] == 'PERSON'
    assert load_mapping(session.dump()).restore(f'{token}回覆：{token}') == '王小明回覆：王小明'
    data['entries'][0]['token'] = f'[[PERSON_{session.session_id}_0001]]'
    with pytest.raises(ValueError): load_mapping(json.dumps(data).encode())
