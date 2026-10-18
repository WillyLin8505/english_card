# Windows → Mac 指令

Windows 端 manager（Claude · Manager）寫，Mac 端每幾分鐘 `git fetch` 看有沒有新項目。
做完一項就在 `docs/mac_verify_results.md` 記結果並 push，然後在下面把那項的 `狀態` 改成 `完成`（同一個 commit）。
問題回報頁 API（`https://api.willylinai.com/api/issues`，`X-API-Key: $ENGLISH_CARD_KEY`）照舊可用：
要 Windows 修的 bug 直接開 `[Mac]` 問題回報最快（會自動派給一個 Claude CLI）。

---

## M1（2026-10-18 22:50）狀態：待做
第 1 輪的 flutter test／analyze 結果收到了：已開問題回報 #294（Windows 也重現 6 個失敗），會派 CLI 修。
1. 等 Xcode 裝好後 `git pull`，繼續第 1 輪的第 4、5 步（`./run_ios_sim.sh`、學習者流程），照 docs/mac_verify.md。
2. 金鑰：owner 會在 Mac 終端機設 `ENGLISH_CARD_KEY`；App 設定頁填打標服務 `https://api.willylinai.com/tag` 與同一把金鑰。
3. 每個新問題開一筆 `[Mac]` 問題回報（API），或寫進 results 檔（Windows 會轉成問題回報）。
4. #294 修好後（GET /api/issues/294 狀態 fixed）`git pull` 重跑 `flutter analyze && flutter test`，結果寫進 results 檔。

## M2（2026-10-18 23:29）狀態：待做
commit `e91339e`（Windows：flutter analyze 無 error、01:08 +370: All tests passed!）。`git pull` 後在 iPhone 模擬器（有接實機也在 iPhone 上）逐張驗證下面的卡：照卡上的結果實際操作一次、截圖，結果寫進 docs/mac_verify_results.md（每張卡一列：通過／不通過＋原因）。不通過的開 `[Mac]` 問題回報，標題寫卡號。
- 卡 #208：問題回報 #209：[qc] entry.full_without_ipa：完整詞條沒有 IPA
  結果：完整詞條缺 IPA：19 筆／15 詞 → 12 筆／11 詞（補 4 詞頭、7 筆）；golden 與其他 QC 指標無退步。
- 卡 #210：問題回報 #246：待決定選了「不做」之後，問題回報被放回待處理又派工
  結果：decide() 回答以「不做」開頭時改為 wontfix。全庫這種決定 1 筆（#208，本來已是不處理），仍待處理 0 筆，沒有改詞庫資料。
- 卡 #211：問題回報 #61：照片標籤排版：少數擁擠的橫式照片會蓋住圓點或引線過長
  結果：橫式擁擠照片的標籤排版：7489 張 × 3 形狀共 22467 次，引線過長 75→0、蓋住圓點 18→3、重疊 0、超出照片 0。
- 卡 #163：系統修正：CEFR 估算只靠 zipf，具體名詞偏難、衍生詞與詞族不一致（需你決定參考詞表）
  結果：結論：衍生詞封頂已完成，46→6 離群（剩 6 個是 owner 已審的 qualityrule，非自動估算）；具體名詞校正因無法可靠自動判斷而改為 135 筆候選清單供人工複核，未自動套用。golden/qc.py check --live 前後數字完全一致，無回歸。
- 卡 #170：常態：全庫掃描例句品質（含粗俗字）
  結果：E 群掃描數字都沒有上升：非完整句 827→2、罕見人名 1503→186、找不到單字 235→12、無例句 1180→1007、例句粗話 2→1、相關詞粗話 0（中途曾計到 24，已濾掉）。
- 卡 #227：模擬使用者・單字本
  結果：第 60 輪：database,detail 2/2 通過；新問題回報 #259、#260（UX 建議 2 個）。
- 卡 #225：模擬使用者・相片冊
  結果：第 61 輪（相片冊分頁，只跑 album）：1/1 通過，無新失敗；問題回報新增 2、UX 建議 2（#257、#258）。
- 卡 #228：模擬使用者・設定
  結果：第 64 輪：1/1 通過（settingssimulation 新建）。修 2 個文案小錯並補測試；無新問題回報（1 筆重複，補一句在 #260）。
- 卡 #226：模擬使用者・複習
  結果：第 59 輪：2/2 通過（learner 66s、restart 47s），新問題 #261、#262，UX 建議 1 個（#262），既有問題補註 2 則（#209、#24）。
