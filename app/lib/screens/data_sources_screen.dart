import 'package:flutter/material.dart';

import '../l10n/ui_text.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';

/// 關於／資料來源與授權 (card #259). Each source names its license and the
/// link to the license text, as CC BY and CC BY-SA require.
class DataSourcesScreen extends StatelessWidget {
  const DataSourcesScreen({super.key});

  static const sources = <(String, String, String, String)>[
    (
      '詞義、詞源、音標',
      'Wiktionary（經 kaikki.org 整理）',
      'CC BY-SA 4.0 與 GFDL（雙授權）',
      'https://kaikki.org/',
    ),
    (
      '例句',
      'Tatoeba（作者為 Tatoeba 貢獻者）',
      'CC BY 2.0 FR',
      'https://tatoeba.org/',
    ),
    (
      '同義詞與詞彙關係',
      'Open English WordNet（McCrae et al.）',
      'CC BY 4.0',
      'https://en-word.net/',
    ),
    (
      '英文發音',
      'CMU Pronouncing Dictionary（Carnegie Mellon University）',
      'BSD-2-Clause',
      'https://github.com/cmusphinx/cmudict',
    ),
    (
      '中文譯詞',
      'ECDICT（skywind3000）；另有標示為 AI 的譯文',
      'MIT（ECDICT）',
      'https://github.com/skywind3000/ECDICT',
    ),
    (
      '卡片集『基礎 3000 字』',
      'New General Service List 1.2（Browne, Culligan & Phillips）',
      'CC BY-SA 4.0',
      'https://www.newgeneralservicelist.com/',
    ),
    (
      'CEFR 程度分級',
      'CEFR-J Wordlist（東京外國語大學投野研究室）與 Octanove Labs',
      'CEFR-J：註明出處即可使用；Octanove：CC BY-SA 4.0',
      'https://github.com/openlanguageprofiles/olp-en-cefrj',
    ),
    (
      '圖片',
      'Wikimedia Commons，以及 Openverse、Smithsonian Open Access',
      '每張圖依各自授權：CC0、公有領域、CC BY 1.0 至 4.0 等。'
          '長按圖片可看該張圖的作者、授權與來源頁。',
      'https://commons.wikimedia.org/',
    ),
    (
      '發音音檔',
      'Wikimedia Commons（含 Shtooka 錄音），以及 Wiktionary 音檔',
      '每個音檔依各自授權：CC BY-SA 4.0、CC BY-SA 3.0、CC BY 3.0 US 等。',
      'https://commons.wikimedia.org/',
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
              title: '資料來源與授權',
              leading: BackNavButton(
                  onTap: () => Navigator.of(context).pop()),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(MSpace.lg),
                children: [
                  UiText('這份 App 使用以下資料。各資料依其授權條款標示作者與來源；'
                      '圖片與音檔的作者、授權與來源頁，請長按圖片或在該張卡片查看。',
                      style: MFont.manrope(14, FontWeight.w600, MColors.ink)),
                  const SizedBox(height: 20),
                  for (final (topic, name, license, url) in sources) ...[
                    UiText(topic,
                        style: MFont.manrope(16, FontWeight.w800, MColors.ink)),
                    const SizedBox(height: 4),
                    UiText('來源：$name',
                        style: MFont.manrope(14, FontWeight.w600, MColors.ink)),
                    UiText('授權：$license',
                        style: MFont.manrope(14, FontWeight.w600, MColors.ink)),
                    SelectableText(url,
                        style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
                    const SizedBox(height: 18),
                  ],
                  UiText('授權條文',
                      style: MFont.manrope(16, FontWeight.w800, MColors.ink)),
                  const SizedBox(height: 4),
                  for (final url in const [
                    'https://creativecommons.org/licenses/by-sa/4.0/',
                    'https://creativecommons.org/licenses/by-sa/3.0/',
                    'https://creativecommons.org/licenses/by/4.0/',
                    'https://creativecommons.org/licenses/by/3.0/',
                    'https://creativecommons.org/licenses/by/3.0/us/',
                    'https://creativecommons.org/licenses/by/2.0/',
                    'https://creativecommons.org/licenses/by/2.0/fr/',
                    'https://creativecommons.org/licenses/by/1.0/',
                    'https://creativecommons.org/publicdomain/zero/1.0/',
                    'https://www.gnu.org/licenses/fdl-1.3.html',
                    'https://opensource.org/license/bsd-2-clause',
                    'https://opensource.org/license/mit',
                  ])
                    SelectableText(url,
                        style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
                  const SizedBox(height: 18),
                  UiText('圖片在 App 內以縮小後的縮圖顯示，未做其他修改。',
                      style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
