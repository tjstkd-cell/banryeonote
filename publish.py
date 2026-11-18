# -*- coding: utf-8 -*-
"""반려노트 - 유기동물 입양 대기 글 자동 생성·예약발행

흐름: 공공데이터(국가동물보호정보시스템) 구조동물 조회 → 지역·동물별로 묶어 글 생성
      → Blogger에 예약발행 (오전 9시~밤 9시 사이 고르게) → 발행한 동물 번호 기록(중복 방지)

처음 한 번:  python publish.py --auth        (브라우저에서 블로그 주인 구글 계정으로 허용)
미리보기:    python publish.py --preview     (발행 안 하고 글을 HTML로 만들어 브라우저에 열기)
발행:        python publish.py               (기본 2개 예약발행)
옵션:        --count 3  --days 20  --now(예약 없이 바로)

필요한 값(.env 또는 환경변수):
  DATA_GO_KR_KEY, BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOG_ID
  BLOGGER_REFRESH_TOKEN (GitHub Actions 용. 없으면 .blogger_token.json 사용)
"""
import argparse
import html
import http.server
import json
import os
import random
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "data", "published.json")
LOG = os.path.join(HERE, "data", "publish_log.csv")
PREVIEW = os.path.join(HERE, "data", "preview.html")
TOKEN = os.path.join(HERE, ".blogger_token.json")
SCOPE = "https://www.googleapis.com/auth/blogger"
API_BASE = "https://apis.data.go.kr/1543061/abandonmentPublicService_v2/"
KST = timezone(timedelta(hours=9))
DAY_START, DAY_END = 9, 21
MAX_PER_POST = 10
MIN_PER_POST = 3

SIDO = [  # (orgNm 앞부분, 라벨들)
    ("서울", ["서울"]), ("부산", ["부산"]), ("대구", ["대구"]), ("인천", ["인천"]),
    ("전남광주", ["광주", "전남"]), ("광주", ["광주"]), ("대전", ["대전"]), ("울산", ["울산"]),
    ("세종", ["세종"]), ("경기", ["경기"]), ("강원", ["강원"]), ("충청북", ["충북"]), ("충북", ["충북"]),
    ("충청남", ["충남"]), ("충남", ["충남"]), ("전북", ["전북"]), ("전라북", ["전북"]),
    ("전라남", ["전남"]), ("전남", ["전남"]), ("경상북", ["경북"]), ("경북", ["경북"]),
    ("경상남", ["경남"]), ("경남", ["경남"]), ("제주", ["제주"]),
]
KIND = {"개": "강아지", "고양이": "고양이"}
ROMAN = {"서울": "seoul", "부산": "busan", "대구": "daegu", "인천": "incheon", "광주": "gwangju", "대전": "daejeon",
         "울산": "ulsan", "세종": "sejong", "경기": "gyeonggi", "강원": "gangwon", "충북": "chungbuk", "충남": "chungnam",
         "전북": "jeonbuk", "전남": "jeonnam", "경북": "gyeongbuk", "경남": "gyeongnam", "제주": "jeju"}
SEX = {"M": "수컷", "F": "암컷"}
NEUTER = {"Y": "완료", "N": "안 함"}


