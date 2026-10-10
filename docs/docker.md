# Docker 安裝與操作

## 安裝並啟動

1. Windows／macOS：安裝 [Docker Desktop](https://docs.docker.com/desktop/)，啟動後等待引擎就緒。Linux 可使用 [Docker Engine](https://docs.docker.com/engine/install/) 加 [Compose plugin](https://docs.docker.com/compose/install/linux/)。
2. 下載並解壓縮本專案。在含有 `Dockerfile` 和 `docker-compose.yaml` 的資料夾開啟終端機。
3. 執行 `docker compose up -d --build`。
4. 等待建置完成，開啟 http://localhost:8080 。執行 `docker compose ps` 可看到服務狀態，正常啟動後會顯示 `healthy`。

不需要另裝 Python、Node.js 或 CUDA。套件建置與首次模型辨識需要網路；模型下載完成後會快取。這個版本使用 CPU，請在隱私設定選擇 CPU。檔案脫敏、復原與設定操作均透過網頁完成。

## 日常操作

| 操作 | 指令 |
| --- | --- |
| 啟動 | `docker compose up -d` |
| 停止 | `docker compose down` |
| 重啟 | `docker compose restart` |
| 更新程式後重建 | `docker compose up -d --build` |
| 查看狀態 | `docker compose ps` |
| 查看最近紀錄 | `docker compose logs --tail=100 presidio-tw` |

所有指令都在專案資料夾執行。預設只允許本機連線，網址是 http://localhost:8080 。電腦重開後啟動 Docker，引擎會依 `unless-stopped` 恢復之前正在執行的服務；手動停止的服務需再執行啟動指令。

若顯示連接埠被占用，複製 `.env.example` 為 `.env`，例如改為 `WEB_PORT=8081`，執行 `docker compose up -d`，再開啟 http://localhost:8081 。

## 設定、備份與模型快取

Docker 自動建立兩個具名 volumes：

- `privacy-settings`：容器 `/data`，規則為 `/data/config/rules.yaml`，上一版備份為 `rules.yaml.bak`。
- `model-cache`：容器 `/models`，保存 Hugging Face 模型快取。

實際 volume 名稱會加上 Compose 專案名稱。第一次啟動才初始化規則；網頁儲存之後即時套用。重建容器不覆蓋既有設定。`config/rule_templates.yaml` 則隨映像更新，保持新增範本與程式版本一致。

將 Docker 規則與上一版備份複製到本機：

```bash
docker compose cp presidio-tw:/data/config ./docker-config-backup
```

復原備份（服務須正在執行）：

```bash
docker compose cp ./docker-config-backup/rules.yaml presidio-tw:/data/config/rules.yaml
docker compose exec --user 0 presidio-tw chown -R 10001:10001 /data/config
docker compose restart
```

備份的規則可能包含指定姓名與內部關鍵字，請妥善保管。原始上傳檔案與還原檔不會自動保存到 volumes；還原檔仍需由使用者下載保存。

`docker compose down` 保留 volumes。**`docker compose down -v` 會刪除設定與模型快取**；移除 Docker Desktop 資料前也請先備份。

## 交付給其他電腦

將專案資料夾交給使用者，依上述指令建置即可。若要省略接收端建置，可以在已成功建置的電腦匯出映像：

```bash
docker save -o presidio-tw-image.tar presidio-tw:local
```

接收端將映像、`docker-compose.yaml` 與 `.env.example` 放在同一資料夾，執行：

```bash
docker load -i presidio-tw-image.tar
docker compose up -d --no-build
```

映像須符合接收端 CPU 架構。映像不包含首次下載的 CKIP 模型與使用者後續設定；模型初次使用仍需網路。需要離線搬移時，先在來源端實際完成一次姓名辨識，再匯出模型目錄：

```bash
docker compose cp presidio-tw:/models ./models-backup
```

接收端啟動後，複製快取並重啟：

```bash
docker compose cp ./models-backup/. presidio-tw:/models
docker compose exec --user 0 presidio-tw chown -R 10001:10001 /models
docker compose restart
```

快取需包含所選模型的完整下載，切換其他模型仍可能需要網路。

## 疑難排解

- 瀏覽器顯示 `0.0.0.0 refused to connect`：請開啟 http://localhost:8080 。日誌中的 `0.0.0.0:8000` 是容器內監聽位址，瀏覽器使用的是 Compose 對外連接埠 `8080`。
- 使用 `docker compose up --build` 後停止終端機執行：前景模式按 Ctrl+C 會停止容器。改用 `docker compose up -d --build` 在背景執行，再用 `docker compose ps` 確認狀態。
- 找不到 `docker` 或 `docker compose`：確認 Docker Desktop 已安裝，或 Linux 已安裝 Compose plugin。
- 無法連接 Docker daemon：確認 Docker 引擎已啟動，Linux 使用者具有 Docker 使用權限。
- 首次下載模型失敗：確認網路可連到 Hugging Face，稍後重新測試；亦可先在隱私設定停用模型，使用格式規則與指定清單。
- 頁面顯示舊版本：更新程式後執行 `docker compose up -d --build`，再重新整理瀏覽器。
- `unhealthy`：查看服務紀錄與網頁錯誤；修正設定後可執行 `docker compose restart`。健康檢查不會主動載入模型。
