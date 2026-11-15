# 個人 AI 加密貨幣交易系統（Personal AI Crypto Trading System）

這是一套「低成本、AI 輔助」的加密貨幣技術分析與新聞情報系統。
**目前版本（Phase 1 + Phase 1.1 + Phase 2）只做市場分析與新聞分析，不會下單、不會真實交易。**

## 安全原則（非常重要）

本專案目前版本遵守以下安全規則：

- 只讀取 Binance **公開** 市場資料與公開的新聞 RSS，**不需要**、也**不會要求**你輸入任何交易所 API Key 或 API Secret。
- **沒有任何真實下單 / 真實交易功能**。
- **不支援合約（Futures）或槓桿（Leverage）**。
- 程式碼中不會包含任何密鑰或敏感資訊，`.gitignore` 已設定避免誤傳 `.env`、金鑰、本地新聞資料庫（`data/`）等檔案到 GitHub。
- OpenAI API Key（如果你選擇使用AI新聞分析）只透過環境變數 `OPENAI_API_KEY` 讀取，**絕對不會寫進程式碼或任何會被commit的檔案**。

未來若要加入「新聞分析」「回測」「模擬交易（paper trading）」「風險管理」等功能，會在之後的階段逐步加入，
現在這一版只專注在「看得懂市場」這件事。

## 這個版本做了什麼

1. 從 Binance 公開 API 抓取 **BTC/USDT、ETH/USDT、SOL/USDT、XRP/USDT** 的 K 線（OHLCV：開盤/最高/最低/收盤/成交量）資料。
2. 計算四個技術指標：
   - EMA 20（20 期指數移動平均線）
   - EMA 50（50 期指數移動平均線）
   - RSI 14（14 期相對強弱指標）
   - MACD（指數平滑異同移動平均線）
3. 根據以上指標，自動產生一段簡單的文字說明（例如：目前偏多/偏空、是否過熱/過冷）。
4. 用 Streamlit 做了一個網頁儀表板，可以：
   - 選擇幣種、K 線週期（15分/1小時/4小時/1天）
   - 看到蠟燭圖（candlestick chart）、EMA 線
   - 看到 RSI、MACD 圖表
   - 看到最新數值與文字摘要
5. 加入了基本的錯誤處理（例如網路斷線、API 回應異常）。
6. **只使用「已經收盤」的 K 棒資料來計算指標與摘要**：Binance 回傳的最新一根 K 棒常常還「正在走」（還沒收盤），如果拿這種還在變動的資料去算 EMA/RSI/MACD，數值會一直跳動、產生誤導性的訊號。本系統會向 Binance 查詢伺服器時間（而不是依賴你電腦本身的時區設定），自動排除還沒收盤的那一根 K 棒，並在儀表板上明確標示「目前顯示的都是已收盤資料」。
7. 加入了 38 個自動化測試（pytest），確保指標計算、資料抓取邏輯、以及「排除未收盤K棒」的邏輯都正確。
8. **強化了對 Binance API 速率限制的處理**：遇到 HTTP 429（請求太頻繁）或 418（暫時被限制）時，會依照 Binance 回應的等待時間自動重試（最多重試 2 次，不會無限重試），重試仍失敗才會顯示錯誤。
9. **K 線週期（interval）會先驗證才送出請求**：只接受 15 分 / 1 小時 / 4 小時 / 1 天這四種週期，不合法的週期會直接被拒絕，不會浪費一次 API 請求。
10. **RSI 的邊界情況修正**：價格完全不漲不跌時，RSI 會正確顯示中性值 50（原本會誤判成 100）。

## Phase 2：AI 新聞情報模組

這個階段加入了「新聞情報」功能，**完全獨立於交易功能**，純粹是收集、分類、分析新聞，不會下單、不會自動交易：

