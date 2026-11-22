"""Connect measured fit with manually curated, film-specific observations."""
from models import FIT_LABELS, MOODS, TIMES, FilmPreferences, Movie, PreferenceScore, ScoreBreakdown, ViewingPreferences


class RecommendationExplainer:
    def explain(self, movie: Movie, prefs: ViewingPreferences | FilmPreferences,
                scores: ScoreBreakdown | PreferenceScore) -> str:
        observation = movie.curator_note or f"{movie.atmosphere}의 작품이에요."
        if isinstance(scores, PreferenceScore):
            matches = sorted((item for item in scores.components if item.points),
                             key=lambda item: (item.kind != "similarity", -item.points))
            if matches:
                details = ", ".join(f"{FIT_LABELS[item.kind]} {item.points}/{item.maximum}점 ({item.evidence})"
                                    for item in matches[:3])
                excluded = prefs.avoid_genres + prefs.avoid_moods + prefs.avoid_focus + prefs.avoid_pace
                prefix = f"{' · '.join(excluded)} 제외 조건을 통과했고, " if excluded and matches[0].kind != "excluded" else ""
                return f"{observation} {prefix}요청과 맞닿는 부분은 {details}이에요."
            return f"{observation} 요청과 일치하는 항목의 점수가 낮아요."
        matches = [tag for tag in prefs.mood_tags if tag in movie.mood_tags]
        mood = "·".join(matches) if matches else f"‘{MOODS[prefs.mood]}’"
        context = f"{TIMES[prefs.time]}에 {'혼자' if prefs.company == 'alone' else '함께'}"
        setting_score = scores.time + scores.company
        if scores.mood >= 40 and setting_score >= 32:
            fit = f"{context} 볼 때 {mood} 조건에 잘 맞아요(기분 {scores.mood}/50점, 관람 조건 {setting_score}/40점)."
        elif scores.mood >= 40:
            fit = f"{context} 볼 후보 중 {mood} 조건에서 좋은 점수를 받았어요(기분 {scores.mood}/50점)."
        elif setting_score >= 32:
            fit = f"{mood} 분위기 점수는 {scores.mood}/50점이지만, {context} 보는 조건에서 {setting_score}/40점을 받았어요."
        else:
            length = f"{prefs.max_runtime}분 이내인 {movie.runtime}분" if prefs.max_runtime else f"{movie.runtime}분"
            fit = f"{context} 볼 수 있는 {length}의 작품으로, {mood} 조건의 적합도는 {scores.mood}/50점이에요."
        return f"{observation} {fit}"
