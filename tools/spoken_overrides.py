# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Casey Reeves <contact@xogium.me>
# SPDX-License-Identifier: MIT
"""What the voice says for strings the F3 leaves in English in every UI language
(popups, Input1/2, x N magnification...). The screen text (and the runtime-text hash) is
unchanged; only the spoken form differs. None = say nothing for that line (its meaning
is already in another line of the same popup). French wording avoids gendered forms where a
person could be meant. sid -> spoken text, per language key of F3_strings_all_langs.json."""

_POWER = (179, 182, 185, 188, 191, 194)

def _mk(d, power):
    for s in _POWER: d[s] = power
    return d

SPOKEN = {
 "EN": {325: "Input 1", 326: "Input 2"},
 "FR": _mk({30: "Mono", 169: "Impossible d'utiliser", 170: "cette fonction !", 178: "Pas de carte SD !",
   181: "Batterie faible !", 184: "Fichier de mise à jour non valide !", 187: "Aucun fichier de mise à jour !",
   190: "Erreur !", 193: "Opération réussie !", 241: "Tonalité activée", 242: "Tonalité désactivée",
   264: "Accès à la carte SD", 266: "Chargement en cours", 325: "Entrée 1", 326: "Entrée 2",
   330: "Carte protégée !", 377: "Démarrer", 378: "Continuer", 379: "Réessayer", 380: "Terminer",
   381: "Mode absolu", 382: "Mode relatif", 383: "Basses fréquences, mode absolu",
   384: "Basses fréquences, mode relatif", 393: "Minimum", 394: "Maximum", 424: "Linéaire",
   425: "Virgule flottante", 445: "Virgule flottante", 428: "Mixage mono",
   438: "Fréquence d'échantillonnage", 439: "de 88,2 kilohertz !", 441: "Ce fichier est en",
   442: "88,2 kilohertz et", 443: "ne peut pas être lu.", 444: "Normaliser",
   446: "Linéaire 24 bits", 447: "Linéaire 16 bits", 475: "Mise à jour du firmware",
   521: "secondes", 286: "Supprimer", 285: "Infos"}, "Veuillez éteindre l'appareil"),
 "DE": _mk({30: "Mono", 169: "Diese Funktion", 170: "ist nicht verfügbar!", 178: "Keine SD-Karte!",
   181: "Batterie schwach!", 184: "Ungültige Update-Datei!", 187: "Keine Update-Dateien!",
   190: "Fehler!", 193: "Fertig!", 241: "Ton an", 242: "Ton aus", 264: "SD-Kartenzugriff",
   266: "Wird geladen", 325: "Eingang 1", 326: "Eingang 2", 330: "Karte schreibgeschützt!",
   377: "Start", 378: "Weiter", 379: "Wiederholen", 380: "Beenden", 381: "Absolut", 382: "Relativ",
   383: "Tiefe Frequenzen, absolut", 384: "Tiefe Frequenzen, relativ", 393: "Minimum",
   394: "Maximum", 424: "Linear", 425: "Gleitkomma", 445: "Gleitkomma", 428: "Mono-Mix",
   438: "Abtastrate", 439: "ist 88,2 Kilohertz!", 441: "Diese Datei hat", 442: "88,2 Kilohertz und",
   443: "kann nicht abgespielt werden.", 444: "Normalisieren", 446: "Linear 24 Bit",
   447: "Linear 16 Bit", 475: "Firmware-Update", 521: "Sekunden", 286: "Löschen", 285: "Info"},
   "Bitte ausschalten"),
 "IT": _mk({30: "Mono", 169: "Impossibile usare", 170: "questa funzione!", 178: "Nessuna scheda SD!",
   181: "Batteria scarica!", 184: "File di aggiornamento non valido!",
   187: "Nessun file di aggiornamento!", 190: "Errore!", 193: "Completato!", 241: "Tono attivo",
   242: "Tono disattivato", 264: "Accesso alla scheda SD", 266: "Caricamento", 325: "Ingresso 1",
   326: "Ingresso 2", 330: "Scheda protetta!", 377: "Avvia", 378: "Avanti", 379: "Riprova",
   380: "Fine", 381: "Assoluto", 382: "Relativo", 383: "Basse frequenze, assoluto",
   384: "Basse frequenze, relativo", 393: "Minimo", 394: "Massimo", 424: "Lineare",
   425: "Virgola mobile", 445: "Virgola mobile", 428: "Mix mono",
   438: "Frequenza di campionamento", 439: "di 88,2 kilohertz!", 441: "Questo file è a",
   442: "88,2 kilohertz e", 443: "non può essere riprodotto.", 444: "Normalizza",
   446: "Lineare 24 bit", 447: "Lineare 16 bit", 475: "Aggiornamento firmware", 521: "secondi",
   286: "Elimina", 285: "Info"}, "Spegnere il dispositivo"),
 "ES": _mk({30: "Mono", 169: "No se puede usar", 170: "esta función.", 178: "No hay tarjeta SD.",
   181: "Batería baja.", 184: "Archivo de actualización no válido.",
   187: "No hay archivos de actualización.", 190: "Error.", 193: "Completado.",
   241: "Tono activado", 242: "Tono desactivado", 264: "Acceso a la tarjeta SD", 266: "Cargando",
   325: "Entrada 1", 326: "Entrada 2", 330: "Tarjeta protegida.", 377: "Iniciar", 378: "Siguiente",
   379: "Reintentar", 380: "Finalizar", 381: "Absoluto", 382: "Relativo",
   383: "Frecuencias bajas, absoluto", 384: "Frecuencias bajas, relativo", 393: "Mínimo",
   394: "Máximo", 424: "Lineal", 425: "Coma flotante", 445: "Coma flotante", 428: "Mezcla mono",
   438: "Frecuencia de muestreo", 439: "de 88,2 kilohercios.", 441: "Este archivo es de",
   442: "88,2 kilohercios y", 443: "no se puede reproducir.", 444: "Normalizar",
   446: "Lineal 24 bits", 447: "Lineal 16 bits", 475: "Actualización de firmware",
   521: "segundos", 286: "Eliminar", 285: "Información"}, "Apague el equipo"),
 "L5": _mk({30: "单声道", 169: "此功能", 170: "无法使用！", 178: "没有SD卡！", 181: "电量低！",
   184: "无效的更新文件！", 187: "没有更新文件！", 190: "错误！", 193: "完成！", 241: "提示音开",
   242: "提示音关", 264: "正在访问SD卡", 266: "正在加载", 325: "输入1", 326: "输入2",
   330: "卡已写保护！", 377: "开始", 378: "下一步", 379: "重试", 380: "完成", 381: "绝对",
   382: "相对", 383: "低频，绝对", 384: "低频，相对", 393: "最小", 394: "最大", 424: "线性",
   425: "浮点", 445: "浮点", 428: "单声道混音", 438: "采样率", 439: "为88.2千赫！",
   441: "此文件为", 442: "88.2千赫，", 443: "无法播放。", 444: "标准化", 446: "线性24位",
   447: "线性16位", 475: "固件更新", 521: "秒", 286: "删除", 285: "信息"}, "请关机"),
 "L6": _mk({30: "モノ", 169: "この機能は", 170: "使用できません！", 178: "SDカードがありません！",
   181: "電池残量が少なくなっています！", 184: "無効なアップデートファイルです！",
   187: "アップデートファイルがありません！", 190: "エラー！", 193: "完了！", 241: "トーン オン",
   242: "トーン オフ", 264: "SDカード アクセス中", 266: "読み込み中", 325: "入力1", 326: "入力2",
   330: "カードが保護されています！", 377: "開始", 378: "次へ", 379: "再試行", 380: "終了",
   381: "絶対", 382: "相対", 383: "低域 絶対", 384: "低域 相対", 393: "最小", 394: "最大",
   424: "リニア", 425: "フロート", 445: "フロート", 428: "モノミックス", 438: "サンプルレート",
   439: "88.2キロヘルツです！", 441: "このファイルは", 442: "88.2キロヘルツのため",
   443: "再生できません。", 444: "ノーマライズ", 446: "リニア 24ビット", 447: "リニア 16ビット",
   475: "ファームウェア アップデート", 521: "秒", 286: "削除", 285: "情報",
   # reviewed by tkna (2026-10-14): "I/F" said in full; "SD Card Full!" as one short sentence
   43: "USBオーディオインターフェース", 86: "オーディオインターフェースを終了",
   324: "オーディオインターフェース", 429: "オーディオインターフェース",
   426: "オーディオインターフェース リニア", 427: "オーディオインターフェース フロート",
   103: "SDカードがいっぱいです", 104: None, 105: None}, "電源を切ってください"),
}

def times_spoken(text, lang):
    """'× 8' magnification -> spoken per language (word order for ZH/JA: '8倍')."""
    import re
    if "×" not in text: return text
    if lang in ("L5", "L6"):
        return re.sub(r"×\s*(\d+)", r"\1倍", text)
    word = {"EN": "times", "FR": "fois", "DE": "mal", "IT": "per", "ES": "por"}[lang]
    return text.replace("×", " " + word + " ").strip()
