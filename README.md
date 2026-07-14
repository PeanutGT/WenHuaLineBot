# 智慧親師通系統 (WenHuaLineBot)

本專案是一個專為補習班設計的「零信任資安」打卡與家長通知系統。結合了 **Thin Client (純網頁刷卡介面)** 與 **零依賴單一執行檔 (Standalone Executable)** 技術，讓補習班內的老舊電腦無需安裝任何 Python 或伺服器環境，只需「雙擊執行檔」並開啟瀏覽器即可完美運作。

## 🌟 系統亮點

1. **老舊電腦救星**：無需安裝 Python、pip，無需處理環境變數衝突。系統已打包成免安裝綠色版執行檔。
2. **純網頁刷卡介面**：打卡機只需外接 USB，操作人員只要打開瀏覽器 `http://localhost:8000/static/swipe.html`，即可進行無延遲的刷卡作業。
3. **離線容錯機制**：就算補習班網路突然斷線，網頁端會自動將打卡紀錄暫存於瀏覽器 (LocalStorage) 中，待網路恢復後自動回傳補登，確保資料絕不遺失。
4. **永久固定內網穿透 (Zrok)**：淘汰需時常換網址的 ngrok，改用資安大廠開源的 Zrok，提供免費、穩定且「永久固定」的 Webhook 網址。

---

## 🚀 快速安裝與啟動教學 (給補習班管理者)

### 第一步：準備系統與設定檔

1. 下載本系統的壓縮包 (`dist/SmartSchoolBot.zip`，由開發者打包提供)，並解壓縮到電腦的任意位置（例如桌面）。
2. 在 `SmartSchoolBot` 資料夾內，建立一個名為 `.env` 的文字檔，內容如下：

```env
# LINE 機器人金鑰
LINE_CHANNEL_SECRET=你的_CHANNEL_SECRET
LINE_CHANNEL_ACCESS_TOKEN=你的_ACCESS_TOKEN

# 安全 Token (請自己亂打一長串英文數字，不要外洩)
ADMIN_TOKEN=my_admin_super_secret_123
CRON_TOKEN=my_cron_super_secret_456
KIOSK_TOKEN=my_kiosk_super_secret_789

# 允許跨網域請求的白名單 (包含您的 Zrok 網址)
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://您的專屬Zrok網址.share.zrok.io
```

### 第二步：申請固定穿透網址 (Zrok)

因為 LINE 機器人必須把訊息傳給我們的電腦，我們需要一個穩定的隧道。我們使用免費強大的 [Zrok](https://zrok.io/)。

1. **註冊 Zrok 帳號**：
   前往 [zrok.io](https://zrok.io/) 註冊一個免費帳號。
   
2. **下載 Zrok 客戶端**：
   前往 Zrok 的 GitHub Releases 頁面下載 Windows 版本的 `.zip`，解壓縮後會有一個 `zrok.exe`。建議把這個 `zrok.exe` 放到我們系統的資料夾裡。

3. **登入 Zrok (只需做一次)**：
   打開命令提示字元 (cmd)，輸入註冊後 Zrok 給你的 Enable 指令：
   `zrok enable 你的專屬Token`

4. **申請固定網址 (Reserved Share) (只需做一次)**：
   在命令提示字元輸入：
   `zrok reserve public localhost:8000 --backend-mode proxy`
   *系統會回傳一組永久網址給您，例如：`https://xxyyzz.share.zrok.io`。請把這個網址填入上面的 `.env` 檔案的 `ALLOWED_ORIGINS` 之中。*

5. **更新 LINE Developer Console**：
   前往 LINE 開發者後台，把 Webhook URL 改為：
   `https://您的專屬Zrok網址.share.zrok.io/webhook`

### 第三步：日常啟動流程

以後每天補習班開門，櫃台人員只需要做三件事：

1. **啟動伺服器**：
   雙擊資料夾內的 `SmartSchoolBot.exe`。看到一個黑色視窗寫著 `Application startup complete` 就代表啟動成功。請把它縮小放在背景，不要關閉。
   
2. **啟動 Zrok 隧道**：
   雙擊我們為您準備的 `start_zrok.bat` (內容為 `zrok share reserved 你的Reserved_Token`)。同樣縮小放背景。
   
3. **開啟刷卡網頁**：
   打開 Chrome 瀏覽器，進入 `http://localhost:8000/static/swipe.html`。
   點擊「開始營業」，將游標點入輸入框，學生即可開始刷卡。

---

## 🛠️ 開發者打包指南 (Build Instructions)

若您是開發者，修改了原始碼後需要重新打包，請遵循以下步驟：

1. 確保已安裝 `pyinstaller` (`pip install pyinstaller`)。
2. 確保虛擬環境 (`.venv`) 已經啟動。
3. 執行根目錄的 `build.bat`。
4. 打包完成後，所有檔案會集中在 `dist/SmartSchoolBot` 資料夾中。
5. 發布時，只需將該資料夾打包成 `.zip` 傳給客戶即可。

> 注意：`test.db` (資料庫) 與 `.env` 會在 `SmartSchoolBot.exe` 執行時，自動於「執行檔所在目錄」下尋找與生成。升級新版 `.exe` 時，切記保留舊的 `test.db` 與 `.env`！

---

## 🛡️ 資安防護機制

1. **全分離架構**：不再使用 LINE 官方帳號對話框直接綁定。全面升級為 LIFF 網頁結合「簡訊 OTP」綁定，杜絕任意冒名註冊。
2. **零信任 API**：前端網頁每次呼叫後端皆需夾帶 Bearer Token，並且嚴格驗證來源網域 (CORS Allow Origins)。
3. **防時序攻擊 (Timing Attack)**：密碼驗證全面採用 `secrets.compare_digest`。
4. **離線打卡去重 (`client_swipe_id`)**：解決網路不穩導致的重複推播與重複寫入問題。
