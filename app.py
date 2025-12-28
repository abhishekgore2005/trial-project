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
from thefuzz import process, fuzz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Pro Resume Screener", layout="wide")

# --- UI CLEAN UP (Hide GitHub, Menu, Footer) ---
st.markdown("""
    <style>
        /* Hides the top right toolbar (Share, Star, GitHub, Menu, etc.) */
        [data-testid="stToolbar"] {
            visibility: hidden;
            height: 0%;
            position: fixed;
        }
        /* Hides the standard "Made with Streamlit" footer */
        footer {
            visibility: hidden;
        }
        /* Hides the hamburger menu (top right 3 dots) */
        #MainMenu {
            visibility: hidden;
        }
        /* Adds a little padding since the header is gone */
        .block-container {
            padding-top: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('resume_history.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS candidates
                 (date TEXT, filename TEXT, email TEXT, score REAL, status TEXT, missing_skills TEXT)''')
    conn.commit()
    conn.close()

def save_to_db(data_list):
    conn = sqlite3.connect('resume_history.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in data_list:
        c.execute("INSERT INTO candidates VALUES (?,?,?,?,?,?)", 
                  (timestamp, row['Filename'], row['Email'], row['Score'], row['Status'], row['Missing Skills']))
    conn.commit()
    conn.close()

def fetch_history():
    conn = sqlite3.connect('resume_history.db')
    df = pd.read_sql_query("SELECT * FROM candidates ORDER BY date DESC", conn)
    conn.close()
    return df

# Initialize DB on app start
init_db()

# --- 3. HELPER FUNCTIONS ---
def extract_text_from_pdf(file):
    try:
        pdf_reader = pypdf.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        return ""

def extract_email_from_text(text):
    text = re.sub(r'\s+', ' ', text)
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    match = re.search(email_pattern, text)
    return match.group(0) if match else None

def calculate_score_fuzzy(text, required_skills, required_edu):
    text = text.lower()
    text_words = set(text.split())
    
    # 1. Education
    edu_matches = [edu for edu in required_edu if edu in text]
    edu_score = 30 if edu_matches else 0
    
    # 2. Skills (Fuzzy)
    skill_matches = []
    missing_skills = []
    
    for skill in required_skills:
        if skill in text:
            skill_matches.append(skill)
        else:
            match = process.extractOne(skill, text_words, scorer=fuzz.ratio)
            if match and match[1] >= 85:
                skill_matches.append(skill)
            else:
                missing_skills.append(skill)
    
    if required_skills:
        skill_score = (len(skill_matches) / len(required_skills)) * 70
    else:
        skill_score = 0
        
    return round(edu_score + skill_score, 2), missing_skills

def send_email(to_email, subject, body_html):
    try:
        sender_email = st.secrets["email"]["address"]
        sender_password = st.secrets["email"]["password"]
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body_html, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Email Error: {e}")
        return False

# --- 4. AUTH & CONFIG ---
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("Error: 'config.yaml' not found.")
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

# --- 5. MAIN APPLICATION ---
elif st.session_state["authentication_status"]:
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.write(f'User: *{st.session_state["name"]}*')
    st.sidebar.divider()

    st.title("🚀 Pro Resume Screener v2.0")
    
    tab1, tab2 = st.tabs(["📄 Analysis Board", "🗄️ History Database"])

    # --- SIDEBAR INPUTS ---
    with st.sidebar:
        st.header("1. Job Criteria")
        DEFAULT_SKILLS = "python, sql, machine learning, power bi, excel"
        req_skills_input = st.text_area("Required Skills", DEFAULT_SKILLS)
        req_edu_input = st.text_area("Required Education", "b.tech, mca, bca, computer science")
        cutoff = st.slider("Cutoff Score (%)", 0, 100, 60)
        
        REQUIRED_SKILLS = [s.strip().lower() for s in req_skills_input.split(",") if s.strip()]
        REQUIRED_EDUCATION = [e.strip().lower() for e in req_edu_input.split(",") if e.strip()]
        
        st.divider()
        st.header("2. Email Automation")
        enable_email = st.checkbox("Enable Auto-Emailing", value=False)
        if enable_email: st.success("✅ Active")

    # --- TAB 1: ANALYSIS ---
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            uploaded_files = st.file_uploader("Upload Resumes (PDF)", type="pdf", accept_multiple_files=True)
        with col2:
            st.info("💡 New: Fuzzy logic is enabled. 'PowerBI' will match 'Power BI'.")

        if 'results' not in st.session_state:
            st.session_state['results'] = None

        if uploaded_files and st.button(f"Analyze {len(uploaded_files)} Resumes"):
            results_data = []
            progress_bar = st.progress(0)
            
            for i, file in enumerate(uploaded_files):
                text = extract_text_from_pdf(file)
                candidate_email = extract_email_from_text(text)
                
                score, missing_skills = calculate_score_fuzzy(text, REQUIRED_SKILLS, REQUIRED_EDUCATION)
                
                status = "SELECTED" if score >= cutoff else "REJECTED"
                email_sent_status = "Skipped"

                if enable_email and candidate_email:
                    if status == "SELECTED":
                        subject = "Interview Invitation"
                        body = f"<html><body><h2 style='color:green'>Shortlisted!</h2><p>Score: {score}%</p></body></html>"
                        email_success = send_email(candidate_email, subject, body)
                    else:
                        subject = "Application Update"
                        body = f"<html><body><h2 style='color:gray'>Update</h2><p>Missing: {', '.join(missing_skills[:3])}</p></body></html>"
                        email_success = send_email(candidate_email, subject, body)
                    
                    email_sent_status = "Sent" if email_success else "Failed"
                elif enable_email and not candidate_email:
                    email_sent_status = "No Email"

                results_data.append({
                    "Filename": file.name,
                    "Email": candidate_email,
                    "Score": score,
                    "Status": status,
                    "Missing Skills": ", ".join(missing_skills),
                    "Email Status": email_sent_status,
                    "Raw Text": text
                })
                progress_bar.progress((i + 1) / len(uploaded_files))
            
            st.session_state['results'] = pd.DataFrame(results_data)
            save_to_db(results_data)
            st.success("Analysis Complete & Saved to History!")

        # --- DISPLAY RESULTS ---
        if st.session_state['results'] is not None:
            df = st.session_state['results']
            
            df['Status'] = df['Score'].apply(lambda x: "SELECTED" if x >= cutoff else "REJECTED")

            c1, c2 = st.columns([2, 1])
            
            with c1:
                st.subheader("Results Table")
                def color_row(row):
                    return ['background-color: #d4edda' if row['Status'] == 'SELECTED' else 'background-color: #f8d7da'] * len(row)
                
                display_cols = ['Filename', 'Email', 'Score', 'Status', 'Missing Skills', 'Email Status']
                st.dataframe(df[display_cols].style.apply(color_row, axis=1), use_container_width=True)

            with c2:
                st.subheader("📊 Market Insights")
                all_missing = [skill for sublist in df['Missing Skills'].str.split(', ') for skill in sublist if skill]
                if all_missing:
                    missing_counts = pd.DataFrame(Counter(all_missing).items(), columns=['Skill', 'Count'])
                    st.bar_chart(missing_counts.set_index('Skill'), color="#ff4b4b")
                else:
                    st.write("No missing skills detected!")

            st.divider()
            st.subheader("👁️ Resume Deep Dive")
            selected_file = st.selectbox("Select Candidate to Preview", df['Filename'])
            
            if selected_file:
                candidate_text = df[df['Filename'] == selected_file]['Raw Text'].values[0]
                st.text_area("Extracted Text Content", candidate_text, height=200)

    # --- TAB 2: HISTORY ---
    with tab2:
        st.header("🗄️ Database History")
        history_df = fetch_history()
        
        if not history_df.empty:
            st.dataframe(history_df, use_container_width=True)
            csv = history_df.to_csv(index=False).encode('utf-8')
            st.download_button("Download Full History (CSV)", csv, "full_history.csv", "text/csv")
            
            if st.button("Clear History"):
                conn = sqlite3.connect('resume_history.db')
                conn.execute("DELETE FROM candidates")
                conn.commit()
                conn.close()
                st.rerun()
        else:
            st.info("No history found in database.")
