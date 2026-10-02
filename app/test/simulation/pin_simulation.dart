// Photo label layout simulation (not part of the regular suite).
//
// Every reply cached by the tagger is laid out the way the photo page does
// (layoutPins with the real badge sizes), on three photo shapes, and checked
// against the spec's 照片標籤排版 rule: labels never overlap, never cover any
// object's dot, and stay inside the photo.
//
//   flutter test test/simulation/pin_simulation.dart

import 'dart:convert';
import 'dart:io';

import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'package:photo_english_app/widgets/mobile/pin_layout.dart';

import 'learner_simulation.dart' show Findings;

void main() {
  testWidgets('labels of every cached photo are laid out cleanly', (tester) async {
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(Platform.environment['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
          .readAsStringSync()) as Map<String, dynamic>);
    final files = Directory('../tagger/cache')
        .listSync()
        .whereType<File>()
        .where((f) => !f.uri.pathSegments.last.startsWith('score-'))
        .toList();
    const shapes = {'直式': Size(343, 460), '方形': Size(343, 343), '橫式': Size(343, 230)};
    final f = Findings();
    var photos = 0, layouts = 0;
    for (final file in files) {
      final Object? raw;
      try {
        raw = jsonDecode(file.readAsStringSync());
      } catch (_) {
        continue;
      }
      final list = raw is Map ? raw['candidates'] : raw;
      if (list is! List) continue;
      final words = [
        for (final c in list)
          if (c is Map && c['point'] is List && (c['point'] as List).length >= 2) c
      ].take(5).toList();
      if (words.isEmpty) continue;
      photos++;
      for (final shape in shapes.entries) {
        final box = shape.value;
        final items = <PinItem>[];
        for (final (i, c) in words.indexed) {
          final p = c['point'] as List;
          final word = '${c['word']}';
          final zh = pack.lookup(word)?.entry.nativeMeaning ?? '';
          items.add(PinItem('$i:$word', Offset((p[0] as num).toDouble() * box.width,
              (p[1] as num).toDouble() * box.height),
              WordPin.badgeSize(word, zh, false, TextScaler.noScaling, linked: zh.isNotEmpty)));
        }
        final out = layoutPins(items, box);
        layouts++;
        final name = '${file.uri.pathSegments.last.substring(0, 10)} ${shape.key}';
        final area = Offset.zero & box;
        for (final pl in out) {
          if (pl.badge.left < -0.5 || pl.badge.top < -0.5 ||
              pl.badge.right > area.right + 0.5 || pl.badge.bottom > area.bottom + 0.5) {
            f.add('標籤超出照片', '$name ${pl.id} ${pl.badge}');
          }
          for (final it in items) {
            if (pl.badge.inflate(2).contains(it.anchor)) {
              f.add('標籤蓋住圓點', '$name ${pl.id} 蓋住 ${it.id}');
            }
          }
          for (final q in out) {
            if (!identical(pl, q) && pl.id.compareTo(q.id) < 0 && pl.badge.overlaps(q.badge)) {
              f.add('標籤互相重疊', '$name ${pl.id} × ${q.id}');
            }
          }
          if (pl.leaderLength > box.shortestSide * 0.6) {
            f.add('引線過長（標籤離物件太遠）', '$name ${pl.id} ${pl.leaderLength.round()}px');
          }
        }
        if (out.length != items.length) f.add('有標籤沒被放上去', '$name ${out.length}/${items.length}');
      }
    }
    final report = {'photos': photos, 'layouts': layouts, 'findings': f.toJson()};
    File('build/pin_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({'photos': photos, 'layouts': layouts, 'counts': f.counts}));
  });
}
