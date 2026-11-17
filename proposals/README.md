# Propostas de alteração do método ECG

Cada proposta deve ser um arquivo `<id>.json` e conter:
- `id`, `version_sugerida`, `status` (somente `aprovavel` pode ser aplicada);
- `evidencia.replicacao_confirmada: true`;
- `evidencia.ic95_inferior_vs_ecg_original` maior que zero;
- `modalidades.lotofacil` e `modalidades.megasena`, cada uma com seis `pesos_frequencia` somando 1 e `peso_estrutural` entre 0 e 1;
- justificativa, protocolo, concursos avaliados e limitações.

O workflow bloqueia propostas exploratórias ou sem replicação confirmada. A autorização humana é obrigatória.
