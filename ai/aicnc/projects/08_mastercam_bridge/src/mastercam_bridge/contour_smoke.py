"""Prepare and verify a synthetic Mastercam contour through the existing MCP.

This is a native capability test fixture, not a second CAM plan or executor.
Run the generated scripts with mastercam_run_script, save, close the owned host,
launch the saved MCAM in a fresh process, then run the read-only reopen script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import uuid

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[4]
TEMPLATE = Path(__file__).resolve().parents[1] / "mastercam/aicnc_contour_smoke.csx"
SCHEMA = ROOT / "schemas/mastercam_contour_smoke.schema.json"


def validate_contract(value: dict, definition: str) -> None:
    schema = load(SCHEMA)
    Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}).validate(value)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def prepare(directory: Path) -> dict:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    run_id = "contour-" + uuid.uuid4().hex[:12]
    request = {
        "schema_version": "aicnc.mastercam-contour-smoke-request/0.1",
        "purpose": "synthetic_native_validation", "run_id": run_id,
        "operation_name": "AICNC_" + run_id,
        "model_path": str(directory / "contour.mcam"),
        "width_mm": 60.0, "height_mm": 40.0, "depth_mm": -2.0,
        "tool_diameter_mm": 6.0, "feed_mm_min": 300.0, "spindle_rpm": 3000,
    }
    validate_contract(request, "request")
    write_new(directory / "request.json", request)
    rendered = {}
    for mode in ("create", "reopen"):
        text = TEMPLATE.read_text(encoding="utf-8")
        assembly=subprocess.check_output([__import__("sys").executable,str(ROOT.parent/"tools/compile_script.py"),"--json-assembly"],text=True).strip()
        text=text.replace("__SYSTEM_TEXT_JSON__",assembly.replace("\\","/"))
        for key, value in {
            "__REQUEST_PATH__": str(directory / "request.json"),
            "__RECEIPT_PATH__": str(directory / (mode + ".json")),
            "__MODE__": mode,
            "__REQUEST_SHA256__": digest(directory / "request.json"),
        }.items():
            text = text.replace(key, json.dumps(value, ensure_ascii=True))
        script = directory / (mode + ".csx")
        script.write_text(text, encoding="utf-8", newline="\n")
        rendered[mode] = digest(script)
    manifest = {
        "base_commit": json.loads((ROOT/"source-manifest.json").read_text(encoding="utf-8"))["upstream_base_commit"],
        "template_sha256": digest(TEMPLATE), "verifier_sha256": digest(Path(__file__)),
        "request_sha256": digest(directory / "request.json"), "scripts_sha256": rendered,
        "scope": "synthetic contour creation, native readback and fresh-process persistence",
        "cutting_parameters_source": "explicit software test fixture; no material or production qualification",
    }
    validate_contract(manifest, "manifest")
    write_new(directory / "source_manifest.json", manifest)
    return request


def verify(directory: Path) -> dict:
    directory = directory.resolve()
    request = load(directory / "request.json")
    validate_contract(request, "request")
    manifest = load(directory / "source_manifest.json")
    validate_contract(manifest, "manifest")
    before, after = (load(directory / (mode + ".json")) for mode in ("create", "reopen"))
    validate_contract(before, "receipt")
    validate_contract(after, "receipt")
    errors: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    def near(actual, expected, label: str) -> None:
        check(isinstance(actual, (int, float)) and not isinstance(actual, bool)
              and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-7), label)

    request_hash = digest(directory / "request.json")
    check(request_hash == manifest["request_sha256"], "request changed after preparation")
    for mode in ("create", "reopen"):
        check(digest(directory / (mode + ".csx")) == manifest["scripts_sha256"][mode], f"{mode} script changed")
    check(digest(TEMPLATE) == manifest["template_sha256"], "native source changed since trial")
    for mode, receipt in (("create", before), ("reopen", after)):
        check(receipt.get("ok") is True and receipt.get("stage") == "complete", f"{mode}: native execution failed")
        check(receipt.get("mode") == mode and receipt.get("run_id") == request["run_id"], f"{mode}: wrong run")
        check(receipt.get("request_sha256") == request_hash, f"{mode}: wrong request hash")
        check(Path(receipt.get("model_path", "")).resolve() == directory / "contour.mcam", f"{mode}: model path")
        check(receipt.get("production_released") is False, f"{mode}: production scope")
        check(receipt.get("regeneration_performed") is (mode == "create"), f"{mode}: regeneration boundary")
        snapshot = receipt.get("snapshot", {})
        check(snapshot.get("metric") is True, f"{mode}: units")
        check(snapshot.get("operation_count") == 1 and snapshot.get("geometry_count") == 4, f"{mode}: object counts")
        check(snapshot.get("operation_name") == request["operation_name"], f"{mode}: operation identity")
        check(snapshot.get("operation_type") == "Mastercam.Operations.ContourOperation", f"{mode}: operation type")
        check(snapshot.get("dirty") is False, f"{mode}: dirty toolpath")
        for key in ("depth_mm", "feed_mm_min", "spindle_rpm"):
            near(snapshot.get(key), request[key], f"{mode}: {key}")
        for key, expected in (("top_stock_mm", 0), ("clearance_mm", 10), ("retract_mm", 5), ("feed_plane_mm", 2)):
            near(snapshot.get(key), expected, f"{mode}: {key}")
        check(snapshot.get("depth_incremental") is False and snapshot.get("lead_enabled") is False, f"{mode}: linking mode")
        check(snapshot.get("comp_type") == "CutterCompComputer" and snapshot.get("comp_direction") == "CutterCompRight", f"{mode}: compensation")
        tool = snapshot.get("tool", {})
        check(tool.get("type") == "Mastercam.Tools.EndMillFlatTool" and tool.get("metric") is True, f"{mode}: tool type/units")
        near(tool.get("diameter_mm"), request["tool_diameter_mm"], f"{mode}: bound tool diameter")
        for key, expected in (("number", 1), ("length_offset", 1), ("diameter_offset", 1), ("length_mm", 50), ("flute_length_mm", 20)):
            near(tool.get(key), expected, f"{mode}: tool {key}")
        chain = snapshot.get("chain", {})
        check(chain.get("count") == 1 and chain.get("curves_count") == 4 and chain.get("closed") is True and chain.get("flat") is True, f"{mode}: closed chain")
        check(chain.get("direction") == "CounterClockwise", f"{mode}: chain direction")
        near(abs(chain.get("area_mm2", float("nan"))), request["width_mm"] * request["height_mm"], f"{mode}: chain area")
        near(chain.get("perimeter_mm"), 2 * (request["width_mm"] + request["height_mm"]), f"{mode}: chain perimeter")
        expected_edges = []
        corners = [(0, 0, 0), (request["width_mm"], 0, 0), (request["width_mm"], request["height_mm"], 0), (0, request["height_mm"], 0)]
        for a, b in zip(corners, corners[1:] + corners[:1]):
            expected_edges.append((a, b))
        def point_matches(a, b):
            return len(a) == len(b) == 3 and all(math.isfinite(x) and abs(x-y) <= 1e-7 for x, y in zip(a, b))
        remaining = list(expected_edges)
        for curve in chain.get("curves", []):
            a, b = curve["start"], curve["end"]
            matches = [edge for edge in remaining if
                       (point_matches(a, edge[0]) and point_matches(b, edge[1])) or
                       (point_matches(a, edge[1]) and point_matches(b, edge[0]))]
            check(len(matches) == 1 and curve.get("type") == "Mastercam.Curves.LineGeometry", f"{mode}: bound line endpoints")
            if len(matches) == 1:
                remaining.remove(matches[0])
        check(not remaining and len(chain.get("curves", [])) == 4, f"{mode}: bound geometry endpoints")
        path = snapshot.get("path", {})
        check(path.get("data_valid") is True and path.get("travel_valid") is True, f"{mode}: native NCI extents invalid")
        seconds = path.get("cycle_time_seconds", 0)
        check(isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds > 0, f"{mode}: empty path time")
        near(path.get("z_min_mm"), request["depth_mm"], f"{mode}: path depth")
        # GetMaxAndMinZ and OperationExtentsData expose different Z summaries
        # on Mastercam 2026. Preserve both; validate full travel using WorldMax.
        z_max = path.get("z_max_mm", float("nan"))
        check(isinstance(z_max, (int, float)) and math.isfinite(z_max)
              and request["depth_mm"] <= z_max <= 10, f"{mode}: NCI Z summary")
        low, high = path.get("world_min", []), path.get("world_max", [])
        check(len(low) == len(high) == 3 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in low + high), f"{mode}: path bounds finite")
        if len(low) == len(high) == 3:
            radius = request["tool_diameter_mm"] / 2
            for i, expected in enumerate((-radius, -radius, request["depth_mm"])):
                near(low[i], expected, f"{mode}: path minimum axis {i}")
            for i, expected in enumerate((request["width_mm"] + radius, request["height_mm"] + radius, 10)):
                near(high[i], expected, f"{mode}: path maximum axis {i}")
    check(before.get("pid") != after.get("pid"), "reopen must use a fresh process")
    check(before.get("api_version") == after.get("api_version") and before.get("host_version") == after.get("host_version")
          and before.get("api_sha256") == after.get("api_sha256"), "host/API changed")
    check(before.get("machine_sha256") == after.get("machine_sha256"), "machine definition changed")
    check(Path(after.get("current_file", "")).resolve() == directory / "contour.mcam", "reopen current document identity")
    check(before.get("snapshot") == after.get("snapshot"), "native parameters/geometry/path summary changed on reopen")
    model = Path(request["model_path"])
    check(model.resolve() == directory / "contour.mcam", "unexpected model path")
    model_hash = digest(model) if model.is_file() else None
    check(model_hash is not None and before.get("model_sha256") == after.get("model_sha256") == model_hash, "saved/reopened file hash mismatch")
    result = {"schema_version": "aicnc.mastercam-contour-smoke-verification/0.1", "run_id": request["run_id"],
            "passed": not errors, "errors": errors, "model_sha256": model_hash,
            "verifier_sha256": digest(Path(__file__)),
            "scope": "one synthetic contour; native NCI bounds/time, not full motion or material verification",
            "production_released": False, "postprocessing_performed": False}
    validate_contract(result, "verification")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = prepare(args.directory) if args.action == "prepare" else verify(args.directory)
    if args.action == "verify":
        write_new(args.directory / "verification.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
