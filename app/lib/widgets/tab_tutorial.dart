import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../theme/mobile_theme.dart';

/// 各分頁的使用教學（卡 #893）: a few short steps per tab, written from what
/// the tab really has. Copy is UI copy: keys live in `ui_catalog.dart`.
const tabTutorials = <AppTab, List<String>>{
  AppTab.camera: [
    '對準身邊的東西按拍照，或點左下角選一張照片。',
    '拍完會找出照片裡的單字，並收進單字本。',
    '第一次使用時，請在系統提示出現時允許相機。',
  ],
  AppTab.album: [
    '這裡是你拍過、選過的所有照片。',
    '點一張照片，看上面的單字和意思。',
    '右上角可以搜尋照片或選新照片。',
  ],
  AppTab.review: [
    '這裡用字卡複習你學過的單字。',
    '先想一想答案，再翻開卡片核對。',
    '翻開後依記得多少評分，系統會安排下次複習的時間。',
  ],
  AppTab.words: [
    '這是你的單字本，列出所有收進來的字。',
    '點一個字看詳細內容；右上角可新增單字。',
    '想練習時按「開始複習」。',
  ],
  AppTab.settings: [
    '這裡可以改語言、卡片樣式和每天的學習量。',
    '往下捲還有資料備份、隱私和意見回饋。',
    '想再看一次教學，用「使用教學」。',
  ],
};

const tabTutorialNames = <AppTab, String>{
  AppTab.camera: '相機',
  AppTab.album: '相片冊',
  AppTab.review: '複習',
  AppTab.words: '單字本',
  AppTab.settings: '設定',
};

const tabTutorialTitles = <AppTab, String>{
  AppTab.camera: '相機怎麼用',
  AppTab.album: '相片冊怎麼用',
  AppTab.review: '複習怎麼用',
  AppTab.words: '單字本怎麼用',
  AppTab.settings: '設定怎麼用',
};

/// The tutorial card of the tab being shown. It sits over the bottom of the
/// tab but never covers all of it or takes touches elsewhere, so the camera
/// preview and the system permission dialog stay usable. Skipping or
/// finishing marks the tab as seen.
class TabTutorialOverlay extends StatefulWidget {
  final AppTab tab;
  final VoidCallback onDone;

  const TabTutorialOverlay(
      {super.key, required this.tab, required this.onDone});

  @override
  State<TabTutorialOverlay> createState() => _TabTutorialOverlayState();
}

class _TabTutorialOverlayState extends State<TabTutorialOverlay> {
  int _step = 0;

  @override
  Widget build(BuildContext context) {
    final steps = tabTutorials[widget.tab]!;
    final last = _step == steps.length - 1;
    final maxHeight = MediaQuery.sizeOf(context).height * 0.4;
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
        child: Material(
          key: const ValueKey('tab-tutorial'),
          color: MColors.surface,
          elevation: 6,
          borderRadius: MRadii.rSm,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxHeight: maxHeight),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Flexible(
                    child: SingleChildScrollView(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          UiText(tabTutorialTitles[widget.tab]!,
                              style: MFont.manrope(
                                  12, FontWeight.w700, MColors.primary)),
                          Text('${_step + 1}/${steps.length}',
                              style: MFont.manrope(
                                  11, FontWeight.w600, MColors.label)),
                          const SizedBox(height: 6),
                          UiText(steps[_step],
                              style: MFont.manrope(
                                  15, FontWeight.w600, MColors.ink)),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      TextButton(
                        key: const ValueKey('tab-tutorial-skip'),
                        onPressed: widget.onDone,
                        child: const UiText('略過'),
                      ),
                      const Spacer(),
                      FilledButton(
                        key: const ValueKey('tab-tutorial-next'),
                        onPressed: last
                            ? widget.onDone
                            : () => setState(() => _step++),
                        child: UiText(last ? '知道了' : '下一步'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
