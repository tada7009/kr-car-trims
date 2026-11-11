"""캐딜락 코리아 공식 사이트 → data/cadillac/*.json (사진까지 한 번에)

- 가격·트림: 온라인 견적(구성기) 페이지 /purchase/onlineshop/car-configuration.gm?dmsModelCd=..
  트림 목록에 판매 가격(개별소비세 5.0% 기준)·주요 사양·배경 투명 렌더가 들어 있다.
  캐딜락은 가격표 PDF가 없고, 구성기 첫 화면의 차종 목록이 곧 판매 차종이다.
- 트림별 사양: 차종 '트림' 비교표(/suvs/escalade/trim, /electric/escalade-iq/trim)의 체크 표시
- 제원: 차종 '제원' 페이지(/suvs/escalade/specs, /electric/escalade-iq/specs)
- 사진: 구성기의 트림별 렌더(배경 투명)와 실내 사진
GMC(scrape_gmc.py)도 같은 GM 한국사업장 구성기를 써서 configurator()·photos()를 가져다 쓴다.
"""
import hashlib
import html as H
import json
import re
from html.parser import HTMLParser

from common import DATA, curl_get, save
from fetch_import_media import IMG, cut_from, load, save as save_img

BASE = "https://www.cadillac.co.kr"
CFG = "/purchase/onlineshop/car-configuration.gm?salesSection=offline&dmsModelCd={}"
# 구성기 차종 코드 → (파일 키, 이름, 차급, 연료, 트림 비교표 열 이름, 사양 페이지 경로)
MODELS = {
    "61": ("escalade", "Escalade", "SUV", "가솔린", "ESCALADE", "/suvs/escalade"),
    "61A": ("escalade-esv", "Escalade ESV", "SUV", "가솔린", "ESCALADE ESV", "/suvs/escalade"),
    "62": ("escalade-iq", "Escalade IQ", "전기 SUV", "전기", "ESCALADE IQ", "/electric/escalade-iq"),
    "62A": ("escalade-iql", "Escalade IQL", "전기 SUV", "전기", "ESCALADE IQL", "/electric/escalade-iq"),
}
# 구성기 실내 사진의 시트 색 코드(구성기가 트림을 고르면 받아 오는 첫 시트 색). 사진 주소: <트림코드>_<시트>_F.jpg
SEATS = {"61": "4AA", "61A": "4AA", "62": "EMY", "62A": "EMY"}
SECTIONS = {  # 트림 비교표 구역 이름 → 분류 이름
    "INTERIOR": "내장", "EXTERIOR": "외관", "SAFETY & DRIVER ASSISTANCE": "안전·주행 보조",
    "SAFETY & DRIVER ASSISTANCE & CONVENIENCE": "안전·주행 보조·편의", "PERFORMANCE": "파워트레인",
    "MECHANICAL": "파워트레인", "EXTERIOR COLOR": None, "INTERIOR COLOR": None,
}


def text(s):
    s = H.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return " ".join(s.replace("\u200b", "").replace("\ufeff", "").split())


def norm(s):
    return re.sub(r"[^0-9A-Z가-힣]", "", text(s).upper())


# ---------- 구성기 ----------
def configurator(base, code):
    """구성기 페이지 → (차종 목록 {코드: (이름, 시작가)}, 트림 [{ub, name, price, keys, img}])"""
    h = curl_get(base + CFG.format(code), cache=False)
    models = {}
    for nm, c, p in re.findall(r'<p class="car_name">(.*?)</p>\s*<p class="car_price"><span>￦</span>'
                               r'<span id="p_price_([^"]+)"[^>]*>([\d,]+)', h, re.S):
        models.setdefault(c, (text(nm), int(p.replace(",", ""))))
    trims = []
    for li in re.findall(r'<li class="trim_item[^"]*"(.*?)</ul>\s*</li>', h, re.S):
        ub = re.search(r'data-ubCarCd="([^"]+)"', li)
        nm = re.search(r'class="car_name">(.*?)</span>', li, re.S)
        pr = re.search(r'<span class="unit">￦</span><span>([\d,]+)</span>', li)
        im = re.search(r'<img src="([^"]+_F\.png)"', li)
        if not (ub and nm and pr):
            continue
        keys = [text(x) for x in re.findall(r"<p>(.*?)</p>", li, re.S)]
        trims.append({"ub": ub.group(1), "name": text(nm.group(1)), "price": int(pr.group(1).replace(",", "")),
                      "keys": [k for k in keys if k], "img": base + im.group(1) if im else ""})
    return models, trims


