import 'dart:async';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:photo_english_app/services/audio_file_cache.dart';
import 'package:photo_english_app/services/speaker.dart';
import 'package:flutter_test/flutter_test.dart';

// 問題回報 #684（單字詳情 actor）：「這聲音需要等很久的時間」— server
// recordings were streamed again on every tap.
void main() {
  late Directory tmp;
  late List<Uri> downloads;
  late List<Source> played;

  setUp(() {
    tmp = Directory.systemTemp.createTempSync('card684_');
    downloads = [];
    played = [];
  });
  tearDown(() => tmp.deleteSync(recursive: true));

  AudioFileCache cache(
          {Future<List<int>> Function(Uri)? download, int maxFiles = 300}) =>
      AudioFileCache(
        directory: () async => Directory('${tmp.path}/audio_cache'),
        download: download ??
            (url) async {
              downloads.add(url);
              return [1, 2, 3, 4];
            },
        maxFiles: maxFiles,
      );

  DeviceSpeaker speaker(AudioFileCache c) =>
      DeviceSpeaker(cache: c, play: (source) async => played.add(source));

  const url = 'https://api.willylinai.com/api/audio?path=audio/en/actor.mp3';

  test('first say downloads and keeps the clip, the second plays the file',
      () async {
    final s = speaker(cache());
    expect(await s.say('actor', language: 'en', audioUrl: url), isTrue);
    expect(downloads, [Uri.parse(url)]);
    final first = played.single as DeviceFileSource;
    expect(first.path, endsWith('.mp3'));
    expect(File(first.path).readAsBytesSync(), [1, 2, 3, 4]);

    expect(await s.say('actor', language: 'en', audioUrl: url), isTrue);
    expect(downloads, hasLength(1));
    expect((played.last as DeviceFileSource).path, first.path);
  });

  test('a prefetched clip plays without downloading again', () async {
    final c = cache();
    final s = speaker(c);
    prefetchRecordings(s, [url, null, 'assets/lexicon/media/a.mp3']);
    // Asked again while the download is running: still one download.
    s.prefetch(url);
    await c.file(url);
    expect(downloads, hasLength(1));

    await s.say('actor', language: 'en', audioUrl: url);
    expect(downloads, hasLength(1));
    expect(played.single, isA<DeviceFileSource>());
  });

  test('the same URL asked for at once is downloaded once', () async {
    final gate = Completer<void>();
    final c = cache(download: (u) async {
      downloads.add(u);
      await gate.future;
      return [9];
    });
    final files = [c.file(url), c.file(url), c.file(url)];
    gate.complete();
    final got = await Future.wait(files);
    expect(downloads, hasLength(1));
    expect(got.map((f) => f!.path).toSet(), hasLength(1));
  });

  test('a failed download streams the URL as before', () async {
    final s = speaker(cache(download: (u) async {
      downloads.add(u);
      throw const SocketException('offline');
    }));
    expect(await s.say('actor', language: 'en', audioUrl: url), isTrue);
    expect((played.single as UrlSource).url, url);
  });

  test('bundled clips are played as assets, not cached', () async {
    final s = speaker(cache());
    await s.say('go', language: 'en', audioUrl: 'assets/lexicon/media/go.mp3');
    expect(downloads, isEmpty);
    expect((played.single as AssetSource).path, 'lexicon/media/go.mp3');
  });

  test('the oldest clips are deleted past the limit', () async {
    final c = cache(maxFiles: 2);
    final a = (await c.file('$url&n=1'))!;
    a.setLastModifiedSync(DateTime(2020));
    await c.file('$url&n=2');
    await c.file('$url&n=3');
    final left = Directory('${tmp.path}/audio_cache').listSync();
    expect(left, hasLength(2));
    expect(a.existsSync(), isFalse);
  });

  test('file names are stable per URL and keep the extension', () {
    expect(AudioFileCache.fileName(url), AudioFileCache.fileName(url));
    expect(AudioFileCache.fileName(url),
        isNot(AudioFileCache.fileName('$url&x=1')));
    expect(AudioFileCache.fileName('https://x/y.m4a'), endsWith('.m4a'));
  });
}
