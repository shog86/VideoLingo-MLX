import os
import re
import shutil
from time import sleep

import streamlit as st
from core._1_ytdlp import download_video_ytdlp, find_media_file, write_input_manifest
from core.st_utils.i18n_widgets import localized_uploader, cta_progress
from core.utils import *
from translations.translations import translate as t

OUTPUT_DIR = "output"

@st.fragment
def download_video_section():
    st.header(t("a. Download or Upload Video"))
    with st.container():
        try:
            media_file, media_type = find_media_file()
            if media_type == "video":
                st.video(media_file)
            else:
                st.audio(media_file)
            if st.button(t("Delete and Reselect"), key="delete_video_button"):
                os.remove(media_file)
                if os.path.exists(OUTPUT_DIR):
                    shutil.rmtree(OUTPUT_DIR)
                sleep(1)
                st.rerun()
            return True
        except:
            col1, col2 = st.columns([3, 1])
            with col1:
                url = st.text_input(t("Enter YouTube link:"))
            with col2:
                res_dict = {
                    "360p": "360",
                    "1080p": "1080",
                    "Best": "best"
                }
                target_res = load_key("ytb_resolution")
                res_options = list(res_dict.keys())
                default_idx = list(res_dict.values()).index(target_res) if target_res in res_dict.values() else 0
                res_display = st.selectbox(t("Resolution"), options=res_options, index=default_idx)
                res = res_dict[res_display]
            dl_slot = st.empty()
            if dl_slot.button(t("Download Video"), key="download_button", use_container_width=True,
                              type="primary"):
                if url:
                    last_step = [-1]

                    def _dl_progress(percent=None, speed=None, eta=None, finished=False, **kwargs):
                        if finished:
                            cta_progress(dl_slot, t("dl_finalizing"))
                            return
                        if percent is None:
                            return
                        # Throttle: refresh button text on every 5% step
                        step = int(percent // 5)
                        if step == last_step[0]:
                            return
                        last_step[0] = step
                        parts = [f"{percent:.0f}%"]
                        if speed:
                            if speed > 1_000_000:
                                parts.append(f"{speed/1_000_000:.1f} MB/s")
                            else:
                                parts.append(f"{speed/1_000:.1f} KB/s")
                        if eta:
                            parts.append(f"ETA {eta:.0f}s")
                        cta_progress(dl_slot, f"{t('Download Video')} {' | '.join(parts)}")

                    download_video_ytdlp(url, resolution=res, progress_callback=_dl_progress)
                    st.rerun()

            uploaded_file = localized_uploader(
                key="video_upload",
                file_types=load_key("allowed_video_formats") + load_key("allowed_audio_formats"))
            st.caption(f"{t('Or upload video')} · {t('uploader_limit_video')}")
            if uploaded_file:
                if os.path.exists(OUTPUT_DIR):
                    shutil.rmtree(OUTPUT_DIR)
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                
                raw_name = uploaded_file.name.replace(' ', '_')
                name, ext = os.path.splitext(raw_name)
                clean_name = re.sub(r'[^\w\-_\.]', '', name) + ext.lower()
                    
                with open(os.path.join(OUTPUT_DIR, clean_name), "wb") as f:
                    f.write(uploaded_file.getbuffer())

                media_path = os.path.join(OUTPUT_DIR, clean_name)
                media_ext = ext.lower().lstrip(".")
                media_type = "video" if media_ext in load_key("allowed_video_formats") else "audio"
                write_input_manifest(media_path, media_type)
                st.rerun()
            else:
                return False
