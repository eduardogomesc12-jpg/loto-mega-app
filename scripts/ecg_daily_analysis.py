#!/usr/bin/env python3
"""Relatório estatístico ECG com validação do histórico e atualização incremental pela CAIXA."""
import datetime, json, pathlib, statistics, time, urllib.request, math

GAMES = {"lotofacil": {"max": 25, "draw": 15}, "megasena": {"max": 60, "draw": 6}}
FEED = "https://raw.githubusercontent.com/maickon/free-apiloterias/refs/heads/master/database/{}/_todos.json"
CAIXA = "https://servicebus2.caixa.gov.br/portaldeloterias/api"

def get_json(url, attempts=3):
    last = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ECG-Loto-Mega/2.0", "Accept": "application/json, text/plain, */*"})
            with urllib.request.urlopen(req, timeout=35) as response:
                return json.load(response)
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Falha ao consultar {url}: {last}")

def normalize(item, cfg):
    if not isinstance(item, dict): return None
    raw = item.get("listaDezenas") or item.get("dezenasSorteadasOrdemSorteio") or item.get("dezenas") or []
    contest = item.get("numero") or item.get("numeroDoConcurso") or item.get("concurso")
    date = item.get("dataApuracao") or item.get("dataPorExtenso") or item.get("data") or ""
    try:
        numbers = [int(value) for value in raw]
        contest = int(contest)
    except (TypeError, ValueError): return None
    if contest < 1 or len(numbers) != cfg["draw"] or len(set(numbers)) != cfg["draw"]: return None
    if any(number < 1 or number > cfg["max"] for number in numbers): return None
    return {"concurso": contest, "data": str(date), "dezenas": sorted(numbers)}

def collect(game, cfg):
    raw = get_json(FEED.format(game))
    if isinstance(raw, dict):
        raw = raw.get("dados") or raw.get("concursos") or raw.get("resultados") or raw.get("lista") or []
    if not isinstance(raw, list): raise RuntimeError(f"Formato inesperado do histórico de {game}")
    records = {}
    for item in raw:
        draw = normalize(item, cfg)
        if draw: records[draw["concurso"]] = draw
    if not records: raise RuntimeError(f"Histórico vazio ou inválido: {game}")
    official = normalize(get_json(f"{CAIXA}/{game}"), cfg)
    if not official: raise RuntimeError(f"Último resultado oficial inválido: {game}")
    feed_latest = max(records)
    if official["concurso"] < feed_latest:
        raise RuntimeError(f"Feed {game} está à frente da CAIXA: {feed_latest} > {official['concurso']}")
    for contest in range(feed_latest + 1, official["concurso"] + 1):
        draw = official if contest == official["concurso"] else normalize(get_json(f"{CAIXA}/{game}/{contest}"), cfg)
        if not draw or draw["concurso"] != contest:
            raise RuntimeError(f"Não foi possível validar o concurso {contest} de {game}")
        records[contest] = draw
        time.sleep(0.08)
    ordered = sorted(records.values(), key=lambda item: item["concurso"])
    missing = [number for number in range(ordered[0]["concurso"], official["concurso"] + 1) if number not in records]
    if missing: raise RuntimeError(f"Histórico {game} contém lacunas; primeiros concursos ausentes: {missing[:10]}")
    if ordered[-1]["concurso"] != official["concurso"] or ordered[-1]["dezenas"] != official["dezenas"]:
        raise RuntimeError(f"Conferência do último concurso falhou: {game}")
    return ordered, official, feed_latest

def expected_even(cfg):
    return cfg["draw"] * (cfg["max"] // 2) / cfg["max"]

def walk_forward(draws, cfg, window, max_tests=100):
    results = []
    first_test = max(window, len(draws) - max_tests)
    for test_index in range(first_test, len(draws)):
        training = draws[max(0, test_index - window):test_index]
        if len(training) < window: continue
        freq = [0] * cfg["max"]
        for draw in training:
            for number in draw["dezenas"]: freq[number - 1] += 1
        selected = sorted(range(1, cfg["max"] + 1), key=lambda number: (-freq[number - 1], number))[:cfg["draw"]]
        results.append(len(set(selected) & set(draws[test_index]["dezenas"])))
    mean = statistics.mean(results) if results else None
    baseline = cfg["draw"] * cfg["draw"] / cfg["max"]
    return {"janela_treinamento": window, "concursos_teste": len(results),
        "media_acertos": round(mean, 4) if mean is not None else None,
        "baseline_aleatorio_esperado": round(baseline, 4),
        "diferenca_vs_baseline": round(mean - baseline, 4) if mean is not None else None,
        "periodo_teste": [draws[first_test]["data"], draws[-1]["data"]] if results else None,
        "regra": "Treinamento usa somente concursos anteriores ao concurso testado; empate resolvido pela menor dezena."}


def _bootstrap_ci(values, seed, rounds=2000):
    if not values: return [None, None]
    rng = __import__("random").Random(seed)
    n = len(values)
    means = sorted(statistics.mean(values[rng.randrange(n)] for _ in range(n)) for _ in range(rounds))
    return [round(means[int(0.025 * rounds)], 4), round(means[min(rounds - 1, int(0.975 * rounds))], 4)]

def _round2(value):
    return math.floor(value * 100 + 0.5) / 100

def _profile_ecg(history, cfg, profile_weights):
    maximum = cfg["max"]
    def count(rows):
        freq = [0] * maximum
        for draw in rows:
            for number in draw["dezenas"]:
                freq[number - 1] += 1
        return freq
    columns = [count(history), count(history[:30]), count(history[:20]),
               count(history[:15]), count(history[:10]), count(history[:100])]
    maxima = [max([1] + col) for col in columns]
    profile = []
    for i in range(maximum):
        components = [columns[j][i] / maxima[j] * 100 for j in range(6)]
        score = sum(profile_weights[j] * components[j] for j in range(6))
        profile.append({"n": i + 1, "score": _round2(score), "components": components})
    return profile

def _score_context(history, cfg):
    if cfg['max'] == 25:
        return {'latest': history[0] if history else None}
    sums = [sum(draw['dezenas']) for draw in history]
    mean = statistics.mean(sums) if sums else cfg['draw'] * (cfg['max'] + 1) / 2
    variance = statistics.pvariance(sums) if sums else 1
    repeat_counts = []
    for i in range(len(history) - 1):
        previous = set(history[i + 1]['dezenas'])
        repeat_counts.append(sum(number in previous for number in history[i]['dezenas']))
    return {'latest': history[0] if history else None, 'sum_mean': mean,
            'sum_sd': math.sqrt(max(1, variance)),
            'repeat_mean': statistics.mean(repeat_counts) if repeat_counts else 0.6}

def _candidate_score(numbers, profile, history, cfg, structural_weight, context=None):
    context = context or _score_context(history, cfg)
    by_number = {item['n']: item['score'] for item in profile}
    base = sum(by_number.get(number, 0) for number in numbers)
    even_count = sum(number % 2 == 0 for number in numbers)
    parity_score = max(0, 100 - abs(even_count - cfg['draw'] / 2) * 20)
    latest = context['latest']
    repeats = sum(number in latest['dezenas'] for number in numbers) if latest else 0
    if cfg['max'] == 25:
        structural = sum([
            max(0, 100 - abs(even_count - 7.5) * 20),
            max(0, 100 - abs(sum(numbers) - 195) * 1.2),
            max(0, 100 - abs(repeats - 9) * 12)
        ]) / 3
    else:
        sum_score = max(0, 100 - abs(sum(numbers) - context['sum_mean']) / context['sum_sd'] * 18)
        repeat_score = max(0, 100 - abs(repeats - context['repeat_mean']) * 20)
        structural = (parity_score + sum_score + repeat_score) / 3
    return _round2(base * (1 - structural_weight) + structural * structural_weight)

def _generate_portfolio(history, cfg, variant, seed, qty=3):
    """Reprodução estatística do makeGames() do app; não modifica o gerador de produção."""
    import random
    rng = random.Random(seed)
    original_weights = [0.35, 0.20, 0.15, 0.10, 0.10, 0.10]
    if variant == "ecg_original":
        profile_weights, structural_weight, diversity_penalty = original_weights, 0.30, 0.0
    elif variant == "recencia_reforcada":
        profile_weights, structural_weight, diversity_penalty = [0.20, 0.30, 0.20, 0.10, 0.05, 0.15], 0.30, 0.0
    elif variant == "equilibrio_estrutural":
        profile_weights, structural_weight, diversity_penalty = original_weights, 0.40, 0.0
    elif variant == "diversificacao_portfolio":
        profile_weights, structural_weight, diversity_penalty = original_weights, 0.30, 2.0
    else:
        raise ValueError("Variante desconhecida: " + variant)
    profile = _profile_ecg(history, cfg, profile_weights)
    context = _score_context(history, cfg)
    candidates, seen = [], set()
    for _ in range(100):
        keys = [{"n": item["n"], "key": rng.random() ** (1 / max(0.01, item["score"]))} for item in profile]
        keys.sort(key=lambda item: -item["key"])
        numbers = sorted(item["n"] for item in keys[:cfg["draw"]])
        key = "-".join(map(str, numbers))
        if key not in seen:
            seen.add(key)
            candidates.append({"dezenas": numbers, "score": _candidate_score(numbers, profile, history, cfg, structural_weight, context)})
    candidates.sort(key=lambda item: -item["score"])
    if diversity_penalty == 0:
        return [item["dezenas"] for item in candidates[:qty]]
    selected, remaining = [], candidates[:]
    while remaining and len(selected) < qty:
        best_index, best_value = 0, None
        for index, candidate in enumerate(remaining):
            overlap = max([len(set(candidate["dezenas"]) & set(old)) for old in selected] or [0])
            adjusted = candidate["score"] - diversity_penalty * overlap
            if best_value is None or adjusted > best_value:
                best_index, best_value = index, adjusted
        selected.append(remaining.pop(best_index)["dezenas"])
    return selected

def _random_portfolio(cfg, seed, qty=3):
    import random
    rng = random.Random(seed)
    portfolio, seen = [], set()
    while len(portfolio) < qty:
        numbers = sorted(rng.sample(range(1, cfg["max"] + 1), cfg["draw"]))
        key = tuple(numbers)
        if key not in seen:
            seen.add(key)
            portfolio.append(numbers)
    return portfolio

def _portfolio_metrics(portfolio, actual, prize_threshold):
    hits = [len(set(ticket) & actual) for ticket in portfolio]
    return {"media_acertos": statistics.mean(hits), "melhor_acerto": max(hits),
            "jogos_com_faixa_minima": sum(value >= prize_threshold for value in hits),
            "algum_jogo_com_faixa_minima": int(any(value >= prize_threshold for value in hits))}

def research_experiments(draws, cfg, game):
    """Compara o gerador real reproduzido e variantes completas em walk-forward."""
    import random
    max_tests = min(180, max(0, len(draws) - 250))
    if max_tests < 40:
        return {"status": "amostra_insuficiente", "concursos_teste": max_tests,
                "nota": "São necessários ao menos 40 concursos de teste após 250 concursos de treinamento."}
    variants = ["ecg_original", "recencia_reforcada", "equilibrio_estrutural", "diversificacao_portfolio"]
    records = {name: [] for name in variants + ["aleatorio_uniforme"]}
    first = len(draws) - max_tests
    prize_threshold = 11 if game == "lotofacil" else 4
    for idx in range(first, len(draws)):
        history = list(reversed(draws[:idx]))
        actual = set(draws[idx]["dezenas"])
        contest = draws[idx]["concurso"]
        if len(history) < 250: continue
        for name in variants:
            portfolio = _generate_portfolio(history, cfg, name, contest * 1009 + cfg["max"], 3)
            records[name].append(_portfolio_metrics(portfolio, actual, prize_threshold))
        random_portfolio = _random_portfolio(cfg, contest * 1009 + cfg["max"] + 7919, 3)
        records["aleatorio_uniforme"].append(_portfolio_metrics(random_portfolio, actual, prize_threshold))
    baseline = records["aleatorio_uniforme"]
    summary = {}
    for name in variants + ["aleatorio_uniforme"]:
        rows = records[name]
        mean_hits = [row["media_acertos"] for row in rows]
        best_hits = [row["melhor_acerto"] for row in rows]
        threshold_rates = [row["algum_jogo_com_faixa_minima"] for row in rows]
        paired_mean = [rows[i]["media_acertos"] - baseline[i]["media_acertos"] for i in range(len(rows))] if name != "aleatorio_uniforme" else [0.0] * len(rows)
        paired_best = [rows[i]["melhor_acerto"] - baseline[i]["melhor_acerto"] for i in range(len(rows))] if name != "aleatorio_uniforme" else [0.0] * len(rows)
        original_rows = records["ecg_original"]
        paired_original = [rows[i]["media_acertos"] - original_rows[i]["media_acertos"] for i in range(len(rows))] if name not in ("ecg_original", "aleatorio_uniforme") else [0.0] * len(rows)
        summary[name] = {
            "media_acertos_por_jogo": round(statistics.mean(mean_hits), 4),
            "media_melhor_jogo_por_concurso": round(statistics.mean(best_hits), 4),
            "concursos_com_algum_jogo_na_faixa_minima_pct": round(statistics.mean(threshold_rates) * 100, 3),
            "media_jogos_na_faixa_minima_por_concurso": round(statistics.mean(row["jogos_com_faixa_minima"] for row in rows), 4),
            "diferenca_pareada_media_acertos_vs_aleatorio": round(statistics.mean(paired_mean), 4),
            "ic95_diferenca_media_acertos": _bootstrap_ci(paired_mean, sum(map(ord, name)) + len(draws)),
            "diferenca_pareada_melhor_jogo_vs_aleatorio": round(statistics.mean(paired_best), 4),
            "ic95_diferenca_melhor_jogo": _bootstrap_ci(paired_best, sum(map(ord, name)) + len(draws) + 31),
            "diferenca_pareada_media_vs_ecg_original": round(statistics.mean(paired_original), 4),
            "ic95_diferenca_vs_ecg_original": _bootstrap_ci(paired_original, sum(map(ord, name)) + len(draws) + 67),
            "vitorias_vs_ecg_original": sum(value > 0 for value in paired_original),
            "empates_vs_ecg_original": sum(value == 0 for value in paired_original),
            "derrotas_vs_ecg_original": sum(value < 0 for value in paired_original),
            "concursos_teste": len(rows)
        }
    deltas = {name: summary[name]["diferenca_pareada_media_acertos_vs_aleatorio"] for name in variants}
    leader = max(variants, key=lambda name: deltas[name])
    ci = summary[leader]["ic95_diferenca_media_acertos"]
    if ci[0] is not None and ci[0] > 0:
        evidence = "sinal_positivo_exploratorio"
    elif ci[1] is not None and ci[1] < 0:
        evidence = "desempenho_inferior_ao_aleatorio"
    else:
        evidence = "inconclusiva"
    return {
        "status": "concluido",
        "desenho": "Walk-forward por concurso: todo o histórico anterior disponível; 100 candidatos por lote; 3 jogos finais por estratégia; todos avaliados no mesmo resultado futuro. Parâmetros fixos antes do período de teste.",
        "concursos_teste": len(baseline),
        "periodo_teste": [draws[first]["data"], draws[-1]["data"]],
        "limiar_faixa_minima": prize_threshold,
        "jogos_por_concurso": 3,
        "candidatos_por_estrategia": 100,
        "estrategias": summary,
        "melhor_variante_vs_aleatorio": leader,
        "diferencas_variantes_vs_gerador_original": {
            name: round(summary[name]["media_acertos_por_jogo"] - summary["ecg_original"]["media_acertos_por_jogo"], 4)
            for name in variants if name != "ecg_original"
        },
        "evidencia": evidence,
        "decisao": "Nenhuma alteração automática. Uma variante só deve ser considerada após replicação em período futuro intocado, análise de múltiplas comparações e autorização explícita.",
        "fidelidade": [
            "O baseline reproduz o scoreProfile do app: pesos 35/20/15/10/10/10 para histórico completo, 30, 20, 15, 10 e 100 concursos.",
            "Reproduz candidateScore da Lotofácil e da Mega-Sena, 100 candidatos, sorteio ponderado, remoção de duplicatas e seleção dos 3 maiores scores.",
            "A sequência aleatória é reproduzível por semente; a distribuição do sorteio ponderado corresponde ao algoritmo do navegador, mas não é a mesma sequência de Math.random()."
        ],
        "limitacoes": [
            "O experimento testa o padrão de 3 jogos, que é o padrão inicial da interface; outros tamanhos de lote podem produzir métricas diferentes.",
            "A janela de teste é a mais recente e serve como validação retrospectiva exploratória; deve haver um período futuro intocado para confirmação.",
            "O limiar de faixa mínima é apenas referência de acertos (11+ Lotofácil; 4+ Mega-Sena), não cálculo de prêmio ou rentabilidade.",
            "Sorteios são independentes; desempenho histórico não implica vantagem futura."
        ]
    }

def analyze(game, cfg, draws, official, feed_latest):
    newest = list(reversed(draws))
    max_num, draw_count = cfg["max"], cfg["draw"]
    freq, delay = [0] * max_num, [len(newest)] * max_num
    for index, draw in enumerate(newest):
        for number in draw["dezenas"]:
            freq[number - 1] += 1
            if delay[number - 1] == len(newest): delay[number - 1] = index
    ranking = sorted(range(1, max_num + 1), key=lambda n: (-freq[n - 1], n))
    windows = {}
    for size in (30, 50, 100):
        subset, counts = newest[:min(size, len(newest))], [0] * max_num
        for draw in subset:
            for number in draw["dezenas"]: counts[number - 1] += 1
        windows[str(size)] = {"concursos": len(subset), "top15": [{"number": n, "count": counts[n - 1]} for n in sorted(range(1, max_num + 1), key=lambda n: (-counts[n - 1], n))[:15]]}
    sums = [sum(d["dezenas"]) for d in draws]
    even_counts = [sum(n % 2 == 0 for n in d["dezenas"]) for d in draws]
    low_counts = [sum(n <= max_num // 2 for n in d["dezenas"]) for d in draws]
    repeats = [len(set(draws[i]["dezenas"]) & set(draws[i - 1]["dezenas"])) for i in range(1, len(draws))]
    ranges = [max(d["dezenas"]) - min(d["dezenas"]) for d in draws]
    band_size, bands = (max_num + 1) // 5, {}
    for start in range(1, max_num + 1, band_size):
        end = min(max_num, start + band_size - 1)
        bands[f"{start:02d}-{end:02d}"] = sum(sum(start <= n <= end for n in d["dezenas"]) for d in draws)
    backtests = [walk_forward(draws, cfg, w) for w in (30, 100, 250) if len(draws) > w]
    average_even = statistics.mean(even_counts)
    observations = [
        {"title": "Equilíbrio pares/ímpares", "detail": f"Média observada de {average_even:.2f} pares; expectativa combinatória {expected_even(cfg):.2f}.", "type": "context"},
        {"title": "Integridade do histórico", "detail": f"CAIXA confirmou o concurso {official['concurso']} ({official['data']}); histórico validado com {len(draws)} concursos.", "type": "context"},
        {"title": "Backtesting temporal", "detail": "Comparação walk-forward contra a esperança de seleção uniforme; diferenças pequenas não demonstram vantagem preditiva.", "type": "recommendation"}]
    experiments = research_experiments(draws, cfg, game)
    return {"game": game, "label": "Lotofácil" if game == "lotofacil" else "Mega-Sena",
        "experimentos_pesquisa": experiments,
        "contest": official["concurso"], "date": official["data"], "draw_count": len(draws),
        "feed_previous_latest": feed_latest, "history_gap_filled": official["concurso"] - feed_latest,
        "official_source": f"{CAIXA}/{game}",
        "top15": [{"number": n, "count": freq[n - 1], "last100": next((x["count"] for x in windows["100"]["top15"] if x["number"] == n), 0)} for n in ranking[:15]],
        "overdue10": [{"number": n, "draws": delay[n - 1]} for n in sorted(range(1, max_num + 1), key=lambda n: (-delay[n - 1], n))[:10]],
        "frequency_windows": windows, "average_even": round(average_even, 3), "expected_even": round(expected_even(cfg), 3),
        "average_low": round(statistics.mean(low_counts), 3), "average_high": round(draw_count - statistics.mean(low_counts), 3),
        "average_sum": round(statistics.mean(sums), 3), "sum_stddev": round(statistics.pstdev(sums), 3),
        "average_range": round(statistics.mean(ranges), 3), "average_repeats": round(statistics.mean(repeats), 3) if repeats else None,
        "distribution_by_band": bands, "backtesting": backtests, "observations": observations}

def main():
    report = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Feed histórico público com conferência do último concurso e preenchimento incremental via endpoint público do Portal Loterias CAIXA.",
        "notice": "Estatística descritiva, não preditiva. Frequência e atraso não alteram a probabilidade matemática de sorteios futuros.",
        "games": {}, "errors": {}}
    for game, cfg in GAMES.items():
        try:
            draws, official, feed_latest = collect(game, cfg)
            report["games"][game] = analyze(game, cfg, draws, official, feed_latest)
        except Exception as exc: report["errors"][game] = str(exc)
    if len(report["games"]) != len(GAMES):
        raise RuntimeError("Relatório incompleto; publicação bloqueada para evitar dados desatualizados: " + json.dumps(report["errors"], ensure_ascii=False))
    output = pathlib.Path("reports/latest.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"games": {k: {"contest": v["contest"], "count": v["draw_count"]} for k, v in report["games"].items()}, "errors": report["errors"]}, ensure_ascii=False))

if __name__ == "__main__": main()
