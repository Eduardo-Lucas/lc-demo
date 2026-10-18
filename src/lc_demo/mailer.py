"""Outgoing email over plain SMTP, so any provider works (Gmail app password, Resend, SES, ...)."""

import smtplib
import ssl
from email.message import EmailMessage

from lc_demo.config import (
    APP_URL,
    RESET_LINK_MINUTES,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USERNAME,
)


def is_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def reset_link(token: str) -> str:
    return f"{APP_URL}/?reset={token}"


def send(message: EmailMessage) -> None:
    context = ssl.create_default_context()
    if SMTP_PORT == 465:
        smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=15)
    else:
        smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
    with smtp:
        if SMTP_PORT != 465:
            # Always upgrade to TLS (starttls() sends EHLO itself); fail rather than send credentials in clear.
            smtp.starttls(context=context)
        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message)


def send_reset_email(to: str, token: str) -> None:
    # The interface is in Brazilian Portuguese, so is the email.
    message = EmailMessage()
    message["Subject"] = "Redefinição de senha — lc-demo"
    message["From"] = SMTP_FROM
    message["To"] = to
    message.set_content(
        "Olá!\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no lc-demo.\n"
        "Para criar uma nova senha, abra o link abaixo:\n\n"
        f"{reset_link(token)}\n\n"
        f"O link vale por {RESET_LINK_MINUTES} minutos e só pode ser usado uma vez.\n"
        "Se você não pediu a redefinição, ignore este e-mail: sua senha continua a mesma.\n"
    )
    send(message)
