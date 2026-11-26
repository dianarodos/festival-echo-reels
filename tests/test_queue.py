from reels.run import caption_for, queue

V = [{"id": "a", "name": "B.mp4", "createdTime": "2026-01-02"},
     {"id": "b", "name": "a.mp4", "createdTime": "2026-01-03"},
     {"id": "c", "name": "C.mp4", "createdTime": "2026-01-01"}]


def test_queue_by_name_skips_done():
    log = [{"drive_id": "b", "status": "posted"}]
    assert [v["id"] for v in queue(V, log, "name")] == ["a", "c"]


def test_failed_is_retried():
    log = [{"drive_id": "b", "status": "failed"}]
    assert queue(V, log, "name")[0]["id"] == "b"


def test_queue_by_created():
    assert [v["id"] for v in queue(V, [], "created")] == ["c", "a", "b"]


def test_caption_lookup():
    cfg = {"default": "D", "by_file": {"x": "X"}}
    assert caption_for("x.mp4", cfg) == "X" and caption_for("y.mp4", cfg) == "D"


def test_recycle_oldest_posted_first_and_excludes_fresh():
    from reels.run import recycle_queue
    log = [{"drive_id": "a", "status": "posted", "at": "2026-01-05"},
           {"drive_id": "c", "status": "posted", "at": "2026-01-02"},
           {"drive_id": "b", "status": "skipped", "at": "2026-01-01"}]
    todo = queue(V, log, "name")          # only b is unhandled... but it was skipped, so todo is []
    assert [v["id"] for v in recycle_queue(V, log, todo)] == ["c", "a"]


def test_priority_goes_first_then_normal_order():
    assert [v["id"] for v in queue(V, [], "name", ["c.mp4", "B.mp4"])] == ["c", "a", "b"]
