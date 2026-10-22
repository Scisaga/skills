#!/usr/bin/env python3
"""Record SHA-bound content, visual, or narration approval."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from build_manifest import build_manifest, render_review
from page_script_contract import (
    audit_director_text,
    audit_page_script,
)
from narration_performance import audit_narration_performance
from validate_input_document import INPUT_CONTRACT_VERSION
from production_common import (
    file_hash,
    load_object,
    load_project_config,
    load_voice_profile,
    parse_page_list,
    project_paths,
    record_approval,
    require_approvals,
    write_object,
)


def verify_source(project: Path) -> None:
    config = load_project_config(project)
    source = config["source"]
    if source.get("mode") != "document":
        raise ValueError("project.json source.mode must be document")
    document_value = source.get("document")
    if not isinstance(document_value, str) or not document_value:
        raise ValueError("project.json source.document is required")
    document = Path(document_value)
    if not document.is_absolute():
        document = project / document
    if not document.is_file():
        raise FileNotFoundError(document)
    if source.get("document_sha256") != file_hash(document):
        raise RuntimeError(
            "Input document changed after its quality gate; review it again "
            "before approving content"
        )
    gate_value = source.get("gate_report")
    if not isinstance(gate_value, str) or not gate_value:
        raise ValueError("project.json source.gate_report is required")
    gate_path = Path(gate_value)
    if not gate_path.is_absolute():
        gate_path = project / gate_path
    gate = load_object(gate_path)
    if (
        gate.get("passed") is not True
        or gate.get("document_sha256") != source["document_sha256"]
        or gate.get("contract_version") != INPUT_CONTRACT_VERSION
    ):
        raise RuntimeError(
            "The recorded input quality gate is not current; regenerate it "
            "with the current input contract before content approval"
        )
    gate_sha = source.get("gate_report_sha256")
    if not isinstance(gate_sha, str) or not gate_sha:
        raise RuntimeError(
            "Input gate SHA evidence is missing; run refresh-input-gate first"
        )
    if gate_sha != file_hash(gate_path):
        raise RuntimeError("The recorded input quality gate file was modified")
    semantic_required = gate.get(
        "semantic_review_required",
        source.get("profile") != "page-narration",
    )
    if semantic_required:
        review_value = source.get("review")
        if not isinstance(review_value, str) or not review_value:
            raise RuntimeError("The source profile requires input-review.json")
        review_path = Path(review_value)
        if not review_path.is_absolute():
            review_path = project / review_path
        if not review_path.is_file():
            raise FileNotFoundError(review_path)
        review_sha = source.get("review_sha256")
        if not isinstance(review_sha, str) or not review_sha:
            raise RuntimeError(
                "Input review SHA evidence is missing; run refresh-input-gate first"
            )
        if review_sha != file_hash(review_path):
            raise RuntimeError("The SHA-bound input review file was modified")


def verify_narration_review(project: Path) -> dict[str, object]:
    config = load_project_config(project)
    paths = project_paths(project)
    visual = load_object(paths["manifest"])
    director = load_object(paths["director"])
    text_audit = audit_director_text(paths["page_script"], director)
    if text_audit["status"] != "pass":
        raise RuntimeError(
            "Narration source binding: " + "; ".join(text_audit["errors"])
        )
    performance_audit = audit_narration_performance(director)
    if performance_audit["status"] != "pass":
        raise RuntimeError(
            "Narration performance contract: "
            + "; ".join(performance_audit["errors"])
        )
    voice = load_voice_profile(paths["voice_profile"])
    expected_manifest = build_manifest(
        None if config["deliverable"] == "narration_audio" else visual,
        director,
        voice,
    )
    if visual != expected_manifest:
        raise RuntimeError(
            "Narration fields in animation_manifest.json are stale; "
            "run manifest before approving narration"
        )
    review_path = project / "video" / "narration_review.md"
    if not review_path.is_file():
        raise FileNotFoundError(review_path)
    if review_path.read_text(encoding="utf-8") != render_review(
        expected_manifest
    ):
        raise RuntimeError(
            "narration_review.md is stale; run manifest before approval"
        )
    return {
        "director_text_audit": text_audit,
        "performance_audit": performance_audit,
        "narration_pitch": expected_manifest["narration_pitch"],
    }


def persisted_rewrite_authorization(
    config: dict[str, object],
    paths: dict[str, Path],
    source_path: Path,
) -> bool:
    """Reuse an explicit adapted authorization only for the same bound bytes."""
    source = config.get("source")
    content = config.get("content")
    if (
        not isinstance(source, dict)
        or not isinstance(content, dict)
        or source.get("profile") != "page-narration"
        or content.get("binding_mode") != "adapted"
        or not paths["binding_audit"].is_file()
    ):
        return False
    try:
        recorded = load_object(paths["binding_audit"])
    except (OSError, ValueError):
        return False
    page_script_sha = file_hash(paths["page_script"])
    return bool(
        recorded.get("status") == "pass"
        and recorded.get("binding_mode") == "adapted"
        and recorded.get("rewrite_authorized") is True
        and recorded.get("rewrite_authorized_page_script_sha256")
        == page_script_sha
        and recorded.get("page_script_sha256") == page_script_sha
        and recorded.get("source_document_sha256") == file_hash(source_path)
        and recorded.get("source_profile") == "page-narration"
    )


def approve_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    verify_source(project)
    pages = parse_page_list(args.pages)
    extra_evidence = None
    if args.allow_substantial_rewrite and args.stage != "content":
        raise ValueError(
            "--allow-substantial-rewrite is valid only with --stage content"
        )
    if args.stage == "content":
        if pages:
            raise ValueError("--pages is only valid with --stage visual")
        config = load_project_config(project)
        if (
            args.allow_substantial_rewrite
            and config["source"].get("profile") != "page-narration"
        ):
            raise ValueError(
                "--allow-substantial-rewrite applies only to page-narration sources"
            )
        paths = project_paths(project, config)
        source_value = config["source"]["document"]
        source_path = Path(source_value)
        if not source_path.is_absolute():
            source_path = project / source_path
        persisted_authorization = persisted_rewrite_authorization(
            config,
            paths,
            source_path,
        )
        effective_rewrite_authorization = bool(
            args.allow_substantial_rewrite or persisted_authorization
        )
        audit = audit_page_script(
            paths["page_script"],
            source=source_path,
            allow_substantial_rewrite=effective_rewrite_authorization,
            enforce_source_fidelity=(
                config["source"].get("profile") == "page-narration"
            ),
        )
        if audit["status"] != "pass":
            raise RuntimeError("Page script contract: " + "; ".join(audit["errors"]))
        fidelity = audit.get("fidelity")
        content_metadata_changed = False
        exact_page_source = bool(
            config["source"].get("profile") == "page-narration"
            and isinstance(fidelity, dict)
            and fidelity.get("exact_byte_copy") is True
        )
        if exact_page_source and config["content"].get("binding_mode") != "identity":
            config["content"]["binding_mode"] = "identity"
            content_metadata_changed = True
            print("INFO exact page narration recorded as identity binding")
        elif config["content"].get("binding_mode") is None:
            config["content"]["binding_mode"] = "adapted"
            content_metadata_changed = True
        if config["content"].get("binding_audit") is None:
            config["content"]["binding_audit"] = (
                "inputs/page-script-binding.json"
            )
            content_metadata_changed = True
        if config["content"].get("page_count_at_init") is None:
            config["content"]["page_count_at_init"] = audit["page_count"]
            content_metadata_changed = True
        if config["content"].get("page_script_origin_document") is None:
            config["content"]["page_script_origin_document"] = (
                config["source"].get("document") or "page-script.md"
            )
            content_metadata_changed = True
        if (
            config["content"].get("binding_mode") == "identity"
            and isinstance(fidelity, dict)
            and fidelity.get("exact_byte_copy") is not True
        ):
            if not args.allow_substantial_rewrite:
                raise RuntimeError(
                    "Identity binding changed; restore the byte-identical source "
                    "or explicitly authorize a transition to adapted binding"
                )
            config["content"]["binding_mode"] = "adapted"
            content_metadata_changed = True
            print("INFO content binding transitioned from identity to adapted")
        if content_metadata_changed:
            write_object(paths["project"], config)
            print("INFO content binding metadata recorded in project.json")
        extra_evidence = {
            "page_script_audit": {
                "page_count": audit["page_count"],
                "page_script_sha256": audit["page_script_sha256"],
                "fidelity": audit["fidelity"],
                "rewrite_authorized": effective_rewrite_authorization,
                "authorization_source": (
                    "current-command"
                    if args.allow_substantial_rewrite
                    else "persisted-binding-audit"
                    if persisted_authorization
                    else None
                ),
            }
        }
        recorded_audit = {
            **audit,
            "page_script": "page-script.md",
            "source_document": config["source"]["document"],
            "source_document_sha256": config["source"]["document_sha256"],
            "source_profile": config["source"].get("profile"),
            "binding_mode": config["content"]["binding_mode"],
            "rewrite_authorized": bool(
                config["source"].get("profile") == "page-narration"
                and config["content"].get("binding_mode") == "adapted"
                and effective_rewrite_authorization
            ),
            "rewrite_authorized_page_script_sha256": (
                audit["page_script_sha256"]
                if config["source"].get("profile") == "page-narration"
                and config["content"].get("binding_mode") == "adapted"
                and effective_rewrite_authorization
                else None
            ),
            "page_script_origin_document": config["content"].get(
                "page_script_origin_document", "page-script.md"
            ),
        }
        if isinstance(recorded_audit.get("fidelity"), dict):
            recorded_audit["fidelity"]["source"] = config["source"][
                "document"
            ]
        write_object(paths["binding_audit"], recorded_audit)
    elif args.stage == "visual":
        require_approvals(project, ("content",))
        if not pages:
            raise ValueError("--stage visual requires representative --pages")
    else:
        if pages:
            raise ValueError("--pages is only valid with --stage visual")
        require_approvals(project, ("content",))
        extra_evidence = verify_narration_review(project)
    record = record_approval(
        project,
        args.stage,
        approved_by=args.approved_by,
        pages=pages,
        extra_evidence=extra_evidence,
    )
    print(
        f"OK  approved stage={args.stage} "
        f"fingerprint={record['fingerprint']} "
        f"by={record['approved_by']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--stage",
        choices=("content", "visual", "narration"),
        required=True,
    )
    parser.add_argument(
        "--allow-substantial-rewrite",
        action="store_true",
        help="User-confirmed authorization for any non-identity page narration",
    )
    parser.add_argument("--approved-by", required=True)
    parser.add_argument(
        "--pages",
        help="Representative pages for visual approval, for example 3,7,10",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return approve_command(build_parser().parse_args(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
