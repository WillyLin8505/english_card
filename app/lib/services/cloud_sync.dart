import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;

import '../models/learning_card.dart';
import 'app_backup.dart';
import 'app_settings.dart';
import 'cloud_backup.dart';
import 'deck_library.dart';
import 'fsrs_optimizer.dart';
import 'fsrs_scheduler.dart';
import 'photo_store.dart';
import 'sync_index.dart';
import 'word_database_store.dart';

enum CloudSyncState {
  /// Not signed in, or 自動同步 is off.
  off,
  idle,
  syncing,

  /// No connection: changes stay queued and go up when it is back.
  offline,
  failed,

  /// The account holds data from a newer version of the App.
  needsUpdate,
  photoSpaceFull,
}

/// A record of another device, as pulled.
class _Incoming {
  final String id;
  final int stamp;
  final String device;
  final bool deleted;
  final Map<String, dynamic>? data;
  const _Incoming(this.id, this.stamp, this.device, this.deleted, this.data);
}

class _Stop implements Exception {
  final CloudSyncState state;
  const _Stop(this.state);
}

/// 跨裝置自動同步 (card #912, 問題回報 #1173; #902 only had one backup that
/// the last upload replaced). Signed in, each device keeps its own copy and
/// exchanges single records with the account:
///
/// - The newest write of a record wins (see [SyncMark], [SyncClock]). A
///   deleted record travels as a tombstone.
/// - Review logs are only ever added, named by word + time + grade, so an
///   upload that is repeated counts once. A card two devices reviewed offline
///   has its FSRS state rebuilt from all the logs in time order, so both end
///   up with the same schedule and neither review is lost.
/// - Words and cards are matched by the word, not by their per-device ids.
/// - Photo records travel with the rest; pixels go separately and can wait
///   for Wi-Fi ([AppSettings.syncPhotosWifiOnly]).
/// - Whatever happens offline stays marked in the sync index until the
///   server has taken it.
///
/// Not synced: this device's learning language, native language and 分享使用
/// 統計 (a consent is given per device).
class CloudSync extends ChangeNotifier {
  static const _batchRecords = 300;
  static const _batchBytes = 3 * 1024 * 1024;
  static const _settingsLanguage = '_';
  static const _settingsCollection = 'settings';
  static const _deviceFields = {
    'learningLanguage',
    'nativeLanguage',
    'shareUsageStats',
  };
  static const _retryMinutes = [1, 5, 15, 30];

  final AppSettings settings;
  final PhotoStore photoStore;
  final String baseUrl;
  final http.Client _client;

  /// Reopens the word database after records were applied.
  final Future<void> Function()? reload;

  /// False while pulled records must wait (a review is running).
  final bool Function()? canApply;
  final Future<bool> Function()? onWifi;
  final String boxPrefix;

  CloudSync(
    this.settings,
    this.photoStore, {
    http.Client? client,
    String? baseUrl,
    this.reload,
    this.canApply,
    this.onWifi,
    this.boxPrefix = '',
  })  : baseUrl = baseUrl ?? CloudBackup.accountUrl,
        _client = client ?? http.Client();

  CloudSyncState _state = CloudSyncState.off;
  CloudSyncState get state => _state;

  DateTime? _lastSyncedAt;
  DateTime? get lastSyncedAt => _lastSyncedAt;

  /// Records waiting for upload, photos waiting to go up or come down.
  int pendingRecords = 0;
  int pendingPhotos = 0;

  /// [pendingPhotos] are held back until Wi-Fi.
  bool photosWaitForWifi = false;

  bool _running = false, _again = false, _disposed = false;
  bool _wasSignedIn = false;
  int _failures = 0;
  Timer? _soon, _retry, _periodic;
  StreamSubscription<List<ConnectivityResult>>? _connectivity;

  bool get _enabled =>
      settings.cloudSignedIn &&
      settings.cloudSyncEnabled &&
      baseUrl.trim().isNotEmpty;

