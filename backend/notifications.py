"""
Email Notification System using Resend API (Cloud-friendly)
Falls back to SMTP if Resend key is not set.
"""
import os

class NotificationManager:
    def __init__(self):
        self.sender = os.getenv("EMAIL_SENDER")
        self.recipient = os.getenv("EMAIL_RECIPIENT")
        self.resend_key = os.getenv("RESEND_API_KEY")
        
        # Legacy SMTP (fallback for local dev)
        self.password = os.getenv("EMAIL_PASSWORD")
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))

    def send_email(self, subject, body):
        if not self.sender or not self.recipient:
            print("⚠️ Email credentials missing. Skipping email.")
            self._print_mock(subject, body)
            return
        
        # Prefer Resend API if available
        if self.resend_key:
            self._send_via_resend(subject, body)
        elif self.password:
            self._send_via_smtp(subject, body)
        else:
            print("⚠️ No email method configured (RESEND_API_KEY or EMAIL_PASSWORD).")
            self._print_mock(subject, body)

    def _send_via_resend(self, subject, body):
        try:
            import resend
            resend.api_key = self.resend_key
            
            params = {
                "from": f"Financial Physics <{self.sender}>",
                "to": [self.recipient],
                "subject": subject,
                "html": body,
            }
            
            email = resend.Emails.send(params)
            print(f"✅ Email sent via Resend! ID: {email.get('id', 'N/A')}")
        except Exception as e:
            print(f"❌ Error sending email via Resend: {e}")

    def _send_via_smtp(self, subject, body):
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender
            msg['To'] = self.recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'html'))

            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
            
            server.login(self.sender, self.password)
            server.sendmail(self.sender, self.recipient, msg.as_string())
            server.quit()
            print("✅ Email sent via SMTP.")
        except Exception as e:
            print(f"❌ Error sending email via SMTP: {e}")

    def _print_mock(self, subject, body):
        clean_body = body.replace("<br>", "\n").replace("<b>", "").replace("</b>", "")
        print(f"--- [MOCK EMAIL] ---\nSubject: {subject}\n{clean_body[:500]}...\n--------------------")
