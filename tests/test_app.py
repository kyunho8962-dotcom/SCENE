import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import dotenv
import pytest
from streamlit.testing.v1 import AppTest

from database import MovieDatabase
import media
from models import FilmPreferences
from test_media import png

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    for key in ("TMDB_READ_TOKEN", "TMDB_API_KEY", "OMDB_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    return AppTest.from_file(str(APP))


def html(app):
    return " ".join(element.proto.body for element in app.get("html"))


def submit(app, text):
    app.text_area(key="film_request").input(text)
    app.button(key="recommend").click().run()
    assert not app.exception
    app.button(key="recommend").click().run()
    assert not app.exception


def test_input_review_editing_and_navigation(app):
    app.run()
    assert len(app.selectbox) == 0
    app.button(key="example_0").click().run()
    assert app.text_area(key="film_request").value == "가볍게 볼 수 있는 액션 영화"
    app.button(key="recommend").click().run()
    assert app.multiselect(key="genres").value == ["액션"]
    assert app.selectbox(key="time").value == "unspecified"
    assert app.number_input(key="max_runtime").value is None
    assert not any(box.label == "현재 기분" for box in app.selectbox)
    app.number_input(key="max_runtime").set_value(120)
    app.button(key="recommend").click().run()
    assert not app.exception
    assert app.session_state.preferences.max_runtime == 120
    assert "120분 이하" in html(app)
    assert "정보 없음" in html(app) and "without-still" in html(app)
    assert 'class="feature-scene"' not in html(app)
    assert "줄거리" in html(app) and "이런 점이 달라요" in html(app)
    app.button[1].click().run()
    assert app.session_state.offset == 3
    app.button[0].click().run()
    assert app.number_input(key="max_runtime").value == 120


def test_unknown_input_requires_review_conditions(app):
    app.run()
    app.text_area(key="film_request").input("그냥 모르겠어")
    app.button(key="recommend").click().run()
    assert any("찾지 못했어요" in notice.value for notice in app.info)
    app.button(key="recommend").click().run()
    assert len(app.warning) == 1
    assert not app.session_state.get("show_results", False)
    app.multiselect(key="genres").set_value(["코미디"])
    app.button(key="recommend").click().run()
    assert app.session_state.preferences == FilmPreferences(genres=("코미디",))
    assert html(app).count("<meter ") == 1


def test_result_shows_provider_art_and_ratings(app, monkeypatch):
    portrait, backdrop = png((300, 450), "red"), png((1280, 720), "blue")
    films = {str(movie.tmdb_id): movie for movie in MovieDatabase().movies}

    def download(url, maximum, headers=None):
        address = urlsplit(url)
        if address.hostname == "api.themoviedb.org":
            if address.path.endswith("/images"):
                return b'{"backdrops":[{"file_path":"/scene.png","width":1280,"height":720}]}'
            film = films[address.path.rsplit("/", 1)[-1]]
            return json.dumps({
                "id": film.tmdb_id, "imdb_id": film.imdb_id, "poster_path": "/poster.png",
                "overview": "두 사람이 처음 만나요. 둘은 영화관으로 향해요.",
                "original_title": film.original_title, "release_date": f"{film.year}-01-01",
            }).encode()
        if address.hostname == "image.tmdb.org":
            return portrait if address.path.endswith("/poster.png") else backdrop
        imdb_id = parse_qs(address.query)["i"][0]
        return json.dumps({
            "Response": "True", "imdbID": imdb_id, "imdbRating": "7.5",
            "Ratings": [{"Source": "Rotten Tomatoes", "Value": "80%"}],
        }).encode()

    monkeypatch.setattr(media, "_download", download)
    app.secrets["TMDB_READ_TOKEN"] = "ui-artwork-fixture"
    app.secrets["OMDB_API_KEY"] = "ui-ratings-fixture"
    app.run()
    submit(app, "가볍게 볼 수 있는 액션 영화")
    body = html(app)
    assert 'class="feature-backdrop" src="data:image/png;base64,' in body
    assert 'class="feature-poster" src="data:image/png;base64,' in body
    assert body.count('class="alternate-poster"') == 2
    assert "배경 이미지 · TMDB" in body and "7.5<small>/10</small>" in body and "<dd>80%</dd>" in body
    assert "두 사람이 처음 만나요." in body and "영화의 분위기와 특징" in body
    assert "ui-ratings-fixture" not in body and "ui-artwork-fixture" not in body
