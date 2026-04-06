import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from commands.activity.tickets import (  # noqa: E402
    _build_transcript_files,
    _render_transcript_html,
    normalize_transcript_format,
)


class TicketTranscriptFormatTests(unittest.TestCase):
    def test_normalize_transcript_format_defaults_to_both(self) -> None:
        self.assertEqual(normalize_transcript_format(None), "both")
        self.assertEqual(normalize_transcript_format("weird"), "both")
        self.assertEqual(normalize_transcript_format("txt"), "txt")
        self.assertEqual(normalize_transcript_format("html"), "html")
        self.assertEqual(normalize_transcript_format("both"), "both")

    def test_build_transcript_files_respects_format(self) -> None:
        both_files = _build_transcript_files(42, "both", "plain text", "<html></html>")
        self.assertEqual([file.filename for file in both_files], ["ticket-42-transcript.txt", "ticket-42-transcript.html"])

        html_only = _build_transcript_files(42, "html", "plain text", "<html></html>")
        self.assertEqual([file.filename for file in html_only], ["ticket-42-transcript.html"])

        txt_only = _build_transcript_files(42, "txt", "plain text", "<html></html>")
        self.assertEqual([file.filename for file in txt_only], ["ticket-42-transcript.txt"])


class TicketTranscriptHtmlTests(unittest.TestCase):
    def test_render_transcript_html_escapes_content_and_renders_meta(self) -> None:
        guild = SimpleNamespace(name="Guild Name")
        channel = SimpleNamespace(name="ticket-12")
        opened_by = SimpleNamespace(display_name="Opened By")
        closed_by = SimpleNamespace(display_name="Closed By")
        claimed_by = SimpleNamespace(display_name="Claimed By")
        created_at = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)

        html_doc = _render_transcript_html(
            guild=guild,
            channel=channel,
            ticket_id=12,
            opened_by=opened_by,
            closed_by=closed_by,
            opened_at=created_at,
            closed_at=created_at,
            claimed_by=claimed_by,
            reason='Need <help> & support',
            entries=[
                {
                    "created_at": created_at,
                    "author_display": "User <One>",
                    "author_full": "user#0001",
                    "author_id": 1,
                    "avatar_url": "https://cdn.test/avatar.png",
                    "content": "<script>alert('x')</script>\nsecond line",
                    "attachments": [{"filename": "report <1>.txt", "url": "https://cdn.test/file.txt"}],
                    "embeds_count": 1,
                    "stickers_count": 0,
                    "message_type": "default",
                }
            ],
        )

        self.assertIn("Ticket #12", html_doc)
        self.assertIn("Guild Name", html_doc)
        self.assertIn("Need &lt;help&gt; &amp; support", html_doc)
        self.assertIn("&lt;script&gt;alert", html_doc)
        self.assertIn("report &lt;1&gt;.txt", html_doc)
        self.assertIn("Embeds: 1", html_doc)


if __name__ == "__main__":
    unittest.main()
