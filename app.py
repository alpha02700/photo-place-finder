"""
Photo Place Finder
==================

Upload a building / landmark photo → app figures out where it is
(via EXIF GPS, or Google Vision Landmark Detection as a fallback) →
shows the location on a map alongside nearby restaurants, cafes,
and tourist attractions powered by the Google Places API.

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
# Secret / config loading
# ---------------------------------------------------------------------------
def _load_api_keys() -> Tuple[str, str]:
    """
    Load API keys from Streamlit secrets first, then fall back to
    environment variables. This makes local development AND Streamlit
    Cloud deployment work without changes.
    """
    # st.secrets behaves like a dict but raises if no secrets.toml exists,
    # so guard with a try/except.
    maps_key = ""
    vision_key = ""
    try:
        maps_key = st.secrets.get("GOOGLE_MAPS_API_KEY", "") or ""
        vision_key = st.secrets.get("GOOGLE_VISION_API_KEY", "") or ""
    except Exception:
        pass

    maps_key = maps_key or os.environ.get("GOOGLE_MAPS_API_KEY", "")
    vision_key = vision_key or os.environ.get("GOOGLE_VISION_API_KEY", "")
    return maps_key, vision_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _bytes_for_image(uploaded_file) -> bytes:
    """Return raw image bytes from a Streamlit UploadedFile."""
    uploaded_file.seek(0)
    data = uploaded_file.read()
    uploaded_file.seek(0)
    return data


@st.cache_data(show_spinner=False)
def _cached_reverse_geocode(api_key: str, lat: float, lng: float) -> Optional[str]:
    return PlacesClient(api_key).reverse_geocode(lat, lng)


@st.cache_data(show_spinner=False)
def _cached_nearby(
    api_key: str, lat: float, lng: float, category: str, radius_m: int
) -> List[Place]:
    return PlacesClient(api_key).nearby(
        lat, lng, category=category, radius_m=radius_m
    )


def _build_map(
    center_lat: float,
    center_lng: float,
    center_label: str,
    places_by_category: dict,
    photo_api_key: str,
) -> folium.Map:
    """Compose a folium map with the source pin + nearby place markers."""
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=15,
        tiles="OpenStreetMap",
    )

    # Source marker (large green star-style pin).
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
            popup_html = f"""
            <div style='min-width:180px'>
              <b>{place.name}</b><br>
              {rating_txt}<br>
              <small>{place.address or ''}</small><br>
              <a href='{place.google_maps_url}' target='_blank'>
                Google 지도에서 보기 →
              </a>
            </div>
            """
            folium.Marker(
                location=[place.latitude, place.longitude],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=place.name,
                icon=folium.Icon(color=color, icon="info-sign"),
            ).add_to(m)

    return m


def _render_place_card(place: Place, photo_api_key: str) -> None:
    """Render one place as a compact card."""
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
            if place.rating is not None:
                st.markdown(
                    f"⭐ **{place.rating:.1f}** "
                    f"({place.user_ratings_total or 0} reviews)"
                )
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
maps_key, vision_key = _load_api_keys()

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

    st.divider()

    radius_m = st.slider(
        "검색 반경 (m)",
        min_value=200,
        max_value=3000,
        value=1000,
        step=100,
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
st.title("📸 Photo Place Finder")
st.markdown(
    "사진 한 장으로 **장소를 찾고, 주변 맛집·카페·관광지까지** 추천받으세요."
)

uploaded = st.file_uploader(
    "건물 / 랜드마크 사진을 업로드하세요",
    type=["jpg", "jpeg", "png", "heic", "heif"],
    help="스마트폰 카메라로 찍은 사진을 그대로 올리면 EXIF의 GPS를 우선 사용합니다.",
)

if uploaded is None:
    st.info(
        "👆 사진을 업로드하면 시작합니다.\n\n"
        "- 📱 핸드폰 사진이면 EXIF의 GPS를 자동으로 읽어요.\n"
        "- 🌍 GPS가 없으면 Google Vision AI가 랜드마크를 인식해요."
    )
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
coords: Optional[Tuple[float, float]] = None
place_label = "내가 업로드한 위치"

with right:
    with st.status("📍 위치 정보 분석 중...", expanded=True) as status:
        # 1) Try EXIF first (free, instant, very accurate when present).
        st.write("EXIF GPS 정보 확인 중...")
        coords = extract_gps(image)
        if coords:
            location_source = "EXIF"
            st.write(f"✅ EXIF에서 GPS를 찾았어요: {coords[0]:.5f}, {coords[1]:.5f}")
        else:
            st.write("EXIF에 GPS가 없네요. Vision AI로 랜드마크 인식 시도...")
            if not vision_key:
                status.update(
                    label="❌ Vision API 키가 없어 인식할 수 없습니다.",
                    state="error",
                )
                st.error(
                    "GPS가 없는 사진이라서 Google Vision API로 인식해야 합니다. "
                    "사이드바에 Vision API 키를 입력해주세요."
                )
                st.stop()
            try:
                landmark = best_landmark(_bytes_for_image(uploaded), vision_key)
            except Exception as e:
                status.update(label="❌ Vision API 호출 실패", state="error")
                st.error(str(e))
                st.stop()

            if landmark is None:
                status.update(
                    label="😢 랜드마크를 인식하지 못했습니다.",
                    state="error",
                )
                st.warning(
                    "유명한 건물/랜드마크 사진이면 인식 가능성이 높아요. "
                    "다른 사진을 시도해보세요."
                )
                st.stop()

            coords = (landmark.latitude, landmark.longitude)
            location_source = "Vision API"
            place_label = landmark.description
            st.write(
                f"✅ 인식 결과: **{landmark.description}** "
                f"(확신도 {landmark.score:.0%})"
            )

        status.update(label="✅ 위치 확인 완료!", state="complete")

assert coords is not None
lat, lng = coords

# ---------------------------------------------------------------------------
# Step 2 — reverse geocode + nearby search
# ---------------------------------------------------------------------------
if not maps_key:
    st.error("Google Maps API 키가 없으면 주변 장소 검색을 할 수 없습니다.")
    st.stop()

# Reverse geocode for a nice human label.
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
                maps_key, lat, lng, category, radius_m
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
        # 2-column grid.
        for i in range(0, len(places), 2):
            row = st.columns(2)
            for col, place in zip(row, places[i : i + 2]):
                with col:
                    _render_place_card(place, maps_key)

st.markdown("---")
st.caption(
    "Powered by Google Maps Platform & Google Cloud Vision. "
    "Built with Streamlit · "
    "[GitHub Repo →](https://github.com/your-username/photo-place-finder)"
)
