"""차종 대표 이미지를 받아 img/<id>.webp로 저장하고 data/<brand>/*.json의 image를 그 경로로 바꾼다.

제조사 서버가 자동화 요청을 막거나 주소가 바뀌어도 사이트에서 사진이 항상 보이도록 사이트 안에 둔다.
투명 배경 이미지는 차체 둘레의 빈 여백을 잘라내고, 가로 960px 이하로만 줄인다(키우지 않는다).
"""
import io
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from common import DATA, ROOT

IMG = ROOT / "img"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130"}

# 제조사 페이지의 대표 이미지가 비었거나 사진이 아닌 경우 쓸 공식 이미지
OVERRIDES = {
    "renault-arkana": "https://cdn.renault.co.kr/ko/resource/img/upload/asset/arkana/builder/car_img_iconic.webp",
    "renault-grand-koleos": "https://cdn.renault.co.kr/upload/asset/koleos/main_off.webp",
    "renault-filante": "https://cdn.renault.co.kr/upload/asset/filante/main_off.webp",
    "chevrolet-trailblazer": "https://www.chevrolet.co.kr/content/dam/chevrolet/as/kr/ko/index/"
                             "e-catalogue-price-list/2025/may/01-images/catalog-img-trailblazer.png",
}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=40) as r:
        return r.read()


def hyundai_45(model):
    """현대차 모델 소개 페이지의 og:image(45도 측면, 400px)가 목록용 측면 썸네일(290px)보다 크다."""
    for src in model.get("sources", []):
        m = re.match(r"(https://www\.hyundai\.com/kr/ko/e/vehicles/[^/]+)/price", src)
        if not m:
            continue
        try:
            html = get(m.group(1) + "/intro").decode("utf-8", "replace")
        except Exception:
            continue
        og = re.search(r'property="og:image" content="([^"]+)"', html)
        if og and "side-45" in og.group(1):
            return og.group(1)
    return None


def candidates(model):
    out = []
    if model["id"] in OVERRIDES:
        out.append(OVERRIDES[model["id"]])
    if model["brand"] == "hyundai":
        u = hyundai_45(model)
        if u:
            out.append(u)
    src = model.get("imageSource") or model.get("image") or ""
    if src.startswith("http"):
        out.append(src)
    return out


def save_image(model):
    for url in candidates(model):
        try:
            im = Image.open(io.BytesIO(get(url)))
            im.load()
        except Exception:
            continue
        im = im.convert("RGBA")
        box = im.getchannel("A").getbbox()
        if box and box != (0, 0, *im.size):
            pad = 6
            im = im.crop((max(box[0] - pad, 0), max(box[1] - pad, 0),
                          min(box[2] + pad, im.width), min(box[3] + pad, im.height)))
        if im.width > 960:
            im = im.resize((960, round(im.height * 960 / im.width)), Image.LANCZOS)
        IMG.mkdir(exist_ok=True)
        im.save(IMG / f"{model['id']}.webp", "WEBP", quality=86, method=6)
        return url, im.size
    return None, None


def main(only=None):
    files = sorted(DATA.glob("*/*.json"))
    files = [f for f in files if f.parent.name != "data" and f.name not in ("index.json", "search.json")]
    models = [(f, json.loads(f.read_text(encoding="utf-8"))) for f in files]
    models = [(f, d) for f, d in models if not only or d["id"] in only]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda fd: save_image(fd[1]), models))
    for (f, d), (url, size) in zip(models, res):
        if not url:
            print("NO IMAGE", d["id"])
            continue
        d["imageSource"] = url
        d["image"] = f"img/{d['id']}.webp"
        f.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{d['id']}: {size[0]}x{size[1]}")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
