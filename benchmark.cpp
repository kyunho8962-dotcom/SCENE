// Companion benchmark for the same in-memory filter, score, and sort as Python.
#include <algorithm>
#include <array>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>

struct Movie {
    std::string id;
    int runtime;
    std::array<int, 4> moods;
    std::array<int, 3> times;
    std::array<int, 2> company;
};

struct Preferences {
    int mood, time, company, cap;
};

struct Scored {
    const Movie* movie;
    int mood, time, company, runtime;

    int total() const { return mood + time + company + runtime; }
};

std::vector<Scored> rank(const std::vector<Movie>& movies, Preferences choice) {
    std::vector<Scored> scores;
    scores.reserve(movies.size());
    for (const auto& movie : movies) {
        if (choice.cap && movie.runtime > choice.cap) continue;
        scores.push_back({&movie,
            movie.moods[choice.mood] * 50 / 5,
            movie.times[choice.time] * 20 / 5,
            movie.company[choice.company] * 20 / 5,
            10});
    }
    std::sort(scores.begin(), scores.end(), [](Scored a, Scored b) {
        if (a.total() != b.total()) return a.total() > b.total();
        if (a.mood != b.mood) return a.mood > b.mood;
        return a.movie->id < b.movie->id;
    });
    return scores;
}

int main() {
    std::size_t movie_count;
    if (!(std::cin >> movie_count)) return 1;
    std::vector<Movie> movies(movie_count);
    for (auto& movie : movies) {
        std::cin >> movie.id >> movie.runtime;
        for (auto& score : movie.moods) std::cin >> score;
        for (auto& score : movie.times) std::cin >> score;
        for (auto& score : movie.company) std::cin >> score;
    }

    std::array<Preferences, 4> scenarios;
    for (auto& choice : scenarios) std::cin >> choice.mood >> choice.time >> choice.company >> choice.cap;
    if (!std::cin) return 1;

    for (const auto& choice : scenarios) {
        for (const auto& entry : rank(movies, choice)) {
            std::cout << entry.movie->id << ',' << entry.mood << ',' << entry.time
                      << ',' << entry.company << ',' << entry.runtime << ' ';
        }
        std::cout << '\n';
    }

    using Clock = std::chrono::steady_clock;
    std::array<double, 1000> samples;
    int checksum = 0;
    for (std::size_t i = 0; i < samples.size() + 100; ++i) {
        const auto start = Clock::now();
        auto ranked = rank(movies, scenarios[i % scenarios.size()]);
        const auto stop = Clock::now();
        if (i >= 100) {
            samples[i - 100] = std::chrono::duration<double, std::micro>(stop - start).count();
            if (!ranked.empty()) checksum += ranked.front().total();
        }
    }
    std::sort(samples.begin(), samples.end());
    const auto mean = std::accumulate(samples.begin(), samples.end(), 0.0) / samples.size();
    const auto median = (samples[499] + samples[500]) / 2;
    std::cout << std::fixed << std::setprecision(2)
              << mean << ' ' << median << ' ' << samples[949] << ' ' << checksum << '\n';
}