def photos(d, trims, seat, old):
    """구성기 렌더로 대표 사진(배경 투명)·트림별 사진·실내 사진을 만든다. 실패하면 예전 사진 정보를 그대로 둔다."""
    try:
        r = cut_from(d, trims[0]["img"]) if trims and trims[0]["img"] else None
    except Exception as e:
        print("  사진 실패", d["id"], e)
        r = None
    if not r:
        for k in ("image", "media", "imageSource"):
            if k in old:
                d[k] = old[k]
        old_imgs = {t["name"]: t.get("img") for v in old.get("variants", []) for t in v["trims"] if t.get("img")}
        for v in d["variants"]:
            for t in v["trims"]:
                if t["name"] in old_imgs:
                    t["img"] = old_imgs[t["name"]]
        return
    d["image"], d["media"], d["imageSource"] = r["image"], r["media"], r["src"]
    if len(trims) > 1:  # 트림마다 겉모습(그릴·휠·색)이 달라서 트림 사진을 따로 둔다. 같은 렌더는 한 파일을 같이 쓴다
        for f in IMG.glob(f"{d['id']}-t*.webp"):
            f.unlink()
        seen = {hashlib.md5(curl_get(trims[0]["img"], binary=True)).hexdigest(): r["image"]}
        by = {t["name"]: t for t in trims}
        for v in d["variants"]:
            for t in v["trims"]:
                src = by.get(t["name"], {}).get("img")
                if not src:
                    continue
                try:
                    k = hashlib.md5(curl_get(src, binary=True)).hexdigest()
                    if k not in seen:
                        seen[k] = save_img(load(src), f"{d['id']}-t{len(seen)}.webp", True, 1200)
                    t["img"] = seen[k]
                except Exception as e:
                    print("  트림 사진 실패", t["name"], e)
    if seat and trims[0]["img"]:
        inn = []
        for n, a in enumerate("FS", 1):
            u = re.sub(r"_[A-Z0-9]+_F\.png$", f"_{seat}_{a}.jpg", trims[0]["img"])
            try:
                inn.append(save_img(load(u), f"{d['id']}-i{n}.webp", False, 1600))
            except Exception as e:
                print("  실내 사진 실패", u, e)
        d["media"]["int"] = inn