# ------------------------------------------------------------ 설정
def env(name):
    v = os.environ.get(name, "").strip()
    p = os.path.join(HERE, ".env")
    if not v and os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for line in f:
                if line.startswith(name + "="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
    return v


def need(name):
    v = env(name)
    if not v:
        sys.exit(f"{name} 값이 없어요. .env 또는 환경변수에 넣어주세요.")
    return v


# ------------------------------------------------------------ 공공데이터
def fetch_animals(days):
    key = need("DATA_GO_KR_KEY")
    end = datetime.now(KST)
    start = end - timedelta(days=days)
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({
            "serviceKey": key, "_type": "json", "bgnde": start.strftime("%Y%m%d"),
            "endde": end.strftime("%Y%m%d"), "state": "protect", "pageNo": page, "numOfRows": 500})
        with urllib.request.urlopen(API_BASE + "abandonmentPublic_v2?" + q, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        body = data.get("response", {}).get("body", {})
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        out += items
        if len(out) >= int(body.get("totalCount") or 0) or not items:
            break
        page += 1
    return out


def sido_labels(org):
    org = org.replace(" ", "")
    for prefix, labels in SIDO:
        if org.startswith(prefix):
            return labels
    return []


def ymd(s):
    s = str(s or "")
    return f"{s[:4]}.{s[4:6]}.{s[6:8]}" if len(s) == 8 else s


def https(url):
    url = str(url or "").strip()
    return "https://" + url[7:] if url.startswith("http://") else url


# ------------------------------------------------------------ 글 만들기
def group_animals(animals, done):
    groups = defaultdict(list)
    for a in animals:
        no = str(a.get("desertionNo", ""))
        kind = KIND.get(a.get("upKindNm", ""))
        labels = sido_labels(a.get("orgNm", ""))
        if not no or no in done or not kind or not labels or not a.get("popfile1"):
            continue
        groups[(labels[0], kind)].append(a)
    for k in groups:  # 공고 마감이 가까운 순
        groups[k].sort(key=lambda a: (str(a.get("noticeEdt", "")), str(a.get("desertionNo"))))
    return groups


TITLES = [
    "{sido} 입양 대기 {kind} {n}마리, 보호소 연락처까지 정리 ({md})",
    "{md} {sido} 보호소에서 가족을 기다리는 {kind} {n}마리",
    "{sido} 유기{kind2} 입양 공고 {n}건 모음 | {md} 업데이트",
    "새 가족을 찾는 {sido} {kind} {n}마리 ({md} 보호소 공고)",
]
INTROS = [
    "{md} 기준으로 {sido} 지역 동물보호센터에 새로 등록된 {kind} 공고를 모았어요. 사진과 특징, 보호소 연락처를 함께 정리했으니 마음이 가는 아이가 있다면 공고가 끝나기 전에 보호소로 먼저 전화해 보세요.",
    "{sido}에서 보호 중인 {kind} {n}마리의 공고를 정리했어요. 공고 기간이 지나면 입양이 가능해지거나 다른 곳으로 옮겨질 수 있어서, 관심 있는 아이는 공고번호를 메모해 두고 보호소에 바로 문의하는 게 좋아요.",
    "오늘은 {sido} 보호소 공고 중 {kind} {n}마리를 소개해요. 잃어버린 반려동물을 찾는 분이라면 발견 장소와 특징을, 입양을 고민하는 분이라면 성격 메모를 먼저 살펴보세요.",
]
GUIDE = {
    "강아지": [
        "보호소에 전화해 아이가 아직 보호 중인지, 입양 가능 날짜가 언제인지 확인하기",
        "산책 시간과 혼자 있는 시간을 미리 계산해 보기 (하루 2회 산책이 기본)",
        "동물등록(내장형 칩) 여부와 예방접종 이력 물어보기",
        "입양 첫 주에는 낯선 환경 적응을 위해 조용한 공간과 일정한 일과 만들어 주기",
    ],
    "고양이": [
        "보호소에 전화해 아직 보호 중인지, 입양 가능 날짜가 언제인지 확인하기",
        "창문·방묘문 등 탈출 방지 준비가 되어 있는지 점검하기",
        "화장실, 모래, 스크래처, 숨을 곳(박스)을 미리 마련하기",
        "첫 며칠은 숨어 지내는 게 정상이니 억지로 꺼내지 말고 기다려 주기",
    ],
}


def animal_card(a, kind):
    img = html.escape(https(a.get("popfile1")))
    breed = html.escape(str(a.get("kindNm") or a.get("kindFullNm") or "").strip())
    sex = SEX.get(a.get("sexCd"), "미상")
    age = html.escape(str(a.get("age", "")).replace("(년생)", "년생").strip())
    weight = html.escape(str(a.get("weight", "")).strip())
    color = html.escape(str(a.get("colorCd", "")).strip())
    neuter = NEUTER.get(a.get("neuterYn"), "확인 필요")
    mark = html.escape(str(a.get("specialMark", "")).strip())
    place = html.escape(str(a.get("happenPlace", "")).strip())
    care = html.escape(str(a.get("careNm", "")).strip())
    tel = html.escape(str(a.get("careTel", "")).strip())
    addr = html.escape(str(a.get("careAddr", "")).strip())
    notice = html.escape(str(a.get("noticeNo", "")).strip())
    period = f"{ymd(a.get('noticeSdt'))} ~ {ymd(a.get('noticeEdt'))}"
    org = html.escape(str(a.get("orgNm", "")).strip())
    return f"""
<div style="border:1px solid #E7DFCF;border-radius:14px;overflow:hidden;margin:22px 0;background:#fff">
  <img src="{img}" alt="{org} 보호 중인 {breed} {sex}" loading="lazy" style="width:100%;max-height:420px;object-fit:cover;display:block;margin:0;border-radius:0"/>
  <div style="padding:16px 18px">
    <h3 style="margin:0 0 8px;font-size:19px;color:#1F4D3A">{breed} · {sex} · {age}</h3>
    <table style="width:100%;border-collapse:collapse;font-size:15px;margin:0">
      <tr><th style="width:92px;text-align:left;padding:6px 8px;background:#E6EFE9;border:1px solid #E7DFCF">특징</th><td style="padding:6px 8px;border:1px solid #E7DFCF">{mark or '-'}</td></tr>
      <tr><th style="text-align:left;padding:6px 8px;background:#E6EFE9;border:1px solid #E7DFCF">털색·체중</th><td style="padding:6px 8px;border:1px solid #E7DFCF">{color} / {weight}</td></tr>
      <tr><th style="text-align:left;padding:6px 8px;background:#E6EFE9;border:1px solid #E7DFCF">중성화</th><td style="padding:6px 8px;border:1px solid #E7DFCF">{neuter}</td></tr>
      <tr><th style="text-align:left;padding:6px 8px;background:#E6EFE9;border:1px solid #E7DFCF">발견 장소</th><td style="padding:6px 8px;border:1px solid #E7DFCF">{org} {place}</td></tr>
      <tr><th style="text-align:left;padding:6px 8px;background:#E6EFE9;border:1px solid #E7DFCF">공고 기간</th><td style="padding:6px 8px;border:1px solid #E7DFCF">{period}<br/><span style="color:#5E6B64;font-size:13px">공고번호 {notice}</span></td></tr>
      <tr><th style="text-align:left;padding:6px 8px;background:#E6EFE9;border:1px solid #E7DFCF">보호소</th><td style="padding:6px 8px;border:1px solid #E7DFCF"><b>{care}</b><br/>{addr}<br/>☎ <a href="tel:{tel}">{tel}</a></td></tr>
    </table>
  </div>
</div>"""


def build_post(sido, kind, animals, now, idx=0):
    n = len(animals)
    md = f"{now.month}월 {now.day}일"
    kind2 = "견" if kind == "강아지" else "묘"
    rnd = random.Random(f"{sido}{kind}{now:%Y%m%d}")
    ctx = dict(sido=sido, kind=kind, kind2=kind2, n=n, md=md)
    title = TITLES[(now.toordinal() + idx) % len(TITLES)].format(**ctx)
    shelters = sorted({str(a.get("careNm", "")).strip() for a in animals if a.get("careNm")})
    ends = sorted(str(a.get("noticeEdt", "")) for a in animals if a.get("noticeEdt"))
    breeds = defaultdict(int)
    for a in animals:
        breeds[str(a.get("kindNm") or "").strip() or "기타"] += 1
    breed_txt = ", ".join(f"{b} {c}마리" for b, c in sorted(breeds.items(), key=lambda x: -x[1])[:4])

    parts = [f"<p>{html.escape(rnd.choice(INTROS).format(**ctx))}</p>"]
    parts.append(
        '<div style="background:#E6EFE9;border:1px solid #CFE0D5;border-radius:14px;padding:16px 18px;margin:20px 0">'
        f'<b style="color:#14362A">한눈에 보기</b><ul style="margin:8px 0 0;padding-left:20px">'
        f"<li>지역: {html.escape(sido)}</li><li>동물: {kind} {n}마리 ({html.escape(breed_txt)})</li>"
        f"<li>보호소: {html.escape(', '.join(shelters[:4]))}{' 외' if len(shelters) > 4 else ''}</li>"
        f"<li>가장 빠른 공고 마감: {ymd(ends[0]) if ends else '-'}</li></ul></div>")
    parts.append(f"<h2>{html.escape(sido)} 입양 대기 {kind} 공고</h2>")
    parts += [animal_card(a, kind) for a in animals]
    parts.append(f"<h2>{kind} 입양 전에 확인하세요</h2><ol>" +
                 "".join(f"<li>{html.escape(x)}</li>" for x in GUIDE[kind]) + "</ol>")
    parts.append("<h2>입양·문의 방법</h2><p>마음에 드는 아이가 있다면 위 카드의 <b>보호소 전화번호</b>로 공고번호를 알려주고 "
                 "보호 상태와 방문 가능 시간을 먼저 확인하세요. 공고 기간 중에는 원래 보호자가 찾아갈 수 있도록 기다리는 기간이라, "
                 "입양은 보통 공고가 끝난 뒤에 진행돼요. 잃어버린 반려동물을 찾는 중이라면 공고 기간 안에 바로 연락하는 게 중요해요.</p>")
    parts.append('<blockquote>출처: 농림축산식품부 국가동물보호정보시스템(<a href="https://www.animal.go.kr" rel="nofollow noopener" target="_blank">animal.go.kr</a>) 공공데이터. '
                 f"{md} 수집 기준이며, 이미 입양·반환되었을 수 있으니 최신 상태는 보호소에 확인해 주세요.</blockquote>")
    labels = ["입양정보", kind] + sido_labels(animals[0].get("orgNm", ""))
    slug = f"{ROMAN.get(sido, 'korea')} {'dog' if kind == '강아지' else 'cat'} adoption {now:%Y %m %d}"
    return {"title": title, "slug": slug, "group": (sido, kind), "content": "\n".join(parts), "labels": list(dict.fromkeys(labels)),
            "nos": [str(a["desertionNo"]) for a in animals]}


REPEAT_DAYS = 3  # 같은 지역·동물 글은 3일 안에 다시 쓰지 않음


def plan_posts(animals, done, count, now):
    groups = group_animals(animals, done)
    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    posts, used_sido = [], set()
    recent = (now - timedelta(days=REPEAT_DAYS)).strftime("%Y-%m-%d")
    for (sido, kind), items in ranked:
        if len(posts) >= count:
            break
        if len(items) < MIN_PER_POST or sido in used_sido:
            continue
        if done.get(f"group:{sido}:{kind}", "") > recent:
            continue
        posts.append(build_post(sido, kind, items[:MAX_PER_POST], now, len(posts)))
        used_sido.add(sido)
    return posts


# ------------------------------------------------------------ Blogger
def post_form(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def auth():
    cid, sec = need("BLOGGER_CLIENT_ID"), need("BLOGGER_CLIENT_SECRET")
    state, got = secrets.token_urlsafe(16), {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if qs.get("state", [""])[0] == state:
                got["code"] = qs.get("code", [""])[0]
                got["error"] = qs.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "연결 완료! 이 창은 닫아도 돼요." if got.get("code") else "연결 실패. 창을 닫고 다시 시도해 주세요."
            self.wfile.write(f"<h2 style='font-family:sans-serif'>{msg}</h2>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_port}/"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state})
    print("브라우저에서 블로그 주인 구글 계정으로 '허용'을 눌러주세요.\n" + url, flush=True)
    webbrowser.open(url)
    t = threading.Thread(target=srv.handle_request)
    t.start()
    t.join(timeout=600)
    srv.server_close()
    if not got.get("code"):
        sys.exit(f"인증 실패: {got.get('error') or '시간 초과'}")
    tok = post_form("https://oauth2.googleapis.com/token", {
        "code": got["code"], "client_id": cid, "client_secret": sec,
        "redirect_uri": redirect, "grant_type": "authorization_code"})
    if "refresh_token" not in tok:
        sys.exit("refresh_token 을 받지 못했어요. 다시 --auth 해주세요.")
    with open(TOKEN, "w", encoding="utf-8") as f:
        json.dump({"refresh_token": tok["refresh_token"]}, f)
    print("인증 완료.")


def access_token():
    rt = env("BLOGGER_REFRESH_TOKEN")
    if not rt:
        if not os.path.exists(TOKEN):
            sys.exit("먼저 python publish.py --auth 를 실행해 주세요.")
        with open(TOKEN, encoding="utf-8") as f:
            rt = json.load(f)["refresh_token"]
    try:
        return post_form("https://oauth2.googleapis.com/token", {
            "refresh_token": rt, "client_id": need("BLOGGER_CLIENT_ID"),
            "client_secret": need("BLOGGER_CLIENT_SECRET"), "grant_type": "refresh_token"})["access_token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"토큰 갱신 실패({e.code}). python publish.py --auth 로 다시 연결해 주세요.")


def api(method, path, token, body=None, params=None):
    url = f"https://www.googleapis.com/blogger/v3/blogs/{need('BLOG_ID')}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Blogger API {e.code}: {e.read().decode(errors='replace')[:300]}")


def schedule(n, now):
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start, end = day.replace(hour=DAY_START), day.replace(hour=DAY_END)
    if now > end - timedelta(hours=1):
        start, end = start + timedelta(days=1), end + timedelta(days=1)
    start = max(start, now + timedelta(minutes=15))
    step = (end - start) / max(n, 1)
    return [start + step * i + timedelta(minutes=random.randint(0, 20)) for i in range(n)]


# ------------------------------------------------------------ 기록
def load_done():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_done(done):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    cutoff = (datetime.now(KST) - timedelta(days=90)).strftime("%Y-%m-%d")
    done = {k: v for k, v in done.items() if v >= cutoff or k.startswith("guide:")}  # 정보글 기록은 영구 보관
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=0)


def log(row):
    new = not os.path.exists(LOG)
    with open(LOG, "a", encoding="utf-8-sig") as f:
        if new:
            f.write("예약시각,제목,라벨,URL\n")
        f.write(",".join('"' + str(x).replace('"', "'") + '"' for x in row) + "\n")


def write_preview(posts):
    os.makedirs(os.path.dirname(PREVIEW), exist_ok=True)
    body = "".join(f"<section style='background:#fff;border-radius:16px;padding:24px;margin:24px 0'>"
                   f"<small>{html.escape(', '.join(p['labels']))}</small><h1 style='color:#14362A'>{html.escape(p['title'])}</h1>{p['content']}</section>"
                   for p in posts)
    page = ("<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>반려노트 발행 미리보기</title></head><body style=\"margin:0;background:#FBF6EC;font-family:'Malgun Gothic',sans-serif;"
            "color:#1E2A24;line-height:1.8\"><div style='max-width:760px;margin:0 auto;padding:16px'>" + body + "</div></body></html>")
    with open(PREVIEW, "w", encoding="utf-8") as f:
        f.write(page)
    return PREVIEW


# ------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--now", action="store_true")
    a = ap.parse_args()
    if a.auth:
        return auth()

    now = datetime.now(KST)
    done = load_done()
    animals = fetch_animals(a.days)
    posts = plan_posts(animals, done, a.count, now)
    print(f"수집 {len(animals)}마리 → 글 {len(posts)}개")
    if not posts:
        print("발행할 새 공고가 없어요.")
        return
    if a.preview:
        p = write_preview(posts)
        for x in posts:
            print(" -", x["title"], x["labels"])
        print("미리보기:", p)
        webbrowser.open("file:///" + p.replace("\\", "/"))
        return

    token = access_token()
    times = [now] * len(posts) if a.now else schedule(len(posts), now)
    ok = 0
    for p, t in zip(posts, times):
        try:
            # 영어 제목으로 먼저 발행해 주소(slug)를 고정한 뒤 한글 제목으로 바꾼다
            draft = api("POST", "posts/", token, {"kind": "blogger#post", "title": p["slug"],
                                                 "content": p["content"], "labels": p["labels"]},
                        {"isDraft": "true"})
            params = {} if a.now else {"publishDate": t.isoformat(timespec="seconds")}
            res = api("POST", f"posts/{draft['id']}/publish", token, params=params)
            res = api("PATCH", f"posts/{draft['id']}", token, {"title": p["title"]})
            for no in p["nos"]:
                done[no] = now.strftime("%Y-%m-%d")
            done[f"group:{p['group'][0]}:{p['group'][1]}"] = now.strftime("%Y-%m-%d")
            save_done(done)
            log([f"{t:%Y-%m-%d %H:%M}", p["title"], "/".join(p["labels"]), res.get("url", "")])
            ok += 1
            print(f"[예약] {t:%m-%d %H:%M}  {p['title']}  {res.get('url', '')}")
        except Exception as e:
            print(f"[실패] {p['title']}: {e}")
    print(f"완료: {ok}/{len(posts)}개")
    if ok < len(posts):
        sys.exit(1)


if __name__ == "__main__":
    main()
