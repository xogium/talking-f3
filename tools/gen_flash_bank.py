#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""gen_flash_bank.py -- build one language's clip bank for the talking F3.

For every UI string of the language (F3_strings_all_langs.json) plus our extra phrases
(slots 590..839: "selected", numbers, months, date fields, letters, hundreds/thousands,
status words, the startup chime), the text is prepared for espeak-ng (spoken overrides for
strings the F3 leaves in English, unit words, pinyin for Chinese, kana for Japanese kanji,
English voice for latin words inside Japanese), synthesized, resampled to 16 kHz mono and
Opus-encoded (libopus via tools/opus_tool: VOIP, 16 kbps, 10 ms frames; chime: music mode).

Bank layout (all little-endian), the engine reads it in place from flash:
   header 32 B : magic 'F3VX' 'BANK', rate, nslots, fmt (2 = Opus),
                 r0 = offset of the built-in-text hash table, r1 = offset of the clip-text
                 lookup table, r2 = language index | year_style << 8
   index       : nslots x {offset from clip data start, PCM sample count}  (slot = string id)
   clip data   : per clip [u8 length][Opus packet]...
   r0 table    : nslots x u16 FNV-1a of the built-in UI string (runtime-text detection)
   r1 table    : nslots x u32 FNV-1a of each clip's lower-cased text (runtime-text lookup)

  python3 tools/gen_flash_bank.py --lang FR --out build/banks/FR [--speed 300] [--pitch 50]
          [--variant michel] [--kbps 16]
