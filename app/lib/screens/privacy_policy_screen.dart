import 'package:flutter/material.dart';

import '../l10n/ui_text.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';

/// In-app privacy policy (App Store guideline 5.1.1(i)).
/// The same text is published at https://api.willylinai.com/privacy
/// (`docs/privacy.html`, served by serve_app.py).
class PrivacyPolicyScreen extends StatelessWidget {
  const PrivacyPolicyScreen({super.key});

  static const sections = <(String, String)>[
    (
      '隱私權政策',
      '本政策說明「拍照學單字」如何處理資料。分享使用統計預設是關閉的。匿名安裝與留存統計預設是打開的，可在設定裡關閉。',
    ),
    (
      '匿名安裝與留存',
      '「設定 → 匿名安裝與留存統計」預設是打開的，用來計算新安裝、有沒有完成引導、有沒有做第一次複習，以及安裝後第 1、7、30 天有沒有回來。'
          '打開時只送這次安裝的隨機編號，以及「安裝、完成引導、第一次拍照、第一次複習、每天開啟」這幾種事件的名稱和日期，送到我們自己的伺服器。'
          '不送姓名、帳號、電子郵件、照片、單字或位置，也不跟登入帳號合併。可以隨時關掉；關掉後還沒送出的事件會捨棄。'
          '這項跟「分享使用統計」分開。',
    ),
    (
      '使用統計',
      '打開「分享使用統計」之後，操作紀錄會送到 PostHog（主機 us.i.posthog.com）。'
          '送出的只有：這次安裝產生的隨機代號、開啟 App、所在分頁、學習語言、母語、程度與程度來源、'
          '有沒有加入照片或單字（不含照片和單字本身）、複習開始與結束，以及單次作答的評分、題型、對錯、'
          '提示次數、作答時間與下次間隔天數。不送姓名、帳號、電子郵件或廣告識別碼。'
          '隨時可以在設定裡關掉；還沒送出的紀錄會一併捨棄。',
    ),
    (
      '雲端帳號的使用數字',
      '只有登入雲端帳號的人，App 每天最多一次把數字送到自己的帳號伺服器，讓管理者看到用了哪些資料庫。'
          '送出的只有：已安裝的單字牌組與相片冊的名稱與類型、目前的學習語言與母語、單字數，以及複習與拍照的次數。'
          '不送單字內容、照片或位置。這些數字跟你的電子郵件放在同一筆帳號裡，刪除帳號時一併刪除。'
          '沒登入就不會送出。',
    ),
    (
      '照片與辨識',
      '照片和字卡保存在這台裝置。使用辨識時，照片會傳到你設定的辨識伺服器，只在記憶體裡即時辨識，'
          '不會存成照片檔。伺服器可能留下辨識結果的文字快取（單字與分數，不含照片），'
          '以免同一張照片重複運算。照片不會送到分析服務。',
    ),
    (
      '不做跨 App 追蹤',
      '本 App 只做自己的使用統計，不把資料拿去跟其他 App 或網站比對，也不使用廣告識別碼，'
          '所以不會跳出「允許追蹤」的詢問。',
    ),
    (
      '聯絡與政策網頁',
      '公開網址：https://api.willylinai.com/privacy（與 App Store 頁面相同內容）。'
          '要詢問本政策，或要求刪除已送到 PostHog 的匿名統計，請寫信到 sssss971412@gmail.com。',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MColors.canvas,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            MNavBar(
              title: '隱私權政策',
              leading: BackNavButton(onTap: () => Navigator.of(context).pop()),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(MSpace.lg),
                children: [
                  for (final section in sections) ...[
                    UiText(section.$1,
                        style: MFont.manrope(16, FontWeight.w800, MColors.ink)),
                    const SizedBox(height: 8),
                    UiText(section.$2,
                        style: MFont.manrope(14, FontWeight.w600, MColors.ink)),
                    const SizedBox(height: 20),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
