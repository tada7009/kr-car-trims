"""지프 코리아 공식 홈페이지 → data/jeep/*.json (+ img/jeep-*.webp)

- 트림·가격·사양: 차종별 '제원 • 사양' 페이지(jeep.co.kr/…/specs.html)에 iframe으로 걸린 비교표(jeepdealer.co.kr/_common/…)
  표 머리에 [트림 이름, (하드탑/파워탑), ￦가격]이 있고, 아래 표는 행마다 [항목, 트림별 값]이다.
  값이 O/X인 행은 사양 유무, 그 밖의 행은 제원 값이다. '하드탑: O 파워탑: X'처럼 지붕별로 다른 칸은 나눠 넣는다.
- 한정판: 에디션 페이지 iframe(차량 가격·기본 제원·에디션 하이라이트)과 홈페이지 모델 메뉴의 시작가
- 사진: 공식 홈페이지 사진(배경 있음)·에디션 페이지의 배경 투명 렌더
가격 날짜가 페이지에 없어서 priceDate는 수집일로 둔다.
"""
import html as H
import json
import re
import sys

from common import DATA, curl_get, save
from fetch_import_media import cut_from, load, photo_set
from fetch_import_media import save as save_img

BASE = "https://www.jeep.co.kr"
DAM = BASE + "/content/dam/cross-regional/"
PRICE_DATE = "2026-11-11"
TOP = {"Hard Top": "하드탑", "Power Top": "파워탑"}

MODELS = [
    {"slug": "wrangler", "name": "Wrangler", "segment": "SUV", "spec": "/2026/wrangler/specs.html",
     "fallback": "https://jeepdealer.co.kr/_common/wrangler/specs/index_wrangler_2026.html",
     "editions": [
         {"name": "Tuscadero Edition", "page": "/2026/wrangler/edition.html", "nav": "TUSCADERO EDITION"},
         {"name": "85th Anniversary Edition", "page": None, "nav": "WRANGLER<br>85<sup>th</sup> ANNIVERSARY EDITION"},
     ],
     "photos": ["global/jeep/2026/wrangler/overview/desktop/my26-jeep-wrangler-overview-gallery-expanded-02-desktop.jpg",
                "global/jeep/2026/wrangler/design/desktop/my26-jeep-wrangler-design-gallery-01-expanded-modal-v2-desktop.jpg"],
     "cut": None,
     "int": ["global/jeep/2026/wrangler/overview/desktop/my26-jeep-wrangler-overview-gallery-expanded-03-desktop.jpg",
             "global/jeep/2026/wrangler/gallery/desktop/my26-wrangler-gallery-expanded-interior-image-5-desktop.jpg"]},
    {"slug": "gladiator", "name": "Gladiator", "segment": "픽업", "spec": "/gladiator/specs.html",
     "fallback": "https://jeepdealer.co.kr/_common/gladiator/specs/index2.html",
     "editions": [{"name": "85th Anniversary Edition", "page": "/gladiator/edition.html", "nav": "GLADIATOR<br>85<sup>th</sup> ANNIVERSARY EDITION"}],
     "photos": ["apac/jeep/ko_kr/2025/Design/PC/JT_design_view_pc_250401.png"],
     # 85주년 에디션 페이지의 배경 투명 렌더(국내 공식)
     "cut": "https://jeepdealer.co.kr/_common/gladiatorEditions/img/carimg1_jt.png",
     "int": ["apac/jeep/ko_kr/2025/Design/PC/JT_design_interior_pc_250414.png"]},
    {"slug": "grand-cherokee-l", "name": "Grand Cherokee L", "segment": "SUV", "spec": "/grand-cherokee-l/specs.html",
     "fallback": "https://jeepdealer.co.kr/_common/grand_cherokee_l/specs/index_2026.html",
     "editions": [],
     # 대체 문구에 'Grand Cherokee L'이 적힌 사진만 쓴다(디자인 첫 화면 = 갤러리 10번과 같은 장면)
     "photos": ["apac/jeep/ko_kr/2026/grand-cherokee/design/desktop/my26-jeep-grand-cherokee-design-hero-main-v2-desktop.jpg",
                "apac/jeep/ko_kr/2026/grand-cherokee/gallery/desktop/my26-grandcherokee-gallery-11-desktop.jpg"],
     "cut": None,
     "int": ["apac/jeep/ko_kr/2026/grand-cherokee/gallery/desktop/my26-grandcherokee-gallery-03-v3-desktop.jpg",
             "apac/jeep/ko_kr/2026/grand-cherokee/design/desktop/my26-jeep-grand-cherokee-design-sticky-container-seats-up-v3-desktop.jpg"]},
]


