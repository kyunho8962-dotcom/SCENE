"""Extract editable film preferences with local Korean keyword rules."""
from dataclasses import dataclass
import re
from typing import Iterable

from models import FilmPreferences, Movie

RULES = {
    "genres": {
        "액션": r"액션|격투|추격전", "코미디": r"코미디|희극|웃긴 영화",
        "로맨스": r"로맨스|로맨틱|연애물|멜로", "미스터리": r"미스터리|추리물|수수께끼",
        "느와르": r"느와르|누아르", "독립영화": r"독립\s*영화|인디\s*(?:영화|작품)", "예술영화": r"예술\s*영화|아트하우스",
        "공포": r"공포(?:물| 영화)?|호러", "스릴러": r"스릴러", "SF": r"(?<![a-z])sf(?![a-z])|공상 ?과학",
        "드라마": r"드라마", "애니메이션": r"애니메이션|애니(?!메이션)",
        "판타지": r"판타지|환상물", "모험": r"모험|어드벤처", "가족": r"가족 ?영화",
        "범죄": r"범죄|하이스트", "뮤지컬": r"뮤지컬|음악 영화",
    },
    "moods": {
        "가벼운": r"가볍|가벼|시간\s*(?:때우|보내)|킬링\s*타임|아무\s*생각\s*없이",
        "오락적": r"오락|시간\s*(?:때우|보내)|킬링\s*타임",
        "유머": r"(?<!이)웃(?:을|긴|기|고|음|는)|유쾌|웃음|재치|(?<!블랙)(?<!블랙 )유머",
        "블랙유머": r"블랙\s*유머|검은\s*유머",
        "따뜻한": r"따뜻|따스|포근|힐링|잔잔",
        "밝은": r"밝|명랑|발랄|경쾌",
        "여운": r"여운|감성|먹먹|뭉클|쓸쓸",
        "슬픈": r"슬프|슬픈|슬퍼|눈물",
        "긴장감": r"긴장|손에\s*땀|스릴(?!러)",
        "무서운": r"무섭|무서|으스스|섬뜩",
        "영상미": r"영상미|색감|미장센|시각적",
        "해석거리": r"해석|곱씹|여러 번 생각|의미를 생각|생각할 거리",
        "반전": r"반전|예상\s*밖의\s*전개",
        "기분전환": r"기분\s*전환|활력|기분\s*풀|기분이\s*나아",
        "정형적 로맨스": r"(?:뻔|흔)한\s*(?:로맨스|멜로|연애물)",
    },
    "focus": {
        "부담 없는 관람": r"부담\s*(?:없이|없는|없게)|아무\s*생각\s*없이|머리(?:를)?\s*안\s*쓰|편하게\s*볼|가볍게\s*볼|시간\s*(?:때우|보내)|킬링\s*타임",
        "높은 집중": r"집중(?:력|해서|해야|이 필요한)|복잡|난해|몰입도\s*높|고도의\s*몰입",
    },
    "pace": {
        "빠른 전개": r"빠른\s*전개|전개(?:가|는)?\s*빠르|속도감|템포(?:가)?\s*빠르",
        "느긋한 전개": r"느긋|느린\s*전개|전개(?:가|는)?\s*(?:느리|느린)|천천히\s*흐르|잔잔",
    },
}
EXCLUSIONS = {"genres": "avoid_genres", "moods": "avoid_moods", "focus": "avoid_focus", "pace": "avoid_pace"}
PATTERNS = tuple((field, label, re.compile(pattern)) for field, rules in RULES.items()
                 for label, pattern in rules.items())
NEGATION = re.compile(r"싫|빼[고줘]|제외|피하고|별로|않(?:은|는|아|고|게|으면서)|않$|아닌|안\s*(?:보고|볼)|없(?:는|고|어)")
SPLIT = re.compile(r"([.!?,;\n]+|보다는|보다(?!가|고|서|도)|말고|지만|그런데|않은데|싫고)")
RUNTIME = re.compile(r"(?<!\d)(?:(\d+)\s*시간(?:\s*(반|\d+\s*분))?|(\d+)\s*분(?:\s*짜리)?)\s*(이내|이하|안(?:에)?|까지|미만|정도|쯤)?")
HOURS = {"한 시간 반": "1시간 반", "두 시간 반": "2시간 반", "한 시간": "1시간", "두 시간": "2시간", "세 시간": "3시간"}
REFERENCE = r"\s*(?:['\"’”])?\s*(?:처럼|같은|(?:와|과|이랑|랑)\s*비슷)"
UNHANDLED = re.compile(r"감독|배우|평점|넷플릭스|디즈니|왓챠|오티티|ott|더빙|자막|청불|[0-9]+\s*(?:년대|분\s*이상|시간\s*이상)")
SITUATIONS = {
    "time": {"late": r"새벽", "night": r"밤에|밤쯤|오늘 밤|저녁", "day": r"낮에|대낮|오후|아침"},
    "company": {"alone": r"혼자", "together": r"(?:여자|남자)?친구(?:랑|와|하고|끼리)|가족과|가족이랑|같이|함께|둘이|데이트"},
}


