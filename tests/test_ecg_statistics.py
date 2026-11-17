import importlib.util
import unittest

spec = importlib.util.spec_from_file_location("ecg", "scripts/ecg_daily_analysis.py")
ecg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ecg)

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
