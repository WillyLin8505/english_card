from types import SimpleNamespace
import pytest
from app.text import looks_simplified
from app.adapters.base import Candidate, Context, validate
from app.pipeline import stored_candidates


@pytest.mark.parametrize('value', ['蜂群', '床罩', '群居的', '人群的聚集。',
                                  '清除同位素混合物（中的同位素或同位素群）。'])
def test_taiwan_characters_are_not_simplified(value):
    assert not looks_simplified(value)
    assert validate(Candidate('native_definition','zh-TW',{'text':value},'s'),
                    Context('en','zh-TW','test')) is None


@pytest.mark.parametrize('value', ['外观', '颠覆者', '公开展示', '后台程序'])
def test_actual_simplified_is_still_rejected(value):
    assert looks_simplified(value)


@pytest.mark.parametrize('value,reason,expected', [
    ('蜂群', '簡體字（繁中資料包需繁體）', True),
    ('外观', '簡體字（繁中資料包需繁體）', False),
    ('蜂群', 'manual rejection', False),
    ('蜂群gammon', '簡體字（繁中資料包需繁體）', False),
])
def test_cached_rejection_recovery_is_narrow(value, reason, expected):
    row=SimpleNamespace(id=1,language='zh-TW',value={'text':value},item_key='s',
        source='ai_translate',slot='s',source_record_id='',confidence=.6,
        license='',attribution='',raw_value=None,retrieved_at=None,valid=False,
        invalid_reason=reason,snapshot_id=None)
    class Result:
        def scalar_one_or_none(self): return SimpleNamespace(status='missing')
        def scalars(self): return self
        def all(self): return [row]
    class Session:
        def execute(self, query): return Result()
    cs,_=stored_candidates(Session(),Context('en','zh-TW','hive'),'native_definition','ai_translate')
    assert cs[0].valid is expected