  /// Starts syncing on its own: now, after each change, every few minutes
  /// and when the connection comes back.
  void start() {
    _wasSignedIn = settings.cloudSignedIn;
    SyncBoxes.onLocalChange = () => syncSoon(const Duration(seconds: 15));
    settings.addListener(_settingsChanged);
    _periodic = Timer.periodic(
        const Duration(minutes: 5), (_) => syncSoon(Duration.zero));
    _connectivity = Connectivity().onConnectivityChanged.listen((r) {
      if (r.any((c) => c != ConnectivityResult.none)) syncSoon(Duration.zero);
    });
    syncSoon(Duration.zero);
  }

  void _settingsChanged() {
    final signedIn = settings.cloudSignedIn;
    final justSignedIn = signedIn && !_wasSignedIn;
    _wasSignedIn = signedIn;
    syncSoon(justSignedIn ? Duration.zero : const Duration(seconds: 15));
  }

  void syncSoon(Duration delay) {
    _soon?.cancel();
    _soon = Timer(delay, () => unawaited(syncNow()));
  }

  void _emit(CloudSyncState s) {
    _state = s;
    if (!_disposed) notifyListeners();
  }

  /// One round; failures show in [state] and retry on their own.
  Future<void> syncNow() async {
    if (_running) {
      _again = true;
      return;
    }
    if (!_enabled) {
      _emit(CloudSyncState.off);
      return;
    }
    _running = true;
    _retry?.cancel();
    _emit(CloudSyncState.syncing);
    var result = CloudSyncState.idle;
    try {
      await _cycle();
      _failures = 0;
      _lastSyncedAt = DateTime.now();
    } on _Stop catch (e) {
      result = e.state;
    } on TimeoutException {
      result = CloudSyncState.offline;
    } on http.ClientException {
      result = CloudSyncState.offline;
    } catch (e) {
      debugPrint('CloudSync: $e');
      result = CloudSyncState.failed;
    }
    _running = false;
    if (result == CloudSyncState.offline || result == CloudSyncState.failed) {
      final i = min(_failures++, _retryMinutes.length - 1);
      _retry = Timer(Duration(minutes: _retryMinutes[i]),
          () => unawaited(syncNow()));
    }
    _emit(result);
    if (_again) {
      _again = false;
      syncSoon(Duration.zero);
    }
  }

  Uri _uri(String path, [Map<String, String>? query]) => Uri.parse(baseUrl)
      .resolve('/api/account/sync/$path')
      .replace(queryParameters: query);

  Map<String, String> get _auth =>
      {'Authorization': 'Bearer ${settings.cloudToken}'};

  Never _fail(http.Response r) {
    if (r.statusCode == 401) {
      settings.setCloudAccount('', '');
      throw const _Stop(CloudSyncState.off);
    }
    if (r.statusCode == 507) throw const _Stop(CloudSyncState.photoSpaceFull);
    throw const _Stop(CloudSyncState.failed);
  }

  Future<Box<String>> _stateBox() =>
      Hive.openBox<String>('${boxPrefix}sync_state');

  Future<void> _cycle() async {
    final state = await _stateBox();
    final device = state.get('device') ?? _newDevice();
    await state.put('device', device);
    SyncClock.observe(int.tryParse(state.get('clock') ?? '') ?? 0);

    final books = <String, SyncBoxes>{
      for (final language in supportedLanguages.keys)
        language: (await HiveWordDatabaseStore.open(
                language: language, boxPrefix: boxPrefix))
            .sync,
    };
    // Another account on this device: its data is new to that account.
    if (state.get('account') != settings.cloudEmail) {
      for (final b in books.values) {
        for (final c in SyncBoxes.collections) {
          for (final (id, m) in b.marks(c).toList()) {
            await b.setMark(
                c,
                id,
                m.copyWith(
                    pending: true,
                    blob: m.blob == SyncMark.blobSent
                        ? SyncMark.blobToSend
                        : m.blob));
          }
        }
      }
      await state.delete('cursor');
      await state.put('account', settings.cloudEmail);
    }
    for (final e in books.entries) {
      await e.value.indexExisting(device);
      await _noteDecks(e.key, e.value);
    }
    await _noteSettings(state);

    // Mid-review the session's cards must not change under the learner:
    // uploads go on, what came down waits for the next round.
    final free = canApply?.call() ?? true;
    if (free && await _pull(state, device, books)) _reloadDue = true;
    await _push(state, device, books);
    if (await _photos(books)) _reloadDue = true;
    pendingRecords = books.values.fold(0, (n, b) => n + b.pendingCount);
    await state.put('clock', '${SyncClock.next()}');
    if (_reloadDue && (canApply?.call() ?? true)) {
      _reloadDue = false;
      await reload?.call();
    }
    if (!free) syncSoon(const Duration(minutes: 1));
    if (_stoppedPhotos != null) throw _Stop(_stoppedPhotos!);
  }

