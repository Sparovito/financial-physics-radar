import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

class NotificationManager:
    def __init__(self):
        self.sender = os.getenv("EMAIL_SENDER")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.recipient = os.getenv("EMAIL_RECIPIENT")
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))

    def send_email(self, subject, body):
        if not self.sender or not self.password or not self.recipient:
            print("⚠️ Email credentials missing. Skipping email.")
            # Print simplified version to console for debugging
            clean_body = body.replace("<br>", "\n").replace("<b>", "").replace("</b>", "")
            print(f"--- [MOCK EMAIL] ---\nSubject: {subject}\n{clean_body}\n--------------------")
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender
            msg['To'] = self.recipient
            msg['Subject'] = subject

            msg.attach(MIMEText(body, 'html'))

            if self.smtp_port == 465:
                # SSL Connection (bypass firewall for 587)
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                # Standard TLS Connection
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
            
            server.login(self.sender, self.password)
            text = msg.as_string()
            server.sendmail(self.sender, self.recipient, text)
            server.quit()
            print("✅ Email sent successfully.")
        except Exception as e:
            print(f"❌ Error sending email: {e}")
