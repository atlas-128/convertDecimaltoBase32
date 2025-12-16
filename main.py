from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
import uvicorn
from urllib.parse import urlparse, unquote
import re  # <---【新增】引入正则模块，用于精准还原

# --- 配置区域 ---
B32_FUZZY_CONFIG = {
    "url_mode": "host_plus_path",
    "treat_domain_like_url": True,
    "url_joiner": "/",
    "separators": set("-_/:@?=&%#"), 
    "keep_alnum_only": True,
    "uppercase_letters": True,

    "char_alias": {
        "O": "0", "o": "0",
        "I": "1", "i": "1",
        "L": "1", "l": "1",
        "Z": "2", "z": "2",
        "U": "u", "u": "u", 
    },

    # 魔法替换表 (注意顺序)
    "magic_substitutions": [
        ("Q", "QQ"),   # 必须最先处理
        ("q", "QQ"),   # 小写q也转义
        (" ", "QX"),   # 空格
        (".", "QJ"),   # 句号
        ("!", "QB"),   # 叹号
        (",", "QC"),   # 逗号
        ("?", "QK"),   # 问号
        ("\n", "QN"),  # 换行
    ],

    "invalid_char_policy": "skip", 
    "return_normalized_on_fail": True,
}


app = FastAPI(title="Magic Base32 Decoder System")


class PinCode32Service:
    def __init__(self, config: dict):
        self.config = config
        self.charset = "0123456789ABCDEFGHJKMNPQRSTuVWXY"
        self.base = 32
        
        self.decode_map = {char: idx for idx, char in enumerate(self.charset)}
        
        for ch, val in list(self.decode_map.items()):
            if ch.isalpha() and ch != "u":
                self.decode_map[ch.lower()] = val
        
        alias = self.config.get("char_alias", {})
        for k, v in alias.items():
            if v in self.decode_map:
                self.decode_map[k] = self.decode_map[v]

        # ---【预计算】构建反向魔法查找表 ---
        # 我们把 magic_substitutions 反过来： {'QX': ' ', 'QQ': 'Q', ...}
        # 注意：这里我们只取 value -> key 的映射，忽略小写 'q' 这种重复项，
        # 因为还原时只有大写代码。
        self.reverse_magic_map = {}
        # 为了防止冲突，我们需要按照 key 的长度降序排列（虽然这里都是2位，但为了健壮性）
        raw_subs = self.config.get("magic_substitutions", [])
        
        for original, code in raw_subs:
            # 建立 code -> original 的映射 (比如 QX -> 空格)
            # 注意：如果 original 是 'q'，code是 'QQ'，我们已经有 'Q'->'QQ'了，
            # 还原时 'QQ' 统一还原为 'Q' 即可，所以可以跳过小写覆盖。
            if code not in self.reverse_magic_map:
                self.reverse_magic_map[code] = original
            elif original == 'Q': # 强制优先保留大写Q的还原
                 self.reverse_magic_map[code] = original

        # 构建正则表达式模式：类似 (QQ|QX|QJ|QB)
        # re.escape 用于安全处理特殊字符
        if self.reverse_magic_map:
            pattern_str = '|'.join(map(re.escape, self.reverse_magic_map.keys()))
            self.reverse_magic_pattern = re.compile(pattern_str)
        else:
            self.reverse_magic_pattern = None

    def encode(self, number: int) -> str:
        """数值 -> Base32 (含转义符的中间态)"""
        if number < 0: return "ERROR"
        if number == 0: return "00"

        result = []
        while number > 0:
            number, remainder = divmod(number, self.base)
            result.append(self.charset[remainder])

        encoded = "".join(reversed(result))
        return encoded.zfill(2) if len(encoded) < 2 else encoded

    def apply_magic_substitutions(self, text: str) -> str:
        """【加密】自然语言 -> 带转义的Base32"""
        subs = self.config.get("magic_substitutions", [])
        for original, code in subs:
            if original in text:
                text = text.replace(original, code)
        return text

    def reverse_magic_substitutions(self, encoded_text: str) -> str:
        """
        【新增】【解密】带转义的Base32 -> 自然语言
        使用正则回调，精准还原 QX, QQ, QB 等
        """
        if not self.reverse_magic_pattern:
            return encoded_text

        # 回调函数：找到匹配项(match)，去字典里查对应的原字符
        def replace_callback(match):
            token = match.group(0)
            return self.reverse_magic_map.get(token, token)

        # 执行替换
        return self.reverse_magic_pattern.sub(replace_callback, encoded_text)

    def extract_payload(self, raw: str) -> str:
        s = (raw or "").strip()
        s = unquote(s)
        if not s: return ""
        if "://" in s:
            try:
                parts = s.split("://", 1)[1]
                if "/" in parts:
                    return parts.split("/", 1)[1]
            except Exception:
                pass
        return s

    def normalize_for_decode(self, raw: str) -> str:
        payload = self.extract_payload(raw)
        if not payload: return ""
        # 1. 加密转义 (Q->QQ, Space->QX)
        payload = self.apply_magic_substitutions(payload)
        
        separators = self.config.get("separators", set())
        uppercase_letters = self.config.get("uppercase_letters", True)
        keep_alnum_only = self.config.get("keep_alnum_only", True)
        alias = self.config.get("char_alias", {})

        out = []
        for ch in payload:
            if ch in separators: continue
            if uppercase_letters and ("a" <= ch <= "z") and ch != 'u':
                ch = ch.upper()
            if ch in alias: ch = alias[ch]
            if keep_alnum_only and (not ch.isalnum()): continue
            out.append(ch)
        return "".join(out)

    def decode(self, b32_str: str) -> int:
        """Base32 -> 数值"""
        policy = (self.config.get("invalid_char_policy", "error") or "error").lower()
        total = 0
        for ch in b32_str:
            if ch not in self.decode_map:
                if policy == "skip": continue
                elif policy == "zero": val = 0
                else: raise ValueError(f"Invalid character: {ch}")
            else:
                val = self.decode_map[ch]
            total = total * self.base + val
        return total


