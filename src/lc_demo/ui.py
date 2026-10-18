"""Static look of the login page: split layout, left-hand intro panel, right-hand form styling.

Layout modelled on Colorlib's "Relay Auth" template; markup and copy are this app's own.
"""

import streamlit as st

FONTS = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Instrument+Serif:ital@1&display=swap"

CSS = f"""
<style>
@import url('{FONTS}');

:root {{
  --ink: #1d3a2a;
  --muted: #5d6a61;
  --accent: #4d6b3a;
  --panel: #f3f2ec;
  --line: #e4e2da;
  --card: #dcebc6;
}}

/* Full-bleed page: drop Streamlit's centered padding on the login page only. */
[data-testid="stMainBlockContainer"] {{ padding: 0; max-width: 100%; }}
[data-testid="stHeader"] {{ background: transparent; }}
.stMain [data-testid="stHorizontalBlock"] {{ min-height: 100vh; gap: 0; }}

/* Left panel */
.st-key-intro {{
  background: var(--panel);
  min-height: 100vh;
  padding: 3rem 3.5rem 2.5rem;
  justify-content: space-between;
}}
.intro {{ font-family: Inter, sans-serif; color: var(--ink); }}
.brand {{
  display: flex;
  align-items: center;
  gap: .6rem;
  font-weight: 700;
  font-size: 1.45rem;
  letter-spacing: -.03em;
}}
.brand .mark {{
  width: 2rem; height: 2rem; border-radius: .55rem; background: var(--ink); color: var(--panel);
  display: grid; place-items: center; font-size: 1rem;
}}
.brand .tag {{ font-size: .62rem; font-weight: 600; letter-spacing: .22em; color: var(--muted); margin-left: .35rem; }}
.eyebrow {{
  font-size: .66rem;
  font-weight: 600;
  letter-spacing: .24em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 4.5rem 0 1.4rem;
}}
.intro h1 {{
  font-family: Inter, sans-serif; font-size: clamp(2.6rem, 4.6vw, 3.9rem); font-weight: 600;
  letter-spacing: -.055em; line-height: 1.02; color: var(--ink); margin: 0; padding: 0;
}}
.intro h1 em {{
  font-family: 'Instrument Serif', serif;
  font-weight: 400;
  letter-spacing: -.02em;
  color: var(--accent);
}}
.lede {{ font-size: 1.02rem; line-height: 1.6; color: var(--muted); margin: 1.6rem 0 1.4rem; max-width: 30rem; }}
.intro ul.features {{ list-style: none; padding: 0; margin: 0; display: grid; gap: .55rem; max-width: 30rem; }}
.features li {{ display: flex; gap: .65rem; font-size: .92rem; line-height: 1.45; color: var(--muted); margin: 0; }}
.features li::before {{
  content: "✓"; flex: none; width: 1.15rem; height: 1.15rem; border-radius: 50%; background: var(--ink);
  color: #fff; font-size: .62rem; display: grid; place-items: center; margin-top: .12rem;
}}
.features b {{ color: var(--ink); font-weight: 600; }}

/* Illustration: a tilted answer card with a ring behind it and a floating chip. */
.art {{ position: relative; height: 15rem; margin-top: 2.2rem; max-width: 26rem; }}
.art .ring {{ position: absolute; left: 3.5rem; top: 0; width: 13.5rem; height: 13.5rem; border-radius: 50%;
  border: 1.3rem solid #e9eadf; }}
.art .card {{ position: absolute; left: .5rem; top: 2rem; width: 11.5rem; padding: 1.1rem 1.15rem 1.3rem;
  background: var(--card); border-radius: .9rem; transform: rotate(-5deg);
  box-shadow: 0 18px 40px -18px rgba(29, 58, 42, .35); }}
.art .card small {{ display: block; font-size: .55rem; font-weight: 600; letter-spacing: .2em; color: var(--accent); }}
.art .card p {{
  margin: .55rem 0 .9rem;
  font-size: 1.28rem;
  font-weight: 600;
  letter-spacing: -.04em;
  line-height: 1.1;
  color: var(--ink);
}}
.art .card i {{
  display: block;
  height: .3rem;
  border-radius: 1rem;
  background: #b9cfa0;
  margin-top: .35rem;
  width: 75%;
}}
.art .card i + i {{ width: 50%; }}
.art .check {{ position: absolute; left: 10.6rem; top: 9.7rem; width: 1.6rem; height: 1.6rem; border-radius: 50%;
  background: var(--ink); color: #fff; font-size: .75rem; display: grid; place-items: center; }}
.art .chip {{
  position: absolute; left: 12.3rem; top: 10.2rem;
  background: #fff; border-radius: .45rem; padding: .55rem .85rem;
  font-size: .78rem; color: var(--ink); transform: rotate(4deg); box-shadow: 0 10px 24px -12px rgba(29, 58, 42, .35); }}
.art .spark {{ position: absolute; right: 1rem; top: 4.2rem; font-size: 2.6rem; color: var(--accent); line-height: 1; }}
.footnote {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: .74rem;
  color: var(--muted);
  margin-top: 2rem;
}}
.footnote span:last-child {{ font-size: 1.1rem; color: var(--accent); }}

/* Right panel */
.st-key-auth {{ max-width: 22rem; margin: 0 auto; padding: 7rem 0 3rem; }}
.auth-head {{ font-family: Inter, sans-serif; }}
.auth-head .step {{
  font-size: .64rem;
  font-weight: 600;
  letter-spacing: .26em;
  text-transform: uppercase;
  color: var(--muted);
}}
.auth-head h2 {{ font-family: Inter, sans-serif; font-size: 2.3rem; font-weight: 600; letter-spacing: -.055em;
  color: var(--ink); margin: .9rem 0 .5rem; padding: 0; }}
.auth-head p {{ color: var(--muted); font-size: .95rem; margin: 0 0 .6rem; }}
.st-key-auth [data-testid="stForm"] {{ border: 0; padding: 0; }}
.st-key-auth label p {{ font-weight: 600; color: var(--ink); font-size: .85rem; }}
.st-key-auth [data-testid="stTextInputRootElement"] {{ border-radius: .5rem; min-height: 2.9rem; background: #fff; }}
.st-key-auth [data-testid="stTextInputRootElement"]:not(:focus-within) {{ border-color: var(--line); }}
.st-key-auth [data-testid="stFormSubmitButton"] button {{ min-height: 2.9rem; border-radius: .5rem; }}
/* Template puts the arrow at the far right of the label; Streamlit renders icons first. */
.st-key-auth [data-testid="stFormSubmitButton"] button > div {{ width: 100%; padding: 0 .35rem; }}
.st-key-auth [data-testid="stFormSubmitButton"] button > div > span {{
  flex-direction: row-reverse;
  justify-content: space-between;
  width: 100%;
}}

/* Stack the panels on narrow screens. */
@media (max-width: 640px) {{
  .st-key-intro {{ min-height: auto; padding: 2rem 1.5rem; }}
  .eyebrow {{ margin-top: 2.5rem; }}
  .art {{ display: none; }}
  .st-key-auth {{ padding: 2.5rem 1.5rem; }}
}}
</style>
"""

