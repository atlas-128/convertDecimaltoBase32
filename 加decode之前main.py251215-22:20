from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
import uvicorn
from urllib.parse import urlparse, unquote

# --- 配置区域 ---
B32_FUZZY_CONFIG = {
    "url_mode": "host_plus_path",  
    "treat_domain_like_url": True,
    "url_joiner": "/",

    # 基础字符集分隔符，遇到这些会被当作无效字符忽略（除非被魔法替换处理了）
    "separators": set("-_/:@?=&%#"), 
    
    "keep_alnum_only": True,
    "uppercase_letters": True,

    # 字符形似字纠错（模糊匹配）
    "char_alias": {
        "O": "0", "o": "0",
        "I": "1", "i": "1",
        "L": "1", "l": "1",
        "Z": "2", "z": "2",
        "U": "u", "u": "u", # 本系统的特色：u 是 32进制的最后一位，必须小写
    },

    # --- 核心升级：魔法替换策略 (Magic Substitutions) ---
    # 使用列表(list)而不是字典(dict)，因为【顺序至关重要】！
    # 必须先执行 Q -> QQ 的转义，防止后续生成的 QX/QB 中的 Q 被错误再次转义。
    "magic_substitutions": [
        # 1. 第一步：先把原文中的 Q 转义为 QQ (不论大小写)
        ("Q", "QQ"),
        ("q", "QQ"),

        # 2. 第二步：将特殊符号替换为 Q 开头的标记
        (" ", "QX"),   # 空格 -> QX
        (".", "QJ"),   # 句号 -> QJ
        ("!", "QB"),   # 叹号 -> QB
        (",", "QC"),   # 逗号 -> QC
        ("?", "QK"),   # 问号 -> QK
        ("\n", "QN"),  # 换行 -> QN
        ("\r", ""),    # 回车 -> 忽略
    ],

    # 非法字符策略：跳过无法识别的字符
    "invalid_char_policy": "skip", 
    "return_normalized_on_fail": True,
}


app = FastAPI(title="News-to-Integer Magic Converter V2")


