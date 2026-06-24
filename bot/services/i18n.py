from bot.locales import uz, ru, en, kk, tg, ky

_locales = {
    "uz": uz.texts,
    "ru": ru.texts,
    "en": en.texts,
    "kk": kk.texts,
    "tg": tg.texts,
    "ky": ky.texts,
}


def t(lang: str, key: str, **kwargs) -> str:
    texts = _locales.get(lang, uz.texts)
    template = texts.get(key, uz.texts.get(key, key))
    return template.format(**kwargs) if kwargs else template
