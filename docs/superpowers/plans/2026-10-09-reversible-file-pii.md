# 原格式可復原脫敏 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution or superpowers:subagent-driven-development if the user selects delegated execution. Steps use checkbox syntax for tracking.

**Goal:** 透過設定檔擴充個資規則，提供七種格式的原格式脫敏下載、獨立還原檔，以及 AI 回覆檔案／文字復原。

**Architecture:** Presidio 與 CKIP 共用同一個設定式分析服務，產生不重疊的個資範圍；可復原代碼服務建立工作內唯一映射。各格式適配器處理文字位置與原容器回寫，Web 只協調輸入、結果及下載，不保存映射或文件。

**Tech Stack:** Python、Presidio、CKIP Transformers、PyYAML、FastAPI、Uvicorn、python-multipart、lxml、PyMuPDF、pytest、httpx；DOCX 與 XLSX 採 ZIP/XML 套件編輯。

**Spec:** [核准設計](../specs/2026-10-09-configurable-rules-web-design.md)

## Global Constraints

- 支援 DOCX、XLSX、PDF、TXT、CSV、JSON、XML；輸出沿用輸入格式，貼上文字輸出 TXT。
- 使用 ASCII 代碼 `[[PERSON_a4c83e21_0001]]`，同一工作內相同 entity 與原文共用代碼；還原 JSON 包含完整原文。
- 預設來源上傳限制 10 MiB；另設定還原檔 10 MiB、ZIP 解開總量 50 MiB、文字總量 2,000,000 字元、映射最多 100,000 筆。
- YAML 設定不執行任意 Python；XML 不允許 DTD 與外部實體；不能在記錄中輸出個資。
- 預設綁定 127.0.0.1，文件只在請求範圍保存；不包含登入、OCR、圖片內個資及嵌入物件处理。
- 保留原容器與未修改部分；代碼長度會影響換行，PDF 不能保證原字型或逐位元一致。
- 保留現有 staged app.py，未經使用者要求不一併提交既有暫存內容；在此工作區原地實作，避免無初始提交時無法建立 worktree。

## Review Focus

1. 長姓名或原文橫跨 DOCX run、PDF span：必須完整匹配，復原不能留半個代碼（Tasks 3、4）。
2. JSON 鍵與 XML 屬性包含特殊字元：替換後仍有效，拒絕鍵碰撞與實體攻擊（Task 2）。
3. Big5、BOM、CRLF、帶引號多行 CSV：未修改文字不被無意重排或錯誤解碼（Task 2）。
4. PDF 區域太窄、旋轉頁面及敏感文字靠近非敏感文字：不截斷代碼、不刪除相鄰內容，無法處理時報錯（Task 4）。
5. AI 改寫代碼、還原檔衝突及多請求並行：不猜測、不串用映射，未识別代碼明確回報（Tasks 1、5）。

---

### Task 1: 設定式分析與可復原代碼

**Files:** Create `pii_service/__init__.py`, `pii_service/config.py`, `pii_service/recognizers.py`, `pii_service/service.py`, `restoration.py`, `config/rules.yaml`, `tests/test_service.py`, `tests/test_restoration.py`, `requirements.txt`, `.gitignore`; modify `app.py` to delegate to the service after tests pass.

**Interfaces:**
- `load_config(path: Path) -> Config`; `create_service(config: Config) -> PiiService`.
- `PiiService.analyze(text: str, entities: list[str] | None = None) -> list[Match]`; `Match(entity: str, start: int, end: int, score: float)`.
- `MappingSession(filename: str)`; `replace(text: str, matches: list[Match]) -> str`; `dump() -> bytes`.
- `load_mapping(data: bytes) -> RestorationMap`; `RestorationMap.restore(text: str) -> str`; `report() -> dict` contains restored count and unresolved tokens, without raw original values.
- `TextTransform = Callable[[str], str]` used by file adapters. Text transformations are scoped to one request.

- [x] Write failing tests proving custom EMAIL YAML detects an address without code changes, disabled rule is absent, invalid regex/validator/score rejected, Taiwanese ID checksum preserved, and CKIP label mapping with a driver substitute.
- [x] Write failing restoration tests: repeated identical originals share a token; distinct originals differ; repeated/reordered AI tokens restore; unknown and malformed tokens remain; conflicting mapping rejected; replacements are single-pass; original token-like strings do not collide.
- [x] Run `.venv/bin/python -m pytest tests/test_service.py tests/test_restoration.py -v`; confirm failures are missing feature assertions/imports, not fixture errors. Install declared test dependencies if absent.
- [x] Implement config validation, named validator registry, configurable recognizers and deterministic overlap resolution (higher score, then longer range). Lazy-load CKIP only when enabled and requested, serialize inference, chunk with overlap and deduplicate adjusted positions. Apply replacements right-to-left and allocate tokens from a collision-checked random session namespace.
- [x] Implement versioned JSON mapping validation with size/count constraints, duplicate-key rejection, exact one-pass restoration and unresolved-token reporting.
- [x] Run both suites and existing CLI demo; check rule-only mode does not initialize CKIP. Preserve original demonstration behavior through the service. Mark task complete only on green results.