Output: <out>/flash_bank.bin (+ manifest.txt, report.json). tools/gen_all_banks.sh builds
all seven languages and joins them.
"""
import os, sys, json, struct, subprocess, tempfile, argparse

MAGIC0=0x58563346   # 'F3VX'
MAGIC1=0x4B4E4142   # 'BANK'
CLIP_MAX_ID=840
HDR_BYTES=32
FMT_OPUS=2
OPUS_TOOL=os.path.join(os.path.dirname(os.path.abspath(__file__)),"opus_tool")

CHIME_ID=756
def chime_pcm(rate):
    """Startup chime: rising major arpeggio (C6 E6 G6 C7), soft bell-like notes, ~1 s,
    peak -3 dBFS like the speech clips. Played once the voice engine is ready."""
    import math
    notes=[1046.50,1318.51,1567.98,2093.00]; step=0.13; dur=0.55
    n=int(rate*(step*(len(notes)-1)+dur)); buf=[0.0]*n
    for k,f in enumerate(notes):
        t0=int(k*step*rate)
        for i in range(int(dur*rate)):
            t=i/rate
            env=min(1.0,t/0.006)*math.exp(-t*6.5)
            h=0.25*math.sin(2*math.pi*2*f*t)*math.exp(-t*10) if 2*f < rate/2 else 0.0   # no alias at 8 kHz
            v=env*(math.sin(2*math.pi*f*t)+h)
            if t0+i<n: buf[t0+i]+=v
    pk=max(abs(x) for x in buf) or 1.0; g=0.7*32767/pk
    return [int(round(x*g)) for x in buf]

def opus_encode(pcm, kbps, frame_ms, music=False, rate=16000):
    """mono PCM at 16 kHz (wideband) or 24 kHz (super-wideband) -> [u8 len][packet]... (libopus VOIP)."""
    raw=struct.pack("<%dh"%len(pcm),*pcm)
    p=subprocess.run([OPUS_TOOL,"enc",str(kbps*1000),str(frame_ms),"rate=%d"%rate]+(["music"] if music else []),input=raw,
                     capture_output=True,check=True).stdout
    out=bytearray(); i=0; nfr=0
    while i<len(p):
        L=p[i]|p[i+1]<<8; i+=2
        if not 0<L<256: raise ValueError("packet length %d"%L)
        out.append(L); out+=p[i:i+L]; i+=L; nfr+=1
    if nfr*(rate//1000)*frame_ms < len(pcm): raise ValueError("short encode")
    return bytes(out)

VARIANT = "michel"     # espeak-ng voice variant for every language (--variant)
PITCH = 50             # espeak-ng pitch 0..99 (--pitch)
def synth(text, voice, rate, speed):
    if "+" not in voice and VARIANT: voice = voice + "+" + VARIANT
    tw=tempfile.NamedTemporaryFile(suffix=".wav",delete=False).name
    tr=tempfile.NamedTemporaryFile(suffix=".raw",delete=False).name
    try:
        subprocess.run(["espeak-ng","-v",voice,"-s",str(speed),"-p",str(PITCH),"-w",tw],
                       input=text.encode("utf-8"),check=True,timeout=30,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(["ffmpeg","-y","-loglevel","error","-i",tw,"-ar",str(rate),
                        "-ac","1","-f","s16le",tr],check=True,timeout=30)
        raw=open(tr,"rb").read()
        return list(struct.unpack("<%dh"%(len(raw)//2),raw))
    finally:
        for f in (tw,tr):
            try: os.remove(f)
            except OSError: pass

# ---- per-language configuration --------------------------------------------------
# key (F3_strings_all_langs.json) -> (F3 language index L, espeak voice, year style)
# year style: 0 = English pairs, 1 = whole number, 2 = digit by digit (see voice.c say_year)
LANG_CFG = {
    "EN": (0, "en", 0), "FR": (1, "fr", 1), "DE": (2, "de", 1),
    "IT": (3, "it", 1), "ES": (4, "es", 1), "L5": (5, "cmn", 2),
    "L6": (6, "ja", 1),
}
LANG_NAME_SID = {"EN": 48, "FR": 49, "DE": 50, "IT": 51, "ES": 52, "L5": 53, "L6": 54}
MONTHS = {
 "EN": "January February March April May June July August September October November December",
 "FR": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
 "DE": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember",
 "IT": "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre",
 "ES": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre",
 "L5": "一月 二月 三月 四月 五月 六月 七月 八月 九月 十月 十一月 十二月",
 "L6": "いちがつ にがつ さんがつ しがつ ごがつ ろくがつ しちがつ はちがつ くがつ じゅうがつ じゅういちがつ じゅうにがつ",
}
# slot: selected, Year, Month, Day, Hour, Minute, hundred, thousand, point, percent, of,
#       hours, minutes, Battery, external power
WORDS = {
 "EN": ["selected","Year","Month","Day","Hour","Minute","hundred","thousand","point","percent","of",
        "hours","minutes","Battery","external power"],
 "FR": ["choix actuel","Année","Mois","Jour","Heure","Minute","cent","mille","virgule","pour cent","sur",
        "heures","minutes","Batterie","alimentation externe"],
 "DE": ["ausgewählt","Jahr","Monat","Tag","Stunde","Minute","hundert","tausend","Komma","Prozent","von",
        "Stunden","Minuten","Batterie","externe Stromversorgung"],
 "IT": ["selezionato","Anno","Mese","Giorno","Ora","Minuto","cento","mille","virgola","per cento","su",
        "ore","minuti","Batteria","alimentazione esterna"],
 "ES": ["seleccionado","Año","Mes","Día","Hora","Minuto","cien","mil","coma","por ciento","de",
        "horas","minutos","Batería","alimentación externa"],
 "L5": ["已选择","年","月","日","时","分","百","千","点","百分比","共",
        "小时","分钟","电池","外部电源"],
 "L6": ["せんたくちゅう","ねん","つき","ひ","じ","ふん","ひゃく","せん","てん","パーセント","ぜんたいわ",
        "じかん","ふん","でんち","がいぶでんげん"],
}
WORD_SLOTS = [590, 712, 713, 714, 715, 716, 746, 747, 748, 749, 750, 751, 752, 753, 754]

# Slot 757: said after the title when the Factory Reset dialog opens. The F3 switches itself
# off after a reset, which is otherwise silent and confusing without sight. Uses the F3's
# own word for the Execute button in each language.
RESET_NOTE = {
 "EN": "After Execute, the F3 resets its settings and then switches itself off.",
 "FR": "Après Exécuter, le F3 rétablit ses réglages d'usine, puis s'éteint automatiquement.",
 "DE": "Nach Ausführen setzt der F3 seine Einstellungen zurück und schaltet sich dann selbst aus.",
 "IT": "Dopo Esegui, l'F3 ripristina le impostazioni di fabbrica e poi si spegne automaticamente.",
 "ES": "Después de Ejecutar, el F3 restablece los ajustes de fábrica y luego se apaga automáticamente.",
 "L5": "执行后，F3 将恢复出厂设置，然后自动关机。",
 "L6": "実行すると、F3 は初期設定に戻り、そのあと自動的に電源が切れます。",
}
RESET_NOTE_ID = 757

# Slots 800..830: the name editor (Rec File Name > User Defined Name). Order:
# 800 capital, 801 space, 802-804 the three character sets, 805 "character set" (the key
# that switches them), 806/807 cursor left/right, 808 end (cursor after the last
# character), 809 empty (no name yet), 810-829 the symbols _ - + = ! # ' , ; ( ) [ ] { } $ @ ^ ` ~
# in that order, 830 deleted. The engine puts "capital" after the letter in FR/IT/ES.
KEYBOARD = {
 "EN": ["capital","space","uppercase letters","lowercase letters","numbers and symbols","character set",
        "cursor left","cursor right","end","empty",
        "underscore","dash","plus","equals","exclamation mark","hash","apostrophe","comma","semicolon",
        "open parenthesis","close parenthesis","open bracket","close bracket","open brace","close brace",
        "dollar","at","caret","backtick","tilde","deleted"],
 "FR": ["majuscule","espace","lettres majuscules","lettres minuscules","chiffres et symboles","jeu de caractères",
        "curseur à gauche","curseur à droite","fin","vide",
        "tiret bas","tiret","plus","égal","point d'exclamation","dièse","apostrophe","virgule","point-virgule",
        "parenthèse ouvrante","parenthèse fermante","crochet ouvrant","crochet fermant","accolade ouvrante","accolade fermante",
        "dollar","arobase","accent circonflexe","accent grave","tilde","suppression"],
 "DE": ["großes","Leerzeichen","Großbuchstaben","Kleinbuchstaben","Ziffern und Symbole","Zeichensatz",
        "Cursor nach links","Cursor nach rechts","Ende","leer",
        "Unterstrich","Bindestrich","Plus","Gleich","Ausrufezeichen","Raute","Apostroph","Komma","Semikolon",
        "Klammer auf","Klammer zu","eckige Klammer auf","eckige Klammer zu","geschweifte Klammer auf","geschweifte Klammer zu",
        "Dollar","At-Zeichen","Zirkumflex","Gravis","Tilde","gelöscht"],
 "IT": ["maiuscola","spazio","lettere maiuscole","lettere minuscole","numeri e simboli","set di caratteri",
        "cursore a sinistra","cursore a destra","fine","vuoto",
        "trattino basso","trattino","più","uguale","punto esclamativo","cancelletto","apostrofo","virgola","punto e virgola",
        "parentesi tonda aperta","parentesi tonda chiusa","parentesi quadra aperta","parentesi quadra chiusa",
        "parentesi graffa aperta","parentesi graffa chiusa",
        "dollaro","chiocciola","accento circonflesso","accento grave","tilde","cancellazione"],
 "ES": ["mayúscula","espacio","letras mayúsculas","letras minúsculas","números y símbolos","juego de caracteres",
        "cursor a la izquierda","cursor a la derecha","fin","vacío",
        "guion bajo","guion","más","igual","signo de exclamación","almohadilla","apóstrofo","coma","punto y coma",
        "abrir paréntesis","cerrar paréntesis","abrir corchete","cerrar corchete","abrir llave","cerrar llave",
        "dólar","arroba","acento circunflejo","acento grave","virgulilla","borrado"],
 "L5": ["大写","空格","大写字母","小写字母","数字和符号","字符集",
        "光标左移","光标右移","末尾","空",
        "下划线","连字符","加号","等号","感叹号","井号","撇号","逗号","分号",
        "左圆括号","右圆括号","左方括号","右方括号","左花括号","右花括号",
        "美元符号","艾特符号","脱字符","反引号","波浪号","已删除"],
 "L6": ["おおもじ","スペース","おおもじ","こもじ","すうじと きごう","もじの しゅるい",
        "カーソル ひだり","カーソル みぎ","さいご","にゅうりょく なし",
        "アンダーバー","ハイフン","プラス","イコール","びっくりマーク","シャープ","アポストロフィ","カンマ","セミコロン",
        "まるかっこ ひらき","まるかっこ とじ","かくかっこ ひらき","かくかっこ とじ","なみかっこ ひらき","なみかっこ とじ",
        "ドル","アットマーク","キャレット","バッククォート","チルダ","さくじょ"],
}
KEYBOARD_SLOTS = list(range(800, 810)) + list(range(810, 830)) + [830]

# 831 "seconds" (playback: time left after fast-forward / rewind), 832 "next file" (the Stop
# status: the name the next recording will get)
STATUS2 = {
 "EN": ["seconds", "next file"],
 "FR": ["secondes", "prochain fichier"],
 "DE": ["Sekunden", "nächste Datei"],
 "IT": ["secondi", "prossimo file"],
 "ES": ["segundos", "próximo archivo"],
 "L5": ["秒", "下一个文件"],
 "L6": ["びょう", "つぎの ファイル"],
}
STATUS2_SLOTS = [831, 832]

# Units and technical words espeak would spell out ("k h z", "b i t"): replaced by the
# spoken word in each language before synthesis. Display text (and so the runtime-text
# lookup) is unchanged; only what the voice says differs.
UNIT_WORDS = {   #  kHz            Hz        bit      float                 dB            ms
 "EN": ["kilohertz", "hertz", "bit", "float", "decibels", "milliseconds"],
 "FR": ["kilohertz", "hertz", "bit", "virgule flottante", "décibels", "millisecondes"],
 "DE": ["Kilohertz", "Hertz", "Bit", "Gleitkomma", "Dezibel", "Millisekunden"],
 "IT": ["kilohertz", "hertz", "bit", "virgola mobile", "decibel", "millisecondi"],
 "ES": ["kilohercios", "hercios", "bits", "coma flotante", "decibelios", "milisegundos"],
 "L5": ["千赫", "赫兹", "位", "浮点", "分贝", "毫秒"],
 "L6": ["キロヘルツ", "ヘルツ", "ビット", "フロート", "デシベル", "ミリびょう"],
}
def prep_units(text, lang):
    import re
    kHz, Hz, bit, flt, dB, ms = UNIT_WORDS[lang]
    t = re.sub(r"(?<![A-Za-z])kHz(?![A-Za-z])", " " + kHz + " ", text)
    t = re.sub(r"(?<![A-Za-z])Hz(?![A-Za-z])", " " + Hz + " ", t)
    t = re.sub(r"(?<=\d)\s*-?\s*bit(?![A-Za-z])", " " + bit, t)
    t = re.sub(r"(?<![A-Za-z])[Ff]loat(?![A-Za-z])", " " + flt + " ", t)
    t = re.sub(r"(?<![A-Za-z])dBFS(?![A-Za-z])", " " + dB + " F S ", t)
    t = re.sub(r"(?<![A-Za-z])dB(?![A-Za-z])", " " + dB + " ", t)
    t = re.sub(r"(?<=\d)\s*ms(?![A-Za-z])", " " + ms + " ", t)
    return re.sub(r"\s+", " ", t).strip()

def _is_cjk(ch): return "\u3400" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff"
def _kana(text):
    """Japanese without latin letters: kanji -> hiragana (pykakasi), kana as is."""
    import pykakasi
    out = ""
    for tok in pykakasi.kakasi().convert(text):
        o = tok["orig"]
        out += tok["hira"] if any(_is_cjk(ch) for ch in o) else o
    return out

def plan_lang(text, lang):
    """Prepare text for espeak-ng -> list of (espeak voice, text) segments, spoken in order.
    Units become words (prep_units). Chinese: Han characters -> tone-numbered pinyin read by
    the pinyin voice, other runs (latin, digits) by the cmn voice. Japanese: espeak's ja
    voice spells every latin word letter by letter, so latin runs go to the English voice;
    kanji -> hiragana (pykakasi)."""
    import re
    voice = LANG_CFG[lang][1]
    text = prep_units(text, lang)
    if lang == "L6":
        segs = []
        for part in re.split(r"([A-Za-z][A-Za-z .,/&'+-]*[A-Za-z]|[A-Za-z])", text):
            if not part or not part.strip(" ,.:;()[]/-_"): continue
            if re.fullmatch(r"[A-Za-z][A-Za-z .,/&'+-]*", part): segs.append(("en", part))
            else: segs.append(("ja", _kana(part)))
        return segs
    if lang == "L5":
        from pypinyin import lazy_pinyin, Style
        runs = []; cur = ""; cj = None
        for ch in text:
            c = _is_cjk(ch)
            if cj is None or c == cj: cur += ch
            else: runs.append((cj, cur)); cur = ch
            cj = c
        if cur: runs.append((cj, cur))
        segs = []
        for c, r in runs:
            if c: segs.append(("cmn-latn-pinyin", " ".join(lazy_pinyin(r, style=Style.TONE3, neutral_tone_with_five=True))))
            elif r.strip(" ,.:;()[]/-_"): segs.append((voice, r))
        return segs
    return [(voice, text)]

def synth_lang(text, lang, rate, speed):
    pcm = []
    for v, t in plan_lang(text, lang): pcm += synth(t, v, rate, speed)
    return pcm

def fnv16(t):
    h=0x811C9DC5
    for ch in t.encode("utf-16-le"): h=((h ^ ch) * 0x01000193) & 0xFFFFFFFF
    return ((h >> 16) ^ h) & 0xFFFF or 1
def fnv32(t):
    h=0x811C9DC5
    for ch in t.encode("utf-16-le"): h=((h ^ ch) * 0x01000193) & 0xFFFFFFFF
    return h or 1

STRINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "F3_strings_all_langs.json")
def bank_plan(lang, strings=STRINGS):
    """Everything about a language's bank that does not depend on the voice settings:
    which slots exist, the unique clips with their espeak segments, the two hash tables and
    the header fields. Used by main() here and exported for the web patcher."""
    import re
    from spoken_overrides import SPOKEN, times_spoken
    tbl = json.load(open(strings, encoding="utf-8"))[lang]
    orig = dict(tbl)
    # Skip empty lines and runtime placeholders ("****", "xx:xx", "9999/99/99"): the firmware
    # fills those in on screen. Placeholder = only * x - : . / spaces and the dummy digits 0, 9.
    placeholder = lambda t: re.fullmatch(r"[\s*x\-:./09]*", t) is not None
    ids = sorted(int(k) for k in tbl if tbl[k] and not placeholder(tbl[k]) and int(k) < 590)
    L_IDX, voice, YEAR_STYLE = LANG_CFG[lang]
    # Extra phrases (590..799; the engine uses these slot numbers directly)
    EXTRA = dict(zip(WORD_SLOTS, WORDS[lang]))
    EXTRA.update({600 + n: str(n) for n in range(100)})            # numbers 0..99
    if lang == "L6": EXTRA[600] = "ゼロ"                          # tkna: zero as ゼロ, not れい
    EXTRA.update({700 + i: m for i, m in enumerate(MONTHS[lang].split())})   # months
    EXTRA[717] = "2000"                                            # "two thousand", natively
    EXTRA.update({720 + i: chr(65 + i) for i in range(26)})        # letters A..Z
    EXTRA.update({780 + k: str(100 * k) for k in range(1, 10)})    # 100..900 as whole words
    EXTRA.update({789 + k: str(1000 * k) for k in range(1, 10)})   # 1000..9000
    if lang == "L5": EXTRA[799] = "零"                             # linking zero (两千零五)
    EXTRA[CHIME_ID] = "\u266a startup chime"
    EXTRA[RESET_NOTE_ID] = RESET_NOTE[lang]
    EXTRA.update(dict(zip(KEYBOARD_SLOTS, KEYBOARD[lang])))
    EXTRA.update(dict(zip(STATUS2_SLOTS, STATUS2[lang])))
    for k, v in EXTRA.items(): tbl[str(k)] = v; ids.append(k)
    clips, keys, slots = [], {}, {}
    for sid in ids:
        text = tbl[str(sid)]
        slang = next((k for k, v in LANG_NAME_SID.items() if v == sid), lang)  # language names: own voice
        spoken = SPOKEN.get(slang, {}).get(sid, text)
        if spoken is None: continue                                  # silent line
        spoken = times_spoken(spoken, slang)
        key = "chime" if sid == CHIME_ID else (slang, spoken)
        if key not in keys:
            keys[key] = len(clips)
            clips.append({"chime": True} if sid == CHIME_ID else {"segs": plan_lang(spoken, slang)})
        slots[sid] = {"clip": keys[key], "text": text}
    nslots = CLIP_MAX_ID
    r0 = bytearray(nslots*2)              # u16 hash of each built-in UI string (runtime text?)
    for k, v in orig.items():
        if v and int(k) < nslots: struct.pack_into("<H", r0, int(k)*2, fnv16(v))
    r1 = bytearray(nslots*4)              # u32 hash of each clip's lower-cased text (lookup)
    for sid, e in slots.items(): struct.pack_into("<I", r1, sid*4, fnv32(e["text"].lower()))
    return {"lang": lang, "L": L_IDX, "year_style": YEAR_STYLE, "nslots": nslots,
            "clips": clips, "slots": slots, "r0": bytes(r0), "r1": bytes(r1)}

def assemble(plan, clip_data, rate=16000):
    """clip_data[i] = (encoded bytes, PCM sample count) for plan['clips'][i] -> bank blob."""
    nslots = plan["nslots"]; bank = bytearray(); offs = []
    for enc, ns in clip_data: offs.append((len(bank), ns)); bank += enc
    idxb = bytearray(nslots*8)
    for sid, e in plan["slots"].items(): struct.pack_into("<II", idxb, sid*8, *offs[e["clip"]])
    bank += b"\0" * ((-len(bank)) % 4)
    hash_off = HDR_BYTES + nslots*8 + len(bank); look_off = hash_off + nslots*2
    hdr = struct.pack("<IIIIIIII", MAGIC0, MAGIC1, rate, nslots, FMT_OPUS, hash_off, look_off,
                      plan["L"] | (plan["year_style"] << 8))
    return bytes(hdr) + bytes(idxb) + bytes(bank) + plan["r0"] + plan["r1"]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--strings",default=STRINGS)
    ap.add_argument("--lang",default="EN")
    ap.add_argument("--variant",default="michel",help="espeak-ng variant, '' for none")
    ap.add_argument("--pitch",type=int,default=50)
    ap.add_argument("--rate",type=int,default=16000)
    ap.add_argument("--speed",type=int,default=300)   # calmer than 480 -> clearer
    ap.add_argument("--out",default=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","build","flash_bank"))
    ap.add_argument("--kbps",type=int,default=16)
    ap.add_argument("--frame-ms",type=int,default=10)      # 10 or 20
    a=ap.parse_args()
    os.makedirs(a.out,exist_ok=True)
    global VARIANT, PITCH
    VARIANT, PITCH = a.variant, a.pitch
    if a.rate not in (8000, 16000, 24000): sys.exit("the bank rate must be 8000, 16000 or 24000")
    a.voice = LANG_CFG[a.lang][1]
    plan = bank_plan(a.lang, a.strings)
    data = []
    for i, c in enumerate(plan["clips"]):
        if c.get("chime"):
            pcm = chime_pcm(a.rate); data.append((opus_encode(pcm, 32, a.frame_ms, music=True, rate=a.rate), len(pcm)))
        else:
            pcm = []
            for v, t in c["segs"]: pcm += synth(t, v, a.rate, a.speed)
            data.append((opus_encode(pcm, a.kbps, a.frame_ms, rate=a.rate), len(pcm)))
        if (i+1) % 100 == 0: print("  %d/%d clips" % (i+1, len(plan["clips"])), flush=True)
    blob = assemble(plan, data, a.rate)
    open(f"{a.out}/flash_bank.bin","wb").write(blob)
    index = plan["slots"]; nslots = plan["nslots"]
    bank = blob
    json.dump({"codec":"opus","kbps":a.kbps,"frame_ms":a.frame_ms,"rate":a.rate,"voice":a.voice,
               "variant":a.variant,"pitch":a.pitch,"speed":a.speed,"nslots":nslots,"clips":len(index),
               "hdr_bytes":HDR_BYTES,"index_bytes":nslots*8,
               "blob_bytes":len(blob)}, open(f"{a.out}/report.json","w"),indent=1)
    with open(f"{a.out}/manifest.txt","w") as mf:
        mf.write(("FLASH bank  voice=%s+"+a.variant+" rate=%dHz opus "+str(a.kbps)+"k  clips=%d  blob=%d B (%.2f MB)\n\n")%(
            a.voice,a.rate,len(index),len(blob),len(blob)/1048576))
        for sid in sorted(index): mf.write("  %4d  %s\n"%(sid,index[sid]["text"]))
    print("\nflash_bank.bin = %d B (%.2f MB)  slots=%d  unique clips=%d"%(
        len(blob),len(blob)/1048576,len(index),len(plan["clips"])))

if __name__=="__main__": main()
