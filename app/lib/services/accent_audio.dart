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

/// The IPA of [source] in [accent] (卡 #227 第 147 輪): the first pack IPA
/// in that accent, else the default one — 美式 used to show the British
/// /ˈkʌvə/ next to the American recording.
String? packAccentIpa(LexEntry source, String accent) {
  final aliases = _aliases(accent);
  return source.ipas
          .where((p) => aliases.contains(p.accent?.toLowerCase()))
          .firstOrNull
          ?.value ??
      source.ipa;
}

/// [entry]'s IPA in [accent], from its pack lexeme when there is one. An
/// IPA the learner typed, or one the pack doesn't have, is kept as is.
String? accentIpa(WordEntry entry, String accent) {
  if (entry.ipaSource == 'user') return entry.ipa;
  final pack = LexiconPack.instance;
  final source = (entry.lexemeId == null ? null : pack.byId(entry.lexemeId!)) ??
      pack.lookup(entry.word, pos: entry.pos)?.entry;
  if (source == null || source.ipas.isEmpty) return entry.ipa;
  final own = entry.ipa?.trim();
  if (own != null && own.isNotEmpty && !source.ipas.any((p) => p.value == own)) {
    return entry.ipa;
  }
  return packAccentIpa(source, accent) ?? entry.ipa;
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

/// The credit of the recording [accentAudioUrl] plays for [entry] in
/// [accent] (問題回報 #657): null for TTS or a recording with no credit.
RecordingCredit? accentAudioCredit(WordEntry entry, String accent) {
  final pack = LexiconPack.instance;
  final source = (entry.lexemeId == null ? null : pack.byId(entry.lexemeId!)) ??
      pack.lookup(entry.word, pos: entry.pos)?.entry;
  if (source == null) return null;
  return packAccentAudioCredit(source, accent);
}

/// [packAccentAudioUrl]'s recording's credit (orDefault, as the word pages
/// play it).
RecordingCredit? packAccentAudioCredit(LexEntry source, String accent) {
  final aliases = _aliases(accent);
  final recording = source.recordings
          .where((r) => aliases.contains(r.accent?.toLowerCase()))
          .firstOrNull ??
      source.recordings.firstOrNull;
  return recording == null ? null : source.recordingCredits[recording.path];
}
