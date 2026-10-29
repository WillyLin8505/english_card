import 'package:flutter/material.dart';

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
];

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
