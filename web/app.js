"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const money = (value) => Number(value || 0).toLocaleString("zh-CN", {maximumFractionDigits: 0});
const state = {trip: null, trips: [], day: 1, view: "new", thread: null, chatBusy: false, mutation: false};
const fields = {destination: "destination", start_date: "start-date", days: "days", travelers: "travelers", budget: "budget", pace: "pace", transport: "transport", companion: "companion", meal_budget_per_person: "meal-budget"};
const mealNames = {lunch: "午餐", dinner: "晚餐"};
const touchedFields = new Set();
let carriedPreferences = {};
let apiToken = "";
let authPending = null;
let authResolve = null;
let confirmResolve = null;
let map = null;
let mapLayers = null;
let openSequence = 0;

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function safeLink(url, title) {
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol)) return el("span", "", title);
    const link = el("a", "", title);
    link.href = parsed.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  } catch { return el("span", "", title); }
}

function notify(message = "", success = false) {
  $("#notice").textContent = message;
  $("#notice").hidden = !message;
  $("#notice").classList.toggle("success", success);
}

function requestToken() {
  if (!authPending) {
    authPending = new Promise((resolve) => { authResolve = resolve; });
    $("#auth-dialog").showModal();
    $("#token").focus();
  }
  return authPending;
}

async function request(path, options = {}, retried = false) {
  const headers = {...(options.body instanceof FormData ? {} : {"Content-Type": "application/json"}), ...options.headers};
  if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
  let response;
  try { response = await fetch(path, {...options, headers}); }
  catch { throw new Error("暂时无法连接服务，请检查服务是否正在运行。"); }
  if (response.status === 401 && !retried) {
    if (await requestToken()) return request(path, options, true);
    throw new Error("尚未连接，请通过访问设置输入令牌。");
  }
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch { detail = null; }
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item) => item.msg).join("；") : "请求未完成，请稍后重试。";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  if (options.download) return response;
  return response.status === 204 ? {} : response.json();
}

function working(active, title = "正在为你安排下一站", description = "收集目的地信息，整理路线与预算…") {
  state.mutation = active;
  $("#working-overlay").hidden = !active;
  $("#working-title").textContent = title;
  $("#working-description").textContent = description;
  $("#generate").disabled = active;
  $("#revise-submit").disabled = active;
  $("#new-trip").disabled = active;
}

