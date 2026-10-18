// Settings-tab simulation (not part of the regular suite; card #228).
//
// A learner opens 設定 and works through every control: learning/native
// language, English accent, CEFR level, the tagging-service URL/key fields
// and 測試連線, the review-retention slider, 卡片背面順序, and the
// dictionary-sync status / data card. For each control it checks the change
// actually took effect in AppSettings / WordDatabaseRepository, and that
// wrong input (same language twice, no URL, an unreachable URL) shows the
// right message instead of silently doing nothing.
//
//   flutter test test/simulation/settings_simulation.dart   (SIM_OUT)

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/learning_content.dart';

import '../helpers.dart';
import 'learner_simulation.dart' show Findings;

void main() {
  testWidgets('learner works through every setting', (tester) async {
    final f = Findings();
    final original = FlutterError.onError;
    var current = '';
    FlutterError.onError = (d) => f.add('版面錯誤', '$current：${d.exceptionAsString().split('\n').first}');
    addTearDown(() => FlutterError.onError = original);

    // A tall viewport (like screens_test's 設定 group) so every card,
    // including the collapsed 進階設定 ones once expanded, stays built
    // instead of being virtualized out of the widget tree.
    final app = await pumpApp(tester,
        initialTab: AppTab.settings,
        settings: AppSettings.inMemory(
            learningLanguage: 'en', nativeLanguage: 'zh-TW'),
        size: const Size(402, 2200));
    final settings = app.settings;
    final repo = app.repository;

    void checkNoNull() {
      for (final t in tester.widgetList<Text>(find.byType(Text))) {
        final s = t.data ?? t.textSpan?.toPlainText() ?? '';
        if (RegExp(r'\bnull\b').hasMatch(s)) f.add('畫面出現 null', '$current：$s');
      }
    }

    // --- 語言：相同語言不能互換（母語區塊的「英文」是第二個出現，學習語言
    // 區塊同樣有一個「英文（English）」chip，用 .last 取母語那一個）---
    current = '母語選成學習語言';
    final enChips = find.widgetWithText(ChoiceChip, '英文（English）');
    if (enChips.evaluate().length < 2) {
      f.add('找不到母語的英文選項', '$current（找到 ${enChips.evaluate().length} 個）');
    } else {
      await tester.tap(enChips.last);
      await tester.pump();
      if (find.text('學習語言和母語不能相同').evaluate().isEmpty) {
        f.add('母語與學習語言相同時沒有提示', current);
      }
      await tester.pump(const Duration(seconds: 3));
    }
    if (settings.nativeLanguage != 'zh-TW') {
      f.add('提示後母語被誤改', settings.nativeLanguage);
    }

    // --- 語言：切母語為法文（介面語言，不受已發布詞庫限制）生效 ---
    current = '切母語為法文';
    final frChip = find.widgetWithText(ChoiceChip, '法文（Français）');
    if (frChip.evaluate().isEmpty) {
      f.add('找不到法文母語選項', current);
    } else {
      await tester.tap(frChip.first);
      await tester.pump();
      if (settings.nativeLanguage != 'fr') f.add('切母語沒有生效', current);
      settings.nativeLanguage = 'zh-TW'; // 還原，之後的檢查都用中文介面比對
      await tester.pump();
    }

    // --- 發音腔調：切換生效 ---
    current = '切發音腔調';
    final usChip = find.widgetWithText(ChoiceChip, '美式（en-US）');
    if (usChip.evaluate().isEmpty) {
      f.add('找不到發音腔調選項', current);
    } else {
      await tester.tap(usChip.first);
      await tester.pump();
      if (settings.englishAccent != 'en-US') f.add('切發音腔調沒有生效', current);
      final chip = tester.widget<ChoiceChip>(usChip.first);
      if (chip.selected != true) f.add('切換後選取狀態沒有更新', current);
    }
    checkNoNull();

    // --- 單字難度：CEFR chip 生效 ---
    for (final level in const ['A1', 'B1', 'C1']) {
      current = '切難度 $level';
      final chip = find.widgetWithText(ChoiceChip, levelLabel(level));
      if (chip.evaluate().isEmpty) {
        f.add('找不到難度選項', current);
        continue;
      }
      await tester.tap(chip.first);
      await tester.pump();
      if (repo.profile.cefr != level) f.add('切難度沒有生效', '$current → ${repo.profile.cefr}');
    }
    checkNoNull();

    // --- 進階設定：展開照片辨識區塊（flutter test 以 VM 執行，kIsWeb 為
    // false，說明文字不該再講「網頁版會自動連接」—— card228 修正）---
    current = '展開辨識連線';
    final advanced = find.text('進階設定：照片辨識連線');
    if (advanced.evaluate().isEmpty) {
      f.add('找不到辨識連線設定', current);
    } else {
      await tester.ensureVisible(advanced);
      await tester.tap(advanced);
      await tester.pumpAndSettle();
      if (find.textContaining('網頁版會自動連接').evaluate().isNotEmpty) {
        f.add('非網頁版仍顯示「網頁版會自動連接」說明', current);
      }
    }

    // --- 測試連線：沒填網址時的提示 ---
    current = '沒填網址就測試連線';
    settings.taggingUrl = '';
    await tester.pump();
    final testBtn = find.widgetWithText(OutlinedButton, '測試連線');
    if (testBtn.evaluate().isEmpty) {
      f.add('找不到測試連線按鈕', current);
    } else {
      await tester.ensureVisible(testBtn);
      await tester.tap(testBtn);
      await tester.pump();
      if (find.text('請先填寫服務網址').evaluate().isEmpty) {
        f.add('沒填網址時沒有提示', current);
      }
    }

    // --- 網址／金鑰欄位：輸入生效 ---
    current = '輸入辨識服務網址與金鑰';
    final urlField = find.widgetWithText(TextField, '服務網址');
    final keyField = find.widgetWithText(TextField, '連線金鑰（API Key）');
    if (urlField.evaluate().isEmpty || keyField.evaluate().isEmpty) {
      f.add('找不到網址或金鑰欄位', current);
    } else {
      await tester.enterText(urlField, 'http://127.0.0.1:19999/tag');
      await tester.enterText(keyField, 'test-key-123');
      await tester.pump();
      if (settings.taggingUrl != 'http://127.0.0.1:19999/tag') f.add('網址欄位沒有生效', current);
      if (settings.apiKey != 'test-key-123') f.add('金鑰欄位沒有生效', current);
    }

    // --- 測試連線：網址連不到時的提示（本機沒人聽的 port，不呼叫真的 AI）---
    current = '測試連線到打不開的網址';
    if (testBtn.evaluate().isNotEmpty) {
      await tester.ensureVisible(testBtn);
      await tester.tap(testBtn);
      await settle(tester);
      final hasResult = find.textContaining('✕').evaluate().isNotEmpty ||
          find.textContaining('✓').evaluate().isNotEmpty;
      if (!hasResult) f.add('連線失敗時沒有看到結果訊息', current);
    }
    checkNoNull();

    // --- 進階設定：複習安排 ---
    current = '展開複習安排';
    final reviewAdvanced = find.text('進階設定：複習安排');
    if (reviewAdvanced.evaluate().isEmpty) {
      f.add('找不到複習安排設定', current);
    } else {
      await tester.ensureVisible(reviewAdvanced);
      await tester.tap(reviewAdvanced);
      await tester.pumpAndSettle();
      current = '拖動希望記住的比例';
      final slider = find.byType(Slider);
      if (slider.evaluate().isEmpty) {
        f.add('找不到複習比例滑桿', current);
      } else {
        final before = settings.desiredRetention;
        final center = tester.getCenter(slider.first);
        await tester.dragFrom(center, const Offset(-80, 0));
        await tester.pump();
        if (settings.desiredRetention == before) f.add('複習比例滑桿沒有生效', current);
        if (settings.desiredRetention < 0.8 || settings.desiredRetention > 0.95) {
          f.add('複習比例超出允許範圍', '${settings.desiredRetention}');
        }
      }

      // --- 卡片背面順序 ---
      current = '開卡片背面順序';
      final order = find.text('卡片背面順序');
      if (order.evaluate().isEmpty) {
        f.add('找不到卡片背面順序入口', current);
      } else {
        await tester.ensureVisible(order);
        await tester.tap(order);
        await tester.pumpAndSettle();
        if (find.byType(Dialog).evaluate().isEmpty) {
          f.add('卡片背面順序沒有開啟對話框', current);
        } else {
          final cancel = find.text('取消');
          if (cancel.evaluate().isNotEmpty) {
            await tester.tap(cancel.first);
          } else {
            tester.state<NavigatorState>(find.byType(Navigator).last).pop();
          }
          await tester.pumpAndSettle();
        }
      }
    }
    checkNoNull();

    // --- 詞庫連線狀態：顯示、不崩潰（不主動按「立即更新詞庫」，避免真的打網路）---
    current = '詞庫連線狀態';
    if (find.text(DictionarySync.instance.status).evaluate().isEmpty) {
      f.add('詞庫連線狀態沒有顯示', current);
    }
    if (find.text('立即更新詞庫').evaluate().isEmpty) {
      f.add('找不到立即更新詞庫按鈕', current);
    }

    // --- 資料卡：統計數字、裝置用詞（flutter test 以 VM 執行，kIsWeb 為
    // false，不該再顯示「此瀏覽器」—— card228 修正，見 settings_screen.dart）---
    current = '資料卡統計';
    if (find.textContaining('個單字').evaluate().isEmpty) {
      f.add('資料卡沒有顯示單字數', current);
    }
    if (find.textContaining('此瀏覽器').evaluate().isNotEmpty) {
      f.add('非網頁版仍顯示「此瀏覽器」', current);
    }
    checkNoNull();

    final report = {
      'learningLanguage': settings.learningLanguage,
      'nativeLanguage': settings.nativeLanguage,
      'englishAccent': settings.englishAccent,
      'desiredRetention': settings.desiredRetention,
      'cefr': repo.profile.cefr,
      'findings': f.toJson(),
    };
    File(Platform.environment['SIM_OUT'] ?? 'build/settings_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({...report, 'findings': f.counts}));
  }, timeout: const Timeout(Duration(minutes: 10)));
}
