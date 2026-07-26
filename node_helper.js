const NodeHelper = require("node_helper");
const fs = require("fs");
const path = require("path");

module.exports = NodeHelper.create({
	socketNotificationReceived(notification, payload) {
		if (notification !== "TOKENUSAGE_START") return;
		const send = () => {
			const file = path.join(__dirname, "data.json");
			fs.readFile(file, "utf8", (err, raw) => {
				if (err) return;
				try {
					this.sendSocketNotification("TOKENUSAGE_DATA", JSON.parse(raw));
				} catch (e) { /* halbe Schreibung — nächster Tick */ }
			});
		};
		send();
		if (!this.timer) this.timer = setInterval(send, payload.interval || 900000);
	}
});
