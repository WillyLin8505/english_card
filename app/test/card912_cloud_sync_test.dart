import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/cloud_sync.dart';
import 'package:photo_english_app/services/fsrs_scheduler.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/sync_index.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_store.dart';

/// The rules of lexicon/backend/app/account_sync.py (tested there too).
class FakeAccount {
  final records = <String, Map<String, dynamic>>{};
  final blobs = <String, Uint8List>{};
  var seq = 0;
  var pushes = 0;
  var online = true;

  http.Client client() => MockClient((req) async {
        if (!online) throw http.ClientException('offline');
        final path = req.url.path;
        if (path.endsWith('/push')) {
          pushes++;
          final body = jsonDecode(req.body) as Map<String, dynamic>;
          for (final r in (body['records'] as List).cast<Map<String, dynamic>>()) {
            final old = records[r['key']];
            final device = body['device'] as String;
            final wins = old == null ||
                (r['stamp'] as int) > (old['stamp'] as int) ||
                (r['stamp'] == old['stamp'] &&
                    device.compareTo(old['device'] as String) > 0);
            if (!wins) continue;
            records[r['key'] as String] = {
              ...r,
              'device': device,
              'seq': ++seq
            };
          }
          return http.Response('{}', 200);
        }
        if (path.endsWith('/pull')) {
          final since = int.parse(req.url.queryParameters['since']!);
          final device = req.url.queryParameters['device'];
          final rows = records.values
              .where((r) => (r['seq'] as int) > since)
              .toList()
            ..sort((a, b) => (a['seq'] as int).compareTo(b['seq'] as int));
          return http.Response.bytes(
              utf8.encode(jsonEncode({
                'records': rows.where((r) => r['device'] != device).toList(),
                'next': rows.isEmpty ? since : rows.last['seq'],
                'more': false,
              })),
              200);
        }
        final id = path.split('/').last;
        if (req.method == 'POST') {
          blobs[id] = req.bodyBytes;
          return http.Response('{}', 200);
        }
        final b = blobs[id];
        return b == null
            ? http.Response('{}', 404)
            : http.Response.bytes(b, 200);
      });
}

/// One device: its own boxes, its own repository, the same account.
class Device {
  final String name;
  final FakeAccount account;
  final settings = AppSettings.inMemory(taggingUrl: 'https://x.test')
    ..setCloudAccount('tok', 'a@x.com');
  final photoStore = PhotoStore.inMemory();
  late HiveWordDatabaseStore store;
  late WordDatabaseRepository repo;
  late CloudSync sync;
  var wifi = true;
  var clock = DateTime.utc(2026, 11, 1, 9);

  Device(this.name, this.account);

  static Future<Device> make(String name, FakeAccount account) async {
    final d = Device(name, account);
    d.store = await HiveWordDatabaseStore.open(boxPrefix: name);
    await d.reopen();
    d.sync = CloudSync(d.settings, d.photoStore,
        client: account.client(),
        baseUrl: 'https://x.test',
        boxPrefix: name,
        onWifi: () async => d.wifi);
    return d;
  }

  Future<void> reopen() async {
    await Future<void>.delayed(Duration.zero);
    repo = WordDatabaseRepository.fromData(store.load(),
        language: 'en', store: store, clock: () => clock);
  }

  Future<void> syncNow() async {
    await repo.flush();
    await sync.syncNow();
    await reopen();
  }

  WordEntry add(String word) =>
      repo.addWord(word: word, pos: 'noun', meaning: 'x');

  void review(String word, Rating rating) {
    repo.review(repo.cardOf(repo.entryByWord(word)!.id)!.id, rating);
  }

  Future<void> deleteWord(String word) async {
    final entry = repo.entryByWord(word)!;
    await repo.flush();
    await store.deleteCard(repo.cardOf(entry.id)!.id);
    await store.deleteEntry(entry.id);
    await reopen();
  }

  List<ReviewLog> logsOf(String word) =>
      repo.logsOf(repo.cardOf(repo.entryByWord(word)!.id)!.id);
}

