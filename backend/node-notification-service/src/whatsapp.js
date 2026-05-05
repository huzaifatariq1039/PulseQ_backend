import axios from "axios";

function normalizeToE164(phone) {
  if (!phone) return null;
  const digits = String(phone).replace(/[^\d]/g, "");
  if (!digits) return null;
  // Convenience: Pakistan local 03xxxxxxxxx -> +92xxxxxxxxxx
  if (digits.startsWith("03") && digits.length === 11) return `+92${digits.slice(1)}`;
  if (digits.startsWith("923")) return `+${digits}`;
  if (String(phone).startsWith("+")) return String(phone);
  return `+${digits}`;
}

export async function sendWhatsAppTemplate({
  to,
  templateName = "appointment_reminder",
  languageCode = "en",
  components,
}) {
  const token = process.env.WHATSAPP_ACCESS_TOKEN;
  const phoneNumberId = process.env.WHATSAPP_PHONE_NUMBER_ID;
  if (!token || !phoneNumberId) {
    const err = new Error("WhatsApp API not configured (missing WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID)");
    err.code = "WA_NOT_CONFIGURED";
    throw err;
  }

  const recipient = normalizeToE164(to);
  if (!recipient) {
    const err = new Error("Invalid phone number");
    err.code = "WA_INVALID_PHONE";
    throw err;
  }

  const url = `https://graph.facebook.com/v18.0/${phoneNumberId}/messages`;
  const payload = {
    messaging_product: "whatsapp",
    to: recipient,
    type: "template",
    template: {
      name: templateName,
      language: { code: languageCode },
      ...(components ? { components } : {}),
    },
  };

  const resp = await axios.post(url, payload, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    timeout: 15000,
    validateStatus: () => true,
  });

  if (resp.status < 200 || resp.status >= 300) {
    const err = new Error(`WhatsApp API failed (${resp.status})`);
    err.code = "WA_API_ERROR";
    err.details = resp.data;
    err.httpStatus = resp.status;
    throw err;
  }

  return { success: true, status: resp.status, data: resp.data, to: recipient };
}

export async function sendWhatsAppText({ to, text }) {
  const token = process.env.WHATSAPP_ACCESS_TOKEN;
  const phoneNumberId = process.env.WHATSAPP_PHONE_NUMBER_ID;
  if (!token || !phoneNumberId) {
    const err = new Error("WhatsApp API not configured (missing WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID)");
    err.code = "WA_NOT_CONFIGURED";
    throw err;
  }

  const recipient = normalizeToE164(to);
  if (!recipient) {
    const err = new Error("Invalid phone number");
    err.code = "WA_INVALID_PHONE";
    throw err;
  }

  const url = `https://graph.facebook.com/v18.0/${phoneNumberId}/messages`;
  const payload = {
    messaging_product: "whatsapp",
    to: recipient,
    type: "text",
    text: { preview_url: false, body: String(text || "").slice(0, 4096) },
  };

  const resp = await axios.post(url, payload, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    timeout: 15000,
    validateStatus: () => true,
  });

  if (resp.status < 200 || resp.status >= 300) {
    const err = new Error(`WhatsApp API failed (${resp.status})`);
    err.code = "WA_API_ERROR";
    err.details = resp.data;
    err.httpStatus = resp.status;
    throw err;
  }

  return { success: true, status: resp.status, data: resp.data, to: recipient };
}

