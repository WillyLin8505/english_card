import 'package:flutter/material.dart';

import '../models/word_entry.dart';
import '../services/app_settings.dart';
import '../services/cefr_lexicon.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';

/// What the learner chose on first launch.
class OnboardingResult {
  final String learningLanguage;
  final String nativeLanguage;
  final String level;

  /// 'self' (自評 only) or 'check' (with the quick vocabulary check).
  final String source;

  const OnboardingResult(
      this.learningLanguage, this.nativeLanguage, this.level, this.source);
}

/// 自評背景 → starting CEFR (spec section 7, 首次程度估計: 從未接觸、會基礎
/// 單字、已學一段時間、熟練，並映射至初始 CEFR).
const selfAssessment = [
  ('從未接觸', '幾乎沒學過', 'A1'),
  ('會基礎單字', '認得日常生活的簡單單字', 'A2'),
  ('已學一段時間', '能讀懂簡單的文章', 'B1'),
  ('熟練', '大部分內容都看得懂', 'B2'),
];

/// Level from the quick check: the highest level at which the learner
/// knew at least two of three words, counting up from A1 while every
/// level below also passed.
String levelFromCheck(Map<String, List<bool>> knownByLevel) {
  var level = 'A1';
  for (final l in cefrLevels) {
    final answers = knownByLevel[l];
    if (answers == null || answers.isEmpty) break;
    if (answers.where((k) => k).length * 3 >= answers.length * 2) {
      level = l;
    } else {
      break;
    }
  }
  return level;
}

/// First launch: learning language, native language, background, and an
/// optional 18-word check (spec section 7: 首次詢問學習語言、母語與自評背景
/// …首次可由自評及 15–20 題快速詞彙檢查估計). No Figma frames exist for
/// these; they use the app's card and pill style.
class OnboardingScreen extends StatefulWidget {
  final CefrLexicon lexicon;
  final ValueChanged<OnboardingResult> onDone;

  const OnboardingScreen(
      {super.key, required this.lexicon, required this.onDone});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  int _step = 0;
  int _checkLevel = 0;
  String _learning = 'en';
  String _native = 'zh-TW';
  String? _self;
  late final Map<String, List<String>> _checkWords = {
    'A1': ['apple', 'book', 'water'],
    'A2': ['kitchen', 'travel', 'weather'],
    'B1': ['improve', 'prepare', 'explain'],
    // B2–C2 too: with only A1–B1 a learner who knew every word was put at
    // B1 (問題回報: 程度測驗最高只到 B1). Levels from the CEFR word list.
    'B2': ['reluctant', 'ambiguous', 'eloquent'],
    'C1': ['scrutiny', 'candid', 'profound'],
    'C2': ['meticulous', 'superfluous', 'ephemeral'],
  };
  final Map<String, List<bool>> _known = {};

  bool get _canCheck =>
      _learning == 'en' && _checkWords.values.every((w) => w.length == 3);

  void _finish({required bool checked}) {
    final self = _self ?? 'A1';
    widget.onDone(OnboardingResult(
      _learning,
      _native,
      checked ? levelFromCheck(_known) : self,
      checked ? 'check' : 'self',
    ));
  }

  @override
  Widget build(BuildContext context) {
    final steps = [_languages, _background, if (_canCheck) _check];
    return Scaffold(
      backgroundColor: MColors.canvas,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 8),
              child: Row(
                children: [
                  for (var i = 0; i < steps.length; i++) ...[
                    if (i > 0) const SizedBox(width: 6),
                    Expanded(
                      child: Container(
                        height: 4,
                        decoration: BoxDecoration(
                          color: i <= _step
                              ? MColors.primary
                              : MColors.primarySoft,
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (_step > 0)
              Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                      onPressed: () => setState(() => _step--),
                      icon: const Icon(Icons.arrow_back),
                      label: const Text('上一步'))),
            Expanded(child: steps[_step]()),
          ],
        ),
      ),
    );
  }