function showView(view, scroll = true) {
  openSequence++;
  state.view = view;
  $$(".view").forEach((section) => { section.hidden = section.id !== `view-${view}`; });
  $$("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === (view === "trip" ? "new" : view)));
  $("#page-name").textContent = {new: "旅行规划", trip: "我的旅程", knowledge: "攻略知识库", chat: "出行对话"}[view];
  renderTripList();
  if (scroll) window.scrollTo({top: 0, behavior: "instant"});
}

function renderTripList() {
  $("#trip-list").replaceChildren();
  $("#trip-count").textContent = state.trips.length;
  if (!state.trips.length) $("#trip-list").append(el("p", "sidebar-empty", "还没有旅程，开始安排下一站吧。"));
  state.trips.forEach((trip) => {
    const button = el("button", "trip-item");
    button.classList.toggle("selected", state.view === "trip" && state.trip?.id === trip.id);
    button.append(el("strong", "", trip.title), el("small", "", `${trip.start_date} · ${trip.days} 天 · ${trip.destination}`));
    button.addEventListener("click", () => { if (!state.mutation) openTrip(trip.id); });
    $("#trip-list").append(button);
  });
}

async function refreshTrips() {
  const data = await request("/trips");
  state.trips = data.trips;
  renderTripList();
}

async function openTrip(id) {
  const sequence = ++openSequence;
  notify();
  try {
    const trip = await request(`/trips/${encodeURIComponent(id)}`);
    if (sequence !== openSequence) return;
    state.day = 1;
    displayTrip(trip);
  } catch (error) { if (sequence === openSequence) notify(error.message); }
}

function dateLabel(value, includeYear = false) {
  if (!value) return "";
  const date = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  if (Number.isNaN(date.valueOf())) return value;
  return date.toLocaleDateString("zh-CN", {year: includeYear ? "numeric" : undefined, month: "long", day: "numeric", weekday: "short"});
}

function hydratePreferences(preferences) {
  for (const [key, id] of Object.entries(fields)) {
    if (preferences[key] !== undefined && preferences[key] !== null) {
      const input = $(`#${id}`);
      if (input.tagName === "SELECT" && ![...input.options].some((option) => option.value === String(preferences[key]))) {
        input.add(new Option(String(preferences[key]), String(preferences[key])));
      }
      input.value = preferences[key];
    }
  }
  if (Array.isArray(preferences.interests)) {
    $$("input[name=interest]").forEach((input) => { input.checked = preferences.interests.includes(input.value); });
  }
  if (Array.isArray(preferences.cuisine_preferences)) $("#cuisine-preferences").value = preferences.cuisine_preferences.join("、");
  if (Array.isArray(preferences.dietary_preferences)) {
    const available = $$("input[name=dietary]").map((input) => input.value);
    preferences.dietary_preferences.filter((value) => !available.includes(value)).forEach((value) => {
      const option = el("label");
      const input = el("input");
      input.type = "checkbox";
      input.name = "dietary";
      input.value = value;
      input.addEventListener("change", () => touchedFields.add("dietary_preferences"));
      option.append(input, el("span", "", value));
      $(".dining-dietary .interest-options").append(option);
    });
    $$("input[name=dietary]").forEach((input) => { input.checked = preferences.dietary_preferences.includes(input.value); });
  }
}

function collectPreferences(message) {
  const preferences = {...carriedPreferences};
  for (const [key, id] of Object.entries(fields)) {
    const value = $(`#${id}`).value.trim();
    if (touchedFields.has(key) || (value && (!message || ["destination", "start_date"].includes(key)))) {
      preferences[key] = value && ["days", "travelers", "budget", "meal_budget_per_person"].includes(key) ? Number(value) : value;
    }
  }
  if (!message || touchedFields.has("interests")) preferences.interests = $$("input[name=interest]:checked").map((input) => input.value);
  if (!message || touchedFields.has("cuisine_preferences")) preferences.cuisine_preferences = [...new Set($("#cuisine-preferences").value.split(/[，,、；;]+/).map((value) => value.trim()).filter(Boolean))].slice(0, 8);
  if (!message || touchedFields.has("dietary_preferences")) preferences.dietary_preferences = $$("input[name=dietary]:checked").map((input) => input.value);
  return preferences;
}

function displayTrip(trip, scroll = true) {
  state.trip = trip;
  const plan = trip.plan;
  const prefs = plan.preferences;
  if (!plan.days.some((day) => day.day === state.day)) state.day = plan.days[0]?.day || 1;
  showView("trip", scroll);
  $("#trip-title").textContent = plan.title;
  $("#trip-summary").textContent = plan.summary;
  $("#trip-meta").textContent = `${prefs.destination} / ${dateLabel(prefs.start_date, true)} 出发`;
  $("#version-label").textContent = `v${trip.version}`;
  $("#trip-stats").replaceChildren();
  const stats = [["旅程天数", `${prefs.days}`, "天"], ["一起出发", `${prefs.travelers}`, "人"], ["预计总费用", `¥${money(plan.budget.total)}`, ""], ["旅行节奏", {relaxed: "轻松慢游", balanced: "刚好尽兴", packed: "充实探索"}[prefs.pace], ""]];
  stats.forEach(([label, value, unit]) => {
    const item = el("div", "stat");
    const number = el("strong", "", value);
    if (unit) number.append(el("small", "", unit));
    item.append(el("span", "", label), number);
    $("#trip-stats").append(item);
  });
  $("#day-tabs").replaceChildren();
  $("#revision-day").replaceChildren(new Option("整个旅程", ""));
  plan.days.forEach((day) => {
    const tab = el("button", "day-tab", `第 ${day.day} 天`);
    tab.type = "button";
    tab.setAttribute("role", "tab");
    tab.dataset.day = day.day;
    tab.addEventListener("click", () => { state.day = day.day; renderDay(); });
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const index = plan.days.findIndex((entry) => entry.day === state.day);
      const target = event.key === "Home" ? 0 : event.key === "End" ? plan.days.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + plan.days.length) % plan.days.length;
      state.day = plan.days[target].day;
      renderDay();
      $(`#day-tabs [data-day="${state.day}"]`).focus();
    });
    $("#day-tabs").append(tab);
    $("#revision-day").append(new Option(`只调整第 ${day.day} 天`, day.day));
  });
  $("#revision-status").textContent = "";
  renderLodging(plan.lodging);
  renderDay();
  renderBudget(plan.budget);
  renderSources($("#plan-sources"), plan.sources);
  $("#source-count").textContent = `${plan.sources.length} 条`;
  $("#workflow-trace").replaceChildren(...plan.trace.map((step) => el("li", "", step)));
}

