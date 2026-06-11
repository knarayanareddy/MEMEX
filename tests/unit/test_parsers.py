"""Unit tests for parsers."""

import pytest

from memex.config.settings import ContentType
from memex.parse.dispatcher import ParserDispatcher
from memex.parse.plain_parser import PlainParser
from memex.parse.markdown_parser import MarkdownParser
from memex.parse.code_parser import CodeParser
from memex.parse.html_parser import HTMLParser
from memex.parse.email_parser import EmailParser
from memex.parse.pdf_parser import PDFParser


class TestPlainParser:
    def test_utf8_text(self):
        parser = PlainParser()
        result = parser.parse(b"Hello, world!")
        assert result.clean_content == "Hello, world!"
        assert result.content_type == ContentType.PLAIN

    def test_empty_content_raises(self):
        parser = PlainParser()
        with pytest.raises(Exception):
            parser.parse(b"")

    def test_latin1_fallback(self):
        parser = PlainParser()
        # Bytes that are valid Latin-1 but not UTF-8
        text = "Café résumé".encode("latin-1")
        result = parser.parse(text)
        assert "Caf" in result.clean_content

    def test_whitespace_only_raises(self):
        parser = PlainParser()
        with pytest.raises(Exception):
            parser.parse(b"   \n\t  ")


class TestMarkdownParser:
    def test_basic_markdown(self):
        parser = MarkdownParser()
        md = b"# Title\n\nParagraph here.\n\n## Section\n\nMore text."
        result = parser.parse(md)
        assert "Title" in result.clean_content
        assert result.content_type == ContentType.MARKDOWN

    def test_empty_markdown(self):
        parser = MarkdownParser()
        with pytest.raises(Exception):
            parser.parse(b"")


class TestCodeParser:
    def test_python_code(self):
        parser = CodeParser()
        code = b'def hello():\n    """Say hello."""\n    print("hello")\n\nclass World:\n    pass\n'
        result = parser.parse(code, filename="test.py")
        assert result.content_type == ContentType.CODE
        assert result.language == "python"
        assert "hello" in result.clean_content

    def test_javascript_code(self):
        parser = CodeParser()
        code = b'function greet() {\n  console.log("hello");\n}\n'
        result = parser.parse(code, filename="test.js")
        assert result.language == "javascript"


class TestHTMLParser:
    def test_basic_html(self):
        parser = HTMLParser()
        html = b"<html><head><title>Test</title></head><body><p>Content</p></body></html>"
        result = parser.parse(html)
        assert "Content" in result.clean_content or "Test" in result.clean_content


class TestEmailParser:
    def test_basic_email(self):
        parser = EmailParser()
        email = (
            b"From: alice@example.com\r\n"
            b"To: bob@example.com\r\n"
            b"Subject: Hello\r\n"
            b"\r\n"
            b"This is the email body.\r\n"
        )
        result = parser.parse(email)
        assert "Hello" in result.clean_content
        assert "email body" in result.clean_content
        assert result.content_type == ContentType.EMAIL


class TestContentTypeDetection:
    def setup_method(self):
        self.dispatcher = ParserDispatcher()

    def test_pdf_detection(self):
        ct = self.dispatcher.detect_content_type("file.pdf", b"%PDF-1.4")
        assert ct == ContentType.PDF

    def test_html_detection(self):
        ct = self.dispatcher.detect_content_type("page.html", b"<html>")
        assert ct == ContentType.HTML

    def test_python_detection(self):
        ct = self.dispatcher.detect_content_type("script.py", b"")
        assert ct == ContentType.CODE

    def test_markdown_detection(self):
        ct = self.dispatcher.detect_content_type("README.md", b"")
        assert ct == ContentType.MARKDOWN

    def test_unknown_defaults_to_plain(self):
        ct = self.dispatcher.detect_content_type("random.xyz", b"hello")
        assert ct == ContentType.PLAIN

    def test_email_detection(self):
        ct = self.dispatcher.detect_content_type("msg.eml", b"From:")
        assert ct == ContentType.EMAIL

    def test_magic_byte_pdf(self):
        ct = self.dispatcher.detect_content_type("noext", b"%PDF-1.4 data")
        assert ct == ContentType.PDF
