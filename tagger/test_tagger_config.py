import os, re, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tagger_config as tc


def test_defaults_fast_path():
    env = tc.apply_defaults({})
    assert env['TAGGER_BACKEND'] == 'llamacpp'
    assert env['TAGGER_PARALLEL'] == '4'
    assert env['TAGGER_IMAGE_MAX_EDGE'] == '512' and env['TAGGER_JPEG_QUALITY'] == '65'
    assert env['TAGGER_CEFR_REPEAT_GUARD'] == '1' and env['TAGGER_CEFR_NUM_PREDICT'] == '820'


def test_explicit_env_wins():
    assert tc.apply_defaults({'TAGGER_PARALLEL': '2'})['TAGGER_PARALLEL'] == '2'


def test_ollama_needs_opt_in():
    with pytest.raises(SystemExit):
        tc.check_backend({'TAGGER_BACKEND': 'ollama'})
    tc.check_backend({'TAGGER_BACKEND': 'ollama', 'TAGGER_ALLOW_OLLAMA': '1'})
    tc.check_backend({'TAGGER_BACKEND': 'llamacpp'})


def test_bat_does_not_duplicate_defaults():
    bat = open(os.path.join(os.path.dirname(tc.__file__), 'start_tagger.bat'), encoding='utf-8', errors='replace').read()
    assert not re.search(r'^\s*set TAGGER_', bat, re.I | re.M)
