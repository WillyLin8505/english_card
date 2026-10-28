"""Card #694 / 問題回報 #822 (owner option A): Datamuse "related" words of function words are noise
(be→existence, at→halogen, as→arsenic).  They are hidden in the App, never deleted.
can / may / will / a / i are left out: they are also real nouns whose related words are fine."""

FUNCTION_WORDS = frozenset((
    "be,the,was,were,is,are,am,been,being,for,at,of,to,in,on,by,with,from,an,and,or,but,not,do,does,did,"
    "have,has,had,it,he,she,they,we,you,this,that,these,those,as,if,so,than,then,there,"
    "would,could,might,shall,should,must,up,out,into,about,over,after,before,who,which,what,when,where,how"
).split(","))

NOISY_SOURCE = "datamuse"
HIDDEN_REASON = "function_word_datamuse"


def is_noisy_function_word_relation(lemma: str, source: str | None) -> bool:
    return (lemma or "").strip().lower() in FUNCTION_WORDS and (source or "").lower() == NOISY_SOURCE
