"""Spec for scripts/dev/mutation_check.py: #90 (a running but stuck adapter turns the container unhealthy)."""

TESTS = ["tests/test_health.py", "tests/test_telegram_adapter.py"]
H, E, T = "app/health.py", "app/channels/email.py", "app/channels/telegram.py"
MUTATIONS = {
    "M1 heartbeat ignores stale components": (H, "        if stale:\n            logger.warning(", "        if False:\n            logger.warning("),
    "M2 mark never updates": (H, "        _components[name][1] = time.monotonic()", "        pass"),
    "M3 stale as soon as registered": (H, "_components[name] = [max_age, time.monotonic()]", "_components[name] = [max_age, 0.0]"),
    "M4 stale check off by a factor": (H, "if now - last > max_age)", "if now - last > max_age * 1000)"),
    "M5 email marks even after a failed poll": (E, "                await _poll_once()\n                health.mark(\"email\")\n            except Exception:\n                logger.exception(\"Email poll failed\")", "                await _poll_once()\n            except Exception:\n                logger.exception(\"Email poll failed\")\n            health.mark(\"email\")"),
    "M6 email never marks": (E, "                health.mark(\"email\")\n", ""),
    "M7 email not unregistered": (E, "        health.unregister(\"email\")", "        pass"),
    "M8 telegram marks without getMe": (T, "            await bot.get_me()\n            health.mark(\"telegram\")", "            health.mark(\"telegram\")\n            await bot.get_me()"),
    "M9 telegram loop not started": (T, "        liveness = asyncio.create_task(_liveness_loop(application.bot))", "        liveness = asyncio.create_task(asyncio.sleep(0))"),
}
