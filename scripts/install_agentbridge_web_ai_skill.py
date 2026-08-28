from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install the repository AgentBridge web-AI skill for this Codex user"
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        help="Target Codex home; defaults to CODEX_HOME or ~/.codex",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing installed agentbridge-web-ai skill",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    source = project_root / "skills" / "agentbridge-web-ai"
    if not (source / "SKILL.md").is_file():
        raise SystemExit(f"Skill source is missing: {source}")

    codex_home = args.codex_home or Path(os.getenv("CODEX_HOME", Path.home() / ".codex"))
    target = codex_home / "skills" / "agentbridge-web-ai"
    if target.exists():
        if not args.force:
            raise SystemExit(
                f"Skill already exists: {target}. Re-run with --force to replace it."
            )
        shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    print(f"Installed AgentBridge skill: {target}")
    print("Start a new Codex session to load the skill.")


if __name__ == "__main__":
    main()
