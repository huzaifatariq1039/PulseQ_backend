import "dotenv/config";
import express from "express";
import cron from "node-cron";

import { scheduleTokenMessages, cronSendDueNotifications, sendQueueAlertNow, sendFinalCallNow } from "./scheduler.js";

const app = express();
app.use(express.json({ limit: "1mb" }));

const port = Number(process.env.PORT || 5055);

app.get("/health", (_req, res) => res.json({ ok: true, service: "pulseq-notification-service" }));

// Schedule token messages (booking confirmation + reminders plan persisted to Firestore)
app.post("/schedule/token", async (req, res) => {
  try {
    const result = await scheduleTokenMessages(req.body || {});
    res.json({ ok: true, result });
  } catch (e) {
    res.status(400).json({ ok: false, error: String(e?.message || e) });
  }
});

// Webhook: queue alert (position <= 4 OR wait_time <= 15)
app.post("/events/queue-alert", async (req, res) => {
  try {
    const { token_id: tokenId, patient_id: patientId, phone } = req.body || {};
    const result = await sendQueueAlertNow({ tokenId, patientId, phone });
    res.json({ ok: true, result });
  } catch (e) {
    res.status(400).json({ ok: false, error: String(e?.message || e) });
  }
});

// Webhook: final call (patient called)
app.post("/events/final-call", async (req, res) => {
  try {
    const { token_id: tokenId, patient_id: patientId, phone } = req.body || {};
    const result = await sendFinalCallNow({ tokenId, patientId, phone });
    res.json({ ok: true, result });
  } catch (e) {
    res.status(400).json({ ok: false, error: String(e?.message || e) });
  }
});

// Manual trigger for cron cycle (useful for debugging)
app.post("/cron/run", async (_req, res) => {
  const result = await cronSendDueNotifications({ limit: Number(process.env.CRON_BATCH_LIMIT || 50) });
  res.json({ ok: true, result });
});

// Cron job: every minute
const cronExpr = process.env.CRON_EXPRESSION || "* * * * *";
cron.schedule(cronExpr, async () => {
  try {
    await cronSendDueNotifications({ limit: Number(process.env.CRON_BATCH_LIMIT || 50) });
  } catch {
    // swallow errors; per-message failures are recorded in Firestore
  }
});

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Notification service listening on :${port} (cron=${cronExpr})`);
});

