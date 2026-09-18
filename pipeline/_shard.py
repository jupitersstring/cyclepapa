"""Shared sharding helper for EDGAR-bound scans.

The SEC rate-limit policy is 10 requests per second per User-Agent.
Sequential scans run ~1 req/s. With 8 concurrent workers and the global
governor here, we can sustain ~7-8 req/s — within limits.

Pattern:
  from _shard import shard_map
  results = shard_map(func, items, n_workers=8, rps=8)

Each worker runs `func(item)` on a thread (cheap curl/IO-bound work).
A token bucket governor in the main thread releases `rps` tokens/sec.
Each worker pulls a token before its next request.

DB writes are serialised in the MAIN thread — workers return per-item
results, the main thread serialises them into SQLite. Avoids the lock
issue from multiple writers.
"""
import queue, threading, time

class TokenBucket:
    """Simple steady-rate token bucket — `rps` tokens/sec."""
    def __init__(self, rps):
        self.rps = rps
        self.interval = 1.0 / rps
        self.lock = threading.Lock()
        self.last = time.time() - self.interval

    def take(self):
        with self.lock:
            now = time.time()
            wait = max(0, self.last + self.interval - now)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()

def shard_map(func, items, n_workers=8, rps=8, on_result=None, on_error=None):
    """Run func(item) across n_workers threads, rate-limited to rps total.

    Returns a list of (item, result_or_exception) in completion order
    if on_result is None. Otherwise on_result(item, result) is called
    per success, on_error(item, exc) on failure, and returns empty list.
    """
    bucket = TokenBucket(rps)
    in_q = queue.Queue()
    out_q = queue.Queue()
    sentinel = object()

    def worker():
        while True:
            item = in_q.get()
            if item is sentinel:
                in_q.task_done()
                return
            try:
                bucket.take()
                result = func(item)
                out_q.put((item, result, None))
            except Exception as e:
                out_q.put((item, None, e))
            finally:
                in_q.task_done()

    threads = []
    for _ in range(n_workers):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)

    for it in items:
        in_q.put(it)
    for _ in range(n_workers):
        in_q.put(sentinel)

    results = []
    n_total = len(items)
    n_done = 0
    while n_done < n_total:
        item, result, exc = out_q.get()
        n_done += 1
        if exc:
            if on_error:
                on_error(item, exc)
            else:
                results.append((item, exc))
        else:
            if on_result:
                on_result(item, result)
            else:
                results.append((item, result))
    for t in threads:
        t.join(timeout=1)
    return results
