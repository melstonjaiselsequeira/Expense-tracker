import os
import smtplib

smtp_server = os.getenv('SMTP_SERVER')
smtp_port = int(os.getenv('SMTP_PORT', 587))
smtp_user = os.getenv('SMTP_USER')
smtp_password = os.getenv('SMTP_PASSWORD')

try:
    with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()

        server.login(smtp_user, smtp_password)

        print("SUCCESS: Brevo SMTP connection established!")

except Exception as e:
    print("SMTP ERROR:", str(e))