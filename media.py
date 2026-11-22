"""Optional film artwork and ratings, independent of the recommender."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http.client import HTTPException
from io import BytesIO
import json
import logging
from pathlib import Path
import re
from threading import Condition
from typing import NamedTuple
import unicodedata
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cachetools import TLRUCache, cached
from PIL import Image, ImageChops, ImageOps, ImageStat

from models import Movie

STATIC = Path(__file__).parent / "static"
IMAGE_LIMIT = 2_000_000
TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p"
LOGGER = logging.getLogger(__name__)
IMAGE_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


@dataclass(frozen=True)
class Credentials:
    tmdb_token: str = field(default="", repr=False)
    tmdb_key: str = field(default="", repr=False)
    omdb_key: str = field(default="", repr=False)

    @property
    def has_tmdb(self) -> bool:
        return bool(self.tmdb_token or self.tmdb_key)


@dataclass(frozen=True)
class Artwork:
    data: bytes
    content_type: str


class TMDBMetadata(NamedTuple):
    poster: Artwork | None = None
    backdrop: Artwork | None = None
    synopsis: str | None = None


@dataclass(frozen=True)
class MovieMedia:
    poster: Artwork | None = None
    backdrop: Artwork | None = None
    imdb: str | None = None
    rotten_tomatoes: str | None = None
    uses_ghibli_still: bool = False
    synopsis: str | None = None


def _download(url: str, maximum: int, headers: dict[str, str] | None = None) -> bytes:
    request = Request(url, headers={"User-Agent": "SCENE/1.0", **(headers or {})})
    with urlopen(request, timeout=4) as response:
        content = response.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError("Response size exceeded")
    return content


def _log_failure(provider: str, operation: str, imdb_id: str, error: Exception) -> None:
    # Exception text may contain a URL with credentials. Log only the type or HTTP code.
    if isinstance(error, HTTPError):
        event = "auth_failed" if error.code in (401, 403) else "request_failed"
        LOGGER.warning("%s %s operation=%s imdb_id=%s http_status=%s",
                       provider, event, operation, imdb_id, error.code)
    else:
        LOGGER.warning("%s request_failed operation=%s imdb_id=%s error=%s",
                       provider, operation, imdb_id, type(error).__name__)


def _json(
    provider: str, operation: str, imdb_id: str, url: str, headers: dict[str, str] | None = None
) -> dict | None:
    try:
        payload = json.loads(_download(url, 500_000, headers))
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        return payload
    except (OSError, ValueError, HTTPException) as error:
        _log_failure(provider, operation, imdb_id, error)
        return None


def _tmdb_request(
    movie: Movie, credentials: Credentials, path: str, **params: str | int
) -> dict | None:
    headers = {"Accept": "application/json"}
    if not path.endswith("/images"):
        params.setdefault("language", "ko-KR")
    if credentials.tmdb_token:
        headers["Authorization"] = f"Bearer {credentials.tmdb_token}"
    else:
        params["api_key"] = credentials.tmdb_key
    query = f"?{urlencode(params)}" if params else ""
    return _json("TMDB", path, movie.imdb_id, f"{TMDB_API}/{path}{query}", headers)


def _normalize_title(title: object) -> str:
    if not isinstance(title, str):
        return ""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", title).casefold())


def _original_and_year_match(record: dict, movie: Movie) -> bool:
    return (
        _normalize_title(record.get("original_title")) == _normalize_title(movie.original_title)
        and str(record.get("release_date", ""))[:4] == str(movie.year)
    )


def _records(payload: dict, field: str) -> list[dict]:
    values = payload.get(field)
    return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def _tmdb_movie(movie: Movie, credentials: Credentials) -> dict | None:
    if movie.tmdb_id:
        details = _tmdb_request(movie, credentials, f"movie/{movie.tmdb_id}")
        if details and details.get("imdb_id") == movie.imdb_id and _original_and_year_match(details, movie):
            return details
        if details:
            LOGGER.warning("TMDB movie_id_mismatch imdb_id=%s tmdb_id=%s", movie.imdb_id, movie.tmdb_id)

    found = _tmdb_request(movie, credentials, f"find/{movie.imdb_id}", external_source="imdb_id")
    if found is None:
        return None
    records = _records(found, "movie_results")
    matches = [item for item in records if _original_and_year_match(item, movie)]
    if len(matches) == 1:
        return matches[0]
    if records:
        LOGGER.warning("TMDB movie_identity_mismatch imdb_id=%s year=%s", movie.imdb_id, movie.year)

    search = _tmdb_request(
        movie, credentials, "search/movie", query=movie.original_title, year=movie.year
    )
    if search is None:
        return None
    matches = [item for item in _records(search, "results") if _original_and_year_match(item, movie)]
    for item in matches:
        tmdb_id = item.get("id")
        if type(tmdb_id) is int and tmdb_id > 0:
            details = _tmdb_request(movie, credentials, f"movie/{tmdb_id}")
            if details and details.get("imdb_id") == movie.imdb_id:
                return details
    LOGGER.warning("TMDB movie_not_found imdb_id=%s year=%s", movie.imdb_id, movie.year)
    return None


def _artwork(content: bytes) -> Artwork:
    with Image.open(BytesIO(content)) as image:
        content_type = IMAGE_TYPES.get(image.format)
        if not content_type or image.width * image.height > 8_000_000:
            raise ValueError("Unsupported image")
        image.load()
    return Artwork(content, content_type)


def _tmdb_image(path: object, width: str, operation: str, imdb_id: str) -> Artwork | None:
    if path is None:
        LOGGER.info("TMDB image_unavailable operation=%s imdb_id=%s", operation, imdb_id)
        return None
    if not isinstance(path, str) or not re.fullmatch(r"/[\w-]+\.(?:jpe?g|png|webp)", path, re.ASCII | re.I):
        LOGGER.warning("TMDB invalid_image_path operation=%s imdb_id=%s", operation, imdb_id)
        return None
    try:
        return _artwork(_download(f"{TMDB_IMAGE}/{width}{path}", IMAGE_LIMIT))
    except (OSError, ValueError, HTTPException, Image.DecompressionBombError) as error:
        _log_failure("TMDB", operation, imdb_id, error)
        return None


def _backdrop_paths(images: dict, poster_path: object) -> list[str]:
    candidates = []
    for record in _records(images, "backdrops"):
        width, height, path = record.get("width"), record.get("height"), record.get("file_path")
        if (type(width) is not int or type(height) is not int or width < 960 or height < 480
                or not 1.55 <= width / height <= 2.6 or not isinstance(path, str) or path == poster_path):
            continue
        priority = (bool(record.get("iso_639_1")), abs(width / height - 16 / 9), -min(width, 1920))
        candidates.append((priority, path))
    return list(dict.fromkeys(path for _, path in sorted(candidates)))


def _usable_backdrop(backdrop: Artwork, poster: Artwork | None) -> bool:
    with Image.open(BytesIO(backdrop.data)) as image:
        if image.width < 640 or not 1.55 <= image.width / image.height <= 2.6:
            return False
        if poster is None:
            return True
        background = image.convert("RGB")
    with Image.open(BytesIO(poster.data)) as image:
        cover = image.convert("RGB")
    for preview in (lambda item: item.resize((16, 16)), lambda item: ImageOps.fit(item, (16, 16))):
        difference = ImageChops.difference(preview(background), preview(cover))
        if sum(ImageStat.Stat(difference).mean) / 3 < 20:
            return False
    return True


def _choose_backdrop(movie: Movie, config: Credentials, details: dict, poster: Artwork | None) -> Artwork | None:
    poster_path = details.get("poster_path")
    paths = [movie.backdrop_override] if movie.backdrop_override and movie.backdrop_override != poster_path else []
    tmdb_id = details.get("id")
    if type(tmdb_id) is int and tmdb_id > 0:
        images = _tmdb_request(movie, config, f"movie/{tmdb_id}/images")
        paths.extend(_backdrop_paths(images or {}, poster_path))
    for path in list(dict.fromkeys(paths))[:6]:
        image = _tmdb_image(path, "w1280", "backdrop", movie.imdb_id)
        if image and _usable_backdrop(image, poster):
            return image
    return None


def _expires(_key, pair, now):
    # Retry missing or temporarily unavailable fields sooner than complete responses.
    return now + (3600 if all(value is not None for value in pair) else 120)


def _korean_synopsis(overview: object) -> str | None:
    if not isinstance(overview, str):
        return None
    sentences = re.split(r"(?<=[.!?。])\s+", " ".join(overview.split()))
    if len(sentences) < 2:
        return None
    premise = " ".join(sentences[:2])
    if len(premise) > 340 or not re.search(r"[가-힣]", premise):
        return None
    if re.search(r"결말|반전|정체가 밝혀|범인이 밝혀|죽고 만다|사실은", premise):
        return None
    return premise


@cached(TLRUCache(maxsize=48, ttu=lambda key, value, now: _expires(key, value[:2], now)),
        condition=Condition(),
        key=lambda movie, config: (movie.imdb_id, movie.tmdb_id, movie.original_title, movie.year,
                                   movie.backdrop_override, config.tmdb_token, config.tmdb_key))
def _tmdb_metadata(movie: Movie, config: Credentials) -> TMDBMetadata:
    details = _tmdb_movie(movie, config)
    if details is None:
        return TMDBMetadata()
    poster = _tmdb_image(details.get("poster_path"), "w342", "poster", movie.imdb_id)
    return TMDBMetadata(poster, _choose_backdrop(movie, config, details, poster),
                        _korean_synopsis(details.get("overview")))


@cached(TLRUCache(maxsize=64, ttu=_expires), condition=Condition())
def _omdb_ratings(imdb_id: str, key: str) -> tuple[str | None, str | None]:
    params = urlencode({"i": imdb_id, "type": "movie", "apikey": key})
    data = _json("OMDb", "ratings", imdb_id, f"https://www.omdbapi.com/?{params}")
    if data is None:
        return None, None
    if data.get("Response") != "True":
        error = str(data.get("Error", "")).casefold()
        if "api key" in error:
            event = "auth_failed"
        elif "not found" in error or "incorrect imdb id" in error:
            event = "movie_not_found"
        else:
            event = "request_failed"
        LOGGER.warning("OMDb %s operation=ratings imdb_id=%s", event, imdb_id)
        return None, None
    if data.get("imdbID") != imdb_id:
        LOGGER.warning("OMDb movie_id_mismatch imdb_id=%s", imdb_id)
        return None, None

    score = data.get("imdbRating")
    imdb = score if isinstance(score, str) and re.fullmatch(r"(?:[0-9](?:\.[0-9])?|10(?:\.0)?)", score) else None
    tomato = None
    for rating in _records(data, "Ratings"):
        score = rating.get("Value")
        if rating.get("Source") == "Rotten Tomatoes" and isinstance(score, str):
            if re.fullmatch(r"(?:[0-9]{1,2}|100)%", score):
                tomato = score
                break
    return imdb, tomato


def _load_movie(movie: Movie, config: Credentials) -> MovieMedia:
    poster, backdrop, synopsis = _tmdb_metadata(movie, config) if config.has_tmdb else TMDBMetadata()
    imdb, tomatoes = _omdb_ratings(movie.imdb_id, config.omdb_key) if config.omdb_key else (None, None)
    local = False
    if backdrop is None and movie.local_backdrop:
        try:
            backdrop = _artwork((STATIC / movie.local_backdrop).read_bytes())
            local = True
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            _log_failure("LOCAL", "backdrop", movie.imdb_id, error)
    return MovieMedia(poster, backdrop, imdb, tomatoes, local, synopsis)


def load_media(movies: tuple[Movie, ...], config: Credentials) -> tuple[MovieMedia, ...]:
    if not config.has_tmdb:
        LOGGER.warning("TMDB credential_missing")
    if not config.omdb_key:
        LOGGER.warning("OMDb credential_missing")
    if not config.has_tmdb and not config.omdb_key:
        return tuple(_load_movie(movie, config) for movie in movies)
    with ThreadPoolExecutor(max_workers=3) as pool:
        return tuple(pool.map(_load_movie, movies, (config,) * len(movies)))
