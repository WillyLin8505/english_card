import 'package:flutter/material.dart';

import '../models/word_entry.dart' show levelIndex;
import 'deck_library.dart';

/// 新手引導「你為什麼想學？」(卡 #814). The key is what AppSettings stores.
const learningGoalOptions = <(String key, String label, IconData icon)>[
  ('travel', '旅行', Icons.flight_takeoff),
  ('work', '工作', Icons.work_outline),
  ('exam', '考試', Icons.edit_note),
  ('school', '學校課業', Icons.school_outlined),
  ('social', '和家人朋友溝通', Icons.forum_outlined),
  ('fun', '興趣／看影片', Icons.movie_outlined),
];

/// 新手引導「你對哪些主題有興趣？」: the topics the card sets really have
/// (/api/decks `topic`) and the scenes the 相片冊 groups photos by
/// ([albumSceneWords]) — no invented categories. [match] are the deck
/// topic / title words that put a deck under the interest.
const interestOptions = <(String key, String label, IconData icon, List<String> match)>[
  ('daily', '日常基礎', Icons.wb_sunny_outlined, ['日常基礎', '基礎單字', '基礎 3000']),
  ('food', '食物', Icons.restaurant, ['食物', '水果', '蔬菜']),
  ('kitchen', '廚房', Icons.kitchen, ['廚房']),
  ('living', '客廳', Icons.weekend_outlined, ['客廳']),
  ('outdoor', '戶外', Icons.park_outlined, ['戶外']),
  ('animal', '動物', Icons.pets, ['動物']),
  ('advanced', '進階單字', Icons.trending_up, ['進階單字']),
  // 卡 #891: shown only once a deck with these words exists ([availableInterests]).
  ('sports', '運動', Icons.sports_soccer, ['運動']),
  ('hiking', '爬山／戶外活動', Icons.terrain, ['爬山', '登山', '戶外活動']),
  ('travel', '旅行', Icons.flight_takeoff, ['旅行', '旅遊']),
];

/// The interests that have at least one deck in [decks] (卡 #891): a topic
/// without content is not offered. Decks that match nothing (e.g. 基礎) are
/// not an interest of their own, so an empty [decks] keeps the original list.
List<(String key, String label, IconData icon, List<String> match)>
    availableInterests(Iterable<DeckInfo> decks) {
  final list = decks.toList();
  if (list.isEmpty) return interestOptions.sublist(0, 7);
  return [
    for (final o in interestOptions)
      if (list.any((d) => interestScore(d, [o.$1]) > 0)) o,
  ];
}

/// Deck topic words each learning goal looks for (卡 #891).
const _goalMatch = <String, List<String>>{
  'travel': ['旅行', '旅遊', '戶外'],
  'work': ['工作', '商務', '進階單字'],
  'exam': ['考試', '進階單字', '基礎 3000'],
  'school': ['基礎 3000', '基礎單字'],
  'social': ['日常基礎', '基礎單字'],
  'fun': ['日常基礎', '食物'],
};

/// Up to [limit] decks for a new learner (卡 #891): decks matching the
/// interests first, then the goals, then basics at the learner's [level]
/// (so the result is never empty while the server lists any deck). Photo
/// decks and level-split sub-decks are ranked by distance to [level].
List<DeckInfo> recommendDecks(
  List<DeckInfo> decks, {
  Iterable<String> interests = const [],
  Iterable<String> goals = const [],
  String level = 'A1',
  int limit = 4,
}) {
  if (decks.isEmpty) return const [];
  final lv = levelIndex(level);
  int dist(DeckInfo d) => d.cefr == null ? 1 : (levelIndex(d.cefr) - lv).abs();
  int goalScore(DeckInfo d) {
    final text = '${d.topic ?? ''} ${d.title}';
    var n = 0;
    for (final g in goals) {
      if ((_goalMatch[g] ?? const []).any(text.contains)) n++;
    }
    return n;
  }

  final ranked = [...decks]..sort((a, b) {
      final c = interestScore(b, interests).compareTo(interestScore(a, interests));
      if (c != 0) return c;
      final g = goalScore(b).compareTo(goalScore(a));
      if (g != 0) return g;
      final d = dist(a).compareTo(dist(b));
      if (d != 0) return d;
      return b.count.compareTo(a.count);
    });
  final picked = ranked.where((d) => d.count > 0).take(limit).toList();
  return picked.isEmpty ? ranked.take(limit).toList() : picked;
}

/// How well [info] fits the chosen [interests] (keys): the number of
/// interests whose words appear in the deck's topic or title.
int interestScore(DeckInfo info, Iterable<String> interests) {
  final text = '${info.topic ?? ''} ${info.title}';
  var score = 0;
  for (final o in interestOptions) {
    if (interests.contains(o.$1) && o.$4.any(text.contains)) score++;
  }
  return score;
}

/// [decks] with the ones matching [interests] first; otherwise the original
/// order is kept.
List<DeckInfo> sortByInterests(List<DeckInfo> decks, Iterable<String> interests) {
  if (interests.isEmpty) return decks;
  final scored = [for (final d in decks) (d, interestScore(d, interests))];
  final order = {for (var i = 0; i < scored.length; i++) scored[i].$1: i};
  scored.sort((a, b) {
    final c = b.$2.compareTo(a.$2);
    return c != 0 ? c : order[a.$1]!.compareTo(order[b.$1]!);
  });
  return [for (final s in scored) s.$1];
}
