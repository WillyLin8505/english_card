import 'dart:io';
import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/widgets/mobile/photo_cache.dart';

void main() {
  test('failure reasons', () {
    final u = Uri.parse('http://x/a.jpg');
    expect(CachedNetworkPhoto.failureReason(const SocketException('x')),
        contains('網路'));
    expect(
        CachedNetworkPhoto.failureReason(
            NetworkImageLoadException(statusCode: 503, uri: u)),
        contains('忙碌'));
    expect(
        CachedNetworkPhoto.failureReason(
            NetworkImageLoadException(statusCode: 404, uri: u)),
        contains('找不到'));
  });
}
