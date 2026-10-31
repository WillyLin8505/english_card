import 'package:flutter_test/flutter_test.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:photo_english_app/services/crash_reporting.dart';

SentryEvent _event() => SentryEvent(
      user: SentryUser(email: 'a@b.c', id: '1'),
      request: SentryRequest(url: 'https://x/y?word=cat'),
      breadcrumbs: [Breadcrumb(message: 'opened photo of my dog')],
      extra: {'word': 'cat'},
      message: SentryMessage('word cat failed'),
      serverName: 'pc',
      tags: {'handled': 'no', 'word': 'cat', 'app.screen': 'album'},
      exceptions: [
        SentryException(type: 'StateError', value: 'no word "cat"'),
      ],
    );

void main() {
  tearDown(() {
    CrashReporting.instance.sharing = false;
    CrashReporting.instance.debugTreatAsEnabled = false;
  });

  test('without SENTRY_DSN nothing starts and the app still runs', () async {
    final c = CrashReporting.instance;
    expect(c.enabled, isFalse);
    var ran = false;
    await c.run(() => ran = true);
    expect(ran, isTrue);
  });

  test('events are dropped while sharing is off', () {
    final c = CrashReporting.instance;
    c.debugTreatAsEnabled = true;
    expect(c.beforeSend(_event(), Hint()), isNull);
  });

  test('with sharing on, learner content is stripped', () {
    final c = CrashReporting.instance..sharing = true;
    final e = c.beforeSend(_event(), Hint())!;
    expect(e.user, isNull);
    expect(e.request, isNull);
    expect(e.breadcrumbs, isEmpty);
    expect(e.extra, isNull);
    expect(e.message, isNull);
    expect(e.serverName, isNull);
    expect(e.tags, {'handled': 'no', 'app.screen': 'album'});
    expect(e.exceptions!.single.type, 'StateError');
    expect(e.exceptions!.single.value, isNull);
  });

  test('options turn off every automatic data source', () {
    final o = SentryFlutterOptions();
    CrashReporting.instance.configure(o);
    expect(o.sendDefaultPii, isFalse);
    expect(o.maxBreadcrumbs, 0);
    expect(o.attachScreenshot, isFalse);
    expect(o.attachViewHierarchy, isFalse);
    expect(o.tracesSampleRate, isNull);
    expect(o.beforeSend, isNotNull);
  });
}
