import os
import streamlit as st
import io, zipfile
from core.st_utils.download_video_section import download_video_section
from core.st_utils.sidebar_setting import page_setting
from core.st_utils.i18n_widgets import localized_uploader, uploader_i18n_css, cta_progress
from translations.translations import translate as t

def download_subtitle_zip_button(text: str):
    zip_buffer = io.BytesIO()
    output_dir = "output"
    
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for file_name in os.listdir(output_dir):
            if file_name.endswith(".srt"):
                file_path = os.path.join(output_dir, file_name)
                with open(file_path, "rb") as file:
                    zip_file.writestr(file_name, file.read())
    
    zip_buffer.seek(0)
    
    st.download_button(
        label=text,
        data=zip_buffer,
        file_name="subtitles.zip",
        mime="application/zip"
    )

# st.markdown
give_star_button = """
<style>
    .github-button {
        display: block;
        width: 100%;
        padding: 0.5em 1em;
        color: #1c1917;
        background-color: #f5f5f4;
        border: 1px solid #e7e5e4;
        border-radius: 10px;
        text-decoration: none;
        font-size: 14px;
        font-weight: 600;
        text-align: center;
        transition: background-color 0.3s ease;
        box-sizing: border-box;
    }
    .github-button:hover {
        background-color: #e7e5e4;
        color: #1c1917;
    }
</style>
<a href="https://github.com/shog86/VideoLingo-MLX" target="_blank" style="text-decoration: none;">
    <div class="github-button">
        Star on GitHub 🌟
    </div>
</a>
"""