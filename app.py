import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import pypdf
import smtplib
import re
import pandas as pd
import sqlite3
from datetime import datetime
from collections import Counter
import plotly.express as px
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="AI Resume Analyst Pro", layout="wide", page_icon="🧠")

# --- UI TWEAKS ---
st.markdown("""
    <style>
        .metric-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; }
        [data-testid="stHeader"] { opacity: 0; transition: opacity 0.5s ease-in-out; }
        [data-testid="stHeader"]:hover { opacity: 1; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURATION & CREDENTIALS ---
# ⚠️ SECURITY NOTE: Ideally use st.secrets for this. 
# If you must hardcode for a student project, replace the values below.
EMAIL_ADDRESS = "hirebot.project@gmail.com"  # <--- REPLACE THIS
EMAIL_PASSWORD = "nfyq ghye qzlw bmcb"    # <--- REPLACE THIS

# --- 3. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('resume_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS candidates
                 (date TEXT, filename TEXT, email TEXT, score REAL, status TEXT)''')
    conn.commit()
    conn.close()

def save_to_db(data_list):
    conn = sqlite3.connect('resume_data.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in data_list:
        c.execute("INSERT INTO candidates VALUES (?,?,?,?,?)", 
                  (timestamp, row['Filename'], row['Email'], row['Match Score'], row['Status']))
    conn.commit()
    conn.close()

def fetch_history():
    conn = sqlite3.connect('resume_data.db')
    try:
        df = pd.read_sql_query("SELECT * FROM candidates ORDER BY date DESC", conn)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

init_db()

# --- 4. CORE FUNCTIONS (Data Science Upgrade) ---

def extract_text_from_pdf(file):
    try:
        pdf_reader = pypdf.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    except:
        return ""

def extract_email(text):
    match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    return match.group(0) if match else None

def calculate_similarity(resume_text, job_desc):
    """Upgraded to use Cosine Similarity (TF-IDF) instead of just keywords"""
    if not job_desc: return 0.0
    text_list = [resume_text, job_desc]
    cv = TfidfVectorizer(stop_words='english')
    count_matrix = cv.fit_transform(text_list)
    match_percentage = cosine_similarity(count_matrix)[0][1] * 100
    return round(match_percentage, 2)

def send_email_notification(to_email, status, score):
    if "YOUR_EMAIL" in EMAIL_ADDRESS: 
        return "Not Configured" 
        
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        
        if status == "✅ Shortlisted":
            msg['Subject'] = "Interview Invitation: Shortlisted"
            body = f"<html><body><h2 style='color:green'>Congratulations!</h2><p>Your profile matched our requirements with a score of <b>{score}%</b>.</p></body></html>"
        else:
            msg['Subject'] = "Application Update"
            body = f"<html><body><h2 style='color:gray'>Application Status</h2><p>Thank you for applying. Unfortunately, your score of {score}% did not meet our cutoff.</p></body></html>"
            
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        server.quit()
        return "Sent"
    except Exception as e:
        return f"Failed: {e}"

# --- 5. AUTHENTICATION ---
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("⚠️ Config.yaml not found!")
    st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

authenticator.login()

if st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
    st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')
    st.stop()

# --- 6. MAIN APP LOGIC ---
elif st.session_state["authentication_status"]:
    
    with st.sidebar:
        st.write(f'User: **{st.session_state["name"]}**')
        authenticator.logout('Logout', 'sidebar')
        st.divider()
        st.header("⚙️ Settings")
        cutoff = st.slider("Minimum Match Score (%)", 0, 100, 50)
        enable_email = st.checkbox("Enable Auto-Emailing", value=False)

    st.title("🧠 AI Resume Analyst (Data Science Edition)")
    
    tab1, tab2 = st.tabs(["📂 Analysis Board", "📊 Analytics & History"])

    # --- TAB 1: UPLOAD & PROCESS ---
    with tab1:
        col1, col2 = st.columns([1, 2])
        with col1:
            uploaded_files = st.file_uploader("Upload Resumes (PDF)", type="pdf", accept_multiple_files=True)
        with col2:
            job_description = st.text_area("Paste Job Description (JD)", height=150, 
                                           placeholder="Paste the full JD here. The AI will compare resumes against this text...")

        if uploaded_files and st.button(f"Analyze {len(uploaded_files)} Resumes"):
            if not job_description:
                st.error("⚠️ Please paste a Job Description first!")
            else:
                results = []
                progress = st.progress(0)
                
                for i, file in enumerate(uploaded_files):
                    text = extract_text_from_pdf(file)
                    email = extract_email(text)
                    score = calculate_similarity(text, job_description)
                    status = "✅ Shortlisted" if score >= cutoff else "❌ Rejected"
                    
                    email_status = "Skipped"
                    if enable_email and email:
                        email_status = send_email_notification(email, status, score)
                    elif enable_email and not email:
                        email_status = "No Email Found"
                        
                    results.append({
                        "Filename": file.name,
                        "Email": email,
                        "Match Score": score,
                        "Status": status,
                        "Email Status": email_status
                    })
                    progress.progress((i + 1) / len(uploaded_files))
                
                # Save & Display
                save_to_db(results)
                df = pd.DataFrame(results)
                df = df.sort_values(by="Match Score", ascending=False)
                
                st.success("Processing Complete!")
                st.dataframe(df, use_container_width=True)

    # --- TAB 2: ANALYTICS ---
    with tab2:
        history_df = fetch_history()
        if not history_df.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Score Distribution")
                fig = px.histogram(history_df, x="score", nbins=10, title="Candidate Scores", color_discrete_sequence=['#636EFA'])
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.subheader("Status Breakdown")
                fig2 = px.pie(history_df, names="status", title="Shortlisted vs Rejected", color_discrete_sequence=['#00CC96', '#EF553B'])
                st.plotly_chart(fig2, use_container_width=True)
                
            st.dataframe(history_df, use_container_width=True)
            
            if st.button("Clear History Database"):
                conn = sqlite3.connect('resume_data.db')
                conn.execute("DELETE FROM candidates")
                conn.commit()
                conn.close()
                st.rerun()
        else:
            st.info("No historical data found.")
