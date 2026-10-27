import '../l10n/ui_text.dart';
import '../screens/connection_scan_screen.dart';
import '../screens/data_sources_screen.dart';
import '../screens/my_feedback_screen.dart';
import '../screens/privacy_policy_screen.dart';
import '../services/learning_content.dart';
import '../services/learning_insights.dart';
import '../services/dictionary_sync.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/word_entry.dart';
import '../services/accent_audio.dart';
import '../services/app_settings.dart';
import '../services/connection_qr.dart';
import '../services/lexicon_pack.dart';
import '../services/tagging_service.dart';
import '../services/word_database_query.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';
import '../widgets/anki_export_button.dart';
import '../widgets/card_style_picker.dart';
import '../widgets/backup_buttons.dart';

/// 設定 — the fifth tab. The Figma file has no frame for it, so it uses
/// the other screens' nav bar and card style. It holds spec section 4's
/// UserLearningSettings, section 7's language pair and level, and
/// section 2's tagging service address.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  TextEditingController? _url;
  TextEditingController? _key;
  String? _check;
  // 問題回報 #475: a failed check either just delays photos (they queue and
  // are recognised once the service is back) or needs the learner to fix the
  // URL/key; the collapsed hint says which.
  bool _checkNeedsFix = false;
  // 問題回報 #815 (owner chose 1): the fix-it hint is also shown at the top
  // of the page; tapping it scrolls down to 進階設定 and opens it.
  final _scroll = ScrollController();
  final _advanced = ExpansibleController();
  final _advancedKey = GlobalKey();
  bool _checking = false;
  bool _switching = false;

  /// 問題回報 #510: picking an accent (or tapping it again) says a word
  /// whose British and American sounds clearly differ, so the learner
  /// hears the choice without hunting for a word in another tab.
  static const _accentDemoWord = 'water';

  Future<void> _previewAccent(String accent) async {
    final scope = AppScope.of(context);
    final source = LexiconPack.instance.lookup(_accentDemoWord)?.entry;
    final ok = await scope.speaker.say(_accentDemoWord,
        language: 'en',
        accent: accent,
        audioUrl: source == null ? null : packAccentAudioUrl(source, accent));
    if (!ok && mounted) showToast(context, '播放發音失敗，請檢查音量或稍後再試');
  }

  /// The broken-recognition hint, when the last check says the learner
  /// has to fix the URL or key (not when the service is only offline).
  String? _fixHint(AppSettings settings) =>
      settings.showsTaggingServer &&
              (_check?.startsWith('✕') ?? false) &&
              _checkNeedsFix
          ? '照片辨識設定有誤，新照片無法辨識，點開修正'
          : null;

  Future<void> _openAdvanced() async {
    if (_scroll.hasClients) {
      await _scroll.animateTo(_scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
    }
    _advanced.expand();
    await Future<void>.delayed(const Duration(milliseconds: 250));
    final target = _advancedKey.currentContext;
    if (target != null && target.mounted) {
      await Scrollable.ensureVisible(target,
          duration: const Duration(milliseconds: 200));
    }
  }

  /// 掃描後台 QR code，帶入網址與金鑰後直接測試連線（手動輸入仍可用）。
  Future<void> _scanConnection() async {
    final found = await Navigator.of(context).push<ConnectionQr>(
        MaterialPageRoute<ConnectionQr>(
            builder: (_) => const ConnectionScanScreen()));
    if (found == null || !mounted) return;
    _url!.text = found.taggingUrl;
    _key!.text = found.apiKey;
    final settings = AppScope.of(context).settings;
    settings.taggingUrl = found.taggingUrl;
    settings.apiKey = found.apiKey;
    await _testConnection();
  }

  Future<void> _testConnection() async {
    final scope = AppScope.of(context);
    final settings = scope.settings;
    if (settings.taggingUrl.isEmpty) {
      setState(() => _check = '請先填寫服務網址');
      return;
    }
    setState(() {
      _checking = true;
      _check = null;
    });
    final tagger = scope.intake
        .createTagger(Uri.parse(settings.taggingUrl), settings.apiKey);
    String result;
    var needsFix = false;
    try {
      final h = await tagger.checkHealth();
      needsFix = h.ollama && h.keyOk == false;
      result = !h.ollama
          ? '✕ 服務有回應，但 AI 模型沒有啟動'
          : h.keyOk == false
              ? '✕ 服務正常，但 API Key 不正確'
              : '✓ 已連線 · ${h.model}';
    } catch (e) {
      needsFix = !isOffline(e);
      result = '✕ ${describeTaggingError(e, settings.taggingUrl)}';
    } finally {
      tagger.close();
    }
    if (result.startsWith('✓')) {
      scope.queue.process();
      scope.enricher.process();
    }
    if (mounted) {
      setState(() {
        _checking = false;
        _check = result;
        _checkNeedsFix = needsFix;
      });
    }
  }

  Future<void> _switchLanguage(String language) async {
    final scope = AppScope.of(context);
    if (language == scope.settings.learningLanguage || _switching) return;
    if (language == scope.settings.nativeLanguage) {
      showToast(context, '學習語言和母語不能相同');
      return;
    }
    setState(() => _switching = true);
    try {
      await scope.switchLanguage(language);
    } finally {
      if (mounted) setState(() => _switching = false);
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final settings = AppScope.of(context).settings;
    _url ??= TextEditingController(text: settings.taggingUrl);
    _key ??= TextEditingController(text: settings.apiKey);
  }

  @override
  void dispose() {
    _url?.dispose();
    _key?.dispose();
    _scroll.dispose();
    super.dispose();
  }

  static const _levelInfo =
      '累積至少 20 次使用紀錄後，程度會依你的評分、左滑與轉盤自動調整，一次最多一級。照片詳情的難度轉盤只影響那一張照片。';

  // 問題回報 #520: the exceptions to the accent setting, behind the info icon.
  static const _accentInfo = '複習卡翻到背面時英式、美式各唸一次。沒有這個腔調錄音的字，播現有的錄音。';

  static String _sourceLabel(String source) => switch (source) {
        'check' => '快速詞彙檢查',
        'elo' => '依你的使用情況調整',
        'user' => '你設定的',
        _ => '自評',
      };

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final settings = scope.settings;
    final repo = scope.repository;
    return ListenableBuilder(
      listenable: Listenable.merge(
          [settings, repo, scope.queue, DictionarySync.instance]),
      builder: (context, _) {
        final profile = repo.profile;
        final shift = profile.suggestedShift;
        final waiting = repo.photos.where((p) => p.awaitingTagging).length;
        return Scaffold(
          backgroundColor: MColors.canvas,
          body: SafeArea(
            bottom: false,
            child: Column(
              children: [
                MNavBar(
                  title: '設定',
                  leading: BackNavButton(
                      onTap: () => scope.navigator.selectTab(AppTab.camera)),
                ),
                Expanded(
                  child: ListView(
                    controller: _scroll,
                    padding: const EdgeInsets.all(MSpace.lg),
                    children: [
                      if (_fixHint(settings) case final hint?)
                        Padding(
                          padding: const EdgeInsets.only(bottom: MSpace.md),
                          child: Material(
                            color: MColors.againFg.withValues(alpha: 0.08),
                            borderRadius: MRadii.rLg,
                            child: InkWell(
                              key: const ValueKey('settings-fix-hint'),
                              borderRadius: MRadii.rLg,
                              onTap: _openAdvanced,
                              child: Padding(
                                padding: const EdgeInsets.all(MSpace.md),
                                child: Row(children: [
                                  const Icon(Icons.error_outline_rounded,
                                      color: MColors.againFg, size: 20),
                                  const SizedBox(width: MSpace.sm),
                                  Expanded(
                                    child: UiText(hint,
                                        style: MFont.manrope(13,
                                            FontWeight.w700, MColors.againFg)),
                                  ),
                                  const Icon(Icons.chevron_right_rounded,
                                      color: MColors.againFg),
                                ]),
                              ),
                            ),
                          ),
                        ),
                      _Card(
                        title: '語言',
                        children: [
                          _label('學習語言'),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final e in supportedLanguages.entries)
                                if (learningLanguageAvailable(e.key) &&
                                    e.key != settings.nativeLanguage)
                                  ChoiceChip(
                                    label: UiText(languageOptionLabel(e.key,
                                        learning: true)),
                                    selected:
                                        e.key == settings.learningLanguage,
                                    onSelected: _switching
                                        ? null
                                        : (_) => _switchLanguage(e.key),
                                  ),
                            ],
                          ),
                          if (availableLearningLanguages.length > 1)
                            _note('每個學習語言有自己的相片冊、單字、卡片與程度。'),
                          const SizedBox(height: 12),
                          _label('母語'),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final e in supportedLanguages.entries)
                                if (nativeLanguageAvailable(e.key) &&
                                    e.key != settings.learningLanguage)
                                  ChoiceChip(
                                    label: UiText(languageOptionLabel(e.key,
                                        learning: false)),
                                    selected: e.key == settings.nativeLanguage,
                                    onSelected: (_) {
                                      settings.nativeLanguage = e.key;
                                      scope.enricher.process();
                                    },
                                  ),
                            ],
                          ),
                          _note('介面語言跟著母語切換。'),
                          if (settings.learningLanguage == 'en') ...[
                            const SizedBox(height: 12),
                            _label('發音腔調'),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                for (final a in const {
                                  'en-GB': '英式（en-GB）',
                                  'en-US': '美式（en-US）',
                                }.entries)
                                  ChoiceChip(
                                    label: UiText(a.value),
                                    selected: a.key == settings.englishAccent,
                                    onSelected: (_) {
                                      settings.englishAccent = a.key;
                                      _previewAccent(a.key);
                                    },
                                  ),
                              ],
                            ),
                            // 問題回報 #520: one line for the learner; the
                            // exceptions live behind the info icon, as for
                            // 單字難度 (#391).
                            Row(
                              children: [
                                Expanded(
                                  child: _note(
                                      '點一下試聽「water」；單字頁、單字本和複習卡都用這個腔調。'),
                                ),
                                Tooltip(
                                  message: ui(context, _accentInfo),
                                  triggerMode: TooltipTriggerMode.tap,
                                  showDuration: const Duration(seconds: 8),
                                  child: const Padding(
                                    padding: EdgeInsets.all(6),
                                    child: Icon(Icons.info_outline,
                                        size: 18, color: MColors.muted),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                      _Card(
                        title: '單字難度',
                        children: [
                          // 問題回報 #511: a level the user picked is already
                          // the lit chip below; only an App change gets a line.
                          Row(
                            children: [
                              Expanded(
                                child: profile.source == 'elo'
                                    ? UiText(
                                        'App 已依你的複習調成 ${ui(context, levelLabel(profile.cefr))}',
                                        style: MFont.manrope(
                                            15, FontWeight.w800, MColors.ink),
                                      )
                                    : _note(
                                        '新照片的單字以下面選的程度為主，App 會依你的複習慢慢調整。'),
                              ),
                              Tooltip(
                                message: ui(context, _levelInfo),
                                triggerMode: TooltipTriggerMode.tap,
                                showDuration: const Duration(seconds: 8),
                                child: const Padding(
                                  padding: EdgeInsets.all(6),
                                  child: Icon(Icons.info_outline,
                                      size: 18, color: MColors.muted),
                                ),
                              ),
                            ],
                          ),
                          if (profile.source == 'elo')
                            _note('新照片的單字以這個程度為主，App 會依你的複習慢慢調整。'),
                          if (shift != 0) ...[
                            const SizedBox(height: 10),
                            Container(
                              padding: const EdgeInsets.all(MSpace.sm),
                              decoration: MDecor.insetCard(
                                color: MColors.primarySoft,
                                radius: MRadii.md,
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: UiText(
                                      shift > 0
                                          ? '你最近常把難度調高，要把預設程度改成 ${cefrLevels[profile.level + 1]} 嗎？'
                                          : '你最近常把難度調低，要把預設程度改成 ${cefrLevels[profile.level - 1]} 嗎？',
                                      style: MFont.manrope(
                                          13, FontWeight.w700, MColors.primary),
                                    ),
                                  ),
                                  TextButton(
                                    onPressed: () => repo.setLevel(
                                        cefrLevels[profile.level + shift]),
                                    child: const UiText('好'),
                                  ),
                                ],
                              ),
                            ),
                          ],
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final l in cefrLevels)
                                ChoiceChip(
                                  label: UiText(levelLabel(l)),
                                  selected: l == profile.cefr,
                                  onSelected: (_) => repo.setLevel(l),
                                ),
                            ],
                          ),
                        ],
                      ),
                      // 問題回報 #317: the review card's look only.
                      _Card(
                        title: '卡片樣式',
                        children: [
                          CardStylePicker(
                            selected: settings.cardStyle,
                            onChanged: (style) => settings.cardStyle = style,
                          ),
                          _note('只改變複習卡片的外觀，內容和複習方式不變。'),
                          const Divider(height: 24),
                          Row(
                            children: [
                              Expanded(
                                child: UiText('照片上的單字標示',
                                    style: MFont.manrope(
                                        15, FontWeight.w800, MColors.ink)),
                              ),
                              Switch(
                                key: const ValueKey('photo-labels-switch'),
                                value: settings.showPhotoLabels,
                                onChanged: (v) => settings.showPhotoLabels = v,
                              ),
                            ],
                          ),
                          _note('複習卡片背面的照片上，顯示這個單字的標籤。'),
                        ],
                      ),
                      _insightsCard(repo.insights()),
                      // The store build has no server to point at (問題回報
                      // #265): photos are recognized on the phone, so the
                      // address / key fields are a developer and web thing.
                      if (!settings.showsTaggingServer)
                        _Card(
                          title: '照片辨識',
                          children: [
                            _note(settings.usesLocalRecognition
                                ? '照片在這支手機上辨識，不會上傳到任何伺服器。'
                                : '這台裝置沒有本機照片辨識，照片會先留在相片冊。'),
                            if (waiting > 0) ...[
                              const SizedBox(height: 8),
                              UiText(
                                scope.queue.current != null
                                    ? '⌛ 正在辨識照片（還有 $waiting 張在排隊）'
                                    : '⌛ 有 $waiting 張照片等待 AI 辨識',
                                style: MFont.manrope(
                                    12, FontWeight.w700, MColors.muted),
                              ),
                            ],
                          ],
                        ),
                      // Connecting/connected and the polling interval are
                      // debug chrome; learners only need to know when the
                      // dictionary can't update (問題回報 #260, #306).
                      if (DictionarySync.instance.hasError)
                        _Card(title: '詞庫連線', children: [
                          UiText(DictionarySync.instance.status),
                          TextButton(
                              onPressed: DictionarySync.instance.refresh,
                              child: const UiText('重新連線')),
                        ]),
                      _Card(
                        title: '資料',
                        children: [
                          UiText(
                            '字卡和複習紀錄保存在${kIsWeb ? '此瀏覽器' : '此裝置'}。',
                            style: MFont.manrope(
                                14, FontWeight.w700, MColors.success),
                          ),
                          const SizedBox(height: 6),
                          // The language prefix only tells learners which
                          // language's data this is when there is more than
                          // one to choose from (問題回報 #572, like #474).
                          _note(
                              '${availableLearningLanguages.length > 1 ? '${ui(context, supportedLanguages[repo.language]!)}：' : ''}'
                              '${formatCount(repo.wordCount)} 個單字 · '
                              '${formatCount(repo.photoCount)} 張照片 · '
                              '已學會 ${formatCount(profile.learned.length)} 個'),
                          const SizedBox(height: 6),
                          const BackupButtons(),
                          const AnkiExportButton(),
                        ],
                      ),
                      _Card(
                        title: '隱私',
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: UiText('分享使用統計',
                                    style: MFont.manrope(
                                        15, FontWeight.w800, MColors.ink)),
                              ),
                              Switch(
                                key: const ValueKey('usage-stats-switch'),
                                value: settings.shareUsageStats,
                                onChanged: (v) => settings.shareUsageStats = v,
                              ),
                            ],
                          ),
                          _note('只送匿名的操作紀錄，用來改善 App；關閉不影響任何功能。'),
                          Align(
                            alignment: Alignment.centerLeft,
                            child: TextButton(
                              onPressed: () => Navigator.of(context).push(
                                  MaterialPageRoute<void>(
                                      builder: (_) =>
                                          const PrivacyPolicyScreen())),
                              child: const UiText('查看隱私權政策'),
                            ),
                          ),
                        ],
                      ),
                      // 問題回報 #701: what this phone sent, deletable.
                      _Card(
                        title: '意見回饋',
                        children: [
                          _note('看這支手機送過的意見回饋與卡片回報，也可以刪除。'),
                          Align(
                            alignment: Alignment.centerLeft,
                            child: TextButton(
                              key: const ValueKey('my-feedback-button'),
                              onPressed: () => Navigator.of(context).push(
                                  MaterialPageRoute<void>(
                                      builder: (_) =>
                                          const MyFeedbackScreen())),
                              child: const UiText('我的意見回饋'),
                            ),
                          ),
                        ],
                      ),
                      _Card(
                        title: '關於',
                        children: [
                          Align(
                            alignment: Alignment.centerLeft,
                            child: TextButton(
                              onPressed: () => Navigator.of(context).push(
                                  MaterialPageRoute<void>(
                                      builder: (_) =>
                                          const DataSourcesScreen())),
                              child: const UiText('資料來源與授權'),
                            ),
                          ),
                        ],
                      ),
                      // 問題回報 #390: advanced settings sit at the bottom,
                      // collapsed; a failed connection shows only as a hint.
                      _Card(
                        key: _advancedKey,
                        controller: _advanced,
                        title: '進階設定',
                        collapsed: true,
                        hint: settings.showsTaggingServer &&
                                (_check?.startsWith('✕') ?? false)
                            ? (_checkNeedsFix
                                ? '照片辨識設定有誤，新照片無法辨識，點開修正'
                                : '照片辨識暫時連不上：新照片會先排隊，連上後自動辨識，不用處理')
                            : null,
                        children: [
                          if (settings.showsTaggingServer) ...[
                            const SectionLabel('照片辨識連線'),
                            const SizedBox(height: 10),
                            _note(kIsWeb
                                ? '網頁版會自動連接這台電腦的照片辨識服務，不用填網址或金鑰。只有使用其他服務時才需要修改。連不上時照片會先排隊，'
                                    '恢復連線後自動處理。'
                                : '留空時用手機本機辨識照片；填入服務網址與金鑰則改用該服務。連不上時照片會先排隊，'
                                    '恢復連線後自動處理。'),
                            const SizedBox(height: 12),
                            TextField(
                              controller: _url,
                              keyboardType: TextInputType.url,
                              decoration: InputDecoration(
                                labelText: ui(context, '服務網址'),
                                hintText: 'http://127.0.0.1:8765/tag',
                              ),
                              onChanged: (v) => settings.taggingUrl = v,
                            ),
                            const SizedBox(height: 10),
                            TextField(
                              controller: _key,
                              obscureText: true,
                              decoration: InputDecoration(
                                  labelText: ui(context, '連線金鑰（API Key）'),
                                  // #546: the backup note no longer mentions the key;
                                  // only people who set one need to know.
                                  helperText: ui(context, '金鑰不會存進備份檔；在新手機還原備份後要重新輸入。')),
                              onChanged: (v) => settings.apiKey = v,
                            ),
                            const SizedBox(height: 12),
                            Wrap(
                              spacing: 12,
                              runSpacing: 8,
                              children: [
                                if (!kIsWeb)
                                  OutlinedButton(
                                    onPressed:
                                        _checking ? null : _scanConnection,
                                    child: const UiText('掃描 QR code'),
                                  ),
                                OutlinedButton(
                                  onPressed: _checking ? null : _testConnection,
                                  child: UiText(_checking ? '測試中…' : '測試連線'),
                                ),
                              ],
                            ),
                            if (_check != null) ...[
                              const SizedBox(height: 8),
                              UiText(
                                // The learner is already on this page.
                                _check!.replaceAll('（設定 → 照片辨識連線）', ''),
                                style: MFont.manrope(
                                    13,
                                    FontWeight.w700,
                                    _check!.startsWith('✓')
                                        ? MColors.success
                                        : MColors.againFg),
                              ),
                            ],
                            if (waiting > 0) ...[
                              const SizedBox(height: 8),
                              UiText(
                                scope.queue.current != null
                                    ? '⌛ 正在辨識照片（還有 $waiting 張在排隊）'
                                    : '⌛ 有 $waiting 張照片等待 AI 辨識',
                                style: MFont.manrope(
                                    12, FontWeight.w700, MColors.muted),
                              ),
                            ],
                            const SizedBox(height: 24),
                          ],
                          const SectionLabel('複習安排'),
                          const SizedBox(height: 10),
                          UiText(
                            '希望記住的比例 ${(settings.desiredRetention * 100).round()}%',
                            style:
                                MFont.manrope(15, FontWeight.w800, MColors.ink),
                          ),
                          _note('越高，單字越常出現。預設 90%。'),
                          Slider(
                            value: settings.desiredRetention,
                            min: AppSettings.minRetention,
                            max: AppSettings.maxRetention,
                            divisions: 15,
                            label:
                                '${(settings.desiredRetention * 100).round()}%',
                            onChanged: (v) => settings.desiredRetention = v,
                          ),
                          const Divider(height: 24),
                          UiText(
                            '每天最多 ${settings.dailyNewLimit} 張新卡',
                            style:
                                MFont.manrope(15, FontWeight.w800, MColors.ink),
                          ),
                          _note('超過的新卡順延到明天。預設 20 張。'),
                          Slider(
                            value: settings.dailyNewLimit.toDouble(),
                            min: AppSettings.minDailyNew.toDouble(),
                            max: AppSettings.maxDailyNew.toDouble(),
                            divisions: (AppSettings.maxDailyNew -
                                    AppSettings.minDailyNew) ~/
                                5,
                            label: '${settings.dailyNewLimit}',
                            onChanged: (v) => settings.dailyNewLimit = v.round(),
                          ),
                          UiText(
                            '每天最多複習 ${settings.dailyReviewLimit} 張',
                            style:
                                MFont.manrope(15, FontWeight.w800, MColors.ink),
                          ),
                          _note('超過的複習順延到明天。預設 100 張。'),
                          Slider(
                            value: settings.dailyReviewLimit.toDouble(),
                            min: AppSettings.minDailyReview.toDouble(),
                            max: AppSettings.maxDailyReview.toDouble(),
                            divisions: (AppSettings.maxDailyReview -
                                    AppSettings.minDailyReview) ~/
                                10,
                            label: '${settings.dailyReviewLimit}',
                            onChanged: (v) =>
                                settings.dailyReviewLimit = v.round(),
                          ),
                          const Divider(height: 24),
                          Tap(
                            onTap: () async {
                              final t = await showTemplateOrderDialog(
                                  context, repo.template);
                              if (t != null) repo.updateTemplate(t);
                            },
                            label: '卡片背面順序',
                            child: Row(
                              children: [
                                Expanded(
                                  child: UiText('卡片背面順序',
                                      style: MFont.manrope(
                                          15, FontWeight.w800, MColors.ink)),
                                ),
                                const Icon(Icons.chevron_right,
                                    color: MColors.label),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _insightsCard(LearningInsights ins) {
    String bars(List<int> v) => v.join(' · ');
    // 問題回報 #345: clicking a level in 設定 is not progress.
    final shownChanges =
        ins.levelChanges.where((c) => c.source != 'user').toList();
    // 問題回報 #430: with nothing to show, one line instead of three empty
    // headings; sub-sections appear only once they have data.
    if (ins.total == 0 && shownChanges.isEmpty && ins.weakWords.isEmpty) {
      return _Card(title: '學習洞察', children: [
        _note('複習幾次之後，這裡會顯示你的複習次數、程度變化和弱項單字。'),
      ]);
    }
    final sections = <List<Widget>>[
      if (ins.total > 0)
        [
          _label('複習次數'),
          UiText('最近 7 天（每日）：${bars(ins.daily)}',
              style: MFont.manrope(13, FontWeight.w600, MColors.ink)),
          const SizedBox(height: 4),
          UiText('最近 4 週（每週）：${bars(ins.weekly)}',
              style: MFont.manrope(13, FontWeight.w600, MColors.ink)),
          _note('共 ${ins.total} 次複習。'),
        ],
      if (shownChanges.isNotEmpty)
        [
          _label('CEFR 等級變化'),
          for (final c in shownChanges.reversed.take(5))
            UiText(
                '${c.at.toLocal().toString().substring(0, 10)}　'
                '${cefrLevels[c.from]} → ${cefrLevels[c.to]}'
                '（${_sourceLabel(c.source)}）',
                style: MFont.manrope(13, FontWeight.w600, MColors.ink)),
        ],
      if (ins.weakWords.isNotEmpty)
        [
          _label('弱項單字'),
          // 問題回報 #307: each word opens its details, and the list can be
          // practised straight away instead of searching 單字本 for each.
          for (final w in ins.weakWords) _weakWordRow(w),
          const SizedBox(height: 4),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => AppScope.of(context)
                  .navigator
                  .reviewCards([for (final w in ins.weakWords) w.cardId]),
              icon: const Icon(Icons.replay_rounded, size: 18),
              label: const UiText('複習這些字'),
            ),
          ),
        ],
    ];
    return _Card(title: '學習洞察', children: [
      for (var i = 0; i < sections.length; i++) ...[
        if (i > 0) const SizedBox(height: 12),
        ...sections[i],
      ],
    ]);
  }

  /// 「複習 5 次，忘了 2 次」— how often it was forgotten is the message, not
  /// the rating names (問題回報 #307).
  static String _weakWordNote(WeakWord w) {
    final parts = [
      if (w.again > 0) '忘了 ${w.again} 次',
      if (w.hard > 0) '吃力 ${w.hard} 次',
    ];
    return '複習 ${w.reviews} 次，${parts.join('、')}';
  }

  Widget _weakWordRow(WeakWord w) {
    final scope = AppScope.of(context);
    final entryId = scope.repository.card(w.cardId)?.wordEntryId;
    return InkWell(
      onTap: entryId == null ? null : () => scope.navigator.openWord(entryId),
      borderRadius: BorderRadius.circular(MRadii.md),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            UiText(w.word,
                style: MFont.manrope(14, FontWeight.w800, MColors.ink)),
            const SizedBox(width: 10),
            Expanded(
              child: UiText(_weakWordNote(w),
                  style: MFont.manrope(12, FontWeight.w600, MColors.muted)),
            ),
            if (entryId != null)
              const Icon(Icons.chevron_right_rounded,
                  size: 20, color: MColors.muted),
          ],
        ),
      ),
    );
  }

  Widget _label(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: UiText(text,
            style: MFont.manrope(14, FontWeight.w800, MColors.ink)),
      );

  Widget _note(String text) => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: UiText(text,
            style: MFont.manrope(12, FontWeight.w600, MColors.muted)),
      );
}

class _Card extends StatelessWidget {
  final String title;
  final List<Widget> children;
  final bool collapsed;

  /// Shown under a collapsed title (e.g. a failed connection check).
  final String? hint;

  /// Opens a collapsed card from elsewhere on the page (問題回報 #815).
  final ExpansibleController? controller;

  const _Card(
      {super.key,
      required this.title,
      required this.children,
      this.collapsed = false,
      this.hint,
      this.controller});

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: MSpace.md),
        padding: const EdgeInsets.all(MSpace.md),
        decoration: MDecor.card(
          color: MColors.surface,
          borderColor: MColors.borderSoft,
          radius: MRadii.xl,
          shadow: MShadows.soft,
        ),
        child: collapsed
            ? Material(
                color: Colors.transparent,
                child: ExpansionTile(
                    controller: controller,
                    title: UiText(title),
                    subtitle: hint == null
                        ? null
                        : UiText(hint!,
                            style: MFont.manrope(
                                12, FontWeight.w700, MColors.againFg)),
                    children: children))
            : Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SectionLabel(title),
                  const SizedBox(height: 10),
                  ...children,
                ],
              ),
      );
}
