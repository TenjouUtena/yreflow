"""Tests for EventBus pub/sub with regex pattern matching."""

import pytest

from yreflow.protocol.events import EventBus


@pytest.mark.asyncio
class TestEventBus:
    async def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        async def handler(**kwargs):
            received.append(kwargs)

        bus.subscribe("test.event", handler)
        await bus.publish("test.event", data="hello")

        assert len(received) == 1
        assert received[0]["event_name"] == "test.event"
        assert received[0]["data"] == "hello"

    async def test_pattern_matching(self):
        bus = EventBus()
        received = []

        async def handler(**kwargs):
            received.append(kwargs["event_name"])

        bus.subscribe(r"message\..*", handler)
        await bus.publish("message.received", msg="hi")
        await bus.publish("message.sent", msg="bye")
        await bus.publish("notification", text="nope")

        assert received == ["message.received", "message.sent"]

    async def test_no_match_does_not_fire(self):
        bus = EventBus()
        called = False

        async def handler(**kwargs):
            nonlocal called
            called = True

        bus.subscribe("specific.event", handler)
        await bus.publish("other.event")

        assert called is False

    async def test_multiple_subscribers(self):
        bus = EventBus()
        results = []

        async def handler_a(**kwargs):
            results.append("a")

        async def handler_b(**kwargs):
            results.append("b")

        bus.subscribe("evt", handler_a)
        bus.subscribe("evt", handler_b)
        await bus.publish("evt")

        assert sorted(results) == ["a", "b"]

    async def test_kwargs_passed_through(self):
        bus = EventBus()
        received = {}

        async def handler(**kwargs):
            received.update(kwargs)

        bus.subscribe("test", handler)
        await bus.publish("test", x=1, y="two", z=[3])

        assert received["x"] == 1
        assert received["y"] == "two"
        assert received["z"] == [3]