def text(s):
    s = re.sub(r"<br\s*/?>", " ", s or "")
    s = H.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").replace("​", "")
    return " ".join(s.split())


def iframe(page, fallback):
    try:
        h = H.unescape(curl_get(BASE + page, cache=False))
        m = re.search(r'<iframe class="iframeurl" src="([^"]+)"', h)
        if m:
            return m.group(1).strip()
    except Exception as e:
        print("iframe 찾기 실패", page, e)
    return fallback


def split_top(cell):
    """'하드탑: O 파워탑: X' → {'하드탑': 'O', '파워탑': 'X'}, 지붕 구분이 없으면 None"""
    parts = re.findall(r"(하드탑|파워탑)\s*:\s*(.*?)(?=(?:하드탑|파워탑)\s*:|$)", cell)
    return {k: v.strip() for k, v in parts} if parts else None


def spec_table(url):
    """비교표 → (트림 목록 [{name, price, col, top}], 섹션 목록 [(분류, [(항목, [칸...])])])"""
    h = curl_get(url, cache=False)
    b = re.sub(r"<!--.*?-->", "", h[h.find("<body"):], flags=re.S)
    b = re.sub(r"<script.*?</script>", "", b, flags=re.S)
    trims = []
    for col, m in enumerate(re.finditer(r'<div class="txt-wrap">(.*?)</div>', b, re.S)):
        blk = m.group(1)
        strong = re.search(r"<strong>(.*?)</strong>", blk, re.S).group(1)
        name = text(re.split(r"<br\s*/?>", strong)[-1])  # 'NEW GRAND CHEROKEE L<br>SUMMIT RESERVE…' → 뒷줄
        label = None
        for sp in re.findall(r"<span>(.*?)</span>", blk, re.S):
            t = text(sp)
            p = re.match(r"^￦\s*([\d,]+)$", t)
            if p:
                trims.append({"name": f"{name} {label}" if label else name, "price": int(p.group(1).replace(",", "")),
                              "col": col, "top": TOP.get(label)})
            elif t:
                label = t
    sections = []
    for sec in re.finditer(r"<li>\s*<p>(.*?)</p>\s*<div>(.*?)</div>\s*</li>", b, re.S):
        title, rows, sub = text(sec.group(1)), [], None
        for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", sec.group(2), re.S):
            cells = [text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr.group(1), re.S)]
            if len(cells) == 1:  # 표 안 소제목(라이트·휠·시트·에어백 등)
                sub = cells[0]
                continue
            if len(cells) >= 2:
                flag = all(is_flag(c) for c in cells[1:])
                # 사양 유무 행은 소제목으로 묶고(외관 · 휠 등), 제원 행은 소제목이 어디서 끝나는지 표에 없어서 대분류만 쓴다
                cat = f"{title} · {sub}" if sub and flag else title
                label = cells[0]
                if not flag and sub == "기어비" and re.fullmatch(r"[\d/]+|후진", label):
                    label = f"기어비 {label}"
                rows.append((cat, label, cells[1:]))
        sections.append(rows)
    return trims, [r for rows in sections for r in rows]


def is_flag(cell):
    if cell in ("O", "X", "-"):
        return True
    t = split_top(cell)
    return bool(t) and all(v in ("O", "X", "-") for v in t.values())


