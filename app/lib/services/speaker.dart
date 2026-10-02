import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// Word pronunciation (spec section 7: 翻到背面時自動播放單字真人發音；所有
/// 順位皆無音檔時才使用系統 TTS). Example sentences are never read aloud
/// (移除例句整句發音).
abstract interface class Speaker {
  /// Plays [audioUrl] if there is one, else speaks [text] in [language]
  /// ("en", "fr", "zh-TW"). Never throws.
  Future<void> say(String text, {required String language, String? audioUrl});

  Future<void> stop();
}

class DeviceSpeaker implements Speaker {
  FlutterTts? _tts;
  AudioPlayer? _player;

  static String _locale(String language) => switch (language) {
        'fr' => 'fr-FR',
        'zh-TW' => 'zh-TW',
        // British English is the default playback (spec section 7).
        _ => 'en-GB',
      };

  @override
  Future<void> say(String text,
      {required String language, String? audioUrl}) async {
    await stop();
    if (audioUrl != null && audioUrl.isNotEmpty) {
      try {
        await (_player ??= AudioPlayer()).play(UrlSource(audioUrl));
        return;
      } catch (e) {
        debugPrint('Recording failed, using TTS: $e');
      }
    }
    try {
      final tts = _tts ??= FlutterTts();
      await tts.setLanguage(_locale(language));
      await tts.setSpeechRate(kIsWeb ? 0.8 : 0.45);
      await tts.speak(text);
    } catch (e) {
      debugPrint('TTS unavailable: $e');
    }
  }

  @override
  Future<void> stop() async {
    try {
      await _player?.stop();
      await _tts?.stop();
    } catch (_) {}
  }
}

/// For tests: records what would be said.
class SilentSpeaker implements Speaker {
  final said = <String>[];

  @override
  Future<void> say(String text,
          {required String language, String? audioUrl}) async =>
      said.add(text);

  @override
  Future<void> stop() async {}
}