  CloudSyncState? _stoppedPhotos;
  bool _reloadDue = false;

  static String _newDevice() {
    final r = Random.secure();
    return '${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}-'
        '${r.nextInt(1 << 32).toRadixString(36)}';
  }

  // ── Changes that have no write hook ──────────────────────────────────

  Future<Box<String>> _deckBox() =>
      Hive.openBox<String>('${boxPrefix}installed_decks_v1');

  static String _slugOf(Map<String, dynamic> deck) =>
      (deck['info'] as Map)['slug'] as String;

  List<Map<String, dynamic>> _decksOf(Box<String> box, String language) => [
        for (final d in jsonDecode(box.get(language) ?? '[]') as List)
          (d as Map).cast<String, dynamic>()
      ];

  Future<void> _noteDecks(String language, SyncBoxes b) async {
    final decks = _decksOf(await _deckBox(), language);
    final slugs = {for (final d in decks) _slugOf(d)};
    for (final slug in slugs) {
      final m = b.mark(SyncBoxes.decks, slug);
      if (m == null || m.deleted) await b.touch(SyncBoxes.decks, slug, slug);
    }
    for (final (slug, m) in b.marks(SyncBoxes.decks).toList()) {
      if (!m.deleted && !slugs.contains(slug)) {
        await b.touch(SyncBoxes.decks, slug, slug, deleted: true);
      }
    }
  }

  Map<String, Object> get _syncedSettings => {
        for (final e in AppBackup.settingsOf(settings).entries)
          if (!_deviceFields.contains(e.key)) e.key: e.value,
      };

  Future<void> _noteSettings(Box<String> state) async {
    for (final e in _syncedSettings.entries) {
      final key = 'set/${e.key}';
      final raw = state.get(key);
      final mark = raw == null ? null : SyncMark.decode(raw);
      final value = jsonEncode(e.value);
      if (mark?.value == value) continue;
      await state.put(
          key,
          SyncMark(
                  // Defaults a device never changed lose to a real choice.
                  stamp: mark == null ? 1 : SyncClock.next(),
                  wire: e.key,
                  pending: true,
                  value: value)
              .encode());
    }
  }

  // ── Pull ─────────────────────────────────────────────────────────────

  Future<bool> _pull(Box<String> state, String device,
      Map<String, SyncBoxes> books) async {
    var since = int.tryParse(state.get('cursor') ?? '') ?? 0;
    final all = <Map<String, dynamic>>[];
    while (true) {
      final r = await _client
          .get(
              _uri('pull',
                  {'since': '$since', 'limit': '1000', 'device': device}),
              headers: _auth)
          .timeout(const Duration(seconds: 60));
      if (r.statusCode != 200) _fail(r);
      final page = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
      all.addAll((page['records'] as List).cast<Map<String, dynamic>>());
      since = page['next'] as int;
      if (page['more'] != true) break;
    }
    final groups = <String, Map<String, List<_Incoming>>>{};
    var newest = 0;
    for (final r in all) {
      final key = r['key'] as String;
      final a = key.indexOf('/');
      final b = key.indexOf('/', a + 1);
      if (a < 0 || b < 0) continue;
      final deleted = r['deleted'] == true;
      final data = deleted
          ? null
          : (jsonDecode(r['data'] as String) as Map).cast<String, dynamic>();
      if ((data?['_v'] as int? ?? 0) > HiveWordDatabaseStore.schemaVersion) {
        throw const _Stop(CloudSyncState.needsUpdate);
      }
      final stamp = r['stamp'] as int;
      newest = max(newest, stamp);
      (groups[key.substring(0, a)] ??= {})
          .putIfAbsent(key.substring(a + 1, b), () => [])
          .add(_Incoming(key.substring(b + 1), stamp, r['device'] as String,
              deleted, data));
    }
    var changed = false;
    for (final e in groups.entries) {
      if (e.key == _settingsLanguage) {
        await _applySettings(state, device, e.value[_settingsCollection] ?? []);
        continue;
      }
      final b = books[e.key];
      if (b == null) continue;
      if (await _applyLanguage(e.key, b, device, e.value) &&
          e.key == settings.learningLanguage) {
        changed = true;
      }
    }
    SyncClock.observe(newest);
    await state.put('cursor', '$since');
    return changed;
  }