def trim_cats(rows, trim):
    cats = {}
    for cat, label, cells in rows:
        if trim["col"] >= len(cells):
            continue
        flag_row = all(is_flag(c) for c in cells)
        cell = cells[trim["col"]]
        tops = split_top(cell)
        if tops and trim["top"]:
            cell = tops.get(trim["top"], "")
        if flag_row:
            if cell == "O":
                cats.setdefault(cat, []).append(label)
        elif cell and cell not in ("-", "N/A"):
            cats.setdefault(cat, []).append(f"{label}: {cell}")
    return [{"cat": c, "items": [{"n": x} for x in its]} for c, its in cats.items()]


def page_lines(url):
    h = curl_get(url, cache=False)
    b = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", h[h.find("<body"):], flags=re.S)
    t = re.sub(r"<(br|/p|/li|/div|/tr|/h\d|/td|/span)[^>]*>", "\n", b)
    t = re.sub(r"<[^>]+>", " ", t)
    lines = [" ".join(H.unescape(l).replace("​", "").split()) for l in t.split("\n")]
    return [l for l in lines if l]


def edition(ed, home):
    """한정판 → (트림, 출처 URL들, 한정 대수 문구)"""
    srcs, cats, price, limit = [], [], None, ""
    if ed["page"]:
        src = iframe(ed["page"], None)
        srcs = [BASE + ed["page"], src] if src else [BASE + ed["page"]]
        if src:
            lines = page_lines(src)
            for i, l in enumerate(lines):
                if price is None and l.startswith("차량 가격"):
                    m = re.search(r"([\d,]{9,})\s*원", " ".join(lines[i:i + 3]))
                    price = int(m.group(1).replace(",", "")) if m else None
                if not limit and re.fullmatch(r"\d+대 한정", l):
                    limit = l
            if "기본 제원" in lines:
                spec = []
                for l in lines[lines.index("기본 제원") + 1:]:
                    if not re.match(r"^[-•·]\s*", l):
                        break
                    spec.append(re.sub(r"^[-•·]\s*", "", l))
                if spec:
                    cats.append({"cat": "기본 제원", "items": [{"n": x} for x in spec]})
            hl = [l for l in lines if l.endswith("에디션 하이라이트")]
            if hl:  # '85주년 에디션 하이라이트' 아래 그림 설명(배지·휠·데칼·시트)
                i = lines.index(hl[0])
                picks = [l for l in lines[i + 1:i + 30] if re.search(r"(토우 훅|휠|데칼|디테일|시트)$", l) and len(l) < 30]
                if picks:
                    cats.append({"cat": "에디션 사양", "items": [{"n": x} for x in dict.fromkeys(picks)]})
    nav = re.search(re.escape(ed["nav"]) + r'".{0,1500}?"price":\{"description":"시작가"[^}]*?"price":"([\d,]+)"', home, re.S)
    nav_price = int(nav.group(1).replace(",", "")) if nav else None
    if price is None:
        price = nav_price
        srcs.append(BASE + "/")
    elif nav_price and nav_price != price:
        print("  가격 차이(에디션 페이지 vs 메뉴)", ed["name"], price, nav_price)
    if price is None:
        return None, srcs, limit
    return {"name": ed["name"], "price": price, "cats": cats, "adds": [], "opts": []}, srcs, limit


def trim_white(im):
    """디자인 페이지 실내 사진 일부는 흰 여백이 붙어 있어서 여백만 잘라 낸다."""
    from PIL import ImageChops, Image
    rgb = im.convert("RGB")
    box = ImageChops.difference(rgb, Image.new("RGB", rgb.size, (255, 255, 255))).point(lambda v: 255 if v > 12 else 0).getbbox()
    return rgb.crop(box) if box else rgb


