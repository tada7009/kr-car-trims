"""폭스바겐코리아 모델 페이지의 가격표 PDF → data/volkswagen/*.json

가격표의 'Price | 주요 기본 사양' 쪽은 트림마다 [트림 이름, 권장소비자 가격, ・분류 : 품목, 품목…] 순서이고,
상위 트림은 '▶ (하위 트림) 기본 사양 및'으로 시작해 추가 품목만 적는다(하위 트림 품목을 이어받는다).
"""
import re

import fitz  # PyMuPDF

from common import DATA, curl_get, save

BASE = "https://www.volkswagen.co.kr"
MODELS = {  # 모델 페이지 → (모델 이름, 차급)
    "golf": ("Golf", "해치백"), "golf_gti": ("Golf GTI", "해치백"), "atlas": ("Atlas", "SUV"),
    "touareg": ("Touareg", "SUV"), "id4": ("ID.4", "전기 SUV"), "id5": ("ID.5", "전기 SUV"),
}
PRICE = re.compile(r"^\d{2,3},\d{3},\d{3}$")


def split_items(s):
    """쉼표로 나누되 괄호 안 쉼표는 그대로 둔다."""
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += ch in "(（"
        depth -= ch in ")）"
        if ch == "," and depth <= 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return [x.strip(" /") for x in out if x.strip(" /")]


def parse(pdf):
    doc = fitz.open(stream=pdf, filetype="pdf")
    text = next((p.get_text() for p in doc if "주요 기본 사양" in p.get_text()), "")
    lines = [l.rstrip() for l in text.split("\n")]
    if "주요 기본 사양" in lines:
        lines = lines[lines.index("주요 기본 사양") + 1:]
    trims, buf, cur, bullet = [], [], None, None

    def flush():
        nonlocal bullet
        if cur is not None and bullet:
            cat, body = bullet
            items = cur["cats"].setdefault(cat, [])
            for it in split_items(body):
                if it not in items:
                    items.append(it)
        bullet = None

    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith("(단위") or s in ("Seat", "Deco"):
            flush()
            break
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        # 가격 다음 줄이 '(권장소비자 가격)'이거나(내연기관) 바로 사양 글머리(전기차, 개소세 줄 없음)면 트림 시작
        if PRICE.match(s) and ("권장소비자" in nxt or nxt.startswith(("・", "•", "▶"))) and (cur is None or bullet is None or buf):
            flush()
            name = []
            for b in reversed(buf):  # 가격 바로 위의 쉼표 없는 한두 줄이 트림 이름
                if "," in b or len(name) == 3:
                    break
                name.insert(0, b)
            cur = {"name": " ".join(name).strip(), "price": int(s.replace(",", "")), "cats": {}}
            trims.append(cur)
            buf = []
            continue
        if PRICE.match(s) or s.startswith("(") and "가격" in s:
            continue
        if s.startswith("▶") and cur is not None:  # 하위 트림 기본 사양 이어받기
            base = trims[-2] if len(trims) >= 2 else None
            if base:
                cur["cats"] = {k: list(v) for k, v in base["cats"].items()}
            continue
        m = re.match(r"^[・•·]\s*([^:：]+?)\s*[:：]\s*(.*)$", s)
        if m and cur is not None:
            flush()
            bullet = (m.group(1).strip(), m.group(2))
            continue
        if bullet and cur is not None and s and (l.startswith(" ") or not re.match(r"^(The |[A-Z])", s)):
            bullet = (bullet[0], bullet[1] + " " + s)
            continue
        if s:
            flush()
            buf.append(s)
            buf = buf[-3:]  # 트림 이름은 가격 바로 위 한두 줄
    flush()
    for t in trims:
        t["name"] = re.sub(r"^(The\s+)?", "", t["name"]).strip()
    return trims


def main():
    out = DATA / "volkswagen"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    for key, (name, seg) in MODELS.items():
        page = f"{BASE}/ko/models/{key}.html"
        html = curl_get(page)
        m = re.search(r'(/idhub/content/dam/[^"\']+?Price[^"\']*?\.pdf)', html)
        if not m:
            print(key, "가격표 없음")
            continue
        url = BASE + m.group(1)
        trims = parse(curl_get(url, binary=True))
        if not trims:
            print(key, "트림 없음")
            continue
        date = re.search(r"_(\d{2})(\d{2})(\d{2})", m.group(1))
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        d = {"id": f"volkswagen-{slug}", "brand": "volkswagen", "name": name, "segment": seg, "image": "",
             "lowPrice": min(t["price"] for t in trims),
             "priceDate": f"20{date.group(1)}-{date.group(2)}-{date.group(3)}" if date else None,
             "sources": [page, url], "structure": "price-list",
             "variants": [{"name": "기본", "code": key, "trims": [
                 {"name": t["name"], "price": t["price"], "cats": [{"cat": c, "items": [{"n": x} for x in its]} for c, its in t["cats"].items()],
                  "adds": [], "opts": []} for t in sorted(trims, key=lambda t: t["price"])]}],
             "notes": ["폭스바겐코리아 공식 가격표(권장소비자가격)의 주요 기본 사양입니다."]}
        save(out / f"{slug}.json", d)
        print(d["id"], [(t["name"], t["price"], sum(len(v) for v in t["cats"].values())) for t in trims])


if __name__ == "__main__":
    main()