function renderDay() {
  const day = state.trip.plan.days.find((entry) => entry.day === state.day);
  if (!day) return;
  $$("#day-tabs button").forEach((button) => {
    const selected = Number(button.dataset.day) === state.day;
    button.setAttribute("aria-selected", selected);
    button.tabIndex = selected ? 0 : -1;
  });
  $("#day-date").textContent = `DAY ${String(day.day).padStart(2, "0")} · ${dateLabel(day.date)}`;
  $("#day-title").textContent = day.title;
  $("#day-cost").textContent = `当日约 ¥${money(day.estimated_cost)}`;
  $("#timeline").replaceChildren();
  const entries = [
    ...day.activities.map((activity, index) => ({kind: "activity", item: activity, index})),
    ...(day.meals || []).map((meal) => ({kind: "meal", item: meal})),
  ].sort((a, b) => a.item.start_time.localeCompare(b.item.start_time));
  entries.forEach(({kind, item: activity, index}) => {
    if (kind === "meal") {
      $("#timeline").append(renderMeal(activity, day.day));
      return;
    }
    const item = el("article", "activity");
    const body = el("div", "activity-body");
    body.append(el("div", "activity-time", `${activity.start_time} — ${activity.end_time}`));
    const head = el("div", "activity-head");
    head.append(el("h3", "", activity.name), el("span", "activity-cost", activity.cost_per_person ? `¥${money(activity.cost_per_person)} / 人` : "免费"));
    const tags = el("div", "activity-tags");
    tags.append(el("span", "", activity.indoor ? "室内活动" : "户外探索"), el("span", "", `${activity.duration_minutes} 分钟`), el("span", "", activity.category));
    const source = el("div", "activity-source");
    source.append(el("span", "", "资料 · "), safeLink(activity.source_url, activity.source));
    body.append(head, el("p", "activity-desc", activity.description), tags, source);
    const marker = el("button", "activity-marker", index + 1);
    marker.type = "button";
    marker.setAttribute("aria-label", `在地图上查看${activity.name}`);
    marker.addEventListener("click", () => {
      if (map) { map.setView([activity.lat, activity.lon], 15); $("#map").scrollIntoView({behavior: "smooth", block: "center"}); }
    });
    item.append(marker, body);
    $("#timeline").append(item);
  });
  $("#day-notes").replaceChildren(...day.notes.map((note) => el("p", "", note)));
  $("#day-notes").hidden = !day.notes.length;
  $("#route-distance").textContent = `${Number(day.route.distance_km || 0).toFixed(1)} km · ${day.route.duration_minutes || 0} 分钟`;
  $("#route-source").textContent = day.route.source;
  $("#meal-map-legend").hidden = !day.meals?.length;
  renderMap(day);
}

function restaurantInfo(restaurant, compact = false) {
  const content = el("div", "restaurant-info");
  if (restaurant.recommendation_reason) content.append(el("p", "restaurant-reason", restaurant.recommendation_reason));
  const tags = el("div", "activity-tags restaurant-tags");
  [...(restaurant.cuisines || []), ...(restaurant.dietary_tags || [])].forEach((tag) => tags.append(el("span", "", tag)));
  if (restaurant.rating !== null && restaurant.rating !== undefined) tags.append(el("span", "restaurant-rating", `★ ${Number(restaurant.rating).toFixed(1)}`));
  if (Number.isFinite(restaurant.detour_minutes)) tags.append(el("span", "", `绕行约 ${restaurant.detour_minutes} 分钟`));
  if (tags.childElementCount) content.append(tags);
  if (restaurant.address) content.append(el("p", "restaurant-address", `⌖ ${restaurant.address}`));
  if (restaurant.opening_hours) content.append(el("p", "restaurant-hours", `营业时间 · ${restaurant.opening_hours}`));
  const source = el("div", "activity-source restaurant-source");
  if (restaurant.price_source) source.append(el("span", "", `${restaurant.price_source} · `));
  source.append(safeLink(restaurant.source_url, restaurant.source || "餐饮地点资料"));
  content.append(source);
  content.classList.toggle("compact", compact);
  return content;
}

function focusRestaurant(restaurant) {
  if (!map) return;
  map.setView([restaurant.lat, restaurant.lon], 15);
  $("#map").scrollIntoView({behavior: "smooth", block: "center"});
}

function renderMeal(meal, dayNumber) {
  const restaurant = meal.restaurant;
  const label = mealNames[meal.slot] || "用餐";
  const item = el("article", "activity meal-activity");
  const marker = el("button", "activity-marker meal-marker", "🍴");
  marker.type = "button";
  marker.setAttribute("aria-label", `在地图上查看第${dayNumber}天${label}：${restaurant.name}`);
  marker.addEventListener("click", () => focusRestaurant(restaurant));
  const body = el("div", "activity-body meal-body");
  const time = el("div", "activity-time meal-time", `${meal.start_time} — ${meal.end_time}`);
  time.append(el("span", "meal-slot", label));
  const head = el("div", "activity-head");
  head.append(el("h3", "", restaurant.name), el("span", "activity-cost", `¥${money(restaurant.cost_per_person)} / 人`));
  body.append(time, head, restaurantInfo(restaurant));
  if (meal.notes?.length) {
    const notes = el("div", "meal-notes");
    meal.notes.forEach((note) => notes.append(el("p", "", note)));
    body.append(notes);
  }
  if (meal.alternatives?.length) {
    const alternatives = el("details", "meal-alternatives");
    alternatives.append(el("summary", "", `想换个口味？查看 ${meal.alternatives.length} 个备选`));
    meal.alternatives.forEach((alternative) => {
      const card = el("div", "restaurant-alternative");
      const heading = el("div", "activity-head");
      heading.append(el("strong", "", alternative.name), el("span", "activity-cost", `¥${money(alternative.cost_per_person)} / 人`));
      const choose = el("button", "secondary choose-restaurant", "换成这家 ↗");
      choose.type = "button";
      choose.setAttribute("aria-label", `第${dayNumber}天${label}换成${alternative.name}`);
      choose.addEventListener("click", () => selectMeal(dayNumber, meal.slot, alternative.id));
      card.append(heading, restaurantInfo(alternative, true), choose);
      alternatives.append(card);
    });
    body.append(alternatives);
  }
  item.append(marker, body);
  return item;
}

