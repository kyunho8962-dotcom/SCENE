# SCENE

**지금, 어떤 영화를 보고 싶나요?**

SCENE은 기분, 시간대, 관람 형태, 러닝타임으로 지금 보기 좋은 영화 한 편과 대안 두 편을 고르는 Streamlit 앱입니다. 영화 목록 24편은 저장소에 포함되어 있고, 추천은 브라우저에서 조건을 선택할 때마다 서버에서 계산합니다.

## 시작하기

프로젝트 폴더에서 Python 3.11 이상으로 실행합니다.

```bash
pip install -r requirements.txt
streamlit run app.py
```

터미널에 표시되는 로컬 주소를 브라우저에서 열면 됩니다. Windows PowerShell에서 프로젝트 전용 가상환경을 사용할 경우 다음 명령으로 실행할 수 있습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## 추천 원리

1. 러닝타임이 설정한 한도를 넘으면 후보에서 제외합니다. 한도와 같은 길이의 작품은 포함합니다.
2. 영화마다 저장된 기분, 시간대, 관람 형태 항목 중 사용자가 선택한 값의 등급을 가져옵니다. 각 등급은 0~5이며 개발자가 정의한 큐레이션 값입니다.
3. `등급 ÷ 5 × 최대 점수`로 항목별 점수를 구합니다. 길이 제한을 통과한 작품은 러닝타임 10점을 받습니다. 제한이 없는 경우도 모든 작품에 10점을 줍니다.
4. 총점 내림차순으로 정렬합니다. 같으면 기분 점수가 높은 작품부터, 다시 같으면 IMDb ID의 사전순으로 정렬합니다. 상위 세 작품을 표시하고, **다른 작품 보기**를 누르면 다음 세 작품을 보여줍니다.

| 항목 | 최대 점수 |
| --- | ---: |
| 기분 | 50 |
| 시간대 | 20 |
| 관람 형태 | 20 |
| 러닝타임 | 10 |
| 합계 | 100 |

가중치는 개발자가 세운 초기 가설입니다. 사용자를 대상으로 검증한 수치는 아닙니다. SCENE 적합도는 지금의 관람 조건과 어울리는 정도입니다. IMDb와 Rotten Tomatoes 평점은 작품의 외부 평가로 표시되며 적합도 계산에는 사용하지 않습니다.

## 선택 사항 · 포스터, 백드롭, 외부 평점

API 키 없이 실행할 수 있습니다. 스튜디오 지브리 작품 3편의 공식 스틸컷은 로컬에 포함되어 있습니다. 그 외에 제공된 이미지가 없으면 포스터 및 스틸컷 자리에 대체 화면을 표시합니다. 확인 가능한 평점이 없을 때는 `정보 없음`을 표시합니다.

실시간 정보를 사용하려면 `.env.example`을 `.env`로 복사하거나 `.streamlit/secrets.toml`에 다음 이름으로 값을 설정하세요. 환경 변수와 `.env`가 Streamlit secrets보다 우선하며, 값을 수정한 뒤에는 서버를 다시 시작하세요.

| 설정 | 값 |
| --- | --- |
| `TMDB_READ_TOKEN` | TMDB의 **API Read Access Token**. IMDb ID로 작품을 찾아 포스터와 백드롭을 가져옵니다. |
| `OMDB_API_KEY` | OMDb API 키. 응답에 포함된 IMDb 및 Rotten Tomatoes 평점을 표시합니다. |