  bool _replaces(SyncMark? mine, _Incoming r, String device) {
    if (mine == null) return true;
    final who = mine.device.isEmpty ? device : mine.device;
    return mine.stamp < r.stamp ||
        (mine.stamp == r.stamp && who.compareTo(r.device) < 0);
  }

  SyncMark _applied(_Incoming r, String wire, {SyncMark? old, int? blob}) =>
      SyncMark(
        stamp: r.stamp,
        wire: wire,
        device: r.device,
        deleted: r.deleted,
        logKey: old?.logKey,
        blob: blob ?? old?.blob ?? SyncMark.blobSent,
      );

  static Map<String, dynamic> _clean(Map<String, dynamic> data) =>
      {...data}..remove('_v')..remove('_w');

  Future<bool> _applyLanguage(String language, SyncBoxes b, String device,
      Map<String, List<_Incoming>> groups) async {
    var changed = false;
    final entryIdOf = <String, String>{
      for (final (id, m) in b.marks(SyncBoxes.entries)) m.wire: id,
    };
    final cardIdOf = <String, String>{
      for (final (id, m) in b.marks(SyncBoxes.cards)) m.wire: id,
    };

    // Records named by their own id, same on every device.
    Future<void> plain(String collection,
        Future<void> Function(_Incoming r, SyncMark? mine)? write) async {
      for (final r in groups[collection] ?? const <_Incoming>[]) {
        final mine = b.mark(collection, r.id);
        if (!_replaces(mine, r, device)) {
          continue;
        }
        changed = true;
        if (r.deleted) {
          await b.boxOf(collection)!.delete(r.id);
          await b.setMark(collection, r.id, _applied(r, r.id, old: mine));
        } else if (write != null) {
          await write(r, mine);
        } else {
          await b
              .boxOf(collection)!
              .put(r.id, jsonEncode(_clean(r.data!)));
          await b.setMark(collection, r.id, _applied(r, r.id, old: mine));
        }
      }
    }

    await plain(SyncBoxes.albums, null);

    final gone = <String>{};
    for (final r in groups[SyncBoxes.entries] ?? const <_Incoming>[]) {
      final local = entryIdOf[r.id];
      final mine = local == null ? null : b.mark(SyncBoxes.entries, local);
      if (!_replaces(mine, r, device)) continue;
      if (r.deleted) {
        if (local == null) continue;
        changed = true;
        gone.add(local);
        await b.entriesBox.delete(local);
        await b.setMark(SyncBoxes.entries, local, _applied(r, r.id, old: mine));
        continue;
      }
      changed = true;
      final id = local ?? r.data!['id'] as String;
      await b.entriesBox.put(id, jsonEncode(_clean(r.data!)..['id'] = id));
      await b.setMark(SyncBoxes.entries, id, _applied(r, r.id, old: mine));
      entryIdOf[r.id] = id;
    }

    await plain(SyncBoxes.photos, (r, mine) async {
      final here = b.photosBox.get(r.id);
      final old = here == null
          ? const <String, dynamic>{}
          : jsonDecode(here) as Map<String, dynamic>;
      final json = _clean(r.data!);
      final hasBlob = json.remove('hasBlob') == true;
      final path = old['filePath'], key = old['storedKey'];
      json['filePath'] = path;
      json['storedKey'] = key;
      await b.photosBox.put(r.id, jsonEncode(json));
      await b.setMark(
          SyncBoxes.photos,
          r.id,
          _applied(r, r.id,
              old: mine,
              blob: path != null || key != null
                  ? SyncMark.blobSent
                  : hasBlob
                      ? SyncMark.blobToFetch
                      : SyncMark.blobNone));
    });

    await plain(SyncBoxes.occurrences, (r, mine) async {
      final entry = entryIdOf[r.data!['_w']];
      if (entry == null) return;
      await b.occurrencesBox
          .put(r.id, jsonEncode(_clean(r.data!)..['wordEntryId'] = entry));
      await b.setMark(SyncBoxes.occurrences, r.id, _applied(r, r.id, old: mine));
    });

    final affected = <String>{};
    for (final r in groups[SyncBoxes.cards] ?? const <_Incoming>[]) {
      final known = cardIdOf[r.id];
      final mine = known == null ? null : b.mark(SyncBoxes.cards, known);
      if (!_replaces(mine, r, device)) continue;
      if (r.deleted) {
        if (known == null) continue;
        changed = true;
        await b.cardsBox.delete(known);
        await b.setMark(SyncBoxes.cards, known, _applied(r, r.id, old: mine));
        continue;
      }
      final entry = entryIdOf[r.id];
      if (entry == null) continue;
      changed = true;
      final id = known ?? LearningCard.idFor(entry);
      await b.cardsBox.put(
          id,
          jsonEncode(_clean(r.data!)
            ..['id'] = id
            ..['wordEntryId'] = entry));
      await b.setMark(SyncBoxes.cards, id, _applied(r, r.id, old: mine));
      cardIdOf[r.id] = id;
      affected.add(id);
    }

    final newLogs = <String>{};
    for (final r in groups[SyncBoxes.logs] ?? const <_Incoming>[]) {
      final logId = SyncBoxes.logId(r.id);
      if (b.mark(SyncBoxes.logs, logId) != null) continue; // already counted
      final word = r.data!['_w'] as String?;
      final entry = entryIdOf[word];
      final card = cardIdOf[word] ??
          (entry == null ? null : LearningCard.idFor(entry)) ??
          r.data!['cardId'] as String;
      final key =
          await b.logsBox.add(jsonEncode(_clean(r.data!)..['cardId'] = card));
      await b.setMark(SyncBoxes.logs, logId,
          SyncMark(stamp: r.stamp, wire: r.id, device: r.device, logKey: key));
      newLogs.add(card);
      changed = true;
    }
    // A card whose only news is its record keeps it unless logs say more:
    // the optimizer rewrites stability without adding a log.
    await _rebuildCards(language, b, newLogs);

    await plain(SyncBoxes.meta, (r, mine) async {
      await b.metaBox.put(r.id, r.data!['raw'] as String);
      await b.setMark(SyncBoxes.meta, r.id, _applied(r, r.id, old: mine));
    });
    for (final r in groups[SyncBoxes.meta] ?? const <_Incoming>[]) {
      if (r.id != 'profile' || r.deleted) continue;
      final mine = b.metaBox.get(r.id);
      if (mine == null) continue;
      final merged = _mergeProfile(mine, r.data!['raw'] as String);
      if (merged != mine) {
        changed = true;
        await b.put(SyncBoxes.meta, r.id, merged);
      }
    }

    if (await _applyDecks(language, b, device, groups[SyncBoxes.decks])) {
      changed = true;
    }

    // Records of a word that is gone: the tombstones come with them, except
    // for a card reviewed elsewhere after the word was deleted.
    for (final id in gone) {
      for (final (box, c) in [
        (b.cardsBox, SyncBoxes.cards),
        (b.occurrencesBox, SyncBoxes.occurrences),
      ]) {
        for (final k in box.keys.toList()) {
          final j = jsonDecode(box.get(k)!) as Map<String, dynamic>;
          if (j['wordEntryId'] == id) {
            await box.delete(k);
            await b.forget(c, '$k');
          }
        }
      }
    }
    return changed;
  }