async function selectMeal(day, slot, restaurantId) {
  if (state.mutation || !state.trip) return;
  const id = state.trip.id;
  notify();
  working(true, "正在安排这一餐", "更新餐厅、交通时间与费用，保存为新的行程版本…");
  try {
    const trip = await request(`/trips/${encodeURIComponent(id)}/meals/select`, {method: "POST", body: JSON.stringify({day, slot, restaurant_id: restaurantId, base_version: state.trip.version})});
    state.day = day;
    displayTrip(trip, false);
    $("#revision-status").textContent = `第 ${day} 天${mealNames[slot]}已更新，当前版本为 v${trip.version}。`;
    await refreshTrips();
  } catch (error) { await conflictRefresh(error, id); }
  finally { working(false); }
}

function renderMap(day) {
  if (!window.L) {
    $("#map").classList.add("map-unavailable");
    $("#map").textContent = "地图资源尚未加载。请联网后刷新页面查看地图。";
    return;
  }
  if (!map) {
    $("#map").replaceChildren();
    $("#map").classList.remove("map-unavailable");
    map = L.map("map", {scrollWheelZoom: false, zoomControl: true});
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
    mapLayers = L.layerGroup().addTo(map);
  }
  mapLayers.clearLayers();
  const points = [];
  day.activities.forEach((activity, index) => {
    const point = [activity.lat, activity.lon];
    points.push(point);
    const popup = el("div");
    popup.append(el("strong", "", activity.name), el("div", "", `${activity.start_time} — ${activity.end_time}`), el("div", "", activity.description));
    const icon = L.divIcon({className: "map-marker", html: String(index + 1), iconSize: [28, 28], iconAnchor: [14, 14]});
    L.marker(point, {icon, title: activity.name}).bindPopup(popup).addTo(mapLayers);
  });
  (day.meals || []).forEach((meal) => {
    const restaurant = meal.restaurant;
    const point = [restaurant.lat, restaurant.lon];
    points.push(point);
    const label = mealNames[meal.slot];
    const popup = el("div");
    popup.append(el("strong", "", `${label} · ${restaurant.name}`), el("div", "", `${meal.start_time} — ${meal.end_time} · ¥${money(restaurant.cost_per_person)} / 人`));
    if (restaurant.address) popup.append(el("div", "", restaurant.address));
    const icon = L.divIcon({className: "map-marker restaurant-marker", html: "🍴", iconSize: [30, 30], iconAnchor: [15, 15]});
    L.marker(point, {icon, title: `${label} · ${restaurant.name}`}).bindPopup(popup).addTo(mapLayers);
  });
  const lodging = state.trip.plan.lodging;
  if (lodging) {
    const point = [lodging.lat, lodging.lon];
    points.push(point);
    const popup = el("div");
    popup.append(el("strong", "", lodging.name), el("div", "", `参考房价 ¥${money(lodging.nightly_rate)} / 间 / 晚`), el("div", "", lodging.source));
    const icon = L.divIcon({className: "map-marker lodging-marker", html: "⌂", iconSize: [30, 30], iconAnchor: [15, 15]});
    L.marker(point, {icon, title: lodging.name}).bindPopup(popup).addTo(mapLayers);
  }
  const route = (day.route.coordinates || []).filter((point) => point.length === 2 && point.every(Number.isFinite)).map(([lon, lat]) => [lat, lon]);
  if (route.length > 1) L.polyline(route, {color: "#688954", weight: 3, opacity: .8, dashArray: /估算|连线|无道路/.test(day.route.source) ? "6 7" : undefined}).addTo(mapLayers);
  requestAnimationFrame(() => {
    map.invalidateSize();
    if (points.length) map.fitBounds(L.latLngBounds(points), {padding: [35, 35], maxZoom: 14, animate: false});
  });
}

