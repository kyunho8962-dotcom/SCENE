"""Measure recommendation processing on the local catalog, with an optional C++ ranking comparison."""
import argparse
from pathlib import Path
import platform
from statistics import mean, median
import subprocess
from time import perf_counter_ns

from database import MovieDatabase
from models import COMPANIONS, MOODS, TIMES, ViewingPreferences
from recommender import RecommendationEngine

SCENARIOS = {
    "편안함 / 낮 / 함께 / 100분": ViewingPreferences("relax", "day", "together", 100),
    "감성 / 새벽 / 혼자 / 120분": ViewingPreferences("reflect", "late", "alone", 120),
    "설렘 / 밤 / 함께 / 제한 없음": ViewingPreferences("joy", "night", "together", None),
    "긴장감 / 새벽 / 혼자 / 제한 없음": ViewingPreferences("thrill", "late", "alone", None),
}


def measure(operation) -> str:
    scenarios = tuple(SCENARIOS.values())
    for index in range(100):
        operation(scenarios[index % len(scenarios)])

    samples = []
    for index in range(1_000):
        preferences = scenarios[index % len(scenarios)]
        start = perf_counter_ns()
        operation(preferences)
        samples.append(perf_counter_ns() - start)

    p95 = sorted(samples)[949]
    return f"평균 {mean(samples) / 1_000:.2f} µs · 중앙값 {median(samples) / 1_000:.2f} µs · p95 {p95 / 1_000:.2f} µs"


def compare_cpp(executable: Path, database: MovieDatabase, engine: RecommendationEngine) -> None:
    # Load the same JSON in Python, then send the numeric fields to C++ before timing.
    rows = [str(len(database.movies))]
    for movie in database.movies:
        values = (movie.imdb_id, movie.runtime, *(movie.mood_fit[key] for key in MOODS),
                  *(movie.time_fit[key] for key in TIMES), *(movie.company_fit[key] for key in COMPANIONS))
        rows.append(" ".join(map(str, values)))
    for choice in SCENARIOS.values():
        values = (list(MOODS).index(choice.mood), list(TIMES).index(choice.time),
                  list(COMPANIONS).index(choice.company), choice.max_runtime or 0)
        rows.append(" ".join(map(str, values)))
    completed = subprocess.run(
        [str(executable.resolve())], input="\n".join(rows) + "\n", text=True,
        encoding="ascii", check=True, capture_output=True,
    )
    *rankings, timing = completed.stdout.splitlines()
    expected = [
        [f"{movie.imdb_id},{score.mood},{score.time},{score.company},{score.runtime}"
         for movie, score in engine.rank(choice)]
        for choice in SCENARIOS.values()
    ]
    if [row.split() for row in rankings] != expected:
        raise RuntimeError("C++과 Python의 순위 또는 세부 점수가 일치하지 않습니다.")
    average, middle, p95, _checksum = timing.split()
    print("비교 범위 · 후보 필터링, 점수 계산, 정렬 · 모든 후보의 순위 및 세부 점수 일치")
    print("Python  " + measure(engine.rank))
    print(f"C++     평균 {average} µs · 중앙값 {middle} µs · p95 {p95} µs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpp", type=Path, help="compiled companion benchmark executable")
    args = parser.parse_args()
    database = MovieDatabase()
    engine = RecommendationEngine(database)
    print(f"Python {platform.python_version()} · {platform.system()} {platform.release()} {platform.machine()}")
    print(f"영화 {len(database.movies)}편 · 조건별 250회 · 총 1,000회")
    for label, preferences in SCENARIOS.items():
        results = engine.recommend(preferences)
        picks = ", ".join(f"{item.movie.title} ({item.scores.total})" for item in results)
        print(f"{label} · 후보 {len(database.eligible(preferences.max_runtime))}편 · {picks}")
    print("Python (추천 이유 포함)  " + measure(engine.recommend))
    if args.cpp:
        compare_cpp(args.cpp, database, engine)


if __name__ == "__main__":
    main()
