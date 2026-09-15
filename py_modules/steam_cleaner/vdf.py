import re
import struct


MAX_BYTES = 8 * 1024 * 1024


def read_text(path):
    with open(path, "rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("oversized_vdf")
    text = raw.decode("utf-8-sig")
    tokens = []
    position = 0
    pattern = re.compile(r'\s+|//[^\n]*|"((?:\\.|[^"\\])*)"|([{}])|([^\s{}"]+)')
    for match in pattern.finditer(text):
        if match.start() != position:
            raise ValueError("malformed_vdf")
        position = match.end()
        if match.group(1) is not None:
            tokens.append(re.sub(r'\\([\\"])', r'\1', match.group(1)))
        elif match.group(2) or match.group(3):
            tokens.append(match.group(2) or match.group(3))
    if position != len(text):
        raise ValueError("malformed_vdf")
    cursor = 0

    def object_value(depth=0, nested=False):
        nonlocal cursor
        if depth > 32:
            raise ValueError("malformed_vdf")
        result = {}
        while cursor < len(tokens):
            key = tokens[cursor]
            cursor += 1
            if key == "}":
                if nested:
                    return result
                raise ValueError("malformed_vdf")
            if key == "{" or cursor == len(tokens):
                raise ValueError("malformed_vdf")
            value = tokens[cursor]
            cursor += 1
            if value == "{":
                value = object_value(depth + 1, True)
            elif value == "}":
                raise ValueError("malformed_vdf")
            if key.lower() in result:
                raise ValueError("duplicate_vdf_key")
            result[key.lower()] = value
        if nested:
            raise ValueError("malformed_vdf")
        return result

    return object_value()


def read_shortcuts(path):
    with open(path, "rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("oversized_vdf")
    cursor = 0

    def string():
        nonlocal cursor
        end = raw.index(b"\0", cursor)
        result = raw[cursor:end].decode("utf-8")
        cursor = end + 1
        return result

    def object_value(depth=0):
        nonlocal cursor
        if depth > 32:
            raise ValueError("malformed_vdf")
        result = {}
        while cursor < len(raw):
            kind = raw[cursor]
            cursor += 1
            if kind == 8:
                return result
            key = string().lower()
            if kind == 0:
                value = object_value(depth + 1)
            elif kind == 1:
                value = string()
            elif kind in (2, 3, 4, 6, 7, 10):
                length = 8 if kind in (7, 10) else 4
                value = int.from_bytes(raw[cursor:cursor + length], "little")
                if cursor + length > len(raw):
                    raise ValueError("malformed_vdf")
                cursor += length
            else:
                raise ValueError("malformed_vdf")
            if key in result:
                raise ValueError("duplicate_vdf_key")
            result[key] = value
        raise ValueError("malformed_vdf")

    try:
        result = object_value()
    except (IndexError, UnicodeError, struct.error) as error:
        raise ValueError("malformed_vdf") from error
    if raw[cursor:].strip(b"\x08"):
        raise ValueError("malformed_vdf")
    return result.get("shortcuts", {})
