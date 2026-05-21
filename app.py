"""
Photo Place Finder
==================

Upload a building / landmark photo → app figures out where it is
(via EXIF GPS, or Google Vision Landmark Detection, or Claude Vision AI
as a final fallback) → shows the location on a map alongside nearby
restaurants, cafes, and tourist attractions powered by the Google Places API.

Run locally:
    streamlit run app.py
"""
from __future__ import annotations

import io
import os
from typing import List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

import folium
import streamlit as st
from PIL import Image
from streamlit_folium import st_folium

from utils.exif_reader import extract_gps
from utils.places_api import (
    CATEGORY_COLORS,
    CATEGORY_LABELS_KO,
    CATEGORY_TYPES,
    Place,
    PlacesClient,
)
from utils.vision_api import LandmarkResult, best_landmark
from utils.claude_api import identify_building, ClaudeLocationGuess


# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="📸 Photo Place Finder",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ── Hero ── */
.hero {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border-radius: 20px;
    padding: 3rem 2.5rem 2.5rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: "";
    position: absolute;
    top: -60px; right: -60px;
    width: 220px; height: 220px;
    background: radial-gradient(circle, rgba(102,126,234,0.35) 0%, transparent 70%);
    border-radius: 50%;
}
.hero-title {
    font-size: 2.8rem;
    font-weight: 800;
    background: linear-gradient(90deg, #a78bfa, #60a5fa, #34d399);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 0.5rem;
    line-height: 1.2;
}
.hero-sub {
    color: rgba(255,255,255,0.75);
    font-size: 1.1rem;
    margin: 0;
}

/* ── Step cards ── */
.steps {
    display: flex;
    gap: 1rem;
    margin-bottom: 2rem;
}
.step-card {
    flex: 1;
    background: linear-gradient(145deg, #1e293b, #0f172a);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 1.3rem 1.2rem;
    text-align: center;
    position: relative;
}
.step-card .icon { font-size: 2rem; margin-bottom: 0.5rem; }
.step-card .label {
    font-weight: 700;
    color: #e2e8f0;
    font-size: 0.9rem;
    margin-bottom: 0.3rem;
}
.step-card .desc {
    color: rgba(255,255,255,0.45);
    font-size: 0.78rem;
    line-height: 1.4;
}
.step-card .badge {
    position: absolute; top: -10px; left: 50%;
    transform: translateX(-50%);
    background: linear-gradient(90deg,#7c3aed,#2563eb);
    color: white; font-size: 0.65rem; font-weight: 700;
    padding: 2px 10px; border-radius: 20px; white-space: nowrap;
}
.arrow {
    display: flex; align-items: center; color: rgba(255,255,255,0.25);
    font-size: 1.4rem; padding-top: 1.8rem;
}

/* ── Upload zone ── */
.upload-zone {
    background: linear-gradient(145deg, #1e293b, #0f172a);
    border: 2px dashed rgba(124,58,237,0.5);
    border-radius: 16px;
    padding: 2rem;
    text-align: center;
    margin-bottom: 1rem;
}
.upload-zone .upload-icon { font-size: 3rem; margin-bottom: 0.5rem; }
.upload-zone .upload-title {
    color: #e2e8f0; font-size: 1.1rem; font-weight: 600; margin-bottom: 0.3rem;
}
.upload-zone .upload-hint {
    color: rgba(255,255,255,0.4); font-size: 0.82rem;
}

/* ── Misc ── */
[data-testid="stFileUploader"] { border: none !important; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Secret / config loading
# ---------------------------------------------------------------------------
def _load_api_keys() -> Tuple[str, str, str]:
    """Load API keys from Streamlit secrets → env vars."""
    maps_key = ""
    vision_key = ""
    anthropic_key = ""
    try:
        maps_key = st.secrets.get("GOOGLE_MAPS_API_KEY", "") or ""
        vision_key = st.secrets.get("GOOGLE_VISION_API_KEY", "") or ""
        anthropic_key = st.secrets.get("ANTHROPIC_API_KEY", "") or ""
    except Exception:
        pass

    maps_key = maps_key or os.environ.get("GOOGLE_MAPS_API_KEY", "")
    vision_key = vision_key or os.environ.get("GOOGLE_VISION_API_KEY", "")
    anthropic_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")
    return maps_key, vision_key, anthropic_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _bytes_for_image(uploaded_file) -> bytes:
    uploaded_file.seek(0)
    data = uploaded_file.read()
    uploaded_file.seek(0)
    return data


@st.cache_data(show_spinner=False)
def _cached_reverse_geocode(api_key: str, lat: float, lng: float) -> Optional[str]:
    return PlacesClient(api_key).reverse_geocode(lat, lng)


@st.cache_data(show_spinner=False)
def _cached_geocode(api_key: str, query: str) -> Optional[Tuple[float, float]]:
    return PlacesClient(api_key).geocode(query)


@st.cache_data(show_spinner=False)
def _cached_nearby(
    api_key: str, lat: float, lng: float, category: str, radius_m: int, sort_by: str
) -> List[Place]:
    return PlacesClient(api_key).nearby(
        lat, lng, category=category, radius_m=radius_m, sort_by=sort_by
    )


def _build_map(
    center_lat: float,
    center_lng: float,
    center_label: str,
    places_by_category: dict,
    photo_api_key: str,
) -> folium.Map:
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=15,
        tiles="OpenStreetMap",
    )

    folium.Marker(
        location=[center_lat, center_lng],
        popup=folium.Popup(f"<b>📍 {center_label}</b>", max_width=250),
        tooltip=center_label,
        icon=folium.Icon(color="green", icon="camera", prefix="fa"),
    ).add_to(m)

    for category, places in places_by_category.items():
        color = CATEGORY_COLORS.get(category, "gray")
        for place in places:
            rating_txt = (
                f"⭐ {place.rating:.1f} ({place.user_ratings_total or 0})"
                if place.rating is not None
                else "평점 없음"
            )
            dist_txt = f" · {place.distance_label}" if place.distance_m is not None else ""
            popup_html = f"""
            <div style='min-width:180px'>
              <b>{place.name}</b><br>
              {rating_txt}{dist_txt}<br>
              <small>{place.address or ''}</small><br>
              <a href='{place.google_maps_url}' target='_blank'>
                Google 지도에서 보기 →
              </a>
            </div>
            """
            folium.Marker(
                location=[place.latitude, place.longitude],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"{place.name}{dist_txt}",
                icon=folium.Icon(color=color, icon="info-sign"),
            ).add_to(m)

    return m


def _render_place_card(place: Place, photo_api_key: str) -> None:
    with st.container(border=True):
        cols = st.columns([1, 2])
        photo_url = place.photo_url(photo_api_key)
        with cols[0]:
            if photo_url:
                st.image(photo_url, use_container_width=True)
            else:
                st.markdown(
                    "<div style='height:120px;display:flex;"
                    "align-items:center;justify-content:center;"
                    "background:#f0f2f6;border-radius:8px;color:#888'>"
                    "사진 없음</div>",
                    unsafe_allow_html=True,
                )
        with cols[1]:
            st.markdown(f"**{place.name}**")
            meta_parts = []
            if place.rating is not None:
                meta_parts.append(f"⭐ **{place.rating:.1f}** ({place.user_ratings_total or 0})")
            if place.distance_label:
                meta_parts.append(f"📍 **{place.distance_label}**")
            if meta_parts:
                st.markdown("  ·  ".join(meta_parts))
            if place.address:
                st.caption(place.address)
            if place.open_now is True:
                st.success("영업 중", icon="🟢")
            elif place.open_now is False:
                st.warning("영업 종료", icon="🔴")
            st.markdown(
                f"[Google 지도에서 보기 →]({place.google_maps_url})"
            )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
maps_key, vision_key, anthropic_key = _load_api_keys()

with st.sidebar:
    st.title("⚙️ 설정")

    st.markdown("**Google Maps API Key**")
    maps_key = st.text_input(
        "Maps / Places API key",
        value=maps_key,
        type="password",
        label_visibility="collapsed",
        help="Places API + Geocoding API가 활성화된 키",
    )

    st.markdown("**Google Vision API Key**")
    vision_key = st.text_input(
        "Vision API key",
        value=vision_key,
        type="password",
        label_visibility="collapsed",
        help="Cloud Vision API가 활성화된 키 (Maps 키와 동일해도 됨)",
    )

    st.markdown("**Anthropic API Key** *(선택 — Claude AI 인식 폴백용)*")
    anthropic_key = st.text_input(
        "Anthropic API key",
        value=anthropic_key,
        type="password",
        label_visibility="collapsed",
        help="Vision API가 실패할 때 Claude AI로 건물을 인식합니다. 없으면 건너뜁니다.",
    )

    st.divider()

    radius_m = st.slider(
        "검색 반경 (m)",
        min_value=200,
        max_value=3000,
        value=1000,
        step=100,
    )

    sort_by = st.radio(
        "정렬 기준",
        options=["prominence", "rating", "distance"],
        format_func=lambda x: {"prominence": "🔥 인기순", "rating": "⭐ 평점순", "distance": "📍 거리순"}[x],
        horizontal=True,
    )

    st.markdown("**보여줄 카테고리**")
    show_restaurants = st.checkbox("🍽️ 주변 맛집", value=True)
    show_cafes = st.checkbox("☕ 카페 / 디저트", value=True)
    show_attractions = st.checkbox("🗺️ 관광 명소", value=True)

    st.divider()
    st.caption(
        "💡 API 키는 [Google Cloud Console]"
        "(https://console.cloud.google.com/)에서 발급받을 수 있어요. "
        "Places API, Geocoding API, Cloud Vision API를 활성화하세요."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Hero
st.markdown("""
<div class="hero">
  <div class="hero-title">📸 Photo Place Finder</div>
  <p class="hero-sub">사진 한 장으로 장소를 찾고, 주변 맛집·카페·관광지까지 추천받으세요.</p>
</div>
""", unsafe_allow_html=True)

# How it works — 3-step cards
st.markdown("""
<div class="steps">
  <div class="step-card">
    <div class="badge">STEP 1</div>
    <div class="icon">📱</div>
    <div class="label">GPS 자동 인식</div>
    <div class="desc">핸드폰 사진의 EXIF GPS를<br>자동으로 읽어요</div>
  </div>
  <div class="arrow">›</div>
  <div class="step-card">
    <div class="badge">STEP 2</div>
    <div class="icon">🔍</div>
    <div class="label">AI 랜드마크 인식</div>
    <div class="desc">GPS 없으면 Google Vision &<br>Claude AI가 인식해요</div>
  </div>
  <div class="arrow">›</div>
  <div class="step-card">
    <div class="badge">STEP 3</div>
    <div class="icon">🗺️</div>
    <div class="label">주변 장소 추천</div>
    <div class="desc">맛집·카페·관광지를<br>지도와 카드로 보여줘요</div>
  </div>
</div>
""", unsafe_allow_html=True)

# Upload zone hint
st.markdown("""
<div class="upload-zone">
  <div class="upload-icon">📂</div>
  <div class="upload-title">사진을 업로드하세요</div>
  <div class="upload-hint">JPG · PNG · HEIC · HEIF · 파일당 최대 200MB</div>
</div>
""", unsafe_allow_html=True)

uploaded = st.file_uploader(
    "건물 / 랜드마크 사진을 업로드하세요",
    type=["jpg", "jpeg", "png", "heic", "heif"],
    label_visibility="collapsed",
)

if uploaded is None:
    st.stop()

# Show the uploaded image right away.
left, right = st.columns([1, 1])
try:
    image = Image.open(uploaded)
except Exception as e:
    st.error(f"이미지를 열 수 없습니다: {e}")
    st.stop()

with left:
    st.image(image, caption="업로드한 사진", use_container_width=True)

# ---------------------------------------------------------------------------
# Step 1 — figure out coordinates
# ---------------------------------------------------------------------------
location_source = None
landmark: Optional[LandmarkResult] = None
claude_guess: Optional[ClaudeLocationGuess] = None
coords: Optional[Tuple[float, float]] = None
place_label = "내가 업로드한 위치"

with right:
    with st.status("📍 위치 정보 분석 중...", expanded=True) as status:
        # 1) Try EXIF first.
        st.write("EXIF GPS 정보 확인 중...")
        coords = extract_gps(image)
        if coords:
            location_source = "EXIF"
            st.write(f"✅ EXIF에서 GPS를 찾았어요: {coords[0]:.5f}, {coords[1]:.5f}")
        else:
            st.write("EXIF에 GPS가 없네요.")

            # 2) Google Vision API.
            if vision_key:
                st.write("Google Vision AI로 랜드마크 인식 시도...")
                try:
                    landmark = best_landmark(_bytes_for_image(uploaded), vision_key)
                except Exception as e:
                    st.write(f"⚠️ Vision API 오류: {e}")

            if landmark:
                coords = (landmark.latitude, landmark.longitude)
                location_source = "Google Vision API"
                place_label = landmark.description
                st.write(
                    f"✅ Google Vision 인식: **{landmark.description}** "
                    f"(확신도 {landmark.score:.0%})"
                )
            else:
                if vision_key:
                    st.write("Google Vision이 랜드마크를 인식하지 못했어요.")

                # 3) Claude Vision fallback.
                if anthropic_key and maps_key:
                    st.write("🤖 Claude AI로 건물 인식 시도...")
                    try:
                        claude_guess = identify_building(
                            _bytes_for_image(uploaded), anthropic_key
                        )
                    except Exception as e:
                        st.write(f"⚠️ Claude API 오류: {e}")

                    if claude_guess:
                        st.write(
                            f"🤖 Claude 추정: **{claude_guess.building_name}** "
                            f"({claude_guess.city_hint}, 확신도: {claude_guess.confidence})"
                        )
                        st.caption(f"_{claude_guess.description}_")
                        # Geocode the search query.
                        geocoded = _cached_geocode(maps_key, claude_guess.search_query)
                        if geocoded:
                            coords = geocoded
                            location_source = "Claude AI + Geocoding"
                            place_label = claude_guess.building_name
                            st.write(f"✅ 좌표 확인: {coords[0]:.5f}, {coords[1]:.5f}")
                        else:
                            st.write("⚠️ Geocoding으로 좌표를 찾지 못했어요.")
                    else:
                        st.write("Claude도 건물을 인식하지 못했어요.")
                elif not anthropic_key:
                    st.write("💡 Anthropic API 키를 사이드바에 입력하면 Claude AI가 추가로 시도합니다.")

        if coords is None:
            status.update(
                label="😢 위치를 인식하지 못했습니다.",
                state="error",
            )
            st.warning(
                "유명한 건물·랜드마크 사진이거나 GPS가 있는 핸드폰 사진을 써보세요. "
                "Anthropic API 키가 있으면 Claude AI가 추가로 시도합니다."
            )
            st.stop()

        status.update(label="✅ 위치 확인 완료!", state="complete")

assert coords is not None
lat, lng = coords

# ---------------------------------------------------------------------------
# Step 2 — reverse geocode + nearby search
# ---------------------------------------------------------------------------
if not maps_key:
    st.error("Google Maps API 키가 없으면 주변 장소 검색을 할 수 없습니다.")
    st.stop()

address = _cached_reverse_geocode(maps_key, lat, lng)

st.markdown("---")
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.subheader(f"📍 {place_label}")
    if address:
        st.caption(address)
    st.caption(f"좌표: `{lat:.5f}, {lng:.5f}` · 출처: **{location_source}**")
with header_col2:
    st.link_button(
        "Google 지도에서 열기",
        f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
        use_container_width=True,
    )

# Collect nearby places per requested category.
categories_to_fetch = []
if show_restaurants:
    categories_to_fetch.append("restaurant")
if show_cafes:
    categories_to_fetch.append("cafe")
if show_attractions:
    categories_to_fetch.append("tourist_attraction")

if not categories_to_fetch:
    st.warning("사이드바에서 표시할 카테고리를 최소 하나 선택해주세요.")
    st.stop()

places_by_category: dict = {}
with st.spinner("주변 장소 검색 중..."):
    for category in categories_to_fetch:
        try:
            places_by_category[category] = _cached_nearby(
                maps_key, lat, lng, category, radius_m, sort_by
            )
        except Exception as e:
            st.error(f"{CATEGORY_LABELS_KO[category]} 검색 실패: {e}")
            places_by_category[category] = []

# ---------------------------------------------------------------------------
# Step 3 — render map + recommendation cards
# ---------------------------------------------------------------------------
st.markdown("### 🗺️ 지도")
fmap = _build_map(lat, lng, place_label, places_by_category, maps_key)
st_folium(fmap, height=500, width=None, returned_objects=[])

st.markdown("### 🌟 추천")
tabs = st.tabs([CATEGORY_LABELS_KO[c] for c in categories_to_fetch])
for tab, category in zip(tabs, categories_to_fetch):
    with tab:
        places = places_by_category.get(category, [])
        if not places:
            st.info("주변에서 찾지 못했어요. 검색 반경을 늘려보세요.")
            continue
        for i in range(0, len(places), 2):
            row = st.columns(2)
            for col, place in zip(row, places[i : i + 2]):
                with col:
                    _render_place_card(place, maps_key)

st.markdown("---")
st.caption(
    "Powered by Google Maps Platform & Google Cloud Vision & Claude AI. "
    "Built with Streamlit · "
    "[GitHub →](https://github.com/alpha02700/photo-place-finder)"
)