INTRO = """
<div class="intro">
  <div class="brand"><span class="mark">§</span>lc-demo<span class="tag">FISCAL ASSISTANT</span></div>
  <p class="eyebrow">Brazilian fiscal compliance, in plain language</p>
  <h1>Fiscal answers,<br>without the<br><em>paperwork.</em></h1>
  <p class="lede">A chat assistant for Brazilian tax compliance. Ask a question the way you would ask
  a colleague; it checks the right source before it answers, and says so when it doesn't know.</p>
  <ul class="features">
    <li><span><b>CNPJ checks</b> — validates the check digits and reports registration status.</span></li>
    <li><span><b>ECF rules</b> — answers grounded in the ECF manual, found by semantic search.</span></li>
    <li><span><b>Filing deadlines</b> — looked up through a dedicated MCP tool server.</span></li>
    <li><span><b>Your history</b> — every conversation is saved to your account.</span></li>
  </ul>
  <div class="art" aria-hidden="true">
    <div class="ring"></div>
    <div class="card"><small>ASK ANYTHING</small><p>Is this CNPJ still active?</p><i></i><i></i></div>
    <div class="check">✓</div>
    <div class="chip">↗ ECF due July 2026</div>
    <div class="spark">✳</div>
  </div>
</div>
"""

FOOTNOTE = (
    '<div class="intro footnote"><span>Built with LangChain, LangGraph, MCP and Streamlit.</span><span>✳</span></div>'
)


def intro_panel() -> None:
    st.html(CSS)
    with st.container(key="intro"):
        st.html(INTRO)
        st.html(FOOTNOTE)


def auth_header(step: str, title: str, subtitle: str) -> None:
    st.html(f'<div class="auth-head"><div class="step">{step}</div><h2>{title}</h2><p>{subtitle}</p></div>')
