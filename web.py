"""Local Web workspace. Results and mappings never enter a shared server cache."""
import base64
import os
from pathlib import Path
import re
from fastapi import Request
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pii_service import DEFAULT_CONFIG, PiiTransform
from pii_service.settings import SettingsManager, SettingsConflict, form_choices
from restoration import MappingSession, load_mapping, MAX_MAPPING_BYTES
from file_adapters import transform_file, SUPPORTED
from file_adapters.base import MAX_FILE_BYTES
from file_adapters.text import decode_text

ROOT = Path(__file__).resolve().parent
MAX_BODY_BYTES = 21 * 1024 * 1024


class BodyLimitMiddleware:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in ('POST','PUT','PATCH'):
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try: declared = int(headers.get(b'content-length', b'0'))
        except ValueError: declared = MAX_BODY_BYTES+1
        if declared > MAX_BODY_BYTES:
            return await JSONResponse({'detail':'上傳總量超過 21 MiB'}, status_code=413)(scope, receive, send)
        chunks, total = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect': return
            chunk = message.get('body', b'')
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                return await JSONResponse({'detail':'上傳總量超過 21 MiB'}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body'): break
        body = b''.join(chunks)
        chunks.clear()
        sent = False
        async def replay():
            nonlocal sent, body
            if not sent:
                sent = True
                output = body
                body = b''
                return {'type':'http.request', 'body':output, 'more_body':False}
            return await receive()
        return await self.app(scope, replay, send)


def safe_filename(filename):
    filename = (filename or 'document.txt').replace('\\','/').split('/')[-1]
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)[:160]
    return filename if filename and filename not in ('.','..') else 'document.txt'


def _encoded(content): return base64.b64encode(content).decode('ascii')


def _result(filename, result, report, encoding):
    suffix = Path(filename).suffix.lower().lstrip('.')
    preview = ''
    if suffix in ('txt','csv','json','xml'):
        preview,_,_ = decode_text(result.content, encoding)
    return {'filename':filename, 'media_type':result.media_type, 'content':_encoded(result.content), 'preview':preview[:100_000], 'preview_truncated':len(preview)>100_000, 'report':report, 'warnings':result.warnings}


async def _source(file, text, encoding):
    has_text = text is not None and bool(text.strip())
    has_file = file is not None and bool(file.filename)
    if has_text == has_file: raise HTTPException(400, '請擇一上傳檔案或貼上非空白文字')
    if has_file:
        filename = safe_filename(file.filename)
        content = await file.read(MAX_FILE_BYTES+1)
    else:
        filename = 'text.txt'
        try: content = text.encode(encoding)
        except (UnicodeEncodeError, LookupError) as exc: raise HTTPException(400, '文字無法以選定編碼表示，請選 UTF-8') from exc
    if len(content) > MAX_FILE_BYTES: raise HTTPException(413, '檔案超過 10 MiB')
    return filename, content


