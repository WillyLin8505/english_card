import '../services/learning_content.dart';
import '../services/dictionary_sync.dart';
import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/word_entry.dart';
import '../services/app_settings.dart';
import '../services/tagging_service.dart';
import '../services/word_database_query.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';

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

  Future<void> _testConnection() async {
    final scope = AppScope.of(context);
    final settings = scope.settings;
    if (!settings.taggingConfigured) {
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
          ? '✕ 服務有回應，但 Ollama 沒有啟動'
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
                    padding: const EdgeInsets.all(20),
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
                                  label: Text(languageOptionLabel(e.key,
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
                                  label: Text(languageOptionLabel(e.key,
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
                          _note('第一階段提供英文學習與繁體中文提示；其他語言會在對應詞庫發布後開放。'),
                        ],
                      ),
                      _Card(
                        title: '單字難度',
                        children: [
                          Text(
                            '目前程度 ${levelLabel(profile.cefr)}',
                            style:
                                MFont.manrope(15, FontWeight.w800, MColors.ink),
                          ),
                          _note(
                              '來源：${_sourceLabel(profile.source)}。新照片的單字會以這個程度為中心挑選；'
                              '照片詳情的難度轉盤只影響那一張照片。'),
                          if (shift != 0) ...[
                            const SizedBox(height: 10),
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: MColors.primarySoft,
                                borderRadius: BorderRadius.circular(14),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Text(
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
                                    child: const Text('好'),
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
                                  label: Text(levelLabel(l)),
                                  selected: l == profile.cefr,
                                  onSelected: (_) => repo.setLevel(l),
                                ),
                            ],
                          ),
                          _note(
                              '累積足夠的使用紀錄後（至少 20 次），程度會依你的評分、左滑與轉盤慢慢自動調整，一次最多一級。'),
                        ],
                      ),
                      _Card(
                        title: '進階設定：照片辨識連線',
                        collapsed: true,
                        children: [
                          _note(
                              '網頁版會自動連接這台電腦的照片辨識服務，不用填網址或金鑰。只有使用其他服務時才需要修改。連不上時照片會先排隊，'
                              '恢復連線後自動處理。'),
                          const SizedBox(height: 12),
                          TextField(
                            controller: _url,
                            keyboardType: TextInputType.url,
                            decoration: const InputDecoration(
                              labelText: '服務網址',
                              hintText: 'http://127.0.0.1:8765/tag',
                            ),
                            onChanged: (v) => settings.taggingUrl = v,
                          ),
                          const SizedBox(height: 10),
                          TextField(
                            controller: _key,
                            obscureText: true,
                            decoration: const InputDecoration(
                                labelText: '連線金鑰（API Key）'),
                            onChanged: (v) => settings.apiKey = v,
                          ),
                          const SizedBox(height: 12),
                          Row(
                            children: [
                              OutlinedButton(
                                onPressed: _checking ? null : _testConnection,
                                child: Text(_checking ? '測試中…' : '測試連線'),
                              ),
                              const SizedBox(width: 12),
                              if (_check != null)
                                Expanded(
                                  child: Text(
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
                            Text(
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
                          Text(
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
                                  child: Text('卡片背面順序',
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
                        Text(DictionarySync.instance.status),
                        if (DictionarySync.instance.lastSuccess
                            case final time?)
                          _note(
                              '上次確認：${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}'),
                        TextButton(
                            onPressed: DictionarySync.instance.refresh,
                            child: const Text('立即更新詞庫')),
                      ]),
                      _Card(
                        title: '資料',
                        children: [
                          Text(
                            '字卡和複習紀錄保存在此瀏覽器。詞庫會從你的資料庫自動更新。',
                            style: MFont.manrope(
                                14, FontWeight.w700, MColors.success),
                          ),
                          const SizedBox(height: 6),
                          _note('${supportedLanguages[repo.language]}：'
                              '${formatCount(repo.wordCount)} 個單字 · '
                              '${formatCount(repo.photoCount)} 張照片 · '
                              '${formatCount(repo.cardCount)} 張卡片 · '
                              '已學會 ${formatCount(profile.learned.length)} 個'),
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

  Widget _label(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child:
            Text(text, style: MFont.manrope(14, FontWeight.w800, MColors.ink)),
      );

  Widget _note(String text) => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Text(text,
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
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: MColors.borderSoft),
          borderRadius: BorderRadius.circular(20),
        ),
        child: collapsed
            ? Material(
                color: Colors.transparent,
                child: ExpansionTile(title: Text(title), children: children))
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
