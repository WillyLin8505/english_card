import 'dart:convert';

/// 首次連線用的 QR code 內容，由後台／筆電端產生（見
/// `lexicon/tools/make_connect_qr.py`）：
/// `{"v":1,"taggingUrl":"https://…/tag","apiKey":"…"}`。
class ConnectionQr {
  const ConnectionQr({required this.taggingUrl, required this.apiKey});

  final String taggingUrl;
  final String apiKey;

  static const version = 1;

  /// 不是連線設定的 QR code（或格式不對）回 null，讓掃描頁繼續等下一個。
  static ConnectionQr? parse(String raw) {
    try {
      final data = jsonDecode(raw);
      if (data is! Map || data['v'] != version) return null;
      final url = data['taggingUrl'];
      final key = data['apiKey'];
      if (url is! String || key is! String) return null;
      final uri = Uri.tryParse(url.trim());
      if (uri == null || !uri.hasScheme || uri.host.isEmpty) return null;
      if (key.trim().isEmpty) return null;
      return ConnectionQr(taggingUrl: url.trim(), apiKey: key.trim());
    } on FormatException {
      return null;
    }
  }
}
