from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from synthesis.datasets import (
    assemble_execution_rejection,
    assemble_rejection,
    assemble_sample,
    write_dataset_artifacts,
)
from synthesis.environments import ContactEnvironment
from synthesis.execution import execute_candidate
from synthesis.llm import LLMConfig, OpenAICompatibleClient
from synthesis.seeds import foundation_seed
from synthesis.seeds import DomainSeed
from synthesis.tasks import (
    CandidateTask,
    generate_foundation_candidates,
    generate_llm_backed_candidates,
)
from synthesis.tools import build_contact_tool_registry
from synthesis.verification import ExactAnswerVerifier


@dataclass(frozen=True)
class PipelineResult:
    samples_path: Path
    manifest_path: Path
    rejections_path: Path
    accepted_count: int
    rejected_count: int


CandidateGenerator = Callable[[DomainSeed], list[CandidateTask]]


def build_llm_candidate_generator(http_client: httpx.Client | None = None) -> CandidateGenerator:
    client = OpenAICompatibleClient(LLMConfig.from_env(), http_client=http_client)
    return lambda seed: generate_llm_backed_candidates(seed, client)


def run_foundation_pipeline(
    output_dir: Path,
    *,
    dataset_version: str = "dataset_foundation_v1",
    candidate_generator: CandidateGenerator | None = None,
) -> PipelineResult:
    seed = foundation_seed()
    environment = ContactEnvironment.create_fixture(output_dir / "environment")
    registry = build_contact_tool_registry(environment)
    verifier = ExactAnswerVerifier()
    llm_config = LLMConfig.from_env()
    generate_candidates = candidate_generator or generate_foundation_candidates

    samples: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    for task in generate_candidates(seed):
        try:
            execution = execute_candidate(task, registry)
        except Exception as exc:
            rejections.append(assemble_execution_rejection(task=task, error=exc))
            continue
        verification = verifier.verify(task, execution)
        if verification.passed:
            samples.append(
                assemble_sample(
                    dataset_version=dataset_version,
                    environment=environment.metadata(),
                    tools=registry.export(),
                    task=task,
                    execution=execution,
                    verification=verification,
                    llm_config=llm_config,
                )
            )
            continue

        rejections.append(assemble_rejection(task=task, verification=verification))

    artifacts = write_dataset_artifacts(
        output_dir=output_dir,
        dataset_version=dataset_version,
        samples=samples,
        rejections=rejections,
    )
    return PipelineResult(
        samples_path=artifacts.samples_path,
        manifest_path=artifacts.manifest_path,
        rejections_path=artifacts.rejections_path,
        accepted_count=artifacts.accepted_count,
        rejected_count=artifacts.rejected_count,
    )
