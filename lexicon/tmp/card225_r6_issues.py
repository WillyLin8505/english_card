import json,urllib.request
B='http://127.0.0.1:5173/api/issues'
def req(url,d,m):
    r=urllib.request.Request(url,data=json.dumps(d,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method=m)
    return json.load(urllib.request.urlopen(r))
log='log：app/build/rounds/113/pack.json、114/album.events.jsonl；量測 lexicon/tmp/card225_r6_measure.py'
r1=req(B,dict(kind='bug',severity='medium',area='data',reporter='claude-simulation',
 title='相片冊 247 個照片標籤掛在「變化形」詞條（gazing＝gaze 的現在分詞），沒有 CEFR，全落在「未分級」；17/20 個字其實有同拼法的形容詞／名詞詞條',
 detail='卡 #225 第113輪。pack 9286 詞條中 99 個詞條的所有義項都是 present participle／simple past／third-person singular／plural of 這類變化形說明；照片上有 247 個 approved tag（244 張圖、20 個字）掛在這些詞條，全部沒有 CEFR（佔全部 281 個未分級 tag 的 88%）。前幾名：gazing(verb) 66、surrounds(verb) 50、embossed(verb) 30、glistening(verb) 29、bent 13、railing(verb) 12、crossing 12、meandering 11。其中 17 個字另有同拼法、有 CEFR 的真詞條（embossed adj C2、glistening adj C2、railing noun B2、surrounds noun B2、gazing noun C1），標籤應掛那邊或改指原形 gaze。學習者視角：選了 B1 級別看不到這些字，在「未分級」看到 gazing，點開只有「gaze 的現在分詞」，收藏後卡片背面沒有意思可學。另：90 個圖上同時有原形和變化形（rail+railing 7、carve+carving 7、gaze+gazing 5），同一個概念列兩次是雜訊。與 #217（已修，偵測變化形）同類，但這批是已存在的 tag 資料，沒被重綁。'+log,
 steps='資料庫相片冊 → 搜尋 gazing 或 embossed → 開照片看標籤所在的級別區塊與詳情。',
 expected='照片標籤不掛在純變化形詞條：有同拼法形容詞／名詞就改綁那個詞條，否則改綁原形；未分級 tag 只剩真正沒有 CEFR 的字。',
 actual='247 個 tag 掛在變化形詞條、全部未分級。',
 code_ref='lexicon/backend/app/exporter.py（catalog tags）；綁定規則見 #217'),'POST')
print('new',r1.get('id'))
r2=req(B,dict(kind='bug',severity='low',area='app',reporter='claude-simulation',status='fixed',
 title='從照片／資料庫相片冊加入的字沒有送 word_added 事件，PostHog 看不到相片冊的主要使用行為（只有手動新增有）',
 detail='卡 #225 第113輪：album 模擬 198 張照片、加入大量單字，events.jsonl 0 筆。原因：word_added 只在 addWord（手動）送；savePhotoWords／addDeckPhoto 沒送。'+log,
 expected='每個從照片新增的字送一次 word_added，source 區分 photo／database_album。',
 actual='0 筆。',
 resolution='卡 #225 第114輪已修：savePhotoWords 對新建的字送 word_added（source=photo，addDeckPhoto 為 database_album）；測試 app/test/card225_photo_word_added_test.dart；README 事件清單已補。第114輪 album 模擬 824 筆 word_added。單字集（addDeckWords）仍未送，未擴大範圍。',
 code_ref='app/lib/services/word_database_repository.dart savePhotoWords'),'POST')
print('new',r2.get('id'))
