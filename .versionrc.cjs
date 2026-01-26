module.exports = {
	types: [
		{ type: "feat", section: "✨ Features" },
		{ type: "fix", section: "🐛 Bug Fixes" },
		{ type: "chore", section: "🔧 Maintenance", hidden: false },
		{ type: "docs", section: "📚 Documentation" },
		{ type: "ci", section: "👷 CI/CD" },
		{ type: "refactor", section: "♻️ Refactoring" },
		{ type: "perf", section: "⚡ Performance" },
		{ type: "test", section: "🧪 Tests" },
	],
	bumpFiles: [
		{ filename: "package.json", type: "json" },
		{ filename: "frontend/package.json", type: "json" },
		{
			filename: "crm/__init__.py",
			updater: "./scripts/python-version-updater.cjs",
		},
	],
	tagPrefix: "v",
};
