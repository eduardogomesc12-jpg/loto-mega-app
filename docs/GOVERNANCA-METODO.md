# Governança de alterações do método ECG

## Fluxo
1. O laboratório diário analisa Lotofácil e Mega-Sena de forma independente.
2. Uma hipótese é comparada ao método original e à referência aleatória.
3. Uma proposta precisa de replicação em período intocado e IC95% pareado com limite inferior acima de zero para ser elegível.
4. A proposta é registrada em `proposals/<id>.json`.
5. O responsável abre **Actions → ECG - aplicar melhoria autorizada ou restaurar backup → Run workflow**, escolhe `apply`, informa o ID e digita exatamente `AUTORIZO-ECG`.
6. O workflow valida os parâmetros, cria backup da versão anterior, atualiza o histórico, executa testes e publica somente se tudo passar.
7. Para restaurar, escolhe `restore`, informa uma versão existente em `backups/metodos` e confirma novamente.

## Backup e trilha de auditoria
- `data/metodo-aprovado.json`: método atualmente usado pelo aplicativo.
- `backups/metodos/<versão>.json`: cópia imutável dos parâmetros antes de uma promoção.
- `data/historico-versoes.json`: eventos de aplicação e restauração.
- Git preserva cada commit e permite comparar/recuperar arquivos anteriores.

## Limitação de IA gratuita
O repositório executa análises estatísticas locais, sem API paga. O prompt em `prompts/analista-estatistico-ecg.md` padroniza a análise por um modelo de linguagem, mas a chamada automática a um LLM externo não está habilitada: isso exigiria um serviço/modelo com acesso e limites próprios. Não se deve chamar o motor local de IA generativa. Uma proposta produzida manualmente pelo ChatGPT também precisa cumprir os mesmos critérios e passar pelo workflow de autorização.
