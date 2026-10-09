"""Meal selection, bounded scheduling and day-local restaurant changes."""

import asyncio

from travel_assistant.models import MealPlan, Preferences, Route


def minutes(value):
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def clock(value):
    return f"{value // 60:02}:{value % 60:02}"


def lunch_index(activities, meals=()):
    lunch = next((meal for meal in meals if meal.slot == "lunch"), None)
    if lunch:
        return next(
            (
                index
                for index, activity in enumerate(activities)
                if minutes(activity.start_time) >= minutes(lunch.end_time)
            ),
            len(activities),
        )
    for index, activity in enumerate(activities):
        if index and minutes(activity.start_time) >= 13 * 60:
            return index
    return max(1, min(2, len(activities)))


class MealPlanningMixin:
    @staticmethod
    def _meal_preferences(preferences, meal=None, changes=None):
        data = preferences.model_dump()
        if meal:
            data.update(
                cuisine_preferences=meal.cuisine_preferences,
                dietary_preferences=meal.dietary_preferences,
                meal_budget_per_person=meal.budget_per_person,
            )
        data.update(changes or {})
        return Preferences.model_validate(data)

    async def _recommend_meal(self, day, preferences, slot, excluded_ids=()):
        split = lunch_index(day.activities, day.meals)
        before = day.activities[split - 1] if slot == "lunch" else day.activities[-1]
        after = (
            day.activities[split]
            if slot == "lunch" and split < len(day.activities)
            else None
        )
        start = "12:00" if slot == "lunch" else "18:00"
        candidates = await self.dining.recommend(
            preferences,
            before,
            after,
            slot=slot,
            excluded_ids=excluded_ids,
            start_time=start,
            date=day.date,
        )
        candidates = list(
            {candidate.id: candidate for candidate in candidates}.values()
        )
        if not candidates:
            raise ValueError("附近没有满足当前口味与预算的餐厅，请调整餐饮条件。")
        return MealPlan(
            slot=slot,
            start_time=start,
            end_time="13:00" if slot == "lunch" else "19:00",
            duration_minutes=60,
            restaurant=candidates[0],
            alternatives=candidates[1:3],
            cuisine_preferences=preferences.cuisine_preferences,
            dietary_preferences=preferences.dietary_preferences,
            budget_per_person=preferences.meal_budget_per_person,
        )

    async def _schedule_meal_day(self, day, preferences, meal_plans):
        """Keep attraction order/identities and insert dining stops into the actual route."""
        meals = {meal.slot: meal.model_copy(deep=True) for meal in meal_plans}
        if set(meals) != {"lunch", "dinner"}:
            raise ValueError("每日餐饮安排需要包含午餐和晚餐。")
        split = lunch_index(day.activities, day.meals)
        events = [
            ("activity", item.model_copy(deep=True)) for item in day.activities[:split]
        ]
        events.append(("lunch", meals["lunch"]))
        events.extend(
            ("activity", item.model_copy(deep=True)) for item in day.activities[split:]
        )
        events.append(("dinner", meals["dinner"]))
        points = [
            item.restaurant if kind != "activity" else item for kind, item in events
        ]
        legs = await asyncio.gather(
            *(
                self._leg(points[i - 1], points[i], preferences)
                for i in range(1, len(points))
            )
        )
        now, previous_kind = 9 * 60, None
        activities, scheduled_meals = [], []
        for index, (kind, item) in enumerate(events):
            if index:
                now += legs[index - 1]["minutes"]
                if previous_kind == "activity":
                    now += 15
            if kind == "activity":
                start, end = now, now + item.duration_minutes
                if end > 18 * 60:
                    raise ValueError(
                        "加入餐厅绕行后景点将超过18:00，请选择更近餐厅或减少当天景点。"
                    )
                item.start_time, item.end_time = clock(start), clock(end)
                activities.append(item)
            else:
                earliest, latest = (
                    (11 * 60 + 30, 14 * 60)
                    if kind == "lunch"
                    else (17 * 60 + 30, 20 * 60 + 30)
                )
                start = max(now, earliest)
                end = start + item.duration_minutes
                if end > latest:
                    label = "午餐" if kind == "lunch" else "晚餐"
                    raise ValueError(
                        f"当前餐厅无法在{label}时间窗内到达并用餐，请选择更近的餐厅。"
                    )
                item.start_time, item.end_time = clock(start), clock(end)
                available = self.dining.is_open(
                    item.restaurant, item.start_time, item.end_time, day.date
                )
                if available is False:
                    raise ValueError(
                        f"{item.restaurant.name} 的营业时段不覆盖这次用餐，请更换备选。"
                    )
                scheduled_meals.append(item)
            now, previous_kind = end, kind
        result = day.model_copy(deep=True)
        result.activities, result.meals = activities, scheduled_meals
        result.route = Route(
            distance_km=round(sum(leg["km"] for leg in legs), 2),
            duration_minutes=sum(leg["minutes"] for leg in legs),
            mode=preferences.transport,
            coordinates=[point for leg in legs for point in leg["coordinates"]],
            source="高德路线规划（含用餐途经点）"
            if all(leg["actual"] for leg in legs)
            else "地点连线 · 距离与时长估算（含用餐途经点）",
        )
        result.estimated_cost = self._day_cost(result, preferences)
        return result

    async def _with_meals(
        self, day, preferences, existing_meals=None, allow_trim=False
    ):
        candidate = day.model_copy(deep=True)
        existing = {
            meal.slot: meal.model_copy(deep=True) for meal in existing_meals or []
        }
        while candidate.activities:
            lunch = existing.get("lunch") or await self._recommend_meal(
                candidate, preferences, "lunch"
            )
            dinner = existing.get("dinner") or await self._recommend_meal(
                candidate, preferences, "dinner", excluded_ids=[lunch.restaurant.id]
            )
            try:
                return await self._schedule_meal_day(
                    candidate, preferences, [lunch, dinner]
                )
            except ValueError as exc:
                if (
                    not allow_trim
                    or len(candidate.activities) <= 1
                    or "营业时段" in str(exc)
                ):
                    raise
                removed = candidate.activities.pop()
                candidate.notes.append(
                    f"为保留用餐和餐厅往返时间，{removed.name} 可作为备选景点。"
                )

    async def _dining_node(self, state):
        days = await asyncio.gather(
            *(
                self._with_meals(day, state["preferences"], allow_trim=True)
                for day in state["days"]
            )
        )
        return {
            "days": days,
            "trace": state["trace"]
            + ["餐饮推荐：筛选午晚餐主选与备选，串联路线并校验用餐时间"],
        }

    @staticmethod
    def _has_meal_change(intent):
        return any(
            [
                intent.replace_meal,
                intent.meal_slot,
                intent.cuisine_preferences is not None,
                intent.dietary_preferences is not None,
                intent.meal_budget_per_person is not None,
            ]
        )

    async def _revise_meals(self, plan, intent, target_day, message):
        slots = [intent.meal_slot] if intent.meal_slot else ["lunch", "dinner"]
        changes = {
            key: getattr(intent, key)
            for key in (
                "cuisine_preferences",
                "dietary_preferences",
                "meal_budget_per_person",
            )
            if getattr(intent, key) is not None
        }
        updated = plan.model_copy(deep=True)
        if target_day is None and intent.meal_slot is None:
            updated.preferences = self._meal_preferences(
                updated.preferences, changes=changes
            )
        for index, original in enumerate(plan.days):
            if target_day is not None and original.day != target_day:
                continue
            local_prefs = updated.preferences.model_copy(
                update={"transport": original.route.mode}
            )
            day = original.model_copy(deep=True)
            if not day.meals:
                day = await self._with_meals(day, local_prefs)
            meals = {meal.slot: meal.model_copy(deep=True) for meal in day.meals}
            for slot in slots:
                current = meals[slot]
                prefs = self._meal_preferences(local_prefs, current, changes)
                excluded = [meal.restaurant.id for meal in meals.values()]
                replacement = await self._recommend_meal(day, prefs, slot, excluded)
                replacement.notes.append("本次调整：" + message[:180])
                meals[slot] = replacement
            revised = await self._schedule_meal_day(
                day, local_prefs, list(meals.values())
            )
            revised.notes.append("餐饮调整：" + message[:180])
            updated.days[index] = revised
        await self._validate({"days": updated.days, "trace": []})
        updated.budget = self._budget(updated.days, updated.preferences)
        updated.trace = [
            "餐饮需求解析：" + message[:120],
            f"影响范围：第 {target_day} 天" if target_day else "影响范围：全行程餐饮",
            "保留景点与未修改的餐厅，更新选定餐次",
            "重算餐厅途经路线、时间及餐饮预算",
        ]
        return updated

    async def select_meal(self, plan, day, slot, restaurant_id):
        if not 1 <= day <= len(plan.days) or slot not in ("lunch", "dinner"):
            raise ValueError("请选择有效的日期及午餐或晚餐。")
        original = plan.days[day - 1]
        current = next((meal for meal in original.meals if meal.slot == slot), None)
        if current is None:
            raise ValueError("该日期还没有餐饮安排，请先生成餐饮推荐。")
        selected = next(
            (
                restaurant
                for restaurant in current.alternatives
                if restaurant.id == restaurant_id
            ),
            None,
        )
        if selected is None:
            raise ValueError("只能选择当前餐次的备选餐厅，请刷新计划后重试。")
        meal = current.model_copy(deep=True)
        meal.restaurant = selected.model_copy(deep=True)
        meal.alternatives = [current.restaurant.model_copy(deep=True)] + [
            r.model_copy(deep=True)
            for r in current.alternatives
            if r.id != restaurant_id
        ]
        prefs = plan.preferences.model_copy(update={"transport": original.route.mode})
        revised = await self._schedule_meal_day(
            original, prefs, [meal if m.slot == slot else m for m in original.meals]
        )
        updated = plan.model_copy(deep=True)
        updated.days[day - 1] = revised
        await self._validate({"days": updated.days, "trace": []})
        updated.budget = self._budget(updated.days, updated.preferences)
        updated.trace = [
            f"替换第 {day} 天{'午餐' if slot == 'lunch' else '晚餐'}：{selected.name}",
            "保留其他日期与景点，重算当天餐饮途经路线和费用",
        ]
        return updated
