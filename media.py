"""Optional enrichment. The recommendation engine never calls these providers."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http.client import HTTPException
from pathlib import Path
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STATIC = Path(__file__).parent / "static"
IMAGE_LIMIT = 2_000_000
TMDB_IMAGE = "https://image.tmdb.org/t/p"


@dataclass(frozen=True)
class MovieMedia:
    poster: bytes | None = None
    backdrop: bytes | None = None
    imdb: str | None = None
    rotten_tomatoes: str | None = None
    uses_ghibli_still: bool = False


def _download(url: str, maximum: int, headers: dict[str, str] | None = None) -> bytes:
    request = Request(url, headers={"User-Agent": "SCENE/1.0", **(headers or {})})
    with urlopen(request, timeout=2.5) as response:
        content = response.read(maximum + 1)
    return content if len(content) <= maximum else b""


def _json(url: str, headers: dict[str, str] | None = None) -> dict:
    try:
        payload = json.loads(_download(url, 500_000, headers))
    except (OSError, ValueError, HTTPException):
        return {}
    return payload if isinstance(payload, dict) else {}


def _tmdb_image(path: object, width: str) -> bytes | None:
    if not isinstance(path, str) or not re.fullmatch(r"/[\w-]+\.jpg", path, re.ASCII):
        return None
    try:
        content = _download(f"{TMDB_IMAGE}/{width}{path}", IMAGE_LIMIT)
    except (OSError, HTTPException):
        return None
    return content if content.startswith(b"\xff\xd8") else None


def _tmdb_images(imdb_id: str, token: str) -> tuple[bytes | None, bytes | None]:
    if not token:
        return None, None
    data = _json(
        f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id",
        {"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    movies = data.get("movie_results")
    if not isinstance(movies, list) or not movies or not isinstance(movies[0], dict):
        return None, None
    movie = movies[0]
    return _tmdb_image(movie.get("poster_path"), "w342"), _tmdb_image(movie.get("backdrop_path"), "w780")


def _omdb_ratings(imdb_id: str, key: str) -> tuple[str | None, str | None]:
    if not key:
        return None, None
    data = _json("https://www.omdbapi.com/?" + urlencode({"i": imdb_id, "apikey": key}))
    if data.get("Response") != "True" or data.get("imdbID") != imdb_id:
        return None, None
    score = data.get("imdbRating")
    imdb = score if isinstance(score, str) and re.fullmatch(r"(?:[0-9](?:\.[0-9])?|10(?:\.0)?)", score) else None
    ratings = data.get("Ratings")
    tomato = None
    if isinstance(ratings, list):
        for rating in ratings:
            if isinstance(rating, dict) and rating.get("Source") == "Rotten Tomatoes":
                score = rating.get("Value")
                if isinstance(score, str) and re.fullmatch(r"(?:[0-9]{1,2}|100)%", score):
                    tomato = score
                    break
    return imdb, tomato


def _load_movie(imdb_id: str, still_file: str, tmdb_token: str, omdb_key: str) -> MovieMedia:
    poster, backdrop = _tmdb_images(imdb_id, tmdb_token)
    imdb, tomatoes = _omdb_ratings(imdb_id, omdb_key)
    uses_ghibli_still = False
    if backdrop is None and still_file:
        try:
            backdrop = (STATIC / still_file).read_bytes()
            uses_ghibli_still = True
        except OSError:
            pass
    return MovieMedia(poster, backdrop, imdb, tomatoes, uses_ghibli_still)


def load_media(
    films: tuple[tuple[str, str], ...], tmdb_token: str, omdb_key: str
) -> tuple[MovieMedia, ...]:
    if not tmdb_token and not omdb_key:
        return tuple(_load_movie(imdb_id, still, "", "") for imdb_id, still in films)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = [
            pool.submit(_load_movie, imdb_id, still, tmdb_token, omdb_key)
            for imdb_id, still in films
        ]
        return tuple(result.result() for result in results)
