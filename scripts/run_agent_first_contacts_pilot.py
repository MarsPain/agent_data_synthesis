"""Run the separately authorized, diagnostic Agent-first Contacts pilot."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_synthesis.contacts import ContactsDomainAdapter, ContactsPilotConfiguration
from scripts.agent_first_contacts_pilot import (
    ContactsLivePilotAuthorization,
    ContactsLivePilotError,
    run_authorized_contacts_pilot,
)
from agent_synthesis.model import OpenAICompatibleJsonAdapter


_BASE_URL_ENV = "AGENT_DATA_LLM_BASE_URL"
_API_KEY_ENV = "AGENT_DATA_API_KEY"
_MODEL_ENV = "AGENT_DATA_LLM_MODEL"
_TOTAL_PHYSICAL_REQUEST_LIMIT = 41
_GENERATION_REQUEST_LIMIT = 1
_AGENT_REQUEST_LIMIT = 40
_TRANSPORT_RETRY_LIMIT = 0
_THINKING_MODE = "disabled"
_MAX_OUTPUT_TOKENS = 4_096
_MAX_RESPONSE_BYTES = 64_000
_TIMEOUT_SECONDS = 30.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one explicitly authorized, diagnostic-only Agent-first Contacts "
            "pilot. It uses eight task attempts and never retries provider requests."
        )
    )
    parser.add_argument("--authorize-live-provider", action="store_true", required=True)
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--generator-model", default=os.environ.get(_MODEL_ENV))
    parser.add_argument(
        "--model-version",
        default="provider-version-unavailable",
        help="A non-secret model version label; the default records that it is unavailable.",
    )
    parser.add_argument(
        "--pilot-id",
        default="contacts-early-feasibility-live",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "agent-first-contacts-pilot",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = os.environ.get(_BASE_URL_ENV)
    api_key = os.environ.get(_API_KEY_ENV)
    if not base_url or not api_key or not args.generator_model:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason_code": "live_provider_configuration_required",
                    "required_environment": [_BASE_URL_ENV, _API_KEY_ENV, _MODEL_ENV],
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    provider_host = urlparse(base_url).hostname
    if not provider_host:
        print(
            json.dumps(
                {"status": "failed", "reason_code": "live_provider_host_invalid"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        configuration = ContactsPilotConfiguration(
            pilot_id=args.pilot_id,
            model_id=args.generator_model,
            model_version=args.model_version,
            total_physical_request_limit=_TOTAL_PHYSICAL_REQUEST_LIMIT,
            generation_request_limit=_GENERATION_REQUEST_LIMIT,
            agent_request_limit=_AGENT_REQUEST_LIMIT,
            thinking_mode=_THINKING_MODE,
            transport_retry_limit=_TRANSPORT_RETRY_LIMIT,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            max_response_bytes=_MAX_RESPONSE_BYTES,
            timeout_seconds=_TIMEOUT_SECONDS,
        )
        authorization = ContactsLivePilotAuthorization(
            approved=args.authorize_live_provider,
            authorization_id=args.authorization_id,
            provider_id="openai_compatible",
            provider_host=provider_host,
            remote_model=args.generator_model,
            thinking_mode=_THINKING_MODE,
        )
        model = OpenAICompatibleJsonAdapter(
            model_id=configuration.model_id,
            model_version=configuration.model_version,
            base_url=base_url,
            api_key=api_key,
            remote_model=args.generator_model,
            thinking_mode=_THINKING_MODE,
        )
        result = run_authorized_contacts_pilot(
            output_directory=args.output_dir,
            adapter=ContactsDomainAdapter.fixture(),
            model=model,
            configuration=configuration,
            authorization=authorization,
        )
    except (ContactsLivePilotError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason_code": getattr(error, "reason_code", "contacts_live_pilot_failed"),
                    "output_dir": str(args.output_dir),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            {
                "status": (
                    "required_behaviors_observed"
                    if result.requirements_met
                    else "insufficient_evidence"
                ),
                "output_dir": str(result.run.run_directory),
                "report_path": str(result.report_path),
                "replay_path": str(result.replay.report_path),
                "demonstrations": result.run.demonstration_count,
                "negatives": result.run.negative_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result.requirements_met else 1


if __name__ == "__main__":
    raise SystemExit(main())