# ---------- 트림 비교표 ----------
class Tree(HTMLParser):
    """gb-adv-grid(행)·adv-col(열)만 골라 나무 구조로 만든다. 체크 표시는 svg 그림이다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "root", "kids": [], "txt": [], "svg": 0}
        self.stack, self.skip, self.svg = [self.root], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "svg":
            self.svg += 1
            self.stack[-1]["svg"] += 1
        elif tag in ("gb-adv-grid", "adv-col"):
            n = {"tag": tag, "kids": [], "txt": [], "svg": 0, "cls": dict(attrs).get("class") or ""}
            self.stack[-1]["kids"].append(n)
            self.stack.append(n)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag == "svg":
            self.svg = max(0, self.svg - 1)
        elif tag in ("gb-adv-grid", "adv-col"):
            while len(self.stack) > 1:
                if self.stack.pop()["tag"] == tag:
                    break

    def handle_data(self, data):
        if not self.skip and not self.svg:
            t = text(data)
            if t:
                self.stack[-1]["kids"].append(t)


def node_text(n):
    out = []
    for k in n["kids"]:
        out.extend([k] if isinstance(k, str) else node_text(k))
    return out


def node_svg(n):
    return n["svg"] + sum(node_svg(k) for k in n["kids"] if isinstance(k, dict))


def trim_table(path, names):
    """트림 비교표 → {열 이름: [(구역, 사양), ...]} — names는 표 머리에 나오는 열 이름(트림 또는 차종)"""
    tree = Tree()
    tree.feed(curl_get(BASE + path + "/trim", cache=False))
    keys = sorted(((norm(n), n) for n in names), key=lambda x: -len(x[0]))
    out = {n: [] for n in names}
    state = {"cols": [], "sec": None, "year": ""}

    def match(cell):
        s = norm(" ".join(node_text(cell)))
        return next((n for k, n in keys if k and k in s), None)

    def cols_of(n):
        return [k for k in n["kids"] if isinstance(k, dict) and k["tag"] == "adv-col"]

    def has_multi(n):  # 안에 열이 둘 이상인 행이 또 있으면 표 한 줄이 아니라 묶음이다
        return any(isinstance(k, dict) and ((k["tag"] == "gb-adv-grid" and len(cols_of(k)) >= 2) or has_multi(k))
                   for k in n["kids"])

    def walk(n):
        cols = cols_of(n)
        if n["tag"] == "gb-adv-grid" and len(cols) >= 2:
            label = " ".join(node_text(cols[0])[:1])
            rest = cols[1:]
            has_txt = any(node_text(c) for c in rest)
            # 구역의 마지막 행에는 다음 구역용 전체 폭 열(col-sm-12)이 붙어 있어 빼고 센다
            cells = [c for c in rest if not "col-sm-12" in c["cls"].split()]
            if (label and state["cols"] and len(cells) >= len(state["cols"]) and not has_txt
                    and not node_svg(cols[0]) and not has_multi(cols[0])):  # 사양 행: 끝의 열들이 트림 열
                for name, c in zip(state["cols"], cells[-len(state["cols"]):]):
                    if node_svg(c) and state["sec"]:
                        out[name].append((state["sec"], label))
                return
            hit = [match(c) for c in rest]
            if any(hit):  # 머리 행: 열 이름(트림·차종)
                state["cols"] = [h for h in hit if h]
            up = label.upper()
            if (any(hit) or has_txt) and (up in SECTIONS or "이그젝큐티브" in label):  # 구역 이름
                state["sec"] = SECTIONS.get(up, label)
        for k in n["kids"]:  # 묶음(탭·구역)은 안으로 들어가 머리 행을 다시 읽는다
            if isinstance(k, dict):
                walk(k)

    walk(tree.root)
    year = re.search(r"\b(20\d\d) (?:THE NEW )?ESCALADE", " ".join(node_text(tree.root)))
    return out, year.group(1) if year else ""


def to_cats(pairs, skip=()):
    cats = {}
    for sec, n in pairs:
        if sec in skip:
            continue
        lst = cats.setdefault(sec, [])
        if n not in lst:
            lst.append(n)
    return [{"cat": c, "items": [{"n": n} for n in v]} for c, v in cats.items()]


# ---------- 제원 ----------
def find(pat, s, g=1):
    m = re.search(pat, s)
    return m.group(g).strip() if m else ""


def body_specs(seg):
    """한 차체 구간(전장~적재 공간)의 치수·공간"""
    items = []
    for lab, pat in (("전장", r"전장 ([\d,]+ ?mm)"), ("휠베이스", r"휠베이스 ([\d,]+ ?mm)"), ("전폭", r"전폭 ([\d,]+ ?mm)"),
                     ("전고", r"전고 ([\d,]+ ?mm)"), ("지상고", r"지상고 ([\d,]+ ?mm)")):
        v = find(pat, seg)
        if v:
            items.append(f"{lab} {v}")
    seats = find(r"SEATS (?:UP TO )?(\d+) ?PASSENGERS", seg)
    if seats:
        items.append(f"승차 정원 {seats}명")
    for lab, pat in (("1열 레그룸", r"FRONT LEGROOM ([\d,]+ ?mm)"), ("2열 레그룸", r"SECOND ROW LEGROOM ([\d,]+ ?mm)"),
                     ("3열 레그룸", r"THIRD ROW LEGROOM ([\d,]+ ?mm)"), ("적재 공간(1열 뒤)", r"BEHIND FIRST ROW ([\d,]+ ?L)"),
                     ("적재 공간(2열 뒤)", r"BEHIND SECOND ROW ([\d,]+ ?L)"), ("적재 공간(3열 뒤)", r"BEHIND THIRD ROW ([\d,]+ ?L)"),
                     ("앞 트렁크(eTRUNK) 적재 공간", r"eTRUNK® CARGO SPACE ([\d,]+ ?L)")):
        v = find(pat, seg)
        if v:
            items.append(f"{lab} {v}")
    return items


def specs(path, col):
    """제원 페이지 → 그 차종(열 이름)의 '성능·제원' 항목"""
    t = text(curl_get(BASE + path + "/specs", cache=False))
    t = t.replace("&nbsp;", " ")
    items = []
    if "IQ" in col:
        rng = re.search(r"RANGE ([\d,]+ ?km) \(IQ 기준\), ([\d,]+ ?km) \(IQL 기준\) (\S+ \S+ \S+ 기준)", t)
        if rng:
            items.append(f"1회 충전 주행거리 {rng.group(2 if col.endswith('IQL') else 1)} ({rng.group(3)})")
        acc = re.search(r"가속력 \(0-100 km/h\) ([\d.]+) SECONDS (Velocity 모드 기준)", t)
        if acc:
            items.append(f"가속력(0-100km/h) {acc.group(1)}초 ({acc.group(2)})")
        for lab, pat in (("최고출력", r"POWERTRAIN ([\d,]+ ?HP) (Velocity 모드 기준)"),
                         ("최대토크", r"TORQUE ([\d.,]+ ?kg\.?m) (Velocity 모드 기준)")):
            m = re.search(pat, t)
            if m:
                items.append(f"{lab} {m.group(1)} ({m.group(2)})")
        for lab, pat in (("배터리 용량", r"([\d,.]+ ?kWh) 배터리 용량"), ("최대 충전 전력", r"CHARGING RATE ([\d,]+ ?kW) 최대 충전 전력"),
                         ("DC 급속 충전 10분 충전 시 최대 주행 가능 거리", r"CHARGE UP TO ([\d,]+ ?km) 10분 충전 시"),
                         ("레벨2 AC 충전 1시간 충전 시 최대 주행 가능 거리", r"CHARGE UP TO ([\d,]+ ?km) 1시간 충전 시")):
            v = find(pat, t)
            if v:
                items.append(f"{lab} {v}")
        segs = [m.start() for m in re.finditer(r"ESCALADE IQ ESCALADE IQL 전장", t)]
    else:
        for lab, pat in (("엔진", r"ENGINE (.+?) HORSEPOWER"), ("최고출력", r"HORSEPOWER (.+?\)) TORQUE"),
                         ("최대토크", r"TORQUE (.+?\)) MAX TOWING"), ("최대 견인력", r"MAX TOWING CAPACITY ([\d,]+ ?kg)")):
            v = find(pat, t)
            if v:
                items.append(f"{lab} {v}")
        segs = [m.start() for m in re.finditer(r"ESCALADE ESCALADE ESV 전장", t)]
    # 차체 구간: 첫 구간은 기본(IQ·ESCALADE), 두 번째 구간은 긴 차체(IQL·ESV)
    long = col.endswith(("ESV", "IQL"))
    if len(segs) >= 2:
        start = segs[1] if long else segs[0]
        end = t.find("2열 이그젝큐티브 시트 패키지", start) if long else segs[1]
        items += body_specs(t[start:end if end > start else len(t)])
    return items


# ---------- 차종 ----------
def build(code, cfg_models, old):
    key, name, seg, fuel, col, path = MODELS[code]
    _, trims = configurator(BASE, code)
    if not trims:
        print("트림 없음", code)
        return None
    trims.sort(key=lambda t: t["price"])  # 가격이 같으면 구성기 순서 유지
    is_iq = path.startswith("/electric")
    if is_iq:  # 전기차 비교표는 열이 차종(IQ·IQL)이고 차종마다 트림이 하나다
        table, year = trim_table(path, [MODELS[c][4] for c in ("62", "62A")])
        rows = {t["name"]: table.get(col, []) for t in trims}
    else:  # 에스컬레이드·ESV는 같은 비교표를 쓰고 열이 트림이다
        table, year = trim_table(path, [t["name"] for t in trims])
        rows = {t["name"]: table.get(t["name"], []) for t in trims}
    perf = specs(path, col)
    skip = () if col.endswith("ESV") else ("이그젝큐티브 시트 패키지 (ESV 기준)",)
    out, missing = [], []
    for t in trims:
        cats = []
        if t["keys"]:
            cats.append({"cat": "주요 사양", "items": [{"n": k} for k in t["keys"]]})
        if perf:
            cats.append({"cat": "성능·제원", "items": [{"n": x} for x in perf]})
        table_cats = to_cats(rows.get(t["name"], []), skip)
        if not table_cats:
            missing.append(t["name"])
        cats += table_cats
        out.append({"name": t["name"], "price": t["price"], "cats": cats, "adds": [], "opts": []})
    src = [BASE + CFG.format(code), BASE + path + "/trim", BASE + path + "/specs"]
    notes = [f"캐딜락 코리아 공식 온라인 견적(구성기)의 트림별 판매 가격(개별소비세 5.0% 기준, 부가세 포함)과 "
             f"공식 사이트 '트림' 비교표·'제원' 페이지의 사양입니다. 가격표 날짜가 없어 조회일 기준이며, {year or '2026'}년형입니다."]
    if any("CHOICE" in t["name"] for t in out):
        notes.append("이름에 'CHOICE'가 붙은 트림은 같은 이름의 기본 트림에서 나이트 비전을 뺀 구성으로, 공식 구성기 가격이 100만 원 낮습니다.")
    if col.endswith("ESV"):
        notes.append("트림 비교표의 '이그젝큐티브 시트 패키지 (ESV 기준)' 항목은 ESV에 해당해 이 차종에만 넣었습니다.")
    if is_iq:
        notes.append("전기차 구매 보조금은 반영되지 않은 가격입니다.")
    if missing:
        notes.append("트림 비교표에서 찾지 못한 트림(" + ", ".join(missing) + ")은 구성기 주요 사양만 실었습니다.")
    d = {"id": f"cadillac-{key}", "brand": "cadillac", "name": name, "segment": seg, "image": "", "imageSource": "",
         "lowPrice": min(t["price"] for t in out), "priceDate": "2026-11-11", "sources": src, "structure": "configurator",
         "variants": [{"name": fuel, "code": code, "trims": out}],
         "media": {"hero": "", "heroType": "cut", "ext": [], "int": []}, "notes": notes}
    photos(d, trims, SEATS.get(code), old)
    return d


def main():
    out = DATA / "cadillac"
    out.mkdir(parents=True, exist_ok=True)
    cfg_models, _ = configurator(BASE, "61")
    for c in cfg_models:
        if c not in MODELS:
            print("구성기에 새 차종이 있음(MODELS에 추가 필요):", c, cfg_models[c])
    for code in MODELS:
        if code not in cfg_models:
            print("구성기에 없음(판매 종료?):", code)
            continue
        f = out / f"{MODELS[code][0]}.json"
        old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        d = build(code, cfg_models, old)
        if not d:
            continue
        save(f, d)
        print(d["id"], d["media"]["heroType"] if d.get("media") else "-",
              [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"])) for t in d["variants"][0]["trims"]])


if __name__ == "__main__":
    main()
