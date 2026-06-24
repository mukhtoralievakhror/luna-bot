from bot.locales import uz, ru, en

_locales = {"uz": uz.texts, "ru": ru.texts, "en": en.texts}


def t(lang: str, key: str, **kwargs) -> str:
    texts = _locales.get(lang, uz.texts)
    template = texts.get(key, uz.texts.get(key, key))
    return template.format(**kwargs) if kwargs else template
