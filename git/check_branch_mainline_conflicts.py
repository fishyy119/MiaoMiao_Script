"""
预测多个开发分支按不同顺序合回主分支时，是否会产生需要人工处理的冲突。

脚本不会修改目标仓库，而是创建一个临时实验仓库，在其中执行真实的合并测试，
并针对每一对分支分析以下两种顺序：

1. `main + A + B`
2. `main + B + A`

默认纳入测试的候选分支为：
1. 所有本地分支。
2. 所有尚未存在同名本地分支的远程跟踪分支。

另外，远程分支中以 `archive` 开头的分支会被自动排除。
"""

import fnmatch
import json
import shutil
import subprocess
import sys
import uuid
from argparse import ArgumentParser, Namespace
from dataclasses import asdict, dataclass
from enum import StrEnum
from itertools import combinations
from math import comb
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Self, Sequence, Set, Tuple

from rich.console import Console
from rich.table import Table
from tqdm import tqdm


class PreparedMergeStatus(StrEnum):
    CONFLICT_WITH_MAIN = "conflict-with-main"
    CLEAN = "clean"
    ALREADY_CONTAINED = "already-contained"


class SequenceStatus(StrEnum):
    FIRST_CONFLICTS_WITH_MAIN = "first-conflicts-with-main"
    CONFLICT = "conflict"
    CLEAN = "clean"
    ALREADY_CONTAINED = "already-contained"

    @property
    def is_conflict(self) -> bool:
        return self in {self.FIRST_CONFLICTS_WITH_MAIN, self.CONFLICT}

    @property
    def rank(self) -> int:
        match self:
            case self.FIRST_CONFLICTS_WITH_MAIN:
                return 0
            case self.CONFLICT:
                return 1
            case self.CLEAN:
                return 2
            case self.ALREADY_CONTAINED:
                return 3
            case _:
                raise ValueError(f"unexpected SequenceStatus: {self}")


class PairStatus(StrEnum):
    CONFLICT_WITH_MAIN = "conflict-with-main"
    CONFLICT_BOTH_ORDERS = "conflict-both-orders"
    ORDER_SENSITIVE = "order-sensitive"
    CLEAN = "clean"

    @property
    def rank(self) -> int:
        match self:
            case self.CONFLICT_WITH_MAIN:
                return 0
            case self.CONFLICT_BOTH_ORDERS:
                return 1
            case self.ORDER_SENSITIVE:
                return 2
            case self.CLEAN:
                return 3
            case _:
                raise ValueError(f"unexpected PairStatus: {self}")

    @classmethod
    def from_sequences(cls, sequence_ab: "SequenceResult", sequence_ba: "SequenceResult") -> "PairStatus":
        ab_conflict = sequence_ab.status.is_conflict
        ba_conflict = sequence_ba.status.is_conflict

        if ab_conflict and ba_conflict:
            if (
                sequence_ab.status is SequenceStatus.FIRST_CONFLICTS_WITH_MAIN
                or sequence_ba.status is SequenceStatus.FIRST_CONFLICTS_WITH_MAIN
            ):
                return cls.CONFLICT_WITH_MAIN
            return cls.CONFLICT_BOTH_ORDERS

        if ab_conflict or ba_conflict:
            return cls.ORDER_SENSITIVE

        return cls.CLEAN


console = Console()


@dataclass(frozen=True)
class Args:
    repo: Path
    main_branch: Optional[str]
    branch_patterns: List[str]
    conflicts_only: bool
    output_json: bool
    temp_root: Path

    @classmethod
    def from_ns(cls, ns: Namespace) -> "Args":
        repo = Path(str(ns.repo)).expanduser().resolve()
        if not repo.exists():
            raise ValueError(f"仓库路径不存在: {repo}")
        if not repo.is_dir():
            raise ValueError(f"仓库路径不是目录: {repo}")

        main_branch = ns.main.strip() if ns.main else None
        branch_patterns = cls._normalize_branch_patterns(ns.branch)

        if ns.temp_root:
            temp_root = Path(str(ns.temp_root)).expanduser().resolve()
        else:
            temp_root = Path(__file__).resolve().parent / ".tmp"

        if temp_root.exists() and not temp_root.is_dir():
            raise ValueError(f"临时目录不是文件夹: {temp_root}")

        return cls(
            repo=repo,
            main_branch=main_branch,
            branch_patterns=branch_patterns,
            conflicts_only=bool(ns.conflicts_only),
            output_json=bool(ns.json),
            temp_root=temp_root,
        )

    @staticmethod
    def _normalize_branch_patterns(values: Optional[Sequence[str]]) -> List[str]:
        if not values:
            return []

        patterns: List[str] = []
        seen: Set[str] = set()
        for raw_value in values:
            pattern = raw_value.strip()
            if not pattern:
                raise ValueError("--branch 不能为空")
            if pattern in seen:
                continue

            patterns.append(pattern)
            seen.add(pattern)

        return patterns


