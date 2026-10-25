// Lints every dashboards/*/panels/*.js file -- the Business Charts
// getOption() bodies extracted from dashboard JSON. These are function
// bodies (top-level `return` is expected, not a module), evaluated inside
// Grafana's panel runtime, so `context`/`window`/`fetch` etc. are globals
// provided by that runtime, not undefined references.
export default [
  {
    files: ["**/panels/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: {
        context: "readonly",
        window: "readonly",
        fetch: "readonly",
        console: "readonly",
        Promise: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
      },
    },
    rules: {
      "no-unused-vars": "error",
      "no-undef": "error",
      "no-redeclare": "error",
      eqeqeq: ["error", "smart"],
    },
  },
];
