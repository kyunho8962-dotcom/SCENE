"""Compute 100-point fit from only the requested criteria."""
from models import COMPANIONS, TIMES, FilmPreferences, FitComponent, Movie, PreferenceScore


def _tags(wanted: tuple[str, ...], actual) -> tuple[float, str]:
    matches = [tag for tag in wanted if tag in actual]
    return len(matches) / len(wanted), " · ".join(matches) if matches else "일치 항목 없음"


def _similarity(movie: Movie, reference: Movie) -> tuple[float, str]:
    pairs = (
        (movie.genre_tags, reference.genre_tags, .25),
        (set(movie.mood_tags), set(reference.mood_tags), .35),
        (set(movie.themes), set(reference.themes), .25),
        (set(movie.focus_tags + movie.pace_tags), set(reference.focus_tags + reference.pace_tags), .15),
    )
    overlap = 0.0
    comparable = 0.0
    shared = []
    for own, other, weight in pairs:
        if own or other:
            common = own & other
            overlap += weight * len(common) / len(own | other)
            comparable += weight
            shared.extend(sorted(common))
    detail = " · ".join(shared[:4]) if shared else "공통 분류 없음"
    score = overlap / comparable if comparable else 0
    if movie.imdb_id in reference.similar_movies:
        score = min(1, score + .10)
        detail += " · 카탈로그 유사 작품"
    return score, f"{reference.title}과 공통 · {detail}"


def score_preferences(movie: Movie, prefs: FilmPreferences, reference: Movie | None) -> PreferenceScore:
    factors = []
    for name, weight, requested, actual in (
        ("genre", 5, prefs.genres, movie.genre_tags),
        ("mood", 5, prefs.moods, movie.mood_tags),
        ("focus", 3, prefs.focus, movie.focus_tags),
        ("pace", 3, prefs.pace, movie.pace_tags),
    ):
        if requested:
            factors.append((name, weight, *_tags(requested, actual)))
    if prefs.max_runtime is not None:
        factors.append(("runtime", 2, 1, f"{movie.runtime}분 · {prefs.max_runtime}분 이하"))
    if prefs.time:
        factors.append(("time", 2, movie.time_fit.get(prefs.time, 0) / 5, TIMES.get(prefs.time, "")))
    if prefs.company:
        factors.append(("company", 2, movie.company_fit.get(prefs.company, 0) / 5, COMPANIONS.get(prefs.company, "")))
    if reference:
        factors.append(("similarity", 6, *_similarity(movie, reference)))
    if not factors:
        return PreferenceScore((FitComponent("excluded", 100, 100, "요청한 제외 조건을 통과했어요."),)
                               if prefs.has_exclusions else ())

    weights = sum(row[1] for row in factors)
    maxima = [weight * 100 // weights for _, weight, _, _ in factors]
    largest_remainders = sorted(range(len(factors)), key=lambda index: -(factors[index][1] * 100 % weights))
    for index in largest_remainders[:100 - sum(maxima)]:
        maxima[index] += 1
    return PreferenceScore(tuple(
        FitComponent(name, round(maximum * fit), maximum, evidence)
        for (name, _, fit, evidence), maximum in zip(factors, maxima)
    ))
