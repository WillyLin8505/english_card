import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_tts/flutter_tts.dart';

class TtsService {
  static FlutterTts? _tts;
  static bool _initialized = false;
  static bool _isAvailable = false;

  static Future<void> init() async {
    if (_initialized) return;

    _tts = FlutterTts();
    
    try {
      if (kIsWeb) {
        _isAvailable = true;
      } else {
        final engines = await _tts!.getEngines;
        _isAvailable = engines != null && (engines as List).isNotEmpty;
      }

      if (_isAvailable) {
        await _tts!.setLanguage('en-US');
        await _tts!.setSpeechRate(0.5);
        await _tts!.setVolume(1.0);
        await _tts!.setPitch(1.0);
      }

      _initialized = true;
    } catch (e) {
      _isAvailable = false;
      _initialized = true;
    }
  }

  static bool get isAvailable => _isAvailable;

  static Future<void> speak(String text) async {
    if (!_initialized) {
      await init();
    }

    if (!_isAvailable || _tts == null) return;

    await _tts!.stop();
    await _tts!.speak(text);
  }

  static Future<void> stop() async {
    if (_tts != null) {
      await _tts!.stop();
    }
  }

  static Future<void> dispose() async {
    if (_tts != null) {
      await _tts!.stop();
    }
  }
}
