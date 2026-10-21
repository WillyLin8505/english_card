import '../models/word_entry.dart';
import 'lexicon_pack.dart';
import 'pack_media.dart';

/// Recording accent labels that count as [accent] ("en-GB" / "en-US").
Set<String> _aliases(String accent) =>
    accent == 'en-GB' ? const {'uk', 'gb', 'en-gb'} : const {'us', 'en-us'};

/// The pack recording of [source] in [accent]. With [orDefault], a word
/// without one plays its default recording (British first, #20/#56) rather
/// than TTS: 有該腔調的音檔就用，否則用現有音檔，最後才用 TTS.
String? packAccentAudioUrl(LexEntry source, String accent,
    {bool orDefault = false}) {
  final aliases = _aliases(accent);
  final recording = source.recordings
          .where((r) => aliases.contains(r.accent?.toLowerCase()))
          .firstOrNull ??
      (orDefault ? source.recordings.firstOrNull : null);
  if (recording == null) return null;
  return packRecordingUrl(LexiconPack.instance.mediaBase, recording.path);
}

/// The language pack's recording of [entry] in [accent] ("en-GB" /
/// "en-US"), or the entry's own audio when it is in that accent (or, with
/// [orDefault], whatever its accent); null means TTS in that accent.
String? accentAudioUrl(WordEntry entry, String accent,
    {bool orDefault = false}) {
  final pack = LexiconPack.instance;
  final source = (entry.lexemeId == null ? null : pack.byId(entry.lexemeId!)) ??
      pack.lookup(entry.word, pos: entry.pos)?.entry;
  if (source != null && source.recordings.isNotEmpty) {
    return packAccentAudioUrl(source, accent, orDefault: orDefault);
  }
  if (orDefault || _aliases(accent).contains(entry.accent?.toLowerCase())) {
    return entry.audioUrl;
  }
  return null;
}
