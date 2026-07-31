const assert = require("assert");
const http = require("http");
const ModuleLoader = require("module");
const { Readable } = require("stream");

const originalLoad = ModuleLoader._load;
ModuleLoader._load = function(request, parent, isMain) {
	if (request === "node_helper") return { create: value => value };
	return originalLoad.call(this, request, parent, isMain);
};
const helper = require("../node_helper.js");
ModuleLoader._load = originalLoad;

function read(source) {
	return new Promise(resolve => helper.readSource(source, resolve));
}

(async () => {
	const local = await read("data.json");
	assert.strictEqual(local.schema_version, 2);
	assert.strictEqual(await read("../package.json"), null);

	const originalGet = http.get;
	http.get = (source, options, callback) => {
		const response = new Readable({
			read() {
				this.push(JSON.stringify({ schema_version: 2, dates: ["2026-01-01"], series: [] }));
				this.push(null);
			}
		});
		response.statusCode = 200;
		response.headers = {};
		process.nextTick(() => callback(response));
		return { on() { return this; }, destroy() {} };
	};
	const remote = await read("http://usage.example.test/usage.json");
	http.get = originalGet;
	assert.strictEqual(remote.schema_version, 2);

	console.log("node helper file/http sources: ok");
})().catch(error => {
	console.error(error);
	process.exitCode = 1;
});
