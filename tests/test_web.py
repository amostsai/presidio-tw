import base64
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from web import create_app
from tests.fixtures import docx_sample, xlsx_sample
from tests.test_pdf_formats import pdf_sample


@pytest.fixture
def client(tmp_path):
    p = tmp_path/'rules.yaml'
    p.write_text('''version: 1
ner:
  enabled: false
rules:
  - name: names
    entity: PERSON
    deny_list: [王小明, 李小華]
  - name: id
    entity: TW_NATIONAL_ID
    patterns:
      - regex: 'A[0-9]{9}'
        score: 0.9
''')
    with TestClient(create_app(p)) as c: yield c


@pytest.mark.parametrize('ext,data', [('txt','王小明'.encode()), ('csv','姓名\n王小明\n'.encode()), ('json','{"姓名":"王小明"}'.encode()), ('xml','<r>王小明</r>'.encode()), ('docx',docx_sample()), ('xlsx',xlsx_sample()), ('pdf',pdf_sample())])
def test_every_format_anonymize_restore(client, ext,data):
    r = client.post('/api/anonymize',files={'file':('sample.'+ext,data)},data={'entities':['PERSON','TW_NATIONAL_ID']})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['filename'].endswith('.'+ext)
    mapping = base64.b64decode(d['mapping'])
    masked = base64.b64decode(d['content'])
    assert d['report']['matched_count'] >= 1
    r = client.post('/api/restore',files={'file':('ai.'+ext,masked), 'mapping':('sample.mapping.json',mapping)})
    assert r.status_code == 200, r.text
    assert r.json()['filename'].endswith('.'+ext)
    assert r.json()['report']['restored_count'] >= 1


def test_ai_reordered_text_and_unknown_token(client):
    d = client.post('/api/anonymize',data={'text':'王小明與李小華'}).json()
    mapping = base64.b64decode(d['mapping'])
    a,b = [e['token'] for e in json.loads(mapping)['entries']]
    unknown = '[[PERSON_deadbeef_9999]]'
    r = client.post('/api/restore',data={'text':f'{b}與{a}、{a} {unknown}'},files={'mapping':('mapping.json',mapping)})
    assert r.status_code == 200
    assert r.json()['preview'] == f'李小華與王小明、王小明 {unknown}'
    assert r.json()['report']['restored_count'] == 3
    assert r.json()['report']['unresolved_tokens'] == [unknown]


def test_validation_and_config(client):
    page = client.get('/')
    assert page.status_code == 200
    assert 'rel="noopener noreferrer">學創科技有限公司</a>' in page.text
    assert '>metalearning.tw</a>' not in page.text
    assert client.get('/api/config').json()['entities'] == ['PERSON','TW_NATIONAL_ID']
    assert client.post('/api/anonymize',data={}).status_code == 400
    assert client.post('/api/anonymize',data={'text':'name'},files={'file':('x.txt',b'x')}).status_code == 400
    assert client.post('/api/anonymize',files={'file':('x.exe',b'x')}).status_code == 400
    assert client.post('/api/restore',data={'text':'x'},files={'mapping':('x.json',b'{}')}).status_code == 400


def test_limits_and_html_literal(client):
    assert client.post('/api/anonymize',files={'file':('x.txt',b'x'*(10*1024*1024+1))}).status_code == 413
    assert client.post('/api/anonymize',content=b'x'*(21*1024*1024+1),headers={'content-type':'application/octet-stream'}).status_code == 413
    literal = '<img src=x onerror=alert(1)>王小明'
    d = client.post('/api/anonymize',data={'text':literal}).json()
    assert '<img src=x onerror=alert(1)>' in d['preview']
    assert '王小明' not in d['preview']
    assert 'original' not in d['report']


def test_request_isolation(client):
    def run(text): return client.post('/api/anonymize',data={'text':text}).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        ds = list(pool.map(run,['王小明','李小華']))
    maps = [json.loads(base64.b64decode(d['mapping'])) for d in ds]
    assert maps[0]['session_id'] != maps[1]['session_id']
    assert [m['entries'][0]['original'] for m in maps] == ['王小明','李小華']
