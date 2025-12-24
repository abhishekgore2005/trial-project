import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import pypdf
import smtplib
import re
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Pro Resume Screener", layout="wide")

# --- 2. HELPER FUNCTIONS ---
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
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    match = re.search(email_pattern, text)
    return match.group(0) if match else None

def calculate_score(text, required_skills, required_edu):
    text = text.lower()
    # Education (30%)
    edu_matches = [edu for edu in required_edu if edu in text]
    edu_score = 30 if edu_matches else 0
    # Skills (70%)
    skill_matches = [skill for skill in required_skills if skill in text]
    missing_skills = [skill for skill in required_skills if skill not in text]
    if required_skills:
        skill_score = (len(skill_matches) / len(required_skills)) * 70
    else:
        skill_score = 0
    return round(edu_score + skill_score, 2), missing_skills

def send_email(to_email, subject, body, sender_email, sender_password):
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return False

# --- 3. AUTHENTICATION SETUP ---
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("Error: 'config.yaml' file not found. Please create it!")
    st.stop()

# FIX: Removed 'config['preauthorized']' to fix DeprecationError
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# --- 4. LOGIN LOGIC ---
authenticator.login()

if st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
    st.stop()
    
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')
    st.stop()
    
elif st.session_state["authentication_status"]:
    # --- 5. MAIN APP (Runs only when logged in) ---
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    st.sidebar.divider()

    # --- RESUME SCREENER LOGIC STARTS HERE ---
    DEFAULT_SKILLS = "python, sql, machine learning, tableau, excel"
    DEFAULT_EDU = "b.tech, computer science, mca, bca"
    CUTOFF_SCORE = 65 
    SENDER_EMAIL = "your_email@gmail.com"
    SENDER_PASSWORD = "xxxx xxxx xxxx xxxx" 

    st.title("🚀 Pro Resume Screening System")

    with st.sidebar:
        st.header("1. Job Criteria")
        req_skills_input = st.text_area("Required Skills", DEFAULT_SKILLS)
        req_edu_input = st.text_area("Required Education", DEFAULT_EDU)
        cutoff = st.slider("Cutoff Score (%)", 0, 100, CUTOFF_SCORE)
        
        REQUIRED_SKILLS = [s.strip().lower() for s in req_skills_input.split(",") if s.strip()]
        REQUIRED_EDUCATION = [e.strip().lower() for e in req_edu_input.split(",") if e.strip()]
        
        st.divider()
        st.header("2. Email Automation")
        enable_email = st.checkbox("Enable Auto-Emailing", value=False)

    col1, col2, col3 = st.columns(3)
    col1.metric("Target Score", f"{cutoff}%")
    col2.metric("Skills Looked For", len(REQUIRED_SKILLS))
    col3.metric("Education Looked For", len(REQUIRED_EDUCATION))

    uploaded_files = st.file_uploader("Upload Resumes (PDF)", type="pdf", accept_multiple_files=True)

    if uploaded_files and st.button(f"Analyze {len(uploaded_files)} Resumes"):
        results_data = []
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            text = extract_text_from_pdf(file)
            candidate_email = extract_email_from_text(text)
            score, missing_skills = calculate_score(text, REQUIRED_SKILLS, REQUIRED_EDUCATION)
            status = "SELECTED" if score >= cutoff else "REJECTED"
            
            email_sent = "Skipped"
            if enable_email and candidate_email:
                if status == "SELECTED":
                    subj = "Interview Invitation"
                    body = f"Dear Candidate,\n\nYour resume has been shortlisted. Score: {score}%.\n\nBest regards,\nRecruitment Team"
                    if send_email(candidate_email, subj, body, SENDER_EMAIL, SENDER_PASSWORD):
                        email_sent = "Sent (Invite)"
                    else:
                        email_sent = "Failed"
                else:
                    subj = "Application Update"
                    body = f"Dear Candidate,\n\nWe have decided to proceed with other candidates.\n\nBest regards,\nRecruitment Team"
                    if send_email(candidate_email, subj, body, SENDER_EMAIL, SENDER_PASSWORD):
                        email_sent = "Sent (Reject)"
                    else:
                        email_sent = "Failed"
            elif enable_email and not candidate_email:
                 email_sent = "No Email Found"

            results_data.append({
                "Filename": file.name,
                "Email": candidate_email,
                "Score": score,
                "Status": status,
                "Missing Skills": ", ".join(missing_skills),
                "Email Status": email_sent
            })
            progress_bar.progress((i + 1) / len(uploaded_files))

        st.success("Processing Complete!")
        df = pd.DataFrame(results_data)
        
        colA, colB = st.columns(2)
        with colA:
            st.bar_chart(df['Status'].value_counts())
        with colB:
            st.bar_chart(df.set_index('Filename')['Score'])

        def color_status(val):
            return f'color: {"green" if val == "SELECTED" else "red"}; font-weight: bold'

        st.dataframe(df.style.map(color_status, subset=['Status']), use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Report (CSV)", csv, "hiring_report.csv", "text/csv")

    elif not uploaded_files:
        st.info("Waiting for PDF uploads...")