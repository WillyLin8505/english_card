// 卡 #840 (問題回報 #969): 英文介面下，例句旁的播放鍵 tooltip 仍是中文。
// The tooltips and semantics labels in app/lib must go through ui()/UiText
// so the catalog translates them; no hard-coded Chinese tooltip may remain.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';

final _cjk = RegExp(r'[一-鿿]');

void main() {
  test('tooltips translate in English and French', () {
    const keys = [
      '播放例句',
      '播放發音',
      '播放英式發音',
      '播放美式發音',
      '已加入我的單字本',
      '加入我的單字本與複習',
      '刪除相關字',
      '刪除詞形變化',
      '等待 AI 辨識',
    ];
    for (final key in keys) {
      for (final language in ['en', 'fr']) {
        final text = translateUi(key, language);
        expect(text, isNot(matches(_cjk)), reason: '$key in $language');
      }
    }
    expect(translateUi('播放例句', 'en'), 'Play example');
    expect(translateUi('播放英式發音', 'en'), 'Play British pronunciation');
  });

  test('no hard-coded Chinese tooltip is left in app/lib', () {
    final tooltip = RegExp(r"tooltip:\s*(?:[^,;]*\?\s*)?'[^']*[一-鿿]");
    final offenders = <String>[];
    for (final file in Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))) {
      final source = file.readAsStringSync();
      for (final m in tooltip.allMatches(source)) {
        offenders.add('${file.path}: ${m.group(0)}');
      }
    }
    expect(offenders, isEmpty);
  });

  test('card 841: spoken labels with variables translate', () {
    expect(translateUi('單字難度 Intermediate，左右拖曳調整', 'en'),
        'Word difficulty Intermediate; drag left or right to adjust');
    expect(translateUi('搜尋的字 cat 在 Beginner（A1），切到 A1', 'en'),
        'Searched word cat is at Beginner（A1）; switch to A1');
    expect(translateUi('搜尋的字 cat 沒有分級，切到 All', 'fr'),
        'Le mot cat n’a pas de niveau ; passer à All');
    expect(translateUi('標籤程度 Beginner（A1）', 'fr'),
        'Niveau de l’étiquette Beginner（A1）');
    expect(translateUi('3 個單字', 'en'), '3 words');
    expect(translateUi('第 2 張，共 5 張，左右滑動切換照片', 'fr'),
        'Photo 2 sur 5 ; balayez pour changer de photo');
  });
}
