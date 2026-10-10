import base64
from copy import deepcopy
from pathlib import Path
import pytest
import yaml
from fastapi.testclient import TestClient
from web import create_app


@pytest.fixture
def settings_app(tmp_path):
    path = tmp_path/'rules.yaml'
    path.write_text('''version: 1
custom_option:
  preserve: yes
ner:
  enabled: false
  model_name: custom-model
  device: -1
  score: 0.73
  chunk_size: 200
  overlap: 30
  mapping: {PERSON: PERSON}
rules:
  - name: 指定姓名
    entity: PERSON
    deny_list: [王小明]
    custom_field: preserved
''')
    with TestClient(create_app(path)) as client: yield client,path


def test_settings_read_includes_all_fields_and_form_choices(settings_app):
    client,path = settings_app
    r = client.get('/api/privacy-settings')
    assert r.status_code == 200
    d = r.json()
    assert d['config']['rules'][0]['custom_field'] == 'preserved'
    assert d['config']['ner']['score'] == .73
    assert d['revision']
    assert {'national-id','mobile','tax-id','email','names','keywords'}.issubset({t['id'] for t in d['templates']})
    assert [v['value'] for v in d['validators']] == ['', 'tw_id', 'tw_tax_id']


def test_save_persists_backup_and_immediate_effect(settings_app):
    client,path = settings_app
    initial = path.read_bytes()
    d = client.get('/api/privacy-settings').json()
    d['config']['rules'][0]['deny_list'] = ['李小華']
    r = client.post('/api/privacy-settings',json={'config':d['config'],'revision':d['revision']})
    assert r.status_code == 200,r.text
    assert r.json()['revision'] != d['revision']
    cfg = yaml.safe_load(path.read_text())
    assert cfg['rules'][0]['deny_list'] == ['李小華']
    assert cfg['rules'][0]['custom_field'] == 'preserved'
    assert cfg['custom_option'] == {'preserve':True}
    assert path.with_suffix('.yaml.bak').read_bytes() == initial
    response = client.post('/api/anonymize',data={'text':'王小明找李小華'})
    assert response.status_code == 200
    assert response.json()['preview'].startswith('王小明找[[PERSON_')
    # New app instance reads the saved config too.
    with TestClient(create_app(path)) as again:
        assert again.get('/api/privacy-settings').json()['config']['rules'][0]['deny_list'] == ['李小華']


def test_test_draft_does_not_save_or_apply(settings_app):
    client,path = settings_app
    before = path.read_bytes()
    draft = client.get('/api/privacy-settings').json()['config']
    draft['rules'][0]['deny_list'] = ['李小華']
    r = client.post('/api/privacy-settings/test',json={'config':draft,'text':'王小明與李小華'})
    assert r.status_code == 200,r.text
    assert [m['text'] for m in r.json()['matches']] == ['李小華']
    assert r.json()['preview'].startswith('王小明與[[PERSON_')
    assert path.read_bytes() == before
    assert client.post('/api/anonymize',data={'text':'王小明與李小華'}).json()['preview'].endswith('與李小華')


def test_removing_custom_rule_and_exclusions_applies_to_next_anonymize(settings_app):
    client, path = settings_app
    state = client.get('/api/privacy-settings').json()
    state['config']['rules'].append({'name':'自訂格式規則', 'entity':'CUSTOM_TEST', 'deny_list':['DEMO']})
    state['config']['exclusions'] = [{'entity':'PERSON','words':['王小明']}]
    saved = client.post('/api/privacy-settings', json={'config':state['config'],'revision':state['revision']})
    assert saved.status_code == 200
    before = client.post('/api/anonymize', data={'text':'王小明 DEMO'}).json()
    assert before['preview'].startswith('王小明 [[CUSTOM_TEST_')
    state = saved.json()
    state['config']['rules'] = [r for r in state['config']['rules'] if r['entity'] != 'CUSTOM_TEST']
    state['config']['exclusions'] = []
    saved = client.post('/api/privacy-settings', json={'config':state['config'],'revision':state['revision']})
    assert saved.status_code == 200
    after = client.post('/api/anonymize', data={'text':'王小明 DEMO'}).json()
    assert after['preview'].startswith('[[PERSON_')
    assert after['preview'].endswith(' DEMO')
    assert 'CUSTOM_TEST' not in client.get('/api/config').json()['entities']
    assert client.get('/api/privacy-settings').json()['config']['exclusions'] == []


@pytest.mark.parametrize('mutation',['bad-regex','bad-score','empty-list','bad-mapping','bad-type'])
def test_invalid_config_does_not_change_file_or_service(settings_app, mutation):
    client,path = settings_app
    d = client.get('/api/privacy-settings').json()
    before = path.read_bytes()
    rule = d['config']['rules'][0]
    if mutation == 'bad-regex': rule['patterns'] = [{'regex':'[','score':.9}]
    if mutation == 'bad-score': rule['deny_list_score'] = 99
    if mutation == 'empty-list': rule['deny_list'] = []
    if mutation == 'bad-mapping': d['config']['ner']['mapping'] = []
    if mutation == 'bad-type': d['config']['ner']['enabled'] = 'true'
    r = client.post('/api/privacy-settings',json={'config':d['config'],'revision':d['revision']})
    assert r.status_code == 400,r.text
    assert path.read_bytes() == before
    assert client.post('/api/anonymize',data={'text':'王小明'}).json()['report']['matched_count'] == 1


