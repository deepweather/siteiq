"""Auth package — passwords, sessions, tokens, email, routes.

Mirrors the existing `state.source.SiteStateSource` seam: the
`EmailSender` Protocol is implemented by both `ConsoleSender` (dev/test:
writes to the email_outbox table, viewable at /dev/outbox) and
`ResendSender` (prod: posts to the Resend HTTPS API). Tests assert
against the outbox table; the same code path runs in prod.
"""
