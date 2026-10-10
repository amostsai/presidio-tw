# Presidio TW 隱私工作台

以設定檔擴充台灣個資辨識，將文件中的敏感文字換成可復原代碼。原格式脫敏檔可交給 AI；保存在本機的 JSON 還原檔可將 AI 回覆中的代碼換回姓名、證號等原文。

## Docker 啟動（一般使用者）

先安裝並啟動 [Docker Desktop](https://docs.docker.com/compose/install/)，下載本專案並解壓縮。在含有 `docker-compose.yaml` 的資料夾開啟終端機，執行：

```bash
docker compose up -d --build
```

完成後開啟 **http://localhost:8080**。第一次建置需要下載套件；第一次姓名辨識還會下載 CKIP 模型，請保持網路連線並等待。平常啟動只需 `docker compose up -d`。

容器使用 CPU，模型設定請選 CPU。Docker 的設定與模型快取各有獨立 volume；介面儲存的規則及 `.bak` 備份位於容器 `/data/config/`，停止、重建或更新容器都會保留。第一次啟動才複製專案預設規則，後續啟動不會覆蓋使用者設定。Docker 版設定與直接執行 Python 的 `config/rules.yaml` 各自獨立。

停止：`docker compose down`。更新程式後重新執行 `docker compose up -d --build`。查看狀態：`docker compose ps`；查看紀錄：`docker compose logs --tail=100 presidio-tw`。已啟動的容器發生程序退出會自動重啟；健康檢查失敗會標記狀態，不會單憑標記自動重啟。電腦重新開機後，需要 Docker 引擎也啟動才會恢復服務。

8080 被占用時，將 `.env.example` 複製成 `.env`，修改 `WEB_PORT` 後重新啟動。不要使用 `docker compose down -v`，除非確定要刪除已保存的設定與模型快取。

完整安裝、備份與離線搬移方法請見 [Docker 使用說明](docs/docker.md)。

## Python 啟動（開發者）

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn web:app --host 127.0.0.1 --port 8000
```

開啟 http://127.0.0.1:8000 。預設僅在本機提供服務。第一次使用 CKIP 需要下載 `ckiplab/bert-base-chinese-ner` 模型；已有 Hugging Face 快取則可直接使用。CPU 推論期間畫面會顯示處理狀態。

## 使用流程

1. 「文件脫敏」上傳 DOCX、XLSX、PDF、TXT、CSV、JSON、XML，或貼上文字；選擇需要的辨識項目。
2. 分別下載原格式的脫敏檔與 `.mapping.json` 還原檔。**只將脫敏檔交給 AI；還原檔包含真實個資，留在本機。**
3. 要求 AI 保留所有代碼，例如 `[[PERSON_a4c83e21_0001]]`，不要改寫、翻譯、拆開或新增代碼。
4. 在「回覆復原」上傳 AI 回覆檔案或貼上文字，並上傳對應還原檔。
5. 下載復原結果，格式沿用 AI 回覆檔案；貼上文字則下載 TXT 或複製內容。

同一工作內相同 entity 與相同原文共用代碼；不同原文使用不同代碼。代碼可重複、重排、省略。未知或被修改的 `[[…]]` 代碼保持原樣並列出；系統不猜測 AI 自行新增的人名。若 AI 把括號移除成一般文字，系統無法可靠識別它是代碼，請自行檢查。

## 設定檔擴充

在「隱私設定」使用開關啟用／停用規則與模型，從下拉選單新增身分證、手機、統編、Email、指定姓名或關鍵字範本。姓名與關鍵字每行輸入一筆；正則表達式、模型對應與分數放在進階設定中。

可先輸入範例文字並「測試辨識」，測試使用目前草稿，不會儲存設定。按「儲存並立即套用」後，新請求會立刻使用新規則，不必重啟服務；既有脫敏結果與還原檔不受影響。

「指定納入清單」預設使用完整英數字詞比對，英文不分大小寫：`EXAMPLE` 可比對 `EXAMPLE`、`example`，但不會比對 `exampled`、`XEXAMPLE`、`EXAMPLE1`、`_EXAMPLE` 中的片段。中文姓名仍可連在句子中，例如「王小明找李小華」。需要片段比對時，可明確選擇「任意子字串」。英數邊界包含 A–Z、a–z、0–9 與底線，並不以中文為分隔限制。

「排除清單」每行一筆，適用類型可選全部、姓名或其他類型。**完整辨識內容**與排除項目相同時保留原文，英文不分大小寫；排除優先於納入清單、格式規則及模型。同時出現在兩份清單會顯示提醒。排除「EXAMPLE」不會自動排除「EXAMPLE Inc.」，請把要保留的完整內容列入。

桌面版可拖拉左右面板間的分隔線，調整右側結果／測試區寬度；也可用左右方向鍵，雙擊恢復預設。各分頁會記住寬度，手機版改為上下排列。

預設規則檔為 `config/rules.yaml`，上一版備份為 `config/rules.yaml.bak`。表單儲存會保留自訂欄位，但 YAML 的註解與排版會重新整理。版本不同時會拒絕覆蓋，請重新載入後再編輯；儲存期間請避免同時用外部編輯器寫入，檔案系統無法將版本檢查與其他程式的寫入合併成同一操作。直接修改 YAML 也會在下一次設定讀取或脫敏請求套用。範本來源為 `config/rule_templates.yaml`，新增範本可擴充下拉選單。

```yaml
version: 1
ner:
  enabled: false  # true 開啟 CKIP
rules:
  - name: 電子信箱
    enabled: true
    entity: EMAIL
    context: [Email, 信箱]
    patterns:
      - name: email
        regex: '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
        score: 0.9
  - name: 指定姓名
    entity: PERSON
    deny_list: [王小明, 李小華]
    deny_list_score: 1.0
    deny_list_match: word  # substring 明確開啟任意子字串比對
exclusions:
  - entity: PERSON  # '*' 表示全部類型
    words: [李小華]
```

新增正則／詞庫只需要改 YAML。`entity` 使用大寫英文字母、數字與底線，最長 40 字元；分數介於 0 與 1。`enabled: false` 停用規則。`context` 可對周圍出現指定文字的結果增加分數。預設包含台灣身分證、統編、手機、姓名欄位與地址欄位規則。身分證格式符合即脫敏，不以檢查碼決定是否遮蔽；需要時可在進階設定啟用校驗。統編預設保留校驗。姓名與地址欄位規則辨識獨立一行的欄位值；完整臺灣道路地址也可在一般句子或儲存格中辨識，涵蓋縣市、區鄉、路街、巷弄、門牌與樓層，整段換成同一個代碼。JSON 地址欄位值會整段處理。

目前可信任的 `validator` 名稱是 `tw_id`、`tw_tax_id`。新增校驗演算法需在 `pii_service/recognizers.py` 實作並註冊，設定檔不執行任意程式。規則互相重疊時依分數、長度與位置選擇不重疊範圍。

CKIP 設定：`enabled`、`model_name`、`device`（-1 CPU）、`score`、`mapping`、`chunk_size`（16–450）、`overlap`。預設 PERSON→姓名、ORG→組織、GPE/LOC→地點；可調整對應與在介面取消選取。姓名的泛用辨識依賴 CKIP，指定姓名可使用詞庫。

使用另一份設定檔：

```bash
PII_CONFIG=/path/to/rules.yaml .venv/bin/python -m uvicorn web:app --host 127.0.0.1 --port 8000
```

## 檔案格式與排版界線

| 格式 | 可處理文字 | 保留與限制 |
| --- | --- | --- |
| DOCX | 段落、表格、頁首頁尾、註腳／尾註、可讀文字框，支援跨 run；Tab／換行／段落為辨識分隔邊界 | 原 ZIP 容器保留樣式、圖片、關聯；替換文字繼承起始 run 樣式。長代碼可能改變換行。欄位指令、圖片、文件屬性與嵌入物件不處理。 |
| XLSX | 所有工作表的 shared/inline 字串與富文字 | 保留公式、合併、樣式、欄寬、列高、圖片與其他套件內容。數字型儲存格、公式及其計算值、工作表名稱、批註、文件屬性、圖片與嵌入物件不處理。 |
| PDF | 可抽取文字層，含跨 span 的同一行文字；依設定欄位名稱辨識對齊的表格欄位，同一儲存格內換行地址合併處理 | 真正移除指定文字並完整重寫 PDF，插入可抽取短代碼；保留頁面尺寸、旋轉與表格。替換可利用右側空白，必要時重新排該行文字或縮小字級（最低 5 pt）。仍放不下、移除區域會碰到其他文字或代碼不能完整抽取則報錯。字型可能改變。掃描檔不含 OCR；直書／旋轉文字的替換、圖片、註解、表單、附件、文件屬性不處理。 |
| TXT | 全文；有已知欄位標題的 CSV 內容則依欄處理 | 保留來源換行、BOM 及選定編碼。 |
| CSV | 依標題列套用欄位規則，再處理其他資料格；標題保留 | 保留分隔符、換行與引號風格，必要時補引號。支援逗號、分號、Tab、直線分隔符。 |
| JSON | 字串值（鍵名保留） | 保留縮排、鍵名、順序與數值原寫法；來源重複鍵時拒絕輸出。數字與布林值不處理。姓名／地址欄位可用 YAML 的 `field_keys` 與 `field_value_regex` 擴充比對。 |
| XML | 依標籤／屬性名稱套用欄位規則，再辨識內容 | 保留結構、命名空間、註解與空白，正確跳脫；不支援 DTD/外部實體。標籤名稱不替換。 |

結構化欄位規則使用 `field_keys` 設定欄位別名，`field_value_regex` 設定整格内容格式；既有 `json_keys`／`json_value_regex` 仍相容。CSV 使用可辨識的標題列；DOCX 使用表格首列、XLSX 使用首個含已知欄位名稱的列。簡單標題列下的同欄字串會一致套用規則，標題保留。XLSX 必要時將共用字串轉成保留樣式的 inline 字串，並清除已無儲存格引用的原敏感字串。

**本工具處理可讀文字，不能保證所有個資都被辨識或涵蓋圖片、公式與文件附加資訊。** 請依格式檢查未處理範圍。版面盡量保持一致，不承諾逐位元相同；復原保留 AI 本身的修改，並非還原整份文件的原始歷史版本。

文字檔支援 UTF-8（含 BOM）與 Big5，BOM 優先。復原內容若無法以 Big5 表示，請改用 UTF-8 來源／回覆檔。單檔與還原檔各最多 10 MiB，上傳總量最多 21 MiB，Office 解開總量最多 50 MiB、5,000 項，處理文字最多 2,000,000 字元，映射最多 100,000 筆。加密 PDF、加密 Office 及含巨集文件不支援。

## 還原檔

PDF 使用短代碼 `[[P_a4c83e21_0001]]` 及第 2 版還原檔；實際隱私類型保留在 `entity` 欄位。其他格式維持第 1 版，兩版均支援上傳檔案或貼上 AI 回覆文字復原，舊版還原檔仍可使用。

```json
{
  "version": 1,
  "session_id": "a4c83e21",
  "filename": "example.txt",
  "entries": [
    {"token": "[[PERSON_a4c83e21_0001]]", "entity": "PERSON", "original": "王小明"}
  ]
}
```

還原檔為未加密 JSON，請像原始文件一樣保管；遺失後無法僅靠代碼推導真實資料。每次請求的映射獨立，服務不保存共享下載快取或上傳原檔、不記錄原始個資，不向 AI 服務傳送資料；瀏覽器持有結果直到清除／關閉頁面。這是本機工具，若要對外部署，需另加登入、存取隔離與 HTTPS。

## 命令列示範

```bash
.venv/bin/python app.py
.venv/bin/python app.py --no-ner --text '身分證A123456789，手機0912-345-678'
.venv/bin/python app.py --config config/rules.yaml --text '王小明的手機0912-345-678' --mapping /tmp/example.mapping.json
```

未指定 `--mapping` 時不寫入含原文的對照檔。

## 測試

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
node tests/settings-ui.test.cjs
```

測試涵蓋設定擴充、校驗、映射驗證、AI 代碼重排／重複、七種格式回寫與復原、Office 樣式／圖片保留、PDF 真正移除及可抽取代碼、Web 完整流程、上傳大小限制及請求隔離。CKIP 單元測試使用推論替身；另外可用預設命令列示範驗證本機真實模型。
