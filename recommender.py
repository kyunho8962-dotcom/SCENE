"""Computes a fresh ranking from the selected viewing conditions."""
from database import MovieDatabase
from models import (
    MOODS, TIMES, WEIGHTS,
    Movie, RecommendationResult, ScoreBreakdown, ViewingPreferences,
)


class RecommendationEngine:
    def __init__(self, database: MovieDatabase) -> None:
        self._database = database

    @staticmethod
    def _score(movie: Movie, preferences: ViewingPreferences) -> ScoreBreakdown:
        return ScoreBreakdown(
            mood=movie.mood_fit[preferences.mood] * WEIGHTS["mood"] // 5,
            time=movie.time_fit[preferences.time] * WEIGHTS["time"] // 5,
            company=movie.company_fit[preferences.company] * WEIGHTS["company"] // 5,
            runtime=WEIGHTS["runtime"],
        )

    @staticmethod
    def _explain(movie: Movie, preferences: ViewingPreferences, scores: ScoreBreakdown) -> str:
        mood = MOODS[preferences.mood]
        company = "혼자" if preferences.company == "alone" else "함께"
        context = f"{TIMES[preferences.time]}에 {company} 보는 상황"
        mood_detail = (
            f"선택한 기분 ‘{mood}’에 잘 어울려요."
            if scores.mood >= 40 else f"선택한 기분 ‘{mood}’에는 {scores.mood}/50점이에요."
        )
        viewing_points = scores.time + scores.company
        context_detail = (
            f"{context}에도 잘 맞아요."
            if viewing_points >= 32 else f"{context}에는 {viewing_points}/40점이에요."
        )
        runtime_detail = (
            f"{movie.runtime}분으로 {preferences.max_runtime}분 이내예요."
            if preferences.max_runtime is not None else f"상영 시간은 {movie.runtime}분이에요."
        )
        return f"{movie.atmosphere}의 작품이에요. {mood_detail} {context_detail} {runtime_detail}"

    def recommend(
        self, preferences: ViewingPreferences, *, offset: int = 0, limit: int = 3
    ) -> tuple[RecommendationResult, ...]:
        if offset < 0 or limit < 1:
            raise ValueError("추천 시작 위치와 개수를 확인하세요.")

        return tuple(
            RecommendationResult(movie, scores, self._explain(movie, preferences, scores))
            for movie, scores in self.rank(preferences)[offset:offset + limit]
        )

    def rank(self, preferences: ViewingPreferences) -> list[tuple[Movie, ScoreBreakdown]]:
        """Score and sort eligible films before building any recommendation cards."""
        scored = [
            (movie, self._score(movie, preferences))
            for movie in self._database.eligible(preferences.max_runtime)
        ]
        scored.sort(key=lambda entry: (-entry[1].total, -entry[1].mood, entry[0].imdb_id))
        return scored
