"""Isolated browser outage lab; dictionary read-only, preview state separate.

Run from project root. Change data/fault-lab.json to inject a request failure:
{"stage":"exercise", "delay":2, "fail":true}. Empty object disables it.
"""
import json
import sys
import time
from pathlib import Path
from http.server import ThreadingHTTPServer

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from server import PreviewService, make_handler
from state import State
from repository import Repository


def inject(stage, limit=None):
        flag = BASE / 'data/fault-lab.json'
        try:
            config = json.loads(flag.read_text(encoding='utf-8-sig'))
        except (FileNotFoundError, ValueError):
            config = {}
        if config.get('stage') == stage and (not config.get('only_random') or limit == 1):
            time.sleep(min(10, max(0, float(config.get('delay', 0)))))
            if config.get('fail'):
                raise ConnectionError('Isolated simulated outage')


class FaultRepository(Repository):
    def card(self, *args):
        word = super().card(*args)
        # Unique URLs bypass decoded-image reuse during delay/failure tests.
        for image in word.get('images', []):
            image['url'] += '?fault_lab=' + str(time.time_ns())
        return word

    def media(self, kind, id):
        if kind == 'image':
            inject('image')
        return super().media(kind, id)

    def words(self, *args, **kwargs):
        inject('words', args[4] if len(args) > 4 else kwargs.get('limit'))
        return super().words(*args, **kwargs)


class FaultService(PreviewService):

    def templates(self, *args):
        inject('templates')
        return super().templates(*args)

    def card(self, *args):
        inject('card')
        return super().card(*args)

    def exercise(self, *args):
        inject('exercise')
        return super().exercise(*args)


class FaultState(State):
    def save(self, *args, **kwargs):
        inject('save')
        return super().save(*args, **kwargs)


if __name__ == '__main__':
    service = FaultService(repo=FaultRepository(), state=FaultState(BASE / 'data/fault-lab.sqlite'))
    server = ThreadingHTTPServer(('127.0.0.1', 8786), make_handler(service))
    print('Isolated outage lab: http://127.0.0.1:8786/', flush=True)
    server.serve_forever()