### Task 2: Text, CSV, JSON, XML 適配器

**Files:** Create `file_adapters/__init__.py`, `file_adapters/base.py`, `file_adapters/text.py`, `file_adapters/structured.py`, `tests/test_text_formats.py`.

**Interfaces:**
- `transform_file(filename: str, content: bytes, transform: TextTransform, encoding: str = "utf-8") -> FileResult` dispatches by extension.
- `FileResult(content: bytes, media_type: str, warnings: list[str])`; bad/unsupported files raise `FileProcessingError` with user-readable messages.
- `replace_spans(text: str, spans: list[tuple[int, int, str]]) -> str` rejects overlapping edits; text total accounting enforces the limit across every field.

- [x] Write round-trip tests for UTF-8/BOM/Big5 and CRLF; CSV quoted delimiters and multiline fields; JSON escaped strings, keys and unchanged number formatting; XML attributes, text/tails, namespaces, CDATA and comments.
- [x] Write rejection tests for invalid JSON/XML, JSON key collision, unknown suffix, unencodable restoration text, excessive text and XML DTD/entity declarations. Assert unknown AI tokens are reported through RestorationMap.
- [x] Run `.venv/bin/python -m pytest tests/test_text_formats.py -v` and inspect expected missing-feature failures.
- [x] Implement byte/encoding preservation for TXT; a CSV field scanner that preserves separators/line endings and quotes changed fields correctly; a validated JSON string-token scanner that changes only string spans; secure XML validation plus source-span edits with appropriate escaping. Reparse outputs and reject structural failures rather than emitting damaged files.
- [x] Run Task 1 and Task 2 suites. Check no source original values are exposed in ordinary error messages.

### Task 3: DOCX / XLSX 原套件編輯

**Files:** Create `file_adapters/office.py`, `tests/test_office_formats.py`, `tests/fixtures.py`.

**Interfaces:**
- Office adapters use the Task 2 `FileResult`, `TextTransform` and dispatcher.
- `transform_docx(content: bytes, transform: TextTransform) -> FileResult`.
- `transform_xlsx(content: bytes, transform: TextTransform) -> FileResult`.
- Shared helper `replace_text_nodes(nodes: list, transform: TextTransform) -> None` maps paragraph/full-string spans back to runs, retaining node formatting.

- [x] Create actual ZIP/XML test fixtures: Word surname and given name split across bold/plain runs, header/footer, tables, textbox, unrelated image and document styles; Excel shared/inline/rich strings, multiple sheets, formula, merged cell and drawing relationship.
- [x] Write tests asserting full-token restoration across runs, unchanged ZIP member bytes for images/styles/relationships, retained formulas/column widths/merged cells and valid output package. Validate required Office package types and reject macro-bearing/misnamed files, encrypted/corrupt archives, duplicate ZIP names and excessive unpacked data.
- [x] Run `.venv/bin/python -m pytest tests/test_office_formats.py -v`; confirm failures reflect missing adapters.
- [x] Implement bounded ZIP inspection without extraction; use hardened XML parser. DOCX edits relevant Word text paragraphs, preserving all untouched entries; XLSX edits shared and inline strings, retaining text/run properties and other parts. Update `xml:space` when replacements introduce boundary spaces. Document numeric cells, formulas, comments or unsupported text containers that are not processed; show file-specific warnings rather than claiming complete coverage.
- [x] Run all current suites; reopen output package and compare styles, images and layout properties. Include a cross-format test restoring Office-produced tokens in an AI TXT reply.

### Task 4: PDF 真正移除與可復原排版

**Files:** Create `file_adapters/pdf.py`, `tests/test_pdf_formats.py`, `tests/pdf_visual_check.py`.

**Interfaces:**
- `transform_pdf(content: bytes, transform: TextTransform) -> FileResult` shares the dispatcher interface.
- Collect per-character rectangles into per-line strings, then map transformation edits to original page geometry. Replacement operations contain original span, replacement text and per-line boxes.

- [x] Generate PDFs with Chinese names and ASCII IDs/phones using fonts available through PyMuPDF. Test text split across spans, repeated values, page rotation, adjacent nonsensitive text, narrow regions, multi-page documents and image-only pages.
- [x] Assert output page sizes and nonsensitive text unchanged, matched sensitive strings absent from text extraction, tokens fully extractable, and restoration output contains originals. For no text, invalid/encrypted PDF and replacement areas below readable size, assert useful errors.
- [x] Run `.venv/bin/python -m pytest tests/test_pdf_formats.py -v`; confirm missing-feature failures.
- [x] Implement geometric text removal with `apply_redactions` preserving nontext artwork/images by explicit flags. Avoid implicit replacement-text insertion: remove first, then insert complete replacement using font/size fitting. Require a minimum readable font size of 5 pt; refuse output if text cannot fit. Preserve page orientation and use Chinese-capable fonts for restoration. Fully rewrite with garbage collection so removed content is not retained in incremental revisions. Warn when images or annotations may contain unprocessed personal data.
- [x] Reopen output PDF and verify replacement token extraction against expected tokens; do not return an output with missing/truncated tokens. Run all suites and render sample original/masked/restored pages for visual inspection.

