"""Pure script-detection helpers for Japanese text (no IO, no model calls)."""


def contains_japanese(value: str) -> bool:
    return any(
        "\u3040" <= character <= "\u30ff" or "\u3400" <= character <= "\u9fff"
        for character in value
    )


def contains_kanji(value: str) -> bool:
    return any("\u3400" <= character <= "\u9fff" for character in value)


def is_kana_only(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and all(
        "\u3040" <= character <= "\u30ff" or character in "〜・ 　"
        for character in stripped
    )


def is_japanese_name(value: str) -> bool:
    return contains_kanji(value)


def is_non_japanese_name(value: str) -> bool:
    name = value.replace("・", "").replace("-", "").replace(" ", "")
    return bool(name) and all(
        "\u30a0" <= character <= "\u30ff" or character.isascii() and character.isalpha()
        for character in name
    )