1. **新聞收集**：從多個免費的公開 RSS 新聞源（CoinDesk、Cointelegraph、Decrypt、CryptoSlate）抓取文章標題、來源、發布時間、原文連結、摘要，**不需要任何付費新聞API**。
2. **本地分類（不花錢、不用AI）**：
   - 自動判斷文章跟 BTC / ETH / SOL / XRP 哪些幣種有關（也可能跟任何一個都無關，不會硬套）。
   - 自動分類成「ETF/機構動向」「監管政策」「交易所/市場」「技術生態」「安全事件」「宏觀經濟」等類別。
3. **AI 新聞分析（選用，需要 OpenAI API Key）**：
   - 使用 OpenAI API，針對使用者**手動點擊**的文章產生結構化分析：情緒（看漲/看跌/中性/混合）、影響程度、信心分數（0-100）、可能的市場影響、影響時間長短、推理依據等。
   - AI 分析結果會被清楚標示「這是推測還是確定事實」，**不會聲稱某個新聞「保證」會造成價格變動**。
4. **成本控制**（因為 OpenAI 預算只有約 5 美元）：
   - AI 分析**只在使用者按下按鈕時才會執行**，不會有背景程式持續呼叫 API。
   - 同一篇文章分析過一次後會被快取（存在本地 SQLite 資料庫），**不會重複分析、重複花錢**。
   - 每次點擊分析的文章數量有上限（可調整，預設 5 篇，最多 20 篇）。
   - 沒有設定 `OPENAI_API_KEY` 時，新聞收集與分類功能依然正常運作，只是AI分析那部分會顯示提示訊息，不會讓整個程式出錯。
5. 新聞與分析結果都存在本地的 SQLite 資料庫（`data/news.db`，已加入 `.gitignore`，不會上傳到 GitHub）。
6. Streamlit 儀表板新增了「News Intelligence」頁籤，原本的市場數據頁籤完全沒有被動到。

## 專案結構

```
.
├── app.py                      # Streamlit 儀表板主程式
├── requirements.txt            # 需要安裝的 Python 套件
├── src/
│   ├── config.py                # 設定（支援的幣種、參數），不含任何密鑰
│   ├── data/
│   │   └── binance_client.py    # 向 Binance 公開 API 抓取 OHLCV 資料
│   ├── indicators/
│   │   └── technical.py         # EMA / RSI / MACD 計算
│   ├── analysis/
│   │   └── summary.py           # 產生文字版技術摘要
│   └── news/                     # Phase 2：新聞情報模組
│       ├── config.py             # RSS來源、分類關鍵字、OpenAI設定（不含密鑰）
│       ├── models.py             # Article / NewsAnalysis 資料結構
│       ├── rss_fetcher.py        # 抓取並正規化 RSS 新聞
│       ├── classifier.py         # 幣種識別 + 事件分類（純本地規則，不花錢）
│       ├── storage.py            # SQLite 儲存文章與AI分析快取
│       ├── collector.py          # 串接「抓取→分類→儲存」的整合流程
│       └── ai_analyst.py         # OpenAI 整合：產生結構化分析、驗證格式、快取
└── tests/
    ├── test_binance_client.py
    ├── test_technical.py
    ├── test_summary.py
    ├── test_news_rss_fetcher.py
    ├── test_news_classifier.py
    ├── test_news_storage.py
    └── test_news_ai_analyst.py
```

這樣的模組化設計，是為了讓之後要加「新聞分析」「回測」「模擬交易」「風險管理」時，
可以直接新增模組（例如 `src/news/`、`src/backtest/`、`src/paper_trading/`、`src/risk/`），
不需要重寫現有的程式碼。

## 在 Windows 上安裝與執行（步驟教學）

### 第一步：安裝 Python

