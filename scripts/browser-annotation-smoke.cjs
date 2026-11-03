const { chromium } = require(
  process.env.PROOFLINE_PLAYWRIGHT_MODULE || "playwright",
);
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PROOFLINE_CHROME_PATH,
  });
  const page = await browser.newPage({
    acceptDownloads: true,
    viewport: { width: 1200, height: 900 },
  });
  let errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const file = path.resolve("evals/annotation/review.html");
  if (fs.readFileSync(file, "utf8").includes("expected_issues"))
    throw Error("Expected labels leaked");
  await page.goto(pathToFileURL(file).href);
  await page
    .locator("#reviewer")
    .fill("Automated UI smoke — not independent annotation");
  const first = page.locator("article").first();
  await first.locator("select").selectOption("uncertain");
  await first
    .locator("textarea")
    .fill("Synthetic smoke test; do not use as reviewer evidence.");
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export annotations" }).click();
  const download = await pending;
  const saved = "/private/tmp/proofline-annotation-smoke.json";
  await download.saveAs(saved);
  const data = JSON.parse(fs.readFileSync(saved, "utf8"));
  if (
    data.annotations.length !== 36 ||
    data.annotations[0].verdict !== "uncertain"
  )
    throw Error("Wrong export");
  await page.reload();
  if ((await first.locator("select").inputValue()) !== "uncertain")
    throw Error("Progress not restored");
  await page.setViewportSize({ width: 390, height: 844 });
  if (
    await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  )
    throw Error("Mobile overflow");
  if (errors.length) throw Error(errors.join("\n"));
  console.log(
    "PASS: blinded packet, progress persistence, JSON export, mobile",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
