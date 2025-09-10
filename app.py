import re
import time
import json
from collections import Counter
import openai
import streamlit as st
from io import BytesIO

# -----------------------------
# Analyzer Class
# -----------------------------
class ResourceAnalyzer:
    def __init__(self, api_key, model="gpt-4o", max_tokens=1000, system_prompt="", user_prompt="", brand_list=None):
        openai.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.brand_list = brand_list if brand_list else []

    def extract_urls(self, text):
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w%!.?&=+]*)*'
        domain_pattern = r'(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]{0,62}\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62}\.[a-zA-Z]{2,}|[a-zA-Z0-9][-a-zA-Z0-9]{0,62}\.[a-zA-Z]{2,})'

        urls = re.findall(url_pattern, text)
        domains = re.findall(domain_pattern, text)

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
            if re.search(r'\b' + re.escape(product) + r'\b', text, re.IGNORECASE):
                product_mentions.append(product)
        return product_mentions

    def analyze_response(self, response_text):
        return {
            "resources": self.extract_urls(response_text),
            "products": self.extract_product_names(response_text),
            "response_length": len(response_text),
        }

    def get_response(self, question):
        try:
            user_msg = self.user_prompt.replace("{question}", question)
            response = openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                max_tokens=self.max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            st.error(f"Error calling OpenAI API: {e}")
            time.sleep(5)
            return None

# -----------------------------
# HTML Export
# -----------------------------
def generate_html_report(results, mentions, brand_list):
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>AI Visibility Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1 {{ color: #333; }}
            .search-box {{ margin-bottom: 20px; }}
            .result {{ border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin-bottom: 10px; }}
            .question {{ font-weight: bold; margin-bottom: 10px; }}
            .response {{ white-space: pre-wrap; }}
            .badge {{ background: #007BFF; color: white; padding: 2px 6px; border-radius: 6px; margin-left: 6px; font-size: 12px; }}
        </style>
        <script>
            function searchResults() {{
                var input = document.getElementById("searchInput").value.toLowerCase();
                var results = document.getElementsByClassName("result");
                for (var i = 0; i < results.length; i++) {{
                    var text = results[i].innerText.toLowerCase();
                    results[i].style.display = text.includes(input) ? "" : "none";
                }}
            }}
        </script>
    </head>
    <body>
        <h1>🔍 AI Visibility Report</h1>
        <div class="search-box">
            <input type="text" id="searchInput" onkeyup="searchResults()" placeholder="Search in results..." style="width:100%; padding:8px;">
        </div>
        <h2>🏢 Brand Mentions</h2>
        <ul>
    """
    for brand in brand_list:
        count = mentions["products"].get(brand, 0)
        html += f"<li>{brand} <span class='badge'>{count}</span></li>"
    html += "</ul><h2>📄 Responses</h2>"

    for r in results:
        html += f"""
        <div class="result">
            <div class="question">{r['question']}</div>
            <div class="response">{r['response']}</div>
        </div>
        """
    html += "</body></html>"
    return html

# -----------------------------
# Streamlit UI
# -----------------------------
st.title("🔍 Custom AI Visibility & Resource Analyzer")

api_key = st.text_input("Enter your OpenAI API key", type="password")

st.subheader("⚙️ Prompt Configuration")
system_prompt = st.text_area("System Role Prompt", "You are a helpful assistant who provides detailed information about institutional investments")
user_prompt = st.text_area("User Role Prompt (use {{question}} as placeholder)", "I'm an institutional investor with the following question. {question}")

st.subheader("🏢 Brand / Product List")
brand_input = st.text_area("Enter brand names (one per line)", "BlackRock\nVanguard\nUBS\nFidelity\nGoldman Sachs")
brand_list = [b.strip() for b in brand_input.splitlines() if b.strip()]

st.subheader("❓ Questions to Ask")
questions_input = st.text_area("Enter questions (one per line)",
"""How do you evaluate the risk profile of corporate treasurers & cfos?
How do you evaluate the risk profile of endowments & foundations?
What are the key factors to consider when selecting institutional investors?""")
questions = [q.strip() for q in questions_input.splitlines() if q.strip()]

model = st.selectbox("Choose model", ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-3.5-turbo"])
limit = st.slider("Number of questions to analyze", 1, len(questions), min(5, len(questions)))

if api_key and st.button("🚀 Run Analysis"):
    analyzer = ResourceAnalyzer(api_key=api_key, model=model, system_prompt=system_prompt, user_prompt=user_prompt, brand_list=brand_list)

    results = []
    mentions = {"domains": Counter(), "products": Counter()}

    progress = st.progress(0)
    for i, question in enumerate(questions[:limit]):
        resp = analyzer.get_response(question)
        if resp:
            analysis = analyzer.analyze_response(resp)
            results.append({"question": question, "response": resp, "analysis": analysis})
            for d in analysis["resources"]["domains"]:
                mentions["domains"][d] += 1
            for p in analysis["products"]:
                mentions["products"][p] += 1
        progress.progress((i+1)/limit)

    st.subheader("📊 Top Mentioned Brands")
    st.json(dict(mentions["products"].most_common()))

    st.subheader("📄 Detailed Responses")
    for r in results:
        with st.expander(r["question"]):
            st.write(r["response"])

    # Export as HTML
    html_report = generate_html_report(results, mentions, brand_list)

    # Preview inside Streamlit
    st.subheader("👀 Preview Report")
    st.components.v1.html(html_report, height=600, scrolling=True)

    # Download button
    st.download_button(
        label="⬇️ Download HTML Report",
        data=html_report,
        file_name="ai_visibility_report.html",
        mime="text/html"
    )
