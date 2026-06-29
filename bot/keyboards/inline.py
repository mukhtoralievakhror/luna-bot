from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from bot.services.i18n import t
from bot.config import MINIAPP_URL


def main_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_start")), KeyboardButton(text=t(lang, "btn_end"))],
            [KeyboardButton(text=t(lang, "btn_history"), web_app=WebAppInfo(url=MINIAPP_URL)), KeyboardButton(text=t(lang, "btn_symptoms"))],
            [KeyboardButton(text=t(lang, "btn_reminders")), KeyboardButton(text=t(lang, "btn_settings"))],
        ],
        resize_keyboard=True,
    )


def role_select_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_role_woman"), callback_data="setup_role:woman"),
        InlineKeyboardButton(text=t(lang, "btn_role_man"), callback_data="setup_role:partner"),
    ]])


def partner_main_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_reminders")), KeyboardButton(text=t(lang, "btn_settings"))],
        ],
        resize_keyboard=True,
    )


def lang_select() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="setup_lang:uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setup_lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="setup_lang:en"),
        ],
        [
            InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="setup_lang:kk"),
            InlineKeyboardButton(text="🇹🇯 Тоҷикӣ", callback_data="setup_lang:tg"),
            InlineKeyboardButton(text="🇰🇬 Кыргызча", callback_data="setup_lang:ky"),
        ],
    ])


def lang_change_select() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="change_lang:uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="change_lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="change_lang:en"),
        ],
        [
            InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="change_lang:kk"),
            InlineKeyboardButton(text="🇹🇯 Тоҷикӣ", callback_data="change_lang:tg"),
            InlineKeyboardButton(text="🇰🇬 Кыргызча", callback_data="change_lang:ky"),
        ],
    ])


def holat_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_oqim"), callback_data="holat:oqim"),
        InlineKeyboardButton(text=t(lang, "btn_daily_pain"), callback_data="holat:pain"),
    ]])


_PAIN_TYPES = ["cramp", "headache", "back", "chest"]
_PAIN_TYPE_KEYS = {
    "cramp": "pain_type_cramp",
    "headache": "pain_type_headache",
    "back": "pain_type_back",
    "chest": "pain_type_chest",
}


def pain_types_keyboard(lang: str, selected: list) -> InlineKeyboardMarkup:
    rows = []
    for pt in _PAIN_TYPES:
        mark = "✅ " if pt in selected else "⬜ "
        rows.append([InlineKeyboardButton(
            text=mark + t(lang, _PAIN_TYPE_KEYS[pt]),
            callback_data=f"ptype:{pt}",
        )])
    rows.append([
        InlineKeyboardButton(text=t(lang, "pain_type_none"), callback_data="ptype_none"),
        InlineKeyboardButton(text=t(lang, "pain_types_done"), callback_data="ptype_done"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pain_hour_keyboard(lang: str, current_hour: int) -> InlineKeyboardMarkup:
    hours = [18, 19, 20, 21, 22]
    buttons = [
        InlineKeyboardButton(
            text=f"{'✅ ' if h == current_hour else ''}{h}:00",
            callback_data=f"pain_hour:{h}",
        )
        for h in hours
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def flow_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "flow_light"), callback_data="flow:light"),
        InlineKeyboardButton(text=t(lang, "flow_medium"), callback_data="flow:medium"),
        InlineKeyboardButton(text=t(lang, "flow_heavy"), callback_data="flow:heavy"),
    ]])


def pain_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "pain_none"), callback_data="pain:0"),
        InlineKeyboardButton(text=t(lang, "pain_mild"), callback_data="pain:1"),
        InlineKeyboardButton(text=t(lang, "pain_moderate"), callback_data="pain:3"),
        InlineKeyboardButton(text=t(lang, "pain_severe"), callback_data="pain:5"),
    ]])


def mood_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "mood_happy"), callback_data="mood:happy"),
            InlineKeyboardButton(text=t(lang, "mood_sad"), callback_data="mood:sad"),
            InlineKeyboardButton(text=t(lang, "mood_irritable"), callback_data="mood:irritable"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "mood_tired"), callback_data="mood:tired"),
            InlineKeyboardButton(text=t(lang, "mood_normal"), callback_data="mood:normal"),
        ],
    ])


def reminder_keyboard(lang: str, enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = t(lang, "reminder_off") if enabled else t(lang, "reminder_on")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data="reminder:toggle")],
        [
            InlineKeyboardButton(text="1 kun", callback_data="reminder:days:1"),
            InlineKeyboardButton(text="2 kun", callback_data="reminder:days:2"),
            InlineKeyboardButton(text="3 kun", callback_data="reminder:days:3"),
        ],
    ])


def settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "settings_change_lang"), callback_data="settings:lang")],
        [InlineKeyboardButton(text=t(lang, "settings_partner"), callback_data="settings:partner")],
        [InlineKeyboardButton(text=t(lang, "settings_pain_time"), callback_data="settings:pain_time")],
        [InlineKeyboardButton(text=t(lang, "settings_reset"), callback_data="settings:reset")],
    ])


def partner_keyboard(lang: str, has_partner: bool) -> InlineKeyboardMarkup:
    rows = []
    if not has_partner:
        rows.append([InlineKeyboardButton(text=t(lang, "partner_btn_generate"), callback_data="settings:partner:generate")])
    else:
        rows.append([InlineKeyboardButton(text=t(lang, "partner_btn_disconnect"), callback_data="settings:partner:disconnect")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def partner_confirm_keyboard(lang: str, code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "partner_confirm_yes"), callback_data=f"partner:confirm:{code}"),
        InlineKeyboardButton(text=t(lang, "partner_confirm_no"), callback_data=f"partner:reject:{code}"),
    ]])


def reset_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "reset_yes"), callback_data="reset:yes"),
        InlineKeyboardButton(text=t(lang, "reset_no"), callback_data="reset:no"),
    ]])
