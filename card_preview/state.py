"""Preview-owned metadata only. The lexicon and all learning stores are untouched."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from domain import default_layout, validate_layout


class State:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''
              CREATE TABLE IF NOT EXISTS drafts(pair TEXT PRIMARY KEY, layout TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS template_names(pair TEXT, id TEXT, name TEXT NOT NULL, PRIMARY KEY(pair,id));
              CREATE TABLE IF NOT EXISTS versions(pair TEXT, version INTEGER, layout TEXT NOT NULL, created TEXT, PRIMARY KEY(pair,version));
              CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY, lexeme_id INTEGER, target_language TEXT, native_language TEXT,
                sense_id INTEGER, template TEXT, version TEXT, field TEXT, category TEXT, note TEXT, created TEXT);
            ''')

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def templates(self, target, native, template_id='default'):
        base = target + ':' + native
        with self.connect() as c:
            choices = [{'id': 'default', 'name': '預設模板'}] + [dict(r) for r in c.execute('SELECT id,name FROM template_names WHERE pair=? ORDER BY rowid', (base,))]
            if template_id not in [x['id'] for x in choices]:
                raise ValueError('找不到這個語言方向的模板')
            pair = base if template_id == 'default' else base + ':' + template_id
            draft = c.execute('SELECT layout FROM drafts WHERE pair=?', (pair,)).fetchone()
            versions = [dict(r) for r in c.execute('SELECT * FROM versions WHERE pair=? ORDER BY version DESC', (pair,))]
        for v in versions:
            v['layout'] = json.loads(v['layout'])
        return {'draft': json.loads(draft['layout']) if draft else default_layout(), 'versions': versions, 'choices': choices, 'template_id': template_id}

    def create(self, target, native, name, layout=None):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('模板名稱需為 1～80 字')
        if layout is None:
            layout = default_layout()
            for section in layout['sections']:
                section['visible'] = section['key'] in ('hint', 'meaning', 'answer', 'pronunciation', 'examples')
        layout = validate_layout(layout)
        template_id = uuid.uuid4().hex
        base = target + ':' + native
        with self.connect() as c:
            c.execute('INSERT INTO template_names VALUES (?,?,?)', (base, template_id, name.strip()))
            c.execute('INSERT INTO drafts VALUES (?,?)', (base + ':' + template_id, json.dumps(layout, ensure_ascii=False)))
        return self.templates(target, native, template_id)

    def save(self, target, native, layout, publish=False, template_id='default'):
        self.templates(target, native, template_id)
        layout = validate_layout(layout)
        pair = target + ':' + native
        if template_id != 'default':
            pair += ':' + template_id
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)', (pair, json.dumps(layout, ensure_ascii=False)))
            if publish:
                version = c.execute('SELECT coalesce(max(version),0)+1 FROM versions WHERE pair=?', (pair,)).fetchone()[0]
                c.execute('INSERT INTO versions VALUES (?,?,?,?)', (pair, version, json.dumps(layout, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
        return self.templates(target, native, template_id)

    def issues(self, id, target, native):
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM issues WHERE lexeme_id=? AND target_language=? AND native_language=? ORDER BY id DESC', (id, target, native))]

    def add_issue(self, body):
        allowed = ['資料錯誤', '翻譯錯誤', '圖片不符', '音檔錯誤', '選項不唯一', '拖曳區域錯誤', '版面問題']
        if body.get('category') not in allowed or not isinstance(body.get('note'), str) or not 1 <= len(body['note'].strip()) <= 2000:
            raise ValueError('請選擇問題類別並填寫 1～2000 字備註')
        with self.connect() as c:
            cursor = c.execute('INSERT INTO issues(lexeme_id,target_language,native_language,sense_id,template,version,field,category,note,created) VALUES(?,?,?,?,?,?,?,?,?,?)',
                tuple(body.get(k) for k in ['lexeme_id','target_language','native_language','sense_id','template','version','field','category','note']) + (datetime.now(timezone.utc).isoformat(),))
            return {'id': cursor.lastrowid}
