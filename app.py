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

# --- CREDENTIALS (Integrated) ---
SENDER_EMAIL = "hirebot.project@gmail.com"
SENDER_PASSWORD = "nfyq ghye qzlw bmcb"

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
    # Clean text to ensure regex works even with weird PDF spacing
    text = text.replace('\n', ' ')
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

def send_email(to_email, subject, body_html, sender_email, sender_password):
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Attach HTML body
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

# --- 3. AUTHENTICATION SETUP ---
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("Error: 'config.yaml' file not found. Please create it!")
    st.stop()

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
    # --- 5. MAIN APP ---
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    st.sidebar.divider()

    # Constants
    DEFAULT_SKILLS = "python, sql, machine learning, tableau, excel"
    DEFAULT_EDU = "b.tech, computer science, mca, bca"
    
    st.title("🚀 Smart HR Resume Screening System")
    st.markdown("### Automated Screening & Email Notification Module")

    with st.sidebar:
        st.header("1. Job Criteria")
        req_skills_input = st.text_area("Required Skills", DEFAULT_SKILLS)
        req_edu_input = st.text_area("Required Education", DEFAULT_EDU)
        cutoff = st.slider("Cutoff Score (%)", 0, 100, 65)
        
        REQUIRED_SKILLS = [s.strip().lower() for s in req_skills_input.split(",") if s.strip()]
        REQUIRED_EDUCATION = [e.strip().lower() for e in req_edu_input.split(",") if e.strip()]
        
        st.divider()
        st.header("2. Email Automation")
        enable_email = st.checkbox("Enable Auto-Emailing", value=False)
        
        if enable_email:
             st.success("✅ Email System Active")

    # Dashboard Metrics
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
            
            email_sent_status = "Skipped"
            
            # --- EMAIL LOGIC ---
            if enable_email and candidate_email:
                if status == "SELECTED":
                    subject = "Interview Invitation - HR Team"
                    body = f"""
                    <html>
                        <body>
                            <h2 style="color: #2e6c80;">Congratulations!</h2>
                            <p>Dear Candidate,</p>
                            <p>We are pleased to inform you that your resume has been shortlisted for the next round.</p>
                            <p><strong>Screening Score:</strong> {score}%</p>
                            <p>Our HR team will contact you shortly regarding the interview schedule.</p>
                            <br>
                            <p>Best regards,<br><strong>Talent Acquisition Team</strong></p>
                        </body>
                    </html>
                    """
                    if send_email(candidate_email, subject, body, SENDER_EMAIL, SENDER_PASSWORD):
                        email_sent_status = "Sent (Invite)"
                    else:
                        email_sent_status = "Failed"
                        
                else:
                    subject = "Update on your Application"
                    body = f"""
                    <html>
                        <body>
                            <h2 style="color: #555;">Application Update</h2>
                            <p>Dear Candidate,</p>
                            <p>Thank you for your interest in our company. After careful review, we have decided to proceed with other candidates who more closely match our current requirements.</p>
                            <p><strong>Feedback:</strong> Missing skills included: <em>{', '.join(missing_skills[:3])}...</em></p>
                            <br>
                            <p>We wish you the best in your job search.</p>
                            <p>Best regards,<br><strong>Talent Acquisition Team</strong></p>
                        </body>
                    </html>
                    """
                    if send_email(candidate_email, subject, body, SENDER_EMAIL, SENDER_PASSWORD):
                        email_sent_status = "Sent (Reject)"
                    else:
                        email_sent_status = "Failed"
            
            elif enable_email and not candidate_email:
                 email_sent_status = "No Email Found"

            results_data.append({
                "Filename": file.name,
                "Email": candidate_email,
                "Score": score,
                "Status": status,
                "Missing Skills": ", ".join(missing_skills),
                "Email Status": email_sent_status
            })
            progress_bar.progress((i + 1) / len(uploaded_files))

        st.success("Processing Complete!")
        df = pd.DataFrame(results_data)
        
        # Visualization
        colA, colB = st.columns(2)
        with colA:
            st.bar_chart(df['Status'].value_counts())
        with colB:
            if not df.empty:
                st.bar_chart(df.set_index('Filename')['Score'])

        # Display Dataframe with Colors
        def color_status(val):
            color = 'green' if val == "SELECTED" else 'red'
            return f'color: {color}; font-weight: bold'

        st.dataframe(df.style.map(color_status, subset=['Status']), use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Report (CSV)", csv, "hiring_report.csv", "text/csv")

    elif not uploaded_files:
        st.info("Waiting for PDF uploads...")
