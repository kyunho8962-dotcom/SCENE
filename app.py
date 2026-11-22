"""Streamlit screens for SCENE. Run with: streamlit run app.py."""
import base64
from html import escape
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from database import MovieDatabase
from media import MovieMedia, load_media
from models import (
    COMPANIONS, MOODS, RUNTIME_LIMITS, TIMES, WEIGHTS,
    RecommendationResult, ViewingPreferences,
)
from recommender import RecommendationEngine

ROOT = Path(__file__).parent
DEFAULT = ViewingPreferences("relax", "day", "together", 100)
PAGE_SIZE = 3
RUNTIME_BY_LABEL = {label: maximum for maximum, label in RUNTIME_LIMITS.items()}
FIT_DESCRIPTION = "SCENE 적합도는 선택한 관람 상황과 얼마나 잘 어울리는지를 보여줘요. 작품성 및 외부 평점은 이 점수에 반영되지 않아요."


@st.cache_resource
def catalog() -> MovieDatabase:
    return MovieDatabase()


@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def movie_media(
    films: tuple[tuple[str, str], ...], tmdb_token: str, omdb_key: str
) -> tuple[MovieMedia, ...]:
    return load_media(films, tmdb_token, omdb_key)


def setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(name, "")).strip()
    except FileNotFoundError:
        return ""


def image_tag(image: bytes | None, title: str, kind: str) -> str:
    label = "포스터" if kind == "poster" else "스틸컷"
    if image:
        data = base64.b64encode(image).decode("ascii")
        return f'<img class="film-{kind}" src="data:image/jpeg;base64,{data}" alt="{escape(title)} {label}">'
    return (
        f'<div class="film-{kind} film-fallback">'
        f'<span>{label} 이미지 없음</span></div>'
    )


def show_form() -> None:
    st.html("""
        <section class="scene-hero" aria-labelledby="scene-title">
          <h1 id="scene-title">SCENE<span>.</span></h1>
          <p>지금, 어떤 영화를 보고 싶나요?</p>
        </section>
    """)
    previous = st.session_state.get("preferences", DEFAULT)
    with st.form("viewing_preferences", border=True):
        st.html('<h2 class="form-heading">오늘의 관람 조건</h2>')
        left, right = st.columns(2)
        with left:
            mood = st.selectbox(
                "현재 기분", list(MOODS), index=list(MOODS).index(previous.mood),
                format_func=MOODS.__getitem__, key="mood",
            )
            company = st.selectbox(
                "관람 형태", list(COMPANIONS), index=list(COMPANIONS).index(previous.company),
                format_func=COMPANIONS.__getitem__, key="company",
            )
        with right:
            time = st.selectbox(
                "관람 시간대", list(TIMES), index=list(TIMES).index(previous.time),
                format_func=TIMES.__getitem__, key="time",
            )
            runtime_label = st.selectbox(
                "원하는 러닝타임", list(RUNTIME_BY_LABEL),
                index=list(RUNTIME_BY_LABEL).index(RUNTIME_LIMITS[previous.max_runtime]),
                key="runtime",
            )
        submitted = st.form_submit_button("나에게 맞는 영화 찾기", type="primary", width="stretch")
    if submitted:
        st.session_state.update(
            preferences=ViewingPreferences(mood, time, company, RUNTIME_BY_LABEL[runtime_label]),
            offset=0,
            show_results=True,
        )
        st.rerun()


def show_card(result: RecommendationResult, media: MovieMedia, *, featured_label: str = "") -> None:
    movie, scores = result.movie, result.scores
    title = escape(movie.title)
    original = f'<p class="original">{escape(movie.display_original)}</p>'
    metadata = escape(" · ".join((str(movie.year), f"{movie.runtime}분", " / ".join(movie.genres))))
    imdb = f"{escape(media.imdb)}/10" if media.imdb else "정보 없음"
    tomatoes = escape(media.rotten_tomatoes) if media.rotten_tomatoes else "정보 없음"
    factors = "".join(
        f"<span>{label} <strong>{getattr(scores, name)}/{WEIGHTS[name]}</strong></span>"
        for name, label in (("mood", "기분"), ("time", "시간대"), ("company", "관람 형태"), ("runtime", "러닝타임"))
    )
    heading = "h1" if featured_label else "h3"
    eyebrow = f'<p class="eyebrow">{escape(featured_label)}</p>' if featured_label else ""
    credit = '<small class="still-credit">스틸컷 © Studio Ghibli 및 해당 작품 권리자</small>' if media.uses_ghibli_still else ""
    st.html(f"""
        <article class="movie-card {'featured' if featured_label else 'alternate'}">
          <div class="movie-media">
            {image_tag(media.backdrop, movie.title, "backdrop")}
            {image_tag(media.poster, movie.title, "poster")}
            {credit}
          </div>
          <div class="movie-info">
            <div class="title-line">
              <div>
                {eyebrow}
                <{heading}>{title}</{heading}>
                {original}
              </div>
              <div class="fit-score"><span>SCENE 적합도</span><strong>{scores.total}<small>/100</small></strong></div>
            </div>
            <p class="film-meta">{metadata}</p>
            <div class="ratings"><span>IMDb <b>{imdb}</b></span><span>Rotten Tomatoes <b>{tomatoes}</b></span></div>
            <p class="summary">{escape(movie.description)}</p>
            <div class="reason"><strong>추천 이유</strong><p>{escape(result.reason)}</p></div>
            <div class="score-factors" aria-label="적합도 점수 세부 내역">{factors}</div>
          </div>
        </article>
    """)


