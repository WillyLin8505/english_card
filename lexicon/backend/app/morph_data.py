"""English word parts for 構詞拆解: prefixes, suffixes and bound
(Latin / Greek) roots, each with an English and a Traditional Chinese
meaning. Compiled for this project from standard word-formation
references; origin: L Latin, G Greek, E English (Germanic), F French.

One entry per line:  forms | English meaning | 繁中意思 | origin
The first form is the one shown; the others are spellings met in words
(assimilated prefixes such as in- → im-, il-, ir-).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Morph:
    kind: str  # prefix / suffix / root
    form: str  # shown form
    spellings: tuple[str, ...]
    en: str
    zh: str
    origin: str
    tag: str = ""  # "neg" / "dir" for prefixes with two meanings

    @property
    def shown(self) -> str:
        return {"prefix": f"{self.form}-", "suffix": f"-{self.form}"}.get(self.kind, self.form)


PREFIXES = """
a | not, without | 不、無 | G | neg
a | on, in a state of | 處於…狀態、在…上 | E
ab, abs | away from | 離開 | L
ad, ac, af, ag, al, an, ap, ar, as, at | to, toward | 朝向、加強 | L
ambi | both | 兩、雙 | L
amphi | both, around | 兩側、周圍 | G
an | not, without | 不、無 | G | neg
ana | up, again | 向上、再 | G
ante | before | 之前 | L
anti, ant | against | 反對、對抗 | G
apo | away from | 離開 | G
arch | chief | 首要、主要的 | G
auto | self | 自己 | G
be | make, thoroughly | 使…、完全地 | E
bene | good, well | 好 | L
bi | two | 二、雙 | L
circum | around | 環繞 | L
co, col, com, con, cor | together, with | 共同、一起 | L
contra, contro | against | 相反、對抗 | L
counter | against, opposite | 相反、對應 | F
de | down, away, reverse | 向下、去除、相反 | L
deca, dec | ten | 十 | G
di | two | 二 | G
dia | through, across | 穿過、之間 | G
dis, dif | apart, not | 分開、不 | L
dys | bad, difficult | 不良、困難 | G
e, ef, ex | out, away | 向外、出 | L
ec | out | 向外 | G
em, en | in, into; make | 進入；使… | F
endo | within | 在內 | G
epi | upon, over | 在…之上 | G
eu | good, well | 好 | G
extra, extro | outside, beyond | 以外、超出 | L
fore | before | 之前、預先 | E
hemi | half | 半 | G
hetero | other | 異 | G
homo | same | 同 | G
hyper | over, too much | 超過、過度 | G
hypo | under, too little | 在下、不足 | G
il, im, in, ir | not | 不、無 | L | neg
il, im, in, ir | in, into | 在內、向內 | L | dir
infra | below | 在下 | L
inter | between, among | 在…之間、互相 | L
intra, intro | within, inward | 在內、向內 | L
kilo | thousand | 千 | G
macro | large | 大 | G
mal, male | bad, badly | 壞、不良 | L
micro | small | 小 | G
mid | middle | 中間 | E
milli | thousandth | 千分之一 | L
mis | wrongly | 錯誤地 | E
mono | one, single | 單一 | G
multi | many | 多 | L
neo | new | 新 | G
non | not | 非、不 | L | neg
ob, oc, of, op | against, toward | 相對、朝向 | L
omni | all | 全 | L
out | beyond, more than | 超過、向外 | E
over | above, too much | 在上、過度 | E
pan | all | 全 | G
para | beside, beyond | 旁邊、類似 | G
per | through, thoroughly | 穿過、完全 | L
peri | around | 周圍 | G
poly | many | 多 | G
post | after, behind | 之後 | L
pre | before | 之前、預先 | L
pro | forward, for | 向前、支持 | L
pseudo | false | 假 | G
re, red | again, back | 再、回 | L
retro | backward | 向後 | L
se | apart | 分開 | L
semi | half | 半 | L
sub, suc, suf, sug, sum, sup, sur, sus | under, below | 在下、次於 | L
super, supra | above, over | 在上、超 | L
sur | over, above | 在上、超 | F
sym, syn, syl, sys | together, with | 共同、同時 | G
tele | far | 遠 | G
trans, tra | across, beyond | 橫越、轉移 | L
tri | three | 三 | L
ultra | beyond | 超越 | L
un | not | 不 | E | neg
un | reverse an action | 反轉動作、解開 | E | dir
under | below, too little | 在下、不足 | E
uni | one | 單一 | L
up | up | 向上 | E
with | back, against | 向後、反 | E
"""

SUFFIXES = """
able, ible | can be done | 可…的 | L
ac | relating to | …的 | G
acy, cy | state, quality | 狀態、性質 | L
age | action, result, place | 行為、結果、場所 | F
al | relating to; act of | …的；…的行為 | L
an, ian | person; relating to | …的人；…的 | L
ance, ence, ancy, ency | state, quality | 狀態、性質 | L
ant, ent | one who; -ing | …的人；…的 | L
ar | relating to | …的 | L
ard | person (often negative) | …的人 | F
ary, ery, ory | place; relating to | 場所；…的 | L
ate | make; having | 使…；具有…的 | L
ation, ition, tion, sion, ion | act, result | 行為、結果 | L
ator, itor | one who does | 做…的人、…器 | L
cide | killing | 殺 | L
cracy | rule | 統治 | G
crat | ruler | 統治者 | G
dom | state, realm | 狀態、領域 | E
ed | having; past | 具有…的；已… | E
ee | one who receives | 受…者 | F
eer | one who works with | …者 | F
en | make; made of | 使…；…製的 | E
er | one who; more | …的人、…的東西；更… | E
ern | direction | …方的 | E
ese | of a place | …地方的 | L
esque | in the style of | …風格的 | F
ess | female | 女性… | F
est | most | 最… | E
ette | small | 小… | F
ful | full of | 充滿…的 | E
fy, ify | make | 使…化 | L
graph | writing, record | 書寫、記錄 | G
graphy | writing, study | …書寫、…學 | G
hood | state, group | 狀態、身分 | E
ia | condition | 狀況、病症 | G
ic | relating to | …的 | G
ical | relating to | …的 | G
ics | study, skill | …學、…術 | G
ier, yer | one who | …者 | F
ile | capable of | 能…的 | L
ine | relating to | …的 | L
ing | action, result | 動作、…的事物 | E
ior | more (comparative) | 較…的（比較級） | L
ish | like, somewhat | 像…的、有點… | E
ism | belief, practice | 主義、行為 | G
ist | person who does | …家、…者 | G
ite | person, mineral | …人、…石 | G
itis | inflammation | 發炎 | G
ity, ty | state, quality | 性質、狀態 | L
ive, ative, itive | tending to | 有…性質的 | L
ize, ise | make | 使…化 | G
less | without | 無…的 | E
let | small | 小… | F
like | like | 像…的 | E
ling | small; person | 小…；…的人 | E
logy, ology | study of | …學 | G
ly | in a … way; like | …地；像…的 | E
ment | result, act | 結果、行為 | L
meter | measuring device | …計、…表 | G
most | most | 最… | E
ness | state, quality | 性質、狀態 | E
oid | like | 類似…的 | G
or | one who | …者 | L
ose | full of | 含…的 | L
ous, ious, eous, uous | full of | 充滿…的 | L
phile | lover of | 愛好…者 | G
phobia | fear | 恐懼 | G
phone | sound | 聲音 | G
scope | viewing device | …鏡 | G
ship | state, skill | 身分、技能 | E
some | tending to | 易於…的 | E
ster | person | 從事…的人 | E
teen | plus ten | 十幾 | E
ter | (Latin) on the … side | （拉丁字尾，表「…側」） | L
th | state; ordinal | 狀態；第… | E
tude | state | 狀態 | L
ule, cule | small | 小 | L
ure | act, result | 行為、結果 | L
ward, wards | direction | 朝…方向 | E
ways | manner, direction | …方式、…方向 | E
wise | manner | 以…方式 | E
y | full of, like | 有…的、像…的 | E
y | state, act | 狀態、行為 | L
"""

ROOTS = """
act, ag | do, drive | 做、驅動 | L
aer, aero | air | 空氣 | G
agr | field | 田 | L
alter, alt | other | 其他 | L
am, amat | love | 愛 | L
ambul | walk | 走 | L
anim | life, mind | 生命、心靈 | L
ann, enn | year | 年 | L
anthrop | human | 人類 | G
aqu, aqua | water | 水 | L
arch | rule | 統治 | G
art | skill | 技藝 | L
astr, aster | star | 星 | G
aud, audi, audit | hear | 聽 | L
bell | war | 戰爭 | L
bibli | book | 書 | G
bio | life | 生命 | G
brev | short | 短 | L
cad, cas, cid | fall | 落下 | L
cand | white, shining | 白、發光 | L
cap, capt, cept, ceiv, ceit, cip | take | 拿、抓 | L
capit | head | 頭 | L
carn | flesh | 肉 | L
ced, cede, ceed, cess | go, yield | 走、讓 | L
cent | hundred | 百 | L
centr | center | 中心 | L
chrom | color | 顏色 | G
chron | time | 時間 | G
cis, cise | cut | 切 | L
cit | call, set in motion | 召喚、引起 | L
civ | citizen | 公民 | L
claim, clam | shout | 喊叫 | L
clar | clear | 清楚 | L
clin | lean | 傾斜 | L
clud, clus, clude, clos | close | 關閉 | L
cogn, gnos | know | 知道 | L
cord, cor | heart | 心 | L
corp, corpor | body | 身體 | L
cosm | world, order | 宇宙、秩序 | G
cred | believe | 相信 | L
cre, cresc, cret | grow | 生長 | L
crim | crime | 罪 | L
cruc | cross | 十字 | L
cult | grow, till | 培育、耕種 | L
cur, curr, curs, cour | run | 跑 | L
cycl | circle | 圓、循環 | G
dem, demo | people | 人民 | G
dent, dont | tooth | 牙齒 | L
derm | skin | 皮膚 | G
dic, dict | say | 說 | L
doc, doct | teach | 教 | L
dom | house; rule | 家；統治 | L
don, dat | give | 給 | L
dorm | sleep | 睡 | L
duc, duct, duce | lead | 引導 | L
dur | hard, lasting | 堅硬、持久 | L
dyn, dynam | power | 力量 | G
ego | I, self | 我 | L
equ, equi | equal | 相等 | L
erg | work | 工作 | G
err | wander, mistake | 偏離、錯誤 | L
fac, fact, fect, fic, fac | make, do | 做 | L
fall, fals | deceive | 欺騙、錯誤 | L
fam | fame | 名聲 | L
fend, fens | strike | 打擊 | L
fer | carry | 攜帶 | L
fess | say, admit | 說、承認 | L
fid | trust | 信任 | L
fil | thread; son | 線；子 | L
fin | end, limit | 結束、界限 | L
firm | strong | 堅固 | L
flam | flame | 火焰 | L
flect, flex | bend | 彎曲 | L
flor | flower | 花 | L
flu, flux | flow | 流 | L
form | shape | 形狀 | L
fort | strong | 強 | L
fract, frag | break | 破碎 | L
fus, fund | pour | 倒、流 | L
gam | marriage | 婚姻 | G
gen, gener | birth, kind | 產生、種類 | L
geo | earth | 土地 | G
gest | carry | 攜帶 | L
grad, gress | step | 步、走 | L
gram | written | 寫下的 | G
graph | write | 寫、畫 | G
grat | pleasing, thanks | 感謝、令人愉快 | L
grav | heavy | 重 | L
greg | flock | 群 | L
hab, habit, hibit | have, live | 擁有、居住 | L
her, hes | stick | 黏著 | L
hosp, host | guest, host | 客人、主人 | L
hum | earth; human | 土地；人 | L
hydr | water | 水 | G
ject | throw | 投擲 | L
jud, judic | judge | 判斷 | L
junct, join | join | 連接 | L
jur, jus | law, right | 法律、正當 | L
lab, labor | work | 工作 | L
lat | carry | 攜帶 | L
lect, leg, lig | choose, read | 選、讀 | L
leg | law | 法律 | L
lev | light, raise | 輕、舉起 | L
liber | free | 自由 | L
lingu | tongue, language | 舌、語言 | L
lit, liter | letter | 字母、文字 | L
loc | place | 地方 | L
log, logue | word, reason | 言語、道理 | G
loqu, locut | speak | 說 | L
luc, lum, lumin | light | 光 | L
magn | great | 大 | L
man, manu | hand | 手 | L
mand, mend | order | 命令 | L
mar | sea | 海 | L
mater, matr | mother | 母親 | L
medi | middle | 中間 | L
mem, memor | remember | 記憶 | L
ment | mind | 心智 | L
merg, mers | dip | 沉、浸 | L
meter, metr | measure | 測量 | G
migr | move | 遷移 | L
min | small | 小 | L
mir | wonder | 驚奇 | L
miss, mit | send | 送 | L
mob, mot, mov | move | 動 | L
mon, monit | warn | 警告 | L
mor | custom | 習俗 | L
morph | shape | 形狀 | G
mort | death | 死 | L
mult | many | 多 | L
mut | change | 改變 | L
nat, nasc | born | 出生 | L
nav | ship | 船 | L
neg | deny | 否定 | L
nom, nym, onym | name | 名字 | G
not | mark | 記號 | L
nounc, nunci | announce | 宣告 | L
nov | new | 新 | L
numer | number | 數 | L
oper | work | 工作 | L
opt | choose; see | 選擇；看 | L
ord, ordin | order | 順序 | L
orig | beginning | 起源 | L
pac | peace | 和平 | L
pan | bread | 麵包 | L
par | equal; appear | 相等；出現 | L
part, pars | part | 部分 | L
pass, pat, path | feel, suffer | 感受、忍受 | L
pater, patr | father | 父親 | L
ped | foot; child | 腳；兒童 | L
pel, puls | drive, push | 推、驅動 | L
pend, pens | hang, weigh | 懸掛、衡量 | L
pet | seek | 追求 | L
phil | love | 愛 | G
phon | sound | 聲音 | G
phot, photo | light | 光 | G
plac | please | 使高興 | L
plen, plet | full | 滿 | L
plic, ply, plex | fold | 摺疊 | L
pon, pos, posit, pose | put, place | 放置 | L
pop, publ | people | 人民 | L
port | carry | 攜帶 | L
pot | power | 能力 | L
press | press | 壓 | L
prim, prin | first | 第一 | L
prob, prov | prove, test | 證明、測試 | L
psych | mind | 心靈 | G
punct | point | 點 | L
quer, quest, quir, quis | seek, ask | 尋求、問 | L
rect, reg | straight; rule | 直；統治 | L
rid, ris | laugh | 笑 | L
rupt | break | 破裂 | L
san | health | 健康 | L
sat | enough | 足夠 | L
sci | know | 知道 | L
scop | look | 看 | G
scrib, script | write | 寫 | L
sect, sec | cut | 切 | L
sed, sid, sess | sit | 坐 | L
sens, sent | feel | 感覺 | L
sequ, secu | follow | 跟隨 | L
serv | serve, keep | 服務、保存 | L
sign | mark | 記號 | L
simil, simul | like | 相似 | L
sist, sta, stat, stit | stand | 站立 | L
soci | companion | 同伴 | L
sol | sun; alone | 太陽；單獨 | L
solv, solu | loosen | 鬆開、解開 | L
son | sound | 聲音 | L
soph | wise | 智慧 | G
spec, spect, spic | look | 看 | L
spir | breathe | 呼吸 | L
spond, spons | promise | 承諾 | L
struct, stru | build | 建造 | L
sum, sumpt | take | 拿 | L
tact, tang, tag, ting | touch | 觸摸 | L
tain, ten, tin | hold | 握住 | L
tempor, temp | time | 時間 | L
tend, tens, tent | stretch | 伸展 | L
terr, terra | earth | 土地 | L
test | witness | 證明 | L
text | weave | 編織 | L
the, theo | god | 神 | G
therm | heat | 熱 | G
tim | fear | 害怕 | L
tort | twist | 扭 | L
tract, trah | pull | 拉 | L
trib | give | 給予 | L
turb | disturb | 擾亂 | L
urb | city | 城市 | L
vac | empty | 空 | L
vad, vas | go | 走 | L
vag | wander | 漫遊 | L
val, vail | strong, worth | 強、價值 | L
ven, vent | come | 來 | L
ver | true | 真 | L
vers, vert | turn | 轉 | L
vid, vis | see | 看 | L
vinc, vict | conquer | 征服 | L
vit, viv | life | 生命 | L
voc, vok | call, voice | 呼喚、聲音 | L
vol | wish | 意願 | L
volv, volu | roll | 捲、滾 | L
vor | eat | 吃 | L
"""


def _parse(kind: str, text: str) -> list[Morph]:
    out = []
    for line in text.strip().splitlines():
        cols = [c.strip() for c in line.split("|")]
        forms = tuple(f.strip() for f in cols[0].split(","))
        out.append(Morph(kind, forms[0], forms, cols[1], cols[2], cols[3],
                         cols[4] if len(cols) > 4 else ""))
    return out


ALL = _parse("prefix", PREFIXES) + _parse("suffix", SUFFIXES) + _parse("root", ROOTS)


def index(kind: str) -> dict[str, list[Morph]]:
    """spelling → entries (one spelling can belong to several entries)."""
    out: dict[str, list[Morph]] = {}
    for m in ALL:
        if m.kind == kind:
            for s in m.spellings:
                out.setdefault(s, []).append(m)
    return out


PREFIX = index("prefix")
SUFFIX = index("suffix")
ROOT = index("root")
# Prepositions that also work as a word's base, as in Latin comparatives:
# ex·ter·ior, inter·ior, super·ior, post·er·ior.
BASE_PREFIXES = {"ex", "inter", "super", "sub", "post", "ante", "pre", "pro", "extra", "ultra",
                 "intra", "contra", "infra", "trans", "circum", "de", "in"}
GERMANIC = {"ang", "enm", "non", "gem-pro", "gmw-pro", "goh", "gmh", "osx", "odt", "dum", "nl",
            "de", "frk", "ine-pro"}
LATINATE = {"la", "LL.", "ML.", "VL.", "fro", "frm", "fr", "xno", "grc", "it", "es", "pt",
            "itc-pro"}


def lookup(kind: str, part: str) -> list[Morph]:
    """Entries for a displayed part such as 'ex-', '-ior' or 'spect'."""
    p = part.strip().strip("-").lower()
    return {"prefix": PREFIX, "suffix": SUFFIX, "root": ROOT}[kind].get(p, [])
