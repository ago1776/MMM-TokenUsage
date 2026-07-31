/* MMM-TokenUsage — daily AI token usage as stacked gradient bars.
 * The renderer reads the configured JSON file and remains source-agnostic. */
Module.register("MMM-TokenUsage", {
	defaults: {
		updateInterval: 15 * 60 * 1000,
		dataSource: "data.json",
		header: "AI Usage · 14 days",
		barMaxHeight: 96,
		providerColors: {},
		colorClaude: "#c96f4a",
		colorOpenAI: "#5aa6d8"
	},

	start() {
		this.data_ = null;
		this.sendSocketNotification("TOKENUSAGE_START", {
			interval: this.config.updateInterval,
			dataSource: this.config.dataSource
		});
	},

	getStyles() { return ["MMM-TokenUsage.css"]; },
	getHeader() { return this.config.header; },

	socketNotificationReceived(notification, payload) {
		if (notification === "TOKENUSAGE_DATA") { this.data_ = payload; this.updateDom(300); }
	},

	getDom() {
		const w = document.createElement("div");
		w.className = "tokenusage";
		const d = this.data_;
		const series = this.normalizedSeries(d);
		if (!series.length) { w.innerHTML = `<div class="tu-load">&hellip;</div>`; return w; }

		const n = Math.max(...series.map(item => item.daily.length), 1);
		const totals = Array.from({ length: n }, (_, i) =>
			series.reduce((sum, item) => sum + Number(item.daily[i] || 0), 0));
		const peak = Math.max(...totals, 1);
		const H = this.config.barMaxHeight;

		const chart = document.createElement("div");
		chart.className = "tu-chart";
		chart.style.height = `${H + 16}px`;
		const anchor = new Date(String(d.generated || "").replace(" ", "T"));
		const peakIdx = totals.indexOf(peak);
		for (let i = 0; i < n; i++) {
			const col = document.createElement("div");
			col.className = "tu-col";
			const explicitDate = Array.isArray(d.dates) && d.dates[i]
				? new Date(`${d.dates[i]}T12:00:00`)
				: null;
			const date = explicitDate && !Number.isNaN(explicitDate.getTime())
				? explicitDate
				: Number.isNaN(anchor.getTime())
				? new Date()
				: new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate() - (n - 1 - i), 12);
			const weekday = date.getDay();
			const stack = document.createElement("div");
			stack.className = "tu-stack" + (weekday === 0 || weekday === 6 ? " tu-we" : "") + (i === n - 1 ? " tu-today" : "");
			series.forEach(item => {
				const value = Number(item.daily[i] || 0);
				if (value > 0) stack.appendChild(this.bar(Math.max(Math.round((value / peak) * H), 2), item.color));
			});
			col.appendChild(stack);
			const lbl = document.createElement("div");
			lbl.className = `tu-day${weekday === 0 ? " tu-sun" : weekday === 6 ? " tu-sat" : ""}`;
			lbl.textContent = weekday === 0 ? "So" : weekday === 6 ? "Sa" : "";
			col.appendChild(lbl);
			chart.appendChild(col);
		}
		w.appendChild(chart);

		const seriesTotals = series.map(item => item.daily.reduce((a, b) => a + Number(b || 0), 0));
		const grandTotal = seriesTotals.reduce((a, b) => a + b, 0);
		const todayTotal = totals[totals.length - 1] || 0;

		const legend = document.createElement("div");
		legend.className = "tu-legend";
		series.forEach((item, index) => {
			const entry = document.createElement("span");
			entry.className = "tu-li";
			const dot = document.createElement("i");
			dot.className = "tu-dot";
			dot.style.background = item.color;
			entry.appendChild(dot);
			entry.appendChild(document.createTextNode(`${item.label} `));
			const value = document.createElement("b");
			value.textContent = this.fmt(seriesTotals[index]);
			entry.appendChild(value);
			legend.appendChild(entry);
		});
		w.appendChild(legend);

		const sum = document.createElement("div");
		sum.className = "tu-sum";
		sum.innerHTML = `<span class="tu-sig">Σ&nbsp;<b>${this.fmt(grandTotal)}</b></span><span class="tu-today-v">heute&nbsp;<b>${this.fmt(todayTotal)}</b></span>`;
		w.appendChild(sum);

		const notes = Array.isArray(d.notes) ? d.notes
			: (d.fallback_days && d.fallback_days.length ? ["OpenAI-Fallback: " + d.fallback_days.join(", ")] : []);
		if (notes.length) {
			const fb = document.createElement("div");
			fb.className = "tu-foot";
			fb.textContent = notes.join(" · ");
			w.appendChild(fb);
		}
		return w;
	},

	normalizedSeries(data) {
		if (!data) return [];
		if (Array.isArray(data.series)) {
			return data.series
				.filter(item => item && Array.isArray(item.daily))
				.map((item, index) => ({
					id: String(item.id || `provider-${index + 1}`),
					label: String(item.label || item.id || `Provider ${index + 1}`),
					color: this.safeColor(
						(this.config.providerColors || {})[item.id] || item.color,
						this.palette(index)
					),
					daily: item.daily.map(value => Math.max(0, Number(value) || 0))
				}));
		}
		const legacy = [];
		if (Array.isArray(data.claude_daily)) legacy.push({
			id: "claude", label: "Claude", color: this.safeColor(this.config.colorClaude, this.palette(0)), daily: data.claude_daily
		});
		if (Array.isArray(data.openai_daily)) legacy.push({
			id: "openai", label: "OpenAI", color: this.safeColor(this.config.colorOpenAI, this.palette(1)), daily: data.openai_daily
		});
		return legacy;
	},

	palette(index) {
		return ["#c96f4a", "#5aa6d8", "#8abf69", "#b58ad8", "#e0a84f", "#62b8a7"][index % 6];
	},

	safeColor(value, fallback) {
		return typeof value === "string" && /^#[0-9a-f]{3,8}$/i.test(value) ? value : fallback;
	},

	fmt(value) {
		const n = Number(value || 0);
		if (n >= 1000000) return `${(n / 1000000).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 2 })} Mio.`;
		if (n >= 1000) return `${Math.round(n / 1000).toLocaleString("de-DE")}k`;
		return Math.round(n).toLocaleString("de-DE");
	},

	bar(h, color) {
		const b = document.createElement("div");
		b.className = "tu-bar";
		b.style.height = `${h}px`;
		b.style.setProperty("--bar-col", color);
		return b;
	}
});
