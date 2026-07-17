#!/usr/bin/env python3
"""Scheduler - runs the full pipeline for automated/weekly updates.
Can be called by cron, WorkBuddy automation, or manually.

Usage:
    python3 scheduler.py           # Run once
    python3 scheduler.py --daemon  # Run as daemon (weekly)
"""
import os
import sys
import logging
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(BASE, "data", "scheduler.log")),
    ]
)
logger = logging.getLogger(__name__)


def run_once(run_type="auto"):
    """Execute one full pipeline run."""
    import database as db
    from engine.collector import DataCollector
    from engine.indicators import IndicatorEngine
    from engine.scorer import ScoringEngine
    from engine.reporter import ReportGenerator

    db.init_db()
    logger.info("=== Starting automated pipeline run ===")

    try:
        collector = DataCollector()
        data = collector.collect()
        logger.info("Data collected.")

        ie = IndicatorEngine()
        indicators = ie.run(data)
        logger.info(f"Indicators computed. Regime: {indicators['regime']}")

        se = ScoringEngine()
        selection = se.score(indicators)
        bt = se.backtest(data)
        logger.info(f"Selection: L={selection['longs']}, S={selection['shorts']}")

        rg = ReportGenerator()
        report = rg.generate_full_report(selection, indicators)

        run_id, alerts = db.save_run(
            run_type, selection, indicators, report,
            bt["stats"] if bt else None
        )
        logger.info(f"=== Pipeline complete. Run ID: {run_id} ===")

        if alerts:
            for a in alerts:
                logger.info(f"  ALERT [{a['severity']}]: {a['message']}")

        return run_id

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return None


def run_daemon(interval_days=7):
    """Run as daemon, executing every N days."""
    logger.info(f"Starting daemon mode. Interval: {interval_days} days.")
    while True:
        run_once(run_type="auto")
        sleep_seconds = interval_days * 24 * 3600
        logger.info(f"Sleeping {interval_days} days...")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        run_daemon()
    else:
        run_once(run_type="auto")
        print("Done. Check dashboard at http://localhost:5050")
