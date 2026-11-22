import json

import pytest

from database import DEFAULT_CATALOG
from validate_catalog import validate_catalog


def test_release_catalog_has_required_titles_and_varied_metadata():
    movies = validate_catalog().movies
    required = {
        "버닝", "마더", "박쥐", "기생충", "살인의 추억", "올드보이", "아가씨", "헤어질 결심",
        "라라랜드", "이터널 선샤인", "그녀", "비포 선라이즈", "어바웃 타임", "그랜드 부다페스트 호텔",
        "문라이즈 킹덤", "블레이드 러너 2049", "인터스텔라", "컨택트", "듄", "위플래쉬", "소셜 네트워크",
        "나이트크롤러", "프리즈너스", "나를 찾아줘", "겟 아웃", "놉", "에브리씽 에브리웨어 올 앳 원스",
        "월터의 상상은 현실이 된다", "인사이드 아웃", "소울", "업",
    }
    assert required <= {movie.title for movie in movies}
    assert all(movie.tmdb_id and movie.similar_movies for movie in movies)
    assert {movie.pacing for movie in movies} == {"slow", "medium", "fast"}
    assert {1990, 2000, 2010, 2020} <= {movie.year // 10 * 10 for movie in movies}
    assert any("KR" in movie.countries for movie in movies)
    assert any("KR" not in movie.countries for movie in movies)


@pytest.mark.parametrize(("field", "invalid"), [
    ("imdb_id", "tt1216496"),
    ("original_title", None),
    ("tmdb_id", "duplicate"),
    ("runtime", 0),
    ("genre_tags", "미스터리"),
    ("complexity", 6),
    ("emotional_intensity", False),
    ("similar_movies", ["tt9999999"]),
    ("pacing", "very fast"),
])
def test_validation_rejects_invalid_catalog(tmp_path, field, invalid):
    records = json.loads(DEFAULT_CATALOG.read_text(encoding="utf-8"))
    records[0][field] = records[1]["tmdb_id"] if field == "tmdb_id" else invalid
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        validate_catalog(path)