1. 前往 [https://www.python.org/downloads/](https://www.python.org/downloads/) 下載並安裝 Python（建議 3.10 以上版本）。
2. 安裝時記得勾選 **「Add Python to PATH」**。
3. 安裝完成後，打開「命令提示字元」（在開始選單搜尋 `cmd`），輸入：

   ```
   python --version
   ```

   能看到版本號（例如 `Python 3.11.5`）就代表安裝成功。

### 第二步：下載本專案

如果你已經有這個資料夾，直接跳到第三步。
如果需要從 GitHub 下載，可以用瀏覽器點 GitHub 頁面上的「Code → Download ZIP」，解壓縮後進入資料夾。

### 第三步：建立虛擬環境（建議，但非必要）

在命令提示字元中，切換到專案資料夾，例如：

```
cd C:\Users\你的使用者名稱\Downloads\ai-crypto-trading-system
```

建立並啟用虛擬環境：

```
python -m venv venv
venv\Scripts\activate
```

啟用成功後，命令列前面會出現 `(venv)` 字樣。

### 第四步：安裝套件

```
pip install -r requirements.txt
```

這會自動安裝 Streamlit、Pandas、Requests、Plotly、Pytest、feedparser 等必要套件。

### 第五步（選用）：設定 OpenAI API Key，啟用AI新聞分析

**這一步可以跳過** — 不設定的話，新聞收集與分類功能一樣正常運作，只是不會有AI分析。

如果你有 OpenAI API Key，想啟用 AI 新聞分析，在命令提示字元中執行（**只在目前這個視窗/這次執行有效**，不會寫入任何檔案）：

```
set OPENAI_API_KEY=你的金鑰
```

注意：
- 這個指令**不會**把金鑰存到程式碼或任何會被上傳到 GitHub 的檔案裡。
- 關掉命令提示字元視窗後這個設定就會消失，下次要用的話要重新輸入一次。
- 金鑰絕對不要貼到程式碼裡、不要commit到GitHub。

### 第六步：執行測試（確認一切正常）

```
pytest
```

如果看到類似 `90 passed`（或未來測試數量增加後的 `N passed`，沒有出現 `failed`）的訊息，代表程式邏輯測試全部通過。

### 第七步：啟動儀表板

```
streamlit run app.py
```

執行後，命令列會顯示一個網址（通常是 `http://localhost:8501`），
Streamlit 通常會自動幫你打開瀏覽器；如果沒有自動打開，手動複製網址到瀏覽器開啟即可。

### 第八步：使用儀表板

儀表板現在有兩個頁籤：

**📈 Market Data（市場數據）**
1. 左側選單選擇想看的幣種（BTC/ETH/SOL/XRP）與 K 線週期。
2. 右側會顯示最新的技術指標數值與文字摘要。
3. 想重新抓取最新資料時，點擊左側的「Refresh data」按鈕。

**📰 News Intelligence（新聞情報）**
1. 點擊「🔄 Refresh news」抓取各新聞源最新文章（會自動分類幣種與事件類別，去除重複文章）。
2. 如果有設定 OpenAI API Key，可以設定「每次分析幾篇文章」後，點擊「🤖 Analyze with AI」，針對還沒分析過的文章產生AI分析（已經分析過的文章不會重複花錢分析）。
3. 每篇文章卡片會顯示：標題（可點擊連到原文）、來源與時間、幣種標籤、事件類別、AI情緒與信心分數（如果有分析過）、展開可看完整AI推理內容。

## 常見問題

- **抓不到資料 / 顯示錯誤訊息**：通常是網路連線問題，或 Binance API / RSS 新聞源暫時無法連線。請檢查網路，稍後再試。
- **想關掉程式**：回到命令提示字元視窗，按 `Ctrl + C`。
- **會不會不小心真的下單？**：不會。目前版本完全沒有下單功能，也沒有連接任何交易所帳戶或金鑰，只讀取公開市場資料與公開新聞。
- **AI分析按鈕沒反應/顯示警告**：檢查是否已設定 `OPENAI_API_KEY`；如果額度用完（quota exceeded）或金鑰錯誤，畫面會顯示清楚的警告訊息，不會讓程式當掉。
- **新聞資料存在哪裡？**：存在專案資料夾下的 `data/news.db`（SQLite資料庫檔案），這個檔案不會被上傳到GitHub。

## 免責聲明

本系統產生的所有文字摘要與指標數值，僅供技術分析學習與參考使用，**不構成任何投資建議**，
加密貨幣市場風險極高，請自行判斷並承擔投資風險。