function renderLodging(lodging) {
  $("#lodging-card")?.remove();
  if (!lodging) return;
  const card = el("div", "lodging-card");
  card.id = "lodging-card";
  const body = el("div");
  body.append(el("strong", "", lodging.name), el("p", "", `参考房价 ¥${money(lodging.nightly_rate)} / 间 / 晚 · ${lodging.rooms} 间 × ${lodging.nights} 晚`), safeLink(lodging.source_url, lodging.source));
  card.append(el("span", "lodging-symbol", "⌂"), body);
  $(".map-panel").append(card);
}

function renderBudget(budget) {
  const number = el("div", "budget-number");
  number.append(el("small", "", "¥"), document.createTextNode(money(budget.total)));
  const progress = el("div", "budget-progress");
  progress.classList.toggle("over", budget.remaining < 0);
  const bar = el("div");
  bar.style.width = `${budget.limit > 0 ? Math.min(100, budget.total / budget.limit * 100) : 100}%`;
  progress.append(bar);
  $("#budget-total").replaceChildren(number, el("div", "budget-meta", `人均 ¥${money(budget.per_person)} · 总预算 ¥${money(budget.limit)}`), progress, el("div", "budget-left", budget.remaining >= 0 ? `预算余额 ¥${money(budget.remaining)}` : `超出预算 ¥${money(-budget.remaining)}`));
  const names = {tickets: "景点门票", meals: "餐饮费用", lodging: "住宿费用", local_transport: "当地交通", contingency: "机动预算"};
  const colors = ["#789c61", "#d5ae74", "#a3b987", "#86a69a", "#c6c9ab"];
  $("#budget-categories").replaceChildren();
  Object.entries(budget.categories).forEach(([key, value], index) => {
    const row = el("div", "budget-row");
    const swatch = el("span", "swatch");
    swatch.style.background = colors[index % colors.length];
    row.append(swatch, el("span", "", names[key] || key), el("b", "", `¥${money(value)}`));
    $("#budget-categories").append(row);
  });
  $("#budget-advice").replaceChildren(el("h3", "", "让预算花得更合适"));
  budget.warnings.forEach((warning) => $("#budget-advice").append(el("p", "warning", warning)));
  budget.alternatives.forEach((alternative) => $("#budget-advice").append(el("p", "", alternative)));
  if (!budget.warnings.length && !budget.alternatives.length) $("#budget-advice").append(el("p", "", "当前计划在预算之内。可以在调整行程中提出新的预算目标。"));
  renderMealBudget(state.trip.plan);
}

function renderMealBudget(plan) {
  const days = plan.days.filter((day) => day.meals?.length);
  $("#meal-budget-details").hidden = !days.length;
  $("#meal-budget-items").replaceChildren();
  days.forEach((day) => {
    const card = el("section", "meal-budget-day");
    card.append(el("h3", "", `第 ${day.day} 天 · ${dateLabel(day.date)}`));
    const breakfast = el("div", "meal-cost-row");
    breakfast.append(el("span", "", "早餐预留"), el("small", "", `¥${money(day.breakfast_cost_per_person)} × ${plan.preferences.travelers} 人`), el("b", "", `¥${money(day.breakfast_cost_per_person * plan.preferences.travelers)}`));
    card.append(breakfast);
    day.meals.forEach((meal) => {
      const row = el("div", "meal-cost-row");
      row.append(el("span", "", `${mealNames[meal.slot]} · ${meal.restaurant.name}`), el("small", "", `¥${money(meal.restaurant.cost_per_person)} × ${plan.preferences.travelers} 人`), el("b", "", `¥${money(meal.restaurant.cost_per_person * plan.preferences.travelers)}`));
      card.append(row);
    });
    $("#meal-budget-items").append(card);
  });
}

function renderSources(container, sources = []) {
  container.replaceChildren();
  sources.forEach((source, index) => {
    const card = el("div", "source-card");
    card.append(safeLink(source.url, `[${index + 1}] ${source.title}`));
    if (source.excerpt) card.append(el("p", "", source.excerpt));
    container.append(card);
  });
  if (!sources.length) container.append(el("p", "muted", "这份内容还没有关联资料。"));
}

async function conflictRefresh(error, id) {
  if (error.status === 409) {
    try {
      const latest = await request(`/trips/${encodeURIComponent(id)}`);
      if (state.trip?.id === id) displayTrip(latest, false);
      notify("旅程已在其他页面更新，已载入最新版本。你的调整要求仍在输入框内，可再次提交。");
    } catch (refreshError) { notify(refreshError.message); }
  } else notify(error.message);
}

function confirmAction(title, copy) {
  $("#confirm-title").textContent = title;
  $("#confirm-copy").textContent = copy;
  $("#confirm-dialog").showModal();
  return new Promise((resolve) => { confirmResolve = resolve; });
}

