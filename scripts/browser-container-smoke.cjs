// Uses the actual local containers with static-only authored fixtures. No mocked review responses.
const { chromium } = require(
  process.env.PROOFLINE_PLAYWRIGHT_MODULE || "playwright",
);
(async () => {
  const token = process.env.PROOFLINE_CONTAINER_TEST_TOKEN;
  if (!token) throw Error("Set the isolated test stack operator token");
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PROOFLINE_CHROME_PATH,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(process.env.PROOFLINE_BROWSER_URL || "http://127.0.0.1:3005");
  await page.getByText("Settings & debug", { exact: true }).click();
  await page.getByLabel("Operator access token", { exact: true }).fill(token);
  await page.getByText("Settings & debug", { exact: true }).click();
  await page.getByRole("button", { name: "Try example" }).click();
  await page
    .getByRole("button", { name: /Findings · [1-9]/ })
    .waitFor({ timeout: 60000 });
  await page.locator(".finding.selected").waitFor();
  await page.screenshot({
    path: "docs/screenshots/review-workspace-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Files & diff" }).click();
  if (!(await page.locator(".added").count())) throw Error("Real diff missing");
  await page.getByRole("button", { name: "Coverage & test gaps" }).click();
  await page.getByText("Independent verification", { exact: true }).waitFor();
  await page.getByRole("button", { name: /Findings ·/ }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  if (
    await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  )
    throw Error("Mobile overflow");
  await page.screenshot({
    path: "docs/screenshots/review-workspace-mobile.png",
    fullPage: true,
  });
  if (errors.length) throw Error(errors.join("\n"));
  await browser.close();
  console.log(
    "PASS: actual container UI authenticated example, real findings/diff/coverage/mobile; screenshots contain static-only partial results",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
