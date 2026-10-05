import { expect, test } from "@playwright/test";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../../../", import.meta.url));

test("register external Agent, receive alert, repair through MCP and replay", async ({
  page,
  baseURL,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByRole("button", { name: /Agent 接入中心/ }).click();
  const name = `Browser Agent ${Date.now()}`;
  await page.getByLabel("Agent 名称").fill(name);
  const registration = page.waitForResponse(
    (r) => r.url().endsWith("/api/agents") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "注册 Agent", exact: true }).click();
  const { agent, credentials } = await (await registration).json();
  await expect(page.getByTestId("agent-token")).toHaveAttribute(
    "type",
    "password",
  );
  await expect(page.getByTestId("mcp-config")).toContainText(baseURL!);
  await expect(page.getByTestId("mcp-config")).not.toContainText(
    credentials.token,
  );
  const connector = spawn(
    `${root}.venv/bin/python`,
    [
      "scripts/mcp_agent.py",
      "--url",
      `${baseURL}/mcp`,
      "--mode",
      "reference",
      "--once",
      "--poll-seconds",
      "0.1",
    ],
    {
      cwd: root,
      env: {
        ...process.env,
        INCIDENTLAB_AGENT_TOKEN: credentials.token,
        AGENT_POLL_SECONDS: "0.5",
      },
      stdio: "ignore",
    },
  );
  const exited = new Promise<number | null>((resolve, reject) => {
    connector.once("exit", resolve);
    connector.once("error", reject);
  });
  try {
    await page.getByRole("button", { name: "已保存，关闭凭据" }).click();
    const card = page.getByTestId(`agent-card-${agent.id}`);
    await expect(card.getByText("在线", { exact: true })).toBeVisible({
      timeout: 15000,
    });
    await card.getByRole("button", { name: "连接检查" }).click();
    await expect(page.getByRole("status")).toContainText("检查通过");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: "../../artifacts/agent-registry.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "故障实验台", exact: true }).click();
    await page.getByLabel("响应 Agent").selectOption(agent.id);
    await page.getByRole("button", { name: "注入故障", exact: true }).click();
    await expect(page.getByTestId("incident-status")).toHaveText("已恢复", {
      timeout: 45000,
    });
    expect(await exited).toBe(0);
    await expect(page.getByTestId("workbench-agent")).toContainText(name);
    await expect(
      page.getByText("Agent 已接收告警", { exact: true }),
    ).toBeVisible();
    for (const key of ["redis_connections", "api_latency_ms", "api_error_rate"])
      await expect(page.getByTestId(`trend-${key}`)).toBeVisible();
    for (const label of [
      "故障注入",
      "告警触发",
      "Agent 接收",
      "根因诊断",
      "执行修复",
      "恢复验证",
      "事件恢复",
    ])
      await expect(
        page
          .getByRole("button", { name: new RegExp(`^${label} · 事件`) })
          .first(),
      ).toBeVisible();
    const left = await page.getByTestId("workbench-environment").boundingBox();
    const right = await page.getByTestId("workbench-agent").boundingBox();
    expect(left!.x + left!.width).toBeLessThanOrEqual(right!.x);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: "../../artifacts/console-trace.png",
      fullPage: true,
    });
    await page.getByRole("tab", { name: /诊断报告/ }).click();
    await expect(
      page.getByText("独立评估：恢复通过", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("worker / connection_leak", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("SOP-CONNECTION-PRESSURE-001", { exact: true }),
    ).toBeVisible();
    const downloadEvent = page.waitForEvent("download");
    await page.getByRole("button", { name: "下载报告" }).click();
    const report = JSON.parse(
      await readFile((await (await downloadEvent).path())!, "utf8"),
    );
    expect(report.agent.id).toBe(agent.id);
    expect(report.evaluation.incident_resolved).toBe(true);
    expect(report.actions).toHaveLength(1);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: "../../artifacts/console-desktop.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: /^故障注入 · 事件/ }).click();
    await expect(page.getByTestId("incident-status")).toHaveText("故障演化中");
    await expect(page.getByText("未产生诊断", { exact: true })).toBeVisible();
    await expect(
      page.getByText("独立评估：恢复通过", { exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: /^告警触发 · 事件/ }).click();
    await expect(page.getByTestId("incident-status")).toHaveText("告警触发");
    await expect(page.getByText("未产生诊断", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "实时", exact: true }).click();
    await expect(
      page.getByText("独立评估：恢复通过", { exact: true }),
    ).toBeVisible();
    await page.reload();
    await page.getByRole("tab", { name: /诊断报告/ }).click();
    await expect(
      page.getByText("worker / connection_leak", { exact: true }),
    ).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: "../../artifacts/console-mobile.png",
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await page.setViewportSize({ width: 1440, height: 1080 });
    await page
      .getByRole("button", { name: "Agent 排行榜", exact: true })
      .click();
    const ranked = page.getByTestId(`leaderboard-agent-${agent.id}`);
    await expect(ranked).toContainText(name);
    await expect(ranked.locator('[data-label="场景覆盖"]')).toHaveText("1 / 6");
    await page.getByLabel("排行场景").selectOption("redis-connection-leak");
    await expect(ranked.locator('[data-label="综合分"]')).toContainText("100");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: "../../artifacts/leaderboard.png",
      fullPage: true,
    });
    expect(errors).toEqual([]);
  } finally {
    if (connector.exitCode === null) connector.kill("SIGTERM");
  }
});

