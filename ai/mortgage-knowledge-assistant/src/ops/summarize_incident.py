"""Summarize an incident file from the command line (Task 7.6 demo).

    python -m src.ops.summarize_incident incidents/INC-2026-0042-servicing-dlq-backlog.txt
    python -m src.ops.summarize_incident --incident-id INC-2026-0043 incidents/INC-2026-0043-vague-report.txt

Prints the same JSON body POST /api/v1/assistant/summarize-incident returns. The incident id defaults to the
INC-YYYY-NNNN prefix of the file name. Exit codes: 0 ok, 2 bad input/config, 1 AI provider failure.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import uuid
from pathlib import Path

from src.config import ConfigError, load_settings
from src.ops.incident import IncidentInputError, IncidentSummarizer
from src.rag.llm import LLMError, build_chat_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.ops.summarize_incident")
    parser.add_argument("file", type=Path, help="incident log or notes (plain text)")
    parser.add_argument("--incident-id", help="INC-YYYY-NNNN (default: taken from the file name)")
    parser.add_argument("--debug", action="store_true", help="show service log lines")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.debug else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    correlation_id = str(uuid.uuid4())
    incident_id = args.incident_id
    if incident_id is None:
        match = re.match(r"(INC-\d{4}-\d{4})", args.file.name)
        incident_id = match.group(1) if match else None
    try:
        text = args.file.read_text(encoding="utf-8")
        summarizer = IncidentSummarizer(build_chat_model(load_settings()))
        result = summarizer.summarize(text, incident_id, correlation_id)
    except (OSError, ConfigError, IncidentInputError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except LLMError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.as_api(correlation_id), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