### Task 5: Web 脫敏與復原完整流程

**Files:** Create `web.py`, `templates/index.html`, `static/app.css`, `static/app.js`, `tests/test_web.py`.

**Interfaces:**
- `create_app(config_path: Path | None = None) -> FastAPI`; export `app` for `uvicorn web:app`.
- `GET /` serves interface; `GET /api/config` returns enabled entity labels and input limits only.
- `POST /api/anonymize` multipart fields: optional `file`, optional `text`, selected `entities`, `encoding`; exactly one nonempty content source required.
- `POST /api/restore` multipart fields: required mapping file `mapping`, optional `file` or `text`, `encoding`; same exclusive-source rule.
- Responses contain filename/media type/base64 output, sanitized report/warnings and, for anonymize only, base64 mapping. Browser creates local Blob download links and releases old object URLs; no shared download cache or tokenized server storage.

- [x] Write full TestClient round-trip tests: upload every format, decode output and mapping, send AI TXT/JSON with repeated/reordered tokens and restore, verify downloads use the correct extension. Include invalid mapping, both/neither input, unsupported suffix and oversized sources/mapping/body tests.
- [x] Test concurrent independent requests; content/mapping must remain isolated. Test literal HTML input is displayed as text, not executed. Ensure source filenames cannot create paths or headers.
- [x] Run `.venv/bin/python -m pytest tests/test_web.py -v`; expected failure is missing app/routes.
- [x] Implement bounded request body handling before multipart parsing plus read limits for individual uploads, execute CPU/blocking processing off the event loop, close uploads in finally blocks and map expected errors to 400/413. Expose no raw tracebacks to the page. Keep CKIP instance cached, transformations and reports request-local.
- [x] Implement responsive Traditional Chinese tabs, upload/drop zone, paste input, rule checkboxes, loading/error states, masked preview/report, two independent download buttons and restoration preview/result. Show format-specific limitations and instructions to send only the masked file to AI and preserve exact tokens. Use DOM textContent for untrusted text.
- [x] Run complete pytest suite; start local server and exercise the full workflow in a browser with a real file and pasted AI reply. Stop/release the verification server after checks, or explicitly report its running URL if retained at the user's request.

### Task 6: 使用說明、模型實測與最終檢查

**Files:** Create `README.md`, `tests/test_cli.py`; update `requirements.txt`, plan checkboxes and necessary fixes from verification.

**Interfaces:** CLI: `.venv/bin/python app.py --config config/rules.yaml` for existing demo; Web: `.venv/bin/python -m uvicorn web:app --host 127.0.0.1 --port 8000`; optional environment `PII_CONFIG` selects config.

- [x] Write CLI subprocess test for rule-only configuration and configuration validation errors; run to confirm missing CLI options fail.
- [x] Finish argparse/environment config handling and document setup, launch, EMAIL/deny-list extension examples, all formats' boundaries, mapping schema and AI instructions. Explain restart-to-reload settings and avoid calling scan/image content fully anonymized.
- [x] Run `.venv/bin/python -m pytest` and compile/import check. Use locally cached CKIP model for real surname/ID/mobile sample; if cache absent, report download requirement and attempt permitted dependency/model installation rather than silently substituting regex for names.
- [x] Review changes against every spec section, visually inspect rendered PDF and Web views, confirm original staged content is preserved and no uploaded samples or generated sensitive mapping files are tracked.
- [x] Report actual test counts, startup command, verified formats and material limitations. Do not claim exact layout identity or restoration of AI-mutated tokens.

## Reference Decisions

FastAPI upload uses multipart form fields and requires python-multipart: https://fastapi.tiangolo.com/tutorial/request-files/ . PyMuPDF removal and insertion are separate operations, with explicit image/vector preservation flags and checked insertion fit: https://pymupdf.readthedocs.io/en/latest/page.html .

## Self-review

Coverage checked against the approved spec: configurable recognizers, mapping, both Web flows, seven adapters, same-format download, layout constraints, upload lifetime/limits, unresolved tokens, error states and tests each have a task. Task dependencies are 1 → 2 → 3/4 → 5 → 6; Task 3 and Task 4 share the adapter interface but may be implemented sequentially. No implementation/dependency-installation action has been performed during planning.

## Execution results

60 tests passed (17.39s); Python imports/compile and JavaScript syntax checks passed. Real CKIP sample recognized PERSON, PHONE_NUMBER and TW_NATIONAL_ID using local cached model. PDF masked/restored pages rendered and visually inspected. Fresh reviewer found two important issues; both reproduced, fixed and re-reviewed (15 Office/PDF tests passed). Browser text anonymization showed complete tokens; a real Excel upload also showed completed downloads without altering the user-owned results. Browser automated mapping upload is blocked by extension file-URL permissions, so seven-format restoration was verified through FastAPI multipart integration tests. No commits, push or merge performed; existing staged original app.py is preserved.
