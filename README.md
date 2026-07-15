# 智慧親師通系統 (WenHuaLineBot)

本專案是一個專為補習班設計的「零信任資安」打卡與家長通知系統。採用 **全雲端化 (Thin Client)** 架構，讓補習班內無論多麼老舊的電腦 (如 Windows 7 32-bit)、平板或手機，都只需打開網頁瀏覽器即可完美運作！

目前系統已全面部署至雲端，所有的功能皆可透過專屬網址直接存取。
**專屬網址**：[https://wenhuacheckin.onrender.com/](https://wenhuacheckin.onrender.com/)

---

## 🌟 系統特色

1. **老舊電腦救星**：補習班端無需安裝任何軟體。只需一台能上網的電腦加上 USB 刷卡機，就能達成無延遲刷卡作業。
2. **極簡的家長綁定**：家長只需在官方 LINE 帳號直接輸入文字（例如「綁定 王小明 0912345678」），即可瞬間完成 LINE 綁定，無需跳轉網頁。
3. **無痛的後台管理**：專屬的圖形化後台介面，支援一鍵上傳 Excel 名單建檔，同時新增了「成績登錄」與「課表管理」功能。
4. **離線容錯機制**：萬一補習班網路瞬斷，刷卡網頁會自動暫存打卡紀錄於瀏覽器內，待網路恢復後自動回傳補登。
5. **防止重複推播**：具備 Idempotency Key (冪等性) 設計，確保網路重試時不會導致家長收到重複的到班通知。

---

## 🚀 日常營運操作手冊 (給補習班櫃檯/管理者)

### 一、每日刷卡 (學生到班/離班)
這是放在櫃檯讓學生拿卡片嗶嗶的畫面。
1. **網址**：[https://wenhuacheckin.onrender.com/static/swipe.html](https://wenhuacheckin.onrender.com/static/swipe.html)
2. **操作步驟**：
   - 每天開門時，打開上述網址 (建議存成瀏覽器書籤)。
   - 輸入「打卡機密碼」(KIOSK_TOKEN) 後，點擊「開始營業」。
   - 將滑鼠游標停留在白色的輸入框內。
   - 學生拿卡片在 USB 感應機上刷卡，系統會自動輸入卡號並按下 Enter，家長立刻收到 LINE 到班通知！

### 二、後台管理 (匯入名單與下載報表)
這是只有老闆與行政老師可以進入的系統後台。
1. **網址**：[https://wenhuacheckin.onrender.com/static/admin.html](https://wenhuacheckin.onrender.com/static/admin.html)
2. **操作步驟**：
   - 進入網址後，輸入「管理員密碼」(ADMIN_TOKEN) 登入。
   - **匯入學生名單**：點擊上傳 Excel (檔案內需包含：`學號`、`姓名`、`卡號`、`家裡電話` / `簡訊電話` / `父母手機`)，系統會自動新建或更新學生與家長資料。
   - **下載今日出勤**：點擊下載按鈕，即可取得今天所有學生的進班與離班打卡時間明細報表。
   - **額外管理系統**：透過主選單，您可進入 **名單管理 (`students.html`)**、**成績登錄 (`grades.html`)** 與 **課表管理 (`timetable.html`)** 系統，統一使用管理員密碼 (ADMIN_TOKEN) 進行驗證。

### 三、家長綁定身分 (給家長的手機操作)
為了讓家長能收到 LINE 通知，必須先進行綁定。
1. 家長在補習班官方 LINE 帳號，點擊下方「圖文選單」的 **[綁定身分]**。
2. 系統會自動提示綁定格式。
3. 家長於聊天室內輸入指令（例如：`綁定 王小明 0912345678`），手機號碼需與當初留在補習班的資料一致。
4. 系統比對符合後即刻綁定成功，未來家長可主動點擊選單查詢出勤狀況與近期成績。

---

## 🛠️ 開發與部署指南 (給開發人員)

### 雲端架構配置 (Render + Supabase)
本專案的生產環境使用 Render (Web Service) 與 Supabase (PostgreSQL 資料庫)。
內建 `render.yaml` 支援一鍵部署 (Infrastructure as Code)。

#### 必備環境變數 (Environment Variables)：
- `DATABASE_URL`: Supabase 連接池網址 (請務必勾選 Use connection pooling，採用 IPv4 格式，例如 `postgresql://postgres:密碼@aws-0-ap...pooler.supabase.com:6543/postgres`)
- `LINE_CHANNEL_SECRET`: LINE 機器人的 Secret 金鑰
- `LINE_CHANNEL_ACCESS_TOKEN`: LINE 機器人的 Access Token 金鑰
- `ADMIN_TOKEN`: 後台管理頁面的登入密碼
- `KIOSK_TOKEN`: 前台刷卡機頁面的啟動密碼
- `CRON_TOKEN`: 給定時排程任務使用的安全金鑰
- `ALLOWED_ORIGINS`: CORS 允許的網域清單 (雲端部署時選填)

### 🚀 圖文選單更新機制 (LINE Rich Menu)
當部署到雲端且設定好金鑰後，若需要更新 LINE 官方帳號的底部圖文選單，請直接用瀏覽器造訪：
`https://wenhuacheckin.onrender.com/api/setup-menu`
系統就會自動將最新版的圖文選單註冊至 LINE 伺服器！

### 關於喚醒延遲 (防休眠機制)
Render 免費方案在 15 分鐘無人使用後會進入休眠。為避免第一位學生刷卡時遇到 50 秒的喚醒延遲：
強烈建議使用免費服務 [cron-job.org](https://cron-job.org/)，設定每 **14 分鐘** 對 `https://wenhuacheckin.onrender.com/static/swipe.html` 發送一次 GET 請求，確保伺服器 24 小時保持清醒。

---

## 📦 單機免安裝版 (Legacy Standalone / 進階備查)
如果您未來遇到雲端服務大斷線，需要轉為本地運行 (僅限 64 位元 Windows 10/11)。
1. **打包指令**：開發環境執行 `build.bat`。
2. **產出物**：打包完成的檔案會在 `dist/SmartSchoolBot` 內。
3. **啟動隧道**：需自行下載 Zrok (`zrok.exe`) 並執行 `zrok reserve public localhost:8000 --backend-mode proxy` 取得外網穿透網址。
4. **執行伺服器**：雙擊 `SmartSchoolBot.exe` 啟動本地伺服器，將使用同目錄下的 `test.db` SQLite 資料庫。