  /// Per-word familiarity is the 已學會清單: words either device marked stay,
  /// whichever profile was written last.
  static String _mergeProfile(String mine, String theirs) {
    final a = jsonDecode(mine) as Map<String, dynamic>;
    final b = jsonDecode(theirs) as Map<String, dynamic>;
    var changed = false;
    for (final f in const ['familiarity', 'exposure']) {
      final to = a[f], from = b[f];
      if (to is! Map || from is! Map) continue;
      for (final e in from.entries) {
        if (!to.containsKey(e.key)) {
          to[e.key] = e.value;
          changed = true;
        }
      }
    }
    return changed ? jsonEncode(a) : mine;
  }

  FsrsScheduler _schedulerOf(SyncBoxes b) {
    FsrsOptimization? optimization;
    try {
      final raw = b.metaBox.get('fsrsOptimization');
      final json = raw == null ? null : jsonDecode(raw);
      if (json is Map<String, dynamic>) {
        optimization = FsrsOptimization.decode(json);
      }
    } catch (_) {
      // Default weights, as a repository does with an unreadable record.
    }
    return FsrsScheduler(FsrsParameters(
      w: optimization?.weights ?? FsrsParameters.defaultWeights,
      desiredRetention: settings.desiredRetention,
    ));
  }

  /// Runs each card's logs in time order. A log that followed from the state
  /// before it keeps its result; one that was made on another device, from
  /// a state that missed the other's reviews, is computed again.
  Future<void> _rebuildCards(
      String language, SyncBoxes b, Set<String> cardIds) async {
    if (cardIds.isEmpty) return;
    final logs = <String, List<ReviewLog>>{};
    for (final raw in b.logsBox.values) {
      final log = ReviewLog.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      if (cardIds.contains(log.cardId)) (logs[log.cardId] ??= []).add(log);
    }
    String enc(FsrsState s) => jsonEncode(s.toJson());
    final scheduler = _schedulerOf(b);
    for (final e in logs.entries) {
      final raw = b.cardsBox.get(e.key);
      if (raw == null) continue;
      final rows = e.value
        ..sort((x, y) {
          final t = x.reviewedAt.compareTo(y.reviewedAt);
          return t != 0 ? t : x.rating.index.compareTo(y.rating.index);
        });
      var state = rows.first.before;
      for (final l in rows) {
        state = enc(state) == enc(l.before)
            ? l.after
            : scheduler.next(state, l.rating, l.reviewedAt).state;
      }
      final json = jsonDecode(raw) as Map<String, dynamic>;
      json['fsrs'] = state.toJson();
      json['updatedAt'] = rows.last.reviewedAt.toIso8601String();
      await b.cardsBox.put(e.key, jsonEncode(json));
    }
  }

