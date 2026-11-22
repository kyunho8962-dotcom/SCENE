"""Streamlit screens for SCENE. Run with: streamlit run app.py."""
import base64
from html import escape
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from database import MovieDatabase
from media import Credentials, load_media
from film_input import EXCLUSIONS, RULES, analyze_film_request
from models import (
    COMPANIONS, TIMES, FilmPreferences,
)
from recommender import RecommendationEngine
import result_view

ROOT = Path(__file__).parent
PAGE_SIZE = 3
UNSPECIFIED = "unspecified"
EXAMPLES = ("가볍게 볼 수 있는 액션 영화", "새벽에 혼자 볼 여운이 긴 영화", "해석할 거리가 많은 미스터리 영화")
TAG_FIELDS = {
    "genres": "선호 장르", "avoid_genres": "제외 장르",
    "moods": "원하는 분위기", "avoid_moods": "피하고 싶은 분위기",
    "focus": "선호 몰입도", "avoid_focus": "피하고 싶은 몰입도",
    "pace": "선호 전개", "avoid_pace": "피하고 싶은 전개",
}
DETAIL_FIELDS = ("time", "company", "reference_id")


@st.cache_resource
def catalog() -> MovieDatabase:
    return MovieDatabase()


def setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(name, "")).strip()
    except FileNotFoundError:
        return ""


def use_example(example: str) -> None:
    st.session_state.film_request = example
    st.session_state.analyzed_text = None
    st.session_state.review_error = ""


def _load_review(preferences: FilmPreferences) -> None:
    state = st.session_state
    for field in TAG_FIELDS:
        state[field] = list(getattr(preferences, field))
    for field in DETAIL_FIELDS:
        state[field] = getattr(preferences, field) or UNSPECIFIED
    state.max_runtime = preferences.max_runtime


def submit_conditions(database: MovieDatabase) -> None:
    state = st.session_state
    text = state.film_request.strip()
    state.review_error = ""
    if not text:
        state.review_error = "보고 싶은 영화를 한 문장으로 적어 주세요."
        return
    if text != state.get("analyzed_text"):
        analysis = analyze_film_request(text, database.movies)
        state.update(analyzed_text=text, analysis=analysis)
        _load_review(analysis.preferences)
        return

    details = {field: state[field] if state[field] != UNSPECIFIED else None for field in DETAIL_FIELDS}
    preferences = FilmPreferences(**{field: tuple(state[field]) for field in TAG_FIELDS},
                                  **details, max_runtime=state.max_runtime)
    if any(set(getattr(preferences, field)) & set(getattr(preferences, blocked))
           for field, blocked in EXCLUSIONS.items()):
        state.review_error = "같은 조건이 선호와 제외에 모두 있어요. 하나를 지워 주세요."
        return
    if not preferences.has_conditions:
        state.review_error = "추천에 적용할 조건이 없어요. 문장을 구체적으로 적거나 분석 결과에서 조건을 추가해 주세요."
        return
    state.update(preferences=preferences, submitted_text=text, offset=0, show_results=True)


def _review(database: MovieDatabase) -> None:
    state = st.session_state
    st.subheader("분석 결과")
    for note in state.analysis.notes:
        st.info(note)
    st.caption("찾은 조건만 채웠어요. 아래에서 고칠 수 있어요. 목록에 없는 표현은 적용되지 않아요.")
    preferred, excluded = st.columns(2)
    for field, blocked in EXCLUSIONS.items():
        with preferred:
            st.multiselect(TAG_FIELDS[field], list(RULES[field]), key=field, placeholder="미지정")
        with excluded:
            st.multiselect(TAG_FIELDS[blocked], list(RULES[field]), key=blocked, placeholder="미지정")
    with st.expander("상세 조건", expanded=bool(state.analysis.preferences.reference_id
                    or state.analysis.preferences.max_runtime or state.analysis.preferences.time
                    or state.analysis.preferences.company)):
        titles = {movie.imdb_id: movie.title for movie in database.movies}
        for field, label, values in (("time", "관람 시간대", TIMES), ("company", "관람 형태", COMPANIONS),
                                     ("reference_id", "비슷한 작품", titles)):
            choices = {UNSPECIFIED: "미지정", **values}
            st.selectbox(label, list(choices), format_func=choices.__getitem__, key=field)
        st.number_input("최대 러닝타임 (분)", min_value=1, max_value=600, step=1, key="max_runtime",
                        placeholder="미지정")


def show_form(database: MovieDatabase) -> None:
    st.html("""
        <section class="scene-hero" aria-labelledby="scene-title">
          <h1 id="scene-title">SCENE<span>.</span></h1>
          <p>지금 어떤 영화가 보고 싶나요?</p>
        </section>
    """)
    state = st.session_state
    if "film_request" not in state:
        state.film_request = state.get("submitted_text", "")
        if state.get("analyzed_text") == state.film_request and "preferences" in state:
            _load_review(state.preferences)

    with st.container(key="viewing_preferences", border=True):
        st.text_area(
            "기분, 장르, 분위기, 관람 상황까지 자유롭게 이야기해 주세요.",
            key="film_request", height=118, max_chars=350, placeholder="예: 영상미가 좋고 여운이 오래 남는 영화",
        )
        with st.container(horizontal=True, gap="small"):
            for index, example in enumerate(EXAMPLES):
                st.button(example, key=f"example_{index}", on_click=use_example, args=(example,))
        reviewed = bool(state.film_request.strip()) and state.film_request.strip() == state.get("analyzed_text")
        if reviewed:
            _review(database)
        if state.get("review_error"):
            st.warning(state.review_error)
        st.button("추천 결과 보기" if reviewed else "나에게 맞는 영화 찾기", key="recommend",
                  type="primary", width="stretch", on_click=submit_conditions, args=(database,))