def parse_args() -> Args:
    parser = ArgumentParser(description="预测多个分支按不同顺序合回主分支时，是否会产生人工冲突。")
    parser.add_argument("repo", help="Git 仓库路径")
    parser.add_argument("--main", help="主分支名称，例如 main、master、origin/main；省略时自动检测")
    parser.add_argument("--branch", action="append", help="分支名或通配模式，可重复传入，例如 --branch 'feat/*'")
    parser.add_argument("--conflicts-only", action="store_true", help="只输出存在风险或已经冲突的分支对")
    parser.add_argument("--json", action="store_true", help="输出机器可读的 JSON 结果")
    parser.add_argument("--temp-root", help="临时实验仓库的根目录，默认使用脚本目录下的 .tmp")

    namespace = parser.parse_args()
    try:
        return Args.from_ns(namespace)
    except ValueError as exc:
        parser.error(str(exc))


@dataclass(frozen=True)
class BranchInfo:
    name: str
    tip: str

    @classmethod
    def resolve_many(cls, repo: Path, branches: Sequence[str]) -> List[Self]:
        return [
            cls(
                name=branch,
                tip=run_git(repo, "rev-parse", f"{branch}^{{commit}}").stdout.strip(),
            )
            for branch in branches
        ]


@dataclass(frozen=True)
class SequenceResult:
    status: SequenceStatus
    conflict_files: Tuple[str, ...]

    @classmethod
    def first_conflicts_with_main(cls, conflict_files: Sequence[str]) -> Self:
        return cls(
            status=SequenceStatus.FIRST_CONFLICTS_WITH_MAIN,
            conflict_files=tuple(conflict_files),
        )

    @classmethod
    def already_contained(cls) -> Self:
        return cls(status=SequenceStatus.ALREADY_CONTAINED, conflict_files=())

    @classmethod
    def clean(cls) -> Self:
        return cls(status=SequenceStatus.CLEAN, conflict_files=())

    @classmethod
    def conflict(cls, conflict_files: Sequence[str]) -> Self:
        return cls(status=SequenceStatus.CONFLICT, conflict_files=tuple(conflict_files))


@dataclass(frozen=True)
class PreparedMerge:
    status: PreparedMergeStatus
    conflict_files: Tuple[str, ...]
    integration_commit: str

    @classmethod
    def already_contained(cls, integration_commit: str) -> Self:
        return cls(
            status=PreparedMergeStatus.ALREADY_CONTAINED,
            conflict_files=(),
            integration_commit=integration_commit,
        )

    @classmethod
    def conflict_with_main(cls, conflict_files: Sequence[str], integration_commit: str) -> Self:
        return cls(
            status=PreparedMergeStatus.CONFLICT_WITH_MAIN,
            conflict_files=tuple(conflict_files),
            integration_commit=integration_commit,
        )

    @classmethod
    def clean(cls, integration_commit: str) -> Self:
        return cls(
            status=PreparedMergeStatus.CLEAN,
            conflict_files=(),
            integration_commit=integration_commit,
        )

    @classmethod
    def from_main_merge(
        cls,
        source_repo: Path,
        lab: "MergeLab",
        main_commit: str,
        branch: BranchInfo,
    ) -> Self:
        if branch.tip == main_commit or is_ancestor(source_repo, branch.tip, main_commit):
            return cls.already_contained(main_commit)

        lab.reset_to(main_commit)
        clean, conflict_files = lab.merge_without_commit(branch.tip)
        if not clean:
            return cls.conflict_with_main(conflict_files, main_commit)

        integration_commit = lab.commit_merge(f"temp merge {branch.name} into main")
        return cls.clean(integration_commit)

    def analyse_followup(self, lab: "MergeLab", second_branch: BranchInfo) -> SequenceResult:
        if self.status is PreparedMergeStatus.CONFLICT_WITH_MAIN:
            return SequenceResult.first_conflicts_with_main(self.conflict_files)

        current_commit = self.integration_commit
        if is_ancestor(lab.path, second_branch.tip, current_commit):
            return SequenceResult.already_contained()

        lab.reset_to(current_commit)
        clean, conflict_files = lab.merge_without_commit(second_branch.tip)
        if clean:
            return SequenceResult.clean()
        return SequenceResult.conflict(conflict_files)


