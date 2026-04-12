import base64
import os
import streamlit as st
from utils import sidebar_login, apply_mobile_css

st.set_page_config(page_title="Regras", page_icon="📜", layout="wide")
apply_mobile_css()

with st.sidebar:
    st.title("⚽ Copa Elevação Sabichão")
    st.caption("Sistema de palpites para amigos")

sidebar_login()

st.title("📜 Regras")

html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "regras.html")
with open(html_path, "r", encoding="utf-8") as f:
    html_content = f.read()

b64 = base64.b64encode(html_content.encode()).decode()
data_url = f"data:text/html;base64,{b64}"

st.markdown(
    f"""
    <div style="text-align:center; padding: 60px 20px;">
        <p style="font-size:1.1rem; color:#94a3b8; margin-bottom:32px;">
            As regras completas abrem em uma nova aba com o visual temático original.
        </p>
        <a href="{data_url}" target="_blank"
           style="
               display:inline-block;
               background: linear-gradient(135deg, #00d2ff, #0077aa);
               color: #fff;
               font-size: 1.1rem;
               font-weight: 700;
               padding: 16px 40px;
               border-radius: 10px;
               text-decoration: none;
               letter-spacing: 1px;
               box-shadow: 0 4px 20px rgba(0,210,255,0.3);
           ">
            📜 Abrir Regras
        </a>
    </div>
    """,
    unsafe_allow_html=True,
)
