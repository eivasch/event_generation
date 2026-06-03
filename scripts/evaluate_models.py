from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from openai import OpenAI

DEFAULT_MODELS = ["gpt-5.4-mini"]
DEFAULT_CASES_PATH = Path("tests/fixtures/calendar_ru.json")
DEFAULT_PROMPTS_PATH = Path("tests/fixtures/prompts_ru.json")
DEFAULT_OUTPUT_DIR = Path("eval_reports")
FROZEN_NOW = "02.06.2026 12:00"
DEFAULT_RUNS = 3
PASS_THRESHOLD = 80.0
ALLOWED_CALENDAR_HOSTS = {"calendar.google.com", "www.google.com"}

MODEL_PRICES_PER_MILLION_TOKENS = {
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-5.4": {"input": 2.50, "output": 15.00},
    "gpt-5.5": {"input": 5.00, "output": 30.00},
}


@dataclass(frozen=True)
class CalendarCase:
    id: str
    description: str
    input: str
    expected_title_terms: list[str]
    expected_start: str | None = None
    expected_end: str | None = None
    expected_timezone: str | None = None
    expected_no_link: bool = False


@dataclass(frozen=True)
class PromptVariant:
    id: str
    description: str
    instructions: str


@dataclass(frozen=True)
class ParsedCalendarLink:
    found: bool
    url: str | None
    title: str | None
    dates: str | None
    ctz: str | None
    start: str | None
    end: str | None


@dataclass(frozen=True)
class ScoreResult:
    score: float
    date_time_score: float
    title_score: float
    url_score: float
    instruction_score: float
    notes: list[str]


@dataclass(frozen=True)
class EvalResult:
    model: str
    prompt_id: str
    case_id: str
    run: int
    ok: bool
    latency_seconds: float
    estimated_cost_usd: float
    input_tokens: int | None
    output_tokens: int | None
    score: float
    date_time_score: float
    title_score: float
    url_score: float
    instruction_score: float
    notes: list[str]
    response_text: str
    parsed: dict[str, Any]
    error: str | None = None


def build_instructions() -> str:
    return render_prompt(
        PromptVariant(
            id="baseline",
            description="Current bot prompt",
            instructions=(
                "Сейчас я буду присылать сообщения, "
                "а ты из них будешь делать ссылки на гугл календарь, "
                "чтобы я могла автоматически создать там событие. "
                "Таймзона по умолчанию -- Москва. "
                "Ссылки писать текстом, а не гиперссылками. Сейчас {now}"
            ),
        )
    )


def load_cases(path: Path) -> list[CalendarCase]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases: list[CalendarCase] = []
    for raw_case in raw_cases:
        cases.append(
            CalendarCase(
                id=raw_case["id"],
                description=raw_case["description"],
                input=raw_case["input"],
                expected_title_terms=raw_case.get("expected_title_terms", []),
                expected_start=raw_case.get("expected_start"),
                expected_end=raw_case.get("expected_end"),
                expected_timezone=raw_case.get("expected_timezone"),
                expected_no_link=raw_case.get("expected_no_link", False),
            )
        )
    return cases


def load_prompts(path: Path) -> list[PromptVariant]:
    raw_prompts = json.loads(path.read_text(encoding="utf-8"))
    prompts: list[PromptVariant] = []
    for raw_prompt in raw_prompts:
        prompts.append(
            PromptVariant(
                id=raw_prompt["id"],
                description=raw_prompt.get("description", ""),
                instructions=raw_prompt["instructions"],
            )
        )
    return prompts


def filter_prompts(
    prompts: list[PromptVariant],
    prompt_ids: list[str] | None,
) -> list[PromptVariant]:
    if not prompt_ids:
        return prompts

    by_id = {prompt.id: prompt for prompt in prompts}
    missing = [prompt_id for prompt_id in prompt_ids if prompt_id not in by_id]
    if missing:
        raise ValueError(f"Unknown prompt IDs: {', '.join(missing)}")
    return [by_id[prompt_id] for prompt_id in prompt_ids]