@dataclass(frozen=True)
class FilmAnalysis:
    preferences: FilmPreferences
    notes: tuple[str, ...] = ()


def _reference(text: str, movies: Iterable[Movie]) -> tuple[str, str | None]:
    aliases = [(title, movie.imdb_id) for movie in movies
               for title in (movie.title, movie.original_title, movie.international_title) if title]
    for title, imdb_id in sorted(aliases, key=lambda item: -len(item[0])):
        prefix = r"(?<!\w)" + r"\s*".join(re.escape(part) for part in title.casefold().split())
        match = re.search(prefix + REFERENCE, text)
        if match:
            return text[:match.start()] + " " + text[match.end():], imdb_id
    return text, None


def _runtime(text: str) -> int | None:
    for numeral, value in HOURS.items():
        text = text.replace(numeral, value)
    for match in RUNTIME.finditer(text):
        hours, extra, minutes, modifier = match.groups()
        if re.match(r"\s*(?:이상|초과|넘)", text[match.end():]):
            continue
        if not modifier and not re.search(r"짜리|보고|볼|러닝타임", text[match.start():match.end() + 10]):
            continue
        total = int(hours or 0) * 60 + int(minutes or "0")
        if extra:
            total += 30 if extra == "반" else int(re.search(r"\d+", extra).group())
        if modifier == "미만":
            total -= 1
        if 1 <= total <= 600:
            return total
    return None


def analyze_film_request(text: str, movies: Iterable[Movie]) -> FilmAnalysis:
    text = " ".join(text.casefold().split())
    remaining, reference = _reference(text, movies)
    parts = SPLIT.split(remaining)
    collected = {field: [] for field in (*RULES, *EXCLUSIONS.values())}
    for index in range(0, len(parts), 2):
        clause = parts[index]
        connector = parts[index + 1] if index + 1 < len(parts) else ""
        # A comparison or explicit rejection applies to the clause on its left.
        contrast_excluded = connector in {"말고", "않은데", "싫고"}
        if connector in {"보다", "보다는"} and index + 2 < len(parts):
            contrast_excluded = any(pattern.search(parts[index + 2]) for _, _, pattern in PATTERNS)
        matches = sorted((match.start(), match.end(), field, label)
                         for field, label, pattern in PATTERNS for match in pattern.finditer(clause))
        for start, end, field, label in matches:
            # The qualified request refers to formulaic romance rather than the whole genre.
            if label == "로맨스" and re.search(RULES["moods"]["정형적 로맨스"], clause):
                continue
            next_start = min((item[0] for item in matches if item[0] >= end), default=len(clause))
            tail = clause[end:next_start]
            negative = (contrast_excluded or NEGATION.search(tail)
                        or re.search(r"(?<!\w)(?:안|전혀)\s*$", clause[:start]))
            if not negative and re.fullmatch(r"\s*(?:고|거나|와|과|또는)\s*", tail):
                following_end = max((item[1] for item in matches if item[0] == next_start), default=next_start)
                boundary = min((item[0] for item in matches if item[0] >= following_end), default=len(clause))
                negative = bool(NEGATION.search(clause[following_end:boundary]))
            target = EXCLUSIONS[field] if negative else field
            if label not in collected[target]:
                collected[target].append(label)

    for field, excluded in EXCLUSIONS.items():
        collected[field] = [label for label in collected[field] if label not in collected[excluded]]
    contextual = {}
    for field, patterns in SITUATIONS.items():
        found = {value for value, pattern in patterns.items() if re.search(pattern, remaining)}
        contextual[field] = next(iter(found)) if len(found) == 1 else None

    preferences = FilmPreferences(**{field: tuple(values) for field, values in collected.items()},
                                  **contextual, max_runtime=_runtime(remaining), reference_id=reference)
    notes = []
    if reference is None and re.search(r"처럼|(?:와|과)\s*비슷", remaining):
        notes.append("카탈로그에서 비교할 작품을 찾지 못했어요. 상세 조건에서 작품을 직접 선택할 수 있어요.")
    if UNHANDLED.search(remaining):
        notes.append("감독·배우, 시청 서비스, 등급, 개봉 시기, 최소 길이 같은 조건은 문장 분석에 포함되지 않아요.")
    if not preferences.has_conditions:
        notes.append("적용할 영화 조건을 찾지 못했어요. 장르나 분위기, 러닝타임을 더 적거나 아래에서 직접 설정해 주세요.")
    return FilmAnalysis(preferences, tuple(notes))
