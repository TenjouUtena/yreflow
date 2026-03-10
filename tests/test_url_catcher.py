"""Tests for UrlCatcher deduplication and capacity."""

from yreflow.protocol.events import EventBus
from yreflow.url_catcher import UrlCatcher


class TestUrlCatcherDedup:
    def test_dedup_same_url(self):
        catcher = UrlCatcher(EventBus(), max_urls=10)
        catcher.capture("Link A", "https://example.com")
        catcher.capture("Link B", "https://example.com")
        urls = catcher.recent(10)
        assert len(urls) == 1
        assert urls[0].display_text == "Link B"

    def test_dedup_preserves_order(self):
        catcher = UrlCatcher(EventBus(), max_urls=10)
        catcher.capture("First", "https://a.com")
        catcher.capture("Second", "https://b.com")
        catcher.capture("First again", "https://a.com")
        urls = catcher.recent(10)
        assert len(urls) == 2
        # a.com should now be last (most recent)
        assert urls[0].url == "https://b.com"
        assert urls[1].url == "https://a.com"

    def test_capacity_limit(self):
        catcher = UrlCatcher(EventBus(), max_urls=3)
        for i in range(5):
            catcher.capture(f"Link {i}", f"https://example.com/{i}")
        urls = catcher.recent(10)
        assert len(urls) == 3
        # Oldest (0, 1) evicted; 2, 3, 4 remain
        assert urls[0].url == "https://example.com/2"
        assert urls[2].url == "https://example.com/4"

    def test_recent_limits_output(self):
        catcher = UrlCatcher(EventBus(), max_urls=10)
        for i in range(5):
            catcher.capture(f"Link {i}", f"https://example.com/{i}")
        urls = catcher.recent(2)
        assert len(urls) == 2
        assert urls[0].url == "https://example.com/3"
        assert urls[1].url == "https://example.com/4"
