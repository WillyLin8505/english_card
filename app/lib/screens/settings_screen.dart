import '../l10n/ui_text.dart';
import '../screens/connection_scan_screen.dart';
import '../screens/data_sources_screen.dart';
import '../screens/privacy_policy_screen.dart';
import '../services/learning_content.dart';
import '../services/learning_insights.dart';
import '../services/dictionary_sync.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/word_entry.dart';
import '../services/app_settings.dart';
import '../services/connection_qr.dart';
import '../services/tagging_service.dart';
import '../services/word_database_query.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';
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
  bool _checking = false;
  bool _switching = false;

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
    try {
      final h = await tagger.checkHealth();
      result = !h.ollama
          ? '✕ 服務有回應，但 AI 模型沒有啟動'
          : h.keyOk == false
              ? '✕ 服務正常，但 API Key 不正確'
              : '✓ 已連線 · ${h.model}';
    } catch (e) {
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
    super.dispose();
  }

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
                    padding: const EdgeInsets.all(MSpace.lg),
                    children: [
                      _Card(
                        title: '語言',
                        children: [
                          _label('學習語言'),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final e in supportedLanguages.entries)
                                ChoiceChip(
                                  label: UiText(languageOptionLabel(e.key,
                                      learning: true)),
                                  selected: e.key == settings.learningLanguage,
                                  onSelected: _switching ||
                                          !learningLanguageAvailable(e.key)
                                      ? null
                                      : (_) => _switchLanguage(e.key),
                                ),
                            ],
                          ),
                          _note('每個學習語言有自己的相片冊、單字、卡片與程度。'),
                          const SizedBox(height: 12),
                          _label('母語'),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final e in supportedLanguages.entries)
                                ChoiceChip(
                                  label: UiText(languageOptionLabel(e.key,
                                      learning: false)),
                                  selected: e.key == settings.nativeLanguage,
                                  onSelected: !nativeLanguageAvailable(e.key)
                                      ? null
                                      : (_) {
                                          if (e.key ==
                                              settings.learningLanguage) {
                                            showToast(context, '學習語言和母語不能相同');
                                            return;
                                          }
                                          settings.nativeLanguage = e.key;
                                          scope.enricher.process();
                                        },
                                ),
                            ],
                          ),
                          _note('介面隨母語切換；學習內容依已發布的詞庫提供。'),
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
                                    onSelected: (_) =>
                                        settings.englishAccent = a.key,
                                  ),
                              ],
                            ),
                          ],
                        ],
                      ),
                      _Card(
                        title: '單字難度',
                        children: [
                          UiText(
                            '目前程度 ${ui(context, levelLabel(profile.cefr))}',
                            style:
                                MFont.manrope(15, FontWeight.w800, MColors.ink),
                          ),
                          _note(
                              '來源：${ui(context, _sourceLabel(profile.source))}。新照片的單字會以這個程度為中心挑選；'
                              '照片詳情的難度轉盤只影響那一張照片。'),
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
                          _note(
                              '累積足夠的使用紀錄後（至少 20 次），程度會依你的評分、左滑與轉盤慢慢自動調整，一次最多一級。'),
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
                        )
                      else
                        _Card(
                          title: '進階設定：照片辨識連線',
                          collapsed: true,
                          children: [
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
                                  labelText: ui(context, '連線金鑰（API Key）')),
                              onChanged: (v) => settings.apiKey = v,
                            ),
                            const SizedBox(height: 12),
                            Row(
                              children: [
                                if (!kIsWeb) ...[
                                  OutlinedButton(
                                    onPressed:
                                        _checking ? null : _scanConnection,
                                    child: const UiText('掃描 QR code'),
                                  ),
                                  const SizedBox(width: 12),
                                ],
                                OutlinedButton(
                                  onPressed: _checking ? null : _testConnection,
                                  child: UiText(_checking ? '測試中…' : '測試連線'),
                                ),
                                const SizedBox(width: 12),
                                if (_check != null)
                                  Expanded(
                                    child: UiText(
                                      _check!,
                                      style: MFont.manrope(
                                          13,
                                          FontWeight.w700,
                                          _check!.startsWith('✓')
                                              ? MColors.success
                                              : MColors.againFg),
                                    ),
                                  ),
                              ],
                            ),
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
                      _Card(
                        title: '進階設定：複習安排',
                        collapsed: true,
                        children: [
                          UiText(
                            '希望記住的比例 ${(settings.desiredRetention * 100).round()}%',
                            style:
                                MFont.manrope(15, FontWeight.w800, MColors.ink),
                          ),
                          _note('越高，單字越常出現。預設 90%。'),
                          Slider(
                            value: settings.desiredRetention,
                            min: 0.8,
                            max: 0.95,
                            divisions: 15,
                            label:
                                '${(settings.desiredRetention * 100).round()}%',
                            onChanged: (v) => settings.desiredRetention = v,
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
                      _Card(title: '詞庫連線', children: [
                        UiText(DictionarySync.instance.status),
                        if (DictionarySync.instance.lastSuccess
                            case final time?)
                          _note(
                              '上次確認：${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}'),
                        TextButton(
                            onPressed: DictionarySync.instance.refresh,
                            child: const UiText('立即更新詞庫')),
                      ]),
                      _Card(
                        title: '資料',
                        children: [
                          UiText(
                            '字卡和複習紀錄保存在${kIsWeb ? '此瀏覽器' : '此裝置'}。詞庫會從你的資料庫自動更新。',
                            style: MFont.manrope(
                                14, FontWeight.w700, MColors.success),
                          ),
                          const SizedBox(height: 6),
                          _note(
                              '${ui(context, supportedLanguages[repo.language]!)}：'
                              '${formatCount(repo.wordCount)} 個單字 · '
                              '${formatCount(repo.photoCount)} 張照片 · '
                              '${formatCount(repo.cardCount)} 張卡片 · '
                              '已學會 ${formatCount(profile.learned.length)} 個'),
                          const SizedBox(height: 6),
                          const BackupButtons(),
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
                                value: settings.shareUsageStats,
                                onChanged: (v) => settings.shareUsageStats = v,
                              ),
                            ],
                          ),
                          _note('關閉時不會送出使用統計。打開後只送匿名的操作紀錄，用來了解功能好不好用，不影響任何功能。'),
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
    return _Card(title: '學習洞察', children: [
      _label('複習次數'),
      if (ins.total == 0)
        _note('還沒有複習紀錄。')
      else ...[
        UiText('最近 7 天（每日）：${bars(ins.daily)}',
            style: MFont.manrope(13, FontWeight.w600, MColors.ink)),
        const SizedBox(height: 4),
        UiText('最近 4 週（每週）：${bars(ins.weekly)}',
            style: MFont.manrope(13, FontWeight.w600, MColors.ink)),
        _note('共 ${ins.total} 次複習。'),
      ],
      const SizedBox(height: 12),
      _label('CEFR 等級變化'),
      if (ins.levelChanges.isEmpty)
        _note('目前程度還沒有變動。')
      else
        for (final c in ins.levelChanges.reversed.take(5))
          UiText(
              '${c.at.toLocal().toString().substring(0, 10)}　'
              '${cefrLevels[c.from]} → ${cefrLevels[c.to]}'
              '（${_sourceLabel(c.source)}）',
              style: MFont.manrope(13, FontWeight.w600, MColors.ink)),
      const SizedBox(height: 12),
      _label('弱項單字'),
      if (ins.weakWords.isEmpty)
        _note('還沒有常按「忘記」或「吃力」的字。')
      else
        for (final w in ins.weakWords)
          UiText('${w.word}　忘記 ${w.again}・吃力 ${w.hard}／${w.reviews} 次',
              style: MFont.manrope(13, FontWeight.w600, MColors.ink)),
    ]);
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

  const _Card(
      {required this.title, required this.children, this.collapsed = false});

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
                child: ExpansionTile(title: UiText(title), children: children))
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
