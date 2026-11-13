"""GiftStream — silnik reguł (preset engine).

Przepływ: TikTokEvent -> dopasowanie reguł presetów -> GameAction -> gra.
Obsługuje: cooldowny, streaki prezentów, progi lajków, paid interrupts.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from . import presets as store
from .gifts import coin_price_for_gift
from .models import GameAction, Preset, Rule, TikTokEvent

OnAction = Callable[[GameAction], Awaitable[None]]


class Engine:
    def __init__(self, on_action: OnAction | None = None):
        self.on_action = on_action
        self.active_preset: Preset | None = None
        self._cooldowns: dict[str, float] = {}   # rule_id -> ts ostatniego odpalenia
        self._like_accum: dict[str, int] = {}    # rule_id -> nagromadzone lajki
        self.stats = {"events": 0, "actions": 0, "cooldown_skips": 0}

    def reset_stats(self) -> None:
        self.stats = {"events": 0, "actions": 0, "cooldown_skips": 0}
        self._cooldowns.clear()
        self._like_accum.clear()

    # -- preset ------------------------------------------------------------
    def load_preset(self, preset_id: str) -> Preset | None:
        self.active_preset = store.get_preset(preset_id)
        self._cooldowns.clear()
        self._like_accum.clear()
        return self.active_preset

    # -- dopasowanie ---------------------------------------------------------
    def _matches(self, rule: Rule, ev: TikTokEvent) -> bool:
        t = rule.trigger
        if t.type != ev.type:
            return False
        if t.type == "gift":
            if t.gift_name and (ev.gift_name or "").lower() != t.gift_name.lower():
                return False
            if t.gift_id is not None and ev.gift_id != t.gift_id:
                return False
            if t.min_diamonds is not None and ev.diamonds < t.min_diamonds:
                return False
            if t.min_coins is not None or t.max_coins is not None:
                coins, estimated = ev.gift_coins, ev.gift_coins_estimated
                if coins <= 0 or estimated:
                    coins, estimated = coin_price_for_gift(ev.gift_id, ev.gift_name)
                # Coin tiers require explicit TikTok coin prices; never treat diamonds or
                # an estimated catalog value as a viewer purchase price.
                if estimated or coins <= 0:
                    return False
                if t.min_coins is not None and coins < t.min_coins:
                    return False
                if t.max_coins is not None and coins > t.max_coins:
                    return False
            # Streaki: akcję odpalamy dopiero na końcu streaka (repeat_end),
            # chyba że prezent nie jest streakowalny (repeat_count == 1).
            if not ev.repeat_end and ev.repeat_count > 1:
                return False
            return True
        if t.type == "like":
            return True  # progi obsługuje _like_threshold_hit
        if t.type == "comment":
            if t.keyword:
                return t.keyword.lower() in (ev.comment or "").lower()
            return True
        return True  # follow / join / share / subscribe — bez warunków

    def _like_threshold_hit(self, rule: Rule, ev: TikTokEvent) -> bool:
        threshold = rule.trigger.like_threshold or 100
        acc = self._like_accum.get(rule.id, 0) + (ev.like_count or 1)
        if acc >= threshold:
            self._like_accum[rule.id] = acc - threshold
            return True
        self._like_accum[rule.id] = acc
        return False

    # -- główna metoda -------------------------------------------------------
    async def handle(self, ev: TikTokEvent) -> list[GameAction]:
        self.stats["events"] += 1
        actions: list[GameAction] = []
        preset = self.active_preset
        if preset is None:
            return actions

        for rule in preset.rules:
            if not rule.enabled:
                continue
            if not self._matches(rule, ev):
                continue
            if rule.trigger.type == "like" and not self._like_threshold_hit(rule, ev):
                continue

            # Cooldown
            if rule.cooldown_sec > 0:
                last = self._cooldowns.get(rule.id, 0.0)
                if time.time() - last < rule.cooldown_sec:
                    self.stats["cooldown_skips"] += 1
                    continue

            self._cooldowns[rule.id] = time.time()
            ga = GameAction(
                action=rule.action.type,
                params={**rule.action.params,
                        "interrupt": rule.interrupt,
                        "alert_text": rule.alert_text or rule.name,
                        "sound": rule.sound},
                triggered_by=ev,
                rule_name=rule.name,
                ts=time.time(),
            )
            actions.append(ga)
            self.stats["actions"] += 1
            if self.on_action:
                await self.on_action(ga)
        return actions

    # -- testowanie ----------------------------------------------------------
    async def test_rule(self, rule_id: str, ev: TikTokEvent | None = None) -> GameAction | None:
        """Odpala pojedynczą regułę (przycisk 'Test' w dashboardzie)."""
        preset = self.active_preset
        if preset is None:
            return None
        rule = next((r for r in preset.rules if r.id == rule_id), None)
        if rule is None:
            return None
        ev = ev or TikTokEvent(type="gift", gift_name=rule.trigger.gift_name or "Test",
                               diamonds=rule.trigger.min_diamonds or 1, source="test")
        ga = GameAction(action=rule.action.type,
                        params={**rule.action.params, "interrupt": rule.interrupt,
                                "alert_text": rule.alert_text or rule.name, "sound": rule.sound},
                        triggered_by=ev, rule_name=rule.name, ts=time.time())
        self.stats["actions"] += 1
        if self.on_action:
            await self.on_action(ga)
        return ga
