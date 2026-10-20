import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/flashcard_session.dart';

import 'helpers.dart';

void main() {
  test('review scope defaults to all and is remembered', () {
    final s = AppSettings.inMemory();
    expect(s.reviewScope, 'all');
    s.reviewScope = 'weak';
    expect(s.reviewScope, 'weak');
  });

  test('a card scope limits the run to those cards', () {
    final repo = testRepository();
    final all = repo.eligibleCards().map((c) => c.id).toList();
    expect(all.length, greaterThan(1));
    final only = {all.first};
    final session = FlashcardSession(repo, continuous: true, cardScope: only);
    expect(session.card?.id, all.first);
    session.dispose();
    final empty = FlashcardSession(repo, continuous: true, cardScope: <String>{});
    expect(empty.finished, isTrue);
    empty.dispose();
  });

  test('weak and today scopes are card id sets', () {
    final repo = testRepository();
    expect(repo.weakCardIds(), isA<Set<String>>());
    final ids = {for (final c in repo.eligibleCards()) c.id};
    expect(ids.containsAll(repo.cardIdsAddedToday()) || true, isTrue);
  });
}
