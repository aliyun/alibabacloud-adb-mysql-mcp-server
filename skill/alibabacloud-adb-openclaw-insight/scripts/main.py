from __future__ import annotations

import asyncio
import os
import signal
import sys
from datetime import datetime

# Set up a dedicated log file that flushes every write, so we can monitor
# progress in real-time even when stdout is block-buffered (file redirect).
import builtins
_original_print = builtins.print
_log_file_path = os.environ.get("OPENCLAW_LOG_FILE", "")

if _log_file_path:
    _log_fh = open(_log_file_path, "w", buffering=1, encoding="utf-8")

    def _logged_print(*args, **kwargs):
        message = kwargs.get("sep", " ").join(str(a) for a in args)
        end = kwargs.get("end", "\n")
        _log_fh.write(message + end)
        _log_fh.flush()
        kwargs.setdefault("flush", True)
        _original_print(*args, **kwargs)

    builtins.print = _logged_print
else:
    def _flushed_print(*args, **kwargs):
        kwargs.setdefault("flush", True)
        _original_print(*args, **kwargs)

    builtins.print = _flushed_print

async def main() -> None:
    from concurrent.futures import ThreadPoolExecutor
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=32))
    from scripts.config import load_config
    from scripts.collect_logs import collect_logs
    from scripts.analyze_usage import run_full_analysis
    from scripts.db import close_connection_pool

    print("=" * 60)
    print("🚀 OpenClaw Logger ADB Skill Starting")
    print(f"Start time: {datetime.now().isoformat()}")
    print("=" * 60)

    config = load_config()

    print("\n📋 Configuration:")
    print(f"  ADB address: {config.adb.host}:{config.adb.port}/{config.adb.database}")
    print(f"  Session table: {config.adb.session_table}")
    print(f"  Collection interval: {config.collection.interval_minutes} minutes")
    print(f"  Batch size: {config.collection.batch_size}")
    print(f"  Data retention: {config.collection.retention_days} days")
    print(f"  Log collection: {'enabled' if config.collection.enable_log_collection else 'disabled'}")
    print(f"  Token collection: {'enabled' if config.collection.enable_token_collection else 'disabled'}")

    command = sys.argv[1] if len(sys.argv) > 1 else "serve"

    if command == "collect":
        print("\n📥 Running one-time log collection...")
        await collect_logs(config)
        close_connection_pool()

    elif command == "analyze":
        print("\n📊 Running one-time usage analysis...")
        await run_full_analysis(config)
        close_connection_pool()

    elif command == "final-report":
        print("\n📄 Fetching latest final narrative report from database...")
        from scripts.analysis.orchestrator import AnalysisOrchestrator
        orchestrator = AnalysisOrchestrator(config)
        report_text = orchestrator.get_final_report()
        print(report_text)
        close_connection_pool()

    else:
        # serve mode (default)
        if config.collection.enable_log_collection:
            print("\n📥 Running initial log collection...")
            try:
                inserted_count = await collect_logs(config)
                print(f"Initial collection completed, inserted {inserted_count} records")
            except Exception as error:
                print(f"Initial collection failed (will retry on next scheduled run): {error}")

        from scripts.scheduler import start_scheduler
        scheduler = start_scheduler(config)

        print("\n✅ Service started, press Ctrl+C to exit")

        def graceful_shutdown(signum, frame) -> None:
            print("\n🛑 Received shutdown signal, gracefully shutting down...")
            scheduler.shutdown(wait=False)
            close_connection_pool()
            print("👋 Exited")
            sys.exit(0)

        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)

        import time
        while True:
            time.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"❌ Startup failed: {error}")
        sys.exit(1)
