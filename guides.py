# -*- coding: utf-8 -*-
"""
guides/ 폴더의 정보글을 아직 안 올린 것부터 순서대로 발행한다.
  python guides.py            하루 1개 예약 (09~21시 사이)
  python guides.py --count 3 --now   지금 바로 3개
글 파일 맨 위 주석: <!-- title: 제목 -->, <!-- labels: 가이드,강아지 -->
"""
import argparse
import glob
import os
import re
from datetime import datetime

from publish import HERE, KST, access_token, api, load_done, save_done, schedule, log

GUIDES = os.path.join(HERE, "guides")
FOOT = ("<p style='font-size:13px;color:#5E6B64;margin-top:32px'>이 글은 일반적인 정보를 정리한 것으로, "
        "아이의 건강 상태에 따라 달라질 수 있어요. 치료나 접종 같은 의료 판단은 꼭 동물병원과 상담해 주세요.</p>")


def read(path):
    raw = open(path, encoding="utf-8").read()
    title = re.search(r"<!--\s*title:\s*(.*?)\s*-->", raw).group(1)
    labels = [x.strip() for x in re.search(r"<!--\s*labels:\s*(.*?)\s*-->", raw).group(1).split(",") if x.strip()]
    body = re.sub(r"<!--.*?-->\s*", "", raw, flags=re.S).strip()
    slug = re.sub(r"^\d+-", "", os.path.basename(path)[:-5])
    return {"slug": slug, "title": title, "labels": labels, "content": body + "\n" + FOOT}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--now", action="store_true")
    a = ap.parse_args()
    now = datetime.now(KST)
    done = load_done()
    todo = [g for g in map(read, sorted(glob.glob(os.path.join(GUIDES, "*.html")))) if f"guide:{g['slug']}" not in done]
    todo = todo[:a.count]
    print(f"남은 정보글 → 이번에 {len(todo)}개")
    if not todo:
        return
    tok = access_token()
    times = [now] * len(todo) if a.now else schedule(len(todo), now)
    for g, t in zip(todo, times):
        draft = api("POST", "posts/", tok, {"kind": "blogger#post", "title": g["slug"].replace("-", " "),
                                            "content": g["content"], "labels": g["labels"]}, {"isDraft": "true"})
        params = {} if a.now else {"publishDate": t.isoformat(timespec="seconds")}
        res = api("POST", f"posts/{draft['id']}/publish", tok, params=params)
        api("PATCH", f"posts/{draft['id']}", tok, {"title": g["title"]})
        done[f"guide:{g['slug']}"] = now.strftime("%Y-%m-%d")
        save_done(done)
        log([t.strftime("%Y-%m-%d %H:%M"), g["title"], "/".join(g["labels"]), res.get("url", "")])
        print(" -", t.strftime("%m-%d %H:%M"), g["title"], res.get("url", ""))


if __name__ == "__main__":
    main()
