const { chromium } = require(
  process.env.PROOFLINE_PLAYWRIGHT_MODULE || "playwright",
);
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PROOFLINE_CHROME_PATH,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  let submitted,
    resumed = false,
    profile;
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const finding = {
    id: "f1",
    category: "bug",
    severity: "high",
    disposition: "open",
    title: "Empty cart crashes checkout",
    explanation: "Empty input reaches cart[0].",
    user_impact: "Checkout returns a server error.",
    proposed_remedy: "Guard empty input.",
    analysis_status: "contextual_assessment",
    evidence_status: "source_supported",
    verification_assessment: {
      explanation: "The caller allows an empty cart.",
      citations: [
        { path: "checkout.py", start_line: 2, quote: "    return cart[0]" },
      ],
    },
    primary_location: { path: "checkout.py", start_line: 2 },
    related_locations: [],
    evidence_items: [],
  };
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body;
    if (path.endsWith("/capabilities"))
      body = {
        trusted_verification_profiles: [
          "expense_service_sql",
          "custom-approved",
        ],
      };
    else if (path.endsWith("/resume")) {
      resumed = true;
      body = { run_id: "resumed" };
    } else if (path.endsWith("/reviews")) {
      submitted = route.request().postDataJSON();
      body = { run_id: "first" };
    } else if (path.endsWith("/findings")) body = [finding];
    else if (path.endsWith("/source"))
      body = {
        path: "checkout.py",
        content: "def checkout(cart):\n    return cart[0]",
      };
    else if (path.endsWith("/verify")) {
      profile = route.request().postDataJSON().profile_id;
      body = { message: "Verification passed" };
    } else if (path.includes("/patches"))
      body = {
        id: "patch",
        status: "proposed",
        diff: "@@ -1 +1 @@\n-return cart[0]\n+return cart[0] if cart else None",
        checks: [],
      };
    else
      body = {
        id: resumed ? "resumed" : "first",
        status: "partial",
        review_mode: "commit",
        coverage: {
          impact: {
            changes: [
              {
                symbol: {
                  id: "checkout",
                  name: "checkout",
                  path: "checkout.py",
                  start: 1,
                  end: 2,
                },
                callers: [
                  {
                    path: "caller.py",
                    line: 3,
                    relationship: "resolved_python_call",
                  },
                ],
                test_hints: ["test_checkout.py"],
              },
            ],
            deleted_symbols: [],
            limitations: "Tests are lexical hints.",
          },
          review_summary: "One supported finding.",
          verification_coverage: {
            requested: 2,
            assessed: 1,
            unassessed_ids: ["other"],
          },
          diff: "@@ -1 +1 @@\n-return None\n+return cart[0]",
          investigation: {
            model_calls: 2,
            tool_calls: 1,
            trace: [{ event_type: "tool_completed", role: "review" }],
          },
        },
        stage_statuses: { ingestion: "succeeded", challenge: "failed" },
      };
    await route.fulfill({ json: body });
  });
  await page.goto("http://127.0.0.1:3002");
  await page.getByText("Settings & debug", { exact: true }).click();
  await page.getByLabel("Gemini API", { exact: true }).selectOption("interactions");
  await page.getByText("Advanced model roles", { exact: true }).click();
  await page
    .getByLabel("Verifier model", { exact: true })
    .fill("gemini-2.5-flash");
  await page.getByText("Settings & debug", { exact: true }).click();
  await page
    .getByLabel("GitHub review URL")
    .fill("https://github.com/demo/project/commit/abcdef1");
  await page.getByRole("button", { name: "Start review" }).click();
  await page.getByRole("heading", { name: finding.title }).last().waitFor();
  if (submitted.api_mode !== "interactions") throw Error("API mode selection not sent");
  if (submitted.role_models.verify_reasoning !== "gemini-2.5-flash")
    throw Error("Role selection not sent");
  await page.getByRole("button", { name: "checkout.py:2 ↗" }).last().click();
  await page.locator(".highlight").waitFor();
  await page.getByRole("button", { name: "Propose repair" }).click();
  await page.getByText("Verification & publication", { exact: true }).click();
  await page
    .getByLabel("Verification profile", { exact: true })
    .selectOption("custom-approved");
  await page.getByRole("button", { name: "Run approved verification" }).click();
  await page.getByText("Verification passed", { exact: true }).waitFor();
  if (profile !== "custom-approved") throw Error("Wrong profile");
  await page.getByRole("button", { name: "Files & diff" }).click();
  if (!(await page.locator(".added").count()))
    throw Error("Missing colored diff");
  await page.getByRole("heading", { name: "checkout", exact: true }).waitFor();
  await page.getByText("test_checkout.py", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Coverage & test gaps" }).click();
  await page
    .getByRole("heading", { name: "Independent verification" })
    .waitFor();
  await page.getByRole("button", { name: "Resume pinned review" }).click();
  await page.waitForURL("**/?run=resumed");
  if (!resumed) throw Error("Resume route not used");
  await page.setViewportSize({ width: 390, height: 844 });
  if (
    await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  )
    throw Error("Mobile overflow");
  if (errors.length) throw Error(errors.join("\n"));
  console.log(
    "PASS: roles, citations, source, repair, custom profile, diff, coverage, resume, mobile",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
