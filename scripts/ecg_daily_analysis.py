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

def _block_bootstrap_ci(values, seed, confidence=0.95, block_size=10, rounds=3000):
    """IC por bootstrap de blocos móveis para reduzir a falsa precisão temporal."""
    import random
    if not values: return [None, None]
    rng = random.Random(seed)
    n = len(values)
    block_size = max(1, min(block_size, n))
    means = []
    blocks_needed = math.ceil(n / block_size)
    for _ in range(rounds):
        sample = []
        for _ in range(blocks_needed):
            start = rng.randrange(max(1, n - block_size + 1))
            sample.extend(values[start:start + block_size])
        means.append(statistics.mean(sample[:n]))
    means.sort()
    alpha = (1 - confidence) / 2
    low = means[max(0, int(alpha * rounds))]
    high = means[min(rounds - 1, int((1 - alpha) * rounds))]
    return [round(low, 4), round(high, 4)]


def research_experiments(draws, cfg, game):
    """Backtest multi-seed, temporalmente separado e com confirmação final intocada."""
    variants = ["ecg_original", "recencia_reforcada", "equilibrio_estrutural", "diversificacao_portfolio"]
    seed_ids = [11, 23, 37, 53, 71]
    max_tests = min(180, max(0, len(draws) - 250))
    if max_tests < 120:
        return {"status": "amostra_insuficiente", "concursos_teste": max_tests,
                "nota": "São necessários 250 concursos de treino e ao menos 120 testes para separar descoberta e confirmação."}

    first = len(draws) - max_tests
    split = max(60, int(max_tests * 2 / 3))
    split = min(split, max_tests - 60)
    discovery_indices = list(range(first, first + split))
    confirmation_indices = list(range(first + split, len(draws)))
    prize_threshold = 11 if game == "lotofacil" else 4
    # Uma média por concurso, agregada sobre as mesmas cinco sementes para cada método.
    records = {name: [] for name in variants + ["aleatorio_uniforme"]}
    seed_records = {name: {seed: [] for seed in seed_ids} for name in variants}
    for idx in range(first, len(draws)):
        history = list(reversed(draws[:idx]))
        actual = set(draws[idx]["dezenas"])
        contest = draws[idx]["concurso"]
        if len(history) < 250: continue
        for name in variants:
            per_seed = []
            for seed_id in seed_ids:
                seed = contest * 1009 + cfg["max"] * 17 + seed_id * 7919
                portfolio = _generate_portfolio(history, cfg, name, seed, 3)
                metric = _portfolio_metrics(portfolio, actual, prize_threshold)
                per_seed.append(metric)
                seed_records[name][seed_id].append(metric["media_acertos"])
            records[name].append({
                "media_acertos": statistics.mean(x["media_acertos"] for x in per_seed),
                "melhor_acerto": statistics.mean(x["melhor_acerto"] for x in per_seed),
                "jogos_na_faixa": statistics.mean(x["jogos_com_faixa_minima"] for x in per_seed),
                "algum_faixa": statistics.mean(x["algum_jogo_com_faixa_minima"] for x in per_seed)
            })
        random_metrics = []
        for seed_id in seed_ids:
            random_seed = contest * 1009 + cfg["max"] * 17 + seed_id * 104729 + 7919
            random_metrics.append(_portfolio_metrics(_random_portfolio(cfg, random_seed, 3), actual, prize_threshold))
        records["aleatorio_uniforme"].append({
            "media_acertos": statistics.mean(x["media_acertos"] for x in random_metrics),
            "melhor_acerto": statistics.mean(x["melhor_acerto"] for x in random_metrics),
            "jogos_na_faixa": statistics.mean(x["jogos_com_faixa_minima"] for x in random_metrics),
            "algum_faixa": statistics.mean(x["algum_jogo_com_faixa_minima"] for x in random_metrics)
        })

    if len(records["ecg_original"]) != max_tests:
        return {"status": "erro_amostra", "concursos_teste": len(records["ecg_original"]),
                "nota": "Quantidade efetiva de concursos difere da janela planejada."}

    def summarize(values):
        return round(statistics.mean(values), 4) if values else None

    summary = {}
    for name in variants + ["aleatorio_uniforme"]:
        rows = records[name]
        summary[name] = {
            "media_acertos_por_jogo": summarize([x["media_acertos"] for x in rows]),
            "media_melhor_jogo_por_concurso": summarize([x["melhor_acerto"] for x in rows]),
            "pct_concursos_com_algum_jogo_faixa_minima": round(statistics.mean(x["algum_faixa"] for x in rows) * 100, 3),
            "media_jogos_faixa_minima_por_concurso": summarize([x["jogos_na_faixa"] for x in rows]),
            "concursos_teste": len(rows)
        }

    comparisons = {}
    for name in variants:
        all_delta = [records[name][i]["media_acertos"] - records["ecg_original"][i]["media_acertos"] for i in range(max_tests)]
        discovery_delta = [all_delta[i] for i in range(split)]
        confirmation_delta = [all_delta[i] for i in range(split, max_tests)]
        seed_deltas = []
        for seed_id in seed_ids:
            candidate = seed_records[name][seed_id]
            original = seed_records["ecg_original"][seed_id]
            seed_deltas.append(statistics.mean(candidate[i] - original[i] for i in range(max_tests)))
        # Bonferroni: três variantes candidatas comparadas ao ECG original.
        comparisons[name] = {
            "diferenca_media_vs_ecg_original": summarize(all_delta),
            "ic95_bootstrap_blocos_vs_original": _block_bootstrap_ci(all_delta, sum(map(ord, name)) + len(draws)),
            "descoberta_diferenca_media": summarize(discovery_delta),
            "confirmacao_diferenca_media": summarize(confirmation_delta),
            "ic98_33_bootstrap_blocos_confirmacao": _block_bootstrap_ci(confirmation_delta, sum(map(ord, name)) + len(draws) + 101, confidence=0.9833333333),
            "sementes_com_diferenca_positiva": sum(x > 0 for x in seed_deltas),
            "diferencas_por_semente": [round(x, 4) for x in seed_deltas],
            "vitorias": sum(x > 0 for x in all_delta),
            "empates": sum(x == 0 for x in all_delta),
            "derrotas": sum(x < 0 for x in all_delta)
        }

    # Desempenho contra aleatório, com IC por blocos e cinco réplicas do baseline.
    random_comparison = {}
    for name in variants:
        delta = [records[name][i]["media_acertos"] - records["aleatorio_uniforme"][i]["media_acertos"] for i in range(max_tests)]
        random_comparison[name] = {
            "diferenca_media_vs_aleatorio": summarize(delta),
            "ic95_bootstrap_blocos": _block_bootstrap_ci(delta, sum(map(ord, name)) + len(draws) + 211)
        }

    reproducible = {}
    for name in variants[1:]:
        c = comparisons[name]
        ci = c["ic98_33_bootstrap_blocos_confirmacao"]
        reproducible[name] = bool(
            c["descoberta_diferenca_media"] is not None and c["descoberta_diferenca_media"] > 0
            and c["confirmacao_diferenca_media"] is not None and c["confirmacao_diferenca_media"] > 0
            and ci[0] is not None and ci[0] > 0
            and c["sementes_com_diferenca_positiva"] >= 4
        )
    winners = [name for name, passed in reproducible.items() if passed]
    decision = ("candidata_a_aprovacao_humana" if winners else
                "manter_gerador_original_sem_evidencia_reproduzivel")
    return {
        "status": "concluido",
        "protocolo": "ECG-ROBUST-1",
        "desenho": "Walk-forward com 250+ concursos anteriores por previsão; cinco sementes fixas por estratégia; 100 candidatos e três jogos finais; descoberta cronológica seguida de bloco final de confirmação intocado; bootstrap de blocos móveis de 10 concursos; IC de 98,33% na confirmação para controlar três comparações (Bonferroni).",
        "concursos_teste": max_tests,
        "concursos_descoberta": split,
        "concursos_confirmacao_intocada": max_tests - split,
        "periodo_teste": [draws[first]["data"], draws[-1]["data"]],
        "periodo_confirmacao": [draws[first + split]["data"], draws[-1]["data"]],
        "sementes_independentes": seed_ids,
        "jogos_por_concurso": 3,
        "candidatos_por_estrategia": 100,
        "limiar_faixa_minima": prize_threshold,
        "estrategias": summary,
        "comparacao_pareada_vs_original": comparisons,
        "comparacao_vs_aleatorio": random_comparison,
        "variantes_com_evidencia_reproduzivel": winners,
        "status_reprodutibilidade": reproducible,
        "decisao": decision,
        "regra_promocao": "Exige diferença positiva na descoberta e confirmação, limite inferior do IC 98,33% por blocos acima de zero na confirmação e resultado positivo em pelo menos quatro das cinco sementes. Ainda requer replicação prospectiva e autorização humana.",
        "fidelidade": [
            "O baseline preserva os pesos 35/20/15/10/10/10, peso estrutural 0,30, score, 100 candidatos e seleção dos três maiores scores conforme a implementação reproduzida do app.",
            "As variantes alteram somente parâmetros explicitados e são avaliadas nos mesmos concursos e sementes pareadas.",
            "O gerador de produção não é alterado por este experimento; sementes reproduzem o motor de pesquisa, não a sequência Math.random() do navegador."
        ],
        "limitacoes": [
            "O bloco de confirmação é retrospectivo e só fica verdadeiramente prospectivo quando concursos futuros forem adicionados sem reajuste de parâmetros.",
            "Bootstrap em blocos reduz dependência local, mas não torna sorteios ou janelas temporalmente independentes.",
            "Cinco sementes medem sensibilidade à aleatoriedade do gerador, não constituem cinco amostras independentes de sorteios.",
            "Múltiplas variantes e métricas ainda podem gerar descobertas ocasionais; só a métrica primária (média de acertos por jogo) determina a regra de promoção.",
            "Frequência e estrutura histórica não alteram a probabilidade matemática de uma combinação em sorteios independentes."
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
