// Caçador de Oportunidades — despertador no Cloudflare (plano gratuito).
//
// O agendador do GitHub atrasa ou salta muitas execuções. Este Worker tem um Cron Trigger
// de 15 em 15 minutos que pede ao GitHub para correr o workflow "cacador.yml" (como o botão
// "Run workflow") com agendada=true: o bot só vai aos sites se já passou o tempo da regra
// "De quanto em quanto tempo procurar". O "schedule" do workflow fica como reserva.
//
// Variáveis (Settings > Variables and secrets), do tipo "Secret":
//   GITHUB_TOKEN      token fine-grained só deste repositório, com Actions: Read and write
// Opcionais (Secret): TELEGRAM_TOKEN e TELEGRAM_CHAT_ID. Com eles o Worker:
//   - avisa (1 vez por dia, às 9h de Lisboa) se o despertador estiver a falhar;
//   - recebe os botões do bot do Telegram (webhook em /telegram): "🔄 Procurar agora" pede ao
//     GitHub uma procura imediata (ignora o intervalo das regras) com resumo no fim.
//   Depois de pôr os segredos, abre uma vez https://<worker>.workers.dev/instalar.
// Opcional (texto): REPO, por omissão tigreman263/cacador-oportunidades.
//
// Abrir o endereço do Worker (https://<worker>.workers.dev) mostra se está bem configurado.

const REPO_OMISSAO = "tigreman263/cacador-oportunidades";
const WORKFLOW = "cacador.yml";
const RAMO = "main";

export default {
  async scheduled(evento, env, ctx) {
    ctx.waitUntil(despertar(env));
  },

  async fetch(pedido, env) {
    const url = new URL(pedido.url);
    if (pedido.method === "POST" && url.pathname === "/telegram") {
      if (!env.TELEGRAM_TOKEN || pedido.headers.get("X-Telegram-Bot-Api-Secret-Token") !== await segredoWebhook(env)) {
        return new Response("proibido", { status: 403 });
      }
      try { await tratarUpdate(env, await pedido.json()); } catch (e) { console.log("erro no update: " + e.message); }
      return new Response("ok"); // sempre 200, senão o Telegram repete o mesmo update
    }
    const texto = t => new Response(t, { headers: { "content-type": "text/plain; charset=utf-8" } });
    if (pedido.method === "GET" && url.pathname === "/instalar") return texto(await instalar(env, url));
    if (pedido.method !== "GET" || url.pathname !== "/") return new Response("não encontrado", { status: 404 });
    return texto(await estado(env));
  },
};

const repo = env => env.REPO || REPO_OMISSAO;

async function gh(env, caminho, opcoes = {}) {
  if (!env.GITHUB_TOKEN) throw new Error("falta o segredo GITHUB_TOKEN");
  const r = await fetch("https://api.github.com" + caminho, {
    method: opcoes.method || "GET",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: "Bearer " + env.GITHUB_TOKEN,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "cacador-despertador",
      ...(opcoes.body ? { "Content-Type": "application/json" } : {}),
    },
    body: opcoes.body ? JSON.stringify(opcoes.body) : undefined,
  });
  if (!r.ok) throw new Error(`GitHub respondeu ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.status === 204 ? null : r.json();
}

async function despertar(env) {
  try {
    await gh(env, `/repos/${repo(env)}/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST", body: { ref: RAMO, inputs: { agendada: "true" } },
    });
  } catch (e) {
    console.log("despertador falhou: " + e.message);
    const { hora, minuto } = horaLisboa();
    if (hora === 9 && minuto < 15) {
      await avisarTelegram(env, "⚠️ O despertador do Caçador de Oportunidades está a falhar:\n" + e.message);
    }
  }
}

// ------------------------------------------------------------------ bot do Telegram
const BOTAO_PROCURAR = "🔄 Procurar agora";
const TECLADO = { reply_markup: { keyboard: [[{ text: BOTAO_PROCURAR }]], resize_keyboard: true, is_persistent: true } };

async function segredoWebhook(env) {
  // Derivado do token do bot: só quem tem o token sabe o valor (o Telegram envia-o em cada pedido).
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("cacador-webhook:" + env.TELEGRAM_TOKEN));
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 48);
}

async function telegram(env, metodo, dados) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/${metodo}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  const j = await r.json().catch(() => ({}));
  if (!j.ok) throw new Error(`${metodo}: ${j.description || r.status}`);
  return j.result;
}