  Future<bool> _applyDecks(String language, SyncBoxes b, String device,
      List<_Incoming>? incoming) async {
    if (incoming == null) return false;
    final box = await _deckBox();
    final decks = _decksOf(box, language);
    var changed = false;
    for (final r in incoming) {
      final mine = b.mark(SyncBoxes.decks, r.id);
      if (!_replaces(mine, r, device)) continue;
      await b.setMark(SyncBoxes.decks, r.id, _applied(r, r.id, old: mine));
      final at = decks.indexWhere((d) => _slugOf(d) == r.id);
      if (r.deleted && at >= 0) {
        decks.removeAt(at);
        changed = true;
      } else if (!r.deleted && at < 0) {
        decks.add((jsonDecode(r.data!['raw'] as String) as Map)
            .cast<String, dynamic>());
        changed = true;
      }
    }
    if (changed) {
      await box.put(language, jsonEncode(decks));
      DeckLibrary.instance.forgetLoaded();
    }
    return changed;
  }

  Future<void> _applySettings(
      Box<String> state, String device, List<_Incoming> incoming) async {
    for (final r in incoming) {
      if (_deviceFields.contains(r.id) || r.deleted) continue;
      final key = 'set/${r.id}';
      final raw = state.get(key);
      if (!_replaces(raw == null ? null : SyncMark.decode(raw), r, device)) {
        continue;
      }
      AppBackup.applySettings(settings, {r.id: r.data!['value']});
      final now = _syncedSettings[r.id];
      await state.put(
          key,
          SyncMark(
                  stamp: r.stamp,
                  wire: r.id,
                  device: r.device,
                  value: jsonEncode(now))
              .encode());
    }
  }

