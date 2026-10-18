"""Report card #25 without reading service credentials."""
import json
import sys
import urllib.request

done = '--done' in sys.argv
payload = {
    'by': 'Codex',
    'progress': ('完成繁中／英文／法文介面切換、動態文字及測試；flutter test 與 analyze 通過，結果已存檔。'
                 if done else '已完成介面詞庫、母語即時更新及新增切換測試；正在驗證窄螢幕與完整測試。'),
}
if done:
    payload.update(status='done', note='完成')
request = urllib.request.Request(
    'http://127.0.0.1:5173/api/tasks/25',
    data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
    headers={'Content-Type': 'application/json; charset=utf-8'}, method='PUT')
with urllib.request.urlopen(request, timeout=10) as response:
    print(response.status)
if done:
    issue = {'status': 'fixed', 'reporter': 'Codex', 'note': '排程卡 #25 完成',
             'resolution': '主要介面隨母語切換繁中、英文、法文；新增語系切換測試，flutter test 與 flutter analyze 通過。詳見 lexicon/logs/agents/card25.result.md。'}
    request = urllib.request.Request(
        'http://127.0.0.1:5173/api/issues/7',
        data=json.dumps(issue, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json; charset=utf-8'}, method='PUT')
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.load(response)
        print('issue 7:', result.get('status'))