const chatsAutorizados = env => String(env.TELEGRAM_CHAT_ID || "").split(",").map(s => s.trim()).filter(Boolean);

async function tratarUpdate(env, u) {
  const msg = u.message || {};
  const chat = String((msg.chat || {}).id || "");
  if (!chat || !chatsAutorizados(env).includes(chat)) return; // só os teus chats
  const t = (msg.text || "").trim();
  if (t === BOTAO_PROCURAR || /^\/procurar(@\w+)?$/.test(t)) {
    try {
      await gh(env, `/repos/${repo(env)}/actions/workflows/${WORKFLOW}/dispatches`, {
        method: "POST", body: { ref: RAMO, inputs: { resumo: "true" } },
      });
      await telegram(env, "sendMessage", { chat_id: chat, text: "🔄 A procurar agora em todas as procuras ativas. Demora 1 a 2 minutos: no fim recebes as oportunidades novas ou um resumo.", ...TECLADO });
    } catch (e) {
      await telegram(env, "sendMessage", { chat_id: chat, text: "⚠️ Não consegui pedir a procura ao GitHub: " + e.message, ...TECLADO });
    }
  } else if (/^\/(start|ajuda)/.test(t)) {
    await telegram(env, "sendMessage", { chat_id: chat, text: "Olá! Recebes aqui as boas oportunidades.\n\n• " + BOTAO_PROCURAR + ": procura já, sem esperar pelo despertador.\n• 📊 Painel (ao lado da caixa de texto): ver e mudar as procuras.", ...TECLADO });
  }
}

async function instalar(env, url) {
  if (!env.TELEGRAM_TOKEN || !env.TELEGRAM_CHAT_ID) return "❌ Faltam os segredos TELEGRAM_TOKEN e TELEGRAM_CHAT_ID.";
  const linhas = [];
  await telegram(env, "setWebhook", { url: `${url.origin}/telegram`, secret_token: await segredoWebhook(env), allowed_updates: ["message"] });
  linhas.push("✅ Bot ligado a este Worker (" + url.origin + "/telegram)");
  await telegram(env, "setMyCommands", { commands: [{ command: "procurar", description: "Procurar agora" }, { command: "ajuda", description: "O que este bot faz" }] });
  linhas.push("✅ Comandos /procurar e /ajuda");
  for (const chat of chatsAutorizados(env)) {
    await telegram(env, "sendMessage", { chat_id: chat, text: "✅ Botão \"" + BOTAO_PROCURAR + "\" ativado. Carrega nele quando quiseres uma procura imediata.", ...TECLADO });
  }
  linhas.push("✅ Botão enviado para o teu chat");
  return linhas.join("\n");
}

async function estado(env) {
  const linhas = ["Caçador de Oportunidades — despertador", `Repositório: ${repo(env)}`, ""];
  try {
    const w = await gh(env, `/repos/${repo(env)}/actions/workflows/${WORKFLOW}`);
    linhas.push(`✅ Ligação ao GitHub: OK (workflow "${w.name}", ${w.state})`);
    const runs = await gh(env, `/repos/${repo(env)}/actions/workflows/${WORKFLOW}/runs?per_page=5`);
    linhas.push("", "Últimas execuções:");
    for (const r of runs.workflow_runs) {
      linhas.push(`  ${r.created_at}  ${r.event}  ${r.conclusion || r.status}`);
    }
  } catch (e) {
    linhas.push("❌ " + e.message);
  }
  linhas.push("", env.TELEGRAM_TOKEN && env.TELEGRAM_CHAT_ID
    ? "Avisos de falha no Telegram: ligados" : "Avisos de falha no Telegram: desligados (opcional)");
  return linhas.join("\n");
}

async function avisarTelegram(env, texto) {
  if (!env.TELEGRAM_TOKEN || !env.TELEGRAM_CHAT_ID) return;
  for (const chat of String(env.TELEGRAM_CHAT_ID).split(",").map(s => s.trim()).filter(Boolean)) {
    await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendMessage`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chat, text: texto }),
    }).catch(() => {});
  }
}

function horaLisboa() {
  const p = new Intl.DateTimeFormat("pt-PT", { timeZone: "Europe/Lisbon", hour: "numeric", minute: "numeric", hourCycle: "h23" })
    .formatToParts(new Date());
  const v = t => Number(p.find(x => x.type === t)?.value);
  return { hora: v("hour"), minuto: v("minute") };
}