def edit_preferences() -> None:
    st.session_state.show_results = False


def next_results(candidate_count: int) -> None:
    next_offset = st.session_state.offset + PAGE_SIZE
    st.session_state.offset = next_offset if next_offset < candidate_count else 0


def show_recommendations(database: MovieDatabase, config: Credentials) -> None:
    preferences = st.session_state.preferences
    offset = st.session_state.offset
    engine = RecommendationEngine(database)
    candidate_count = len(engine.candidates(preferences))
    results = engine.recommend(preferences, offset=offset, limit=PAGE_SIZE)
    if not results:
        st.warning("조건에 맞는 영화가 없어요. 러닝타임이나 피하고 싶은 요소를 조정해 주세요.")
        st.button("조건 변경", on_click=edit_preferences)
        return

    selections = [f"{TAG_FIELDS[field]} · {' · '.join(getattr(preferences, field))}"
                  for field in TAG_FIELDS if getattr(preferences, field)]
    if preferences.time:
        selections.append(TIMES[preferences.time])
    if preferences.company:
        selections.append(COMPANIONS[preferences.company])
    if preferences.max_runtime is not None:
        selections.append(f"{preferences.max_runtime}분 이하")
    if preferences.reference_id:
        reference = next((movie.title for movie in database.movies if movie.imdb_id == preferences.reference_id), "")
        selections.append(f"{reference}과 비슷한 작품")
    chips = "".join(f"<span>{escape(item)}</span>" for item in selections)
    with st.container(key="result_controls"):
        context, actions = st.columns([3, 2], vertical_alignment="center")
        with context:
            st.html(f'<div class="result-context" aria-label="오늘의 관람 조건">{chips}</div>')
        with actions:
            with st.container(key="result_buttons"):
                edit, retry = st.columns(2)
                with edit:
                    st.button("조건 변경", on_click=edit_preferences, width="stretch")
                with retry:
                    st.button(
                        "다시 추천받기", type="primary", width="stretch",
                        on_click=next_results, args=(candidate_count,),
                        disabled=candidate_count <= PAGE_SIZE,
                    )

    with st.spinner("영화 정보를 불러오는 중…", show_time=False):
        media = load_media(tuple(item.movie for item in results), config)
    label = "오늘의 추천" if offset == 0 else "다른 추천"
    st.html(result_view.feature(results[0], media[0], label))
    st.html(result_view.story(results[0], media[0]))
    st.html(result_view.rationale(results[0]))
    if len(results) > 1:
        st.html(result_view.alternatives(results[1:], media[1:]))


def footer(config: Credentials) -> None:
    st.html('<p class="scene-footer">SCENE <span>·</span> 지금 보고 싶은 한 편</p>')
    with st.expander("추천 기준 및 출처"):
        st.markdown(
            "확인한 조건에만 100점을 나누어 배정합니다. 러닝타임 상한과 제외 조건은 후보를 걸러냅니다. "
            "영화별 분위기, 몰입도와 전개 속도는 개발자가 정의한 큐레이션 정보입니다."
        )
        st.markdown(
            "오프라인 스틸컷 제공 · [Studio Ghibli](https://www.ghibli.jp/works/). "
            "시작 화면의 극장 사진은 SCENE용으로 생성한 배경입니다."
        )
    if config.has_tmdb:
        logo = base64.b64encode((ROOT / "static" / "tmdb.svg").read_bytes()).decode("ascii")
        st.html(f"""
            <div class="source-credit">
              <a href="https://www.themoviedb.org"><img src="data:image/svg+xml;base64,{logo}" alt="TMDB"></a>
              <span>This product uses the TMDB API but is not endorsed or certified by TMDB.</span>
            </div>
        """)
    if config.omdb_key:
        st.caption("외부 평점 제공 · [OMDb](https://www.omdbapi.com/) ([CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)).")


def main() -> None:
    st.set_page_config(page_title="SCENE · 영화 추천", page_icon="🎞️", layout="wide", menu_items={})
    load_dotenv(ROOT / ".env")
    st.html(ROOT / "style.css")
    st.html("""
        <header class="scene-nav">
          <span class="scene-wordmark">SCENE<span>.</span></span>
          <span class="scene-nav-caption">영화 취향으로 고르는 한 편</span>
        </header>
    """)
    try:
        database = catalog()
    except (OSError, TypeError, ValueError):
        st.error("영화 목록을 열 수 없어요. data/movies.json 파일을 확인해 주세요.")
        return

    config = Credentials(
        tmdb_token=setting("TMDB_READ_TOKEN"),
        tmdb_key=setting("TMDB_API_KEY"),
        omdb_key=setting("OMDB_API_KEY"),
    )
    if st.session_state.get("show_results", False):
        show_recommendations(database, config)
    else:
        show_form(database)
    footer(config)


if __name__ == "__main__":
    main()
