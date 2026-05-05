import { getDb, admin } from "./firebase.js";
import { sendWhatsAppTemplate, sendWhatsAppText } from "./whatsapp.js";

const NOTIFICATIONS_COLLECTION = "notifications_queue";
const MAX_WINDOW_MINUTES = 120;

function asDate(v) {
  if (!v) return null;
  if (v instanceof Date) return v;
  if (typeof v === "number") return new Date(v);
  if (typeof v === "string") {
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  // Firestore Timestamp
  if (typeof v.toDate === "function") return v.toDate();
  return null;
}

function minutesDiff(a, b) {
  return Math.floor((a.getTime() - b.getTime()) / 60000);
}

function nowUtc() {
  return new Date();
}

function buildPlan({ timeDiffMinutes }) {
  // Cap the effective window to MAX_WINDOW_MINUTES as a safety guard.
  const eff = Math.min(timeDiffMinutes, MAX_WINDOW_MINUTES);
  const messages = [];

  // CASE 1: LONG (90–120 mins)
  if (eff >= 90) {
    messages.push({ type: "confirmation", sendAt: "now" });
    messages.push({ type: "reminder_90", offsetMinutes: 90 });
    messages.push({ type: "reminder_60", offsetMinutes: 60 });
    messages.push({ type: "reminder_45", offsetMinutes: 45 });
    messages.push({ type: "final_call", offsetMinutes: 30 });
    messages.push({ type: "reminder_20", offsetMinutes: 20 });
    messages.push({ type: "reminder_15", offsetMinutes: 15 });
    messages.push({ type: "turn_approaching", offsetMinutes: 1 });
    // Dynamic events (queue + doctor ready + final)
    messages.push({ type: "queue_alert", dynamic: true, sendAt: "on_queue_alert" });
    messages.push({ type: "doctor_ready", dynamic: true, sendAt: "on_doctor_ready" });
    messages.push({ type: "final_call_dynamic", dynamic: true, sendAt: "on_called" });
  } else if (eff >= 30) {
    // CASE 2: MEDIUM (30–90 mins)
    messages.push({ type: "confirmation", sendAt: "now" });
    messages.push({ type: "final_call", offsetMinutes: 30 });
    messages.push({ type: "reminder_20", offsetMinutes: 20 });
    messages.push({ type: "reminder_15", offsetMinutes: 15 });
    messages.push({ type: "turn_approaching", offsetMinutes: 1 });
    messages.push({ type: "queue_alert", dynamic: true, sendAt: "on_queue_alert" });
    messages.push({ type: "final_call_dynamic", dynamic: true, sendAt: "on_called" });
  } else {
    // CASE 3: SHORT (< 30 mins)
    messages.push({ type: "confirmation", sendAt: "now" });
    messages.push({ type: "final_call", offsetMinutes: 25 }); // If short, send soon
    messages.push({ type: "turn_approaching", offsetMinutes: 1 });
    messages.push({ type: "queue_alert", dynamic: true, sendAt: "on_queue_alert" });
    messages.push({ type: "doctor_ready", dynamic: true, sendAt: "on_doctor_ready" });
    messages.push({ type: "final_call_dynamic", dynamic: true, sendAt: "on_called" });
  }

  // Enforce hard cap on total planned messages
  if (messages.length > 10) {
    return messages.slice(0, 10);
  }
  return messages;
}

function shouldSendNow(sendAt) {
  return sendAt === "now";
}

function computeSendAt({ appointmentTime, planItem }) {
  if (planItem.sendAt === "now") return nowUtc();
  if (typeof planItem.offsetMinutes === "number") {
    return new Date(appointmentTime.getTime() - planItem.offsetMinutes * 60000);
  }
  // Event-driven items are stored but won’t be auto-sent by cron; they’re sent via webhooks.
  return null;
}

export async function scheduleTokenMessages(token) {
  const db = getDb();
  const patientId = String(token.patient_id || token.patientId || "").trim();
  const phone = String(token.phone || "").trim();
  const tokenId = String(token.token_id || token.tokenId || token.id || "").trim();
  const appointmentTime = asDate(token.appointment_time || token.appointmentTime);
  const queuePosition = Number(token.queue_position ?? token.queuePosition ?? null);

  if (!patientId || !phone || !appointmentTime) {
    throw new Error("Missing patient_id, phone, or appointment_time");
  }

  const now = nowUtc();
  const rawDiffMin = minutesDiff(appointmentTime, now);
  // Cap time diff to MAX_WINDOW_MINUTES per spec
  const diffMin = Math.min(rawDiffMin, MAX_WINDOW_MINUTES);
  const plan = buildPlan({ timeDiffMinutes: diffMin });

  // Write pending notifications to Firestore.
  const batch = db.batch();
  const col = db.collection(NOTIFICATIONS_COLLECTION);

  const createdAt = admin.firestore.FieldValue.serverTimestamp();
  const tokenRef = tokenId ? db.collection("tokens").doc(tokenId) : null;

  const docsToCreate = [];
  for (const item of plan) {
    const sendAt = computeSendAt({ appointmentTime, planItem: item });
    // Skip invalid / past-due times (except "now" which will be immediate)
    if (sendAt && sendAt.getTime() <= now.getTime() && !shouldSendNow(item.sendAt)) continue;

    const ref = col.doc();
      const doc = {
      token_id: tokenId || null,
      token_ref: tokenRef || null,
      patient_id: patientId,
      phone,
      queue_position: Number.isFinite(queuePosition) ? queuePosition : null,
      appointment_time: appointmentTime,
      type: item.type,
      send_at: sendAt, // null for event-driven items
      status: "pending",
      attempts: 0,
      last_error: null,
      created_at: createdAt,
      updated_at: createdAt,
    };
    batch.set(ref, doc);
    docsToCreate.push({ id: ref.id, ...doc });
  }

  await batch.commit();

  // Send immediate confirmation now (best effort) by enqueuing as due.
  // We keep it in Firestore as pending; cron will pick it up immediately as well.
  return { scheduled: docsToCreate.length, time_diff_minutes: diffMin };
}

async function getTokenStatus({ tokenId, tokenRef }) {
  const db = getDb();
  let snap = null;
  if (tokenRef) snap = await tokenRef.get();
  else if (tokenId) snap = await db.collection("tokens").doc(tokenId).get();
  if (!snap?.exists) return { exists: false, status: null, data: {} };
  const t = snap.data() || {};
  const status = String(t.status || "").toLowerCase();
  return { exists: true, status, data: t };
}

async function cancelPendingForToken(tokenId, reason) {
  const db = getDb();
  if (!tokenId) return;
  const col = db.collection(NOTIFICATIONS_COLLECTION);
  const now = admin.firestore.FieldValue.serverTimestamp();
  const pending = await col.where("token_id", "==", tokenId).where("status", "==", "pending").get();
  const batch = db.batch();
  pending.forEach((doc) => {
    batch.update(doc.ref, { status: "cancelled", cancel_reason: reason || "stop_condition", updated_at: now });
  });
  await batch.commit();
}

function isStopStatus(status) {
  const s = String(status || "").toLowerCase();
  return (
    s === "in_consultation" ||
    s === "completed" ||
    s === "cancelled" ||
    s === "rescheduled"
  );
}

async function sendOneNotification(docSnap) {
  const db = getDb();
  const data = docSnap.data() || {};
  const tokenId = data.token_id || null;
  const tokenRef = data.token_ref || null;

  // STOP CONDITIONS
  if (tokenId || tokenRef) {
    const { exists, status } = await getTokenStatus({ tokenId, tokenRef });
    if (exists && isStopStatus(status)) {
      await cancelPendingForToken(tokenId, status);
      await docSnap.ref.update({
        status: "cancelled",
        cancel_reason: status,
        updated_at: admin.firestore.FieldValue.serverTimestamp(),
      });
      return { skipped: true, reason: `stop:${status}` };
    }
  }

  const phone = data.phone;
  const type = String(data.type || "");

  // Template vs text: reminders use template by default; alerts/final use text.
  if (type.startsWith("reminder") || type === "immediate_confirmation") {
    await sendWhatsAppTemplate({
      to: phone,
      templateName: process.env.WHATSAPP_TEMPLATE_NAME || "appointment_reminder",
      languageCode: process.env.WHATSAPP_TEMPLATE_LANGUAGE || "en",
    });
  } else if (type === "turn_approaching") {
    const { data: tokenData } = await getTokenStatus({ tokenId, tokenRef });
    const patientName = tokenData.patient_name || tokenData.patientName || "Patient";
    await sendWhatsAppTemplate({
      to: phone,
      templateName: "patient_call_alert",
      languageCode: "en", // or appropriate language
      components: [
        {
          type: "body",
          parameters: [{ type: "text", text: String(patientName) }],
        },
      ],
    });
  } else if (type === "queue_alert") {
    await sendWhatsAppText({ to: phone, text: "Your turn is near. Please reach hospital." });
  } else if (type === "final_call" || type === "final_call_dynamic") {
    const { data: tokenData } = await getTokenStatus({ tokenId, tokenRef });
    const patientName = tokenData.patient_name || tokenData.patientName || "Patient";
    const tokenNumber = tokenData.token_number || tokenData.tokenNumber || tokenData.formatted_token || "";
    
    await sendWhatsAppTemplate({
      to: phone,
      templateName: "final_alert",
      languageCode: "en", // or appropriate language
      components: [
        {
          type: "body",
          parameters: [
            { type: "text", text: String(patientName) },
            { type: "text", text: String(tokenNumber) }
          ],
        },
      ],
    });
  } else {
    await sendWhatsAppText({ to: phone, text: "Appointment update." });
  }

  await docSnap.ref.update({
    status: "sent",
    sent_at: admin.firestore.FieldValue.serverTimestamp(),
    updated_at: admin.firestore.FieldValue.serverTimestamp(),
    last_error: null,
  });
  return { sent: true };
}

export async function cronSendDueNotifications({ limit = 50 } = {}) {
  const db = getDb();
  const col = db.collection(NOTIFICATIONS_COLLECTION);
  const now = nowUtc();

  // We intentionally avoid composite-index-heavy queries; this can be indexed later.
  const pending = await col.where("status", "==", "pending").get();
  const due = [];
  pending.forEach((doc) => {
    const d = doc.data() || {};
    const sendAt = asDate(d.send_at);
    if (!sendAt) return; // event-driven
    if (sendAt.getTime() <= now.getTime()) due.push(doc);
  });

  due.sort((a, b) => {
    const da = asDate(a.data()?.send_at)?.getTime() || 0;
    const dbb = asDate(b.data()?.send_at)?.getTime() || 0;
    return da - dbb;
  });

  const sliced = due.slice(0, limit);
  let sent = 0;
  let failed = 0;
  let cancelled = 0;

  for (const doc of sliced) {
    try {
      const res = await sendOneNotification(doc);
      if (res?.sent) sent += 1;
      else if (res?.skipped) cancelled += 1;
    } catch (err) {
      failed += 1;
      const data = doc.data() || {};
      const attempts = Number(data.attempts || 0) + 1;
      const maxAttempts = 3; // initial + 2 retries
      const update = {
        attempts,
        last_error: {
          code: err?.code || "ERROR",
          message: String(err?.message || err),
          details: err?.details || null,
          at: admin.firestore.FieldValue.serverTimestamp(),
        },
        updated_at: admin.firestore.FieldValue.serverTimestamp(),
      };

      if (attempts >= maxAttempts) {
        update.status = "failed";
        update.failed_at = admin.firestore.FieldValue.serverTimestamp();
      } else {
        // Retry in 1 minute
        update.send_at = new Date(Date.now() + 60 * 1000);
      }

      await doc.ref.update(update);
    }
  }

  return { processed: sliced.length, sent, failed, cancelled };
}

// -------------------- Event-driven sends --------------------
export async function sendQueueAlertNow({ tokenId, patientId, phone }) {
  const db = getDb();
  if (!phone) throw new Error("Missing phone");

  // Stop conditions (token status)
  if (tokenId) {
    const { exists, status } = await getTokenStatus({ tokenId, tokenRef: null });
    if (exists && isStopStatus(status)) {
      await cancelPendingForToken(tokenId, status);
      return { skipped: true, reason: `stop:${status}` };
    }
  }

  await sendWhatsAppText({ to: phone, text: "Your turn is near. Please reach hospital." });

  // Persist as an audit row
  await db.collection(NOTIFICATIONS_COLLECTION).add({
    token_id: tokenId || null,
    patient_id: patientId || null,
    phone,
    type: "queue_alert",
    send_at: nowUtc(),
    status: "sent",
    sent_at: admin.firestore.FieldValue.serverTimestamp(),
    attempts: 1,
    created_at: admin.firestore.FieldValue.serverTimestamp(),
    updated_at: admin.firestore.FieldValue.serverTimestamp(),
    source: "event",
  });

  return { sent: true };
}

export async function sendFinalCallNow({ tokenId, patientId, phone }) {
  const db = getDb();
  if (!phone) throw new Error("Missing phone");

  if (tokenId) {
    const { exists, status } = await getTokenStatus({ tokenId, tokenRef: null });
    if (exists && isStopStatus(status)) {
      await cancelPendingForToken(tokenId, status);
      return { skipped: true, reason: `stop:${status}` };
    }
  }

  const { data: tokenData } = await getTokenStatus({ tokenId, tokenRef: null });
  const patientName = tokenData.patient_name || tokenData.patientName || "Patient";
  const tokenNumber = tokenData.token_number || tokenData.tokenNumber || tokenData.formatted_token || "";

  await sendWhatsAppTemplate({
    to: phone,
    templateName: "final_alert",
    languageCode: "en",
    components: [
      {
        type: "body",
        parameters: [
          { type: "text", text: String(patientName) },
          { type: "text", text: String(tokenNumber) }
        ],
      },
    ],
  });

  await db.collection(NOTIFICATIONS_COLLECTION).add({
    token_id: tokenId || null,
    patient_id: patientId || null,
    phone,
    type: "final_call",
    send_at: nowUtc(),
    status: "sent",
    sent_at: admin.firestore.FieldValue.serverTimestamp(),
    attempts: 1,
    created_at: admin.firestore.FieldValue.serverTimestamp(),
    updated_at: admin.firestore.FieldValue.serverTimestamp(),
    source: "event",
  });

  return { sent: true };
}

