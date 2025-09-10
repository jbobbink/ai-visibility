import re
import time
import json
import base64
from collections import Counter

import streamlit as st

# --- OpenAI client with backward compatibility (v1+ and legacy) ---
class OpenAIClient:
    def __init__(self, api_key: str):
        self.use_modern = False
        self.client = None
        self.legacy = None
        try:
            from openai import OpenAI  # v1+
            self.client = OpenAI(api_key=api_key)
            self.use_modern = True
        except Exception:
            import openai as legacy  # legacy
            legacy.api_key = api_key
            self.legacy = legacy

    def chat(self, model: str, messages: list, max_tokens: int):
        if self.use_modern:
            return self.client.chat.completions.create(
                model=model, messages=messages, max_tokens=max_tokens
            ).choices[0].message.content
        else:
            # Legacy path
            resp = self.legacy.ChatCompletion.create(
                model=model, messages=messages, max_tokens=max_tokens
            )
            # robust extraction
            choice = resp["choices"][0]
            if isinstance(choice, dict):
                return choice["message"]["content"]
            return choice.message["content"]


# -----------------------------
# Analyzer Class
# -----------------------------
class ResourceAnalyzer:
    def __init__(self, api_key, model="gpt-4o", max_tokens=1000, system_prompt="", user_prompt="", brand_list=None):
        self.client = OpenAIClient(api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.brand_list = brand_list if brand_list else []

    def extract_urls(self, text):
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w%!.?&=+]*)*'
        domain_pattern = r'(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]{0,62}\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62}\.[a-zA-Z]{2,}|[a-zA-Z0-9][-a-zA-Z0-9]{0,62}\.[a-zA-Z]{2,})'

        urls = re.findall(url_pattern, text or "")
        domains = re.findall(domain_pattern, text or "")

        url_domains = []
        for url in urls:
            domain_match = re.search(r'https?://(?:www\.)?([^/]+)', url)
            if domain_match:
                url_domains.append(domain_match.group(1))

        all_domains = list(set(domains + url_domains))
        return {"full_urls": urls, "domains": all_domains}

    def extract_product_names(self, text):
        product_mentions = []
        for product in self.brand_list:
            if re.search(r'\b' + re.escape(product) + r'\b', text or "", re.IGNORECASE):
                product_mentions.append(product)
        return product_mentions

    def analyze_response(self, response_text):
        return {
            "resources": self.extract_urls(response_text),
            "products": self.extract_product_names(response_text),
            "response_length": len(response_text or ""),
        }

    def get_response(self, question):
        try:
            user_msg = self.user_prompt.replace("{question}", question)
            return self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                max_tokens=self.max_tokens
            )
        except Exception as e:
            st.error(f"Error calling OpenAI API: {e}")
            time.sleep(2)
            return None


# -----------------------------
# HTML Export helpers
# -----------------------------
def html_escape(s: str) -> str:
    """Escape text for safe HTML embedding."""
    if s is None:
        return ""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )

