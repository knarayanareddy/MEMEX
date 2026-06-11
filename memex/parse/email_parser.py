"""Email parser using stdlib email module."""

from __future__ import annotations

import email
from email import policy
from email.message import EmailMessage
from io import BytesIO

from ..config.settings import ContentType, ParsedDocument
from ..observability.logging import get_logger
from .base import BaseParser, ParserError

logger = get_logger("parse.email")


class EmailParser(BaseParser):
    """Email (.eml) parser."""

    content_type = ContentType.EMAIL

    @property
    def supported_extensions(self) -> set[str]:
        return {".eml"}

    def parse(self, raw_bytes: bytes, filename: str = "") -> ParsedDocument:
        """Parse an email from raw bytes."""
        try:
            msg = email.message_from_bytes(raw_bytes, policy=policy.default)

            subject = str(msg.get("Subject", ""))
            sender = str(msg.get("From", ""))
            date = str(msg.get("Date", ""))
            to = str(msg.get("To", ""))

            # Extract text body
            body = self._extract_body(msg)

            # Build clean content
            header_parts = []
            if subject:
                header_parts.append(f"Subject: {subject}")
            if sender:
                header_parts.append(f"From: {sender}")
            if to:
                header_parts.append(f"To: {to}")
            if date:
                header_parts.append(f"Date: {date}")

            header = "\n".join(header_parts)
            clean_content = f"{header}\n\n{body}" if body else header

            return ParsedDocument(
                document_id="",
                clean_content=clean_content,
                content_type=ContentType.EMAIL,
                parse_metadata={
                    "subject": subject,
                    "from": sender,
                    "to": to,
                    "date": date,
                },
            )

        except Exception as e:
            raise ParserError(f"Email parse error: {e}", parser_name="EmailParser") from e

    @staticmethod
    def _extract_body(msg: EmailMessage) -> str:
        """Extract plain text body from email message."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        return part.get_content()
                    except Exception:
                        payload = part.get_payload(decode=True)
                        if payload:
                            return payload.decode("utf-8", errors="replace")
            # Fallback: try HTML part
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    import re
                    html = part.get_payload(decode=True)
                    if html:
                        text = re.sub(r"<[^>]+>", " ", html.decode("utf-8", errors="replace"))
                        return " ".join(text.split())
        else:
            try:
                return msg.get_content()
            except Exception:
                payload = msg.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")

        return ""
