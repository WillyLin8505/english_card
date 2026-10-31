// 問題回報 #1135: after switching lens, tab or route the preview went black and
// the shutter did nothing. The iOS plugin keeps one camera: dispose ignores the
// id and closes whatever is current, and takePicture on no camera never
// completes. This fake behaves the same way.
import 'dart:async';

import 'package:camera_platform_interface/camera_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';

import 'helpers.dart';

class _IosLikeCamera extends CameraPlatform {
  int? current;
  int created = 0;
  bool hang = false;
  int takePictureCalls = 0;
  Duration disposeDelay = const Duration(milliseconds: 200);
  final _initialized = StreamController<CameraInitializedEvent>.broadcast();

  @override
  Future<List<CameraDescription>> availableCameras() async => const [
        CameraDescription(
            name: 'back',
            lensDirection: CameraLensDirection.back,
            sensorOrientation: 90),
        CameraDescription(
            name: 'front',
            lensDirection: CameraLensDirection.front,
            sensorOrientation: 90),
      ];

  @override
  Future<int> createCameraWithSettings(
      CameraDescription description, MediaSettings? mediaSettings) async {
    created++;
    current = created;
    return created;
  }

  @override
  Future<void> initializeCamera(int cameraId,
      {ImageFormatGroup imageFormatGroup = ImageFormatGroup.unknown}) async {
    scheduleMicrotask(() => _initialized.add(CameraInitializedEvent(cameraId,
        1280, 720, ExposureMode.auto, true, FocusMode.auto, true)));
  }

  @override
  Stream<CameraInitializedEvent> onCameraInitialized(int cameraId) =>
      _initialized.stream.where((e) => e.cameraId == cameraId);

  @override
  Stream<CameraErrorEvent> onCameraError(int cameraId) =>
      StreamController<CameraErrorEvent>.broadcast().stream;

  @override
  Stream<DeviceOrientationChangedEvent> onDeviceOrientationChanged() =>
      const Stream.empty();

  @override
  Future<void> dispose(int cameraId) async {
    await Future<void>.delayed(disposeDelay);
    current = null;
  }

  @override
  Future<XFile> takePicture(int cameraId) {
    takePictureCalls++;
    if (current == null || hang) return Completer<XFile>().future;
    return Future.value(XFile.fromData(Uint8List.fromList(const [1, 2, 3])));
  }

  @override
  Widget buildPreview(int cameraId) => const ColoredBox(color: Colors.black);
}

final _shutter = find.byKey(const ValueKey('camera-shutter'));
final _flip = find.byKey(const ValueKey('camera-flip'));

void main() {
  late _IosLikeCamera camera;

  setUp(() => CameraPlatform.instance = camera = _IosLikeCamera());

  Future<void> settle(WidgetTester tester) =>
      tester.pump(const Duration(seconds: 1));

  /// Closes the app and lets the fake's slow dispose finish.
  Future<void> finish(WidgetTester tester) async {
    await tester.pumpWidget(const SizedBox());
    await settle(tester);
  }

  testWidgets('a lens switch leaves a live camera', (tester) async {
    await pumpApp(tester);
    await settle(tester);
    await settle(tester);
    expect(camera.current, isNotNull);

    await tester.tap(_flip);
    await settle(tester);
    await settle(tester);
    expect(camera.created, 2);
    expect(camera.current, 2);
    await finish(tester);
  });

  testWidgets('quick lens switches end on one live camera', (tester) async {
    await pumpApp(tester);
    await settle(tester);
    await settle(tester);

    await tester.tap(_flip);
    await tester.pump(const Duration(milliseconds: 50));
    for (var i = 0; i < 6 && _flip.evaluate().isEmpty; i++) {
      await settle(tester);
    }
    await tester.tap(_flip);
    await settle(tester);
    await settle(tester);
    expect(camera.current, camera.created);
    await finish(tester);
  });

  testWidgets('leaving the tab and coming back leaves a live camera',
      (tester) async {
    final app = await pumpApp(tester);
    await settle(tester);
    await settle(tester);

    app.navigator.selectTab(AppTab.words);
    await tester.pump(const Duration(milliseconds: 50));
    app.navigator.selectTab(AppTab.camera);
    await settle(tester);
    await settle(tester);
    expect(camera.current, isNotNull);
    await finish(tester);
  });

  testWidgets('a shutter that gets no answer reopens the camera',
      (tester) async {
    await pumpApp(tester);
    await settle(tester);
    await settle(tester);

    camera.hang = true;
    await tester.tap(_shutter);
    await tester.pump(const Duration(seconds: 7));
    await settle(tester);
    await settle(tester);
    expect(find.text('相機沒有回應，已重新開啟，請再按一次'), findsOneWidget);
    expect(camera.created, 2);
    expect(camera.current, 2);

    camera.hang = false;
    await tester.pump(const Duration(seconds: 5));
    await settle(tester);
    await settle(tester);
    await tester.tap(_shutter);
    await settle(tester);
    expect(camera.takePictureCalls, 2);
    expect(find.text('存到相片冊'), findsWidgets);
    await finish(tester);
  });
}
