"""Run directly: python lexicon/tests/test_image_fetch_audit.py (no live DB)."""
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.image_fetch_audit import snapshot


class AuditTest(unittest.TestCase):
    def test_missing_eligible_rejected_and_failures_without_writes(self):
        engine = create_engine('sqlite://')
        with Session(engine) as s:
            for ddl in (
                'CREATE TABLE image_fetch_tasks (id int, target_language text, lemma text, status text, error text, finished_at text)',
                'CREATE TABLE lexemes (id int, language text, normalized text, status text, pos text)',
                'CREATE TABLE senses (id int, lexeme_id int, ordinal int)',
                'CREATE TABLE sense_images (sense_id int, review_status text)',
            ):
                s.execute(text(ddl))
            s.execute(text("INSERT INTO lexemes VALUES (1,'en','apple','full','noun'),(2,'en','run','full','verb'),(3,'en','pear','full','noun'),(4,'en','plum','full','noun')"))
            s.execute(text('INSERT INTO senses VALUES (1,1,0),(2,2,0),(3,3,0),(4,4,0)'))
            s.execute(text("INSERT INTO sense_images VALUES (1,'rejected'),(4,'pending')"))
            s.execute(text("INSERT INTO image_fetch_tasks VALUES (1,'en','Apple','completed',NULL,NULL),(2,'en','run','completed',NULL,NULL),(3,'en','x','completed_with_errors','HTTP 429',NULL),(4,'en','y','failed','timed out',NULL),(5,'en','z','queued',NULL,NULL)"))
            s.commit()
            result = snapshot(s)
            self.assertEqual(result['zero_image_completed'], 2)
            self.assertEqual(result['eligible_zero_image_completed_ids'], [1])
            self.assertEqual(result['never_enqueued_bare_nouns'], [{'language': 'en', 'normalized': 'pear'}])
            self.assertEqual(result['failure_reasons'], {'rate_limit': 1, 'timeout': 1})
            self.assertEqual(result['statuses']['queued'], 1)
            self.assertEqual(result['statuses']['running'], 0)
            self.assertEqual(s.scalar(text('SELECT count(*) FROM image_fetch_tasks')), 5)


if __name__ == '__main__':
    unittest.main()
