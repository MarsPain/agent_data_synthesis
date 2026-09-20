"""Manually exercise bounded Agent-first engine capacity with a fake test Domain."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_synthesis import (
    AdapterRegistry,
    AssessmentCheck,
    CompiledTask,
    EpisodeAssessment,
    FrozenInitialState,
    JsonModelResponse,
    PublicTask,
    RunConfiguration,
    SynthesisEngine,
    TaskProposal,
    TaskSlot,
    ToolDefinition,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the provider-free Agent-first scale benchmark."
    )
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--attempts", type=int, default=10_000)
    parser.add_argument("--max-concurrency", type=int, default=4)
    return parser.parse_args()


@dataclass(frozen=True)
class _BenchmarkCase:
    slot_id: str
    task: PublicTask


class _BenchmarkDomain:
    domain_id = "agent_first_scale_benchmark"
    domain_version = "agent_first_scale_benchmark_v1"

    def __init__(self, attempts: int) -> None:
        self._attempts = attempts

    def open_run(self, configuration: RunConfiguration) -> "_BenchmarkRun":
        del configuration
        return _BenchmarkRun(self._attempts)


class _BenchmarkRun:
    def __init__(self, attempts: int) -> None:
        self._attempts = attempts

    @property
    def known_task_capacity(self) -> int:
        return self._attempts

    def slots(self, limit: int) -> tuple[TaskSlot, ...]:
        return tuple(
            TaskSlot(
                slot_id=f"benchmark-slot-{index:05d}",
                proposal_prompt="Return the fixed benchmark proposal.",
            )
            for index in range(1, min(limit, self._attempts) + 1)
        )

    def freeze_initial_state(self) -> FrozenInitialState:
        contents = json.dumps({"benchmark_attempts": self._attempts}, sort_keys=True).encode()
        return FrozenInitialState(
            fingerprint="sha256:" + hashlib.sha256(contents).hexdigest(),
            contents=contents,
        )

    def compile(self, slot: TaskSlot, proposal: TaskProposal) -> CompiledTask:
        if proposal.content != "benchmark task":
            raise ValueError("benchmark proposal did not bind its slot")
        task = PublicTask(
            instruction=f"Complete benchmark task {slot.slot_id}.",
            tools=(
                ToolDefinition(
                    name="benchmark_noop",
                    description="A declared benchmark no-op tool.",
                    input_schema={"type": "object", "properties": {}},
                    output_schema={"type": "object", "properties": {}},
                ),
            ),
        )
        return CompiledTask(
            public_task=task,
            semantic_key=f"benchmark:{slot.slot_id}",
            private_case_bytes=slot.slot_id.encode("utf-8"),
            domain_case=_BenchmarkCase(slot.slot_id, task),
        )

    def restore_task_case(
        self,
        *,
        public_task: PublicTask,
        semantic_key: str,
        private_case_bytes: bytes,
    ) -> CompiledTask:
        slot_id = private_case_bytes.decode("utf-8")
        if semantic_key != f"benchmark:{slot_id}":
            raise ValueError("benchmark task case semantic key drifted")
        return CompiledTask(
            public_task=public_task,
            semantic_key=semantic_key,
            private_case_bytes=private_case_bytes,
            domain_case=_BenchmarkCase(slot_id, public_task),
        )

    def open_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "_BenchmarkEpisode":
        del frozen_initial_state
        assert isinstance(task.domain_case, _BenchmarkCase)
        return _BenchmarkEpisode()

    def open_replay_episode(
        self,
        task: CompiledTask,
        frozen_initial_state: FrozenInitialState,
    ) -> "_BenchmarkEpisode":
        return self.open_episode(task, frozen_initial_state)


class _BenchmarkEpisode:
    def execute_tool_call(self, tool_name: str, arguments: dict[str, object]) -> object:
        raise AssertionError(f"benchmark policy must not call {tool_name} with {arguments}")

    def assess(self, trace: object) -> EpisodeAssessment:
        del trace
        return EpisodeAssessment(
            passed=True,
            checks=(AssessmentCheck(name="benchmark_final_response", passed=True),),
            reason_codes=(),
            coverage_tags=("engine_scale_benchmark",),
            structural_key="benchmark.final_response",
        )


class _BenchmarkModel:
    model_id = "agent_first_scale_benchmark_model"
    model_version = "agent_first_scale_benchmark_model_v1"
    provider_id = "deterministic_fake"

    def __init__(self) -> None:
        self.physical_call_count = 0

    def complete(self, request: object) -> JsonModelResponse:
        self.physical_call_count += 1
        if request.role == "task_generation":
            return JsonModelResponse(
                content={
                    "proposals": [
                        {"slot_id": slot.slot_id, "content": "benchmark task"}
                        for slot in request.slots
                    ]
                }
            )
        return JsonModelResponse(
            content={"type": "final_response", "content": "Benchmark complete."}
        )


class _NoCallBenchmarkModel(_BenchmarkModel):
    def complete(self, request: object) -> JsonModelResponse:
        raise AssertionError(f"resume repeated a terminal benchmark Episode: {request}")


def run_benchmark(
    *,
    output_directory: Path,
    attempts: int = 10_000,
    max_concurrency: int = 4,
) -> dict[str, object]:
    """Run and resume a finite fake Domain without making provider calls."""

    if not 1 <= attempts <= 10_000:
        raise ValueError("attempts must be between 1 and 10000")
    domain = _BenchmarkDomain(attempts)
    model = _BenchmarkModel()
    generation_requests = (attempts + 7) // 8
    configuration = RunConfiguration(
        run_id="agent-first-scale-benchmark",
        domain_id=domain.domain_id,
        model_id=model.model_id,
        slot_limit=attempts,
        accepted_target=attempts,
        generation_batch_size=8,
        max_concurrency=max_concurrency,
        total_request_limit=attempts + generation_requests + 16,
        generation_request_limit=generation_requests + 8,
        agent_request_limit=attempts + 8,
    )
    started = time.perf_counter()
    engine = SynthesisEngine(AdapterRegistry(domains=(domain,), models=(model,)))
    result = engine.run(configuration, output_directory)
    resumed_model = _NoCallBenchmarkModel()
    resumed = SynthesisEngine(
        AdapterRegistry(domains=(domain,), models=(resumed_model,))
    ).resume(configuration, output_directory)
    elapsed_seconds = time.perf_counter() - started
    peak_memory_mib = _peak_memory_mib()
    payload = {
        "schema_version": "agent_first_scale_benchmark_v1",
        "benchmark_scope": "test_domain_engine_capacity_only",
        "production_domain_capacity_claim": "none",
        "attempt_target": attempts,
        "known_unique_task_capacity": attempts,
        "task_attempt_count": result.task_attempt_count,
        "unique_accepted_count": result.demonstration_count,
        "physical_request_count": result.physical_request_count,
        "initial_status": result.status,
        "resume_status": resumed.status,
        "resume_provider_call_count": resumed_model.physical_call_count,
        "peak_memory_mib": peak_memory_mib,
        "memory_limit_mib": 512,
        "within_memory_limit": peak_memory_mib < 512,
        "elapsed_seconds": round(elapsed_seconds, 3),
    }
    report_path = output_directory / "agent_first_scale_benchmark.json"
    report_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload


def _peak_memory_mib() -> float:
    raw_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    bytes_per_unit = 1 if sys.platform == "darwin" else 1024
    return raw_peak * bytes_per_unit / (1024 * 1024)


def main() -> int:
    args = parse_args()
    payload = run_benchmark(
        output_directory=args.output_directory,
        attempts=args.attempts,
        max_concurrency=args.max_concurrency,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["within_memory_limit"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