- 卡 #229：問題回報 #254：outlaw 被譯成「通姦者」（例句翻譯與詞源），另有帶政治／宗教立場的例句
  結果：outlaw 的「通姦者」已改成逃犯／被放逐者（例句 11、詞源 3、義項 1、衍生 4）；學習卡改為中性句優先。另開問題回報 #264。
- 卡 #250：問題回報 #179：資料庫分級標籤太長；大型畫面檔需拆分
  結果：相片冊縮圖不再把各級標籤接成一行：3244 張已核准圖中 2263 張會中這個路徑，現改為每級自己一行、超過 3 個才展開。
- 卡 #257：問題回報 #267：App 圖示是 Flutter 預設圖、啟動畫面是 1×1 空白圖：上架前要換
  結果：iOS 1024 圖示已脫離 Flutter 範本（md5 c785f893… → 35b086bb…），LaunchImage 由 1×1 改為 168/336/504；問題回報 #267 已標已修正。
- 卡 #260：問題回報 #270：原生 iOS 上 pack 圖片與音檔 URL 用 Uri.base 解析、內建音檔用 UrlSou
  結果：原生 iOS 不再用 Uri.base 解 pack 媒體：相對路徑改打詞庫伺服器，內建音檔改 AssetSource。內建包 11658 詞、音檔 0、目錄圖 0；線上包每一張圖都是 /api/image、每一段錄音都是 /api/audio，全部走同一條解析。
- 卡 #262：問題回報 #272：音檔授權：Commons 抓不到時留下假授權名（Wikimedia Commons（依檔案授權））且
  結果：指標 · 前 · 後；license 為佔位字「Wikimedia Commons（依檔案授權）」 · 12 · 0
- 卡 #263：問題回報 #273：詞源把 Icelandic 譯成愛沙尼亞語或愛斯蘭尼亞語
  結果：已修正 Icelandic 的兩種誤譯：10 筆正式詞源、5 筆彙整欄位、5 筆候選快取，共 20 筆；全庫重掃殘留 0，golden／QC 無退步。
- 卡 #264：問題回報 #274：詞源把 German 譯成「德國語」
  結果：德國語/法國語 全庫修正完成：etymologytranslations 32 筆 + fieldvalues 16 + fieldcandidates 16（共 16 個字）改成德語／法語／低地德語／古法語，剩 0；golden 與 QC 無退步。
- 卡 #259：問題回報 #269：App 內缺「資料來源與授權」頁：Wiktionary CC BY-SA、Tatoeba CC BY
  結果：第二輪：owner 10/18 決定已照做（不加 urllauncher、不顯示音檔作者），本輪只核對，沒有改資料或程式。音檔作者缺口目前 24 筆（r1 記 36），授權佔位字 0 筆。
- 卡 #272：問題回報 #280：首次連線設定：用 QR code 帶入後端網址與金鑰
  結果：完成 #280：設定頁新增「掃描 QR code」，掃到連線 QR 後自動帶入服務網址與金鑰並測試連線；手動輸入保留。筆電端新增產生 QR 的腳本。
- 卡 #256：問題回報 #266：iOS 專案上架設定：bundle id com.example、版本號缺 +build、ATS 明
  結果：iOS bundle id 已改成 com.willylinai.photoflashcard（Runner Debug/Release/Profile 3 處＋RunnerTests 3 處，共 6 行）；卡上 9 項 iOS 設定全部完成。
- 卡 #242：問題回報 #221：CEFR 估算偏難：striped (adj) B2 → 建議 A2–B1
  結果：結論：striped（adj）B2→B1（落在 owner 決定的 A2–B1）；根因是 -ed 衍生形容詞封頂用「本形+1」，全庫 2,724 個「字表外、有字表本形的 -ed 詞」同步改為「本形同級」（potted/dotted/frosted/cushioned 皆 B2→B1 類）。
- 卡 #269：問題回報 #278：備份還原：匯出成單一檔案並可匯入還原
  結果：完成：設定 → 資料 新增「匯出備份／從備份還原」，一個 .ecbackup 檔含 3 個學習語言的全部資料＋照片原始位元組＋設定；新測試 2/2 通過、analyze 0 issue。
- 卡 #271：問題回報 #279：原始照片遺失：維持複製原圖，找不到時改用同單字的其他圖
  結果：卡 #271（問題回報 #279）：學習卡背面不再選找不到原檔的照片，改用同單字的其他圖；伺服器端沒有原圖參照，裝置上的遺失數量這裡量不到。
