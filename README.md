# Presidio TW 隱私工作台

將姓名、身分證、手機及地址換成可復原代碼，交給 AI 處理後，再用還原檔換回真實資料。

支援 **DOCX、XLSX、PDF、TXT、CSV、JSON、XML**。脫敏沿用原檔格式；復原沿用 AI 回覆檔案的格式，並盡量保留排版。

## 快速開始：Docker

1. 安裝並啟動 [Docker Desktop](https://docs.docker.com/desktop/)。Linux 安裝方式見 [Docker 使用說明](docs/docker.md)。
2. 解壓縮專案，在含有 `docker-compose.yaml` 的資料夾開啟終端機。
3. 執行：

   ```bash
   docker compose up -d --build
   ```

4. 開啟 **http://localhost:8080**。

首次建置會下載套件，首次使用模型會下載 CKIP 模型，請保持網路連線並等待。Docker 版使用 CPU，不需另裝 Python 或 CUDA。

| 操作 | 指令 |
| --- | --- |
| 日常啟動 | `docker compose up -d` |
| 停止服務 | `docker compose down` |
| 更新程式 | `docker compose up -d --build` |
| 查看狀態 | `docker compose ps` |
| 查看紀錄 | `docker compose logs --tail=100 presidio-tw` |

8080 被占用時，複製 `.env.example` 為 `.env`，例如改成 `WEB_PORT=8081`，再啟動並開啟 `http://localhost:8081`。

設定與模型快取會保留在 Docker volumes，停止或重建容器不會刪除。**`docker compose down -v` 會刪除兩者。** 備份與離線搬移方式見 [Docker 使用說明](docs/docker.md)。

## 脫敏與復原

1. 在「文件脫敏」上傳檔案或貼上文字，選擇辨識項目。
2. 下載**脫敏檔**與 **`.mapping.json` 還原檔**。
3. 將脫敏檔交給 AI，按「複製 AI 提示語」，提醒 AI 完整保留 `[[…]]` 代碼。
4. 在「回覆復原」上傳 AI 回覆檔案或貼上文字，再選擇對應還原檔。
5. 下載復原檔；貼上文字時，可下載 TXT 或複製結果。

**還原檔包含真實個資，請留在本機，不要交給 AI。** 遺失後無法只靠代碼找回原文。

將滑鼠移到「已替換的敏感內容」，或點擊展開，可查看原文與代碼對照。桌面版可拖拉面板分隔線調整右側寬度、用方向鍵微調，雙擊恢復預設；各分頁會記住寬度，手機版改為上下排列。

同次脫敏中，相同類型、相同原文共用代碼。AI 可重複、重排或省略代碼；未知或被修改的 `[[…]]` 代碼會保留並列出。若括號被移除或 AI 新增姓名，系統不會猜測原文。復原會保留 AI 的修改。

| 來源格式 | 代碼範例 | 還原檔版本 |
| --- | --- | --- |
| PDF | `[[P_a4c83e21_0001]]`，短代碼適合窄欄位 | 2 |
| 其他格式 | `[[PERSON_a4c83e21_0001]]` | 1 |

兩版均可用於檔案或文字復原，舊版還原檔仍可使用。

## 隱私設定

用開關與下拉選單管理規則，不必修改程式。

| 設定 | 用途 |
| --- | --- |
| 格式規則 | 辨識身分證、手機、統編、Email 等格式 |
| 指定納入清單 | 確保特定姓名、關鍵字被替換，每行一筆 |
| 排除清單 | 保留指定內容，套用到全部或特定類型，每行一筆 |
| 智慧模型辨識 | 自動找出清單以外的姓名、組織；可另開啟地點辨識 |
| 進階設定 | 調整正則表達式、校驗、模型對應與辨識優先程度 |

先按「測試辨識」檢查草稿，再按**「儲存並立即套用」**。新請求會使用新規則，不必重啟服務；既有結果不會更新，請重新執行脫敏。

### 預設規則

- **台灣身分證**：預設啟用並勾選。格式符合即脫敏，不因檢查碼不符而保留；需要時可啟用校驗。
- **台灣手機、統編**：預設啟用，統編會校驗；市話格式需另增規則。
- **姓名欄位**：處理已知姓名欄位的整格文字，以及 `姓名：王小明` 等獨立一行的內容。
- **地址欄位**：已知欄位整格替換；一般文字可辨識完整臺灣道路地址，包含縣市、區鄉、路街、巷弄、門牌與樓層。
- **CKIP 模型**：專案預設辨識姓名與組織，地點可另行啟用。模型結果仍需檢查。

### 清單比對方式

納入清單預設比對**完整英數字詞**，英文不分大小寫。`EXAMPLE` 可比對 `example`，不會替換 `exampled`、`XEXAMPLE`、`EXAMPLE1` 或 `_EXAMPLE` 中的片段。需要片段比對時，選「任意子字串」。中文姓名可在句子中直接比對。

排除清單比對**完整辨識內容**，英文不分大小寫，優先於所有納入規則與模型。排除 `EXAMPLE` 不會連帶排除 `EXAMPLE Inc.`；兩份清單有相同內容時，介面會提醒。

### 設定保存位置

| 啟動方式 | 規則檔 | 上一版備份 |
| --- | --- | --- |
| Docker | 容器 `/data/config/rules.yaml` | 同目錄的 `rules.yaml.bak` |
| Python | 專案 `config/rules.yaml` | `config/rules.yaml.bak` |

兩種方式的設定各自獨立。Docker 只在首次啟動時複製預設規則，更新程式不會覆蓋既有設定。

儲存會保留自訂欄位，並重新整理 YAML 排版與註解。版本衝突時，請重新載入再編輯；避免同時用外部編輯器修改。直接修改 YAML 也會在下次讀取設定時套用。

## 各格式如何處理

依檔案結構判斷脫敏位置，盡量保留標題、欄位名稱與版面。

| 格式 | 處理方式與限制 |
| --- | --- |
| DOCX | 處理段落、表格、頁首頁尾、註腳、尾註與可讀文字框；依表格首列的已知標題套用欄位規則。保留樣式與圖片，代碼可能改變換行 |
| XLSX | 處理各工作表的文字儲存格；首個含已知欄位名稱的列作為標題。保留公式、合併、樣式、欄寬與列高；不處理數字儲存格、公式及計算值 |
| PDF | 真正移除敏感文字，再寫入短代碼。辨識對齊表格，合併同格的跨行地址；必要時調整該行排版或縮小字級，最低 5 pt。無法安全容納時停止輸出；掃描檔未提供 OCR |
| TXT | 處理全文；具有已知標題的 CSV 內容則依欄處理。保留換行與 BOM，支援 UTF-8、Big5 |
| CSV | 保留已知標題列，逐列套用同欄規則，再辨識其他資料格。保留分隔符、換行與引號；支援逗號、分號、Tab、直線分隔符 |
| JSON | 只處理字串值，保留鍵名、縮排、順序與數值。數字、布林值不處理，重複鍵會拒絕輸出 |
| XML | 依標籤或屬性名稱處理文字與 CDATA，保留結構、命名空間、註解與空白；不支援 DTD、外部實體 |

例如 CSV 的「姓名」欄會逐列處理；JSON 的 `"name": "陳建華"` 保留 `name`，只替換右側內容。地址 `臺北市中正區重慶南路一段122號` 會整段換成一個代碼。

不處理圖片、文件屬性，以及 PDF 註解／表單／附件／直書與旋轉文字替換、DOCX 欄位指令／嵌入物件、XLSX 工作表名稱／批註。請檢查結果提醒與文件內容，**辨識及排版不保證完全準確**。

### 檔案限制

- 原檔、還原檔各最多 **10 MiB**，單次上傳總量最多 **21 MiB**。
- Office 解壓後最多 50 MiB、5,000 項；文字最多 2,000,000 字元，還原對照最多 100,000 筆。
- 不支援加密 PDF、加密 Office 或含巨集文件。
- 預覽最多 100,000 字元，下載檔仍包含完整內容。Big5 無法表示復原文字時，請改用 UTF-8。

## 常見問題

| 問題 | 處理方式 |
| --- | --- |
| `0.0.0.0 refused to connect` | 開啟 `http://localhost:8080`；`0.0.0.0:8000` 是容器內監聽位址 |
| 網頁仍是舊版 | 更新程式後執行 `docker compose up -d --build`，再重新整理；僅重啟不會重建映像 |
| 刪除規則後結果沒變 | 儲存設定，再重新執行脫敏 |
| 新版預設規則未出現 | Docker 保留既有設定，請在介面新增需要的範本 |
| 模型載入很久或下載失敗 | 等待並確認網路；也可停用模型，改用格式規則與指定清單 |
| PDF 替換空間不足 | 短代碼與排版調整仍放不下時，可改用 DOCX 或文字格式 |
| AI 回覆無法復原 | 確認還原檔對應同次脫敏，並檢查代碼是否被改動 |

容器程序退出時會自動重啟；健康檢查失敗只標記 `unhealthy`。電腦重開後需啟動 Docker 引擎；手動停止的服務須再次啟動。

服務不永久保存上傳檔案與下載結果，也不會自動將文件傳給 AI。還原檔是未加密 JSON，請自行下載保管。預設只供本機使用，對外部署需另設登入、存取隔離與 HTTPS。

## 開發者說明

### Python 啟動

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn web:app --host 127.0.0.1 --port 8000
```

開啟 **http://127.0.0.1:8000**。首次使用 CKIP 會下載模型；已有快取則直接使用。指定其他規則檔：

```bash
PII_CONFIG=/path/to/rules.yaml .venv/bin/python -m uvicorn web:app --host 127.0.0.1 --port 8000
```

### YAML 擴充範例

```yaml
version: 1
ner:
  enabled: false
rules:
  - name: 指定姓名與姓名欄位
    entity: PERSON
    deny_list: [王小明, 李小華]
    deny_list_match: word
    deny_list_score: 1.0
    field_keys: [name, full_name, 姓名]
    field_value_regex: '(?=\s*\S)[^\r\n]{1,120}'
exclusions:
  - entity: PERSON
    words: [測試人員]
```

擴充時常用的設定：

- `patterns`：正則表達式與分數，分數介於 0 和 1。
- `field_keys`／`field_value_regex`：欄位別名與整格比對格式；舊版 `json_keys`／`json_value_regex` 仍相容。
- `enabled: false`：停用規則。`exclusions` 的 `entity: '*'` 套用全部類型。
- `validator`：可用 `tw_id`、`tw_tax_id`；新演算法需在 `pii_service/recognizers.py` 註冊。

`entity` 使用大寫英文、數字、底線，最多 40 字元，首字須為英文字母。重疊結果依分數、長度與位置決定。修改 `config/rule_templates.yaml` 可新增下拉選單範本。

CKIP 預設模型為 `ckiplab/bert-base-chinese-ner`，`device: -1` 表示 CPU；可調整類型對應、分數與分段大小。設定檔不執行任意程式。

### 命令列與測試

```bash
.venv/bin/python app.py --no-ner --text '身分證A123456789，手機0912-345-678'
.venv/bin/python app.py --text '姓名：王小明' --mapping /tmp/example.mapping.json
```

未指定 `--mapping` 時，不會寫入還原檔。

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
node --test tests/*.test.cjs
```

測試涵蓋設定、七種格式脫敏與復原、Office 樣式、PDF 短代碼與跨行地址、還原檔驗證及 Web 操作。CKIP 單元測試使用推論替身，實際模型可用命令列示範驗證。

開發團隊：[學創科技有限公司](https://metalearning.tw)
