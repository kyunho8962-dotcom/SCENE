"""Domain objects shared by the catalog, engine, and UI."""
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping


MOODS = {
    "relax": "편안하고 싶다",
    "reflect": "우울하거나 감성적이다",
    "joy": "설레거나 행복하다",
    "thrill": "긴장감과 자극을 원한다",
}
TIMES = {"day": "낮", "night": "밤", "late": "새벽"}
COMPANIONS = {"alone": "혼자", "together": "다른 사람과 함께"}
RUNTIME_LIMITS = {100: "100분 이하", 120: "120분 이하", None: "제한 없음"}
WEIGHTS = {"mood": 50, "time": 20, "company": 20, "runtime": 10}


@dataclass(frozen=True)
class ViewingPreferences:
    mood: str
    time: str
    company: str
    max_runtime: int | None

    def __post_init__(self) -> None:
        if self.mood not in MOODS or self.time not in TIMES or self.company not in COMPANIONS:
            raise ValueError("알 수 없는 관람 조건입니다.")
        if self.max_runtime not in RUNTIME_LIMITS:
            raise ValueError("알 수 없는 러닝타임 제한입니다.")


@dataclass(frozen=True)
class Movie:
    imdb_id: str
    title: str
    original_title: str
    year: int
    genres: tuple[str, ...]
    runtime: int
    atmosphere: str
    description: str
    mood_fit: Mapping[str, int]
    time_fit: Mapping[str, int]
    company_fit: Mapping[str, int]
    international_title: str = ""
    local_backdrop: str = ""

    def __post_init__(self) -> None:
        if not re.fullmatch(r"tt[0-9]{7,}", self.imdb_id):
            raise ValueError(f"{self.title}의 IMDb ID를 확인하세요.")
        if self.local_backdrop and self.local_backdrop != f"{self.imdb_id}.jpg":
            raise ValueError(f"{self.title}의 로컬 스틸컷 파일명을 확인하세요.")
        if type(self.runtime) is not int or self.runtime <= 0:
            raise ValueError(f"{self.title}의 러닝타임을 확인하세요.")
        for field, options in (
            ("mood_fit", MOODS), ("time_fit", TIMES), ("company_fit", COMPANIONS)
        ):
            scores = dict(getattr(self, field))
            if scores.keys() != options.keys() or any(
                type(score) is not int or not 0 <= score <= 5 for score in scores.values()
            ):
                raise ValueError(f"{self.title}의 {field}는 항목별 0~5점이어야 합니다.")
            object.__setattr__(self, field, MappingProxyType(scores))
        object.__setattr__(self, "genres", tuple(self.genres))

    @property
    def display_original(self) -> str:
        return self.international_title or self.original_title


@dataclass(frozen=True)
class ScoreBreakdown:
    mood: int
    time: int
    company: int
    runtime: int

    @property
    def total(self) -> int:
        return self.mood + self.time + self.company + self.runtime


@dataclass(frozen=True)
class RecommendationResult:
    movie: Movie
    scores: ScoreBreakdown
    reason: str