def render_prompt(prompt: PromptVariant, now: str = FROZEN_NOW) -> str:
    return prompt.instructions.replace("{now}", now)


def parse_models(value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return DEFAULT_MODELS
    return [model.strip() for model in value.split(",") if model.strip()]


def parse_prompt_ids(value: str | None) -> list[str] | None:
    if value is None or value.strip() == "":
        return None
    return [prompt_id.strip() for prompt_id in value.split(",") if prompt_id.strip()]


def parse_calendar_link(response_text: str) -> ParsedCalendarLink:
    for token in response_text.split():
        normalized = token.strip(".,;()[]<>\"'")
        parsed_url = urlparse(normalized)
        if not _is_allowed_calendar_url(parsed_url):
            continue

        query = parse_qs(parsed_url.query)
        title = _first_query_value(query, "text")
        dates = _first_query_value(query, "dates")
        ctz = _first_query_value(query, "ctz")
        start, end = parse_dates_value(dates, ctz)
        return ParsedCalendarLink(
            found=True,
            url=normalized,
            title=title,
            dates=dates,
            ctz=ctz,
            start=start,
            end=end,
        )

    return ParsedCalendarLink(
        found=False,
        url=None,
        title=None,
        dates=None,
        ctz=None,
        start=None,
        end=None,
    )


def parse_dates_value(
    dates: str | None,
    ctz: str | None = "Europe/Moscow",
) -> tuple[str | None, str | None]:
    if dates is None or "/" not in dates:
        return None, None
    start_raw, end_raw = dates.split("/", 1)
    return normalize_calendar_datetime(start_raw, ctz), normalize_calendar_datetime(end_raw, ctz)


def normalize_calendar_datetime(
    value: str,
    ctz: str | None = "Europe/Moscow",
) -> str | None:
    value = unquote(value)
    if len(value) == 8 and value.isdigit():
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"

    target_timezone = _zoneinfo_or_moscow(ctz)
    if value.endswith("Z"):
        compact_utc = value[:-1]
        for date_format in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
            try:
                parsed_utc = datetime.strptime(compact_utc, date_format).replace(tzinfo=UTC)
                return parsed_utc.astimezone(target_timezone).isoformat()
            except ValueError:
                continue

    for date_format in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            parsed = datetime.strptime(value, date_format).replace(tzinfo=target_timezone)
            return parsed.isoformat()
        except ValueError:
            continue
    return None


def score_case(case: CalendarCase, response_text: str) -> tuple[ParsedCalendarLink, ScoreResult]:
    parsed = parse_calendar_link(response_text)
    notes: list[str] = []

    if case.expected_no_link:
        if parsed.found:
            return parsed, ScoreResult(0.0, 0.0, 0.0, 0.0, 0.0, ["unexpected calendar link"])
        return parsed, ScoreResult(100.0, 70.0, 15.0, 10.0, 5.0, ["correctly avoided link"])

    url_score = _score_url(case, parsed, notes)
    title_score = _score_title(case, parsed.title, notes)
    date_time_score = _score_dates(case, parsed, notes)
    instruction_score = _score_instruction_compliance(response_text, parsed, notes)
    score = date_time_score + title_score + url_score + instruction_score

    return parsed, ScoreResult(
        score=round(score, 2),
        date_time_score=round(date_time_score, 2),
        title_score=round(title_score, 2),
        url_score=round(url_score, 2),
        instruction_score=round(instruction_score, 2),
        notes=notes,
    )


def estimate_cost(model: str, usage: Any) -> tuple[float, int | None, int | None]:
    input_tokens = _usage_value(usage, "input_tokens")
    output_tokens = _usage_value(usage, "output_tokens")
    prices = MODEL_PRICES_PER_MILLION_TOKENS.get(model)
    if prices is None or input_tokens is None or output_tokens is None:
        return 0.0, input_tokens, output_tokens
    cost = (input_tokens / 1_000_000 * prices["input"]) + (
        output_tokens / 1_000_000 * prices["output"]
    )
    return cost, input_tokens, output_tokens


def run_evaluation(
    client: OpenAI,
    models: list[str],
    prompts: list[PromptVariant],
    cases: list[CalendarCase],
    runs: int,
    output_dir: Path,
) -> list[EvalResult]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "raw_results.jsonl"
    results: list[EvalResult] = []

    with results_path.open("w", encoding="utf-8") as results_file:
        for model in models:
            for prompt in prompts:
                instructions = render_prompt(prompt)
                for case in cases:
                    for run in range(1, runs + 1):
                        result = evaluate_one(
                            client,
                            model,
                            prompt.id,
                            case,
                            run,
                            instructions,
                        )
                        results.append(result)
                        results_file.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
                        results_file.flush()

    return results


def evaluate_one(
    client: OpenAI,
    model: str,
    prompt_id: str,
    case: CalendarCase,
    run: int,
    instructions: str,
) -> EvalResult:
    started_at = time.perf_counter()
    try:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=case.input,
            max_output_tokens=1024,
        )
        latency_seconds = time.perf_counter() - started_at
        response_text = response.output_text
        parsed, score = score_case(case, response_text)
        estimated_cost, input_tokens, output_tokens = estimate_cost(model, response.usage)
        return EvalResult(
            model=model,
            prompt_id=prompt_id,
            case_id=case.id,
            run=run,
            ok=True,
            latency_seconds=round(latency_seconds, 3),
            estimated_cost_usd=round(estimated_cost, 8),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            score=score.score,
            date_time_score=score.date_time_score,
            title_score=score.title_score,
            url_score=score.url_score,
            instruction_score=score.instruction_score,
            notes=score.notes,
            response_text=response_text,
            parsed=asdict(parsed),
        )
    except Exception as error:
        latency_seconds = time.perf_counter() - started_at
        return EvalResult(
            model=model,
            prompt_id=prompt_id,
            case_id=case.id,
            run=run,
            ok=False,
            latency_seconds=round(latency_seconds, 3),
            estimated_cost_usd=0.0,
            input_tokens=None,
            output_tokens=None,
            score=0.0,
            date_time_score=0.0,
            title_score=0.0,
            url_score=0.0,
            instruction_score=0.0,
            notes=["model call failed"],
            response_text="",
            parsed=asdict(parse_calendar_link("")),
            error=str(error),
        )