  Widget _page({
    required String title,
    required String subtitle,
    required List<Widget> children,
    required Widget action,
  }) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
              children: [
                Text(title,
                    style: MFont.manrope(24, FontWeight.w800, MColors.ink)),
                const SizedBox(height: 8),
                Text(subtitle,
                    style: MFont.manrope(14, FontWeight.w600, MColors.muted)),
                const SizedBox(height: 24),
                ...children,
              ],
            ),
          ),
          Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 24), child: action),
        ],
      );

  Widget _option({
    required String title,
    String? subtitle,
    required bool selected,
    required VoidCallback? onTap,
  }) =>
      Builder(builder: (context) {
        final enabled = onTap != null;
        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Tap(
            onTap: onTap,
            label: subtitle == null ? title : '$title，$subtitle',
            labelOnly: true,
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: !enabled
                    ? MColors.surfaceSoft
                    : selected
                        ? MColors.primarySoft
                        : Colors.white,
                border: Border.all(
                    color: selected ? MColors.primary : MColors.borderSoft,
                    width: 1.5),
                borderRadius: MRadii.rLg,
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title,
                            style: MFont.manrope(16, FontWeight.w800,
                                enabled ? MColors.ink : MColors.gray500)),
                        if (subtitle != null)
                          Text(subtitle,
                              style: MFont.manrope(
                                  13, FontWeight.w600, MColors.muted)),
                      ],
                    ),
                  ),
                  if (selected)
                    const Icon(Icons.check_circle, color: MColors.primary),
                ],
              ),
            ),
          ),
        );
      });

  Widget _languages() => _page(
        title: '歡迎使用拍照學單字',
        subtitle: '用喜歡的照片學單字。先選想學的語言和你的母語。',
        children: [
          const SectionLabel('我想學'),
          const SizedBox(height: 8),
          for (final e in supportedLanguages.entries)
            _option(
              title: languageOptionLabel(e.key, learning: true),
              subtitle: learningLanguageAvailable(e.key) ? null : '第一階段尚未提供詞庫',
              selected: _learning == e.key,
              onTap: learningLanguageAvailable(e.key)
                  ? () => setState(() => _learning = e.key)
                  : null,
            ),
          const SizedBox(height: 12),
          const SectionLabel('我的母語（翻譯與提示會用這個語言）'),
          const SizedBox(height: 8),
          for (final e in supportedLanguages.entries)
            _option(
              title: languageOptionLabel(e.key, learning: false),
              subtitle: nativeLanguageAvailable(e.key) ? null : '第一階段尚未提供翻譯資料',
              selected: _native == e.key,
              onTap: nativeLanguageAvailable(e.key)
                  ? () => setState(() => _native = e.key)
                  : null,
            ),
        ],
        action:
            PrimaryButton(label: '下一步', onTap: () => setState(() => _step = 1)),
      );

  Widget _background() => _page(
        title: '你對${languageNameZh[_learning]}熟悉嗎？',
        subtitle: '用來決定一開始建議的單字難度，之後會依你的使用情況慢慢調整。',
        children: [
          for (final (title, subtitle, level) in selfAssessment)
            _option(
              title: title,
              subtitle: subtitle,
              selected: _self == level,
              onTap: () => setState(() => _self = level),
            ),
        ],
        action: Column(
          children: [
            PrimaryButton(
              label: _self == 'A1' ? '從基礎開始' : '開始使用',
              onTap: _self == null ? null : () => _finish(checked: false),
            ),
            if (_canCheck)
              TextButton(
                onPressed: _self == null
                    ? null
                    : () => setState(() {
                          _step = 2;
                          _checkLevel = 0;
                          _known.clear();
                        }),
                child: const Text('想測看看？試試單字程度（可略過）'),
              ),
          ],
        ),
      );

  Widget _check() => _page(
        title: '試試你認得哪些單字',
        subtitle: '一次只看 3 個字。認得就點一下，不認得也沒關係。',
        children: [
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              for (final l in [cefrLevels[_checkLevel]])
                for (final (i, w) in _checkWords[l]!.indexed)
                  _CheckChip(
                    word: w,
                    known: _known[l]?[i] ?? false,
                    onTap: () => setState(() {
                      final answers =
                          _known.putIfAbsent(l, () => List.filled(3, false));
                      answers[i] = !answers[i];
                    }),
                  ),
            ],
          ),
        ],
        action: Column(children: [
          PrimaryButton(
            label: '繼續',
            onTap: () {
              final level = cefrLevels[_checkLevel];
              final answers =
                  _known.putIfAbsent(level, () => List.filled(3, false));
              if (answers.where((v) => v).length >= 2 &&
                  _checkLevel < _checkWords.length - 1) {
                setState(() => _checkLevel++);
              } else {
                _finish(checked: true);
              }
            },
          ),
          TextButton(
              onPressed: () => _finish(checked: true),
              child: Text(_checkLevel == 0 ? '都不認識，從基礎開始' : '先到這裡，開始學習'))
        ]),
      );
}

class _CheckChip extends StatelessWidget {
  final String word;
  final bool known;
  final VoidCallback onTap;

  const _CheckChip(
      {required this.word, required this.known, required this.onTap});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: known ? '$word（認得）' : word,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: known ? MColors.successSoft : MColors.surfaceSoft,
            border:
                Border.all(color: known ? MColors.success : MColors.borderSoft),
            borderRadius: MRadii.rXl,
          ),
          child: Text(word,
              style: MFont.manrope(
                  15, FontWeight.w800, known ? MColors.success : MColors.ink)),
        ),
      );
}