async function loadVersions() {
  if (!state.trip) return;
  const id = state.trip.id;
  $("#history-dialog").showModal();
  $("#version-list").replaceChildren(el("p", "muted", "正在读取历史版本…"));
  try {
    const {versions} = await request(`/trips/${encodeURIComponent(id)}/versions`);
    $("#version-list").replaceChildren();
    versions.forEach((version) => {
      const row = el("div", "version-item");
      const body = el("div");
      body.append(el("strong", "", `版本 ${version.version}${version.version === state.trip.version ? " · 当前版本" : ""}`), el("p", "", version.reason), el("small", "", new Date(version.created_at).toLocaleString("zh-CN")));
      const restore = el("button", "secondary", "恢复此版本");
      restore.disabled = version.version === state.trip.version;
      restore.addEventListener("click", async () => {
        if (state.mutation) return;
        $("#history-dialog").close();
        working(true, "正在恢复历史版本", "保留现有历史，并生成一个新的当前版本…");
        try {
          const trip = await request(`/trips/${encodeURIComponent(id)}/restore`, {method: "POST", body: JSON.stringify({version: version.version, base_version: state.trip.version})});
          displayTrip(trip, false);
          notify(`已恢复版本 ${version.version} 的行程，当前版本为 v${trip.version}。`, true);
          await refreshTrips();
        } catch (error) { await conflictRefresh(error, id); }
        finally { working(false); }
      });
      row.append(body, restore);
      $("#version-list").append(row);
    });
  } catch (error) { $("#version-list").replaceChildren(el("p", "muted", error.message)); }
}

async function loadDocuments() {
  const {documents} = await request("/knowledge/documents");
  $("#document-count").textContent = documents.length;
  $("#documents").replaceChildren();
  if (!documents.length) {
    const empty = el("div", "empty-state");
    empty.append(el("span", "", "▧"), el("p", "", "添加第一份攻略，让下一次规划有据可查。"));
    $("#documents").append(empty);
  }
  documents.forEach((doc) => {
    const card = el("article", "document-card panel");
    const remove = el("button", "icon-button", "×");
    remove.setAttribute("aria-label", `删除资料：${doc.title}`);
    remove.addEventListener("click", async () => {
      if (!await confirmAction("删除这份资料？", `“${doc.title}”将从攻略库及检索索引中移除。`)) return;
      remove.disabled = true;
      try { await request(`/knowledge/documents/${encodeURIComponent(doc.id)}`, {method: "DELETE"}); await loadDocuments(); }
      catch (error) { notify(error.message); remove.disabled = false; }
    });
    card.append(el("div", "document-icon", "▧"), remove, el("h3", "", doc.title), el("small", "", `${doc.chunk_count} 个内容片段 · ${dateLabel(doc.created_at)}`));
    if (doc.source_url) card.append(safeLink(doc.source_url, "查看来源 ↗"));
    $("#documents").append(card);
  });
}

function addMessage(role, text, tools = []) {
  const article = el("article", `message ${role}`);
  const body = el("div", "body", text);
  article.append(el("div", "role", role === "user" ? "你" : "TRAVEL ASSISTANT"), body);
  if (tools.length) {
    const trace = el("div", "trace");
    tools.forEach((tool) => trace.append(el("span", "", `${tool.status === "error" ? "!" : "✓"} ${tool.name}`)));
    article.append(trace);
  }
  $("#messages").append(article);
  $("#messages").scrollTop = $("#messages").scrollHeight;
  return body;
}

async function connect() {
  try {
    const health = await request("/health");
    $("#mode").textContent = health.mode === "demo" ? "DEMO · 本地演示" : "LIVE · 实时服务";
    $("#connection").textContent = "出行工作台已连接";
    if (health.warnings?.length) notify(health.warnings.join("\n"));
    await refreshTrips();
  } catch (error) { $("#connection").textContent = "连接未完成"; notify(error.message); }
}

Object.entries(fields).forEach(([key, id]) => {
  $(`#${id}`).addEventListener("input", () => touchedFields.add(key));
  $(`#${id}`).addEventListener("change", () => touchedFields.add(key));
});
$("#companion").addEventListener("change", () => {
  if ($("#companion").value === "独自旅行") {
    $("#travelers").value = "1";
    touchedFields.add("travelers");
  }
});
$$("input[name=interest]").forEach((input) => input.addEventListener("change", () => touchedFields.add("interests")));
$("#cuisine-preferences").addEventListener("input", () => touchedFields.add("cuisine_preferences"));
$$("input[name=dietary]").forEach((input) => input.addEventListener("change", () => touchedFields.add("dietary_preferences")));
$("#plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.mutation) return;
  const message = $("#plan-message").value.trim();
  notify();
  $("#missing-info").hidden = true;
  working(true);
  try {
    const result = await request("/trips", {method: "POST", body: JSON.stringify({message, preferences: collectPreferences(message), explicit_fields: [...touchedFields]})});
    if (result.status === "needs_input") {
      carriedPreferences = result.preferences;
      hydratePreferences(result.preferences);
      $("#plan-message").value = "";
      $("#plan-message").placeholder = "补充一下出行信息，或直接填写下方的目的地和日期…";
      $("#missing-info").textContent = `再补充一点，就可以出发了：\n${result.questions.join("\n")}`;
      $("#missing-info").hidden = false;
      $("#missing-info").scrollIntoView({behavior: "smooth", block: "center"});
    } else {
      state.day = 1;
      displayTrip(result.trip);
      await refreshTrips();
    }
  } catch (error) { notify(error.message); }
  finally { working(false); }
});