  // ── Push ─────────────────────────────────────────────────────────────

  /// What [mark] sends, or null when the record is no longer here.
  String? _wireData(SyncBoxes b, String collection, String id, SyncMark mark) {
    String wrap(String raw) => jsonEncode({
          'raw': raw,
          '_v': HiveWordDatabaseStore.schemaVersion,
        });
    if (collection == SyncBoxes.meta) {
      final raw = b.metaBox.get(id);
      return raw == null ? null : wrap(raw);
    }
    final raw = collection == SyncBoxes.logs
        ? b.logsBox.get(mark.logKey)
        : b.boxOf(collection)!.get(id);
    if (raw == null) return null;
    final json = jsonDecode(raw) as Map<String, dynamic>;
    json['_v'] = HiveWordDatabaseStore.schemaVersion;
    switch (collection) {
      case SyncBoxes.photos:
        json['hasBlob'] = json['filePath'] != null || json['storedKey'] != null;
        json
          ..remove('filePath')
          ..remove('storedKey');
      case SyncBoxes.occurrences:
        json['_w'] = b.wordOf(json['wordEntryId'] as String);
      case SyncBoxes.cards:
        json['_w'] = mark.wire;
      case SyncBoxes.logs:
        json['_w'] = b.wordOfCard(json['cardId'] as String);
    }
    return jsonEncode(json);
  }

  Future<String?> _deckData(String language, String slug) async {
    for (final d in _decksOf(await _deckBox(), language)) {
      if (_slugOf(d) == slug) {
        // Those ids belong to this device; `words` names the same words.
        return jsonEncode({
          'raw': jsonEncode({...d, 'wordEntryIds': const <String>[]}),
          '_v': HiveWordDatabaseStore.schemaVersion,
        });
      }
    }
    return null;
  }

  Future<void> _send(
      String device, List<Map<String, Object?>> records) async {
    final r = await _client
        .post(_uri('push'),
            headers: {..._auth, 'Content-Type': 'application/json'},
            body: jsonEncode({'device': device, 'records': records}))
        .timeout(const Duration(seconds: 60));
    if (r.statusCode != 200) _fail(r);
  }

  Future<void> _push(Box<String> state, String device,
      Map<String, SyncBoxes> books) async {
    var batch = <Map<String, Object?>>[];
    var done = <Future<void> Function()>[];
    var bytes = 0;
    Future<void> flush() async {
      if (batch.isEmpty) return;
      await _send(device, batch);
      for (final clear in done) {
        await clear();
      }
      batch = [];
      done = [];
      bytes = 0;
    }

    Future<void> add(Map<String, Object?> record, int size,
        Future<void> Function() clear) async {
      batch.add(record);
      done.add(clear);
      bytes += size;
      if (batch.length >= _batchRecords || bytes >= _batchBytes) await flush();
    }

    for (final e in books.entries) {
      final language = e.key;
      final b = e.value;
      for (final c in SyncBoxes.collections) {
        for (final (id, m) in b.marks(c).toList()) {
          if (!m.pending) continue;
          // Sent, unless it changed again meanwhile.
          Future<void> clear() async {
            final now = b.mark(c, id);
            if (now?.stamp == m.stamp) {
              await b.setMark(c, id, now!.copyWith(pending: false));
            }
          }

          final data = m.deleted
              ? null
              : c == SyncBoxes.decks
                  ? await _deckData(language, id)
                  : _wireData(b, c, id, m);
          if (data == null && !m.deleted) {
            await clear();
            continue;
          }
          await add({
            'key': '$language/$c/${m.wire}',
            'stamp': m.stamp,
            'deleted': m.deleted,
            'data': data,
          }, data?.length ?? 64, clear);
        }
      }
    }
    for (final key in state.keys.toList()) {
      if (!'$key'.startsWith('set/')) continue;
      final m = SyncMark.decode(state.get(key)!);
      if (!m.pending) continue;
      final data = jsonEncode({'value': jsonDecode(m.value!)});
      await add({
        'key': '$_settingsLanguage/$_settingsCollection/${m.wire}',
        'stamp': m.stamp,
        'deleted': false,
        'data': data,
      }, data.length, () async {
        final raw = state.get(key);
        if (raw == null) return;
        final now = SyncMark.decode(raw);
        if (now.stamp == m.stamp) {
          await state.put(key, now.copyWith(pending: false).encode());
        }
      });
    }
    await flush();
  }

