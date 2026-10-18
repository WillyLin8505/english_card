import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/pack_media.dart';

void main() {
  test('server paths become the dictionary origin on a device', () {
    // flutter test runs as a VM: kIsWeb is false, Uri.base is not http.
    expect(
      resolvePackMedia('/api/image?id=9'),
      'http://127.0.0.1:8123/api/image?id=9',
    );
    expect(
      packRecordingUrl('/api/audio', 'audio/en/go.mp3'),
      'http://127.0.0.1:8123/api/audio?path=audio%2Fen%2Fgo.mp3',
    );
  });

  test('absolute URLs and bundled assets are left alone', () {
    expect(resolvePackMedia('http://localhost/media'), 'http://localhost/media');
    expect(
      packRecordingUrl('http://localhost/media', 'audio/en/go.mp3'),
      'http://localhost/media?path=audio%2Fen%2Fgo.mp3',
    );
    expect(
      packRecordingUrl(null, 'audio/en/go.mp3'),
      'assets/lexicon/media/audio/en/go.mp3',
    );
    expect(packMediaIsAsset('assets/lexicon/media/audio/en/go.mp3'), isTrue);
  });
}