def generate_html_report(*, results, mentions, brand_list, system_prompt, user_prompt, questions, model):
    """Self-contained HTML with working search + collapsible answers + prompts shown."""
    # Build brand mention list (keep original order submitted)
    brand_items = []
    for brand in brand_list:
        brand_items.append((brand, mentions["products"].get(brand, 0)))

    # Build the results section with <details>/<summary> and a robust search index
    result_cards = []
    for r in results:
        q = r["question"] or ""
        a = r["response"] or ""
        safe_q = html_escape(q)
        safe_a = html_escape(a)
        # Precompute a searchable, lowercased string in a data attribute (no quotes/newlines)
        data_search = (q + " " + a).lower().replace("\n", " ").replace('"', "'")
        card = f"""
        <details class="result" data-search="{html_escape(data_search)}">
            <summary class="question">Q: {safe_q}</summary>
            <div class="answer">{safe_a}</div>
        </details>
        """
        result_cards.append(card)

    # Simple, robust search (filters by data-search attribute)
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AI Visibility Report</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    :root {{
        --bg:#fff; --fg:#222; --muted:#666; --card:#f8f8f8; --accent:#2563eb; --chip:#eef2ff;
        --border:#e5e7eb;
    }}
    body {{
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
        margin: 24px; background: var(--bg); color: var(--fg);
    }}
    h1,h2 {{ margin: 0 0 12px; }}
    .section {{ margin: 20px 0 28px; }}
    .grid {{ display: grid; gap: 12px; }}
    .muted {{ color: var(--muted); }}
    .kbd {{ font: 12px/1.2 Menlo, Consolas, monospace; background: var(--card); padding: 2px 6px; border-radius: 6px; border:1px solid var(--border); }}
    .panel {{
        background: var(--card); border:1px solid var(--border); border-radius:12px; padding:16px;
    }}
    .brand-list li {{ margin: 6px 0; }}
    .badge {{
        background: var(--chip); color: var(--accent); font-weight: 600;
        padding: 2px 8px; border-radius: 999px; margin-left: 8px;
        border:1px solid #dbeafe;
    }}
    .search-box input {{
        width:100%; padding:12px 14px; font-size:16px;
        border-radius:10px; border:1px solid var(--border); outline: none;
    }}
    .result {{
        border:1px solid var(--border); border-radius:12px; padding:0; background:#fff;
    }}
    .result + .result {{ margin-top: 10px; }}
    .result > summary {{
        cursor: pointer; list-style:none; padding:14px 16px; font-weight:600;
    }}
    .result[open] > summary {{ border-bottom:1px solid var(--border); background: #fafafa; }}
    .question::marker {{ display:none; }}
    .answer {{ padding:16px; white-space: pre-wrap; }}
    .pill {{
        display:inline-block; padding:2px 8px; border-radius:999px; background:#f1f5f9; color:#0f172a; font-size:12px;
        border:1px solid var(--border); margin-right:6px;
    }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    @media (prefers-color-scheme: dark) {{
        :root {{
            --bg:#0b0f19; --fg:#e5e7eb; --muted:#9aa2b1; --card:#111827; --accent:#93c5fd; --chip:#1f2937; --border:#202939;
        }}
        .result {{ background:#0f172a; }}
    }}
</style>
<script>
document.addEventListener('DOMContentLoaded', function() {{
    const input = document.getElementById('searchInput');
    const cards = Array.from(document.querySelectorAll('.result'));

    function filter() {{
        const q = (input.value || '').toLowerCase().trim();
        for (const el of cards) {{
            const hay = el.getAttribute('data-search');
            if (!q) {{
                el.style.display = '';
            }} else {{
                el.style.display = (hay && hay.indexOf(q) !== -1) ? '' : 'none';
            }}
        }}
    }}

    input.addEventListener('input', filter);
    input.addEventListener('keyup', filter);
}});
</script>
</head>
<body>

    <h1>🔍 AI Visibility Report</h1>

    <div class="section panel">
        <div><span class="pill">Model</span> {html_escape(model)}</div>
        <div style="margin-top:10px;">
            <span class="pill">System prompt</span>
            <pre style="margin:8px 0 0; white-space:pre-wrap;">{html_escape(system_prompt)}</pre>
        </div>
        <div style="margin-top:10px;">
            <span class="pill">User prompt template</span>
            <pre style="margin:8px 0 0; white-space:pre-wrap;">{html_escape(user_prompt)}</pre>
        </div>
    </div>

    <div class="section panel">
        <h2>Questions asked</h2>
        <ol class="grid" style="margin-top:10px;">
            {''.join(f'<li>{html_escape(q)}</li>' for q in questions)}
        </ol>
    </div>

    <div class="section panel">
        <h2>Brand mentions</h2>
        <ul class="brand-list" style="margin-top:10px;">
            {''.join(f'<li>{html_escape(b)} <span class="badge">{c}</span></li>' for b,c in brand_items)}
        </ul>
    </div>

    <div class="section search-box">
        <input id="searchInput" type="text" placeholder="Type to filter questions & answers… (live search)">
        <div class="muted" style="margin-top:6px;">Tip: press <span class="kbd">/</span> to focus search in many browsers.</div>
    </div>

    <div class="section">
        <h2>Responses</h2>
        <div class="grid" style="margin-top:10px;">
            {''.join(result_cards)}
        </div>
    </div>

</body>
</html>"""
    return html


# -----------------------------
# Streamlit UI
# -----------------------------
st.title("🔍 Custom AI Visibility & Resource Analyzer")

api_key = st.text_input("Enter your OpenAI API key", type="password")

# Prompts
st.subheader("⚙️ Prompt Configuration")
system_prompt = st.text_area("System Role Prompt", "You are a helpful assistant who provides detailed information about institutional investments")
user_prompt = st.text_area("User Role Prompt (use {question} as placeholder)", "I'm an institutional investor with the following question. {question}")

# Brand list
st.subheader("🏢 Brand / Product List")
brand_input = st.text_area("Enter brand names (one per line)", "BlackRock\nVanguard\nUBS\nFidelity\nGoldman Sachs")
brand_list = [b.strip() for b in brand_input.splitlines() if b.strip()]

# Questions
st.subheader("❓ Questions to Ask")
questions_input = st.text_area("Enter questions (one per line)",
"""How do you evaluate the risk profile of corporate treasurers & cfos?
How do you evaluate the risk profile of endowments & foundations?
What are the key factors to consider when selecting institutional investors?""")
questions = [q.strip() for q in questions_input.splitlines() if q.strip()]

# Model + limit
model = st.selectbox("Choose model", ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-3.5-turbo"])
if len(questions) == 0:
    st.stop()
limit = st.slider("Number of questions to analyze", 1, len(questions), min(5, len(questions)))

# Run
if api_key and st.button("🚀 Run Analysis"):
    analyzer = ResourceAnalyzer(
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        brand_list=brand_list
    )

    results = []
    mentions = {"domains": Counter(), "products": Counter()}

    progress = st.progress(0)
    for i, question in enumerate(questions[:limit]):
        resp = analyzer.get_response(question)
        if resp:
            analysis = analyzer.analyze_response(resp)
            results.append({
                "question": question,
                "response": resp,
                "analysis": analysis
            })
            for d in analysis["resources"]["domains"]:
                mentions["domains"][d] += 1
            for p in analysis["products"]:
                mentions["products"][p] += 1
        progress.progress((i+1)/limit)

    # Summary
    st.subheader("📊 Top Mentioned Brands")
    st.json(dict(mentions["products"].most_common()))

    st.subheader("📄 Detailed Responses")
    for r in results:
        with st.expander(r["question"]):
            st.write(r["response"])
            st.caption(f"Domains: {', '.join(r['analysis']['resources']['domains']) or '—'}")
            if r["analysis"]["products"]:
                st.caption(f"Brand hits: {', '.join(r['analysis']['products'])}")

    # Downloads (JSON)
    summary = {
        "domains": dict(mentions["domains"].most_common()),
        "products": dict(mentions["products"].most_common()),
        "total_questions": len(results),
        "model_used": model,
    }
    st.subheader("⬇️ Download JSON")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Detailed Results (JSON)",
            data=json.dumps(results, indent=2),
            file_name="ai_visibility_detailed.json",
            mime="application/json"
        )
    with c2:
        st.download_button(
            "Summary (JSON)",
            data=json.dumps(summary, indent=2),
            file_name="ai_visibility_summary.json",
            mime="application/json"
        )

    # HTML report (search + collapsible + prompts)
    html_report = generate_html_report(
        results=results,
        mentions=mentions,
        brand_list=brand_list,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        questions=questions[:limit],
        model=model
    )

    st.subheader("👀 Preview Report")
    st.components.v1.html(html_report, height=650, scrolling=True)

    # Open-in-new-tab link (data URL)
    b64 = base64.b64encode(html_report.encode("utf-8")).decode("utf-8")
    st.markdown(f'<a href="data:text/html;base64,{b64}" target="_blank">Open full-size preview in a new tab</a>', unsafe_allow_html=True)

    # Download HTML
    st.download_button(
        label="⬇️ Download HTML Report",
        data=html_report,
        file_name="ai_visibility_report.html",
        mime="text/html"
    )
