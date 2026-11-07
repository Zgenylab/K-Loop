#!/usr/bin/env python3
"""Read-only K-Loop state, artifact, and handoff consistency checks (stdlib only)."""

import argparse
import hashlib
import json
import re
import sys
from collections import deque
from itertools import islice
from pathlib import Path, PureWindowsPath

PHASES = tuple("K" + str(i) for i in range(6))
STATUSES = ("pending", "in_progress", "done", "blocked", "needs_review", "skipped_with_reason")
TERMINAL = ("done", "skipped_with_reason")
SCOPE = ("Checks structure, declared status, file presence and supplied hashes only; "
         "does not independently verify semantic acceptance or approve execution.")


def text(value):
    return isinstance(value, str) and bool(value.strip())


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def invalid_constant(value):
    raise ValueError("non-standard JSON constant: " + value)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def inspect_project(project_root, state_name):
    result = {"ok": False, "counts": dict.fromkeys(STATUSES, 0),
              "counts_basis": "declared unit statuses; skipped is not done",
              "errors": [], "warnings": [], "scope": SCOPE}
    errors, warnings = result["errors"], result["warnings"]

    def require(condition, message):
        if not condition:
            errors.append(message)

    try:
        root = Path(project_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("PROJECT_ROOT must be an existing directory")
    except (OSError, ValueError, RuntimeError) as exc:
        errors.append("PROJECT_ROOT: " + str(exc))
        return result

    def project_file(value, label, nonempty=False):
        if not text(value) or "\x00" in value:
            errors.append(label + ": expected a nonempty relative file path")
            return None
        path = Path(value)
        windows = PureWindowsPath(value)
        if path.is_absolute() or windows.drive or windows.root or ".." in value.replace("\\", "/").split("/"):
            errors.append(label + ": absolute paths and '..' are forbidden")
            return None
        try:
            resolved = (root / path).resolve(strict=True)
            resolved.relative_to(root)
            if not resolved.is_file():
                raise ValueError("not a regular file")
            if nonempty and resolved.stat().st_size == 0:
                raise ValueError("file is empty")
            return resolved
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(label + ": missing, invalid or outside project: " + str(exc))
            return None

    def files(values, label, nonempty=False):
        if not isinstance(values, list) or not values:
            errors.append(label + ": expected a nonempty file-path array")
            return
        for i, value in enumerate(values):
            project_file(value, label + "[" + str(i) + "]", nonempty)

    state_path = project_file(state_name, "state", nonempty=True)
    if state_path is None:
        return result
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig"), parse_constant=invalid_constant)
        if not isinstance(state, dict):
            raise ValueError("state must be a JSON object")
    except (OSError, ValueError, RecursionError) as exc:
        errors.append("state: " + str(exc))
        return result

    for key in ("project_id", "name", "goal", "plan_version"):
        require(text(state.get(key)), key + ": expected a nonempty string")
    require(state.get("schema_version") == "k-loop/1", "schema_version must be k-loop/1")
    revision = state.get("revision")
    require(integer(revision, 1), "revision must be an integer >= 1 (not bool)")
    require(integer(state.get("rounds_completed")), "rounds_completed must be an integer >= 0")
    phase, status = state.get("phase"), state.get("status")
    require(phase in PHASES, "phase must be K0..K5")
    require(status in ("active", "blocked", "needs_review", "complete"), "invalid project status")
    result.update(project_id=state.get("project_id") if text(state.get("project_id")) else None,
                  revision=revision if integer(revision, 1) else None,
                  phase=phase if phase in PHASES else None,
                  status=status if isinstance(status, str) else None)
    approval = state.get("plan_approval")
    if not isinstance(approval, dict):
        errors.append("plan_approval must be an object")
    else:
        require(approval.get("status") == "confirmed", "plan_approval.status must be confirmed")
        require(approval.get("plan_version") == state.get("plan_version"), "plan_approval.plan_version is stale")
        require(text(approval.get("basis")), "plan_approval.basis must be nonempty")

    units = state.get("units")
    if not isinstance(units, list):
        errors.append("units must be an array")
        units = []
    by_id, dependencies = {}, {}
    for i, unit in enumerate(units):
        label = "units[" + str(i) + "]"
        if not isinstance(unit, dict):
            errors.append(label + ": must be an object")
            continue
        uid, unit_status = unit.get("unit_id"), unit.get("status")
        if not text(uid):
            errors.append(label + ".unit_id must be nonempty")
        elif uid in by_id:
            errors.append(label + ".unit_id is duplicated: " + uid)
        else:
            by_id[uid] = unit
        require(unit_status in STATUSES, label + ": invalid unit status")
        if unit_status in STATUSES:
            result["counts"][unit_status] += 1
        if unit_status == "done":
            files(unit.get("outputs"), label + ".outputs", nonempty=True)
            acceptance = unit.get("acceptance")
            if not isinstance(acceptance, dict):
                errors.append(label + ".acceptance must be an object")
            else:
                require(acceptance.get("status") == "passed", label + ".acceptance.status must be passed")
                files(acceptance.get("evidence"), label + ".acceptance.evidence")
        if unit_status == "skipped_with_reason":
            require(text(unit.get("reason")), label + ".reason is required for skipped units")

    for uid, unit in by_id.items():
        deps = unit.get("depends_on", [])
        if not isinstance(deps, list) or any(not text(dep) for dep in deps):
            errors.append(uid + ".depends_on must be an array of nonempty IDs")
            deps = []
        dependencies[uid] = set()
        for dep in deps:
            if dep not in by_id:
                errors.append(uid + ": unknown dependency " + dep)
            elif dep == uid:
                errors.append(uid + ": self-dependency is forbidden")
            else:
                dependencies[uid].add(dep)
                parent = by_id[dep]
                ready = parent.get("status") == "done" or (parent.get("status") == "skipped_with_reason" and text(parent.get("reason")))
                require(unit.get("status") != "done" or ready, uid + ": done unit has unfinished dependency " + dep)
    indegree = {uid: len(deps) for uid, deps in dependencies.items()}
    children = {uid: [] for uid in by_id}
    for uid, deps in dependencies.items():
        for dep in deps:
            children[dep].append(uid)
    queue, visited = deque(uid for uid, count in indegree.items() if count == 0), 0
    while queue:
        uid = queue.popleft()
        visited += 1
        for child in children[uid]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    require(visited == len(by_id), "dependency cycle detected")
    terminal = len(by_id) == len(units) and all(u.get("status") in TERMINAL for u in by_id.values())
    result["all_units_terminal"] = terminal

    require("next_action" in state, "next_action must be present (object or null)")
    next_action, next_phase = state.get("next_action"), None
    if next_action is not None:
        if not isinstance(next_action, dict):
            errors.append("next_action must be an object or null")
        else:
            next_phase = next_action.get("phase")
            require(next_phase in PHASES, "next_action.phase must be K0..K5")
            for key in ("label", "prompt"):
                require(text(next_action.get(key)), "next_action." + key + " must be nonempty")
            expected = next_action.get("expected_revision")
            require(integer(expected, 1) and expected == revision, "next_action.expected_revision is invalid or stale")
            ids = next_action.get("unit_ids")
            if not isinstance(ids, list):
                errors.append("next_action.unit_ids must be an array")
            else:
                require(next_phase != "K1" or bool(ids), "next K1 requires nonempty unit_ids")
                earlier = set()
                for uid in ids:
                    if not text(uid) or uid not in by_id:
                        errors.append("next_action.unit_ids contains an unknown or invalid ID")
                    else:
                        require(by_id[uid].get("status") in ("pending", "in_progress"), "next_action targets a non-executable unit: " + uid)
                        if next_phase == "K1":
                            require(uid not in earlier, "next K1 unit_ids contains a duplicate: " + uid)
                            for dep in dependencies[uid]:
                                parent = by_id[dep]
                                ready = parent.get("status") == "done" or (parent.get("status") == "skipped_with_reason" and text(parent.get("reason")))
                                require(ready or dep in earlier, "next K1 dependency is neither complete nor earlier in this batch: " + uid + " <- " + dep)
                            earlier.add(uid)
    if next_phase in ("K3", "K4", "K5"):
        require(terminal, "next K3/K4/K5 requires all main units to be done or skipped with reason")

    checks = state.get("stage_checks", {})
    if not isinstance(checks, dict):
        errors.append("stage_checks must be an object")
        checks = {}
    if next_phase in PHASES[1:]:
        require(checks.get("K0") == "passed", "next K1..K5 requires stage_checks.K0 passed")
    if next_phase in ("K4", "K5") or phase == "K5":
        require(checks.get("K3") == "passed", "next K4/K5 or current K5 requires stage_checks.K3 passed")
    blockers = state.get("blocking_issues")
    if "blocking_issues" in state:
        require(isinstance(blockers, list), "blocking_issues must be an array")
    limits = state.get("known_limitations")
    if "known_limitations" in state:
        require(isinstance(limits, list), "known_limitations must be an array")
    k4_ok = checks.get("K4") in ("passed", "conditional_pass")
    if checks.get("K4") == "conditional_pass":
        require(isinstance(limits, list) and bool(limits) and all(text(x) for x in limits), "K4 conditional_pass requires nonempty known_limitations strings")
        warnings.append("K4 is conditional_pass; retain known_limitations in the delivery.")
    if phase == "K5" or next_phase == "K5" or status == "complete":
        require(terminal, "K5/complete requires all main units terminal")
        require(k4_ok, "K5/complete requires stage_checks.K4 passed or conditional_pass")
        require(isinstance(blockers, list) and not blockers, "K5/complete requires explicit empty blocking_issues")
    if status == "complete":
        require(phase == "K5", "complete requires phase=K5")
        require(checks.get("K0") == "passed", "complete requires stage_checks.K0 passed")
        require(checks.get("K3") == "passed", "complete requires stage_checks.K3 passed")
        require(checks.get("K5") == "passed", "complete requires stage_checks.K5 passed")
        require(next_action is None, "complete requires next_action=null")

    handoff = project_file("KLOOP_HANDOFF.md", "handoff", nonempty=True)
    if handoff:
        try:
            with handoff.open(encoding="utf-8-sig") as handle:
                lines = [line for line in islice(handle, 30) if re.search(r"<!--\s*kloop-state\b", line)]
            if len(lines) != 1:
                raise ValueError("expected exactly one kloop-state marker in the first 30 lines")
            match = re.fullmatch(r"\s*<!--\s*kloop-state\s+(\{.*\})\s*-->\s*", lines[0])
            marker = json.loads(match.group(1), parse_constant=invalid_constant) if match else None
            if not isinstance(marker, dict):
                raise ValueError("marker must contain a JSON object on one line")
            require(marker.get("project_id") == state.get("project_id"), "handoff project_id mismatch")
            require(integer(marker.get("revision"), 1) and marker["revision"] == revision, "handoff revision mismatch")
        except (OSError, ValueError, RecursionError) as exc:
            errors.append("handoff: " + str(exc))

    hashes = state.get("evidence_sha256", {})
    if not isinstance(hashes, dict):
        errors.append("evidence_sha256 must be a path:sha256 object")
    else:
        for name, expected in hashes.items():
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
                errors.append("evidence_sha256: invalid SHA-256 for " + name)
                continue
            path = project_file(name, "evidence_sha256[" + name + "]")
            if path:
                try:
                    digest = hashlib.sha256()
                    with path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    require(digest.hexdigest() == expected.lower(), "evidence_sha256 mismatch: " + name)
                except OSError as exc:
                    errors.append("evidence_sha256: " + str(exc))
    result["ok"] = not errors
    return result


def main():
    parser = Parser(description=__doc__)
    parser.add_argument("project_root", metavar="PROJECT_ROOT")
    parser.add_argument("--state", default="_kloop/state.json", help="project-relative state file")
    try:
        args = parser.parse_args()
        result = inspect_project(args.project_root, args.state)
    except (OSError, ValueError, RecursionError) as exc:
        result = {"ok": False, "counts": dict.fromkeys(STATUSES, 0), "errors": [str(exc)], "warnings": [], "scope": SCOPE}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