def test_stale_revision_and_external_changes_are_not_overwritten(settings_app):
    client,path = settings_app
    d = client.get('/api/privacy-settings').json()
    cfg = yaml.safe_load(path.read_text()); cfg['rules'][0]['deny_list'] = ['李小華']
    path.write_text(yaml.safe_dump(cfg,allow_unicode=True))
    changed = path.read_bytes()
    r = client.post('/api/privacy-settings',json={'config':d['config'],'revision':d['revision']})
    assert r.status_code == 409
    assert path.read_bytes() == changed
    latest = client.get('/api/privacy-settings').json()
    assert latest['config']['rules'][0]['deny_list'] == ['李小華']
    assert client.post('/api/anonymize',data={'text':'李小華'}).json()['report']['matched_count'] == 1


def test_cross_origin_write_and_preview_rejected(settings_app):
    client,path = settings_app
    d = client.get('/api/privacy-settings').json()
    for route in ['/api/privacy-settings','/api/privacy-settings/test']:
        assert client.post(route,json={'config':d['config'],'revision':d['revision'],'text':'王小明'},headers={'origin':'https://untrusted.example'}).status_code == 403
    assert client.post('/api/privacy-settings',json={'config':d['config'],'revision':d['revision']},headers={'origin':'http://testserver'}).status_code == 200


def test_save_failure_preserves_running_configuration(settings_app, monkeypatch):
    import pii_service.settings as settings
    client,path = settings_app
    d = client.get('/api/privacy-settings').json()
    before = path.read_bytes()
    d['config']['rules'][0]['deny_list'] = ['李小華']
    def fail(*args): raise OSError('disk unavailable')
    monkeypatch.setattr(settings.os, 'replace', fail)
    r = client.post('/api/privacy-settings',json={'config':d['config'],'revision':d['revision']})
    assert r.status_code == 400
    assert path.read_bytes() == before
    assert client.post('/api/anonymize',data={'text':'王小明'}).json()['report']['matched_count'] == 1


def test_disable_all_model_categories_is_valid(settings_app):
    client,path = settings_app
    d = client.get('/api/privacy-settings').json()
    d['config']['ner']['enabled'] = False
    d['config']['ner']['mapping'] = {}
    r = client.post('/api/privacy-settings',json={'config':d['config'],'revision':d['revision']})
    assert r.status_code == 200,r.text
    assert client.get('/api/config').json()['ner_enabled'] is False


def test_invalid_enabled_model_with_no_categories_rejected(settings_app):
    client,path = settings_app
    d = client.get('/api/privacy-settings').json()
    d['config']['ner']['enabled'] = True
    d['config']['ner']['mapping'] = {}
    assert client.post('/api/privacy-settings',json={'config':d['config'],'revision':d['revision']}).status_code == 400


def test_requests_hold_consistent_service_snapshot(settings_app):
    from pii_service.settings import SettingsManager
    client,path = settings_app
    manager = SettingsManager(path)
    cfg,old_service,rev = manager.snapshot()
    cfg['rules'][0]['deny_list'] = ['李小華']
    manager.save(cfg,rev)
    _,new_service,_ = manager.snapshot()
    assert old_service.analyze('王小明')[0].entity == 'PERSON'
    assert old_service.analyze('李小華') == []
    assert new_service.analyze('王小明') == []
    assert new_service.analyze('李小華')[0].entity == 'PERSON'
    assert new_service._ner_state is old_service._ner_state


def test_changed_model_draft_reuses_runtime_when_tested_and_saved(settings_app):
    from pii_service.settings import SettingsManager
    _,path = settings_app
    manager = SettingsManager(path)
    cfg,active,rev = manager.snapshot()
    cfg['ner']['model_name'] = 'another-model'
    first = manager.draft_service(cfg)
    marker = object()
    first.ner_driver = marker
    assert first._ner_state is not active._ner_state
    assert manager.draft_service(cfg).ner_driver is marker
    manager.save(cfg,rev)
    assert manager.snapshot()[1].ner_driver is marker
    cfg['ner']['device'] = 0
    assert manager.draft_service(cfg)._ner_state is not first._ner_state


def test_external_edit_during_staging_is_not_overwritten(settings_app, monkeypatch):
    import pii_service.settings as settings
    client,path = settings_app
    d = client.get('/api/privacy-settings').json()
    changed = path.read_bytes() + b'\n# concurrent edit\n'
    fsync = settings.os.fsync
    count = 0
    def edit_on_second_sync(fd):
        nonlocal count
        fsync(fd)
        count += 1
        if count == 2: path.write_bytes(changed)
    monkeypatch.setattr(settings.os,'fsync',edit_on_second_sync)
    r = client.post('/api/privacy-settings',json={'config':d['config'],'revision':d['revision']})
    assert r.status_code == 409
    assert path.read_bytes() == changed


def test_exclusion_draft_and_save_take_effect_without_mapping_excluded_text(settings_app):
    client,path = settings_app
    d = client.get('/api/privacy-settings').json()
    d['config']['rules'].append({'name':'keywords','entity':'CUSTOM','deny_list':['ACER','ASUS']})
    d['config']['exclusions'] = [{'entity':'*','words':['ACER']}]
    before = path.read_bytes()
    preview = client.post('/api/privacy-settings/test',json={'config':d['config'],'text':'王小明 ACER ASUS in acerd'}).json()
    assert [m['text'] for m in preview['matches']] == ['王小明','ASUS']
    assert path.read_bytes() == before
    saved = client.post('/api/privacy-settings',json={'config':d['config'],'revision':d['revision']})
    assert saved.status_code == 200
    result = client.post('/api/anonymize',data={'text':'ACER ASUS in acerd'}).json()
    assert result['preview'].startswith('ACER [[CUSTOM_') and result['preview'].endswith(' in acerd')
    import base64,json
    assert [entry['original'] for entry in json.loads(base64.b64decode(result['mapping']))['entries']] == ['ASUS']