class PinCode32Service:
    def __init__(self, config: dict):
        self.config = config

        # 自定义字符集：0-9, A-Z (排除 I,L,O,U), 加上 u
        self.charset = "0123456789ABCDEFGHJKMNPQRSTuVWXY"
        self.base = 32
        
        # 构建解码映射表 (Char -> Int)
        self.decode_map = {char: idx for idx, char in enumerate(self.charset)}

        # 注入别名处理 (比如输入小写 a 映射到 A 的值)
        for ch, val in list(self.decode_map.items()):
            if ch.isalpha() and ch != "u":
                self.decode_map[ch.lower()] = val
        
        # 注入配置中的额外别名 (比如 o -> 0)
        alias = self.config.get("char_alias", {})
        for k, v in alias.items():
            if v in self.decode_map:
                self.decode_map[k] = self.decode_map[v]

    def encode(self, number: int) -> str:
        """
        [还原] 将十进制整数 还原回 Base32 字符串
        注意：这里还原出来的是带 QQ, QX 的中间态字符串，
        使用者看到 QX 需要自己理解为空格，看到 QQ 理解为字母 Q。
        """
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

    def apply_magic_substitutions(self, text: str) -> str:
        """
        [魔法层] 执行文本替换
        关键逻辑：按照配置列表的顺序，依次 replace。
        """
        subs = self.config.get("magic_substitutions", [])
        
        # 遍历配置列表 [('Q','QQ'), (' ','QX'), ...]
        for original, code in subs:
            if original in text:
                text = text.replace(original, code)
        return text

    def extract_payload(self, raw: str) -> str:
        """从 URL 提取核心文本"""
        s = (raw or "").strip()
        s = unquote(s) # URL 解码

        if not s:
            return ""

        # 简单的 URL 路径提取逻辑
        if "://" in s:
            try:
                # 截取 http://domain.com/ 之后的部分
                parts = s.split("://", 1)[1]
                if "/" in parts:
                    return parts.split("/", 1)[1]
            except Exception:
                pass
        return s

    def normalize_for_decode(self, raw: str) -> str:
        """
        [预处理流程]
        1. 提取 Payload
        2. 执行魔法替换 (Q->QQ, Space->QX)
        3. 过滤杂质，统一大小写
        """
        # 1. 提取
        payload = self.extract_payload(raw)
        if not payload:
            return ""

        # 2. 魔法替换 (这是转换成数字前的关键一步)
        # 输入: "Quit it"
        # 此时变为: "QQqu1tQX1t" (假设 i->1, u保持)
        payload = self.apply_magic_substitutions(payload)

        # 3. 标准化字符 (过滤掉不在 charset 里的符号)
        separators = self.config.get("separators", set())
        uppercase_letters = self.config.get("uppercase_letters", True)
        keep_alnum_only = self.config.get("keep_alnum_only", True)
        alias = self.config.get("char_alias", {})

        out = []
        for ch in payload:
            if ch in separators:
                continue

            # 处理大小写 (注意 u 特殊处理)
            if uppercase_letters and ("a" <= ch <= "z") and ch != 'u':
                ch = ch.upper()

            # 处理别名 (o->0 等)
            if ch in alias:
                ch = alias[ch]

            # 过滤非字母数字 (此时标点已经变成了 QX/QB 等字母，所以可以安全过滤)
            if keep_alnum_only and (not ch.isalnum()):
                continue

            out.append(ch)

        return "".join(out)

    def decode(self, b32_str: str) -> int:
        """[核心] Base32 字符串 转 十进制大整数"""
        policy = (self.config.get("invalid_char_policy", "error") or "error").lower()
        
        total = 0
        for ch in b32_str:
            if ch not in self.decode_map:
                if policy == "skip":
                    continue
                elif policy == "zero":
                    val = 0
                else:
                    raise ValueError(f"Invalid character: {ch}")
            else:
                val = self.decode_map[ch]
            
            total = total * self.base + val
        return total


service = PinCode32Service(B32_FUZZY_CONFIG)


@app.get("/", response_class=PlainTextResponse)
async def index():
    return (
        "Magic Base32 Converter V2 (With Q-Escape)\n"
        "-----------------------------------------\n"
        "Rules:\n"
        "1. Literal 'Q' or 'q' -> Becomes 'QQ'\n"
        "2. Space ' '          -> Becomes 'QX'\n"
        "3. Period '.'         -> Becomes 'QJ'\n\n"
        "Example:\n"
        "  Input:  /quit now\n"
        "  Logic:  q->QQ, ' '->QX\n"
        "  Code:   QQu1tQXn0w\n"
        "  Result: [Integer ID]\n"
    )


@app.get("/{input_val:path}", response_class=PlainTextResponse)
async def unified_converter(input_val: str):
    input_str = (input_val or "").strip()
    if not input_str:
        return "Empty input."

    # 如果输入全是数字 -> 认为是 ID -> 还原回 Base32 字符串
    if input_str.isdigit():
        try:
            return service.encode(int(input_str))
        except Exception as e:
            return f"Error: {e}"

    # 否则 -> 认为是文本/URL -> 转换为 ID
    else:
        # 去掉强制后缀
        raw_input = input_str
        if raw_input.lower().endswith("b32"):
            raw_input = raw_input[:-3]

        # 1. 预处理 (含 Q->QQ 转义)
        normalized = service.normalize_for_decode(raw_input)
        
        if not normalized:
            return "No valid payload."
            
        try:
            # 2. 转为整数
            decimal_val = service.decode(normalized)
            # 调试用：也可以返回 normalized 看看中间结果是否正确
            # return f"{normalized} \n{decimal_val}" 
            return str(decimal_val)
        except Exception as e:
            return f"Decode Error: {e}\nPayload: {normalized}"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)