- 卡 #268：問題回報 #265：上架版 App 連不到家裡電腦：照片辨識與詞庫後端要選方案（本機辨識＋內建詞庫 / 雲端 GPU）
  結果：結論：上架版 App 已不依賴家裡電腦——iOS 照片用 Apple Vision 本機辨識、詞庫內建精簡 pack（5,132 完整詞、1,768 張圖；JSON 150 MB → 30 MB），設定頁消費者版不再有網址／金鑰欄與 Ollama 字句；新測試 17 項通過、QC 無退步。Swift 端尚需在 Mac 
- 卡 #279：問題回報 #276：照片詳情的自動保存說明位於所有單字下方，建議移到列表標題旁
  結果：結論：照 owner 決定，自動保存短提示已移到「辨識單字列表」標題正下方（第一個單字之前），底部說明刪掉重複句；新增 1 個 widget 測試通過，#276 的 resolution 已寫上。
- 卡 #280：問題回報 #275：拍照首頁「即時辨識」容易讓學習者以為取景時就會出現單字
  結果：拍照首頁副標已照 owner 決定改成「拍照或選一張照片，找出生活中的英文單字」（1 處畫面＋1 筆三語翻譯），不再暗示取景即時辨識。
- 卡 #276：問題回報 #283：原始照片遺失：詞項照片列表與相簿封面仍會顯示壞圖（#271 只修了卡片背面）
  結果：卡 #276 / 問題回報 #283 完成：詞項照片列表、單字詳情「出現這個單字的照片」、相簿封面、相機縮圖都改成跳過原檔遺失的照片；新增 3 個測試全過，全套 flutter test 364 過 / 6 失敗（都在別張卡正在改的畫面，與本卡無關），QC regressions = 0。
- 卡 #164：系統修正：主用法／主義項用「字典收錄多寡」決定，照片標籤綁到冷僻義項
  結果：結論：主詞性改由「CEFR 詞表 → WordNet＋ECDICT 詞性投票 → 加權義項／例句」決定，照片標籤義項依同圖其他標籤重選並回填 714 筆；QC phototag.senselowpriority 85→0、sensewithoutchinese 0、golden 全項不變（photo.expecteds
- 卡 #285：問題回報 #288：#267 查核：field_values 有 132 個過期的缺漏義項；sense_key 有 56
  結果：全部完成：全庫 574 列 fieldvalues（14 欄位）的 missing 列出已不存在的 slot，已依 resolver 規則重算（nativedefinition 78 列／131 個過期代號 → 77 列 complete、1 列真缺仍 partial）；根因在 pipeline 修好並加測試；sens
- 卡 #286：問題回報 #289：example_sense 有 753 列 missing 列出的例句其實已由 local_calc
  結果：全部完成：根因是 card166reselect.py 的 writeitems 只改 items、沒同步 status/missing（已修）；全庫 640 列 examplesense（2950 個已填卻列缺的例句代號）依 resolver 規則重算 → 554 列 complete、86 列仍 partial（真
- 卡 #277：問題回報 #271：上架版要不要過濾 vulgar／offensive／derogatory 義項與例句？年齡分級目標？
  結果：全部完成：#271 已照 owner 決定實作——匯出加 storesafe 開關，上架版 vulgar 78／offensive 23／derogatory 143 義項（及其例句）全部不輸出；內建 pack 不重產，等 #287 自動同步。
- 卡 #289：問題回報 #291：新匯入的罕見衍生詞沒有任何 IPA 來源，#209 會一再被 qc 重開
  結果：全部完成：ipa 欄位新增「詞根＋字尾」推導備援（localcalc），以前只能手補的 12 個詞有 8 個可自動推出；3000 個 stub 抽樣中「沒有任何 IPA 來源」821→261（-68%）；沒有改資料，golden 8 項不變、regressions=[]。
- 卡 #233：問題回報 #255：字卡與詳情頁的英文全部首字大寫、詞義用藍色字，像專有名詞和連結
  結果：根因修好：flashcard_back.dart 的 _chips() 對相關字/詞形變化逐字 displayWord() 強制大寫，已改回保留原大小寫；word_detail_screen.dart 詞義文字由 MColors.primary(藍) 改 MColors.ink。更新對應 widget test，flu
- 卡 #234：問題回報 #260：資料庫瀏覽頁常駐顯示「已連接詞庫・每 30 秒自動更新」等技術性同步狀態文字
  結果：已修：database_library_screen.dart 常駐同步狀態文字只在連線失敗時顯示；dictionary_sync.dart 新增 hasError 旗標；相關測試 15 項全過