$("#new-trip").addEventListener("click", () => {
  if (state.mutation) return;
  carriedPreferences = {};
  touchedFields.clear();
  $("#plan-form").reset();
  $("#plan-message").placeholder = "比如：和朋友去杭州玩三天，喜欢自然风景和美食，预算 3000 元，不想太赶…";
  $("#missing-info").hidden = true;
  notify();
  showView("new");
  $("#destination").focus();
});
$$("[data-view]").forEach((button) => button.addEventListener("click", async () => {
  if (state.mutation) return;
  notify();
  showView(button.dataset.view);
  if (button.dataset.view === "knowledge") {
    try { await loadDocuments(); } catch (error) { notify(error.message); }
  }
}));
$$("[data-example]").forEach((button) => button.addEventListener("click", () => {
  const city = button.dataset.example;
  const ideas = {杭州: "和朋友去杭州玩三天，预算3000元，喜欢自然风光和美食，行程轻松一点。", 北京: "两个人去北京玩三天，预算3000元，想看历史建筑和博物馆。", 成都: "和朋友去成都玩两天，预算2000元，喜欢美食和城市漫步。"};
  $("#destination").value = city;
  $("#plan-message").value = ideas[city];
  $("#days").value = city === "成都" ? "2" : "3";
  $("#budget").value = city === "成都" ? "2000" : "3000";
  $("#travelers").value = "2";
  touchedFields.add("destination");
  $("#start-date").focus();
}));

$("#revise-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("#revision-message").value.trim();
  if (!message || state.mutation || !state.trip) return;
  const id = state.trip.id;
  const selectedDay = $("#revision-day").value;
  notify();
  working(true, "正在调整你的旅程", "重新安排活动、路线与费用，保存为新的行程版本…");
  try {
    const trip = await request(`/trips/${encodeURIComponent(id)}/revise`, {method: "POST", body: JSON.stringify({message, day: selectedDay ? Number(selectedDay) : null, base_version: state.trip.version})});
    if (selectedDay) state.day = Number(selectedDay);
    displayTrip(trip, false);
    $("#revision-message").value = "";
    $("#revision-status").textContent = `已更新为 v${trip.version}，可在版本历史中查看之前的计划。`;
    await refreshTrips();
  } catch (error) { await conflictRefresh(error, id); }
  finally { working(false); }
});
$$("[data-revision]").forEach((button) => button.addEventListener("click", () => {
  $("#revision-message").value = button.dataset.revision;
  $("#revision-day").value = String(state.day);
  $("#revision-message").focus();
}));
$("#history-open").addEventListener("click", loadVersions);
$("#history-dialog .dialog-close").addEventListener("click", () => $("#history-dialog").close());
$("#delete-trip").addEventListener("click", async () => {
  if (state.mutation || !state.trip) return;
  const trip = state.trip;
  if (!await confirmAction("删除这份旅程？", `“${trip.plan.title}”及其历史版本将一起删除。`)) return;
  working(true, "正在删除旅程", "正在更新你的旅行列表…");
  try {
    await request(`/trips/${encodeURIComponent(trip.id)}`, {method: "DELETE"});
    state.trip = null;
    showView("new");
    await refreshTrips();
    notify("旅程已删除。", true);
  } catch (error) { notify(error.message); }
  finally { working(false); }
});
$("#export-trip").addEventListener("click", async () => {
  if (!state.trip) return;
  const trip = state.trip;
  const format = $("#export-format").value;
  $("#export-trip").disabled = true;
  notify();
  try {
    const response = await request(`/trips/${encodeURIComponent(trip.id)}/export?format=${format}`, {download: true});
    const url = URL.createObjectURL(await response.blob());
    const link = el("a");
    link.href = url;
    link.download = `${trip.plan.preferences.destination}-${trip.plan.preferences.start_date}-v${trip.version}.${format}`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    notify(`${format.toUpperCase()} 行程已准备好。`, true);
  } catch (error) { notify(error.message); }
  finally { $("#export-trip").disabled = false; }
});