@dataclass(frozen=True)
class PairResult:
    branch_a: str
    branch_b: str
    pair_status: PairStatus
    a_then_b_status: SequenceStatus
    a_then_b_conflict_files: List[str]
    b_then_a_status: SequenceStatus
    b_then_a_conflict_files: List[str]

    @classmethod
    def from_sequences(
        cls,
        branch_a: BranchInfo,
        branch_b: BranchInfo,
        sequence_ab: SequenceResult,
        sequence_ba: SequenceResult,
    ) -> Self:
        return cls(
            branch_a=branch_a.name,
            branch_b=branch_b.name,
            pair_status=PairStatus.from_sequences(sequence_ab, sequence_ba),
            a_then_b_status=sequence_ab.status,
            a_then_b_conflict_files=list(sequence_ab.conflict_files),
            b_then_a_status=sequence_ba.status,
            b_then_a_conflict_files=list(sequence_ba.conflict_files),
        )

    @property
    def sort_key(self) -> Tuple[int, int, int, str, str]:
        return (
            self.pair_status.rank,
            self.a_then_b_status.rank,
            self.b_then_a_status.rank,
            self.branch_a,
            self.branch_b,
        )

    @staticmethod
    def _format_conflict_files(values: Sequence[str]) -> str:
        return "\n".join(values) if values else "-"

    def to_row(self) -> Dict[str, str]:
        return {
            "branch_a": self.branch_a,
            "branch_b": self.branch_b,
            "pair_status": self.pair_status,
            "a_then_b_status": self.a_then_b_status,
            "a_then_b_conflict_files": self._format_conflict_files(self.a_then_b_conflict_files),
            "b_then_a_status": self.b_then_a_status,
            "b_then_a_conflict_files": self._format_conflict_files(self.b_then_a_conflict_files),
        }


@dataclass(frozen=True)
class AnalysisReport:
    main_branch: str
    main_commit: str
    tested_branches: List[str]
    pair_results: List[PairResult]

    @classmethod
    def create(
        cls,
        main_branch: str,
        main_commit: str,
        tested_branches: Sequence[str],
        pair_results: Sequence[PairResult],
    ) -> Self:
        return cls(
            main_branch=main_branch,
            main_commit=main_commit,
            tested_branches=list(tested_branches),
            pair_results=sorted(pair_results, key=lambda item: item.sort_key),
        )

    @property
    def branch_count(self) -> int:
        return len(self.tested_branches)

    def filtered_pair_results(self, conflicts_only: bool) -> List[PairResult]:
        if not conflicts_only:
            return list(self.pair_results)
        return [item for item in self.pair_results if item.pair_status is not PairStatus.CLEAN]

    def to_table_rows(self, conflicts_only: bool) -> List[Dict[str, str]]:
        return [item.to_row() for item in self.filtered_pair_results(conflicts_only)]

    def to_json_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = asdict(self)
        payload["branch_count"] = self.branch_count
        return payload


