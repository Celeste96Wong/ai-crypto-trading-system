# 個人 AI 加密貨幣交易系統（Personal AI Crypto Trading System）

這是一套「低成本、AI 輔助」的加密貨幣技術分析系統。
**目前版本（Phase 1 MVP）只做市場分析，不會下單、不會真實交易。**

## 安全原則（非常重要）

本專案目前版本遵守以下安全規則：

- 只讀取 Binance **公開** 市場資料，**不需要**、也**不會要求**你輸入任何 API Key 或 API Secret。
- **沒有任何真實下單 / 真實交易功能**。
- **不支援合約（Futures）或槓桿（Leverage）**。
- 程式碼中不會包含任何密鑰或敏感資訊，`.gitignore` 已設定避免誤傳 `.env`、金鑰等檔案到 GitHub。

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
7. 加入了 20 個自動化測試（pytest），確保指標計算、資料抓取邏輯、以及「排除未收盤K棒」的邏輯都正確。

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
│   └── analysis/
│       └── summary.py           # 產生文字版技術摘要
└── tests/
    ├── test_binance_client.py
    ├── test_technical.py
    └── test_summary.py
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

這會自動安裝 Streamlit、Pandas、Requests、Plotly、Pytest 等必要套件。

### 第五步：執行測試（確認一切正常）

```
pytest
```

如果看到類似 `20 passed`（或未來測試數量增加後的 `N passed`，沒有出現 `failed`）的訊息，代表程式邏輯測試全部通過。

### 第六步：啟動儀表板

```
streamlit run app.py
```

執行後，命令列會顯示一個網址（通常是 `http://localhost:8501`），
Streamlit 通常會自動幫你打開瀏覽器；如果沒有自動打開，手動複製網址到瀏覽器開啟即可。

### 第七步：使用儀表板

1. 左側選單選擇想看的幣種（BTC/ETH/SOL/XRP）與 K 線週期。
2. 右側會顯示最新的技術指標數值與文字摘要。
3. 想重新抓取最新資料時，點擊左側的「Refresh data」按鈕。

## 常見問題

- **抓不到資料 / 顯示錯誤訊息**：通常是網路連線問題，或 Binance API 暫時無法連線。請檢查網路，稍後再試。
- **想關掉程式**：回到命令提示字元視窗，按 `Ctrl + C`。
- **會不會不小心真的下單？**：不會。目前版本完全沒有下單功能，也沒有連接任何交易所帳戶或金鑰，只讀取公開市場資料。

## 免責聲明

本系統產生的所有文字摘要與指標數值，僅供技術分析學習與參考使用，**不構成任何投資建議**，
加密貨幣市場風險極高，請自行判斷並承擔投資風險。
