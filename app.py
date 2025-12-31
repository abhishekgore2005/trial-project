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

# --- UI CLEAN UP (Show Toolbar ONLY on Hover) ---
st.markdown("""
    <style>
        /* Make the header transparent by default */
        [data-testid="stHeader"] {
            opacity: 0;
            transition: opacity 0.5s ease-in-out;
        }

        /* Make it visible when you hover over it */
        [data-testid="stHeader"]:hover {
            opacity: 1;
        }

        /* Hides the standard "Made with Streamlit" footer completely */
        footer {
            visibility: hidden;
        }

        /* Adds a little padding since the header visually disappears */
        .block-container {
            padding-top: 2rem;
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

# LOGIN WIDGET
name, authentication_status, username = authenticator.login('Login', 'main')

if authentication_status is False:
    st.error('Username/password is incorrect')
    st.stop()
elif authentication_status is None:
    st.warning('Please enter your username and password')
    st.stop()

# --- 5. MAIN APPLICATION ---
if authentication_status:
    # LOGOUT BUTTON
    authenticator.logout('Logout', 'sidebar')
    
    st.sidebar.write(f'User: *{name}*')
    st.sidebar.divider()

    st.title("🚀 Pro Resume Screener v2.0")
    
    tab1, tab2 = st.tabs(["📄 Analysis Board", "🗄️ History Database"])
