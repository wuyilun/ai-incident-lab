import { expect, test } from "@playwright/test";

test("operator injects an incident, observes recovery, and replays history", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "故障有迹，恢复有据。" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "注入故障", exact: true }).click();
  await expect(page.getByTestId("incident-status")).toHaveText("已恢复", {
    timeout: 45000,
  });
  await expect(
    page.getByText("独立评估：恢复通过", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("worker / connection_leak", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("SOP-CONNECTION-PRESSURE-001", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/console-desktop.png",
    fullPage: true,
  });
  await page.getByLabel("回放进度").fill("0");
  await expect(page.getByTestId("incident-status")).toHaveText("故障演化中");
  await expect(page.getByText("等待诊断证据", { exact: true })).toBeVisible();
  await expect(
    page.getByText("独立评估：恢复通过", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "实时", exact: true }).click();
  await expect(
    page.getByText("独立评估：恢复通过", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("worker / connection_leak", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../../artifacts/console-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});

test("manual alert response and cancellation", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("告警后自动响应").uncheck();
  await page.getByRole("button", { name: "注入故障", exact: true }).click();
  await expect(page.getByTestId("incident-status")).toHaveText("告警触发", {
    timeout: 20000,
  });
  await expect(
    page.getByRole("button", { name: "启动 Agent", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "停止", exact: true }).click();
  await expect(page.getByTestId("incident-status")).toHaveText("已取消");
  await expect(
    page.getByText("独立评估：未通过", { exact: true }),
  ).toBeVisible();
});