  // ── Photo files ──────────────────────────────────────────────────────

  Future<bool> _wifiNow() async {
    if (onWifi != null) return onWifi!();
    if (kIsWeb) return true;
    final now = await Connectivity().checkConnectivity();
    return now.contains(ConnectivityResult.wifi) ||
        now.contains(ConnectivityResult.ethernet);
  }

  /// Uploads and fetches photo files, one at a time. True when a fetched
  /// photo changed the current language's records.
  Future<bool> _photos(Map<String, SyncBoxes> books) async {
    _stoppedPhotos = null;
    final work = <(String, SyncBoxes, String, SyncMark)>[
      for (final e in books.entries)
        for (final (id, m) in e.value.marks(SyncBoxes.photos))
          if (!m.deleted &&
              (m.blob == SyncMark.blobToSend || m.blob == SyncMark.blobToFetch))
            (e.key, e.value, id, m),
    ];
    pendingPhotos = work.length;
    photosWaitForWifi = false;
    if (work.isEmpty || !settings.syncPhotos) return false;
    if (settings.syncPhotosWifiOnly && !await _wifiNow()) {
      photosWaitForWifi = true;
      return false;
    }
    var fetched = false;
    for (final (language, b, id, m) in work) {
      final raw = b.photosBox.get(id);
      if (raw == null) continue;
      final json = jsonDecode(raw) as Map<String, dynamic>;
      if (m.blob == SyncMark.blobToSend) {
        final bytes = await AppBackup.photoBytes(json, photoStore);
        if (bytes == null) {
          await b.setMark(
              SyncBoxes.photos, id, m.copyWith(blob: SyncMark.blobNone));
        } else {
          final r = await _client
              .post(_uri('blob/$id'),
                  headers: {
                    ..._auth,
                    'Content-Type': 'application/octet-stream'
                  },
                  body: bytes)
              .timeout(const Duration(minutes: 2));
          if (r.statusCode == 507) {
            _stoppedPhotos = CloudSyncState.photoSpaceFull;
            return fetched;
          }
          if (r.statusCode != 200) _fail(r);
          await b.setMark(
              SyncBoxes.photos, id, m.copyWith(blob: SyncMark.blobSent));
        }
      } else {
        final r = await _client
            .get(_uri('blob/$id'), headers: _auth)
            .timeout(const Duration(minutes: 2));
        if (r.statusCode == 404) continue; // the other device has not sent it
        if (r.statusCode != 200) _fail(r);
        final saved = await photoStore.save(id, r.bodyBytes);
        json['filePath'] = saved.filePath;
        json['storedKey'] = saved.storedKey;
        await b.photosBox.put(id, jsonEncode(json));
        await b.setMark(
            SyncBoxes.photos, id, m.copyWith(blob: SyncMark.blobSent));
        if (language == settings.learningLanguage) fetched = true;
      }
      pendingPhotos--;
      if (!_disposed) notifyListeners();
    }
    return fetched;
  }

  @override
  void dispose() {
    _disposed = true;
    _soon?.cancel();
    _retry?.cancel();
    _periodic?.cancel();
    unawaited(_connectivity?.cancel());
    settings.removeListener(_settingsChanged);
    if (SyncBoxes.onLocalChange != null) SyncBoxes.onLocalChange = null;
    super.dispose();
  }
}