def create_app(config_path=None):
    app = FastAPI(title='隱私工作台', docs_url=None, redoc_url=None)
    app.add_middleware(BodyLimitMiddleware)
    app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')
    manager = SettingsManager(config_path or os.environ.get('PII_CONFIG', DEFAULT_CONFIG))

    def current_settings():
        try: return manager.snapshot()
        except ValueError as exc: raise HTTPException(503, str(exc)) from exc

    def check_origin(request):
        origin = request.headers.get('origin')
        expected = str(request.base_url).rstrip('/')
        if origin and origin.rstrip('/') != expected:
            raise HTTPException(403, '僅允許由本機工作台操作隱私設定')
        if request.headers.get('content-type','').split(';')[0].strip() != 'application/json':
            raise HTTPException(415, '隱私設定請使用 JSON 表單內容')

    @app.get('/api/privacy-settings')
    def privacy_settings():
        cfg, _, revision = current_settings()
        return {'config': cfg, 'revision': revision, **form_choices()}

    @app.post('/api/privacy-settings')
    async def save_privacy_settings(request: Request):
        check_origin(request)
        try:
            body = await request.json()
            if not isinstance(body, dict): raise ValueError('設定表單格式不合法')
            cfg, revision = await run_in_threadpool(manager.save, body.get('config'), body.get('revision'))
            return {'config': cfg, 'revision': revision, 'message': '設定已儲存並立即生效，原設定已備份'}
        except SettingsConflict as exc: raise HTTPException(409, str(exc)) from exc
        except (ValueError, TypeError) as exc: raise HTTPException(400, str(exc)) from exc

    @app.post('/api/privacy-settings/test')
    async def test_privacy_settings(request: Request):
        check_origin(request)
        try:
            body = await request.json()
            if not isinstance(body, dict): raise ValueError('測試表單格式不合法')
            text = body.get('text')
            if not isinstance(text, str) or not text.strip(): raise ValueError('請輸入非空白的測試文字')
            if len(text) > 10_000: raise ValueError('測試文字最多 10,000 字元')
            def process():
                service = manager.draft_service(body.get('config'))
                matches = service.analyze(text)
                session = MappingSession('preview.txt')
                preview = session.replace(text, matches)
                return {'preview': preview, 'matches': [{'entity':m.entity,'text':text[m.start:m.end],'start':m.start,'end':m.end,'score':m.score} for m in matches]}
            return await run_in_threadpool(process)
        except (ValueError, TypeError, TimeoutError) as exc: raise HTTPException(400, str(exc)) from exc
        except Exception as exc: raise HTTPException(503, '測試辨識失敗，請確認模型與裝置設定；也可先停用模型') from exc

    @app.get('/', response_class=HTMLResponse)
    def index(): return (ROOT/'templates/index.html').read_text(encoding='utf-8')

    @app.get('/api/config')
    def settings():
        cfg, service, _ = current_settings()
        labels = {r['entity']:r['name'] for r in cfg['rules'] if r.get('enabled', True)}
        for entity in cfg['ner']['mapping'].values(): labels.setdefault(entity, {'PERSON':'姓名', 'LOCATION':'地點', 'ORGANIZATION':'組織'}.get(entity,entity))
        return {'entities':service.entities, 'labels':labels, 'ner_enabled':cfg['ner'].get('enabled',False), 'formats':SUPPORTED, 'max_file_bytes':MAX_FILE_BYTES}

    @app.post('/api/anonymize')
    async def anonymize(file: UploadFile | None = File(None), text: str | None = Form(None), entities: list[str] | None = Form(None), encoding: str = Form('utf-8')):
        try:
            cfg, service, _ = current_settings()
            if encoding not in ('utf-8','big5'): raise HTTPException(400,'編碼只支援 UTF-8 或 Big5')
            if entities is not None and not set(entities).issubset(service.entities): raise HTTPException(400,'選擇了設定中不存在的辨識類型')
            filename, content = await _source(file,text,encoding)
            def process():
                session = MappingSession(filename)
                result = transform_file(filename, content, PiiTransform(service,session,entities), encoding)
                output_name = Path(filename).stem+'_masked'+Path(filename).suffix.lower()
                data = _result(output_name,result,session.report(),encoding)
                data.update(mapping=_encoded(session.dump()), mapping_filename=Path(filename).stem+'.mapping.json')
                return data
            return await run_in_threadpool(process)
        except HTTPException: raise
        except (ValueError, TimeoutError) as exc: raise HTTPException(400,str(exc)) from exc
        except Exception as exc: raise HTTPException(503,'辨識或檔案處理失敗，請確認 CKIP 模型可用及檔案格式；可在設定檔停用模型後重試') from exc
        finally:
            if file is not None: await file.close()

    @app.post('/api/restore')
    async def restore(mapping: UploadFile = File(...), file: UploadFile | None = File(None), text: str | None = Form(None), encoding: str = Form('utf-8')):
        try:
            if encoding not in ('utf-8','big5'): raise HTTPException(400,'編碼只支援 UTF-8 或 Big5')
            filename, content = await _source(file,text,encoding)
            map_bytes = await mapping.read(MAX_MAPPING_BYTES+1)
            if len(map_bytes) > MAX_MAPPING_BYTES: raise HTTPException(413,'還原檔超過 10 MiB')
            def process():
                originals = load_mapping(map_bytes)
                result = transform_file(filename,content,originals.restore,encoding)
                output_name = Path(filename).stem+'_restored'+Path(filename).suffix.lower()
                return _result(output_name,result,originals.report(),encoding)
            return await run_in_threadpool(process)
        except HTTPException: raise
        except (ValueError, TimeoutError) as exc: raise HTTPException(400,str(exc)) from exc
        except Exception as exc: raise HTTPException(400,'復原失敗，請確認回覆檔案及還原檔格式') from exc
        finally:
            await mapping.close()
            if file is not None: await file.close()
    return app


app = create_app()
