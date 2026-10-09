"""Shared structured travel planning contracts."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TravelModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class Preferences(TravelModel):
    destination: str = Field(min_length=1, max_length=80)
    start_date: date
    days: int = Field(default=3, ge=1, le=7)
    travelers: int = Field(default=2, ge=1, le=10)
    budget: float = Field(default=3000, ge=0, le=1000000)
    interests: list[str] = Field(
        default_factory=lambda: ["自然", "人文"], max_length=12
    )
    pace: Literal["relaxed", "balanced", "packed"] = "balanced"
    transport: Literal["walking", "transit", "driving"] = "transit"
    companion: str = Field(default="朋友", max_length=80)
    notes: str = Field(default="", max_length=3000)
    cuisine_preferences: list[str] = Field(default_factory=list, max_length=8)
    dietary_preferences: list[str] = Field(default_factory=list, max_length=8)
    meal_budget_per_person: float = Field(default=60, ge=10, le=10000)


class Source(BaseModel):
    id: str
    title: str
    excerpt: str = ""
    url: str = ""


class Activity(TravelModel):
    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    start_time: str
    end_time: str
    duration_minutes: int = Field(ge=15, le=480)
    cost_per_person: float = Field(ge=0)
    category: str
    indoor: bool
    description: str
    source: str = "目的地资料"
    source_url: str = ""


class Route(TravelModel):
    distance_km: float = 0
    duration_minutes: int = 0
    mode: str = "transit"
    coordinates: list[list[float]] = Field(default_factory=list)
    source: str = "地点连线与距离估算"


class Restaurant(TravelModel):
    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    address: str = ""
    cuisines: list[str] = Field(default_factory=list)
    dietary_tags: list[str] = Field(default_factory=list)
    cost_per_person: float = Field(ge=0)
    price_source: str = "餐费估算"
    rating: float | None = Field(default=None, ge=0, le=5)
    opening_hours: str = ""
    recommendation_reason: str = ""
    detour_minutes: int = Field(default=0, ge=0)
    source: str = "餐饮地点资料"
    source_url: str = ""


class MealPlan(TravelModel):
    slot: Literal["lunch", "dinner"]
    start_time: str
    end_time: str
    duration_minutes: int = Field(default=60, ge=15, le=180)
    restaurant: Restaurant
    alternatives: list[Restaurant] = Field(default_factory=list, max_length=2)
    cuisine_preferences: list[str] = Field(default_factory=list)
    dietary_preferences: list[str] = Field(default_factory=list)
    budget_per_person: float = Field(default=60, ge=10, le=10000)
    notes: list[str] = Field(default_factory=list)


class DayPlan(BaseModel):
    day: int
    date: date
    title: str
    activities: list[Activity]
    route: Route = Field(default_factory=Route)
    estimated_cost: float = 0
    notes: list[str] = Field(default_factory=list)
    meals: list[MealPlan] = Field(default_factory=list)
    breakfast_cost_per_person: float = Field(default=15, ge=0)


class Budget(TravelModel):
    currency: str = "CNY"
    total: float
    per_person: float
    limit: float
    remaining: float
    categories: dict[str, float]
    warnings: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)


class Lodging(TravelModel):
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    nightly_rate: float = Field(ge=0)
    rooms: int = Field(ge=1)
    nights: int = Field(ge=1)
    source: str
    source_url: str = ""


class Plan(BaseModel):
    title: str
    summary: str
    preferences: Preferences
    days: list[DayPlan]
    budget: Budget
    lodging: Lodging | None = None
    sources: list[Source] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    preferences: dict = Field(default_factory=dict)
    explicit_fields: list[str] = Field(default_factory=list, max_length=16)


class ReviseRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    day: int | None = Field(default=None, ge=1, le=7)
    base_version: int = Field(ge=1)


class RestoreRequest(BaseModel):
    version: int = Field(ge=1)
    base_version: int = Field(ge=1)


class MealSelectionRequest(BaseModel):
    day: int = Field(ge=1, le=7)
    slot: Literal["lunch", "dinner"]
    restaurant_id: str = Field(min_length=1, max_length=180)
    base_version: int = Field(ge=1)


class DocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=20, max_length=200000)
    source_url: str = Field(default="", max_length=1000)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