def photos(d, m, old):
    """공식 사진 → image·media·imageSource. 실패하면 이전 값을 그대로 둔다."""
    try:
        r = None
        if m["cut"]:
            r = cut_from(d, m["cut"])
            if r:  # 투명 렌더가 작아서 상세 화면용으로 공식 사진도 함께 둔다
                r["media"]["ext"] = [save_img(load(DAM + p), f"{d['id']}-x{n}.webp", False, 1600)
                                     for n, p in enumerate(m["photos"], 1)]
        if not r:
            r = photo_set(d, [DAM + p for p in m["photos"]])
        inn = []
        for n, p in enumerate(m["int"], 1):
            inn.append(save_img(trim_white(load(DAM + p)), f"{d['id']}-i{n}.webp", False, 1600))
        r["media"]["int"] = inn
        return r
    except Exception as e:
        print("  사진 실패", d["id"], e)
        if old.get("image"):
            return {"image": old["image"], "media": old.get("media"), "src": old.get("imageSource", "")}
        return None


def main(only=None):
    out = DATA / "jeep"
    out.mkdir(parents=True, exist_ok=True)
    old = {}
    for f in out.glob("*.json"):
        o = json.loads(f.read_text(encoding="utf-8"))
        old[o["id"]] = o
    home = H.unescape(H.unescape(curl_get(BASE + "/", cache=False)))
    done = set()
    for m in MODELS:
        mid = f"jeep-{m['slug']}"
        if only and mid not in only:
            done.add(f"{m['slug']}.json")
            continue
        src = iframe(m["spec"], m["fallback"])
        trims, rows = spec_table(src)
        if not trims:
            print(mid, "트림 없음")
            continue
        base = [{"name": t["name"], "price": t["price"], "cats": trim_cats(rows, t), "adds": [], "opts": []} for t in trims]
        variants = [{"name": "가솔린", "code": m["slug"], "trims": sorted(base, key=lambda t: t["price"])}]
        sources = [BASE + m["spec"], src]
        eds, notes_ed = [], []
        for ed in m["editions"]:
            t, s, limit = edition(ed, home)
            if not t:
                print("  에디션 가격 없음", ed["name"])
                continue
            eds.append(t)
            sources += [x for x in s if x not in sources]
            label = f"{t['name']}({limit})" if limit else t["name"]
            if not t["cats"]:
                notes_ed.append(f"{label}은 공식 홈페이지 모델 메뉴에 시작가만 있고 사양 자료가 없어 가격만 실었습니다.")
            else:
                got = "·".join(c["cat"] for c in t["cats"])
                notes_ed.append(f"{label}은 에디션 페이지에 적힌 {got}만 실었습니다(다른 사양은 공식 자료에 트림별로 나와 있지 않음).")
        if eds:
            variants.append({"name": "가솔린 · 한정판", "code": m["slug"] + "-edition", "trims": sorted(eds, key=lambda t: t["price"])})
        allt = [t for v in variants for t in v["trims"]]
        d = {"id": mid, "brand": "jeep", "name": m["name"], "segment": m["segment"], "image": "", "imageSource": "",
             "lowPrice": min(t["price"] for t in allt), "priceDate": PRICE_DATE, "sources": sources, "structure": "web",
             "variants": variants, "media": {"hero": "", "heroType": "photo", "ext": [], "int": []},
             "notes": ["지프 코리아 공식 홈페이지 '제원 • 사양' 페이지 비교표의 트림별 가격과 사양입니다(26년식). "
                       "가격표 날짜와 부가세·개별소비세 포함 여부는 페이지에 따로 적혀 있지 않아 수집일을 기준일로 두었습니다."]
             + notes_ed}
        r = photos(d, m, old.get(mid, {}))
        if r:
            d["image"], d["media"], d["imageSource"] = r["image"], r["media"], r["src"]
        save(out / f"{m['slug']}.json", d)
        done.add(f"{m['slug']}.json")
        print(mid, [(v["name"], [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"])) for t in v["trims"]]) for v in variants],
              d["media"].get("heroType"), len(d["media"].get("int", [])))
    for f in out.glob("*.json"):  # 공식 사이트에서 빠진 차종 파일 정리
        if f.name not in done:
            f.unlink()
            print("삭제", f.name)


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