- 卡 #235：問題回報 #262：複習畫面「刪除此卡片」沒有確認也沒有復原提示，誤觸就移除卡片
  結果：flashcard_screen.dart 加確認對話框+復原SnackBar；review_archive_session_test.dart 更新/新增2個測試；全部通過，寫 result.md 中
- 卡 #236：問題回報 #258：資料庫相片冊 → 我的收藏（嵌入的 AlbumScreen）點「返回」會直接跳到拍照分頁，不是回到資料庫/我的收藏切換
  結果：修好 AlbumScreen/WordDatabaseScreen 的返回鍵（onBack 覆寫），接線到 DatabaseLibraryScreen，新增 2 個回歸測試，8/8 + 26/26 測試通過，見 card236.result.md
- 卡 #237：問題回報 #257：資料庫相片冊：圖片詳情每個標籤都顯示「已確認／待確認」等內部審核狀態，學習者看不懂也用不到
  結果：修完 database_tag_sections.dart 的 review_status 內部字樣，測試+QC 過，寫好 result.md
- 卡 #238：問題回報 #259：單字本內「我的收藏」在三處用了三種名稱：收藏／單字本／複習字卡
  結果：已統一「單字本」命名：切換鈕/提示/翻譯改完，測試42/42過，問題回報#259標fixed+decision A。result.md 已寫。
- 卡 #246：問題回報 #4：同一拼字不同詞性的 usage 層未實作
  結果：根因：複習字卡背面(FlashcardBack)用 entry 預設 pos/meaning，沒跟著當次測驗的 usage_id/sense_id。已修 flashcard_session.dart + flashcard_session_views.dart + flashcard_back.dart，加回歸測試，u
- 卡 #249：問題回報 #79：App 不能編輯相關字、詞形變化、構詞與詞源
  結果：3 項編輯功能（相關字、詞形變化、構詞與詞源）程式碼已在 working tree 完成並接上編輯對話框；word_details_edit_test.dart 8/8 通過，user_edits_survive_test.dart 通過；跑全套 flutter test 確認無迴歸中
- 卡 #251：複習字卡背面改版（owner 10/18 九項）
  結果：九項全部完成：背面兩口音依序播放、去等級標籤與照片情境、例句靠近、詞形全列、同義／相關／近音／拼字相近 Wrap 滿寬、構詞拆解框樣式、多圖左右滑、英文字連到字庫詳情。flutter test 342 通過（新測試 10 條）。注意：關係字取消 CEFR 過濾，詳 card251.result.md
- 卡 #252：App 照片載入有時要等很久：找根因並修正
  結果：根因：原尺寸解碼(48MB/張,快取只放2張)、網頁存放照片每次重讀重解碼、手機網路圖無磁碟快取、背面未預載。新增 photo_cache.dart 依顯示尺寸解碼(48→7MB,快取2→14張)+穩定快取鍵+磁碟快取+字卡背面預載；flutter test 342 全過
- 卡 #253：複習卡片正面標示單字在圖片中的位置
  結果：正面看圖題以 TargetRing 標出單字位置（有框加框、無座標不標、不露字）；新測試 7 個，全部 flutter test 342 通過；catalog 13278 標籤中 35 個無座標

## M3（2026-10-18 23:44）狀態：完成
commit `99ba0fa`（Windows：flutter analyze 無 error、01:32 +370: All tests passed!）。`git pull` 後在 iPhone 模擬器（有接實機也在 iPhone 上）逐張驗證下面的卡：照卡上的結果實際操作一次、截圖，結果寫進 docs/mac_verify_results.md（每張卡一列：通過／不通過＋原因）。不通過的開 `[Mac]` 問題回報，標題寫卡號。
- 卡 #291：問題回報 #294：[Mac] flutter test 失敗與 analyze 警告（Mac 第 1 輪，Window
  結果：全部完成：flutter analyze 3→0 個問題、flutter test 6 失敗→0（370 全過）；6 個失敗都是測試過時，程式本身沒錯，只改了測試檔。

## M4（2026-10-19 00:05）狀態：待做
commit `270dac5`（Windows：flutter analyze 無 error、02:35 +370: All tests passed!）。`git pull` 後在 iPhone 模擬器（有接實機也在 iPhone 上）逐張驗證下面的卡：照卡上的結果實際操作一次、截圖，結果寫進 docs/mac_verify_results.md（每張卡一列：通過／不通過＋原因）。不通過的開 `[Mac]` 問題回報，標題寫卡號。
- 卡 #166：系統修正：例句選取與重寫（義項不對齊、非完整句、Tatoeba 罕見人名、缺例句）
  結果：全部完成：alfred 照片解綁並排除（決定 B），照片字缺例句 0、oddname 1,503→0、notsentence 827→2、missinglemma 235→0（validator）；另有 #292 進行中的重新 materialize 新增 5 個 A1–B1 缺口，已開問題回報 #295。

