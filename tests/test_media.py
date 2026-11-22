from io import BytesIO
from dataclasses import replace
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from PIL import Image
import pytest

from database import MovieDatabase
import media


@pytest.fixture(autouse=True)
def clear_media_caches():
    media._tmdb_metadata.cache_clear()
    media._omdb_ratings.cache_clear()


def movie(imdb_id):
    return next(item for item in MovieDatabase().movies if item.imdb_id == imdb_id)


def test_keyless_media_uses_local_still_and_logs_missing_credentials(monkeypatch, caplog):
    def unexpected_call(*args, **kwargs):
        raise AssertionError("keyless execution requested the network")

    monkeypatch.setattr(media, "_download", unexpected_call)
    first, second = media.load_media((movie("tt0096283"), movie("tt0338013")), media.Credentials())
    assert first.backdrop.data.startswith(b"\xff\xd8")
    assert first.uses_ghibli_still
    assert first.poster is first.imdb is first.rotten_tomatoes is None
    assert second == media.MovieMedia()
    assert "TMDB credential_missing" in caplog.text
    assert "OMDb credential_missing" in caplog.text


def png(size, color):
    image = BytesIO()
    Image.new("RGB", size, color).save(image, "PNG")
    return image.getvalue()


def test_tmdb_details_paths_mime_and_per_movie_cache(monkeypatch):
    calls = []
    portrait = png((300, 450), "#d11e2a")
    duplicate = png((1280, 720), "#d3202b")
    backdrop = png((1280, 720), "#173be8")

    def download(url, maximum, headers=None):
        calls.append((url, headers))
        if url.endswith("/movie/38/images"):
            return json.dumps({"backdrops": [
                {"file_path": path, "width": width, "height": height, "iso_639_1": lang}
                for path, width, height, lang in (
                    ("/legacy.png", 800, 1200, None), ("/poster.png", 1920, 1080, None),
                    ("/duplicate.png", 1920, 1080, None), ("/scene.png", 1280, 720, None),
                    ("/text.png", 1920, 1080, "en"),
                )
            ]}).encode()
        if url.startswith(media.TMDB_API):
            return json.dumps({
                "id": 38, "imdb_id": "tt0338013", "poster_path": "/poster.png", "backdrop_path": "/legacy.png",
                "original_title": "Eternal Sunshine of the Spotless Mind", "release_date": "2004-03-19",
                "overview": "두 사람은 기차에서 만나요. 서로의 이야기를 들어요. 마지막 문장은 잘라요.",
            }).encode()
        return {"/poster.png": portrait, "/duplicate.png": duplicate, "/scene.png": backdrop}[
            "/" + url.rsplit("/", 1)[-1]
        ]

    monkeypatch.setattr(media, "_download", download)
    config = media.Credentials(tmdb_token="test-token")
    films = (movie("tt0338013"),)
    first, = media.load_media(films, config)
    second, = media.load_media(films, config)
    assert first == second
    assert first.poster.content_type == first.backdrop.content_type == "image/png"
    assert first.backdrop.data == backdrop
    assert first.synopsis == "두 사람은 기차에서 만나요. 서로의 이야기를 들어요."
    assert calls == [
        (media.TMDB_API + "/movie/38?language=ko-KR", {"Authorization": "Bearer test-token", "Accept": "application/json"}),
        (media.TMDB_IMAGE + "/w342/poster.png", None),
        (media.TMDB_API + "/movie/38/images", {"Authorization": "Bearer test-token", "Accept": "application/json"}),
        (media.TMDB_IMAGE + "/w1280/duplicate.png", None),
        (media.TMDB_IMAGE + "/w1280/scene.png", None),
    ]


def test_manual_backdrop_preferred_but_never_reuses_poster(monkeypatch):
    film = replace(movie("tt0338013"), backdrop_override="/chosen.png")
    poster = media.Artwork(png((300, 450), "red"), "image/png")
    distinct = media.Artwork(png((1280, 720), "blue"), "image/png")
    duplicate = media.Artwork(png((1280, 720), "red"), "image/png")
    monkeypatch.setattr(media, "_tmdb_request", lambda *args: {"backdrops": []})
    monkeypatch.setattr(media, "_tmdb_image", lambda *args: distinct)
    assert media._choose_backdrop(film, media.Credentials(), {"id": 38, "poster_path": "/poster.png"}, poster) == distinct
    monkeypatch.setattr(media, "_tmdb_image", lambda *args: duplicate)
    assert media._choose_backdrop(film, media.Credentials(),
                                  {"id": 38, "poster_path": "/poster.png", "backdrop_path": "/poster.png"}, poster) is None


