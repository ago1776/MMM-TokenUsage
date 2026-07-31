const NodeHelper = require("node_helper");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");

const MAX_BYTES = 2 * 1024 * 1024;

module.exports = NodeHelper.create({
	socketNotificationReceived(notification, payload = {}) {
		if (notification !== "TOKENUSAGE_START") return;
		const source = typeof payload.dataSource === "string" ? payload.dataSource : "data.json";
		const send = () => this.readSource(source, data => {
			if (data) this.sendSocketNotification("TOKENUSAGE_DATA", data);
		});
		send();
		if (!this.timer) this.timer = setInterval(send, payload.interval || 900000);
	},

	readSource(source, done) {
		if (/^https?:\/\//i.test(source)) {
			this.readUrl(source, done);
			return;
		}
		const file = path.resolve(__dirname, source);
		const moduleRoot = path.resolve(__dirname) + path.sep;
		if (!file.startsWith(moduleRoot)) return done(null);
		fs.readFile(file, "utf8", (error, raw) => {
			if (error || raw.length > MAX_BYTES) return done(null);
			done(this.parse(raw));
		});
	},

	readUrl(source, done, redirects = 0) {
		if (redirects > 3 || !/^https?:\/\//i.test(source)) return done(null);
		let settled = false;
		const finish = data => {
			if (settled) return;
			settled = true;
			done(data);
		};
		const client = source.startsWith("https://") ? https : http;
		const request = client.get(source, { timeout: 10000, headers: { "User-Agent": "MMM-TokenUsage/1.2" } }, response => {
			if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
				response.resume();
				const next = new URL(response.headers.location, source).toString();
				return this.readUrl(next, finish, redirects + 1);
			}
			if (response.statusCode !== 200) {
				response.resume();
				return finish(null);
			}
			let raw = "";
			response.setEncoding("utf8");
			response.on("data", chunk => {
				raw += chunk;
				if (raw.length > MAX_BYTES) {
					finish(null);
					response.destroy();
				}
			});
			response.on("end", () => finish(raw.length <= MAX_BYTES ? this.parse(raw) : null));
			response.on("error", () => finish(null));
		});
		request.on("timeout", () => request.destroy());
		request.on("error", () => finish(null));
	},

	parse(raw) {
		try {
			return JSON.parse(raw);
		} catch (error) {
			return null;
		}
	}
});
