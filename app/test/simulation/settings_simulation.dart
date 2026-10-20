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

import 'package:flutter/foundation.dart' show listEquals;
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

    // --- 商店版（問題回報 #265）：沒有伺服器可填，設定只說明照片在手機上
    // 辨識，不該出現網址／金鑰欄位 ---
    current = '商店版照片辨識說明';
    if (!settings.showsTaggingServer) {
      if (find.text('照片辨識').evaluate().isEmpty) {
        f.add('商店版找不到照片辨識說明', current);
      }
      if (find.widgetWithText(TextField, '服務網址').evaluate().isNotEmpty) {
        f.add('商店版仍顯示服務網址欄位', current);
      }
      // 開發者已填過網址的情境：網址／金鑰區塊才會出現。
      settings.taggingUrl = 'http://127.0.0.1:19999/tag';
      await tester.pumpAndSettle();
    }

    // --- 進階設定（展開一次即可看到照片辨識連線）（flutter test 以 VM 執行，kIsWeb 為
    // false，說明文字不該再講「網頁版會自動連接」—— card228 修正）---
    current = '展開辨識連線';
    await tester.scrollUntilVisible(find.text('進階設定'), 300,
        maxScrolls: 50);
    final advanced = find.text('進階設定'); // 問題回報 #390: one collapsed section
    if (advanced.evaluate().isEmpty) {
      f.add('找不到辨識連線設定', current);
    } else {
      // 第 5 輪：頁底的「進階設定」會被前面操作留下的提示條（SnackBar）蓋住，
      // 點擊打不到（學習者等提示消失再點即可）——先收掉提示條再點。
      ScaffoldMessenger.of(tester.element(advanced)).clearSnackBars();
      await tester.pumpAndSettle();
      await tester.ensureVisible(advanced);
      await tester.tap(advanced);
      await tester.pumpAndSettle();
      if (find.text('照片辨識連線').evaluate().isEmpty &&
          find.text('複習安排').evaluate().isEmpty) {
        f.add('進階設定點了沒有展開', current);
      }
      if (find.textContaining('網頁版會自動連接').evaluate().isNotEmpty) {
        f.add('非網頁版仍顯示「網頁版會自動連接」說明', current);
      }
    }

    // --- 測試連線：沒填網址時的提示（只有開發版／網頁版清空網址後區塊還在）---
    current = '沒填網址就測試連線';
    final testBtn = find.widgetWithText(OutlinedButton, '測試連線');
    if (testBtn.evaluate().isEmpty) {
      f.add('找不到測試連線按鈕', current);
    } else if (AppSettings.developerTools) {
      settings.taggingUrl = '';
      await tester.pump();
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
      ScaffoldMessenger.of(tester.element(testBtn)).clearSnackBars();
      await tester.pumpAndSettle();
      await tester.ensureVisible(testBtn);
      await tester.pumpAndSettle(); // 金鑰欄聚焦時的捲動動畫要先停
      await tester.tap(testBtn);
      await settle(tester);
      final hasResult = find.textContaining('✕').evaluate().isNotEmpty ||
          find.textContaining('✓').evaluate().isNotEmpty;
      if (!hasResult) f.add('連線失敗時沒有看到結果訊息', current);
      // 第 3 輪：失敗訊息要是給人看的中文，不是伺服器的英文原文。
      for (final t in tester.widgetList<Text>(find.textContaining('✕'))) {
        final s = t.data ?? '';
        if (RegExp(r'\b(failed|error|request|response)\b', caseSensitive: false)
            .hasMatch(s)) {
          f.add('連線失敗訊息是英文原文', '$current：$s');
        }
      }
    }
    checkNoNull();

    // --- 進階設定：複習安排 ---
    current = '展開複習安排';
    final reviewAdvanced = find.text('複習安排'); // inside 進階設定, already open
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

    // 第 5 輪：看完收起進階設定，上方的資料卡才不會被清單回收。
    if (advanced.evaluate().isNotEmpty) {
      ScaffoldMessenger.of(tester.element(advanced)).clearSnackBars();
      await tester.pumpAndSettle();
      await tester.ensureVisible(advanced);
      await tester.tap(advanced);
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('匯出備份'), -300,
          maxScrolls: 50);
    }

    // --- 詞庫連線：只在失敗時出現（問題回報 #306）；正常時不該有輪詢頻率、
    // 上次確認時間或「你的資料庫」這類除錯文字 ---
    current = '詞庫連線狀態';
    if (DictionarySync.instance.hasError) {
      if (find.text(DictionarySync.instance.status).evaluate().isEmpty) {
        f.add('詞庫連線失敗但設定頁沒有顯示', current);
      }
    } else {
      if (find.text('詞庫連線').evaluate().isNotEmpty) {
        f.add('詞庫正常時仍顯示「詞庫連線」卡', current);
      }
      if (find.textContaining('每 30 秒').evaluate().isNotEmpty ||
          find.textContaining('上次確認').evaluate().isNotEmpty) {
        f.add('詞庫正常時仍顯示輪詢頻率或上次確認時間', current);
      }
    }
    if (find.textContaining('你的資料庫').evaluate().isNotEmpty) {
      f.add('資料卡仍寫「你的資料庫」', current);
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

    // --- 資料備份與還原（問題回報 #278）：按鈕在、說明在；不真的開檔案選擇器 ---
    current = '資料備份與還原';
    for (final label in ['匯出備份', '從備份還原']) {
      if (find.text(label).evaluate().isEmpty) f.add('找不到「$label」按鈕', current);
    }
    checkNoNull();

    // --- 隱私：分享使用統計開關要真的改到 AppSettings（第 3 輪）---
    current = '隱私開關';
    final privacy = find.widgetWithText(Row, '分享使用統計');
    final share = find.descendant(of: privacy, matching: find.byType(Switch));
    if (share.evaluate().isEmpty) {
      f.add('找不到分享使用統計開關', current);
    } else {
      final before = settings.shareUsageStats;
      await tester.ensureVisible(share.first);
      await tester.tap(share.first);
      await tester.pumpAndSettle();
      if (settings.shareUsageStats == before) {
        f.add('分享使用統計開關沒有生效', current);
      }
      await tester.tap(share.first);
      await tester.pumpAndSettle();
    }

    // --- 卡片樣式：每個樣式都點一次，要真的換掉 settings.cardStyle ---
    current = '卡片樣式';
    for (final style in [...CardStyle.values.skip(1), CardStyle.values.first]) {
      // #346：樣式改成附縮圖的方塊（CardStylePicker），不再是 ChoiceChip。
      final chip = find.byKey(ValueKey('cardStyle-${style.name}'));
      if (chip.evaluate().isEmpty) {
        f.add('找不到卡片樣式「${style.label}」', current);
        continue;
      }
      await tester.ensureVisible(chip.first);
      await tester.tap(chip.first);
      await tester.pumpAndSettle();
      if (settings.cardStyle != style) {
        f.add('卡片樣式「${style.label}」沒有生效', current);
      }
    }

    // --- 子頁面：隱私權政策、資料來源與授權要能開、能回來。卡片集頁用
    // DeckLibrary.instance（Hive），這裡只看入口；頁面本身由
    // card323_deck_library_test 測 ---
    if (find.text('瀏覽並下載卡片集').evaluate().isEmpty) {
      f.add('找不到「瀏覽並下載卡片集」', '卡片集');
    }
    for (final label in ['查看隱私權政策', '資料來源與授權']) {
      current = '開「$label」';
      final btn = find.text(label);
      if (btn.evaluate().isEmpty) {
        f.add('找不到「$label」', current);
        continue;
      }
      await tester.ensureVisible(btn.first);
      await tester.tap(btn.first);
      await tester.pump(const Duration(milliseconds: 500));
      checkNoNull();
      final nav = tester.state<NavigatorState>(find.byType(Navigator).last);
      if (!nav.canPop()) {
        f.add('「$label」沒有開新頁', current);
      } else {
        nav.pop();
        await tester.pumpAndSettle();
      }
      if (find.text('設定').evaluate().isEmpty) f.add('回不到設定頁', current);
    }

    // 學習者由上往下讀到的文字（易用性評估用）。
    // ListView 會把看不到的區塊丟掉，所以從頂端分段往下捲，每段接上前一段
    // 重疊的部分（只收清單裡的字，底部導覽列不算）。
    final list = find.byType(ListView).first;
    List<String> visibleText() => [
          for (final t in tester.widgetList<Text>(
              find.descendant(of: list, matching: find.byType(Text))))
            if ((t.data ?? t.textSpan?.toPlainText() ?? '').trim().isNotEmpty)
              (t.data ?? t.textSpan!.toPlainText()).trim(),
        ];
    final listState = tester.state<ScrollableState>(
        find.descendant(of: list, matching: find.byType(Scrollable)).first);
    listState.position.jumpTo(0);
    await tester.pumpAndSettle();
    final screenText = <String>[];
    for (var step = 0; step < 40; step++) {
      final snap = visibleText();
      var overlap = 0;
      for (var k = snap.length < screenText.length ? snap.length : screenText.length;
          k > 0;
          k--) {
        if (listEquals(screenText.sublist(screenText.length - k), snap.sublist(0, k))) {
          overlap = k;
          break;
        }
      }
      screenText.addAll(snap.skip(overlap));
      final pos = listState.position;
      if (pos.pixels >= pos.maxScrollExtent) break;
      pos.jumpTo((pos.pixels + 300).clamp(0, pos.maxScrollExtent));
      await tester.pumpAndSettle();
    }

    final report = {
      'learningLanguage': settings.learningLanguage,
      'nativeLanguage': settings.nativeLanguage,
      'englishAccent': settings.englishAccent,
      'desiredRetention': settings.desiredRetention,
      'cefr': repo.profile.cefr,
      'cardStyle': settings.cardStyle.name,
      'shareUsageStats': settings.shareUsageStats,
      'screenText': screenText,
      'findings': f.toJson(),
    };
    File(Platform.environment['SIM_OUT'] ?? 'build/settings_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({...report, 'screenText': screenText.length, 'findings': f.counts}));
  }, timeout: const Timeout(Duration(minutes: 10)));
}
