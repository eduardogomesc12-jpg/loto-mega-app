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
    const leaderName = experiment.melhor_variante_vs_aleatorio;
    const leader = experiment.estrategias?.[leaderName];
    const original = experiment.estrategias?.ecg_original;
    const comparisons = Object.entries(experiment.estrategias || {}).map(([name, metrics]) =>
      name + ": média " + metrics.media_acertos_por_jogo + " acertos/jogo; melhor jogo " +
      metrics.media_melhor_jogo_por_concurso + "; concursos com faixa mínima " +
      metrics.concursos_com_algum_jogo_na_faixa_minima_pct + "%."
    ).join(" ");
    const deltas = Object.entries(experiment.estrategias || {})
      .filter(([name]) => name !== "ecg_original" && name !== "aleatorio_uniforme")
      .map(([name, metrics]) => name + " vs ECG original: " +
        (metrics.diferenca_pareada_media_vs_ecg_original > 0 ? "+" : "") +
        metrics.diferenca_pareada_media_vs_ecg_original + " acertos/jogo; IC95% [" +
        (metrics.ic95_diferenca_vs_ecg_original || []).join(", ") + "].")
      .join(" ");
    recommendations.push(recommendation(
      "Comparação completa do gerador ECG com variantes",
      experiment.evidencia === "sinal_positivo_exploratorio" ? "Investigar" : "Manter método atual",
      "Avaliar se alterações de recência, equilíbrio estrutural ou diversificação de portfólio melhoram o desempenho fora da amostra.",
      "Foram avaliados " + experiment.concursos_teste + " concursos, com " + experiment.jogos_por_concurso +
      " jogos por estratégia e 100 candidatos por lote. Melhor variante vs aleatório: " + leaderName +
      " (" + (leader?.media_acertos_por_jogo ?? "n/d") + " acertos/jogo). ECG original: " +
      (original?.media_acertos_por_jogo ?? "n/d") + " acertos/jogo. " + deltas,
      comparisons + " Diferença da melhor variante vs aleatório: " +
      (leader?.diferenca_pareada_media_acertos_vs_aleatorio ?? "n/d") +
      "; IC95% [" + (leader?.ic95_diferenca_media_acertos || []).join(", ") + "]. Evidência: " + experiment.evidencia + ".",
      (experiment.limitacoes || []).join(" "),
      "Replicar as variantes em um período futuro intocado, avaliar intervalos pareados contra o ECG original e corrigir múltiplas comparações. Nenhuma mudança será aplicada sem autorização."
    ));
  } else {
    recommendations.push(recommendation(
      "Laboratório de comparação completa",
      "Aguardando amostra",
      "Comparar o gerador original reproduzido com variantes completas de recência, equilíbrio e diversificação.",
      "Status: " + (experiment.status || "indisponível") + ". " + (experiment.nota || ""),
      "Nenhuma conclusão comparativa foi emitida.",
      "Sem amostra mínima, não há base para recomendar mudança no método.",
      "Aguardar histórico suficiente e executar a comparação temporal."
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
    modelo: "ECG Laboratório Estatístico Local v3",
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
