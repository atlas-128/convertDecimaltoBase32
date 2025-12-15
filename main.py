from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
import uvicorn

app = FastAPI(title="Ultra-Fast Base32 Converter")

class PinCode32Service:
    def __init__(self):
        # 自定义字符集：注意这里用的是小写 'u'，不允许输出 'U'
        self.charset = "0123456789ABCDEFGHJKMNPQRSTuVWXY"
        self.base = 32

        # 预计算解码字典（以 charset 为准）
        self.decode_map = {char: idx for idx, char in enumerate(self.charset)}

        # 工程增强：允许用户输入小写字母（a-z），等价于大写（A-Z）
        # 但 U 是特殊：强制映射为 'u'
        # 下面这段保证 decode_map 对用户更友好，即便未来规范化漏掉也不容易炸
        for ch, val in list(self.decode_map.items()):
            if ch.isalpha() and ch != "u":
                # 例如 'A' -> 支持 'a'
                self.decode_map[ch.lower()] = val

        # 特殊：支持用户输入 'U'，并强制当作 'u'
        self.decode_map["U"] = self.decode_map["u"]

    def encode(self, number: int) -> str:
        """
        十进制 -> 自定义 32 进制
        特性：不足2位自动补零 (0 -> 00, 1 -> 01, 10 -> 0A)
        输出规范：除 'u' 外字母均为大写（由 charset 决定）
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
        if len(encoded) < 2:
            encoded = encoded.zfill(2)
        return encoded

    def normalize_b32_input(self, s: str) -> str:
        """
        输入规范化（只用于“解码路径”）：
        - a-z 视为 A-Z
        - U/u 强制变成 'u'
        - 其它字符（数字等）保持不变
        """
        out = []
        for c in s:
            if c == "U" or c == "u":
                out.append("u")
            elif "a" <= c <= "z":
                out.append(c.upper())
            else:
                out.append(c)
        return "".join(out)

    def decode(self, b32_str: str) -> int:
        """
        自定义 32进制 -> 十进制
        """
        total = 0
        for char in b32_str:
            if char not in self.decode_map:
                raise ValueError(f"Invalid character: {char}")
            value = self.decode_map[char]
            total = total * self.base + value
        return total


service = PinCode32Service()

@app.get("/{input_val}", response_class=PlainTextResponse)
async def unified_converter(input_val: str):
    """
    统一接口：
    - 末尾 b32（大小写不敏感）=> 强制按 base32 解码到十进制
    - 非纯数字 => 按 base32 解码到十进制（支持用户乱输大小写；U 强制当 u）
    - 纯数字 => 按十进制编码为 base32（输出遵循 charset：u 小写，其它大写）
    """
    input_str = input_val.strip()

    try:
        # 逻辑 1: 显式后缀 b32（大小写不敏感） -> 强制 32转10
        if input_str.lower().endswith("b32"):
            clean_str = input_str[:-3]  # 去掉 b32
            clean_str = service.normalize_b32_input(clean_str)
            return str(service.decode(clean_str))

        # 逻辑 2: 包含非数字字符 -> 自动判断为 32转10
        # 在解码前做规范化：a->A，U->u
        if not input_str.isdigit():
            normalized = service.normalize_b32_input(input_str)
            return str(service.decode(normalized))

        # 逻辑 3: 纯数字 -> 默认为 10转32
        number = int(input_str)
        return service.encode(number)

    except ValueError:
        return "ERROR: Invalid Input"
    except Exception as e:
        return f"ERROR: {str(e)}"


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
