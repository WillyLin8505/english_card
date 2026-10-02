import 'dart:async';

import 'package:flutter/material.dart';

import '../theme/mobile_theme.dart';
import '../widgets/mobile/m_icon.dart';

/// Presents the phone UI on wide screens (web / desktop): the app runs
/// inside a 402×874 device — the Figma frames' size — with the mock's
/// status bar and a home indicator drawn as device chrome, scaled down
/// to fit the window. On a phone-sized screen it gets out of the way and
/// the OS draws the real status bar.
class PhoneFrame extends StatelessWidget {
  static const deviceSize = Size(402, 874);
  static const statusBarHeight = 44.0;

  final Widget child;

  const PhoneFrame({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final screen = MediaQuery.sizeOf(context);
    if (screen.width < 600) return child;

    final outer = MediaQuery.of(context);
    return ColoredBox(
      color: MColors.canvas,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: FittedBox(
            child: Container(
              width: deviceSize.width,
              height: deviceSize.height,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(36),
                boxShadow: const [
                  BoxShadow(
                      color: Color(0x2E1C2434),
                      blurRadius: 40,
                      offset: Offset(0, 16)),
                ],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(36),
                child: MediaQuery(
                  data: outer.copyWith(
                    size: deviceSize,
                    padding: const EdgeInsets.only(top: statusBarHeight),
                    viewPadding: const EdgeInsets.only(top: statusBarHeight),
                    viewInsets: EdgeInsets.zero,
                  ),
                  child: Stack(
                    children: [
                      Positioned.fill(child: child),
                      const Positioned(
                        left: 0,
                        right: 0,
                        top: 0,
                        height: statusBarHeight,
                        child: IgnorePointer(child: _StatusBar()),
                      ),
                      const Positioned(
                        left: 0,
                        right: 0,
                        bottom: 8,
                        child: IgnorePointer(child: _HomeIndicator()),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Figma status-bar (e.g. 36:45): clock in Manrope Bold 15, then signal,
/// wifi and battery icons.
class _StatusBar extends StatefulWidget {
  const _StatusBar();

  @override
  State<_StatusBar> createState() => _StatusBarState();
}

class _StatusBarState extends State<_StatusBar> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer =
        Timer.periodic(const Duration(seconds: 20), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final time = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Row(
        children: [
          Text(time, style: MFont.manrope(15, FontWeight.w700, MColors.ink)),
          const Spacer(),
          const MSvg(MIcon.statusSignal, size: 20),
          const SizedBox(width: 6),
          const MSvg(MIcon.statusWifi, size: 20),
          const SizedBox(width: 6),
          const MSvg.sized(MIcon.statusBattery, width: 28, height: 20),
        ],
      ),
    );
  }
}

/// Figma home-indicator (17:84): 134×5, black, fully rounded.
class _HomeIndicator extends StatelessWidget {
  const _HomeIndicator();

  @override
  Widget build(BuildContext context) => Center(
        child: Container(
          width: 134,
          height: 5,
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(100),
          ),
        ),
      );
}
