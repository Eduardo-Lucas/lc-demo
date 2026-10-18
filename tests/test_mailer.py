from lc_demo import mailer


class FakeSMTP:
    """Behaves like Gmail: AUTH is only offered once the connection is upgraded with STARTTLS."""

    sent = []

    def __init__(self, host, port, timeout):
        self.host, self.port, self.calls, self.tls = host, port, [], False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def has_extn(self, name):
        # Like smtplib before EHLO: no features known yet.
        return False

    def starttls(self, context):
        self.tls = True
        self.calls.append("starttls")

    def login(self, user, password):
        if not self.tls:
            raise mailer.smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server.")
        self.calls.append(("login", user))

    def send_message(self, message):
        FakeSMTP.sent.append((self, message))


def test_reset_email(monkeypatch):
    for name, value in {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": 587,
        "SMTP_USERNAME": "sender@example.com",
        "SMTP_PASSWORD": "app-password",
        "SMTP_FROM": "lc-demo <sender@example.com>",
        "APP_URL": "https://lc-demo.streamlit.app",
    }.items():
        monkeypatch.setattr(mailer, name, value)
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    assert mailer.is_configured()
    mailer.send_reset_email("ana@example.com", "tok123")

    smtp, message = FakeSMTP.sent[-1]
    assert (smtp.host, smtp.port) == ("smtp.example.com", 587)
    assert smtp.calls == ["starttls", ("login", "sender@example.com")]
    assert message["To"] == "ana@example.com"
    assert message["From"] == "lc-demo <sender@example.com>"
    assert message["Subject"] == "Redefinição de senha — Prumo Fiscal"
    assert "sua conta no Prumo Fiscal" in message.get_content()
    assert "https://lc-demo.streamlit.app/?reset=tok123" in message.get_content()


def test_not_configured_without_host(monkeypatch):
    monkeypatch.setattr(mailer, "SMTP_HOST", "")
    assert not mailer.is_configured()