def test_tmdb_search_fallback_checks_original_year_and_external_id(monkeypatch):
    film = replace(movie("tt1798709"), tmdb_id=None)
    calls = []

    def download(url, maximum, headers=None):
        path = urlsplit(url).path
        query = parse_qs(urlsplit(url).query)
        assert query["api_key"] == ["test-v3-key"]
        calls.append(path)
        if path == f"/3/find/{film.imdb_id}":
            assert query["external_source"] == ["imdb_id"]
            return b'{"movie_results":[{"original_title":"Different title","release_date":"2013-01-01"}]}'
        if path == "/3/search/movie":
            assert query["query"] == [film.original_title] and query["year"] == [str(film.year)]
            return json.dumps({"results": [
                {"id": 1, "original_title": "Not the original title", "title": "Her", "release_date": "2013-01-01"},
                {"id": 2, "original_title": "Her", "release_date": "1990-01-01"},
                {"id": 3, "original_title": "Her", "release_date": "2013-01-01"},
                {"id": 4, "original_title": "Her", "release_date": "2013-12-18"},
            ]}).encode()
        if path.endswith("/3"):
            return b'{"imdb_id":"tt0000001"}'
        return b'{"imdb_id":"tt1798709","poster_path":"/identified.jpg"}'

    monkeypatch.setattr(media, "_download", download)
    assert media._tmdb_movie(film, media.Credentials(tmdb_key="test-v3-key"))["poster_path"] == "/identified.jpg"
    assert calls == [f"/3/find/{film.imdb_id}", "/3/search/movie", "/3/movie/3", "/3/movie/4"]


def test_invalid_tmdb_image_body_and_path_are_not_rendered(monkeypatch, caplog):
    monkeypatch.setattr(media, "_download", lambda *args: b"\xff\xd8not-an-image")
    assert media._tmdb_image("/image.jpg", "w342", "poster", "tt0338013") is None
    assert media._tmdb_image("https://untrusted.example/image.jpg", "w342", "poster", "tt0338013") is None
    assert "request_failed operation=poster" in caplog.text
    assert "invalid_image_path operation=poster" in caplog.text


def test_omdb_verified_response_and_cache(monkeypatch, caplog):
    calls = []
    data = {
        "Response": "True", "imdbID": "tt0338013", "imdbRating": "8.4",
        "Ratings": [{"Source": "Rotten Tomatoes", "Value": "93%"}],
    }

    def download(url, maximum, headers=None):
        calls.append(url)
        return json.dumps(data).encode()

    monkeypatch.setattr(media, "_download", download)
    assert media._omdb_ratings("tt0338013", "fixture-key") == ("8.4", "93%")
    assert media._omdb_ratings("tt0338013", "fixture-key") == ("8.4", "93%")
    assert len(calls) == 1
    assert media._omdb_ratings("tt7282468", "fixture-key") == (None, None)
    assert "OMDb movie_id_mismatch" in caplog.text
    data.update(imdbRating="N/A", Ratings=[{"Source": "Rotten Tomatoes", "Value": "N/A"}])
    assert media._omdb_ratings("tt0338013", "other-fixture-key") == (None, None)


@pytest.mark.parametrize(
    ("failure", "log_event"),
    [
        ({"Response": "False", "Error": "Movie not found!"}, "movie_not_found"),
        (HTTPError("https://example.test/?apikey=secret-value", 401, "Unauthorized", {}, None), "auth_failed"),
        (TimeoutError("https://example.test/?apikey=secret-value"), "request_failed"),
    ],
)
def test_omdb_logs_specific_failure_without_exposing_key(monkeypatch, caplog, failure, log_event):
    def download(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return json.dumps(failure).encode()

    monkeypatch.setattr(media, "_download", download)
    assert media._omdb_ratings("tt0338013", "secret-value") == (None, None)
    assert f"OMDb {log_event} operation=ratings imdb_id=tt0338013" in caplog.text
    assert "secret-value" not in caplog.text
