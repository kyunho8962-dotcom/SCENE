from pathlib import Path

import dotenv
from streamlit.testing.v1 import AppTest

from database import MovieDatabase
from models import ViewingPreferences
from recommender import RecommendationEngine

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_ui_recommends_explores_and_preserves_editable_conditions(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("TMDB_READ_TOKEN", raising=False)
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    app = AppTest.from_file(str(APP))
    app.secrets["TMDB_READ_TOKEN"] = ""
    app.secrets["OMDB_API_KEY"] = ""
    app.run()
    assert not app.exception
    assert len(app.selectbox) == 4

    app.button[0].click().run()
    assert not app.exception
    html = " ".join(element.proto.body for element in app.get("html"))
    assert html.count('class="movie-card ') == 3
    assert "이웃집 토토로" in html and "정보 없음" in html

    app.button[1].click().run()
    assert not app.exception
    assert app.session_state.offset == 3

    app.button[0].click().run()
    assert not app.exception
    assert app.selectbox(key="runtime").value == "100분 이하"
    app.selectbox(key="mood").select("thrill")
    app.selectbox(key="time").select("late")
    app.selectbox(key="company").select("alone")
    app.selectbox(key="runtime").select("제한 없음")
    app.button[0].click().run()
    assert not app.exception
    preferences = ViewingPreferences("thrill", "late", "alone", None)
    assert app.session_state.preferences == preferences
    assert app.session_state.offset == 0
    winner = RecommendationEngine(MovieDatabase()).recommend(preferences)[0].movie.title
    assert winner in " ".join(element.proto.body for element in app.get("html"))
