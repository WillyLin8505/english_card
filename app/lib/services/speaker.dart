import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

import 'pack_media.dart';

/// Word pronunciation (spec section 7: 翻到背面時自動播放單字真人發音；所有
/// 順位皆無音檔時才使用系統 TTS). Example sentences are never read aloud
/// (移除例句整句發音).
abstract interface class Speaker {
  /// Plays [audioUrl] if there is one, else speaks [text] in [language]
  /// ("en", "fr", "zh-TW"), using [accent] ("en-GB" or "en-US") when
  /// [language] is "en". Never throws; returns false when nothing could be
  /// played (e.g. a browser blocking autoplay) so the caller can tell the
  /// learner there was no sound.
  Future<bool> say(String text,
      {required String language, String? audioUrl, String accent = 'en-GB'});

  Future<void> stop();
}

class DeviceSpeaker implements Speaker {
  FlutterTts? _tts;
  AudioPlayer? _player;

  static String _locale(String language, String accent) => switch (language) {
        'fr' => 'fr-FR',
        'zh-TW' => 'zh-TW',
        _ => accent,
      };

  @override
  Future<bool> say(String text,
      {required String language,
      String? audioUrl,
      String accent = 'en-GB'}) async {
    await stop();
    if (audioUrl != null && audioUrl.isNotEmpty) {
      try {
        final player = _player ??= AudioPlayer();
        // Wait for the clip to end so two accents played in a row (card
        // #251: 英式、美式各一次) do not cut each other off; a clip that
        // never reports completion gives up after a few seconds.
        final Future<void> finished =
            player.onPlayerComplete.first.then<void>((_) {});
        // UrlSource only plays http/file URLs. Bundled clips are Flutter
        // assets; AssetSource's cache already prefixes `assets/`.
        final source = packMediaIsAsset(audioUrl)
            ? AssetSource(audioUrl.substring('assets/'.length))
            : UrlSource(audioUrl);
        await player.play(source);
        await finished.timeout(const Duration(seconds: 6),
            onTimeout: () => null);
        return true;
      } catch (e) {
        debugPrint('Recording failed, using TTS: $e');
      }
    }
    try {
      final tts = _tts ??= FlutterTts();
      // speak()'s own future resolves before the utterance actually
      // finishes on some platforms (notably web), so success/failure is
      // tracked through these handlers instead — on Chrome, a blocked
      // autoplay fires onError rather than rejecting speak() itself.
      final done = Completer<bool>();
      tts.setCompletionHandler(() {
        if (!done.isCompleted) done.complete(true);
      });
      tts.setCancelHandler(() {
        if (!done.isCompleted) done.complete(false);
      });
      tts.setErrorHandler((msg) {
        debugPrint('TTS error: $msg');
        if (!done.isCompleted) done.complete(false);
      });
      await tts.setLanguage(_locale(language, accent));
      await tts.setSpeechRate(kIsWeb ? 0.8 : 0.45);
      await tts.speak(text);
      return await done.future.timeout(const Duration(seconds: 6),
          onTimeout: () => true);
    } catch (e) {
      debugPrint('TTS unavailable: $e');
      return false;
    }
  }

  @override
  Future<void> stop() async {
    try {
      await _player?.stop();
      await _tts?.stop();
    } catch (e) {
      debugPrint('Speaker stop failed: $e');
    }
  }
}

/// For tests: records what would be said.
class SilentSpeaker implements Speaker {
  final said = <String>[];

  @override
  Future<bool> say(String text,
      {required String language,
      String? audioUrl,
      String accent = 'en-GB'}) async {
    said.add(text);
    return true;
  }

  @override
  Future<void> stop() async {}
}
