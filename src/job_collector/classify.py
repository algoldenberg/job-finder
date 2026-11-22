"""Title-based filtering, CV selection and scoring."""

import re
from dataclasses import dataclass
from typing import Self

from job_collector.models import Job

FLAGS = re.IGNORECASE


@dataclass(frozen=True)
class Classifier:
    exclude: tuple[re.Pattern, ...]
    rules: tuple[tuple[str, tuple[re.Pattern, ...]], ...]
    junior: re.Pattern

    @classmethod
    def from_config(cls, config: dict) -> Self:
        return cls(
            exclude=tuple(re.compile(p, FLAGS) for p in config["filters"]["exclude_title"]),
            rules=tuple(
                (rule["cv"], tuple(re.compile(p, FLAGS) for p in rule["patterns"]))
                for rule in config["cv_rules"]
            ),
            junior=re.compile(config["scoring"]["junior_pattern"], FLAGS),
        )

    def is_excluded(self, title: str) -> bool:
        return any(p.search(title) for p in self.exclude)

    def pick_cv(self, title: str) -> str | None:
        """Return the first CV whose patterns match the title."""
        for cv, patterns in self.rules:
            if any(p.search(title) for p in patterns):
                return cv
        return None

    def score(self, title: str, cv: str) -> int:
        """3 = junior or tier 1/2, 2 = matches profile, 1 = stretch."""
        if self.junior.search(title):
            return 3
        return 1 if cv == "DevOps" else 2

    def classify(self, job: Job) -> bool:
        """Fill in job.cv and job.score. Return False if the job should be dropped."""
        if self.is_excluded(job.title):
            return False
        cv = self.pick_cv(job.title)
        if cv is None:
            return False
        job.cv = cv
        job.score = self.score(job.title, cv)
        return True
