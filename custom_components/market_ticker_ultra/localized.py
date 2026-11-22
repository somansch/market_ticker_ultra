"""What the integration says in its own words, by language.

Written by tools/i18n/i18n_build.js - not by hand. English and German come
from tools/i18n/src/extra.*.json, the others from tools/i18n/out.

These are the texts no translation file reaches: a price alert's default
words, sent by the integration itself, and the names of what a new
installation starts with. They follow Home Assistant's own language.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

TEXTS: dict[str, dict[str, Any]] = {
    "en": {
        "alert_title": "Price alert",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Price alert. {name} is at {price}, {direction} {limit}.",
        "direction_below": "at or below",
        "direction_above": "at or above",
        "settings": "Settings",
        "portfolio": "Portfolio",
        "watchlist": "Watchlist",
        "decimal_comma": False,
    },
    "de": {
        "alert_title": "Kursalarm",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Kursalarm. {name} steht bei {price}, {direction} {limit}.",
        "direction_below": "auf oder unter",
        "direction_above": "auf oder über",
        "settings": "Einstellungen",
        "portfolio": "Depot",
        "watchlist": "Watchlist",
        "decimal_comma": True,
    },
    "cs": {
        "alert_title": "Cenový alarm",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Cenový alarm. {name} je na {price}, {direction} {limit}.",
        "direction_below": "na nebo pod",
        "direction_above": "na nebo nad",
        "settings": "Nastavení",
        "portfolio": "Portfolio",
        "watchlist": "Watchlist",
        "decimal_comma": True,
    },
    "da": {
        "alert_title": "Kursalarm",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Kursalarm. {name} står i {price}, {direction} {limit}.",
        "direction_below": "på eller under",
        "direction_above": "på eller over",
        "settings": "Indstillinger",
        "portfolio": "Portefølje",
        "watchlist": "Watchlist",
        "decimal_comma": True,
    },
    "es": {
        "alert_title": "Alerta de precio",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Alerta de precio. {name} está en {price}, {direction} {limit}.",
        "direction_below": "igual o por debajo de",
        "direction_above": "igual o por encima de",
        "settings": "Configuración",
        "portfolio": "Cartera",
        "watchlist": "Lista de seguimiento",
        "decimal_comma": True,
    },
    "fi": {
        "alert_title": "Hintahälytys",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Hintahälytys. {name}: kurssi on {price}, {direction} {limit}.",
        "direction_below": "enintään",
        "direction_above": "vähintään",
        "settings": "Asetukset",
        "portfolio": "Salkku",
        "watchlist": "Seurantalista",
        "decimal_comma": True,
    },
    "fr": {
        "alert_title": "Alerte de cours",
        "alert_message": "{name} : {price} - {direction} {limit}",
        "alert_spoken": "Alerte de cours. {name} est à {price}, {direction} {limit}.",
        "direction_below": "égal ou inférieur à",
        "direction_above": "égal ou supérieur à",
        "settings": "Paramètres",
        "portfolio": "Portefeuille",
        "watchlist": "Liste de suivi",
        "decimal_comma": True,
    },
    "it": {
        "alert_title": "Avviso di prezzo",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Avviso di prezzo. {name} è a {price}, {direction} {limit}.",
        "direction_below": "pari o inferiore a",
        "direction_above": "pari o superiore a",
        "settings": "Impostazioni",
        "portfolio": "Portafoglio",
        "watchlist": "Watchlist",
        "decimal_comma": True,
    },
    "ja": {
        "alert_title": "価格アラート",
        "alert_message": "{name}: {price} - {limit} {direction}",
        "alert_spoken": "価格アラート。{name} は {price} で、{limit} {direction}です。",
        "direction_below": "以下",
        "direction_above": "以上",
        "settings": "設定",
        "portfolio": "ポートフォリオ",
        "watchlist": "ウォッチリスト",
        "decimal_comma": False,
    },
    "lt": {
        "alert_title": "Kainos įspėjimas",
        "alert_message": "{name}: {price} – {direction} {limit}",
        "alert_spoken": "Kainos įspėjimas. {name} kaina {price}, {direction} {limit}.",
        "direction_below": "ties arba žemiau",
        "direction_above": "ties arba aukščiau",
        "settings": "Nustatymai",
        "portfolio": "Portfelis",
        "watchlist": "Stebimų sąrašas",
        "decimal_comma": True,
    },
    "nb": {
        "alert_title": "Kursvarsel",
        "alert_message": "{name}: {price} – {direction} {limit}",
        "alert_spoken": "Kursvarsel. {name} står i {price}, {direction} {limit}.",
        "direction_below": "på eller under",
        "direction_above": "på eller over",
        "settings": "Innstillinger",
        "portfolio": "Portefølje",
        "watchlist": "Favorittliste",
        "decimal_comma": True,
    },
    "nl": {
        "alert_title": "Koersalarm",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Koersalarm. {name} staat op {price}, {direction} {limit}.",
        "direction_below": "op of onder",
        "direction_above": "op of boven",
        "settings": "Instellingen",
        "portfolio": "Portefeuille",
        "watchlist": "Watchlist",
        "decimal_comma": True,
    },
    "pl": {
        "alert_title": "Alert cenowy",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Alert cenowy. {name}: cena {price}, {direction} {limit}.",
        "direction_below": "na poziomie lub poniżej",
        "direction_above": "na poziomie lub powyżej",
        "settings": "Ustawienia",
        "portfolio": "Portfel",
        "watchlist": "Lista obserwowanych",
        "decimal_comma": True,
    },
    "pt-BR": {
        "alert_title": "Alerta de preço",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Alerta de preço. {name} está em {price}, {direction} {limit}.",
        "direction_below": "igual ou abaixo de",
        "direction_above": "igual ou acima de",
        "settings": "Configurações",
        "portfolio": "Carteira",
        "watchlist": "Watchlist",
        "decimal_comma": True,
    },
    "ru": {
        "alert_title": "Ценовое оповещение",
        "alert_message": "{name}: {price} — {direction} {limit}",
        "alert_spoken": "Ценовое оповещение. {name} стоит {price}, {direction} {limit}.",
        "direction_below": "на уровне или ниже",
        "direction_above": "на уровне или выше",
        "settings": "Настройки",
        "portfolio": "Портфель",
        "watchlist": "Список наблюдения",
        "decimal_comma": True,
    },
    "sk": {
        "alert_title": "Cenové upozornenie",
        "alert_message": "{name}: {price} – {direction} {limit}",
        "alert_spoken": "Cenové upozornenie. {name} je na {price}, {direction} {limit}.",
        "direction_below": "na alebo pod",
        "direction_above": "na alebo nad",
        "settings": "Nastavenia",
        "portfolio": "Portfólio",
        "watchlist": "Zoznam sledovaných",
        "decimal_comma": True,
    },
    "sv": {
        "alert_title": "Kurslarm",
        "alert_message": "{name}: {price} - {direction} {limit}",
        "alert_spoken": "Kurslarm. {name} ligger på {price}, {direction} {limit}.",
        "direction_below": "på eller under",
        "direction_above": "på eller över",
        "settings": "Inställningar",
        "portfolio": "Portfölj",
        "watchlist": "Bevakningslista",
        "decimal_comma": True,
    },
    "tr": {
        "alert_title": "Fiyat alarmı",
        "alert_message": "{name}: {price} - {limit} {direction}",
        "alert_spoken": "Fiyat alarmı. {name} {price} fiyatında, {limit} {direction}.",
        "direction_below": "seviyesinde veya altında",
        "direction_above": "seviyesinde veya üstünde",
        "settings": "Ayarlar",
        "portfolio": "Portföy",
        "watchlist": "İzleme listesi",
        "decimal_comma": True,
    },
    "zh-Hans": {
        "alert_title": "价格提醒",
        "alert_message": "{name}：{price} - {direction} {limit}",
        "alert_spoken": "价格提醒。{name} 现价 {price}，{direction} {limit}。",
        "direction_below": "等于或低于",
        "direction_above": "等于或高于",
        "settings": "设置",
        "portfolio": "投资组合",
        "watchlist": "自选列表",
        "decimal_comma": False,
    },
}

# A language Home Assistant names otherwise than the table does.
_ALIASES = {"pt": "pt-BR", "zh": "zh-Hans", "no": "nb", "nn": "nb"}


def language_of(hass: HomeAssistant) -> str:
    """The table's language for Home Assistant's own - English where it has
    none."""
    wanted = (hass.config.language or "en").replace("_", "-")
    if wanted in TEXTS:
        return wanted
    short = wanted.split("-")[0].lower()
    if short in TEXTS:
        return short
    return _ALIASES.get(short, "en") if _ALIASES.get(short) in TEXTS else "en"


def text(hass: HomeAssistant, key: str) -> str:
    return str(TEXTS[language_of(hass)].get(key) or TEXTS["en"][key])


def decimal_comma(hass: HomeAssistant) -> bool:
    """Whether the language writes 1,5 for one and a half."""
    return bool(TEXTS[language_of(hass)].get("decimal_comma"))
