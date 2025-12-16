from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
import uvicorn
from urllib.parse import urlparse


B32_FUZZY_CONFIG = {
    "url_mode": "host_plus_path",            # last_segment | host_plus_path | full
    "treat_domain_like_url": True,
    "url_joiner": "/",

    "separators": set("-_./:@?=&%#"),
    "keep_alnum_only": True,
    "uppercase_letters": True,

    "char_alias": {
        "O": "0", "o": "0",
        "I": "1", "i": "1",
        "L": "1", "l": "1",
        "Z": "2", "z": "2",
        "U": "u", "u": "u",
    },

    # 新增：非法字符处理策略
    # - "error": 遇到不在 charset 的字符就报错（但接口层会返回友好信息）
    # - "skip":  跳过非法字符（改变语义，谨慎）
    # - "zero":  非法字符替换为 '0'（改变语义，但更可控）
    "invalid_char_policy": "error",

    "return_normalized_on_fail": True,
}


app = FastAPI(title="Ultra-Fast Base32 Converter")


class PinCode32Service:
    def __init__(self, config: dict):
        self.config = config

        # 自定义字符集：注意这里用的是小写 'u'，不允许输出 'U'
        self.charset = "0123456789ABCDEFGHJKMNPQRSTuVWXY"
        self.base = 32
        self.allowed_set = set(self.charset)

        # decode_map（合法字符 -> 值）
        self.decode_map = {char: idx for idx, char in enumerate(self.charset)}

        # 小写输入支持（除 u 以外映射到对应大写值）
        for ch, val in list(self.decode_map.items()):
            if ch.isalpha() and ch != "u":
                self.decode_map[ch.lower()] = val

        # U 强制当 u
        self.decode_map["U"] = self.decode_map["u"]

    def encode(self, number: int) -> str:
        if number < 0:
            return "ERROR"
        if number == 0:
            return "00"

        result = []
        while number > 0:
            number, remainder = divmod(number, self.base)
            result.append(self.charset[remainder])

        encoded = "".join(reversed(result))
        return encoded.zfill(2) if len(encoded) < 2 else encoded

    def extract_payload(self, raw: str) -> str:
        s = (raw or "").strip()
        if not s:
            return ""

        if "://" in s:
            try:
                p = urlparse(s)
                host = (p.hostname or "").strip()
                path = (p.path or "").strip("/")
                query = (p.query or "").strip()
                frag = (p.fragment or "").strip()

                mode = self.config.get("url_mode", "last_segment")
                joiner = self.config.get("url_joiner", "/")

                if mode == "last_segment":
                    return path.split("/")[-1] if path else ""
                if mode == "host_plus_path":
                    if host and path:
                        return host + joiner + path
                    return host or path
                if mode == "full":
                    parts = []
                    if host:
                        parts.append(host)
                    if path:
                        parts.append(path)
                    if query:
                        parts.append(query)
                    if frag:
                        parts.append(frag)
                    return joiner.join(parts)

                return path.split("/")[-1] if path else ""
            except Exception:
                return s

        if self.config.get("treat_domain_like_url", True) and "/" in s:
            head = s.split("/")[0]
            if "." in head:
                host = head.strip()
                path = "/".join(s.split("/")[1:]).strip("/")
                mode = self.config.get("url_mode", "last_segment")
                joiner = self.config.get("url_joiner", "/")

                if mode == "last_segment":
                    return path.split("/")[-1] if path else ""
                if mode == "host_plus_path":
                    if host and path:
                        return host + joiner + path
                    return host or path
                if mode == "full":
                    if host and path:
                        return host + joiner + path
                    return host or path

                return path.split("/")[-1] if path else ""

        return s

    def normalize_for_decode(self, raw: str) -> str:
        payload = self.extract_payload(raw)
        if not payload:
            return ""

        alias = self.config.get("char_alias", {})
        separators = self.config.get("separators", set())
        uppercase_letters = self.config.get("uppercase_letters", True)
        keep_alnum_only = self.config.get("keep_alnum_only", True)

        out = []
        for ch in payload:
            if ch in separators:
                continue

            if uppercase_letters and ("a" <= ch <= "z"):
                ch = ch.upper()

            if ch in alias:
                ch = alias[ch]

            if keep_alnum_only and (not ch.isalnum()):
                continue

            out.append(ch)

        return "".join(out)

    def decode(self, b32_str: str) -> int:
        """
        支持 invalid_char_policy：
        - error:  遇到非法字符 raise ValueError
        - skip:   跳过非法字符
        - zero:   非法字符当作 '0'
        """
        policy = (self.config.get("invalid_char_policy", "error") or "error").lower()
        if policy not in ("error", "skip", "zero"):
            policy = "error"

        total = 0
        for ch in b32_str:
            if ch not in self.decode_map:
                if policy == "skip":
                    continue
                if policy == "zero":
                    ch = "0"
                else:
                    raise ValueError(f"Invalid character: {ch}")

            value = self.decode_map[ch]
            total = total * self.base + value
        return total


service = PinCode32Service(B32_FUZZY_CONFIG)


@app.get("/", response_class=PlainTextResponse)
async def index():
    return (
        "Ultra-Fast Base32 Converter\n"
        "Usage:\n"
        "  /123                 -> encode decimal to custom base32\n"
        "  /ABCD                -> decode (fuzzy) custom base32 to decimal\n"
        "  /ABCDb32             -> force decode (fuzzy)\n"
        "  /http://domain/path  -> decode using configured URL mode\n"
    )


@app.get("/{input_val:path}", response_class=PlainTextResponse)
async def unified_converter(input_val: str):
    input_str = (input_val or "").strip()
    if not input_str:
        return "Please provide input. Example: /123 or /ABCD or /http://domain/path"

    def friendly_decode(raw: str) -> str:
        normalized = service.normalize_for_decode(raw)
        if not normalized:
            return "No decodable payload found."
        try:
            return str(service.decode(normalized))
        except Exception:
            if B32_FUZZY_CONFIG.get("return_normalized_on_fail", True):
                return f"Could not decode. Normalized payload was: {normalized}"
            return "Could not decode."

    if input_str.lower().endswith("b32"):
        return friendly_decode(input_str[:-3])

    if not input_str.isdigit():
        return friendly_decode(input_str)

    try:
        return service.encode(int(input_str))
    except Exception:
        return "Invalid decimal input."


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
