# 拍照學英文

用喜歡的照片學英文。選擇照片後，AI 會辨識其中物品並產生英文標籤。

## 功能（Knife 1）

- 從相簿選擇照片或直接拍照
- 自動壓縮圖片（最長邊 1280px，≤500KB）
- 呼叫標籤 API 辨識照片內容
- 顯示最多 5 個可編輯的英文標籤
- 錯誤處理與重試機制
- Mock 模式支援離線測試

## 快速開始

### Mock 模式（離線測試）

預設使用 Mock 模式，無需設定即可測試 UI：

```bash
flutter run
```

### Live 模式（連接真實 API）

使用 `--dart-define` 設定 API 參數：

```bash
flutter run \
  --dart-define=MOCK_LABEL=false \
  --dart-define=LABEL_API_BASE=https://your-tunnel.trycloudflare.com \
  --dart-define=LABEL_API_KEY=YOUR_KEY
```

**注意**：`LABEL_API_BASE` 是 Cloudflare quick tunnel 網址，可能會變動，請向服務提供者取得最新網址。

## 設定參數

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `MOCK_LABEL` | 是否使用 Mock 模式 | `true` |
| `LABEL_API_BASE` | 標籤 API 的 Base URL | （空） |
| `LABEL_API_KEY` | API 金鑰 | （空） |

當 `MOCK_LABEL=false` 且 `LABEL_API_BASE` 與 `LABEL_API_KEY` 皆已設定時，才會連接真實 API。

## API 規格

### 標籤辨識

```
POST {LABEL_API_BASE}/v1/label
Header: X-API-Key: {LABEL_API_KEY}
Content-Type: multipart/form-data
Body: image (JPEG file)
```

成功回應：
```json
{
  "ok": true,
  "labels": [
    { "en": "cup", "zh": "杯子", "confidence": 0.91 }
  ],
  "model": "model-name",
  "latency_ms": 1234
}
```

失敗回應：
```json
{
  "ok": false,
  "error": {
    "code": "timeout",
    "message": "Request timed out"
  }
}
```

錯誤代碼：`timeout` | `upstream` | `bad_image` | `queue_full` | `unavailable`

### 健康檢查（選用）

```
GET {LABEL_API_BASE}/health
```

## 手動測試步驟

### Mock 模式

1. 執行 `flutter run`
2. 點擊「相簿」選擇照片
3. 等待約 0.8 秒，顯示 Mock 標籤
4. 點擊編輯圖示修改標籤
5. 確認底部顯示「Mock 模式」

### Live 模式

1. 取得 API Base URL 與 Key
2. 執行：
   ```bash
   flutter run \
     --dart-define=MOCK_LABEL=false \
     --dart-define=LABEL_API_BASE=https://xxx.trycloudflare.com \
     --dart-define=LABEL_API_KEY=your-key
   ```
3. 選擇照片後確認標籤來自真實 API
4. 確認底部顯示連接的主機名稱

### 錯誤重試

1. 在 Mock 模式下無法測試真實錯誤
2. Live 模式下，若 API 回傳錯誤，會顯示錯誤訊息與重試按鈕
3. 點擊「重試」會重新送出請求

## 開發

### 執行測試

```bash
flutter test
```

### 程式碼分析

```bash
flutter analyze
```

## 專案結構

```
lib/
├── main.dart              # 應用程式進入點
├── models/
│   ├── label.dart         # 標籤資料模型
│   ├── label_response.dart # API 回應模型
│   └── album_entry.dart   # 相簿項目模型（Knife 2 預留）
├── services/
│   ├── config_service.dart     # 設定管理
│   ├── compression_service.dart # 圖片壓縮
│   └── label_service.dart      # 標籤 API
├── screens/
│   └── home_screen.dart   # 主畫面
└── widgets/
    ├── label_card.dart    # 標籤卡片元件
    └── error_view.dart    # 錯誤顯示元件
```

## 技術細節

- Flutter 3.47+
- iOS 優先，Android 可運行
- 圖片壓縮：最長邊 1280px，JPEG quality 75（必要時降低），目標 ≤500KB
- API 請求逾時：60 秒

## 授權

Private