def edit_preferences() -> None:
    st.session_state.show_results = False


def show_recommendations(database: MovieDatabase, tmdb_token: str, omdb_key: str) -> None:
    preferences = st.session_state.preferences
    offset = st.session_state.offset
    candidate_count = len(database.eligible(preferences.max_runtime))
    results = RecommendationEngine(database).recommend(preferences, offset=offset, limit=PAGE_SIZE)
    if not results:
        st.warning("조건에 맞는 영화가 없어요. 러닝타임 제한을 늘려 다시 찾을 수 있어요.")
        st.button("조건 변경", on_click=edit_preferences)
        return

    selections = (MOODS[preferences.mood], TIMES[preferences.time], COMPANIONS[preferences.company],
                  RUNTIME_LIMITS[preferences.max_runtime])
    chips = "".join(f"<span>{escape(item)}</span>" for item in selections)
    st.html(f'<div class="result-context"><p>오늘의 관람 조건</p><div>{chips}</div></div>')

    films = tuple((item.movie.imdb_id, item.movie.local_backdrop) for item in results)
    with st.spinner("영화 정보를 불러오는 중…", show_time=False):
        media = movie_media(films, tmdb_token, omdb_key)
    show_card(results[0], media[0], featured_label="가장 잘 맞는 영화" if offset == 0 else "다른 추천")
    st.html(f'<p class="fit-note">{FIT_DESCRIPTION}</p>')
    if len(results) > 1:
        st.html('<h2 class="alternates-title">함께 살펴볼 영화</h2>')
        for column, result, details in zip(st.columns(2), results[1:], media[1:]):
            with column:
                show_card(result, details)

    edit, more = st.columns(2)
    with edit:
        st.button("조건 변경", on_click=edit_preferences, width="stretch")
    with more:
        next_offset = offset + PAGE_SIZE
        if next_offset < candidate_count:
            if st.button("다른 작품 보기", type="primary", width="stretch"):
                st.session_state.offset = next_offset
                st.rerun()
        elif offset and st.button("첫 추천으로 돌아가기", width="stretch"):
            st.session_state.offset = 0
            st.rerun()


def footer(tmdb_token: str, omdb_key: str) -> None:
    st.html('<p class="scene-footer">SCENE <span>·</span> 지금의 기분으로 고르는 한 편</p>')
    with st.expander("추천 기준 및 출처"):
        st.markdown(
            "기분 50점 · 시간대 20점 · 관람 형태 20점 · 러닝타임 10점. "
            "가중치는 개발자가 세운 초기 가설이며 객관적으로 검증하지 않았습니다. "
            "영화별 분위기와 적합도는 개발자가 직접 정의한 큐레이션 값입니다."
        )
        st.markdown(
            "오프라인 스틸컷 제공 · [Studio Ghibli](https://www.ghibli.jp/works/). "
            "시작 화면의 극장 사진은 SCENE용으로 생성한 배경입니다."
        )
        if tmdb_token:
            logo = base64.b64encode((ROOT / "static" / "tmdb.svg").read_bytes()).decode("ascii")
            st.html(f"""
                <div class="source-credit">
                  <a href="https://www.themoviedb.org"><img src="data:image/svg+xml;base64,{logo}" alt="TMDB"></a>
                  <span>This product uses the TMDB API but is not endorsed or certified by TMDB.</span>
                </div>
            """)
        if omdb_key:
            st.markdown("외부 평점 제공 · [OMDb](https://www.omdbapi.com/) ([CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)).")


def main() -> None:
    st.set_page_config(page_title="SCENE · 영화 추천", page_icon="🎞️", layout="wide", menu_items={})
    load_dotenv(ROOT / ".env")
    st.html(ROOT / "style.css")
    st.html("""
        <header class="scene-nav">
          <span class="scene-wordmark">SCENE<span>.</span></span>
          <span class="scene-nav-caption">기분으로 고르는 영화</span>
        </header>
    """)
    try:
        database = catalog()
    except (OSError, TypeError, ValueError):
        st.error("영화 목록을 열 수 없어요. data/movies.json 파일을 확인해 주세요.")
        return

    tmdb_token, omdb_key = setting("TMDB_READ_TOKEN"), setting("OMDB_API_KEY")
    if st.session_state.get("show_results", False):
        show_recommendations(database, tmdb_token, omdb_key)
    else:
        show_form()
    footer(tmdb_token, omdb_key)


if __name__ == "__main__":
    main()
