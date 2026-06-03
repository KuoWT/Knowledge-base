import unittest

from hermes.markdown import parse_markdown


class MarkdownParseTests(unittest.TestCase):
    def test_parse_markdown_splits_headings_and_chunks(self):
        content = """---
title: Demo
---
# Alpha

First paragraph.

## Beta

Second paragraph.
"""
        chunks = parse_markdown(content, max_chars=100)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(chunks[0].heading_path.startswith("Alpha"))
