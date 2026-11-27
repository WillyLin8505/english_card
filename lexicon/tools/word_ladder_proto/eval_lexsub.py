"""Lexical-substitution models as the judge (owner 11/27 「同時驗證其他的詞彙替換模型」), CPU only (onnxruntime):
  * BERT (Xenova/bert-base-uncased, quantized): LS-BERT style — "sentence [SEP] sentence with the word masked";
    score = log-probability of the candidate at the mask (first word piece; multi-piece words get a penalty);
  * MiniLM (Xenova/all-MiniLM-L6-v2): cosine between the example sentence and the sentence with the candidate.
Same gold as eval_methods.py (batch 00; kept by both Claude and Codex). Only senses with an example sentence.

    python lexicon/tools/word_ladder_proto/eval_lexsub.py
"""
import os, re, sys, time
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_methods as em  # rows / gold

M = os.path.join(em.wl.ROOT, 'lexicon', 'raw-data', 'ls_models')
opt = ort.SessionOptions()
opt.intra_op_num_threads = 4  # leave the rest of the CPU to everything else
bert = ort.InferenceSession(os.path.join(M, 'bert', 'model_quantized.onnx'), opt, providers=['CPUExecutionProvider'])
btok = Tokenizer.from_file(os.path.join(M, 'bert', 'tokenizer.json'))
mini = ort.InferenceSession(os.path.join(M, 'minilm', 'model_quantized.onnx'), opt, providers=['CPUExecutionProvider'])
mtok = Tokenizer.from_file(os.path.join(M, 'minilm', 'tokenizer.json'))
MASK = btok.token_to_id('[MASK]')

sense_info = {}
for e in em.qwen['entries']:
    for s in e['senses']:
        if s.get('ssid'):
            sense_info[(e['word'], e['pos'], s['ssid'])] = s


def find(word, sent):
    """Span of the headword (or an inflected form) in the example."""
    stem = word[:-1] if len(word) > 4 and word.endswith('e') else word
    m = re.search(r'\b(' + re.escape(word) + r'|' + re.escape(stem) + r'[a-z]{0,4})\b', sent, re.I)
    return m.span() if m else None


def feed(sess, enc_list):
    n = max(len(e.ids) for e in enc_list)
    ids = np.array([e.ids + [0] * (n - len(e.ids)) for e in enc_list], dtype=np.int64)
    att = np.array([[1] * len(e.ids) + [0] * (n - len(e.ids)) for e in enc_list], dtype=np.int64)
    inp = {'input_ids': ids, 'attention_mask': att}
    if 'token_type_ids' in [i.name for i in sess.get_inputs()]:
        inp['token_type_ids'] = np.array([e.type_ids + [0] * (n - len(e.ids)) for e in enc_list], dtype=np.int64)
    return sess.run(None, inp)[0], att


def bert_scores(sent, span, cands):
    masked = sent[:span[0]] + '[MASK]' + sent[span[1]:]
    enc = btok.encode(sent, masked)
    pos = enc.ids.index(MASK)
    logits, _ = feed(bert, [enc])
    lp = logits[0, pos] - np.log(np.exp(logits[0, pos] - logits[0, pos].max()).sum()) - logits[0, pos].max()
    out = {}
    for c in cands:
        pieces = btok.encode(c, add_special_tokens=False).ids
        out[c] = float(lp[pieces[0]]) - 3.0 * (len(pieces) - 1)
    return out


def mini_scores(sent, span, cands):
    texts = [sent] + [sent[:span[0]] + c + sent[span[1]:] for c in cands]
    embs, att = feed(mini, [mtok.encode(t) for t in texts])
    v = (embs * att[..., None]).sum(1) / att.sum(1, keepdims=True)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return {c: float(v[0] @ v[i + 1]) for i, c in enumerate(cands)}


by = {}
for key, x, gold, m in em.rows:
    by.setdefault(key, []).append((x, gold, m))
data, t = [], time.time()
for key, items in by.items():
    s = sense_info[key]
    sent = s.get('example') or ''
    span = find(key[0], sent)
    if not span:
        continue
    cands = [x for x, _, _ in items]
    b, mi = bert_scores(sent, span, cands), mini_scores(sent, span, cands)
    data += [(key, x, g, m, b[x], mi[x]) for x, g, m in items]
sec = time.time() - t
print(f'lexsub: {len(by)} senses, {len({d[0] for d in data})} with an example, {len(data)} candidates, '
      f'{sec:.0f}s CPU ({sec / max(len(data), 1) * 1000:.0f} ms per candidate)')


def report(name, pred):
    tp = sum(1 for d in data if d[2] and pred(d))
    fp = sum(1 for d in data if not d[2] and pred(d))
    fn = sum(1 for d in data if d[2] and not pred(d))
    print(f'{name:34s} precision {tp / max(tp + fp, 1):5.1%}  recall {tp / max(tp + fn, 1):5.1%}  kept {tp + fp}')


report('all (same senses)', lambda d: True)
report('wordnet (same senses)', lambda d: d[3]['wordnet'])
for th in (-6, -8, -10):
    report(f'BERT logp >= {th}', lambda d, th=th: d[4] >= th)
for th in (0.85, 0.9, 0.93):
    report(f'MiniLM cos >= {th}', lambda d, th=th: d[5] >= th)
report('BERT>=-8 and MiniLM>=0.85', lambda d: d[4] >= -8 and d[5] >= 0.85)
report('wordnet or (BERT>=-8 & MiniLM>=.9)', lambda d: d[3]['wordnet'] or (d[4] >= -8 and d[5] >= 0.9))
report('prefilter & BERT>=-10', lambda d: (d[3]['wordnet'] or d[3]['reverse'] or d[3]['wup.8']) and d[4] >= -10)
report('wordnet or (prefilter & BERT>=-8)', lambda d: d[3]['wordnet'] or ((d[3]['reverse'] or d[3]['wup.8']) and d[4] >= -8))


def topk(k):
    best = {}
    for d in data:
        best.setdefault(d[0], []).append(d)
    keep = set()
    for key, ds in best.items():
        ds.sort(key=lambda d: -(d[4] + 10 * d[5] + (5 if d[3]['wordnet'] else 0)))
        keep |= {(key, d[1]) for d in ds[:k]}
    return keep


for k in (3, 5):
    kk = topk(k)
    report(f'top {k} per sense (BERT+MiniLM+WN)', lambda d, kk=kk: (d[0], d[1]) in kk)
