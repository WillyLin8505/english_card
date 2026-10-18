"""Read-only image queue diagnostics; no downloads, tagging or credentials."""
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from .picture_need import PICTURE_POS, PRIMARY_ORDINAL


def snapshot(s):
    now = datetime.now(timezone.utc)
    rows = s.execute(text("""
        SELECT t.id, t.status, t.error, t.finished_at,
          EXISTS (SELECT 1 FROM lexemes l JOIN senses sn ON sn.lexeme_id=l.id
            WHERE l.language=t.target_language AND l.normalized=lower(t.lemma)
              AND l.status='full' AND l.pos='%s' AND sn.ordinal<%d) AS eligible,""" % (
                  PICTURE_POS, PRIMARY_ORDINAL) + """
          EXISTS (SELECT 1 FROM lexemes l JOIN senses sn ON sn.lexeme_id=l.id
            JOIN sense_images si ON si.sense_id=sn.id
            WHERE l.language=t.target_language AND l.normalized=lower(t.lemma)
              AND si.review_status<>'rejected') AS has_image
        FROM image_fetch_tasks t
    """)).mappings().all()
    statuses = Counter({k: 0 for k in ('queued', 'running', 'completed', 'completed_with_errors', 'failed')})
    reasons = Counter()
    recent = Counter()
    bare_completed = []
    eligible_bare_completed = []
    for row in rows:
        statuses[row['status']] += 1
        if row['status'] == 'completed' and not row['has_image']:
            bare_completed.append(row['id'])
            if row['eligible']:
                eligible_bare_completed.append(row['id'])
        if row['status'] in ('failed', 'completed_with_errors'):
            error = (row['error'] or '').lower()
            reason = ('rate_limit' if '429' in error or '503' in error else
                      'timeout' if 'timeout' in error or 'timed out' in error or '逾時' in error else
                      'no_english_label' if ('沒有英文標籤' in error or '沒有任何語言標籤' in error
                                             or 'no_english_label' in error) else
                      'no_candidates' if '沒有來源回候選圖片' in error else
                      'format_or_size' if any(k in error for k in ('format', '尺寸', 'size', '格式')) else
                      'other')
            reasons[reason] += 1
        finished = row['finished_at']
        if isinstance(finished, str):
            finished = datetime.fromisoformat(finished)
        if finished and finished.replace(tzinfo=finished.tzinfo or timezone.utc) >= now - timedelta(hours=1):
            recent[row['status']] += 1
    missing = s.execute(text("""
        SELECT DISTINCT l.language, l.normalized FROM lexemes l
        WHERE l.status='full' AND l.pos='%s'
          AND EXISTS (SELECT 1 FROM senses sn WHERE sn.lexeme_id=l.id AND sn.ordinal<%d)""" % (
            PICTURE_POS, PRIMARY_ORDINAL) + """
          AND NOT EXISTS (SELECT 1 FROM image_fetch_tasks t
            WHERE t.target_language=l.language AND lower(t.lemma)=l.normalized)
          AND NOT EXISTS (SELECT 1 FROM senses sn JOIN sense_images si ON si.sense_id=sn.id
            WHERE sn.lexeme_id=l.id AND si.review_status<>'rejected')
        ORDER BY l.language, l.normalized
    """)).mappings().all()
    return {'at': now.isoformat(), 'statuses': dict(statuses),
            'finished_last_hour': dict(recent), 'failure_reasons': dict(reasons),
            'zero_image_completed': len(bare_completed),
            'ineligible_zero_image_completed': len(bare_completed) - len(eligible_bare_completed),
            'eligible_zero_image_completed': len(eligible_bare_completed),
            'eligible_zero_image_completed_ids': eligible_bare_completed,
            'never_enqueued_bare_noun_count': len(missing),
            'never_enqueued_bare_nouns': [dict(r) for r in missing]}
