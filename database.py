"""Loads the local movie catalog and applies hard eligibility filters."""
import json
from pathlib import Path

from models import Movie

DEFAULT_CATALOG = Path(__file__).parent / "data" / "movies.json"


class MovieDatabase:
    def __init__(self, path: Path = DEFAULT_CATALOG) -> None:
        with Path(path).open(encoding="utf-8") as file:
            self._movies = tuple(Movie(**record) for record in json.load(file))
        ids = {movie.imdb_id for movie in self._movies}
        if len(ids) != len(self._movies):
            raise ValueError("영화 목록에 중복 IMDb ID가 있습니다.")

    @property
    def movies(self) -> tuple[Movie, ...]:
        return self._movies

    def eligible(self, max_runtime: int | None) -> tuple[Movie, ...]:
        if max_runtime is None:
            return self._movies
        return tuple(movie for movie in self._movies if movie.runtime <= max_runtime)
