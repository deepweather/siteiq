"""Plain-text + minimal-HTML transactional email bodies.

Kept inline (not Jinja) so we can ship without a template engine and
diff easily. Every template returns a (subject, html, text) tuple.

The frontend origin is interpolated so links work in dev (localhost) and
prod alike; the URL path matches the React routes in App.tsx.
"""
from __future__ import annotations

from typing import Tuple


def _wrap_html(title: str, body_html: str) -> str:
    return f"""<!doctype html>
<html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#fafafa; padding: 32px;">
  <div style="max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
    <div style="font-weight: 700; color: #ea580c; font-size: 14px; letter-spacing: 0.5px;">SITEIQ</div>
    <h1 style="font-size: 22px; margin: 16px 0;">{title}</h1>
    {body_html}
    <hr style="border: 0; border-top: 1px solid #eee; margin: 32px 0 16px;" />
    <div style="font-size: 12px; color: #888;">
      If you didn't request this email, you can safely ignore it.
    </div>
  </div>
</body></html>"""


def verify_email(name: str, frontend_origin: str, token: str) -> Tuple[str, str, str]:
    link = f"{frontend_origin}/verify-email?token={token}"
    subject = "Verify your SiteIQ email"
    text = (
        f"Hi {name},\n\n"
        f"Confirm your email so we can send you operational alerts and invites.\n\n"
        f"{link}\n\n"
        f"This link expires in 24 hours.\n"
    )
    html = _wrap_html(
        f"Confirm your email, {name}",
        f"""<p style="color:#444; line-height:1.5;">Click the button to confirm your email address. We use this for operational alerts and team invites.</p>
        <p><a href="{link}" style="display:inline-block; background:#ea580c; color:#fff; padding:12px 20px; border-radius:8px; text-decoration:none; font-weight:600;">Confirm email</a></p>
        <p style="font-size:12px; color:#888;">Or paste this URL into your browser: <br/>{link}</p>
        <p style="font-size:12px; color:#888;">This link expires in 24 hours.</p>""",
    )
    return subject, html, text


def password_reset(name: str, frontend_origin: str, token: str) -> Tuple[str, str, str]:
    link = f"{frontend_origin}/reset-password?token={token}"
    subject = "Reset your SiteIQ password"
    text = (
        f"Hi {name},\n\n"
        f"Use this link to set a new password. It expires in 30 minutes and can only be used once.\n\n"
        f"{link}\n\n"
        f"If you didn't request a reset, ignore this email — your password stays unchanged.\n"
    )
    html = _wrap_html(
        "Reset your password",
        f"""<p style="color:#444; line-height:1.5;">Click below to choose a new password. The link expires in 30 minutes and can only be used once.</p>
        <p><a href="{link}" style="display:inline-block; background:#ea580c; color:#fff; padding:12px 20px; border-radius:8px; text-decoration:none; font-weight:600;">Reset password</a></p>
        <p style="font-size:12px; color:#888;">Or paste this URL: <br/>{link}</p>
        <p style="font-size:12px; color:#888;">If you didn't request this, no action is needed — your password remains unchanged.</p>""",
    )
    return subject, html, text


def org_invite(
    inviter_name: str, org_name: str, frontend_origin: str, token: str, role: str
) -> Tuple[str, str, str]:
    link = f"{frontend_origin}/accept-invite?token={token}"
    subject = f"{inviter_name} invited you to {org_name} on SiteIQ"
    text = (
        f"{inviter_name} invited you to join {org_name} on SiteIQ as a {role}.\n\n"
        f"Accept the invite:\n{link}\n\n"
        f"This invite expires in 7 days.\n"
    )
    html = _wrap_html(
        f"Join {org_name} on SiteIQ",
        f"""<p style="color:#444; line-height:1.5;"><strong>{inviter_name}</strong> invited you to {org_name} as a <strong>{role}</strong>.</p>
        <p><a href="{link}" style="display:inline-block; background:#ea580c; color:#fff; padding:12px 20px; border-radius:8px; text-decoration:none; font-weight:600;">Accept invite</a></p>
        <p style="font-size:12px; color:#888;">Expires in 7 days.</p>""",
    )
    return subject, html, text
