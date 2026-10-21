import json,urllib.request
B='http://127.0.0.1:5173/api/issues'
def req(url,d,m):
    r=urllib.request.Request(url,data=json.dumps(d,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method=m)
    return json.load(urllib.request.urlopen(r))
log='log：app/build/rounds/110/album.log、pack.json；量測 lexicon/tmp/card225_r5_measure.py'
i=json.load(urllib.request.urlopen(B+'/432'))
req(B+'/432',{'resolution':i['resolution']+'（卡 #225 第110輪：pack 仍有 45 筆同圖同字同詞義重複 tag／59 張圖同字重複，資料尚未重跑 fix-catalog-senses；App 端去重仍擋著，顯示 0。）'},'PUT')
r=req(B,dict(kind='bug',severity='low',area='data',reporter='claude-simulation',
 title='詞庫有 145 個首字大寫的詞條（Porch、Skull、Fairy…），其中 74 個另有小寫同字，照片標籤與收藏會出現兩個 fairy',
 detail='卡 #225 第110輪。pack 9286 詞條中 145 個 lemma 首字大寫（只有 2 個是多字或縮寫），74 個另有小寫同字詞條（Fairy 2539 A1 10 義／fairy 43464；Skull 15034／skull 44512；Rival 14923／rival 42550、42551）。照片上 168 個 tag 掛在大寫詞條（Appendage 24、Porch 23、Insignia 20、Skull 12），學習者在照片詳情看到大寫 Porch，從照片加入收藏的「Fairy」和單字本的「fairy」是兩張卡、進度分開。可能與 #281（重跑新增重複 en 詞條）同源。'+log,
 steps='資料庫相片冊 → 搜尋 porch 或 skull → 開照片看標籤；或從照片收藏 Fairy 後到單字本找 fairy。',
 expected='lemma 一律小寫（專有名詞除外），同字只有一個詞條，tag 與收藏合併到同一筆。',
 actual='145 個大寫詞條、74 組大小寫重複。',
 code_ref='lexicon/backend/app/exporter.py'),'POST')
print('new',r.get('id'))
