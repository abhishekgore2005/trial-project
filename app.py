import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import pypdf
import pandas as pd
import sqlite3 
import spacy
import re
from datetime import datetime
from collections import Counter
import plotly.express as px
import matplotlib.pyplot as plt
from wordcloud import WordCloud
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --- 1. SETUP & CONFIGURATION ---
st.set_page_config(page_title="AI Resume Analyst", layout="wide", page_icon="🧠")

# Load NLP Model (Cache it for speed)
# --- CHANGED: Robust Model Loading ---
@st.cache_resource
def load_nlp():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        # If the model is missing, download it via command line
        from spacy.cli import download
        download("en_core_web_sm")
        return spacy.load("en_core_web_sm")

nlp = load_nlp()

# Custom CSS for UI
st.markdown("""
    <style>
        .metric-card {
            background-color: #f0f2f6;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        [data-testid="stHeader"] {
            opacity: 0;
            transition: opacity 0.5s ease-in-out;
        }
        [data-testid="stHeader"]:hover {
            opacity: 1;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. AUTHENTICATION SETUP ---
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("⚠️ Error: 'config.yaml' file is missing. Please create it to proceed.")
    st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Login Widget
authenticator.login('main')

if st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
    st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')
    st.stop()

# --- 3. MAIN APPLICATION (Only runs if logged in) ---
elif st.session_state["authentication_status"]:
    
    # Sidebar Logout
    with st.sidebar:
        st.write(f'User: **{st.session_state["name"]}**')
        authenticator.logout('Logout', 'sidebar')
        st.divider()

    # --- DATABASE FUNCTIONS ---
    def init_db():
        conn = sqlite3.connect('resume_data.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS candidates
                     (date TEXT, filename TEXT, name TEXT, email TEXT, score REAL, experience_years INTEGER)''')
        conn.commit()
        conn.close()

    def save_to_db(data_list):
        conn = sqlite3.connect('resume_data.db')
        c = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d")
        for row in data_list:
            c.execute("SELECT * FROM candidates WHERE filename = ?", (row['Filename'],))
            if not c.fetchone():
                c.execute("INSERT INTO candidates VALUES (?,?,?,?,?,?)", 
                          (timestamp, row['Filename'], row['Name'], row['Email'], row['Match Score'], 0))
        conn.commit()
        conn.close()

    init_db()

    # --- ANALYTIC FUNCTIONS ---
    def extract_text_from_pdf(file):
        try:
            pdf_reader = pypdf.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() or ""
            return text
        except Exception:
            return ""

    def extract_entities(text):
        """Uses spaCy (NER) to find Names and Organizations"""
        doc = nlp(text)
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        email_match = re.search(email_pattern, text)
        email = email_match.group(0) if email_match else "Unknown"
        
        name = "Unknown"
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                name = ent.text
                break
                
        return name, email

    def calculate_similarity(resume_text, job_desc):
        """Calculates Semantic Similarity using TF-IDF & Cosine Similarity"""
        if not job_desc:
            return 0.0
        
        text_list = [resume_text, job_desc]
        cv = TfidfVectorizer(stop_words='english')
        count_matrix = cv.fit_transform(text_list)
        match_percentage = cosine_similarity(count_matrix)[0][1] * 100
        return round(match_percentage, 2)

    def generate_wordcloud(text):
        wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text)
        return wordcloud

    # --- APP UI ---
    st.title("🧠 AI Resume Analyst (Data Science Edition)")
    st.markdown("Powered by **NLP (spaCy)**, **Vectorization (Scikit-Learn)**, and **Interactive Dataviz (Plotly)**.")

    # Sidebar: Job Context
    with st.sidebar:
        st.header("🎯 Job Description (JD)")
        st.info("Paste the full Job Description here.")
        job_description = st.text_area("Paste JD Here", height=300, 
                                       placeholder="e.g. We are looking for a Data Analyst...")
        
        cutoff = st.slider("Minimum Match Score", 0, 100, 50)

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📂 Upload & Analyze", "📊 Batch Analytics", "🔍 Deep Dive"])

    # --- TAB 1: UPLOAD & PROCESS ---
    with tab1:
        uploaded_files = st.file_uploader("Upload Resumes (PDF)", type="pdf", accept_multiple_files=True)
        
        if 'results' not in st.session_state:
            st.session_state['results'] = None

        if uploaded_files and st.button("Analyze Resumes"):
            if not job_description:
                st.error("⚠️ Please enter a Job Description in the sidebar first!")
            else:
                with st.spinner("Vectorizing text and computing cosine similarity..."):
                    results = []
                    for file in uploaded_files:
                        text = extract_text_from_pdf(file)
                        name, email = extract_entities(text)
                        score = calculate_similarity(text, job_description)
                        
                        status = "✅ Shortlisted" if score >= cutoff else "❌ Rejected"
                        
                        results.append({
                            "Filename": file.name,
                            "Name": name,
                            "Email": email,
                            "Match Score": score,
                            "Status": status,
                            "Raw Text": text
                        })
                    
                    df = pd.DataFrame(results)
                    df = df.sort_values(by="Match Score", ascending=False)
                    st.session_state['results'] = df
                    save_to_db(results)
                    st.success(f"Processed {len(df)} resumes successfully!")

        if st.session_state['results'] is not None:
            st.dataframe(
                st.session_state['results'][['Name', 'Email', 'Match Score', 'Status']], 
                use_container_width=True
            )

    # --- TAB 2: DASHBOARD (Data Viz) ---
    with tab2:
        if st.session_state['results'] is not None:
            df = st.session_state['results']
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Match Score Distribution")
                fig_hist = px.histogram(df, x="Match Score", nbins=10, title="Candidate Score Distribution",
                                        color_discrete_sequence=['#636EFA'])
                st.plotly_chart(fig_hist, use_container_width=True)
                
            with col2:
                st.subheader("Status Breakdown")
                fig_pie = px.pie(df, names='Status', title="Shortlisted vs Rejected",
                                 color_discrete_sequence=['#00CC96', '#EF553B'])
                st.plotly_chart(fig_pie, use_container_width=True)
                
            st.subheader("Most Mentioned Keywords (Top 15)")
            all_text = " ".join(df['Raw Text'])
            words = [w.lower() for w in all_text.split() if len(w) > 5 and w.isalpha()] 
            word_counts = Counter(words).most_common(15)
            kw_df = pd.DataFrame(word_counts, columns=['Keyword', 'Count'])
            
            fig_bar = px.bar(kw_df, x='Keyword', y='Count', title="Trending Keywords in Batch",
                             color='Count', color_continuous_scale='Viridis')
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Upload and analyze resumes to see the dashboard.")

    # --- TAB 3: DEEP DIVE (Word Cloud & NER) ---
    with tab3:
        if st.session_state['results'] is not None:
            df = st.session_state['results']
            candidate_names = df['Name'].tolist()
            
            selected_candidate = st.selectbox("Select a Candidate", candidate_names)
            
            if selected_candidate:
                row = df[df['Name'] == selected_candidate].iloc[0]
                st.subheader(f"Analyzing: {row['Name']}")
                st.write(f"**Score:** {row['Match Score']}%")
                
                c1, c2 = st.columns(2)
                
                with c1:
                    st.markdown("### ☁️ Skill Cloud")
                    wc = generate_wordcloud(row['Raw Text'])
                    fig, ax = plt.subplots()
                    ax.imshow(wc, interpolation='bilinear')
                    ax.axis("off")
                    st.pyplot(fig)
                    
                with c2:
                    st.markdown("### 🤖 Entity Recognition (NER)")
                    doc = nlp(row['Raw Text'])
                    orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
                    locs = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
                    
                    st.write("**Organizations/Colleges Detected:**")
                    st.write(", ".join(set(orgs)) if orgs else "None detected")
                    
                    st.write("**Locations Detected:**")
                    st.write(", ".join(set(locs)) if locs else "None detected")
                    
                with st.expander("View Full Resume Text"):
                    st.text(row['Raw Text'])
        else:
            st.info("Upload and analyze resumes to unlock Deep Dive.")