service = PinCode32Service(B32_FUZZY_CONFIG)


@app.get("/", response_class=PlainTextResponse)
async def index():
    return (
        "Magic Converter V3 (With Auto-Decode)\n"
        "-------------------------------------\n"
        "Usage:\n"
        "1. Encode Text (Get ID):\n"
        "   /http://site.com/I love mom!\n"
        "   -> [ID]\n\n"
        "2. Recover Raw Base32 (Get QX/QB code):\n"
        "   /[ID]\n"
        "   -> 1QX10VEQXM0MQB\n\n"
        "3. Fully Decode (Get Original Text):\n"
        "   /decode/[ID]\n"
        "   -> 1 10VE M0M!\n"
    )


@app.get("/{input_val:path}", response_class=PlainTextResponse)
async def unified_converter(input_val: str):
    input_str = (input_val or "").strip()
    if not input_str:
        return "Empty input."

    # --- 功能分支 1: 显式解密模式 (decode/...) ---
    # 检测用户是否想把数字直接变回可读文章
    if input_str.startswith("decode/"):
        # 去掉前缀，拿到后面的部分
        real_input = input_str[7:] # len("decode/") == 7
        
        # 只有当后面跟的是纯数字时，才有意义去还原
        if real_input.isdigit():
            try:
                # 步骤 A: 数值 -> Base32 (含转义符)
                # 结果如: "HE110QJH0W..."
                raw_b32 = service.encode(int(real_input))
                
                # 步骤 B: 逆向魔法还原
                # 结果如: "HE110.H0W..."
                final_text = service.reverse_magic_substitutions(raw_b32)
                
                return final_text
            except Exception as e:
                return f"Decode Error: {e}"
        else:
            return "Error: /decode/ must be followed by a number."

    # --- 功能分支 2: 默认转换模式 ---
    
    # 如果是纯数字 (且没有 decode 前缀)，还原为 Base32 (保留 QX, QB)
    if input_str.isdigit():
        try:
            return service.encode(int(input_str))
        except Exception as e:
            return f"Error: {e}"

    # 如果是文本/URL，转换为数字 ID
    else:
        raw_input = input_str
        if raw_input.lower().endswith("b32"):
            raw_input = raw_input[:-3]

        # 1. 清洗 + 魔法转义
        normalized = service.normalize_for_decode(raw_input)
        if not normalized:
            return "No valid payload."
            
        try:
            # 2. 计算数值
            decimal_val = service.decode(normalized)
            return str(decimal_val)
        except Exception as e:
            return f"Decode Error: {e}"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)