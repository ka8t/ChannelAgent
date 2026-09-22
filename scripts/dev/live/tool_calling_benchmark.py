"""#115's benchmark (docs/MCP_EXTENSION.md section 6): against a real llama-server
without --skip-chat-parsing, N scripted tasks each with one clearly correct tool
among T exposed tools, reporting tool-selection accuracy and argument-validity
rate for T = 1, 5, 10, 20.

Usage: .venv/bin/python scripts/dev/live/tool_calling_benchmark.py [base_url]
(default base_url: http://127.0.0.1:8091, a temporary instance without the flag —
never point this at the live engine while it still has --skip-chat-parsing, since
every call would then "fail" the benchmark for a reason unrelated to tool choice).
"""

import json
import sys
import urllib.request

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8091"

# name -> (description, {required arg: python type})
TOOLS = {
    "get_time": ("Get the current time in a timezone.", {"timezone": str}),
    "get_weather": ("Get the current weather in a city.", {"city": str}),
    "calculator": ("Evaluate an arithmetic expression.", {"expression": str}),
    "translate": ("Translate text into a target language.", {"text": str, "target_language": str}),
    "search_web": ("Search the web for a query.", {"query": str}),
    "convert_currency": ("Convert an amount from one currency to another.",
                          {"amount": (int, float), "from_currency": str, "to_currency": str}),
    "set_reminder": ("Set a reminder for a time.", {"text": str, "when": str}),
    "lookup_word": ("Look up the definition of a word.", {"word": str}),
    "roll_dice": ("Roll a die with a number of sides.", {"sides": int}),
    "create_calendar_event": ("Create a calendar event.", {"title": str, "date": str}),
    "get_stock_price": ("Get the current price of a stock ticker.", {"ticker": str}),
    "send_email": ("Send an email.", {"to": str, "subject": str, "body": str}),
    # Pure decoys: never the right answer for any task below, only padding for T.
    "list_files": ("List files in a directory.", {"path": str}),
    "play_music": ("Play a song.", {"title": str}),
    "book_flight": ("Book a flight.", {"origin": str, "destination": str}),
    "order_pizza": ("Order a pizza.", {"toppings": str}),
    "water_plants": ("Water the plants.", {"zone": str}),
    "turn_on_lights": ("Turn on the lights.", {"room": str}),
    "lock_door": ("Lock a door.", {"door": str}),
    "start_timer": ("Start a countdown timer.", {"seconds": int}),
}

TASKS = [
    ("What time is it in Tokyo right now?", "get_time"),
    ("What's the weather like in Berlin today?", "get_weather"),
    ("What is 47 times 89?", "calculator"),
    ("Translate 'good morning' into Spanish.", "translate"),
    ("Search the web for the tallest mountain in Europe.", "search_web"),
    ("Convert 100 US dollars to euros.", "convert_currency"),
    ("Remind me to call my dentist tomorrow at 9am.", "set_reminder"),
    ("What does the word 'ephemeral' mean?", "lookup_word"),
    ("Roll a 20-sided die.", "roll_dice"),
    ("Create a calendar event for a team meeting on 2026-10-01.", "create_calendar_event"),
    ("What's the current stock price of Apple?", "get_stock_price"),
    ("Send an email to sam@example.com with subject Hello and body See you soon.", "send_email"),
]


def _schema(name: str) -> dict:
    description, args = TOOLS[name]
    props = {}
    for arg, kind in args.items():
        json_type = "number" if kind in (int, float, (int, float)) else "string"
        props[arg] = {"type": json_type}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": props, "required": list(args)},
        },
    }


def _valid_arguments(name: str, raw_arguments: str) -> bool:
    try:
        parsed = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(parsed, dict):
        return False
    _description, args = TOOLS[name]
    for arg, kind in args.items():
        if arg not in parsed or not isinstance(parsed[arg], kind):
            return False
    return True


def _ask(prompt: str, exposed_tools: list[str]) -> dict:
    body = json.dumps(
        {
            "messages": [{"role": "user", "content": prompt}],
            "tools": [_schema(t) for t in exposed_tools],
            "temperature": 0,
            "max_tokens": 200,
        }
    ).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _exposed_for(correct: str, t: int) -> list[str]:
    decoy_pool = [name for name in TOOLS if name != correct]
    return [correct, *decoy_pool[: t - 1]]


def main() -> None:
    print(f"Benchmarking {BASE_URL} — {len(TASKS)} tasks, T in (1, 5, 10, 20)\n")
    rows = []
    for t in (1, 5, 10, 20):
        correct_count = 0
        valid_args_count = 0
        called_count = 0
        for prompt, correct_tool in TASKS:
            exposed = _exposed_for(correct_tool, t)
            response = _ask(prompt, exposed)
            message = response["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            if not calls:
                continue
            called_count += 1
            call = calls[0]
            name = call["function"]["name"]
            arguments = call["function"]["arguments"]
            if name == correct_tool:
                correct_count += 1
                if _valid_arguments(name, arguments):
                    valid_args_count += 1
        accuracy = correct_count / len(TASKS)
        arg_validity = valid_args_count / correct_count if correct_count else 0.0
        rows.append((t, called_count, correct_count, accuracy, valid_args_count, arg_validity))
        print(
            f"T={t:>2}  called_a_tool={called_count}/{len(TASKS)}  "
            f"correct_tool={correct_count}/{len(TASKS)} ({accuracy:.0%})  "
            f"valid_arguments={valid_args_count}/{correct_count if correct_count else 0} "
            f"({arg_validity:.0%})"
        )
    print("\n| T | tool-selection accuracy | argument-validity rate |")
    print("|---|---|---|")
    for t, _called, _correct, accuracy, _valid, arg_validity in rows:
        print(f"| {t} | {accuracy:.0%} | {arg_validity:.0%} |")


if __name__ == "__main__":
    main()
