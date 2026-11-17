import importlib.util
import unittest

spec = importlib.util.spec_from_file_location("ecg", "scripts/ecg_daily_analysis.py")
ecg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ecg)

class FullGeneratorExperimentTests(unittest.TestCase):
    def test_original_and_variants_generate_three_unique_valid_games(self):
        cfg = {"max": 25, "draw": 15}
        history = [{"concurso": i + 1, "data": str(i),
                    "dezenas": sorted(((i + j) % 25) + 1 for j in range(15))}
                   for i in range(260)]
        for variant in ("ecg_original", "recencia_reforcada",
                        "equilibrio_estrutural", "diversificacao_portfolio"):
            first = ecg._generate_portfolio(history, cfg, variant, 12345, 3)
            second = ecg._generate_portfolio(history, cfg, variant, 12345, 3)
            self.assertEqual(first, second)
            self.assertEqual(len(first), 3)
            self.assertEqual(len({tuple(game) for game in first}), 3)
            for game in first:
                self.assertEqual(len(game), 15)
                self.assertEqual(len(set(game)), 15)
                self.assertTrue(all(1 <= number <= 25 for number in game))

    def test_portfolio_metrics_count_minimum_hits(self):
        portfolio = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        actual = {1, 2, 3, 4}
        metrics = ecg._portfolio_metrics(portfolio, actual, 3)
        self.assertEqual(metrics["media_acertos"], 4 / 3)
        self.assertEqual(metrics["melhor_acerto"], 3)
        self.assertEqual(metrics["jogos_com_faixa_minima"], 1)
        self.assertEqual(metrics["algum_jogo_com_faixa_minima"], 1)

class ExpectedEvenTests(unittest.TestCase):
    def test_lotofacil_expectation_is_7_2(self):
        self.assertAlmostEqual(ecg.expected_even({"max": 25, "draw": 15}), 7.2)
    def test_megasena_expectation_is_3(self):
        self.assertAlmostEqual(ecg.expected_even({"max": 60, "draw": 6}), 3.0)
    def test_walk_forward_uses_prior_draws_only(self):
        cfg = {"max": 25, "draw": 15}
        draws = [{"concurso": i + 1, "data": str(i), "dezenas": list(range(1, 16))} for i in range(40)]
        result = ecg.walk_forward(draws, cfg, 30)
        self.assertEqual(result["concursos_teste"], 10)
        self.assertAlmostEqual(result["baseline_aleatorio_esperado"], 9.0)

if __name__ == "__main__": unittest.main()
