"""Stop a CEFR response once it is stuck repeating already emitted labels."""
import json


class RepetitionGuard:
    def __init__(self, repeats=3):
        self.repeats = repeats
        self.text = ''
        self.seen = set()
        self.run = 0
        self.depth = 0
        self.quoted = self.escaped = False
        self.start = None
        self.stopped = False

    def feed(self, fragment):
        if self.stopped:
            return True
        offset = len(self.text)
        self.text += fragment
        for i, ch in enumerate(fragment, offset):
            if self.quoted:
                if self.escaped:
                    self.escaped = False
                elif ch == '\\':
                    self.escaped = True
                elif ch == '"':
                    self.quoted = False
                continue
            if ch == '"':
                self.quoted = True
            elif ch == '{':
                self.depth += 1
                if self.depth == 2:
                    self.start = i
            elif ch == '}':
                if self.depth == 2 and self.start is not None:
                    try:
                        obj = json.loads(self.text[self.start:i+1])
                        word = str(obj.get('w', obj.get('word', ''))).strip().lower()
                        # Repeated words at different evidence points are not
                        # a generation loop: later body parts may still follow.
                        fingerprint = json.dumps(obj, sort_keys=True, separators=(',', ':'))
                    except (ValueError, TypeError):
                        word = ''
                    if word:
                        self.run = self.run + 1 if fingerprint in self.seen else 0
                        self.seen.add(fingerprint)
                        if self.run >= self.repeats:
                            self.text = self.text[:i+1]
                            self.stopped = True
                            return True
                self.depth -= 1
        return False


def read_cefr_stream(response, on_timings=None):
    """``on_timings`` gets llama-server's final ``timings`` (absent if the guard stops early)."""
    guard = RepetitionGuard()
    for line in response:
        if not line.startswith(b'data:'):
            continue
        payload = line[5:].strip()
        if payload == b'[DONE]':
            break
        event = json.loads(payload)
        if event.get('error'):
            raise ValueError(f"model stream failed: {event['error']}")
        if on_timings is not None and event.get('timings'):
            on_timings(event['timings'])
        choices = event.get('choices') or []
        if choices and guard.feed(choices[0].get('delta', {}).get('content') or ''):
            break  # closing the HTTP response cancels the remaining generation
    return guard.text
