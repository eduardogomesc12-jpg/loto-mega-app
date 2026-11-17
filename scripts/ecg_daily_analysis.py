#!/usr/bin/env python3
"""Relatório estatístico ECG com validação do histórico e atualização incremental pela CAIXA."""
import datetime, json, pathlib, statistics, time, urllib.request

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
    return {"game": game, "label": "Lotofácil" if game == "lotofacil" else "Mega-Sena",
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
