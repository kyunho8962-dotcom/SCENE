import media


def test_keyless_media_uses_local_still_and_never_calls_network(monkeypatch):
    def unexpected_call(*args, **kwargs):
        raise AssertionError("keyless execution requested the network")

    monkeypatch.setattr(media, "_download", unexpected_call)
    first, second = media.load_media((("tt0096283", "tt0096283.jpg"), ("tt7282468", "")), "", "")
    assert first.backdrop.startswith(b"\xff\xd8")
    assert first.uses_ghibli_still
    assert first.poster is first.imdb is first.rotten_tomatoes is None
    assert second == media.MovieMedia()


def test_omdb_uses_only_ratings_from_the_matching_title(monkeypatch):
    payload = {
        "Response": "True", "imdbID": "tt0096283", "imdbRating": "8.1",
        "Ratings": [{"Source": "Rotten Tomatoes", "Value": "94%"}],
    }
    monkeypatch.setattr(media, "_json", lambda url: payload)
    assert media._omdb_ratings("tt0096283", "test-key") == ("8.1", "94%")
    assert media._omdb_ratings("tt7282468", "test-key") == (None, None)
    payload.update(imdbRating="N/A", Ratings=[{"Source": "Rotten Tomatoes", "Value": "N/A"}])
    assert media._omdb_ratings("tt0096283", "test-key") == (None, None)


def test_tmdb_paths_and_request_failures(monkeypatch):
    requests = []

    def download(url, maximum, headers=None):
        requests.append((url, headers))
        if url.startswith("https://api.themoviedb.org"):
            return b'{"movie_results":[{"poster_path":"/poster.jpg","backdrop_path":"/backdrop.jpg"}]}'
        if url.endswith("/poster.jpg"):
            return b"\xff\xd8mock-jpeg"
        raise TimeoutError

    monkeypatch.setattr(media, "_download", download)
    assert media._tmdb_images("tt0096283", "test-token") == (b"\xff\xd8mock-jpeg", None)
    assert requests[0][1]["Authorization"] == "Bearer test-token"
    assert media._tmdb_image("https://untrusted.example/test.jpg", "w342") is None
    assert len(requests) == 3
