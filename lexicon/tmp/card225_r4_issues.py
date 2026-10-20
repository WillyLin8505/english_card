import json,urllib.request
def post(d):
    r=urllib.request.Request('http://127.0.0.1:5173/api/issues',data=json.dumps(d,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='POST')
    print(json.load(urllib.request.urlopen(r)).get('id'))
log='log：app/build/rounds/97/album.log、pack.json；量測 lexicon/tmp/card225_r4_measure.py'
post(dict(kind='bug',severity='low',area='data',reporter='claude-simulation',
 title='圖片標籤重複：sense_fallback 把兩個詞義改到同一個，同一張圖同一字同一詞義出現兩次（44 筆，pile·堆起 等）',
 detail='卡 #225 第97輪。pack 6109 張圖中 44 個 tag 與同圖另一個 tag 的 lexeme_id+sense_id 完全相同，其中一個帶 sense_fallback=true、sense_id_before（例：圖 1 pile 12332，原 6046）。App 照片詳情的標籤清單因此列兩次。App 端已在 databaseImageTags 去重（卡 #225，test/card225_duplicate_tags_test.dart），資料端仍需在 sense 重對應時合併重複 tag。'+log,
 steps='資料庫相片冊 → 圖 1（或 64、90、144…）→ 看 A2 標籤。',
 expected='同一字同一詞義只出現一次；重對應時遇到已存在的 (lexeme, sense) 就合併。',
 actual='DB／pack 有 44 筆重複 tag（App 已遮住）。',
 code_ref='app/lib/widgets/database_image_data.dart:17'))
post(dict(kind='decision',severity='low',area='app',reporter='claude-simulation',
 title='資料庫相片冊搜尋：字首相符的圖常比整字多 3 倍且不相干（car 整字 68、字首 219：carve 80、carry 41；bus→bush 54），兩段之間沒有分隔',
 detail='卡 #225 第97輪 UX（雜訊／一目了然）。#396 修好後 20 個常見短字共 1,061 張，整字 544（51%）排前面；但 car、sun、bus、art、ant 的字首結果遠多於整字，而且接在整字後面沒有任何標示，學習者捲下去會以為 carve、bush 也是 car、bus。'+log,
 steps='資料庫相片冊 → 搜尋 car（或 bus、art）→ 捲過前 68 張。',
 expected='看得出哪裡開始是「以 car 開頭的其他字」，或預設只看整字。',
 actual='整字與字首結果連成一片，沒有分段或數量。',
 options=['整字結果後加一行小標「以 car 開頭的其他字（219）」，頂端摘要寫「car 68 張 · 開頭相同 219 張」（建議）','有整字結果時預設只列整字，底部按鈕「再看以 car 開頭的 219 張」','維持現狀'],
 code_ref='app/lib/screens/database_library_screen.dart:154'))
