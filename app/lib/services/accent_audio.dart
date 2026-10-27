import '../models/word_entry.dart';
import 'lexicon_pack.dart';
import 'pack_media.dart';

/// Recording accent labels that count as [accent] ("en-GB" / "en-US").
Set<String> _aliases(String accent) =>
    accent == 'en-GB' ? const {'uk', 'gb', 'en-gb'} : const {'us', 'en-us'};

/// The pack recording [source] plays in [accent] (Windows 卡 #584/#695/
/// #759, owner order): 1) a real recording in that accent, 2) a real
/// recording in any other accent, 3) an Azure synthetic file — the same
/// accent first, else any — and null for 4) the phone's TTS voice.
///
/// Without [orDefault] only that accent's own files count: its real
/// recording, else its synthetic one.
LexRecording? packAccentRecording(LexEntry source, String accent,
    {bool orDefault = false}) {
  final aliases = _aliases(accent);
  bool inAccent(LexRecording r) => aliases.contains(r.accent?.toLowerCase());
  final real = source.recordings.where((r) => !r.synthetic);
  final synthetic = source.recordings.where((r) => r.synthetic);
  return real.where(inAccent).firstOrNull ??
      (orDefault ? real.firstOrNull : null) ??
      synthetic.where(inAccent).firstOrNull ??
      (orDefault ? synthetic.firstOrNull : null);
}

/// The URL of [packAccentRecording]. With [orDefault], a word without a
/// recording in [accent] plays another one (British first, #20/#56) rather
/// than TTS: 有該腔調的音檔就用，否則用現有音檔，最後才用 TTS.
String? packAccentAudioUrl(LexEntry source, String accent,
    {bool orDefault = false}) {
  final recording = packAccentRecording(source, accent, orDefault: orDefault);
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
  if (own != null &&
      own.isNotEmpty &&
      !source.ipas.any((p) => p.value == own)) {
    return entry.ipa;
  }
  return packAccentIpa(source, accent) ?? entry.ipa;
}

LexEntry? _packSource(WordEntry entry) {
  final pack = LexiconPack.instance;
  return (entry.lexemeId == null ? null : pack.byId(entry.lexemeId!)) ??
      pack.lookup(entry.word, pos: entry.pos)?.entry;
}

/// The language pack's recording of [entry] in [accent] ("en-GB" /
/// "en-US"), or the entry's own audio when it is in that accent (or, with
/// [orDefault], whatever its accent); null means TTS in that accent.
String? accentAudioUrl(WordEntry entry, String accent,
    {bool orDefault = false}) {
  final source = _packSource(entry);
  if (source != null && source.recordings.isNotEmpty) {
    return packAccentAudioUrl(source, accent, orDefault: orDefault);
  }
  if (orDefault || _aliases(accent).contains(entry.accent?.toLowerCase())) {
    return entry.audioUrl;
  }
  return null;
}

/// How [entry] sounds in [accent] (orDefault, as the card and word pages
/// play it): 0 a real recording in that accent, 1 a real recording in
/// another accent, 2 an Azure synthetic file, 3 the phone's TTS voice.
int accentAudioRank(WordEntry entry, String accent) {
  final source = _packSource(entry);
  if (source == null || source.recordings.isEmpty) {
    if (entry.audioUrl == null) return 3;
    return _aliases(accent).contains(entry.accent?.toLowerCase()) ? 0 : 1;
  }
  final r = packAccentRecording(source, accent, orDefault: true);
  if (r == null) return 3;
  if (r.synthetic) return 2;
  return _aliases(accent).contains(r.accent?.toLowerCase()) ? 0 : 1;
}

/// Whether what [entry] plays in [accent] is synthesized — an Azure file
/// or the phone's TTS — so the card shows 「合成」 (問題回報 #724, 卡 #695).
bool accentAudioIsSynthetic(WordEntry entry, String accent) =>
    accentAudioRank(entry, accent) >= 2;

/// The credit of the recording [accentAudioUrl] plays for [entry] in
/// [accent] (問題回報 #657): null for TTS or a recording with no credit.
RecordingCredit? accentAudioCredit(WordEntry entry, String accent) {
  final source = _packSource(entry);
  if (source == null) return null;
  return packAccentAudioCredit(source, accent);
}

/// [packAccentAudioUrl]'s recording's credit (orDefault, as the word pages
/// play it): an Azure file shows [RecordingCredit.synthetic] instead of a
/// speaker and license.
RecordingCredit? packAccentAudioCredit(LexEntry source, String accent) {
  final recording = packAccentRecording(source, accent, orDefault: true);
  if (recording == null) return null;
  if (recording.synthetic) return RecordingCredit.synthetic;
  return source.recordingCredits[recording.path];
}
