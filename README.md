# 📸 Photo Place Finder

> 사진 한 장으로 **장소를 찾고**, **주변 맛집·카페·관광지까지** 추천해주는 웹 앱.

핸드폰으로 찍은 건물·랜드마크 사진을 업로드하면,
1. 📍 사진의 **EXIF GPS 정보**로 위치를 먼저 찾고,
2. GPS가 없으면 **Google Vision AI**가 랜드마크를 인식하고,
3. 그래도 모르면 **Claude AI**가 건물을 인식해 위치를 추정한 뒤,
4. 🗺️ **Google Places API**로 주변 맛집·카페·관광지를 지도와 카드로 보여줍니다.

[English version below ↓](#english)

---

## ✨ 주요 기능

- **3단계 위치 인식**: EXIF GPS → Google Vision AI → Claude AI (단계별 폴백)
- **지도 시각화**: 사진 위치(녹색 핀)와 주변 추천 장소를 한눈에 (folium 기반)
- **카테고리별 추천**: 🍽️ 맛집 · ☕ 카페/디저트 · 🗺️ 관광 명소
- **장소 카드**: 평점·거리·리뷰 수·영업 여부·사진·구글 지도 링크
- **정렬 옵션**: 🔥 인기순 / ⭐ 평점순 / 📍 거리순
- **검색 반경 조절**: 200m ~ 3km 슬라이더로 조정

## 🛠 기술 스택

| 구분 | 사용 기술 |
|---|---|
| Frontend / Backend | Python + [Streamlit](https://streamlit.io) (단일 앱) |
| 이미지 처리 | Pillow (EXIF 파싱) |
| 위치 인식 | Google Cloud Vision API + Claude AI (claude-haiku) |
| 장소 검색 | Google Maps Platform (Places API + Geocoding API) |
| 지도 렌더링 | folium + streamlit-folium |

## 📦 설치 및 실행

### 1. 저장소 복제

```bash
git clone https://github.com/alpha02700/photo-place-finder.git
cd photo-place-finder
```

### 2. 가상환경 생성 후 의존성 설치

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. API 키 발급

**Google Cloud Console** ([console.cloud.google.com](https://console.cloud.google.com/))에서 프로젝트를 만들고 아래 API들을 활성화하세요.

- **Places API** (Nearby Search용)
- **Geocoding API** (좌표 → 주소 변환, Claude AI 인식 결과 좌표 변환에도 사용)
- **Cloud Vision API** (랜드마크 인식 - GPS 없는 사진용)

이후 `사용자 인증 정보 → API 키 만들기`로 API 키 한 개를 발급받으면 됩니다 (위 API 모두를 같은 키로 사용 가능).

**Anthropic API Key** (선택, Claude AI 폴백용) — [console.anthropic.com](https://console.anthropic.com/)에서 발급.

> 💡 **요금 정보**: Google Maps Platform은 매월 $200 무료 크레딧을 제공하며, Vision API도 월 1,000건까지 무료입니다. Anthropic은 새 계정에 무료 크레딧을 제공합니다. 개인 프로젝트 수준에서는 거의 무료로 쓸 수 있습니다.

### 4. API 키 설정

두 가지 방법 중 하나를 선택하세요.

**(A) 로컬 개발용: `.env` 파일**

```bash
cp .env.example .env
# .env 파일을 열어 실제 키를 입력
```

**(B) Streamlit Cloud 배포용: `secrets.toml`**

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# 파일을 열어 실제 키를 입력
```

> ⚠️ `.env`와 `secrets.toml`은 모두 `.gitignore`에 포함되어 있어 GitHub에 올라가지 않습니다.
> 깃에 절대 API 키를 커밋하지 마세요.

### 5. 실행

```bash
streamlit run app.py
```

브라우저가 자동으로 열리며 (`http://localhost:8501`), 사이드바에서 API 키를 직접 붙여 넣어도 동작합니다.

## 🚀 Streamlit Community Cloud로 무료 배포

다른 사람에게 링크 하나로 보여주고 싶다면 [Streamlit Community Cloud](https://share.streamlit.io)에 무료 배포할 수 있어요.

1. 이 저장소를 GitHub에 푸시
2. [share.streamlit.io](https://share.streamlit.io) 접속 후 GitHub 계정 연결
3. `New app` → repo 선택 → `app.py` 지정
4. **Advanced settings → Secrets**에 아래처럼 키를 입력

   ```toml
   GOOGLE_MAPS_API_KEY = "your_key_here"
   GOOGLE_VISION_API_KEY = "your_key_here"
   ANTHROPIC_API_KEY = "your_key_here"   # 선택
   ```

5. Deploy 클릭 → 1~2분 후 `https://<your-app>.streamlit.app` 주소가 발급됩니다 🎉

## 📁 프로젝트 구조

```
photo-place-finder/
├── app.py                          # Streamlit 메인 앱 (UI + 흐름 제어)
├── utils/
│   ├── exif_reader.py             # EXIF에서 GPS 추출
│   ├── vision_api.py              # Google Vision API 호출
│   ├── claude_api.py              # Claude AI 건물 인식 (폴백)
│   └── places_api.py              # Google Places + Geocoding API 호출
├── .streamlit/
│   └── secrets.toml.example       # 배포용 시크릿 템플릿
├── .env.example                   # 로컬 환경변수 템플릿
├── .gitignore
├── requirements.txt
└── README.md
```

## 🧠 동작 흐름

```
[사진 업로드]
      ↓
[① EXIF GPS 추출] ──── 성공 ────────────────────────┐
      ↓ 실패                                          │
[② Google Vision AI 랜드마크 인식] ─── 성공 ─────┐   │
      ↓ 실패                                       │   │
[③ Claude AI 건물 인식 → Geocoding으로 좌표화]    │   │
      ↓ 성공                                       │   │
[위·경도 좌표] ←───────────────────────────────────┴───┘
      ↓
[Geocoding API: 좌표 → 주소]
      ↓
[Places API: 반경 N미터 내 검색 (인기/평점/거리순)]
      ↓
[folium 지도 + 장소 카드 렌더링]
```

## ⚠️ 한계

- Vision API의 **랜드마크 인식은 유명한 건물 위주**입니다 (Eiffel Tower, 경복궁 등). Claude AI 폴백을 켜두면 동네 건물도 어느 정도 인식합니다.
- HEIC/HEIF 포맷은 `pillow-heif` 같은 추가 의존성이 필요할 수 있습니다.
- **추후 개선 아이디어**: 즐겨찾기 저장 / 여러 장소 코스 추천 / 사용자 현재 위치 기반 검색.

## 📄 라이선스

MIT License – 자유롭게 가져다 쓰세요!

---

<a id="english"></a>

# 📸 Photo Place Finder (English)

Upload a building/landmark photo → the app finds where it is and recommends nearby restaurants, cafes, and attractions.

## How it works

1. Reads **EXIF GPS** from your photo first (free, instant).
2. Falls back to **Google Cloud Vision Landmark Detection** if GPS is missing.
3. Falls back to **Claude AI** (claude-haiku) if Vision API fails too.
4. Uses **Google Places API** to fetch nearby restaurants, cafes, and tourist attractions.
5. Displays everything on an interactive **folium** map plus card grid with distance info.

## Quick start

```bash
git clone https://github.com/alpha02700/photo-place-finder.git
cd photo-place-finder
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add your API keys
streamlit run app.py
```

Enable these Google Cloud APIs (one key works for all):
**Places API · Geocoding API · Cloud Vision API**.
Optionally add an **Anthropic API key** for Claude AI fallback.

Deploy free on [Streamlit Community Cloud](https://share.streamlit.io) – just push to GitHub and connect.
