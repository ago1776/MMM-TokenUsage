const assert = require("assert");

let definition;
global.Module = {
	register(name, value) {
		assert.strictEqual(name, "MMM-TokenUsage");
		definition = value;
	}
};
require("../MMM-TokenUsage.js");

definition.config = { ...definition.defaults, providerColors: { gemini: "#112233" } };
assert.strictEqual(definition.defaults.updateInterval, 15 * 60 * 1000);
assert.strictEqual(definition.defaults.showScale, true);
assert.strictEqual(definition.fmt(16823296), "16,82 Mio.");

const generic = definition.normalizedSeries({
	schema_version: 2,
	series: [
		{ id: "gemini", label: "Gemini", color: "#ffffff", daily: [1, 2] },
		{ id: "mistral", label: "Mistral", color: "url(https://invalid.example)", daily: [3, -4] },
		{ id: "openrouter", label: "OpenRouter", daily: [5, 6] }
	]
});
assert.deepStrictEqual(generic.map(item => item.id), ["gemini", "mistral", "openrouter"]);
assert.strictEqual(generic[0].color, "#112233");
assert.strictEqual(generic[1].color, definition.palette(1));
assert.deepStrictEqual(generic[1].daily, [3, 0]);

const legacy = definition.normalizedSeries({ claude_daily: [1], openai_daily: [2] });
assert.deepStrictEqual(legacy.map(item => item.id), ["claude", "openai"]);

console.log("renderer normalization: ok");