def run_git(
    repo: Path,
    *args: str,
    check: bool = True,
    allowed_returncodes: Tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode not in allowed_returncodes:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or "unknown git error"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result


def validate_repo(repo: Path) -> Path:
    run_git(repo, "rev-parse", "--git-dir")
    return repo


def split_remote_branch(refname: str) -> Optional[Tuple[str, str]]:
    prefix = "refs/remotes/"
    if not refname.startswith(prefix):
        return None

    suffix = refname[len(prefix) :]
    if "/" not in suffix:
        return None

    remote_name, branch_name = suffix.split("/", 1)
    if branch_name == "HEAD":
        return None

    return remote_name, branch_name


def collect_branches(repo: Path) -> List[str]:
    local_result = run_git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    local_branches = sorted(
        {line.strip() for line in local_result.stdout.splitlines() if line.strip() and line.strip() != "HEAD"}
    )
    local_branch_set: Set[str] = set(local_branches)

    remote_result = run_git(repo, "for-each-ref", "--format=%(refname)", "refs/remotes")
    remote_branches: List[str] = []
    for raw_ref in remote_result.stdout.splitlines():
        refname = raw_ref.strip()
        if not refname:
            continue

        parsed = split_remote_branch(refname)
        if not parsed:
            continue

        remote_name, branch_name = parsed
        if branch_name.startswith("archive"):
            continue

        short_name = f"{remote_name}/{branch_name}"
        if branch_name not in local_branch_set:
            remote_branches.append(short_name)

    return sorted(set(local_branches + remote_branches))


def branch_exists(repo: Path, branch: str) -> bool:
    result = run_git(
        repo,
        "rev-parse",
        "--verify",
        "--quiet",
        f"{branch}^{{commit}}",
        check=False,
        allowed_returncodes=(0, 1),
    )
    return result.returncode == 0


def detect_main_branch(repo: Path, requested: Optional[str]) -> str:
    if requested:
        if not branch_exists(repo, requested):
            raise ValueError(f"main branch not found: {requested}")
        return requested

    preferred = ["main", "master", "origin/main", "origin/master"]
    for candidate in preferred:
        if branch_exists(repo, candidate):
            return candidate

    remote_head = run_git(
        repo,
        "symbolic-ref",
        "refs/remotes/origin/HEAD",
        check=False,
        allowed_returncodes=(0, 1, 128),
    )
    if remote_head.returncode == 0:
        ref = remote_head.stdout.strip()
        if ref.startswith("refs/remotes/"):
            return ref.removeprefix("refs/remotes/")

    raise ValueError("unable to auto-detect main branch, please specify --main")


def select_branches(
    all_branches: Sequence[str],
    patterns: Sequence[str],
    main_branch: str,
) -> List[str]:
    if patterns:
        selected: Set[str] = set()
        missing: List[str] = []
        for pattern in patterns:
            matches = [branch for branch in all_branches if fnmatch.fnmatch(branch, pattern)]
            if not matches:
                missing.append(pattern)
                continue
            selected.update(matches)
        if missing:
            raise ValueError(f"no branches matched pattern(s): {', '.join(missing)}")
        branches = sorted(selected)
    else:
        branches = list(all_branches)

    return [branch for branch in branches if branch != main_branch]


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = run_git(
        repo,
        "merge-base",
        "--is-ancestor",
        ancestor,
        descendant,
        check=False,
        allowed_returncodes=(0, 1),
    )
    return result.returncode == 0


class MergeLab:
    def __init__(self, source_git_dir: Path, temp_root: Path) -> None:
        temp_root.mkdir(parents=True, exist_ok=True)
        self._root = temp_root / f"git-mainline-conflicts-{uuid.uuid4().hex[:12]}"
        self._root.mkdir(parents=True, exist_ok=False)
        self.path = self._root
        run_git(self.path, "init", "--quiet")
        alternates = self.path / ".git" / "objects" / "info" / "alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_bytes(((source_git_dir / "objects").as_posix() + "\n").encode("utf-8"))
        run_git(self.path, "config", "user.name", "Codex Temp Merge")
        run_git(self.path, "config", "user.email", "codex-temp-merge@example.invalid")

    def close(self) -> None:
        shutil.rmtree(self._root, ignore_errors=True)

    def reset_to(self, commit: str) -> None:
        run_git(
            self.path,
            "merge",
            "--abort",
            check=False,
            allowed_returncodes=(0, 1, 128),
        )
        run_git(self.path, "switch", "--detach", "--force", commit)
        run_git(self.path, "reset", "--hard", commit)
        run_git(self.path, "clean", "-fd")

    def head_commit(self) -> str:
        return run_git(self.path, "rev-parse", "HEAD").stdout.strip()

    def list_conflict_files(self) -> Tuple[str, ...]:
        result = run_git(self.path, "diff", "--name-only", "--diff-filter=U")
        files = sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})
        return tuple(files)

    def commit_merge(self, message: str) -> str:
        run_git(self.path, "commit", "--quiet", "-m", message)
        return self.head_commit()

    def merge_without_commit(self, commit: str) -> Tuple[bool, Tuple[str, ...]]:
        result = run_git(
            self.path,
            "merge",
            "--no-commit",
            "--no-ff",
            commit,
            check=False,
            allowed_returncodes=(0, 1),
        )
        if result.returncode == 0:
            return True, ()
        return False, self.list_conflict_files()


