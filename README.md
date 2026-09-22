# 拍照學英文

用喜歡的照片學英文。選擇照片後，AI 會辨識其中物品並產生英文標籤，自動儲存到本機相簿。點擊英文單字可聽發音。

## 功能

### Knife 1：照片辨識
- 從相簿選擇照片或直接拍照
- 自動壓縮圖片（最長邊 1280px，≤500KB）
- 呼叫標籤 API 辨識照片內容
- 顯示最多 5 個可編輯的英文標籤
- 錯誤處理與重試機制
- Mock 模式支援離線測試

### Knife 2：本機相簿 + TTS
- 辨識成功後自動儲存到本機相簿
- 相簿列表：重新開啟 App 後資料仍在
- 照片詳情頁：可編輯標籤並覆寫儲存
- 點擊英文單字 → 播放 TTS 發音（en-US）
- 資料完全在裝置本機，不上傳雲端

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
  --dart-define=LABEL_API_BASE=http://127.0.0.1:8765 \
  --dart-define=LABEL_API_KEY=YOUR_KEY
```

**注意**：`LABEL_API_BASE` 可能是 Cloudflare quick tunnel 或本機伺服器，請向服務提供者取得最新網址。

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

### Knife 1：Mock 模式

1. 執行 `flutter run`
2. 點擊「相簿」選擇照片
3. 等待約 0.8 秒，顯示 Mock 標籤
4. 點擊編輯圖示修改標籤
5. 確認底部顯示「Mock 模式」

### Knife 1：Live 模式

1. 取得 API Base URL 與 Key
2. 執行：
   ```bash
   flutter run \
     --dart-define=MOCK_LABEL=false \
     --dart-define=LABEL_API_BASE=http://127.0.0.1:8765 \
     --dart-define=LABEL_API_KEY=your-key
   ```
3. 選擇照片後確認標籤來自真實 API
4. 確認底部顯示連接的主機名稱

### Knife 2：相簿持久化

1. 選擇照片並完成辨識（Mock 或 Live 皆可）
2. 辨識成功後會自動儲存到相簿
3. 點擊右上角相簿圖示進入「我的相簿」
4. 確認照片和標籤已儲存
5. 完全關閉 App 後重新開啟
6. 進入相簿，確認資料仍在

### Knife 2：標籤編輯

1. 在相簿列表點擊任一照片
2. 進入詳情頁，點擊標籤旁的編輯圖示
3. 修改英文或中文標籤
4. 點擊打勾儲存
5. 點擊右上角儲存圖示確認變更
6. 返回相簿或重啟 App，確認變更已保留

### Knife 2：TTS 發音

1. 在辨識結果頁或詳情頁
2. 點擊英文單字（會顯示小喇叭圖示）
3. 聽到英文發音（en-US）

### 錯誤重試

1. Live 模式下，若 API 回傳錯誤，會顯示錯誤訊息與重試按鈕
2. 點擊「重試」會重新送出請求

## 已知限制

### Web 平台
- **TTS**：依賴瀏覽器的 Web Speech API，部分瀏覽器可能不支援或發音品質不同
- **儲存空間**：使用 IndexedDB（Hive），瀏覽器可能有配額限制（通常 50MB+）
- **圖片選擇**：使用檔案選擇器，無原生相簿/相機整合

### 建議開發環境
- **Windows/Chrome**：Web 開發首選，TTS 與儲存相容性最佳
- **iOS/Android**：完整功能支援，TTS 使用系統 TTS 引擎

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
├── main.dart                    # 應用程式進入點
├── models/
│   ├── label.dart               # 標籤資料模型
│   ├── label_response.dart      # API 回應模型
│   └── album_entry.dart         # 相簿項目模型
├── services/
│   ├── config_service.dart      # 設定管理
│   ├── compression_service.dart # 圖片壓縮
│   ├── label_service.dart       # 標籤 API
│   ├── album_service.dart       # 本機相簿持久化
│   └── tts_service.dart         # TTS 語音服務
├── screens/
│   ├── home_screen.dart         # 主畫面
│   ├── album_list_screen.dart   # 相簿列表
│   └── album_detail_screen.dart # 照片詳情
└── widgets/
    ├── label_card.dart          # 標籤卡片元件
    └── error_view.dart          # 錯誤顯示元件
```

## 技術細節

- Flutter 3.47+
- iOS 優先，Android/Web 可運行
- 圖片壓縮：最長邊 1280px，JPEG quality 75（必要時降低），目標 ≤500KB
- API 請求逾時：60 秒
- 本機儲存：Hive（IndexedDB on Web，檔案系統 on mobile）
- TTS：flutter_tts（en-US）

## 資料形狀

```dart
AlbumEntry {
  String id;
  DateTime createdAt;
  String imagePath;
  List<Label> labels;
}

Label {
  String en;
  String? zh;
  double? confidence;
}
```

## 授權

Private
