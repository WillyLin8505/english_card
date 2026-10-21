import '../models/word_entry.dart';
import 'lexicon_pack.dart';
import 'pack_media.dart';

/// Recording accent labels that count as [accent] ("en-GB" / "en-US").
Set<String> _aliases(String accent) =>
    accent == 'en-GB' ? const {'uk', 'gb', 'en-gb'} : const {'us', 'en-us'};

/// The pack recording of [source] in [accent]. With [allowUnlabelled], a
/// recording without an accent label is used when none is labelled
/// [accent]; one labelled with another accent never is (問題回報 #510).
String? packAccentAudioUrl(LexEntry source, String accent,
    {bool allowUnlabelled = false}) {
  final aliases = _aliases(accent);
  final recording = source.recordings
          .where((r) => aliases.contains(r.accent?.toLowerCase()))
          .firstOrNull ??
      (allowUnlabelled
          ? source.recordings
              .where((r) => (r.accent ?? '').trim().isEmpty)
              .firstOrNull
          : null);
  if (recording == null) return null;
  return packRecordingUrl(LexiconPack.instance.mediaBase, recording.path);
}

/// The language pack's recording of [entry] in [accent] ("en-GB" /
/// "en-US"), or the entry's own audio when it is in that accent; null
/// means the speaker falls back to TTS in that accent.
String? accentAudioUrl(WordEntry entry, String accent,
    {bool allowUnlabelled = false}) {
  final pack = LexiconPack.instance;
  final source = (entry.lexemeId == null ? null : pack.byId(entry.lexemeId!)) ??
      pack.lookup(entry.word, pos: entry.pos)?.entry;
  if (source != null && source.recordings.isNotEmpty) {
    return packAccentAudioUrl(source, accent,
        allowUnlabelled: allowUnlabelled);
  }
  final own = entry.accent?.toLowerCase();
  if (_aliases(accent).contains(own)) return entry.audioUrl;
  if (allowUnlabelled && (own ?? '').isEmpty) return entry.audioUrl;
  return null;
}
