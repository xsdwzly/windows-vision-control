"""Local, pixel-only checkpoint runner. No UIA and no cloud calls.

Observe first, inspect the PNG, then supply window-relative points and tight
single-line OCR regions in a plan. Only use for authorized reversible actions.
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from PIL import ImageGrab
import win_control as control


class VerificationError(RuntimeError):
    pass


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def region_box(region, size):
    if not isinstance(region, list) or len(region) != 4 or any(type(v) is not int for v in region):
        raise ValueError("ROI must be four integer window-relative coordinates")
    x1, y1, x2, y2 = region
    if not (0 <= x1 < x2 <= size[0] and 0 <= y1 < y2 <= size[1]):
        raise ValueError("ROI is outside the observed window")
    return tuple(region)


def normalize(text, mode="text"):
    text = text.strip()
    if mode == "integer":
        # Allow valid thousands grouping, never discard arbitrary punctuation
        # or concatenate multiple OCR lines to manufacture a passing value.
        if not re.fullmatch(r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", text):
            return None
        return text.replace(",", "")
    return text


class LocalOCR:
    def __init__(self):
        from rapidocr import RapidOCR
        # Default OCR expands a short ROI's small side to document scale.
        # Cap the long side instead: screen text is already upright/readable.
        self.engine = RapidOCR(params={
            "Det.limit_type": "max", "Det.limit_side_len": 960,
            "EngineConfig.onnxruntime.intra_op_num_threads": 2,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "Global.log_level": "warning",
        })
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        result = self.engine(image, use_cls=False)
        texts = result.txts
        scores = result.scores
        if texts is None or scores is None:
            return []
        return [(str(t), float(s)) for t, s in zip(texts, scores)]


def check_checkpoint(grab, ocr, expected, mode="text", confidence=0.90,
                     timeout=3.0, interval=0.10):
    target = normalize(expected, mode)
    if target is None or not target:
        raise ValueError("Invalid expected checkpoint text")
    started = time.perf_counter()
    streak = 0
    attempts = 0
    last = []
    previous_pixels = None
    ocr_calls = 0
    while True:
        image = grab()
        pixels = ((image.size, hashlib.sha256(image.tobytes()).digest())
                  if image is not None else None)
        if pixels is None or pixels != previous_pixels:
            last = ocr(image)
            ocr_calls += 1
        previous_pixels = pixels
        attempts += 1
        matches = (len(last) == 1 and last[0][1] >= confidence
                   and normalize(last[0][0], mode) == target)
        streak = streak + 1 if matches else 0
        if streak >= 2:
            return {"text": last[0][0], "confidence": last[0][1],
                    "attempts": attempts, "ocr_calls": ocr_calls,
                    "seconds": time.perf_counter() - started}
        if time.perf_counter() - started >= timeout:
            raise VerificationError(f"Checkpoint mismatch/timeout: expected {expected!r}, observed {last!r}")
        time.sleep(interval)


def validate_plan(plan, observation):
    rect = observation["state"][2]
    size = (rect[2] - rect[0], rect[3] - rect[1])
    segments = plan.get("segments")
    if not isinstance(segments, list) or not 1 <= len(segments) <= 50:
        raise ValueError("Expected 1..50 segments")
    for segment in segments:
        points = segment.get("points", [])
        if not isinstance(points, list) or len(points) > 20:
            raise ValueError("At most 20 clicks between checkpoints")
        for p in points:
            if (not isinstance(p, list) or len(p) != 2 or any(type(v) is not int for v in p)
                    or not (0 <= p[0] < size[0] and 0 <= p[1] < size[1])):
                raise ValueError("Point is outside the observed window")
        region_box(segment["roi"], size)
        if segment.get("mode", "text") not in ("text", "integer"):
            raise ValueError("Unsupported normalization mode")
        expected = segment["expect"]
        if not isinstance(expected, str) or not expected.strip():
            raise ValueError("Each segment needs expected text")
        if normalize(expected, segment.get("mode", "text")) is None:
            raise ValueError("Invalid expected integer")
    return size


def run_plan(plan, observation, output, ocr=None, max_age=120, dry_run=False):
    size = validate_plan(plan, observation)
    if not 0 <= time.time() - observation["captured_at"] <= max_age:
        raise VerificationError("Observation expired; capture and inspect again")
    state = observation["state"]
    state = (state[0], state[1], tuple(state[2]))
    # Do not activate/reposition here: preserve the exact inspected observation.
    control.validate_window(state)
    if dry_run:
        return {"status": "dry-run", "segments": len(plan["segments"]), "ocr_calls": 0}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "segments": [], "clicks": 0}
    started = time.perf_counter()
    try:
        ocr = ocr or LocalOCR()  # Model initialization must finish before any click.
        if not 0 <= time.time() - observation["captured_at"] <= max_age:
            raise VerificationError("Observation expired during OCR startup; observe again")
        from mouse import click
        for index, segment in enumerate(plan["segments"]):
            control.validate_window(state)
            for x, y in segment.get("points", []):
                sx, sy = state[2][0] + x, state[2][1] + y
                control.validate_window(state, sx, sy)
                click(sx, sy)
                report["clicks"] += 1
                time.sleep(0.08)
            box = region_box(segment["roi"], size)

            def grab():
                control.validate_window(state)
                # Check region corners/center for occluding windows as well.
                for x, y in [(box[0], box[1]), (box[2]-1, box[3]-1),
                             ((box[0]+box[2])//2, (box[1]+box[3])//2)]:
                    control.validate_window(state, state[2][0]+x, state[2][1]+y)
                image = ImageGrab.grab(bbox=(state[2][0]+box[0], state[2][1]+box[1],
                                            state[2][0]+box[2], state[2][1]+box[3]))
                control.validate_window(state)
                return image

            result = check_checkpoint(grab, ocr, segment["expect"],
                                      segment.get("mode", "text"))
            report["segments"].append({"index": index, **result})
            print(f"[CHECK {index+1}] {result['text']} ({result['seconds']:.3f}s)", flush=True)
        control.validate_window(state)
        ImageGrab.grab(bbox=state[2]).save(output / "final.png")
        report["status"] = "verified"
        return report
    except (Exception, SystemExit) as error:
        report["status"] = "stopped"
        report["error"] = str(error)
        # Capture current target geometry when possible; never upload failures.
        try:
            import qwen_locate
            current = qwen_locate.get_physical_rect(state[0])
            ImageGrab.grab(bbox=current).save(output / "failure.png")
        except Exception:
            pass
        raise
    finally:
        report["seconds"] = time.perf_counter() - started
        report["ocr_calls"] = getattr(ocr, "calls", None)
        save_json(output / "report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe")
    observe.add_argument("--win", required=True)
    observe.add_argument("--out", required=True)
    run = commands.add_parser("run")
    run.add_argument("--plan", required=True)
    run.add_argument("--observation", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--max-age", type=int, default=120)
    run.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "observe":
        control.activate_window(args.win)
        state = control.window_state(args.win)
        control.validate_window(state)
        output = Path(args.out)
        output.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=state[2]).save(output / "observation.png")
        control.validate_window(state)
        save_json(output / "observation.json", {"state": state, "captured_at": time.time()})
        print(str(output / "observation.png"))
    else:
        report = run_plan(read_json(args.plan), read_json(args.observation), args.out,
                          max_age=args.max_age, dry_run=args.dry_run)
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
