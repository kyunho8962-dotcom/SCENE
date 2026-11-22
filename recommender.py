"""Computes a fresh ranking from the selected viewing conditions."""
from hashlib import sha256
from database import MovieDatabase
from explainer import RecommendationExplainer
from models import (
    WEIGHTS, FilmPreferences, PreferenceScore,
    Movie, RecommendationResult, ScoreBreakdown, ViewingPreferences,
)
from preference_fit import score_preferences


class RecommendationEngine:
    def __init__(self, database: MovieDatabase) -> None:
        self._database = database
        self._explainer = RecommendationExplainer()

    @staticmethod
    def _score(movie: Movie, preferences: ViewingPreferences) -> ScoreBreakdown:
        return ScoreBreakdown(
            mood=movie.mood_fit[preferences.mood] * WEIGHTS["mood"] // 5,
            time=movie.time_fit[preferences.time] * WEIGHTS["time"] // 5,
            company=movie.company_fit[preferences.company] * WEIGHTS["company"] // 5,
            runtime=WEIGHTS["runtime"],
        )

    def candidates(self, preferences: ViewingPreferences | FilmPreferences) -> tuple[Movie, ...]:
        eligible = self._database.eligible(preferences.max_runtime)
        if isinstance(preferences, FilmPreferences):
            if not preferences.has_conditions:
                return ()
            blocked = tuple(map(set, (preferences.avoid_genres, preferences.avoid_moods,
                                      preferences.avoid_focus, preferences.avoid_pace)))
            return tuple(movie for movie in eligible if movie.imdb_id != preferences.reference_id
                         and all(tags.isdisjoint(actual) for tags, actual in zip(
                             blocked, (movie.genre_tags, movie.mood_tags, movie.focus_tags, movie.pace_tags)
                         )))
        if not preferences.avoid_tags:
            return eligible
        excluded = set(preferences.avoid_tags)
        return tuple(movie for movie in eligible if excluded.isdisjoint(movie.mood_tags))

    def recommend(
        self, preferences: ViewingPreferences | FilmPreferences, *, offset: int = 0, limit: int = 3
    ) -> tuple[RecommendationResult, ...]:
        if offset < 0 or limit < 1:
            raise ValueError("추천 시작 위치와 개수를 확인하세요.")

        return tuple(
            RecommendationResult(movie, scores, self._explainer.explain(movie, preferences, scores))
            for movie, scores in self.rank(preferences)[offset:offset + limit]
        )

    def rank(self, preferences: ViewingPreferences | FilmPreferences) -> list[tuple[Movie, ScoreBreakdown | PreferenceScore]]:
        """Score and sort eligible films before building any recommendation cards."""
        if isinstance(preferences, FilmPreferences):
            reference = next((movie for movie in self._database.movies
                              if movie.imdb_id == preferences.reference_id), None)
            ranked = [(movie, score_preferences(movie, preferences, reference))
                      for movie in self.candidates(preferences)]
            seed = repr(preferences).encode("utf-8")
            return sorted(ranked, key=lambda entry: (
                -entry[1].total, sha256(seed + entry[0].imdb_id.encode("ascii")).digest()
            ))
        scored = [
            (movie, self._score(movie, preferences))
            for movie in self.candidates(preferences)
        ]
        scored.sort(key=lambda entry: (-entry[1].total, -entry[1].mood, entry[0].imdb_id))
        return scored
