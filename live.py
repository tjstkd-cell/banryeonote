# -*- coding: utf-8 -*-
"""
반려노트 홈 '오늘의 입양 대기' 실시간 데이터 만들기.
공공데이터(구조동물 조회)에서 보호 중인 동물을 받아 data/live.json 으로 저장한다.
블로그 테마 JS 가 GitHub Pages 의 이 파일을 읽어 카드로 보여준다.
  python live.py
"""
import json
import os
from datetime import datetime

from publish import HERE, KIND, KST, SEX, NEUTER, fetch_animals, sido_labels, https

OUT = os.path.join(HERE, "data", "live.json")
DAYS = 14
LIMIT = 600


def slim(a):
    labels = sido_labels(a.get("orgNm", ""))
    return {
        "no": str(a.get("desertionNo", "")),
        "k": KIND.get(a.get("upKindNm", ""), "기타"),
        "b": str(a.get("kindNm") or "").strip(),
        "s": SEX.get(a.get("sexCd"), "미상"),
        "a": str(a.get("age") or "").strip(),
        "w": str(a.get("weight") or "").strip(),
        "c": str(a.get("colorCd") or "").strip(),
        "n": NEUTER.get(a.get("neuterYn"), "미상"),
        "m": str(a.get("specialMark") or "").strip(),
        "p": str(a.get("happenPlace") or "").strip(),
        "r": labels[0] if labels else "",
        "img": https(a.get("popfile1")),
        "nn": str(a.get("noticeNo") or "").strip(),
        "ns": str(a.get("noticeSdt") or ""),
        "ne": str(a.get("noticeEdt") or ""),
        "cn": str(a.get("careNm") or "").strip(),
        "ct": str(a.get("careTel") or "").strip(),
        "ca": str(a.get("careAddr") or "").strip(),
    }


def main():
    animals = [a for a in fetch_animals(DAYS) if a.get("popfile1") and a.get("desertionNo")]
    items = [slim(a) for a in animals]
    items = [x for x in items if x["k"] in ("강아지", "고양이") and x["r"]]
    items.sort(key=lambda x: (x["ns"], x["no"]), reverse=True)  # 최근 공고 순
    items = items[:LIMIT]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    data = {"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "total": len(animals), "items": items}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"보호 중 {len(animals)}마리 → {len(items)}마리 저장 ({os.path.getsize(OUT)//1024}KB)")


if __name__ == "__main__":
    main()
