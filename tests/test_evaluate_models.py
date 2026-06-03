from pathlib import Path
from unittest import TestCase

from scripts.evaluate_models import (
    DEFAULT_MODELS,
    CalendarCase,
    EvalResult,
    PromptVariant,
    filter_prompts,
    load_cases,
    load_prompts,
    normalize_calendar_datetime,
    parse_calendar_link,
    parse_models,
    parse_prompt_ids,
    render_prompt,
    score_case,
    write_summary,
)


class CalendarParsingTests(TestCase):
    def test_parse_calendar_template_link(self) -> None:
        parsed = parse_calendar_link(
            "https://calendar.google.com/calendar/render?action=TEMPLATE&"
            "text=%D1%83%D0%B6%D0%B8%D0%BD&"
            "dates=20260605T193000/20260605T203000&ctz=Europe/Moscow"
        )

        self.assertTrue(parsed.found)
        self.assertEqual(parsed.title, "ужин")
        self.assertEqual(parsed.start, "2026-06-05T19:30:00+03:00")
        self.assertEqual(parsed.end, "2026-06-05T20:30:00+03:00")
        self.assertEqual(parsed.ctz, "Europe/Moscow")

    def test_parse_missing_link(self) -> None:
        parsed = parse_calendar_link("Не вижу события в этом сообщении.")

        self.assertFalse(parsed.found)
        self.assertIsNone(parsed.url)

    def test_rejects_lookalike_google_calendar_host(self) -> None:
        parsed = parse_calendar_link(
            "https://calendar.google.com.evil.example/calendar/render?action=TEMPLATE&"
            "text=%D1%83%D0%B6%D0%B8%D0%BD&"
            "dates=20260605T193000/20260605T203000&ctz=Europe/Moscow"
        )

        self.assertFalse(parsed.found)

    def test_normalizes_utc_calendar_time_to_calendar_timezone(self) -> None:
        normalized = normalize_calendar_datetime("20260605T163000Z", "Europe/Moscow")

        self.assertEqual(normalized, "2026-06-05T19:30:00+03:00")


class CalendarScoringTests(TestCase):
    def test_scores_correct_calendar_link(self) -> None:
        case = CalendarCase(
            id="weekday_relative",
            description="Relative weekday and time",
            input="в пятницу в 19:30 ужин",
            expected_title_terms=["ужин"],
            expected_start="2026-06-05T19:30:00+03:00",
            expected_end="2026-06-05T20:30:00+03:00",
            expected_timezone="Europe/Moscow",
        )

        _, score = score_case(
            case,
            "https://calendar.google.com/calendar/render?action=TEMPLATE&"
            "text=%D1%83%D0%B6%D0%B8%D0%BD&"
            "dates=20260605T193000/20260605T203000&ctz=Europe/Moscow",
        )

        self.assertEqual(score.score, 100.0)

    def test_scores_non_event_without_link(self) -> None:
        case = CalendarCase(
            id="non_event_noise",
            description="Non-event message",
            input="как дела?",
            expected_title_terms=[],
            expected_no_link=True,
        )

        _, score = score_case(case, "Не вижу события, ссылку не создаю.")

        self.assertEqual(score.score, 100.0)

    def test_scores_bad_date_lower(self) -> None:
        case = CalendarCase(
            id="explicit_tomorrow",
            description="Explicit relative day and time",
            input="завтра в 15:00 встреча с Машей",
            expected_title_terms=["встреча", "Машей"],
            expected_start="2026-06-03T15:00:00+03:00",
            expected_end="2026-06-03T16:00:00+03:00",
            expected_timezone="Europe/Moscow",
        )

        _, score = score_case(
            case,
            "https://calendar.google.com/calendar/render?action=TEMPLATE&"
            "text=%D0%B2%D1%81%D1%82%D1%80%D0%B5%D1%87%D0%B0%20"
            "%D1%81%20%D0%9C%D0%B0%D1%88%D0%B5%D0%B9&"
            "dates=20260604T150000/20260604T160000&ctz=Europe/Moscow",
        )

        self.assertLess(score.score, 100.0)
        self.assertIn("start mismatch", " ".join(score.notes))

    def test_load_default_cases(self) -> None:
        cases = load_cases(Path("tests/fixtures/calendar_ru.json"))

        self.assertGreaterEqual(len(cases), 9)
        self.assertTrue(any(case.expected_no_link for case in cases))
        self.assertIn(
            "weekday_abbrev_thursday_spaced_time",
            {case.id for case in cases},
        )

    def test_scores_weekday_abbreviation_and_spaced_time(self) -> None:
        case = CalendarCase(
            id="weekday_abbrev_thursday_spaced_time",
            description="Short weekday abbreviation and spaced time",
            input="чт 20 00 йога",
            expected_title_terms=["йога"],
            expected_start="2026-06-04T20:00:00+03:00",
            expected_end="2026-06-04T21:00:00+03:00",
            expected_timezone="Europe/Moscow",
        )

        _, score = score_case(
            case,
            "https://calendar.google.com/calendar/render?action=TEMPLATE&"
            "text=%D0%B9%D0%BE%D0%B3%D0%B0&"
            "dates=20260604T200000/20260604T210000&ctz=Europe/Moscow",
        )

        self.assertEqual(score.score, 100.0)


