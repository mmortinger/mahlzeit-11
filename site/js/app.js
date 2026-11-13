/* MAhlzeit 11 – Vanilla JS, kein Build-Step. Lädt data/menu.json und rendert Tageskarten. */
(() => {
  "use strict";

  const TZ = "Europe/Vienna";
  const ORDER_KEY = "mahlzeit11.order";
  const COMPACT_KEY = "mahlzeit11.compact";
  const WD_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
  const WD_LONG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
  // Beschriftungen ohne Informationswert ("Menü 1", "Gericht 3") werden nicht angezeigt
  const GENERIC_LABEL = /^(menü|gericht)\s*\d+$/i;

  const $ = (sel) => document.querySelector(sel);
  const els = {
    tabs: $(".day-tabs"),
    cards: $(".cards"),
    hint: $(".hint"),
    updated: $(".updated"),
    weekNav: $(".week-nav"),
    weekLabel: $(".week-label"),
    compactBtn: $('[data-action="compact"]'),
    reorderBtn: $('[data-action="reorder"]'),
  };

  // ---------------------------------------------------------------- Datum (ISO-Strings "YYYY-MM-DD")
  const toUTC = (iso) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d));
  };
  const toISO = (dt) => dt.toISOString().slice(0, 10);
  const addDays = (iso, n) => {
    const d = toUTC(iso);
    d.setUTCDate(d.getUTCDate() + n);
    return toISO(d);
  };
  const weekday = (iso) => (toUTC(iso).getUTCDay() + 6) % 7; // 0 = Montag
  const mondayOf = (iso) => addDays(iso, -weekday(iso));
  const shortDate = (iso) => {
    const d = toUTC(iso);
    return `${d.getUTCDate()}.${d.getUTCMonth() + 1}.`;
  };
  const isoWeek = (iso) => {
    const d = toUTC(iso);
    d.setUTCDate(d.getUTCDate() - weekday(iso) + 3); // Donnerstag derselben Woche
    const jan4 = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
    return 1 + Math.round(((d - jan4) / 864e5 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
  };
  const viennaToday = () =>
    new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" })
      .format(new Date());

  const viennaParts = (isoDateTime) => {
    const d = new Date(isoDateTime);
    if (Number.isNaN(d.getTime())) return null;
    const parts = {};
    new Intl.DateTimeFormat("de-AT", {
      timeZone: TZ, weekday: "short", day: "numeric", month: "numeric", year: "numeric",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(d).forEach((p) => { parts[p.type] = p.value; });
    parts.weekday = (parts.weekday || "").replace(".", "");
    parts.iso = new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(d);
    return parts;
  };

  /** "heute 10:30", "Mo 10:30" (letzte Tage) bzw. "9.11. 10:30" */
  const stampShort = (isoDateTime) => {
    const p = viennaParts(isoDateTime);
    if (!p) return null;
    const age = (toUTC(viennaToday()) - toUTC(p.iso)) / 864e5;
    const time = `${p.hour}:${p.minute}`;
    if (age === 0) return `heute ${time}`;
    return age < 6 ? `${p.weekday} ${time}` : `${p.day}.${p.month}. ${time}`;
  };
  const stampLong = (isoDateTime) => {
    const p = viennaParts(isoDateTime);
    return p ? `${p.weekday}, ${p.day}.${p.month}.${p.year}, ${p.hour}:${p.minute} Uhr` : "";
  };

  const priceFmt = new Intl.NumberFormat("de-AT", { style: "currency", currency: "EUR" });
  const safeUrl = (u) => (typeof u === "string" && /^https?:\/\//i.test(u) ? u : null);
  const joinNames = (names) =>
    names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} und ${names[names.length - 1]}`;

  // ---------------------------------------------------------------- DOM-Helfer
  function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }
  const extLink = (href, text) => h("a", { href, target: "_blank", rel: "noopener", text });

  // ---------------------------------------------------------------- localStorage (immer mit try/catch)
  function load(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch (_) {
      return fallback;
    }
  }
  function save(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (_) { /* privater Modus o. Ä. – dann eben nicht merken */ }
  }

  // ---------------------------------------------------------------- Zustand
  const state = {
    data: null,
    restaurants: [],
    weeks: [],
    week: null,
    selected: null,
    today: viennaToday(),
    initial: { date: null, hint: null },
    compact: load(COMPACT_KEY, false) === true,
    reordering: false,
  };

  const dayOf = (r, iso) => (r.days || []).find((d) => d.date === iso && d.items && d.items.length);
  const hasDataFor = (iso) => state.restaurants.some((r) => dayOf(r, iso));
  const weekHasData = (r, monday) =>
    (r.days || []).some((d) => mondayOf(d.date) === monday && weekday(d.date) < 5 && d.items && d.items.length);
  const isFutureWeek = (monday) => monday > mondayOf(state.today);

  function applyOrder() {
    const saved = load(ORDER_KEY, []);
    const ids = Array.isArray(saved) ? saved : [];
    const byId = new Map(state.restaurants.map((r) => [r.id, r]));
    const ordered = ids.filter((id) => byId.has(id)).map((id) => byId.get(id));
    state.restaurants.forEach((r) => { if (!ordered.includes(r)) ordered.push(r); });
    state.restaurants = ordered;
  }

  function move(id, dir) {
    const i = state.restaurants.findIndex((r) => r.id === id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= state.restaurants.length) return;
    const list = state.restaurants;
    [list[i], list[j]] = [list[j], list[i]];
    save(ORDER_KEY, list.map((r) => r.id));
    renderCards();
    const btn = els.cards.querySelector(`[data-id="${id}"] .move-btn[data-dir="${dir}"]`);
    (btn && !btn.disabled ? btn : els.cards.querySelector(`[data-id="${id}"] .move-btn:not(:disabled)`))?.focus();
  }

  // ---------------------------------------------------------------- Anfangsauswahl
  function initialSelection() {
    const today = state.today;
    const wd = weekday(today);
    const fromHash = /^#(\d{4}-\d{2}-\d{2})$/.exec(location.hash);
    // Datum aus der URL nur, wenn es nicht in der Vergangenheit liegt – sonst zeigt ein am
    // Handy offen gelassener Tab nach dem Neuladen am nächsten Tag noch den Vortag.
    if (fromHash && weekday(fromHash[1]) < 5 && fromHash[1] >= today) return { date: fromHash[1], hint: null };

    if (wd < 5) {
      const hint = hasDataFor(today)
        ? null
        : "Für heute sind noch keine Menüs da – die Daten werden werktags ab ca. 9:30 Uhr aktualisiert.";
      return { date: today, hint };
    }
    const nextMonday = addDays(today, 7 - wd);
    if (hasDataFor(nextMonday)) return { date: nextMonday, hint: null }; // Vorschau-Hinweis kommt aus hintText()
    return {
      date: addDays(today, 4 - wd),
      hint: "Wochenende – die neuen Menüs gibt es am Montag. Hier der Stand vom Freitag.",
    };
  }

  function computeWeeks(selected) {
    const set = new Set([mondayOf(selected)]);
    state.restaurants.forEach((r) => (r.days || []).forEach((d) => {
      if (weekday(d.date) < 5 && d.items && d.items.length) set.add(mondayOf(d.date));
    }));
    // nur aktuelle/kommende Wochen anbieten (Vergangenes ist uninteressant)
    const min = mondayOf(state.today);
    return [...set].filter((w) => w >= min || w === mondayOf(selected)).sort();
  }

  /** Hinweiszeile: Vorschau-Wochen erklären, sonst den Anfangshinweis (nur auf dem Starttag). */
  function hintText() {
    if (isFutureWeek(state.week)) {
      const names = state.restaurants.filter((r) => weekHasData(r, state.week)).map((r) => r.name);
      const prefix = weekday(state.today) >= 5 ? "Wochenende! " : "";
      let who = "";
      if (names.length === 0) who = " Noch hat kein Restaurant das Menü veröffentlicht.";
      else if (names.length < state.restaurants.length) {
        who = names.length === 1
          ? ` Bisher hat erst ${names[0]} das Menü veröffentlicht.`
          : ` Bisher haben erst ${joinNames(names)} das Menü veröffentlicht.`;
      }
      return `${prefix}Vorschau auf KW ${isoWeek(state.week)}.${who}`;
    }
    return state.selected === state.initial.date ? state.initial.hint : null;
  }

  /** Leerzustand mit Begründung statt pauschalem "Kein Menü". */
  function emptyText(r, iso) {
    const hasWeek = weekHasData(r, mondayOf(iso));
    if (!hasWeek && isFutureWeek(mondayOf(iso))) return "Das Menü für diese Woche ist noch nicht veröffentlicht.";
    if (r.empty_hint && (iso >= state.today || !hasWeek)) return r.empty_hint;
    return "Kein Menü für diesen Tag.";
  }

  // ---------------------------------------------------------------- Rendern
  function select(iso, { focus = false } = {}) {
    state.selected = iso;
    state.week = mondayOf(iso);
    try { history.replaceState(null, "", `#${iso}`); } catch (_) { /* file:// o. Ä. */ }
    renderWeekNav();
    renderTabs(focus);
    renderHint();
    renderCards();
  }

  function renderHint() {
    const text = hintText();
    els.hint.hidden = !text;
    els.hint.textContent = text || "";
  }

  function renderWeekNav() {
    const multiple = state.weeks.length > 1;
    els.weekNav.hidden = !multiple;
    if (!multiple) return;
    const idx = state.weeks.indexOf(state.week);
    const fri = addDays(state.week, 4);
    els.weekLabel.textContent = `KW ${isoWeek(state.week)} · ${shortDate(state.week)}–${shortDate(fri)}`
      + (isFutureWeek(state.week) ? " · Vorschau" : "");
    els.weekNav.querySelectorAll(".week-btn").forEach((b) => {
      const target = idx + Number(b.dataset.dir);
      b.disabled = target < 0 || target >= state.weeks.length;
    });
  }

  function renderTabs(focus) {
    els.tabs.replaceChildren();
    for (let i = 0; i < 5; i++) {
      const iso = addDays(state.week, i);
      const selected = iso === state.selected;
      const tab = h("button", {
        type: "button",
        role: "tab",
        class: ["day-tab", iso === state.today && "is-today", !hasDataFor(iso) && "no-data"].filter(Boolean).join(" "),
        "aria-selected": selected ? "true" : "false",
        "aria-label": `${WD_LONG[i]}, ${shortDate(iso)}${iso === state.today ? " (heute)" : ""}`,
        tabindex: selected ? "0" : "-1",
        "data-date": iso,
        onclick: () => select(iso, { focus: true }),
      }, h("span", { class: "wd", text: WD_SHORT[i] }), h("span", { class: "dt", text: shortDate(iso) }));
      els.tabs.append(tab);
      if (selected && focus) tab.focus();
    }
  }

  function renderItem(item) {
    const badges = [];
    const tags = item.tags || [];
    if (tags.includes("vegan")) badges.push("vegan");
    else if (item.vegetarian === true && !/vegetarisch/i.test(item.label || "")) badges.push("vegetarisch");
    const price = typeof item.price === "number" ? priceFmt.format(item.price) : "";
    const label = item.label && !GENERIC_LABEL.test(item.label) ? item.label : null;
    return h("li", { class: "item" },
      label ? h("span", { class: "item-label", text: label }) : null,
      h("div", { class: "item-name" }, item.name, badges.map((b) => h("span", { class: "badge", text: b }))),
      h("span", { class: "item-price", text: price }),
      item.description ? h("div", { class: "item-meta", text: item.description }) : null,
      item.allergens ? h("div", { class: "item-allergens", text: `Allergene: ${item.allergens}` }) : null,
    );
  }

  function renderCard(r, index, total) {
    const source = safeUrl(r.source_url);
    const flyer = safeUrl(r.flyer_url);
    const preview = safeUrl(r.preview_image);
    const day = dayOf(r, state.selected);
    const website = flyer || source;
    const websiteText = flyer ? "Zum Flugblatt" : "Zur Website";

    const head = h("div", { class: "card-head" },
      h("h2", { class: "card-title" }, source ? extLink(source, r.name) : r.name),
      state.reordering ? [
        h("button", {
          type: "button", class: "move-btn", "data-dir": "-1", "aria-label": `${r.name} nach oben`,
          title: "Nach oben", disabled: index === 0, onclick: () => move(r.id, -1),
        }, "▲"),
        h("button", {
          type: "button", class: "move-btn", "data-dir": "1", "aria-label": `${r.name} nach unten`,
          title: "Nach unten", disabled: index === total - 1, onclick: () => move(r.id, 1),
        }, "▼"),
      ] : null,
    );
    if (state.reordering) return h("article", { class: "card is-reordering", "data-id": r.id }, head);

    const subtitle = r.subtitle ? h("p", { class: "card-sub", text: r.subtitle }) : null;

    let stale = null;
    if (r.stale || r.error) {
      const when = r.fetched_at ? stampShort(r.fetched_at) : null;
      stale = h("p", { class: "stale", title: r.error || "" },
        when ? `Stand: ${when}, aktuelle Daten nicht verfügbar` : "Aktuelle Daten nicht verfügbar");
    }

    let body;
    if (day) {
      body = h("ul", { class: "items" }, day.items.map(renderItem));
    } else {
      body = h("div", { class: "empty" },
        h("p", { class: "empty-text", text: emptyText(r, state.selected) }),
        website ? h("p", { class: "empty-link" }, extLink(website, `${websiteText} ↗`)) : null,
        // Interspar-Fallback: keine geparsten Tage -> Flugblatt-Vorschau
        !(r.days || []).length && flyer && preview
          ? h("a", { class: "flyer", href: flyer, target: "_blank", rel: "noopener" },
            h("img", { src: preview, alt: `Menüplan ${r.name} (Vorschau)`, loading: "lazy", referrerpolicy: "no-referrer" }))
          : null,
      );
    }

    const notes = (r.notes || []).length
      ? h("details", { class: "notes" }, h("summary", { text: "Hinweise" }),
        h("ul", {}, r.notes.map((n) => h("li", { text: n }))))
      : null;

    // Website-Link unten nur, wenn er nicht schon im Leerzustand steht
    const foot = day && website
      ? h("div", { class: "card-foot" }, extLink(website, `${websiteText} ↗`))
      : null;

    return h("article", { class: "card", "data-id": r.id }, head, subtitle, stale, body, notes, foot);
  }

  function renderCards() {
    const total = state.restaurants.length;
    els.cards.replaceChildren(...state.restaurants.map((r, i) => renderCard(r, i, total)));
  }

  function applyModes() {
    document.body.classList.toggle("compact", state.compact);
    document.body.classList.toggle("reordering", state.reordering);
    els.compactBtn.setAttribute("aria-pressed", String(state.compact));
    els.reorderBtn.setAttribute("aria-pressed", String(state.reordering));
    els.reorderBtn.textContent = state.reordering ? "Fertig" : "Reihenfolge ändern";
    els.compactBtn.hidden = state.reordering;
  }

  // ---------------------------------------------------------------- Events
  els.tabs.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const i = weekday(state.selected);
    const next = e.key === "Home" ? 0 : e.key === "End" ? 4 : (i + (e.key === "ArrowRight" ? 1 : -1) + 5) % 5;
    select(addDays(state.week, next), { focus: true });
  });

  els.weekNav.addEventListener("click", (e) => {
    const btn = e.target.closest(".week-btn");
    if (!btn || btn.disabled) return;
    const idx = state.weeks.indexOf(state.week) + Number(btn.dataset.dir);
    if (idx < 0 || idx >= state.weeks.length) return;
    const wd = Math.min(weekday(state.selected), 4);
    select(addDays(state.weeks[idx], wd));
  });

  els.compactBtn.addEventListener("click", () => {
    state.compact = !state.compact;
    save(COMPACT_KEY, state.compact);
    applyModes();
  });

  els.reorderBtn.addEventListener("click", () => {
    state.reordering = !state.reordering;
    applyModes();
    renderCards();
    if (state.reordering) els.cards.querySelector(".move-btn:not(:disabled)")?.focus();
  });

  // ---------------------------------------------------------------- Start
  const REFRESH_AFTER_MS = 5 * 60 * 1000;
  let lastLoad = 0;

  async function fetchData() {
    const res = await fetch("data/menu.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    lastLoad = Date.now();
    return res.json();
  }

  function applyData(data, { keepSelection }) {
    state.data = data;
    state.restaurants = Array.isArray(data.restaurants) ? data.restaurants.slice() : [];
    applyOrder();
    state.initial = initialSelection();
    const target = keepSelection && state.selected ? state.selected : state.initial.date;
    state.weeks = computeWeeks(target);
    els.updated.textContent = data.generated_at ? `Zuletzt aktualisiert: ${stampLong(data.generated_at)}` : "";
    select(target);
  }

  async function init() {
    applyModes();
    try {
      applyData(await fetchData(), { keepSelection: false });
    } catch (err) {
      els.cards.replaceChildren(h("p", { class: "error-box", text: "Die Menüdaten konnten nicht geladen werden. Bitte später nochmal versuchen." }));
      console.error(err);
    }
  }

  // Handys halten Tabs oft stundenlang offen und zeigen sie beim Zurückwechseln ohne Neuladen.
  // Beim Wiederanzeigen daher still nachladen: neuer Tag -> zurück auf "heute",
  // nur neue Daten -> gewählten Tag behalten.
  async function refreshIfStale() {
    if (document.visibilityState !== "visible" || Date.now() - lastLoad < REFRESH_AFTER_MS) return;
    if (state.reordering) return;
    const dayChanged = viennaToday() !== state.today;
    let data;
    try {
      data = await fetchData();
    } catch (_) {
      return; // offline o. Ä. – alte Ansicht behalten
    }
    if (!dayChanged && state.data && data.generated_at === state.data.generated_at) return;
    state.today = viennaToday();
    applyData(data, { keepSelection: !dayChanged });
  }

  document.addEventListener("visibilitychange", refreshIfStale);
  window.addEventListener("pageshow", (e) => { if (e.persisted) refreshIfStale(); });

  init();
})();
