"""Word-detail data pipeline for 拍照學英文.

Aggregates the 12 data categories defined in spec-01-data-sources.html
(單字/釋義/詞性, 音標, 真人發音, 近義字, 同音字, 拼字相近, 詞形變化,
詞性衍生, 字根字尾, 例句, 例句翻譯, 整句發音) from Kaikki/Wiktionary,
Open English WordNet, CMUdict, Datamuse and Tatoeba, following the
source-priority table, and produces the JSON that the Figma
`word-detail-view` screen needs.
"""
