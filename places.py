# -*- coding: utf-8 -*-
"""
반려노트 메뉴 페이지용 공공데이터 파일 만들기 (하루 1번).
  data/shelters.json            동물보호센터 (농림축산검역본부)
  data/hospitals-<지역>.json     영업 중인 동물병원 (행정안전부)
  data/travel-<지역>.json        반려동물 동반 여행지 (한국관광공사)
  python places.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime

from publish import HERE, KST, ROMAN, need, https

DATA = os.path.join(HERE, "data")
GWANGJU_GU = ("동구", "서구", "남구", "북구", "광산구")
FULL = [  # 주소 앞부분 → 지역
    ("서울", "서울"), ("부산", "부산"), ("대구", "대구"), ("인천", "인천"), ("광주", "광주"),
    ("대전", "대전"), ("울산", "울산"), ("세종", "세종"), ("경기", "경기"), ("강원", "강원"),
    ("충청북", "충북"), ("충북", "충북"), ("충청남", "충남"), ("충남", "충남"),
    ("전북", "전북"), ("전라북", "전북"), ("전라남", "전남"), ("전남", "전남"),
    ("경상북", "경북"), ("경북", "경북"), ("경상남", "경남"), ("경남", "경남"), ("제주", "제주"),
]
TRAVEL_TYPE = {"12": "관광지", "14": "문화시설", "15": "행사", "25": "여행코스", "28": "레포츠",
               "32": "숙박", "38": "쇼핑", "39": "음식점"}


def region(addr):
    a = str(addr or "").strip()
    if a.startswith("전남광주"):
        parts = a.split()
        return "광주" if len(parts) > 1 and parts[1] in GWANGJU_GU else "전남"
    for p, r in FULL:
        if a.startswith(p):
            return r
    return ""


def fetch_all(url, rows, **params):
    key = need("DATA_GO_KR_KEY")
    out, page = [], 1
    while True:
        q = dict(params, serviceKey=key, pageNo=page, numOfRows=rows)
        with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(q), timeout=90) as r:
            d = json.loads(r.read().decode("utf-8"))
        body = d["response"]["body"]
        items = (body.get("items") or {}).get("item") or [] if isinstance(body.get("items"), dict) else []
        if isinstance(items, dict):
            items = [items]
        out += items
        total = int(body.get("totalCount") or 0)
        if not items or len(out) >= total:
            return out
        page += 1


def save(name, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def tel(s):
    s = str(s or "").strip()
    return "" if s in ("-", "--") else s


def shelters(now):
    raw = fetch_all("https://apis.data.go.kr/1543061/animalShelterSrvc_v2/shelterInfo_v2", 1000, _type="json")
    items = []
    for a in raw:
        r = region(a.get("careAddr")) or region(a.get("orgNm"))
        if not r:
            continue
        items.append({"n": str(a.get("careNm") or "").strip(), "r": r, "o": str(a.get("orgNm") or "").strip(),
                      "ad": str(a.get("careAddr") or "").strip(), "t": tel(a.get("careTel")),
                      "an": str(a.get("saveTrgtAnimal") or "").replace("+", ", "),
                      "dv": str(a.get("divisionNm") or ""),
                      "h": f"{a.get('weekOprStime') or ''}~{a.get('weekOprEtime') or ''}".strip("~")})
    items.sort(key=lambda x: (x["r"], x["n"]))
    save("shelters.json", {"updated": now, "items": items})
    return len(items)


def hospitals(now):
    raw = fetch_all("https://apis.data.go.kr/1741000/animal_hospitals/info", 1000, returnType="json",
                    **{"cond[SALS_STTS_CD::EQ]": "01"})
    by = defaultdict(list)
    for a in raw:
        addr = str(a.get("ROAD_NM_ADDR") or a.get("LOTNO_ADDR") or "").strip()
        r = region(addr)
        if not r or not a.get("BPLC_NM"):
            continue
        by[r].append({"n": a["BPLC_NM"].strip(), "ad": addr, "t": tel(a.get("TELNO"))})
    for r, items in by.items():
        items.sort(key=lambda x: x["ad"])
        save(f"hospitals-{ROMAN[r]}.json", {"updated": now, "region": r, "items": items})
    return sum(len(v) for v in by.values())


def travel(now):
    raw = fetch_all("https://apis.data.go.kr/B551011/KorPetTourService2/areaBasedList2", 1000,
                    MobileOS="ETC", MobileApp="banryeonote", _type="json")
    by = defaultdict(list)
    for a in raw:
        addr = (str(a.get("addr1") or "") + " " + str(a.get("addr2") or "")).strip()
        r = region(addr)
        typ = TRAVEL_TYPE.get(str(a.get("contenttypeid")), "")
        if not r or not typ or not a.get("title"):
            continue
        by[r].append({"n": str(a["title"]).strip(), "ty": typ, "ad": addr, "t": tel(a.get("tel")),
                      "img": https(a.get("firstimage2") or a.get("firstimage") or "")})
    for r, items in by.items():
        items.sort(key=lambda x: (not x["img"], x["ty"], x["n"]))
        save(f"travel-{ROMAN[r]}.json", {"updated": now, "region": r, "items": items})
    return sum(len(v) for v in by.values())


def main():
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    for name, fn in (("보호센터", shelters), ("동물병원", hospitals), ("반려동반", travel)):
        try:
            print(name, fn(now))
        except Exception as e:  # 한 API 가 실패해도 나머지는 갱신
            print(name, "실패:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
