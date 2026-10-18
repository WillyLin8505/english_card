"""Studio template storage through the authenticated local admin proxy.

The preview SQLite remains responsible only for QA reports. No credentials
are exposed to the browser, and API failures never silently publish locally.
"""
import json
import os
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError


class PublishedState:
    def request(self, action='', template_id='default', body=None):
        base = os.environ.get('CARD_TEMPLATE_ADMIN_URL', 'http://127.0.0.1:5173/api')
        url = base.rstrip('/') + '/card-templates' + action + '?' + urlencode({'template_id': template_id})
        req = Request(url, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=15) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError):
            raise ValueError('正式版型 API 無法使用；草稿／發布未儲存，請確認後台服務已載入新版程式') from None

    def templates(self, target, native, template_id='default'):
        return self.request(template_id=template_id)

    def create(self, target, native, name, layout=None):
        return self.request('/create', body={'name': name, 'layout': layout})

    def save(self, target, native, layout, publish=False, template_id='default'):
        return self.request('/publish' if publish else '/save', template_id, {'layout': layout})
