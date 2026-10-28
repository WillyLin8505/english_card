import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../l10n/ui_text.dart';
import '../services/connection_qr.dart';

/// 掃描後台產生的連線 QR code。成功時 pop 出 [ConnectionQr]；按返回則不設定。
class ConnectionScanScreen extends StatefulWidget {
  const ConnectionScanScreen({super.key});

  @override
  State<ConnectionScanScreen> createState() => _ConnectionScanScreenState();
}

class _ConnectionScanScreenState extends State<ConnectionScanScreen> {
  final _controller = MobileScannerController();
  bool _done = false;
  String? _hint;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_done) return;
    for (final barcode in capture.barcodes) {
      final raw = barcode.rawValue;
      if (raw == null) continue;
      final parsed = ConnectionQr.parse(raw);
      if (parsed != null) {
        _done = true;
        Navigator.of(context).pop(parsed);
        return;
      }
    }
    setState(() => _hint = '這不是連線設定的 QR code，請掃描電腦上產生的那一個。');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const UiText('掃描連線 QR code')),
      body: Stack(
        alignment: Alignment.bottomCenter,
        children: [
          MobileScanner(controller: _controller, onDetect: _onDetect),
          if (_hint != null)
            Padding(
              padding: const EdgeInsets.all(24),
              child: Container(
                padding: const EdgeInsets.all(12),
                color: Colors.black54,
                child:
                    UiText(_hint!, style: const TextStyle(color: Colors.white)),
              ),
            ),
        ],
      ),
    );
  }
}
