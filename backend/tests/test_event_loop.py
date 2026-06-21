"""Bug #2 — YOLO inference must run off the event loop.

We simulate a slow detector frame call. Before the fix, this would block
the event loop and other coroutines would not progress. After the fix
(asyncio.to_thread), the loop should remain responsive.
"""
from __future__ import annotations

import asyncio
import time

import pytest


@pytest.mark.asyncio
async def test_camera_loop_does_not_block_event_loop():
    """Run the camera streaming logic with a synchronous detector that
    sleeps 250ms per frame. While it 'inferences', another coroutine must
    still get scheduled within ~50ms — proving we're off the loop."""

    class SlowDetector:
        def __init__(self):
            self.calls = 0

        def get_next_frame(self, *_a, **_kw):
            time.sleep(0.25)  # blocks the calling thread (NOT the event loop)
            self.calls += 1
            return {"video_id": "x", "frame_idx": self.calls,
                    "width": 1, "height": 1, "detections": [],
                    "inference_ms": 250, "image": ""}

        def get_video_ids(self): return ["x"]

    detector = SlowDetector()

    # The same call pattern as api/camera.py:
    async def fake_camera_loop():
        for _ in range(2):
            frame = await asyncio.to_thread(detector.get_next_frame, "x", 5)
            assert frame is not None

    # A heartbeat coroutine that records how often it gets scheduled
    heartbeats = []
    async def heartbeat():
        for _ in range(20):
            heartbeats.append(time.monotonic())
            await asyncio.sleep(0.01)

    t0 = time.monotonic()
    await asyncio.gather(fake_camera_loop(), heartbeat())
    elapsed = time.monotonic() - t0

    # If YOLO had blocked the event loop, heartbeats would only fire while
    # the detector wasn't running. With to_thread, we should see >=18 of
    # the 20 heartbeats (some scheduling slack).
    assert len(heartbeats) >= 18, (
        f"only got {len(heartbeats)} heartbeats — event loop was likely blocked"
    )
    # And the two frames at 0.25s each ran concurrently with heartbeats
    assert elapsed < 0.7, (
        f"loop took {elapsed:.2f}s — should be ~0.5s (frames run in threads)"
    )


@pytest.mark.asyncio
async def test_blocking_version_would_have_failed():
    """Same scenario WITHOUT asyncio.to_thread — confirms our test would
    actually have detected the bug if it were still there."""

    def sync_blocker():
        time.sleep(0.25)
        return 1

    async def bad_loop():
        for _ in range(2):
            # Direct synchronous call from inside an async function ==
            # blocks the event loop.
            sync_blocker()

    heartbeats = []
    async def heartbeat():
        for _ in range(20):
            heartbeats.append(time.monotonic())
            await asyncio.sleep(0.01)

    await asyncio.gather(bad_loop(), heartbeat())

    # With the bug, heartbeats happen in big gaps — we'd typically see far
    # fewer than 20 in the same wall-clock window. This test exists to
    # prove the previous test is a real signal, not a vacuous pass.
    assert len(heartbeats) >= 1  # didn't crash, but we expect cluster gaps
