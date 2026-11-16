#!/usr/bin/env python3
"""Gera um relatório descritivo diário a partir do feed histórico público."""
import json, urllib.request, datetime, pathlib, statistics

GAMES = {"lotofacil": (25, 15), "megasena": (60, 6)}
BASE = "https://raw.githubusercontent.com/maickon/free-apiloterias/refs/heads/master/database/{}/_todos.json"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent":"ECG-Loto-Mega-Stats/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)

def normalize(item):
    nums = item.get("listaDezenas") or item.get("dezenasSorteadasOrdemSorteio") or item.get("dezenas") or []
    contest = item.get("numero") or item.get("numeroDoConcurso") or item.get("concurso")
    date = item.get("dataApuracao") or item.get("dataPorExtenso") or item.get("data") or ""
    try: nums = sorted(int(x) for x in nums)
    except (TypeError, ValueError): return None
    if not contest or not nums: return None
    return {"concurso": int(contest), "data": str(date), "dezenas": nums}

def analyze(game, max_num, draw_count):
    raw = fetch(BASE.format(game))
    if isinstance(raw, dict):
        raw = raw.get("dados") or raw.get("concursos") or raw.get("resultados") or raw.get("lista") or []
    draws = [x for x in (normalize(d) for d in raw) if x]
    draws.sort(key=lambda x: x["concurso"], reverse=True)
    if not draws: raise RuntimeError("feed sem concursos válidos")
    freq = [0] * max_num
    last_seen = [None] * max_num
    for idx, d in enumerate(draws):
        for n in d["dezenas"]:
            if 1 <= n <= max_num:
                freq[n-1] += 1
                if last_seen[n-1] is None: last_seen[n-1] = idx
    top = sorted(range(1, max_num+1), key=lambda n: (-freq[n-1], n))[:15]
    overdue = sorted(range(1, max_num+1), key=lambda n: (-(last_seen[n-1] if last_seen[n-1] is not None else len(draws)), n))[:10]
    sums = [sum(d["dezenas"]) for d in draws]
    evens = [sum(1 for n in d["dezenas"] if n % 2 == 0) for d in draws]
    repeat_counts = [len(set(draws[i]["dezenas"]) & set(draws[i+1]["dezenas"])) for i in range(len(draws)-1)]
    window = draws[:min(100, len(draws))]
    window_freq = [0] * max_num
    for d in window:
        for n in d["dezenas"]: window_freq[n-1] += 1
    avg_even = statistics.mean(evens) if evens else 0
    expected_even = draw_count / 2
    avg_sum = statistics.mean(sums) if sums else 0
    theoretical_sum = draw_count * (max_num + 1) / 2
    observations = [
      {"title":"Equilíbrio pares/ímpares","detail":f"Média observada de {avg_even:.2f} pares por concurso; referência combinatória: {expected_even:.2f}.","type":"context"},
      {"title":"Soma das dezenas","detail":f"Média histórica {avg_sum:.1f}; média teórica sob sorteio uniforme {theoretical_sum:.1f}.","type":"context"},
      {"title":"Repetição entre concursos","detail":f"Média observada de {statistics.mean(repeat_counts):.2f} dezenas repetidas entre concursos consecutivos." if repeat_counts else "Ainda não há pares de concursos suficientes para avaliar repetição.","type":"context"}
    ]
    if len(draws) < 100:
        observations.append({"title":"Amostra histórica curta","detail":f"Foram encontrados {len(draws)} concursos. Evite ajustar pesos com base em amostras pequenas.","type":"caution"})
    else:
        observations.append({"title":"Validação antes de alterar pesos","detail":"Use backtesting temporal, comparando cada regra com sorteios aleatórios e sem usar concursos futuros no treinamento. Frequências e atrasos não são previsões.","type":"recommendation"})
    return {"game":game,"label":"Lotofácil" if game=="lotofacil" else "Mega-Sena","contest":draws[0]["concurso"],"date":draws[0]["data"],"draw_count":len(draws),"top15":[{"number":n,"count":freq[n-1],"last100":window_freq[n-1]} for n in top],"overdue10":[{"number":n,"draws":last_seen[n-1] if last_seen[n-1] is not None else len(draws)} for n in overdue],"average_even":round(avg_even,3),"expected_even":round(expected_even,3),"average_sum":round(avg_sum,3),"theoretical_sum":round(theoretical_sum,3),"average_repeats":round(statistics.mean(repeat_counts),3) if repeat_counts else None,"observations":observations}

def main():
    report={"generated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"source":"Feed público de resultados; o app também consulta a API oficial da Caixa.","notice":"Análise descritiva, não preditiva. Nenhuma frequência ou atraso altera a probabilidade matemática de uma dezena em um sorteio justo.","games":{}}
    errors={}
    for game,(maximum,draw_count) in GAMES.items():
        try: report["games"][game]=analyze(game,maximum,draw_count)
        except Exception as exc: errors[game]=str(exc)
    report["errors"]=errors
    if not report["games"]: raise RuntimeError("Nenhuma modalidade pôde ser analisada: "+json.dumps(errors,ensure_ascii=False))
    out=pathlib.Path("reports/latest.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"generated":list(report["games"]),"errors":errors},ensure_ascii=False))

if __name__=="__main__": main()