## M5（2026-10-19 01:23）狀態：待做
commit `6cfa872`（Windows：flutter analyze 無 error、01:01 +370: All tests passed!）。`git pull` 後在 iPhone 模擬器（有接實機也在 iPhone 上）逐張驗證下面的卡：照卡上的結果實際操作一次、截圖，結果寫進 docs/mac_verify_results.md（每張卡一列：通過／不通過＋原因）。不通過的開 `[Mac]` 問題回報，標題寫卡號。
- 卡 #295：問題回報 #298：looks_simplified 把台灣正體常用字（峰、卷、祕／秘、夸、里）當簡體字退回：聖母峰、十
  結果：本輪完成：lookssimplified 不再把 峰／秘／夸（夸克）／里／巨 判為簡體，#298 的 11 個候選值全部通過驗證；補寫 peak／bound 缺漏的 20 個義項＋1 句例句（AI 翻譯，台灣用語）。

## M6（2026-10-19 02:45）狀態：待做
commit `d0bc371`（Windows：flutter analyze 無 error、01:57 +372: All tests passed!）。`git pull` 後在 iPhone 模擬器（有接實機也在 iPhone 上）逐張驗證下面的卡：照卡上的結果實際操作一次、截圖，結果寫進 docs/mac_verify_results.md（每張卡一列：通過／不通過＋原因）。不通過的開 `[Mac]` 問題回報，標題寫卡號。
- 卡 #227：模擬使用者・單字本
  結果：第 68 輪：database,detail 2/2 通過；第 70 輪（補模擬覆蓋後）2/2 通過；新問題 #303；UX 建議 #304（已直接修）、#206 補充。
- 卡 #296：問題回報 #229：每圖 ≤10 秒：選擇完整品質流程或先出可用標籤再補強，並安排小樣本硬體驗證
  結果：全部完成：照 owner 決定（保留完整品質、≤10 秒只是待驗證目標）加了分段計時；正式負載實測 25 張每圖中位 33.9 秒、≤10 秒 0 張，cefr 17.6 秒＋score 15.4 秒各佔約一半，單輪（rounds=1）已確認。
- 卡 #228：模擬使用者・設定
  結果：第 2 輪：1/1 通過（runround 第 74 輪，findings 3→0）、修 1 個真錯（複習比例超出滑桿範圍會壞畫面）、新問題 #306 #307、UX 建議 #306 #307＋#277 補一句。

## M7（2026-10-19 03:04）狀態：待做
commit `63131d5`（Windows：flutter analyze 無 error、01:08 +375: All tests passed!）。`git pull` 後在 iPhone 模擬器（有接實機也在 iPhone 上）逐張驗證下面的卡：照卡上的結果實際操作一次、截圖，結果寫進 docs/mac_verify_results.md（每張卡一列：通過／不通過＋原因）。不通過的開 `[Mac]` 問題回報，標題寫卡號。
- 卡 #297：問題回報 #303：詞庫有 status=full 但 0 個義項的詞條（shack 形容詞、hollow 感嘆詞），資
  結果：全部完成：全庫只有 2 個「status=full 但 0 義項」的詞條（shack adj #28442、hollow intj #40443），根因在 materialize，已從根因修並重建這 2 個字；QC/golden 無退步。
- 卡 #300：問題回報 #306：設定頁「詞庫連線」卡常駐顯示「已連接詞庫 · 每 30 秒自動更新」與「上次確認 HH:MM」，#2
  結果：完成：設定頁「詞庫連線」卡改成只在詞庫連線失敗（DictionarySync.hasError）時出現，「資料」卡刪掉「詞庫會從你的資料庫自動更新」；flutter test 375 全過、analyze 0 error（問題回報 #306）。
- 卡 #301：問題回報 #307：學習洞察的「弱項單字」只是文字，點了沒反應；看到弱項卻無法直接打開或複習
  結果：完成：學習洞察「弱項單字」每行可點開單字詳情，清單下加「複習這些字」直接進複習（這些字先出），文案改成「複習 5 次，忘了 2 次」；flutter test 375 全過、analyze 無新問題。
