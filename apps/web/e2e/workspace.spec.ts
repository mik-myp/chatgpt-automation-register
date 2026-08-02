import { expect, test } from "@playwright/test"

test("pipeline list restores URL state and clamps invalid pages", async ({
  page,
}) => {
  await page.goto("/pipelines?status=completed&page=999")

  await expect(page.getByRole("heading", { name: "流水线轮次" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "轮次状态" })).toContainText(
    "已完成"
  )
  await expect(page).toHaveURL(/\/pipelines\?status=completed$/)

  await page.reload()
  await expect(page.getByRole("combobox", { name: "轮次状态" })).toContainText(
    "已完成"
  )
})

test("security dialog keeps its actions visible on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/pipelines")
  await page
    .getByRole("button", { name: "修改密码与 MFA", exact: true })
    .click()

  const dialog = page.getByRole("dialog")
  await expect(dialog).toBeVisible()
  await expect(
    dialog.getByRole("button", { name: /创建安全流水线/ })
  ).toBeVisible()
  await expect(dialog.getByRole("button", { name: "取消" })).toBeVisible()
})

test("pipeline detail tabs are URL-backed", async ({ page }) => {
  await page.route("**/api/pipelines/runs/test-run", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        id: "test-run",
        kind: "registration",
        source_pipeline_run_id: null,
        status: "completed",
        mode: "single",
        target_count: 1,
        kakao_enabled: false,
        config_snapshot: {},
        scheduled_count: 1,
        registered_count: 1,
        failed_count: 0,
        kakao_task_count: 0,
        started_at: null,
        finished_at: null,
        created_at: "2026-08-02T00:00:00Z",
        updated_at: "2026-08-02T00:00:00Z",
        items: [],
        cards: [],
      },
    })
  })
  await page.route("**/api/pipelines/runs/test-run/events?**", (route) =>
    route.fulfill({ json: { items: [], last_sequence: 0, terminal: true } })
  )
  await page.route("**/api/pipelines/runs/test-run/deliveries?**", (route) =>
    route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } })
  )
  await page.route("**/api/kakao/tasks?**", (route) =>
    route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } })
  )

  await page.goto("/pipelines/test-run?tab=events")
  await expect(page.getByRole("tab", { name: "运行日志" })).toHaveAttribute(
    "data-state",
    "active"
  )

  await page.getByRole("tab", { name: "Kakao 任务" }).click()
  await expect(page).toHaveURL(/\?tab=kakao$/)
})
