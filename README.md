# 智慧親師通 (Smart School LINE Bot)

這是一套專為補習班/安親班打造的「智慧打卡與家長通知系統」。整合了實體感應卡打卡、自動 Excel 報表結算，以及 LINE Bot 自動推播，協助補習班以最低的成本達成最高效率的數位化管理。

## 🌟 系統特色

1. **一鍵 Excel 同步**：免去繁瑣的建檔，只要將包含「學號」、「卡號」、「姓名」、「家長手機」的 Excel 檔案放入系統，按下一鍵即可完成數百人的資料庫建立。
2. **防走失警示**：每日晚上定時巡邏，若學生有進班但未離班，將自動推播警示家長。
3. **每日出勤批次結算**：將同一家庭一整天的多筆打卡紀錄濃縮成「一封信」發送，極大化節省 LINE 推播費用。
4. **營業安全控制**：打卡機具備「鎖定」與「解鎖」功能，避免非營業時段的誤刷。
5. **打烊自動結算**：每日結束營業時，系統自動將今日所有打卡紀錄備份成 Excel 報表供作帳。

---

## 💻 系統硬體與環境需求

- **作業系統**：Windows 10 / 11
- **硬體需求**：一般櫃台行政電腦即可，需具備對外網路連線與 USB 讀卡機/掃描槍。
- **必備軟體**：[Python 3.10+](https://www.python.org/)、[Ngrok](https://ngrok.com/)。

---

## 🚀 第一次建置：完整安裝與設定指南

為了確保系統能在櫃台電腦上穩定且長期運行，請負責建置的主管或 IT 人員嚴格依照以下步驟依序設定。

### 第一步：安裝 Python 語言環境
本系統由 Python 驅動，因此必須安裝 Python 環境。
1. 前往 [Python 官方網站](https://www.python.org/downloads/) 下載最新版 Python for Windows (建議 3.10 或以上)。
2. 啟動安裝程式時，畫面最下方會有一個 **「Add python.exe to PATH」** 的選項，**⚠️ 請務必打勾（極度重要）**，然後再點擊「Install Now」。
3. 安裝完成後，將本專案資料夾解壓縮並放置於櫃台電腦的 `C:` 或 `D:` 槽（路徑請盡量避免使用全中文名稱）。

### 第二步：申請與設定 LINE 商業官方帳號
1. 進入 [LINE Developers Console](https://developers.line.biz/) 並登入您的 LINE 帳號。
2. 點擊 `Create a new provider`，並在該 Provider 下創建一個 **Messaging API channel**（這將是您的補習班官方帳號）。
3. 進入該 Channel 的設定頁面，完成以下金鑰擷取與設定：
   - 到 **Basic settings** 分頁，往下滑找到 `Channel secret`，將其複製備用。
   - 到 **Messaging API** 分頁：
     - 找到 `Channel access token`，點擊 **Issue** 產生一組長代碼並複製備用。
     - 在下方的 **LINE Official Account features** 中，將「Auto-reply messages（自動回覆訊息）」點擊 Edit 設為 **停用 (Disabled)**，並確保「Webhooks」設為 **啟用 (Enabled)**。

### 第三步：申請 Ngrok 固定網址 (突破內網防火牆)
因為 LINE 的雲端伺服器必須要能連線到您補習班的櫃台電腦，我們必須使用 Ngrok 服務建立安全通道。為了避免每天網址一直變動，請務必領取免費的固定網址。
1. 前往 [Ngrok 官網](https://ngrok.com/) 免費註冊帳號並登入。
2. 進入儀表板後，點擊左側選單的 **Cloud Edge** -> **Domains**。
3. 點擊 **Create Domain**，系統會免費配發一個專屬您的固定網址 (例如：`heroic-frog-upward.ngrok-free.app`)，請把這串網址複製記錄下來。
4. 點擊左側選單的 **Getting Started** -> **Your Authtoken**，複製您的 Authtoken。
5. 下載 Ngrok Windows 版本並解壓縮出 `ngrok.exe`。打開命令提示字元 (cmd)，輸入以下指令綁定您的帳號：
   ```bash
   ngrok config add-authtoken <您的Authtoken>
   ```

### 第四步：專案機密金鑰配置 (.env)
1. 在本專案的最外層目錄下，尋找或新增一個檔名為 `.env` 的文字檔。
2. 將剛才收集到的 LINE 金鑰填入（請勿包含引號或多餘空格）：
   ```env
   LINE_CHANNEL_SECRET=您的_Channel_Secret
   LINE_CHANNEL_ACCESS_TOKEN=您的_Access_Token
   DATABASE_URL=sqlite:///./school.db
   ```
3. 找到專案內的 **`啟動智慧親師通.bat`** 檔案，按右鍵選「編輯」，將裡面 ngrok 指令的 `--domain=` 後面，換成您在第三步領取到的**固定網址**並存檔。

### 第五步：設定 LINE Webhook URL 並初始化系統
1. 在專案資料夾內打開命令提示字元 (cmd)，執行以下指令建立環境與套件：
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. 將補習班的學生名單存成 `學生資料.xlsx`，並放到專案的 `excels/` 資料夾內。
   *(必須包含欄位：`學號`、`姓名`、`卡號`、`爸爸手機` / `媽媽手機` / `簡訊電話1`，手機號碼需為09開頭)*
3. 點擊執行 **`啟動智慧親師通.bat`**，讓伺服器與 Ngrok 順利運行。
4. 回到 [LINE Developers Console](https://developers.line.biz/) 的 Messaging API 分頁。找到 **Webhook settings**，在 Webhook URL 欄位填入：
   `https://<您申請的Ngrok固定網址>/callback`
   *(例如：https://heroic-frog-upward.ngrok-free.app/callback)*
5. 點擊 **Verify** 按鈕測試連線，顯示 Success 即代表整套系統串接完美成功！

---

## 🎯 櫃台每日操作 SOP

這套系統建置完成後，日常的櫃台操作非常防呆且簡單，每天只需遵循以下三步：

1. **啟動系統**
   - 點擊桌面上的 **`啟動智慧親師通.bat`** 捷徑。
   - 系統會自動彈出三個黑色視窗（伺服器、排程器與 Ngrok 連線），**請勿關閉這些黑視窗**，只要縮小即可。
   - 瀏覽器會自動彈出打卡畫面。

2. **開始營業 (解鎖)**
   - 點選打卡網頁左上角的 **「▶️ 開始營業」**，此時打卡機輸入框才會發亮解鎖。
   - 學生即可拿感應卡靠近讀卡機「嗶」一聲完成打卡。

3. **結束營業 (結算)**
   - 打烊時，點選左上角的 **「⏹️ 結束營業並結算」**。
   - 系統會立刻鎖定打卡機（避免誤刷），並將今日所有打卡紀錄備份到專案的 `excels/Students/` 目錄下（檔名會自動標註日期）。
   - 確認畫面上跳出「報表已儲存」後，即可安心關閉網頁與所有黑色視窗，完成一天的工作！
