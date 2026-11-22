"""Validate the complete SCENE release catalog and print its distribution."""
from collections import Counter
import json
from pathlib import Path
import re
import unicodedata

from database import DEFAULT_CATALOG, MovieDatabase
from models import PACING_LABELS

TEXT_FIELDS = ("title", "original_title", "synopsis", "description", "atmosphere",
               "visual_style", "tone", "curator_note", "emotional_tone")
LIST_FIELDS = ("genres", "genre_tags", "mood_tags", "focus_tags", "pace_tags",
               "themes", "similar_movies", "countries")


def _title_key(title: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", title).casefold())


def validate_catalog(path: Path = DEFAULT_CATALOG) -> MovieDatabase:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not 100 <= len(raw) <= 120:
        raise ValueError("전체 카탈로그는 영화 100~120편의 JSON 목록이어야 합니다.")
    seen_titles = set()
    seen_display_titles = set()
    seen_tmdb = set()
    seen_notes = set()
    for record in raw:
        if not isinstance(record, dict):
            raise ValueError("각 영화는 JSON 객체여야 합니다.")
        imdb_id = record.get("imdb_id", "?")
        for field in TEXT_FIELDS:
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"{imdb_id}: {field}가 비어 있습니다.")
        for field in LIST_FIELDS:
            values = record.get(field)
            if (not isinstance(values, list) or (not values and field not in {"focus_tags", "pace_tags"})
                    or any(not isinstance(tag, str) or not tag.strip() or tag.strip() != tag for tag in values)
                    or len(set(values)) != len(values)):
                raise ValueError(f"{imdb_id}: {field} 목록을 확인하세요.")
        if any(re.fullmatch("[A-Z]{2}", code) is None for code in record["countries"]):
            raise ValueError(f"{imdb_id}: 국가 코드 형식을 확인하세요.")
        runtime = record.get("runtime")
        if type(runtime) is not int or not 40 <= runtime <= 300:
            raise ValueError(f"{imdb_id}: 러닝타임은 40~300분이어야 합니다.")
        year = record.get("year")
        if type(year) is not int or not 1900 <= year <= 2099:
            raise ValueError(f"{imdb_id}: 개봉 연도가 유효하지 않습니다.")
        for field in ("complexity", "emotional_intensity"):
            if type(record.get(field)) is not int or not 1 <= record[field] <= 5:
                raise ValueError(f"{imdb_id}: {field}는 1~5 사이 정수여야 합니다.")
        if record.get("pacing") not in PACING_LABELS:
            raise ValueError(f"{imdb_id}: 전개 속도를 확인하세요.")
        pace = record["pacing"]
        expected_pace = [] if pace == "medium" else [PACING_LABELS[pace]]
        complexity = record["complexity"]
        expected_focus = ["부담 없는 관람"] if complexity <= 2 else ["높은 집중"] if complexity >= 4 else []
        if record["pace_tags"] != expected_pace or record["focus_tags"] != expected_focus:
            raise ValueError(f"{imdb_id}: 전개·집중도와 추천 태그가 서로 다릅니다.")
        if not set(record["genres"]) <= set(record["genre_tags"]):
            raise ValueError(f"{imdb_id}: 장르 태그에 기본 장르가 빠졌습니다.")
        key = (_title_key(record["original_title"]), year)
        display_key = (_title_key(record["title"]), year)
        tmdb_id = record.get("tmdb_id")
        if tmdb_id is not None and (type(tmdb_id) is not int or tmdb_id < 1):
            raise ValueError(f"{imdb_id}: TMDB ID는 양의 정수여야 합니다.")
        if key in seen_titles or display_key in seen_display_titles or (tmdb_id is not None and tmdb_id in seen_tmdb):
            raise ValueError(f"{imdb_id}: 같은 작품이 중복 등록됐습니다.")
        seen_titles.add(key)
        seen_display_titles.add(display_key)
        if tmdb_id is not None:
            seen_tmdb.add(tmdb_id)
        if record["curator_note"] in seen_notes:
            raise ValueError(f"{imdb_id}: 작품별 소개가 중복됩니다.")
        seen_notes.add(record["curator_note"])

    database = MovieDatabase(path)
    ids = {movie.imdb_id for movie in database.movies}
    for movie in database.movies:
        if movie.imdb_id in movie.similar_movies or set(movie.similar_movies) - ids:
            raise ValueError(f"{movie.imdb_id}: 유사 작품 참조를 확인하세요.")
    return database


def main() -> None:
    movies = validate_catalog().movies
    print(f"유효한 영화 {len(movies)}편")
    print("장르 분포 (작품별 복수 집계)")
    for genre, count in Counter(genre for movie in movies for genre in movie.genres).most_common():
        print(f"  {genre}: {count}")
    for tag in ("독립영화", "예술영화", "느와르", "로맨틱 코미디", "블록버스터"):
        print(f"  {tag} 큐레이션: {sum(tag in movie.genre_tags for movie in movies)}")
    print("연대:", dict(sorted(Counter(f"{movie.year // 10 * 10}년대" for movie in movies).items())))
    print("한국 제작 참여:", sum("KR" in movie.countries for movie in movies))


if __name__ == "__main__":
    main()
