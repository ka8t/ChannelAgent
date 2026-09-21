"""Spec for scripts/dev/mutation_check.py: #86 (summary) and #87 (exact token counts)."""

TESTS = ["tests/test_summary_tokenizer.py", "tests/test_history_window.py"]
G = "app/graph.py"
MUTATIONS = {
    "M1 summary every turn (no batching)": (G, "SUMMARY_BATCH = 6", "SUMMARY_BATCH = 1"),
    "M2 summary never made": (G, "if dropped > covers and dropped - covers >= SUMMARY_BATCH:", "if False:"),
    "M3 summary not sent": (G, "            sent = [SystemMessage(content=SUMMARY_HEADER + summary), *window]", "            sent = window"),
    "M4 summary not checkpointed": (G, "                update = {\"summary\": summary, \"summary_covers\": covers}", "                update = {}"),
    "M5 previous summary not folded in": (G, "    text = (f\"Earlier summary: {previous}\\n\\n\" if previous else \"\") + transcript", "    text = transcript"),
    "M6 already summarized messages summarized again": (G, "messages[covers:dropped]", "messages[:dropped]"),
    "M7 summary failure raises": (G, "    except Exception:\n        logger.warning(\n            \"Summarizing", "    except ZeroDivisionError:\n        logger.warning(\n            \"Summarizing"),
    "M8 summary size not counted in the budget": (G, "return counter([SystemMessage(content=SUMMARY_HEADER + summary)]) if summary else 0", "return 0"),
    "M9 tokenizer never used": (G, "        counter = await _exact_counter(client, messages)", "        counter = count_tokens_approximately"),
    "M10 tokenizer failure raises": (G, "    except Exception:\n        _tokenizer_down_until", "    except ZeroDivisionError:\n        _tokenizer_down_until"),
    "M11 no backoff for a server without tokenizer": (G, "        _tokenizer_down_until = time.monotonic() + _TOKENIZER_RETRY_SECONDS\n", ""),
    "M12 token cache not used": (G, "            if key is not None and key in _token_cache:", "            if False:"),
    "M13 per-message overhead dropped": (G, "MESSAGE_OVERHEAD_TOKENS = 4", "MESSAGE_OVERHEAD_TOKENS = 0"),
}