class PromptEvaluationTests(TestCase):
    def test_load_prompt_variants(self) -> None:
        prompts = load_prompts(Path("tests/fixtures/prompts_ru.json"))

        self.assertGreaterEqual(len(prompts), 10)
        self.assertIn("combined_best_guess", {prompt.id for prompt in prompts})
        self.assertIn("production_candidate_v2", {prompt.id for prompt in prompts})
        self.assertIn("production_candidate_v3_compact", {prompt.id for prompt in prompts})

    def test_render_prompt_substitutes_now(self) -> None:
        rendered = render_prompt(
            PromptVariant(
                id="sample",
                description="sample",
                instructions="Сейчас {now}",
            ),
            now="03.06.2026 10:00",
        )

        self.assertEqual(rendered, "Сейчас 03.06.2026 10:00")

    def test_default_model_and_prompt_selection(self) -> None:
        prompts = load_prompts(Path("tests/fixtures/prompts_ru.json"))

        self.assertEqual(parse_models(None), DEFAULT_MODELS)
        self.assertEqual(parse_models("gpt-5.4-mini,gpt-5.5"), ["gpt-5.4-mini", "gpt-5.5"])
        self.assertIsNone(parse_prompt_ids(None))
        self.assertEqual(
            [prompt.id for prompt in filter_prompts(prompts, ["baseline"])],
            ["baseline"],
        )

    def test_summary_includes_prompt_ids_and_winner(self) -> None:
        output_dir = Path("/private/tmp/msg_to_event_prompt_summary_test")
        result = EvalResult(
            model="gpt-5.4-mini",
            prompt_id="combined_best_guess",
            case_id="explicit_tomorrow",
            run=1,
            ok=True,
            latency_seconds=1.0,
            estimated_cost_usd=0.001,
            input_tokens=10,
            output_tokens=20,
            score=100.0,
            date_time_score=70.0,
            title_score=15.0,
            url_score=10.0,
            instruction_score=5.0,
            notes=[],
            response_text=(
                "Готово: https://calendar.google.com/calendar/render?"
                "action=TEMPLATE&text=x&dates=20260603T150000/"
                "20260603T160000&ctz=Europe/Moscow"
            ),
            parsed={},
        )

        summary_path = write_summary([result], output_dir)
        summary = summary_path.read_text(encoding="utf-8")

        self.assertIn("gpt-5.4-mini/combined_best_guess", summary)
        self.assertIn("| gpt-5.4-mini | combined_best_guess |", summary)
