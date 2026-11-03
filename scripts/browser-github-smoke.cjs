const { chromium } = require(
  process.env.PROOFLINE_PLAYWRIGHT_MODULE || "playwright",
);
(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.PROOFLINE_CHROME_PATH
      ? { executablePath: process.env.PROOFLINE_CHROME_PATH }
      : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let submitted;
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body = {};
    if (path.endsWith("/github/status"))
      body = { configured: true, connected: true, login: "demo-user" };
    else if (path.endsWith("/github/repositories"))
      body = {
        items: [
          {
            name: "demo/project",
            url: "https://github.com/demo/project",
            private: true,
          },
        ],
        has_more: false,
      };
    else if (path.endsWith("/branches"))
      body = {
        items: [
          {
            label: "main",
            revision: "a".repeat(40),
            url: "https://github.com/demo/project",
          },
        ],
      };
    else if (path.endsWith("/pulls"))
      body = {
        items: [
          {
            label: "#12 Fix checkout",
            revision: "",
            url: "https://github.com/demo/project/pull/12",
          },
        ],
      };
    else if (path.endsWith("/commits"))
      body = {
        items: [
          {
            label: "abcdef1 Update checkout",
            revision: "",
            url: "https://github.com/demo/project/commit/abcdef1",
          },
        ],
      };
    else if (path.endsWith("/reviews")) {
      submitted = route.request().postDataJSON();
      body = { run_id: "test-run" };
    } else if (path.endsWith("/findings")) body = [];
    else
      body = {
        id: "test-run",
        status: "completed",
        review_mode: "pr",
        coverage: {},
        stage_statuses: {},
      };
    await route.fulfill({ json: body });
  });
  await page.goto(process.env.PROOFLINE_TEST_URL || "http://127.0.0.1:3002");
  if (
    await page
      .getByRole("button", { name: "Detect from URL", exact: true })
      .count()
  )
    throw Error("Old mode controls remain");
  await page
    .getByLabel("GitHub review URL")
    .fill("https://github.com/demo/project/commit/abcdef1");
  await page.getByText("Single commit detected", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Pick from GitHub", exact: true })
    .click();
  await page.getByLabel("GitHub repository").selectOption("demo/project");
  await page.getByLabel("GitHub review target").selectOption("0");
  await page.getByText("Whole project detected", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Pull request", exact: true }).click();
  await page.getByLabel("GitHub review target").selectOption("0");
  await page.getByRole("button", { name: /^Start review/ }).click();
  await page.getByRole("heading", { name: "Your review is ready." }).waitFor();
  if (
    submitted.repo_url !== "https://github.com/demo/project/pull/12" ||
    submitted.mode !== "pr"
  )
    throw Error("Wrong selected review");
  await page.setViewportSize({ width: 390, height: 844 });
  if (
    await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  )
    throw Error("Mobile overflow");
  if (errors.length) throw Error(errors.join("\n"));
  console.log(
    "PASS: simplified entry, URL detection, connected private repo picker, branch/PR selection, review payload, mobile layout, no browser errors",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
