const { chromium } = require(
  process.env.PROOFLINE_PLAYWRIGHT_MODULE || "playwright",
);
(async () => {
  const b = await chromium.launch({
    headless: true,
    executablePath: process.env.PROOFLINE_CHROME_PATH,
  });
  const p = await b.newPage({ viewport: { width: 1440, height: 1100 } });
  let errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.route("**/api/v1/**", async (r) => {
    let url = r.request().url();
    let json = url.endsWith("/reviews")
      ? { run_id: "demo" }
      : url.endsWith("/findings")
        ? [
            {
              id: "f",
              category: "bug",
              severity: "high",
              disposition: "open",
              title: "Empty cart crashes checkout",
              explanation: "An empty cart reaches items[0] without a guard.",
              user_impact: "Customers receive a server error.",
              proposed_remedy:
                "Guard the empty input and add a regression test.",
              analysis_status: "static_confirmed",
              primary_location: { path: "checkout.py", start_line: 2 },
              related_locations: [],
              evidence_items: [],
            },
          ]
        : {
            id: "demo",
            status: "partial",
            review_mode: "commit",
            coverage: {
              review_summary: "One correctness issue needs attention.",
              diff: "@@ -1 +1 @@\n-return None\n+return items[0]",
            },
            stage_statuses: { ingestion: "completed", review: "partial" },
          };
    await r.fulfill({ json });
  });
  await p.goto("http://127.0.0.1:3002");
  await p
    .getByLabel("GitHub review URL")
    .fill("https://github.com/demo/project/commit/abcdef1");
  await p.getByRole("button", { name: "Start review" }).click();
  await p
    .getByRole("heading", { name: "Empty cart crashes checkout" })
    .last()
    .waitFor();
  await p.screenshot({
    path: "docs/screenshots/review-workspace-desktop.png",
    fullPage: true,
  });
  await p.getByRole("button", { name: "Files & diff" }).click();
  if (!(await p.locator(".added").count())) throw Error("Missing diff");
  await p.getByRole("button", { name: "Coverage & test gaps" }).click();
  await p.setViewportSize({ width: 390, height: 844 });
  if (await p.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    throw Error("Overflow");
  await p.screenshot({
    path: "docs/screenshots/review-workspace-mobile.png",
    fullPage: true,
  });
  if (errors.length) throw Error(errors.join("\n"));
  console.log("PASS: findings, diff, coverage, mobile");
  await b.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
