import fs from "node:fs/promises";

const REPORT_PATH = "reports/latest.json";
const OUTPUT_PATH = "data/inteligencia.json";

function recommendation(titulo, prioridade, hipotese, evidencia, backtest, limitacoes, proximo_teste) {
  return { titulo, prioridade, hipotese, evidencia, backtest, limitacoes, proximo_teste };
}

function analyzeGame(game, label) {
  const cfg = game;
  const recent = cfg.frequency_windows?.["30"];
  const previous = cfg.frequency_windows?.["100"];
  const top = cfg.top15 || [];
  const tests = cfg.backtesting || [];
  const bestTest = tests.find(x => x.concursos_teste > 0 && x.media_acertos !== null);
  const windowTop = recent?.top15 || [];
  const sample = Number(cfg.draw_count || 0);
  const recommendations = [];

  recommendations.push(recommendation(
    "Preservar a separação entre histórico e janela recente",
    "Alta",
    "Acompanhar se as frequências recentes diferem do histórico sem transformar oscilações em previsão.",
    "Foram analisados " + sample + " concursos. A janela recente contém " + Number(recent?.concursos || 0) + " concursos; o ranking completo contém " + top.length + " dezenas destacadas.",
    "Análise descritiva; não constitui teste de capacidade preditiva.",
    "Frequências variam naturalmente em sorteios independentes. Rankings podem mudar com o tamanho da janela.",
    "Comparar rankings em janelas de 30, 50 e 100 concursos e registrar a estabilidade antes de qualquer alteração no gerador."
  ));

  if (windowTop.length) {
    const names = windowTop.slice(0, 5).map(x => String(x.number).padStart(2, "0") + " (" + x.count + ")").join(", ");
    recommendations.push(recommendation(
      "Monitorar a concentração do ranking recente",
      "Monitorar",
      "Verificar se as dezenas mais frequentes na janela curta permanecem estáveis em janelas maiores.",
      "Top 5 na janela de " + Number(recent.concursos) + " concursos: " + names + ". Valores representam contagens observadas, não probabilidades futuras.",
      "Comparação descritiva entre contagens; não demonstra vantagem sobre sorteio uniforme.",
      "Janela curta tem maior variabilidade e pode destacar extremos por acaso. Não selecionar dezenas apenas por este ranking.",
      "Recalcular a posição dessas dezenas nas janelas de 50 e 100 concursos e medir a persistência do ranking."
    ));
  }

  if (bestTest) {
    const delta = Number(bestTest.diferenca_vs_baseline || 0);
    const sign = delta > 0 ? "+" : "";
    recommendations.push(recommendation(
      "Acompanhar o backtesting walk-forward",
      "Alta",
      "Manter a avaliação temporal como critério obrigatório antes de aprovar mudanças no método estatístico.",
      "Janela de treinamento " + bestTest.janela_treinamento + "; " + bestTest.concursos_teste + " concursos de teste; média observada " + bestTest.media_acertos + " acertos; referência aleatória esperada " + bestTest.baseline_aleatorio_esperado + "; diferença " + sign + delta + ".",
      "Resultado calculado em sequência temporal, usando somente concursos anteriores no treinamento. A referência informada é a esperança matemática de uma seleção uniforme.",
      "O valor esperado não substitui uma simulação de distribuição nem intervalo de confiança. Diferença observada não comprova superioridade; há risco de sobreajuste e múltiplas comparações.",
      "Executar simulações aleatórias com o mesmo número de testes, calcular distribuição de resultados e repetir em períodos futuros sem reajustar parâmetros."
    ));
  } else {
    recommendations.push(recommendation(
      "Aumentar a base de validação temporal",
      "Média",
      "Ampliar a quantidade de concursos disponíveis para avaliar o método fora da amostra.",
      "Não há janela de backtesting com tamanho suficiente registrada neste relatório.",
      "Backtesting indisponível para esta amostra.",
      "Sem testes temporais suficientes, não é possível avaliar estabilidade ou desempenho relativo.",
      "Acumular histórico e executar walk-forward com janelas predefinidas antes de comparar versões."
    ));
  }

  const experiment = cfg.experimentos_pesquisa || { status: "nao_executado" };
  if (experiment.status === "concluido") {
    const leader = experiment.estrategias?.[experiment.melhor_media_observada];
    const ci = leader?.ic95_diferenca_pareada || [null, null];
    recommendations.push(recommendation(
      "Experimento walk-forward: comparação de estratégias",
      experiment.evidencia === "sinal_positivo_exploratorio" ? "Investigar" : "Manter método atual",
      "Verificar se janelas históricas diferentes ou ponderação de recência superam uma seleção uniforme fora da amostra.",
      "Foram testadas " + experiment.concursos_teste + " previsões históricas. Melhor média observada: " + experiment.melhor_media_observada + " (" + (leader?.media_acertos ?? "n/d") + " acertos por jogo).",
      "Diferença média pareada contra baseline aleatório: " + (leader?.diferenca_media_vs_baseline_simulado ?? "n/d") + "; IC95%: [" + ci.join(", ") + "]. Evidência: " + experiment.evidencia + ".",
      (experiment.limitacoes || []).join(" "),
      "Repetir a hipótese em concursos futuros ainda não usados e em uma segunda janela temporal. Não alterar o gerador antes de validação independente e autorização."
    ));
  } else {
    recommendations.push(recommendation(
      "Laboratório de experimentos: ampliar validação",
      "Aguardando amostra",
      "Executar comparações walk-forward independentes para frequências de 30, 100 e 250 concursos e ponderação de recência.",
      "Status: " + (experiment.status || "indisponível") + ". " + (experiment.nota || ""),
      "Nenhuma conclusão comparativa foi emitida.",
      "Sem amostra mínima, não há base para recomendar mudança no método.",
      "Aguardar histórico suficiente e repetir a execução diária."
    ));
  }

  return {
    resumo: label + ": laboratório estatístico local em " + sample + " concursos. Experimentos independentes e temporais são exploratórios; não preveem sorteios.",
    concursos_analisados: sample,
    fonte: cfg.official_source || "Histórico público validado",
    experimentos: experiment,
    recomendacoes: recommendations,
    aviso: "Sorteios são aleatórios e independentes. Frequência, atraso e padrões históricos não aumentam a probabilidade matemática de ganhar."
  };
}

async function main() {
  const statistics = JSON.parse(await fs.readFile(REPORT_PATH, "utf8"));
  if (!statistics.games?.lotofacil || !statistics.games?.megasena) {
    throw new Error("Relatório estatístico incompleto; publicação bloqueada.");
  }
  const output = {
    schema_version: 3,
    gerado_em: new Date().toISOString(),
    fonte_dados: statistics.source,
    status_ia: "gerado_localmente",
    modelo: "ECG Laboratório Estatístico Local v2",
    metadados: Object.fromEntries(Object.entries(statistics.games).map(([key, value]) =>
      [key, { ultimo_concurso: value.contest, data_ultimo: value.date, concursos_analisados: value.draw_count }])),
    modalidades: {
      lotofacil: analyzeGame(statistics.games.lotofacil, "Lotofácil"),
      megasena: analyzeGame(statistics.games.megasena, "Mega-Sena")
    },
    aviso: "Relatório gerado localmente, sem API paga. Estatística descritiva não é previsão."
  };
  await fs.mkdir("data", { recursive: true });
  await fs.writeFile(OUTPUT_PATH, JSON.stringify(output, null, 2) + "\n", "utf8");
  console.log("Relatório ECG local salvo em " + OUTPUT_PATH + " para Lotofácil e Mega-Sena.");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
