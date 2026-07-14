# 智慧親師通系統 (WenHuaLineBot)

本專案是一個專為補習班設計的「零信任資安」打卡與家長通知系統。採用 **全雲端化 (Thin Client)** 架構，讓補習班內無論多麼老舊的電腦 (如 Windows 7 32-bit)、或是平板、手機，都只需「打開網頁瀏覽器」即可完美運作！

## 🌟 系統亮點

1. **無限相容的老電腦救星**：補習班端無需安裝任何軟體或應用程式，打開瀏覽器 `https://您的網域/static/swipe.html` 即可進行無延遲的刷卡作業。
2. **全雲端化 24H 運作**：結合免費的 Render.com 與 Supabase PostgreSQL，系統全天候在雲端運作，不用擔心家裡/補習班電腦當機斷線。
3. **離線容錯機制**：就算補習班網路突然斷線，網頁端會自動將打卡紀錄暫存於瀏覽器 (LocalStorage) 中，待網路恢復後自動回傳補登，確保資料絕不遺失。
4. **一鍵部署 (Infrastructure as Code)**：內建 `render.yaml`，連接 GitHub 後即可達成真正的「一鍵上線」。

---

## 🚀 全雲端部署教學 (100% 免費方案)

### 步驟一：建立免費雲端資料庫 (Supabase)
1. 前往 [Supabase](https://supabase.com/) 註冊並建立 New Project。
2. 進入 Project Settings -> Database，找到 **Connection string (URI)**。
3. 複製並把密碼替換好 (這就是您的 `DATABASE_URL`)。

### 步驟二：一鍵部署至 Render
1. 前往 [Render.com](https://render.com/) 註冊並綁定您的 GitHub 帳號。
2. 點擊 `New +` -> `Blueprint`。
3. 選擇本專案的 GitHub 儲存庫。
4. 系統會自動讀取 `render.yaml`，您只需要在介面上填入以下環境變數 (Environment Variables)：
   - `DATABASE_URL`: (剛才的 Supabase URI)
   - `LINE_CHANNEL_SECRET`: (您的 LINE 機器人 Secret)
   - `LINE_CHANNEL_ACCESS_TOKEN`: (您的 LINE 機器人 Token)
   - `ADMIN_TOKEN`: (自訂管理員密碼)
   - `CRON_TOKEN`: (自訂排程密碼)
   - `KIOSK_TOKEN`: (自訂打卡機密碼)
5. 點擊 Apply，等待約 3 分鐘，您的專案就上線了！(您會獲得一個專屬網址，例如 `https://wenhua-linebot.onrender.com`)

### 步驟三：日常營運 (補習班端)
補習班**不需要做任何安裝**！
1. 打開電腦上的 Chrome 瀏覽器。
2. 進入網址：`https://您的Render網址/static/swipe.html`。
3. 將游標停在輸入框，學生拿卡片嗶下去，家長就會立刻收到 LINE 通知！

---

## 🛠️ 進階開發者專區：單機免安裝版 (Standalone)
如果您因為某些原因無法使用雲端平台，仍可透過我們編譯的免安裝版，在本地電腦運行 (僅限 64 位元 Windows 10/11)。

1. **打包指令**：執行專案內的 `build.bat`。
2. **產出物**：打包完成後，檔案會集中在 `dist/SmartSchoolBot`。
3. **啟動隧道**：您需要自行下載 Zrok (`zrok.exe`) 並執行 `zrok reserve public localhost:8000 --backend-mode proxy` 取得外網穿透網址。
4. **執行伺服器**：雙擊 `SmartSchoolBot.exe` 即可啟動本地伺服器。

---

## 🛡️ 資安防護機制

1. **全分離架構**：不再使用 LINE 官方帳號對話框直接綁定。全面升級為 LIFF 網頁結合「簡訊 OTP」綁定，杜絕任意冒名註冊。
2. **零信任 API**：前端網頁每次呼叫後端皆需夾帶 Bearer Token，並且嚴格驗證來源網域 (CORS Allow Origins)。
3. **防時序攻擊 (Timing Attack)**：密碼驗證全面採用 `secrets.compare_digest`。
4. **離線打卡去重 (`client_swipe_id`)**：解決網路不穩導致的重複推播與重複寫入問題。