void main() {
  late Directory dir;
  late FakeAccount account;
  late Device a, b;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('card912');
    Hive.init(dir.path);
    account = FakeAccount();
    a = await Device.make('a_', account);
    b = await Device.make('b_', account);
  });

  tearDown(() async {
    a.sync.dispose();
    b.sync.dispose();
    await Hive.deleteFromDisk();
    await Hive.close();
    await dir.delete(recursive: true);
  });

  test('a word saved on one device reaches the other', () async {
    a.add('apple');
    await a.syncNow();
    await b.syncNow();
    expect(b.repo.entryByWord('apple'), isNotNull);
    expect(a.sync.state, CloudSyncState.idle);
    expect(a.sync.pendingRecords, 0);
  });

  test('both devices offline: each keeps its words and both reviews',
      () async {
    a.add('apple');
    await a.syncNow();
    await b.syncNow();

    a.add('pear');
    b.add('plum');
    a.clock = DateTime.utc(2026, 11, 2, 9);
    a.review('apple', Rating.good);
    b.clock = DateTime.utc(2026, 11, 3, 9);
    b.review('apple', Rating.hard);

    await a.syncNow();
    await b.syncNow();
    await a.syncNow();
    for (final d in [a, b]) {
      expect(d.repo.entryByWord('pear'), isNotNull, reason: d.name);
      expect(d.repo.entryByWord('plum'), isNotNull, reason: d.name);
      expect(d.logsOf('apple').map((l) => l.rating.name).toList(),
          ['good', 'hard'],
          reason: d.name);
    }
    final fa = a.repo.cardOf(a.repo.entryByWord('apple')!.id)!.fsrs;
    final fb = b.repo.cardOf(b.repo.entryByWord('apple')!.id)!.fsrs;
    expect(jsonEncode(fa.toJson()), jsonEncode(fb.toJson()));
    // The later review built on the earlier one instead of replacing it.
    expect(fa.reps, 2);
  });

  test('two devices that both saved a word share one word and one card',
      () async {
    final x = a.add('apple');
    final y = b.add('apple');
    expect(x.id, isNot(y.id));
    a.clock = DateTime.utc(2026, 11, 2);
    a.review('apple', Rating.good);
    b.clock = DateTime.utc(2026, 11, 3);
    b.review('apple', Rating.easy);
    await a.syncNow();
    await b.syncNow();
    await a.syncNow();
    for (final d in [a, b]) {
      expect(d.repo.entries.where((e) => e.word == 'apple'), hasLength(1));
      expect(d.logsOf('apple'), hasLength(2), reason: d.name);
    }
  });

  test('reviews of a word with accents or Chinese sync and count once',
      () async {
    for (final word in ['école', '蘋果']) {
      a.add(word);
      a.review(word, Rating.good);
    }
    await a.syncNow();
    await b.syncNow();
    await b.syncNow();
    expect(b.logsOf('école'), hasLength(1));
    expect(b.logsOf('蘋果'), hasLength(1));
  });

  test('a deletion reaches the other device and stays deleted', () async {
    a.add('apple');
    await a.syncNow();
    await b.syncNow();
    expect(b.repo.entryByWord('apple'), isNotNull);

    await a.deleteWord('apple');
    await a.syncNow();
    await b.syncNow();
    expect(b.repo.entryByWord('apple'), isNull);
    expect(b.store.load().cards, isEmpty);
    await b.syncNow();
    await a.syncNow();
    expect(a.repo.entryByWord('apple'), isNull);
  });

  test('the same word added again after a deletion comes back', () async {
    a.add('apple');
    await a.syncNow();
    await b.syncNow();
    await a.deleteWord('apple');
    await a.syncNow();
    await b.syncNow();
    b.add('apple');
    await b.syncNow();
    await a.syncNow();
    expect(a.repo.entryByWord('apple'), isNotNull);
  });

  test('an upload repeated after a lost reply does not count twice', () async {
    a.add('apple');
    a.review('apple', Rating.good);
    await a.syncNow();
    await b.syncNow();
    // A reinstalled device: same data, nothing marked as sent.
    await a.store.sync.index.clear();
    await (await Hive.openBox<String>('a_sync_state')).delete('cursor');
    await a.syncNow();
    await b.syncNow();
    await a.syncNow();
    expect(a.logsOf('apple'), hasLength(1));
    expect(b.logsOf('apple'), hasLength(1));
    expect(
        account.records.keys.where((k) => k.startsWith('en/logs/')).length, 1);
  });

  test('offline changes stay queued, show as offline, and go up later',
      () async {
    account.online = false;
    a.add('apple');
    await a.syncNow();
    expect(a.sync.state, CloudSyncState.offline);
    account.online = true;
    await a.syncNow();
    expect(a.sync.state, CloudSyncState.idle);
    expect(account.records.keys, contains('en/entries/apple'));
    await b.syncNow();
    expect(b.repo.entryByWord('apple'), isNotNull);
  });

  test('photo records travel at once, pixels wait for Wi-Fi', () async {
    final bytes = Uint8List.fromList([1, 2, 3]);
    final where = await a.photoStore.save('photo-1', bytes);
    a.repo.addPhoto(Photo(
        id: 'photo-1',
        title: 'Pic',
        takenAt: DateTime.utc(2026, 11, 1),
        createdAt: DateTime.utc(2026, 11, 1),
        storedKey: where.storedKey));
    a.wifi = false;
    await a.syncNow();
    expect(a.sync.photosWaitForWifi, isTrue);
    expect(account.blobs, isEmpty);

    a.wifi = true;
    await a.syncNow();
    expect(account.blobs['photo-1'], bytes);

    b.wifi = false;
    await b.syncNow();
    expect(b.repo.photo('photo-1'), isNotNull);
    expect(b.repo.photo('photo-1')!.storedKey, isNull);
    b.wifi = true;
    await b.syncNow();
    expect(await b.photoStore.storedBytes('photo-1'), bytes);
    expect(b.repo.photo('photo-1')!.storedKey, 'photo-1');
  });

  test('a device-specific picture path is no change to sync', () async {
    a.repo.addPhoto(Photo(
        id: 'p', title: 'Pic', takenAt: DateTime.utc(2026), createdAt: DateTime.utc(2026), filePath: '/a/p.jpg'));
    await a.syncNow();
    final before = a.store.sync.mark(SyncBoxes.photos, 'p')!.stamp;
    // Direct store write, not the repository queue: wait for it, or tearDown
    // closes Hive while the stamp check is still running.
    await a.store.putPhoto(Photo(
        id: 'p', title: 'Pic', takenAt: DateTime.utc(2026), createdAt: DateTime.utc(2026), filePath: '/b/p.jpg'));
    await a.repo.flush();
    await Future<void>.delayed(Duration.zero);
    expect(a.store.sync.mark(SyncBoxes.photos, 'p')!.stamp, before);
    final sent = jsonDecode(account.records['en/photos/p']!['data'] as String);
    expect((sent as Map).containsKey('filePath'), isFalse);
  });

  test('settings merge per field; learning language stays on the device',
      () async {
    await a.syncNow();
    await b.syncNow();
    a.settings.dailyNewLimit = 7;
    b.settings.showPhotoLabels = !b.settings.showPhotoLabels;
    final labels = b.settings.showPhotoLabels;
    a.settings.learningLanguage = 'fr';
    await a.syncNow();
    await b.syncNow();
    await a.syncNow();
    expect(b.settings.dailyNewLimit, 7);
    expect(a.settings.showPhotoLabels, labels);
    expect(b.settings.learningLanguage, 'en');
  });

  test('learned words of either device stay in the profile', () async {
    a.add('apple');
    b.add('pear');
    await a.syncNow();
    await b.syncNow();
    await a.syncNow();
    for (final d in [a, b]) {
      expect(d.repo.profile.familiarity.keys,
          containsAll(['apple', 'pear']), reason: d.name);
    }
  });

  test('a photo deleted on one device goes on the other', () async {
    a.repo.addPhoto(Photo(id: 'p', title: 'Pic', takenAt: DateTime.utc(2026), createdAt: DateTime.utc(2026)));
    await a.syncNow();
    await b.syncNow();
    expect(b.repo.photo('p'), isNotNull);
    a.repo.removePhoto('p');
    await a.syncNow();
    await b.syncNow();
    expect(b.repo.photo('p'), isNull);
  });

  test('data from a newer App version is left alone', () async {
    account.records['en/entries/zzz'] = {
      'key': 'en/entries/zzz',
      'stamp': 5,
      'device': 'future',
      'deleted': false,
      'seq': ++account.seq,
      'data': jsonEncode({
        'id': 'word-9',
        'word': 'zzz',
        '_v': HiveWordDatabaseStore.schemaVersion + 1
      }),
    };
    await a.syncNow();
    expect(a.sync.state, CloudSyncState.needsUpdate);
    expect(a.repo.entryByWord('zzz'), isNull);
  });

  test('a rejected token signs out instead of retrying', () async {
    final sync = CloudSync(a.settings, a.photoStore,
        client: MockClient((_) async => http.Response('{}', 401)),
        baseUrl: 'https://x.test',
        boxPrefix: 'a_');
    await sync.syncNow();
    expect(a.settings.cloudSignedIn, isFalse);
    expect(sync.state, CloudSyncState.off);
    sync.dispose();
  });

  test('a card replay matches a single device that did both reviews', () async {
    a.add('apple');
    await a.syncNow();
    await b.syncNow();
    a.clock = DateTime.utc(2026, 11, 2);
    a.review('apple', Rating.good);
    b.clock = DateTime.utc(2026, 11, 5);
    b.review('apple', Rating.good);
    await a.syncNow();
    await b.syncNow();

    const scheduler = FsrsScheduler();
    var s = FsrsState.initial;
    s = scheduler.next(s, Rating.good, DateTime.utc(2026, 11, 2)).state;
    s = scheduler.next(s, Rating.good, DateTime.utc(2026, 11, 5)).state;
    final merged = b.repo.cardOf(b.repo.entryByWord('apple')!.id)!.fsrs;
    expect(merged.reps, s.reps);
    expect(merged.stability, closeTo(s.stability, 1e-9));
    expect(merged.due, s.due);
  });
}
