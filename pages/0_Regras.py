import streamlit as st
import os
from utils import sidebar_login, apply_mobile_css

st.set_page_config(page_title="Regras", page_icon="📜", layout="wide")
apply_mobile_css()

with st.sidebar:
    st.title("⚽ Copa Elevação Sabichão")
    st.caption("Sistema de palpites para amigos")

sidebar_login()

html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "regras.html")
with open(html_path, "r", encoding="utf-8") as f:
    html_content = f.read()

st.components.v1.html(html_content, height=1600, scrolling=True)
