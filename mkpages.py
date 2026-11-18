# -*- coding: utf-8 -*-
"""메뉴용 Blogger 페이지 4개 만들기 (한 번만 실행). 영어 제목으로 만들어 주소를 고정한 뒤 한글 제목으로 바꾼다."""
from publish import access_token, api

SRC = "<p class='rn-src'>출처: {src} 공공데이터(공공데이터포털). 정보가 바뀌었을 수 있으니 방문·진료 전에 꼭 전화로 확인해 주세요.</p>"

PAGES = [
    ("shelters", "전국 동물보호센터 찾기", """
<p>유기·유실동물을 구조해 보호하는 전국 동물보호센터 목록이에요. 지역을 고르거나 이름·주소로 검색하면 보호센터의 주소, 전화번호, 보호하는 동물 종류를 바로 볼 수 있어요.</p>
<p>잃어버린 반려동물을 찾고 있다면 가까운 보호센터부터 전화로 확인해 보세요. 공고 기간(보통 10일)이 지나면 입양이나 다른 절차로 넘어갈 수 있어서, 하루라도 빨리 연락하는 게 좋아요. 입양을 고민 중이라면 방문 전에 운영 시간과 입양 상담 가능 여부를 먼저 물어보세요.</p>
<div id='rn-app' data-app='shelters'></div>""", "농림축산식품부 농림축산검역본부 동물보호센터 정보"),
    ("hospitals", "우리 동네 동물병원 찾기", """
<p>현재 영업 중으로 등록된 전국 동물병원 목록이에요. 지역을 고른 뒤 동네 이름이나 병원 이름으로 검색해 보세요. 주소를 누르면 지도에서 위치를 볼 수 있어요.</p>
<p>밤이나 주말에 급하게 진료가 필요하면 방문 전에 전화로 진료 시간과 응급 진료 가능 여부를 꼭 확인하세요. 처음 가는 병원이라면 예방접종 기록과 먹고 있는 약을 챙겨 가면 진료가 빨라요.</p>
<div id='rn-app' data-app='hospitals'></div>""", "행정안전부 동물병원 인허가 정보"),
    ("pet-travel", "반려동물 동반 여행지·식당·숙소", """
<p>반려동물과 함께 갈 수 있는 전국의 관광지, 식당, 숙소, 문화시설 목록이에요. 지역과 종류를 골라 보세요.</p>
<p>장소마다 동반 가능한 크기, 목줄·이동장 규칙, 실내 입장 여부가 달라요. 출발 전에 전화로 오늘 동반이 가능한지 확인하고, 배변 봉투와 물, 리드줄은 꼭 챙기세요.</p>
<div id='rn-app' data-app='travel'></div>""", "한국관광공사 반려동물 동반여행 정보"),
    ("lost-pets", "실종 동물 신고 목록", """
<p>국가동물보호정보시스템에 올라온 최근 분실(실종) 신고 목록이에요. 길에서 이 아이들을 봤다면 신고된 연락처나 관할 기관으로 알려 주세요.</p>
<p>반려동물을 잃어버렸다면 바로 국가동물보호정보시스템에 분실 신고를 하고, 가까운 동물보호센터의 보호 공고를 매일 확인하세요. 동물등록이 되어 있으면 보호소에서 주인을 찾기가 훨씬 쉬워요.</p>
<div id='rn-app' data-app='lost'></div>""", "농림축산식품부 농림축산검역본부 분실동물 정보"),
]


def main():
    tok = access_token()
    existing = {p.get("url", "").rsplit("/", 1)[-1]: p for p in api("GET", "pages", tok, params={"status": "live"}).get("items", [])}
    for slug, title, body, src in PAGES:
        if slug + ".html" in existing:
            print("이미 있음", slug)
            continue
        content = body.strip() + "\n" + SRC.format(src=src)
        p = api("POST", "pages", tok, {"title": slug.replace("-", " "), "content": content})
        api("PATCH", f"pages/{p['id']}", tok, {"title": title})
        print("만듦", p.get("url"), title)


if __name__ == "__main__":
    main()
