"""
Scheduled task runner using APScheduler.
- Log collection at the configured interval
- Usage analysis daily at 02:00
- Data cleanup daily at 03:00
"""

from __future__ import annotations

import asyncio
import signal
import sys

from apscheduler.schedulers.background import BackgroundScheduler

from scripts.config import AppConfig, load_config
from scripts.collect_logs import clean_expired_data, collect_logs
from scripts.db import close_connection_pool


def _run_async(coro) -> None:
    """Run an async coroutine in a new event loop (for APScheduler callbacks)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


def start_scheduler(config: AppConfig) -> BackgroundScheduler:
    interval_minutes = config.collection.interval_minutes

    print("[Scheduler] Starting scheduler")
    print(f"[Scheduler] Log collection interval: every {interval_minutes} minutes")
    print("[Scheduler] Usage analysis: daily at 02:00")
    print("[Scheduler] Data cleanup: daily at 03:00")

    scheduler = BackgroundScheduler()

    if config.collection.enable_log_collection:
        def collect_job() -> None:
            from datetime import datetime
            print(f"\n[Scheduler] {datetime.now().isoformat()} - Starting scheduled log collection")
            try:
                _run_async(collect_logs(config))
                print("[Scheduler] Log collection completed")
            except Exception as error:
                print(f"[Scheduler] Log collection failed: {error}")

        scheduler.add_job(collect_job, "interval", minutes=interval_minutes, id="collect_logs")
        print("[Scheduler] ✅ Log collection scheduled task started")
    else:
        print("[Scheduler] ⚠️ Log collection is disabled")

    def analyze_job() -> None:
        from datetime import datetime
        from scripts.analyze_usage import run_full_analysis
        print(f"\n[Scheduler] {datetime.now().isoformat()} - Starting daily usage analysis")
        try:
            _run_async(run_full_analysis(config))
            print("[Scheduler] Daily usage analysis completed")
        except Exception as error:
            print(f"[Scheduler] Daily usage analysis failed: {error}")

    scheduler.add_job(analyze_job, "cron", hour=2, minute=0, id="daily_analysis")
    print("[Scheduler] ✅ Daily analysis scheduled task started")

    def cleanup_job() -> None:
        from datetime import datetime
        print(f"\n[Scheduler] {datetime.now().isoformat()} - Starting expired data cleanup")
        try:
            _run_async(clean_expired_data(config))
            print("[Scheduler] Expired data cleanup completed")
        except Exception as error:
            print(f"[Scheduler] Expired data cleanup failed: {error}")

    scheduler.add_job(cleanup_job, "cron", hour=3, minute=0, id="data_cleanup")
    print("[Scheduler] ✅ Data cleanup scheduled task started")

    scheduler.start()
    return scheduler


if __name__ == "__main__":
    config = load_config()
    scheduler = start_scheduler(config)

    print("\n[Scheduler] Scheduler running, press Ctrl+C to exit...")

    def graceful_shutdown(signum, frame) -> None:
        print("\n[Scheduler] Received shutdown signal, gracefully shutting down...")
        scheduler.shutdown(wait=False)
        close_connection_pool()
        sys.exit(0)

    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # Keep the main thread alive
    import time
    while True:
        time.sleep(1)
