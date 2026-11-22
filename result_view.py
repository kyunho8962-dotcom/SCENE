"""HTML fragments for the editorial result screen."""
import base64
from html import escape

from media import Artwork, MovieMedia
from models import FIT_LABELS, PreferenceScore, RecommendationResult, WEIGHTS

FACTORS = {"mood": "기분", "time": "시간대", "company": "관람 형태", "runtime": "러닝타임"}


def _image(artwork: Artwork, alt: str, class_name: str) -> str:
    data = base64.b64encode(artwork.data).decode("ascii")
    return f'<img class="{class_name}" src="data:{artwork.content_type};base64,{data}" alt="{escape(alt)}">'


def _external_value(value: str | None, suffix: str = "") -> str:
    return escape(value) + suffix if value else '<span class="rating-unavailable">정보 없음</span>'


def feature(result: RecommendationResult, media: MovieMedia, label: str) -> str:
    movie = result.movie
    title = f"""
        <div class="feature-title">
          <p>{escape(label)}</p>
          <h1 id="feature-title">{escape(movie.title)}</h1>
        </div>
    """
    still = ""
    if media.backdrop:
        still_credit = (
            '<figcaption>스틸컷 © Studio Ghibli 및 해당 작품 권리자</figcaption>'
            if media.uses_ghibli_still else "<figcaption>배경 이미지 · TMDB</figcaption>"
        )
        still = f"""
            <figure class="feature-scene">
              {_image(media.backdrop, movie.title + (" 스틸컷" if media.uses_ghibli_still else " 배경 이미지"), "feature-backdrop")}
              {title}
              {still_credit}
            </figure>
        """

    poster = _image(media.poster, movie.title + " 포스터", "feature-poster") if media.poster else ""
    layout = "with-still" if still else "without-still"
    if poster:
        layout += " with-poster"

    original_title = movie.original_title
    if original_title == movie.title and movie.international_title:
        original_title = movie.international_title
    meta = escape(" · ".join((str(movie.year), " / ".join(movie.genres), f"{movie.runtime}분")))
    return f"""
        <article class="result-feature {layout}" aria-labelledby="feature-title">
          {still}
          <div class="feature-profile">
            {poster}
            <div class="feature-details">
              {title if not still else ""}
              <p class="feature-original">{escape(original_title)}</p>
              <p class="feature-meta">{meta}</p>
              <dl class="feature-ratings">
                <div class="rating-scene">
                  <dt>SCENE 적합도</dt>
                  <dd>{result.scores.total}<small>/100</small></dd>
                </div>
                <div>
                  <dt><a href="https://www.imdb.com/title/{movie.imdb_id}/" target="_blank" rel="noopener noreferrer">IMDb</a></dt>
                  <dd>{_external_value(media.imdb, '<small>/10</small>')}</dd>
                </div>
                <div>
                  <dt>Rotten Tomatoes</dt>
                  <dd>{_external_value(media.rotten_tomatoes)}</dd>
                </div>
              </dl>
            </div>
          </div>
        </article>
    """


def story(result: RecommendationResult, media: MovieMedia) -> str:
    movie = result.movie
    synopsis = media.synopsis or movie.synopsis or movie.description
    source = "TMDB 한국어 줄거리" if media.synopsis else "SCENE 작품 소개"
    tags = " · ".join(movie.mood_tags)
    return f"""
        <div class="film-editorial">
          <section aria-labelledby="synopsis-title">
            <h2 id="synopsis-title">줄거리</h2>
            <p>{escape(synopsis)}</p>
            <small>{source}</small>
          </section>
          <section aria-labelledby="film-style-title">
            <h2 id="film-style-title">영화의 분위기와 특징</h2>
            <p>{escape(movie.visual_style)} {escape(movie.emotional_tone)}</p>
            <small>{escape(" · ".join(filter(None, (movie.pacing_label, tags, "주제 " + " · ".join(movie.themes) if movie.themes else ""))))} · SCENE 큐레이션</small>
          </section>
        </div>
    """


def rationale(result: RecommendationResult) -> str:
    items = []
    if isinstance(result.scores, PreferenceScore):
        factors = [(FIT_LABELS[item.kind], item.points, item.maximum, item.evidence)
                   for item in result.scores.components]
    else:
        factors = [(label, getattr(result.scores, name), WEIGHTS[name], "") for name, label in FACTORS.items()]
    for label, value, maximum, evidence in factors:
        items.append(f"""
            <li>
              <span>{label}</span><strong>{value}<small> / {maximum}</small></strong>
              <meter min="0" max="{maximum}" value="{value}" aria-label="{label} 적합도">{value}/{maximum}</meter>
              {f'<small class="factor-evidence">{escape(evidence)}</small>' if evidence else ""}
            </li>
        """)
    return f"""
        <section class="result-rationale" aria-labelledby="rationale-title">
          <div>
            <h2 id="rationale-title">왜 이 영화를 추천하나요?</h2>
            <p>{escape(result.reason)}</p>
            <p class="scoring-note">확인한 조건에만 100점을 나눠 배정해요. 제외 조건과 러닝타임 상한은 먼저 후보에 적용해요.</p>
          </div>
          <ul aria-label="적합도 점수 세부 내역">{"".join(items)}</ul>
        </section>
    """


def alternatives(items: tuple[RecommendationResult, ...], details: tuple[MovieMedia, ...]) -> str:
    cards = []
    for result, media in zip(items, details):
        movie = result.movie
        poster = _image(media.poster, movie.title + " 포스터", "alternate-poster") if media.poster else ""
        synopsis = media.synopsis or movie.synopsis or movie.description
        cards.append(f"""
            <article class="result-alternate{' with-poster' if poster else ''}">
              {poster}
              <div>
                <h3>{escape(movie.title)}</h3>
                <p class="alternate-meta">{movie.runtime}분 <span>SCENE <strong>{result.scores.total}</strong><small>/100</small></span></p>
                <dl class="alternate-copy">
                  <dt>줄거리</dt><dd>{escape(synopsis)}</dd>
                  <dt>영화의 특징</dt><dd>{escape(movie.visual_style or movie.atmosphere)}</dd>
                  <dt>추천 이유</dt><dd>{escape(result.reason)}</dd>
                </dl>
              </div>
            </article>
        """)
    comparison = ""
    if len(items) == 2 and all(item.movie.pacing for item in items):
        left, right = (item.movie for item in items)
        comparison = (
            f'<p class="alternate-comparison"><strong>이런 점이 달라요</strong> '
            f'{escape(left.title)}의 {escape(left.pacing_label)} · '
            f'{escape(right.title)}의 {escape(right.pacing_label)}</p>'
        )
    return f"""
        <section class="result-alternatives" aria-labelledby="alternatives-title">
          <h2 id="alternatives-title">함께 살펴볼 영화</h2>
          {comparison}
          <div class="alternate-grid">{"".join(cards)}</div>
        </section>
    """
