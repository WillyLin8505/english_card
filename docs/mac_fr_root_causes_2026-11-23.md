# 法文完整重測：不通過項目的原因（Mac，2026-11-23，commit 827c2fa4）

做法：每一項先由一個只讀的調查者對照程式碼和詞庫資料（fr-en 詞庫、精簡字典 sqlite）找出原因，再由另一個獨立的複查者重開每個引用的檔案和行號、重跑查詢，試著推翻它。下面只列複查後成立的內容；行號是複查時的位置。修不修、怎麼修由 Windows 決定。

| 檢查 | 原因（複查結論） | 種類 | 最小修法建議 |
|---|---|---|---|
| FR02／FR03 單字本頁沒有變位表、形容詞表（#1703、#1698） | 卡 #1220 只把 FrenchVerbSection／FrenchAdjectiveSection 接在詞庫頁（widgets/database_word_detail.dart:73-78、375-382）；單字本頁 WordDetailScreen 的 _WordBody 從沒引用它們，只有舊的「詞形變化」列表。詞庫資料齊全（aller、parler、être、manger 各 45-47 個變位，beau、grand 有陰陽性和單複數）。（成立） | App 程式 | 在 word_detail_screen.dart _WordBody 已有的逐詞性迴圈（約 254-261 行，已經會 `pack.lookup(entry.word, pos: usage.pos)`）裡，法文時對 verb 呼叫 frenchVerbFrom、對 adj 呼叫 frenchAdjectiveFrom，加到例句之後；詞形變化列表照詞庫頁一樣扣掉已顯示的欄位。 |
| FR06 動詞／形容詞的標題變成名詞（l'aller m. plural allers） | 詞庫頁把同一拼字所有詞性的形式合在一起（database_word_detail.dart:69-72、79-81），標題取第一個找到的 fr_gender／fr_plural，不看打開的是哪個詞性，所以動詞 aller 借了名詞 aller 的「m.／allers」。（成立） | App 程式 | 陰陽性和複數只取打開的那個詞條，而且只在它是名詞時顯示。 |
| FR05 beau 沒有形容詞表；beau 第一個意思是 boyfriend | 詞庫資料：法文詞庫把每個拼字除了主詞性以外的詞性全標成「少用」（912／912 列；英文詞庫只有部分），beau 的主詞性被排成名詞 boyfriend，形容詞變成少用；manger 也是名詞在前。單字本頁和複習卡同樣先顯示 boyfriend。（成立；另外測試本身用不帶詞性的查詢打開 beau，所以打開的是名詞頁，已改成指定詞性） | 詞庫資料＋測試 | 詞庫建置端（lexicon/backend/app/app_pack.py 約 516-518 行清掉次要詞性的地方）重新檢查主詞性的選法，至少常用形容詞、動詞不該排在少見名詞之後。 |
| FR07 héros 說明是中文（#1236） | 這句 h aspiré 說明的英文／法文翻譯在 ui_catalog.dart 的 `_templateCopy`（約 2299 行），不在 `uiCatalog`；translateUi 的精確查找查不到它，而且兩邊撇號不一樣（程式用 '，翻譯表用 ’），範本比對也對不上。（部分成立：原調查以為只是撇號，複查指出位置也不對） | App 程式 | 把這句移到 uiCatalog，並讓兩邊的撇號一致。 |
| FR09 搜尋時打的字排很後面 | 單字本搜尋只篩選不排名：matchesSearch（word_database_query.dart:238-255）只回答「有沒有出現在單字、意思、例句…任何欄位」，結果再照字母排（預設 SortOrder.alphabetical）。（成立；Mac 在 #1251 第 5 項已回報過） | App 程式 | 有搜尋字時先排：單字完全相同 → 單字開頭相同 → 單字包含 → 其他欄位；沒有搜尋字時排序不變。 |
| FR12 複習卡 ne 顯示「NE＝東北」 | 詞庫資料：fr-en 詞庫裡唯一的 ne（id 200498）是縮寫 NE 的名詞，音標、錄音也是 NE 的；否定詞 ne 根本沒進詞庫，因為建置時 Kaikki 的詞性對照表沒有 "particle"（lexicon/backend/app/adapters/kaikki.py 約 27-30 行），而且大小寫不分地合併了 NE 和 ne。se、sa、st 在精簡字典也是縮寫排第一。（成立） | 詞庫資料 | 詞性對照加上 particle；同名時優先大小寫完全相同的詞條（保留 #460 Fairy → fairy 的行為）；重建 fr-en 詞庫和精簡字典。 |
| FR12 複習卡 la 沒有例句 | 單字集存的是代名詞 la（沒有例句），複習時卡片換成常用的冠詞 la 顯示，但例句區還是讀代名詞的例句，所以顯示「還沒有例句」。同樣情況還有 de、un、ce、son、une、tout、pas、bien、pendant、voici 等 13 個字。（成立） | App 程式 | FlashcardBack 的例句（flashcard_back.dart 約 938-940 行）取正在顯示的那個詞性的例句，空的時候再用其他詞性的。 |
| FR14 沒有法文相片冊 | 伺服器上沒有任何 target_language=fr、kind=photos 的卡片集；名字叫 Photo Deck 的法文卡片集本來就是單字集。App 只照伺服器的 kind 顯示（deck_library.dart:47、51）。（成立） | 伺服器資料／產品決定 | 先由 owner 決定法文要不要真的有照片相片冊；如果現在的單字集就是預期的產品，這項檢查改成不判定。 |
| FR15 umbrella→ombrelle、lighthouse→fanal | 對照表是內建資料 app/assets/vision_fr.json（14,390 個英文標籤），由 lexicon/tools/card1205_build_vision_fr.py 從精簡字典的英文解釋反查產生（這支腳本不在 repo 裡）。parapluie 的解釋是「umbrella for rain」，所以永遠搶不到「umbrella」；phare 在精簡字典被標成形容詞，所以不在名詞候選裡。（成立） | 內建資料 | 在腳本的 OVERRIDES 加 umbrella→parapluie、lighthouse→phare 後重建；較根本的做法是優先選 fr-en 詞庫裡第一個意思就是該標籤的常用名詞。 |
| FR17 照片新加的字沒有意思 | 存檔時其實有寫入意思（例如 bicyclette＝bicycle），但新詞條沒有標「意思是哪個母語」（translatedFor 是空的），WordEnricher 把空值當成舊的中文資料，於是清掉意思並標失敗，而且只試一次、之後不會再補。只有詞庫裡沒有的字會這樣（bicyclette、ombrelle、saxophone 都不在 fr-en 詞庫，但精簡字典有）。（成立） | App 程式 | 建立詞條時有意思就同時寫入目前母語（word_database_repository.dart _createEntry 約 659-699 行）。較好的做法是詞庫沒有時改用精簡字典補意思和音標。已經被清空的舊詞條要另外處理。 |

## 測試本身的修正（Mac 端，已改）

複查也找出 Mac 測試的弱點，已在本機測試修正，下一輪起生效：
- 唯讀模式不再按教學卡的「略過」（它會存「已看過教學」到使用者設定）；`READONLY` 一定會關掉會寫資料的步驟。
- 結果表會列出沒跑到的檢查、沒跑完、或用到舊記錄的情況，不會再看起來全部乾淨。
- 讀音檢查改看錄音網址；la 有沒有例句改看例句元件；照片翻譯改看候選字裡有沒有 parapluie／phare；複習評分改算真的寫入的複習紀錄；詞庫頁指定詞性打開；已封存的卡不判定。