$("#document-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#document-submit").disabled = true;
  notify();
  try {
    await request("/knowledge/documents", {method: "POST", body: JSON.stringify({title: $("#document-title").value.trim(), content: $("#document-content").value.trim(), source_url: $("#document-url").value.trim()})});
    $("#document-form").reset();
    await loadDocuments();
    notify("资料已加入知识库，可以直接提问或用于下一次行程规划。", true);
  } catch (error) { notify(error.message); }
  finally { $("#document-submit").disabled = false; }
});
$("#document-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  event.target.disabled = true;
  $("#upload-status").textContent = `正在导入 ${file.name}…`;
  const body = new FormData();
  body.append("file", file);
  notify();
  try {
    await request("/knowledge/upload", {method: "POST", body});
    await loadDocuments();
    $("#upload-status").textContent = `已导入 ${file.name}`;
    notify("文件已完成导入并建立检索索引。", true);
  } catch (error) { $("#upload-status").textContent = "导入未完成，可重新选择文件。"; notify(error.message); }
  finally { event.target.disabled = false; event.target.value = ""; }
});
$("#knowledge-ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = $("#knowledge-question").value.trim();
  if (!question) return;
  $("#knowledge-ask-submit").disabled = true;
  $("#knowledge-answer").replaceChildren(el("p", "muted", "正在检索相关资料，整理有来源的回答…"));
  try {
    const result = await request("/knowledge/ask", {method: "POST", body: JSON.stringify({question})});
    const sources = el("div", "source-list");
    renderSources(sources, result.sources);
    const modeLabel = {generated: "知识库检索 · 模型回答", extractive: "知识库检索 · 资料摘要", no_results: "知识库检索 · 暂无匹配"};
    $("#knowledge-answer").replaceChildren(el("div", "answer-mode", modeLabel[result.mode] || "知识库检索"), el("div", "answer-text", result.answer), sources);
  } catch (error) { $("#knowledge-answer").replaceChildren(el("p", "muted", error.message)); }
  finally { $("#knowledge-ask-submit").disabled = false; }
});
$("#refresh-documents").addEventListener("click", async () => {
  try { await loadDocuments(); } catch (error) { notify(error.message); }
});

$("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("#message").value.trim();
  if (!message || state.chatBusy) return;
  state.chatBusy = true;
  $("#send").disabled = true;
  $("#new-chat").disabled = true;
  addMessage("user", message);
  const pending = addMessage("assistant", "正在理解你的需求并查询相关信息…");
  const allowSave = $("#allow-save").checked;
  $("#allow-save").checked = false;
  $("#message").value = "";
  try {
    if (!state.thread) state.thread = (await request("/sessions", {method: "POST"})).thread_id;
    const data = await request("/chat", {method: "POST", body: JSON.stringify({message, thread_id: state.thread, allow_save: allowSave})});
    pending.parentElement.remove();
    addMessage("assistant", data.content, data.tools);
  } catch (error) {
    pending.textContent = error.message;
    if ([404, 502, 504].includes(error.status)) state.thread = null;
    $("#message").value = message;
  } finally {
    state.chatBusy = false;
    $("#send").disabled = false;
    $("#new-chat").disabled = false;
    $("#message").focus();
  }
});
$("#message").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("#chat-form").requestSubmit(); }
});
$$("[data-prompt]").forEach((button) => button.addEventListener("click", () => { $("#message").value = button.dataset.prompt; $("#message").focus(); }));
$("#new-chat").addEventListener("click", async () => {
  if (state.chatBusy) return;
  $("#new-chat").disabled = true;
  try {
    if (state.thread) {
      try { await request(`/sessions/${state.thread}`, {method: "DELETE"}); }
      catch (error) { if (error.status !== 404) throw error; }
    }
    state.thread = null;
    $("#messages").replaceChildren();
    $("#message").value = "";
  } catch (error) { notify(error.message); }
  finally { $("#new-chat").disabled = false; }
});

$("#auth-form").addEventListener("submit", (event) => {
  event.preventDefault();
  apiToken = $("#token").value.trim();
  $("#token").value = "";
  $("#auth-dialog").close();
  const resolve = authResolve;
  authPending = null;
  authResolve = null;
  if (resolve) resolve(true);
});
function cancelAuth() {
  $("#auth-dialog").close();
  const resolve = authResolve;
  authPending = null;
  authResolve = null;
  if (resolve) resolve(false);
}
$("#auth-cancel").addEventListener("click", cancelAuth);
$("#auth-dialog").addEventListener("cancel", (event) => { event.preventDefault(); cancelAuth(); });
$("#access-settings").addEventListener("click", async () => { if (await requestToken()) { notify(); await connect(); } });
$("#confirm-form").addEventListener("submit", (event) => { event.preventDefault(); $("#confirm-dialog").close(); confirmResolve?.(true); confirmResolve = null; });
function cancelConfirm() { $("#confirm-dialog").close(); confirmResolve?.(false); confirmResolve = null; }
$("#confirm-cancel").addEventListener("click", cancelConfirm);
$("#confirm-dialog").addEventListener("cancel", (event) => { event.preventDefault(); cancelConfirm(); });
connect();
