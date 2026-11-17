import fs from "node:fs/promises";

const REPORT_PATH = "reports/latest.json";
const OUTPUT_PATH = "data/inteligencia.json";
const MODEL = process.env.OPENAI_MODEL || "gpt-4.1-mini";
const reportSchema = {
  type: "object", additionalProperties: false,
  required: ["resumo", "concursos_analisados", "fonte", "recomendacoes", "aviso"],
  properties: {
    resumo: { type: "string" }, concursos_analisados: { type: "integer" },
    fonte: { type: "string" }, aviso: { type: "string" },
    recomendacoes: { type: "array", items: {
      type: "object", additionalProperties: false,
      required: ["titulo", "prioridade", "hipotese", "evidencia", "backtest", "limitacoes", "proximo_teste"],
      properties: {
        titulo: { type: "string" }, prioridade: { type: "string", enum: ["Alta", "Média", "Baixa", "Monitorar"] },
        hipotese: { type: "string" }, evidencia: { type: "string" }, backtest: { type: "string" },
        limitacoes: { type: "string" }, proximo_teste: { type: "string" }
      }
    }}
  }
};

function extractOutputText(response) {
  if (typeof response.output_text === "string") return response.output_text;
  for (const item of response.output ?? []) {
    if (item.type !== "message") continue;
    for (const content of item.content ?? []) {
      if (content.type === "output_text" && typeof content.text === "string") return content.text;
    }
  }
  throw new Error("A API respondeu sem conteúdo textual estruturado.");
}

async function generateWithOpenAI(data) {
  const instructions = [
    "Você é o analista estatístico do ECG Loto & Mega.",
    "Use exclusivamente os números e resultados contidos no relatório local fornecido.",
    "Produza de 1 a 3 recomendações acionáveis por modalidade; se não houver evidência, diga isso explicitamente.",
    "Cada recomendação deve incluir hipótese, evidência, métrica de backtest, limitações, risco de regressão e próximo teste.",
    "Não afirme que frequência, atraso, pares/ímpares ou qualquer padrão prevê resultados ou aumenta a chance matemática de ganhar.",
    "Não invente métricas, fontes, significância ou concursos. Diferencie qualidade de software de suposta vantagem preditiva.",
    "Avalie tamanho da amostra, múltiplas comparações, sobreajuste e vazamento temporal."
  ].join(" ");

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: { Authorization: "Bearer " + process.env.OPENAI_API_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: MODEL, instructions,
      input: "Data de geração: " + new Date().toISOString() + "\nRelatório estatístico validado localmente:\n" + JSON.stringify(data),
      text: { format: { type: "json_schema", name: "ecg_statistical_report", strict: true,
        schema: { type: "object", additionalProperties: false, required: ["modalidades"],
          properties: { modalidades: { type: "object", additionalProperties: false,
            required: ["lotofacil", "megasena"], properties: { lotofacil: reportSchema, megasena: reportSchema }
          }}
        }
      }},
      max_output_tokens: 5000
    })
  });
  if (!response.ok) throw new Error("OpenAI HTTP " + response.status + ": " + (await response.text()).slice(0, 1200));
  return JSON.parse(extractOutputText(await response.json()));
}

async function main() {
  const statistics = JSON.parse(await fs.readFile(REPORT_PATH, "utf8"));
  if (!statistics.games?.lotofacil || !statistics.games?.megasena) throw new Error("Relatório estatístico incompleto; IA não será executada.");
  const output = {
    schema_version: 2, gerado_em: new Date().toISOString(), fonte_dados: statistics.source,
    status_ia: "aguardando_configuracao", modelo: MODEL,
    metadados: Object.fromEntries(Object.entries(statistics.games).map(([key, value]) =>
      [key, { ultimo_concurso: value.contest, data_ultimo: value.date, concursos_analisados: value.draw_count }])),
    modalidades: null,
    aviso: "Frequências e atrasos são descritivos e não aumentam a probabilidade matemática de ganhar."
  };
  if (process.env.OPENAI_API_KEY) {
    output.modalidades = (await generateWithOpenAI(statistics)).modalidades;
    output.status_ia = "gerado";
  } else {
    output.aviso_ia = "Configure OPENAI_API_KEY em Settings > Secrets and variables > Actions para ativar a análise generativa. Nunca insira a chave no código ou no navegador.";
    console.warn("OPENAI_API_KEY ausente: relatório local será publicado; IA ficará aguardando o Secret.");
  }
  await fs.mkdir("data", { recursive: true });
  await fs.writeFile(OUTPUT_PATH, JSON.stringify(output, null, 2) + "\n", "utf8");
  console.log("Relatório ECG salvo em " + OUTPUT_PATH + " (IA: " + output.status_ia + ").");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
