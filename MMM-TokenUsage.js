/* MMM-TokenUsage — KI-Token-Verbrauch, 14 Tage als gestapelte Gradient-Saeulen.
 * Datenquelle: data.json (fleet-precollect, token-sparkline.py --json). Kein Cache-Token
 * (Quelle zaehlt nur input+output). Werte k/Mio. abgekuerzt. */
Module.register("MMM-TokenUsage", {
	defaults: {
		updateInterval: 15 * 60 * 1000,
		header: "AI Usage · 14 days",
		barMaxHeight: 96,
		colorClaude: "#c96f4a",
		colorOpenAI: "#5aa6d8"
	},

	start() {
		this.data_ = null;
		this.sendSocketNotification("TOKENUSAGE_START", { interval: this.config.updateInterval });
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
		if (!d || !d.claude_daily) { w.innerHTML = `<div class="tu-load">&hellip;</div>`; return w; }

		const n = d.claude_daily.length;
		const totals = d.claude_daily.map((c, i) => c + (d.openai_daily[i] || 0));
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
			const date = Number.isNaN(anchor.getTime())
				? new Date()
				: new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate() - (n - 1 - i), 12);
			const weekday = date.getDay();
			const stack = document.createElement("div");
			stack.className = "tu-stack" + (weekday === 0 || weekday === 6 ? " tu-we" : "") + (i === n - 1 ? " tu-today" : "");
			const hC = Math.round((d.claude_daily[i] / peak) * H);
			const hO = Math.round(((d.openai_daily[i] || 0) / peak) * H);
			if ((d.openai_daily[i] || 0) > 0) stack.appendChild(this.bar(Math.max(hO, 3), this.config.colorOpenAI, "o"));
			stack.appendChild(this.bar(Math.max(hC, totals[i] > 0 ? 2 : 0), this.config.colorClaude, "c"));
			col.appendChild(stack);
			const lbl = document.createElement("div");
			lbl.className = `tu-day${weekday === 0 ? " tu-sun" : weekday === 6 ? " tu-sat" : ""}`;
			lbl.textContent = weekday === 0 ? "So" : weekday === 6 ? "Sa" : "";
			col.appendChild(lbl);
			chart.appendChild(col);
		}
		w.appendChild(chart);

		const claudeTotal = d.claude_daily.reduce((a, b) => a + Number(b || 0), 0);
		const openaiTotal = d.openai_daily.reduce((a, b) => a + Number(b || 0), 0);
		const grandTotal = claudeTotal + openaiTotal;
		const todayTotal = totals[totals.length - 1] || 0;

		const legend = document.createElement("div");
		legend.className = "tu-legend";
		legend.innerHTML =
			`<span class="tu-li"><i class="tu-dot" style="background:${this.config.colorClaude}"></i>Claude <b>${this.fmt(claudeTotal)}</b></span>` +
			`<span class="tu-li"><i class="tu-dot" style="background:${this.config.colorOpenAI}"></i>OpenAI <b>${this.fmt(openaiTotal)}</b></span>`;
		w.appendChild(legend);

		const sum = document.createElement("div");
		sum.className = "tu-sum";
		sum.innerHTML = `<span class="tu-sig">Σ&nbsp;<b>${this.fmt(grandTotal)}</b></span><span class="tu-today-v">heute&nbsp;<b>${this.fmt(todayTotal)}</b></span>`;
		w.appendChild(sum);

		if (d.fallback_days && d.fallback_days.length) {
			const fb = document.createElement("div");
			fb.className = "tu-foot";
			fb.textContent = "OpenAI-Fallback: " + d.fallback_days.join(", ");
			w.appendChild(fb);
		}
		return w;
	},

	fmt(value) {
		const n = Number(value || 0);
		if (n >= 1000000) return `${(n / 1000000).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 2 })} Mio.`;
		if (n >= 1000) return `${Math.round(n / 1000).toLocaleString("de-DE")}k`;
		return Math.round(n).toLocaleString("de-DE");
	},

	bar(h, color, cls) {
		const b = document.createElement("div");
		b.className = "tu-bar tu-bar-" + cls;
		b.style.height = `${h}px`;
		b.style.setProperty("--bar-col", color);
		return b;
	}
});
