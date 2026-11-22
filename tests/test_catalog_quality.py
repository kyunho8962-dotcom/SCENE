"""Acceptance criteria fixed before running the expanded-catalog quality evaluation."""
import pytest

from database import MovieDatabase
from film_input import analyze_film_request
from models import FilmPreferences
from recommender import RecommendationEngine

# Every case requires three distinct results, honest 0–100 point accounting,
# the requested constraints in the analysis, and every title satisfying the predicate.
CASES = (
    ("머리 안 쓰고 볼 수 있는 액션 영화", FilmPreferences(genres=("액션",), focus=("부담 없는 관람",)),
     lambda m: "액션" in m.genre_tags and "부담 없는 관람" in m.focus_tags and m.complexity <= 2),
    ("새벽에 혼자 볼 만한 감성적인 영화", FilmPreferences(moods=("여운",), time="late", company="alone"),
     lambda m: "여운" in m.mood_tags and m.time_fit["late"] >= 4 and m.company_fit["alone"] >= 4),
    ("버닝처럼 해석할 거리가 많은 영화", FilmPreferences(moods=("해석거리",), reference_id="tt7282468"),
     lambda m: "해석거리" in m.mood_tags and m.imdb_id != "tt7282468"),
    ("여자친구랑 볼 가벼운 로맨틱 코미디", FilmPreferences(genres=("로맨스", "코미디"), moods=("가벼운",), company="together"),
     lambda m: {"로맨스", "코미디"} <= m.genre_tags and "가벼운" in m.mood_tags and m.company_fit["together"] >= 4),
    ("2시간 이내의 긴장감 있는 스릴러", FilmPreferences(genres=("스릴러",), moods=("긴장감",), max_runtime=120),
     lambda m: m.runtime <= 120 and "스릴러" in m.genre_tags and "긴장감" in m.mood_tags),
    ("무섭지 않으면서 반전이 있는 영화", FilmPreferences(moods=("반전",), avoid_moods=("무서운",)),
     lambda m: "반전" in m.mood_tags and "무서운" not in m.mood_tags and "공포" not in m.genre_tags),
    ("영상미가 아름답고 전개가 느린 영화", FilmPreferences(moods=("영상미",), pace=("느긋한 전개",)),
     lambda m: "영상미" in m.mood_tags and m.pacing == "slow"),
    ("우울할 때 웃을 수 있는 영화", FilmPreferences(moods=("유머",)),
     lambda m: "유머" in m.mood_tags),
)


@pytest.fixture(scope="module")
def database():
    return MovieDatabase()


@pytest.mark.parametrize(("text", "expected", "accept"), CASES, ids=[f"case-{i}" for i in range(1, 9)])
def test_quality_case(database, text, expected, accept):
    actual = analyze_film_request(text, database.movies).preferences
    assert actual == expected
    results = RecommendationEngine(database).recommend(actual)
    assert len({result.movie.imdb_id for result in results}) == 3
    for result in results:
        assert accept(result.movie), result.movie.title
        assert 0 <= result.scores.total <= 100
        assert sum(part.maximum for part in result.scores.components) == 100
        assert result.movie.curator_note in result.reason
        assert any(part.points > 0 and f"{part.points}/{part.maximum}점" in result.reason
                   for part in result.scores.components)
    if expected.reference_id:
        reference = next(movie for movie in database.movies if movie.imdb_id == expected.reference_id)
        assert results[0].movie.imdb_id in reference.similar_movies
        assert all(any(part.kind == "similarity" and part.points > 0 for part in result.scores.components)
                   for result in results)