값은 서버에서만 읽습니다. `.env`와 `.streamlit/secrets.toml`은 Git에서 제외됩니다. 외부 서비스가 실패했을 때도 추천과 조건 변경은 계속 사용할 수 있습니다. API 이용 조건은 각 제공자의 비상업 이용 안내를 따릅니다. [TMDB 인증](https://developer.themoviedb.org/docs/authentication-application) · [TMDB 이미지 이용 및 출처 표기](https://developer.themoviedb.org/docs/faq) · [OMDb API](https://www.omdbapi.com/) · [OMDb 콘텐츠 라이선스](https://creativecommons.org/licenses/by-nc/4.0/)

## 프로젝트 구조

| 파일 | 역할 |
| --- | --- |
| `app.py`, `style.css` | Streamlit 입력 폼, 추천 화면, 반응형 카드 디자인 |
| `models.py` | 영화, 사용자 조건, 항목별 점수와 추천 결과를 표현하는 클래스 |
| `database.py` | 로컬 영화 목록 읽기, 러닝타임 필터 |
| `recommender.py` | 추천 점수 계산, 정렬, 추천 이유 생성 |
| `media.py`, `static/` | 선택적 이미지·평점 조회와 로컬 이미지 |
| `data/movies.json` | 영화 정보 24편과 수동 큐레이션 등급 |
| `tests/` | 추천, 매체 응답 처리, Streamlit 조작 테스트 |
| `benchmark.py`, `benchmark.cpp` | Python 추천 및 동일 조건의 C++ 순위 계산 벤치마크 |
| `PRESENTATION_GUIDE.md` | 발표 순서, Mermaid 클래스 다이어그램과 흐름도, 측정 결과 |

Python은 인공지능학과에서 배우는 언어를 실제 프로젝트에 적용하고 싶어 선택했습니다. 표준 라이브러리로 JSON을 읽어 데이터 클래스로 표현할 수 있고, Streamlit에서 같은 언어로 입력과 결과를 빠르게 연결할 수 있습니다. C++ 벤치마크는 순위 계산 비용을 비교하는 데 사용했습니다.

## 테스트와 성능 측정

```bash
python -m pytest -q
python benchmark.py
```

C++ 비교는 C++17 컴파일러가 있는 환경에서 실행합니다. Windows의 Visual Studio Developer Command Prompt에서는 다음처럼 빌드합니다.

```bat
cl /O2 /EHsc /std:c++17 benchmark.cpp
python benchmark.py --cpp benchmark.exe
```

GCC에서는 다음과 같습니다.

```bash
g++ -O2 -std=c++17 benchmark.cpp -o benchmark_cpp
python benchmark.py --cpp ./benchmark_cpp
```

Python 벤치마크는 JSON을 한 번 읽고 같은 네 조건을 250회씩 실행합니다. C++ 비교 시에는 공통으로 후보 필터링, 점수 계산, 정렬만 측정하고 양쪽의 순위와 항목별 점수를 대조합니다. 최신 실행에서 측정한 수치와 순위 예시는 [발표 준비 가이드](PRESENTATION_GUIDE.md)에 있습니다.

## 데이터 및 이미지 출처

- 영화 식별자는 각 작품의 IMDb 제목 페이지에 대응합니다. 한국 영화의 러닝타임은 한국 극장판의 KOFIC 표기를 우선했습니다. 배급판과 복원판에 따라 분 단위 표기는 달라질 수 있습니다. 장르 선택과 줄거리 요약은 SCENE에서 작성했습니다. [IMDb](https://www.imdb.com/) · [KOFIC 버닝](https://www.koreanfilm.or.kr/eng/films/index/filmsView.jsp?movieCd=20173202) · [KOFIC 마더](https://www.koreanfilm.or.kr/eng/films/index/filmsView.jsp?movieCd=20090248) · [KOFIC 박쥐](https://www.koreanfilm.or.kr/view/news.jsp?category=IN_FOCUS&seq=354) · [KOFIC 기생충](https://www.koreanfilm.or.kr/eng/films/index/filmsView.jsp?movieCd=20183782) · [KOFIC 리틀 포레스트](https://www.koreanfilm.or.kr/eng/films/index/filmsView.jsp?movieCd=20170841) · [Criterion 12인의 성난 사람들](https://www.criterion.com/films/27871-12-angry-men)
- 세 작품의 스틸컷은 통상적인 범위에서 사용을 허용하는 Studio Ghibli 공식 작품 페이지의 공개 스틸컷입니다. 각 이미지의 권리는 해당 작품의 권리자에게 있습니다. [이웃집 토토로](https://www.ghibli.jp/works/totoro/) · [마녀 배달부 키키](https://www.ghibli.jp/works/majo/) · [센과 치히로의 행방불명](https://www.ghibli.jp/works/chihiro/)
- 시작 화면의 극장 배경은 SCENE을 위해 생성한 이미지입니다. 작품의 포스터 및 백드롭은 설정한 경우 TMDB에서 표시합니다. [TMDB 이미지 문서](https://developer.themoviedb.org/docs/image-basics) · [TMDB 공식 로고](https://www.themoviedb.org/about/logos-attribution)
