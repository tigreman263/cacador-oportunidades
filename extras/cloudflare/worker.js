// Caçador de Oportunidades — despertador no Cloudflare (plano gratuito).
//
// O agendador do GitHub atrasa ou salta muitas execuções. Este Worker tem um Cron Trigger
// de 15 em 15 minutos que pede ao GitHub para correr o workflow "cacador.yml" (como o botão
// "Run workflow") com agendada=true: o bot só vai aos sites se já passou o tempo da regra
// "De quanto em quanto tempo procurar". O "schedule" do workflow fica como reserva.
//
// Variáveis (Settings > Variables and secrets), do tipo "Secret":
//   GITHUB_TOKEN      token fine-grained só deste repositório, com Actions: Read and write
// Opcionais (Secret): TELEGRAM_TOKEN e TELEGRAM_CHAT_ID, para avisar (1 vez por dia, às 9h
//   de Lisboa) se o despertador estiver a falhar.
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
    if (pedido.method !== "GET" || url.pathname !== "/") return new Response("não encontrado", { status: 404 });
    return new Response(await estado(env), { headers: { "content-type": "text/plain; charset=utf-8" } });
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
