// Controlled transport faults only. Never contacts GitHub or Gemini.
const { chromium } = require(
  process.env.PROOFLINE_PLAYWRIGHT_MODULE || "playwright",
);
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PROOFLINE_CHROME_PATH,
  });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let submissions = 0,
    flakyReads = 0,
    releaseOld;
  const oldPending = new Promise((resolve) => {
    releaseOld = resolve;
  });
  const finding = (id, title) => ({
    id,
    category: "bug",
    severity: "high",
    disposition: "open",
    title,
    explanation: title,
    user_impact: "Incorrect result",
    proposed_remedy: "Check input",
    analysis_status: "static_observation",
    evidence_status: "insufficient_evidence",
    primary_location: { path: "app.py", start_line: 1 },
    related_locations: [],
    evidence_items: [],
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/capabilities")) return route.fulfill({ json: {} });
    if (path.endsWith("/reviews") && route.request().method() === "POST") {
      submissions++;
      return route.fulfill({ json: { run_id: "old" } });
    }
    if (path.endsWith("/old/findings")) {
      await oldPending;
      return route
        .fulfill({ json: [finding("old", "Stale result must not appear")] })
        .catch(() => {});
    }
    if (path.endsWith("/flaky") && ++flakyReads === 1)
      return route.fulfill({
        status: 503,
        json: { detail: "Temporarily unavailable" },
      });
    if (path.endsWith("/private") && !route.request().headers().authorization)
      return route.fulfill({
        status: 401,
        json: { detail: "Operator token required" },
      });
    if (path.endsWith("/findings"))
      return route.fulfill({
        json: [finding("current", "Current report stays selected")],
      });
    const id = path.split("/").at(-1);
    return route.fulfill({
      json: {
        id,
        status:
          id === "interrupted"
            ? "interrupted"
            : id === "flaky" && flakyReads === 2
              ? "running"
              : "partial",
        coverage: {},
        stage_statuses: {},
      },
    });
  });
  await page.goto("http://127.0.0.1:3002");
  await page
    .getByLabel("GitHub review URL")
    .fill("https://github.com/demo/app/pull/1");
  await page.getByRole("button", { name: "Start review" }).click();
  await page.waitForURL("**/?run=old");
  await page.getByText("Settings & debug", { exact: true }).click();
  async function open(id) {
    await page.getByLabel("Restore report", { exact: true }).fill(id);
    await page
      .getByRole("button", { name: "Open saved report", exact: true })
      .click();
  }
  await open("new");
  await page
    .getByRole("heading", { name: "Current report stays selected" })
    .last()
    .waitFor();
  releaseOld();
  await page.waitForTimeout(150);
  if (await page.getByText("Stale result must not appear").count())
    throw Error("Stale findings replaced current report");
  await open("flaky");
  await page.getByText(/Connection lost. Reconnecting/).waitFor();
  await page
    .getByRole("heading", { name: "Current report stays selected" })
    .last()
    .waitFor();
  if (flakyReads < 3 || submissions !== 1)
    throw Error(
      "Reconnect resubmitted a review or stopped polling a running saved review",
    );
  await page.reload();
  await page
    .getByRole("heading", { name: "Current report stays selected" })
    .last()
    .waitFor();
  if (submissions !== 1) throw Error("Reload submitted another paid review");
  await page.getByText("Settings & debug", { exact: true }).click();
  await open("private");
  await page
    .getByRole("alert")
    .filter({ hasText: "Operator token required" })
    .waitFor();
  await page
    .getByLabel("Operator access token", { exact: true })
    .fill("test-only");
  await page.getByRole("button", { name: "Reconnect to saved review" }).click();
  await page
    .getByRole("heading", { name: "Current report stays selected" })
    .last()
    .waitFor();
  await open("interrupted");
  await page
    .getByRole("heading", { name: "Review interrupted.", exact: true })
    .waitFor();
  if (submissions !== 1 || errors.length)
    throw Error(JSON.stringify({ submissions, errors }));
  await browser.close();
  console.log(
    "PASS: stale findings discarded, saved active review followed, transient reconnect, URL reload, auth recovery, no duplicate submissions",
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