test("cancel an active experiment", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "注入故障", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "注入故障", exact: true }).click();
  await page.getByRole("button", { name: "停止", exact: true }).click();
  await expect(page.getByTestId("incident-status")).toHaveText("已取消");
  await page.getByRole("tab", { name: /诊断报告/ }).click();
  await expect(
    page.getByText("独立评估：未通过", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^实验取消 · 事件/ }),
  ).toBeVisible();
});

for (const [scenario, rootCause, metric] of [
  ["api-cpu-saturation", "api / cpu_saturation", "api_cpu_percent"],
  ["database-slow-queries", "database / slow_queries", "database_latency_ms"],
  ["worker-queue-backlog", "worker / queue_backlog", "queue_depth"],
  ["queue-service-down", "queue / service_down", "queue_depth"],
]) {
  test(`simulate and repair ${scenario}`, async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("故障场景").selectOption(scenario);
    for (const service of [
      "gateway",
      "api",
      "worker",
      "redis",
      "database",
      "queue",
    ]) {
      await expect(page.getByTestId(`service-${service}`)).toBeVisible();
    }
    await page.getByRole("button", { name: "注入故障", exact: true }).click();
    await expect(page.getByTestId("incident-status")).toHaveText("已恢复", {
      timeout: 45000,
    });
    await expect(page.getByTestId(`trend-${metric}`)).toBeVisible();
    await page.getByRole("tab", { name: /诊断报告/ }).click();
    await expect(page.getByText(rootCause, { exact: true })).toBeVisible();
    await expect(
      page.getByText("独立评估：恢复通过", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: /^告警触发 · 事件/ }).click();
    await expect(page.getByTestId("incident-status")).toHaveText("告警触发");
    if (scenario === "database-slow-queries") {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({
        path: "../../artifacts/expanded-topology-fault.png",
        fullPage: true,
      });
    }
  });
}

test("fault marker, dependency semantics and expanded topology geometry", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("故障场景")
    .selectOption("db-connection-pool-exhaustion");
  await expect(page.getByTestId("fault-location")).toContainText(
    "待注入 · db_proxy",
  );
  await expect(page.getByTestId("service-db_proxy")).toBeVisible();
  await page.getByRole("button", { name: "注入故障", exact: true }).click();
  await expect(page.getByTestId("incident-status")).toHaveText("已恢复", {
    timeout: 45000,
  });
  await expect(page.getByTestId("fault-location")).toContainText(
    "注入点已恢复 · db_proxy",
  );
  await page.getByRole("tab", { name: /诊断报告/ }).click();
  await expect(
    page.getByText("db_proxy / connection_pool_exhaustion", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /^告警触发 · 事件/ }).click();
  await expect(page.getByTestId("fault-location")).toContainText(
    "故障注入点 · db_proxy",
  );
  await expect(page.getByTestId("service-database")).toHaveAttribute(
    "aria-label",
    /healthy/,
  );
  await expect(
    page.getByTestId("dependency-db_proxy-database"),
  ).toHaveAttribute("data-affected", "false");
  await expect(page.getByTestId("dependency-payment-db_proxy")).toHaveAttribute(
    "data-affected",
    "true",
  );
  await page.getByRole("button", { name: "展开拓扑", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "展开环境拓扑" });
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("service-db_proxy").click();
  await expect(dialog.locator('path[data-focused="true"]')).toHaveCount(1);
  const intersections = await dialog.evaluate((element) => {
    const nodes = [
      ...element.querySelectorAll<HTMLElement>('[data-testid^="service-"]'),
    ];
    const collisions: string[] = [];
    for (const edge of element.querySelectorAll<SVGPathElement>(
      'path[data-testid^="dependency-"]',
    )) {
      const transform = edge.getScreenCTM();
      if (!transform) continue;
      const length = edge.getTotalLength();
      for (let distance = 5; distance < length - 5; distance += 5) {
        const p = edge.getPointAtLength(distance);
        const point = new DOMPoint(p.x, p.y).matrixTransform(transform);
        for (const node of nodes) {
          const r = node.getBoundingClientRect();
          if (
            point.x > r.left + 2 &&
            point.x < r.right - 2 &&
            point.y > r.top + 2 &&
            point.y < r.bottom - 2
          ) {
            collisions.push(
              `${edge.dataset.testid} intersects ${node.dataset.testid}`,
            );
          }
        }
      }
    }
    return [...new Set(collisions)];
  });
  expect(intersections).toEqual([]);
  await dialog.getByRole("button", { name: "显示全部依赖", exact: true }).click();
  await page.screenshot({
    path: "../../artifacts/topology-expanded-fault.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await page.getByRole("button", { name: "实时", exact: true }).click();
  await expect(page.getByTestId("fault-location")).toContainText(
    "注入点已恢复",
  );
});