def write_summary(results: list[EvalResult], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.md"
    summaries = summarize_results(results)
    winners = choose_winners(summaries)

    lines = [
        "# Model Evaluation Summary",
        "",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"Frozen evaluation time: {FROZEN_NOW} Europe/Moscow",
        "",
        "## Winners",
        "",
    ]
    for label, winner in winners.items():
        lines.append(f"- `{label}`: `{winner}`")
    if not winners:
        lines.append("- No successful model calls; inspect `raw_results.jsonl` errors.")

    lines.extend(
        [
            "",
            "## Model Scores",
            "",
            "| Model | Prompt | Avg score | Pass rate | P50 latency | P95 latency | Est. cost | Best for |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )

    for summary in sorted(summaries, key=lambda item: item["balanced_score"], reverse=True):
        lines.append(
            "| {model} | {prompt_id} | {avg_score:.2f} | {pass_rate:.1f}% | {p50:.3f}s | "
            "{p95:.3f}s | ${cost:.6f} | {best_for} |".format(**summary)
        )

    lines.extend(build_prompt_case_sections(results))
    lines.extend(["", "Raw results: `raw_results.jsonl`", ""])
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def summarize_results(results: list[EvalResult]) -> list[dict[str, Any]]:
    by_group: dict[tuple[str, str], list[EvalResult]] = {}
    for result in results:
        by_group.setdefault((result.model, result.prompt_id), []).append(result)

    max_latency = max((result.latency_seconds for result in results), default=0.0)
    max_cost = max((sum(item.estimated_cost_usd for item in items) for items in by_group.values()), default=0.0)

    summaries: list[dict[str, Any]] = []
    for (model, prompt_id), group_results in by_group.items():
        scores = [result.score for result in group_results]
        latencies = [result.latency_seconds for result in group_results]
        total_cost = sum(result.estimated_cost_usd for result in group_results)
        ok_count = sum(1 for result in group_results if result.ok)
        avg_score = statistics.fmean(scores) if scores else 0.0
        pass_rate = (
            sum(1 for result in group_results if result.score >= PASS_THRESHOLD)
            / len(group_results)
            * 100
            if group_results
            else 0.0
        )
        p50 = statistics.median(latencies) if latencies else 0.0
        p95 = percentile(latencies, 95)
        latency_component = _inverse_component(p50, max_latency)
        cost_component = _inverse_component(total_cost, max_cost)
        balanced_score = (avg_score * 0.70) + (latency_component * 0.15) + (cost_component * 0.15)
        summaries.append(
            {
                "model": model,
                "prompt_id": prompt_id,
                "avg_score": avg_score,
                "pass_rate": pass_rate,
                "p50": p50,
                "p95": p95,
                "cost": total_cost,
                "ok_count": ok_count,
                "balanced_score": balanced_score,
                "best_for": "quality" if ok_count > 0 and avg_score >= 90 else "needs review",
            }
        )

    winners = choose_winners(summaries)
    for summary in summaries:
        labels = [
            label
            for label, winner in winners.items()
            if winner == _summary_label(summary)
        ]
        if labels:
            summary["best_for"] = ", ".join(labels)

    return summaries


def choose_winners(summaries: list[dict[str, Any]]) -> dict[str, str]:
    eligible = [summary for summary in summaries if summary["ok_count"] > 0]
    if not eligible:
        return {}
    return {
        "best_overall": _summary_label(max(eligible, key=lambda item: item["balanced_score"])),
        "best_low_cost": _summary_label(min(eligible, key=lambda item: item["cost"])),
        "best_quality": _summary_label(max(eligible, key=lambda item: item["avg_score"])),
    }


def build_prompt_case_sections(results: list[EvalResult]) -> list[str]:
    if not results:
        return []

    lines = ["", "## Worst Cases By Prompt", ""]
    for key, group_results in sorted(_results_by_group(results).items()):
        low_results = sorted(group_results, key=lambda result: result.score)[:3]
        rendered = ", ".join(
            f"`{result.case_id}` run {result.run}: {result.score:.0f}"
            for result in low_results
        )
        lines.append(f"- `{key}`: {rendered}")

    lines.extend(["", "## Examples", ""])
    for key, group_results in sorted(_results_by_group(results).items()):
        best = max(group_results, key=lambda result: result.score)
        worst = min(group_results, key=lambda result: result.score)
        lines.append(
            f"- `{key}` best `{best.case_id}` ({best.score:.0f}): "
            f"{_shorten(best.response_text)}"
        )
        lines.append(
            f"- `{key}` worst `{worst.case_id}` ({worst.score:.0f}): "
            f"{_shorten(worst.response_text)}"
        )
    return lines


def _results_by_group(results: list[EvalResult]) -> dict[str, list[EvalResult]]:
    grouped: dict[str, list[EvalResult]] = {}
    for result in results:
        grouped.setdefault(f"{result.model}/{result.prompt_id}", []).append(result)
    return grouped


def percentile(values: list[float], percentile_value: int) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = round((len(sorted_values) - 1) * percentile_value / 100)
    return sorted_values[index]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate OpenAI models for Russian calendar links.")
    parser.add_argument(
        "--models",
        default=os.getenv("EVAL_MODELS"),
        help="Comma-separated model IDs. Defaults to gpt-5.4-mini.",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=DEFAULT_PROMPTS_PATH,
        help="Path to JSON prompt variants.",
    )
    parser.add_argument(
        "--prompt-ids",
        default=os.getenv("EVAL_PROMPT_IDS"),
        help="Comma-separated prompt IDs. Defaults to all prompts in --prompts.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=int(os.getenv("EVAL_RUNS_PER_CASE", str(DEFAULT_RUNS))),
        help="Runs per case per model.",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to JSON eval cases.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for raw JSONL and Markdown summary.",
    )
    return parser


def main() -> None:
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for live model evaluation.")

    args = build_arg_parser().parse_args()
    models = parse_models(args.models)
    cases = load_cases(args.cases)
    prompts = filter_prompts(load_prompts(args.prompts), parse_prompt_ids(args.prompt_ids))
    client = OpenAI()
    results = run_evaluation(client, models, prompts, cases, args.runs, args.output_dir)
    summary_path = write_summary(results, args.output_dir)
    print(f"Wrote {len(results)} raw results to {args.output_dir / 'raw_results.jsonl'}")
    print(f"Wrote summary to {summary_path}")


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _summary_label(summary: dict[str, Any]) -> str:
    return f"{summary['model']}/{summary['prompt_id']}"


def _is_google_calendar_template(parsed: ParsedCalendarLink) -> bool:
    if parsed.url is None:
        return False
    parsed_url = urlparse(parsed.url)
    query = parse_qs(parsed_url.query)
    return (
        _is_allowed_calendar_url(parsed_url)
        and "/calendar/" in parsed_url.path
        and _first_query_value(query, "action") == "TEMPLATE"
        and parsed.title is not None
        and parsed.dates is not None
    )


def _is_allowed_calendar_url(parsed_url: Any) -> bool:
    return (
        parsed_url.scheme == "https"
        and parsed_url.hostname in ALLOWED_CALENDAR_HOSTS
        and "/calendar/" in parsed_url.path
    )


def _zoneinfo_or_moscow(ctz: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(ctz or "Europe/Moscow")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def _score_url(case: CalendarCase, parsed: ParsedCalendarLink, notes: list[str]) -> float:
    score = 0.0
    if _is_google_calendar_template(parsed):
        score += 5.0
    else:
        notes.append("missing valid Google Calendar template URL")

    if case.expected_timezone is None or parsed.ctz == case.expected_timezone:
        score += 5.0
    else:
        notes.append(
            f"timezone mismatch: expected {case.expected_timezone}, got {parsed.ctz}"
        )

    return score


def _score_title(case: CalendarCase, title: str | None, notes: list[str]) -> float:
    if not case.expected_title_terms:
        return 15.0
    if title is None:
        notes.append("missing title")
        return 0.0
    normalized_title = title.casefold()
    matches = sum(1 for term in case.expected_title_terms if term.casefold() in normalized_title)
    score = 15.0 * matches / len(case.expected_title_terms)
    if score < 15.0:
        notes.append("title does not include all expected terms")
    return score


def _score_dates(case: CalendarCase, parsed: ParsedCalendarLink, notes: list[str]) -> float:
    score = 0.0
    if parsed.start == case.expected_start:
        score += 50.0
    else:
        notes.append(f"start mismatch: expected {case.expected_start}, got {parsed.start}")

    if case.expected_end is None:
        score += 20.0
    elif parsed.end == case.expected_end:
        score += 20.0
    else:
        notes.append(f"end mismatch: expected {case.expected_end}, got {parsed.end}")

    return score


def _score_instruction_compliance(
    response_text: str,
    parsed: ParsedCalendarLink,
    notes: list[str],
) -> float:
    if not parsed.found:
        notes.append("no plain-text URL found")
        return 0.0
    if "<a " in response_text.casefold() or "[" in response_text and "](" in response_text:
        notes.append("response appears to use hyperlink markup")
        return 0.0
    return 5.0


def _usage_value(usage: Any, key: str) -> int | None:
    if usage is None:
        return None
    value = getattr(usage, key, None)
    if isinstance(value, int):
        return value
    if isinstance(usage, dict):
        dict_value = usage.get(key)
        if isinstance(dict_value, int):
            return dict_value
    return None


def _inverse_component(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 100.0
    return max(0.0, 100.0 * (1.0 - value / max_value))


def _shorten(value: str, limit: int = 220) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


if __name__ == "__main__":
    main()