def analyse_repo(
    source_repo: Path,
    main_branch: str,
    branches: Sequence[BranchInfo],
    temp_root: Path,
) -> AnalysisReport:
    main_commit = run_git(source_repo, "rev-parse", f"{main_branch}^{{commit}}").stdout.strip()
    source_git_dir = Path(run_git(source_repo, "rev-parse", "--absolute-git-dir").stdout.strip())
    prepared_merges: Dict[str, PreparedMerge] = {}
    pair_results: List[PairResult] = []
    total_steps = 2 * comb(len(branches), 2)

    lab = MergeLab(source_git_dir=source_git_dir, temp_root=temp_root)
    try:

        def get_prepared_merge(branch: BranchInfo) -> PreparedMerge:
            cached = prepared_merges.get(branch.name)
            if cached is not None:
                return cached

            prepared = PreparedMerge.from_main_merge(
                source_repo=source_repo,
                lab=lab,
                main_commit=main_commit,
                branch=branch,
            )
            prepared_merges[branch.name] = prepared
            return prepared

        with tqdm(
            total=total_steps,
            desc="测试合并序列",
            unit="step",
            dynamic_ncols=True,
            leave=True,
        ) as progress:
            for branch_a, branch_b in combinations(branches, 2):
                result_a = get_prepared_merge(branch_a)
                result_b = get_prepared_merge(branch_b)

                progress.set_postfix_str(f"main + {branch_a.name} + {branch_b.name}")
                sequence_ab = result_a.analyse_followup(lab, branch_b)
                progress.update(1)

                progress.set_postfix_str(f"main + {branch_b.name} + {branch_a.name}")
                sequence_ba = result_b.analyse_followup(lab, branch_a)
                progress.update(1)

                pair_results.append(PairResult.from_sequences(branch_a, branch_b, sequence_ab, sequence_ba))
    finally:
        lab.close()

    return AnalysisReport.create(
        main_branch=main_branch,
        main_commit=main_commit,
        tested_branches=[branch.name for branch in branches],
        pair_results=pair_results,
    )


def print_table(
    title: str,
    rows: Sequence[Mapping[str, str]],
    columns: Sequence[Tuple[str, str]],
) -> None:
    table = Table(title=title, show_lines=False)
    for _, header in columns:
        table.add_column(header, overflow="fold")

    if not rows:
        empty_row = ["(none)"] + [""] * (len(columns) - 1)
        table.add_row(*empty_row)
        console.print(table)
        return

    for row in rows:
        table.add_row(*[str(row.get(key, "")) for key, _ in columns])

    console.print(table)


def print_report(report: AnalysisReport, conflicts_only: bool) -> None:
    console.print(f"[bold]主分支:[/] {report.main_branch}")
    console.print(f"[bold]主分支提交:[/] {report.main_commit}")
    console.print(f"[bold]测试分支数:[/] {report.branch_count}")
    console.print()

    print_table(
        "主线合并冲突预测",
        report.to_table_rows(conflicts_only),
        [
            ("branch_a", "分支A"),
            ("branch_b", "分支B"),
            ("pair_status", "整体结论"),
            ("a_then_b_status", "main+A+B"),
            ("a_then_b_conflict_files", "A后合B冲突文件"),
            ("b_then_a_status", "main+B+A"),
            ("b_then_a_conflict_files", "B后合A冲突文件"),
        ],
    )


def main() -> int:
    args = parse_args()
    try:
        repo = validate_repo(args.repo)
        main_branch = detect_main_branch(repo, args.main_branch)
        all_branches = collect_branches(repo)
        branches = select_branches(all_branches, args.branch_patterns, main_branch)
        if len(branches) < 2:
            raise RuntimeError("过滤后至少需要 2 个候选分支")

        branch_info = BranchInfo.resolve_many(repo, branches)
        report = analyse_repo(repo, main_branch, branch_info, temp_root=args.temp_root)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        json.dump(report.to_json_dict(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print_report(report, conflicts_only=args.conflicts_only)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
